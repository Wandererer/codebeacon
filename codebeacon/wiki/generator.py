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
    generate_wiki(G, communities, output_dir)  → int (files actually rewritten)
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import networkx as nx

from codebeacon.common.io import write_text_if_changed
from codebeacon.common.safety import dedup_stem, safe_wiki_filename
from codebeacon.graph.write import relativize_source_file
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


def _safe_filename(label: str, dest_dir: Path | None = None) -> str:
    """Strip filename-unsafe characters, then cap the stem to a safe byte length.

    The byte cap stops a pathologically long class label (or an 85+ character
    CJK name) from overflowing the filesystem's per-component limit and crashing
    the whole wiki write with ENAMETOOLONG. ``cap_filename`` keeps long-prefix
    labels distinct via a hash suffix, so two capped names never collide.
    ``dest_dir`` narrows the budget to what that directory can actually hold.
    """
    # Delegates to the shared transform so generator filenames and template
    # links can never drift apart again.
    return safe_wiki_filename(label, dest_dir=dest_dir)


def _project_type_map(
    G: nx.DiGraph, project_name: str
) -> dict[str, list[tuple[str, dict]]]:
    """Rebuild the ``type → [(node_id, data)]`` map for one project in graph order.

    Mirrors the grouping ``generate_wiki`` performs up front, so the resolver
    (``node_to_wiki_path``) can replay the writer's dedup over the exact same
    node set and iteration order.
    """
    type_map: dict[str, list[tuple[str, dict]]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("project", "_unknown") != project_name:
            continue
        ntype = data.get("type", "unknown")
        type_map.setdefault(ntype, []).append((node_id, data))
    return type_map


def _iter_project_articles(
    G: nx.DiGraph,
    project_name: str,
    type_map: dict[str, list[tuple[str, dict]]],
    proj_dir: Path | None = None,
) -> Iterator[tuple[str, dict, str, str]]:
    """Yield ``(node_id, data, bucket, stem)`` for every per-node article of a
    project, in write order, replaying the collision-salting.

    Single source of truth for on-disk article filenames: the writer
    (``_write_project``), the index links, the stale-article prune, and the
    resolver (``node_to_wiki_path``) all consume it, so the salted stem a
    colliding node lands on can never drift between them (BH-W2).
    ``dedup_stem`` salts the *second* distinct node that maps to an
    already-claimed ``<bucket>/<stem>`` key, so the class → entity → component
    order below must match the writer's exactly.

    ``proj_dir`` — the project's directory on disk — makes the byte budget
    destination-aware. It is optional because the resolver has only the graph;
    on any filesystem where the budget is not actually reduced (the normal case)
    both produce the same stem.
    """
    def stem_for(label: str, bucket: str) -> str:
        return _safe_filename(label, (proj_dir / bucket) if proj_dir else None)

    claimed: dict[str, str] = {}
    for node_id, data in type_map.get("class", []):
        label = data.get("label") or node_id
        annotations = data.get("annotations") or []
        bucket = "controllers" if _is_controller(label, annotations) else "services"
        stem = dedup_stem(stem_for(label, bucket), node_id, claimed, bucket)
        yield node_id, data, bucket, stem
    for node_id, data in type_map.get("entity", []):
        label = data.get("label") or node_id
        stem = dedup_stem(stem_for(label, "entities"), node_id, claimed, "entities")
        yield node_id, data, "entities", stem
    for node_id, data in type_map.get("component", []):
        label = data.get("label") or node_id
        stem = dedup_stem(stem_for(label, "components"), node_id, claimed, "components")
        yield node_id, data, "components", stem


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
    if ntype not in ("class", "entity", "component"):
        # route, external, concept, document, paper — no dedicated wiki article
        return None
    project = data.get("project", "_unknown")
    # Replay the writer's per-project dedup so the returned filename matches the
    # file actually on disk. Deriving the stem statelessly from the label alone
    # would always return the FIRST (unsalted) article, silently handing back the
    # wrong node's documentation when two same-bucket nodes share a label (BH-W2).
    for nid, _d, bucket, stem in _iter_project_articles(
        G, project, _project_type_map(G, project)
    ):
        if nid == node_id:
            return f"{project}/{bucket}/{stem}.md"
    return None


# ── Node neighbour helpers ────────────────────────────────────────────────────

_CALL_RELATIONS = frozenset({"calls", "injects", "depends"})
_ENTITY_TYPES = frozenset({"entity"})


def _predecessors_labels(G: nx.DiGraph, node_id: str, relations: frozenset[str]) -> list[str]:
    """Labels of predecessors connected via the given relation types.

    A ``None`` / empty label falls back to the node id (never ``None``), so the
    templates that ``sorted()``/format this list can't hit a str-vs-None
    TypeError (G06).
    """
    result = []
    for pred in G.predecessors(node_id):
        edge_data = G.edges[pred, node_id]
        if edge_data.get("relation") in relations:
            result.append(G.nodes[pred].get("label") or pred)
    return result


def _successors_labels(G: nx.DiGraph, node_id: str, relations: frozenset[str]) -> list[str]:
    """Labels of successors connected via the given relation types.

    ``None``/empty labels coerce to the node id so downstream sort/format never
    sees ``None`` (G06).
    """
    result = []
    for succ in G.successors(node_id):
        edge_data = G.edges[node_id, succ]
        if edge_data.get("relation") in relations:
            result.append(G.nodes[succ].get("label") or succ)
    return result


def _related_entities(G: nx.DiGraph, node_id: str) -> list[str]:
    """Entity node labels reachable via imports/calls edges.

    ``None``/empty labels coerce to the node id so downstream sort/format never
    sees ``None`` (G06).
    """
    result = []
    for succ in G.successors(node_id):
        if G.nodes[succ].get("type") in _ENTITY_TYPES:
            result.append(G.nodes[succ].get("label") or succ)
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

def _collect_routes(
    G: nx.DiGraph,
    project_roots: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Collect route nodes grouped by project.

    ``source_file`` is relativized here, the way every other article branch does
    it at emit time. Without this the routes table — the one wiki page built from
    route nodes rather than class/entity/component nodes — was the single place
    that still published the build machine's absolute path, complete with the
    developer's username, into a committed artifact nobody else can resolve
    (graphify #3223/#942-10).
    """
    routes_by_project: dict[str, list[dict[str, Any]]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") != "route":
            continue
        project = data.get("project", "_unknown")
        routes_by_project.setdefault(project, []).append({
            "method": data.get("method", ""),
            "path": data.get("path", ""),
            "handler": data.get("label", ""),
            "source_file": relativize_source_file(
                data.get("source_file", ""), (project_roots or {}).get(project)
            ),
            "framework": data.get("framework", ""),
            "tags": data.get("tags", []),
        })
    return routes_by_project


# ── Main generator ────────────────────────────────────────────────────────────

def generate_wiki(
    G: nx.DiGraph,
    communities: dict[str, int],
    output_dir: str | Path,
    project_roots: dict[str, str] | None = None,
) -> int:
    """Generate full wiki from the knowledge graph.

    Args:
        G:             built NetworkX DiGraph (output of graph/build.py + enrich.py)
        communities:   node_id → community_id (output of graph/cluster.py)
        output_dir:    root output directory (e.g. /path/to/project/.codebeacon)
        project_roots: optional project_name → absolute root path; when supplied,
                       each article's ``source_file`` is emitted relative to its
                       project root so committed wiki files stay machine-portable
                       (graphify #1417).

    Returns:
        How many wiki files this run actually rewrote. Every page is regenerated
        on every scan, but only the ones whose content differs are written, so a
        rebuild of an unchanged repository returns 0 and leaves every mtime in
        ``.codebeacon/wiki`` alone (graphify #3060).
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
    _prune_stale_articles(wiki_dir, projects, G)

    # Collect routes for routes.md (all projects)
    routes_by_project = _collect_routes(G, project_roots)

    # Per-project stats accumulator for overview
    project_summary: list[dict[str, Any]] = []
    changed = 0

    for project_name, type_map in sorted(projects.items()):
        proj_dir = wiki_dir / project_name
        project_root = (project_roots or {}).get(project_name)
        changed += _write_project(
            G, project_name, type_map, routes_by_project, proj_dir, project_root
        )

        # Collect summary stats
        route_count = len(routes_by_project.get(project_name, []))
        service_count = 0
        entity_count = 0
        component_count = 0
        framework = ""

        for node_id, data in type_map.get("class", []):
            annotations = data.get("annotations", [])
            # Coerce a None label to the node id before _is_controller so one
            # mis-shaped node can't abort the whole export (G06).
            if not _is_controller(data.get("label") or node_id, annotations):
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
    changed += generate_index(
        wiki_dir=wiki_dir,
        project_summary=project_summary,
        routes_by_project=routes_by_project,
        cross_edges=cross_edges,
        total_stats=total_stats,
    )

    # Every article is now on disk; downgrade any link whose target article was
    # never written so navigation never lands on a missing page (graphify #1444).
    changed += _downgrade_dead_links(wiki_dir)
    return changed


# Matches a portable relative markdown link `[display](./stem.md)` as emitted by
# templates._rel_link / _back_link (targets have no path separators or query).
_REL_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(\./([^)/]+)\.md\)")


def _downgrade_dead_links(wiki_dir: Path) -> int:
    """Repair or downgrade ``[text](./X.md)`` links so none dangle.

    ``templates._rel_link`` emits a ``./X.md`` link for every referenced label
    (DI dependency types, callers/callees, imports), but articles are written
    into per-type sub-buckets (controllers/services/entities/components) under a
    project directory. So a link resolves three ways (graphify #1444):

    * target article is in the SAME directory      → keep the link as-is;
    * target article exists elsewhere in the SAME  → rewrite to the correct
      project (a different bucket)                    relative path (e.g.
                                                       ``../entities/X.md``);
    * target article was never written (framework   → downgrade to plain text.
      type, unresolved interface)

    Resolution is scoped to the article's own project directory (the immediate
    child of ``wiki_dir``; global files at the root form their own scope), so a
    stem is never matched against an unrelated project. Cosmetic: no graph/data
    change. ``../`` links (e.g. the back-link) are not matched by the regex and
    are left untouched.

    Returns how many files it rewrote, for the caller's changed-page tally.
    """
    changed = 0
    # Group every article by its project scope (immediate child dir of wiki_dir;
    # global root-level files share the "" scope).
    by_scope: dict[str, list[Path]] = {}
    for md in wiki_dir.rglob("*.md"):
        rel = md.relative_to(wiki_dir)
        scope = rel.parts[0] if len(rel.parts) > 1 else ""
        by_scope.setdefault(scope, []).append(md)

    for files in by_scope.values():
        # stem → the on-disk article. Two buckets can share a stem (an entity
        # `Order` and a component `Order`); first-writer-wins, but iterate in a
        # SORTED order so the winner is deterministic across platforms — rglob
        # order is unspecified, and a non-deterministic repair target would break
        # the byte-stable-artifact guarantee (#1417). Salted stems are unique.
        files = sorted(files)
        stem_to_path: dict[str, Path] = {}
        for md in files:
            stem_to_path.setdefault(md.stem, md)

        for md in files:
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                continue

            def _repl(m: "re.Match[str]") -> str:
                stem = m.group(2)
                if (md.parent / f"{stem}.md").exists():
                    return m.group(0)  # same directory → keep
                other = stem_to_path.get(stem)
                if other is not None and other.exists():
                    rel_target = os.path.relpath(other, md.parent).replace(os.sep, "/")
                    return f"[{m.group(1)}]({rel_target})"  # repair cross-bucket
                return m.group(1)  # dangling → plain text

            new = _REL_MD_LINK_RE.sub(_repl, text)
            if new != text and _write_file(md, new):
                changed += 1
    return changed


# ── Controller route matching ─────────────────────────────────────────────────

# Method separators across frameworks: Spring/NestJS/ASP.NET ``Class.method``,
# ``Class#method``, Laravel ``Class@method``. A bare ``Class`` (Laravel array
# syntax ``[UserController::class, 'index']``, invokable / bare-function
# handlers) has none of these.
_HANDLER_METHOD_SEPS = (".", "#", "@")


def _route_handler_class(handler: str) -> str:
    """Declaring-class segment of a route handler, for controller route matching.

    Route node labels are built as ``<handler> [<VERB> <path>]`` (build.py:137).
    ``<handler>`` is ``Class.method`` / ``Class#method`` / ``Class@method`` or a
    bare ``Class``. Strip the ``[VERB path]`` suffix first, then peel off the
    method after any separator, so a controller lists its OWN routes for every
    framework — not just dot-handler ones. Matching on ``split(".")[0]`` alone
    left the whole ``"UserController [GET /users]"`` label intact for a non-dot
    handler, so it never equalled the bare ``UserController`` class label and the
    controller article silently dropped every route (BH-W3).
    """
    pre = handler.split(" [", 1)[0]
    for sep in _HANDLER_METHOD_SEPS:
        pre = pre.split(sep, 1)[0]
    return pre


# ── Per-project writer ────────────────────────────────────────────────────────

def _write_project(
    G: nx.DiGraph,
    project_name: str,
    type_map: dict[str, list[tuple[str, dict]]],
    routes_by_project: dict[str, list[dict[str, Any]]],
    proj_dir: Path,
    project_root: str | None = None,
) -> int:
    """Write all wiki files for one project; return how many files changed."""
    proj_dir.mkdir(parents=True, exist_ok=True)
    changed = 0

    # node_id → (bucket, on-disk stem), computed via the same iterator
    # node_to_wiki_path replays. Salting the second of two same-bucket labels
    # that collide on a case-insensitive filesystem (graphify #1453/#1504) now
    # happens in exactly one place, so writer and resolver can never disagree on
    # which file a node owns (BH-W2).
    stem_of = {
        nid: (bucket, stem)
        for nid, _d, bucket, stem in _iter_project_articles(
            G, project_name, type_map, proj_dir
        )
    }

    # (display label, bucket, on-disk stem) per index section. The index has to
    # link the STEM, not a stem re-derived from the label: two same-labelled
    # nodes in one bucket produce `PaymentService.md` and the salted
    # `PaymentService_h5463b7.md`, and re-deriving pointed BOTH index rows at
    # the first file, leaving the second article written but unreachable from
    # the index the lookup strategy starts at (graphify #3032).
    controllers: list[tuple[str, str, str]] = []
    services: list[tuple[str, str, str]] = []

    # Class nodes → controller or service
    for node_id, data in type_map.get("class", []):
        label = data.get("label") or node_id
        annotations = data.get("annotations") or []
        methods = data.get("methods", [])
        dependencies = data.get("dependencies", [])
        source_file = relativize_source_file(data.get("source_file", ""), project_root)
        framework = data.get("framework", "")

        called_by = _predecessors_labels(G, node_id, _CALL_RELATIONS)
        calls = _successors_labels(G, node_id, _CALL_RELATIONS)

        bucket, stem = stem_of[node_id]
        if _is_controller(label, annotations):
            controllers.append((label, bucket, stem))
            # Gather routes for this controller. Match the route handler's class
            # segment EXACTLY — a plain `label in handler` substring test
            # fabricated routes from any controller whose name is a superstring
            # (UserController ⊂ AdminUserController), then misattributed them to
            # this article's source file (BH-W3). `_route_handler_class` peels the
            # class off the `<handler> [<VERB> <path>]` route label across every
            # framework's method separator (and bare handlers), so a controller
            # keeps its OWN routes even when the handler has no dot (Laravel array
            # / invokable / bare-function handlers).
            ctrl_routes = [
                r for r in routes_by_project.get(project_name, [])
                if _route_handler_class(r.get("handler") or "") == label
            ]
            content = templates.controller_article(
                label=label,
                routes=ctrl_routes,
                source_file=source_file,
                called_by=called_by,
                calls=calls,
                project_name=project_name,
            )
            changed += _write_file(proj_dir / bucket / f"{stem}.md", content)
        else:
            services.append((label, bucket, stem))
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
            changed += _write_file(proj_dir / bucket / f"{stem}.md", content)

    # Entity nodes
    entity_names: list[tuple[str, str, str]] = []
    for node_id, data in type_map.get("entity", []):
        label = data.get("label") or node_id
        entity_names.append((label, *stem_of[node_id]))
        table_name = data.get("table_name", "")
        fields = data.get("fields", [])
        relations = data.get("relations", [])
        source_file = relativize_source_file(data.get("source_file", ""), project_root)
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
        changed += _write_file(proj_dir / "entities" / f"{stem_of[node_id][1]}.md", content)

    # Component nodes
    component_names: list[tuple[str, str, str]] = []
    for node_id, data in type_map.get("component", []):
        label = data.get("label") or node_id
        component_names.append((label, *stem_of[node_id]))
        props = data.get("props", [])
        hooks = data.get("hooks", [])
        imports_list = data.get("imports", [])
        is_page = data.get("is_page", False)
        route_path = data.get("route_path", "")
        source_file = relativize_source_file(data.get("source_file", ""), project_root)
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
        changed += _write_file(proj_dir / "components" / f"{stem_of[node_id][1]}.md", content)

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
        changed += _write_file(proj_dir / "routes.md", content)

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
    changed += _write_file(proj_dir / "index.md", content)
    return changed


# ── File writer ───────────────────────────────────────────────────────────────

def _write_file(path: Path, content: str) -> bool:
    """Write one wiki page, skipping the write when it would not change.

    Returns True when the file was actually written. An unwritable page (a
    destination that overruns the filesystem's limits) is reported and skipped
    rather than raised, so one impossible filename costs one article instead of
    the whole wiki (graphify #943-6).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return write_text_if_changed(path, content)
    except OSError as exc:
        print(f"    Warning: skipped wiki page {path.name}: {exc}", file=sys.stderr)
        return False


# ── Stale article pruning ─────────────────────────────────────────────────────

_WIKI_TYPE_DIRS = {
    "class": ("controllers", "services"),   # class nodes split across both
    "entity": ("entities",),
    "component": ("components",),
}


def _prune_stale_articles(
    wiki_dir: Path,
    projects: dict[str, dict[str, list[tuple[str, dict]]]],
    G: nx.DiGraph | None = None,
) -> None:
    """Delete per-node .md files whose underlying graph node no longer exists.

    Without this, ``--update`` runs accumulate stale articles forever: a
    renamed or deleted controller keeps its old file because the rewrite path
    only writes the new name and never touches the old one.

    Scope is intentionally narrow — only the per-node subdirectories
    (``controllers/`` / ``services/`` / ``entities/`` / ``components/``) are
    pruned. Global files (``index.md``, ``routes.md``, ``overview.md``) are
    always fully rewritten, so they self-heal.

    Expectations come from ``_iter_project_articles``, the same iterator the
    writer names files with. Re-deriving them from the bare label instead missed
    every SALTED stem, so each run deleted the salted article and immediately
    rewrote it — churn on a file that never changed, and a window in which the
    article was simply absent.
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
        for _nid, _data, bucket, stem in _iter_project_articles(
            G if G is not None else nx.DiGraph(), project_name, type_map, proj_dir
        ):
            expected[bucket].add(f"{stem}.md")

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
