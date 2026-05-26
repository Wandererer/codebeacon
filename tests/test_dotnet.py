"""Tests for codebeacon.extract.dotnet (`.sln` / `.csproj` / `.razor`).

Mirrors graphify #8bcfffd. .NET project metadata lives in MSBuild XML or
Razor templates — both outside tree-sitter's reach — so we parse them
with the stdlib. These tests pin the *contract* the dispatcher expects:

* every `ProjectReference` and `PackageReference` becomes an edge,
* MSBuild's optional XML namespace doesn't break parsing,
* Razor `@inherits` / `@inject` / `@using` directives are surfaced as
  graph signals so Blazor pages link to their backing types,
* malformed XML is swallowed (returns []), it doesn't crash the wave.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.extract.dotnet import extract_dotnet_edges
from codebeacon.extract.dependencies import extract_dependencies


def _by_relation(edges):
    out = {}
    for e in edges:
        out.setdefault(e.relation, []).append(e.target)
    return out


# ── .sln ─────────────────────────────────────────────────────────────────────

def test_sln_lists_every_project_line(tmp_path):
    sln = tmp_path / "App.sln"
    sln.write_text(
        'Microsoft Visual Studio Solution File, Format Version 12.00\n'
        'Project("{guid1}") = "Web", "src/Web/Web.csproj", "{abc}"\n'
        'EndProject\n'
        'Project("{guid2}") = "Core", "src/Core/Core.csproj", "{def}"\n'
        'EndProject\n'
    )
    edges = extract_dotnet_edges(str(sln))
    targets = [Path(e.target).name for e in edges]
    assert targets == ["Web.csproj", "Core.csproj"]
    assert all(e.relation == "imports_from" for e in edges)


def test_sln_dedupes_repeated_paths(tmp_path):
    sln = tmp_path / "App.sln"
    sln.write_text(
        'Project("{guid}") = "Web", "src/Web/Web.csproj", "{a}"\n'
        'EndProject\n'
        'Project("{guid}") = "Web", "src/Web/Web.csproj", "{a}"\n'
        'EndProject\n'
    )
    assert len(extract_dotnet_edges(str(sln))) == 1


def test_sln_handles_windows_backslashes(tmp_path):
    sln = tmp_path / "App.sln"
    sln.write_text(
        'Project("{guid}") = "Web", "src\\Web\\Web.csproj", "{a}"\n'
        'EndProject\n'
    )
    edges = extract_dotnet_edges(str(sln))
    assert edges and edges[0].target.endswith("src/Web/Web.csproj")


# ── .csproj / .fsproj / .vbproj ──────────────────────────────────────────────

CSPROJ_SAMPLE = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
    <PackageReference Include="Serilog" Version="3.0.0" />
    <ProjectReference Include="..\\Core\\Core.csproj" />
  </ItemGroup>
</Project>
"""


def test_csproj_captures_package_and_project_references(tmp_path):
    proj = tmp_path / "Web.csproj"
    proj.write_text(CSPROJ_SAMPLE)
    edges = extract_dotnet_edges(str(proj))
    targets = sorted(Path(e.target).name for e in edges)
    # Three Includes: 2 packages + 1 ProjectReference
    assert "Newtonsoft.Json" in targets
    assert "Serilog" in targets
    assert any(t.endswith("Core.csproj") for t in targets)


def test_csproj_with_msbuild_xmlns_still_parses(tmp_path):
    """Older Visual Studio templates ship the MSBuild namespace; iter() with
    local-name match must still find ProjectReference / PackageReference."""
    proj = tmp_path / "Old.csproj"
    proj.write_text(
        '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\n'
        '  <ItemGroup>\n'
        '    <PackageReference Include="EntityFramework" Version="6.0.0" />\n'
        '  </ItemGroup>\n'
        '</Project>\n'
    )
    edges = extract_dotnet_edges(str(proj))
    assert any(e.target == "EntityFramework" for e in edges)


def test_csproj_malformed_xml_returns_empty(tmp_path):
    """Bad XML must not crash — wave processes hundreds of files in parallel
    and one corrupt csproj would otherwise abort the whole project."""
    proj = tmp_path / "Bad.csproj"
    proj.write_text("<Project><ItemGroup>  <not closed>")
    assert extract_dotnet_edges(str(proj)) == []


# ── Razor / cshtml ───────────────────────────────────────────────────────────

def test_razor_inherits_inject_using(tmp_path):
    page = tmp_path / "Index.razor"
    page.write_text(
        '@page "/"\n'
        '@inherits LayoutComponentBase\n'
        '@inject IUserService Users\n'
        '@inject IOrderService Orders\n'
        '@using MyApp.Shared\n'
        '<h1>Hello</h1>\n'
    )
    by_rel = _by_relation(extract_dotnet_edges(str(page)))

    # @inherits + @inject → references (last-segment name)
    assert "LayoutComponentBase" in by_rel.get("references", [])
    assert "IUserService" in by_rel.get("references", [])
    assert "IOrderService" in by_rel.get("references", [])
    # @using → imports_from (namespace preserved)
    assert "MyApp.Shared" in by_rel.get("imports_from", [])


def test_razor_strips_namespace_to_last_segment(tmp_path):
    """`@inherits MyApp.Components.Layout` should match a node labelled `Layout`."""
    page = tmp_path / "Page.razor"
    page.write_text("@inherits MyApp.Components.Layout\n")
    edges = extract_dotnet_edges(str(page))
    assert edges and edges[0].target == "Layout"


# ── dispatcher integration ───────────────────────────────────────────────────

def test_dependencies_dispatches_to_dotnet_for_csproj(tmp_path):
    """extract_dependencies (the public entry point) must route .csproj to dotnet,
    not to the SCM path (which would silently return [] because the framework
    'aspnet' SCM file targets C# source, not MSBuild XML)."""
    proj = tmp_path / "Web.csproj"
    proj.write_text(CSPROJ_SAMPLE)
    # framework string is irrelevant for .csproj — dispatcher is extension-driven
    edges = extract_dependencies(str(proj), framework="aspnet")
    assert edges, "extract_dependencies returned nothing for .csproj"
    targets = [e.target for e in edges]
    assert "Newtonsoft.Json" in targets


def test_dependencies_dispatches_to_dotnet_for_razor(tmp_path):
    page = tmp_path / "Index.razor"
    page.write_text("@inherits Component\n")
    edges = extract_dependencies(str(page), framework="aspnet")
    assert any(e.target == "Component" for e in edges)
