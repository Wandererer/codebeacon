"""Recursive file collector with ignore patterns and hash caching."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterator

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
}

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
    """Read .codebeaconignore at the project root and return ignore patterns."""
    ignore_path = Path(root) / filename
    try:
        content = ignore_path.read_text(encoding="utf-8")
        return [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    except (FileNotFoundError, OSError):
        return []


def _should_ignore_dir(name: str, extra_ignore: set[str]) -> bool:
    if name in IGNORE_DIRS:
        return True
    if name in extra_ignore:
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

    Returns absolute paths sorted by directory then filename.
    """
    root = Path(root).resolve()
    ignore_patterns = read_ignore_file(root)
    if extra_ignore:
        ignore_patterns.extend(extra_ignore)

    extra_ignore_set: set[str] = set()
    for p in ignore_patterns:
        # Simple patterns: strip leading / and trailing /* or /**
        clean = p.lstrip("/").rstrip("/").rstrip("*").rstrip("/")
        if clean:
            extra_ignore_set.add(clean)

    result: list[str] = []
    _walk(root, root, 0, max_depth, extra_ignore_set, result)
    return sorted(result)


def _walk(
    base: Path,
    current: Path,
    depth: int,
    max_depth: int,
    extra_ignore: set[str],
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
        if entry.is_dir():
            if not _should_ignore_dir(entry.name, extra_ignore):
                _walk(base, entry, depth + 1, max_depth, extra_ignore, result)
        elif entry.is_file():
            if entry.suffix in CODE_EXTENSIONS:
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
