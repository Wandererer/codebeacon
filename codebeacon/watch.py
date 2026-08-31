"""Watch a project tree and auto-resync the index on file changes.

Opt-in, real-time counterpart to the post-commit rebuild hook
(:mod:`codebeacon.export.hooks`). The design is deliberately thin: the heavy
lifting — deciding which files changed and re-extracting only those — already
lives in the two-tier incremental cache (:mod:`codebeacon.cache`). ``watch``
just runs the *same* ``scan --update`` path a user runs by hand whenever the
tree settles after a burst of edits.

Three concerns are separated so the logic is unit-testable without threads or a
real file-watcher:

* :class:`Debouncer` — coalesce a burst of change events into one resync and
  serialise resyncs (never two at once; at most one queued follow-up). Its
  clock is injectable and :meth:`Debouncer.due` / :meth:`Debouncer.take` are
  pure primitives the tests drive directly.
* :func:`is_watchable_path` — the ignore filter, reusing the *exact* scanner
  helpers (``CODE_EXTENSIONS``, ``IGNORE_DIRS`` via ``_dir_would_be_walked``,
  ``.codebeaconignore`` matching) so the watcher can never diverge from what a
  scan would collect. Crucially this prunes the ``.codebeacon/`` output tree,
  so writing the index never wakes the watcher into an infinite loop.
* :func:`run_watch` — the orchestration, which imports ``watchdog`` lazily so
  the dependency stays an optional extra.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from codebeacon.discover.ignore import IgnoreMatcher
from codebeacon.discover.scanner import (
    CODE_EXTENSIONS,
    DEFAULT_IGNORE_PATTERNS,
    _dir_would_be_walked,
    _is_sensitive_filename,
    read_ignore_file,
)

# Event types that report a *read*, not a change. watchdog's inotify emitter
# subscribes to WATCHDOG_ALL_EVENTS, which includes IN_OPEN and IN_CLOSE_NOWRITE,
# so on Linux merely reading a file dispatches these — and a resync reads every
# source file it extracts. Without this filter each resync re-arms the debouncer
# with its own reads and the watcher never idles again (graphify v0.9.50). The
# macOS FSEvents and Windows backends never emit them, so the filter is a no-op
# there. Compared as strings (the values of watchdog.events.EVENT_TYPE_OPENED /
# EVENT_TYPE_CLOSED_NO_WRITE) so watch.py keeps importing without watchdog
# installed and across watchdog versions that predate either constant.
READ_ONLY_EVENT_TYPES = frozenset({"opened", "closed_no_write"})

# Printed (to stderr) when `watch` is run without the optional dependency.
# Mirrors the missing-grammar hint style in extract/base.py.
WATCHDOG_INSTALL_HINT = (
    "codebeacon watch needs the 'watchdog' package, which is an optional extra.\n"
    "Install it with:\n"
    "  pip install codebeacon[watch]\n"
    "  (or: pip install watchdog)"
)


# ── Ignore filter (shared with the scanner) ──────────────────────────────────

def build_ignore_matcher(
    root: str | Path, extra_ignore: Optional[list[str]] = None
) -> IgnoreMatcher:
    """Build the same :class:`IgnoreMatcher` ``collect_files`` uses for ``root``.

    Precedence matches the scanner exactly: built-in ``DEFAULT_IGNORE_PATTERNS``
    first (lowest), then the repo's ``.gitignore`` + ``.codebeaconignore`` (via
    :func:`read_ignore_file`), then any ``--exclude`` patterns — last-match-wins,
    so a user negation still re-includes.
    """
    lines = list(DEFAULT_IGNORE_PATTERNS)
    lines.extend(read_ignore_file(root))
    if extra_ignore:
        lines.extend(extra_ignore)
    return IgnoreMatcher(lines)


def is_watchable_path(root: str | Path, path: str | Path, matcher: IgnoreMatcher) -> bool:
    """Return True if a change to ``path`` should trigger a resync.

    Pure function of (root, path, matcher) — the ignore decision is identical to
    what :func:`codebeacon.discover.scanner.collect_files` would make for the
    same file, so the watcher and a scan never disagree:

    * only ``CODE_EXTENSIONS`` files (rejects ``.codebeacon/beacon.json`` etc.),
    * never credential-looking basenames (:func:`_is_sensitive_filename`),
    * pruned if any ancestor directory is one the walk would not descend into
      (``IGNORE_DIRS`` / hidden dirs / ``.codebeacon`` — reusing
      :func:`_dir_would_be_walked` so the loop-guard on our own output stays a
      single source of truth), and
    * not matched by the ``.codebeaconignore`` rules.

    Each ancestor is handed to ``_dir_would_be_walked`` *with its on-disk path*,
    which is what the walk itself passes. Ambiguously-named directories
    (``env/``, ``coverage/``, ``build/``, ``vendor/`` …) are pruned only when
    corroborating markers say they really are build output, and that decision
    needs the path — without it the name alone prunes, and the watcher would
    call a file un-watchable that a scan happily collects.
    """
    root = Path(root)
    p = Path(path)
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        # watchdog usually reports paths under the (already resolved) root
        # verbatim; fall back to resolving in case the root traversed a symlink.
        try:
            rel = p.resolve().relative_to(root).as_posix()
        except (ValueError, OSError):
            return False  # outside the watched tree

    if p.suffix.lower() not in CODE_EXTENSIONS:
        return False
    if _is_sensitive_filename(p.name):
        return False

    segments = rel.split("/")
    for i in range(len(segments) - 1):  # every ancestor directory of the file
        rel_dir = "/".join(segments[: i + 1])
        if not _dir_would_be_walked(segments[i], rel_dir, matcher, root / rel_dir):
            return False
    if matcher.is_ignored(rel, is_dir=False):
        return False
    return True


# ── Debounce + coalesce ──────────────────────────────────────────────────────

class Debouncer:
    """Collapse a burst of change notifications into a single, serialised flush.

    A file-watcher fires one event per touched file; a ``git checkout`` that
    rewrites 500 files would otherwise trigger 500 resyncs. :meth:`notify`
    records a changed path and (re)starts a quiet window of ``delay`` seconds —
    only once no new notification has arrived for a full window does
    :meth:`wait_for_batch` release the accumulated set, so the whole burst
    becomes one resync.

    The same single-consumer shape serialises syncs: the consumer thread calls
    :meth:`wait_for_batch`, runs the sync, then loops. Notifications that arrive
    while a sync is running simply accumulate and are handed back by the next
    :meth:`wait_for_batch` — exactly one follow-up, never a concurrent sync.

    The clock is injectable; :meth:`due` and :meth:`take` are pure primitives so
    the debounce arithmetic can be unit-tested without sleeping.
    """

    def __init__(self, delay: float = 2.0, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.delay = delay
        self._clock = clock
        self._cond = threading.Condition()
        self._paths: set[str] = set()
        self._last: float = 0.0
        self._stopped = False

    def notify(self, path: str) -> None:
        """Record a changed path and restart the quiet window."""
        with self._cond:
            self._paths.add(path)
            self._last = self._clock()
            self._cond.notify_all()

    def due(self, now: Optional[float] = None) -> bool:
        """True when work is pending and the quiet window has elapsed."""
        with self._cond:
            if not self._paths:
                return False
            now = self._clock() if now is None else now
            return (now - self._last) >= self.delay

    def take(self) -> set[str]:
        """Atomically clear and return the pending path set."""
        with self._cond:
            batch, self._paths = self._paths, set()
            return batch

    def stop(self) -> None:
        """Wake a blocked :meth:`wait_for_batch` so the consumer can exit."""
        with self._cond:
            self._stopped = True
            self._cond.notify_all()

    @property
    def stopped(self) -> bool:
        with self._cond:
            return self._stopped

    def wait_for_batch(self) -> Optional[set[str]]:
        """Block until a coalesced batch is ready and return it.

        Returns ``None`` when :meth:`stop` has been called (the consumer should
        exit). Otherwise returns a non-empty set of changed paths, at most once
        per quiet window.
        """
        with self._cond:
            while True:
                if self._stopped:
                    return None
                if not self._paths:
                    self._cond.wait()
                    continue
                remaining = self.delay - (self._clock() - self._last)
                if remaining <= 0:
                    batch, self._paths = self._paths, set()
                    return batch
                # A fresh notify() during the wait resets ``_last``, so the next
                # iteration recomputes a longer remaining — the burst coalesces.
                self._cond.wait(timeout=remaining)


# ── Orchestration ────────────────────────────────────────────────────────────

# Type of the resync callback: receives the set of changed paths (empty for the
# initial sync) and returns a process-style exit code (0 == success).
SyncCallback = Callable[[set], int]


def _import_watchdog():
    """Import watchdog lazily. Isolated so tests can force the ImportError path."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    return Observer, FileSystemEventHandler


