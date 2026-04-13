"""Index file generators: global index.md, overview.md, routes.md, cross-project/connections.md.

Public API:
    generate_index(wiki_dir, project_summary, routes_by_project, cross_edges, total_stats)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codebeacon.wiki import templates


def generate_index(
    wiki_dir: Path,
    project_summary: list[dict[str, Any]],
    routes_by_project: dict[str, list[dict[str, Any]]],
    cross_edges: list[dict[str, Any]],
    total_stats: dict[str, int],
) -> None:
    """Write all global index files into wiki_dir.

    Args:
        wiki_dir:          root wiki output directory (.codebeacon/wiki/)
        project_summary:   list of {name, framework, route_count, service_count, entity_count, component_count}
        routes_by_project: project_name → list of route dicts
        cross_edges:       list of cross-project edge dicts {source, target, relation, source_project, target_project}
        total_stats:       aggregate {nodes, edges, communities, routes, services, entities, components}
    """
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # index.md (short ~200 tokens global index)
    content = templates.global_index(
        projects=project_summary,
        total_stats=total_stats,
    )
    _write(wiki_dir / "index.md", content)

    # overview.md
    cross_connections = [
        {"source": f"{e['source_project']}/{e['source']}", "target": f"{e['target_project']}/{e['target']}", "relation": e["relation"]}
        for e in cross_edges
    ]
    content = templates.platform_overview(
        projects=project_summary,
        cross_connections=cross_connections,
        total_stats=total_stats,
    )
    _write(wiki_dir / "overview.md", content)

    # routes.md (all projects)
    content = templates.routes_summary(routes_by_project)
    _write(wiki_dir / "routes.md", content)

    # cross-project/connections.md
    _write_cross_project(wiki_dir / "cross-project" / "connections.md", cross_edges)


def _write_cross_project(path: Path, cross_edges: list[dict[str, Any]]) -> None:
    """Write cross-project/connections.md."""
    lines = [
        "# Cross-Project Connections",
        "",
        "Edges that cross service/project boundaries, extracted from the knowledge graph.",
        "",
    ]

    if not cross_edges:
        lines.append("_No cross-project connections detected._")
    else:
        # Group by relation type
        by_relation: dict[str, list[dict]] = {}
        for e in cross_edges:
            rel = e.get("relation", "unknown")
            by_relation.setdefault(rel, []).append(e)

        for relation in sorted(by_relation.keys()):
            edges = by_relation[relation]
            lines += [f"## `{relation}`", ""]
            for e in edges[:50]:  # cap per relation
                src_proj = e.get("source_project", "")
                tgt_proj = e.get("target_project", "")
                src = e.get("source", "")
                tgt = e.get("target", "")
                lines.append(f"- `{src_proj}/{src}` → `{tgt_proj}/{tgt}`")
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
