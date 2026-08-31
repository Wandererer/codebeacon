"""Lightweight .NET project-file extractors.

Tree-sitter has no grammar for MSBuild XML or Razor templates, so the
generic SCM pipeline can't reach these files. We parse them with the
stdlib instead and emit ``Edge`` objects that fit the existing graph.

What we capture:

* ``.sln``      → ``ProjectReference``-style edges to every nested project
                  file declared in ``Project(...) = "Name", "Path", "{GUID}"``
                  lines.
* ``.csproj`` / ``.fsproj`` / ``.vbproj``
                → ``<ProjectReference Include="...">`` and
                  ``<PackageReference Include="..." Version="...">`` edges.
* ``.razor`` / ``.cshtml``
                → ``@inherits``, ``@inject Type name`` and ``@using``
                  directives as ``references`` edges so Blazor pages link
                  to their backing types.

Mirrors graphify #8bcfffd. The output relations are the same names the
existing graph layer already understands (``imports_from`` /
``references``).

KNOWN LIMITATION — these edges do not currently reach the built graph.
``_remap_import_edges`` resolves an edge by mapping its endpoints to
declaration nodes, and a ``.sln`` / ``.csproj`` / ``.razor`` file declares
nothing, so BOTH endpoints of a project reference are unresolvable and the
edge is dropped. Fanning out to the declarations under each project
directory is not an acceptable substitute: that is |A decls| x |B decls|
edges per reference, the same per-declaration inflation the import fan-out
gate was added to remove. The honest fix is a node for the manifest itself,
so a reference becomes one edge between two real nodes — deferred as the
cross-ecosystem "package-manifest nodes" feature (package.json, pom.xml,
go.mod and this, decided as one), because doing it for .NET alone would
fork the node model.

This module is kept, not deleted, because it becomes live the moment that
tier lands with no change here: targets are already emitted scan-root-
relative (never absolute), which is exactly the join key a manifest node
would need.
"""
from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from codebeacon.common.types import Edge


_DOTNET_PROJ_EXTS = frozenset({".csproj", ".fsproj", ".vbproj"})
_RAZOR_EXTS = frozenset({".razor", ".cshtml"})

# Entity-expansion screen for the one XML parse site in the package.
#
# ElementTree refuses EXTERNAL entities outright (no file disclosure, no SSRF),
# and expat >= 2.4 caps internal expansion at ~10^4x, so a hostile .csproj costs
# a bounded few MB rather than the classic billion-laughs. But
# requires-python ">=3.10" admits runtimes linking expat < 2.4, where that cap
# does not exist and the expansion is unbounded — so refuse the document before
# it reaches the parser. A three-line stdlib screen is preferred over a
# defusedxml dependency: codebeacon is positioned for local/air-gapped use and
# this is the only XML parse in the package.
_PROJECT_XML_UNSAFE_RE = re.compile(r"<!(DOCTYPE|ENTITY)", re.IGNORECASE)

# .sln line: Project("{GUID}") = "Name", "relative/path.csproj", "{GUID}"
_SLN_PROJECT_RE = re.compile(
    r'^Project\("[^"]+"\)\s*=\s*"[^"]+"\s*,\s*"([^"]+)"\s*,\s*"[^"]+"\s*$',
    re.MULTILINE,
)

# Razor directives: @inherits Foo, @inject Bar Baz, @using Some.Namespace
_RAZOR_INHERITS_RE = re.compile(r"^\s*@inherits\s+([\w\.<>]+)", re.MULTILINE)
_RAZOR_INJECT_RE = re.compile(r"^\s*@inject\s+([\w\.<>]+)\s+\w+", re.MULTILINE)
_RAZOR_USING_RE = re.compile(r"^\s*@using\s+([\w\.]+)", re.MULTILINE)


def extract_dotnet_edges(file_path: str) -> list[Edge]:
    """Dispatch on extension; return Edge list (empty if unsupported)."""
    ext = Path(file_path).suffix.lower()
    if ext == ".sln":
        return _extract_sln(file_path)
    if ext in _DOTNET_PROJ_EXTS:
        return _extract_csproj(file_path)
    if ext in _RAZOR_EXTS:
        return _extract_razor(file_path)
    return []


def _read_text(file_path: str) -> str:
    try:
        return Path(file_path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _project_ref_target(raw: str) -> str:
    """Normalise a project reference into a path relative to the referring file.

    ``..\\Core\\Core.csproj`` → ``../Core/Core.csproj``. Deliberately NOT
    resolved to an absolute path: an absolute target is machine-specific, and
    absolute paths must never be able to reach a serialised artifact. Nothing
    is lost — a consumer that wants to follow the reference already has the
    referring file on ``Edge.source_file`` to join against, and downstream label
    matching only ever reads the final path segment.
    """
    return posixpath.normpath(raw.replace("\\", "/").strip())


def _make_edge(source: str, target: str, relation: str) -> Edge:
    return Edge(
        source=source,
        target=target,
        relation=relation,
        confidence="EXTRACTED",
        confidence_score=1.0,
        source_file=source,
    )


def _extract_sln(file_path: str) -> list[Edge]:
    text = _read_text(file_path)
    edges: list[Edge] = []
    seen: set[str] = set()

    for m in _SLN_PROJECT_RE.finditer(text):
        # Normalised relative to the .sln, so downstream label matching picks
        # up the real .csproj basename even if Windows backslashes were used.
        target = _project_ref_target(m.group(1))
        if not target or target in seen:
            continue
        seen.add(target)
        edges.append(_make_edge(file_path, target, "imports_from"))
    return edges


def _extract_csproj(file_path: str) -> list[Edge]:
    text = _read_text(file_path)
    if not text:
        return []
    if _PROJECT_XML_UNSAFE_RE.search(text):
        return []  # DOCTYPE/ENTITY declaration — see _PROJECT_XML_UNSAFE_RE
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()

    # MSBuild files sometimes carry a default namespace; iter() with a
    # local-name match is the simplest way to find elements regardless.
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        include = el.attrib.get("Include")
        if not include:
            continue
        if tag == "ProjectReference":
            target = _project_ref_target(include)
            key = ("imports_from", target)
            if key in seen:
                continue
            seen.add(key)
            edges.append(_make_edge(file_path, target, "imports_from"))
        elif tag == "PackageReference":
            key = ("imports_from", include)
            if key in seen:
                continue
            seen.add(key)
            edges.append(_make_edge(file_path, include, "imports_from"))
    return edges


def _extract_razor(file_path: str) -> list[Edge]:
    text = _read_text(file_path)
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()

    def _emit(target: str, relation: str) -> None:
        name = target.rsplit(".", 1)[-1]
        key = (relation, name)
        if not name or key in seen:
            return
        seen.add(key)
        edges.append(_make_edge(file_path, name, relation))

    for m in _RAZOR_INHERITS_RE.finditer(text):
        _emit(m.group(1), "references")
    for m in _RAZOR_INJECT_RE.finditer(text):
        _emit(m.group(1), "references")
    for m in _RAZOR_USING_RE.finditer(text):
        # @using brings a namespace into scope; record it as imports_from on
        # the namespace name (not class) so symbol resolution can still link
        # it to a class node when present. Unlike _emit we keep the *full*
        # namespace, but still dedupe so repeated @using directives in one
        # file don't emit duplicate edges.
        ns = m.group(1)
        key = ("imports_from", ns)
        if ns and key not in seen:
            seen.add(key)
            edges.append(_make_edge(file_path, ns, "imports_from"))
    return edges
