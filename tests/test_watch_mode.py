"""Tests for `codebeacon watch` — the opt-in file-watcher auto-resync.

Three layers, matching the module's split of concerns:

1. :class:`~codebeacon.watch.Debouncer` — pure debounce/coalesce arithmetic,
   driven with an injected clock so no test ever sleeps.
2. :func:`~codebeacon.watch.is_watchable_path` — the ignore filter, asserted as
   a pure function so the loop-guard on our own ``.codebeacon/`` output is
   pinned without spinning up a watcher.
3. CLI wiring + a real-watchdog integration test (skipif the extra is missing).
"""
from __future__ import annotations

import threading
import time
from argparse import Namespace
from pathlib import Path

import pytest

from codebeacon import watch as watch_mod
from codebeacon.watch import (
    Debouncer,
    build_ignore_matcher,
    is_watchable_path,
    run_watch,
)


# ── Debouncer: pure coalesce/debounce arithmetic ─────────────────────────────

class _FakeClock:
    """Manually-advanced monotonic clock so debounce timing is deterministic."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_debouncer_empty_is_never_due():
    d = Debouncer(delay=2.0, clock=_FakeClock())
    assert d.due() is False
    assert d.take() == set()


def test_debouncer_not_due_before_window_elapses():
    clk = _FakeClock()
    d = Debouncer(delay=2.0, clock=clk)
    d.notify("a.py")
    clk.t += 1.9
    assert d.due() is False  # quiet window not yet elapsed


def test_debouncer_due_after_window_elapses():
    clk = _FakeClock()
    d = Debouncer(delay=2.0, clock=clk)
    d.notify("a.py")
    clk.t += 2.0
    assert d.due() is True


def test_debouncer_notify_resets_the_window():
    """A second change inside the window pushes the resync out — a steady stream
    of edits coalesces into one sync fired after things settle."""
    clk = _FakeClock()
    d = Debouncer(delay=2.0, clock=clk)
    d.notify("a.py")
    clk.t += 1.0
    d.notify("b.py")           # resets _last to now
    clk.t += 1.5               # 2.5s since first notify, but only 1.5s since last
    assert d.due() is False
    clk.t += 0.6               # now 2.1s since the last notify
    assert d.due() is True


def test_debouncer_coalesces_a_burst_into_one_batch():
    """500 change events (a git checkout) collapse to a single batch."""
    clk = _FakeClock()
    d = Debouncer(delay=2.0, clock=clk)
    for i in range(500):
        d.notify(f"file_{i}.py")
    clk.t += 2.0
    assert d.due() is True
    batch = d.take()
    assert len(batch) == 500
    # Draining the batch clears the pending state — no phantom second sync.
    assert d.due() is False
    assert d.take() == set()


def test_debouncer_stop_unblocks_wait_for_batch():
    d = Debouncer(delay=0.05)
    d.stop()
    assert d.stopped is True
    assert d.wait_for_batch() is None  # returns immediately, signals "exit"


def test_debouncer_wait_for_batch_returns_coalesced_set():
    """End-to-end through the blocking API with a real (tiny) delay."""
    d = Debouncer(delay=0.05)
    d.notify("x.py")
    d.notify("y.py")
    batch = d.wait_for_batch()
    assert batch == {"x.py", "y.py"}


# ── is_watchable_path: ignore filter parity with the scanner ─────────────────

def test_watchable_accepts_code_file(tmp_path):
    matcher = build_ignore_matcher(tmp_path)
    assert is_watchable_path(tmp_path, tmp_path / "src" / "app.py", matcher) is True


def test_watchable_rejects_non_code_extension(tmp_path):
    matcher = build_ignore_matcher(tmp_path)
    assert is_watchable_path(tmp_path, tmp_path / "README.md", matcher) is False


def test_watchable_rejects_codebeacon_output_dir(tmp_path):
    """The load-bearing loop guard: writing the index must never wake the
    watcher, so anything under ``.codebeacon/`` is unwatchable — even a file
    whose extension is otherwise code."""
    matcher = build_ignore_matcher(tmp_path)
    assert is_watchable_path(tmp_path, tmp_path / ".codebeacon" / "cache" / "x.py", matcher) is False
    assert is_watchable_path(tmp_path, tmp_path / ".codebeacon" / "beacon.json", matcher) is False


def test_watchable_rejects_ignored_dirs(tmp_path):
    matcher = build_ignore_matcher(tmp_path)
    for rel in ("node_modules/lib.js", ".git/hooks/x.py", "dist/bundle.js", "__pycache__/m.py"):
        assert is_watchable_path(tmp_path, tmp_path / rel, matcher) is False, rel


def test_watchable_rejects_sensitive_filename(tmp_path):
    matcher = build_ignore_matcher(tmp_path)
    assert is_watchable_path(tmp_path, tmp_path / "config" / "api_key.py", matcher) is False


def test_watchable_honours_codebeaconignore(tmp_path):
    (tmp_path / ".codebeaconignore").write_text("secret_stuff/\n")
    matcher = build_ignore_matcher(tmp_path)
    assert is_watchable_path(tmp_path, tmp_path / "secret_stuff" / "a.py", matcher) is False
    assert is_watchable_path(tmp_path, tmp_path / "keep" / "a.py", matcher) is True


def test_watchable_respects_extra_ignore(tmp_path):
    matcher = build_ignore_matcher(tmp_path, extra_ignore=["generated/"])
    assert is_watchable_path(tmp_path, tmp_path / "generated" / "a.py", matcher) is False


def test_watchable_rejects_path_outside_root(tmp_path):
    matcher = build_ignore_matcher(tmp_path)
    outside = tmp_path.parent / "elsewhere" / "a.py"
    assert is_watchable_path(tmp_path, outside, matcher) is False


# ── CLI wiring ───────────────────────────────────────────────────────────────

def test_cli_registers_watch_subcommand():
    from codebeacon.cli import _KNOWN_SUBCOMMANDS, _cmd_watch, build_parser

    assert "watch" in _KNOWN_SUBCOMMANDS
    parser = build_parser()
    args = parser.parse_args(
        ["watch", "somedir", "--debounce", "0.5", "--once", "--exclude", "foo/"]
    )
    assert args.func is _cmd_watch
    assert args.path == "somedir"
    assert args.debounce == 0.5
    assert args.once is True
    assert args.exclude == ["foo/"]


def test_cli_watch_defaults():
    from codebeacon.cli import build_parser

    args = build_parser().parse_args(["watch"])
    assert args.path == "."
    assert args.debounce == 2.0
    assert args.once is False


def test_cmd_watch_rejects_missing_path(tmp_path, capsys):
    from codebeacon.cli import _cmd_watch

    rc = _cmd_watch(Namespace(path=str(tmp_path / "nope"), debounce=2.0, once=False, exclude=[]))
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_cmd_watch_rejects_file_path(tmp_path, capsys):
    from codebeacon.cli import _cmd_watch

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    rc = _cmd_watch(Namespace(path=str(f), debounce=2.0, once=False, exclude=[]))
    assert rc == 1
    assert "not a directory" in capsys.readouterr().err


def test_cmd_watch_forwards_flags_to_run_watch(tmp_path, monkeypatch):
    from codebeacon.cli import _cmd_watch

    captured: dict = {}

    def fake_run_watch(root, cb, *, debounce, extra_ignore, once):
        captured.update(root=Path(root), cb=cb, debounce=debounce, extra_ignore=extra_ignore, once=once)
        return 0

    monkeypatch.setattr(watch_mod, "run_watch", fake_run_watch)
    rc = _cmd_watch(Namespace(path=str(tmp_path), debounce=0.3, once=True, exclude=["x/"]))
    assert rc == 0
    assert captured["root"] == tmp_path.resolve()
    assert captured["debounce"] == 0.3
    assert captured["once"] is True
    assert captured["extra_ignore"] == ["x/"]


def test_resync_callback_reuses_scan_update(tmp_path, monkeypatch):
    """The watcher must not reimplement the pipeline — its resync dispatches to
    the same `scan --update` code path a user runs by hand."""
    import codebeacon.cli as cli

    captured: dict = {}

    def fake_run_watch(root, cb, *, debounce, extra_ignore, once):
        captured["cb"] = cb
        return 0

    scan_calls: list = []

    def fake_scan(a):
        scan_calls.append(a)
        return 0

    monkeypatch.setattr(watch_mod, "run_watch", fake_run_watch)
    monkeypatch.setattr(cli, "_cmd_scan", fake_scan)

    cli._cmd_watch(Namespace(path=str(tmp_path), debounce=2.0, once=False, exclude=[]))
    rc = captured["cb"]({str(tmp_path / "foo.py")})  # drive the resync callback

    assert rc == 0
    assert len(scan_calls) == 1
    sa = scan_calls[0]
    assert sa.update is True
    assert sa.watch is False
    assert sa.list_only is False
    assert sa.paths == [str(tmp_path.resolve())]


# ── Missing optional dependency ──────────────────────────────────────────────

def test_run_watch_without_watchdog_prints_hint(tmp_path, monkeypatch, capsys):
    """A missing `watchdog` yields a clear install hint and exit 1 — never a
    bare ImportError traceback, and never a sync it can't then watch."""
    def _boom():
        raise ImportError("no watchdog installed")

    monkeypatch.setattr(watch_mod, "_import_watchdog", _boom)

    calls: list = []
    rc = run_watch(tmp_path, lambda b: calls.append(b) or 0, initial_sync=True)
    assert rc == 1
    assert "watchdog" in capsys.readouterr().err
    assert calls == []  # bailed before running any sync


