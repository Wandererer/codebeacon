"""Graph enrichment: HTTP API cross-service edges + shared DB entity edges.

Two enrichment passes run AFTER the base graph is built by build.py:
  1. enrich_http_api()  — frontend URL calls → backend controller routes (calls_api edges)
  2. enrich_shared_db() — same DAO/Entity used by multiple services (shares_db_entity edges)
"""

from __future__ import annotations

import re

import networkx as nx


def enrich_http_api(G: nx.DiGraph) -> int:
    """Add calls_api edges where frontend URL patterns match backend route paths.

    Strategy:
    - Collect all 'route' nodes with their path attribute
    - Collect all component/class nodes that declare api_calls in metadata
    - Match URLs to routes: exact first, then parameterized

    Returns:
        Number of new calls_api edges added.
    """
    added = 0

    # Build route lookup: normalized_path → node_id
    route_map: dict[str, str] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") != "route":
            continue
        path = data.get("path", "")
        if path:
            route_map[_normalize_path(path)] = node_id

    if not route_map:
        return 0

    # Find frontend nodes that declare api_calls
    for node_id, data in G.nodes(data=True):
        if data.get("type") not in ("component", "class"):
            continue
        api_calls = data.get("api_calls", [])
        if not api_calls:
            continue

        src_file = data.get("source_file", "")

        for url in api_calls:
            normalized = _normalize_path(url)

            # Exact match
            if normalized in route_map:
                target_id = route_map[normalized]
                if not G.has_edge(node_id, target_id):
                    G.add_edge(
                        node_id, target_id,
                        relation="calls_api",
                        confidence="EXTRACTED",
                        confidence_score=1.0,
                        source_file=src_file,
                    )
                    added += 1
                continue

            # Parameterized match: /api/users/123 → /api/users/:id
            for route_path, route_node_id in route_map.items():
                if _paths_match(normalized, route_path):
                    if not G.has_edge(node_id, route_node_id):
                        G.add_edge(
                            node_id, route_node_id,
                            relation="calls_api",
                            confidence="INFERRED",
                            confidence_score=0.8,
                            source_file=src_file,
                        )
                        added += 1
                    break

    return added


def enrich_shared_db(G: nx.DiGraph) -> int:
    """Add shares_db_entity edges when the same entity is accessed by multiple services.

    Detection strategy:
    - Find all entity nodes
    - For each entity, collect which service/class nodes reference it (via any edge)
    - If references span more than one project → add shares_db_entity between those projects

    Returns:
        Number of new shares_db_entity edges added.
    """
    added = 0

    # Collect entity nodes
    entity_ids: set[str] = {
        node_id
        for node_id, data in G.nodes(data=True)
        if data.get("type") == "entity"
    }

    if not entity_ids:
        return 0

    for entity_id in entity_ids:
        entity_data = G.nodes[entity_id]
        entity_src = entity_data.get("source_file", "")

        # Find all nodes that reference this entity (in-edges or out-edges)
        referencing: list[str] = [
            n for n in list(G.predecessors(entity_id)) + list(G.successors(entity_id))
            if G.nodes[n].get("type") in ("class", "route", "component")
        ]

        # Group referencing nodes by project
        project_reps: dict[str, str] = {}  # project → first node_id as representative
        for ref_id in referencing:
            proj = G.nodes[ref_id].get("project", "")
            if proj and proj not in project_reps:
                project_reps[proj] = ref_id

        if len(project_reps) < 2:
            continue  # only interesting when multiple projects share an entity

        projects = list(project_reps.keys())
        for i in range(len(projects)):
            for j in range(i + 1, len(projects)):
                src_rep = project_reps[projects[i]]
                tgt_rep = project_reps[projects[j]]
                if not G.has_edge(src_rep, tgt_rep):
                    G.add_edge(
                        src_rep, tgt_rep,
                        relation="shares_db_entity",
                        confidence="INFERRED",
                        confidence_score=0.9,
                        source_file=entity_src,
                        shared_entity=entity_id,
                    )
                    added += 1

    return added


# ── URL / path utilities ──────────────────────────────────────────────────────

def _normalize_path(path: str) -> str:
    """Normalize a URL or route path for comparison."""
    path = path.split("?")[0].split("#")[0]  # strip query + fragment
    path = path.rstrip("/") or "/"
    return path.lower()


def _paths_match(url: str, route_pattern: str) -> bool:
    """Check if a concrete URL matches a parameterized route pattern.

    Handles :param, {param}, [param], and <param> styles.
    """
    # Convert all parameter styles to a regex segment
    pattern = re.sub(r":[^/]+", r"[^/]+", route_pattern)
    pattern = re.sub(r"\{[^}]+\}", r"[^/]+", pattern)
    pattern = re.sub(r"\[[^\]]+\]", r"[^/]+", pattern)
    pattern = re.sub(r"<[^>]+>", r"[^/]+", pattern)
    try:
        return bool(re.fullmatch(pattern, url))
    except re.error:
        return False
