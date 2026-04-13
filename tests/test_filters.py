"""Tests for common/filters.py — build artifact, cross-language, cross-service filters."""
from __future__ import annotations

import pytest

from codebeacon.common.types import Edge, Node
from codebeacon.common.filters import (
    filter_build_artifacts,
    filter_cross_language,
    filter_cross_service,
)


def _node(nid: str, source_file: str, ntype: str = "class") -> Node:
    return Node(id=nid, label=nid, type=ntype, source_file=source_file, line=1, metadata={})


def _edge(src: str, tgt: str, relation: str = "imports") -> Edge:
    return Edge(source=src, target=tgt, relation=relation, confidence="EXTRACTED",
                confidence_score=1.0, source_file="")


class TestFilterBuildArtifacts:
    def test_removes_target_nodes(self):
        nodes = [
            _node("Clean", "src/main/java/Clean.java"),
            _node("Artifact", "target/classes/Artifact.java"),
        ]
        edges = [_edge("Clean", "Artifact")]
        clean_nodes, clean_edges = filter_build_artifacts(nodes, edges)
        ids = {n.id for n in clean_nodes}
        assert "Clean" in ids
        assert "Artifact" not in ids

    def test_removes_edges_referencing_artifact_nodes(self):
        nodes = [
            _node("Src", "src/Src.java"),
            _node("Art", "dist/Art.js"),
        ]
        edges = [_edge("Src", "Art"), _edge("Art", "Src")]
        _, clean_edges = filter_build_artifacts(nodes, edges)
        assert len(clean_edges) == 0

    def test_preserves_clean_nodes_and_edges(self):
        nodes = [_node("A", "src/A.py"), _node("B", "src/B.py")]
        edges = [_edge("A", "B")]
        clean_nodes, clean_edges = filter_build_artifacts(nodes, edges)
        assert len(clean_nodes) == 2
        assert len(clean_edges) == 1

    def test_all_artifact_dirs(self):
        for artifact_dir in ["target", "build", "dist", "node_modules", ".next", "__pycache__"]:
            nodes = [_node("N", f"{artifact_dir}/Foo.java")]
            clean_nodes, _ = filter_build_artifacts(nodes, [])
            assert len(clean_nodes) == 0, f"Expected {artifact_dir} to be filtered"


class TestFilterCrossLanguage:
    def test_removes_java_to_ts_import(self):
        """Java → TypeScript import edge is spurious."""
        nodes = {
            "JavaClass": _node("JavaClass", "src/main/java/Foo.java"),
            "TSModule": _node("TSModule", "frontend/src/Bar.ts"),
        }
        edges = [_edge("JavaClass", "TSModule", "imports")]
        result = filter_cross_language(edges, nodes)
        assert len(result) == 0

    def test_removes_ts_to_java_import(self):
        """TypeScript → Java import edge is spurious."""
        nodes = {
            "TSModule": _node("TSModule", "frontend/Bar.tsx"),
            "JavaClass": _node("JavaClass", "backend/Foo.kt"),
        }
        edges = [_edge("TSModule", "JavaClass", "imports")]
        result = filter_cross_language(edges, nodes)
        assert len(result) == 0

    def test_preserves_same_language_imports(self):
        """Same-language import stays."""
        nodes = {
            "A": _node("A", "src/A.ts"),
            "B": _node("B", "src/B.ts"),
        }
        edges = [_edge("A", "B", "imports")]
        result = filter_cross_language(edges, nodes)
        assert len(result) == 1

    def test_preserves_calls_api_across_languages(self):
        """calls_api is always preserved regardless of language."""
        nodes = {
            "Front": _node("Front", "src/App.tsx"),
            "Back": _node("Back", "api/UserController.java"),
        }
        edges = [_edge("Front", "Back", "calls_api")]
        result = filter_cross_language(edges, nodes)
        assert len(result) == 1

    def test_preserves_unknown_node_edges(self):
        """If either node is unknown, edge is preserved (conservative)."""
        nodes = {"A": _node("A", "src/A.java")}
        edges = [_edge("A", "UnknownNode", "imports")]
        result = filter_cross_language(edges, nodes)
        assert len(result) == 1


class TestFilterCrossService:
    def test_removes_false_cross_service_import(self):
        """Different-service import of non-shared node is removed."""
        nodes = {
            "SvcA::Button": _node("SvcA::Button", "svc-a/Button.tsx"),
            "SvcB::Button": _node("SvcB::Button", "svc-b/Button.tsx"),
        }
        service_roots = {"SvcA::Button": "svc-a", "SvcB::Button": "svc-b"}
        edges = [_edge("SvcA::Button", "SvcB::Button", "imports")]
        result = filter_cross_service(edges, nodes, service_roots)
        assert len(result) == 0

    def test_preserves_same_service_import(self):
        """Same-service import is always preserved."""
        nodes = {
            "SvcA::Foo": _node("SvcA::Foo", "svc-a/Foo.tsx"),
            "SvcA::Bar": _node("SvcA::Bar", "svc-a/Bar.tsx"),
        }
        service_roots = {"SvcA::Foo": "svc-a", "SvcA::Bar": "svc-a"}
        edges = [_edge("SvcA::Foo", "SvcA::Bar", "imports")]
        result = filter_cross_service(edges, nodes, service_roots)
        assert len(result) == 1

    def test_preserves_shared_lib_cross_service(self):
        """Cross-service import targeting a shared lib node is preserved."""
        nodes = {
            "SvcA::Widget": _node("SvcA::Widget", "svc-a/Widget.tsx"),
            "Shared::Utils": _node("Shared::Utils", "shared/utils/Utils.ts"),
        }
        service_roots = {"SvcA::Widget": "svc-a", "Shared::Utils": "shared"}
        edges = [_edge("SvcA::Widget", "Shared::Utils", "imports")]
        result = filter_cross_service(edges, nodes, service_roots)
        assert len(result) == 1

    def test_preserves_calls_api(self):
        """calls_api is always preserved."""
        nodes = {
            "FE": _node("FE", "frontend/App.tsx"),
            "BE": _node("BE", "backend/Api.java"),
        }
        service_roots = {"FE": "frontend", "BE": "backend"}
        edges = [_edge("FE", "BE", "calls_api")]
        result = filter_cross_service(edges, nodes, service_roots)
        assert len(result) == 1

    def test_preserves_non_import_relations(self):
        """Non-import relations (injects, calls) are never filtered."""
        nodes = {
            "A": _node("A", "svc-a/A.java"),
            "B": _node("B", "svc-b/B.java"),
        }
        service_roots = {"A": "svc-a", "B": "svc-b"}
        edges = [_edge("A", "B", "injects"), _edge("A", "B", "calls")]
        result = filter_cross_service(edges, nodes, service_roots)
        assert len(result) == 2
