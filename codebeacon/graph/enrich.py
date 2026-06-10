"""Graph enrichment: HTTP/IPC cross-service edges + shared DB entity edges.

Four enrichment passes run AFTER the base graph is built by build.py:
  1. enrich_http_api()      — frontend URL calls → backend routes (calls_api edges)
  2. enrich_shared_db()     — same DAO/Entity across services (shares_db_entity edges)
  3. enrich_ipc_invoke()    — frontend invoke("cmd") → IPC command routes (invokes_command edges)
     Covers Tauri, Electron ipcRenderer, and any invoke()-pattern IPC framework.
  4. promote_confirmed_calls() — promote cross-file ``calls`` edges from INFERRED
     to EXTRACTED when the caller's source file imports the callee's file.
     Eliminates a class of false-uncertainty in code that uses explicit imports.
"""

from __future__ import annotations

import re
from pathlib import Path

import networkx as nx


# Regexes to extract API URLs from frontend source files
_API_URL_RES = [
    re.compile(r'''(?:fetch|invoke|\$fetch)\s*\(\s*[`"']([^`"'$]+)[`"']'''),
    # Support TypeScript generics: axios.get<T>('/url'), api.get<PageResponse<T>>('/url')
    re.compile(r'''axios\.\w+\b[^`"']*[`"']([^`"'$]+)[`"']'''),
    re.compile(r'''(?:api|http|client|instance|request)\.\w+\b[^`"']*[`"']([^`"'$]+)[`"']'''),
    re.compile(r'''url\s*[:=]\s*[`"']([^`"'$]+)[`"']'''),
    re.compile(r'''["'](/api/[^"'`\s]+)["'`]'''),
    # Rust reqwest: format!("{}/api/...", base_url)
    re.compile(r'''"\{\}(/api/[^"'\s]+)'''),
]
_URL_LIKE = re.compile(r'^/[a-zA-Z]')


