"""Tests for ``codebeacon upgrade`` install-kind detection and dispatch."""

import argparse
import importlib.metadata
import subprocess
import sys

import pytest

from codebeacon import cli


class _FakeDist:
    def __init__(self, direct_url):
        self._direct_url = direct_url

    def read_text(self, name):
        if name == "direct_url.json":
            return self._direct_url
        return None


def _patch_dist(monkeypatch, direct_url):
    monkeypatch.setattr(
        importlib.metadata.Distribution,
        "from_name",
        classmethod(lambda cls, name: _FakeDist(direct_url)),
    )


def _patch_no_dist(monkeypatch):
    def _raise(cls, name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(
        importlib.metadata.Distribution, "from_name", classmethod(_raise)
    )


# ---------------------------------------------------------------- detection

def test_detect_editable(monkeypatch):
    _patch_dist(monkeypatch, '{"dir_info": {"editable": true}, "url": "file:///x"}')
    assert cli._detect_install_kind() == "editable"


def test_detect_pipx(monkeypatch):
    _patch_no_dist(monkeypatch)
    monkeypatch.setattr(sys, "prefix", "/home/u/.local/pipx/venvs/codebeacon")
    assert cli._detect_install_kind() == "pipx"


def test_detect_uv_tool(monkeypatch):
    _patch_no_dist(monkeypatch)
    monkeypatch.setattr(sys, "prefix", "/home/u/.local/share/uv/tools/codebeacon")
    assert cli._detect_install_kind() == "uv-tool"


def test_detect_plain_pip(monkeypatch):
    _patch_dist(monkeypatch, None)  # installed from an index: no direct_url.json
    monkeypatch.setattr(sys, "prefix", "/home/u/.pyenv/versions/3.11.11")
    assert cli._detect_install_kind() == "pip"


# ----------------------------------------------------------------- dispatch

@pytest.fixture
def upgrade_env(monkeypatch):
    """Neutralize network, skill refresh, and version probing."""
    calls = []

    def fake_call(cmd, *a, **k):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    monkeypatch.setattr(cli, "_pypi_latest_version", lambda timeout=5.0: "9.9.9")
    monkeypatch.setattr(cli, "_installed_version", lambda python: "9.9.9")
    return calls


def _args(force=False):
    return argparse.Namespace(force=force)


def test_upgrade_pipx_uses_pipx(monkeypatch, upgrade_env):
    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "pipx")
    assert cli._cmd_upgrade(_args()) == 0
    upgrade_cmd = upgrade_env[0]
    assert upgrade_cmd[0].endswith("pipx")
    assert upgrade_cmd[1:] == ["upgrade", "codebeacon"]


def test_upgrade_uv_tool_uses_uv(monkeypatch, upgrade_env):
    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "uv-tool")
    assert cli._cmd_upgrade(_args()) == 0
    upgrade_cmd = upgrade_env[0]
    assert upgrade_cmd[0].endswith("uv")
    assert upgrade_cmd[1:] == ["tool", "upgrade", "codebeacon"]


def test_upgrade_pip_uses_current_interpreter(monkeypatch, upgrade_env):
    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "pip")
    assert cli._cmd_upgrade(_args()) == 0
    assert upgrade_env[0] == [
        sys.executable, "-m", "pip", "install", "--upgrade", "codebeacon"
    ]


def test_upgrade_editable_skips_package_upgrade(monkeypatch, upgrade_env, capsys):
    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "editable")
    assert cli._cmd_upgrade(_args()) == 0
    # only the SKILL.md refresh subprocess ran — no pip/pipx/uv invocation
    assert upgrade_env == [[sys.executable, "-m", "codebeacon", "install"]]
    assert "editable" in capsys.readouterr().err


def test_upgrade_pip_without_pip_module_errors(monkeypatch, upgrade_env, capsys):
    import importlib.util

    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "pip")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    # Pin the non-uv-venv branch. Otherwise this suite (which itself runs inside
    # a uv-created .venv) would take the uv-specific branch and never print the
    # pipx/uv-tool advice this test is about. The uv-venv branch has its own
    # coverage in tests/test_audit_069_cli.py.
    monkeypatch.setattr(cli, "_is_uv_venv", lambda: False)
    assert cli._cmd_upgrade(_args()) == 1
    assert upgrade_env == []  # nothing was executed
    err = capsys.readouterr().err
    assert "pipx upgrade codebeacon" in err
    assert "uv tool upgrade codebeacon" in err


def test_upgrade_warns_when_version_unchanged(monkeypatch, upgrade_env, capsys):
    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "pip")
    from codebeacon import __version__ as current

    monkeypatch.setattr(cli, "_installed_version", lambda python: current)
    assert cli._cmd_upgrade(_args()) == 0
    assert f"still on codebeacon {current}" in capsys.readouterr().err


def test_upgrade_failure_hints_externally_managed(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_detect_install_kind", lambda: "pip")
    monkeypatch.setattr(cli, "_pypi_latest_version", lambda timeout=5.0: None)
    monkeypatch.setattr(subprocess, "call", lambda cmd, *a, **k: 1)
    assert cli._cmd_upgrade(_args()) == 1
    assert "externally-managed-environment" in capsys.readouterr().err
