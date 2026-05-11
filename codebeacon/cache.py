"""SHA-256 based incremental cache for codebeacon.

Stores file_path → {hash, result, ts, mtime, size} mapping in
``.codebeacon/cache/cache.json``. On re-scan:

1. **Fast path** — if the cached entry's ``mtime`` and ``size`` still match the
   file on disk, we skip hashing entirely and reuse the cached result. This
   makes incremental scans near-instant on large repos where most files are
   untouched.

2. **Slow path** — if mtime or size has changed, we hash the file. If the
   content hash still matches the cached hash, we trust it (mtime-only bumps
   from sync tools like Obsidian/Nextcloud/iCloud no longer cause needless
   re-extraction). Otherwise the file is treated as changed.

Usage:
    cache = Cache(output_dir)
    cache.load()

    for file in files:
        cached = cache.get(file)        # None if stale/missing
        if cached is not None:
            use(cached)
        else:
            result = extract(file)
            cache.put(file, result)

    cache.save()
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


class Cache:
    """Manages SHA-256 based incremental file extraction cache."""

    def __init__(self, output_dir: str) -> None:
        self._cache_dir = Path(output_dir) / "cache"
        self._cache_file = self._cache_dir / "cache.json"
        self._data: dict[str, dict] = {}
        self._dirty = False
        # Memoize hashes within a single run to avoid double-reading files
        self._hash_memo: dict[str, str] = {}
        # Memoize stat() results within a single run as well
        self._stat_memo: dict[str, tuple[int, int]] = {}

    def load(self) -> None:
        """Load cache from disk. Safe to call even if the cache file doesn't exist."""
        try:
            if self._cache_file.exists():
                self._data = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def save(self) -> None:
        """Persist cache to disk. No-op if nothing has changed."""
        if not self._dirty:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._dirty = False

    def file_hash(self, file_path: str) -> str:
        """Compute (and memoize) the SHA-256 hex digest of a file's contents."""
        if file_path in self._hash_memo:
            return self._hash_memo[file_path]

        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            digest = h.hexdigest()
        except OSError:
            digest = ""

        self._hash_memo[file_path] = digest
        return digest

    def _file_stat(self, file_path: str) -> tuple[int, int]:
        """Return ``(mtime_ns, size)`` for ``file_path``, memoized per run.

        Falls back to ``(0, 0)`` when the file is unreadable; treating an
        unstattable file as "unchanged from a (0, 0) cache" can never produce
        a stale-cache hit because a real file always has size > 0 mtime > 0.
        """
        memo = self._stat_memo.get(file_path)
        if memo is not None:
            return memo
        try:
            st = os.stat(file_path)
            result = (st.st_mtime_ns, st.st_size)
        except OSError:
            result = (0, 0)
        self._stat_memo[file_path] = result
        return result

    def is_fresh(self, file_path: str) -> bool:
        """Return True if the cached entry still matches the file.

        Uses mtime + size as a fast path. On a stat mismatch we fall back to a
        full content hash so a true content change is detected, but a mtime-only
        bump (sync tools, ``touch``) is treated as unchanged.
        """
        entry = self._data.get(file_path)
        if not entry:
            return False
        mtime_ns, size = self._file_stat(file_path)
        if entry.get("mtime_ns") == mtime_ns and entry.get("size") == size:
            return True
        return entry.get("hash") == self.file_hash(file_path)

    def get(self, file_path: str) -> Optional[dict]:
        """Return the cached extraction result dict, or None if stale/missing."""
        entry = self._data.get(file_path)
        if not entry:
            return None
        mtime_ns, size = self._file_stat(file_path)
        if entry.get("mtime_ns") == mtime_ns and entry.get("size") == size:
            return entry.get("result")
        if entry.get("hash") != self.file_hash(file_path):
            return None
        # Content unchanged despite mtime bump — refresh the stat fields so the
        # next run skips hashing.
        entry["mtime_ns"] = mtime_ns
        entry["size"] = size
        self._dirty = True
        return entry.get("result")

    def put(self, file_path: str, result: Any, file_hash: Optional[str] = None) -> None:
        """Store an extraction result for a file.

        Args:
            file_path: absolute path to the source file
            result: extraction result dict (must be JSON-serializable)
            file_hash: pre-computed SHA-256 digest (computed if not provided)
        """
        h = file_hash or self.file_hash(file_path)
        if not isinstance(result, dict):
            try:
                from dataclasses import asdict
                result = asdict(result)
            except (TypeError, ImportError):
                result = {"_raw": str(result)}

        mtime_ns, size = self._file_stat(file_path)
        self._data[file_path] = {
            "hash": h,
            "result": result,
            "ts": time.time(),
            "mtime_ns": mtime_ns,
            "size": size,
        }
        self._hash_memo[file_path] = h
        self._dirty = True

    def invalidate(self, file_path: str) -> None:
        """Remove a specific file's cache entry."""
        if file_path in self._data:
            del self._data[file_path]
            self._dirty = True
        self._hash_memo.pop(file_path, None)
        self._stat_memo.pop(file_path, None)

    def clear(self) -> None:
        """Remove all cache entries."""
        self._data = {}
        self._hash_memo = {}
        self._stat_memo = {}
        self._dirty = True

    def stats(self) -> dict:
        """Return basic cache statistics."""
        return {
            "entries": len(self._data),
            "cache_file": str(self._cache_file),
        }
