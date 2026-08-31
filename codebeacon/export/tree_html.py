"""Self-contained D3 v7 collapsible-tree view of ``beacon.json``.

Writes a single ``beacon.html`` to the output directory. The page embeds the
graph as inert JSON inside a ``<script type="application/json">`` tag; the
payload is JSON-escaped so a malicious identifier from source code can neither
close the script tag nor reach the page as markup.

Public API:

    write_tree_html(G, output_dir, *, top_n=400) → Path
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from codebeacon.common.io import portable_source_path, write_text_if_changed
from codebeacon.common.safety import sanitize_label
from codebeacon.export.assets import html_head_scripts


def write_tree_html(
    G: nx.DiGraph,
    output_dir: str | Path,
    *,
    top_n: int = 400,
    project_roots: dict[str, str] | None = None,
    html_assets: str = "local",
) -> Path:
    """Write ``beacon.html`` (D3 collapsible tree) into ``output_dir``.

    Args:
        G:             knowledge graph.
        output_dir:    directory to write into; created if missing.
        top_n:         maximum number of nodes per project to keep in the tree
                       (sorted by total degree, descending). Prevents the HTML
                       from ballooning on monorepos.
        project_roots: optional project → absolute root, so each node's
                       ``source_file`` is published relative to its project
                       rather than to the build machine.
        html_assets:   ``"local"`` (default) vendors D3 next to the page so it
                       renders offline; ``"cdn"`` restores the CDN ``<script>``.

    Returns:
        Path to the written file.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "beacon.html"

    tree = _build_tree(G, top_n=top_n, project_roots=project_roots, output_dir=out_dir)
    embedded = json.dumps(tree, ensure_ascii=False)
    page = _HTML_TEMPLATE.replace("__DATA__", _json_for_script_tag(embedded))
    page = page.replace("__SCRIPTS__", html_head_scripts(out_dir, ("d3",), html_assets))
    write_text_if_changed(target, page)
    return target


