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
``references``), so no downstream changes are needed.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from codebeacon.common.types import Edge


_DOTNET_PROJ_EXTS = frozenset({".csproj", ".fsproj", ".vbproj"})
_RAZOR_EXTS = frozenset({".razor", ".cshtml"})

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
    base = Path(file_path).parent

    for m in _SLN_PROJECT_RE.finditer(text):
        raw = m.group(1).replace("\\", "/").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        # Resolve relative to the .sln so downstream label matching can pick
        # up the real .csproj basename even if Windows backslashes were used.
        try:
            resolved = (base / raw).resolve().as_posix()
        except OSError:
            resolved = raw
        edges.append(_make_edge(file_path, resolved, "imports_from"))
    return edges


def _extract_csproj(file_path: str) -> list[Edge]:
    text = _read_text(file_path)
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    base = Path(file_path).parent

    # MSBuild files sometimes carry a default namespace; iter() with a
    # local-name match is the simplest way to find elements regardless.
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        include = el.attrib.get("Include")
        if not include:
            continue
        if tag == "ProjectReference":
            raw = include.replace("\\", "/").strip()
            try:
                target = (base / raw).resolve().as_posix()
            except OSError:
                target = raw
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
        # it to a class node when present.
        edges.append(_make_edge(file_path, m.group(1), "imports_from"))
    return edges
