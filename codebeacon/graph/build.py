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
    # raw_id → first source_file that claimed it. Used to disambiguate
    # same-name-different-directory collisions (graphify #952 / #949).
    # Shared across all waves so a name colliding between projects still
    # produces stable distinct ids.
    claimed_ids: dict[str, str] = {}

    for wave in wave_results:
        project_name = wave.project.name
        _ingest_wave(
            wave, project_name, all_nodes, all_edges, all_unresolved,
            service_roots, claimed_ids,
        )

    # Rewrite file-path-keyed UnresolvedRef sources onto their final node IDs.
    # The per-file extractors mint ``UnresolvedRef.source_node_id`` as
    # ``f"{file_path}::{name}"`` (see extract/services.py::_nid), but graph nodes
    # are keyed ``project::name``. Left unrewritten, the resolved injects edge
    # carries a source the graph has never heard of and gets silently dropped by
    # ``_build_nx_graph``. Spring/NestJS survive that drop because they *also*
    # stage the dependency on ``svc.dependencies`` (which _ingest_wave re-emits
    # with the correct id), but FastAPI ``Depends()``, Laravel ``bind()`` and
    # ASP.NET ``AddScoped<>`` only ever emit the file-path form — so their DI
    # edges vanished entirely until this remap.
    _remap_unresolved_sources(all_nodes, all_unresolved)

    # Cross-file declaration merge. When the same symbol appears in multiple
    # files (Swift `extension Foo`, C# partial classes, Ruby reopened classes),
    # the per-file extractor emits one Node per file. NetworkX collapses them
    # by id but the LAST attrs win, losing fields/methods declared in sibling
    # files. Union them deterministically. Mirrors graphify #406bea4.
    all_nodes = _merge_cross_file_decls(all_nodes)

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
    claimed_ids: dict[str, str],
) -> None:
    """Convert one WaveResult's extraction data into Node/Edge/UnresolvedRef objects."""

    # Routes → route nodes (method+path already make the id unique; no
    # disambiguation needed)
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
        node_id, label = _disambiguate_decl(
            project_name, svc.class_name, svc.source_file, claimed_ids,
        )
        node = Node(
            id=node_id,
            label=label,
            type="class",
            source_file=svc.source_file,
            line=svc.line,
            metadata={
                "methods": svc.methods,
                "dependencies": svc.dependencies,
                "annotations": svc.annotations,
                "implements": svc.implements,
                "extends": svc.extends,
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
        node_id, label = _disambiguate_decl(
            project_name, ent.name, ent.source_file, claimed_ids,
        )
        node = Node(
            id=node_id,
            label=label,
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
        node_id, label = _disambiguate_decl(
            project_name, comp.name, comp.source_file, claimed_ids,
        )
        node = Node(
            id=node_id,
            label=label,
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


def _disambiguate_decl(
    project_name: str,
    name: str,
    source_file: str,
    claimed: dict[str, str],
) -> tuple[str, str]:
    """Return ``(node_id, label)`` for a declaration, disambiguating same-name
    collisions across different directories.

    Mirrors graphify #952 / #949: before this guard, ``auth/User.py`` and
    ``admin/User.py`` both produced ``project::User`` so NetworkX silently
    collapsed them into a single node — and the 0.6.0 cross-file merge
    then union-merged their unrelated methods and fields.

    Rule:
      * first declaration claims ``project::Name`` and keeps the bare label.
      * a second declaration in the **same directory** is allowed to share
        the id — this is the genuine cross-file declaration case (Swift
        ``extension Foo``, C# ``partial class``, Ruby reopened classes).
        The merge step will union their list-valued metadata.
      * a declaration in a **different directory** gets a directory-hinted
        id (``project::auth/User``) and a label suffixed with the parent
        dir (``"User (auth)"``) so the wiki / query / MCP layers can tell
        the two classes apart.
    """
    raw_id = f"{project_name}::{name}"
    new_parent = Path(source_file).parent
    if raw_id not in claimed:
        claimed[raw_id] = source_file
        return raw_id, name

    existing_parent = Path(claimed[raw_id]).parent
    if existing_parent == new_parent:
        # same dir → genuine cross-file declaration; merge step will union
        return raw_id, name

    # Different directory — distinct symbol that just happens to share a name.
    hint = new_parent.name or "root"
    disambiguated = f"{project_name}::{hint}/{name}"
    # Rare double collision: same parent-name but in a different ancestry.
    # Fall back to a short content-stable hash of the full directory path.
    if disambiguated in claimed and Path(claimed[disambiguated]).parent != new_parent:
        import hashlib
        h = hashlib.sha1(str(new_parent).encode("utf-8")).hexdigest()[:6]
        disambiguated = f"{project_name}::{hint}@{h}/{name}"
    claimed[disambiguated] = source_file
    return disambiguated, f"{name} ({hint})"


# ── UnresolvedRef source remap ────────────────────────────────────────────────

def _bare_name(node_id: str) -> str:
    """Recover a declaration's plain name from its graph node ID.

    Node IDs are ``project::Name`` or, for directory-disambiguated collisions,
    ``project::hint/Name`` — so the trailing path segment after the last ``::``
    and ``/`` is the original symbol name. Route IDs carry extra ``::`` segments
    but are never DI sources, so the (harmless) value they yield never matches a
    real ``ref_name``.
    """
    return node_id.rsplit("::", 1)[-1].rsplit("/", 1)[-1]


def _remap_unresolved_sources(
    all_nodes: list[Node], all_unresolved: list[UnresolvedRef]
) -> None:
    """Point each UnresolvedRef at a real graph node ID, in place.

    Two lookup tables are built from the finalized node set:

    * ``by_file_name`` — ``(source_file, bare_name) → node_id``. This is the
      exact case: the injecting class is declared in the same file the
      extractor stamped onto the ref (Spring, NestJS, FastAPI).
    * ``by_name`` — ``bare_name → node_id``. The fallback for binding-style DI
      where the ref's file is the *registration site* (a Laravel ServiceProvider
      or an ASP.NET ``Startup``) but the intended source node is the
      implementation class declared elsewhere.

    A ref whose ``source_node_id`` already names a live node (the
    ``project::Name`` form that ``_ingest_wave`` emits from ``svc.dependencies``)
    is left untouched, so this never disturbs edges that already resolve. A ref
    that matches nothing is also left as-is and will drop exactly as it did
    before — no regression, only recovery.
    """
    node_ids = {n.id for n in all_nodes}
    by_file_name: dict[tuple[str, str], str] = {}
    by_name: dict[str, list[str]] = {}
    for n in all_nodes:
        bare = _bare_name(n.id)
        by_file_name.setdefault((n.source_file, bare), n.id)
        by_name.setdefault(bare, []).append(n.id)

    for ref in all_unresolved:
        sid = ref.source_node_id
        if sid in node_ids:
            continue  # already a valid graph node id
        file_part, sep, name_part = sid.rpartition("::")
        if not sep or not name_part:
            continue
        new_id = by_file_name.get((file_part, name_part))
        if new_id is None:
            candidates = by_name.get(name_part)
            new_id = candidates[0] if candidates else None
        if new_id is not None:
            ref.source_node_id = new_id


# ── Cross-file declaration merge ──────────────────────────────────────────────

def _merge_cross_file_decls(nodes: list[Node]) -> list[Node]:
    """Union metadata for nodes that share an id across files.

    The first occurrence wins for scalar attrs (source_file, line) so the
    "canonical" declaration is whichever extractor saw the symbol first.
    List-valued metadata (fields, methods, dependencies, annotations,
    relations, props, hooks) is union-merged while preserving order and
    deduping by stable identity.
    """
    _LIST_KEYS = (
        "fields", "methods", "dependencies", "annotations",
        "relations", "props", "hooks", "implements", "extends",
    )
    first: dict[str, Node] = {}
    for node in nodes:
        existing = first.get(node.id)
        if existing is None:
            first[node.id] = node
            continue
        # union list-valued metadata into the first node
        for key in _LIST_KEYS:
            extra = node.metadata.get(key)
            if not extra:
                continue
            current = existing.metadata.setdefault(key, [])
            seen_keys = {_dedupe_key(item) for item in current}
            for item in extra:
                k = _dedupe_key(item)
                if k not in seen_keys:
                    current.append(item)
                    seen_keys.add(k)
    return list(first.values())


def _dedupe_key(item: Any) -> Any:
    """Stable hash key for list-valued metadata items.

    Items are either plain strings or dicts (``{"name": ..., "type": ...}``);
    dicts get the ``name`` field used as the dedupe key when present, else a
    sorted-tuple of items.
    """
    if isinstance(item, dict):
        name = item.get("name")
        if name is not None:
            return ("d", name)
        return ("d", tuple(sorted(item.items())))
    return ("s", item)


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
    # casefold(label) → [node_id, ...] for case-insensitive fallback.
    # casefold() (not lower()) is used so non-ASCII labels — CJK, Cyrillic,
    # German ß — round-trip correctly. Mirrors graphify #86109e9.
    label_cf_to_nodes: dict[str, list[str]] = {}

    for node in all_nodes:
        file_to_nodes.setdefault(node.source_file, []).append(node.id)
        label_to_nodes.setdefault(node.label, []).append(node.id)
        label_cf_to_nodes.setdefault(node.label.casefold(), []).append(node.id)

    remapped: list[Edge] = []
    non_import: list[Edge] = []

    for edge in all_edges:
        # Treat re_exports the same as imports_from for resolution purposes:
        # both go from a file_path to a raw module string, but we want to
        # preserve the distinct relation in the final graph.
        if edge.relation not in ("imports_from", "re_exports"):
            non_import.append(edge)
            continue

        # Resolve source: file_path → node_ids in that file
        source_ids = file_to_nodes.get(edge.source, [])
        if not source_ids:
            continue

        # Resolve target: raw import string → node_id via label matching.
        # Try exact match first, then case-insensitive fallback so that
        # path aliases like @/components/ui/card → "card" resolve to "Card".
        # The fallback is skipped for very short labels (≤ 2 chars) — two
        # different one-character names are almost always coincidence, not
        # the same symbol, and matching them produced phantom cross-language
        # edges in mixed-language repos. Mirrors graphify #4dce16f.
        target_label = _import_to_label(edge.target)
        target_ids = label_to_nodes.get(target_label)
        if not target_ids and len(target_label) > 2:
            target_ids = label_cf_to_nodes.get(target_label.casefold(), [])
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
