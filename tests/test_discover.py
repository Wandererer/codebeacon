"""Tests for discover/scanner.py and discover/detector.py."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from codebeacon.discover.scanner import collect_files, IGNORE_DIRS, CODE_EXTENSIONS
from codebeacon.discover.detector import detect_framework, discover_projects, SIGNATURE_MAP


class TestScanner:
    def test_collect_basic_python_files(self, tmp_path):
        """collect_files returns .py files in a directory."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("# util")
        result = collect_files(str(tmp_path))
        names = {Path(f).name for f in result}
        assert "main.py" in names
        assert "utils.py" in names

    def test_ignores_node_modules(self, tmp_path):
        """node_modules is excluded."""
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "lib.js").write_text("// lib")
        (tmp_path / "index.js").write_text("// main")
        result = collect_files(str(tmp_path))
        # Check that the file inside node_modules was NOT collected
        names = {Path(f).name for f in result}
        assert "lib.js" not in names
        assert "index.js" in names

    def test_ignores_all_artifact_dirs(self, tmp_path):
        """All IGNORE_DIRS entries are excluded."""
        # pick 3 representative artifact dirs
        for d in ["target", "dist", "__pycache__"]:
            (tmp_path / d).mkdir()
            (tmp_path / d / "Foo.java").write_text("class Foo{}")
        (tmp_path / "src.java").write_text("class Src{}")
        result = collect_files(str(tmp_path))
        for f in result:
            parts = Path(f).parts
            for bad in ["target", "dist", "__pycache__"]:
                assert bad not in parts

    def test_only_code_extensions(self, tmp_path):
        """Non-code files are excluded."""
        (tmp_path / "readme.md").write_text("# readme")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "main.py").write_text("# code")
        result = collect_files(str(tmp_path))
        names = {Path(f).name for f in result}
        assert "readme.md" not in names
        assert "data.json" not in names
        assert "main.py" in names

    def test_respects_codebeaconignore(self, tmp_path):
        """Files matching .codebeaconignore patterns are excluded."""
        (tmp_path / ".codebeaconignore").write_text("generated\n")
        gen = tmp_path / "generated"
        gen.mkdir()
        (gen / "auto.py").write_text("# auto")
        (tmp_path / "manual.py").write_text("# manual")
        result = collect_files(str(tmp_path))
        names = {Path(f).name for f in result}
        assert "auto.py" not in names
        assert "manual.py" in names

    def test_returns_sorted_paths(self, tmp_path):
        """Results are sorted."""
        for name in ["z.py", "a.py", "m.py"]:
            (tmp_path / name).write_text("# code")
        result = collect_files(str(tmp_path))
        assert result == sorted(result)

    def test_empty_directory(self, tmp_path):
        """Empty directory returns empty list."""
        result = collect_files(str(tmp_path))
        assert result == []


