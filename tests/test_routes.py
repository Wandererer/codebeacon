"""Integration tests for route extraction across frameworks.

Requires tree-sitter grammar packages. Tests are skipped if the grammar
for a given language is not installed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.extract.routes import extract_routes

FIXTURES = Path(__file__).parent / "fixtures"


class TestSpringBootRoutes:
    def test_get_routes_extracted(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        routes = extract_routes(str(spring_fixture), "spring-boot", str(spring_fixture.parent))
        methods = {r.method for r in routes}
        assert "GET" in methods

    def test_post_route_extracted(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        routes = extract_routes(str(spring_fixture), "spring-boot", str(spring_fixture.parent))
        methods = {r.method for r in routes}
        assert "POST" in methods

    def test_route_paths_not_empty(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        routes = extract_routes(str(spring_fixture), "spring-boot", str(spring_fixture.parent))
        assert all(r.path for r in routes)

    def test_handler_names_set(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        routes = extract_routes(str(spring_fixture), "spring-boot", str(spring_fixture.parent))
        assert all(r.handler for r in routes)

    def test_framework_field(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        routes = extract_routes(str(spring_fixture), "spring-boot", str(spring_fixture.parent))
        assert all(r.framework == "spring-boot" for r in routes)


class TestFastAPIRoutes:
    def test_get_routes_extracted(self, fastapi_fixture):
        pytest.importorskip("tree_sitter_python")
        routes = extract_routes(str(fastapi_fixture), "fastapi", str(fastapi_fixture.parent))
        methods = {r.method for r in routes}
        assert "GET" in methods

    def test_post_route_extracted(self, fastapi_fixture):
        pytest.importorskip("tree_sitter_python")
        routes = extract_routes(str(fastapi_fixture), "fastapi", str(fastapi_fixture.parent))
        methods = {r.method for r in routes}
        assert "POST" in methods

    def test_route_count(self, fastapi_fixture):
        pytest.importorskip("tree_sitter_python")
        routes = extract_routes(str(fastapi_fixture), "fastapi", str(fastapi_fixture.parent))
        # FastAPI fixture has 5 routes (GET /users, GET /users/{id}, POST, PUT, DELETE)
        assert len(routes) >= 3

    def test_path_contains_users(self, fastapi_fixture):
        pytest.importorskip("tree_sitter_python")
        routes = extract_routes(str(fastapi_fixture), "fastapi", str(fastapi_fixture.parent))
        paths = {r.path for r in routes}
        assert any("users" in p for p in paths)


class TestFlaskRoutes:
    def test_routes_extracted(self, flask_fixture):
        pytest.importorskip("tree_sitter_python")
        routes = extract_routes(str(flask_fixture), "flask", str(flask_fixture.parent))
        assert len(routes) >= 1

    def test_get_route(self, flask_fixture):
        pytest.importorskip("tree_sitter_python")
        routes = extract_routes(str(flask_fixture), "flask", str(flask_fixture.parent))
        methods = {r.method for r in routes}
        assert "GET" in methods


class TestExpressRoutes:
    def test_routes_extracted(self, express_fixture):
        pytest.importorskip("tree_sitter_javascript")
        routes = extract_routes(str(express_fixture), "express", str(express_fixture.parent))
        assert len(routes) >= 1

    def test_get_route(self, express_fixture):
        pytest.importorskip("tree_sitter_javascript")
        routes = extract_routes(str(express_fixture), "express", str(express_fixture.parent))
        methods = {r.method for r in routes}
        assert "GET" in methods


class TestNestJSRoutes:
    def test_routes_extracted(self, nestjs_fixture):
        pytest.importorskip("tree_sitter_typescript")
        routes = extract_routes(str(nestjs_fixture), "nestjs", str(nestjs_fixture.parent))
        assert len(routes) >= 1

    def test_get_route(self, nestjs_fixture):
        pytest.importorskip("tree_sitter_typescript")
        routes = extract_routes(str(nestjs_fixture), "nestjs", str(nestjs_fixture.parent))
        methods = {r.method for r in routes}
        assert "GET" in methods


class TestNonexistentFile:
    def test_missing_file_returns_empty(self):
        routes = extract_routes("/nonexistent/path/file.py", "fastapi", "/nonexistent")
        assert routes == []
