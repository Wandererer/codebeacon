"""Workspace CLAUDE.md diet: split per-project detail into .claude/rules/ files.

Anthropic's guidance is to keep a CLAUDE.md under ~200 lines ("longer files
consume more context and reduce adherence"). codebeacon's single-project output
is already small, but the workspace (multi-project) output grew to hundreds of
lines because it inlined per-project Common Commands + Architecture + a Notes
row for every project. This module pins the diet:

  * workspace CLAUDE.md stays a compact, deduplicated index (≤200 lines);
  * per-project detail moves to `.claude/rules/codebeacon-<project>.md`, each
    carrying YAML `paths:` frontmatter so Claude Code loads it only when that
    project's files are edited;
  * the duplicate-project-rows bug (same name from several discovered dirs) is
    gone — one row, one rules file, but the frontmatter scopes every dir;
  * single-project output and the Cursor/Codex files are untouched;
  * regenerating preserves user content outside the codebeacon markers in both
    the CLAUDE.md and the rules files (do not regress the 0.6.9 merge fix).
"""
from __future__ import annotations

import re
from pathlib import Path

import networkx as nx
import yaml

from codebeacon.common.types import ProjectInfo
from codebeacon.contextmap.generator import (
    _BLOCK_END,
    _BLOCK_START,
    _dedupe_projects,
    _slugify_project,
    generate_context_map,
)

# A Projects stats-table data row: `| <name> | <framework> | R | S | E | C ...`.
# Anchored on the four trailing integer columns so it never matches the Step-2
# Notes table row (`| <name> | 3 services | ...`), which shares the leading cell.
def _projects_rows(text: str, name: str) -> list[str]:
    pat = rf"^\| {re.escape(name)} \| [\w.\-]+ \| \d+ \| \d+ \| \d+ \| \d+"
    return re.findall(pat, text, re.M)


# ── Fixtures / builders ──────────────────────────────────────────────────────

_FRAMEWORKS = [
    "spring-boot", "python", "nextjs", "react", "express", "sveltekit",
    "tauri", "vapor", "fastapi", "flask", "rails", "gin", "echo",
]
_LANG = {
    "spring-boot": "java", "python": "python", "nextjs": "typescript",
    "react": "typescript", "express": "typescript", "sveltekit": "typescript",
    "tauri": "rust", "vapor": "swift", "fastapi": "python", "flask": "python",
    "rails": "ruby", "gin": "go", "echo": "go",
}


def _workspace(tmp_path: Path, n: int) -> tuple[nx.DiGraph, list[ProjectInfo]]:
    """An n-project workspace: each project is a subdir with 3 services + a route."""
    G = nx.DiGraph()
    projects: list[ProjectInfo] = []
    for i in range(n):
        name = f"proj{i}"
        fw = _FRAMEWORKS[i % len(_FRAMEWORKS)]
        pdir = tmp_path / name
        pdir.mkdir()
        projects.append(ProjectInfo(name=name, path=str(pdir), framework=fw,
                                    language=_LANG[fw], signature_file="sig"))
        for j in range(3):
            G.add_node(f"{name}-svc{j}", project=name, type="class", label=f"Svc{j}",
                       annotations=[], source_file=str(pdir / f"s{j}.py"))
        G.add_node(f"{name}-route", project=name, type="route", label="/x")
    return G, projects


def _gen(tmp_path: Path, G, projects, targets=None, rules_split=True) -> Path:
    """Run generate_context_map rooted at tmp_path; return the project root."""
    cb = tmp_path / ".codebeacon"
    if not cb.exists():
        cb.mkdir()
    generate_context_map(G, cb, projects, targets=targets or ["CLAUDE.md"],
                         rules_split=rules_split)
    return tmp_path


# ── (a) CLAUDE.md stays under the line budget ────────────────────────────────

def test_workspace_claude_md_under_200_lines(tmp_path):
    G, projects = _workspace(tmp_path, 44)
    root = _gen(tmp_path, G, projects)
    n = len((root / "CLAUDE.md").read_text(encoding="utf-8").splitlines())
    assert n <= 200, f"workspace CLAUDE.md is {n} lines (>200)"


def test_workspace_claude_md_omits_per_project_detail(tmp_path):
    # Per-project Common Commands / Architecture / Notes table are moved out.
    G, projects = _workspace(tmp_path, 12)
    root = _gen(tmp_path, G, projects)
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Common Commands" not in text
    assert "## Architecture" not in text
    assert "| Project | Notes | Example |" not in text
    # But the compact Projects index and rules pointers remain.
    assert "## Projects" in text
    assert ".claude/rules/codebeacon-proj0.md" in text
    assert "| Detail |" in text


# ── (b) rules files exist with valid, scoped YAML frontmatter ────────────────

