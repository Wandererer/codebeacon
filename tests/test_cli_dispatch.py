"""CLI auto-dispatch: ``codebeacon <path>`` → ``codebeacon scan <path>``."""

from __future__ import annotations

from codebeacon.cli import _maybe_inject_scan, _KNOWN_SUBCOMMANDS


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
