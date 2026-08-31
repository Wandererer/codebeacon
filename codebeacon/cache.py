"""SHA-256 based incremental cache for codebeacon.

Stores file_path → {hash, result, mtime_ns, ctime_ns, size, root} mapping in
``.codebeacon/cache/cache.json`` — a machine-local file the cache directory's
own ``.gitignore`` keeps out of git. On re-scan:

1. **Fast path** — if the cached entry's ``mtime_ns``, ``ctime_ns`` and ``size``
   still match the file on disk, we skip hashing entirely and reuse the cached
   result. This makes incremental scans near-instant on large repos where most
   files are untouched.

2. **Slow path** — if any stat field has changed, we hash the file. If the
   content hash still matches the cached hash, we trust it (mtime-only bumps
   from sync tools like Obsidian/Nextcloud/iCloud no longer cause needless
   re-extraction). Otherwise the file is treated as changed.

Every served entry is additionally vetted before it is handed back
(:func:`_payload_defect`, :meth:`Cache._usable_entry`): an entry minted under a
different project root, or one whose payload has been corrupted in place, is
*quarantined* — dropped so the file is re-extracted — rather than replayed into
the graph or crashing deep inside the merge.

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
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional


# Payload fields that ``codebeacon.wave._merge_file_result`` iterates, mapped to
# the keys its ``_dict_to_*`` helpers index *directly* — a missing one raises a
# KeyError deep inside the merge, with a traceback that never mentions the cache
# that served the entry (graphify v0.9.42).
#
# The required-key half is enforced only for payloads carrying a ``_schema``
# stamp: those were serialised by this codebeacon, so their shape is known
# exactly. Payloads without the stamp (hand-built by callers/tests, or written
# by an older serialiser) are checked structurally only — wave's own schema gate
# turns them into a miss anyway.
_PAYLOAD_REQUIRED_KEYS: dict[str, frozenset[str]] = {
    "routes": frozenset({"method", "path", "handler", "source_file", "line", "framework"}),
    "services": frozenset({"name", "class_name", "source_file", "line", "framework"}),
    "entities": frozenset({"name", "table_name", "source_file", "line", "framework"}),
    "components": frozenset({"name", "source_file", "line", "framework"}),
    "import_edges": frozenset({
        "source", "target", "relation", "confidence", "confidence_score", "source_file",
    }),
    "unresolved": frozenset({"source_node_id", "ref_type", "ref_name", "framework"}),
}


def _payload_defect(result: Any) -> str:
    """Return ``""`` if ``result`` is a servable payload, else a short reason.

    A whole corrupt ``cache.json`` is already handled at load time
    (:meth:`Cache._backup_corrupt`), but codebeacon keeps every entry in *one*
    JSON file, so a single mangled entry parses fine and sails through into the
    merge. This is the per-entry counterpart of that guard.
    """
    if not isinstance(result, dict):
        return f"result is {type(result).__name__}, not an object"
    stamped = "_schema" in result
    for field, required in _PAYLOAD_REQUIRED_KEYS.items():
        value = result.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            return f"{field} is {type(value).__name__}, not a list"
        for item in value:
            if not isinstance(item, dict):
                return f"{field} holds {type(item).__name__}, not an object"
            if stamped:
                missing = required - item.keys()
                if missing:
                    return f"a {field} entry is missing {', '.join(sorted(missing))}"
    return ""


def _still_on_disk(path: Path) -> bool:
    """Whether ``path`` exists, treating an *unanswerable* question as "yes".

    ``Path.exists()`` only swallows the errno family that means "not there"
    (ENOENT/ENOTDIR/ELOOP); ``EACCES`` from an unreadable parent directory
    propagates, so a single ``chmod 000`` subtree turned the liveness sweep into
    a ``PermissionError`` out of ``Cache.save()`` that killed the whole scan
    before the shrink guard was ever consulted.

    Beyond not crashing, the *answer* has to lean live: dropping an entry we
    could not stat is the unsafe direction (it discards work for a file that is
    probably still there), and it would contradict the scanner/shrink-guard rule
    that an unreadable file is never treated as a deliberate exclusion — see
    ``discover.scanner.unreadable_dirs``.
    """
    try:
        return path.exists()
    except OSError:
        return True


def _anchor_id(root: Optional[Path]) -> str:
    """Identity of the project root an entry was minted under.

    A digest rather than the path itself: the anchor is stored on every entry,
    and ``.codebeacon/`` is a directory teams commit — a literal
    ``/Users/alice/work/proj`` in each entry would publish local layout to the
    whole repo. Comparing digests answers the only question the cache asks
    ("same root as last time?") without carrying the path.
    """
    if root is None:
        return ""
    return hashlib.sha256(str(root).encode("utf-8", "surrogateescape")).hexdigest()[:16]


class Cache:
    """Manages SHA-256 based incremental file extraction cache.

    Cache keys are stored *repo-relative* whenever ``project_root`` is
    supplied at construction time. Without that, a developer who commits
    ``.codebeacon/cache/cache.json`` ends up with a cache full of paths
    like ``/Users/alice/proj/src/foo.py`` — every other contributor sees
    100 % cache miss because their absolute paths differ. Mirrors
    graphify #777.

    Existing absolute-path caches are migrated transparently on
    ``load()``: any key that lies inside ``project_root`` is rewritten
    to its relative form before the first read.

    Relative keys are portable by design, but the *payload* they point at is
    not — it embeds the source paths of the tree it was extracted from. So each
    entry also records which project root minted it, and an entry whose anchor
    does not match this Cache's is a miss (see :meth:`_usable_entry`). That is
    what keeps a repo copied or renamed with its committed ``.codebeacon/`` from
    replaying the old checkout's paths into the new one.
    """

    def __init__(self, output_dir: str, *, project_root: str | Path | None = None) -> None:
        self._cache_dir = Path(output_dir) / "cache"
        self._cache_file = self._cache_dir / "cache.json"
        self._root: Optional[Path] = Path(project_root).resolve() if project_root else None
        self._anchor = _anchor_id(self._root)
        self._data: dict[str, dict] = {}
        self._dirty = False
        # Memoize hashes within a single run to avoid double-reading files
        self._hash_memo: dict[str, str] = {}
        # Memoize stat() results within a single run as well
        self._stat_memo: dict[str, tuple[int, int, int]] = {}
        # Keys this run actually consulted — the live corpus, as seen by the
        # cache itself. Drives :meth:`prune_missing`.
        self._touched: set[str] = set()
        # Anomaly counters, reported once per run by :meth:`report_anomalies`.
        self._quarantined = 0
        self._foreign = 0
        self._first_defect: Optional[str] = None
        self._reported = False
        # One Cache instance is shared by the wave ThreadPoolExecutor workers;
        # the get()/put() check-then-act sequences need a lock to stay atomic.
        self._lock = threading.RLock()

    def _key(self, file_path: str, framework: str = "") -> str:
        """Map a (possibly absolute) ``file_path`` to its on-disk cache key.

        Returns a repo-relative POSIX path when ``project_root`` is set.
        A file *outside* the root still gets a relative key (``../beta/app.py``)
        rather than its absolute path: ``run_pipeline`` anchors one shared Cache
        at ``projects[0].path``, so in a multi-project workspace every project
        but the first is out-of-root, and keying those absolutely published
        local absolute paths into a committed ``.codebeacon/`` (graphify #1904).
        The absolute path remains the last-resort key for the cases where no
        relative form exists at all (different Windows drives, unresolvable
        paths) and when no ``project_root`` was supplied.

        ``framework`` namespaces the key: extraction results depend on the
        framework's query set, and one cache can serve several projects (a
        monorepo group shares a single cache at its repo root). Without the
        namespace, a parent project scanning a nested project's files first
        (desktop/ sveltekit walking over desktop/src-tauri) poisons the cache
        with empty results that the nested project (tauri) then reuses.
        """
        if self._root is None:
            key = file_path
        else:
            try:
                resolved = Path(file_path).resolve()
            except OSError:
                resolved = Path(file_path)
            try:
                key = resolved.relative_to(self._root).as_posix()
            except ValueError:
                try:
                    key = Path(os.path.relpath(resolved, self._root)).as_posix()
                except (ValueError, OSError):
                    key = file_path
        return f"{framework}::{key}" if framework else key

    def _entry_path(self, key: str) -> Optional[Path]:
        """Best-effort inverse of :meth:`_key` — where an entry's file lives.

        Returns ``None`` when the key cannot be resolved to a path (a relative
        key with no anchor to resolve it against), in which case callers must
        leave the entry alone rather than guess.
        """
        rel = key.rsplit("::", 1)[-1]
        if not rel:
            return None
        path = Path(rel)
        if path.is_absolute():
            return path
        if self._root is None:
            return None
        return self._root / path

    def load(self) -> None:
        """Load cache from disk. Safe to call even if the cache file doesn't exist.

        On-disk format is a version-stamped wrapper::

            {"_cb_version": "0.6.6", "entries": {key: entry, ...}}

        A cache written by a *different* codebeacon version is discarded: the
        extractor logic and the ``.scm`` queries change between releases, so
        reusing an older version's result for an *unchanged* source file would
        serve silently-stale output. The content hash can't catch this — the
        file didn't change, the extractor did. (Mirrors graphify #1252.) A
        legacy *flat* cache (pre-0.6.6, no wrapper) is unversioned and dropped
        for the same reason.

        When ``project_root`` is set, surviving absolute-path keys are rewritten
        to relative form (graphify #777); the first save persists the migration.
        """
        from codebeacon import __version__

        raw: Any = None
        try:
            if self._cache_file.exists():
                raw = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            # Corrupt cache.json — preserve it (don't let the next save silently
            # overwrite and destroy it) and rebuild from scratch. Mirrors the
            # graphify v0.8.39 "manifest data-loss on corrupt JSON" fix.
            # UnicodeDecodeError (a ValueError, not an OSError) fires when a
            # crash/disk-full truncated a write mid multi-byte sequence, leaving
            # invalid UTF-8 that read_text can't decode — self-heal it too.
            self._backup_corrupt()
            raw = None

        if isinstance(raw, dict) and "_cb_version" in raw and "entries" in raw:
            stored_version = raw.get("_cb_version")
            entries = raw.get("entries") or {}
        elif isinstance(raw, dict):
            stored_version, entries = None, raw  # legacy flat (unversioned)
        else:
            stored_version, entries = __version__, {}  # nothing on disk

        if stored_version != __version__:
            # Discard a foreign-version / unversioned cache exactly once. Mark
            # dirty only when there was something to drop, so the fresh,
            # version-stamped cache is written on save().
            self._data = {}
            if entries:
                self._dirty = True
            return

        self._data = entries if isinstance(entries, dict) else {}
        if self._root is None or not self._data:
            return
        migrated: dict[str, dict] = {}
        changed = False
        for k, v in self._data.items():
            # Keys are namespaced ``framework::path`` (and ``framework::semantic::path``
            # for semantic runs), so the absolute-path test has to run on the path
            # half — ``Path("fastapi::/abs/x.py").is_absolute()`` is False, which
            # left this migration unable to fire for any real entry.
            namespace, _, path_part = k.rpartition("::")
            if not Path(path_part).is_absolute():
                migrated[k] = v
                continue
            new_key = self._key(path_part)
            if namespace:
                new_key = f"{namespace}::{new_key}"
            if new_key != k:
                changed = True
            migrated[new_key] = v
        if changed:
            self._data = migrated
            self._dirty = True

    def _backup_corrupt(self) -> None:
        """Move a corrupt ``cache.json`` aside so the next ``save()`` can't
        silently overwrite it. Best-effort; the cache is reproducible."""
        try:
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup = self._cache_file.with_name(f"{self._cache_file.name}.{ts}.corrupt")
            self._cache_file.replace(backup)
            print(
                f"codebeacon: {self._cache_file} was corrupt; preserved as "
                f"{backup.name} and rebuilt the cache.",
                file=sys.stderr,
            )
        except OSError:
            pass

    def report_anomalies(self) -> None:
        """Print one stderr line per anomaly class seen this run (idempotent).

        Called from :meth:`save`, so a normal run reports without the caller
        having to remember; callers that want the notice earlier may call it
        themselves.
        """
        if self._reported:
            return
        self._reported = True
        if self._foreign:
            subject = (
                "1 cache entry was" if self._foreign == 1
                else f"{self._foreign} cache entries were"
            )
            print(
                f"codebeacon: {subject} built for a different project root "
                f"(moved or cloned checkout) — re-extracting those files.",
                file=sys.stderr,
            )
        if self._quarantined:
            noun = "entry" if self._quarantined == 1 else "entries"
            print(
                f"codebeacon: ignored {self._quarantined} unusable cache {noun} "
                f"(will re-extract; first: {self._first_defect}).",
                file=sys.stderr,
            )

    def prune_missing(self) -> int:
        """Drop entries whose file left the corpus *and* is gone from disk.

        Nothing ever evicts an entry today, so a cache grows for the life of the
        repo: every deleted file keeps its payload forever, bloating a file that
        teams commit (graphify v0.9.27). The two conditions are deliberately a
        conjunction — requiring the file to be missing on disk means a partial or
        aborted run (which consults only some of the corpus) can never evict a
        good entry, and a file that is merely newly *ignored* keeps its payload
        for the day the ignore rule is reverted.

        Returns the number of entries dropped.
        """
        with self._lock:
            if not self._touched:
                # Nothing was consulted: this was not an extraction pass, so we
                # have no evidence about what is live. Leave the cache alone.
                return 0
            dropped = 0
            for key in list(self._data):
                if key in self._touched:
                    continue
                path = self._entry_path(key)
                if path is None or _still_on_disk(path):
                    continue
                del self._data[key]
                dropped += 1
            if dropped:
                self._dirty = True
            return dropped

    def _ensure_gitignore(self) -> None:
        """Make the cache directory ignore itself in git. Written once.

        Cache data is machine-local *by construction*: the validity fast path
        compares ``st_ctime_ns`` (which no clone reproduces) and every entry is
        anchored to the project root that minted it, so an entry committed by
        one contributor can never be served to another — it is a guaranteed
        miss. Committing it therefore buys nothing and costs a file that churns
        in everyone's diffs. ``.codebeacon/`` itself is meant to be committed
        (that is the product contract), so the exclusion has to be scoped to
        this subdirectory rather than left to the consumer's root .gitignore.

        The pattern ``*`` covers the .gitignore too, so git never tracks the
        marker either; any scan recreates it locally. Never rewritten once
        present — a restamp would be its own churn, and the user may have
        edited it.
        """
        marker = self._cache_dir / ".gitignore"
        try:
            if not marker.exists():
                marker.write_text("*\n", encoding="utf-8")
        except OSError:
            # Best effort: failing to write the marker must not cost the cache.
            pass

    def save(self) -> None:
        """Persist cache to disk. No-op if nothing has changed.

        The write is atomic (temp file + ``os.replace``): ``cache.json`` is read
        on every ``--update``, and while :meth:`load` can recover from a
        truncated write by backing it up, a crash mid-write otherwise costs the
        whole cache. A cache directory that cannot be created or written (a
        read-only or third-party tree) degrades to a warning — the cache is an
        optimisation, never a reason to fail a scan.

        The payload is fully canonical (``sort_keys``). Entries land in
        ``self._data`` in ``put()`` order, which is the order the wave's
        ThreadPoolExecutor happens to finish files in — so two runs over an
        unchanged tree serialised the same entries in a different order and
        rewrote the file for no reason.
        """
        self.prune_missing()
        self.report_anomalies()
        if not self._dirty:
            return
        from codebeacon import __version__

        payload = json.dumps(
            {"_cb_version": __version__, "entries": self._data},
            ensure_ascii=False, indent=2, sort_keys=True,
        )
        tmp_path = self._cache_file.with_name(self._cache_file.name + ".tmp")
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._ensure_gitignore()
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, self._cache_file)
        except OSError as exc:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            print(
                f"codebeacon: could not write {self._cache_file} ({exc.strerror or exc}); "
                f"continuing without an incremental cache.",
                file=sys.stderr,
            )
            return
        self._dirty = False

    def file_hash(self, file_path: str) -> str:
        """Compute (and memoize) the SHA-256 hex digest of a file's contents."""
        with self._lock:
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

        with self._lock:
            self._hash_memo[file_path] = digest
        return digest

    def _file_stat(self, file_path: str) -> tuple[int, int, int]:
        """Return ``(mtime_ns, size, ctime_ns)`` for ``file_path``, memoized per run.

        Falls back to ``(0, 0, 0)`` when the file is unreadable; treating an
        unstattable file as "unchanged from a (0, 0, 0) cache" can never produce
        a stale-cache hit because a real file always has size > 0 mtime > 0.

        ``ctime_ns`` joins the fast-path tuple because (mtime, size) alone
        happily serves stale content whenever a same-length rewrite lands under
        a *preserved* mtime — ``cp -p``, ``rsync -a``, ``tar -x``, ``unzip``,
        Docker ``COPY``, and any coarse-granularity filesystem (ext3/HFS+ at 1s,
        FAT at 2s, gRPC-FUSE and many NFS/CIFS mounts) make that routine.
        ctime moves on every inode update, so it catches the rewrite. It does
        not survive a clone — but a ctime mismatch only *downgrades* to the
        content-hash comparison, so the failure direction can never be a stale
        hit (graphify v0.9.40).
        """
        memo = self._stat_memo.get(file_path)
        if memo is not None:
            return memo
        try:
            st = os.stat(file_path)
            result = (st.st_mtime_ns, st.st_size, st.st_ctime_ns)
        except OSError:
            result = (0, 0, 0)
        self._stat_memo[file_path] = result
        return result

    def _stat_matches(self, entry: dict, stat: tuple[int, int, int]) -> bool:
        """True when the entry's recorded stat fields still describe the file.

        An entry written before ``ctime_ns`` was recorded has no value to
        compare, so it falls through to the content-hash path (and is refreshed
        there) instead of being invalidated en masse on the upgrade run.
        """
        mtime_ns, size, ctime_ns = stat
        return (
            entry.get("mtime_ns") == mtime_ns
            and entry.get("size") == size
            and entry.get("ctime_ns") == ctime_ns
        )

    def _quarantine(self, key: str, defect: Optional[str], *, foreign: bool = False) -> None:
        """Drop an unservable entry and record why. Caller holds the lock."""
        self._data.pop(key, None)
        self._dirty = True
        if foreign:
            self._foreign += 1
            return
        self._quarantined += 1
        if self._first_defect is None:
            self._first_defect = f"{key} — {defect}"

    def _usable_entry(self, key: str, entry: Any) -> Optional[dict]:
        """Vet one entry before it is served; quarantine it when it is not.

        Caller holds the lock.
        """
        if not isinstance(entry, dict):
            self._quarantine(key, f"entry is {type(entry).__name__}, not an object")
            return None
        if entry.get("root") != self._anchor:
            # Minted under a different project root. The stored payload embeds
            # source paths from *that* tree, so replaying it here grafts a
            # foreign checkout's paths onto this one — the wiki and every node's
            # source_file then point into a directory the user does not have
            # (graphify v0.9.30 / v0.9.41). Copying a repo (with its committed
            # .codebeacon/) or renaming its directory is all it takes.
            self._quarantine(key, None, foreign=True)
            return None
        defect = _payload_defect(entry.get("result"))
        if defect:
            self._quarantine(key, defect)
            return None
        return entry

    def is_fresh(self, file_path: str, framework: str = "") -> bool:
        """Return True if the cached entry still matches the file.

        Uses the stat tuple as a fast path. On a stat mismatch we fall back to a
        full content hash so a true content change is detected, but a mtime-only
        bump (sync tools, ``touch``) is treated as unchanged.
        """
        with self._lock:
            key = self._key(file_path, framework)
            if key not in self._data:
                return False  # an ordinary miss, not an anomaly
            entry = self._usable_entry(key, self._data[key])
            if not entry:
                return False
            if self._stat_matches(entry, self._file_stat(file_path)):
                return True
            return entry.get("hash") == self.file_hash(file_path)

    def get(self, file_path: str, framework: str = "") -> Optional[dict]:
        """Return the cached extraction result dict, or None if stale/missing."""
        with self._lock:
            key = self._key(file_path, framework)
            self._touched.add(key)
            if key not in self._data:
                return None  # an ordinary miss, not an anomaly
            entry = self._usable_entry(key, self._data[key])
            if not entry:
                return None
            stat = self._file_stat(file_path)
            if self._stat_matches(entry, stat):
                return entry.get("result")
            if entry.get("hash") != self.file_hash(file_path):
                return None
            # Content unchanged despite a stat bump — refresh the stat fields so
            # the next run skips hashing.
            entry["mtime_ns"], entry["size"], entry["ctime_ns"] = stat
            self._dirty = True
            return entry.get("result")

    def put(
        self, file_path: str, result: Any, file_hash: Optional[str] = None,
        framework: str = "",
    ) -> None:
        """Store an extraction result for a file.

        Args:
            file_path: absolute path to the source file
            result: extraction result dict (must be JSON-serializable)
            file_hash: pre-computed SHA-256 digest (computed if not provided)
            framework: extraction namespace — see :meth:`_key`
        """
        h = file_hash or self.file_hash(file_path)
        if not isinstance(result, dict):
            try:
                from dataclasses import asdict
                result = asdict(result)
            except (TypeError, ImportError):
                result = {"_raw": str(result)}

        with self._lock:
            mtime_ns, size, ctime_ns = self._file_stat(file_path)
            key = self._key(file_path, framework)
            self._touched.add(key)
            # No wall-clock stamp. A per-entry ``ts`` was written here and read
            # nowhere — its only observable effect was to make every entry
            # differ on a plain (non ``--update``) rescan, which re-extracts and
            # re-puts everything. That left cache.json as the one artifact still
            # dirtying a committed .codebeacon/ on a no-op run. The file's own
            # mtime already answers "when was this written".
            self._data[key] = {
                "hash": h,
                "result": result,
                "mtime_ns": mtime_ns,
                "size": size,
                "ctime_ns": ctime_ns,
                "root": self._anchor,
            }
            self._hash_memo[file_path] = h
            self._dirty = True

    def invalidate(self, file_path: str) -> None:
        """Remove a file's cache entries across ALL framework namespaces."""
        base = self._key(file_path)
        with self._lock:
            doomed = [
                k for k in self._data
                if k == base or k.endswith("::" + base) or k == file_path
            ]
            for k in doomed:
                del self._data[k]
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
            "quarantined": self._quarantined,
            "foreign_root": self._foreign,
        }
