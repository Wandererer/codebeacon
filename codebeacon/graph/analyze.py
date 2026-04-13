"""Graph analysis: god nodes, surprising connections, hub files, cohesion scoring.

These metrics help users understand their codebase structure at a glance.

Public API:
    god_nodes(G, top_n, min_degree)          → list[GodNode]
    surprising_connections(G, communities)    → list[SurprisingConnection]
    hub_files(G, top_n)                       → list[HubFile]
    analyze(G, communities, cohesion_scores)  → GraphReport
    report_to_markdown(report)                → str
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import networkx as nx


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class GodNode:
    """A node with unusually high degree (hub / bottleneck)."""
    node_id: str
    label: str
    type: str
    in_degree: int
    out_degree: int
    degree: int
    centrality: float
    source_file: str


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

def god_nodes(
    G: nx.DiGraph,
    top_n: int = 20,
    min_degree: int = 5,
) -> list[GodNode]:
    """Find nodes with the highest degree (potential god classes / bottlenecks).

    Args:
        G: the knowledge graph
        top_n: return at most this many nodes
        min_degree: minimum total degree to qualify

    Returns:
        List of GodNode sorted by degree descending.
    """
    centrality = nx.degree_centrality(G)

    results: list[GodNode] = []
    for node_id, data in G.nodes(data=True):
        deg = G.degree(node_id)
        if deg < min_degree:
            continue
        results.append(GodNode(
            node_id=node_id,
            label=data.get("label", node_id),
            type=data.get("type", "unknown"),
            in_degree=G.in_degree(node_id),
            out_degree=G.out_degree(node_id),
            degree=deg,
            centrality=centrality.get(node_id, 0.0),
            source_file=data.get("source_file", ""),
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
) -> GraphReport:
    """Run all analyses and return a unified GraphReport.

    Args:
        G: built knowledge graph (output of build.py + optional enrich.py)
        communities: optional community mapping from cluster.py
        cohesion_scores: optional per-community cohesion scores from cluster.score_all()
    """
    report = GraphReport(
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
        community_count=len(set(communities.values())) if communities else 0,
        cohesion_scores=cohesion_scores or {},
        density=nx.density(G),
        isolated_nodes=sum(1 for n in G.nodes() if G.degree(n) == 0),
    )

    report.god_nodes = god_nodes(G)
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
        lines += ["## God Nodes (High Coupling)", ""]
        lines.append(f"{'Node':<40} {'Type':<12} {'Degree':>6} {'Centrality':>10}")
        lines.append("-" * 72)
        for gn in report.god_nodes[:10]:
            lines.append(
                f"{gn.label:<40} {gn.type:<12} {gn.degree:>6} {gn.centrality:>10.4f}"
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
