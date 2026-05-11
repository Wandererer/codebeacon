"""Semantic pipeline behaviour: relation whitelist, LLM-node policy,
archive backward-compat with the 0.3.1 schema."""

from __future__ import annotations

import networkx as nx
import pytest

from codebeacon.semantic_pipeline import (
    ALLOWED_LLM_NODE_TYPES,
    ALLOWED_RELATIONS,
    _label_index,
    _merge_edge,
    _merge_node,
    _normalize_confidence,
    _normalize_relation,
    _reapply_archive,
)


@pytest.fixture
def graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node(
        "auth_loginservice",
        label="LoginService",
        type="service",
        source_file="src/auth.py",
        project="api",
    )
    G.add_node(
        "auth_userrepo",
        label="UserRepo",
        type="service",
        source_file="src/auth.py",
        project="api",
    )
    return G


def test_relation_normalization_accepts_all_8():
    for rel in ALLOWED_RELATIONS:
        assert _normalize_relation(rel) == rel
    assert _normalize_relation("HALLUCINATED_REL") == "references"
    assert _normalize_relation(None) == "references"
    assert _normalize_relation("") == "references"


def test_confidence_normalization_clamps_to_whitelist():
    assert _normalize_confidence("EXTRACTED") == "EXTRACTED"
    assert _normalize_confidence("inferred") == "INFERRED"
    assert _normalize_confidence("ambiguous") == "AMBIGUOUS"
    assert _normalize_confidence("totally_made_up") == "INFERRED"
    assert _normalize_confidence(None) == "INFERRED"


def test_merge_edge_writes_normalized_attributes(graph: nx.DiGraph):
    label_idx = _label_index(graph)
    assert _merge_edge(
        graph, label_idx,
        source_node_id="auth_loginservice",
        target_name="UserRepo",
        relation="calls",
        score=0.9,
        confidence="EXTRACTED",
    )
    e = graph.edges["auth_loginservice", "auth_userrepo"]
    assert e["relation"] == "calls"
    assert e["confidence"] == "EXTRACTED"
    assert e["confidence_score"] == pytest.approx(0.9)


def test_merge_edge_falls_back_on_unknown_relation(graph: nx.DiGraph):
    label_idx = _label_index(graph)
    assert _merge_edge(
        graph, label_idx,
        source_node_id="auth_loginservice",
        target_name="UserRepo",
        relation="invents_new_relation",
    )
    assert graph.edges["auth_loginservice", "auth_userrepo"]["relation"] == "references"


def test_merge_edge_rejects_primitive_target(graph: nx.DiGraph):
    label_idx = _label_index(graph)
    # `String` is in the primitives blocklist (see _is_type_name)
    assert not _merge_edge(graph, label_idx, "auth_loginservice", "String")


def test_merge_node_allows_concept_but_rejects_code(graph: nx.DiGraph):
    label_idx = _label_index(graph)
    assert _merge_node(
        graph, label_idx,
        node_id="rfc6749_oauth2",
        label="OAuth2 RFC 6749",
        file_type="concept",
        source_file="src/auth.py",
    )
    assert "rfc6749_oauth2" in graph
    assert graph.nodes["rfc6749_oauth2"]["type"] == "concept"
    # label_idx was updated so subsequent edges can resolve by label
    assert label_idx["OAuth2 RFC 6749"] == "rfc6749_oauth2"

    # Code file_type is reserved for AST extraction
    assert not _merge_node(
        graph, label_idx,
        node_id="some_fn",
        label="some_fn",
        file_type="code",
        source_file="src/foo.py",
    )
    assert "some_fn" not in graph


def test_merge_node_rejects_unknown_file_type(graph: nx.DiGraph):
    label_idx = _label_index(graph)
    for bad in ("video", "binary", "", "CODE"):
        assert not _merge_node(
            graph, label_idx,
            node_id=f"x_{bad}", label="X",
            file_type=bad, source_file="",
        )


def test_allowed_llm_node_types_matches_advisor_decision():
    # If someone widens this set without updating tests, fail loudly.
    assert ALLOWED_LLM_NODE_TYPES == frozenset({"concept", "document", "paper"})


def test_reapply_archive_handles_0_3_1_format(graph: nx.DiGraph):
    """Old archives only have task_id/source_node_id/edges with target_name+confidence_score.
    The new replay code must still cleanly project them onto the graph."""
    legacy_archive = [
        {
            "task_id": "abc123",
            "source_node_id": "auth_loginservice",
            "edges": [
                {"target_name": "UserRepo", "confidence_score": 0.7},
                {"target_name": "AuthToken", "confidence_score": 0.7},  # external
            ],
        },
    ]
    reapplied, kept = _reapply_archive(graph, legacy_archive)
    assert reapplied == 2
    assert len(kept) == 1
    # Existing target resolves by label_idx
    assert graph.edges["auth_loginservice", "auth_userrepo"]["relation"] == "references"
    assert graph.edges["auth_loginservice", "auth_userrepo"]["confidence"] == "INFERRED"
    # External target is auto-created as a stub
    assert graph.nodes["AuthToken"]["type"] == "external"


def test_reapply_archive_drops_entries_with_missing_source(graph: nx.DiGraph):
    legacy_archive = [
        {"task_id": "deleted", "source_node_id": "gone_node", "edges": [
            {"target_name": "UserRepo", "confidence_score": 0.7},
        ]},
        {"task_id": "alive", "source_node_id": "auth_loginservice", "edges": [
            {"target_name": "UserRepo", "confidence_score": 0.7},
        ]},
    ]
    reapplied, kept = _reapply_archive(graph, legacy_archive)
    assert reapplied == 1
    assert [e["task_id"] for e in kept] == ["alive"]


def test_reapply_archive_replays_new_format_nodes_and_relations(graph: nx.DiGraph):
    """New 0.3.2 archive entries can carry nodes + arbitrary 8-set relations."""
    archive = [
        {
            "task_id": "t1",
            "source_node_id": "auth_loginservice",
            "nodes": [
                {"id": "rfc6749", "label": "OAuth2 RFC 6749",
                 "file_type": "concept", "source_file": "src/auth.py"},
            ],
            "edges": [
                {"target_name": "OAuth2 RFC 6749", "relation": "implements",
                 "confidence": "EXTRACTED", "confidence_score": 1.0},
                {"target_name": "UserRepo", "relation": "shares_data_with",
                 "confidence": "INFERRED", "confidence_score": 0.7},
            ],
        },
    ]
    reapplied, kept = _reapply_archive(graph, archive)
    assert reapplied == 2
    assert "rfc6749" in graph
    assert graph.nodes["rfc6749"]["type"] == "concept"
    assert graph.edges["auth_loginservice", "rfc6749"]["relation"] == "implements"
    assert graph.edges["auth_loginservice", "rfc6749"]["confidence"] == "EXTRACTED"
    assert graph.edges["auth_loginservice", "auth_userrepo"]["relation"] == "shares_data_with"