class TestDetector:
    def test_detect_spring_boot_pom(self, tmp_path):
        """pom.xml → spring-boot."""
        (tmp_path / "pom.xml").write_text("<project/>")
        fw, lang, sig = detect_framework(str(tmp_path))
        assert fw == "spring-boot"
        assert lang == "java"

    def test_detect_nestjs_package_json(self, tmp_path):
        """package.json with @nestjs/core → nestjs."""
        (tmp_path / "package.json").write_text('{"dependencies":{"@nestjs/core":"^10"}}')
        fw, lang, sig = detect_framework(str(tmp_path))
        assert fw == "nestjs"

    def test_detect_react_package_json(self, tmp_path):
        """package.json with react → react."""
        (tmp_path / "package.json").write_text('{"dependencies":{"react":"^18","react-dom":"^18"}}')
        fw, lang, sig = detect_framework(str(tmp_path))
        assert fw == "react"

    def test_detect_fastapi_requirements(self, tmp_path):
        """requirements.txt with fastapi → fastapi."""
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\nuvicorn\n")
        fw, lang, sig = detect_framework(str(tmp_path))
        assert fw == "fastapi"

    def test_detect_django_requirements(self, tmp_path):
        """requirements.txt with django → django."""
        (tmp_path / "requirements.txt").write_text("Django>=4.0\n")
        fw, lang, sig = detect_framework(str(tmp_path))
        assert fw == "django"

    def test_detect_go_mod(self, tmp_path):
        """go.mod with gin → gin."""
        (tmp_path / "go.mod").write_text(
            "module example.com/app\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n)\n"
        )
        fw, lang, sig = detect_framework(str(tmp_path))
        assert fw == "gin"

    def test_detect_unknown(self, tmp_path):
        """No signature file → unknown/generic."""
        (tmp_path / "hello.py").write_text("print('hi')")
        fw, lang, sig = detect_framework(str(tmp_path))
        # Should return something, not crash
        assert isinstance(fw, str)

    def test_discover_single_project(self, tmp_path):
        """discover_projects with one pom.xml → one project."""
        (tmp_path / "pom.xml").write_text("<project/>")
        projects = discover_projects([str(tmp_path)])
        assert len(projects) >= 1
        assert any(p.framework == "spring-boot" for p in projects)

    def test_discover_multi_project(self, tmp_path):
        """discover_projects with multiple sub-dirs → multiple projects."""
        api = tmp_path / "api"
        api.mkdir()
        (api / "pom.xml").write_text("<project/>")
        web = tmp_path / "web"
        web.mkdir()
        (web / "package.json").write_text('{"dependencies":{"react":"^18","react-dom":"^18"}}')
        projects = discover_projects([str(tmp_path)])
        assert len(projects) >= 2


