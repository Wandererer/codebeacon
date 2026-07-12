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
    .claude/rules/codebeacon-<project>.md  ← Claude Code, workspace mode only

Lookup strategy encoded in each file:
    Step 1 → .codebeacon/wiki/          (routes, controllers, services)
    Step 2 → .codebeacon/obsidian/      (methods, fields, connections)
    Step 3 → source files               (only those found in Steps 1-2)

Workspace (multi-project) mode keeps CLAUDE.md under Anthropic's ~200-line
guidance by moving per-project detail (commands, architecture, class-note
lookup) into scoped .claude/rules/ files that Claude Code loads only when the
matching project's files are touched. The Cursor/Codex files stay monolithic —
`.claude/rules/` is a Claude Code feature and the line budget is Claude-specific.
"""

from __future__ import annotations

import datetime
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

from codebeacon.common.types import ProjectInfo
from codebeacon.discover.detector import classify_repo_type
from codebeacon.plugins.githooks import detect_hooks, format_hooks_section
from codebeacon.plugins.skills import detect_skills, format_skills_section
from codebeacon.wiki.generator import _CONTROLLER_ANNOTATIONS


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


# ── Project de-duplication & rules-file scoping ─────────────────────────────────

def _dedupe_projects(projects: list[ProjectInfo]) -> list[ProjectInfo]:
    """Collapse projects that share a name to a single, order-preserving entry.

    Workspace discovery can surface several ProjectInfo with the SAME name —
    distinct directories whose leaf name collides (``APT-Score/frontend`` and
    ``TriPhotoMap/frontend`` both named ``frontend``), or one directory detected
    under multiple frameworks. Every rendered surface (the stats tables, the
    wiki/obsidian ``{project}`` folder, the per-project commands) is keyed by
    NAME, so the extra rows only duplicate already-conflated data — and two
    same-named projects would otherwise collide on one ``codebeacon-<name>.md``
    rules file. Keep the first occurrence; the full path set for a name is still
    recovered by :func:`_project_scope_globs` for the rules ``paths:`` block.
    """
    seen: set[str] = set()
    out: list[ProjectInfo] = []
    for p in projects:
        if p.name in seen:
            continue
        seen.add(p.name)
        out.append(p)
    return out


def _slugify_project(name: str) -> str:
    """Filesystem-safe slug for a ``codebeacon-<slug>.md`` rules filename.

    Project names are usually already safe (``web``, ``api-python``,
    ``datapopcorn-ai-magic.git``). Replace any character outside
    ``[A-Za-z0-9._-]`` with '-' and trim leading/trailing dashes so a stray path
    separator or space cannot escape the rules directory or split the filename.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    return slug or "project"


def _project_scope_globs(projects: list[ProjectInfo], root: Path) -> dict[str, list[str]]:
    """Map project name → ordered, de-duplicated ``paths:`` globs for its rules file.

    All directories sharing a name contribute their glob (both ``frontend`` dirs),
    so editing any of them loads the scoped rules file. Paths are relativized to
    ``root`` (where ``.claude/`` lives) because Claude Code ``paths:`` globs are
    root-relative; a dir equal to or outside ``root`` falls back to the bare
    project name so the frontmatter still carries a scope hint.
    """
    globs: dict[str, list[str]] = {}
    for p in projects:
        rel = _relativize_to(p.path, root)
        if not rel or os.path.isabs(rel) or rel == "." or rel.startswith(".."):
            glob = f"{p.name}/**"
        else:
            glob = f"{rel.rstrip('/')}/**"
        bucket = globs.setdefault(p.name, [])
        if glob not in bucket:
            bucket.append(glob)
    return globs


# ── Stats extraction ──────────────────────────────────────────────────────────

