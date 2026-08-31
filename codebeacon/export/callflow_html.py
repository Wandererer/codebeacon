"""Mermaid-based call-flow HTML for ``beacon.json``.

Writes a self-contained ``callflow.html`` that renders, per community:

- a Mermaid flowchart of the community's internal call/import structure,
- a node summary table (label, type, file),
- the cross-community edges leaving the community (so the reader sees how the
  community connects to the rest of the system).

The page loads Mermaid from ``_assets/`` next to it (or a CDN when
``output.html_assets: cdn``); everything else is embedded. Identifiers from
source code are sanitized via :func:`codebeacon.common.safety.sanitize_label`,
and the Mermaid node IDs are derived from a synthetic ``n0``, ``n1`` … sequence
so source identifiers can never inject Mermaid syntax.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable

import networkx as nx

from codebeacon.common.io import portable_source_path, write_text_if_changed
from codebeacon.common.safety import sanitize_label
from codebeacon.export.assets import html_head_scripts


# Relations we want to draw inside a community diagram (those that capture the
# call-flow narrative). Edge labels are rendered verbatim under sanitisation.
_FLOW_RELATIONS = frozenset({
    "calls", "calls_api", "invokes_command", "depends", "injects",
    "imports", "imports_from",
})

# Cap on nodes/edges per community to keep Mermaid renderable.
_MAX_NODES_PER_COMMUNITY = 40
_MAX_EDGES_PER_COMMUNITY = 80
# Cap on the cross-community edge table under each community.
_MAX_CROSS_EDGES = 20


def write_callflow_html(
    G: nx.DiGraph,
    output_dir: str | Path,
    *,
    project_roots: dict[str, str] | None = None,
    html_assets: str = "local",
) -> Path:
    """Write ``callflow.html`` into ``output_dir`` and return its path.

    Communities are read from the ``community`` attribute on each node, which
    :mod:`codebeacon.graph.cluster.apply_communities` stamps onto the graph.
    Communities with fewer than two nodes are skipped — a single isolated node
    has no flow to show.

    ``project_roots`` maps project → absolute root so each node's source path is
    published relative to its project. ``html_assets`` is ``"local"`` (vendored
    Mermaid, works offline) or ``"cdn"``.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "callflow.html"

    communities = _group_by_community(G)
    sections = [
        _render_community(G, cid, nodes, total, project_roots, out_dir)
        for cid, nodes, total in communities
    ]
    page = _PAGE_TEMPLATE.replace("__CONTENT__", "\n".join(sections) or "<p>No communities to render.</p>")
    page = page.replace("__SUMMARY__", _summary_line(G, communities))
    page = page.replace("__SCRIPTS__", html_head_scripts(out_dir, ("mermaid",), html_assets))
    write_text_if_changed(target, page)
    return target


# ── Community grouping ───────────────────────────────────────────────────────

def _group_by_community(G: nx.DiGraph) -> list[tuple[int, list[str], int]]:
    """``(community id, nodes kept for rendering, true community size)``.

    The third element is what the header needs: trimming to
    ``_MAX_NODES_PER_COMMUNITY`` before the header was rendered meant a
    120-node community announced itself as "40 nodes", and a reader had no way
    to tell the cap from the total (graphify #953-13).
    """
    by_cid: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") == "external":
            continue
        cid = data.get("community")
        if cid is None:
            continue
        by_cid.setdefault(int(cid), []).append(node_id)

    groups: list[tuple[int, list[str], int]] = []
    for cid, ids in by_cid.items():
        if len(ids) < 2:
            continue
        # Order by total degree so the busiest nodes are the first ones we keep
        # after trimming.
        ids.sort(key=lambda n: G.degree(n), reverse=True)
        groups.append((cid, ids[:_MAX_NODES_PER_COMMUNITY], len(ids)))

    groups.sort(key=lambda group: len(group[1]), reverse=True)
    return groups


def _count_note(shown: int, total: int, noun: str) -> str:
    """``"12 nodes"`` when nothing was cut, ``"showing 40 of 120 nodes"`` when it was."""
    if total <= shown:
        return f"{shown} {noun}"
    return f"showing {shown} of {total} {noun}"


# ── Per-community rendering ─────────────────────────────────────────────────

