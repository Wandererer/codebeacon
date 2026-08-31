"""Edge and node filters for graph cleanup.

Three main filters applied after Pass-2 symbol resolution:
1. filter_build_artifacts() — Remove nodes from build output dirs
2. filter_cross_language() — Remove spurious cross-language import edges
3. filter_cross_service() — Remove false cross-service edges (preserve calls_api, shares_db_entity)
"""

from __future__ import annotations

import os
import sys
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


# ── Language runtime / stdlib guards ──────────────────────────────────────────
#
# A bare-name import target is matched against declaration labels, so any user
# type sharing a name with a runtime type becomes an instant fabricated hub:
# ``com/ex/model/List.java`` collected four ``imports_from`` edges from files
# that only ever wrote ``import java.util.List`` (G-0916-14), and the same holds
# for Swift/Foundation (G-0927-11) and PHP/Illuminate (G-0941-11).
#
# Every set below is keyed by *language family* and consulted only for imports
# emitted from a file of that family — a global deny list would silently erase a
# legitimate ``Foundation`` class in a Java repo (GI-2313's caveat). An unknown
# family denies nothing.
#
# These guards run only AFTER path resolution has failed to place the import on
# a scanned file, so a project that genuinely declares ``com/ex/model/List.java``
# and imports it by its real package path still binds.

_RUNTIME_PREFIXES: dict[str, tuple[str, ...]] = {
    "jvm": ("java.", "javax.", "jakarta.", "kotlin.", "kotlinx.", "android.",
            "androidx.", "sun.", "scala.", "groovy."),
    "csharp": ("System.", "Microsoft.", "Windows."),
    # PHP namespace separators are normalised to "/" before this is consulted.
    "php": ("Illuminate/", "Symfony/", "Psr/", "Doctrine/", "PHPUnit/",
            "Laravel/", "Spatie/"),
    "rust": ("std::", "core::", "alloc::", "std/", "core/", "alloc/"),
    "web": ("node:", "next/", "@angular/", "@nestjs/", "react-native/"),
    "swift": (),
    "python": (),
    "go": (),
    "ruby": (),
}

_RUNTIME_MODULES: dict[str, frozenset[str]] = {
    "web": frozenset({
        # Node builtins (also reachable via the "node:" prefix above)
        "fs", "path", "os", "http", "https", "url", "util", "events", "stream",
        "crypto", "buffer", "child_process", "zlib", "net", "tls", "dns",
        "assert", "querystring", "readline", "worker_threads", "perf_hooks",
        "timers", "process", "module", "vm", "cluster", "string_decoder",
        # Framework entry points whose last path segment collides with common
        # component names ("next/link" → "link", "react-dom" → "dom").
        "react", "react-dom", "react-router", "react-router-dom", "vue",
        "svelte", "next", "express", "@angular/core", "rxjs",
    }),
    "swift": frozenset({
        "Foundation", "UIKit", "SwiftUI", "Combine", "CoreData", "AppKit",
        "XCTest", "Dispatch", "OSLog", "CoreGraphics", "AVFoundation",
        "MapKit", "WidgetKit", "Security", "Network", "CryptoKit",
    }),
    "ruby": frozenset({
        "json", "yaml", "set", "time", "date", "uri", "logger", "fileutils",
        "digest", "securerandom", "openssl", "csv", "erb", "ostruct",
        "pathname", "stringio", "benchmark", "socket", "tempfile", "net/http",
    }),
    # Python's real stdlib list ships with the interpreter (3.10+).
    "python": frozenset(getattr(sys, "stdlib_module_names", ())),
    # Go has no import-path marker that separates the standard library from a
    # module path: "fmt" and "myapp/internal/db" are the same shape. The
    # tempting rule — "a first segment without a dot is stdlib" — condemns every
    # import of a module declared as `module myapp` (still normal in private
    # code; the indexed shotgun_code repo is one), so the standard library is
    # enumerated instead. Judged by first segment, so "net/http" and
    # "encoding/json" are covered by "net" and "encoding".
    #
    # ``internal`` and ``builtin`` are deliberately absent: user code cannot
    # import either from the standard library, while ``internal`` is one of the
    # most common first segments in real Go projects.
    "go": frozenset({
        "archive", "bufio", "bytes", "cmp", "compress", "container", "context",
        "crypto", "database", "debug", "embed", "encoding", "errors", "expvar",
        "flag", "fmt", "go", "hash", "html", "image", "index", "io", "iter",
        "log", "maps", "math", "mime", "net", "os", "path", "plugin", "reflect",
        "regexp", "runtime", "slices", "sort", "strconv", "strings", "structs",
        "sync", "syscall", "testing", "text", "time", "unicode", "unique",
        "unsafe", "weak",
    }),
}

# Supertype names that must never invert into an interface→impl mapping.
#
# ``class AppError extends Exception`` registered ``Exception → [AppError]``, so
# any later reference to a bare ``Exception`` resolved to that unrelated class
# (G-0949-15). These names are generic bases in every language we parse, so the
# core set is shared; per-family extras cover framework base classes.
_GENERIC_SUPERTYPES: frozenset[str] = frozenset({
    "Object", "object", "Exception", "Error", "Base", "Model", "Controller",
    "Service", "Component", "Entity", "Enum", "Thread", "List", "Map", "Set",
})