def _collect_stats(G: nx.DiGraph) -> dict[str, dict[str, int]]:
    """Return per-project counts: routes, services, entities, components."""

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {
        "routes": 0, "services": 0, "entities": 0, "components": 0, "controllers": 0,
    })

    # Controller vs. service classification MUST match wiki/generator.py so the
    # CLAUDE.md counts and the wiki agree (G11). We reuse its annotation set —
    # which deliberately includes the bare `Controller`/`RestController` forms
    # because the Spring/NestJS extractors emit annotations without the leading
    # '@' — and mirror its _CONTROLLER_NAME_SUFFIXES here.
    _CONTROLLER_SUFFIXES = ("Controller", "Router", "Handler", "Resource")

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
            if any(a in _CONTROLLER_ANNOTATIONS for a in anns) or label.endswith(_CONTROLLER_SUFFIXES):
                stats[project]["controllers"] += 1
            else:
                stats[project]["services"] += 1

    return dict(stats)


def _hub_files(G: nx.DiGraph, top_n: int = 5) -> list[tuple[str, int]]:
    """Return (file_path, importer_count) for the most-imported source files.

    Counts DISTINCT importing files per edge-target file, mirroring
    analyze.hub_files. The old version counted `edge["source_file"]` — the
    importer's own file — so CLAUDE.md's "High-Impact Files" actually listed
    the files that *import the most* (entry points), with counts inflated by
    per-node edge remapping (e.g. "imported by 392 files" in a 60-file repo).
    """
    importers: dict[str, set[str]] = defaultdict(set)
    for src, tgt, data in G.edges(data=True):
        if data.get("relation") not in ("imports", "imports_from"):
            continue
        tgt_file = G.nodes[tgt].get("source_file", "")
        src_file = G.nodes[src].get("source_file", "")
        if tgt_file and src_file and tgt_file != src_file:
            importers[tgt_file].add(src_file)
    ranked = sorted(
        ((fp, len(srcs)) for fp, srcs in importers.items()),
        key=lambda x: (-x[1], x[0]),
    )
    return ranked[:top_n]


def _relativize_to(file_path: str, root: Path) -> str:
    """Return ``file_path`` relative to ``root`` (POSIX), or unchanged if it is
    already relative or lives outside the root.

    Keeps absolute machine paths out of the committed CLAUDE.md / AGENTS.md.
    """
    if not file_path or not os.path.isabs(file_path):
        return file_path
    try:
        rel = os.path.relpath(file_path, str(root))
    except ValueError:
        return file_path  # different drive on Windows
    if rel == ".." or rel.startswith(".." + os.sep):
        return file_path
    return rel.replace(os.sep, "/")


# ── Content builders ──────────────────────────────────────────────────────────

_REPO_TYPE_BLURB = {
    "meta":          "Meta-repo (git submodules). Sub-projects are independently versioned.",
    "microservices": "Microservices repo. Services ship independently; coordinate cross-service changes carefully.",
    "monorepo":      "Monorepo. Multiple projects share tooling under one tree.",
    "single":        "Single-project repo.",
}


