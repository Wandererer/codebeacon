"""Import / dependency graph extraction for all supported languages.

Public API:
    extract_dependencies(file_path, framework) -> list[Edge]

Near-generic: every .scm query file uses `@import.path` captures.
This module runs any framework's query and collects all import.path captures,
returning Edge objects with relation="imports_from".

In addition, JS/TS family files are scanned for barrel re-exports
(``export { X } from './mod'``) which the SCM queries miss; those become
``re_exports`` edges so wiki/graph correctly link barrel files to their
backing modules. Mirrors graphify #1494874.
"""
from __future__ import annotations

import re
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


# JS/TS barrel re-exports:
#   export { Foo, Bar as Baz } from './mod'
#   export * from './mod'
#   export * as ns from './mod'
_JS_REEXPORT_RE = re.compile(
    r"""export\s+               # export keyword
        (?:\*(?:\s+as\s+\w+)?   #   * (optionally  * as ns)
           |\{[^}]*\})          #   or named { ... }
        \s+from\s+
        ['\"]([^'\"]+)['\"]     # module string
    """,
    re.VERBOSE,
)

# CommonJS require:
#   const x = require('mod')
#   x = require("mod")
#   require('side-effect')
# Mirrors graphify #753. Only `express.scm` currently captures require()
# inside the tree-sitter pipeline; this regex pass is the framework-agnostic
# fallback that lets Node / Next / Nest / Vue / Svelte projects pick up
# CommonJS imports without us forking 11 SCM query files.
_JS_REQUIRE_RE = re.compile(
    r"""require\s*\(            # require(
        \s*['\"]([^'\"]+)['\"]  # module string
        \s*\)                    # )
    """,
    re.VERBOSE,
)
_JS_FAMILY_EXTS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})


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
    "tornado":     "flask",
    "aiohttp":     "flask",
    "python":      "fastapi",
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
    "tauri":       "tauri",
    "rocket":      "actix",
    "warp":        "actix",
    "vapor":       "vapor",
    "ktor":        "ktor",
    "vue":         "vue",
    "nuxt":        "vue",
    "node":        "express",
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
    # .NET project / Razor files don't have a tree-sitter grammar; the dotnet
    # extractor handles them directly with stdlib XML / regex parsing.
    ext = Path(file_path).suffix.lower()
    if ext in {".sln", ".csproj", ".fsproj", ".vbproj", ".razor", ".cshtml"}:
        from codebeacon.extract.dotnet import extract_dotnet_edges
        return extract_dotnet_edges(file_path)

    fw = framework.lower()
    query_name = _FW_TO_QUERY.get(fw)
    if not query_name:
        return []

    query_src = load_query_file(query_name)
    if not query_src:
        return []

    # SFC dispatch (ext already computed above)
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

    # Generic: collect all import.path captures across all patterns.
    # `seen` keys on (relation, target) so the SCM pass dedupes uniformly
    # with the regex passes below (barrel re-exports + CommonJS require).
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()

    for _idx, caps in matches:
        # All query files use @import.path for the imported module string
        if "import.path" not in caps:
            continue
        for import_node in caps["import.path"]:
            raw = node_text(import_node).strip("'\"` ")
            key = ("imports_from", raw)
            if not raw or key in seen:
                continue
            seen.add(key)
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
                key = ("imports_from", raw)
                if not raw or key in seen:
                    continue
                seen.add(key)
                edges.append(Edge(
                    source=file_path,
                    target=raw,
                    relation="imports_from",
                    confidence="EXTRACTED",
                    confidence_score=1.0,
                    source_file=file_path,
                ))

    # JS/TS barrel re-exports + CommonJS require: re-scan source text with
    # regex. tree-sitter SCM queries here only target ES `import`; the other
    # two forms would otherwise need every framework's query updated. Regex
    # is unambiguous outside strings/comments for both patterns.
    if ext in _JS_FAMILY_EXTS:
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            source = ""
        for m in _JS_REEXPORT_RE.finditer(source):
            raw = m.group(1).strip()
            key = ("re_exports", raw)
            if not raw or key in seen:
                continue
            seen.add(key)
            edges.append(Edge(
                source=file_path,
                target=raw,
                relation="re_exports",
                confidence="EXTRACTED",
                confidence_score=1.0,
                source_file=file_path,
            ))
        for m in _JS_REQUIRE_RE.finditer(source):
            raw = m.group(1).strip()
            # `require()` resolves to the same logical edge as `import` —
            # use the same relation so downstream consumers can't tell
            # them apart (Webpack / Vite / esbuild treat them as equivalent).
            key = ("imports_from", raw)
            if not raw or key in seen:
                continue
            seen.add(key)
            edges.append(Edge(
                source=file_path,
                target=raw,
                relation="imports_from",
                confidence="EXTRACTED",
                confidence_score=1.0,
                source_file=file_path,
            ))

    return edges
