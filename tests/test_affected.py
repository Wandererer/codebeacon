"""Tests for codebeacon.affected (PR diff → graph blast radius).

Mirrors graphify #e44e6e9 ("v8 affected"). The core contract:

* a changed file maps to the graph node(s) whose ``source_file`` ends
  with that path (handles absolute vs repo-relative discrepancy),
* the affected set is the upstream predecessor closure up to ``depth``
  (callers — not callees — because a code change's blast radius is who
  depends on it),
* the ``--limit`` truncates the output, not the walk,
* a diff that touches only docs/config returns a non-empty seed list
  but an empty affected set, with a friendly message.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest

from codebeacon.affected import affected_from_paths


def _write_beacon(d: Path, G: nx.DiGraph) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "beacon.json").write_text(
        json.dumps(nxjson.node_link_data(G), ensure_ascii=False),
        encoding="utf-8",
    )
    return d


def _star_graph() -> nx.DiGraph:
    """Foo ← Bar ← Web   (edges point caller → callee, so predecessors are callers)."""
    G = nx.DiGraph()
    G.add_node("p::Foo", label="Foo", type="class", source_file="src/foo.py", project="p")
    G.add_node("p::Bar", label="Bar", type="class", source_file="src/bar.py", project="p")
    G.add_node("p::Web", label="Web", type="route", source_file="src/web.py", project="p")
    G.add_edge("p::Bar", "p::Foo", relation="calls")
    G.add_edge("p::Web", "p::Bar", relation="calls")
    return G


def test_seed_matches_by_path_suffix(tmp_path):
    _write_beacon(tmp_path, _star_graph())
    r = affected_from_paths(tmp_path, ["src/foo.py"])
    assert r.seed_node_ids == ["p::Foo"]


def test_blast_radius_walks_upstream(tmp_path):
    """Changing Foo affects Bar (direct caller) and Web (indirect)."""
    _write_beacon(tmp_path, _star_graph())
    r = affected_from_paths(tmp_path, ["src/foo.py"])
    assert set(r.affected_node_ids) == {"p::Bar", "p::Web"}


def test_depth_caps_walk(tmp_path):
    """depth=1 stops at direct callers; Web (2 hops away) is excluded."""
    _write_beacon(tmp_path, _star_graph())
    r = affected_from_paths(tmp_path, ["src/foo.py"], depth=1)
    assert "p::Bar" in r.affected_node_ids
    assert "p::Web" not in r.affected_node_ids


def test_limit_truncates_output(tmp_path):
    """limit caps the printed set but the seed/affected computation is unchanged."""
    G = nx.DiGraph()
    G.add_node("p::Hub", label="Hub", type="class", source_file="src/hub.py", project="p")
    for i in range(20):
        nid = f"p::Caller{i}"
        G.add_node(nid, label=f"Caller{i}", type="class", source_file=f"src/c{i}.py", project="p")
        G.add_edge(nid, "p::Hub", relation="calls")
    _write_beacon(tmp_path, G)

    r = affected_from_paths(tmp_path, ["src/hub.py"], limit=5)
    assert len(r.affected_node_ids) == 5


def test_no_match_returns_empty_affected_with_seed_explanation(tmp_path):
    """A docs-only diff has seed_files but zero graph hits — caller should see why."""
    _write_beacon(tmp_path, _star_graph())
    r = affected_from_paths(tmp_path, ["README.md", "docs/intro.md"])
    assert r.seed_files == ["README.md", "docs/intro.md"]
    assert r.seed_node_ids == []
    assert r.affected_node_ids == []
    assert "didn't match" not in r.as_markdown().lower()  # uses 'matched' phrasing
    assert "may be in docs" in r.as_markdown()


def test_missing_beacon_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        affected_from_paths(tmp_path, ["src/foo.py"])


def test_walks_callers_not_callees(tmp_path):
    """Regression: blast radius MUST be upstream. If we accidentally walk
    successors, changing Foo would falsely report 'nothing affected' here
    because Foo has no out-edges."""
    _write_beacon(tmp_path, _star_graph())
    r_foo = affected_from_paths(tmp_path, ["src/foo.py"])
    r_web = affected_from_paths(tmp_path, ["src/web.py"])
    # Foo (leaf callee) is depended on by 2 nodes; Web (root caller) by 0.
    assert len(r_foo.affected_node_ids) == 2
    assert len(r_web.affected_node_ids) == 0


def test_as_markdown_renders_label_type_and_source(tmp_path):
    _write_beacon(tmp_path, _star_graph())
    md = affected_from_paths(tmp_path, ["src/foo.py"]).as_markdown()
    assert "Bar" in md and "class" in md and "src/bar.py" in md
    assert "Web" in md and "route" in md
