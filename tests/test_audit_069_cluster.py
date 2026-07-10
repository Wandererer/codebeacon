"""Audit 0.6.9 — graph/cluster graspologic-Leiden backend regression (#47).

Covers one confirmed bug:
  #47   cluster.py::_try_graspologic unpacked ``communities, _ = leiden(UG)``,
        but graspologic 3.x's ``leiden()`` returns a plain ``dict[node, community]``
        (not a ``(partition, modularity)`` tuple). Every call raised
        "too many values to unpack", warned, and silently degraded to the
        Louvain fallback — so the highest-quality backend never ran. The fix
        accepts both the dict and legacy-tuple shapes.
"""
from __future__ import annotations

import warnings

import networkx as nx
import pytest

from codebeacon.graph import cluster


def _small_graph() -> nx.DiGraph:
    """Two loosely-connected triangles — enough structure for Leiden."""
    G = nx.DiGraph()
    G.add_edges_from(
        [
            ("a", "b"), ("b", "c"), ("a", "c"),   # triangle 1
            ("c", "d"),                            # bridge
            ("d", "e"), ("e", "f"), ("d", "f"),   # triangle 2
        ]
    )
    return G


def _need_graspologic() -> None:
    try:
        import graspologic.partition  # noqa: F401
    except ImportError:
        pytest.skip("graspologic not installed")


class TestGraspologicLeidenBackend:
    def test_returns_mapping_without_leiden_failed_warning(self):
        """#47: the dict-returning leiden() must be accepted, not unpacked.

        Before the fix this raised "too many values to unpack (expected 2)",
        emitted a "graspologic leiden failed" warning, and returned None
        (degrading to Louvain). Now it returns a real node→community mapping
        with no such warning.
        """
        _need_graspologic()
        G = _small_graph()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = cluster._try_graspologic(G)

        assert result is not None, "graspologic backend must run, not fall through"
        assert set(result) == set(G.nodes())
        assert all(isinstance(cid, int) for cid in result.values())

        leiden_failures = [
            str(w.message)
            for w in caught
            if "graspologic leiden failed" in str(w.message)
        ]
        assert not leiden_failures, f"unexpected leiden failure: {leiden_failures}"

    def test_cluster_end_to_end_deterministic(self):
        """cluster() stays deterministic (via _relabel_stable) across runs."""
        _need_graspologic()
        G = _small_graph()
        first = cluster.cluster(G)
        second = cluster.cluster(G)
        assert first == second
        # _relabel_stable assigns consecutive IDs from 0.
        assert set(first.values()) == set(range(len(set(first.values()))))
        assert set(first) == set(G.nodes())
