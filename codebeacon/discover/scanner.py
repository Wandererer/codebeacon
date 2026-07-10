"""Recursive file collector with ignore patterns and hash caching."""

from __future__ import annotations

import hashlib
import json
import os
import sys
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
    # Linked git worktrees created with ``git worktree add ../foo`` may live
    # inside the project root. Their files are duplicates of branches we are
    # not analysing, so they double-count nodes and slow incremental rebuilds.
    "worktrees",
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
# narrow: it must be at the start of the basename or follow ``[-_.]``.
#
# The trailing boundary ``(?=\.[^.]+$|$)`` requires the credential phrase to be
# essentially the whole stem — followed only by the file extension or the end of
# the name. This flags real secret dumps (``api_key.txt``, ``client-secret.json``,
# ``private_key.pem``) while letting through source modules merely *named after*
# the concept (``api_key_manager.go``, ``access_token_service.py``,
# ``client_secret_validator.ts``), which a looser ``(?=[-_.]|$)`` boundary
# silently dropped because the ``_`` in ``_manager`` satisfied it.
import re as _re
_SENSITIVE_NAME_RE = _re.compile(
    r"(?:^|[-_.])(?:api[-_]?key|api[-_]?token|oauth[-_]?token|"
    r"access[-_]?token|refresh[-_]?token|secret[-_]?key|"
    r"private[-_]?key|client[-_]?secret)"
    r"(?=\.[^.]+$|$)",
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
    ".cs", ".razor", ".cshtml",
    ".sln", ".csproj", ".fsproj", ".vbproj",
    ".ex", ".exs",
    ".dart",
    ".scala",
    ".clj",
    ".hs",
    ".ets",
    ".graphql", ".gql",
    ".proto",
    ".sql",
}


def read_ignore_file(
    root: str | Path,
    filename: str = ".codebeaconignore",
    *,
    gitignore_fallback: bool = True,
) -> list[str]:
    """Return the raw lines of the project's ignore rules (no filtering).

    Reads ``.gitignore`` first (when ``gitignore_fallback``) and appends
    ``.codebeaconignore`` last, so the two are **merged** rather than one
    replacing the other. Because :class:`~codebeacon.discover.ignore.IgnoreMatcher`
    uses gitignore last-match-wins semantics, ``.codebeaconignore`` patterns win
    on conflict (including ``!`` negations), yet adding a ``.codebeaconignore``
    can only ever exclude *more* — it never silently drops the repo's existing
    ``.gitignore`` exclusions.

    This matters for privacy: a file excluded only by ``.gitignore`` (e.g. a
    neutrally-named ``prod-dump.sql`` or ``customer-data.*``) must keep being
    skipped even after a ``.codebeaconignore`` is added, or it would get indexed
    into the committed ``.codebeacon/`` artifacts (graphify #1363).

    Pattern parsing is delegated to :class:`codebeacon.discover.ignore.IgnoreMatcher`,
    which implements gitignore semantics (negation, dir-only, anchored, trailing
    whitespace handling).
    """
    root_path = Path(root)
    lines: list[str] = []

    # ``errors="replace"`` so a stray non-UTF-8 byte (e.g. a latin-1 comment)
    # anywhere in an ignore file degrades to a replacement char instead of
    # raising UnicodeDecodeError — a ValueError that the (FileNotFoundError,
    # OSError) guards below cannot catch — and aborting the whole scan. Mirrors
    # detector._read_safe.

    # .gitignore first (lower precedence).
    if gitignore_fallback:
        try:
            lines.extend(
                (root_path / ".gitignore")
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
            )
        except (FileNotFoundError, OSError):
            pass

    # .codebeaconignore last, so its patterns win on conflict and only ever add.
    try:
        lines.extend(
            (root_path / filename)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        )
    except (FileNotFoundError, OSError):
        pass

    return lines


