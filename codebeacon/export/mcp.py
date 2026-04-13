"""stdio MCP server for codebeacon.

Exposes the knowledge graph and wiki as MCP tools for AI agents.

Tools:
    beacon_wiki_index      - global wiki index (short token budget)
    beacon_wiki_article    - read a specific wiki article by path
    beacon_query           - search nodes/edges by label substring
    beacon_path            - shortest path between two named nodes
    beacon_blast_radius    - downstream + upstream neighbours of a node
    beacon_routes          - list all routes (optional: filter by project)
    beacon_services        - list all services (optional: filter by project)

Usage:
    codebeacon serve --dir /path/to/.codebeacon
    codebeacon serve  # defaults to .codebeacon in cwd
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from typing import Any


# ── Graph loader ──────────────────────────────────────────────────────────────

class BeaconIndex:
    """Loaded graph + wiki index, built once at startup."""

    def __init__(self, beacon_dir: Path) -> None:
        self.beacon_dir = beacon_dir
        self.wiki_dir = beacon_dir / "wiki"
        self.G = None
        self._label_to_ids: dict[str, list[str]] = {}

    def load(self) -> None:
        import networkx as nx
        import networkx.readwrite.json_graph as nxjson

        beacon_json = self.beacon_dir / "beacon.json"
        if not beacon_json.exists():
            raise FileNotFoundError(
                f"beacon.json not found at {beacon_json}. "
                "Run 'codebeacon scan <path>' first."
            )

        data = json.loads(beacon_json.read_text(encoding="utf-8"))
        self.G = nxjson.node_link_graph(data, directed=True, multigraph=False)

        # Build label → [node_ids] lookup (case-insensitive key)
        for node_id, node_data in self.G.nodes(data=True):
            label = node_data.get("label", node_id).lower()
            self._label_to_ids.setdefault(label, []).append(node_id)

    def find_node_ids(self, name: str) -> list[str]:
        """Return node IDs whose label contains `name` (case-insensitive)."""
        name_lower = name.lower()
        results: list[str] = []
        for label, ids in self._label_to_ids.items():
            if name_lower in label:
                results.extend(ids)
        return results

    def node_summary(self, node_id: str) -> dict[str, Any]:
        """Return a compact dict for a single node."""
        data = self.G.nodes[node_id]
        return {
            "id": node_id,
            "label": data.get("label", node_id),
            "type": data.get("type", ""),
            "project": data.get("project", ""),
            "source_file": data.get("source_file", ""),
            "framework": data.get("framework", ""),
        }


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_beacon_wiki_index(idx: BeaconIndex, _args: dict) -> str:
    """Read the global wiki index."""
    index_md = idx.wiki_dir / "index.md"
    if index_md.exists():
        return index_md.read_text(encoding="utf-8")
    return "_No wiki index found. Run 'codebeacon scan' to generate._"


def tool_beacon_wiki_article(idx: BeaconIndex, args: dict) -> str:
    """Read a wiki article by relative path (e.g. 'api-server/services/UserService.md').

    Args:
        path: relative path under wiki/ dir
    """
    rel = args.get("path", "").lstrip("/")
    if not rel:
        return "Error: 'path' argument required."
    target = idx.wiki_dir / rel
    # Security: ensure we stay inside wiki_dir
    try:
        target.resolve().relative_to(idx.wiki_dir.resolve())
    except ValueError:
        return "Error: path escapes wiki directory."
    if not target.exists():
        return f"Article not found: {rel}"
    return target.read_text(encoding="utf-8")


def tool_beacon_query(idx: BeaconIndex, args: dict) -> str:
    """Search nodes by label substring.

    Args:
        term: search term (case-insensitive substring match)
        limit: max results (default 20)
    """
    if idx.G is None:
        return "Graph not loaded."
    term = args.get("term", "")
    limit = int(args.get("limit", 20))
    if not term:
        return "Error: 'term' argument required."

    node_ids = idx.find_node_ids(term)[:limit]
    if not node_ids:
        return f"No nodes matching '{term}'."

    lines = [f"## Nodes matching '{term}' ({len(node_ids)} found)\n"]
    for nid in node_ids:
        s = idx.node_summary(nid)
        lines.append(f"- **{s['label']}** ({s['type']}) — {s['project']} — `{s['source_file']}`")

        # Immediate edges
        out_edges = [
            f"  → {idx.G.nodes[t].get('label', t)} [{d.get('relation','')}]"
            for _, t, d in idx.G.out_edges(nid, data=True)
        ][:5]
        in_edges = [
            f"  ← {idx.G.nodes[s].get('label', s)} [{d.get('relation','')}]"
            for s, _, d in idx.G.in_edges(nid, data=True)
        ][:5]
        lines.extend(out_edges + in_edges)

    return "\n".join(lines)


def tool_beacon_path(idx: BeaconIndex, args: dict) -> str:
    """Find shortest path between two nodes by label.

    Args:
        source: source node label (substring match)
        target: target node label (substring match)
    """
    import networkx as nx

    if idx.G is None:
        return "Graph not loaded."
    source = args.get("source", "")
    target = args.get("target", "")
    if not source or not target:
        return "Error: 'source' and 'target' arguments required."

    src_ids = idx.find_node_ids(source)
    tgt_ids = idx.find_node_ids(target)
    if not src_ids:
        return f"No node matching source '{source}'."
    if not tgt_ids:
        return f"No node matching target '{target}'."

    # Try all combinations, return first found
    for sid in src_ids[:3]:
        for tid in tgt_ids[:3]:
            try:
                path = nx.shortest_path(idx.G, sid, tid)
                labels = [idx.G.nodes[n].get("label", n) for n in path]
                edges = []
                for i in range(len(path) - 1):
                    e = idx.G.edges[path[i], path[i + 1]]
                    edges.append(e.get("relation", "→"))
                # Interleave labels and relations
                parts = [labels[0]]
                for rel, lbl in zip(edges, labels[1:]):
                    parts.append(f" --[{rel}]--> {lbl}")
                return f"## Path ({len(path)} hops)\n" + "".join(parts)
            except nx.NetworkXNoPath:
                continue
            except nx.NodeNotFound:
                continue

    return f"No path found between '{source}' and '{target}'."


def tool_beacon_blast_radius(idx: BeaconIndex, args: dict) -> str:
    """Show blast radius: downstream + upstream neighbours of a node.

    Args:
        node: node label (substring match)
        depth: max traversal depth (default 2)
    """
    import networkx as nx

    if idx.G is None:
        return "Graph not loaded."
    node_name = args.get("node", "")
    depth = int(args.get("depth", 2))
    if not node_name:
        return "Error: 'node' argument required."

    ids = idx.find_node_ids(node_name)
    if not ids:
        return f"No node matching '{node_name}'."

    nid = ids[0]
    label = idx.G.nodes[nid].get("label", nid)

    # Downstream (descendants)
    downstream = set()
    frontier = {nid}
    for _ in range(depth):
        next_frontier = set()
        for n in frontier:
            for succ in idx.G.successors(n):
                if succ not in downstream and succ != nid:
                    downstream.add(succ)
                    next_frontier.add(succ)
        frontier = next_frontier

    # Upstream (immediate callers only — one level)
    upstream = set(idx.G.predecessors(nid))
    upstream.discard(nid)

    lines = [f"## Blast Radius: {label}\n"]
    lines.append(f"**Upstream callers** ({len(upstream)}):")
    for u in sorted(upstream, key=lambda n: idx.G.nodes[n].get("label", n)):
        s = idx.node_summary(u)
        lines.append(f"- {s['label']} ({s['type']}) — {s['project']}")

    lines.append(f"\n**Downstream affected** (depth={depth}, {len(downstream)} nodes):")
    for d in sorted(downstream, key=lambda n: idx.G.nodes[n].get("label", n)):
        s = idx.node_summary(d)
        lines.append(f"- {s['label']} ({s['type']}) — {s['project']}")

    if not upstream and not downstream:
        lines.append("_No connections found._")

    return "\n".join(lines)


def tool_beacon_routes(idx: BeaconIndex, args: dict) -> str:
    """List all routes, optionally filtered by project.

    Args:
        project: filter by project name (optional)
        limit: max results (default 50)
    """
    if idx.G is None:
        return "Graph not loaded."
    project_filter = args.get("project", "").lower()
    limit = int(args.get("limit", 50))

    routes = []
    for nid, data in idx.G.nodes(data=True):
        if data.get("type") != "route":
            continue
        proj = data.get("project", "")
        if project_filter and project_filter not in proj.lower():
            continue
        routes.append({
            "method": data.get("method", ""),
            "path": data.get("path", ""),
            "handler": data.get("label", ""),
            "project": proj,
            "framework": data.get("framework", ""),
        })

    routes.sort(key=lambda r: (r["project"], r["method"], r["path"]))
    routes = routes[:limit]

    if not routes:
        return "No routes found."

    lines = [f"## Routes ({len(routes)})\n"]
    lines.append(f"{'Method':<8} {'Path':<40} {'Handler':<30} {'Project'}")
    lines.append("-" * 90)
    for r in routes:
        lines.append(
            f"{r['method']:<8} {r['path']:<40} {r['handler']:<30} {r['project']}"
        )
    return "\n".join(lines)


def tool_beacon_services(idx: BeaconIndex, args: dict) -> str:
    """List all services/classes, optionally filtered by project.

    Args:
        project: filter by project name (optional)
        limit: max results (default 50)
    """
    if idx.G is None:
        return "Graph not loaded."
    project_filter = args.get("project", "").lower()
    limit = int(args.get("limit", 50))

    services = []
    for nid, data in idx.G.nodes(data=True):
        if data.get("type") not in ("class", "service"):
            continue
        proj = data.get("project", "")
        if project_filter and project_filter not in proj.lower():
            continue
        services.append({
            "label": data.get("label", nid),
            "type": data.get("type", ""),
            "project": proj,
            "framework": data.get("framework", ""),
            "source_file": data.get("source_file", ""),
            "annotations": data.get("annotations", []),
        })

    services.sort(key=lambda s: (s["project"], s["label"]))
    services = services[:limit]

    if not services:
        return "No services found."

    lines = [f"## Services ({len(services)})\n"]
    for s in services:
        annots = ", ".join(s["annotations"][:3]) if s["annotations"] else ""
        suffix = f"  [{annots}]" if annots else ""
        lines.append(f"- **{s['label']}** ({s['project']}){suffix}  `{s['source_file']}`")
    return "\n".join(lines)


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOLS = {
    "beacon_wiki_index": {
        "fn": tool_beacon_wiki_index,
        "description": "Return the global wiki index (short overview of all projects and node counts).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "beacon_wiki_article": {
        "fn": tool_beacon_wiki_article,
        "description": "Read a specific wiki article by its relative path under wiki/ (e.g. 'api-server/services/UserService.md').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path under wiki/ directory"},
            },
            "required": ["path"],
        },
    },
    "beacon_query": {
        "fn": tool_beacon_query,
        "description": "Search graph nodes by label substring. Returns matching nodes with their edges.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "term": {"type": "string", "description": "Search term (case-insensitive)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": ["term"],
        },
    },
    "beacon_path": {
        "fn": tool_beacon_path,
        "description": "Find the shortest dependency path between two nodes by label.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source node label"},
                "target": {"type": "string", "description": "Target node label"},
            },
            "required": ["source", "target"],
        },
    },
    "beacon_blast_radius": {
        "fn": tool_beacon_blast_radius,
        "description": "Show upstream callers and downstream affected nodes for a given node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node": {"type": "string", "description": "Node label to analyze"},
                "depth": {"type": "integer", "description": "Downstream traversal depth (default 2)"},
            },
            "required": ["node"],
        },
    },
    "beacon_routes": {
        "fn": tool_beacon_routes,
        "description": "List all HTTP routes in the knowledge graph, optionally filtered by project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter by project name (optional)"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
            "required": [],
        },
    },
    "beacon_services": {
        "fn": tool_beacon_services,
        "description": "List all service/class nodes in the knowledge graph, optionally filtered by project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Filter by project name (optional)"},
                "limit": {"type": "integer", "description": "Max results (default 50)"},
            },
            "required": [],
        },
    },
}


# ── JSON-RPC 2.0 / MCP protocol ───────────────────────────────────────────────

def _write(obj: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _dispatch(idx: BeaconIndex, message: dict) -> dict | None:
    """Dispatch a single JSON-RPC 2.0 message; return response dict or None."""
    req_id = message.get("id")
    method = message.get("method", "")
    params = message.get("params") or {}

    # Notifications (no id) — no response required
    if req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codebeacon", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        tools_list = [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"],
            }
            for name, info in TOOLS.items()
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}

        if tool_name not in TOOLS:
            return _error(req_id, -32601, f"Unknown tool: {tool_name}")

        try:
            result_text = TOOLS[tool_name]["fn"](idx, tool_args)
        except Exception as exc:
            print(f"[codebeacon-mcp] error in {tool_name}: {exc}", file=sys.stderr)
            return _error(req_id, -32603, str(exc))

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
                "isError": False,
            },
        }

    # Unknown method
    return _error(req_id, -32601, f"Method not found: {method}")


def serve(beacon_dir: str | Path) -> None:
    """Start the stdio MCP server. Blocks until stdin is closed."""
    beacon_dir = Path(beacon_dir)
    idx = BeaconIndex(beacon_dir)

    try:
        idx.load()
    except FileNotFoundError as e:
        print(f"[codebeacon-mcp] {e}", file=sys.stderr)
        # Still start server so MCP client can connect — tools will explain the error

    print(f"[codebeacon-mcp] serving from {beacon_dir}", file=sys.stderr)

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError as e:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}})
            continue

        response = _dispatch(idx, message)
        if response is not None:
            _write(response)
