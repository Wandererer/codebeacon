"""Edge and node filters for graph cleanup.

Three main filters applied after Pass-2 symbol resolution:
1. filter_build_artifacts() — Remove nodes from build output dirs
2. filter_cross_language() — Remove spurious Java↔TS/TSX import edges
3. filter_cross_service() — Remove false cross-service edges (preserve calls_api, shares_db_entity)
"""

from __future__ import annotations

from pathlib import Path

from codebeacon.common.types import Edge, Node

# Build artifact directories to exclude (checked against any path segment)
_ARTIFACT_DIRS: frozenset[str] = frozenset({
    "target", "build", "dist", "node_modules", ".next", ".nuxt",
    "out", "output", "__pycache__", ".gradle", "vendor",
    "bin", "obj", ".dart_tool", ".build", ".cache",
})

# Java/Kotlin file extensions
_JAVA_EXTS: frozenset[str] = frozenset({".java", ".kt", ".kts"})
# TypeScript/JavaScript file extensions
_TS_EXTS: frozenset[str] = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})

# Relations to always preserve regardless of filter logic
_PRESERVE_RELATIONS: frozenset[str] = frozenset({"calls_api", "shares_db_entity"})

# Import-type relations that cross-service/cross-language filters operate on
_IMPORT_RELATIONS: frozenset[str] = frozenset({"imports", "imports_from"})

# Shared library directory markers (heuristic)
_SHARED_MARKERS: frozenset[str] = frozenset({
    "shared", "common", "lib", "libs", "core", "utils", "util", "commons", "base",
})


def filter_build_artifacts(
    nodes: list[Node],
    edges: list[Edge],
) -> tuple[list[Node], list[Edge]]:
    """Remove nodes whose source_file is inside a build artifact directory.

    Also removes any edges that reference removed node IDs.

    Returns:
        (clean_nodes, clean_edges)
    """
    artifact_ids: set[str] = set()
    clean_nodes: list[Node] = []

    for node in nodes:
        parts = Path(node.source_file).parts
        if any(part in _ARTIFACT_DIRS for part in parts):
            artifact_ids.add(node.id)
        else:
            clean_nodes.append(node)

    clean_edges = [
        e for e in edges
        if e.source not in artifact_ids and e.target not in artifact_ids
    ]
    return clean_nodes, clean_edges


def filter_cross_language(
    edges: list[Edge],
    nodes: dict[str, Node],
) -> list[Edge]:
    """Remove spurious cross-language import edges (e.g. Java class importing a TS file).

    Preserves:
    - calls_api, shares_db_entity (cross-service HTTP/DB)
    - Non-import relations (calls, injects, etc.)

    Args:
        edges: list of all edges
        nodes: node_id → Node mapping
    """
    result: list[Edge] = []
    for edge in edges:
        if edge.relation in _PRESERVE_RELATIONS:
            result.append(edge)
            continue

        if edge.relation not in _IMPORT_RELATIONS:
            result.append(edge)
            continue

        src_node = nodes.get(edge.source)
        tgt_node = nodes.get(edge.target)
        if not src_node or not tgt_node:
            result.append(edge)
            continue

        src_ext = Path(src_node.source_file).suffix.lower()
        tgt_ext = Path(tgt_node.source_file).suffix.lower()

        src_java = src_ext in _JAVA_EXTS
        src_ts = src_ext in _TS_EXTS
        tgt_java = tgt_ext in _JAVA_EXTS
        tgt_ts = tgt_ext in _TS_EXTS

        # Java/Kotlin ↔ TypeScript/JavaScript import is always spurious
        if (src_java and tgt_ts) or (src_ts and tgt_java):
            continue

        result.append(edge)
    return result


def filter_cross_service(
    edges: list[Edge],
    nodes: dict[str, Node],
    service_roots: dict[str, str],  # node_id → service/project name
) -> list[Edge]:
    """Remove false cross-service import edges caused by name collisions.

    For example: front-pms/Button ↔ front-pvms/Button should NOT be linked.

    Preserved:
    - calls_api, shares_db_entity (intentional cross-service connections)
    - Non-import relations (calls, injects — kept for cross-service analysis)
    - Edges to shared library nodes (heuristic: path contains 'shared', 'common', etc.)
    - Edges where service affiliation is unknown

    Args:
        edges: list of all edges
        nodes: node_id → Node mapping
        service_roots: node_id → project/service name
    """
    result: list[Edge] = []
    for edge in edges:
        if edge.relation in _PRESERVE_RELATIONS:
            result.append(edge)
            continue

        if edge.relation not in _IMPORT_RELATIONS:
            result.append(edge)
            continue

        src_svc = service_roots.get(edge.source)
        tgt_svc = service_roots.get(edge.target)

        # Unknown affiliation → keep (conservative)
        if not src_svc or not tgt_svc:
            result.append(edge)
            continue

        # Same service → always keep
        if src_svc == tgt_svc:
            result.append(edge)
            continue

        # Different service import: check if target is a shared library
        tgt_node = nodes.get(edge.target)
        if tgt_node and _is_shared_lib(tgt_node.source_file):
            result.append(edge)
            continue

        # Different service import to non-shared target → drop (likely false edge)

    return result


def _is_shared_lib(file_path: str) -> bool:
    """Heuristic: is this file in a shared/common/lib directory?"""
    parts = {p.lower() for p in Path(file_path).parts}
    return bool(parts & _SHARED_MARKERS)
