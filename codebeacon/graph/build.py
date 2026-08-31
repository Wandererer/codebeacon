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

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from codebeacon.common.types import Edge, Node, UnresolvedRef
from codebeacon.common.symbols import SymbolTable
from codebeacon.common.filters import (
    families_compatible,
    filter_build_artifacts,
    filter_cross_language,
    filter_cross_service,
    is_runtime_import,
)
from codebeacon.graph.jsmodules import ModuleResolver
from codebeacon.wave import WaveResult

# Edge relations that arrive keyed by (file_path → raw name) and must be
# remapped onto node ids. ``references`` is the AST-semantic relation minted by
# extract/semantic.py; it stamped a FILE PATH as its source, so every one of
# those edges used to be discarded by the builder (V5-EXTRA-1).
_REMAPPED_RELATIONS: frozenset[str] = frozenset(
    {"imports_from", "re_exports", "references"}
)

# Relation precedence on a duplicate (u, v) pair. NetworkX keeps one attribute
# dict per ordered pair, so the last writer used to erase the earlier relation
# outright — a Spring service that both imports and injects a repository kept
# only ``injects`` and vanished from ``hub_files`` (G-0946-11 / GI-2391).
# Specific relations outrank generic ones; ties keep the first writer and record
# the loser under the ``also`` attribute so no relation is ever lost.
_SPECIFIC_RELATIONS: frozenset[str] = frozenset({
    "imports_from", "injects", "re_exports", "calls_api",
    "shares_db_entity", "invokes_command", "imports",
})

# Languages that genuinely re-open a declaration across files: Swift
# ``extension``, C# ``partial class``, Ruby class reopening, Kotlin. Everywhere
# else two same-named declarations in one directory are two different symbols
# and must not share a node (GI-1829 / GI-2810 / G-0923-6).
_REOPEN_EXTS: frozenset[str] = frozenset({".swift", ".cs", ".rb", ".kt", ".kts"})

