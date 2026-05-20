"""Knowledge map: ``.md`` notes → ``KNOWLEDGE.md``.

Ports the codesight 1.9.3 ``--mode knowledge`` feature: scans markdown files
under a directory (ADR-style decision records, meeting notes, retrospectives,
specs/PRDs, research notes, Obsidian vault entries) and produces a single
compact ``KNOWLEDGE.md`` primer next to ``.codebeacon/``.

Public entry point:

    from codebeacon.knowledge import build_knowledge_map
    result = build_knowledge_map(root, output_dir)
"""

from codebeacon.knowledge.generator import build_knowledge_map, KnowledgeResult

__all__ = ["build_knowledge_map", "KnowledgeResult"]
