"""tree-sitter Language/Parser management.

API note: tree-sitter 0.25+ uses QueryCursor for running queries.
  Query(language, pattern) → QueryCursor(query) → cursor.matches(node)
  Each match is (pattern_idx, {capture_name: [Node, ...]}).

Grammar packages: tree-sitter-python, tree-sitter-java, etc.
If a grammar is not installed, that language is gracefully skipped with a warning.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Iterator, Optional

from tree_sitter import Language, Parser, Query, QueryCursor, Node

# ── Grammar registry ─────────────────────────────────────────────────────────

_LANG_CACHE: dict[str, Optional[Language]] = {}

_GRAMMAR_MODULES: dict[str, str] = {
    "python":     "tree_sitter_python",
    "java":       "tree_sitter_java",
    "kotlin":     "tree_sitter_kotlin",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "tsx":        "tree_sitter_typescript",
    "go":         "tree_sitter_go",
    "ruby":       "tree_sitter_ruby",
    "php":        "tree_sitter_php",
    "csharp":     "tree_sitter_c_sharp",
    "rust":       "tree_sitter_rust",
    "swift":      "tree_sitter_swift",
    "html":       "tree_sitter_html",
    "svelte":     "tree_sitter_svelte",
}

# Query files that are only valid for specific grammar families.
# Keys are query file stems (e.g. "nestjs"); values are sets of grammar names
# that the query can compile against. If a file's grammar is not in this set,
# the extractor skips running the query rather than emitting a warning.
QUERY_GRAMMAR_ALLOWLIST: dict[str, frozenset[str]] = {
    # TypeScript/JavaScript families
    "react":       frozenset({"typescript", "tsx", "javascript"}),
    "svelte":      frozenset({"typescript", "tsx", "javascript"}),
    "nestjs":      frozenset({"typescript", "tsx"}),
    "angular":     frozenset({"typescript", "tsx"}),
    "express":     frozenset({"typescript", "tsx", "javascript"}),
    "vue":         frozenset({"typescript", "tsx", "javascript"}),
    # Python families
    "fastapi":     frozenset({"python"}),
    "django":      frozenset({"python"}),
    "flask":       frozenset({"python"}),
    # JVM families
    "spring_boot": frozenset({"java", "kotlin"}),
    "ktor":        frozenset({"kotlin"}),
    # Other single-language families
    "gin":         frozenset({"go"}),
    "rails":       frozenset({"ruby"}),
    "laravel":     frozenset({"php"}),
    "aspnet":      frozenset({"csharp"}),
    "actix":       frozenset({"rust"}),
    "vapor":       frozenset({"swift"}),
}

# Extensions that map to a grammar name
EXT_TO_GRAMMAR: dict[str, str] = {
    ".py":    "python",
    ".java":  "java",
    ".kt":    "kotlin",
    ".kts":   "kotlin",
    ".js":    "javascript",
    ".jsx":   "javascript",
    ".mjs":   "javascript",
    ".cjs":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "tsx",
    ".go":    "go",
    ".rb":    "ruby",
    ".php":   "php",
    ".cs":    "csharp",
    ".rs":    "rust",
    ".swift": "swift",
    ".html":  "html",
    ".svelte":"svelte",
    # Vue: SFC section extraction → use typescript + html
    ".vue":   "_vue_sfc",
}


def is_grammar_allowed(query_name: str, lang: Language) -> bool:
    """Return True if *lang* is compatible with the given query file.

    Uses QUERY_GRAMMAR_ALLOWLIST; if the query is not listed, all grammars are
    allowed (unknown queries fall through gracefully).
    """
    allowed = QUERY_GRAMMAR_ALLOWLIST.get(query_name)
    if allowed is None:
        return True  # no restriction defined — attempt the query
    # Reverse-lookup the grammar name from the cached Language object
    gram_name = next((k for k, v in _LANG_CACHE.items() if v is lang), None)
    if gram_name is None:
        return True  # can't determine — let it run
    return gram_name in allowed


def get_language(name: str) -> Optional[Language]:
    """Return a Language object for the given grammar name, or None if not installed."""
    if name in _LANG_CACHE:
        return _LANG_CACHE[name]

    module_name = _GRAMMAR_MODULES.get(name)
    if not module_name:
        _LANG_CACHE[name] = None
        return None

    try:
        mod = __import__(module_name)
        # Some packages expose dialect-specific functions instead of language()
        if name == "php":
            lang = Language(mod.language_php())
        elif name == "typescript":
            # tree-sitter-typescript: language_typescript() / language_tsx()
            lang = Language(mod.language_typescript())
        elif name == "tsx":
            import tree_sitter_typescript as _tsts
            lang = Language(_tsts.language_tsx())
        elif name == "kotlin":
            # tree-sitter-kotlin may expose language_kotlin or language
            fn = getattr(mod, "language_kotlin", None) or getattr(mod, "language", None)
            lang = Language(fn())
        else:
            lang = Language(mod.language())
        _LANG_CACHE[name] = lang
        return lang
    except (ImportError, AttributeError):
        warnings.warn(
            f"Grammar '{name}' not installed. "
            f"Install with: pip install codebeacon[{_pip_extra(name)}]",
            stacklevel=3,
        )
        _LANG_CACHE[name] = None
        return None


def _pip_extra(name: str) -> str:
    extras = {
        "java": "java", "kotlin": "kotlin",
        "python": "python",
        "javascript": "js", "typescript": "js",
        "go": "go", "ruby": "ruby", "php": "php",
        "csharp": "csharp", "rust": "rust",
        "swift": "swift", "html": "html", "svelte": "svelte",
    }
    return extras.get(name, name)


def get_parser(grammar: str) -> Optional[Parser]:
    """Return a Parser configured for the given grammar, or None."""
    lang = get_language(grammar)
    if lang is None:
        return None
    return Parser(lang)


# ── Query helpers ─────────────────────────────────────────────────────────────

QueryMatch = tuple[int, dict[str, list[Node]]]  # (pattern_idx, captures)


def run_query(language: Language, pattern: str, node: Node) -> list[QueryMatch]:
    """Run a tree-sitter query and return all matches.

    Returns list of (pattern_index, {capture_name: [Node, ...]}).
    """
    try:
        q = Query(language, pattern)
        cursor = QueryCursor(q)
        return list(cursor.matches(node))
    except Exception as e:
        warnings.warn(f"Query error: {e}", stacklevel=2)
        return []


def query_captures_flat(language: Language, pattern: str, node: Node) -> list[tuple[str, Node]]:
    """Convenience: return flat list of (capture_name, Node) pairs from all matches."""
    result: list[tuple[str, Node]] = []
    for _idx, captures in run_query(language, pattern, node):
        for name, nodes in captures.items():
            for n in nodes:
                result.append((name, n))
    return result


def load_query_file(grammar: str) -> Optional[str]:
    """Load the .scm query file for a grammar from extract/queries/."""
    queries_dir = Path(__file__).parent / "queries"
    scm_path = queries_dir / f"{grammar}.scm"
    if scm_path.exists():
        return scm_path.read_text(encoding="utf-8")
    return None


# ── File parsing ──────────────────────────────────────────────────────────────

def parse_file(file_path: str) -> Optional[tuple[Node, Language]]:
    """Parse a source file and return (root_node, language).

    For .vue files, returns None — use extract_vue_sections() instead.
    """
    ext = Path(file_path).suffix.lower()
    grammar = EXT_TO_GRAMMAR.get(ext)

    if grammar is None:
        return None
    if grammar == "_vue_sfc":
        return None  # handled separately

    lang = get_language(grammar)
    if lang is None:
        return None

    try:
        content = Path(file_path).read_bytes()
        parser = Parser(lang)
        tree = parser.parse(content)
        return (tree.root_node, lang)
    except (OSError, UnicodeDecodeError, Exception):
        return None


def parse_source(source: bytes, grammar: str) -> Optional[tuple[Node, Language]]:
    """Parse raw bytes with the given grammar."""
    lang = get_language(grammar)
    if lang is None:
        return None
    parser = Parser(lang)
    tree = parser.parse(source)
    return (tree.root_node, lang)


# ── SFC section extraction (Vue / Svelte) ────────────────────────────────────

_SCRIPT_RE = re.compile(
    r"<script(?:\s[^>]*)?>(.+?)</script>",
    re.DOTALL | re.IGNORECASE,
)
_TEMPLATE_RE = re.compile(
    r"<template(?:\s[^>]*)?>(.+?)</template>",
    re.DOTALL | re.IGNORECASE,
)
_SCRIPT_LANG_RE = re.compile(r'lang=["\'](\w+)["\']', re.IGNORECASE)


class SFCSection:
    __slots__ = ("script_src", "script_lang", "script_offset", "template_src", "template_offset")

    def __init__(
        self,
        script_src: bytes,
        script_lang: str,
        script_offset: int,
        template_src: bytes,
        template_offset: int,
    ) -> None:
        self.script_src = script_src
        self.script_lang = script_lang        # "ts" or "js"
        self.script_offset = script_offset    # byte offset in original file
        self.template_src = template_src
        self.template_offset = template_offset


def extract_sfc_sections(file_path: str) -> Optional[SFCSection]:
    """Extract <script> and <template> sections from a .vue or .svelte SFC file."""
    try:
        raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Script section
    script_match = _SCRIPT_RE.search(raw)
    script_src = b""
    script_lang = "js"
    script_offset = 0
    if script_match:
        # Detect lang attribute on <script> tag
        tag_content = raw[script_match.start():script_match.start(1)]
        lang_m = _SCRIPT_LANG_RE.search(tag_content)
        if lang_m and lang_m.group(1).lower() in ("ts", "typescript"):
            script_lang = "ts"
        script_src = script_match.group(1).encode("utf-8", errors="replace")
        script_offset = script_match.start(1)

    # Template section
    template_match = _TEMPLATE_RE.search(raw)
    template_src = b""
    template_offset = 0
    if template_match:
        template_src = template_match.group(1).encode("utf-8", errors="replace")
        template_offset = template_match.start(1)

    return SFCSection(
        script_src=script_src,
        script_lang=script_lang,
        script_offset=script_offset,
        template_src=template_src,
        template_offset=template_offset,
    )


def parse_sfc_script(sfc: SFCSection) -> Optional[tuple[Node, Language]]:
    """Parse the <script> section of an SFC using typescript or javascript grammar."""
    grammar = "typescript" if sfc.script_lang == "ts" else "javascript"
    return parse_source(sfc.script_src, grammar)


def parse_sfc_template(sfc: SFCSection) -> Optional[tuple[Node, Language]]:
    """Parse the <template> section of an SFC using the html grammar."""
    return parse_source(sfc.template_src, "html")


# ── Utility ───────────────────────────────────────────────────────────────────

def node_text(node: Node) -> str:
    """Return the UTF-8 decoded text of a node."""
    return (node.text or b"").decode("utf-8", errors="replace")


def first_child_of_type(node: Node, *types: str) -> Optional[Node]:
    """Return first named child matching any of the given types."""
    for child in node.named_children:
        if child.type in types:
            return child
    return None


def find_nodes_by_type(root: Node, node_type: str) -> list[Node]:
    """DFS: collect all nodes of a given type."""
    result: list[Node] = []
    _dfs_collect(root, node_type, result)
    return result


def _dfs_collect(node: Node, target_type: str, result: list[Node]) -> None:
    if node.type == target_type:
        result.append(node)
    for child in node.children:
        _dfs_collect(child, target_type, result)


def get_annotation_names(node: Node) -> list[str]:
    """Extract annotation/decorator names from a modifiers/decorators node."""
    names: list[str] = []
    for child in node.named_children:
        if child.type == "annotation":
            name_node = child.child_by_field_name("name")
            if name_node:
                names.append(node_text(name_node))
        elif child.type in ("decorator",):
            # Python/TS decorators: @name or @name(...)
            expr = child.named_children[0] if child.named_children else None
            if expr:
                if expr.type == "identifier":
                    names.append(node_text(expr))
                elif expr.type == "call":
                    func = expr.child_by_field_name("function")
                    if func:
                        names.append(node_text(func))
    return names
