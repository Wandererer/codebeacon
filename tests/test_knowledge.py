"""Knowledge map: classification heuristics + KNOWLEDGE.md rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.knowledge import build_knowledge_map
from codebeacon.knowledge.generator import _classify


def _classify_text(text: str, filename: str = "note.md", path: str = "note.md"):
    return _classify(text, path, filename)


# ── Category classifier ────────────────────────────────────────────────────


def test_adr_filename_is_decision():
    note = _classify_text(
        "# Use Postgres\n\nWe chose Postgres over MongoDB.",
        filename="adr-001-database.md",
        path="decisions/adr-001-database.md",
    )
    assert note is not None
    assert note.category == "decision"
    assert note.title == "Use Postgres"


def test_decision_heading_overrides_generic_filename():
    body = "# Polar over Stripe\n\n## Decision\nGoing with Polar.sh\n"
    note = _classify_text(body, filename="payments.md", path="notes/payments.md")
    assert note is not None
    assert note.category == "decision"


def test_meeting_signal_attendees_plus_action_items():
    body = (
        "# Standup 2026-03-20\n\n"
        "Attendees: alice, bob\n"
        "Action items:\n- ship it\n"
    )
    note = _classify_text(body, filename="standup-2026-03-20.md", path="meetings/standup-2026-03-20.md")
    assert note is not None
    assert note.category == "meeting"
    assert note.date == "2026-03-20"


def test_retro_filename():
    body = "# Q1 Retro\n\n## What went well\n- shipped\n"
    note = _classify_text(body, filename="retro-q1.md", path="retro-q1.md")
    assert note is not None
    assert note.category == "retro"


def test_spec_via_goals_and_requirements_headings():
    body = "# Payments Spec\n\n## Goals\nA\n\n## Requirements\nB\n"
    note = _classify_text(body, filename="payments.md", path="payments.md")
    assert note is not None
    assert note.category == "spec"


def test_research_filename():
    note = _classify_text(
        "# Vector DB benchmark\n\nPgvector vs Pinecone.",
        filename="benchmark.md",
        path="research/benchmark.md",
    )
    assert note is not None
    assert note.category == "research"


def test_open_questions_section():
    body = (
        "# Auth design\n\n"
        "## Open Questions\n"
        "- Should we support PayPal later?\n"
        "- Do we sunset Stripe Connect?\n"
    )
    note = _classify_text(body, filename="auth.md")
    assert note is not None
    assert len(note.open_questions) == 2
    assert "PayPal" in note.open_questions[0]


def test_obsidian_frontmatter_and_backlinks():
    body = (
        "---\n"
        "title: Decision — Database\n"
        "tags:\n"
        "  - decision\n"
        "  - infra\n"
        "date: 2026-03-15\n"
        "---\n\n"
        "Going with Postgres because [[Drizzle]] supports it.\n"
    )
    note = _classify_text(body, filename="2026-03-15-database.md")
    assert note is not None
    assert note.title == "Decision — Database"
    assert note.date == "2026-03-15"
    assert "decision" in note.tags
    assert "Drizzle" in note.backlinks
    # decision-style body matches the body regex even without filename hint.
    assert note.category == "decision"


def test_empty_file_returns_none():
    assert _classify_text("   \n\n", filename="empty.md") is None


# ── Full pipeline ──────────────────────────────────────────────────────────


def test_build_knowledge_map_writes_file(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "decisions").mkdir()
    (vault / "decisions" / "adr-001-db.md").write_text(
        "# Use Postgres\n\n## Decision\nWent with Postgres on 2026-03-15.\n",
        encoding="utf-8",
    )
    (vault / "meetings").mkdir()
    (vault / "meetings" / "standup-2026-03-20.md").write_text(
        "# Standup\n\nAttendees: alice\nAction items:\n- ship\n",
        encoding="utf-8",
    )
    (vault / "noisy" / "node_modules").mkdir(parents=True)
    (vault / "noisy" / "node_modules" / "junk.md").write_text(
        "# Should be skipped\n", encoding="utf-8"
    )

    out_dir = tmp_path / "out"
    result = build_knowledge_map(vault, out_dir)

    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.name == "KNOWLEDGE.md"

    # node_modules entries pruned.
    assert all("node_modules" not in n.path for n in result.notes)

    content = result.output_path.read_text(encoding="utf-8")
    assert "Knowledge Map" in content
    assert "Key Decisions" in content
    assert "Use Postgres" in content
    assert "Standup" in content
    counts = result.counts()
    assert counts.get("decision", 0) >= 1
    assert counts.get("meeting", 0) >= 1


def test_build_knowledge_map_handles_unreadable_files(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    # Write something invalid as UTF-8 then a normal file — the bad one
    # should be skipped silently via errors="replace", not abort the scan.
    (vault / "bad.md").write_bytes(b"# Title\n\n\xff\xfe broken bytes\n")
    (vault / "good.md").write_text("# Hello\n\nA real note.\n", encoding="utf-8")

    out_dir = tmp_path / "out"
    result = build_knowledge_map(vault, out_dir)
    assert any(n.path == "good.md" for n in result.notes)