# ── Integration (real watchdog) ──────────────────────────────────────────────

watchdog = pytest.importorskip("watchdog")  # skip the rest of the file if absent


def _run_in_thread(target):
    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t


def _is_code(path: str) -> bool:
    from codebeacon.discover.scanner import CODE_EXTENSIONS

    return Path(path).suffix.lower() in CODE_EXTENSIONS


def test_watch_fires_exactly_one_resync_on_change(tmp_path):
    """Touching a source file triggers exactly one debounced resync carrying a
    watchable code path.

    The batch reflects a real code change (not our own output, not a spurious
    empty fire). We assert on *which kind* of file rather than the exact name:
    macOS FSEvents diffs whole directories, so it may attribute the change to
    another pre-existing source file — a real resync re-scans the tree either
    way, so the contract that matters is "one resync, watchable files only"."""
    (tmp_path / "seed.py").write_text("x = 1\n")  # exists before the watcher starts

    calls: list = []

    def fake_sync(batch):
        calls.append(set(batch))
        return 0

    result: dict = {}

    def runner():
        result["rc"] = run_watch(
            tmp_path, fake_sync, debounce=0.1, once=True, initial_sync=False
        )

    t = _run_in_thread(runner)
    time.sleep(0.5)  # let the observer come up before we perturb the tree
    (tmp_path / "new_module.py").write_text("y = 2\n")
    t.join(timeout=8)

    assert not t.is_alive(), "watch loop did not exit after one debounce cycle"
    assert result.get("rc") == 0
    assert len(calls) == 1, f"expected exactly one resync, got {len(calls)}"
    assert calls[0], "resync fired with an empty change set"
    assert all(_is_code(p) for p in calls[0])