def _render_community(
    G: nx.DiGraph,
    cid: int,
    node_ids: list[str],
    total_nodes: int | None = None,
    project_roots: dict[str, str] | None = None,
    output_dir: str | Path = ".",
) -> str:
    id_to_local = {nid: f"n{i}" for i, nid in enumerate(node_ids)}
    members: set[str] = set(node_ids)

    diagram_lines = ["flowchart LR"]
    for nid in node_ids:
        data = G.nodes[nid]
        label = sanitize_label(data.get("label", nid)) or "(unnamed)"
        ntype = sanitize_label(data.get("type", "")) or "node"
        # Mermaid bracket syntax: shape varies by node type for visual cue.
        shape = _shape_for(ntype, label)
        diagram_lines.append(f"  {id_to_local[nid]}{shape}")
        diagram_lines.append(f"  class {id_to_local[nid]} type_{ntype}")

    # Count every drawable edge first, then draw up to the cap, so the header
    # can state both figures instead of passing the cap off as the total.
    eligible = [
        (src, tgt, edata.get("relation", ""))
        for src, tgt, edata in G.edges(data=True)
        if src in members and tgt in members and edata.get("relation", "") in _FLOW_RELATIONS
    ]
    for src, tgt, relation in eligible[:_MAX_EDGES_PER_COMMUNITY]:
        rel_label = sanitize_label(relation)
        diagram_lines.append(f"  {id_to_local[src]} -- {rel_label} --> {id_to_local[tgt]}")
    edge_count = min(len(eligible), _MAX_EDGES_PER_COMMUNITY)

    # Cross-community out-edges leaving this community → renders as table.
    cross: list[tuple[str, str, str]] = []
    for nid in node_ids:
        for _, tgt, edata in G.out_edges(nid, data=True):
            if tgt in members:
                continue
            tgt_data = G.nodes.get(tgt, {})
            tgt_cid = tgt_data.get("community")
            if tgt_cid is None or int(tgt_cid) == cid:
                continue
            cross.append((
                sanitize_label(G.nodes[nid].get("label", nid)) or nid,
                sanitize_label(edata.get("relation", "")),
                sanitize_label(tgt_data.get("label", tgt)) or tgt,
            ))

    rows = "".join(
        # `or ''` (not a .get default) so an explicit None value — the graph
        # tolerates None labels/fields — coerces to "" instead of crashing
        # html.escape, which the missing-key default would not do.
        f"<tr><td>{html.escape(G.nodes[nid].get('label', nid) or '(unnamed)')}</td>"
        f"<td>{html.escape(G.nodes[nid].get('type') or '')}</td>"
        f"<td><code>{html.escape(_node_source(G, nid, project_roots, output_dir))}</code></td></tr>"
        for nid in node_ids[:_MAX_NODES_PER_COMMUNITY]
    )

    cross_rows = "".join(
        f"<tr><td>{html.escape(src)}</td><td>{html.escape(rel)}</td><td>{html.escape(tgt)}</td></tr>"
        for src, rel, tgt in cross[:_MAX_CROSS_EDGES]
    )

    node_total = len(node_ids) if total_nodes is None else total_nodes
    node_summary = _count_note(len(node_ids), node_total, "nodes")
    edge_summary = _count_note(edge_count, len(eligible), "flow edges")
    cross_summary = _count_note(min(len(cross), _MAX_CROSS_EDGES), len(cross), "edges")

    diagram_block = "\n".join(diagram_lines)
    return f"""
<section class="community">
  <h2>Community {cid} <span class="muted">— {node_summary}, {edge_summary}</span></h2>
  <div class="mermaid">{html.escape(diagram_block)}</div>
  <details>
    <summary>Nodes ({node_summary})</summary>
    <table><thead><tr><th>Label</th><th>Type</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>
  </details>
  {("<details><summary>Outgoing cross-community edges (" + cross_summary + ")</summary><table><thead><tr><th>From</th><th>Relation</th><th>To</th></tr></thead><tbody>" + cross_rows + "</tbody></table></details>") if cross else ""}
</section>
"""


def _node_source(
    G: nx.DiGraph,
    nid: str,
    project_roots: dict[str, str] | None,
    output_dir: str | Path,
) -> str:
    """A node's source path, made portable before it is published."""
    data = G.nodes[nid]
    return portable_source_path(
        data.get("source_file") or "",
        data.get("project") or "",
        project_roots,
        output_dir,
    )


def _shape_for(ntype: str, label: str) -> str:
    """Return the Mermaid shape suffix for a node, with the label escaped.

    Mermaid uses different bracket pairs for different shapes; we pick one per
    node type so the diagram is visually distinct without needing a legend.
    """
    safe = label.replace("\"", "'").replace("|", "/").replace("[", "(").replace("]", ")")
    if ntype == "route":
        return f"([\"{safe}\"])"        # rounded edges
    if ntype == "entity":
        return f"[(\"{safe}\")]"        # cylinder
    if ntype == "component":
        return f">\"{safe}\"]"          # asymmetric
    if ntype == "class":
        return f"[\"{safe}\"]"          # rectangle
    return f"[\"{safe}\"]"


def _summary_line(G: nx.DiGraph, communities: Iterable[tuple[int, list[str], int]]) -> str:
    n_communities = sum(1 for _ in communities)
    return (
        f"{G.number_of_nodes()} nodes · {G.number_of_edges()} edges · "
        f"{n_communities} communities rendered"
    )


# ── Page template ───────────────────────────────────────────────────────────

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>codebeacon — call flow</title>
__SCRIPTS__
<style>
  body { margin: 0; padding: 24px 32px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1419; color: #e6edf3; }
  header { margin-bottom: 24px; }
  header h1 { font-size: 16px; margin: 0 0 4px 0; }
  header .summary { color: #8b949e; font-size: 12px; }
  section.community { background: #161b22; border: 1px solid #21262d; border-radius: 6px; padding: 16px 20px; margin-bottom: 18px; }
  section.community h2 { font-size: 14px; margin: 0 0 12px 0; }
  section.community .muted { color: #8b949e; font-weight: 400; font-size: 12px; }
  .mermaid { background: #0f1419; border: 1px solid #21262d; border-radius: 4px; padding: 10px; overflow: auto; }
  details { margin-top: 12px; }
  details > summary { cursor: pointer; color: #58a6ff; font-size: 12px; }
  table { width: 100%; margin-top: 8px; border-collapse: collapse; font-size: 12px; }
  th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 600; }
  code { color: #79c0ff; word-break: break-all; }
</style>
</head>
<body>
<header>
  <h1>codebeacon — call flow</h1>
  <div class="summary">__SUMMARY__</div>
</header>
__CONTENT__
<script>
  mermaid.initialize({ startOnLoad: true, theme: "dark", securityLevel: "strict" });
</script>
</body>
</html>
"""
