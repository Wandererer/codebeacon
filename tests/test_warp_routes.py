"""Warp (Rust) filter-combinator route extraction.

Warp shares ``actix.scm`` with Actix/Axum/Rocket, but its routes are filter
chains — ``warp::path!("users" / u32).and(warp::get()).and_then(get_user)`` —
that match neither the Actix ``#[get("/x")]`` attribute pattern nor the Axum
``Router::new().route(...)`` table. Before this, Warp apps extracted ~0 routes.

The path/method/handler pieces are captured independently and correlated in
``_interpret_actix`` by the innermost enclosing let_declaration/block scope.
These tests pin both the extraction and the invariant that Actix/Axum/Rocket
extraction is unchanged (Warp captures are a disjoint set of syntax).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from tree_sitter import Query

from codebeacon.extract.base import get_language, load_query_file
from codebeacon.extract.entities import extract_entities
from codebeacon.extract.routes import extract_routes
from codebeacon.extract.services import extract_services

FIXTURE = Path(__file__).parent / "fixtures" / "warp_app" / "src" / "main.rs"


@pytest.fixture(autouse=True)
def _require_rust():
    if get_language("rust") is None:
        pytest.skip("tree-sitter-rust grammar not installed")


def _routes():
    return extract_routes(str(FIXTURE), "warp", str(FIXTURE.parent.parent))


class TestWarpRouteExtraction:
    def test_get_route_with_identifier_handler(self):
        pairs = {(r.method, r.path, r.handler) for r in _routes()}
        assert ("GET", "/health", "health_check") in pairs
        assert ("GET", "/users", "list_users") in pairs

    def test_post_method_combinator_resolved(self):
        # warp::post() combinator in the chain → POST, not the ANY default.
        pairs = {(r.method, r.path, r.handler) for r in _routes()}
        assert ("POST", "/users", "create_user") in pairs

    def test_path_macro_typed_segment_becomes_param(self):
        # warp::path!("users" / u32) → /users/{param}
        pairs = {(r.method, r.path, r.handler) for r in _routes()}
        assert ("GET", "/users/{param}", "get_user") in pairs

    def test_and_path_composition_is_concatenated(self):
        # warp::path("api").and(warp::path("v1")).and(warp::path("stats"))
        pairs = {(r.method, r.path, r.handler) for r in _routes()}
        assert ("GET", "/api/v1/stats", "get_stats") in pairs

    def test_method_unknown_defaults_to_any(self):
        # warp::path!("hello" / String).map(|name| ...) — no method combinator
        # and a closure (unnameable) handler.
        by_path = {r.path: r for r in _routes()}
        assert by_path["/hello/{param}"].method == "ANY"
        assert by_path["/hello/{param}"].handler == ""

    def test_block_tail_expression_route(self):
        # goodbye() returns its filter as the block's tail expression (no `let`);
        # correlation must fall back to the enclosing block scope.
        assert any(r.path == "/goodbye/{param}" for r in _routes())

    def test_or_only_binding_yields_no_route(self):
        # `let routes = hello.or(goodbye()).or(health)...` has no warp::path of
        # its own — it must not emit a bogus route.
        assert not any(r.handler == "routes" for r in _routes())
        # Exactly the seven filter chains above, nothing spurious.
        assert len([r for r in _routes() if r.framework == "warp"]) == 7

    def test_framework_tag_is_warp(self):
        assert all(r.framework == "warp" for r in _routes())


class TestWarpSharesActixQueryArtifacts:
    """Warp reuses actix.scm, so struct entities / services still extract."""

    def test_entity_still_extracted(self):
        assert any(e.name == "User" for e in extract_entities(str(FIXTURE), "warp"))

    def test_service_struct_still_extracted(self):
        services, _ = extract_services(str(FIXTURE), "warp")
        assert any(s.name == "User" for s in services)


class TestActixAxumRocketUnchanged:
    """The Warp additions are a disjoint capture set; the other three Rust
    frameworks must extract exactly as before."""

    def test_actix_proc_macro_routes_unchanged(self, tmp_path):
        f = tmp_path / "handlers.rs"
        f.write_text(
            "use actix_web::{get, post};\n\n"
            '#[get("/users")]\n'
            "async fn list_users() -> impl Responder { todo!() }\n\n"
            '#[post("/users")]\n'
            "async fn create_user() -> impl Responder { todo!() }\n",
            encoding="utf-8",
        )
        pairs = {(r.method, r.path) for r in extract_routes(str(f), "actix", str(tmp_path))}
        assert ("GET", "/users") in pairs
        assert ("POST", "/users") in pairs
        # Actix code has no warp::path anchors → no Warp routes leak in.
        assert all(not r.path.endswith("{param}") for r in extract_routes(str(f), "actix", str(tmp_path)))

    def test_axum_router_routes_unchanged(self, tmp_path):
        f = tmp_path / "router.rs"
        f.write_text(
            "use axum::{routing::get, routing::post, Router};\n\n"
            "fn app() -> Router {\n"
            '    Router::new()\n'
            '        .route("/health", get(health))\n'
            '        .route("/users", post(create))\n'
            "}\n",
            encoding="utf-8",
        )
        pairs = {(r.method, r.path, r.handler) for r in extract_routes(str(f), "axum", str(tmp_path))}
        assert ("GET", "/health", "health") in pairs
        assert ("POST", "/users", "create") in pairs

    def test_actix_builder_fixture_still_zero_ast_routes(self):
        # fixtures/actix/main.rs uses the App::new().route(web::get().to(h))
        # builder — matched by neither the Actix, Axum, nor Warp patterns. Its
        # AST-route count (0) must be unchanged by the Warp additions.
        actix_fixture = Path(__file__).parent / "fixtures" / "actix" / "main.rs"
        assert extract_routes(str(actix_fixture), "actix", str(actix_fixture.parent)) == []


class TestWarpQueryCompiles:
    """actix.scm (now carrying the Warp section) must still compile against the
    rust grammar — else run_query silently returns [] and every Rust framework
    extracts nothing (mirrors the parity gate in test_graphify_parity_0_6_6)."""

    def test_actix_scm_compiles_against_rust(self):
        src = load_query_file("actix")
        assert src is not None
        Query(get_language("rust"), src)  # must not raise
