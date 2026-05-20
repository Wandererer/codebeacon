"""Hardening: JSONL guard, score coercion, snapshot backup before apply.

Ports the spirit of graphify 0.8.11 (#924) — empty choices / message=None
guard — into codebeacon's apply path. codebeacon reads JSONL written by a
subagent rather than calling an OpenAI-compatible API directly, so the
failure modes look different in surface but the same in shape: malformed
records (None, list, str), missing required fields, non-numeric
``confidence_score`` values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codebeacon.semantic_pipeline import (
    _coerce_score,
    _iter_jsonl,
    _snapshot_beacon,
)


# ── _coerce_score ───────────────────────────────────────────────────────────


def test_coerce_score_handles_none():
    assert _coerce_score(None) == 0.7
    assert _coerce_score(None, default=0.5) == 0.5


def test_coerce_score_handles_string():
    assert _coerce_score("0.9") == 0.9


def test_coerce_score_handles_garbage():
    assert _coerce_score("not a number") == 0.7
    assert _coerce_score({}) == 0.7
    assert _coerce_score([0.5]) == 0.7


def test_coerce_score_clamps_range():
    assert _coerce_score(1.5) == 1.0
    assert _coerce_score(-0.2) == 0.0


def test_coerce_score_nan_falls_back_to_default():
    assert _coerce_score(float("nan")) == 0.7


# ── _iter_jsonl guards ──────────────────────────────────────────────────────


def test_iter_jsonl_skips_blank_and_invalid_lines(tmp_path: Path):
    p = tmp_path / "chunk.jsonl"
    p.write_text(
        "\n"
        "{\"task_id\":\"a\",\"edges\":[]}\n"
        "not even json\n"
        "null\n"
        "[1,2,3]\n"
        "\"a string\"\n"
        "```json\n"
        "{\"task_id\":\"b\",\"edges\":[]}\n",
        encoding="utf-8",
    )
    rows = list(_iter_jsonl(p))
    assert len(rows) == 2
    assert {r["task_id"] for r in rows} == {"a", "b"}


def test_iter_jsonl_missing_file_yields_nothing(tmp_path: Path):
    p = tmp_path / "does-not-exist.jsonl"
    assert list(_iter_jsonl(p)) == []


def test_iter_jsonl_never_raises_on_attrerror(tmp_path: Path):
    """Regression: agent emits ``null`` lines from an empty-choices API
    response — without the dict guard, downstream ``obj.get("task_id")``
    would raise AttributeError."""
    p = tmp_path / "chunk.jsonl"
    p.write_text("null\nnull\nnull\n", encoding="utf-8")
    rows = list(_iter_jsonl(p))
    assert rows == []
    # And caller-side .get() never gets a chance to crash.
    for r in rows:
        r.get("task_id")  # would only run if we yielded a dict — and we won't.


# ── _snapshot_beacon ────────────────────────────────────────────────────────


def test_snapshot_creates_bak_file(tmp_path: Path):
    beacon = tmp_path / "beacon.json"
    beacon.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    snap = _snapshot_beacon(beacon)
    assert snap is not None
    assert snap.name == "beacon.json.bak"
    assert snap.exists()
    assert snap.read_text(encoding="utf-8") == beacon.read_text(encoding="utf-8")


def test_snapshot_missing_source_returns_none(tmp_path: Path):
    beacon = tmp_path / "beacon.json"  # not created
    assert _snapshot_beacon(beacon) is None


def test_snapshot_overwrites_previous_bak(tmp_path: Path):
    beacon = tmp_path / "beacon.json"
    beacon.write_text("v1", encoding="utf-8")
    _snapshot_beacon(beacon)

    beacon.write_text("v2", encoding="utf-8")
    snap = _snapshot_beacon(beacon)
    assert snap is not None
    assert snap.read_text(encoding="utf-8") == "v2"
