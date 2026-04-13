"""Graph build: merge WaveResults → symbol resolve → filter → NetworkX DiGraph.

This is Pass 2 of the two-pass extraction pipeline.

Input:  list[WaveResult] from wave.auto_wave()
Output: networkx.DiGraph with annotated node and edge attributes

Pipeline:
  1. Convert WaveResult data → Node / Edge objects
  2. Build SymbolTable from all nodes across all projects
  3. Resolve UnresolvedRefs → Edges (interface→impl, direct class match)
  4. Apply filters: build artifacts, cross-language imports, cross-service false edges
  5. Construct NetworkX DiGraph (node attrs as flat key=value, not nested dicts)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx

from codebeacon.common.types import Edge, Node, UnresolvedRef
from codebeacon.common.symbols import SymbolTable
from codebeacon.common.filters import (
    filter_build_artifacts,
    filter_cross_language,
    filter_cross_service,
)
from codebeacon.wave import WaveResult


def build_graph(
    wave_results: list[WaveResult],
    apply_filters: bool = True,
) -> nx.DiGraph:
    """Build a NetworkX DiGraph from one or more WaveResults.

    Args:
        wave_results: list of WaveResult objects (one per project)
        apply_filters: whether to run build-artifact, cross-language,
                       and cross-service filters (default: True)

    Returns:
        Annotated nx.DiGraph ready for enrichment, clustering, and analysis.
    """
    all_nodes: list[Node] = []
    all_edges: list[Edge] = []
    all_unresolved: list[UnresolvedRef] = []
    # node_id → project name, used by cross-service filter
    service_roots: dict[str, str] = {}

    for wave in wave_results:
        project_name = wave.project.name
        _ingest_wave(wave, project_name, all_nodes, all_edges, all_unresolved, service_roots)

    # Remap import edges: file_path → raw_import  ➜  node_id → node_id
    all_edges = _remap_import_edges(all_nodes, all_edges)

    # Pass 2: resolve DI references
    symbol_table = SymbolTable()
    symbol_table.build(all_nodes)

    resolved_edges, _ = symbol_table.resolve_all(all_unresolved)
    all_edges.extend(resolved_edges)

    # Filter pass
    if apply_filters:
        all_nodes, all_edges = filter_build_artifacts(all_nodes, all_edges)
        node_dict = {n.id: n for n in all_nodes}
        all_edges = filter_cross_language(all_edges, node_dict)
        all_edges = filter_cross_service(all_edges, node_dict, service_roots)
    else:
        node_dict = {n.id: n for n in all_nodes}

    # Construct NetworkX DiGraph
    return _build_nx_graph(all_nodes, all_edges, node_dict)


# ── Wave ingestion ────────────────────────────────────────────────────────────

def _ingest_wave(
    wave: WaveResult,
    project_name: str,
    all_nodes: list[Node],
    all_edges: list[Edge],
    all_unresolved: list[UnresolvedRef],
    service_roots: dict[str, str],
) -> None:
    """Convert one WaveResult's extraction data into Node/Edge/UnresolvedRef objects."""

    # Routes → route nodes
    for route in wave.routes:
        node_id = f"{project_name}::{route.handler}::route::{route.method}::{route.path}"
        node = Node(
            id=node_id,
            label=f"{route.handler} [{route.method} {route.path}]",
            type="route",
            source_file=route.source_file,
            line=route.line,
            metadata={
                "method": route.method,
                "path": route.path,
                "prefix": route.prefix,
                "framework": route.framework,
                "tags": route.tags,
                "project": project_name,
            },
        )
        all_nodes.append(node)
        service_roots[node_id] = project_name

    # Services → class nodes + unresolved DI refs
    for svc in wave.services:
        node_id = f"{project_name}::{svc.class_name}"
        node = Node(
            id=node_id,
            label=svc.class_name,
            type="class",
            source_file=svc.source_file,
            line=svc.line,
            metadata={
                "methods": svc.methods,
                "dependencies": svc.dependencies,
                "annotations": svc.annotations,
                "framework": svc.framework,
                "project": project_name,
            },
        )
        all_nodes.append(node)
        service_roots[node_id] = project_name

        # Each declared dependency becomes an UnresolvedRef
        for dep_name in svc.dependencies:
            all_unresolved.append(UnresolvedRef(
                source_node_id=node_id,
                ref_type="depends",
                ref_name=dep_name,
                framework=svc.framework,
            ))

    # Entities → entity nodes
    for ent in wave.entities:
        node_id = f"{project_name}::{ent.name}"
        node = Node(
            id=node_id,
            label=ent.name,
            type="entity",
            source_file=ent.source_file,
            line=ent.line,
            metadata={
                "table_name": ent.table_name,
                "fields": ent.fields,
                "relations": ent.relations,
                "framework": ent.framework,
                "project": project_name,
            },
        )
        all_nodes.append(node)
        service_roots[node_id] = project_name

    # Components → component nodes
    for comp in wave.components:
        node_id = f"{project_name}::{comp.name}"
        node = Node(
            id=node_id,
            label=comp.name,
            type="component",
            source_file=comp.source_file,
            line=comp.line,
            metadata={
                "props": comp.props,
                "hooks": comp.hooks,
                "is_page": comp.is_page,
                "route_path": comp.route_path,
                "framework": comp.framework,
                "project": project_name,
            },
        )
        all_nodes.append(node)
        service_roots[node_id] = project_name

    # Import edges from Pass 1
    all_edges.extend(wave.import_edges)
    # Remaining unresolved refs from Pass 1 (e.g. @Autowired)
    all_unresolved.extend(wave.unresolved)


