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
