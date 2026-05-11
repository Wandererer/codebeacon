"""Tests for plugins (skills, githooks) and repo-type classification."""
from __future__ import annotations

import os
import stat as stat_mod
from pathlib import Path

import pytest

from codebeacon.common.types import ProjectInfo
from codebeacon.discover.detector import classify_repo_type
from codebeacon.plugins.skills import detect_skills, format_skills_section
from codebeacon.plugins.githooks import detect_hooks, format_hooks_section


# ── skills ───────────────────────────────────────────────────────────────────

class TestSkills:
    def test_no_dirs_returns_empty(self, tmp_path):
        assert detect_skills(tmp_path) == []

    def test_flat_md_file_with_frontmatter(self, tmp_path):
        d = tmp_path / ".claude" / "commands"
        d.mkdir(parents=True)
        (d / "ship.md").write_text(
            "---\nname: ship\ndescription: Push, PR, and deploy\n---\n# Ship\nBody.\n"
        )
        skills = detect_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "ship"
        assert skills[0].description == "Push, PR, and deploy"
        assert skills[0].path == ".claude/commands/ship.md"

    def test_fallback_description_first_non_empty_line(self, tmp_path):
        d = tmp_path / ".claude" / "skills"
        d.mkdir(parents=True)
        (d / "qa.md").write_text("# QA\n\nRun integration tests.\n")
        skills = detect_skills(tmp_path)
        assert skills[0].description == "QA"  # heading stripped of '#'

    def test_multiline_block_scalar_description(self, tmp_path):
        """`description: |` followed by indented lines → joined and truncated to first sentence."""
        d = tmp_path / ".claude" / "skills"
        d.mkdir(parents=True)
        (d / "review.md").write_text(
            "---\n"
            "name: review\n"
            "description: |\n"
            "  Plan review skill. Walks through the design interactively.\n"
            "  Use when asked to review a plan.\n"
            "---\n"
            "# Body\n"
        )
        skills = detect_skills(tmp_path)
        assert len(skills) == 1
        # First sentence wins.
        assert skills[0].description == "Plan review skill."

    def test_folded_scalar_description(self, tmp_path):
        """`description: >` (folded) joins lines with spaces too."""
        d = tmp_path / ".claude" / "skills"
        d.mkdir(parents=True)
        (d / "qa.md").write_text(
            "---\ndescription: >\n  Quick QA check\n  for the app\n---\n"
        )
        skills = detect_skills(tmp_path)
        assert skills[0].description == "Quick QA check for the app"

    def test_pipe_indicator_not_used_as_description(self, tmp_path):
        """Guard: a bare `|` must never become the description string."""
        d = tmp_path / ".claude" / "skills"
        d.mkdir(parents=True)
        (d / "broken.md").write_text(
            "---\ndescription: |\n  Real description here.\n---\n"
        )
        skills = detect_skills(tmp_path)
        assert skills[0].description != "|"
        assert "Real description here" in skills[0].description

    def test_long_description_truncated_with_ellipsis(self, tmp_path):
        d = tmp_path / ".claude" / "skills"
        d.mkdir(parents=True)
        long = "word " * 200  # 1000 chars, no periods
        (d / "long.md").write_text(f"---\ndescription: {long.strip()}\n---\n")
        skills = detect_skills(tmp_path)
        assert len(skills[0].description) <= 200
        assert skills[0].description.endswith("…")

    def test_subdir_style_with_skill_md(self, tmp_path):
        d = tmp_path / ".claude" / "skills" / "graphify"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\ndescription: Turn input into a knowledge graph\n---\n"
        )
        skills = detect_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].name == "graphify"
        assert skills[0].description == "Turn input into a knowledge graph"
        assert skills[0].path == ".claude/skills/graphify/SKILL.md"

    def test_dedup_across_dirs_preserves_first(self, tmp_path):
        cmds = tmp_path / ".claude" / "commands"
        cmds.mkdir(parents=True)
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        (cmds / "ship.md").write_text("---\ndescription: first\n---\n")
        (skills_dir / "ship.md").write_text("---\ndescription: dup\n---\n")
        skills = detect_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0].description == "first"

    def test_format_empty_returns_empty_string(self):
        assert format_skills_section([]) == ""

    def test_format_includes_slash_prefix_and_description(self, tmp_path):
        d = tmp_path / ".claude" / "skills"
        d.mkdir(parents=True)
        (d / "ship.md").write_text("---\ndescription: Push and PR\n---\n")
        section = format_skills_section(detect_skills(tmp_path))
        assert "## Claude Skills" in section
        assert "- `/ship` — Push and PR" in section


# ── git hooks ────────────────────────────────────────────────────────────────

def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat_mod.S_IXUSR | stat_mod.S_IXGRP | stat_mod.S_IXOTH)