def _json_for_script_tag(payload: str) -> str:
    """Escape a JSON document for embedding in ``<script type=application/json>``.

    HTML-escaping the payload here was wrong in both directions. Inside a script
    element the parser is in script-data state and does NOT decode entities, so
    ``JSON.parse`` received ``List&lt;String&gt;`` verbatim and D3 rendered the
    entity text — which every Flask or ASP.NET typed route converter
    (``/user/<int:user_id>``) triggers, so it was routine, not an edge case.

    Escaping is still load-bearing: a label containing ``</script>`` would
    otherwise close the tag. Doing it JSON-side keeps both properties — no ``<``
    survives in the byte stream, and ``JSON.parse`` decodes ``\\u003c`` back to
    the original character. ``&`` goes too (it cannot start an entity here, but
    it costs nothing and removes the question), and U+2028/U+2029 because they
    are line terminators to a JavaScript parser.
    """
    return (
        payload.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


# ── Tree construction ────────────────────────────────────────────────────────

def _build_tree(
    G: nx.DiGraph,
    *,
    top_n: int,
    project_roots: dict[str, str] | None = None,
    output_dir: str | Path = ".",
) -> dict[str, Any]:
    """Build the project → type → node tree consumed by the D3 page."""
    # Project → type → list[node summary]
    projects: dict[str, dict[str, list[dict]]] = {}

    # Pre-compute total degree so we can keep only the top_n per project.
    degree = dict(G.degree())

    # Bucket nodes by project + type
    for node_id, data in G.nodes(data=True):
        if data.get("type") == "external":
            continue
        project = sanitize_label(data.get("project", "")) or "_unknown"
        ntype = sanitize_label(data.get("type", "")) or "unknown"
        summary = {
            "id": sanitize_label(node_id),
            "label": sanitize_label(data.get("label", node_id)) or "(unnamed)",
            "source_file": sanitize_label(
                portable_source_path(
                    data.get("source_file", "") or "",
                    data.get("project", "") or "",
                    project_roots,
                    output_dir,
                )
            ),
            "framework": sanitize_label(data.get("framework", "")),
            "degree": degree.get(node_id, 0),
        }
        projects.setdefault(project, {}).setdefault(ntype, []).append(summary)

    # Trim each project to top_n by degree and sort by label.
    root_children: list[dict] = []
    rendered_total = 0
    for project_name, by_type in sorted(projects.items()):
        flat = [n for nodes in by_type.values() for n in nodes]
        flat.sort(key=lambda n: n["degree"], reverse=True)
        kept_ids = {n["id"] for n in flat[:top_n]}

        type_children: list[dict] = []
        for type_name, nodes in sorted(by_type.items()):
            keep = sorted(
                (n for n in nodes if n["id"] in kept_ids),
                key=lambda n: n["label"].lower(),
            )
            if not keep:
                continue
            type_children.append({
                "name": type_name,
                "kind": "type",
                "count": len(keep),
                # What the project actually holds, so a trimmed branch says so
                # instead of presenting the cap as the whole truth (#953-13).
                "total": len(nodes),
                "children": [
                    {
                        "name": n["label"],
                        "kind": "node",
                        "id": n["id"],
                        "source_file": n["source_file"],
                        "framework": n["framework"],
                        "degree": n["degree"],
                    }
                    for n in keep
                ],
            })

        kept_here = sum(t["count"] for t in type_children)
        rendered_total += kept_here
        root_children.append({
            "name": project_name,
            "kind": "project",
            "count": kept_here,
            "total": len(flat),
            "children": type_children,
        })

    return {
        "name": "codebeacon",
        "kind": "root",
        "children": root_children,
        "stats": {
            "node_count": G.number_of_nodes(),
            # The headline used to read the graph's node count while the tree
            # rendered at most top_n per project, so a reader had no way to know
            # how much was missing (graphify #953-13).
            "rendered_node_count": rendered_total,
            "edge_count": G.number_of_edges(),
            "project_count": len(projects),
        },
    }


# ── HTML template ────────────────────────────────────────────────────────────

# The data block is interpolated as HTML-escaped JSON via ``.replace`` to keep
# the literal CSS/JS untouched (str.format would choke on every brace).
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>codebeacon — knowledge graph tree</title>
<style>
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f1419; color: #e6edf3; }
  header { padding: 12px 20px; background: #161b22; border-bottom: 1px solid #21262d; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 14px; margin: 0; font-weight: 600; }
  header .stats { font-size: 12px; color: #8b949e; }
  .controls { margin-left: auto; font-size: 12px; }
  .controls button { background: #21262d; color: #e6edf3; border: 1px solid #30363d; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 12px; margin-left: 4px; }
  .controls button:hover { background: #30363d; }
  #svg-wrap { width: 100vw; height: calc(100vh - 49px); overflow: auto; }
  svg { display: block; }
  .node circle { stroke-width: 1.5px; cursor: pointer; }
  .node text { font-size: 12px; fill: #e6edf3; pointer-events: none; }
  .node--internal text { font-weight: 600; }
  .node--leaf text { fill: #8b949e; }
  .link { fill: none; stroke: #30363d; stroke-opacity: 0.6; stroke-width: 1px; }
  #tooltip { position: fixed; background: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 8px 12px; font-size: 11px; pointer-events: none; opacity: 0; transition: opacity 0.15s; max-width: 360px; line-height: 1.4; }
  #tooltip code { color: #79c0ff; word-break: break-all; }
</style>
</head>
<body>
<header>
  <h1>codebeacon</h1>
  <span class="stats" id="stats"></span>
  <div class="controls">
    <button id="expand-all">Expand all</button>
    <button id="collapse-all">Collapse all</button>
  </div>
</header>
<div id="svg-wrap"><svg></svg></div>
<div id="tooltip"></div>
<script type="application/json" id="codebeacon-data">__DATA__</script>
__SCRIPTS__
<script>
(function() {
  const raw = document.getElementById("codebeacon-data").textContent;
  const data = JSON.parse(raw);
  const stats = data.stats || {};
  const total = stats.node_count || 0;
  const shown = stats.rendered_node_count;
  const nodeText = (shown !== undefined && shown !== total)
    ? (shown + " of " + total + " nodes shown")
    : (total + " nodes");
  document.getElementById("stats").textContent =
    nodeText + " · " + (stats.edge_count || 0) + " edges · " + (stats.project_count || 0) + " projects";

  const color = { project: "#58a6ff", type: "#d2a8ff", node: "#7ee787" };
  const NODE_HEIGHT = 22;
  const NODE_WIDTH = 240;

  const root = d3.hierarchy(data);
  // Collapse below the project level by default.
  if (root.children) {
    root.children.forEach(p => { if (p.children) collapse(p); });
  }
  function collapse(d) {
    if (d.children) { d._children = d.children; d.children = null; d._children.forEach(collapse); }
  }
  function expandAll(d) {
    if (d._children) { d.children = d._children; d._children = null; }
    if (d.children) d.children.forEach(expandAll);
  }

  const svg = d3.select("svg");
  const g = svg.append("g").attr("transform", "translate(40,40)");
  const tooltip = d3.select("#tooltip");

  let i = 0;
  const tree = d3.tree().nodeSize([NODE_HEIGHT, NODE_WIDTH]);
  const duration = 200;

  update(root);

  document.getElementById("expand-all").addEventListener("click", () => { expandAll(root); update(root); });
  document.getElementById("collapse-all").addEventListener("click", () => {
    if (root.children) root.children.forEach(c => { c._children = c.children; c.children = null; });
    update(root);
  });

  function update(source) {
    tree(root);
    let x0 = Infinity, x1 = -Infinity;
    root.each(d => { if (d.x > x1) x1 = d.x; if (d.x < x0) x0 = d.x; });
    const height = x1 - x0 + 100;
    svg.attr("viewBox", [-50, x0 - 40, 1600, height]).attr("width", 1600).attr("height", height);

    const nodes = root.descendants();
    const links = root.links();

    const node = g.selectAll("g.node").data(nodes, d => d.id || (d.id = ++i));

    const nodeEnter = node.enter().append("g")
      .attr("class", d => "node " + (d.children || d._children ? "node--internal" : "node--leaf"))
      .attr("transform", d => "translate(" + source.y0 + "," + source.x0 + ")")
      .on("click", (event, d) => {
        if (d.children) { d._children = d.children; d.children = null; }
        else if (d._children) { d.children = d._children; d._children = null; }
        update(d);
      })
      .on("mouseover", (event, d) => {
        const data = d.data || {};
        let html = "<strong>" + escapeHtml(data.name) + "</strong>";
        if (data.kind === "node") {
          if (data.source_file) html += "<br><code>" + escapeHtml(data.source_file) + "</code>";
          if (data.framework) html += "<br>framework: " + escapeHtml(data.framework);
          html += "<br>degree: " + (data.degree || 0);
        } else if (data.count !== undefined) {
          html += (data.total !== undefined && data.total !== data.count)
            ? ("<br>showing " + data.count + " of " + data.total + " nodes")
            : ("<br>" + data.count + " nodes");
        }
        tooltip.html(html).style("opacity", 1).style("left", (event.clientX + 12) + "px").style("top", (event.clientY + 12) + "px");
      })
      .on("mousemove", event => tooltip.style("left", (event.clientX + 12) + "px").style("top", (event.clientY + 12) + "px"))
      .on("mouseout", () => tooltip.style("opacity", 0));

    nodeEnter.append("circle")
      .attr("r", 4.5)
      .attr("fill", d => (d._children ? color[d.data.kind] || "#8b949e" : "#0f1419"))
      .attr("stroke", d => color[d.data.kind] || "#8b949e");

    nodeEnter.append("text")
      .attr("dy", "0.31em")
      .attr("x", d => (d._children || d.children ? -8 : 8))
      .attr("text-anchor", d => (d._children || d.children ? "end" : "start"))
      .text(d => d.data.name);

    const nodeUpdate = node.merge(nodeEnter);
    nodeUpdate.transition().duration(duration).attr("transform", d => "translate(" + d.y + "," + d.x + ")");
    nodeUpdate.select("circle").attr("fill", d => (d._children ? color[d.data.kind] || "#8b949e" : "#0f1419"));

    node.exit().transition().duration(duration)
      .attr("transform", d => "translate(" + source.y + "," + source.x + ")")
      .remove();

    const link = g.selectAll("path.link").data(links, d => d.target.id);
    const linkEnter = link.enter().insert("path", "g").attr("class", "link")
      .attr("d", () => {
        const o = { x: source.x0, y: source.y0 };
        return diagonal({ source: o, target: o });
      });
    linkEnter.merge(link).transition().duration(duration).attr("d", diagonal);
    link.exit().transition().duration(duration)
      .attr("d", () => { const o = { x: source.x, y: source.y }; return diagonal({ source: o, target: o }); })
      .remove();

    root.each(d => { d.x0 = d.x; d.y0 = d.y; });
  }

  function diagonal(d) {
    return "M" + d.source.y + "," + d.source.x
      + "C" + (d.source.y + d.target.y) / 2 + "," + d.source.x
      + " " + (d.source.y + d.target.y) / 2 + "," + d.target.x
      + " " + d.target.y + "," + d.target.x;
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));
  }
})();
</script>
</body>
</html>
"""
