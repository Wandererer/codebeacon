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
