"""Edge and node filters for graph cleanup.

Three main filters applied after Pass-2 symbol resolution:
1. filter_build_artifacts() — Remove nodes from build output dirs
2. filter_cross_language() — Remove spurious cross-language import edges
3. filter_cross_service() — Remove false cross-service edges (preserve calls_api, shares_db_entity)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from codebeacon.common.types import Edge, Node

# Build artifact directories to exclude (checked against any path segment)
_ARTIFACT_DIRS: frozenset[str] = frozenset({
    "target", "build", "dist", "node_modules", ".next", ".nuxt",
    "out", "output", "__pycache__", ".gradle", "vendor",
    "bin", "obj", ".dart_tool", ".build", ".cache",
})

# Language families keyed by source-file extension. Two files whose extensions
# fall in *different* families can never legitimately share an ``import`` edge —
# an ``import time`` in Python must not bind to a TS ``time`` component just
# because the bare names collide. Extensions with no family here are treated as
# "unknown" and never trigger a cross-language drop (conservative).
_LANG_FAMILIES: dict[str, str] = {
    ".java": "jvm", ".kt": "jvm", ".kts": "jvm",
    ".ts": "web", ".tsx": "web", ".js": "web",
    ".jsx": "web", ".mjs": "web", ".cjs": "web",
    ".py": "python", ".pyi": "python",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".cs": "csharp",
    ".swift": "swift",
    ".php": "php",
}


def lang_family(ext: str) -> Optional[str]:
    """Return the language family for a file extension, or None if unknown."""
    return _LANG_FAMILIES.get(ext.lower())


def families_compatible(src_ext: str, tgt_ext: str) -> bool:
    """True unless both extensions map to *different* known language families.

    Unknown extensions (no family) are always compatible, so the guard only
    drops an edge when it is provably cross-language.
    """
    src_fam = lang_family(src_ext)
    tgt_fam = lang_family(tgt_ext)
    return not (src_fam and tgt_fam and src_fam != tgt_fam)


# Relations to always preserve regardless of filter logic
_PRESERVE_RELATIONS: frozenset[str] = frozenset({"calls_api", "shares_db_entity"})

# Import-type relations that the cross-service filter operates on
_IMPORT_RELATIONS: frozenset[str] = frozenset({"imports", "imports_from"})

# Import-type relations the cross-language filter inspects. ``re_exports`` is
# included here (but NOT in _IMPORT_RELATIONS) so a barrel re-export that
# collides across languages is dropped too — it previously bypassed the guard
# entirely.
_CROSS_LANG_RELATIONS: frozenset[str] = frozenset({"imports", "imports_from", "re_exports"})

# Shared library directory markers (heuristic)
_SHARED_MARKERS: frozenset[str] = frozenset({
    "shared", "common", "lib", "libs", "core", "utils", "util", "commons", "base",
})


def _project_relative_parts(source_file: str, root: Optional[str]) -> tuple[str, ...]:
    """Path segments of ``source_file`` *below* its project root.

    ``source_file`` reaches these filters as an absolute machine path (the
    scanner resolves it), so its ancestor directories — the checkout location,
    a CI workspace, a home folder — lie OUTSIDE the scanned project and must
    never be judged by directory-name heuristics. A repo checked out under
    ``/opt/ci/build/…`` or ``~/workspace/core/…`` would otherwise have every
    node's path match a build-artifact / shared-lib marker.

    When ``root`` is known and ``source_file`` sits under it, only the
    in-project segments are returned. Otherwise (relative path, unknown root,
    or a path outside the root) the full segment list is returned unchanged —
    which is correct for the already-relative paths the extractors sometimes
    hand us.
    """
    if root and os.path.isabs(source_file):
        try:
            rel = os.path.relpath(source_file, os.path.abspath(root))
        except ValueError:
            return Path(source_file).parts
        if rel != ".." and not rel.startswith(".." + os.sep):
            return Path(rel).parts
    return Path(source_file).parts


def _node_root(node: Node, project_roots: Optional[dict[str, str]]) -> Optional[str]:
    """Look up a node's project root path via its ``project`` metadata."""
    if not project_roots:
        return None
    proj = (node.metadata or {}).get("project") if node.metadata else None
    return project_roots.get(proj) if proj else None


def filter_build_artifacts(
    nodes: list[Node],
    edges: list[Edge],
    project_roots: Optional[dict[str, str]] = None,
) -> tuple[list[Node], list[Edge]]:
    """Remove nodes whose source_file is inside a build artifact directory.

    Also removes any edges that reference removed node IDs.

    Only path segments *inside* each node's project root are tested — an
    ancestor directory that merely happens to be named ``build``/``dist``/etc.
    (e.g. a repo checked out under ``/opt/ci/build/…``) must not erase the
    whole graph. ``project_roots`` maps project name → absolute root path.

    Returns:
        (clean_nodes, clean_edges)
    """
    artifact_ids: set[str] = set()
    clean_nodes: list[Node] = []

    for node in nodes:
        parts = _project_relative_parts(node.source_file, _node_root(node, project_roots))
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

    Any ``imports``/``imports_from``/``re_exports`` edge between two files whose
    extensions belong to *different* known language families is a bare-name
    collision, not a real dependency, and is dropped. (Previously only the
    hardcoded Java↔TS pair was caught, and ``re_exports`` bypassed the guard
    entirely.)

    Preserves:
    - calls_api, shares_db_entity (cross-service HTTP/DB)
    - Non-import relations (calls, injects, etc.)
    - Same-family and unknown-family edges (conservative)

    Args:
        edges: list of all edges
        nodes: node_id → Node mapping
    """
    result: list[Edge] = []
    for edge in edges:
        if edge.relation in _PRESERVE_RELATIONS:
            result.append(edge)
            continue

        if edge.relation not in _CROSS_LANG_RELATIONS:
            result.append(edge)
            continue

        src_node = nodes.get(edge.source)
        tgt_node = nodes.get(edge.target)
        if not src_node or not tgt_node:
            result.append(edge)
            continue

        src_ext = Path(src_node.source_file).suffix.lower()
        tgt_ext = Path(tgt_node.source_file).suffix.lower()

        # Different language families ⇒ spurious import; drop it.
        if not families_compatible(src_ext, tgt_ext):
            continue

        result.append(edge)
    return result


def filter_cross_service(
    edges: list[Edge],
    nodes: dict[str, Node],
    service_roots: dict[str, str],  # node_id → service/project name
    project_roots: Optional[dict[str, str]] = None,  # project name → root path
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
        if tgt_node and _is_shared_lib(
            tgt_node.source_file, _node_root(tgt_node, project_roots)
        ):
            result.append(edge)
            continue

        # Different service import to non-shared target → drop (likely false edge)

    return result


def _is_shared_lib(file_path: str, root: Optional[str] = None) -> bool:
    """Heuristic: is this file in a shared/common/lib directory?

    Only segments *below* the project root are considered — an ancestor
    directory named ``core``/``common``/``lib`` (a checkout under
    ``~/workspace/core/…``) must not make every target look shared and defeat
    the filter's whole purpose.
    """
    parts = {p.lower() for p in _project_relative_parts(file_path, root)}
    return bool(parts & _SHARED_MARKERS)
