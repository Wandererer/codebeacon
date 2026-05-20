"""Recursive file collector with ignore patterns and hash caching."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

from codebeacon.discover.ignore import IgnoreMatcher

IGNORE_DIRS: set[str] = {
    "node_modules",
    ".git",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    "out",
    ".output",
    "coverage",
    ".turbo",
    ".vercel",
    ".codebeacon",
    ".codesight",
    ".ai-codex",
    "vendor",
    ".cache",
    ".parcel-cache",
    ".gradle",
    "target",           # Maven/Cargo build output
    ".idea",
    ".vscode",
    "tmp",
    "temp",
    ".DS_Store",
    "bin",
    "obj",              # .NET build output
    ".bundle",          # Ruby bundler
    "public",           # usually static assets
    ".terraform",
    # Sensitive credential / secret directories — always skip even when they
    # don't start with `.` (so the hidden-dir rule below doesn't cover them).
    # Mirrors graphify's _SENSITIVE_DIRS hardening (graphify 0.8.12).
    "secrets",
    "credentials",
    ".ssh",
    ".aws",
    ".gnupg",
}

# File basenames that should never be indexed even if their extension matches
# CODE_EXTENSIONS — they almost certainly hold credentials. Underscore-prefixed
# variants (api_token.txt, oauth_token.json) are also caught by the regex in
# ``_is_sensitive_filename`` so we don't need to enumerate every spelling.
_SENSITIVE_BASENAMES: set[str] = {
    "credentials",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}

# Substring (with word-boundary or underscore boundary) match for sensitive
# tokens in file basenames: ``api_token.txt``, ``OAuth_Token.json``,
# ``slack-secret.yml``, ``private_key.pem`` — anything that mentions a
# credential keyword should be skipped even if the extension is otherwise a
# code one (e.g. ``.json`` for Cargo manifests). The pattern is intentionally
# narrow: it must be at the start of the basename or follow ``[-_.]`` so we
# don't match e.g. ``token_bucket.ts`` or ``mysecretweapon.ts``.
import re as _re
_SENSITIVE_NAME_RE = _re.compile(
    r"(?:^|[-_.])(?:api[-_]?key|api[-_]?token|oauth[-_]?token|"
    r"access[-_]?token|refresh[-_]?token|secret[-_]?key|"
    r"private[-_]?key|client[-_]?secret)"
    r"(?=[-_.]|$)",
    _re.IGNORECASE,
)


def _is_sensitive_filename(name: str) -> bool:
    """Return True if ``name`` looks like a credential file.

    Used at file-collection time to skip secrets that happen to share an
    extension with code (e.g. ``service-account.json``, ``api_token.txt``).
    """
    lower = name.lower()
    if lower in _SENSITIVE_BASENAMES:
        return True
    return _SENSITIVE_NAME_RE.search(lower) is not None

CODE_EXTENSIONS: set[str] = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py",
    ".go",
    ".vue", ".svelte",
    ".rb",
    ".java", ".kt",
    ".rs",
    ".php",
    ".swift",
    ".cs",
    ".ex", ".exs",
    ".dart",
    ".scala",
    ".clj",
    ".hs",
    ".graphql", ".gql",
    ".proto",
    ".sql",
}


def read_ignore_file(root: str | Path, filename: str = ".codebeaconignore") -> list[str]:
    """Return the raw lines of ``.codebeaconignore`` (no filtering).

    Pattern parsing is delegated to :class:`codebeacon.discover.ignore.IgnoreMatcher`,
    which implements gitignore semantics (negation, dir-only, anchored, trailing
    whitespace handling). Returning raw lines here keeps that responsibility in
    one place.
    """
    ignore_path = Path(root) / filename
    try:
        return ignore_path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []


def _should_ignore_dir(name: str) -> bool:
    if name in IGNORE_DIRS:
        return True
    if name.startswith("."):
        # Hidden dirs — skip most except known config dirs
        return True
    return False


def collect_files(
    root: str | Path,
    max_depth: int = 15,
    extra_ignore: list[str] | None = None,
) -> list[str]:
    """Recursively collect code files under root.

    Returns absolute paths sorted by directory then filename. Honours
    ``.codebeaconignore`` using gitignore semantics — negation (``!pattern``)
    re-includes paths that would otherwise be skipped.
    """
    root = Path(root).resolve()
    lines = read_ignore_file(root)
    if extra_ignore:
        lines.extend(extra_ignore)
    matcher = IgnoreMatcher(lines)
    # If any rule has `negate=True`, directory pruning is deferred to per-file
    # checks so a negated file inside an ignored directory can still be reached.
    has_negation = any(r.negate for r in matcher._rules)  # noqa: SLF001 — intentional internal access

    result: list[str] = []
    _walk(root, root, 0, max_depth, matcher, has_negation, result)
    return sorted(result)


def _walk(
    base: Path,
    current: Path,
    depth: int,
    max_depth: int,
    matcher: IgnoreMatcher,
    has_negation: bool,
    result: list[str],
) -> None:
    if depth > max_depth:
        return
    try:
        entries = sorted(current.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        return

    for entry in entries:
        if entry.is_symlink():
            continue
        rel = entry.relative_to(base).as_posix()
        if entry.is_dir():
            if _should_ignore_dir(entry.name):
                continue
            # Skip the descent only when no negation rules could un-ignore a
            # nested file. When `!pattern` exists, we must descend so that
            # negated files inside ignored directories are still reachable.
            if not has_negation and matcher.is_ignored(rel, is_dir=True):
                continue
            _walk(base, entry, depth + 1, max_depth, matcher, has_negation, result)
        elif entry.is_file():
            if entry.suffix not in CODE_EXTENSIONS:
                continue
            if _is_sensitive_filename(entry.name):
                continue
            if matcher.is_ignored(rel, is_dir=False):
                continue
            result.append(str(entry))


def hash_file(path: str | Path) -> str:
    """Return SHA-256 hex digest (first 12 chars) of file content."""
    try:
        content = Path(path).read_bytes()
        return hashlib.sha256(content).hexdigest()[:12]
    except OSError:
        return ""


def load_hash_cache(cache_dir: str | Path) -> dict:
    """Load the file hash cache from cache_dir/cache.json."""
    cache_path = Path(cache_dir) / "cache.json"
    try:
        return json.loads(cache_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"version": 1, "hashes": {}}


def save_hash_cache(cache_dir: str | Path, cache: dict) -> None:
    """Persist the hash cache; non-fatal if it fails."""
    try:
        cache_path = Path(cache_dir) / "cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def get_changed_files(files: list[str], cache: dict) -> tuple[list[str], dict]:
    """Return files whose hash differs from cache, and the updated hash map."""
    hashes = cache.get("hashes", {})
    changed: list[str] = []
    new_hashes: dict[str, str] = dict(hashes)

    for f in files:
        h = hash_file(f)
        if hashes.get(f) != h:
            changed.append(f)
            new_hashes[f] = h

    # Remove entries for files that no longer exist
    existing = set(files)
    new_hashes = {k: v for k, v in new_hashes.items() if k in existing}

    return changed, {"version": 1, "hashes": new_hashes}
