"""Pipeline diagnostics: extraction failures + LLM enrichment stats.

These are first-class artefacts (not log lines) so users — and CI — can
detect partial graphs deterministically. The two consumers today:

  * ``codebeacon scan`` / ``sync`` — writes extraction-failures.json after
    Pass 1 and bails out non-zero when the failure rate breaches a
    configurable threshold (default 1%).
  * ``codebeacon semantic-apply`` — writes semantic-stats.json with counts
    of unknown relation labels, dropped low-confidence edges, and
    coerced confidence_score values.

Keep this module free of heavy imports (no networkx, no tree-sitter) so it
can be reused in lightweight diagnostic tooling.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from codebeacon.wave import ExtractionFailure, WaveResult


EXTRACTION_FAILURES_FILENAME = "extraction-failures.json"
SEMANTIC_STATS_FILENAME = "semantic-stats.json"

# Default threshold: if >1% of attempted files fail extraction, the CLI
# returns a non-zero exit code. Tunable via --max-failure-rate.
DEFAULT_MAX_FAILURE_RATE = 0.01


@dataclass
class ExtractionFailureReport:
    """Aggregate report of extraction failures across projects in one run."""
    total_files: int = 0
    total_attempted: int = 0          # files - cache hits
    total_failures: int = 0
    failure_rate: float = 0.0
    by_framework: dict[str, int] = field(default_factory=dict)
    by_error_type: dict[str, int] = field(default_factory=dict)
    failures: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def collect_extraction_failures(waves: Iterable[WaveResult]) -> ExtractionFailureReport:
    """Aggregate failures across one or more ``WaveResult`` objects.

    Computes failure_rate over attempted files (i.e. excludes cache hits),
    because cache hits are not a fair denominator for "did extraction work
    this run." A repo with 100% cache hits should never trip the threshold.
    """
    report = ExtractionFailureReport()
    for wave in waves:
        report.total_files += wave.file_count
        report.total_attempted += wave.file_count - wave.skipped_count
        for f in wave.failures:
            report.total_failures += 1
            report.by_framework[f.framework] = report.by_framework.get(f.framework, 0) + 1
            report.by_error_type[f.error_type] = report.by_error_type.get(f.error_type, 0) + 1
            report.failures.append(f.to_dict())

    if report.total_attempted > 0:
        report.failure_rate = report.total_failures / report.total_attempted
    return report


def write_extraction_failures(
    waves: Iterable[WaveResult],
    output_dir: str | Path,
) -> tuple[ExtractionFailureReport, Optional[Path]]:
    """Write extraction-failures.json (only if there were any failures).

    Returns ``(report, path_or_None)``. ``path_or_None`` is None when there
    are no failures — we don't want to leave a stale empty file from a
    previous bad run in the directory.
    """
    report = collect_extraction_failures(waves)
    out_path = Path(output_dir) / EXTRACTION_FAILURES_FILENAME

    if report.total_failures == 0:
        # Clean up any stale file from a previous run so users don't get
        # confused by an old failures list that no longer applies.
        if out_path.exists():
            out_path.unlink()
        return report, None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return report, out_path


# ── Semantic-pipeline stats (LLM enrichment) ──────────────────────────────────

@dataclass
class SemanticApplyStats:
    """Counts of how LLM-emitted edges were gated during semantic-apply.

    Surfaced both to stdout and to ``semantic-stats.json`` so a CI step can
    fail on a hallucination spike without parsing logs.
    """
    edges_total: int = 0          # rows seen in semantic-results.jsonl
    edges_accepted: int = 0       # made it into beacon.json
    edges_dropped_low_confidence: int = 0
    edges_dropped_unknown_relation: int = 0   # since 0.6.0: drop instead of coerce
    relations_coerced: int = 0    # legacy/unknown labels mapped to "references"
    confidence_score_coerced: int = 0
    unknown_relation_labels: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def write_semantic_stats(
    stats: SemanticApplyStats,
    output_dir: str | Path,
) -> Path:
    """Write semantic-stats.json next to beacon.json."""
    out_path = Path(output_dir) / SEMANTIC_STATS_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(stats.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
