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

from codebeacon.common.io import write_text_if_changed
from codebeacon.wave import ExtractionFailure, WaveResult


EXTRACTION_FAILURES_FILENAME = "extraction-failures.json"
SEMANTIC_STATS_FILENAME = "semantic-stats.json"
IGNORED_FILENAME = "ignored.json"

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
    write_text_if_changed(
        out_path,
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
    )
    return report, out_path


# ── What the file collector left out ──────────────────────────────────────────

@dataclass
class IgnoredReport:
    """Why files and directories are missing from the collected corpus.

    An over-broad ignore rule and a clean scan look identical from the outside:
    both report N files and exit 0. This bucket is what makes the difference
    visible — every pruned subtree, dropped file and unreadable directory is
    recorded with a cause, so "where did my module go?" is one artefact away.

    Bounded twice over so a pathological tree cannot bloat the artefact: a
    pruned directory contributes exactly one entry no matter how many files sit
    beneath it, per-directory file lists stop at ``max_per_dir``, and each
    bucket stops at ``max_entries``. The counts stay exact past both caps.
    """

    max_entries: int = 500
    max_per_dir: int = 20

    dirs: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    permission_denied: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    truncated: bool = False

    # Not serialised: per-parent-directory tallies backing ``max_per_dir``.
    _per_dir: dict[str, int] = field(default_factory=dict, repr=False)

    def add_dir(self, path: str, reason: str) -> None:
        self.counts[reason] = self.counts.get(reason, 0) + 1
        if len(self.dirs) < self.max_entries:
            self.dirs.append({"path": path, "reason": reason})
        else:
            self.truncated = True

    def add_file(self, path: str, reason: str) -> None:
        self.counts[reason] = self.counts.get(reason, 0) + 1
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        seen = self._per_dir.get(parent, 0)
        self._per_dir[parent] = seen + 1
        if seen >= self.max_per_dir or len(self.files) >= self.max_entries:
            self.truncated = True
            return
        self.files.append({"path": path, "reason": reason})

    def add_permission_denied(self, path: str) -> None:
        self.counts["permission_denied"] = self.counts.get("permission_denied", 0) + 1
        if len(self.permission_denied) < self.max_entries:
            self.permission_denied.append(path)
        else:
            self.truncated = True

    @property
    def incomplete(self) -> bool:
        """True when the corpus is short through no decision of ours.

        A subtree we could not read is not the same as a subtree the user
        excluded: the files may well still exist. Callers that compare corpus
        sizes across runs — the shrink guard above all — must treat this as a
        reason to stay armed rather than to accept a smaller graph.
        """
        return bool(self.permission_denied)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def to_dict(self) -> dict:
        return {
            "counts": dict(self.counts),
            "total": self.total,
            "truncated": self.truncated,
            "incomplete": self.incomplete,
            "dirs": self.dirs,
            "files": self.files,
            "permission_denied": self.permission_denied,
        }


def write_ignored_report(
    report: IgnoredReport,
    output_dir: str | Path,
) -> Optional[Path]:
    """Write ignored.json (only when something was actually ignored).

    Mirrors :func:`write_extraction_failures`: an empty run removes a stale file
    from a previous scan rather than leaving a list that no longer applies.
    """
    out_path = Path(output_dir) / IGNORED_FILENAME

    if report.total == 0:
        if out_path.exists():
            out_path.unlink()
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(
        out_path,
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
    )
    return out_path


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
    write_text_if_changed(
        out_path,
        json.dumps(stats.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
    )
    return out_path
