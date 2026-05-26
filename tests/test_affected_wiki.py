"""``codebeacon affected --as wiki`` — map graph blast radius to wiki paths.

The synergy pin from the 0.6.0 audit: graphify's affected analyser + codesight's
wiki generator must connect through a single CLI command so a PR-reviewing
agent can read just the affected articles instead of the whole graph.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest

from codebeacon.affected import affected_from_paths
from codebeacon.wiki.generator import node_to_wiki_path


def _build_graph() -> nx.DiGraph:
    """Tiny three-project graph:

      UserController (api) ──calls──▶ UserService (api) ──calls──▶ User (api)
      LoginPage      (web) ──imports──▶ UserController
    """
    G = nx.DiGraph()
    G.add_node("api::UserController", label="UserController", type="class",
               source_file="api/src/UserController.py", project="api",
               annotations=["@RestController"])
    G.add_node("api::UserService", label="UserService", type="class",
               source_file="api/src/UserService.py", project="api",
               annotations=["@Service"])
    G.add_node("api::User", label="User", type="entity",
               source_file="api/src/User.py", project="api")
    G.add_node("web::LoginPage", label="LoginPage", type="component",
               source_file="web/src/LoginPage.tsx", project="web")

    G.add_edge("api::UserController", "api::UserService", relation="calls")
    G.add_edge("api::UserService", "api::User", relation="calls")
    G.add_edge("web::LoginPage", "api::UserController", relation="imports")
    return G


def _persist(G: nx.DiGraph, tmp_path: Path) -> Path:
    """Write beacon.json under tmp_path/.codebeacon/, plus stub wiki files
    so the existence check in affected_from_paths(include_wiki_paths=True)
    has something to find."""
    bdir = tmp_path / ".codebeacon"
    bdir.mkdir()
    (bdir / "beacon.json").write_text(
        json.dumps(nxjson.node_link_data(G), ensure_ascii=False),
        encoding="utf-8",
    )
    wiki_root = bdir / "wiki"
    for node_id in G.nodes:
        wp = node_to_wiki_path(G, node_id)
        if not wp:
            continue
        full = wiki_root / wp
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("# stub", encoding="utf-8")
    return bdir


class TestNodeToWikiPath:
    def test_controller_class_routes_to_controllers_dir(self):
        G = _build_graph()
        assert node_to_wiki_path(G, "api::UserController") == "api/controllers/UserController.md"

    def test_service_class_routes_to_services_dir(self):
        G = _build_graph()
        assert node_to_wiki_path(G, "api::UserService") == "api/services/UserService.md"

    def test_entity_routes_to_entities_dir(self):
        G = _build_graph()
        assert node_to_wiki_path(G, "api::User") == "api/entities/User.md"

    def test_component_routes_to_components_dir(self):
        G = _build_graph()
        assert node_to_wiki_path(G, "web::LoginPage") == "web/components/LoginPage.md"

    def test_unknown_type_returns_none(self):
        G = nx.DiGraph()
        G.add_node("p::r1", label="GET /users", type="route", project="p",
                   source_file="api.py")
        assert node_to_wiki_path(G, "p::r1") is None

    def test_missing_node_returns_none(self):
        G = nx.DiGraph()
        assert node_to_wiki_path(G, "does-not-exist") is None

    def test_unsafe_chars_in_label_are_sanitised(self):
        G = nx.DiGraph()
        G.add_node("p::Weird Name!", label="Weird Name!", type="class",
                   project="p", source_file="x.py", annotations=[])
        path = node_to_wiki_path(G, "p::Weird Name!")
        # spaces and ! → underscores; project + filename intact
        assert path == "p/services/Weird_Name_.md"


class TestAffectedWikiMapping:
    def test_changed_source_returns_upstream_wiki_paths(self, tmp_path):
        """Changing UserService.py should surface BOTH the service article
        and its upstream controller (because the controller depends on
        the service)."""
        G = _build_graph()
        bdir = _persist(G, tmp_path)

        result = affected_from_paths(
            bdir,
            ["api/src/UserService.py"],
            include_wiki_paths=True,
        )
        assert "api/services/UserService.md" in result.wiki_paths
        # UserController is upstream of UserService → must be in the radius
        assert "api/controllers/UserController.md" in result.wiki_paths

    def test_only_existing_articles_are_listed(self, tmp_path):
        """If a node lacks a wiki article on disk, we don't claim it exists.
        Otherwise consumers chase 404s."""
        G = _build_graph()
        bdir = _persist(G, tmp_path)
        # Delete the service article so it shouldn't appear in output
        (bdir / "wiki" / "api" / "services" / "UserService.md").unlink()

        result = affected_from_paths(
            bdir,
            ["api/src/UserService.py"],
            include_wiki_paths=True,
        )
        assert "api/services/UserService.md" not in result.wiki_paths
        # UserController still exists on disk, so it's still surfaced
        assert "api/controllers/UserController.md" in result.wiki_paths

    def test_wiki_paths_deduplicated(self, tmp_path):
        G = _build_graph()
        bdir = _persist(G, tmp_path)
        # Same file twice → seed_node_ids has the node once, but defensive check
        result = affected_from_paths(
            bdir,
            ["api/src/UserService.py", "api/src/UserService.py"],
            include_wiki_paths=True,
        )
        assert result.wiki_paths.count("api/services/UserService.md") == 1

    def test_include_wiki_paths_default_false(self, tmp_path):
        """Backward compatibility: existing callers don't get wiki_paths."""
        G = _build_graph()
        bdir = _persist(G, tmp_path)
        result = affected_from_paths(bdir, ["api/src/UserService.py"])
        assert result.wiki_paths == []

    def test_no_match_returns_empty_wiki_paths(self, tmp_path):
        G = _build_graph()
        bdir = _persist(G, tmp_path)
        result = affected_from_paths(
            bdir,
            ["docs/README.md"],  # not in graph
            include_wiki_paths=True,
        )
        assert result.wiki_paths == []


class TestAsWikiPathsRendering:
    def test_as_wiki_paths_emits_one_per_line(self, tmp_path):
        G = _build_graph()
        bdir = _persist(G, tmp_path)
        result = affected_from_paths(
            bdir,
            ["api/src/UserService.py"],
            include_wiki_paths=True,
        )
        rendered = result.as_wiki_paths(base=str(bdir / "wiki"))
        lines = rendered.splitlines()
        # Each line is one absolute(ish) wiki path
        assert all(line.endswith(".md") for line in lines)
        assert len(lines) == len(result.wiki_paths)

    def test_as_wiki_paths_empty_when_no_paths(self):
        from codebeacon.affected import AffectedResult
        empty = AffectedResult()
        assert empty.as_wiki_paths() == ""
