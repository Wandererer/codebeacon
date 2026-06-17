"""Graphify-parity audit fixes shipped in 0.6.6.

Swept upstream ``safishamsi/graphify`` v0.8.37–v0.8.40 (plus the closed-but-
unreleased fixes through issue #1362) against codebeacon. Six reproductions
were confirmed; the regression tests for them live here.

Headline finding — three shipped tree-sitter queries silently extracted nothing
under the currently-installed grammars, mirroring upstream's v0.8.39
"pin grammar upper bounds" fix and the earlier broken-framework-queries audit:

  * ``express.scm`` hardcoded ``class_declaration name: (identifier)`` — an
    "Impossible pattern" under the TypeScript/TSX grammars (which the allowlist
    permits), so TS/TSX Express/Koa/Fastify apps yielded 0 routes. (JS was fine,
    and the only express fixture is ``.js``, so it went unnoticed.)
  * ``vue.scm`` hardcoded ``name: (type_identifier)`` — an "Invalid node type"
    under the JavaScript grammar, so the whole query failed to compile and Vue
    SFCs with a plain ``<script>`` (JS) yielded 0 components.
  * ``spring_boot.scm`` is a Java-grammar query, but its allowlist permitted
    ``kotlin``; ``marker_annotation`` does not exist in the Kotlin grammar, so
    every ``.kt`` file in a Spring project was dropped to [] with a warning.

``run_query`` swallows tree-sitter compile errors ("Impossible pattern" /
"Invalid node type") in the same ``except`` as a genuine empty match and returns
``[]`` — so these never surfaced as failures and CI stayed green. The structural
test below makes the allowlist⇄query contract explicit so any future grammar
drift fails loudly here instead of silently in production.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest
from tree_sitter import Query

from codebeacon import __version__
from codebeacon.affected import affected_from_paths
from codebeacon.cache import Cache
from codebeacon.extract import base
from codebeacon.extract.base import (
    QUERY_GRAMMAR_ALLOWLIST,
    get_language,
    is_grammar_allowed,
    load_query_file,
)
from codebeacon.extract.routes import extract_routes


@pytest.fixture(autouse=True)
def _isolate_lang_cache():
    """Snapshot/restore ``_LANG_CACHE`` so grammar loads here don't leak
    (mirrors test_optional_grammars.py)."""
    snapshot = dict(base._LANG_CACHE)
    try:
        yield
    finally:
        base._LANG_CACHE.clear()
        base._LANG_CACHE.update(snapshot)


class TestQueryGrammarCompatibility:
    """Contract: if QUERY_GRAMMAR_ALLOWLIST permits grammar G for query Q, then
    Q.scm MUST actually compile against G. Otherwise run_query silently returns
    [] for every file of that grammar — a whole framework extracts nothing.

    Each pair is compiled in turn; a tree-sitter compile error on one pair does
    not corrupt the others (verified), so all failures are collected and
    reported together.
    """

    def test_every_allowlisted_grammar_compiles_its_query(self):
        failures: list[str] = []
        checked = 0
        for query_name, grammars in sorted(QUERY_GRAMMAR_ALLOWLIST.items()):
            src = load_query_file(query_name)
            assert src is not None, f"{query_name}: allowlisted but no .scm file"
            for grammar in sorted(grammars):
                lang = get_language(grammar)
                if lang is None:
                    # Grammar not installed in this environment — the runtime
                    # skips it gracefully (see test_optional_grammars); not a
                    # query-correctness failure.
                    continue
                checked += 1
                try:
                    Query(lang, src)
                except Exception as exc:  # noqa: BLE001 — we want the message
                    failures.append(f"{query_name}.scm x {grammar}: {exc}")
        assert not failures, (
            "queries that do not compile against an allowlisted grammar "
            "(they would silently extract nothing in production):\n  "
            + "\n  ".join(failures)
        )
        # Guard against a vacuous pass if no grammars were installed at all.
        assert checked >= 5, f"only {checked} pairs checked — grammars missing?"

    def test_express_compiles_against_typescript_and_javascript(self):
        # Direct pin of the regression: the express fix must hold for both.
        src = load_query_file("express")
        for grammar in ("javascript", "typescript", "tsx"):
            lang = get_language(grammar)
            if lang is None:
                pytest.skip(f"{grammar} grammar not installed")
            Query(lang, src)  # must not raise

    def test_vue_compiles_against_javascript(self):
        src = load_query_file("vue")
        lang = get_language("javascript")
        if lang is None:
            pytest.skip("javascript grammar not installed")
        Query(lang, src)  # must not raise (was: Invalid node type type_identifier)


class TestTypeScriptExpressRoutes:
    """express.scm must extract routes from a TypeScript Express app, not just
    JavaScript. Before the fix this returned 0 routes (Impossible pattern)."""

    def _write(self, tmp_path: Path) -> Path:
        f = tmp_path / "router.ts"
        f.write_text(
            'import { Router } from "express";\n'
            "const router: Router = Router();\n"
            'router.get("/health", (req, res) => res.json({ ok: true }));\n'
            'router.post("/users", (req, res) => res.sendStatus(201));\n'
            "export default router;\n",
            encoding="utf-8",
        )
        return f

    def test_ts_express_routes_extracted(self, tmp_path):
        if get_language("typescript") is None:
            pytest.skip("typescript grammar not installed")
        routes = extract_routes(str(self._write(tmp_path)), "express", str(tmp_path))
        methods = {(r.method.upper(), r.path) for r in routes}
        assert ("GET", "/health") in methods
        assert ("POST", "/users") in methods


class TestSpringBootKotlinGate:
    """spring_boot.scm is Java-only; Kotlin must be gated OFF so .kt files are
    skipped cleanly instead of fed to an incompatible grammar."""

    def test_kotlin_not_allowed_for_spring_boot(self):
        assert "kotlin" not in QUERY_GRAMMAR_ALLOWLIST["spring_boot"]
        kt = get_language("kotlin")
        if kt is not None:
            assert is_grammar_allowed("spring_boot", kt) is False

    def test_java_still_allowed_for_spring_boot(self):
        java = get_language("java")
        if java is None:
            pytest.skip("java grammar not installed")
        assert is_grammar_allowed("spring_boot", java) is True


# ── AST cache version-namespacing (graphify #1252) ───────────────────────────

class TestCacheVersionNamespace:
    """The extraction cache is version-stamped. A cache written by a different
    codebeacon version — or a legacy unversioned (pre-0.6.6) cache — is dropped
    on load, so an upgraded extractor (whose .scm queries may have changed)
    never serves a stale result for an unchanged source file. The content hash
    can't catch this: the file didn't change, the extractor did."""

    def _write_cache(self, root: Path, payload) -> Path:
        cdir = root / ".codebeacon" / "cache"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "cache.json").write_text(json.dumps(payload), encoding="utf-8")
        return cdir

    _ENTRY = {"src/a.py": {"hash": "h", "result": {"v": 1},
                           "ts": 0, "mtime_ns": 0, "size": 0}}

    def test_foreign_version_cache_discarded(self, tmp_path):
        self._write_cache(tmp_path, {"_cb_version": "0.0.1-ancient",
                                     "entries": dict(self._ENTRY)})
        c = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        c.load()
        assert c._data == {}

    def test_legacy_unversioned_cache_discarded(self, tmp_path):
        # Pre-0.6.6 flat format — no wrapper, no version.
        self._write_cache(tmp_path, dict(self._ENTRY))
        c = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        c.load()
        assert c._data == {}

    def test_same_version_cache_preserved(self, tmp_path):
        self._write_cache(tmp_path, {"_cb_version": __version__,
                                     "entries": dict(self._ENTRY)})
        c = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        c.load()
        assert "src/a.py" in c._data

    def test_save_then_load_round_trips_under_same_version(self, tmp_path):
        src = tmp_path / "foo.py"
        src.write_text("x = 1\n")
        c = Cache(str(tmp_path / "out"))
        c.put(str(src), {"result": "v1"})
        c.save()
        fresh = Cache(str(tmp_path / "out"))
        fresh.load()
        assert fresh.get(str(src)) == {"result": "v1"}


# ── Corrupt cache.json preserved, not destroyed (graphify v0.8.39) ───────────

class TestCacheCorruptBackup:
    def test_corrupt_cache_backed_up_and_reset(self, tmp_path):
        cdir = tmp_path / ".codebeacon" / "cache"
        cdir.mkdir(parents=True)
        (cdir / "cache.json").write_text("{ this is : not valid json ]]")

        c = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        c.load()
        assert c._data == {}
        backups = list(cdir.glob("cache.json.*.corrupt"))
        assert backups, "corrupt cache.json must be preserved, not silently lost"
        assert "not valid json" in backups[0].read_text()
        # The corrupt original is moved aside so the next save() writes fresh.
        assert not (cdir / "cache.json").exists()


# ── affected_from_paths NFC path matching (graphify #1338) ───────────────────

class TestAffectedNfcPaths:
    """affected_from_paths NFC-normalises both the changed paths and the stored
    source_file, so a macOS git-diff path (NFD) with accented filenames still
    matches the NFC source_file recorded in beacon.json."""

    def test_nfd_changed_path_matches_nfc_source_file(self, tmp_path):
        nfc = unicodedata.normalize("NFC", "src/Auditoría.py")
        nfd = unicodedata.normalize("NFD", "src/Auditoría.py")
        assert nfc != nfd, "fixture precondition: the two forms must differ"

        G = nx.DiGraph()
        G.add_node("p::Aud", label="Auditoría", source_file=nfc,
                   type="service", project="p")
        (tmp_path / "beacon.json").write_text(
            json.dumps(nxjson.node_link_data(G), ensure_ascii=False),
            encoding="utf-8",
        )
        result = affected_from_paths(tmp_path, [nfd])
        assert result.seed_node_ids == ["p::Aud"]  # was [] before #1338
