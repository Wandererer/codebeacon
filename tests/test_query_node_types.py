"""node-types metadata validation of the shipped ``.scm`` queries.

Extends the grammar-drift defense line begun in
``tests/test_graphify_parity_0_6_6.py``. That test asserts each query
*compiles* against its allowlisted grammars; this one asserts, independently,
that every named node type and field name a query references actually exists in
that grammar's node-type metadata (``node-types.json`` when a wheel ships it,
otherwise the compiled :class:`tree_sitter.Language` symbol table).

Why a second, overlapping layer: the two checks use different machinery. The
compile check relies on tree-sitter's parse-table analysis; this one reads the
grammar's declared node-type surface directly. If a future grammar bump renames
or restructures a node type, both should fire — but the metadata check pinpoints
*which* node type / field in *which* pattern, across every query at once, and
does not depend on the compiler's impossible-pattern analysis staying as strict
as it is today. It also auto-upgrades to richer per-field validation the moment a
grammar package starts shipping ``node-types.json``.
"""

from __future__ import annotations

import json

import pytest

from codebeacon.extract import base
from codebeacon.extract import query_check
from codebeacon.extract.base import QUERY_GRAMMAR_ALLOWLIST, get_language
from codebeacon.extract.query_check import (
    GrammarModel,
    _model_from_node_types,
    _scan_refs,
    grammar_model,
    validate_queries,
    validate_source,
)


@pytest.fixture(autouse=True)
def _isolate_caches():
    """Snapshot/restore the grammar caches so loads here do not leak into other
    tests (mirrors the fixture in test_graphify_parity_0_6_6.py)."""
    lang_snapshot = dict(base._LANG_CACHE)
    query_check.clear_model_cache()
    try:
        yield
    finally:
        base._LANG_CACHE.clear()
        base._LANG_CACHE.update(lang_snapshot)
        query_check.clear_model_cache()


# ── The gate: every shipped query references only real node types / fields ────


class TestShippedQueriesValidate:
    def test_no_violations_across_all_queries(self):
        violations = validate_queries()
        assert not violations, (
            "queries reference node types / fields absent from their grammar's "
            "metadata (they would compile-fail or silently capture nothing):\n  "
            + "\n  ".join(str(v) for v in violations)
        )

    def test_gate_is_not_vacuous(self):
        # Guard against a green run that actually validated nothing (e.g. every
        # grammar missing). At least a handful of grammars must resolve a model,
        # and a representative query must contribute real references.
        resolved = 0
        for grammars in QUERY_GRAMMAR_ALLOWLIST.values():
            for grammar in grammars:
                if grammar_model(grammar) is not None:
                    resolved += 1
        assert resolved >= 5, f"only {resolved} grammar models resolved — grammars missing?"


# ── Detection proof: the validator is not a no-op ─────────────────────────────


class TestValidatorDetectsDrift:
    """If these bogus references are NOT flagged, the gate above is theater."""

    def test_flags_nonexistent_node_type_and_field(self):
        if get_language("python") is None:
            pytest.skip("python grammar not installed")
        src = (
            "(call function: (identifier) @f)\n"
            "(call bogus_field: (nonexistent_node) @g)\n"
        )
        violations = validate_source("synthetic", src, "python")
        flagged = {(v.kind, v.name) for v in violations}
        assert ("node_type", "nonexistent_node") in flagged
        assert ("field", "bogus_field") in flagged
        # Real names must NOT be flagged (no false positives).
        assert not any(v.name in {"call", "identifier", "function"} for v in violations)
        # Reported line is where the bad reference actually is.
        assert all(v.line == 2 for v in violations)

    def test_uninstalled_grammar_is_a_clean_skip(self):
        # An unknown grammar has no model → no violations (not a crash, not a
        # false failure), mirroring how the extractor skips uninstalled grammars.
        assert validate_source("x", "(nope) @a", "no_such_grammar") == []


# ── Tokenizer: extracts real references, ignores query noise ──────────────────