def _build_content(
    G: nx.DiGraph,
    projects: list[ProjectInfo],
    output_dir: Path,
    obsidian_path: str,
    stats: dict[str, dict[str, int]],
    hub_files: list[tuple[str, int]],
    tool: str,  # "claude", "cursor", "agents"
    repo_type: str = "",
    skills_section: str = "",
    hooks_section: str = "",
    split: bool = False,
) -> str:
    today = datetime.date.today().isoformat()
    codebeacon_dir = ".codebeacon"  # relative to project root

    # ── Header ──
    if tool == "claude":
        lines = [
            "# CLAUDE.md",
            "",
            "## Lookup strategy",
            "",
            "> This repo ships a pre-built index in `.codebeacon/`. Check it first —",
            "> most \"where is X\" questions resolve in one read without a full-repo search.",
            "",
        ]
    elif tool == "cursor":
        lines = [
            "# Project Context",
            "",
            "## Lookup strategy",
            "",
            "> A pre-built index lives in `.codebeacon/`. Use the 3-step lookup below",
            "> before reaching for Glob or Grep.",
            "",
        ]
    else:  # agents
        lines = [
            "# AGENTS.md",
            "",
            "## Lookup strategy",
            "",
            "> A pre-built index lives in `.codebeacon/`. Follow the 3-step lookup below",
            "> so parallel agents converge on the same answer.",
            "",
        ]

    # ── Repo type banner ──
    if repo_type and repo_type in _REPO_TYPE_BLURB:
        lines += [f"> **Repo type:** `{repo_type}` — {_REPO_TYPE_BLURB[repo_type]}", ""]

    # ── Step 1: wiki ──
    lines += [
        "### Step 1 — codebeacon wiki",
        "Routes, controllers, services, entities.",
        "```",
        f"{codebeacon_dir}/wiki/index.md                    ← global index",
        f"{codebeacon_dir}/wiki/{{project}}/controllers/{{Name}}.md  ← controller logic",
        f"{codebeacon_dir}/wiki/{{project}}/services/{{Name}}.md     ← service methods",
        f"{codebeacon_dir}/wiki/{{project}}/entities/{{Name}}.md     ← data models",
        f"{codebeacon_dir}/wiki/routes.md                   ← all API routes across projects",
        "```",
        "",
    ]

    # ── Step 2: obsidian ──
    lines += [
        "### Step 2 — obsidian notes",
        "Class-level detail (methods, fields, incoming/outgoing edges) the wiki omits.",
        "Look up by class name — replace `{project}` with the relevant folder:",
        "```",
        f"{obsidian_path}/{{project}}/{{ClassName}}.md",
        "```",
        "",
    ]

    # Project table. In split mode the per-project Notes/Example live in each
    # project's .claude/rules/ file, so this workspace index omits the table.
    if projects and not split:
        lines += [
            "| Project | Notes | Example |",
            "| --- | --- | --- |",
        ]
        for p in projects:
            s = stats.get(p.name, {})
            # "Services" = services only (controllers excluded), matching the
            # Architecture section below and wiki/generator.py service_count so
            # every surface reports the same number.
            total = s.get("services", 0)
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
        "### Step 3 — source file",
        "Open the paths surfaced by Steps 1–2.",
        "",
    ]

    if tool == "claude":
        lines += [
            "### Fall back to direct search",
            "Reach for Glob, Grep, or the Explore agent when the index does not cover",
            "what you need — new files, deep implementation details, or cross-cutting",
            "searches that span projects.",
            "",
        ]

    lines.append("---")
    lines.append("")

    # ── Project stats table ──
    lines += ["## Projects", ""]
    if split:
        # Per-project detail is split into scoped .claude/rules/ files so this
        # workspace CLAUDE.md stays under Anthropic's ~200-line guidance. The
        # Detail column points at each; Claude Code loads it only when the
        # matching project's files are touched.
        lines += [
            "Per-project commands, architecture, and class-note lookup live in the",
            "`.claude/rules/codebeacon-<project>.md` files below — Claude Code loads",
            "each automatically when you edit files in that project.",
            "",
            "| Project | Framework | Routes | Services | Entities | Components | Detail |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    else:
        lines += [
            "| Project | Framework | Routes | Services | Entities | Components |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    for p in projects:
        s = stats.get(p.name, {})
        row = (
            f"| {p.name} | {p.framework}"
            f" | {s.get('routes', 0)}"
            f" | {s.get('services', 0)}"  # services only — see Step-2 Notes note
            f" | {s.get('entities', 0)}"
            f" | {s.get('components', 0)}"
        )
        if split:
            row += f" | `.claude/rules/codebeacon-{_slugify_project(p.name)}.md` |"
        else:
            row += " |"
        lines.append(row)
    lines += ["", "---", ""]

    # ── Common Commands ──
    # In split mode these move to the per-project .claude/rules/ files.
    if not split:
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
    # In split mode these move to the per-project .claude/rules/ files.
    if not split:
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
        # CLAUDE.md is committed, so absolute machine paths here would leak one
        # developer's home directory into the repo and churn diffs. Show paths
        # relative to the project root (``output_dir`` is ``<root>/.codebeacon``).
        # Mirrors graphify #999.
        project_root = output_dir.parent
        for fp, cnt in hub_files:
            lines.append(f"- `{_relativize_to(fp, project_root)}` (imported by {cnt} files)")
        lines += ["", "---", ""]

    # ── Skills ──
    if skills_section:
        lines += [skills_section, "---", ""]

    # ── Git hooks ──
    if hooks_section:
        lines += [hooks_section, "---", ""]

    # ── Footer ──
    lines += [
        f"_Generated by [codebeacon](https://github.com/codebeacon/codebeacon) · {today}_",
    ]

    return "\n".join(lines) + "\n"


def _pick_example_note(G: nx.DiGraph, project: str) -> str:
    """Pick a representative note name for the project's Example column.

    Deterministic: among the project's class nodes (or, failing that, any node),
    pick the one with the smallest ``(label, node_id)`` key. Iterating
    ``G.nodes`` and returning the *first* match made the column flip run-to-run
    because networkx preserves wave-completion insertion order, which is not
    stable across scans.
    """
    def _key(item: tuple[Any, dict]) -> tuple[str, str]:
        node_id, data = item
        return (data.get("label", "") or "", str(node_id))

    class_nodes = [
        (nid, d) for nid, d in G.nodes(data=True)
        if d.get("project") == project and d.get("type") == "class"
    ]
    if class_nodes:
        _nid, data = min(class_nodes, key=_key)
        label = data.get("label", "")
        sf = data.get("source_file", "")
        ext = Path(sf).suffix if sf else ""
        return f"{label}{ext}.md" if ext else f"{label}.md"

    proj_nodes = [
        (nid, d) for nid, d in G.nodes(data=True) if d.get("project") == project
    ]
    if proj_nodes:
        _nid, data = min(proj_nodes, key=_key)
        return data.get("label", "example") + ".md"
    return "example.md"


# ── Rules-file builders (workspace split) ───────────────────────────────────────

def _build_rules_frontmatter(globs: list[str]) -> str:
    """YAML ``paths:`` frontmatter so Claude Code scope-loads the rules file only
    when a matching file is edited. Must be the first thing in the file."""
    lines = ["---", "paths:"]
    for g in globs:
        lines.append(f'  - "{g}"')
    lines.append("---")
    return "\n".join(lines)


def _build_rules_body(
    G: nx.DiGraph,
    p: ProjectInfo,
    stats: dict[str, dict[str, int]],
    obsidian_path: str,
) -> str:
    """The codebeacon-managed body of a per-project rules file: the commands,
    architecture, and class-note lookup lifted out of the workspace CLAUDE.md."""
    s = stats.get(p.name, {})
    cmds = _get_commands(p.framework)

    lines = [
        f"## {p.name} ({p.framework})",
        "",
        "### Commands",
        "```bash",
        f"{cmds['build']}  # build",
        f"{cmds['run']}  # run",
        f"{cmds['test']}  # all tests",
    ]
    if cmds.get("test_single") != cmds.get("test"):
        lines.append(f"{cmds['test_single']}  # single test")
    lines += ["```", ""]

    lines += [
        "### Architecture",
        f"**{p.framework}** · {p.language}",
        f"Routes: {s.get('routes', 0)} | "
        f"Services: {s.get('services', 0)} | "
        f"Entities: {s.get('entities', 0)} | "
        f"Components: {s.get('components', 0)}",
        "",
        "### Class notes",
        "Class-level detail (methods, fields, incoming/outgoing edges) — look up",
        "by class name:",
        f"`{obsidian_path}/{p.name}/{{ClassName}}.md`",
        f"Example: `{_pick_example_note(G, p.name)}`",
    ]
    return "\n".join(lines)


def _write_rules_files(
    G: nx.DiGraph,
    projects: list[ProjectInfo],
    scope_projects: list[ProjectInfo],
    project_root: Path,
    stats: dict[str, dict[str, int]],
    obsidian_path: str,
) -> list[str]:
    """Write one ``.claude/rules/codebeacon-<slug>.md`` per (de-duplicated)
    project, preserving any user content below the codebeacon markers. Returns
    the paths written.

    ``scope_projects`` is the PRE-dedup list so a name shared by several
    directories contributes every directory to that rules file's ``paths:``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    scope = _project_scope_globs(scope_projects, project_root)

    written: list[str] = []
    for p in projects:
        path = rules_dir / f"codebeacon-{_slugify_project(p.name)}.md"
        frontmatter = _build_rules_frontmatter(scope.get(p.name, [f"{p.name}/**"]))
        body = _build_rules_body(G, p, stats, obsidian_path)
        path.write_text(_merge_rules_content(frontmatter, body, path), encoding="utf-8")
        written.append(str(path))
    return written


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
    "## Claude Skills",
    "## Git Hooks",
    "_Generated by [codebeacon]",
)

# Codebeacon-EXCLUSIVE headings that legitimately begin a generated block. The
# other _LEGACY_PATTERNS entries ("## Architecture", "## Common Commands", …)
# are generic — Claude Code's own /init writes them — so they must NOT, on their
# own, start a wipe. Only a Lookup-strategy header anchors the strip.
_BLOCK_START_HEADINGS = (
    "## MANDATORY: Lookup Strategy",
    "## Lookup Strategy",
    "## Lookup strategy",
    "## Context Lookup Protocol",
)

# The generated footer. It is the SOLE trigger for the legacy (marker-less)
# strip: without it we cannot be sure a section is codebeacon-managed, so a
# hand-written file — even one that mentions `.codebeacon/wiki/` or carries its
# own `## Lookup strategy` — is left untouched.
_FOOTER_MARKER = "_Generated by [codebeacon]"


def _strip_codebeacon_block(existing: str) -> str:
    """Remove a previously generated codebeacon block from *existing* text.

    Handles two formats:
    1. Marker-delimited blocks  <!-- codebeacon:start --> … <!-- codebeacon:end -->
    2. Legacy files (no markers): FOOTER-ANCHORED. The block is removed only when
       the codebeacon footer ("_Generated by [codebeacon]") is present, and it
       runs from the block-start heading — a Lookup-strategy header from
       ``_BLOCK_START_HEADINGS`` or, when none is present, the first
       ``_LEGACY_PATTERNS`` heading — through the footer line, inclusive.

    Data-loss guard: a file with no footer is returned unchanged, even one that
    mentions ``.codebeacon/wiki/`` or carries its own ``## Lookup strategy``.
    Content above the start heading and below the footer is user content and is
    preserved, so a user's own "## Architecture" section on either side of a
    real codebeacon block survives.
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

    # ── Format 2: legacy heuristic — footer-anchored ──
    # No footer ⇒ we cannot bound a managed region safely; treat as hand-authored.
    if _FOOTER_MARKER not in existing:
        return existing.strip()

    lines = existing.splitlines()
    # Anchor the block end on the last footer line (user prose may repeat it).
    footer_idx = max(
        i for i, ln in enumerate(lines) if ln.strip().startswith(_FOOTER_MARKER)
    )

    # Anchor the block start on a Lookup-strategy header; failing that, on the
    # first legacy codebeacon heading that appears before the footer.
    start_idx: int | None = None
    for i, ln in enumerate(lines[:footer_idx]):
        if any(ln.strip().startswith(p) for p in _BLOCK_START_HEADINGS):
            start_idx = i
            break
    if start_idx is None:
        for i, ln in enumerate(lines[:footer_idx]):
            if any(ln.strip().startswith(p) for p in _LEGACY_PATTERNS):
                start_idx = i
                break
    if start_idx is None:
        # Footer present but no recognizable codebeacon heading to anchor on —
        # leave the file untouched rather than guess at the block boundaries.
        return existing.strip()

    kept = lines[:start_idx] + lines[footer_idx + 1:]
    return "\n".join(kept).strip()


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


def _merge_rules_content(frontmatter: str, body: str, path: Path) -> str:
    """Return the final rules-file text: YAML frontmatter, then the codebeacon
    block, then any user content that follows it.

    A rules file differs from CLAUDE.md in that its ``paths:`` frontmatter is
    codebeacon-generated and MUST sit at the very top (Claude Code only reads
    frontmatter as the file's first bytes), so the frontmatter + marker block
    form the managed region and user content is preserved only BELOW the end
    marker. Regenerating rewrites the frontmatter and block while keeping that
    trailing user tail. A pre-existing hand-authored file with no markers is
    kept whole below the fresh block rather than discarded.
    """
    block = f"{_BLOCK_START}\n{body.rstrip()}\n{_BLOCK_END}\n"
    generated = f"{frontmatter.rstrip()}\n{block}"

    if not path.exists():
        return generated

    existing = path.read_text(encoding="utf-8")
    if _BLOCK_START in existing and _BLOCK_END in existing:
        tail = existing[existing.index(_BLOCK_END) + len(_BLOCK_END):].strip()
    elif _BLOCK_START not in existing:
        tail = existing.strip()  # hand-authored, no block — keep it all, below
    else:
        tail = ""  # start marker but no end (truncated) — regenerate clean

    if tail:
        return f"{generated}\n{tail}\n"
    return generated


# ── Public entry point ─────────────────────────────────────────────────────────

def generate_context_map(
    G: nx.DiGraph,
    output_dir: str | Path,
    projects: list[ProjectInfo],
    obsidian_dir: str | Path | None = None,
    targets: list[str] | None = None,
    rules_split: bool = True,
) -> list[str]:
    """Generate CLAUDE.md, .cursorrules, and AGENTS.md context map files.

    Files are written to the parent of output_dir (i.e. alongside .codebeacon/).

    Args:
        G:           knowledge graph
        output_dir:  .codebeacon/ directory path
        projects:    list of ProjectInfo (name, path, framework, language)
        obsidian_dir: custom obsidian vault path; defaults to output_dir/obsidian
        targets:     which files to generate; defaults to all three
        rules_split: in a multi-project workspace, move per-project detail out of
                     CLAUDE.md into scoped .claude/rules/ files (default on).
                     Disable to keep the old monolithic CLAUDE.md.

    Returns:
        List of absolute paths of files written (context map files, plus any
        .claude/rules/ files when the workspace split is active).
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

    # Repo-level plugins (scanned once at the project root, not per-project).
    repo_type      = classify_repo_type(project_root, projects)
    skills_section = format_skills_section(detect_skills(project_root))
    hooks_section  = format_hooks_section(detect_hooks(project_root))

    # Collapse duplicate project rows before rendering any surface (see
    # _dedupe_projects). Done after repo-type classification so that heuristic
    # still sees every discovered project. The pre-dedup list is retained so a
    # name shared by several directories still contributes every one to its
    # rules-file `paths:` scope.
    all_projects = list(projects)
    projects = _dedupe_projects(projects)

    def _render(tool: str, split: bool) -> str:
        return _build_content(
            G, projects, output_path, obs_path, stats, hubs, tool=tool,
            repo_type=repo_type,
            skills_section=skills_section,
            hooks_section=hooks_section,
            split=split,
        )

    written: list[str] = []
    targets_to_files = {
        "CLAUDE.md": "claude",
        ".cursorrules": "cursor",
        "AGENTS.md": "agents",
    }
    for fname, tool in targets_to_files.items():
        if fname not in targets:
            continue
        # The split is a Claude Code feature (.claude/rules/ with scoped `paths:`
        # frontmatter) and only pays off across a multi-project workspace: the
        # Cursor/Codex files and single-project output stay monolithic.
        do_split = rules_split and tool == "claude" and len(projects) > 1
        path = project_root / fname
        path.write_text(_merge_content(_render(tool, do_split), path), encoding="utf-8")
        written.append(str(path))
        if do_split:
            written += _write_rules_files(
                G, projects, all_projects, project_root, stats, obs_path
            )

    return written