def _should_ignore_dir(name: str) -> bool:
    if name in IGNORE_DIRS:
        return True
    if name.startswith("."):
        # Hidden dirs — skip most except known config dirs
        return True
    return False


def _dir_would_be_walked(name: str, rel: str, matcher: IgnoreMatcher) -> bool:
    """Whether :func:`_walk` would descend into the directory ``name`` at ``rel``.

    Single source of truth for the dir-prune decision, shared by the real walk
    and the symlink-warning gate so the two can never drift.

    ``!pattern`` in ``.codebeaconignore`` can opt a directory back in that the
    default skips (hidden dirs, IGNORE_DIRS) would otherwise drop. Only an
    explicit *self* match counts — a parent-level negation does not auto
    re-include nested dot-folders (mirrors codesight #42 / 0bedd0d).

    An ignored directory is pruned only when no negation rule could re-include a
    file beneath it. A per-directory ``could_unignore_under`` check (not a
    global "any negation → descend everywhere" flag) so an unrelated ``!foo``
    rule doesn't force descent into every excluded subtree (graphify #1274).
    Unanchored negations are treated conservatively (descend), so no rescuable
    file is lost.
    """
    if matcher.is_explicitly_included(rel, is_dir=True):
        return True
    if _should_ignore_dir(name):
        return False
    if matcher.is_ignored(rel, is_dir=True) and not matcher.could_unignore_under(rel):
        return False
    return True


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

    result: list[str] = []
    skipped_symlinks: list[str] = []
    _walk(root, root, 0, max_depth, matcher, result, skipped_symlinks)
    if skipped_symlinks:
        # We deliberately do NOT follow symlinks (loop / double-counting / escape
        # risk), but silently dropping symlinked source is surprising — surface
        # it once, grouped, so shared code isn't lost without a trace.
        joined = ", ".join(sorted(skipped_symlinks))
        print(
            f"    Warning: skipped {len(skipped_symlinks)} symlink(s), not "
            f"followed: {joined}",
            file=sys.stderr,
        )
    return sorted(result)


def _walk(
    base: Path,
    current: Path,
    depth: int,
    max_depth: int,
    matcher: IgnoreMatcher,
    result: list[str],
    skipped_symlinks: list[str],
) -> None:
    if depth > max_depth:
        return
    try:
        entries = sorted(current.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        return

    for entry in entries:
        rel = entry.relative_to(base).as_posix()
        if entry.is_symlink():
            # We deliberately do NOT follow symlinks, but a link that carries
            # code the real walk would otherwise collect is worth surfacing.
            # Only record it when the same IGNORE_DIRS / hidden-dir / matcher
            # checks the walk applies would NOT have pruned it anyway — else a
            # symlinked node_modules / dist / .venv (or an ignore-matched path)
            # is wrongly reported as lost "shared code" (BH-D3).
            try:
                if entry.is_dir():
                    if _dir_would_be_walked(entry.name, rel, matcher):
                        skipped_symlinks.append(rel)
                elif entry.is_file() and entry.suffix.lower() in CODE_EXTENSIONS:
                    if not _is_sensitive_filename(entry.name) and not matcher.is_ignored(
                        rel, is_dir=False
                    ):
                        skipped_symlinks.append(rel)
            except OSError:
                pass  # broken/unstattable symlink — nothing useful to report
            continue
        if entry.is_dir():
            if not _dir_would_be_walked(entry.name, rel, matcher):
                continue
            _walk(base, entry, depth + 1, max_depth, matcher, result, skipped_symlinks)
        elif entry.is_file():
            # Normalise case so uppercase/mixed-case extensions (App.PY, Index.JS,
            # Page.TSX) — valid, importable source on case-insensitive filesystems
            # — aren't silently dropped. Matches extract/semantic.py, common/
            # filters.py and semantic_pipeline.py, which already lowercase suffixes.
            if entry.suffix.lower() not in CODE_EXTENSIONS:
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
