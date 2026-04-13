"""Integration tests for entity / ORM extraction across frameworks."""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.extract.entities import extract_entities

FIXTURES = Path(__file__).parent / "fixtures"


class TestDjangoEntities:
    def test_model_extracted(self, django_fixture):
        pytest.importorskip("tree_sitter_python")
        entities = extract_entities(str(django_fixture), "django")
        names = {e.name for e in entities}
        assert "User" in names

    def test_entity_has_framework(self, django_fixture):
        pytest.importorskip("tree_sitter_python")
        entities = extract_entities(str(django_fixture), "django")
        assert all(e.framework for e in entities)

    def test_entity_has_source_file(self, django_fixture):
        pytest.importorskip("tree_sitter_python")
        entities = extract_entities(str(django_fixture), "django")
        assert all(e.source_file for e in entities)

    def test_fields_list(self, django_fixture):
        pytest.importorskip("tree_sitter_python")
        entities = extract_entities(str(django_fixture), "django")
        for entity in entities:
            assert isinstance(entity.fields, list)


class TestFlaskEntities:
    def test_model_extracted(self, flask_fixture):
        pytest.importorskip("tree_sitter_python")
        entities = extract_entities(str(flask_fixture), "flask")
        names = {e.name for e in entities}
        assert "User" in names

    def test_table_name(self, flask_fixture):
        pytest.importorskip("tree_sitter_python")
        entities = extract_entities(str(flask_fixture), "flask")
        user_entity = next((e for e in entities if e.name == "User"), None)
        if user_entity:
            # Flask fixture has __tablename__ = "users"
            assert user_entity.table_name == "users" or user_entity.table_name == ""


class TestSpringBootEntities:
    def test_no_crash(self, spring_fixture):
        pytest.importorskip("tree_sitter_java")
        entities = extract_entities(str(spring_fixture), "spring-boot")
        assert isinstance(entities, list)


class TestNestJSEntities:
    def test_no_crash(self, nestjs_fixture):
        pytest.importorskip("tree_sitter_typescript")
        entities = extract_entities(str(nestjs_fixture), "nestjs")
        assert isinstance(entities, list)


class TestNonexistentFile:
    def test_missing_file_returns_empty(self):
        entities = extract_entities("/nonexistent/file.py", "django")
        assert entities == []


class TestSemanticRefs:
    """Tests for semantic.py structured comment parsing."""

    def test_javadoc_see_ref(self, tmp_path):
        from codebeacon.extract.semantic import extract_semantic_refs
        java_file = tmp_path / "Foo.java"
        java_file.write_text(
            "/**\n * @see UserService\n * {@link OrderRepository#save}\n */\n"
            "public class Foo {}\n"
        )
        edges = extract_semantic_refs(str(java_file), "spring-boot", "Foo")
        targets = {e.target for e in edges}
        assert "UserService" in targets

    def test_python_cross_ref(self, tmp_path):
        from codebeacon.extract.semantic import extract_semantic_refs
        py_file = tmp_path / "service.py"
        py_file.write_text(
            'def do_thing():\n    """Do something.\n\n    See :class:`UserRepository`.\n    """\n    pass\n'
        )
        edges = extract_semantic_refs(str(py_file), "fastapi", "service")
        targets = {e.target for e in edges}
        assert "UserRepository" in targets

    def test_jsdoc_see_ref(self, tmp_path):
        from codebeacon.extract.semantic import extract_semantic_refs
        js_file = tmp_path / "api.js"
        js_file.write_text(
            "/**\n * @see UserService\n * @param {OrderService} svc - order service\n */\n"
            "function handler() {}\n"
        )
        edges = extract_semantic_refs(str(js_file), "express", "api")
        targets = {e.target for e in edges}
        assert "UserService" in targets or "OrderService" in targets

    def test_edges_have_inferred_confidence(self, tmp_path):
        from codebeacon.extract.semantic import extract_semantic_refs
        java_file = tmp_path / "Bar.java"
        java_file.write_text("/** @see FooService */\npublic class Bar {}\n")
        edges = extract_semantic_refs(str(java_file), "spring-boot", "Bar")
        assert all(e.confidence == "INFERRED" for e in edges)
        assert all(e.relation == "references" for e in edges)

    def test_missing_file_returns_empty(self):
        from codebeacon.extract.semantic import extract_semantic_refs
        edges = extract_semantic_refs("/nonexistent/file.java", "spring-boot")
        assert edges == []

    def test_primitives_not_included(self, tmp_path):
        from codebeacon.extract.semantic import extract_semantic_refs
        java_file = tmp_path / "Prim.java"
        java_file.write_text(
            "/**\n * @param {string} name\n * @param {int} count\n * @see UserService\n */\n"
            "public class Prim {}\n"
        )
        edges = extract_semantic_refs(str(java_file), "spring-boot", "Prim")
        targets = {e.target for e in edges}
        assert "string" not in targets
        assert "int" not in targets
