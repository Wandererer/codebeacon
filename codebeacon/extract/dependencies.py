"""Import / dependency graph extraction for all supported languages.

Public API:
    extract_dependencies(file_path, framework) -> list[Edge]

Near-generic: every .scm query file uses `@import.path` captures.
This module runs any framework's query and collects all import.path captures,
returning Edge objects with relation="imports_from".
"""
from __future__ import annotations

from pathlib import Path

from codebeacon.common.types import Edge
from codebeacon.extract.base import (
    extract_sfc_sections,
    load_query_file,
    node_text,
    parse_file,
    parse_sfc_script,
    run_query,
)


# ── Framework → query file stem ───────────────────────────────────────────────

_FW_TO_QUERY: dict[str, str] = {
    "spring-boot": "spring_boot",
    "express":     "express",
    "koa":         "express",
    "fastify":     "express",
    "nestjs":      "nestjs",
    "nextjs":      "react",
    "react":       "react",
    "fastapi":     "fastapi",
    "django":      "django",
    "flask":       "flask",
    "gin":         "gin",
    "echo":        "gin",
    "fiber":       "gin",
    "go":          "gin",
    "rails":       "rails",
    "laravel":     "laravel",
    "aspnet":      "aspnet",
    "actix":       "actix",
    "axum":        "actix",
    "rust":        "actix",
    "vapor":       "vapor",
    "ktor":        "ktor",
    "vue":         "vue",
    "nuxt":        "vue",
    "sveltekit":   "svelte",
    "angular":     "angular",
}


# ── Public function ───────────────────────────────────────────────────────────

def extract_dependencies(file_path: str, framework: str) -> list[Edge]:
    """Extract import/require/use statements and return list[Edge] with relation='imports_from'.

    Each Edge has:
      - source: file_path (the file that contains the import)
      - target: the imported path/module (raw string from the import statement)
      - relation: "imports_from"
      - confidence: "EXTRACTED"
      - confidence_score: 1.0
      - source_file: file_path
    """
    fw = framework.lower()
    query_name = _FW_TO_QUERY.get(fw)
    if not query_name:
        return []

    query_src = load_query_file(query_name)
    if not query_src:
        return []

    # SFC dispatch
    ext = Path(file_path).suffix.lower()
    if ext in (".vue", ".svelte"):
        sfc = extract_sfc_sections(file_path)
        if sfc is None:
            return []
        parsed = parse_sfc_script(sfc)
    else:
        parsed = parse_file(file_path)

    if parsed is None:
        return []
    root, lang = parsed

    from codebeacon.extract.base import is_grammar_allowed
    if not is_grammar_allowed(query_name, lang):
        return []

    try:
        matches = run_query(lang, query_src, root)
    except Exception:
        return []

    # Generic: collect all import.path captures across all patterns
    edges: list[Edge] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        # All query files use @import.path for the imported module string
        if "import.path" not in caps:
            continue
        for import_node in caps["import.path"]:
            raw = node_text(import_node).strip("'\"` ")
            if not raw or raw in seen:
                continue
            seen.add(raw)
            edges.append(Edge(
                source=file_path,
                target=raw,
                relation="imports_from",
                confidence="EXTRACTED",
                confidence_score=1.0,
                source_file=file_path,
            ))

        # Vapor uses @import.name instead of @import.path
        if "import.name" in caps:
            for import_node in caps["import.name"]:
                raw = node_text(import_node).strip()
                if not raw or raw in seen:
                    continue
                seen.add(raw)
                edges.append(Edge(
                    source=file_path,
                    target=raw,
                    relation="imports_from",
                    confidence="EXTRACTED",
                    confidence_score=1.0,
                    source_file=file_path,
                ))

    return edges
