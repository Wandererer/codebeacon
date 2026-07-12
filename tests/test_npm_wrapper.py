"""Validate the npm ``@codebeacon/mcp`` wrapper without requiring Node.

The wrapper (``npm/``) is a zero-dependency Node shim that launches
``codebeacon serve`` for MCP clients that expect an ``npx`` command. These
checks are mostly static (JSON + source-string assertions) so they run on any
machine; a real ``node`` smoke test is layered on top and skipped when Node or
codebeacon is absent.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py3.10 fallback
    tomllib = None

REPO_ROOT = Path(__file__).resolve().parent.parent
NPM_DIR = REPO_ROOT / "npm"
PACKAGE_JSON = NPM_DIR / "package.json"
RUN_JS = NPM_DIR / "bin" / "run.js"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    if tomllib is not None:
        with PYPROJECT.open("rb") as fh:
            return tomllib.load(fh)["project"]["version"]
    # Fallback for interpreters without tomllib: pull the version line out of the
    # [project] table by hand.
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "could not find version in pyproject.toml"
    return match.group(1)


@pytest.fixture(scope="module")
def package_json() -> dict:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def run_js_source() -> str:
    return RUN_JS.read_text(encoding="utf-8")


# ── Static: package.json ──────────────────────────────────────────────────────

def test_files_exist():
    assert PACKAGE_JSON.is_file(), "npm/package.json missing"
    assert RUN_JS.is_file(), "npm/bin/run.js missing"


def test_package_json_is_valid_json(package_json):
    # json.loads in the fixture already parsed it; assert we got an object.
    assert isinstance(package_json, dict)


def test_package_name(package_json):
    assert package_json["name"] == "@codebeacon/mcp"


def test_bin_entry_points_at_run_js(package_json):
    bin_entry = package_json["bin"]
    assert bin_entry == {"codebeacon-mcp": "bin/run.js"}
    # The declared bin target must actually exist.
    assert (NPM_DIR / bin_entry["codebeacon-mcp"]).is_file()


def test_engines_node_at_least_18(package_json):
    node_range = package_json["engines"]["node"]
    match = re.search(r"(\d+)", node_range)
    assert match, f"unparseable node engine range: {node_range!r}"
    assert int(match.group(1)) >= 18


def test_files_allowlist_ships_the_wrapper(package_json):
    files = package_json["files"]
    assert "bin/run.js" in files
    assert "README.md" in files


def test_metadata_mirrors_pyproject(package_json):
    # License and repository should match the Python package's metadata so the
    # two distributions describe the same project.
    assert package_json["license"] == "MIT"
    assert "github.com/codebeacon/codebeacon" in package_json["repository"]["url"]


def test_version_matches_pyproject(package_json):
    assert package_json["version"] == _pyproject_version()


# ── Static: bin/run.js ────────────────────────────────────────────────────────

def test_run_js_has_node_shebang(run_js_source):
    assert run_js_source.startswith("#!/usr/bin/env node")


def test_resolution_order_is_path_uvx_pipx_python(run_js_source):
    # The four runners must appear, and in the documented priority order:
    # PATH codebeacon → uvx → pipx → python3 -m.
    idx_codebeacon = run_js_source.index('["codebeacon", []]')
    idx_uvx = run_js_source.index('"uvx"')
    idx_pipx = run_js_source.index('"pipx"')
    idx_python = run_js_source.index('"python3"')
    assert idx_codebeacon < idx_uvx < idx_pipx < idx_python


def test_launches_serve_subcommand(run_js_source):
    # The wrapper must invoke `serve` (not invent another subcommand) and forward
    # the user's args verbatim.
    assert '"serve"' in run_js_source
    assert "process.argv.slice(2)" in run_js_source


def test_never_writes_to_stdout(run_js_source):
    # stdout is the MCP JSON-RPC channel: the wrapper's own diagnostics must go
    # to stderr only. Guard against the easy mistakes.
    assert "console.log(" not in run_js_source
    assert "process.stdout.write(" not in run_js_source
    # And it must actually use stderr for its logging.
    assert "process.stderr.write(" in run_js_source


def test_probe_discards_child_stdout(run_js_source):
    # The `--version` probe must not let the child's stdout leak into the MCP
    # stream, so it runs with stdio discarded.
    assert '"--version"' in run_js_source
    assert 'stdio: "ignore"' in run_js_source


def test_real_spawn_inherits_stdio(run_js_source):
    # The actual server launch must inherit stdio so JSON-RPC bytes pass through.
    assert 'stdio: "inherit"' in run_js_source


def test_error_path_lists_install_options(run_js_source):
    # When nothing resolves, the stderr message must show all three installers.
    assert "pipx install codebeacon" in run_js_source
    assert "uv tool install codebeacon" in run_js_source
    assert "pip install codebeacon" in run_js_source


def test_forwards_termination_signals(run_js_source):
    # Signals from the client should tear down the Python child, not orphan it.
    assert 'process.on("SIGINT"' in run_js_source
    assert 'process.on("SIGTERM"' in run_js_source


# ── Dynamic smoke: only when node + codebeacon are both available ─────────────

_NODE = shutil.which("node")
_CODEBEACON = shutil.which("codebeacon")


@pytest.mark.skipif(
    _NODE is None or _CODEBEACON is None,
    reason="requires both `node` and `codebeacon` on PATH",
)
def test_smoke_wrapper_launches_serve():
    """`node run.js --help` should resolve codebeacon and reach `serve --help`.

    ``serve --help`` makes argparse print help and exit 0 without blocking on
    stdin, so this exercises the full resolve→spawn path end to end. The wrapper
    writes its own diagnostics to stderr, so serve's help text is what lands on
    stdout — proof the args were forwarded and stdio was inherited cleanly.
    """
    proc = subprocess.run(
        [_NODE, str(RUN_JS), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    # serve's help advertises the only flag it accepts.
    assert "--dir" in proc.stdout, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    # The wrapper's launch diagnostic goes to stderr, never stdout.
    assert "launching:" in proc.stderr
    assert "[codebeacon-mcp]" not in proc.stdout


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
