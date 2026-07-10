"""Audit 0.6.9 — extract/routes + extract/components regressions (group F-D).

Covers eight confirmed bugs:
  C17    routes.py::_seg — Next.js parallel-route slots (@modal) leaked into URLs
         and catch-all segments ([...all]) were garbled by Path.stem.
  C18    laravel.scm — Eloquent entities missed the canonical `extends Model`
         (bare-name grammar quirk) and app-wide base-class conventions.
  BH-I1  Express app.use("/prefix", router) mount prefix was dropped.
  BH-I2  Chained router.route(p).get().post() dropped every verb after the first.
  BH-I3  Flask register_blueprint(url_prefix=…) ignored when placed after routes.
  BH-I4  FastAPI include_router(prefix=…) ignored when placed after handlers.
  BH-I5  Spring @RequestMapping(method=RequestMethod.X) recorded as "ANY".
  BH-I6  React hooks/imports leaked from one component onto siblings in same file.
"""
from __future__ import annotations

import pytest

from codebeacon.extract.base import get_language
from codebeacon.extract.components import extract_components
from codebeacon.extract.entities import extract_entities
from codebeacon.extract.routes import _app_to_route, _seg, extract_routes


def _need(grammar: str) -> None:
    if get_language(grammar) is None:
        pytest.skip(f"{grammar} grammar not installed")


# ── C17 — Next.js parallel-route slots + catch-all segments ──────────────────

class TestNextJsSegmentConversion:
    def test_parallel_route_slot_stripped(self):
        # @slot folders (parallel routes) never contribute to the URL.
        assert _seg("@modal") == ""
        assert _seg("@team") == ""

    def test_catch_all_segment_survives(self):
        # Path.stem used to mangle "[...all]" → "[.."; the catch-all regex never
        # fired. It must now normalise to "*".
        assert _seg("[...all]") == "*"
        assert _seg("[...slug].tsx") == "*"

    def test_route_group_and_dynamic_param_unchanged(self):
        assert _seg("(marketing)") == ""       # route group
        assert _seg("[slug]") == ":slug"        # dynamic param
        assert _seg("[id].tsx") == ":id"
        assert _seg("index") == ""
        assert _seg("photo") == "photo"

    def test_app_router_paths(self):
        assert _app_to_route(("@modal", "photo", "page.tsx")) == "/photo"
        assert _app_to_route(("blog", "[...all]", "page.tsx")) == "/blog/*"
        assert _app_to_route(("(marketing)", "pricing", "page.tsx")) == "/pricing"
        assert _app_to_route(("blog", "[slug]", "page.tsx")) == "/blog/:slug"

    def test_end_to_end_convention_route(self, tmp_path):
        _need("tsx")
        app = tmp_path / "app" / "@modal" / "photo"
        app.mkdir(parents=True)
        page = app / "page.tsx"
        page.write_text("export default function Page(){ return null }\n", encoding="utf-8")
        routes = extract_routes(str(page), "nextjs", str(tmp_path))
        paths = {r.path for r in routes}
        assert "/photo" in paths
        assert not any("@modal" in p for p in paths)

    def test_esm_extensions_stripped(self):
        # Round-2 hole (C17 .mjs): the strip regex whitelisted only 6 extensions,
        # but scanner.CODE_EXTENSIONS also includes .mjs/.cjs/.mts/.cts — a
        # Pages-Router file with those leaked the extension into the URL segment.
        assert _seg("webhook.mjs") == "webhook"
        assert _seg("cron.cjs") == "cron"
        assert _seg("worker.mts") == "worker"
        assert _seg("edge.cts") == "edge"
        assert _seg("index.mjs") == ""          # index still collapses to root
        assert _seg("[id].mjs") == ":id"        # dynamic param + esm ext

    def test_esm_pages_route_end_to_end(self, tmp_path):
        _need("tsx")
        api = tmp_path / "pages" / "api"
        api.mkdir(parents=True)
        page = api / "webhook.mjs"
        page.write_text("export default function handler(){}\n", encoding="utf-8")
        routes = extract_routes(str(page), "nextjs", str(tmp_path))
        paths = {r.path for r in routes}
        assert "/api/webhook" in paths
        assert not any(".mjs" in p for p in paths)