def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "rules file must open with YAML frontmatter"
    _, fm, _rest = text.split("---\n", 2)
    return yaml.safe_load(fm)


def test_rules_files_have_valid_paths_frontmatter(tmp_path):
    G, projects = _workspace(tmp_path, 5)
    root = _gen(tmp_path, G, projects)
    rules_dir = root / ".claude" / "rules"
    files = sorted(rules_dir.glob("codebeacon-*.md"))
    assert len(files) == 5

    for f in files:
        text = f.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        assert "paths" in fm and isinstance(fm["paths"], list) and fm["paths"]
        # Body carries the per-project detail behind codebeacon markers.
        assert _BLOCK_START in text and _BLOCK_END in text
        assert "### Commands" in text
        assert "### Architecture" in text
        assert "### Class notes" in text


def test_rules_paths_scope_to_the_right_dir(tmp_path):
    G, projects = _workspace(tmp_path, 3)
    root = _gen(tmp_path, G, projects)
    fm = _parse_frontmatter(
        (root / ".claude" / "rules" / "codebeacon-proj1.md").read_text(encoding="utf-8")
    )
    assert fm["paths"] == ["proj1/**"]


def test_rules_body_is_absent_from_workspace_claude_md(tmp_path):
    # The commands block for a project lives ONLY in its rules file, not CLAUDE.md.
    G, projects = _workspace(tmp_path, 4)
    root = _gen(tmp_path, G, projects)
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    rules = (root / ".claude" / "rules" / "codebeacon-proj0.md").read_text(encoding="utf-8")
    assert "### Commands" in rules
    assert "### Commands" not in claude


# ── (c) merge-preservation: user content outside markers survives regenerate ──

def test_regenerate_preserves_user_content_in_claude_md(tmp_path):
    G, projects = _workspace(tmp_path, 6)
    root = _gen(tmp_path, G, projects)
    claude = root / "CLAUDE.md"

    original = claude.read_text(encoding="utf-8")
    marker = "## Team Notes\n\nCRITICAL: never run migrations against prod directly.\n"
    claude.write_text(original + "\n" + marker, encoding="utf-8")

    # Regenerate on top of the edited file.
    _gen(tmp_path, G, projects)
    after = claude.read_text(encoding="utf-8")
    assert "CRITICAL: never run migrations against prod directly." in after
    assert after.count("<!-- codebeacon:start -->") == 1


def test_regenerate_preserves_user_content_in_rules_file(tmp_path):
    G, projects = _workspace(tmp_path, 3)
    root = _gen(tmp_path, G, projects)
    rules = root / ".claude" / "rules" / "codebeacon-proj0.md"

    original = rules.read_text(encoding="utf-8")
    # Frontmatter must be first; user note goes below the end marker.
    assert original.startswith("---\n")
    rules.write_text(
        original + "\n## My notes\n\nproj0 owns the billing ledger — tread carefully.\n",
        encoding="utf-8",
    )

    _gen(tmp_path, G, projects)
    after = rules.read_text(encoding="utf-8")
    assert "proj0 owns the billing ledger — tread carefully." in after
    # Frontmatter still first, and exactly one generated block after re-merge.
    assert after.startswith("---\n")
    assert after.count(_BLOCK_START) == 1
    assert after.count(_BLOCK_END) == 1
    # The scoped paths block is intact.
    assert _parse_frontmatter(after)["paths"] == ["proj0/**"]


# ── (d) dedup: a name shared by several dirs renders once, scopes to all ──────

def test_duplicate_project_names_collapse_to_one_row(tmp_path):
    G, projects = _workspace(tmp_path, 3)
    # Add two more dirs both named "proj0" (like APT/frontend + Tri/frontend).
    for extra in ("dup_a", "dup_b"):
        d = tmp_path / extra
        d.mkdir()
        projects.append(ProjectInfo(name="proj0", path=str(d), framework="react",
                                    language="typescript", signature_file="sig"))
    root = _gen(tmp_path, G, projects)
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")

    # Exactly one Projects-table row for proj0 (was 3 before the dedup fix).
    assert len(_projects_rows(text, "proj0")) == 1
    # One rules file, and its paths scope covers every dir that shares the name.
    rules = root / ".claude" / "rules" / "codebeacon-proj0.md"
    assert rules.exists()
    paths = _parse_frontmatter(rules.read_text(encoding="utf-8"))["paths"]
    assert set(paths) == {"proj0/**", "dup_a/**", "dup_b/**"}


