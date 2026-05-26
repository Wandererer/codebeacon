"""Tests for wiki/generator.py."""
from __future__ import annotations

from pathlib import Path
import pytest
import networkx as nx

from codebeacon.wiki.generator import generate_wiki


def _build_test_graph() -> nx.DiGraph:
    """Build a minimal DiGraph for wiki generation tests."""
    G = nx.DiGraph()

    # Route node
    G.add_node(
        "api::get_users::route::GET::/users",
        label="get_users [GET /users]",
        type="route",
        project="api",
        framework="fastapi",
        source_file="/projects/api/main.py",
        line=10,
        method="GET",
        path="/users",
        community=0,
        annotations=[],
    )

    # Service node
    G.add_node(
        "api::UserService",
        label="UserService",
        type="class",
        project="api",
        framework="fastapi",
        source_file="/projects/api/service.py",
        line=1,
        community=0,
        annotations=["@Service"],
    )

    # Entity node
    G.add_node(
        "api::User",
        label="User",
        type="entity",
        project="api",
        framework="sqlalchemy",
        source_file="/projects/api/models.py",
        line=5,
        community=0,
        annotations=[],
    )

    # Component node
    G.add_node(
        "frontend::UserCard",
        label="UserCard",
        type="component",
        project="frontend",
        framework="react",
        source_file="/projects/frontend/UserCard.tsx",
        line=1,
        community=1,
        annotations=[],
    )

    # Edges
    G.add_edge(
        "api::get_users::route::GET::/users",
        "api::UserService",
        relation="calls",
        confidence="EXTRACTED",
    )
    G.add_edge(
        "api::UserService",
        "api::User",
        relation="reads",
        confidence="EXTRACTED",
    )

    return G


class TestGenerateWiki:
    def test_creates_wiki_directory(self, tmp_path):
        G = _build_test_graph()
        communities = {"api::UserService": 0, "api::User": 0,
                       "api::get_users::route::GET::/users": 0,
                       "frontend::UserCard": 1}
        generate_wiki(G, communities, str(tmp_path))
        wiki_dir = tmp_path / "wiki"
        assert wiki_dir.exists()

    def test_creates_index_md(self, tmp_path):
        G = _build_test_graph()
        communities = {}
        generate_wiki(G, communities, str(tmp_path))
        assert (tmp_path / "wiki" / "index.md").exists()

    def test_index_contains_project_names(self, tmp_path):
        G = _build_test_graph()
        communities = {}
        generate_wiki(G, communities, str(tmp_path))
        content = (tmp_path / "wiki" / "index.md").read_text()
        assert "api" in content or "API" in content.upper()

    def test_creates_routes_md(self, tmp_path):
        G = _build_test_graph()
        communities = {}
        generate_wiki(G, communities, str(tmp_path))
        # routes.md should exist somewhere in wiki/
        routes_files = list((tmp_path / "wiki").rglob("routes.md"))
        assert len(routes_files) >= 1

    def test_creates_per_project_directory(self, tmp_path):
        G = _build_test_graph()
        communities = {}
        generate_wiki(G, communities, str(tmp_path))
        # Should have a subdirectory for project 'api'
        project_dirs = [d.name for d in (tmp_path / "wiki").iterdir() if d.is_dir()]
        assert "api" in project_dirs or any("api" in d for d in project_dirs)

    def test_no_crash_on_empty_graph(self, tmp_path):
        """generate_wiki should not crash on empty graph."""
        G = nx.DiGraph()
        generate_wiki(G, {}, str(tmp_path))
        assert (tmp_path / "wiki").exists()

    def test_routes_md_contains_route_info(self, tmp_path):
        G = _build_test_graph()
        communities = {}
        generate_wiki(G, communities, str(tmp_path))
        routes_files = list((tmp_path / "wiki").rglob("routes.md"))
        if routes_files:
            content = routes_files[0].read_text()
            # Should mention GET or /users
            assert "GET" in content or "/users" in content


def _service_graph(*labels: str) -> nx.DiGraph:
    """Tiny graph: one project, one service node per label."""
    G = nx.DiGraph()
    for lbl in labels:
        G.add_node(
            f"api::{lbl}",
            label=lbl,
            type="class",
            project="api",
            framework="fastapi",
            source_file=f"/projects/api/{lbl}.py",
            line=1,
            methods=[],
            dependencies=[],
            annotations=[],
            community=0,
        )
    return G


class TestStaleArticlePrune:
    """Mirrors graphify #9e6192a (stale wiki nodes).

    `--update` rewrites the wiki under the same directory as a previous
    run. Before 0.6.0, an article for a removed/renamed node lingered
    forever because the writer only touched live nodes. The prune step
    deletes per-node `.md` files whose graph node no longer exists.
    """

    def test_removed_service_article_is_deleted_on_rebuild(self, tmp_path):
        # Round 1: Foo and Bar both exist → both articles written.
        generate_wiki(_service_graph("Foo", "Bar"), {}, str(tmp_path))
        services_dir = tmp_path / "wiki" / "api" / "services"
        round1 = sorted(p.name for p in services_dir.glob("*.md"))
        assert round1 == ["Bar.md", "Foo.md"]

        # Round 2: Foo is gone (renamed / deleted) → its .md must be pruned.
        generate_wiki(_service_graph("Bar"), {}, str(tmp_path))
        round2 = sorted(p.name for p in services_dir.glob("*.md"))
        assert round2 == ["Bar.md"], (
            "Foo.md leaked across rebuilds — stale-article prune regressed"
        )

    def test_prune_only_touches_per_node_subdirs(self, tmp_path):
        """Global files (index.md, overview.md, routes.md) are always
        rewritten by the wiki layer, so the pruner must not delete them
        even when no per-node article matches."""
        generate_wiki(_service_graph("Foo"), {}, str(tmp_path))
        # Rebuild with the same set so the prune step has nothing per-node
        # to delete, then confirm globals are still present.
        generate_wiki(_service_graph("Foo"), {}, str(tmp_path))
        assert (tmp_path / "wiki" / "index.md").exists()
        assert (tmp_path / "wiki" / "api" / "index.md").exists()
