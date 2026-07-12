"""Knowledge ↔ code-graph linking + the ``beacon_knowledge`` MCP tool.

The ``codebeacon knowledge`` scan classifies markdown notes; this suite covers
the pass that links those notes into an existing ``beacon.json`` and the MCP
tool that surfaces them:

* path references produce a trusted EXTRACTED edge;
* bare name mentions produce an AMBIGUOUS edge — but only for distinctive
  compound identifiers, never for generic single words (the precision guard);
* the overlay round-trips through beacon.json;
* ``beacon_knowledge`` answers both "which notes touch this node" and keyword
  search.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from codebeacon.common.types import KNOWLEDGE_NODE_TYPE
from codebeacon.graph.write import load_beacon, write_beacon
from codebeacon.knowledge import build_knowledge_map, link_knowledge_to_graph
from codebeacon.knowledge.link import (
    extract_path_refs,
    is_distinctive_label,
    resolve_beacon_dir,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _write_code_beacon(beacon_dir: Path, specs: list[tuple]) -> None:
    """Write a minimal code beacon.json. specs: (id, label, type, source_file)."""
    G = nx.DiGraph()
    for node_id, label, ntype, source_file in specs:
        G.add_node(
            node_id, label=label, type=ntype,
            source_file=source_file, line=1, project="app",
        )
    beacon_dir.mkdir(parents=True, exist_ok=True)
    write_beacon(G, beacon_dir, project_roots=None)


def _vault_with(tmp_path: Path, files: dict[str, str]) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    for rel, body in files.items():
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return vault


def _edges_between(G: nx.DiGraph, note_substr: str, code_id: str) -> list[dict]:
    """All edge-attr dicts from a knowledge note (id contains note_substr) to code_id."""
    out = []
    for src, tgt, data in G.in_edges(code_id, data=True):
        if note_substr in src and G.nodes[src].get("type") == KNOWLEDGE_NODE_TYPE:
            out.append(data)
    return out


# ── (a) explicit path reference → EXTRACTED ──────────────────────────────────


def test_path_reference_links_with_high_confidence(tmp_path: Path):
    beacon = tmp_path / ".codebeacon"
    _write_code_beacon(beacon, [
        ("app::PaymentService", "PaymentService", "class", "src/payments/PaymentService.java"),
    ])
    vault = _vault_with(tmp_path, {
        "decisions/adr-001-payments.md": (
            "# Payments\n\n## Decision\n"
            "Route all charges through `src/payments/PaymentService.java`.\n"
        ),
    })

    result = build_knowledge_map(vault, tmp_path / "out")
    link = link_knowledge_to_graph(result, beacon)
    assert link is not None
    assert link.reference_edges == 1

    G, _ = load_beacon(beacon / "beacon.json")
    edges = _edges_between(G, "adr-001-payments", "app::PaymentService")
    assert len(edges) == 1
    # A path pointer is unambiguous — trusted, and never down-graded to a
    # duplicate mention even though the body also names ``PaymentService``.
    assert edges[0]["relation"] == "references"
    assert edges[0]["confidence"] == "EXTRACTED"
    assert edges[0]["confidence_score"] == 1.0


# ── (b) name mention → AMBIGUOUS ─────────────────────────────────────────────


def test_name_mention_links_as_ambiguous(tmp_path: Path):
    beacon = tmp_path / ".codebeacon"
    _write_code_beacon(beacon, [
        ("app::OrderService", "OrderService", "class", "src/orders/OrderService.java"),
    ])
    vault = _vault_with(tmp_path, {
        "notes/retro.md": (
            "# Q1 retro\n\n"
            "We agreed OrderService should retry failed charges before alerting.\n"
        ),
    })

    result = build_knowledge_map(vault, tmp_path / "out")
    link = link_knowledge_to_graph(result, beacon)
    assert link is not None
    assert link.mention_edges == 1
    assert link.reference_edges == 0

    G, _ = load_beacon(beacon / "beacon.json")
    edges = _edges_between(G, "retro", "app::OrderService")
    assert len(edges) == 1
    assert edges[0]["relation"] == "mentions"
    assert edges[0]["confidence"] == "AMBIGUOUS"
    assert edges[0]["confidence_score"] < 0.8  # below INFERRED


# ── (c) generic single-word mention does NOT link (precision guard) ──────────


def test_generic_word_does_not_link(tmp_path: Path):
    beacon = tmp_path / ".codebeacon"
    # Single-word labels — the exact prose-collision risk the guard defends.
    _write_code_beacon(beacon, [
        ("app::User", "User", "entity", "src/models/User.java"),
        ("app::Payment", "Payment", "entity", "src/models/Payment.java"),
    ])
    vault = _vault_with(tmp_path, {
        "notes/musing.md": (
            "# Onboarding musings\n\n"
            "The User signs in and makes a Payment during the first session.\n"
        ),
    })

    result = build_knowledge_map(vault, tmp_path / "out")
    link = link_knowledge_to_graph(result, beacon)
    assert link is not None
    assert link.reference_edges == 0
    assert link.mention_edges == 0
    assert link.linked_notes == 0

    G, _ = load_beacon(beacon / "beacon.json")
    assert _edges_between(G, "musing", "app::User") == []
    assert _edges_between(G, "musing", "app::Payment") == []


# ── (d) beacon.json round-trip preserves the overlay ─────────────────────────


def test_round_trip_preserves_knowledge_nodes_and_edges(tmp_path: Path):
    beacon = tmp_path / ".codebeacon"
    _write_code_beacon(beacon, [
        ("app::PaymentService", "PaymentService", "class", "src/payments/PaymentService.java"),
    ])
    vault = _vault_with(tmp_path, {
        "adr-001.md": "# ADR 1\n\nWe use `src/payments/PaymentService.java`.\n",
    })

    result = build_knowledge_map(vault, tmp_path / "out")
    link_knowledge_to_graph(result, beacon)

    G, meta = load_beacon(beacon / "beacon.json")
    note_id = "knowledge::adr-001.md"
    assert note_id in G
    nd = G.nodes[note_id]
    assert nd["type"] == KNOWLEDGE_NODE_TYPE
    assert nd["project"] == "knowledge"
    assert nd["note_path"] == "adr-001.md"
    # The code node still exists alongside the overlay.
    assert "app::PaymentService" in G
    assert G.has_edge(note_id, "app::PaymentService")
    # meta.node_count reflects code + knowledge nodes.
    assert meta["node_count"] == 2


def test_relinking_is_idempotent_and_drops_deleted_notes(tmp_path: Path):
    beacon = tmp_path / ".codebeacon"
    _write_code_beacon(beacon, [
        ("app::OrderService", "OrderService", "class", "src/orders/OrderService.java"),
    ])
    vault = _vault_with(tmp_path, {
        "a.md": "# A\n\nOrderService is central here.\n",
        "b.md": "# B\n\nOrderService also matters here.\n",
    })

    result = build_knowledge_map(vault, tmp_path / "out")
    link_knowledge_to_graph(result, beacon)
    G1, _ = load_beacon(beacon / "beacon.json")
    assert sum(1 for _, d in G1.nodes(data=True) if d.get("type") == KNOWLEDGE_NODE_TYPE) == 2

    # Delete one note and re-run — the stale overlay node must not linger.
    (vault / "b.md").unlink()
    result2 = build_knowledge_map(vault, tmp_path / "out")
    link_knowledge_to_graph(result2, beacon)
    G2, _ = load_beacon(beacon / "beacon.json")
    note_ids = [n for n, d in G2.nodes(data=True) if d.get("type") == KNOWLEDGE_NODE_TYPE]
    assert note_ids == ["knowledge::a.md"]


# ── (e) MCP beacon_knowledge tool ────────────────────────────────────────────


def _linked_index(tmp_path: Path):
    beacon = tmp_path / ".codebeacon"
    _write_code_beacon(beacon, [
        ("app::PaymentService", "PaymentService", "class", "src/payments/PaymentService.java"),
        ("app::OrderService", "OrderService", "class", "src/orders/OrderService.java"),
    ])
    vault = _vault_with(tmp_path, {
        "decisions/adr-001-payments.md": (
            "# Payments rework\n\n## Decision\n"
            "Route charges through `src/payments/PaymentService.java`.\n"
        ),
        "notes/orders.md": "# Orders\n\nOrderService will gain idempotency keys.\n",
    })
    result = build_knowledge_map(vault, tmp_path / "out")
    link_knowledge_to_graph(result, beacon)

    from codebeacon.export.mcp import BeaconIndex
    idx = BeaconIndex(beacon)
    idx.load()
    return idx


def test_mcp_knowledge_by_node(tmp_path: Path):
    from codebeacon.export.mcp import tool_beacon_knowledge

    idx = _linked_index(tmp_path)
    out = tool_beacon_knowledge(idx, {"node": "PaymentService"})
    assert "Payments rework" in out
    assert "references" in out and "EXTRACTED" in out
    # A note about a *different* service must not appear.
    assert "Orders" not in out


def test_mcp_knowledge_by_query(tmp_path: Path):
    from codebeacon.export.mcp import tool_beacon_knowledge

    idx = _linked_index(tmp_path)
    out = tool_beacon_knowledge(idx, {"query": "payments"})
    assert "Payments rework" in out
    # Keyword scoped: the orders note doesn't mention payments.
    assert "OrderService will gain" not in out


def test_mcp_knowledge_requires_an_argument(tmp_path: Path):
    from codebeacon.export.mcp import tool_beacon_knowledge

    idx = _linked_index(tmp_path)
    assert "provide" in tool_beacon_knowledge(idx, {}).lower()


def test_mcp_knowledge_unknown_node(tmp_path: Path):
    from codebeacon.export.mcp import tool_beacon_knowledge

    idx = _linked_index(tmp_path)
    assert "No node matching" in tool_beacon_knowledge(idx, {"node": "NoSuchService"})


# ── No-op when no beacon.json exists ─────────────────────────────────────────


def test_link_is_noop_without_beacon(tmp_path: Path):
    vault = _vault_with(tmp_path, {"a.md": "# A\n\nJust a note.\n"})
    result = build_knowledge_map(vault, tmp_path / "out")
    # No beacon.json anywhere → linking is a silent no-op, KNOWLEDGE.md stands alone.
    assert link_knowledge_to_graph(result, tmp_path / ".codebeacon") is None
    assert resolve_beacon_dir(tmp_path / ".codebeacon", tmp_path) is None


# ── Pure-helper guards ───────────────────────────────────────────────────────


def test_extract_path_refs_requires_directory_separator():
    # Backtick-wrapped and prose paths both captured; a bare filename is not.
    refs = extract_path_refs("see `src/a/B.java` and lib/x/y.ts but not Config.java")
    assert refs == {"src/a/B.java", "lib/x/y.ts"}


@pytest.mark.parametrize("label,expected", [
    ("PaymentService", True),
    ("get_subway_time", True),
    ("UserRepository", True),
    ("User", False),        # single CapWord — prose collision risk
    ("payment", False),     # lowercase word
    ("Database", False),    # single CapWord
    ("id", False),          # too short
    ("README", False),      # stopword
])
def test_is_distinctive_label(label, expected):
    assert is_distinctive_label(label) is expected
