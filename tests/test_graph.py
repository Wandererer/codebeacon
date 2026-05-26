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


class TestCrossFileDeclarationMerge:
    """Mirrors graphify #406bea4 (Swift extension dedup).

    Generalised to every language where a single logical type can be
    declared across multiple files (Swift extensions, C# partial classes,
    Ruby reopened classes, Python class re-declarations). Before 0.6.0,
    NetworkX collapsed same-id nodes but the last writer's metadata
    overwrote earlier metadata, silently losing fields/methods from
    other files.
    """

    def test_fields_union_across_two_files(self):
        """Two `User` entities — one per file, each with different fields —
        must merge into a single canonical node carrying ALL fields."""
        e_a = EntityInfo(
            name="User", table_name="users",
            source_file="/proj/User.swift", line=1, framework="fluent",
            fields=[{"name": "id", "type": "Int", "annotations": ["@ID"]}],
        )
        e_b = EntityInfo(
            name="User", table_name="users",
            source_file="/proj/User+Profile.swift", line=1, framework="fluent",
            fields=[{"name": "name", "type": "String", "annotations": []}],
        )
        wave = WaveResult(project=_project(), entities=[e_a, e_b])
        G = build_graph([wave], apply_filters=False)

        user_node = G.nodes["api::User"]
        field_names = [f["name"] for f in user_node.get("fields", [])]
        assert "id" in field_names and "name" in field_names, (
            "cross-file extension fields were lost — last-writer-wins regression"
        )

    def test_dedup_collapses_duplicates_within_union(self):
        """If both files declare the same `id` field, the merge keeps one,
        not two — order preserved by first occurrence."""
        e_a = EntityInfo(
            name="Order", table_name="orders",
            source_file="/proj/Order.cs", line=1, framework="ef",
            fields=[{"name": "id", "type": "int", "annotations": []}],
        )
        e_b = EntityInfo(
            name="Order", table_name="orders",
            source_file="/proj/Order.Partial.cs", line=1, framework="ef",
            fields=[
                {"name": "id", "type": "int", "annotations": []},  # duplicate
                {"name": "total", "type": "decimal", "annotations": []},
            ],
        )
        wave = WaveResult(project=_project(), entities=[e_a, e_b])
        G = build_graph([wave], apply_filters=False)
        fields = G.nodes["api::Order"].get("fields", [])
        names = [f["name"] for f in fields]
        assert names == ["id", "total"]


class TestCasefoldAndPhantomGuard:
    """Mirrors graphify #86109e9 (CJK/Unicode dedup) and #4dce16f
    (phantom cross-language matches). The import-edge remap uses
    casefold() so non-ASCII labels match, but it also refuses to fall
    back to case-insensitive matching for tokens shorter than 3 chars,
    which were the main source of phantom cross-language edges.
    """

    def test_casefold_matches_eszett_to_ss(self):
        """A path-alias import `@/Strasse` from a *different* file must
        resolve to the class labelled `Straße` via casefold — lower()
        would not handle the ß→ss equivalence."""
        target_entity = EntityInfo(
            name="Straße", table_name="strassen",
            source_file="/proj/Strasse.py", line=1, framework="sqlalchemy",
        )
        caller = ServiceInfo(
            name="Caller", class_name="Caller",
            source_file="/proj/caller.py", line=1, framework="fastapi",
        )
        wave = WaveResult(
            project=_project(),
            services=[caller],
            entities=[target_entity],
            import_edges=[Edge(
                source="/proj/caller.py",
                target="@/Strasse",  # different case + romanised
                relation="imports_from",
                confidence="EXTRACTED",
                confidence_score=1.0,
                source_file="/proj/caller.py",
            )],
        )
        G = build_graph([wave], apply_filters=False)
        # The edge should resolve and end up pointing at the Straße node.
        edges = [(s, t, d.get("relation")) for s, t, d in G.edges(data=True)]
        assert any(t == "api::Straße" and r == "imports_from" for _, t, r in edges)

    def test_short_label_no_case_fold_phantom(self):
        """A two-char label like `Db` must NOT case-fold-match `DB`. In
        mixed-language repos these short tokens are usually unrelated
        types that happen to spell the same letters; the old `.lower()`
        fallback was a major source of phantom cross-project edges."""
        target_entity = EntityInfo(
            name="Db", table_name="db",
            source_file="/proj/Db.py", line=1, framework="sqlalchemy",
        )
        caller = ServiceInfo(
            name="Caller", class_name="Caller",
            source_file="/proj/caller.py", line=1, framework="fastapi",
        )
        wave = WaveResult(
            project=_project(),
            services=[caller],
            entities=[target_entity],
            import_edges=[Edge(
                source="/proj/caller.py",
                target="@/DB",  # short, different case
                relation="imports_from",
                confidence="EXTRACTED",
                confidence_score=1.0,
                source_file="/proj/caller.py",
            )],
        )
        G = build_graph([wave], apply_filters=False)
        # The case-insensitive fallback must be suppressed for short tokens.
        edges = [(s, t, d.get("relation")) for s, t, d in G.edges(data=True)]
        assert not any(
            r == "imports_from" and t == "api::Db" for _, t, r in edges
        ), "short-label case-fold produced a phantom import edge"


class TestReExportEdges:
    """Mirrors graphify #1494874. JS/TS barrel re-exports
    (``export { X } from './m'``) become explicit `re_exports` edges,
    routed through the same file→label resolver as `imports_from`."""

    def test_re_exports_edge_resolves_to_label(self):
        button = ComponentInfo(
            name="Button", source_file="/proj/Button.tsx", line=1,
            framework="react",
        )
        # Barrel index.ts is itself a graph node (e.g. extractor emits a
        # placeholder for the file). Otherwise the file→node resolver has
        # no source to remap from.
        barrel = ComponentInfo(
            name="Barrel", source_file="/proj/index.ts", line=1,
            framework="react",
        )
        wave = WaveResult(
            project=_project("ui", "react"),
            components=[button, barrel],
            import_edges=[Edge(
                source="/proj/index.ts",
                target="./Button",
                relation="re_exports",
                confidence="EXTRACTED",
                confidence_score=1.0,
                source_file="/proj/index.ts",
            )],
        )
        G = build_graph([wave], apply_filters=False)
        re_exports = [
            (s, t) for s, t, d in G.edges(data=True)
            if d.get("relation") == "re_exports"
        ]
        # Barrel re-exports Button — the edge survives remapping AND
        # preserves the distinct `re_exports` relation (not `imports_from`).
        assert ("ui::Barrel", "ui::Button") in re_exports


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
