"""Pin the public API of codebeacon.pipeline after the 0.6.0 extraction.

The CLI and pipeline modules were split in 0.6.0 — cli.py kept argument
parsing and dispatch, pipeline.py owns the extraction + write flow. These
tests guard the contract between them so a future "let's tidy up the CLI"
refactor doesn't silently re-merge them or change the entry-point names.
"""
from __future__ import annotations

import inspect

import pytest


def test_pipeline_module_imports_cleanly():
    """The whole point of the split — pipeline.py must be importable
    without pulling in argparse or CLI machinery."""
    import codebeacon.pipeline as pipeline
    assert pipeline is not None


def test_public_entry_points_exposed():
    """cli.py imports these by name. If the names drift, the CLI breaks
    at startup. Pin them here so the failure is a unit-test failure
    instead of a runtime ImportError in users' terminals."""
    from codebeacon.pipeline import (
        emit_failure_report,
        run_deep_dive_pipeline,
        run_pipeline,
        write_project_artifact_outputs,
    )
    assert callable(emit_failure_report)
    assert callable(run_pipeline)
    assert callable(run_deep_dive_pipeline)
    assert callable(write_project_artifact_outputs)


def test_run_pipeline_signature():
    """If someone changes positional args here, every cli call site breaks
    silently (they pass positionally). Lock the signature."""
    from codebeacon.pipeline import run_pipeline
    sig = inspect.signature(run_pipeline)
    params = list(sig.parameters)
    assert params == ["projects", "output_dir", "args"]


def test_run_deep_dive_pipeline_signature():
    from codebeacon.pipeline import run_deep_dive_pipeline
    sig = inspect.signature(run_deep_dive_pipeline)
    params = list(sig.parameters)
    assert params == ["projects", "workspace_output_dir", "args"]


def test_emit_failure_report_returns_zero_on_clean_run(tmp_path):
    """No failures → exit 0, no file written, nothing on stderr."""
    from argparse import Namespace
    from codebeacon.common.types import ProjectInfo
    from codebeacon.pipeline import emit_failure_report
    from codebeacon.wave import WaveResult

    project = ProjectInfo(
        name="demo", path="/tmp/demo", framework="python",
        language="python", signature_file="pyproject.toml",
    )
    wave = WaveResult(project=project, file_count=5)
    rc = emit_failure_report([wave], str(tmp_path), Namespace())
    assert rc == 0
    assert not (tmp_path / "extraction-failures.json").exists()


def test_emit_failure_report_returns_two_on_threshold_breach(tmp_path, capsys):
    """Failure rate above threshold → exit code 2 (distinct from 1, which
    is reserved for other CLI errors). Stderr explains why."""
    from argparse import Namespace
    from codebeacon.common.types import ProjectInfo
    from codebeacon.pipeline import emit_failure_report
    from codebeacon.wave import ExtractionFailure, WaveResult

    project = ProjectInfo(
        name="demo", path="/tmp/demo", framework="python",
        language="python", signature_file="pyproject.toml",
    )
    # 5 of 10 attempted failed → 50% > 1% default threshold
    wave = WaveResult(
        project=project,
        file_count=10,
        failures=[
            ExtractionFailure(file_path=f"f{i}.py", framework="python",
                              error="boom", error_type="RuntimeError")
            for i in range(5)
        ],
    )
    rc = emit_failure_report([wave], str(tmp_path), Namespace())
    assert rc == 2
    assert (tmp_path / "extraction-failures.json").exists()
    err = capsys.readouterr().err
    assert "exceeds threshold" in err


def test_emit_failure_report_respects_explicit_threshold(tmp_path):
    """Passing --max-failure-rate=1.0 should allow any rate through."""
    from argparse import Namespace
    from codebeacon.common.types import ProjectInfo
    from codebeacon.pipeline import emit_failure_report
    from codebeacon.wave import ExtractionFailure, WaveResult

    project = ProjectInfo(
        name="demo", path="/tmp/demo", framework="python",
        language="python", signature_file="pyproject.toml",
    )
    wave = WaveResult(
        project=project,
        file_count=2,
        failures=[
            ExtractionFailure(file_path="a.py", framework="python",
                              error="boom", error_type="RuntimeError")
        ],
    )
    rc = emit_failure_report(
        [wave], str(tmp_path), Namespace(max_failure_rate=1.0),
    )
    # 50% failure but threshold is 100% → still 0
    assert rc == 0
    # File is still written (counts > 0) so users can audit
    assert (tmp_path / "extraction-failures.json").exists()
