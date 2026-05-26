"""LLM hallucination accounting + low-confidence drop tests for semantic-apply.

Contract pinned here:
  1. ``_classify_relation`` returns ``(label, was_known)`` — unknown labels
     still coerce to "references" but are flagged so apply() can count them.
  2. ``apply(beacon_dir, min_confidence=X)`` drops edges below the threshold
     and records the drops in ``ApplyResult.stats.edges_dropped_low_confidence``.
  3. After apply(), ``.codebeacon/semantic-stats.json`` is always written,
     even on a zero-applied run — that's exactly the case CI needs to see.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest

from codebeacon.diagnostics import SemanticApplyStats
from codebeacon.semantic_pipeline import (
    DEFAULT_MIN_CONFIDENCE_SCORE,
    _classify_relation,
    apply,
)


# ── _classify_relation ──────────────────────────────────────────────────────

class TestClassifyRelation:
    def test_known_relation_is_flagged_as_known(self):
        label, was_known = _classify_relation("calls")
        assert label == "calls"
        assert was_known is True

    def test_known_relation_case_insensitive(self):
        label, was_known = _classify_relation("  CALLS  ")
        assert label == "calls"
        assert was_known is True

    def test_unknown_relation_coerces_but_flags(self):
        """A hallucinated label still coerces to "references" so beacon.json
        stays inside the closed set, but ``was_known`` flips to False so
        apply() can count the hallucination."""
        label, was_known = _classify_relation("frobnicates")
        assert label == "references"
        assert was_known is False

    def test_empty_relation_is_unknown(self):
        label, was_known = _classify_relation("")
        assert label == "references"
        assert was_known is False

    def test_none_relation_is_unknown(self):
        label, was_known = _classify_relation(None)
        assert label == "references"
        assert was_known is False


# ── End-to-end apply() with min_confidence + hallucination counting ─────────

def _write_beacon_with_one_node(d: Path, node_id: str = "p::Foo") -> None:
    """Minimal beacon.json with one source node so apply() has something to
    attach LLM edges to."""
    G = nx.DiGraph()
    G.add_node(
        node_id,
        label="Foo",
        type="class",
        source_file="src/foo.py",
        line=10,
        project="p",
    )
    d.mkdir(parents=True, exist_ok=True)
    (d / "beacon.json").write_text(
        json.dumps(nxjson.node_link_data(G), ensure_ascii=False),
        encoding="utf-8",
    )


def _write_results(d: Path, rows: list[dict]) -> None:
    sem = d / "semantic" / "results"
    sem.mkdir(parents=True, exist_ok=True)
    chunk = sem / "chunk_001.jsonl"
    with open(chunk, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestApplyHallucinationStats:
    def test_unknown_relations_are_counted_per_label(self, tmp_path):
        _write_beacon_with_one_node(tmp_path)
        _write_results(tmp_path, [{
            "task_id": "t1",
            "source_node_id": "p::Foo",
            "edges": [
                {"target_name": "Bar", "relation": "frobnicates", "confidence_score": 0.9},
                {"target_name": "Baz", "relation": "frobnicates", "confidence_score": 0.9},
                {"target_name": "Qux", "relation": "wobbles", "confidence_score": 0.9},
                {"target_name": "Quux", "relation": "calls", "confidence_score": 0.9},  # known
            ],
        }])

        result = apply(tmp_path)
        stats = result.stats
        assert stats is not None
        assert stats.edges_total == 4
        # 3 of 4 had hallucinated labels
        assert stats.relations_coerced == 3
        assert stats.unknown_relation_labels.get("frobnicates") == 2
        assert stats.unknown_relation_labels.get("wobbles") == 1
        # The known "calls" entry should NOT appear in the hallucination map
        assert "calls" not in stats.unknown_relation_labels

    def test_low_confidence_edges_are_dropped(self, tmp_path):
        _write_beacon_with_one_node(tmp_path)
        _write_results(tmp_path, [{
            "task_id": "t1",
            "source_node_id": "p::Foo",
            "edges": [
                {"target_name": "Hi", "relation": "calls", "confidence_score": 0.9},
                {"target_name": "Mid", "relation": "calls", "confidence_score": 0.6},
                {"target_name": "Low", "relation": "calls", "confidence_score": 0.3},
                {"target_name": "Lowest", "relation": "calls", "confidence_score": 0.1},
            ],
        }])

        result = apply(tmp_path, min_confidence=0.5)
        assert result.stats.edges_total == 4
        assert result.stats.edges_dropped_low_confidence == 2  # 0.3 and 0.1
        # Only 0.9 and 0.6 actually became edges
        assert result.applied == 2

    def test_min_confidence_param_overrides_default(self, tmp_path):
        """Passing min_confidence=0.0 should let everything through."""
        _write_beacon_with_one_node(tmp_path)
        _write_results(tmp_path, [{
            "task_id": "t1",
            "source_node_id": "p::Foo",
            "edges": [
                {"target_name": "VeryLow", "relation": "calls", "confidence_score": 0.05},
            ],
        }])

        result = apply(tmp_path, min_confidence=0.0)
        assert result.applied == 1
        assert result.stats.edges_dropped_low_confidence == 0

    def test_default_threshold_is_half(self):
        # Pinning so a future change to default is a deliberate review,
        # not an accidental loosening.
        assert DEFAULT_MIN_CONFIDENCE_SCORE == 0.5

    def test_confidence_score_coerced_counted(self, tmp_path):
        """Out-of-range / None scores are silently clamped by _coerce_score.
        The stats must show how many were coerced so a prompt regression
        producing all-None scores is visible to CI."""
        _write_beacon_with_one_node(tmp_path)
        _write_results(tmp_path, [{
            "task_id": "t1",
            "source_node_id": "p::Foo",
            "edges": [
                {"target_name": "A", "relation": "calls", "confidence_score": None},
                {"target_name": "B", "relation": "calls", "confidence_score": 1.5},   # clamped
                {"target_name": "C", "relation": "calls", "confidence_score": 0.9},   # clean
            ],
        }])

        result = apply(tmp_path, min_confidence=0.0)
        # Two of three needed coercion (None defaulted to 0.7, 1.5 clamped to 1.0)
        assert result.stats.confidence_score_coerced == 2


class TestSemanticStatsFile:
    def test_stats_json_written_on_success(self, tmp_path):
        _write_beacon_with_one_node(tmp_path)
        _write_results(tmp_path, [{
            "task_id": "t1",
            "source_node_id": "p::Foo",
            "edges": [
                {"target_name": "Bar", "relation": "calls", "confidence_score": 0.9},
            ],
        }])
        apply(tmp_path)
        stats_path = tmp_path / "semantic-stats.json"
        assert stats_path.exists()
        data = json.loads(stats_path.read_text())
        assert data["edges_total"] == 1
        assert data["edges_accepted"] == 1

    def test_stats_json_written_even_when_zero_applied(self, tmp_path):
        """The zero-applied case is exactly when CI most wants to see stats
        — that's a "the LLM step produced nothing usable" alarm."""
        _write_beacon_with_one_node(tmp_path)
        _write_results(tmp_path, [{
            "task_id": "t1",
            "source_node_id": "p::Foo",
            "edges": [
                # All below default threshold of 0.5
                {"target_name": "X", "relation": "calls", "confidence_score": 0.1},
                {"target_name": "Y", "relation": "calls", "confidence_score": 0.2},
            ],
        }])
        result = apply(tmp_path)
        assert result.applied == 0
        stats_path = tmp_path / "semantic-stats.json"
        assert stats_path.exists()
        data = json.loads(stats_path.read_text())
        assert data["edges_total"] == 2
        assert data["edges_dropped_low_confidence"] == 2