class TestGitHooks:
    def test_no_hooks_returns_empty(self, tmp_path):
        assert detect_hooks(tmp_path) == []

    def test_lefthook_yaml_parsed(self, tmp_path):
        (tmp_path / "lefthook.yml").write_text(
            "pre-commit:\n"
            "  commands:\n"
            "    lint:\n"
            "      run: npm run lint\n"
            "    test:\n"
            "      run: 'pytest -x'\n"
        )
        hooks = detect_hooks(tmp_path)
        assert len(hooks) == 1
        h = hooks[0]
        assert h.lifecycle == "pre-commit"
        assert h.tool == "lefthook"
        names = {c.name for c in h.commands}
        assert names == {"lint", "test"}
        runs = {c.run for c in h.commands}
        assert "npm run lint" in runs
        assert "pytest -x" in runs

    def test_husky_parsed(self, tmp_path):
        husky = tmp_path / ".husky"
        husky.mkdir()
        (husky / "pre-commit").write_text("#!/bin/sh\n# guard\nnpm test\n")
        hooks = detect_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].tool == "husky"
        assert hooks[0].lifecycle == "pre-commit"
        assert hooks[0].commands[0].run == "npm test"

    def test_raw_hook_requires_executable(self, tmp_path):
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        not_exec = hooks_dir / "pre-commit"
        not_exec.write_text("#!/bin/sh\necho hi\n")
        # not executable yet → ignored
        assert detect_hooks(tmp_path) == []
        _make_executable(not_exec)
        hooks = detect_hooks(tmp_path)
        assert len(hooks) == 1
        assert hooks[0].tool == "raw"

    def test_raw_ignores_sample(self, tmp_path):
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        sample = hooks_dir / "pre-commit.sample"
        sample.write_text("echo hi\n")
        _make_executable(sample)
        assert detect_hooks(tmp_path) == []

    def test_raw_suppressed_when_lefthook_covers_lifecycle(self, tmp_path):
        (tmp_path / "lefthook.yml").write_text(
            "pre-commit:\n  commands:\n    lint:\n      run: npm run lint\n"
        )
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        raw = hooks_dir / "pre-commit"
        raw.write_text("#!/bin/sh\nlefthook run pre-commit\n")
        _make_executable(raw)
        hooks = detect_hooks(tmp_path)
        # Only lefthook should remain; raw delegating to it is suppressed.
        assert len(hooks) == 1
        assert hooks[0].tool == "lefthook"

    def test_format_includes_warning_and_commands(self, tmp_path):
        (tmp_path / "lefthook.yml").write_text(
            "pre-push:\n  commands:\n    test:\n      run: pytest\n"
        )
        section = format_hooks_section(detect_hooks(tmp_path))
        assert "## Git Hooks" in section
        assert "block" in section.lower()
        assert "`pre-push`" in section
        assert "pytest" in section

    def test_format_empty_returns_empty_string(self):
        assert format_hooks_section([]) == ""


# ── repo type classification ─────────────────────────────────────────────────

def _pi(name: str, path: Path) -> ProjectInfo:
    return ProjectInfo(
        name=name, path=str(path), framework="node",
        language="typescript", signature_file=str(path / "package.json"),
        is_multi=True,
    )


class TestRepoType:
    def test_single_project_returns_single(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        proj = _pi("app", tmp_path)
        proj.is_multi = False
        assert classify_repo_type(tmp_path, [proj]) == "single"

    def test_empty_projects_returns_single(self, tmp_path):
        assert classify_repo_type(tmp_path, []) == "single"

    def test_gitmodules_returns_meta(self, tmp_path):
        (tmp_path / ".gitmodules").write_text("[submodule \"a\"]\n")
        a = tmp_path / "a"
        a.mkdir()
        b = tmp_path / "b"
        b.mkdir()
        projects = [_pi("a", a), _pi("b", b)]
        assert classify_repo_type(tmp_path, projects) == "meta"

    def test_k8s_dir_returns_microservices(self, tmp_path):
        (tmp_path / "k8s").mkdir()
        a = tmp_path / "auth"
        a.mkdir()
        b = tmp_path / "payments"
        b.mkdir()
        projects = [_pi("auth", a), _pi("payments", b)]
        assert classify_repo_type(tmp_path, projects) == "microservices"

    def test_multiple_dockerfiles_return_microservices(self, tmp_path):
        a = tmp_path / "auth"
        a.mkdir()
        (a / "Dockerfile").write_text("FROM node\n")
        b = tmp_path / "payments"
        b.mkdir()
        (b / "Dockerfile").write_text("FROM node\n")
        projects = [_pi("auth", a), _pi("payments", b)]
        assert classify_repo_type(tmp_path, projects) == "microservices"

    def test_multiple_projects_no_signals_return_monorepo(self, tmp_path):
        a = tmp_path / "web"
        a.mkdir()
        b = tmp_path / "api"
        b.mkdir()
        projects = [_pi("web", a), _pi("api", b)]
        assert classify_repo_type(tmp_path, projects) == "monorepo"

    def test_single_dockerfile_alone_does_not_trigger_microservices(self, tmp_path):
        a = tmp_path / "web"
        a.mkdir()
        (a / "Dockerfile").write_text("FROM node\n")
        b = tmp_path / "api"
        b.mkdir()
        projects = [_pi("web", a), _pi("api", b)]
        assert classify_repo_type(tmp_path, projects) == "monorepo"
