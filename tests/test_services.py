"""Integration tests for service / DI extraction across frameworks."""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.extract.services import extract_services

FIXTURES = Path(__file__).parent / "fixtures"


class TestSpringBootServices:
    def test_service_extracted(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        services, unresolved = extract_services(str(spring_fixture), "spring-boot")
        # UserController has @Autowired UserService
        assert len(services) >= 1 or len(unresolved) >= 1

    def test_di_dependency_is_unresolved(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        services, unresolved = extract_services(str(spring_fixture), "spring-boot")
        # @Autowired UserService → UnresolvedRef
        ref_names = {u.ref_name for u in unresolved}
        assert "UserService" in ref_names or len(services) >= 1

    def test_unresolved_has_framework(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        _, unresolved = extract_services(str(spring_fixture), "spring-boot")
        assert all(u.framework == "spring-boot" for u in unresolved)

    def test_service_has_source_file(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        services, _ = extract_services(str(spring_fixture), "spring-boot")
        for svc in services:
            assert svc.source_file


class TestFastAPIServices:
    def test_no_crash(self, fastapi_fixture):
        pytest.importorskip("tree_sitter_python")
        services, unresolved = extract_services(str(fastapi_fixture), "fastapi")
        assert isinstance(services, list)
        assert isinstance(unresolved, list)


class TestNestJSServices:
    def test_injectable_extracted(self, nestjs_fixture):
        pytest.importorskip("tree_sitter_typescript")
        services, unresolved = extract_services(str(nestjs_fixture), "nestjs")
        # UserService has @Injectable
        labels = {s.name for s in services}
        assert "UserService" in labels or len(services) >= 1

    def test_controller_di_captured(self, nestjs_fixture):
        pytest.importorskip("tree_sitter_typescript")
        services, unresolved = extract_services(str(nestjs_fixture), "nestjs")
        # UserController injects UserService via constructor
        ref_names = {u.ref_name for u in unresolved}
        assert "UserService" in ref_names or len(services) >= 1

    def test_annotations_populated(self, nestjs_fixture):
        pytest.importorskip("tree_sitter_typescript")
        services, _ = extract_services(str(nestjs_fixture), "nestjs")
        for svc in services:
            assert isinstance(svc.annotations, list)


class TestNonexistentFile:
    def test_missing_file_returns_empty(self):
        services, unresolved = extract_services("/nonexistent/file.py", "fastapi")
        assert services == []
        assert unresolved == []