# ── Import edge remapping ────────────────────────────────────────────────────

def _remap_import_edges(all_nodes: list[Node], all_edges: list[Edge]) -> list[Edge]:
    """Remap import edges from file_path → raw_import to node_id → node_id.

    dependencies.py emits Edge(source=file_path, target=raw_import_string).
    Graph nodes use IDs like "project::ClassName".  This function bridges the
    two by building reverse maps and resolving both sides.
    """
    # source_file → [node_id, ...]
    file_to_nodes: dict[str, list[str]] = {}
    # label (class/component name) → [node_id, ...]
    label_to_nodes: dict[str, list[str]] = {}

    for node in all_nodes:
        file_to_nodes.setdefault(node.source_file, []).append(node.id)
        label_to_nodes.setdefault(node.label, []).append(node.id)

    remapped: list[Edge] = []
    non_import: list[Edge] = []

    for edge in all_edges:
        if edge.relation != "imports_from":
            non_import.append(edge)
            continue

        # Resolve source: file_path → node_ids in that file
        source_ids = file_to_nodes.get(edge.source, [])
        if not source_ids:
            continue

        # Resolve target: raw import string → node_id via label matching
        target_label = _import_to_label(edge.target)
        target_ids = label_to_nodes.get(target_label, [])
        if not target_ids:
            continue

        for src_id in source_ids:
            src_project = src_id.split("::")[0] if "::" in src_id else ""
            # Prefer same-project target
            target_id = target_ids[0]
            for tid in target_ids:
                if tid.startswith(src_project + "::"):
                    target_id = tid
                    break
            if src_id != target_id:
                remapped.append(Edge(
                    source=src_id,
                    target=target_id,
                    relation=edge.relation,
                    confidence=edge.confidence,
                    confidence_score=edge.confidence_score,
                    source_file=edge.source_file,
                ))

    return non_import + remapped


def _import_to_label(raw_import: str) -> str:
    """Extract a class/component name from a raw import string.

    Examples:
        "@/components/Button"           → "Button"
        "com.example.service.UserSvc"   → "UserSvc"
        "../auth/AuthService"           → "AuthService"
        "./UserPage"                    → "UserPage"
    """
    # Java-style package: no slashes, dots as separators
    if "." in raw_import and "/" not in raw_import:
        return raw_import.rsplit(".", 1)[-1]
    # Path-style: take last segment
    name = raw_import.rsplit("/", 1)[-1]
    # Strip file extension
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name


# ── NetworkX construction ─────────────────────────────────────────────────────

def _build_nx_graph(
    nodes: list[Node],
    edges: list[Edge],
    node_dict: dict[str, Node],
) -> nx.DiGraph:
    G = nx.DiGraph()

    for node in nodes:
        attrs = _node_attrs(node)
        G.add_node(node.id, **attrs)

    for edge in edges:
        if edge.source not in G:
            continue
        if edge.target not in G:
            # Add external stub for unresolved targets
            G.add_node(
                edge.target,
                label=edge.target,
                type="external",
                source_file="",
                line=0,
                project="",
            )
        G.add_edge(
            edge.source,
            edge.target,
            relation=edge.relation,
            confidence=edge.confidence,
            confidence_score=edge.confidence_score,
            source_file=edge.source_file,
        )

    return G


def _node_attrs(node: Node) -> dict[str, Any]:
    """Flatten a Node into NetworkX attribute dict (no nested dicts)."""
    attrs: dict[str, Any] = {
        "label": node.label,
        "type": node.type,
        "source_file": node.source_file,
        "line": node.line,
    }
    # Flatten metadata as top-level keys
    for k, v in (node.metadata or {}).items():
        # Stringify lists/dicts for simple serialisation
        if isinstance(v, (list, dict)):
            attrs[k] = v  # NetworkX handles these fine in memory
        else:
            attrs[k] = v
    return attrs