def test_dedupe_projects_is_order_preserving():
    ps = [
        ProjectInfo("a", "/x/a", "react", "typescript", "sig"),
        ProjectInfo("b", "/x/b", "fastapi", "python", "sig"),
        ProjectInfo("a", "/y/a", "node", "typescript", "sig"),  # dup name
    ]
    out = _dedupe_projects(ps)
    assert [p.name for p in out] == ["a", "b"]
    # First occurrence wins (react, not the later node entry).
    assert out[0].framework == "react"


# ── (e) single-project mode is unchanged (no split) ──────────────────────────

def test_single_project_stays_monolithic(tmp_path):
    G = nx.DiGraph()
    G.add_node("s1", project="solo", type="class", label="Svc",
               source_file=str(tmp_path / "solo" / "s.py"))
    (tmp_path / "solo").mkdir()
    projects = [ProjectInfo(name="solo", path=str(tmp_path / "solo"),
                            framework="fastapi", language="python", signature_file="sig")]
    root = _gen(tmp_path, G, projects)
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")

    # Old monolithic shape: inline commands + architecture, no rules split.
    assert "## Common Commands" in text
    assert "## Architecture" in text
    assert "| Detail |" not in text
    assert not (root / ".claude" / "rules").exists()


# ── config knob: rules_split=False keeps the monolithic workspace file ───────

def test_rules_split_false_disables_split(tmp_path):
    G, projects = _workspace(tmp_path, 8)
    root = _gen(tmp_path, G, projects, rules_split=False)
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")

    assert "## Common Commands" in text
    assert "## Architecture" in text
    assert not (root / ".claude" / "rules").exists()
    # Dedup still applies even with the split off (it is a separate bug fix).
    assert "| Detail |" not in text


# ── the split is Claude-specific: Cursor/Codex files stay monolithic ─────────

def test_cursor_and_agents_files_stay_monolithic(tmp_path):
    G, projects = _workspace(tmp_path, 10)
    root = _gen(tmp_path, G, projects,
                targets=["CLAUDE.md", ".cursorrules", "AGENTS.md"])

    cursor = (root / ".cursorrules").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for text in (cursor, agents):
        # Full per-project detail is retained for the non-Claude tools.
        assert "## Common Commands" in text
        assert "## Architecture" in text
        assert "| Detail |" not in text
    # Only Claude's file gains the rules split.
    assert (root / ".claude" / "rules" / "codebeacon-proj0.md").exists()


# ── dedup also fixes the duplicate rows in Cursor/Codex output ────────────────

def test_dedup_applies_to_all_tools(tmp_path):
    G, projects = _workspace(tmp_path, 2)
    for extra in ("dup_a",):
        d = tmp_path / extra
        d.mkdir()
        projects.append(ProjectInfo(name="proj0", path=str(d), framework="react",
                                    language="typescript", signature_file="sig"))
    root = _gen(tmp_path, G, projects,
                targets=["CLAUDE.md", ".cursorrules", "AGENTS.md"])
    for fname in ("CLAUDE.md", ".cursorrules", "AGENTS.md"):
        text = (root / fname).read_text(encoding="utf-8")
        assert len(_projects_rows(text, "proj0")) == 1, fname


# ── slug safety ──────────────────────────────────────────────────────────────

def test_slugify_project_is_filesystem_safe():
    assert _slugify_project("web") == "web"
    assert _slugify_project("datapopcorn-ai-magic.git") == "datapopcorn-ai-magic.git"
    assert _slugify_project("a/b c") == "a-b-c"
    assert _slugify_project("///") == "project"


# ── integration: real discovered fixture workspace ───────────────────────────

def test_fixture_workspace_scopes_to_discovered_dirs(tmp_path):
    """Use the real fixture's discovered project paths to check the `paths:`
    globs are relativized against the project root."""
    from codebeacon.discover.detector import discover_projects

    fixture = Path(__file__).parent / "fixtures" / "integration_workspace"
    discovered = discover_projects([str(fixture)])
    names = {p.name for p in discovered}
    assert {"web", "api-python"} <= names

    # Rebase the discovered paths under tmp_path so we can write outputs safely
    # without touching the checked-in fixture.
    projects = []
    G = nx.DiGraph()
    for p in discovered:
        rel = Path(p.path).name  # "web" / "api-python"
        pdir = tmp_path / rel
        pdir.mkdir(exist_ok=True)
        projects.append(ProjectInfo(name=p.name, path=str(pdir), framework=p.framework,
                                    language=p.language, signature_file=p.signature_file))
        G.add_node(f"{p.name}-c", project=p.name, type="class", label="X",
                   source_file=str(pdir / "x"))

    root = _gen(tmp_path, G, projects)
    for p in projects:
        fm = _parse_frontmatter(
            (root / ".claude" / "rules" / f"codebeacon-{p.name}.md").read_text(encoding="utf-8")
        )
        assert fm["paths"] == [f"{p.name}/**"]
