"""Semantic extraction: structured comment/docstring parsing → Edge objects.

Activated with `--semantic` flag. Parses structured documentation comments
(Javadoc, Python docstrings, JSDoc) to infer additional "references"
relationships between code entities. No LLM is invoked here — LLM-driven
inference is owned by the ``/codebeacon`` skill via
:mod:`codebeacon.semantic_pipeline`, which lets the running agent choose
its own model rather than hardcoding one inside this package.

Public API:
    extract_semantic_refs(file_path, framework, source_node_id="") -> list[Edge]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from codebeacon.common.types import Edge


# ── Patterns ──────────────────────────────────────────────────────────────────

# Javadoc / KDoc: @see ClassName, {@link ClassName#method}, @throws ClassName
_JAVADOC_SEE = re.compile(r"@see\s+([\w.]+)")
_JAVADOC_LINK = re.compile(r"\{@link\s+([\w.#]+)\}")
_JAVADOC_PARAM_TYPE = re.compile(r"@param\s+\{?([\w<>\[\]]+)\}?\s+\w+")
_JAVADOC_THROWS = re.compile(r"@throws\s+([\w.]+)")

# Python docstring: :class:`ClassName`, :func:`name`, :meth:`ClassName.method`
_PY_CROSS_REF = re.compile(r":(?:class|func|meth|exc|attr):`([\w.]+)`")
# "See Also" section in NumPy/Google style docstrings
_PY_SEE_ALSO = re.compile(r"(?:See Also|See also)\s*\n\s*[-–]*\s*\n((?:\s+[\w., ]+\n)+)", re.MULTILINE)
_PY_SEE_ALSO_INLINE = re.compile(r"See[: ]+`?([\w]+)`?")

# JSDoc: @see ClassName, @param {ClassName} name, @returns {ClassName}
_JSDOC_SEE = re.compile(r"@see\s+\{?([\w.]+)\}?")
_JSDOC_TYPE = re.compile(r"@(?:param|returns?|type|throws)\s+\{([\w<>|, ]+)\}")

# Strip leading * from comment lines
_COMMENT_STAR = re.compile(r"^\s*\*+\s?", re.MULTILINE)

# Extract block comments /** ... */ and /* ... */
_BLOCK_COMMENT = re.compile(r"/\*\*?(.*?)\*/", re.DOTALL)
# Extract Python triple-quoted docstrings
_PY_DOCSTRING = re.compile(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'', re.DOTALL)
# Extract line comments // ...
_LINE_COMMENT = re.compile(r"//[^\n]*")
# Extract Python # comments
_PY_LINE_COMMENT = re.compile(r"#[^\n]*")
# Extract Ruby/Shell # comments
_HASH_COMMENT = re.compile(r"#[^\n]*")


def _is_type_name(token: str) -> bool:
    """Heuristic: is this token a meaningful class/type name (not a primitive)?"""
    token = token.strip()
    if not token or len(token) < 2:
        return False
    primitives = {
        "int", "long", "float", "double", "boolean", "void", "string",
        "String", "Integer", "Long", "Float", "Double", "Boolean", "Object",
        "any", "unknown", "never", "undefined", "null", "true", "false",
        "str", "bytes", "list", "dict", "tuple", "set", "bool", "type",
    }
    return token not in primitives and token[0].isupper()


def _make_ref_edge(source_node_id: str, target_name: str, source_file: str) -> Edge:
    return Edge(
        source=source_node_id,
        target=target_name,
        relation="references",
        confidence="INFERRED",
        confidence_score=0.5,
        source_file=source_file,
    )


def _extract_java_refs(content: str, source_node_id: str, source_file: str) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[str] = set()

    for block_match in _BLOCK_COMMENT.finditer(content):
        block = _COMMENT_STAR.sub("", block_match.group(1))

        for m in _JAVADOC_SEE.finditer(block):
            name = m.group(1).split(".")[-1]
            if _is_type_name(name) and name not in seen:
                seen.add(name)
                edges.append(_make_ref_edge(source_node_id, name, source_file))

        for m in _JAVADOC_LINK.finditer(block):
            raw = m.group(1).split("#")[0].split(".")[-1]
            if _is_type_name(raw) and raw not in seen:
                seen.add(raw)
                edges.append(_make_ref_edge(source_node_id, raw, source_file))

        for m in _JAVADOC_THROWS.finditer(block):
            name = m.group(1).split(".")[-1]
            if _is_type_name(name) and name not in seen:
                seen.add(name)
                edges.append(_make_ref_edge(source_node_id, name, source_file))

    return edges


def _extract_python_refs(content: str, source_node_id: str, source_file: str) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[str] = set()

    for ds_match in _PY_DOCSTRING.finditer(content):
        docstring = ds_match.group(1) or ds_match.group(2) or ""

        for m in _PY_CROSS_REF.finditer(docstring):
            name = m.group(1).split(".")[-1]
            if _is_type_name(name) and name not in seen:
                seen.add(name)
                edges.append(_make_ref_edge(source_node_id, name, source_file))

        for m in _PY_SEE_ALSO.finditer(docstring):
            for token in re.split(r"[,\s]+", m.group(1)):
                token = token.strip().rstrip("()")
                if _is_type_name(token) and token not in seen:
                    seen.add(token)
                    edges.append(_make_ref_edge(source_node_id, token, source_file))

    return edges


def _extract_js_refs(content: str, source_node_id: str, source_file: str) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[str] = set()

    for block_match in _BLOCK_COMMENT.finditer(content):
        block = _COMMENT_STAR.sub("", block_match.group(1))

        for m in _JSDOC_SEE.finditer(block):
            name = m.group(1).split(".")[-1]
            if _is_type_name(name) and name not in seen:
                seen.add(name)
                edges.append(_make_ref_edge(source_node_id, name, source_file))

        for m in _JSDOC_TYPE.finditer(block):
            # Handle union types like {UserService | AdminService}
            for part in re.split(r"[|,<> ]+", m.group(1)):
                part = part.strip()
                if _is_type_name(part) and part not in seen:
                    seen.add(part)
                    edges.append(_make_ref_edge(source_node_id, part, source_file))

    return edges


# ── Extension → extractor dispatch ──────────────────────────────────────────

_JAVA_EXTS = frozenset({".java", ".kt", ".kts", ".swift"})
_PY_EXTS = frozenset({".py"})
_JS_EXTS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"})


def extract_semantic_refs(
    file_path: str,
    framework: str,
    source_node_id: str = "",
) -> list[Edge]:
    """Parse structured comments in a source file and return inferred reference edges.

    Args:
        file_path: absolute path to the source file
        framework: detected framework name (used for routing dispatch)
        source_node_id: the node ID that 'owns' these references
                        (defaults to file_path if empty)

    Returns:
        list of Edge objects with relation="references", confidence="INFERRED"
    """
    path = Path(file_path)
    if not path.exists():
        return []

    if not source_node_id:
        source_node_id = str(path)

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    ext = path.suffix.lower()
    if ext in _JAVA_EXTS:
        return _extract_java_refs(content, source_node_id, file_path)
    elif ext in _PY_EXTS:
        return _extract_python_refs(content, source_node_id, file_path)
    elif ext in _JS_EXTS:
        return _extract_js_refs(content, source_node_id, file_path)
    return []
