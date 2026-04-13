"""Community detection for the codebeacon knowledge graph.

Attempts clustering in order of quality:
  1. graspologic Leiden   — best quality, requires: pip install graspologic
  2. leidenalg            — good quality, requires: pip install leidenalg igraph
  3. NetworkX Louvain     — built into networkx >= 3.0 (seed-stable)
  4. Weakly connected components — always available fallback

Public API:
    cluster(G)              → dict[node_id, community_id]
    apply_communities(G, communities)  → writes community attr to G nodes
    score_all(G, communities)          → dict[community_id, cohesion_score]
"""

from __future__ import annotations

import warnings
from typing import Optional

import networkx as nx


def cluster(G: nx.DiGraph) -> dict[str, int]:
    """Detect communities in the graph.

    Returns:
        node_id → community_id mapping (community IDs are consecutive integers
        starting from 0).
    """
    if G.number_of_nodes() == 0:
        return {}

    result = _try_graspologic(G)
    if result is not None:
        return result

    result = _try_leidenalg(G)
    if result is not None:
        return result

    result = _try_louvain(G)
    if result is not None:
        return result

    return _connected_components(G)


def apply_communities(G: nx.DiGraph, communities: dict[str, int]) -> None:
    """Write community labels back as node attributes (in-place)."""
    for node_id, community_id in communities.items():
        if node_id in G:
            G.nodes[node_id]["community"] = community_id


def score_all(G: nx.DiGraph, communities: dict[str, int]) -> dict[int, float]:
    """Compute a simple edge-based cohesion score for each community.

    Cohesion = internal_edges / (internal_edges + boundary_edges).
    A score of 1.0 means all edges stay within the community.

    Returns:
        community_id → cohesion score (0.0–1.0).
    """
    if not communities:
        return {}

    # Build community → member set
    community_nodes: dict[int, set[str]] = {}
    for node, cid in communities.items():
        community_nodes.setdefault(cid, set()).add(node)

    scores: dict[int, float] = {}
    for cid, members in community_nodes.items():
        internal = sum(
            1 for u, v in G.edges()
            if u in members and v in members
        )
        boundary = sum(
            1 for u, v in G.edges()
            if (u in members) != (v in members)
        )
        total = internal + boundary
        scores[cid] = internal / total if total > 0 else 1.0

    return scores


# ── Algorithm implementations ─────────────────────────────────────────────────

def _try_graspologic(G: nx.DiGraph) -> Optional[dict[str, int]]:
    """Leiden via graspologic."""
    try:
        from graspologic.partition import leiden

        UG = G.to_undirected()
        if UG.number_of_edges() == 0:
            return None

        communities, _ = leiden(UG)
        return {str(k): int(v) for k, v in communities.items()}
    except ImportError:
        return None
    except Exception as exc:
        warnings.warn(f"graspologic leiden failed: {exc}", stacklevel=2)
        return None


def _try_leidenalg(G: nx.DiGraph) -> Optional[dict[str, int]]:
    """Leiden via leidenalg + python-igraph."""
    try:
        import leidenalg
        import igraph as ig

        UG = G.to_undirected()
        if UG.number_of_edges() == 0:
            return None

        nodes = list(UG.nodes())
        node_idx = {n: i for i, n in enumerate(nodes)}
        edges = [(node_idx[u], node_idx[v]) for u, v in UG.edges()]

        g = ig.Graph(n=len(nodes), edges=edges, directed=False)
        partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)

        result: dict[str, int] = {}
        for community_id, members in enumerate(partition):
            for member_idx in members:
                result[nodes[member_idx]] = community_id
        return result
    except ImportError:
        return None
    except Exception as exc:
        warnings.warn(f"leidenalg failed: {exc}", stacklevel=2)
        return None


def _try_louvain(G: nx.DiGraph) -> Optional[dict[str, int]]:
    """Louvain via networkx built-in (nx >= 3.0)."""
    try:
        UG = G.to_undirected()
        if UG.number_of_edges() == 0:
            return None

        communities = nx.community.louvain_communities(UG, seed=42)
        result: dict[str, int] = {}
        for community_id, members in enumerate(communities):
            for node in members:
                result[node] = community_id
        return result
    except (AttributeError, Exception):
        return None


def _connected_components(G: nx.DiGraph) -> dict[str, int]:
    """Fallback: weakly connected components as pseudo-communities."""
    result: dict[str, int] = {}
    for community_id, component in enumerate(nx.weakly_connected_components(G)):
        for node in component:
            result[node] = community_id
    return result