def _event_paths(event) -> list[str]:
    """Return the source (and, for moves, destination) paths of a watchdog event."""
    paths = [event.src_path]
    dest = getattr(event, "dest_path", None)
    if dest:
        paths.append(dest)
    return paths


def _make_handler(base_cls, root: Path, matcher: IgnoreMatcher, debouncer: Debouncer):
    """Build a watchdog event handler that debounces watchable file changes."""

    class _ChangeHandler(base_cls):
        def on_any_event(self, event) -> None:
            if event.is_directory:
                return
            if getattr(event, "event_type", "") in READ_ONLY_EVENT_TYPES:
                return  # a read, not a change — see READ_ONLY_EVENT_TYPES
            for p in _event_paths(event):
                if is_watchable_path(root, p, matcher):
                    debouncer.notify(p)

    return _ChangeHandler()


def _install_signal_handlers(debouncer: Debouncer) -> None:
    """Turn SIGINT/SIGTERM into a clean stop. No-op off the main thread.

    Signals can only be installed from the main thread, so a ``run_watch``
    driven from a worker thread (the tests) simply skips this and relies on
    :meth:`Debouncer.stop`.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    import signal

    def _handler(_signum, _frame) -> None:
        debouncer.stop()

    for name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


def _run_sync(
    sync_callback: SyncCallback,
    batch: set,
    log: Callable[[str], None],
    *,
    initial: bool = False,
) -> None:
    """Run one sync and print a single concise status line.

    Exceptions from the callback are caught so a transient failure never kills
    the watch loop; a non-zero return is reported but likewise keeps watching.
    """
    started = time.monotonic()
    try:
        rc = sync_callback(batch)
    except Exception as exc:  # keep watching even if one resync blows up
        label = "initial sync" if initial else "resync"
        log(f"  {label} failed: {exc}")
        return
    elapsed = time.monotonic() - started
    if initial:
        log(f"  initial sync complete ({elapsed:.1f}s)")
    else:
        noun = "file" if len(batch) == 1 else "files"
        log(f"  resynced: {len(batch)} {noun} changed ({elapsed:.1f}s)")
    if rc != 0:
        log(f"  (last sync exited {rc})")


def run_watch(
    root: str | Path,
    sync_callback: SyncCallback,
    *,
    debounce: float = 2.0,
    extra_ignore: Optional[list[str]] = None,
    once: bool = False,
    initial_sync: bool = True,
    observer=None,
    log: Callable[[str], None] = print,
) -> int:
    """Sync ``root`` once, then resync it on every debounced change.

    ``sync_callback(changed_paths)`` performs the actual (incremental) resync —
    ``run_watch`` never touches the pipeline itself. The initial sync passes an
    empty set; each subsequent call receives the coalesced batch of paths.

    ``once`` processes a single debounce cycle then returns (used by tests to
    avoid a forever-loop). ``observer`` injects a pre-built watchdog observer,
    also for tests; when omitted, watchdog is imported lazily and a missing
    install returns 1 with :data:`WATCHDOG_INSTALL_HINT` on stderr.
    """
    root = Path(root).resolve()
    matcher = build_ignore_matcher(root, extra_ignore)
    debouncer = Debouncer(debounce)

    own_observer = observer is None
    if own_observer:
        try:
            Observer, FileSystemEventHandler = _import_watchdog()
        except ImportError:
            print(WATCHDOG_INSTALL_HINT, file=sys.stderr)
            return 1
        handler = _make_handler(FileSystemEventHandler, root, matcher, debouncer)
        observer = Observer()
        observer.schedule(handler, str(root), recursive=True)

    _install_signal_handlers(debouncer)

    if initial_sync:
        log(f"codebeacon: watching {root} (debounce {debounce:g}s) — Ctrl-C to stop")
        _run_sync(sync_callback, set(), log, initial=True)

    if own_observer:
        observer.start()

    try:
        while True:
            batch = debouncer.wait_for_batch()
            if batch is None:  # stop() called (signal / test)
                break
            _run_sync(sync_callback, batch, log)
            if once:
                break
    except KeyboardInterrupt:
        # Belt-and-suspenders: a SIGINT that raced the handler install still
        # unwinds to a clean exit rather than a traceback.
        pass
    finally:
        if own_observer:
            observer.stop()
            observer.join(timeout=5)

    return 0