# ── C18 — Laravel Eloquent entity base-class detection ───────────────────────

class TestLaravelEloquentEntities:
    SRC = (
        "<?php\n"
        "namespace App\\Models;\n"
        "use Illuminate\\Database\\Eloquent\\Model;\n"
        "use Illuminate\\Foundation\\Auth\\User as Authenticatable;\n"
        "abstract class BaseModel extends Model {}\n"
        "class User extends BaseModel {}\n"          # intermediate base
        "class Post extends Model {}\n"              # canonical bare
        "class Account extends Authenticatable {}\n"  # bare auth
        "class Product extends \\Illuminate\\Database\\Eloquent\\Model {}\n"  # qualified
    )

    def test_all_eloquent_forms_detected(self, tmp_path):
        _need("php")
        f = tmp_path / "Models.php"
        f.write_text(self.SRC, encoding="utf-8")
        ents = {e.name: e for e in extract_entities(str(f), "laravel")}
        # Canonical bare `extends Model` (the grammar-quirk regression) …
        assert "Post" in ents
        assert "Product" in ents        # qualified
        assert "Account" in ents        # bare Authenticatable
        # … and the app-wide base-class convention.
        assert "User" in ents           # extends BaseModel
        assert "BaseModel" in ents      # extends Model (abstract base itself)
        assert all(e.framework == "eloquent" for e in ents.values())

    def test_non_model_class_not_an_entity(self, tmp_path):
        _need("php")
        f = tmp_path / "Plain.php"
        f.write_text(
            "<?php\nnamespace App;\nclass PaymentGateway extends Controller {}\n",
            encoding="utf-8",
        )
        names = {e.name for e in extract_entities(str(f), "laravel")}
        assert "PaymentGateway" not in names

    def test_viewmodel_suffix_not_misclassified(self, tmp_path):
        # Round-2 hole: an unanchored `(Model|Authenticatable)$` suffix matched
        # any base ending in "Model" — spatie/laravel-view-models `extends
        # ViewModel`, `extends BaseDataModel`, `extends FormModel` — flagging them
        # as false Eloquent entities. The allowlist is now anchored ^…$.
        _need("php")
        f = tmp_path / "ViewModels.php"
        f.write_text(
            "<?php\nnamespace App;\n"
            "class PostViewModel extends ViewModel {}\n"     # spatie — NOT eloquent
            "class Report extends BaseDataModel {}\n"        # arbitrary *Model — NOT
            "class ContactForm extends FormModel {}\n"       # arbitrary *Model — NOT
            "class Order extends Model {}\n",                # canonical — IS eloquent
            encoding="utf-8",
        )
        names = {e.name for e in extract_entities(str(f), "laravel")}
        assert "PostViewModel" not in names
        assert "Report" not in names
        assert "ContactForm" not in names
        # the canonical bare `extends Model` still resolves
        assert "Order" in names


# ── BH-I1 — Express app.use("/prefix", router) mount prefix ──────────────────

class TestExpressMountPrefix:
    def test_mount_prefix_applied(self, tmp_path):
        _need("javascript")
        f = tmp_path / "app.js"
        f.write_text(
            "const express = require('express');\n"
            "const app = express();\n"
            "const router = express.Router();\n"
            "router.get('/users', (req, res) => res.json([]));\n"
            "router.post('/users', (req, res) => res.sendStatus(201));\n"
            "app.use('/api/v1', router);\n",
            encoding="utf-8",
        )
        routes = extract_routes(str(f), "express", str(tmp_path))
        pairs = {(r.method, r.path) for r in routes}
        assert ("GET", "/api/v1/users") in pairs
        assert ("POST", "/api/v1/users") in pairs
        # The unprefixed form must NOT survive.
        assert not any(p == "/users" for _m, p in pairs)

    def test_unmounted_router_keeps_bare_path(self, tmp_path):
        _need("javascript")
        f = tmp_path / "bare.js"
        f.write_text(
            "const router = require('express').Router();\n"
            "router.get('/health', (req, res) => res.end());\n",
            encoding="utf-8",
        )
        routes = extract_routes(str(f), "express", str(tmp_path))
        assert ("GET", "/health") in {(r.method, r.path) for r in routes}


# ── BH-I2 — Chained router.route(path).verb().verb() ─────────────────────────

