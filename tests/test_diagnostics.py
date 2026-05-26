"""Tests for codebeacon.diagnostics — extraction failures + semantic stats.

These tests pin the contract that:
  1. Failed extractions are returned as ``ExtractionFailure`` objects, NOT
     silently dropped with a warnings.warn.
  2. ``write_extraction_failures`` produces a stable JSON shape that CI can
     parse without parsing log output.
  3. A previous run's failures file is cleaned up when the current run has
     none — no stale "looks like things are broken" artefact.
  4. ``failure_rate`` ignores cache hits so a 100% cache-hit run is never
     flagged as a partial graph.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from codebeacon.common.types import ProjectInfo
from codebeacon.diagnostics import (
    DEFAULT_MAX_FAILURE_RATE,
    ExtractionFailureReport,
    collect_extraction_failures,
    write_extraction_failures,
)
from codebeacon.wave import ExtractionFailure, WaveResult, _extract_file


def _project(name: str = "demo", framework: str = "python") -> ProjectInfo:
    return ProjectInfo(
        name=name,
        path="/tmp/demo",
        framework=framework,
        language=framework,
        signature_file="pyproject.toml",
    )


def _failure(file_path: str, framework: str = "python", err: str = "boom") -> ExtractionFailure:
    return ExtractionFailure(
        file_path=file_path,
        framework=framework,
        error=err,
        error_type="RuntimeError",
    )


class TestExtractFileNeverReturnsNone:
    """Pre-0.6.0 ``_extract_file`` returned None on failure and warned —
    callers had no way to count or surface failures. After the hardening
    pass it returns an ExtractionFailure object instead."""

    def test_unreadable_path_returns_failure(self, tmp_path):
        result = _extract_file(
            file_path=str(tmp_path / "does-not-exist.py"),
            framework="python",
            project_path=str(tmp_path),
        )
        # On a missing file the extractors typically succeed with empty
        # results because tree-sitter parsers don't raise; the contract
        # we care about here is "never None". So either an empty dict OR
        # a failure is acceptable — both are non-None.
        assert result is not None
        assert isinstance(result, (dict, ExtractionFailure))

    def test_extractor_exception_is_captured(self, tmp_path, monkeypatch):
        """When an extractor raises, the file must surface as ExtractionFailure."""
        from codebeacon.extract import routes as routes_mod

        def boom(*a, **kw):
            raise RuntimeError("synthetic extractor crash")

        monkeypatch.setattr(routes_mod, "extract_routes", boom)

        src = tmp_path / "a.py"
        src.write_text("x = 1\n")

        result = _extract_file(
            file_path=str(src),
            framework="python",
            project_path=str(tmp_path),
        )
        assert isinstance(result, ExtractionFailure)
        assert result.error_type == "RuntimeError"
        assert "synthetic" in result.error
        assert result.file_path == str(src)
        assert result.framework == "python"


class TestCollectExtractionFailures:
    def test_empty_waves_produces_zero_report(self):
        report = collect_extraction_failures([])
        assert report.total_files == 0
        assert report.total_failures == 0
        assert report.failure_rate == 0.0

    def test_aggregates_across_multiple_projects(self):
        w1 = WaveResult(
            project=_project("svc-a", "python"),
            file_count=10,
            failures=[_failure("svc-a/a.py"), _failure("svc-a/b.py")],
        )
        w2 = WaveResult(
            project=_project("svc-b", "java"),
            file_count=5,
            failures=[_failure("svc-b/X.java", framework="java")],
        )
        report = collect_extraction_failures([w1, w2])
        assert report.total_files == 15
        assert report.total_failures == 3
        assert report.by_framework == {"python": 2, "java": 1}
        assert report.by_error_type == {"RuntimeError": 3}
        # 3 failures / 15 attempted (no cache hits)
        assert report.failure_rate == pytest.approx(3 / 15)

    def test_cache_hits_excluded_from_denominator(self):
        """100% cache hits should NOT trigger the failure threshold even
        if a stale failures list lingered (defensive)."""
        wave = WaveResult(
            project=_project(),
            file_count=10,
            skipped_count=10,    # all cache hits
            failures=[],
        )
        report = collect_extraction_failures([wave])
        assert report.total_attempted == 0
        assert report.failure_rate == 0.0


class TestWriteExtractionFailures:
    def test_writes_json_when_failures_present(self, tmp_path):
        wave = WaveResult(
            project=_project(),
            file_count=3,
            failures=[_failure("a.py"), _failure("b.py")],
        )
        report, path = write_extraction_failures([wave], tmp_path)
        assert path is not None
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["total_failures"] == 2
        assert data["total_attempted"] == 3
        assert "failures" in data
        assert len(data["failures"]) == 2

    def test_no_file_written_when_no_failures(self, tmp_path):
        wave = WaveResult(project=_project(), file_count=5)
        report, path = write_extraction_failures([wave], tmp_path)
        assert path is None
        assert report.total_failures == 0
        assert not (tmp_path / "extraction-failures.json").exists()

    def test_stale_failure_file_is_cleaned_up(self, tmp_path):
        """A previous bad run left extraction-failures.json behind.
        The current healthy run should delete it so users don't read
        last week's failure list and panic."""
        stale = tmp_path / "extraction-failures.json"
        stale.write_text('{"stale": true}')

        clean_wave = WaveResult(project=_project(), file_count=5)
        report, path = write_extraction_failures([clean_wave], tmp_path)
        assert path is None
        assert not stale.exists()

    def test_default_threshold_is_one_percent(self):
        # Pinning the constant so changing it in the future is a deliberate
        # decision visible in a code review, not an accidental loosening.
        assert DEFAULT_MAX_FAILURE_RATE == 0.01
