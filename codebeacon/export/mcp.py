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
    beacon_knowledge       - search knowledge notes / list notes linked to a node
    beacon_pr_context      - wiki articles covering a set of changed files

Every tool accepts ``token_budget`` (default 2000 tokens) and announces any
trim. A tool that fails returns ``isError: true`` in a normal MCP result — see
:class:`ToolError` — rather than a JSON-RPC error the client may swallow.

Usage:
    codebeacon serve --dir /path/to/.codebeacon
    codebeacon serve  # defaults to .codebeacon in cwd
"""

from __future__ import annotations

import functools
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

from codebeacon import __version__
from codebeacon.common.safety import defang_model_tokens, sanitize_label


# ── Error contract ────────────────────────────────────────────────────────────

class ToolError(Exception):
    """A recoverable tool-level failure.

    Per the MCP spec a *tool* that fails still produces a successful JSON-RPC
    response carrying ``isError: true``; only protocol problems (unknown
    method, malformed request) are JSON-RPC errors. Tools raise this instead of
    returning error prose so the flag and the message can never disagree —
    returning ``"Graph not loaded."`` with ``isError: False`` told every calling
    agent the lookup had succeeded.
    """


# ── Output budget ─────────────────────────────────────────────────────────────
#
# One MCP call used to be able to emit ~214k tokens (measured: beacon_query with
# limit=10000 over a 5,236-node graph). Every tool's text therefore leaves
# through _apply_budget. A budget of 0 disables trimming, which is what a human
# at the CLI wants: they asked for N rows and should get N rows.

DEFAULT_TOKEN_BUDGET = 2000
CHARS_PER_TOKEN = 4
_NOTICE_RESERVE = 240  # chars held back so the notice itself fits the budget
MAX_LIMIT = 1000       # ceiling on a model-supplied `limit`
MAX_DEPTH = 10         # ceiling on a model-supplied traversal `depth`


def _apply_budget(text: str, budget_tokens: int) -> str:
    """Trim `text` to roughly `budget_tokens` tokens, on a line boundary.

    Text that already fits comes back byte-identical — a small result must not
    grow a notice it does not need. Truncation is always announced in the
    payload the model reads, never silent.
    """
    if budget_tokens <= 0 or len(text) <= budget_tokens * CHARS_PER_TOKEN:
        return text

    max_chars = budget_tokens * CHARS_PER_TOKEN
    lines = text.split("\n")
    room = max(0, max_chars - _NOTICE_RESERVE)
    kept: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > room:
            break
        kept.append(line)
        used += len(line) + 1
    if not kept:
        # A single line wider than the whole budget (a minified file, say):
        # hard-cut it rather than answering with nothing but the notice.
        kept = [lines[0][:room] + " …"]

    notice = (
        f"_Truncated to {len(kept)} of {len(lines)} lines (~{budget_tokens} token "
        f"budget). Narrow the request — filter by `project`, use a more specific "
        f"term, or lower `limit` — or raise `token_budget`._"
    )
    return "\n".join([notice, ""] + kept)


def _int_arg(args: dict, name: str, default: int, *, minimum: int = 0,
             maximum: int | None = None) -> int:
    """Read an integer argument, clamped to [minimum, maximum].

    A model can send ``"20"``, ``20.0`` or ``"twenty"``; the first two are
    accepted and the third becomes a tool error rather than a protocol error.
    """
    raw = args.get(name, default)
    if raw is None or raw == "":
        raw = default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"'{name}' must be an integer, got {raw!r}.") from None
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _tool(fn):
    """Apply the two output-side invariants to a tool implementation.

    Every string an agent reads leaves through here, so model-control tokens are
    neutralised and the token budget is honoured regardless of which tool ran or
    who called it (MCP dispatch, or `codebeacon query`/`path` on the CLI).
    """
    @functools.wraps(fn)
    def wrapper(idx: "BeaconIndex", args: dict | None = None) -> str:
        args = args or {}
        budget = _int_arg(args, "token_budget", DEFAULT_TOKEN_BUDGET,
                          minimum=0, maximum=1_000_000)
        return _apply_budget(defang_model_tokens(fn(idx, args)), budget)
    return wrapper


def _require_graph(idx: "BeaconIndex") -> None:
    """Raise the *actionable* load failure, not a flat 'Graph not loaded.'.

    ``serve()`` deliberately starts without a graph so tools can explain the
    problem; that explanation (missing beacon.json, or a corrupt one backed up
    with a .corrupt suffix) previously reached stderr only, where no agent sees
    it.
    """
    if idx.G is not None:
        return
    msg = idx.load_error or f"No graph loaded from {idx.beacon_dir}."
    if "codebeacon scan" not in msg:
        msg += " Run `codebeacon scan <path>` to build it."
    raise ToolError(msg)


def _normalize_term(name: str) -> str:
    """Casefold + NFC-normalise a search term and strip framing punctuation.

    ``"`'`` are intentionally included so quoted queries (which agents often
    generate by reflex) hit the same label. NFC-normalising here and in load()
    is what lets an NFD "Auditoría" meet its NFC twin (#1338).
    """
    return unicodedata.normalize("NFC", name).casefold().strip(".,?!:;()[]{}<>\"'`")


# ── Graph loader ──────────────────────────────────────────────────────────────

class BeaconIndex:
    """Loaded graph + wiki index, built once at startup."""

    def __init__(self, beacon_dir: Path) -> None:
        self.beacon_dir = beacon_dir
        self.wiki_dir = beacon_dir / "wiki"
        self.G = None
        self.load_error: str | None = None
        self._label_to_ids: dict[str, list[str]] = {}
        self._id_to_ids: dict[str, list[str]] = {}

    def load(self) -> None:
        from ..graph.write import load_beacon

        beacon_json = self.beacon_dir / "beacon.json"
        if not beacon_json.exists():
            self.load_error = (
                f"beacon.json not found at {beacon_json}. "
                "Run 'codebeacon scan <path>' first."
            )
            raise FileNotFoundError(self.load_error)

        # Reuse read_beacon's edge-key compat shim so the MCP server stays
        # correct across the NetworkX 3.6 links→edges default flip.
        try:
            self.G, _meta = load_beacon(beacon_json)
        except Exception as exc:
            # Remember why, so the tools can hand the agent the rebuild hint
            # (load_beacon backs a corrupt file up and says so) instead of the
            # flat "Graph not loaded." every tool used to answer.
            self.load_error = str(exc)
            raise

        self._index_nodes()
        self.load_error = None

    def _index_nodes(self) -> None:
        """(Re)build the label and node-id lookups from ``self.G``.

        Keys are casefolded — not lower()ed — so non-ASCII labels (CJK,
        Cyrillic, German ß, Turkish i/İ, Greek σ/ς) round-trip correctly and
        users searching in their own language get hits. Mirrors graphify's
        #020cca2 / #c7a05d6 query-term hardening.

        NFC-normalise first: on macOS (APFS/HFS+) filenames — and labels derived
        from them — arrive in Unicode NFD, while a label stored in beacon.json
        may be NFC. casefold() does not normalise form, so an NFD "Auditoría"
        would never equal its NFC twin. Normalising both the stored key (here)
        and the query term (_normalize_term) is what makes them meet. (#1338)
        """
        self._label_to_ids = {}
        self._id_to_ids = {}
        for node_id, node_data in self.G.nodes(data=True):
            label = unicodedata.normalize("NFC", node_data.get("label", node_id)).casefold()
            self._label_to_ids.setdefault(label, []).append(node_id)
            self._id_to_ids.setdefault(_normalize_term(node_id), []).append(node_id)

    @classmethod
    def from_graph(cls, G, beacon_dir: Path | str = ".codebeacon") -> "BeaconIndex":
        """Build an index over an in-memory graph, skipping beacon.json.

        Same indexes as :meth:`load`, so callers never have to hand-roll them
        and drift from what the resolver expects.
        """
        idx = cls(Path(beacon_dir))
        idx.G = G
        idx._index_nodes()
        return idx

    # ── Name resolution ──────────────────────────────────────────────────────
    #
    # ONE policy, four tiers, used by every tool that turns a name into a node.
    # Before this, blast_radius took ids[0] of a substring scan in graph-build
    # order, so asking about "User" answered about "UserServiceImpl" whenever
    # the impl happened to be built first — a confident answer about the wrong
    # node. Tiers are consulted best-first and a tier is skipped only when it is
    # empty; within a tier the order is (label, node_id) so insertion order can
    # never decide the answer.

    _TIER_EXACT_LABEL = 0
    _TIER_EXACT_ID = 1
    _TIER_PREFIX = 2
    _TIER_SUBSTRING = 3

    def _display_label(self, node_id: str) -> str:
        return self.G.nodes[node_id].get("label", node_id)

    def _ranked(self, name: str) -> list[tuple[int, str, str]]:
        """(tier, label, node_id) for every node matching `name`, best first."""
        term = _normalize_term(name)
        if not term or self.G is None:
            return []

        best: dict[str, int] = {}

        def _offer(node_id: str, tier: int) -> None:
            if node_id not in best or tier < best[node_id]:
                best[node_id] = tier

        for label_cf, ids in self._label_to_ids.items():
            if label_cf == term:
                tier = self._TIER_EXACT_LABEL
            elif label_cf.startswith(term):
                tier = self._TIER_PREFIX
            elif term in label_cf:
                tier = self._TIER_SUBSTRING
            else:
                continue
            for nid in ids:
                _offer(nid, tier)

        # An id-exact hit ranks above any prefix/substring label hit: an agent
        # that pasted back a node id from a previous answer means that node.
        for nid in self._id_to_ids.get(term, ()):
            _offer(nid, self._TIER_EXACT_ID)

        return sorted((tier, self._display_label(nid), nid) for nid, tier in best.items())

    def find_node_ids(self, name: str) -> list[str]:
        """Return node IDs whose label contains `name` (case-insensitive).

        Every match, most relevant first, so that a caller's ``limit`` (or the
        token budget) keeps the best rows rather than an arbitrary prefix of
        build order. Trailing/leading punctuation is stripped from the search
        term so natural queries like ``User?``, ``getUser()``, ``OrderService:``
        still match labels that don't carry the punctuation (graphify #978).
        """
        return [nid for _tier, _label, nid in self._ranked(name)]

    def resolve(self, name: str, *, limit: int | None = None) -> list[str]:
        """Resolve a name to the node IDs of its BEST matching tier.

        The shared policy for every tool (and mirrored by the CLI): an exact
        label match wins outright; failing that an exact node-id match; failing
        that a prefix match; failing that a substring match. Only the best
        non-empty tier is returned, so a tool that must pick one node picks from
        genuine peers, and more than one result means genuine ambiguity worth
        reporting to the caller rather than resolving by coin-flip.
        """
        ranked = self._ranked(name)
        if not ranked:
            return []
        best_tier = ranked[0][0]
        ids = [nid for tier, _label, nid in ranked if tier == best_tier]
        return ids[:limit] if limit else ids

    def node_summary(self, node_id: str) -> dict[str, Any]:
        """Return a compact dict for a single node.

        All free-text fields are run through :func:`sanitize_label` so that
        control characters from source files cannot bleed into MCP text output
        consumed by an LLM agent.
        """
        data = self.G.nodes[node_id]
        return {
            "id": sanitize_label(node_id),
            "label": sanitize_label(data.get("label", node_id)),
            "type": sanitize_label(data.get("type", "")),
            "project": sanitize_label(data.get("project", "")),
            "source_file": sanitize_label(data.get("source_file", "")),
            "framework": sanitize_label(data.get("framework", "")),
        }


# ── Tool implementations ──────────────────────────────────────────────────────

@_tool
def tool_beacon_wiki_index(idx: BeaconIndex, _args: dict) -> str:
    """Read the global wiki index."""
    index_md = idx.wiki_dir / "index.md"
    if not index_md.exists():
        raise ToolError(
            f"No wiki index at {index_md}. Run `codebeacon scan <path>` to generate it."
        )
    return index_md.read_text(encoding="utf-8")


@_tool
def tool_beacon_wiki_article(idx: BeaconIndex, args: dict) -> str:
    """Read a wiki article by relative path (e.g. 'api-server/services/UserService.md').

    Args:
        path: relative path under wiki/ dir
    """
    rel = str(args.get("path", "")).lstrip("/")
    if not rel:
        raise ToolError("'path' argument required.")
    target = idx.wiki_dir / rel
    # Security: ensure we stay inside wiki_dir
    try:
        target.resolve().relative_to(idx.wiki_dir.resolve())
    except ValueError:
        raise ToolError(f"Path escapes the wiki directory: {rel}") from None
    if not target.exists():
        raise ToolError(
            f"Article not found: {rel}. Call beacon_wiki_index for the list of articles."
        )
    return target.read_text(encoding="utf-8")


@_tool
def tool_beacon_query(idx: BeaconIndex, args: dict) -> str:
    """Search nodes by label substring.

    Args:
        term: search term (case-insensitive substring match)
        limit: max results (default 20, capped at MAX_LIMIT)
        token_budget: max tokens of output (default 2000; 0 = unlimited)
    """
    _require_graph(idx)
    term = str(args.get("term", ""))
    limit = _int_arg(args, "limit", 20, minimum=1, maximum=MAX_LIMIT)
    if not term:
        raise ToolError("'term' argument required.")

    matches = idx.find_node_ids(term)
    node_ids = matches[:limit]
    if not node_ids:
        return f"No nodes matching '{sanitize_label(term)}'."

    # Report the true total, not the truncated one: an agent told "(20 found)"
    # when 137 matched has no reason to narrow its search.
    header = (
        f"({len(matches)} found)" if len(node_ids) == len(matches)
        else f"(showing {len(node_ids)} of {len(matches)} — raise `limit` or narrow the term)"
    )
    lines = [f"## Nodes matching '{sanitize_label(term)}' {header}\n"]
    for nid in node_ids:
        s = idx.node_summary(nid)
        lines.append(f"- **{s['label']}** ({s['type']}) — {s['project']} — `{s['source_file']}`")

        # Immediate edges
        out_edges = [
            f"  → {sanitize_label(idx.G.nodes[t].get('label', t))} [{sanitize_label(d.get('relation',''))}]"
            for _, t, d in idx.G.out_edges(nid, data=True)
        ][:5]
        in_edges = [
            f"  ← {sanitize_label(idx.G.nodes[s].get('label', s))} [{sanitize_label(d.get('relation',''))}]"
            for s, _, d in idx.G.in_edges(nid, data=True)
        ][:5]
        lines.extend(out_edges + in_edges)

    return "\n".join(lines)


@_tool
def tool_beacon_path(idx: BeaconIndex, args: dict) -> str:
    """Find shortest path between two nodes by label.

    Args:
        source: source node label (resolved by :meth:`BeaconIndex.resolve`)
        target: target node label (resolved by :meth:`BeaconIndex.resolve`)
        token_budget: max tokens of output (default 2000; 0 = unlimited)
    """
    import networkx as nx

    _require_graph(idx)
    source = str(args.get("source", ""))
    target = str(args.get("target", ""))
    if not source or not target:
        raise ToolError("'source' and 'target' arguments required.")

    src_ids = idx.resolve(source)
    tgt_ids = idx.resolve(target)
    if not src_ids:
        return f"No node matching source '{sanitize_label(source)}'."
    if not tgt_ids:
        return f"No node matching target '{sanitize_label(target)}'."

    # Try all combinations, return first found
    for sid in src_ids[:3]:
        for tid in tgt_ids[:3]:
            try:
                path = nx.shortest_path(idx.G, sid, tid)
                labels = [sanitize_label(idx.G.nodes[n].get("label", n)) for n in path]
                edges = []
                for i in range(len(path) - 1):
                    e = idx.G.edges[path[i], path[i + 1]]
                    edges.append(sanitize_label(e.get("relation", "→")))
                # Interleave labels and relations
                parts = [labels[0]]
                for rel, lbl in zip(edges, labels[1:]):
                    parts.append(f" --[{rel}]--> {lbl}")
                head = f"## Path ({len(path)} hops)\n" + "".join(parts)
                return head + _ambiguity_note(idx, source, src_ids, sid) \
                            + _ambiguity_note(idx, target, tgt_ids, tid)
            except nx.NetworkXNoPath:
                continue
            except nx.NodeNotFound:
                continue

    return (
        f"No path found between '{sanitize_label(source)}' and "
        f"'{sanitize_label(target)}'."
    )


def _ambiguity_note(idx: BeaconIndex, term: str, ids: list[str], chosen: str) -> str:
    """Say which node was picked when the name matched several equally well.

    Silence here is what made the old ``ids[0]`` behaviour dangerous: the answer
    looked authoritative whether or not it was about the node the caller meant.
    """
    if len(ids) < 2:
        return ""
    others = [sanitize_label(idx._display_label(n)) for n in ids if n != chosen][:5]
    more = f", +{len(ids) - 1 - len(others)} more" if len(ids) - 1 > len(others) else ""
    return (
        f"\n\n_'{sanitize_label(term)}' matched {len(ids)} nodes equally well; "
        f"answered for `{sanitize_label(chosen)}`. Others: {', '.join(others)}{more}._"
    )


@_tool
def tool_beacon_blast_radius(idx: BeaconIndex, args: dict) -> str:
    """Show blast radius: downstream + upstream neighbours of a node.

    Args:
        node: node label (resolved by :meth:`BeaconIndex.resolve`)
        depth: max traversal depth (default 2, capped at MAX_DEPTH)
        limit: max neighbours listed per direction (default 100)
        token_budget: max tokens of output (default 2000; 0 = unlimited)
    """
    _require_graph(idx)
    node_name = str(args.get("node", ""))
    depth = _int_arg(args, "depth", 2, minimum=1, maximum=MAX_DEPTH)
    limit = _int_arg(args, "limit", 100, minimum=1, maximum=MAX_LIMIT)
    if not node_name:
        raise ToolError("'node' argument required.")

    ids = idx.resolve(node_name)
    if not ids:
        return f"No node matching '{sanitize_label(node_name)}'."

    nid = ids[0]
    label = sanitize_label(idx.G.nodes[nid].get("label", nid))

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

    def _emit(heading: str, nodes: set[str], extra: str = "") -> None:
        ordered = sorted(nodes, key=lambda n: (idx.G.nodes[n].get("label", n), n))
        shown = ordered[:limit]
        # A hub node can have thousands of neighbours; say so rather than
        # emitting them all and letting the budget cut mid-list.
        count = f"{len(ordered)}" if len(shown) == len(ordered) \
            else f"showing {len(shown)} of {len(ordered)}"
        lines.append(f"{heading} ({extra}{count}):")
        for n in shown:
            s = idx.node_summary(n)
            lines.append(f"- {s['label']} ({s['type']}) — {s['project']}")

    _emit("**Upstream callers**", upstream)
    lines.append("")
    _emit("**Downstream affected**", downstream, extra=f"depth={depth}, ")

    if not upstream and not downstream:
        lines.append("_No connections found._")

    return "\n".join(lines) + _ambiguity_note(idx, node_name, ids, nid)


@_tool
def tool_beacon_routes(idx: BeaconIndex, args: dict) -> str:
    """List all routes, optionally filtered by project.

    Args:
        project: filter by project name (optional)
        limit: max results (default 50, capped at MAX_LIMIT)
        token_budget: max tokens of output (default 2000; 0 = unlimited)
    """
    _require_graph(idx)
    project_filter = str(args.get("project", "")).lower()
    limit = _int_arg(args, "limit", 50, minimum=1, maximum=MAX_LIMIT)

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
    total = len(routes)
    routes = routes[:limit]

    if not routes:
        return "No routes found."

    count = f"{total}" if len(routes) == total else f"showing {len(routes)} of {total}"
    lines = [f"## Routes ({count})\n"]
    lines.append(f"{'Method':<8} {'Path':<40} {'Handler':<30} {'Project'}")
    lines.append("-" * 90)
    for r in routes:
        lines.append(
            f"{sanitize_label(r['method']):<8} {sanitize_label(r['path']):<40} "
            f"{sanitize_label(r['handler']):<30} {sanitize_label(r['project'])}"
        )
    return "\n".join(lines)


@_tool
def tool_beacon_services(idx: BeaconIndex, args: dict) -> str:
    """List all services/classes, optionally filtered by project.

    Args:
        project: filter by project name (optional)
        limit: max results (default 50, capped at MAX_LIMIT)
        token_budget: max tokens of output (default 2000; 0 = unlimited)
    """
    _require_graph(idx)
    project_filter = str(args.get("project", "")).lower()
    limit = _int_arg(args, "limit", 50, minimum=1, maximum=MAX_LIMIT)

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
    total = len(services)
    services = services[:limit]

    if not services:
        return "No services found."

    count = f"{total}" if len(services) == total else f"showing {len(services)} of {total}"
    lines = [f"## Services ({count})\n"]
    for s in services:
        annots = ", ".join(sanitize_label(a) for a in s["annotations"][:3]) if s["annotations"] else ""
        suffix = f"  [{annots}]" if annots else ""
        lines.append(
            f"- **{sanitize_label(s['label'])}** ({sanitize_label(s['project'])})"
            f"{suffix}  `{sanitize_label(s['source_file'])}`"
        )
    return "\n".join(lines)


@_tool
def tool_beacon_knowledge(idx: BeaconIndex, args: dict) -> str:
    """Search knowledge notes, or list the notes linked to a code node.

    Knowledge notes (ADRs, meeting notes, retros, specs, research) are linked
    into the graph by ``codebeacon knowledge`` as ``knowledge``-type nodes with
    edges to the code they reference. This tool surfaces the *why* behind the
    code that the other tools describe.

    Args:
        query: keyword(s) matched against note title, summary, category, and
               tags (case-insensitive substring).
        node:  optional node label/id — return only notes that link to a
               matching code node. May be combined with ``query`` to filter.
        limit: max notes to return (default 20, capped at MAX_LIMIT).
        token_budget: max tokens of output (default 2000; 0 = unlimited).
    """
    from codebeacon.common.types import KNOWLEDGE_NODE_TYPE

    _require_graph(idx)

    query = str(args.get("query") or "").strip()
    node = str(args.get("node") or "").strip()
    limit = _int_arg(args, "limit", 20, minimum=1, maximum=MAX_LIMIT)
    if not query and not node:
        raise ToolError("Provide 'query' and/or 'node'.")

    G = idx.G

    def _is_note(nid: str) -> bool:
        return G.nodes[nid].get("type") == KNOWLEDGE_NODE_TYPE

    # Candidate note ids: linked to a given node, else every knowledge note.
    if node:
        code_ids = idx.resolve(node)
        if not code_ids:
            return f"No node matching '{sanitize_label(node)}'."
        note_ids: list[str] = []
        seen: set[str] = set()
        for cid in code_ids:
            for src, _tgt, _d in G.in_edges(cid, data=True):
                if _is_note(src) and src not in seen:
                    seen.add(src)
                    note_ids.append(src)
    else:
        note_ids = [n for n in G.nodes() if _is_note(n)]

    query_cf = query.casefold()
    if query_cf:
        note_ids = [n for n in note_ids if query_cf in _note_haystack(G, n)]

    note_ids.sort(key=lambda n: (G.nodes[n].get("date", ""), G.nodes[n].get("label", n)), reverse=True)
    total_notes = len(note_ids)
    note_ids = note_ids[:limit]

    # A one-line description of the filter for both the header and the empty case.
    clauses = []
    if query:
        clauses.append(f"matching '{sanitize_label(query)}'")
    if node:
        clauses.append(f"linked to '{sanitize_label(node)}'")
    scope = " ".join(clauses)

    if not note_ids:
        return f"No knowledge notes {scope}.".replace("  ", " ")

    count = f"{total_notes}" if len(note_ids) == total_notes \
        else f"showing {len(note_ids)} of {total_notes}"
    lines = [f"## Knowledge notes ({count} {scope})".rstrip() + "\n"]
    for nid in note_ids:
        d = G.nodes[nid]
        title = sanitize_label(d.get("label", nid))
        category = sanitize_label(d.get("category", "note"))
        date = sanitize_label(d.get("date", "")) or "????-??-??"
        path = sanitize_label(d.get("note_path", d.get("source_file", "")))
        lines.append(f"- **{title}** ({category}, {date}) — `{path}`")
        summary = sanitize_label(d.get("summary", ""))
        if summary:
            lines.append(f"  {summary}")
        # Show what code each note points at, with the confidence band so the
        # agent can weigh a trusted path reference against an ambiguous mention.
        for _src, tgt, ed in G.out_edges(nid, data=True):
            tgt_label = sanitize_label(G.nodes[tgt].get("label", tgt))
            rel = sanitize_label(ed.get("relation", ""))
            conf = sanitize_label(ed.get("confidence", ""))
            lines.append(f"    → {tgt_label} [{rel}, {conf}]")
    return "\n".join(lines)


def _note_haystack(G, node_id: str) -> str:
    """Casefolded search text for a knowledge note (title/summary/category/tags)."""
    d = G.nodes[node_id]
    tags = d.get("tags", [])
    parts = [
        str(d.get("label", "")),
        str(d.get("summary", "")),
        str(d.get("category", "")),
        " ".join(tags) if isinstance(tags, list) else str(tags),
    ]
    return " ".join(parts).casefold()


# ── Tool registry ─────────────────────────────────────────────────────────────

_BUDGET_PROP = {
    "type": "integer",
    "description": (
        f"Max tokens of output (default {DEFAULT_TOKEN_BUDGET}). Output beyond the "
        "budget is trimmed on a line boundary and the trim is announced. 0 = unlimited."
    ),
}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    """Build an inputSchema with the token budget every tool accepts."""
    return {
        "type": "object",
        "properties": {**properties, "token_budget": _BUDGET_PROP},
        "required": required or [],
    }


TOOLS = {
    "beacon_wiki_index": {
        "fn": tool_beacon_wiki_index,
        "description": "Return the global wiki index (short overview of all projects and node counts).",
        "inputSchema": _schema({}),
    },
    "beacon_wiki_article": {
        "fn": tool_beacon_wiki_article,
        "description": "Read a specific wiki article by its relative path under wiki/ (e.g. 'api-server/services/UserService.md').",
        "inputSchema": _schema(
            {"path": {"type": "string", "description": "Relative path under wiki/ directory"}},
            ["path"],
        ),
    },
    "beacon_query": {
        "fn": tool_beacon_query,
        "description": (
            "Search graph nodes by label. Returns every match, best first (exact label, "
            "then prefix, then substring), with each node's edges."
        ),
        "inputSchema": _schema(
            {
                "term": {"type": "string", "description": "Search term (case-insensitive)"},
                "limit": {
                    "type": "integer",
                    "description": f"Max results (default 20, max {MAX_LIMIT})",
                    "minimum": 1, "maximum": MAX_LIMIT,
                },
            },
            ["term"],
        ),
    },
    "beacon_path": {
        "fn": tool_beacon_path,
        "description": "Find the shortest dependency path between two nodes by label.",
        "inputSchema": _schema(
            {
                "source": {"type": "string", "description": "Source node label"},
                "target": {"type": "string", "description": "Target node label"},
            },
            ["source", "target"],
        ),
    },
    "beacon_blast_radius": {
        "fn": tool_beacon_blast_radius,
        "description": (
            "Show upstream callers and downstream affected nodes for a given node. "
            "An exact label match always wins; if several nodes match equally the "
            "answer names which one it used and how many others matched."
        ),
        "inputSchema": _schema(
            {
                "node": {"type": "string", "description": "Node label to analyze"},
                "depth": {
                    "type": "integer",
                    "description": f"Downstream traversal depth (default 2, max {MAX_DEPTH})",
                    "minimum": 1, "maximum": MAX_DEPTH,
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max neighbours listed per direction (default 100, max {MAX_LIMIT})",
                    "minimum": 1, "maximum": MAX_LIMIT,
                },
            },
            ["node"],
        ),
    },
    "beacon_routes": {
        "fn": tool_beacon_routes,
        "description": "List all HTTP routes in the knowledge graph, optionally filtered by project.",
        "inputSchema": _schema({
            "project": {"type": "string", "description": "Filter by project name (optional)"},
            "limit": {
                "type": "integer",
                "description": f"Max results (default 50, max {MAX_LIMIT})",
                "minimum": 1, "maximum": MAX_LIMIT,
            },
        }),
    },
    "beacon_services": {
        "fn": tool_beacon_services,
        "description": "List all service/class nodes in the knowledge graph, optionally filtered by project.",
        "inputSchema": _schema({
            "project": {"type": "string", "description": "Filter by project name (optional)"},
            "limit": {
                "type": "integer",
                "description": f"Max results (default 50, max {MAX_LIMIT})",
                "minimum": 1, "maximum": MAX_LIMIT,
            },
        }),
    },
    "beacon_knowledge": {
        "fn": tool_beacon_knowledge,
        "description": (
            "Search knowledge notes (ADRs, meeting notes, retros, specs, research) by "
            "keyword, or list the notes linked to a given code node. Use this to learn "
            "*why* the code looks the way it does — the decisions behind a service."
        ),
        "inputSchema": _schema({
            "query": {"type": "string", "description": "Keyword(s) matched against note title/summary/category/tags"},
            "node": {"type": "string", "description": "Optional node label/id — return only notes linked to it"},
            "limit": {
                "type": "integer",
                "description": f"Max notes to return (default 20, max {MAX_LIMIT})",
                "minimum": 1, "maximum": MAX_LIMIT,
            },
        }),
    },
    "beacon_pr_context": {
        "fn": "PLACEHOLDER",  # patched below to avoid forward-reference issues
        "description": (
            "Given a set of changed files (e.g. from a git diff), return the wiki article "
            "paths covering the affected slice of the knowledge graph. Use this at the start "
            "of a PR review to read just the docs that matter."
        ),
        "inputSchema": _schema({
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Changed file paths (repo-relative).",
            },
            "base": {
                "type": "string",
                "description": "Optional: git ref to diff against (e.g. main). If set, paths are augmented with `git diff --name-only base...HEAD`.",
            },
            "depth": {
                "type": "integer",
                "description": f"Upstream walk depth (default 3, max {MAX_DEPTH})",
                "minimum": 1, "maximum": MAX_DEPTH,
            },
            "limit": {
                "type": "integer",
                "description": f"Max wiki paths (default 50, max {MAX_LIMIT})",
                "minimum": 1, "maximum": MAX_LIMIT,
            },
        }),
    },
}


@_tool
def tool_beacon_pr_context(idx: BeaconIndex, args: dict) -> str:
    """Given changed files, return the wiki articles in their blast radius.

    Same engine as ``codebeacon affected --as wiki``, but invoked via MCP
    so a PR-reviewing agent can call it directly at the start of a turn.
    Returns a markdown list (so the agent can show it back to the user)
    plus the raw paths separated for easy copy-paste.
    """
    from codebeacon.affected import affected_from_paths, git_changed_files

    _require_graph(idx)

    paths = list(args.get("paths") or [])
    base = str(args.get("base") or "").strip()
    if base:
        paths.extend(git_changed_files(base, "HEAD", repo=idx.beacon_dir.parent))
    if not paths:
        raise ToolError("No changed paths supplied. Pass `paths` or `base`.")

    depth = _int_arg(args, "depth", 3, minimum=1, maximum=MAX_DEPTH)
    limit = _int_arg(args, "limit", 50, minimum=1, maximum=MAX_LIMIT)

    try:
        result = affected_from_paths(
            idx.beacon_dir,
            paths,
            depth=depth,
            limit=limit,
            include_wiki_paths=True,
        )
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from None

    if not result.wiki_paths:
        return (
            f"No wiki articles in the blast radius of {len(paths)} changed file(s). "
            f"(matched {len(result.seed_node_ids)} seed node(s), "
            f"{len(result.affected_node_ids)} upstream node(s) — but none had wiki articles)"
        )

    lines = [f"## PR context ({len(result.wiki_paths)} article(s))\n"]
    for wp in result.wiki_paths:
        lines.append(f"- `wiki/{sanitize_label(wp)}`")
    return "\n".join(lines)


# Patch in the function reference now that it's defined.
TOOLS["beacon_pr_context"]["fn"] = tool_beacon_pr_context


# ── JSON-RPC 2.0 / MCP protocol ───────────────────────────────────────────────

def _write(obj: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def run_tool(idx: BeaconIndex, name: str, args: dict | None = None) -> tuple[str, bool]:
    """Run a registered tool; return ``(text, is_error)``.

    The single entry point for every consumer — MCP dispatch and the CLI — so
    the error contract is decided in one place. ``KeyError`` for an unknown tool
    name is deliberately left to the caller: that is a protocol-level problem
    (JSON-RPC -32601), not a tool failure.
    """
    fn = TOOLS[name]["fn"]
    try:
        return fn(idx, args or {}), False
    except ToolError as exc:
        return _finalize_error(str(exc)), True
    except Exception as exc:
        # A crash inside a tool is still a *tool* result per the MCP spec, so
        # the model gets to see it and retry; the traceback context goes to the
        # server's stderr for the operator.
        print(f"[codebeacon-mcp] error in {name}: {exc}", file=sys.stderr)
        return _finalize_error(f"{type(exc).__name__}: {exc}"), True


def _finalize_error(text: str) -> str:
    """Error text is agent-visible too: defang it and keep it bounded."""
    return _apply_budget(defang_model_tokens(text), DEFAULT_TOKEN_BUDGET)


def _dispatch(idx: BeaconIndex, message: Any) -> dict | None:
    """Dispatch a single JSON-RPC 2.0 message; return response dict or None."""
    if not isinstance(message, dict):
        # Valid JSON but not a JSON-RPC request object (array/string/number/…).
        # A top-level array is the JSON-RPC 2.0 batch envelope, which we don't
        # support. Reply with Invalid Request rather than crashing on .get().
        return _error(None, -32600, "Invalid Request: expected a JSON object")
    req_id = message.get("id")
    method = message.get("method", "")
    params = message.get("params")
    if not isinstance(params, dict):
        # `params` may legitimately be omitted/null, but a non-empty array or
        # scalar would crash the ``params.get(...)`` calls below. Normalise any
        # non-object params to an empty dict.
        params = {}

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
                "serverInfo": {"name": "codebeacon", "version": __version__},
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

        result_text, is_error = run_tool(idx, tool_name, tool_args)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
                "isError": is_error,
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
    except (FileNotFoundError, ValueError) as e:
        # FileNotFoundError: no beacon.json yet. ValueError: corrupt/truncated
        # beacon.json (load_beacon backs it up + raises). Either way, still start
        # the server so the client can connect and tools explain the error rather
        # than crashing at startup with a traceback (graphify #1536). load() has
        # recorded the reason on idx.load_error, which is what the tools hand
        # back to the agent — stderr alone never reaches it.
        print(f"[codebeacon-mcp] {e}", file=sys.stderr)

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

        try:
            response = _dispatch(idx, message)
        except Exception as exc:
            # A single malformed/unexpected request must never take down the
            # long-lived server. Reply with a scoped internal error (echoing the
            # id when the message is a dict) and keep serving the connection.
            req_id = message.get("id") if isinstance(message, dict) else None
            print(f"[codebeacon-mcp] dispatch error: {exc}", file=sys.stderr)
            _write(_error(req_id, -32603, f"Internal error: {exc}"))
            continue
        if response is not None:
            _write(response)
