"""Wiki generator: read the NetworkX graph, write per-project markdown articles.

Output structure:
    <output_dir>/wiki/
        index.md                        ← global index (short)
        overview.md                     ← platform stats + cross-project
        routes.md                       ← all routes table
        cross-project/
            connections.md              ← cross-service edges
        <project>/
            index.md                    ← project index
            routes.md                   ← project routes
            controllers/<Name>.md
            services/<Name>.md
            entities/<Name>.md
            components/<Name>.md

Public API:
    generate_wiki(G, communities, output_dir)  → None
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import networkx as nx

from codebeacon.common.safety import safe_wiki_filename
from codebeacon.wiki import templates


# ── Classification helpers ────────────────────────────────────────────────────

_CONTROLLER_ANNOTATIONS = frozenset({
    # Spring
    "@Controller", "@RestController",
    # NestJS
    "@Controller",
    # ASP.NET
    "[ApiController]", "[Controller]",
    # Generic
    "Controller", "RestController",
})

_CONTROLLER_NAME_SUFFIXES = ("Controller", "Router", "Handler", "Resource")


def _is_controller(label: str, annotations: list[str]) -> bool:
    """Heuristic: is this class node a controller rather than a service?"""
    if any(a in _CONTROLLER_ANNOTATIONS for a in annotations):
        return True
    return label.endswith(_CONTROLLER_NAME_SUFFIXES)


def _safe_filename(label: str) -> str:
    """Strip filename-unsafe characters, then cap the stem to a safe byte length.

    The byte cap stops a pathologically long class label (or an 85+ character
    CJK name) from overflowing the 255-byte filesystem limit and crashing the
    whole wiki write with ENAMETOOLONG. ``cap_filename`` keeps long-prefix
    labels distinct via a hash suffix, so two capped names never collide.
    """
    # Delegates to the shared transform so generator filenames and template
    # links can never drift apart again.
    return safe_wiki_filename(label)


def node_to_wiki_path(G: nx.DiGraph, node_id: str) -> str | None:
    """Map a graph node to its wiki article path (relative to ``wiki/``).

    Used by ``codebeacon affected --as wiki`` to translate a PR's blast
    radius into the exact wiki documents a reviewer / AI agent should
    consult. Returns ``None`` for node types that wiki generation skips
    (route nodes, external nodes, LLM concept nodes) — callers should
    drop those silently so the output list stays clean.

    The path layout mirrors ``_write_project``:
        <project>/controllers/<Name>.md
        <project>/services/<Name>.md
        <project>/entities/<Name>.md
        <project>/components/<Name>.md
    """
    if node_id not in G:
        return None
    data = G.nodes[node_id]
    ntype = data.get("type", "")
    project = data.get("project", "") or "_"
    label = data.get("label", node_id)
    filename = f"{_safe_filename(label)}.md"

    if ntype == "class":
        annotations = data.get("annotations", []) or []
        bucket = "controllers" if _is_controller(label, annotations) else "services"
        return f"{project}/{bucket}/{filename}"
    if ntype == "entity":
        return f"{project}/entities/{filename}"
    if ntype == "component":
        return f"{project}/components/{filename}"
    # route, external, concept, document, paper — no dedicated wiki article
    return None


# ── Node neighbour helpers ────────────────────────────────────────────────────

_CALL_RELATIONS = frozenset({"calls", "injects", "depends"})
_ENTITY_TYPES = frozenset({"entity"})


def _predecessors_labels(G: nx.DiGraph, node_id: str, relations: frozenset[str]) -> list[str]:
    """Labels of predecessors connected via the given relation types."""
    result = []
    for pred in G.predecessors(node_id):
        edge_data = G.edges[pred, node_id]
        if edge_data.get("relation") in relations:
            result.append(G.nodes[pred].get("label", pred))
    return result


def _successors_labels(G: nx.DiGraph, node_id: str, relations: frozenset[str]) -> list[str]:
    """Labels of successors connected via the given relation types."""
    result = []
    for succ in G.successors(node_id):
        edge_data = G.edges[node_id, succ]
        if edge_data.get("relation") in relations:
            result.append(G.nodes[succ].get("label", succ))
    return result


def _related_entities(G: nx.DiGraph, node_id: str) -> list[str]:
    """Entity node labels reachable via imports/calls edges."""
    result = []
    for succ in G.successors(node_id):
        if G.nodes[succ].get("type") in _ENTITY_TYPES:
            result.append(G.nodes[succ].get("label", succ))
    return result


# ── Cross-project connections ─────────────────────────────────────────────────

def _cross_project_edges(G: nx.DiGraph) -> list[dict[str, Any]]:
    """Edges that cross project boundaries."""
    result = []
    for src, tgt, data in G.edges(data=True):
        src_proj = G.nodes[src].get("project", "")
        tgt_proj = G.nodes[tgt].get("project", "")
        if src_proj and tgt_proj and src_proj != tgt_proj:
            result.append({
                "source": G.nodes[src].get("label", src),
                "target": G.nodes[tgt].get("label", tgt),
                "relation": data.get("relation", ""),
                "source_project": src_proj,
                "target_project": tgt_proj,
            })
    return result


# ── Route collector ───────────────────────────────────────────────────────────

def _collect_routes(G: nx.DiGraph) -> dict[str, list[dict[str, Any]]]:
    """Collect route nodes grouped by project."""
    routes_by_project: dict[str, list[dict[str, Any]]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") != "route":
            continue
        project = data.get("project", "_unknown")
        routes_by_project.setdefault(project, []).append({
            "method": data.get("method", ""),
            "path": data.get("path", ""),
            "handler": data.get("label", ""),
            "source_file": data.get("source_file", ""),
            "framework": data.get("framework", ""),
            "tags": data.get("tags", []),
        })
    return routes_by_project


# ── Main generator ────────────────────────────────────────────────────────────

def generate_wiki(
    G: nx.DiGraph,
    communities: dict[str, int],
    output_dir: str | Path,
) -> None:
    """Generate full wiki from the knowledge graph.

    Args:
        G:            built NetworkX DiGraph (output of graph/build.py + enrich.py)
        communities:  node_id → community_id (output of graph/cluster.py)
        output_dir:   root output directory (e.g. /path/to/project/.codebeacon)
    """
    wiki_dir = Path(output_dir) / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # Group nodes by project and type
    projects: dict[str, dict[str, list[tuple[str, dict]]]] = {}
    # project → type → [(node_id, data)]

    for node_id, data in G.nodes(data=True):
        project = data.get("project", "_unknown")
        ntype = data.get("type", "unknown")
        projects.setdefault(project, {}).setdefault(ntype, []).append((node_id, data))

    # Drop any wiki files for nodes that are no longer in the graph (incremental
    # rebuilds otherwise leak stale articles forever). Mirrors graphify #936.
    _prune_stale_articles(wiki_dir, projects)

    # Collect routes for routes.md (all projects)
    routes_by_project = _collect_routes(G)

    # Per-project stats accumulator for overview
    project_summary: list[dict[str, Any]] = []

    for project_name, type_map in sorted(projects.items()):
        proj_dir = wiki_dir / project_name
        _write_project(G, project_name, type_map, routes_by_project, proj_dir)

        # Collect summary stats
        route_count = len(routes_by_project.get(project_name, []))
        service_count = 0
        entity_count = 0
        component_count = 0
        framework = ""

        for node_id, data in type_map.get("class", []):
            annotations = data.get("annotations", [])
            if not _is_controller(data.get("label", ""), annotations):
                service_count += 1
            fw = data.get("framework", "")
            if fw:
                framework = fw

        entity_count = len(type_map.get("entity", []))
        component_count = len(type_map.get("component", []))

        project_summary.append({
            "name": project_name,
            "framework": framework,
            "route_count": route_count,
            "service_count": service_count,
            "entity_count": entity_count,
            "component_count": component_count,
        })

    # Global stats
    total_routes = sum(len(rs) for rs in routes_by_project.values())
    total_services = sum(p["service_count"] for p in project_summary)
    total_entities = sum(p["entity_count"] for p in project_summary)
    total_components = sum(p["component_count"] for p in project_summary)
    total_stats = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(set(communities.values())) if communities else 0,
        "routes": total_routes,
        "services": total_services,
        "entities": total_entities,
        "components": total_components,
    }

    # Cross-project connections
    cross_edges = _cross_project_edges(G)

    # Write global files (delegated to index.py's generate_index)
    from codebeacon.wiki.index import generate_index
    generate_index(
        wiki_dir=wiki_dir,
        project_summary=project_summary,
        routes_by_project=routes_by_project,
        cross_edges=cross_edges,
        total_stats=total_stats,
    )


# ── Per-project writer ────────────────────────────────────────────────────────

def _write_project(
    G: nx.DiGraph,
    project_name: str,
    type_map: dict[str, list[tuple[str, dict]]],
    routes_by_project: dict[str, list[dict[str, Any]]],
    proj_dir: Path,
) -> None:
    """Write all wiki files for one project."""
    proj_dir.mkdir(parents=True, exist_ok=True)

    controllers: list[str] = []
    services: list[str] = []

    # Class nodes → controller or service
    for node_id, data in type_map.get("class", []):
        label = data.get("label", node_id)
        annotations = data.get("annotations", [])
        methods = data.get("methods", [])
        dependencies = data.get("dependencies", [])
        source_file = data.get("source_file", "")
        framework = data.get("framework", "")

        called_by = _predecessors_labels(G, node_id, _CALL_RELATIONS)
        calls = _successors_labels(G, node_id, _CALL_RELATIONS)

        if _is_controller(label, annotations):
            controllers.append(label)
            # Gather routes for this controller
            ctrl_routes = [
                r for r in routes_by_project.get(project_name, [])
                if label in r.get("handler", "")
            ]
            content = templates.controller_article(
                label=label,
                routes=ctrl_routes,
                source_file=source_file,
                called_by=called_by,
                calls=calls,
                project_name=project_name,
            )
            _write_file(proj_dir / "controllers" / f"{_safe_filename(label)}.md", content)
        else:
            services.append(label)
            entities = _related_entities(G, node_id)
            content = templates.service_article(
                label=label,
                methods=methods,
                dependencies=dependencies,
                source_file=source_file,
                called_by=called_by,
                calls=calls,
                related_entities=entities,
                annotations=annotations,
                project_name=project_name,
            )
            _write_file(proj_dir / "services" / f"{_safe_filename(label)}.md", content)

    # Entity nodes
    entity_names: list[str] = []
    for node_id, data in type_map.get("entity", []):
        label = data.get("label", node_id)
        entity_names.append(label)
        table_name = data.get("table_name", "")
        fields = data.get("fields", [])
        relations = data.get("relations", [])
        source_file = data.get("source_file", "")
        framework = data.get("framework", "")
        used_by = _predecessors_labels(G, node_id, frozenset({"imports", "imports_from", "calls"}))

        content = templates.entity_article(
            label=label,
            table_name=table_name,
            fields=fields,
            relations=relations,
            source_file=source_file,
            used_by=used_by,
            framework=framework,
            project_name=project_name,
        )
        _write_file(proj_dir / "entities" / f"{_safe_filename(label)}.md", content)

    # Component nodes
    component_names: list[str] = []
    for node_id, data in type_map.get("component", []):
        label = data.get("label", node_id)
        component_names.append(label)
        props = data.get("props", [])
        hooks = data.get("hooks", [])
        imports_list = data.get("imports", [])
        is_page = data.get("is_page", False)
        route_path = data.get("route_path", "")
        source_file = data.get("source_file", "")
        framework = data.get("framework", "")

        content = templates.component_article(
            label=label,
            props=props,
            hooks=hooks,
            imports=imports_list,
            is_page=is_page,
            route_path=route_path,
            source_file=source_file,
            framework=framework,
            project_name=project_name,
        )
        _write_file(proj_dir / "components" / f"{_safe_filename(label)}.md", content)

    # Detect framework from any node in this project
    framework = ""
    for type_nodes in type_map.values():
        for _, data in type_nodes:
            fw = data.get("framework", "")
            if fw:
                framework = fw
                break
        if framework:
            break

    # Per-project routes.md
    proj_routes = routes_by_project.get(project_name, [])
    if proj_routes:
        content = templates.routes_summary({project_name: proj_routes})
        _write_file(proj_dir / "routes.md", content)

    # Per-project index.md
    stats = {
        "routes": len(proj_routes),
        "services": len(services),
        "entities": len(entity_names),
        "components": len(component_names),
    }
    content = templates.project_index(
        project_name=project_name,
        framework=framework,
        stats=stats,
        controllers=controllers,
        services=services,
        entities=entity_names,
        components=component_names,
    )
    _write_file(proj_dir / "index.md", content)


# ── File writer ───────────────────────────────────────────────────────────────

def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Stale article pruning ─────────────────────────────────────────────────────

_WIKI_TYPE_DIRS = {
    "class": ("controllers", "services"),   # class nodes split across both
    "entity": ("entities",),
    "component": ("components",),
}


def _prune_stale_articles(
    wiki_dir: Path,
    projects: dict[str, dict[str, list[tuple[str, dict]]]],
) -> None:
    """Delete per-node .md files whose underlying graph node no longer exists.

    Without this, ``--update`` runs accumulate stale articles forever: a
    renamed or deleted controller keeps its old file because the rewrite path
    only writes the new name and never touches the old one.

    Scope is intentionally narrow — only the per-node subdirectories
    (``controllers/`` / ``services/`` / ``entities/`` / ``components/``) are
    pruned. Global files (``index.md``, ``routes.md``, ``overview.md``) are
    always fully rewritten, so they self-heal.
    """
    if not wiki_dir.exists():
        return

    for project_name, type_map in projects.items():
        proj_dir = wiki_dir / project_name
        if not proj_dir.exists():
            continue

        # Build the set of filenames we expect to write for each subdirectory.
        expected: dict[str, set[str]] = {
            "controllers": set(),
            "services": set(),
            "entities": set(),
            "components": set(),
        }
        for node_id, data in type_map.get("class", []):
            label = data.get("label", "")
            if not label:
                continue
            fname = f"{_safe_filename(label)}.md"
            bucket = "controllers" if _is_controller(label, data.get("annotations", [])) else "services"
            expected[bucket].add(fname)
        for node_id, data in type_map.get("entity", []):
            label = data.get("label", "")
            if label:
                expected["entities"].add(f"{_safe_filename(label)}.md")
        for node_id, data in type_map.get("component", []):
            label = data.get("label", "")
            if label:
                expected["components"].add(f"{_safe_filename(label)}.md")

        for subdir_name, keep in expected.items():
            subdir = proj_dir / subdir_name
            if not subdir.exists():
                continue
            for md in subdir.glob("*.md"):
                if md.name not in keep:
                    try:
                        md.unlink()
                    except OSError:
                        pass