def test_watch_ignores_output_and_dependency_writes(tmp_path):
    """Writes under `.codebeacon/` and `node_modules/` must not wake the
    watcher (no self-inflicted resync loop); a real source edit still does."""
    (tmp_path / "seed.py").write_text("x = 1\n")

    calls: list = []

    def fake_sync(batch):
        calls.append(set(batch))
        return 0

    result: dict = {}

    def runner():
        result["rc"] = run_watch(
            tmp_path, fake_sync, debounce=0.15, once=True, initial_sync=False
        )

    t = _run_in_thread(runner)
    time.sleep(0.5)

    (tmp_path / ".codebeacon" / "cache").mkdir(parents=True)
    (tmp_path / ".codebeacon" / "beacon.json").write_text("{}")
    (tmp_path / ".codebeacon" / "cache" / "cache.json").write_text("{}")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("module.exports = {}\n")
    (tmp_path / "real.py").write_text("z = 3\n")  # the only watchable change

    t.join(timeout=8)

    assert not t.is_alive()
    assert len(calls) == 1
    changed = calls[0]
    assert changed, "a watchable source edit should have fired one resync"
    # The load-bearing assertion: nothing under .codebeacon/ or node_modules/,
    # and no index artifact (*.json), ever leaks into a resync batch — otherwise
    # the watcher would resync on its own writes forever.
    assert not any(
        "/.codebeacon/" in p or "/node_modules/" in p or p.endswith(".json")
        for p in changed
    )
    assert all(_is_code(p) for p in changed)