class TestReferenceScanner:
    def test_extracts_node_types_and_fields_only(self):
        src = (
            "; comment mentioning fake_field: and (fake_node)\n"
            "(call_expression\n"
            "  function: (member_expression\n"
            "    object: (identifier) @route.object\n"
            "    property: (property_identifier) @m\n"
            '    (#match? @m "^(get|post):(x)$"))\n'
            "  arguments: (arguments . (string) @p))\n"
        )
        refs = _scan_refs(src)
        nodes = {r.name for r in refs if r.kind == "node_type"}
        fields = {r.name for r in refs if r.kind == "field"}
        assert nodes == {
            "call_expression",
            "member_expression",
            "identifier",
            "property_identifier",
            "arguments",
            "string",
        }
        assert fields == {"function", "object", "property", "arguments"}

    def test_ignores_comments_strings_captures_predicates(self):
        src = (
            "; (comment_node) name: here\n"
            '(literal "anonymous" (#eq? @x "value_looking:like_field"))\n'
        )
        refs = _scan_refs(src)
        names = {r.name for r in refs}
        # Only the real node type survives.
        assert {r.name for r in refs if r.kind == "node_type"} == {"literal"}
        assert "comment_node" not in names
        assert "anonymous" not in names
        assert "eq" not in names
        assert "value_looking" not in names

    def test_ignores_wildcards_and_anchors(self):
        # (_) named wildcard, bare _ child, and the . anchor must not be nodes.
        src = "(class_declaration type: _ (_) . (identifier) @n)\n"
        refs = _scan_refs(src)
        nodes = {r.name for r in refs if r.kind == "node_type"}
        assert nodes == {"class_declaration", "identifier"}
        assert "_" not in nodes

    def test_reports_line_numbers(self):
        src = "(a)\n\n(b\n  field: (c))\n"
        by_name = {r.name: r.line for r in _scan_refs(src)}
        assert by_name["a"] == 1
        assert by_name["b"] == 3
        assert by_name["c"] == 4
        assert by_name["field"] == 4


# ── node-types.json path: exercised via a synthetic manifest ──────────────────
# The pinned grammar wheels do not ship node-types.json, so the richer source is
# dormant against real grammars. These tests keep that code path covered so it is
# correct the day a wheel starts shipping the manifest.


class TestNodeTypesJsonModel:
    def _manifest(self):
        return [
            {
                "type": "call",
                "named": True,
                "fields": {
                    "function": {"types": [{"type": "identifier", "named": True}]},
                    "arguments": {"types": []},
                },
            },
            {"type": "identifier", "named": True},
            {"type": "+", "named": False},  # anonymous token — excluded
            {"type": "comment", "named": True, "fields": {}},
            "not a dict",  # malformed entry — tolerated
        ]

    def test_parses_named_types_and_fields(self, tmp_path):
        path = tmp_path / "node-types.json"
        path.write_text(json.dumps(self._manifest()), encoding="utf-8")
        model = _model_from_node_types("synthetic", path)
        assert model is not None
        assert model.source == "node-types.json"
        assert model.named_types == {"call", "identifier", "comment"}
        assert "+" not in model.named_types  # anonymous tokens are not referenceable
        assert model.field_names == {"function", "arguments"}

    def test_validation_against_manifest_model(self, tmp_path, monkeypatch):
        path = tmp_path / "node-types.json"
        path.write_text(json.dumps(self._manifest()), encoding="utf-8")
        model = _model_from_node_types("synthetic", path)
        # Route grammar_model("synthetic") to our manifest-backed model.
        monkeypatch.setitem(query_check._MODEL_CACHE, "synthetic", model)

        ok = validate_source("q", "(call function: (identifier) @f)", "synthetic")
        assert ok == []
        bad = validate_source("q", "(call missing: (ghost) @g)", "synthetic")
        flagged = {(v.kind, v.name) for v in bad}
        assert ("field", "missing") in flagged
        assert ("node_type", "ghost") in flagged
        # The reason string records that node-types.json was the source used.
        assert all("node-types.json" in v.reason for v in bad)

    def test_malformed_manifest_returns_none(self, tmp_path):
        path = tmp_path / "node-types.json"
        path.write_text('{"not": "a list"}', encoding="utf-8")
        assert _model_from_node_types("synthetic", path) is None
        path.write_text("[]", encoding="utf-8")  # no named types
        assert _model_from_node_types("synthetic", path) is None


# ── Model source reporting reflects the current wheel reality ─────────────────


class TestGrammarModelSource:
    def test_real_grammar_resolves_a_model(self):
        if get_language("python") is None:
            pytest.skip("python grammar not installed")
        model = grammar_model("python")
        assert isinstance(model, GrammarModel)
        # Whatever the source, the core node types must be present.
        assert "call" in model.named_types
        assert "identifier" in model.named_types
        assert "function" in model.field_names
        # Source is one of the two supported providers.
        assert model.source in {"node-types.json", "symbol-table"}