def _extract_api_urls(source_file: str) -> list[str]:
    """Scan a source file for HTTP API URL patterns."""
    try:
        content = Path(source_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    urls: set[str] = set()
    for pat in _API_URL_RES:
        for m in pat.finditer(content):
            url = m.group(1).split("?")[0].split("#")[0].strip()
            if _URL_LIKE.match(url):
                urls.add(url)
    # Sorted so edge insertion order — and therefore beacon.json — is
    # deterministic across runs. Mirrors graphify #1090.
    return sorted(urls)


def enrich_http_api(G: nx.DiGraph) -> int:
    """Add calls_api edges where frontend URL patterns match backend route paths.

    Strategy:
    - Collect all 'route' nodes with their path attribute
    - For each frontend component, scan its source file for API URL patterns
    - Match URLs to routes: exact first, then parameterized

    Returns:
        Number of new calls_api edges added.
    """
    added = 0

    # Build route lookup: normalized_path → [(node_id, project), ...].
    # A list, not a single tuple — in a monorepo two services legitimately
    # expose the same path (gateway + upstream both serving /api/users), and
    # a last-writer-wins dict silently dropped all but one of them.
    route_map: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") != "route":
            continue
        path = data.get("path", "")
        if path:
            proj = data.get("project", "")
            route_map.setdefault(_normalize_path(path), []).append((node_id, proj))

    if not route_map:
        return 0

    # Find nodes that may call external APIs and scan their source files
    for node_id, data in G.nodes(data=True):
        if data.get("type") not in ("component", "class", "route", "service"):
            continue
        src_proj = data.get("project", "")

        src_file = data.get("source_file", "")
        if not src_file:
            continue

        # Use metadata api_calls if set, otherwise scan file
        api_calls = data.get("api_calls", [])
        if not api_calls:
            api_calls = _extract_api_urls(src_file)

        for url in api_calls:
            normalized = _normalize_path(url)

            # Exact match
            if normalized in route_map:
                for target_id, target_proj in route_map[normalized]:
                    # Only create cross-project edges (skip same-project)
                    if target_proj == src_proj:
                        continue
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
            matched = False
            for route_path, candidates in route_map.items():
                for route_node_id, route_proj in candidates:
                    if route_proj == src_proj:
                        continue
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
                        matched = True
                        break
                if matched:
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
                if G.has_edge(src_rep, tgt_rep):
                    # Edge already exists (e.g. imports relation) — annotate it
                    # rather than silently dropping the shared-entity relationship.
                    existing = G[src_rep][tgt_rep]
                    if "shared_entities" not in existing:
                        existing["shared_entities"] = []
                    if entity_id not in existing["shared_entities"]:
                        existing["shared_entities"].append(entity_id)
                else:
                    G.add_edge(
                        src_rep, tgt_rep,
                        relation="shares_db_entity",
                        confidence="INFERRED",
                        confidence_score=0.9,
                        source_file=entity_src,
                        shared_entity=entity_id,
                        shared_entities=[entity_id],
                    )
                    added += 1

    return added


# ── IPC invoke enrichment (Tauri, Electron, etc.) ────────────────────────────

# Regexes for IPC invoke patterns across desktop/hybrid frameworks:
#   Tauri:    invoke("cmd")  invoke<T>("cmd")
#   Electron: ipcRenderer.invoke("cmd")  ipcRenderer.send("cmd")
_IPC_INVOKE_RES = [
    re.compile(r"""invoke\s*(?:<[^>]*>)?\s*\(\s*["'](\w+)["']"""),
    re.compile(r"""ipcRenderer\.(?:invoke|send)\s*\(\s*["']([^"']+)["']"""),
]


def _extract_ipc_commands(source_file: str) -> list[str]:
    """Extract IPC invoke/send command names from a frontend source file."""
    try:
        content = Path(source_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    commands: set[str] = set()
    for pat in _IPC_INVOKE_RES:
        for m in pat.finditer(content):
            commands.add(m.group(1))
    # Sorted for deterministic edge order (graphify #1090).
    return sorted(commands)


def enrich_ipc_invoke(G: nx.DiGraph) -> int:
    """Add invokes_command edges: frontend invoke("cmd") → backend IPC command route.

    Framework-agnostic — works with any route whose method is INVOKE,
    regardless of backend framework (Tauri, Electron, etc.).

    Strategy:
    - Collect all 'route' nodes where method == "INVOKE"
    - Extract the command name from the route handler
    - For each frontend component, scan for invoke()/ipcRenderer.invoke() calls
    - Match command names across projects

    Returns:
        Number of new invokes_command edges added.
    """
    added = 0

    # Build command lookup: handler_name → (node_id, project)
    cmd_map: dict[str, tuple[str, str]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") != "route":
            continue
        method = data.get("method", "")
        if method != "INVOKE":
            continue
        handler = data.get("label", "").split(" ")[0]  # "handler [INVOKE /...]" → "handler"
        if handler:
            cmd_map[handler] = (node_id, data.get("project", ""))

    if not cmd_map:
        return 0

    # Find frontend component nodes and scan for IPC calls
    for node_id, data in G.nodes(data=True):
        if data.get("type") != "component":
            continue
        src_proj = data.get("project", "")
        src_file = data.get("source_file", "")
        if not src_file:
            continue

        commands = _extract_ipc_commands(src_file)
        for cmd in commands:
            if cmd not in cmd_map:
                continue
            target_id, target_proj = cmd_map[cmd]
            if target_proj == src_proj:
                continue
            if not G.has_edge(node_id, target_id):
                G.add_edge(
                    node_id, target_id,
                    relation="invokes_command",
                    confidence="EXTRACTED",
                    confidence_score=1.0,
                    source_file=src_file,
                )
                added += 1

    return added


# ── INFERRED→EXTRACTED promotion ──────────────────────────────────────────────

def promote_confirmed_calls(G: nx.DiGraph) -> int:
    """Promote cross-file ``calls`` edges from INFERRED to EXTRACTED.

    Heuristic: if the caller's source file has an outgoing ``imports`` or
    ``imports_from`` edge that resolves into the callee's source file, then the
    binding is provably correct and the call is no longer "inferred". This
    catches a large class of false-uncertainty in CommonJS / TypeScript code
    where every cross-file call defaults to INFERRED because the AST walker
    only sees a bare name at the call site.

    Returns:
        Number of edges promoted.
    """
    if G.number_of_edges() == 0:
        return 0

    # caller_file → set(target_files reachable via an EXTRACTED import edge)
    proven_targets: dict[str, set[str]] = {}
    for src, tgt, edata in G.edges(data=True):
        rel = edata.get("relation", "")
        if rel not in ("imports", "imports_from"):
            continue
        src_file = G.nodes[src].get("source_file", "")
        tgt_file = G.nodes[tgt].get("source_file", "")
        if not src_file or not tgt_file:
            continue
        proven_targets.setdefault(src_file, set()).add(tgt_file)

    if not proven_targets:
        return 0

    promoted = 0
    for src, tgt, edata in G.edges(data=True):
        if edata.get("relation") != "calls":
            continue
        if edata.get("confidence") != "INFERRED":
            continue
        src_file = G.nodes[src].get("source_file", "")
        tgt_file = G.nodes[tgt].get("source_file", "")
        if not src_file or not tgt_file or src_file == tgt_file:
            continue
        if tgt_file in proven_targets.get(src_file, ()):
            edata["confidence"] = "EXTRACTED"
            # Lift the score to match other EXTRACTED edges (1.0 is the
            # convention used by dependencies.py and the http_api enricher).
            edata["confidence_score"] = 1.0
            promoted += 1

    return promoted


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
