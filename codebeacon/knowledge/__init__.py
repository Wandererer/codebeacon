"""Knowledge map: ``.md`` notes → ``KNOWLEDGE.md``.

Ports the codesight 1.9.3 ``--mode knowledge`` feature: scans markdown files
under a directory (ADR-style decision records, meeting notes, retrospectives,
specs/PRDs, research notes, Obsidian vault entries) and produces a single
compact ``KNOWLEDGE.md`` primer next to ``.codebeacon/``.

Public entry points:

    from codebeacon.knowledge import build_knowledge_map
    result = build_knowledge_map(root, output_dir)

    from codebeacon.knowledge import link_knowledge_to_graph, resolve_beacon_dir
    link_knowledge_to_graph(result, beacon_dir)  # notes → beacon.json overlay
"""

from codebeacon.knowledge.generator import build_knowledge_map, KnowledgeResult
from codebeacon.knowledge.link import (
    LinkResult,
    link_knowledge_to_graph,
    reapply_knowledge,
    resolve_beacon_dir,
)

__all__ = [
    "build_knowledge_map",
    "KnowledgeResult",
    "LinkResult",
    "link_knowledge_to_graph",
    "reapply_knowledge",
    "resolve_beacon_dir",
]
