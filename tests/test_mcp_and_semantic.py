"""Query and semantic-context tests for the 0.6.0 patches.

Two cross-cutting changes:

* ``BeaconIndex`` (used by both the MCP server and `codebeacon query`)
  now indexes labels via ``casefold()`` instead of ``lower()``. This
  makes German ``ß``, Turkish ``i/İ``, Greek ``σ/ς``, and CJK labels
  round-trip correctly. Mirrors graphify's #020cca2 / #c7a05d6.
* ``semantic_pipeline.prepare`` now ships graph neighbors (callers +
  callees) with every task so the LLM stays grounded in real node
  labels instead of inventing phantom references. Mirrors graphify
  #ab4e542.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest


def _write_beacon(d: Path, G: nx.DiGraph) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "beacon.json").write_text(
        json.dumps(nxjson.node_link_data(G), ensure_ascii=False),
        encoding="utf-8",
    )


# ── Casefold query ──────────────────────────────────────────────────────────

class TestCasefoldQuery:
    def test_german_eszett_matches_romanised_query(self, tmp_path):
        """`Straße`.casefold() == 'strasse', so a search for 'strasse' or
        'STRASSE' must find it. lower() would not."""
        G = nx.DiGraph()
        G.add_node("p::Straße", label="Straße", project="p", type="class")
        _write_beacon(tmp_path, G)

        from codebeacon.export.mcp import BeaconIndex
        idx = BeaconIndex(tmp_path)
        idx.load()
        assert idx.find_node_ids("strasse") == ["p::Straße"]
        assert idx.find_node_ids("STRASSE") == ["p::Straße"]

    def test_turkish_dotless_i_matches(self, tmp_path):
        """Turkish `İstanbul` casefolds to 'i̇stanbul' — preserved by
        casefold(), unlike lower() which would canonicalise the dot."""
        G = nx.DiGraph()
        G.add_node("p::İstanbul", label="İstanbul", project="p", type="class")
        _write_beacon(tmp_path, G)

        from codebeacon.export.mcp import BeaconIndex
        idx = BeaconIndex(tmp_path)
        idx.load()
        # The exact label should match itself regardless of input case
        assert idx.find_node_ids("İstanbul") == ["p::İstanbul"]

    def test_cjk_label_matches_directly(self, tmp_path):
        G = nx.DiGraph()
        G.add_node("p::로그인", label="로그인", project="p", type="class")
        G.add_node("p::用户", label="用户", project="p", type="class")
        _write_beacon(tmp_path, G)

        from codebeacon.export.mcp import BeaconIndex
        idx = BeaconIndex(tmp_path)
        idx.load()
        assert idx.find_node_ids("로그인") == ["p::로그인"]
        assert idx.find_node_ids("用户") == ["p::用户"]


# ── NFC/NFD label lookup (graphify #1338) ────────────────────────────────────

class TestNfcLabelLookup:
    """Labels and queries are NFC-normalised before casefolding, so an NFD
    query (e.g. a label copied from a macOS APFS/HFS+ filename) matches an NFC
    stored label and vice versa. casefold() alone does NOT normalise Unicode
    form, so without this the same text in different forms never matched."""

    def test_nfd_query_matches_nfc_stored_label(self, tmp_path):
        import unicodedata
        nfc = unicodedata.normalize("NFC", "Auditoría")
        nfd = unicodedata.normalize("NFD", "Auditoría")
        assert nfc != nfd, "fixture precondition: the two forms must differ"

        G = nx.DiGraph()
        G.add_node("p::Auditoría", label=nfc, project="p", type="class")
        _write_beacon(tmp_path, G)

        from codebeacon.export.mcp import BeaconIndex
        idx = BeaconIndex(tmp_path)
        idx.load()
        assert idx.find_node_ids(nfd) == ["p::Auditoría"]  # was [] before #1338
        assert idx.find_node_ids(nfc) == ["p::Auditoría"]

    def test_nfc_query_matches_nfd_stored_label(self, tmp_path):
        """The realistic macOS direction: the stored label is NFD (derived from
        a filename) and the user types an NFC query."""
        import unicodedata
        nfc = unicodedata.normalize("NFC", "Auditoría")
        nfd = unicodedata.normalize("NFD", "Auditoría")

        G = nx.DiGraph()
        G.add_node("p::n1", label=nfd, project="p", type="class")
        _write_beacon(tmp_path, G)

        from codebeacon.export.mcp import BeaconIndex
        idx = BeaconIndex(tmp_path)
        idx.load()
        assert idx.find_node_ids(nfc) == ["p::n1"]  # was [] before #1338


# ── Semantic neighbor context ───────────────────────────────────────────────

class TestSemanticNeighborContext:
    def test_neighbors_captures_callers_and_callees(self):
        """_neighbor_context returns predecessors as `callers` and
        successors as `callees`, each summarised with label, type,
        source_file basename, and language."""
        from codebeacon.semantic_pipeline import _neighbor_context

        G = nx.DiGraph()
        G.add_node("p::Service", label="Service", type="class", source_file="/a/Service.py")
        G.add_node("p::Caller", label="Caller", type="class", source_file="/a/Caller.py")
        G.add_node("p::Dep", label="Dep", type="class", source_file="/a/Dep.ts")
        G.add_edge("p::Caller", "p::Service", relation="calls")
        G.add_edge("p::Service", "p::Dep", relation="depends")

        ctx = _neighbor_context(G, "p::Service")
        caller_labels = [c["label"] for c in ctx["callers"]]
        callee_labels = [c["label"] for c in ctx["callees"]]
        assert caller_labels == ["Caller"]
        assert callee_labels == ["Dep"]
        # Language inference works from extension
        assert ctx["callers"][0]["language"] == "python"
        assert ctx["callees"][0]["language"] == "typescript"
        # Source file is reduced to basename (privacy + payload size)
        assert ctx["callers"][0]["source_file"] == "Caller.py"

    def test_neighbors_capped_to_prevent_god_node_blowup(self):
        """A node with 100 predecessors must not dump all 100 into the
        task payload — chunks would explode. Cap at _NEIGHBOR_CAP."""
        from codebeacon.semantic_pipeline import _neighbor_context, _NEIGHBOR_CAP

        G = nx.DiGraph()
        G.add_node("p::God", label="God", type="class", source_file="/a/God.py")
        for i in range(_NEIGHBOR_CAP + 50):
            nid = f"p::C{i}"
            G.add_node(nid, label=f"C{i}", type="class", source_file=f"/a/C{i}.py")
            G.add_edge(nid, "p::God", relation="calls")

        ctx = _neighbor_context(G, "p::God")
        assert len(ctx["callers"]) == _NEIGHBOR_CAP

    def test_neighbors_empty_for_unknown_node(self):
        from codebeacon.semantic_pipeline import _neighbor_context

        ctx = _neighbor_context(nx.DiGraph(), "p::Missing")
        assert ctx == {"callers": [], "callees": []}


# ── SKILL.md sanity ─────────────────────────────────────────────────────────

class TestSkillStepZero:
    """The SKILL.md ships with Claude Code, so its content is part of the
    user-facing contract. A revert would silently drop the constrained
    expansion guidance — that's worth pinning."""

    def test_skill_includes_constrained_expansion_block(self):
        skill = Path(__file__).resolve().parent.parent / "codebeacon" / "skill" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        assert "Step 0 — Constrained query expansion" in text
        assert "forbidden from adding tokens that are not in the vocab" in text