class TestExpressChainedVerbs:
    def test_every_verb_in_chain_captured(self, tmp_path):
        _need("javascript")
        f = tmp_path / "routes.js"
        f.write_text(
            "const router = require('express').Router();\n"
            "router.route('/users').get(h1).post(h2);\n"
            "router.route('/items').get(a).put(b).delete(c);\n"
            "router.get('/ping', h);\n",
            encoding="utf-8",
        )
        routes = extract_routes(str(f), "express", str(tmp_path))
        users = sorted(r.method for r in routes if r.path == "/users")
        items = sorted(r.method for r in routes if r.path == "/items")
        assert users == ["GET", "POST"]
        assert items == ["DELETE", "GET", "PUT"]
        # single-verb sanity route still works
        assert ("GET", "/ping") in {(r.method, r.path) for r in routes}


# ── BH-I3 — Flask register_blueprint(url_prefix=…) order independence ─────────

class TestFlaskBlueprintPrefixOrder:
    BOTTOM = (
        "from flask import Flask, Blueprint\n"
        "bp = Blueprint('users', __name__, url_prefix='/users')\n"
        "@bp.route('/')\n"
        "def index():\n    return 'i'\n"
        "@bp.route('/profile', methods=['GET', 'POST'])\n"
        "def profile():\n    return 'p'\n"
        "app = Flask(__name__)\n"
        "app.register_blueprint(bp, url_prefix='/api/v2/users')\n"
    )

    # Round-2 hole: pass 1 unconditionally wrote register_prefixes[name]="" for a
    # bare `register_blueprint(bp)`, which then shadowed the blueprint's OWN
    # url_prefix in pass 2 (the resolver never fell back to bp_prefixes once the
    # key existed). The write is now guarded on a captured prefix, mirroring the
    # FastAPI include_router sibling.
    NO_OVERRIDE = (
        "from flask import Flask, Blueprint\n"
        "bp = Blueprint('users', __name__, url_prefix='/users')\n"
        "@bp.route('/')\n"
        "def index():\n    return 'i'\n"
        "@bp.route('/profile', methods=['GET', 'POST'])\n"
        "def profile():\n    return 'p'\n"
        "app = Flask(__name__)\n"
        "app.register_blueprint(bp)\n"  # no url_prefix → blueprint keeps its own
    )

    REGISTER_BEFORE = (
        "from flask import Flask, Blueprint\n"
        "app = Flask(__name__)\n"
        "bp = Blueprint('users', __name__, url_prefix='/users')\n"
        "app.register_blueprint(bp)\n"  # registered BEFORE the decorators
        "@bp.route('/')\n"
        "def index():\n    return 'i'\n"
        "@bp.route('/profile')\n"
        "def profile():\n    return 'p'\n"
    )

    def test_register_after_routes_applies_override(self, tmp_path):
        _need("python")
        f = tmp_path / "app_bottom.py"
        f.write_text(self.BOTTOM, encoding="utf-8")
        routes = extract_routes(str(f), "flask")
        pairs = {(r.method, r.path) for r in routes}
        # Flask replaces the blueprint's own url_prefix at register time.
        assert ("GET", "/api/v2/users") in pairs
        assert ("GET", "/api/v2/users/profile") in pairs
        assert ("POST", "/api/v2/users/profile") in pairs
        # The override must win regardless of statement order.
        assert not any(p == "/users" for _m, p in pairs)

    def test_no_override_keeps_blueprint_own_prefix(self, tmp_path):
        _need("python")
        f = tmp_path / "app_no_override.py"
        f.write_text(self.NO_OVERRIDE, encoding="utf-8")
        routes = extract_routes(str(f), "flask")
        pairs = {(r.method, r.path) for r in routes}
        # register_blueprint(bp) with NO url_prefix → blueprint's own /users wins.
        assert ("GET", "/users") in pairs
        assert ("GET", "/users/profile") in pairs
        assert ("POST", "/users/profile") in pairs
        # The bare '/' and '/profile' must NOT survive (prefix was dropped).
        assert not any(p in ("/", "/profile") for _m, p in pairs)

    def test_no_override_register_before_decorators(self, tmp_path):
        _need("python")
        f = tmp_path / "app_register_before.py"
        f.write_text(self.REGISTER_BEFORE, encoding="utf-8")
        routes = extract_routes(str(f), "flask")
        pairs = {(r.method, r.path) for r in routes}
        # Two-pass resolution is order-free: prefix holds even when the bare
        # register precedes the @bp.route decorators.
        assert ("GET", "/users") in pairs
        assert ("GET", "/users/profile") in pairs
        assert not any(p in ("/", "/profile") for _m, p in pairs)


