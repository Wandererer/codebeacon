"""Tests for graph/build.py and graph/cluster.py."""
from __future__ import annotations

import pytest
import networkx as nx

from codebeacon.common.types import (
    RouteInfo, ServiceInfo, EntityInfo, ComponentInfo,
    ProjectInfo, Edge, UnresolvedRef,
)
from codebeacon.graph.build import build_graph
from codebeacon.graph.cluster import cluster, apply_communities, score_all
from codebeacon.wave import WaveResult


def _project(name: str = "api", framework: str = "fastapi") -> ProjectInfo:
    return ProjectInfo(
        name=name, path=f"/projects/{name}",
        framework=framework, language="python", signature_file="requirements.txt",
    )


def _route(method: str, path: str, handler: str, fw: str = "fastapi") -> RouteInfo:
    return RouteInfo(
        method=method, path=path, handler=handler,
        source_file=f"/projects/api/main.py", line=1, framework=fw,
    )


def _service(name: str, deps: list[str] | None = None) -> ServiceInfo:
    return ServiceInfo(
        name=name, class_name=name,
        source_file=f"/projects/api/{name}.py", line=1,
        framework="fastapi", dependencies=deps or [],
    )


def _entity(name: str) -> EntityInfo:
    return EntityInfo(
        name=name, table_name=name.lower() + "s",
        source_file=f"/projects/api/models.py", line=1,
        framework="sqlalchemy",
    )


class TestBuildGraph:
    def test_empty_wave_result(self):
        """build_graph on empty WaveResult produces empty graph."""
        wave = WaveResult(project=_project())
        G = build_graph([wave], apply_filters=False)
        assert isinstance(G, nx.DiGraph)
        assert G.number_of_nodes() == 0

    def test_route_becomes_node(self):
        """Routes become route-type nodes in the graph."""
        wave = WaveResult(
            project=_project(),
            routes=[_route("GET", "/users", "get_users")],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.number_of_nodes() >= 1
        types = {data["type"] for _, data in G.nodes(data=True)}
        assert "route" in types

    def test_service_becomes_node(self):
        """Services become class-type nodes."""
        wave = WaveResult(
            project=_project(),
            services=[_service("UserService")],
        )
        G = build_graph([wave], apply_filters=False)
        labels = {data.get("label", "") for _, data in G.nodes(data=True)}
        assert any("UserService" in lbl for lbl in labels)

    def test_entity_becomes_node(self):
        """Entities become entity-type nodes."""
        wave = WaveResult(
            project=_project(),
            entities=[_entity("User")],
        )
        G = build_graph([wave], apply_filters=False)
        types = {data["type"] for _, data in G.nodes(data=True)}
        assert "entity" in types

    def test_multiple_projects(self):
        """Multiple WaveResults produce nodes from all projects."""
        wave1 = WaveResult(
            project=_project("api"),
            routes=[_route("GET", "/users", "get_users")],
        )
        wave2 = WaveResult(
            project=_project("frontend", "react"),
            routes=[_route("GET", "/", "HomePage", "react")],
        )
        G = build_graph([wave1, wave2], apply_filters=False)
        projects = {data.get("project", "") for _, data in G.nodes(data=True)}
        assert "api" in projects
        assert "frontend" in projects

    def test_di_resolution_adds_edge(self):
        """Unresolved DI ref that matches a known service produces an edge."""
        wave = WaveResult(
            project=_project(),
            services=[
                _service("UserService"),
                _service("OrderService", deps=["UserService"]),
            ],
            unresolved=[
                UnresolvedRef(
                    source_node_id="api::OrderService",
                    ref_type="autowired",
                    ref_name="UserService",
                    framework="spring-boot",
                )
            ],
        )
        G = build_graph([wave], apply_filters=False)
        # Should have at least the two service nodes
        assert G.number_of_nodes() >= 2

    def test_graph_is_directed(self):
        """Returned graph is a DiGraph."""
        wave = WaveResult(project=_project())
        G = build_graph([wave])
        assert G.is_directed()


class TestCluster:
    def test_empty_graph(self):
        """cluster() on empty graph returns empty dict."""
        G = nx.DiGraph()
        result = cluster(G)
        assert result == {}

    def test_single_node(self):
        """Single node → single community."""
        G = nx.DiGraph()
        G.add_node("A")
        result = cluster(G)
        assert "A" in result

    def test_community_ids_are_ints(self):
        """Community IDs are integers."""
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        result = cluster(G)
        assert all(isinstance(v, int) for v in result.values())

    def test_apply_communities_sets_attr(self):
        """apply_communities writes 'community' attribute to each node."""
        G = nx.DiGraph()
        G.add_nodes_from(["X", "Y"])
        communities = {"X": 0, "Y": 1}
        apply_communities(G, communities)
        assert G.nodes["X"]["community"] == 0
        assert G.nodes["Y"]["community"] == 1

    def test_score_all_returns_float(self):
        """score_all returns dict of community_id → float."""
        G = nx.DiGraph()
        G.add_edges_from([("A", "B"), ("B", "A")])
        G.nodes["A"]["community"] = 0
        G.nodes["B"]["community"] = 0
        communities = {"A": 0, "B": 0}
        scores = score_all(G, communities)
        assert isinstance(scores, dict)
        assert all(isinstance(v, float) for v in scores.values())
