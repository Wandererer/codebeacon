"""Regression tests for the 2026-05 self-audit bug sweep.

Each test reproduces a confirmed bug so reverting the fix flips the assertion
(mutation-verified). Grouped by the module that was fixed.

| Bug | Module / symbol                              | Symptom before fix                          |
|-----|----------------------------------------------|---------------------------------------------|
| 1   | semantic_pipeline.py:_reapply_archive        | float(None) TypeError on null score → crash |
| 2   | affected.py:affected_from_paths suffix match | basename collision over-seeds blast radius  |
| 3   | extract/routes.py:_interpret_laravel         | prefix_stack never popped → prefixes leak   |
| 4   | extract/services.py:_interpret_fastapi       | Depends() attributed to last function       |
| 5   | extract/services.py:_interpret_angular       | all constructor DI → first @Injectable      |
| 6   | discover/ignore.py:_glob_match               | anchored `*` crossed `/`                     |
| 7   | discover/detector.py route discovery         | App Router dropped page.js / page.jsx        |
| 8   | extract/dotnet.py:_extract_razor             | @using emitted duplicate import edges       |

Plus broken-query repairs (queries failed to compile against the installed
grammar versions → whole framework extracted nothing; no prior test coverage):
| 9   | queries/laravel.scm  | scope/name field swap → Impossible pattern        |
| 10  | queries/angular.scm  | decorator on export_statement, not class_decl     |
| 11  | queries/aspnet.scm   | invocation `expression:`/positional args wrong    |
| 12  | queries/actix.scm    | attribute nested in fn/struct, not sibling        |
| 13  | queries/ktor.scm     | kotlin 1.x renamed simple_identifier, delegation  |
| 14  | queries/vapor.scm    | swift 0.0.1 lacks type_inheritance_clause etc.    |
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest


# ── BUG 1: null confidence_score must not crash archive replay ───────────────

class TestSemanticArchiveNullScore:
    def test_null_score_does_not_crash_and_defaults(self):
        """A `confidence_score: null` in an archived edge (legacy/migrated or
        hand-edited JSONL) used to hit `float(None)` → TypeError, aborting the
        whole prepare() run. It must coerce to the 0.7 default instead, exactly
        like the apply() path."""
        from codebeacon.semantic_pipeline import _reapply_archive

        G = nx.DiGraph()
        G.add_node("api::User", label="User", type="class",
                   source_file="src/User.py", line=1, project="api")
        G.add_node("api::OrderService", label="OrderService", type="class",
                   source_file="src/OrderService.py", line=1, project="api")

        archive = [{
            "source_node_id": "api::User",
            "edges": [{"target_name": "OrderService", "relation": "references",
                       "confidence_score": None}],
        }]

        reapplied, kept = _reapply_archive(G, archive)  # must not raise
        assert reapplied == 1
        assert G.has_edge("api::User", "api::OrderService")
        assert G.edges["api::User", "api::OrderService"]["confidence_score"] == pytest.approx(0.7)


# ── BUG 2: affected seed match must respect path-segment boundaries ──────────

class TestAffectedSuffixBoundary:
    def _write_beacon(self, beacon_dir: Path, G: nx.DiGraph) -> None:
        beacon_dir.mkdir(parents=True, exist_ok=True)
        payload = {"meta": {"version": 1}, **nxjson.node_link_data(G, edges="links")}
        (beacon_dir / "beacon.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_basename_suffix_does_not_overseed(self, tmp_path):
        """Changed path `src/foo.py` must seed the node at `src/foo.py` but NOT
        the node at `foosrc/foo.py` — plain str.endswith had no `/` boundary so
        `foosrc/foo.py`.endswith(... `src/foo.py`) wrongly matched."""
        from codebeacon.affected import affected_from_paths

        G = nx.DiGraph()
        G.add_node("p::A", label="A", type="class", source_file="src/foo.py", project="p")
        G.add_node("p::B", label="B", type="class", source_file="foosrc/foo.py", project="p")
        beacon_dir = tmp_path / ".codebeacon"
        self._write_beacon(beacon_dir, G)

        res = affected_from_paths(beacon_dir, ["src/foo.py"])
        assert res.seed_node_ids == ["p::A"]
        assert "p::B" not in res.seed_node_ids

    def test_relative_suffix_of_absolute_node_still_matches(self, tmp_path):
        """The legitimate case must keep working: a repo-relative changed path
        is a segment-aligned suffix of an absolute node source_file."""
        from codebeacon.affected import affected_from_paths

        G = nx.DiGraph()
        G.add_node("p::A", label="A", type="class",
                   source_file="/abs/repo/src/foo.py", project="p")
        beacon_dir = tmp_path / ".codebeacon"
        self._write_beacon(beacon_dir, G)

        res = affected_from_paths(beacon_dir, ["src/foo.py"])
        assert res.seed_node_ids == ["p::A"]


# ── BUG 3: Laravel route group prefixes must be byte-range scoped ────────────

class TestLaravelPrefixScoping:
    def _routes(self, tmp_path):
        pytest.importorskip("tree_sitter_php")
        from codebeacon.extract.routes import extract_routes
        f = tmp_path / "web.php"
        f.write_text(
            "<?php\n"
            "Route::prefix('admin')->group(function () {\n"
            "    Route::get('/users', [AdminController::class, 'users']);\n"
            "});\n"
            "Route::prefix('api')->group(function () {\n"
            "    Route::get('/items', [ApiController::class, 'items']);\n"
            "});\n"
        )
        return extract_routes(str(f), "laravel", str(tmp_path))

    def test_sibling_group_prefixes_do_not_accumulate(self, tmp_path):
        routes = self._routes(tmp_path)
        by_path = {r.path for r in routes}
        # The api route must NOT inherit the admin prefix.
        assert not any("admin" in p and "api" in p for p in by_path), by_path
        assert any(p.endswith("admin/users") or p == "/admin/users" for p in by_path), by_path
        assert any(p.endswith("api/items") or p == "/api/items" for p in by_path), by_path


# ── BUG 4: FastAPI Depends() attributed to its enclosing function ────────────

class TestFastapiDependsEnclosing:
    def test_depends_attributed_to_correct_function(self, tmp_path):
        pytest.importorskip("tree_sitter_python")
        from codebeacon.extract.services import extract_services
        f = tmp_path / "deps.py"
        # Each function needs a plain typed parameter (no default) so the
        # `service.function` query captures it; the Depends() lives in a
        # separate default parameter.
        f.write_text(
            "from fastapi import Depends\n\n"
            "def get_a(x: int, db = Depends(make_db)):\n"
            "    return db\n\n"
            "def get_b(y: int, cache = Depends(make_cache)):\n"
            "    return cache\n"
        )
        _services, unresolved = extract_services(str(f), "fastapi")
        by_ref = {u.ref_name: u.source_node_id for u in unresolved}
        # make_db sits inside get_a, make_cache inside get_b — not both on the
        # last function as the old `enclosing = last service` logic produced.
        assert by_ref.get("make_db") == f"{f}::get_a"
        assert by_ref.get("make_cache") == f"{f}::get_b"


# ── BUG 5: Angular constructor DI attributed to enclosing @Injectable ────────

class TestAngularConstructorDI:
    def test_di_attributed_per_class(self, tmp_path):
        pytest.importorskip("tree_sitter_typescript")
        from codebeacon.extract.services import extract_services
        f = tmp_path / "services.ts"
        f.write_text(
            "import { Injectable } from '@angular/core';\n\n"
            "@Injectable()\n"
            "export class AService {\n"
            "  constructor(private depOne: DepOne) {}\n"
            "}\n\n"
            "@Injectable()\n"
            "export class BService {\n"
            "  constructor(private depTwo: DepTwo) {}\n"
            "}\n"
        )
        services, _unresolved = extract_services(str(f), "angular")
        deps = {s.name: set(s.dependencies) for s in services}
        # Each service owns only its own constructor dep — not all deps piling
        # onto the first @Injectable.
        assert deps.get("AService") == {"DepOne"}
        assert deps.get("BService") == {"DepTwo"}


# ── BUG 6: gitignore `*` must not cross `/` for anchored patterns ────────────

class TestIgnoreAnchoredStar:
    def test_anchored_star_does_not_cross_slash(self):
        from codebeacon.discover.ignore import _glob_match
        # `src/*.py` matches a file directly in src/, not nested ones.
        assert _glob_match("src/*.py", "src/foo.py") is True
        assert _glob_match("src/*.py", "src/a/b.py") is False

    def test_double_star_still_crosses(self):
        from codebeacon.discover.ignore import _glob_match
        assert _glob_match("src/**/*.py", "src/a/b.py") is True

    def test_is_ignored_end_to_end(self):
        from codebeacon.discover.ignore import IgnoreMatcher
        m = IgnoreMatcher(["build/*.js"])
        assert m.is_ignored("build/app.js") is True
        assert m.is_ignored("build/nested/app.js") is False


# ── BUG 7: Next.js App Router must discover page.js / page.jsx ────────────────

class TestNextAppRouterJsExtensions:
    def test_js_page_files_are_discovered(self, tmp_path):
        from codebeacon.common.types import ProjectInfo
        from codebeacon.discover.detector import extract_convention_routes

        app = tmp_path / "app"
        (app / "dashboard").mkdir(parents=True)
        (app / "page.jsx").write_text("export default function P(){}")
        (app / "dashboard" / "page.js").write_text("export default function D(){}")

        project = ProjectInfo(name="web", path=str(tmp_path), framework="nextjs",
                              language="javascript", signature_file="package.json")
        routes = extract_convention_routes(project)
        # Two JS-based app-router pages must be found; only globbing .ts/.tsx
        # silently returned zero.
        assert len(routes) >= 2


# ── BUG 8: Razor @using import edges must be deduplicated ────────────────────

class TestRazorUsingDedup:
    def test_duplicate_using_emits_single_edge(self, tmp_path):
        from codebeacon.extract.dotnet import extract_dotnet_edges
        f = tmp_path / "Page.razor"
        f.write_text(
            "@using My.Shared.Components\n"
            "@using My.Shared.Components\n"
            "<h1>Hi</h1>\n"
        )
        edges = extract_dotnet_edges(str(f))
        using = [e for e in edges if e.relation == "imports_from"
                 and e.target == "My.Shared.Components"]
        assert len(using) == 1, using


# ── BUG 9: Laravel query compiles & extracts routes (already covered above by
#          TestLaravelPrefixScoping, which would fail if the query didn't compile)


# ── BUG 11: ASP.NET query compiles & extracts controller routes ──────────────

class TestAspnetQueryCompiles:
    def test_controller_routes_extracted(self, tmp_path):
        pytest.importorskip("tree_sitter_c_sharp")
        from codebeacon.extract.routes import extract_routes
        f = tmp_path / "UserController.cs"
        f.write_text(
            "using Microsoft.AspNetCore.Mvc;\n"
            "[ApiController]\n[Route(\"api/[controller]\")]\n"
            "public class UserController : ControllerBase {\n"
            "    [HttpGet(\"{id}\")]\n"
            "    public IActionResult Get(int id) { return Ok(); }\n"
            "    [HttpPost]\n"
            "    public IActionResult Create() { return Ok(); }\n"
            "}\n"
        )
        routes = extract_routes(str(f), "aspnet", str(tmp_path))
        # Query previously failed to compile (impossible pattern) → zero routes.
        assert routes, "aspnet query produced no routes — did it fail to compile?"
        methods = {r.method for r in routes}
        assert {"GET", "POST"} <= methods


# ── BUG 12: Actix proc-macro routes + derive entities extracted ──────────────

class TestActixQueryCompiles:
    def test_proc_macro_routes_and_entities(self, tmp_path):
        pytest.importorskip("tree_sitter_rust")
        from codebeacon.extract.routes import extract_routes
        from codebeacon.extract.entities import extract_entities
        f = tmp_path / "handlers.rs"
        f.write_text(
            "use actix_web::{get, post};\n\n"
            "#[get(\"/users\")]\n"
            "async fn list_users() -> impl Responder { todo!() }\n\n"
            "#[post(\"/users\")]\n"
            "async fn create_user() -> impl Responder { todo!() }\n\n"
            "#[derive(Serialize, Deserialize)]\n"
            "struct User { id: u32, name: String }\n"
        )
        routes = extract_routes(str(f), "actix", str(tmp_path))
        paths = {(r.method, r.path) for r in routes}
        assert ("GET", "/users") in paths
        assert ("POST", "/users") in paths
        assert any(e.name == "User" for e in extract_entities(str(f), "actix"))


# ── BUG 13: Ktor query compiles & extracts (kotlin 1.x grammar) ──────────────

class TestKtorQueryCompiles:
    def test_services_and_entities_extracted(self, tmp_path):
        pytest.importorskip("tree_sitter_kotlin")
        from codebeacon.extract.services import extract_services
        from codebeacon.extract.entities import extract_entities
        from codebeacon.extract.routes import extract_routes
        f = tmp_path / "UserRoutes.kt"
        f.write_text(
            "data class User(val id: Int, val name: String)\n\n"
            "class UserService {\n  fun all(): List<User> = emptyList()\n}\n\n"
            "fun Application.routes() {\n"
            "  routing {\n"
            "    route(\"/users\") {\n"
            "      get(\"/{id}\") { call.respond(1) }\n"
            "    }\n"
            "  }\n"
            "}\n"
        )
        svc_list, _unresolved = extract_services(str(f), "ktor")
        services = {s.name for s in svc_list}
        # Query previously failed to compile (invalid simple_identifier) → empty.
        assert "UserService" in services
        assert any(e.name == "User" for e in extract_entities(str(f), "ktor"))
        assert extract_routes(str(f), "ktor", str(tmp_path)), "no ktor routes"


# ── BUG 14: Vapor query compiles & extracts (swift 0.0.1 grammar) ────────────

class TestVaporQueryCompiles:
    def test_routes_and_model_extracted(self, tmp_path):
        pytest.importorskip("tree_sitter_swift")
        from codebeacon.extract.routes import extract_routes
        from codebeacon.extract.entities import extract_entities
        f = tmp_path / "routes.swift"
        f.write_text(
            "import Vapor\n\n"
            "struct User: Content {\n  var id: Int?\n  var name: String\n}\n\n"
            "func routes(_ app: Application) throws {\n"
            "    app.get(\"users\") { req in return [] }\n"
            "    app.post(\"users\") { req in return 1 }\n"
            "}\n"
        )
        routes = extract_routes(str(f), "vapor", str(tmp_path))
        methods = {r.method for r in routes}
        # Query previously failed to compile (invalid type_inheritance_clause).
        assert {"GET", "POST"} <= methods, methods
        assert any(e.name == "User" for e in extract_entities(str(f), "vapor"))