_FAMILY_SUPERTYPES: dict[str, frozenset[str]] = {
    "jvm": frozenset({
        "RuntimeException", "Throwable", "Runnable", "Comparable", "Serializable",
        "Cloneable", "Iterable", "Collection", "Number", "Record", "AbstractList",
        "ArrayList", "HashMap", "JpaRepository", "CrudRepository", "Any",
    }),
    "python": frozenset({
        "BaseException", "ABC", "ABCMeta", "Protocol", "TypedDict", "NamedTuple",
        "Generic", "IntEnum", "StrEnum", "TestCase", "BaseModel", "Thread",
    }),
    "web": frozenset({
        "PureComponent", "HTMLElement", "Array", "Promise", "EventEmitter",
        "Event", "Element", "Node",
    }),
    "csharp": frozenset({
        "ControllerBase", "DbContext", "IDisposable", "Attribute", "ValueType",
        "IEquatable", "IComparable", "INotifyPropertyChanged", "PageModel",
        "EventArgs",
    }),
    "php": frozenset({
        "Throwable", "Middleware", "ServiceProvider", "Command", "Request",
        "FormRequest", "Resource", "Migration", "Seeder", "TestCase", "Facade",
    }),
    "ruby": frozenset({
        "StandardError", "ApplicationRecord", "ApplicationController",
        "ActiveRecord::Base", "Struct", "Module", "Class", "Hash", "Array",
    }),
    "swift": frozenset({
        "NSObject", "Codable", "Decodable", "Encodable", "Equatable", "Hashable",
        "Identifiable", "View", "ObservableObject", "UIViewController",
        "UIView", "Sendable",
    }),
    "go": frozenset({"error"}),
    "rust": frozenset({
        "Default", "Clone", "Debug", "Display", "Iterator", "From", "Into",
        "Copy", "Send", "Sync",
    }),
}


def _normalise_import(raw_import: str) -> str:
    """Strip decoration a language puts around an import path.

    PHP namespaces use ``\\`` and may carry a leading root separator; treating
    them as ``/`` lets one set of prefix rules cover every language.
    """
    text = raw_import.strip().strip("'\"")
    if "\\" in text:
        text = text.replace("\\", "/")
    return text.lstrip("/")


def is_runtime_import(raw_import: str, src_ext: str) -> bool:
    """True when ``raw_import`` names the language's own runtime / stdlib.

    ``src_ext`` is the extension of the *importing* file — the deny set is
    scoped to that file's language family and nothing else.
    """
    fam = lang_family(src_ext)
    if not fam or not raw_import:
        return False
    text = _normalise_import(raw_import)
    if not text:
        return False

    for prefix in _RUNTIME_PREFIXES.get(fam, ()):  # noqa: SIM110 — explicit is clearer
        if text.startswith(prefix):
            return True

    modules = _RUNTIME_MODULES.get(fam)
    if modules:
        if text in modules:
            return True
        # ``os.path`` / ``net/http`` — judge by the owning top-level module.
        head_dot = text.split(".", 1)[0]
        head_slash = text.split("/", 1)[0]
        if fam == "python" and head_dot in modules:
            return True
        if fam in ("web", "ruby", "swift", "go") and head_slash in modules:
            return True

    return False


def is_generic_supertype(name: str, src_ext: str) -> bool:
    """True when ``name`` is a language/framework base type, not a user interface.

    Used to keep the interface→impl map from inverting ``extends Exception``
    into "every error class implements Exception" (G-0949-15).
    """
    if not name:
        return False
    if name in _GENERIC_SUPERTYPES:
        return True
    fam = lang_family(src_ext)
    return bool(fam and name in _FAMILY_SUPERTYPES.get(fam, frozenset()))


def is_shared_lib(file_path: str, root: Optional[str] = None) -> bool:
    """Public alias of the shared-library heuristic (see ``_is_shared_lib``)."""
    return _is_shared_lib(file_path, root)


# Relations to always preserve regardless of filter logic
_PRESERVE_RELATIONS: frozenset[str] = frozenset({"calls_api", "shares_db_entity"})

# Import-type relations that the cross-service filter operates on.
#
# ``injects`` is here because DI resolution binds by *type name*: a bare
# ``PaymentClient`` dependency in service `orders` matched a same-named class in
# an unrelated project `billing` and shipped as a full-confidence edge. A DI
# container never wires across service boundaries unless the target is a shared
# library — which this filter already exempts. (audit 0.7.1 R7c / GI-2207)
_IMPORT_RELATIONS: frozenset[str] = frozenset({"imports", "imports_from", "injects"})

# Import-type relations the cross-language filter inspects. ``re_exports`` is
# included here (but NOT in _IMPORT_RELATIONS) so a barrel re-export that
# collides across languages is dropped too — it previously bypassed the guard
# entirely. ``injects`` likewise: a Spring service must never inject a ``.tsx``
# component just because the names collide (R7c).
_CROSS_LANG_RELATIONS: frozenset[str] = frozenset(
    {"imports", "imports_from", "re_exports", "injects"}
)

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
