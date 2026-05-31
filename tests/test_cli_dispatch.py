"""CLI auto-dispatch: ``codebeacon <path>`` → ``codebeacon scan <path>``."""

from __future__ import annotations

import io

from codebeacon.cli import _maybe_inject_scan, _KNOWN_SUBCOMMANDS, _ensure_utf8_stdio


def test_bare_path_becomes_scan():
    assert _maybe_inject_scan(["./src"]) == ["scan", "./src"]


def test_bare_dot_becomes_scan_dot():
    assert _maybe_inject_scan(["."]) == ["scan", "."]


def test_existing_subcommand_left_alone():
    for cmd in _KNOWN_SUBCOMMANDS:
        assert _maybe_inject_scan([cmd]) == [cmd]


def test_flag_left_alone():
    assert _maybe_inject_scan(["--version"]) == ["--version"]
    assert _maybe_inject_scan(["--help"]) == ["--help"]


def test_empty_argv_left_alone():
    assert _maybe_inject_scan([]) == []


def test_scan_with_extra_args_left_alone():
    assert _maybe_inject_scan(["scan", "./src", "--update"]) == [
        "scan", "./src", "--update",
    ]


def test_path_with_extra_args_becomes_scan():
    assert _maybe_inject_scan(["./src", "--update"]) == [
        "scan", "./src", "--update",
    ]


def test_knowledge_subcommand_recognized():
    assert _maybe_inject_scan(["knowledge", "./docs"]) == ["knowledge", "./docs"]


# ── _ensure_utf8_stdio: Windows non-UTF-8 console crash (graphify #992) ──

def test_ensure_utf8_forces_utf8_on_cp1252_stream(monkeypatch):
    """A cp1252 stream (Windows default console) would raise UnicodeEncodeError
    on our ``→``/``⚠`` output; after the fix the stream is forced to UTF-8."""
    cp1252_stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    # Reproduce the original crash before reconfiguring.
    import pytest
    with pytest.raises(UnicodeEncodeError):
        cp1252_stream.write("⚠ build → done\n")
        cp1252_stream.flush()

    monkeypatch.setattr("sys.stdout", cp1252_stream)
    monkeypatch.setattr("sys.stderr", cp1252_stream)
    _ensure_utf8_stdio()
    assert cp1252_stream.encoding == "utf-8"
    # Now the same non-ASCII output succeeds instead of crashing.
    cp1252_stream.write("⚠ build → done\n")
    cp1252_stream.flush()


def test_ensure_utf8_tolerates_streams_without_reconfigure(monkeypatch):
    """Redirected/legacy streams without ``reconfigure`` must not crash."""
    class NoReconfigure:
        encoding = "ascii"

    monkeypatch.setattr("sys.stdout", NoReconfigure())
    monkeypatch.setattr("sys.stderr", NoReconfigure())
    _ensure_utf8_stdio()  # must be a no-op, not raise