# ── BH-I4 — FastAPI include_router(prefix=…) order independence ──────────────

class TestFastapiIncludeRouterOrder:
    AFTER = (
        "from fastapi import FastAPI, APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/{user_id}')\n"
        "def get_user(user_id: int):\n    return user_id\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api/v2/users')\n"
    )

    def test_include_after_handler_applies_prefix(self, tmp_path):
        _need("python")
        f = tmp_path / "main.py"
        f.write_text(self.AFTER, encoding="utf-8")
        routes = extract_routes(str(f), "fastapi")
        pairs = {(r.method, r.path) for r in routes}
        assert ("GET", "/api/v2/users/{user_id}") in pairs
        assert not any(p == "/{user_id}" for _m, p in pairs)


# ── BH-I5 — Spring @RequestMapping(method=RequestMethod.X) ───────────────────

class TestSpringRequestMappingMethod:
    SRC = (
        "package x;\n"
        "@RestController\n"
        "@RequestMapping(\"/api/items\")\n"
        "public class ItemController {\n"
        "  @RequestMapping(value = \"/{id}\", method = RequestMethod.DELETE)\n"
        "  public String deleteItem(Long id) { return \"\"; }\n"
        "  @RequestMapping(path = \"/create\", method = RequestMethod.POST)\n"
        "  public String createItem() { return \"\"; }\n"
        "  @GetMapping(\"/{id}\")\n"
        "  public String getItem(Long id) { return \"\"; }\n"
        "}\n"
    )

    def test_explicit_request_method_mapped(self, tmp_path):
        _need("java")
        f = tmp_path / "ItemController.java"
        f.write_text(self.SRC, encoding="utf-8")
        by_handler = {
            r.handler.split(".")[-1]: r.method
            for r in extract_routes(str(f), "spring-boot")
        }
        assert by_handler.get("deleteItem") == "DELETE"
        assert by_handler.get("createItem") == "POST"
        # control: modern annotation unaffected
        assert by_handler.get("getItem") == "GET"


# ── BH-I6 — React per-component hook scoping ─────────────────────────────────

class TestReactHookScoping:
    SRC = (
        "import { useState } from 'react';\n"
        "import { useEffect } from 'react';\n"
        "import axios from 'axios';\n"
        "export function Foo() {\n"
        "  const [x, setX] = useState(0);\n"
        "  axios.get('/foo');\n"
        "  return <div>{x}</div>;\n"
        "}\n"
        "export function Bar() {\n"
        "  useEffect(() => {}, []);\n"
        "  return <div>bar</div>;\n"
        "}\n"
    )

    def test_hooks_scoped_to_enclosing_component(self, tmp_path):
        _need("javascript")
        f = tmp_path / "Widgets.jsx"
        f.write_text(self.SRC, encoding="utf-8")
        comps = {c.name: c for c in extract_components(str(f), "react")}
        assert set(comps) == {"Foo", "Bar"}
        # Each component gets only the hooks it actually calls.
        assert comps["Foo"].hooks == ["useState"]
        assert comps["Bar"].hooks == ["useEffect"]
        # useEffect must not leak onto Foo, nor useState onto Bar.
        assert "useEffect" not in comps["Foo"].hooks
        assert "useState" not in comps["Bar"].hooks

    def test_file_level_imports_shared(self, tmp_path):
        # Static imports live at module scope — nothing encloses them, so they
        # remain file-level and are shared by every component in the file. Only
        # per-component *hooks* (call sites inside a body) are scoped.
        _need("javascript")
        f = tmp_path / "Widgets.jsx"
        f.write_text(self.SRC, encoding="utf-8")
        comps = {c.name: c for c in extract_components(str(f), "react")}
        for name in ("Foo", "Bar"):
            assert "react" in comps[name].imports
            assert "axios" in comps[name].imports
