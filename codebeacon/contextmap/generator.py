"""Context Map generator: CLAUDE.md / .cursorrules / AGENTS.md.

Reads the knowledge graph and project metadata to produce AI assistant config
files that implement a 3-step lookup strategy.

Public API:
    generate_context_map(G, output_dir, projects, obsidian_dir, targets)
        → list[str]  (paths of files written)

Output files (written next to .codebeacon/):
    CLAUDE.md                  ← Claude Code
    .cursorrules               ← Cursor IDE
    AGENTS.md                  ← Codex / Copilot multi-agent

Lookup strategy encoded in each file:
    Step 1 → .codebeacon/wiki/          (routes, controllers, services)
    Step 2 → .codebeacon/obsidian/      (methods, fields, connections)
    Step 3 → source files               (only those found in Steps 1-2)
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

from codebeacon.common.types import ProjectInfo


# ── Build-tool command tables ─────────────────────────────────────────────────

_BUILD_COMMANDS: dict[str, dict[str, str]] = {
    "spring-boot": {
        "install": "mvn clean install -DskipTests=true",
        "build":   "mvn clean package -DskipTests=true",
        "run":     "mvn spring-boot:run",
        "test":    "mvn test",
        "test_single": "mvn test -Dtest=ClassName#methodName",
    },
    "ktor": {
        "install": "./gradlew build",
        "build":   "./gradlew build",
        "run":     "./gradlew run",
        "test":    "./gradlew test",
        "test_single": "./gradlew test --tests 'com.example.ClassName'",
    },
    "fastapi": {
        "install": "pip install -r requirements.txt",
        "build":   "pip install -r requirements.txt",
        "run":     "uvicorn main:app --reload",
        "test":    "pytest",
        "test_single": "pytest tests/test_foo.py::test_bar",
    },
    "django": {
        "install": "pip install -r requirements.txt",
        "build":   "python manage.py collectstatic --noinput",
        "run":     "python manage.py runserver",
        "test":    "python manage.py test",
        "test_single": "python manage.py test myapp.tests.MyTestCase",
    },
    "flask": {
        "install": "pip install -r requirements.txt",
        "build":   "pip install -r requirements.txt",
        "run":     "flask run",
        "test":    "pytest",
        "test_single": "pytest tests/test_foo.py::test_bar",
    },
    "express": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run dev",
        "test":    "npm test",
        "test_single": "npm test -- --testNamePattern 'test name'",
    },
    "nestjs": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run start:dev",
        "test":    "npm test",
        "test_single": "npm test -- --testNamePattern 'test name'",
    },
    "react": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run dev",
        "test":    "npm test",
        "test_single": "npm test -- --testPathPattern TestFile",
    },
    "next": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run dev",
        "test":    "npm test",
        "test_single": "npm test -- --testPathPattern TestFile",
    },
    "vue": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run dev",
        "test":    "npm run test:unit",
        "test_single": "npm run test:unit -- TestFile",
    },
    "nuxt": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run dev",
        "test":    "npm run test",
        "test_single": "npm run test -- TestFile",
    },
    "svelte": {
        "install": "npm install",
        "build":   "npm run build",
        "run":     "npm run dev",
        "test":    "npm test",
        "test_single": "npm test -- --testPathPattern TestFile",
    },
    "angular": {
        "install": "npm install",
        "build":   "ng build",
        "run":     "ng serve",
        "test":    "ng test",
        "test_single": "ng test --include **/foo.spec.ts",
    },
    "gin": {
        "install": "go mod download",
        "build":   "go build ./...",
        "run":     "go run .",
        "test":    "go test ./...",
        "test_single": "go test ./... -run TestFunctionName",
    },
    "echo": {
        "install": "go mod download",
        "build":   "go build ./...",
        "run":     "go run .",
        "test":    "go test ./...",
        "test_single": "go test ./... -run TestFunctionName",
    },
    "fiber": {
        "install": "go mod download",
        "build":   "go build ./...",
        "run":     "go run .",
        "test":    "go test ./...",
        "test_single": "go test ./... -run TestFunctionName",
    },
    "rails": {
        "install": "bundle install",
        "build":   "bundle exec rails assets:precompile",
        "run":     "bundle exec rails server",
        "test":    "bundle exec rspec",
        "test_single": "bundle exec rspec spec/models/user_spec.rb",
    },
    "laravel": {
        "install": "composer install",
        "build":   "npm run build",
        "run":     "php artisan serve",
        "test":    "php artisan test",
        "test_single": "php artisan test --filter TestClass",
    },
    "aspnet": {
        "install": "dotnet restore",
        "build":   "dotnet build",
        "run":     "dotnet run",
        "test":    "dotnet test",
        "test_single": "dotnet test --filter 'FullyQualifiedName~TestClass'",
    },
    "actix": {
        "install": "cargo fetch",
        "build":   "cargo build --release",
        "run":     "cargo run",
        "test":    "cargo test",
        "test_single": "cargo test test_function_name",
    },
    "axum": {
        "install": "cargo fetch",
        "build":   "cargo build --release",
        "run":     "cargo run",
        "test":    "cargo test",
        "test_single": "cargo test test_function_name",
    },
    "vapor": {
        "install": "swift package resolve",
        "build":   "swift build",
        "run":     "swift run",
        "test":    "swift test",
        "test_single": "swift test --filter TestClass/testMethod",
    },
}

_FALLBACK_COMMANDS: dict[str, str] = {
    "install": "# see project README",
    "build":   "# see project README",
    "run":     "# see project README",
    "test":    "# see project README",
    "test_single": "# see project README",
}


def _get_commands(framework: str) -> dict[str, str]:
    fw = framework.lower()
    for key, cmds in _BUILD_COMMANDS.items():
        if key in fw:
            return cmds
    return _FALLBACK_COMMANDS


# ── Stats extraction ──────────────────────────────────────────────────────────

def _collect_stats(G: nx.DiGraph) -> dict[str, dict[str, int]]:
    """Return per-project counts: routes, services, entities, components."""

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {
        "routes": 0, "services": 0, "entities": 0, "components": 0, "controllers": 0,
    })

    _CONTROLLER_SUFFIXES = ("Controller", "Router", "Handler", "Resource")
    _CONTROLLER_ANNS = frozenset({
        "@Controller", "@RestController", "[Controller]", "[ApiController]",
    })

    for node_id, data in G.nodes(data=True):
        project = data.get("project", "")
        if not project:
            continue
        ntype = data.get("type", "")
        if ntype == "route":
            stats[project]["routes"] += 1
        elif ntype == "entity":
            stats[project]["entities"] += 1
        elif ntype == "component":
            stats[project]["components"] += 1
        elif ntype == "class":
            anns  = data.get("annotations", [])
            label = data.get("label", "")
            if any(a in _CONTROLLER_ANNS for a in anns) or label.endswith(_CONTROLLER_SUFFIXES):
                stats[project]["controllers"] += 1
            else:
                stats[project]["services"] += 1

    return dict(stats)


def _hub_files(G: nx.DiGraph, top_n: int = 5) -> list[tuple[str, int]]:
    """Return (file_path, import_count) for the most-imported source files."""
    counter: dict[str, int] = defaultdict(int)
    for _, _, data in G.edges(data=True):
        if data.get("relation") in ("imports", "imports_from"):
            sf = data.get("source_file", "")
            if sf:
                counter[sf] += 1
    ranked = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


# ── Content builders ──────────────────────────────────────────────────────────

def _build_content(
    G: nx.DiGraph,
    projects: list[ProjectInfo],
    output_dir: Path,
    obsidian_path: str,
    stats: dict[str, dict[str, int]],
    hub_files: list[tuple[str, int]],
    tool: str,  # "claude", "cursor", "agents"
) -> str:
    today = datetime.date.today().isoformat()
    codebeacon_dir = ".codebeacon"  # relative to project root

    # ── Header ──
    if tool == "claude":
        lines = [
            "# CLAUDE.md",
            "",
            "## MANDATORY: Lookup Strategy",
            "",
            "> **Read these before ANY code exploration. No exceptions.**",
            ">",
            "> Skipping these steps and reading source files directly is a rule violation.",
            "",
        ]
    elif tool == "cursor":
        lines = [
            "# Project Context",
            "",
            "## Lookup Strategy",
            "",
            "> Always follow this 3-step lookup before editing code.",
            "",
        ]
    else:  # agents
        lines = [
            "# AGENTS.md",
            "",
            "## Context Lookup Protocol",
            "",
            "> All agents MUST follow this 3-step lookup before writing or modifying code.",
            "",
        ]

    # ── Step 1: wiki ──
    lines += [
        "### Step 1 → codebeacon wiki (routes, controllers, services, entities) — ALWAYS",
        "```",
        f"{codebeacon_dir}/wiki/index.md                    ← MUST read at session start",
        f"{codebeacon_dir}/wiki/{{project}}/controllers/{{Name}}.md  ← for controller logic",
        f"{codebeacon_dir}/wiki/{{project}}/services/{{Name}}.md     ← for service methods",
        f"{codebeacon_dir}/wiki/{{project}}/entities/{{Name}}.md     ← for data models",
        f"{codebeacon_dir}/wiki/routes.md                   ← all API routes across projects",
        "```",
        "",
    ]

    # ── Step 2: obsidian ──
    lines += [
        "### Step 2 → codebeacon obsidian (methods, fields, connections) — ALWAYS",
        "**MUST read even if Step 1 found results.** Obsidian notes contain method lists,",
        "field definitions, and class-level connections that wiki articles do not have.",
        "",
        f"Look up by class name — replace `{{project}}` with the relevant folder:",
        "```",
        f"{obsidian_path}/{{project}}/{{ClassName}}.md",
        "```",
        "",
    ]

    # Project table
    if projects:
        lines += [
            "| Project | Notes | Example |",
            "| --- | --- | --- |",
        ]
        for p in projects:
            s = stats.get(p.name, {})
            total = s.get("services", 0) + s.get("controllers", 0)
            ent   = s.get("entities", 0)
            comp  = s.get("components", 0)
            # Example note name: pick first service or entity
            example = _pick_example_note(G, p.name)
            parts = []
            if total:
                parts.append(f"{total} services")
            if ent:
                parts.append(f"{ent} entities")
            if comp:
                parts.append(f"{comp} components")
            note_summary = ", ".join(parts) if parts else "—"
            lines.append(f"| {p.name} | {note_summary} | `{example}` |")
        lines.append("")

    # ── Step 3 ──
    lines += [
        "### Step 3 → source file (ONLY files identified in Steps 1-2)",
        "Read only the specific source files whose paths were found in Steps 1-2.",
        "No directory exploration, no Glob scans, no broad Grep searches.",
        "",
    ]

    if tool == "claude":
        lines += [
            "### Prohibited actions (before completing Steps 1-2)",
            "- **DO NOT use Explore agent**",
            "- **DO NOT use Glob for directory scans**",
            "- **DO NOT use Grep for broad searches**",
            "- **DO NOT Read source files directly without checking Steps 1-2 first**",
            "",
            "Proceed to Step 3 only when Steps 1-2 are insufficient.",
            "",
        ]

    lines.append("---")
    lines.append("")

    # ── Project stats table ──
    lines += [
        "## Projects",
        "",
        "| Project | Framework | Routes | Services | Entities | Components |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for p in projects:
        s = stats.get(p.name, {})
        lines.append(
            f"| {p.name} | {p.framework}"
            f" | {s.get('routes', 0)}"
            f" | {s.get('services', 0) + s.get('controllers', 0)}"
            f" | {s.get('entities', 0)}"
            f" | {s.get('components', 0)} |"
        )
    lines += ["", "---", ""]

    # ── Common Commands ──
    lines += ["## Common Commands", ""]
    for p in projects:
        cmds = _get_commands(p.framework)
        lines += [f"### {p.name} ({p.framework})", "```bash"]
        lines.append(f"{cmds['build']}  # build")
        lines.append(f"{cmds['run']}  # run")
        lines.append(f"{cmds['test']}  # all tests")
        if cmds.get("test_single") != cmds.get("test"):
            lines.append(f"{cmds['test_single']}  # single test")
        lines += ["```", ""]
    lines += ["---", ""]

    # ── Architecture ──
    lines += ["## Architecture", ""]
    for p in projects:
        s = stats.get(p.name, {})
        arch_parts = [f"**{p.framework}**", f"{p.language}"]
        lines.append(f"**{p.name}**: {' · '.join(arch_parts)}")
        lines.append(f"  Routes: {s.get('routes', 0)} | "
                     f"Services: {s.get('services', 0)} | "
                     f"Entities: {s.get('entities', 0)} | "
                     f"Components: {s.get('components', 0)}")
        lines.append("")

    # ── High-impact files ──
    if hub_files:
        lines += ["## High-Impact Files", "", "Changes here affect many other files:", ""]
        for fp, cnt in hub_files:
            lines.append(f"- `{fp}` (imported by {cnt} files)")
        lines += ["", "---", ""]

    # ── Footer ──
    lines += [
        f"_Generated by [codebeacon](https://github.com/codebeacon/codebeacon) · {today}_",
    ]

    return "\n".join(lines) + "\n"


def _pick_example_note(G: nx.DiGraph, project: str) -> str:
    """Pick a representative note name for the project example column."""
    for node_id, data in G.nodes(data=True):
        if data.get("project") != project:
            continue
        if data.get("type") == "class":
            label = data.get("label", "")
            sf = data.get("source_file", "")
            ext = Path(sf).suffix if sf else ""
            if ext:
                return f"{label}{ext}.md"
            return f"{label}.md"
    for node_id, data in G.nodes(data=True):
        if data.get("project") != project:
            continue
        return data.get("label", "example") + ".md"
    return "example.md"


# ── Merge helpers ─────────────────────────────────────────────────────────────

_BLOCK_START = "<!-- codebeacon:start -->"
_BLOCK_END   = "<!-- codebeacon:end -->"

# Headings / patterns that are part of codebeacon output — used to strip
# legacy codebeacon content from files that pre-date the markers.
_LEGACY_PATTERNS = (
    "## MANDATORY: Lookup Strategy",
    "## Lookup Strategy",
    "## Context Lookup Protocol",
    "### Step 1 → codebeacon wiki",
    "### Step 2 → codebeacon obsidian",
    "### Step 3 → source file",
    "### Prohibited actions",
    "## Projects",
    "## Common Commands",
    "## Architecture",
    "## High-Impact Files",
    "_Generated by [codebeacon]",
)


def _strip_codebeacon_block(existing: str) -> str:
    """Remove a previously generated codebeacon block from *existing* text.

    Handles two formats:
    1. Marker-delimited blocks  <!-- codebeacon:start --> … <!-- codebeacon:end -->
    2. Legacy files (no markers): heuristically drops lines that belong to a
       contiguous codebeacon section identified by _LEGACY_PATTERNS.
    """
    # ── Format 1: marker-delimited ──
    if _BLOCK_START in existing:
        before = existing[:existing.index(_BLOCK_START)]
        after_marker = existing[existing.index(_BLOCK_START) + len(_BLOCK_START):]
        if _BLOCK_END in after_marker:
            after = after_marker[after_marker.index(_BLOCK_END) + len(_BLOCK_END):]
        else:
            after = ""
        return (before + after).strip()

    # ── Format 2: legacy heuristic ──
    lines = existing.splitlines()
    cleaned: list[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(p) for p in _LEGACY_PATTERNS):
            inside = True
        if inside:
            # Exit the codebeacon section when we hit a user heading that is
            # NOT a codebeacon heading, after we've already entered one.
            if stripped.startswith("#") and not any(
                stripped.startswith(p) for p in _LEGACY_PATTERNS
            ):
                inside = False
                cleaned.append(line)
        else:
            cleaned.append(line)

    return "\n".join(cleaned).strip()


def _merge_content(new_content: str, path: Path) -> str:
    """Return the final file text: codebeacon block on top, user content below.

    - If the file does not exist → return new_content as-is (wrapped in markers).
    - If it exists → strip any old codebeacon block, keep user content, prepend
      the new block.
    Duplicate detection uses the marker scheme so subsequent runs stay clean.
    """
    wrapped = f"{_BLOCK_START}\n{new_content.rstrip()}\n{_BLOCK_END}\n"

    if not path.exists():
        return wrapped

    existing = path.read_text(encoding="utf-8")
    user_content = _strip_codebeacon_block(existing).strip()

    if user_content:
        return f"{wrapped}\n{user_content}\n"
    return wrapped


# ── Public entry point ─────────────────────────────────────────────────────────

def generate_context_map(
    G: nx.DiGraph,
    output_dir: str | Path,
    projects: list[ProjectInfo],
    obsidian_dir: str | Path | None = None,
    targets: list[str] | None = None,
) -> list[str]:
    """Generate CLAUDE.md, .cursorrules, and AGENTS.md context map files.

    Files are written to the parent of output_dir (i.e. alongside .codebeacon/).

    Args:
        G:           knowledge graph
        output_dir:  .codebeacon/ directory path
        projects:    list of ProjectInfo (name, path, framework, language)
        obsidian_dir: custom obsidian vault path; defaults to output_dir/obsidian
        targets:     which files to generate; defaults to all three

    Returns:
        List of absolute paths of files written.
    """
    if targets is None:
        targets = ["CLAUDE.md", ".cursorrules", "AGENTS.md"]

    output_path  = Path(output_dir)
    # Context map files live alongside .codebeacon/, not inside it
    project_root = output_path.parent

    # Obsidian path shown in docs — relative from project root if possible
    if obsidian_dir:
        obs_path = str(obsidian_dir)
    else:
        obs_abs = output_path / "obsidian"
        try:
            obs_path = str(obs_abs.relative_to(project_root))
        except ValueError:
            obs_path = str(obs_abs)

    stats     = _collect_stats(G)
    hubs      = _hub_files(G)

    written: list[str] = []

    # CLAUDE.md
    if "CLAUDE.md" in targets:
        content = _build_content(G, projects, output_path, obs_path, stats, hubs, tool="claude")
        path = project_root / "CLAUDE.md"
        path.write_text(_merge_content(content, path), encoding="utf-8")
        written.append(str(path))

    # .cursorrules
    if ".cursorrules" in targets:
        content = _build_content(G, projects, output_path, obs_path, stats, hubs, tool="cursor")
        path = project_root / ".cursorrules"
        path.write_text(_merge_content(content, path), encoding="utf-8")
        written.append(str(path))

    # AGENTS.md
    if "AGENTS.md" in targets:
        content = _build_content(G, projects, output_path, obs_path, stats, hubs, tool="agents")
        path = project_root / "AGENTS.md"
        path.write_text(_merge_content(content, path), encoding="utf-8")
        written.append(str(path))

    return written
