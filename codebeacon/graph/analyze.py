"""Graph analysis: god nodes, surprising connections, hub files, cohesion scoring.

These metrics help users understand their codebase structure at a glance.

Public API:
    god_nodes(G, top_n, min_degree, project_paths)  → list[GodNode]
    surprising_connections(G, communities)           → list[SurprisingConnection]
    hub_files(G, top_n)                              → list[HubFile]
    analyze(G, communities, cohesion_scores,
            project_paths)                           → GraphReport
    report_to_markdown(report)                       → str
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class GodNode:
    """A directory with unusually high cross-boundary coupling."""
    folder_path: str    # relative path within project: "lib/utils" or "src-tauri/src"
    label: str          # folder name: "utils"
    project: str        # owning project: "desktop"
    child_count: int    # number of nodes inside this folder
    in_degree: int      # external → folder edges
    out_degree: int     # folder → external edges
    degree: int         # total cross-boundary edges
    centrality: float   # degree / (total_nodes - child_count)


@dataclass
class SurprisingConnection:
    """A cross-community edge that may indicate unexpected coupling."""
    source_id: str
    source_label: str
    target_id: str
    target_label: str
    relation: str
    src_community: int
    tgt_community: int
    source_file: str


@dataclass
class HubFile:
    """A source file imported by many other files (potential God file)."""
    file_path: str
    import_count: int
    node_count: int


@dataclass
class GraphReport:
    """Complete analysis report for a built graph."""
    node_count: int = 0
    edge_count: int = 0
    community_count: int = 0
    god_nodes: list[GodNode] = field(default_factory=list)
    surprising_connections: list[SurprisingConnection] = field(default_factory=list)
    hub_files: list[HubFile] = field(default_factory=list)
    cohesion_scores: dict[int, float] = field(default_factory=dict)
    isolated_nodes: int = 0
    density: float = 0.0


# ── Analysis functions ────────────────────────────────────────────────────────

def _infer_project_paths(G: nx.DiGraph) -> dict[str, str]:
    """Infer project root paths from source_file attributes in the graph.

    Groups nodes by their ``project`` attribute, then finds the common path
    prefix of all source_file directories within each project.
    """
    project_dirs: dict[str, list[str]] = defaultdict(list)
    for _node_id, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        proj = data.get("project", "")
        if sf and proj:
            project_dirs[proj].append(os.path.dirname(os.path.abspath(sf)))

    result: dict[str, str] = {}
    for proj, dirs in project_dirs.items():
        if dirs:
            result[proj] = os.path.commonpath(dirs)
    return result


def god_nodes(
    G: nx.DiGraph,
    top_n: int = 20,
    min_degree: int = 5,
    project_paths: Optional[dict[str, str]] = None,
) -> list[GodNode]:
    """Find directories with the highest cross-boundary coupling.

    Counts only edges that cross folder boundaries (cross-boundary edges).
    Intra-folder edges are ignored, so a single large wrapper file can no
    longer dominate solely because of its high node-level degree.

    Args:
        G: the knowledge graph
        top_n: return at most this many folders
        min_degree: minimum cross-boundary edge count to qualify
        project_paths: optional dict mapping project name → absolute project
                       root path.  When None, paths are inferred automatically
                       from source_file attributes via ``_infer_project_paths``.

    Returns:
        List of GodNode (folder-level) sorted by degree descending.
    """
    if project_paths is None:
        project_paths = _infer_project_paths(G)

    total_nodes = G.number_of_nodes()

    # Step 1: build node → (folder_key, folder_path, project) mapping.
    # folder_key uses "{project}/{rel}" for cross-project uniqueness.
    # folder_path stores only the relative portion shown in the report.
    node_folder_key: dict[str, str] = {}
    key_to_rel: dict[str, str] = {}
    key_to_project: dict[str, str] = {}

    for node_id, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        proj = data.get("project", "")
        if not sf:
            continue
        dirname = os.path.dirname(os.path.abspath(sf))
        if proj and proj in project_paths:
            try:
                rel = os.path.relpath(dirname, project_paths[proj])
            except ValueError:
                rel = dirname
            # Skip nodes whose source lives outside the project root
            if rel.startswith(".."):
                rel = dirname
        else:
            rel = dirname
        key = f"{proj}/{rel}" if proj else rel
        node_folder_key[node_id] = key
        key_to_rel[key] = rel
        key_to_project[key] = proj

    # Step 2: count cross-boundary edges in a single pass.
    folder_in: dict[str, int] = defaultdict(int)
    folder_out: dict[str, int] = defaultdict(int)
    folder_children: dict[str, set] = defaultdict(set)

    for node_id in G.nodes():
        fk = node_folder_key.get(node_id)
        if fk:
            folder_children[fk].add(node_id)

    for src, tgt in G.edges():
        src_key = node_folder_key.get(src)
        tgt_key = node_folder_key.get(tgt)
        if src_key is None or tgt_key is None:
            continue
        if src_key != tgt_key:
            folder_out[src_key] += 1
            folder_in[tgt_key] += 1

    # Step 3: filter, build GodNode list, sort.
    results: list[GodNode] = []
    for folder_key in folder_children:
        in_d = folder_in.get(folder_key, 0)
        out_d = folder_out.get(folder_key, 0)
        degree = in_d + out_d
        if degree < min_degree:
            continue
        child_count = len(folder_children[folder_key])
        centrality = degree / max(1, total_nodes - child_count)
        rel = key_to_rel.get(folder_key, folder_key)
        proj = key_to_project.get(folder_key, "")
        label = os.path.basename(rel) if rel not in (".", "") else "(root)"
        results.append(GodNode(
            folder_path=rel,
            label=label,
            project=proj,
            child_count=child_count,
            in_degree=in_d,
            out_degree=out_d,
            degree=degree,
            centrality=centrality,
        ))

    results.sort(key=lambda n: n.degree, reverse=True)
    return results[:top_n]


def surprising_connections(
    G: nx.DiGraph,
    communities: dict[str, int],
    top_n: int = 20,
) -> list[SurprisingConnection]:
    """Find cross-community edges that may indicate unexpected coupling.

    Expected cross-service relations (calls_api, shares_db_entity) are excluded
    because they are intentional architectural connections.

    Args:
        G: the knowledge graph
        communities: node_id → community_id mapping from cluster.py
        top_n: return at most this many connections

    Returns:
        List of SurprisingConnection sorted by relation type (most surprising first).
    """
    # Relations that are expected to cross communities
    expected_relations = frozenset({"calls_api", "shares_db_entity"})
    # Priority: lower = more surprising
    priority = {"injects": 0, "calls": 1, "imports": 2, "imports_from": 3}

    results: list[SurprisingConnection] = []

    for src, tgt, edge_data in G.edges(data=True):
        relation = edge_data.get("relation", "")
        if relation in expected_relations:
            continue

        src_community = communities.get(src, -1)
        tgt_community = communities.get(tgt, -1)

        if src_community < 0 or tgt_community < 0:
            continue
        if src_community == tgt_community:
            continue

        src_data = G.nodes.get(src, {})
        tgt_data = G.nodes.get(tgt, {})

        results.append(SurprisingConnection(
            source_id=src,
            source_label=src_data.get("label", src),
            target_id=tgt,
            target_label=tgt_data.get("label", tgt),
            relation=relation,
            src_community=src_community,
            tgt_community=tgt_community,
            source_file=edge_data.get("source_file", ""),
        ))

    results.sort(key=lambda c: (priority.get(c.relation, 99), c.source_label))
    return results[:top_n]


def hub_files(
    G: nx.DiGraph,
    top_n: int = 20,
) -> list[HubFile]:
    """Find source files imported by many other files.

    Args:
        G: the knowledge graph
        top_n: return at most this many files

    Returns:
        List of HubFile sorted by import_count descending.
    """
    file_imports: dict[str, int] = {}
    file_nodes: dict[str, int] = {}

    for _node_id, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        if sf:
            file_nodes[sf] = file_nodes.get(sf, 0) + 1

    for _src, _tgt, edge_data in G.edges(data=True):
        if edge_data.get("relation") not in ("imports", "imports_from"):
            continue
        sf = edge_data.get("source_file", "")
        if sf:
            file_imports[sf] = file_imports.get(sf, 0) + 1

    results = [
        HubFile(
            file_path=fp,
            import_count=cnt,
            node_count=file_nodes.get(fp, 0),
        )
        for fp, cnt in file_imports.items()
    ]
    results.sort(key=lambda h: h.import_count, reverse=True)
    return results[:top_n]


def analyze(
    G: nx.DiGraph,
    communities: Optional[dict[str, int]] = None,
    cohesion_scores: Optional[dict[int, float]] = None,
    project_paths: Optional[dict[str, str]] = None,
) -> GraphReport:
    """Run all analyses and return a unified GraphReport.

    Args:
        G: built knowledge graph (output of build.py + optional enrich.py)
        communities: optional community mapping from cluster.py
        cohesion_scores: optional per-community cohesion scores from cluster.score_all()
        project_paths: optional dict mapping project name → absolute project root path.
                       When None, paths are inferred automatically from the graph.
    """
    report = GraphReport(
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
        community_count=len(set(communities.values())) if communities else 0,
        cohesion_scores=cohesion_scores or {},
        density=nx.density(G),
        isolated_nodes=sum(1 for n in G.nodes() if G.degree(n) == 0),
    )

    report.god_nodes = god_nodes(G, project_paths=project_paths)
    report.hub_files = hub_files(G)

    if communities:
        report.surprising_connections = surprising_connections(G, communities)

    return report


def report_to_markdown(report: GraphReport) -> str:
    """Render a GraphReport as a Markdown string."""
    lines = [
        "# CodeBeacon Graph Report",
        "",
        "## Statistics",
        f"- Nodes: {report.node_count}",
        f"- Edges: {report.edge_count}",
        f"- Communities: {report.community_count}",
        f"- Graph density: {report.density:.4f}",
        f"- Isolated nodes: {report.isolated_nodes}",
        "",
    ]

    if report.god_nodes:
        lines += ["## God Nodes (High-Coupling Directories)", ""]
        lines.append(
            f"{'Folder':<44} {'Project':<12} {'Cross-Edges':>11} {'Children':>8} {'Centrality':>10}"
        )
        lines.append("-" * 89)
        for gn in report.god_nodes[:10]:
            lines.append(
                f"{gn.folder_path:<44} {gn.project:<12} {gn.degree:>11} {gn.child_count:>8} {gn.centrality:>10.4f}"
            )
        lines.append("")

    if report.surprising_connections:
        lines += ["## Surprising Connections (Cross-Community Coupling)", ""]
        for sc in report.surprising_connections[:10]:
            lines.append(
                f"- [{sc.relation}] {sc.source_label} (C{sc.src_community})"
                f" → {sc.target_label} (C{sc.tgt_community})"
            )
        lines.append("")

    if report.hub_files:
        lines += ["## Hub Files (Most Imported)", ""]
        for hf in report.hub_files[:10]:
            lines.append(f"- {hf.file_path} ({hf.import_count} imports)")
        lines.append("")

    if report.cohesion_scores:
        lines += ["## Community Cohesion Scores", ""]
        for cid, score in sorted(report.cohesion_scores.items()):
            lines.append(f"- Community {cid}: {score:.3f}")
        lines.append("")

    return "\n".join(lines)