# Largest file the body-mention gate will read back for import attribution.
_MENTION_READ_LIMIT = 2_000_000
# Above this many candidate declarations, a module import stops contributing
# their names to the body-mention search — the alternation stops being evidence
# and starts being a wildcard.
_MENTION_NAME_LIMIT = 25


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
    # project name → absolute root path, so the artifact / shared-lib filters
    # judge only the segments BELOW the project root, never machine-specific
    # ancestor directories (which may coincidentally be named build/, core/…).
    project_roots: dict[str, str] = {
        w.project.name: w.project.path for w in wave_results if w.project
    }
    # raw_id → (first source_file, node_type) that claimed it. Used to
    # disambiguate same-name collisions across directories AND node types
    # (graphify #952 / #949). Shared across all waves so a name colliding
    # between projects still produces stable distinct ids.
    claimed_ids: dict[str, tuple[str, str]] = {}

    for wave in wave_results:
        project_name = wave.project.name
        _ingest_wave(
            wave, project_name, all_nodes, all_edges, all_unresolved,
            service_roots, claimed_ids,
            project_root=wave.project.path if wave.project else "",
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

    # Two declarations that survived disambiguation may still *read* alike
    # ("User (models)" twice). Give every colliding label the shortest project
    # -relative path suffix that tells them apart (G-0922-7).
    _relabel_collisions(all_nodes, project_roots)

    # Remap import edges: file_path → raw_import  ➜  node_id → node_id.
    # The resolver is built per call — a module-global alias cache would serve a
    # stale tsconfig to `codebeacon watch` / `serve` (G-0949-18).
    resolver = ModuleResolver(_known_files(all_nodes, all_edges), project_roots)
    all_edges = _remap_import_edges(all_nodes, all_edges, resolver, project_roots)

    # Pass 2: resolve DI references. The already-remapped import edges are the
    # evidence the resolver needs to allow a cross-project bind (R7).
    symbol_table = SymbolTable()
    symbol_table.build(all_nodes, import_edges=all_edges, project_roots=project_roots)

    resolved_edges, _ = symbol_table.resolve_all(all_unresolved)
    all_edges.extend(resolved_edges)

    # Filter pass
    if apply_filters:
        all_nodes, all_edges = filter_build_artifacts(
            all_nodes, all_edges, project_roots
        )
        node_dict = {n.id: n for n in all_nodes}
        all_edges = filter_cross_language(all_edges, node_dict)
        all_edges = filter_cross_service(
            all_edges, node_dict, service_roots, project_roots
        )
    else:
        node_dict = {n.id: n for n in all_nodes}

    # Construct NetworkX DiGraph. Insert nodes in stable id order so the node
    # sequence — and therefore beacon.json plus every insertion-order-derived
    # surface (e.g. contextmap's example-note pick) — is byte-reproducible
    # run-to-run. Without this the order tracks ThreadPoolExecutor wave-completion
    # order, which flips even at a fixed PYTHONHASHSEED (#48 node-order
    # non-determinism).
    all_nodes = sorted(all_nodes, key=lambda n: n.id)
    return _build_nx_graph(all_nodes, all_edges, node_dict)


# ── Wave ingestion ────────────────────────────────────────────────────────────

def _ingest_wave(
    wave: WaveResult,
    project_name: str,
    all_nodes: list[Node],
    all_edges: list[Edge],
    all_unresolved: list[UnresolvedRef],
    service_roots: dict[str, str],
    claimed_ids: dict[str, tuple[str, str]],
    project_root: str = "",
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
            project_name, svc.class_name, svc.source_file, "class", claimed_ids,
            project_root,
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
            project_name, ent.name, ent.source_file, "entity", claimed_ids,
            project_root,
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
            project_name, comp.name, comp.source_file, "component", claimed_ids,
            project_root,
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


def _same_decl_site(
    existing_file: str, existing_type: str, source_file: str, node_type: str
) -> bool:
    """True when two declarations are the *same* symbol re-opened, not two symbols.

    Sharing a node id means sharing an identity: the merge step unions both
    declarations' methods, fields and heritage onto one node and the loser's
    file disappears from the graph entirely.

    That is right for exactly two situations:

    * the two records come from the **same file** (an extractor emitting a class
      and its members separately, a Ruby file reopening its own class);
    * the language genuinely re-opens a declaration across files in one
      directory — Swift ``extension Foo``, C# ``partial class``, Ruby class
      reopening, Kotlin.

    Everywhere else, ``src/Button.tsx`` and ``src/Button.jsx`` are two
    components and ``handler_a.py``/``handler_b.py``'s ``load`` are two
    functions. Merging them lost one file's node outright — 6.3% of
    declarations on codebeacon's own corpus (GI-1829 / GI-2810 / G-0923-6).
    """
    if existing_type != node_type:
        return False
    if existing_file == source_file:
        return True
    old, new = Path(existing_file), Path(source_file)
    ext = old.suffix.lower()
    return (
        ext == new.suffix.lower()
        and ext in _REOPEN_EXTS
        and old.parent == new.parent
    )


def _project_rel(source_file: str, project_root: str) -> str:
    """``source_file`` relative to its project root, with ``/`` separators.

    Falls back to the path as given when it is already relative or lies outside
    the root, so a caller that has no root still gets a usable value.
    """
    if project_root and os.path.isabs(source_file):
        try:
            rel = os.path.relpath(source_file, os.path.abspath(project_root))
        except ValueError:
            return source_file.replace("\\", "/")
        if rel != ".." and not rel.startswith(".." + os.sep):
            return rel.replace(os.sep, "/")
    return source_file.replace("\\", "/")


def _disambiguate_decl(
    project_name: str,
    name: str,
    source_file: str,
    node_type: str,
    claimed: dict[str, tuple[str, str]],
    project_root: str = "",
) -> tuple[str, str]:
    """Return ``(node_id, label)`` for a declaration, disambiguating same-name
    collisions across files, directories **or node types**.

    Mirrors graphify #952 / #949: before this guard, ``auth/User.py`` and
    ``admin/User.py`` both produced ``project::User`` so NetworkX silently
    collapsed them into a single node — and the 0.6.0 cross-file merge
    then union-merged their unrelated methods and fields.

    Rule:
      * first declaration claims ``project::Name`` and keeps the bare label.
      * a second declaration at the **same declaration site** (see
        ``_same_decl_site``) shares the id; the merge step unions their
        list-valued metadata.
      * anything else gets a hinted id and a hinted label, so the wiki / query /
        MCP layers can tell the declarations apart. The hint is the parent
        directory across directories, the node type for a same-directory type
        clash, and otherwise the file that owns the declaration — its stem, or
        its extension when the stem is the symbol name itself
        (``Button.tsx`` vs ``Button.jsx`` → ``project::jsx/Button``).

    ``claimed`` maps id → (source_file, node_type) of whichever declaration
    first claimed it.
    """
    raw_id = f"{project_name}::{name}"
    new_parent = Path(source_file).parent
    if raw_id not in claimed:
        claimed[raw_id] = (source_file, node_type)
        return raw_id, name

    existing_file, existing_type = claimed[raw_id]
    if _same_decl_site(existing_file, existing_type, source_file, node_type):
        return raw_id, name

    existing_parent = Path(existing_file).parent
    if existing_parent != new_parent:
        # different directory — distinct symbol that just happens to share a name.
        hint = new_parent.name or "root"
    elif existing_type != node_type:
        # same dir, different node type — a service/entity/component that just
        # happens to share a name; hint the id with the node type.
        hint = node_type
    else:
        # same dir, same type, different FILE. The file is what tells them
        # apart, so name it: its stem, or its extension when the stem is the
        # symbol itself and would not disambiguate anything.
        stem = Path(source_file).stem
        hint = stem if stem and stem != name else (
            Path(source_file).suffix.lstrip(".") or "file"
        )

    disambiguated = f"{project_name}::{hint}/{name}"
    # Rare double collision: same hint reached from a different declaration
    # site. Reopen (merge) only when the prior claimer really is the same site;
    # otherwise fall back to a short hash of the PROJECT-RELATIVE path, so the
    # id is stable across machines and checkouts (R8).
    if disambiguated in claimed:
        prev_file, prev_type = claimed[disambiguated]
        if not _same_decl_site(prev_file, prev_type, source_file, node_type):
            salt = _project_rel(source_file, project_root)
            h = hashlib.sha1(salt.encode("utf-8")).hexdigest()[:6]
            disambiguated = f"{project_name}::{hint}@{h}/{name}"
    claimed.setdefault(disambiguated, (source_file, node_type))
    return disambiguated, f"{name} ({hint})"


# ── Label collision repair ────────────────────────────────────────────────────

def _relabel_collisions(
    nodes: list[Node], project_roots: dict[str, str]
) -> None:
    """Make every node label unique within its project, in place.

    ``_disambiguate_decl`` hints a label with one path segment, which is not
    enough: ``com/{a,b,c}/models/User.java`` produced ``User``, ``User
    (models)`` and ``User (models)`` — two nodes wearing the same name, so
    free-text discovery through query/MCP/wiki could not tell them apart
    (G-0922-7). Relabel each colliding group with the shortest project-relative
    directory suffix that separates its members, falling back to the file name
    and finally to the node id, which is unique by construction.

    Nodes whose label is already unique are left exactly as they were.
    """
    groups: dict[tuple[str, str], list[Node]] = {}
    for node in nodes:
        if not node.label:
            continue
        project = (node.metadata or {}).get("project") or node.id.split("::")[0]
        groups.setdefault((project, node.label), []).append(node)

    for (project, label), members in groups.items():
        if len(members) < 2:
            continue
        root = project_roots.get(project, "")
        rels = {
            n.id: _project_rel(n.source_file or "", root).split("/")
            for n in members
        }
        base = _bare_name(members[0].id)
        depth = max((len(parts) - 1) for parts in rels.values())
        chosen: Optional[dict[str, str]] = None
        for k in range(1, depth + 1):
            hints = {
                nid: "/".join(parts[max(0, len(parts) - 1 - k):-1]) or "root"
                for nid, parts in rels.items()
            }
            if len(set(hints.values())) == len(members):
                chosen = hints
                break
        if chosen is None:
            # Same directory: the file name is what differs. If even that is
            # shared, the node id always is not.
            hints = {nid: parts[-1] for nid, parts in rels.items()}
            if len(set(hints.values())) != len(members):
                hints = {n.id: n.id.split("::", 1)[-1] for n in members}
            chosen = hints
        for node in members:
            node.label = f"{base} ({chosen[node.id]})"


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


def _shared_path_depth(a: str, b: str) -> int:
    """Number of shared leading path components between two file paths."""
    depth = 0
    for x, y in zip(Path(a).parts, Path(b).parts):
        if x != y:
            break
        depth += 1
    return depth


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
    node_files: dict[str, str] = {}
    by_file_name: dict[tuple[str, str], str] = {}
    by_name: dict[str, list[str]] = {}
    for n in all_nodes:
        bare = _bare_name(n.id)
        node_files.setdefault(n.id, n.source_file or "")
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
            if candidates:
                # The same name may be declared in several projects. ``file_part``
                # is the registration site (a Startup/ServiceProvider file); bind
                # to the candidate whose source file shares the deepest directory
                # prefix with it, so a binding registered under shipping/ resolves
                # to shipping's impl rather than an unrelated same-named class in
                # billing/. On a shared-depth TIE, break it by the lexicographically
                # smallest node id — ``max`` returns the first element at the max, so
                # feeding it ``sorted(candidates)`` makes the winner deterministic and
                # independent of wave/insertion order (the raw ``candidates`` list is
                # built in node order, which is not stable run-to-run).
                new_id = max(
                    sorted(candidates),
                    key=lambda nid: _shared_path_depth(file_part, node_files.get(nid, "")),
                )
            else:
                new_id = None
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

    Scalar metadata is filled in from the other records rather than discarded:
    a Ruby class reopened in a second file may be the only place the extractor
    saw ``table_name``, and dropping it left the entity's wiki page — a page
    that exists to show exactly this — blank (G-0924-4). A value already
    present on the survivor is never overwritten, and the donors are consulted
    in sorted (source_file, line) order so the result does not depend on wave
    completion order.
    """
    _LIST_KEYS = (
        "fields", "methods", "dependencies", "annotations",
        "relations", "props", "hooks", "implements", "extends",
    )
    first: dict[str, Node] = {}
    donors: dict[str, list[Node]] = {}
    for node in nodes:
        existing = first.get(node.id)
        if existing is None:
            first[node.id] = node
            continue
        donors.setdefault(node.id, []).append(node)
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

    for node_id, extra_nodes in donors.items():
        survivor = first[node_id]
        for donor in sorted(extra_nodes, key=lambda n: (n.source_file or "", n.line)):
            for key, value in (donor.metadata or {}).items():
                if key in _LIST_KEYS or isinstance(value, (list, dict)):
                    continue
                if not survivor.metadata.get(key) and value:
                    survivor.metadata[key] = value
    return list(first.values())


def _known_files(nodes: list[Node], edges: list[Edge]) -> set[str]:
    """Every source file the build has evidence was scanned.

    ``WaveResult`` reports only a file *count*, so the corpus is reconstructed
    from what the extraction produced: files that own a declaration, and files
    that emitted an import. That covers every file a module import could
    legitimately name. A file with neither is invisible here, which only means
    an import naming it falls through to the label fallback exactly as before.
    """
    files: set[str] = {n.source_file for n in nodes if n.source_file}
    for edge in edges:
        if edge.relation in _REMAPPED_RELATIONS:
            if edge.source:
                files.add(edge.source)
        if edge.source_file:
            files.add(edge.source_file)
    return files


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

class _BodyMentions:
    """Which declarations in a file actually mention a given name.

    An import is recorded once per FILE, but the edge has to land on a node.
    Fanning it out to every declaration in the file made an N-class file
    importing M names emit N×M edges — a measured 9.3× inflation on
    codebeacon's own corpus and an 83% false-positive rate on a three-class
    fixture (GI-2236 / G-0943-2).

    Each declaration's region runs from its own line to the next declaration's
    (the last one runs to EOF), which is enough to tell "this class uses the
    imported name" from "some other class in the same file does". Files are
    read at most once, and only when a file holds more than one declaration.
    """

    __slots__ = ("_file_to_nodes", "_node_line", "_regions")

    def __init__(self, file_to_nodes: dict[str, list[str]], node_line: dict[str, int]):
        self._file_to_nodes = file_to_nodes
        self._node_line = node_line
        self._regions: dict[str, dict[str, str]] = {}

    def _load(self, path: str) -> dict[str, str]:
        cached = self._regions.get(path)
        if cached is not None:
            return cached
        regions: dict[str, str] = {}
        try:
            if os.path.getsize(path) <= _MENTION_READ_LIMIT:
                lines = Path(path).read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            else:
                lines = []
        except (OSError, ValueError):
            lines = []
        if lines:
            ordered = sorted(
                self._file_to_nodes.get(path, ()),
                key=lambda nid: (self._node_line.get(nid, 0), nid),
            )
            for i, nid in enumerate(ordered):
                start = max(0, (self._node_line.get(nid, 1) or 1) - 1)
                if i + 1 < len(ordered):
                    # Several declarations can share a line — every member of a
                    # one-line object literal does. Give each at least its own
                    # line rather than an empty region it could never match in.
                    end = max(start + 1, (self._node_line.get(ordered[i + 1], 1) or 1) - 1)
                else:
                    end = len(lines)
                regions[nid] = "\n".join(lines[start:end])
        self._regions[path] = regions
        return regions

    def mentioning(self, path: str, names: set[str]) -> list[str]:
        """Node ids in ``path`` whose own source region names one of ``names``."""
        regions = self._load(path)
        pattern = _word_pattern(names)
        if not regions or pattern is None:
            return []
        return [nid for nid, text in regions.items() if pattern.search(text)]

    def names_in(self, path: str, node_id: str, names: set[str]) -> set[str]:
        """Which of ``names`` appear inside one declaration's own region.

        This is how a module-level import picks its endpoint: ``from x import
        SymbolTable`` may reach the builder as the bare module ``x``, and the
        only evidence of WHICH of that module's declarations is meant is the
        importer writing the name in its body.
        """
        text = self._load(path).get(node_id)
        pattern = _word_pattern(names)
        if not text or pattern is None:
            return set()
        return set(pattern.findall(text))


def _word_pattern(names: set[str]) -> Optional[re.Pattern]:
    """Whole-word alternation over ``names``, or None when there is nothing to match."""
    wanted = sorted({n for n in names if n and n.isprintable()})
    if not wanted:
        return None
    return re.compile(r"\b(%s)\b" % "|".join(re.escape(n) for n in wanted))


def _pick_target(
    candidates: list[str],
    src_project: str,
    node_bare: dict[str, str],
    node_line: dict[str, int],
    label: str,
    symbol_hint: Optional[str],
) -> str:
    """Choose one target node deterministically from the resolved candidates."""
    ordered = sorted(candidates)
    same_project = (
        [c for c in ordered if c.startswith(src_project + "::")] if src_project else []
    )
    pool = same_project or ordered
    for want in (symbol_hint, label):
        if not want:
            continue
        for cand in pool:
            if node_bare.get(cand) == want:
                return cand
        low = want.casefold()
        for cand in pool:
            if node_bare.get(cand, "").casefold() == low:
                return cand
    return min(pool, key=lambda c: (node_line.get(c, 0), c))


def _remap_import_edges(
    all_nodes: list[Node],
    all_edges: list[Edge],
    resolver: Optional[ModuleResolver] = None,
    project_roots: Optional[dict[str, str]] = None,
) -> list[Edge]:
    """Remap import edges from file_path → raw_import to node_id → node_id.

    dependencies.py emits Edge(source=file_path, target=raw_import_string).
    Graph nodes use IDs like "project::ClassName".  This function bridges the
    two by resolving both sides.

    Target resolution runs in three tiers, most-evidence-first:

    1. **Path.** ``resolver`` turns the import string into the file it actually
       names (relative specifier, tsconfig alias, package path). If that file
       was scanned, the edge binds inside it — or is dropped when the file
       declares nothing. It is never redirected to a same-named symbol
       somewhere else, which is how ``from codebeacon.graph.build import …``
       came to point at ``SymbolTable.build`` (C-53b).
    2. **Runtime guard.** An import the path tier could not place, but which
       names the language's own stdlib, binds to nothing: four services writing
       ``import java.util.List`` must not turn a domain ``List.java`` into the
       repository's top hub (G-0916-14 / G-0927-11).
    3. **Label.** Otherwise fall back to matching the import's last segment
       against declaration names, as before — this is what keeps barrel files,
       re-exports and alias-free projects resolving.
    """
    # source_file → [node_id, ...]
    file_to_nodes: dict[str, list[str]] = {}
    # label (class/component name) → [node_id, ...]
    label_to_nodes: dict[str, list[str]] = {}
    # casefold(label) → [node_id, ...] for case-insensitive fallback.
    # casefold() (not lower()) is used so non-ASCII labels — CJK, Cyrillic,
    # German ß — round-trip correctly. Mirrors graphify #86109e9.
    label_cf_to_nodes: dict[str, list[str]] = {}
    # node_id → source-file extension (language-family guard), → label
    # (case-collision guard), → declaration name, → line.
    node_ext: dict[str, str] = {}
    node_label: dict[str, str] = {}
    node_bare: dict[str, str] = {}
    node_line: dict[str, int] = {}
    node_ids: set[str] = set()

    for node in all_nodes:
        node_ids.add(node.id)
        file_to_nodes.setdefault(node.source_file, []).append(node.id)
        node_ext[node.id] = Path(node.source_file).suffix.lower() if node.source_file else ""
        node_line[node.id] = node.line or 0
        # A disambiguated node wears a decorated label ("User (admin)"), which no
        # import string will ever spell. Index its plain declaration name too, so
        # a collision-renamed class stays reachable from an import.
        bare = "" if node.type == "route" else _bare_name(node.id)
        node_bare[node.id] = bare
        # A node with a None/empty label (defective extractor output, replayed
        # semantic archive) must not abort the whole build — graphify #1194
        # crashed in exactly this spot via `None.casefold()`.
        if not node.label:
            continue
        node_label[node.id] = node.label
        for key in {node.label, bare}:
            if not key:
                continue
            label_to_nodes.setdefault(key, []).append(node.id)
            label_cf_to_nodes.setdefault(key.casefold(), []).append(node.id)

    mentions = _BodyMentions(file_to_nodes, node_line)

    # Resolve every import string once, and note which (importing file →
    # resolved file) pairs are already described by an edge that names a
    # specific symbol. Extractors emit both spellings of one statement —
    # ``from pkg.mod import Thing`` yields an edge for ``pkg.mod`` AND one for
    # ``pkg.mod.Thing`` — and letting the vaguer one through as well both
    # doubles the edge count and invites a guess about which declaration it
    # meant.
    resolutions: dict[tuple[str, str], tuple[list[str], Optional[str]]] = {}
    symbol_covered: set[tuple[str, str]] = set()
    if resolver is not None:
        for edge in all_edges:
            if edge.relation not in _REMAPPED_RELATIONS:
                continue
            key = (edge.source, edge.target)
            if key not in resolutions:
                resolutions[key] = resolver.resolve(edge.target, edge.source)
            files, hint = resolutions[key]
            if hint:
                for path in files:
                    symbol_covered.add((edge.source, path))

    remapped: list[Edge] = []
    non_import: list[Edge] = []

    for edge in all_edges:
        # Treat re_exports and semantic references the same as imports_from for
        # resolution purposes: all three go from a file_path to a raw name, but
        # we want to preserve the distinct relation in the final graph.
        if edge.relation not in _REMAPPED_RELATIONS:
            non_import.append(edge)
            continue

        # Resolve source: file_path → node_ids in that file. An edge whose
        # source is already a node id (an extractor that knew the declaration)
        # passes straight through instead of being dropped.
        source_ids = file_to_nodes.get(edge.source, [])
        if not source_ids:
            if edge.source in node_ids:
                source_ids = [edge.source]
            else:
                continue

        src_ext = Path(edge.source).suffix.lower() if edge.source else ""
        if not src_ext:
            src_ext = node_ext.get(source_ids[0], "")

        target_label = _import_to_label(edge.target)
        symbol_hint: Optional[str] = None
        target_ids: list[str] = []

        resolved_files: list[str] = []
        if resolver is not None:
            resolved_files, symbol_hint = resolutions.get(
                (edge.source, edge.target), ([], None)
            )

        if resolved_files:
            if symbol_hint is None and any(
                (edge.source, path) in symbol_covered for path in resolved_files
            ):
                # The same statement's symbol-specific edge already covers this.
                continue
            target_ids = sorted({
                nid for path in resolved_files for nid in file_to_nodes.get(path, ())
            })
            if not target_ids:
                # The import names a file we scanned and that file declares
                # nothing. Binding it to a same-named symbol elsewhere is the
                # fabrication this tier exists to prevent — drop it instead.
                continue
        else:
            if is_runtime_import(edge.target, src_ext):
                continue
            # Try exact match first, then case-insensitive fallback so that
            # path aliases like @/components/ui/card → "card" resolve to "Card".
            # The fallback is skipped for very short labels (≤ 2 chars) — two
            # different one-character names are almost always coincidence, not
            # the same symbol, and matching them produced phantom cross-language
            # edges in mixed-language repos. Mirrors graphify #4dce16f.
            target_ids = label_to_nodes.get(target_label, [])
            if not target_ids and len(target_label) > 2 and not target_label.isupper():
                # Skip the casefold fallback for SCREAMING_SNAKE import tokens
                # (CONFIG / PATH / LOGGER): those are module-level constants
                # imported by name, and folding them onto a same-spelled
                # declaration (class Config) fabricates a false god-node hub
                # (graphify #1581).
                #
                # When the fallback does run, PREFER non-all-caps candidates so a
                # lowercase alias ``path`` binds the declaration ``Path`` rather
                # than the constant ``PATH``. But when the ONLY candidates are
                # all-caps we KEEP them — an all-caps label is just as often a
                # legitimate acronym *type* (API / HTTP / URL / PDF) as a module
                # constant, and a blanket isupper() filter silently erased real
                # ``import { API } from './api'`` dependency edges. Never filter
                # to zero.
                cf_candidates = label_cf_to_nodes.get(target_label.casefold(), [])
                non_caps = [
                    tid for tid in cf_candidates if not node_label.get(tid, "").isupper()
                ]
                target_ids = non_caps or cf_candidates
            if not target_ids:
                continue

        # Names that stand for this import inside a declaration's body: the
        # symbol it named, the module's own last segment, and — when the module
        # resolved to a small enough file — the names it declares, since
        # ``from x import a, b`` can reach us as the bare module ``x``.
        names = {target_label}
        if symbol_hint:
            names.add(symbol_hint)
        if len(target_ids) <= _MENTION_NAME_LIMIT:
            names.update(node_bare.get(tid, "") for tid in target_ids)

        # Anchor the edge on the declarations that actually use the name.
        anchors = source_ids
        if len(source_ids) > 1:
            hits = mentions.mentioning(edge.source, names)
            anchors = hits or [
                min(source_ids, key=lambda nid: (node_line.get(nid, 0), nid))
            ]

        for src_id in anchors:
            src_project = src_id.split("::")[0] if "::" in src_id else ""
            this_ext = node_ext.get(src_id, src_ext)
            # Drop candidates from a different language family. A bare-name
            # collision across languages (Python `import time` vs a TS `time`
            # component) must never fabricate an edge — prefer no edge over a
            # cross-family binding (graphify G04).
            candidates = [
                tid for tid in target_ids
                if families_compatible(this_ext, node_ext.get(tid, ""))
            ]
            if not candidates:
                continue
            if len(candidates) > 1 and not symbol_hint:
                # The import named a module, not a symbol. Let the importing
                # declaration's own body say which of that module's names it
                # actually uses, rather than defaulting to whichever happens to
                # be declared first.
                used = mentions.names_in(
                    edge.source, src_id, {node_bare.get(c, "") for c in candidates}
                )
                narrowed = [c for c in candidates if node_bare.get(c, "") in used]
                if narrowed:
                    candidates = narrowed
            target_id = _pick_target(
                candidates, src_project, node_bare, node_line, target_label, symbol_hint
            )
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
        "App\\Models\\User"             → "User"
        "\\App\\Contracts\\Gateway"     → "Gateway"

    PHP namespace separators are folded to ``/`` first. Without that, no PHP
    import ever resolved: ``App\\Models\\User`` was returned verbatim and matched
    no declaration, so every Laravel project in an index had an empty import
    graph (G-0941-11). Folding to ``/`` — rather than adding a third branch —
    also keeps ``.razor``'s dot-separated ``@using`` and the Java package path
    untouched, because a string containing ``/`` takes the path branch.
    """
    if "\\" in raw_import:
        raw_import = raw_import.replace("\\", "/").lstrip("/")
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
        # A node never depends on itself. Self-loops arise when a class names a
        # dependency of its own type, and they distort every degree-based
        # metric while meaning nothing (G-0921-4).
        if edge.source == edge.target:
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
        existing = G.get_edge_data(edge.source, edge.target)
        if existing is None:
            G.add_edge(
                edge.source,
                edge.target,
                relation=edge.relation,
                confidence=edge.confidence,
                confidence_score=edge.confidence_score,
                source_file=edge.source_file,
            )
            continue

        # Duplicate ordered pair: keep the more specific relation and remember
        # the other one under ``also`` instead of overwriting it away.
        current = existing.get("relation", "")
        if current == edge.relation:
            continue
        also = set(existing.get("also", ()))
        if _relation_rank(edge.relation) < _relation_rank(current):
            also.add(current)
            also.discard(edge.relation)
            existing.update(
                relation=edge.relation,
                confidence=edge.confidence,
                confidence_score=edge.confidence_score,
                source_file=edge.source_file,
            )
        else:
            also.add(edge.relation)
        existing["also"] = sorted(also)

    return G


def _relation_rank(relation: str) -> int:
    """0 for relations that name a concrete mechanism, 1 for generic ones."""
    return 0 if relation in _SPECIFIC_RELATIONS else 1


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