class TestNewFeatures_0_6_0:
    """Regression tests for the 0.6.0 scanner patches.

    Each test reproduces the original graphify bug scenario so reverting
    the fix would cause the assertion below to flip.
    """

    def test_skips_nested_worktrees_dir(self, tmp_path):
        """Mirrors graphify #4e80d86. A `worktrees/` directory inside the
        project root (from `git worktree add ../foo`) contains a duplicate
        of another branch's tree. Indexing it doubles every node count."""
        wt = tmp_path / "worktrees" / "feature-x"
        wt.mkdir(parents=True)
        (wt / "leak.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("print('hi')\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "main.py" in names
        assert "leak.py" not in names, "worktrees/ leaked into the file list"

    def test_collects_ets_razor_csproj_extensions(self, tmp_path):
        """Mirrors graphify #52d75bd (.ets) + #8bcfffd (.NET project files).
        Before 0.6.0 these were dropped at the file-collector stage."""
        for fname in ("a.ets", "Page.razor", "View.cshtml", "Web.csproj", "App.sln"):
            (tmp_path / fname).write_text("// stub")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert {"a.ets", "Page.razor", "View.cshtml", "Web.csproj", "App.sln"} <= names

    def test_extra_ignore_filters_files(self, tmp_path):
        """Mirrors the `--exclude PATTERN` flag (graphify #9e6192a).
        Patterns from extra_ignore must be merged with .codebeaconignore."""
        (tmp_path / "keep.py").write_text("x = 1\n")
        (tmp_path / "skip.py").write_text("x = 1\n")
        (tmp_path / "gen.ts").write_text("// generated\n")

        result = collect_files(str(tmp_path), extra_ignore=["skip.py", "*.ts"])
        names = {Path(f).name for f in result}
        assert "keep.py" in names
        assert "skip.py" not in names
        assert "gen.ts" not in names


class TestDotFolderNegation:
    """Regressions mirroring codesight #41 (dot-folder negation) and #42
    (parent-level negation must not override descendant ignores).

    Our ``IgnoreMatcher`` follows gitignore-style "self-match wins, positive
    ancestor sticks" semantics: ``!.source`` re-includes ``.source`` itself,
    not arbitrary descendants. To re-include descendants explicitly, the user
    writes ``!.source/**``.
    """

    def test_dot_folder_re_included_by_negation(self, tmp_path):
        (tmp_path / ".codebeaconignore").write_text("!.source\n")
        src = tmp_path / ".source"
        src.mkdir()
        (src / "keep.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("print('hi')\n")
        result = collect_files(str(tmp_path))
        rels = {Path(f).relative_to(tmp_path).as_posix() for f in result}
        assert ".source/keep.py" in rels
        assert "main.py" in rels

    def test_nested_dot_folder_inside_re_included_remains_excluded(self, tmp_path):
        """`!.source` re-includes `.source` only — `.source/.vs` is still
        subject to the default hidden-dir skip."""
        (tmp_path / ".codebeaconignore").write_text("!.source\n")
        src = tmp_path / ".source"
        src.mkdir()
        (src / "keep.py").write_text("x = 1\n")
        vs = src / ".vs"
        vs.mkdir()
        (vs / "skip.py").write_text("x = 1\n")
        result = collect_files(str(tmp_path))
        rels = {Path(f).relative_to(tmp_path).as_posix() for f in result}
        assert ".source/keep.py" in rels
        assert all(not p.startswith(".source/.vs/") for p in rels), rels

    def test_positive_deep_ignore_wins_over_parent_level_negation(self, tmp_path):
        """codesight #42 regression: a deeper positive ignore must not be
        silently overridden by a parent-level ``!`` rule."""
        (tmp_path / ".codebeaconignore").write_text(
            ".source/testfolder\n!.source\n"
        )
        src = tmp_path / ".source"
        (src / "testfolder").mkdir(parents=True)
        (src / "keep.py").write_text("x = 1\n")
        (src / "testfolder" / "skip.py").write_text("x = 1\n")
        result = collect_files(str(tmp_path))
        rels = {Path(f).relative_to(tmp_path).as_posix() for f in result}
        assert ".source/keep.py" in rels
        assert all("testfolder" not in p for p in rels), rels

    def test_explicit_recursive_negation_re_includes_descendants(self, tmp_path):
        """Opt-in recursive negation via ``!.source/**`` (self-matches
        descendants), the official escape hatch."""
        (tmp_path / ".codebeaconignore").write_text("!.source\n!.source/**\n")
        src = tmp_path / ".source"
        vs = src / ".vs"
        vs.mkdir(parents=True)
        (src / "keep.py").write_text("x = 1\n")
        (vs / "lib.py").write_text("x = 1\n")
        result = collect_files(str(tmp_path))
        rels = {Path(f).relative_to(tmp_path).as_posix() for f in result}
        assert ".source/keep.py" in rels
        assert ".source/.vs/lib.py" in rels


class TestGitignoreFallback:
    """Mirrors graphify #9e6192a. When .codebeaconignore is absent, fall
    back to .gitignore so users don't have to maintain two ignore files."""

    def test_reads_codebeaconignore_when_present(self, tmp_path):
        from codebeacon.discover.scanner import read_ignore_file

        (tmp_path / ".codebeaconignore").write_text("primary/\n")
        (tmp_path / ".gitignore").write_text("fallback/\n")
        lines = read_ignore_file(tmp_path)
        assert lines == ["primary/"], "primary ignore must win when present"

    def test_falls_back_to_gitignore_when_codebeaconignore_absent(self, tmp_path):
        from codebeacon.discover.scanner import read_ignore_file

        (tmp_path / ".gitignore").write_text("build/\n*.log\n")
        assert read_ignore_file(tmp_path) == ["build/", "*.log"]

    def test_returns_empty_when_both_absent(self, tmp_path):
        from codebeacon.discover.scanner import read_ignore_file

        assert read_ignore_file(tmp_path) == []

    def test_fallback_can_be_disabled(self, tmp_path):
        from codebeacon.discover.scanner import read_ignore_file

        (tmp_path / ".gitignore").write_text("build/\n")
        assert read_ignore_file(tmp_path, gitignore_fallback=False) == []

    def test_gitignore_actually_skips_files_end_to_end(self, tmp_path):
        """End-to-end: .gitignore should prune files during collection too."""
        (tmp_path / ".gitignore").write_text("ignored.py\n")
        (tmp_path / "ignored.py").write_text("x = 1\n")
        (tmp_path / "kept.py").write_text("x = 1\n")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "kept.py" in names
        assert "ignored.py" not in names
