"""Audit 0.7.1 — extract/routes + framework .scm regressions (fixer F6).

Covered items, in the order they appear below:

  C-55a/b/c(a), N2, N3
        FastAPI mount prefixes. ``APIRouter(prefix=…)`` composed with
        ``include_router(prefix=…)``; attribute-shaped includers, attribute
        route decorators and the ``router=`` keyword form; same-file cascades
        and a router mounted twice. Oracles were real ``app.openapi()`` output,
        a running Express server and a real Flask ``url_map``.
  V3-N1 Python ``import x as y`` emitted the literal target ``"x as y"``,
        which matched no label, so the import edge vanished entirely.
  GI-3224
        ``.csproj`` XML was parsed with entity expansion enabled.
  G-0953-2
        PHP interfaces / traits / enums produced no nodes at all.
  G-0947-12
        ASP.NET service extraction required a base list and captured no
        constructor injection — its main DI path was missing outright.
  G-0953-5
        A C# base *class* was recorded as an implemented *interface*.
  G-0950-2
        ``class Report < Reporting::Base`` was promoted to an ActiveRecord
        entity purely because the superclass path ends in ``Base``.
  G-0913-8
        ``.rake`` files parsed as nothing (extension mapped to no grammar).
  G-0950-9 / G-0942-4
        A file whose grammar is unavailable extracted to silence: no nodes, no
        failure record, exit 0. A renamed grammar entry point additionally
        advised reinstalling an already-installed package.
  G-0941-11
        PHP ``use App\\Models\\User;`` never bound (namespace separator fix
        lives in graph/build.py — this file supplies the PHP-side fixture).
"""
from __future__ import annotations

import sys
import types

import pytest

from codebeacon.extract.base import get_language
from codebeacon.extract.entities import extract_entities
from codebeacon.extract.routes import extract_routes
from codebeacon.extract.services import extract_services


def _need(grammar: str) -> None:
    if get_language(grammar) is None:
        pytest.skip(f"{grammar} grammar not installed")


def _pairs(routes) -> set[tuple[str, str]]:
    return {(r.method, r.path) for r in routes}


# ── C-55a — FastAPI composes the router's own prefix with the mount prefix ────

class TestFastapiPrefixComposition:
    COMPOSE = (
        "from fastapi import FastAPI, APIRouter\n"
        "app = FastAPI()\n"
        "router = APIRouter(prefix='/users')\n"
        "@router.get('/me')\n"
        "def get_me():\n    return {}\n"
        "app.include_router(router, prefix='/api/v1')\n"
    )

    def test_declared_and_mount_prefix_compose(self, tmp_path):
        _need("python")
        f = tmp_path / "compose.py"
        f.write_text(self.COMPOSE, encoding="utf-8")
        pairs = _pairs(extract_routes(str(f), "fastapi"))
        # Real FastAPI 0.141 serves /api/v1/users/me for this app.
        assert ("GET", "/api/v1/users/me") in pairs
        # The mount write used to clobber the declaration write.
        assert ("GET", "/api/v1/me") not in pairs

    def test_include_before_decorator_is_equivalent(self, tmp_path):
        _need("python")
        f = tmp_path / "swapped.py"
        f.write_text(
            "from fastapi import FastAPI, APIRouter\n"
            "app = FastAPI()\n"
            "router = APIRouter(prefix='/users')\n"
            "app.include_router(router, prefix='/api/v1')\n"
            "@router.get('/me')\n"
            "def get_me():\n    return {}\n",
            encoding="utf-8",
        )
        assert _pairs(extract_routes(str(f), "fastapi")) == {("GET", "/api/v1/users/me")}

    def test_unmounted_router_keeps_only_its_own_prefix(self, tmp_path):
        _need("python")
        f = tmp_path / "leaf.py"
        f.write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter(prefix='/consumer')\n"
            "@router.post('/notification')\n"
            "def notify():\n    return {}\n",
            encoding="utf-8",
        )
        assert _pairs(extract_routes(str(f), "fastapi")) == {("POST", "/consumer/notification")}

    def test_include_without_prefix_keeps_declared_prefix(self, tmp_path):
        _need("python")
        f = tmp_path / "declonly.py"
        f.write_text(
            "from fastapi import FastAPI, APIRouter\n"
            "app = FastAPI()\n"
            "router = APIRouter(prefix='/users')\n"
            "@router.get('/me')\n"
            "def get_me():\n    return {}\n"
            "app.include_router(router)\n",
            encoding="utf-8",
        )
        assert _pairs(extract_routes(str(f), "fastapi")) == {("GET", "/users/me")}


# ── C-55b — the four include/decorator shapes that lost prefixes or routes ────

class TestFastapiIncludeShapes:
    ATTRIBUTE_CALLEE = (
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/users')\n"
        "@router.get('/me')\n"
        "def me():\n    return {}\n"
        "api.v1.app.include_router(router, prefix='/api/v1')\n"
    )
    KEYWORD_ROUTER = (
        "from fastapi import FastAPI, APIRouter\n"
        "app = FastAPI()\n"
        "router = APIRouter(prefix='/users')\n"
        "@router.get('/me')\n"
        "def me():\n    return {}\n"
        "app.include_router(router=router, prefix='/api/v1')\n"
    )
    ATTRIBUTE_ARG = (
        "from fastapi import FastAPI\n"
        "import consumer\n"
        "app = FastAPI()\n"
        "router = consumer.consumer_router\n"
        "@router.get('/ping')\n"
        "def ping():\n    return {}\n"
        "app.include_router(consumer.consumer_router, prefix='/api/v1/consumer')\n"
    )
    ATTRIBUTE_DECORATOR = (
        "from fastapi import FastAPI\n"
        "import consumer\n"
        "app = FastAPI()\n"
        "@consumer.consumer_router.get('/ping')\n"
        "def ping():\n    return {}\n"
        "app.include_router(consumer.consumer_router, prefix='/api/v1/consumer')\n"
    )

    @pytest.mark.parametrize(
        "name,source,expected",
        [
            ("attribute_callee", ATTRIBUTE_CALLEE, ("GET", "/api/v1/users/me")),
            ("keyword_router", KEYWORD_ROUTER, ("GET", "/api/v1/users/me")),
            # An attribute-valued router aliased to a local name: the decorator
            # names the alias, the mount names the attribute.
            ("attribute_arg", ATTRIBUTE_ARG, ("GET", "/api/v1/consumer/ping")),
            # This shape lost the ENTIRE route, not merely its prefix: the
            # decorator pattern demanded an identifier object.
            ("attribute_decorator", ATTRIBUTE_DECORATOR, ("GET", "/api/v1/consumer/ping")),
        ],
    )
    def test_shape_resolves_to_the_served_path(self, tmp_path, name, source, expected):
        _need("python")
        f = tmp_path / f"{name}.py"
        f.write_text(source, encoding="utf-8")
        # N3: exactly one route — no phantom unprefixed duplicate. Two .scm
        # include patterns both fired on a prefixed call before this fix, so any
        # collect-all reading double-counted it.
        assert _pairs(extract_routes(str(f), "fastapi")) == {expected}

    def test_alias_never_overrides_a_router_with_its_own_identity(self, tmp_path):
        _need("python")
        f = tmp_path / "shadow.py"
        f.write_text(
            "from fastapi import FastAPI, APIRouter\n"
            "import other\n"
            "app = FastAPI()\n"
            "router = APIRouter(prefix='/mine')\n"
            "router = other.their_router\n"       # rebinding noise
            "@router.get('/me')\n"
            "def me():\n    return {}\n"
            "app.include_router(router, prefix='/api')\n",
            encoding="utf-8",
        )
        # `router` declares its own prefix and is mounted under its own name, so
        # it is the real router — the alias must not redirect it to their_router.
        assert _pairs(extract_routes(str(f), "fastapi")) == {("GET", "/api/mine/me")}


# ── C-55c(a) + N2 — same-file cascades and multi-mounted routers ─────────────

class TestSameFileMountCascade:
    def test_fastapi_router_into_router(self, tmp_path):
        _need("python")
        f = tmp_path / "cascade.py"
        f.write_text(
            "from fastapi import FastAPI, APIRouter\n"
            "inner = APIRouter(prefix='/inner')\n"
            "@inner.get('/leaf')\n"
            "def leaf():\n    return {}\n"
            "mid = APIRouter(prefix='/mid')\n"
            "mid.include_router(inner, prefix='/x')\n"
            "app = FastAPI()\n"
            "app.include_router(mid, prefix='/root')\n",
            encoding="utf-8",
        )
        # Every level composes; the old flat map kept only the innermost mount.
        assert _pairs(extract_routes(str(f), "fastapi")) == {("GET", "/root/mid/x/inner/leaf")}

    def test_fastapi_router_mounted_twice(self, tmp_path):
        _need("python")
        f = tmp_path / "double.py"
        f.write_text(
            "from fastapi import FastAPI, APIRouter\n"
            "app = FastAPI()\n"
            "r = APIRouter(prefix='/u')\n"
            "@r.get('/me')\n"
            "def me():\n    return {}\n"
            "app.include_router(r, prefix='/v1')\n"
            "app.include_router(r, prefix='/v2')\n",
            encoding="utf-8",
        )
        # /v1 + /v2 versioning: last-write-wins dropped one real route.
        assert _pairs(extract_routes(str(f), "fastapi")) == {
            ("GET", "/v1/u/me"), ("GET", "/v2/u/me"),
        }

    def test_express_router_into_router(self, tmp_path):
        _need("javascript")
        f = tmp_path / "cascade.js"
        f.write_text(
            "const express = require('express');\n"
            "const app = express();\n"
            "const inner = express.Router();\n"
            "const mid = express.Router();\n"
            "inner.get('/leaf', (req, res) => res.send('ok'));\n"
            "mid.use('/x', inner);\n"
            "app.use('/root', mid);\n",
            encoding="utf-8",
        )
        # A running Express server 404s /x/leaf and 200s /root/x/leaf.
        assert _pairs(extract_routes(str(f), "express")) == {("GET", "/root/x/leaf")}

    def test_express_router_mounted_twice(self, tmp_path):
        _need("javascript")
        f = tmp_path / "double.js"
        f.write_text(
            "const express = require('express');\n"
            "const app = express();\n"
            "const r = express.Router();\n"
            "r.get('/me', (req, res) => res.send('ok'));\n"
            "app.use('/v1', r);\n"
            "app.use('/v2', r);\n",
            encoding="utf-8",
        )
        assert _pairs(extract_routes(str(f), "express")) == {
            ("GET", "/v1/me"), ("GET", "/v2/me"),
        }

    def test_flask_nested_blueprint(self, tmp_path):
        _need("python")
        f = tmp_path / "nested.py"
        f.write_text(
            "from flask import Flask, Blueprint\n"
            "app = Flask(__name__)\n"
            "child = Blueprint('child', __name__, url_prefix='/child')\n"
            "@child.route('/leaf')\n"
            "def leaf():\n    return ''\n"
            "parent = Blueprint('parent', __name__, url_prefix='/parent')\n"
            "parent.register_blueprint(child)\n"
            "app.register_blueprint(parent, url_prefix='/root')\n",
            encoding="utf-8",
        )
        # Flask OVERRIDE semantics all the way down: parent's own /parent is
        # replaced by /root, child keeps its own /child (registered bare).
        assert _pairs(extract_routes(str(f), "flask")) == {("GET", "/root/child/leaf")}

    def test_flask_blueprint_registered_twice(self, tmp_path):
        _need("python")
        f = tmp_path / "double_bp.py"
        f.write_text(
            "from flask import Flask, Blueprint\n"
            "app = Flask(__name__)\n"
            "bp = Blueprint('api', __name__, url_prefix='/ignored')\n"
            "@bp.route('/me')\n"
            "def me():\n    return ''\n"
            "app.register_blueprint(bp, url_prefix='/v1')\n"
            "app.register_blueprint(bp, url_prefix='/v2')\n",
            encoding="utf-8",
        )
        assert _pairs(extract_routes(str(f), "flask")) == {
            ("GET", "/v1/me"), ("GET", "/v2/me"),
        }

    def test_mount_cycle_terminates(self, tmp_path):
        _need("python")
        f = tmp_path / "cycle.py"
        f.write_text(
            "from fastapi import APIRouter\n"
            "a = APIRouter(prefix='/a')\n"
            "b = APIRouter(prefix='/b')\n"
            "a.include_router(b, prefix='/x')\n"
            "b.include_router(a, prefix='/y')\n"
            "@a.get('/leaf')\n"
            "def leaf():\n    return {}\n",
            encoding="utf-8",
        )
        # Nonsense input, but it must not hang or recurse without bound.
        routes = extract_routes(str(f), "fastapi")
        assert routes and all(r.path.endswith("/leaf") for r in routes)


# ── V3-N1 — `import x as y` lost the import edge entirely ────────────────────

class TestAliasedPlainImport:
    @pytest.mark.parametrize("framework", ["fastapi", "flask", "django"])
    def test_alias_target_matches_plain_target(self, tmp_path, framework):
        _need("python")
        from codebeacon.extract.dependencies import extract_dependencies

        plain = tmp_path / "plain.py"
        plain.write_text("import widget\n", encoding="utf-8")
        aliased = tmp_path / "aliased.py"
        aliased.write_text("import widget as w\n", encoding="utf-8")

        plain_targets = {e.target for e in extract_dependencies(str(plain), framework)}
        alias_targets = {e.target for e in extract_dependencies(str(aliased), framework)}
        # The capture returned the whole aliased_import node, so the target was
        # the literal string "widget as w" — which matches no node label, so the
        # edge was silently dropped at build time.
        assert plain_targets == alias_targets == {"widget"}

    def test_no_import_target_contains_an_as_clause(self, tmp_path):
        _need("python")
        from codebeacon.extract.dependencies import extract_dependencies

        f = tmp_path / "mixed.py"
        f.write_text(
            "import widget as w\n"
            "import os.path as p\n"
            "from pkg import thing as t\n"
            "import plain\n",
            encoding="utf-8",
        )
        targets = {e.target for e in extract_dependencies(str(f), "fastapi")}
        assert targets, "expected some import edges"
        assert not any(" as " in t for t in targets), targets


# ── GI-3224 — .csproj XML entity expansion ───────────────────────────────────

class TestCsprojEntityScreen:
    BOMB = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE Project [\n"
        '  <!ENTITY a "AAAAAAAAAA">\n'
        '  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
        '  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">\n'
        "]>\n"
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <ItemGroup>\n"
        '    <PackageReference Include="&c;" Version="1.0.0" />\n'
        "  </ItemGroup>\n"
        "</Project>\n"
    )
    PLAIN = (
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <ItemGroup>\n"
        '    <ProjectReference Include="..\\Core\\Core.csproj" />\n'
        '    <PackageReference Include="Serilog" Version="3.0.0" />\n'
        "  </ItemGroup>\n"
        "</Project>\n"
    )
    NAMESPACED = (
        '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">\n'
        "  <ItemGroup>\n"
        '    <PackageReference Include="Serilog" Version="3.0.0" />\n'
        "  </ItemGroup>\n"
        "</Project>\n"
    )

    def test_entity_document_is_refused_before_parsing(self, tmp_path):
        from codebeacon.extract.dotnet import extract_dotnet_edges

        f = tmp_path / "bomb.csproj"
        f.write_text(self.BOMB, encoding="utf-8")
        edges = extract_dotnet_edges(str(f))
        assert edges == []
        # Belt and braces: nothing longer than the source can have been expanded.
        assert all(len(e.target) <= len(self.BOMB) for e in edges)

    def test_plain_csproj_still_extracts(self, tmp_path):
        from codebeacon.extract.dotnet import extract_dotnet_edges

        f = tmp_path / "Api.csproj"
        f.write_text(self.PLAIN, encoding="utf-8")
        targets = {e.target for e in extract_dotnet_edges(str(f))}
        assert targets == {"../Core/Core.csproj", "Serilog"}

    def test_default_namespaced_csproj_still_extracts(self, tmp_path):
        from codebeacon.extract.dotnet import extract_dotnet_edges

        f = tmp_path / "Ns.csproj"
        f.write_text(self.NAMESPACED, encoding="utf-8")
        assert {e.target for e in extract_dotnet_edges(str(f))} == {"Serilog"}


# ── G-0914-1 (hygiene half) — no absolute paths in .NET project edges ────────

class TestDotnetTargetsAreRelative:
    def test_project_reference_targets_carry_no_machine_path(self, tmp_path):
        from codebeacon.extract.dotnet import extract_dotnet_edges

        (tmp_path / "Api").mkdir()
        sln = tmp_path / "App.sln"
        sln.write_text(
            'Project("{GUID}") = "Api", "Api\\Api.csproj", "{GUID2}"\n',
            encoding="utf-8",
        )
        proj = tmp_path / "Api" / "Api.csproj"
        proj.write_text(
            "<Project>\n  <ItemGroup>\n"
            '    <ProjectReference Include="..\\Core\\Core.csproj" />\n'
            "  </ItemGroup>\n</Project>\n",
            encoding="utf-8",
        )
        targets = [e.target for e in extract_dotnet_edges(str(sln))]
        targets += [e.target for e in extract_dotnet_edges(str(proj))]
        assert targets, "expected project-reference edges"
        # Absolute, machine-specific targets must never be minted: they would
        # leak the scan root into any artifact these edges later reach.
        assert not any(t.startswith("/") or str(tmp_path) in t for t in targets)
        assert "Api/Api.csproj" in targets
        assert "../Core/Core.csproj" in targets


# ── G-0953-2 — PHP interfaces, traits and enums are nodes ────────────────────

class TestPhpClassLikeCoverage:
    def test_interface_trait_and_enum_extract(self, tmp_path):
        _need("php")
        f = tmp_path / "Contracts.php"
        f.write_text(
            "<?php\n"
            "namespace App\\Contracts;\n"
            "interface PaymentGateway { public function charge(int $c): bool; }\n"
            "trait HasUuid { public function uuid(): string { return '1'; } }\n"
            "enum PaymentStatus: string { case Paid = 'paid'; }\n"
            "class Plain {}\n",
            encoding="utf-8",
        )
        names = {s.name for s in extract_services(str(f), "laravel")[0]}
        # Interfaces are Laravel's DI contract surface and traits its primary
        # reuse mechanism; class_declaration was the only class-like pattern.
        assert names == {"PaymentGateway", "HasUuid", "PaymentStatus", "Plain"}


# ── G-0947-12 — ASP.NET service + DI coverage ────────────────────────────────

class TestAspnetServiceCoverage:
    SRC = (
        "namespace Api.Services;\n"
        "public class BaseService { }\n"
        "public class UserService : IUserService\n"
        "{\n"
        "    private readonly IRepo _repo;\n"
        "    public UserService(IRepo repo, int retries) { _repo = repo; }\n"
        "}\n"
        "public class AuditService : BaseService\n"
        "{\n"
        "    public AuditService(IRepo repo) { }\n"
        "}\n"
        "public class OrderService(IRepo repo, ILogger logger)\n"
        "{\n"
        "    public string Get() => repo.Find(1);\n"
        "}\n"
    )

    def _services(self, tmp_path):
        _need("csharp")
        f = tmp_path / "Services.cs"
        f.write_text(self.SRC, encoding="utf-8")
        svcs, unresolved = extract_services(str(f), "aspnet")
        return {s.name: s for s in svcs}, unresolved

    def test_class_without_a_base_list_is_a_node(self, tmp_path):
        svcs, _ = self._services(tmp_path)
        # The only service pattern used to require a base_list, so most of a
        # .NET codebase never entered the graph.
        assert "BaseService" in svcs
        assert "OrderService" in svcs

    def test_classic_constructor_injection_captured(self, tmp_path):
        svcs, unresolved = self._services(tmp_path)
        assert svcs["UserService"].dependencies == ["IRepo"]
        assert ("UserService", "IRepo") in {
            (u.source_node_id.rsplit("::", 1)[-1], u.ref_name) for u in unresolved
        }

    def test_primary_constructor_injection_captured(self, tmp_path):
        svcs, _ = self._services(tmp_path)
        assert svcs["OrderService"].dependencies == ["IRepo", "ILogger"]

    def test_primitive_parameters_are_not_dependencies(self, tmp_path):
        svcs, _ = self._services(tmp_path)
        # `int retries` is a config value, not an injected collaborator.
        assert "int" not in svcs["UserService"].dependencies

    @pytest.mark.parametrize(
        "call,expected",
        [
            ("s.AddScoped<IUserService, UserService>();", ("UserService", "IUserService")),
            ("s.AddScoped<Abc.IMailer, Abc.SmtpMailer>();", ("SmtpMailer", "IMailer")),
            ("s.AddScoped<IRepo<User>, SqlRepo>();", ("SqlRepo", "IRepo")),
        ],
    )
    def test_generic_registration_shapes(self, tmp_path, call, expected):
        _need("csharp")
        f = tmp_path / "Startup.cs"
        f.write_text(
            "public class Startup {\n"
            "  public void C(IServiceCollection s) {\n"
            f"    {call}\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        _svcs, unresolved = extract_services(str(f), "aspnet")
        binds = {(u.source_node_id.rsplit("::", 1)[-1], u.ref_name)
                 for u in unresolved if u.ref_type == "bind"}
        # Qualified and generic type arguments were both missed by an
        # identifier-only type_argument_list.
        assert expected in binds


# ── G-0953-5 — a base class is not an implemented interface ──────────────────

class TestAspnetHeritageClassification:
    def test_base_class_is_extends_and_interface_is_implements(self, tmp_path):
        svcs, _ = TestAspnetServiceCoverage()._services(tmp_path)
        audit = svcs["AuditService"]
        user = svcs["UserService"]
        # BaseService is a class declared in the same file.
        assert audit.extends == ["BaseService"]
        assert audit.implements == []
        assert "implements:BaseService" not in audit.annotations
        # IUserService follows the .NET interface convention.
        assert user.implements == ["IUserService"]
        assert user.extends == []

    def test_every_base_list_entry_is_recorded(self, tmp_path):
        _need("csharp")
        f = tmp_path / "Multi.cs"
        f.write_text(
            "public class Base { }\n"
            "public class Svc : Base, IFoo, IBar { }\n",
            encoding="utf-8",
        )
        svcs = {s.name: s for s in extract_services(str(f), "aspnet")[0]}
        # Only the FIRST base-list entry used to be captured.
        assert svcs["Svc"].extends == ["Base"]
        assert svcs["Svc"].implements == ["IFoo", "IBar"]


# ── G-0950-2 — Rails entity base matching ────────────────────────────────────

class TestRailsEntityBase:
    SRC = (
        "class Report < Reporting::Base\nend\n"
        "class Widget < ActiveRecord::Base\nend\n"
        "class Post < ApplicationRecord\nend\n"
        "class Plain\nend\n"
    )

    def test_unrelated_scoped_base_is_not_an_entity(self, tmp_path):
        _need("ruby")
        f = tmp_path / "models.rb"
        f.write_text(self.SRC, encoding="utf-8")
        names = {e.name for e in extract_entities(str(f), "rails")}
        # Matching the tail constant alone promoted any `X::Base` superclass.
        assert "Report" not in names
        assert "Plain" not in names

    def test_real_activerecord_bases_are_entities(self, tmp_path):
        _need("ruby")
        f = tmp_path / "models.rb"
        f.write_text(self.SRC, encoding="utf-8")
        names = {e.name for e in extract_entities(str(f), "rails")}
        assert "Widget" in names
        # `class Post < ApplicationRecord` — the canonical Rails model — matched
        # nothing at all: both bases shared one pattern, and tree-sitter applies
        # a pattern's predicates to the whole pattern, so the bare-constant
        # branch also had to satisfy `#eq? "Base"`.
        assert "Post" in names


# ── G-0913-8 — .rake files are Ruby ──────────────────────────────────────────

class TestRakeExtension:
    def test_rake_file_extracts_like_ruby(self, tmp_path):
        _need("ruby")
        from codebeacon.extract.base import EXT_TO_GRAMMAR
        from codebeacon.extract.dependencies import extract_dependencies

        assert EXT_TO_GRAMMAR[".rake"] == "ruby"
        f = tmp_path / "stats.rake"
        f.write_text(
            "require 'csv'\n"
            "class RakeHelper\n  def run; Widget.tally; end\nend\n"
            "namespace :stats do\n  task :build do\n    RakeHelper.new.run\n  end\nend\n",
            encoding="utf-8",
        )
        assert "RakeHelper" in {s.name for s in extract_services(str(f), "rails")[0]}
        assert "csv" in {e.target for e in extract_dependencies(str(f), "rails")}


# ── G-0950-9 / G-0942-4 — an unavailable grammar is a loud failure ───────────

class TestGrammarUnavailableIsAFailure:
    """A file codebeacon *chose* to scan must never extract to silence."""

    @pytest.fixture
    def _isolated(self, monkeypatch):
        from codebeacon.extract import base

        monkeypatch.setattr(base, "_LANG_CACHE", dict(base._LANG_CACHE))
        monkeypatch.setattr(base, "_LANG_ERROR", dict(base._LANG_ERROR))
        monkeypatch.setattr(base, "_GRAMMAR_MODULES", dict(base._GRAMMAR_MODULES))
        base._LANG_CACHE.pop("ruby", None)
        base._LANG_ERROR.pop("ruby", None)
        return base

    def _rb(self, tmp_path):
        f = tmp_path / "model.rb"
        f.write_text("class Widget\nend\n", encoding="utf-8")
        return str(f)

    def test_missing_grammar_becomes_an_extraction_failure(self, tmp_path, _isolated):
        from codebeacon.extract.base import GrammarUnavailableError
        from codebeacon.wave import ExtractionFailure, _extract_file

        _isolated._GRAMMAR_MODULES["ruby"] = "tree_sitter_ruby_absent_xyz"
        with pytest.warns(UserWarning, match="not installed"):
            result = _extract_file(self._rb(tmp_path), "rails", str(tmp_path))
        # Previously: zero nodes, zero failures, failure_rate 0.0, exit 0.
        assert isinstance(result, ExtractionFailure)
        assert result.error_type == GrammarUnavailableError.__name__
        assert "codebeacon[ruby]" in result.error

    def test_renamed_entry_point_names_the_real_cause(self, tmp_path, _isolated):
        from codebeacon.wave import ExtractionFailure, _extract_file

        stub = types.ModuleType("tree_sitter_ruby_stub_xyz")  # no language()
        monkeypatched = sys.modules.setdefault("tree_sitter_ruby_stub_xyz", stub)
        try:
            _isolated._GRAMMAR_MODULES["ruby"] = "tree_sitter_ruby_stub_xyz"
            with pytest.warns(UserWarning) as rec:
                result = _extract_file(self._rb(tmp_path), "rails", str(tmp_path))
            message = str(rec[0].message)
            # The package IS installed — telling the user to install it sends
            # them down the wrong path; the fix is a version pin.
            assert "not installed" not in message
            assert "entry point" in message
            assert isinstance(result, ExtractionFailure)
        finally:
            if monkeypatched is stub:
                sys.modules.pop("tree_sitter_ruby_stub_xyz", None)

    def test_unmapped_extension_is_still_a_clean_skip(self, tmp_path, _isolated):
        from codebeacon.extract.base import parse_file

        f = tmp_path / "notes.txt"
        f.write_text("hello\n", encoding="utf-8")
        # An extension codebeacon never claimed to read is a skip, not a failure.
        assert parse_file(str(f)) is None


# ── G-0941-11 — PHP namespace separator (fix in graph/build.py) ──────────────

class TestPhpImportEdgesBind:
    """The PHP-side fixture for the ``_import_to_label`` separator fix.

    ``_import_to_label`` knew only ``.`` (Java) and ``/`` (path) separators, so
    every PHP ``use`` target failed label lookup and was dropped — with or
    without a leading backslash, the whole PHP import graph was empty. A unit
    assertion on the helper alone would not have caught the shipped state, so
    this drives real files through extraction and graph construction.
    """

    def _graph(self, tmp_path):
        _need("php")
        from codebeacon.common.types import ProjectInfo
        from codebeacon.graph.build import build_graph
        from codebeacon.wave import auto_wave

        (tmp_path / "app" / "Models").mkdir(parents=True)
        (tmp_path / "app" / "Contracts").mkdir(parents=True)
        (tmp_path / "app" / "Traits").mkdir(parents=True)

        files = {
            "app/Models/User.php": (
                "<?php\nnamespace App\\Models;\nclass User {}\n"
            ),
            "app/Contracts/PaymentGateway.php": (
                "<?php\nnamespace App\\Contracts;\n"
                "interface PaymentGateway { public function charge(int $c): bool; }\n"
            ),
            "app/Traits/HasUuid.php": (
                "<?php\nnamespace App\\Traits;\n"
                "trait HasUuid { public function uuid(): string { return '1'; } }\n"
            ),
            "app/UserService.php": (
                "<?php\nnamespace App;\n"
                "use App\\Models\\User;\n"
                "use \\App\\Contracts\\PaymentGateway;\n"
                "use App\\Traits\\HasUuid;\n"
                "class UserService { use HasUuid; public function make() { return new User(); } }\n"
            ),
        }
        paths = []
        for rel, body in files.items():
            p = tmp_path / rel
            p.write_text(body, encoding="utf-8")
            paths.append(str(p))

        project = ProjectInfo(
            name="php", path=str(tmp_path), framework="laravel",
            language="php", signature_file="composer.json",
        )
        return build_graph([auto_wave(project, sorted(paths))])

    @staticmethod
    def _import_edges(G):
        labels = {n: d.get("label") for n, d in G.nodes(data=True)}
        return {
            (labels.get(s), labels.get(t))
            for s, t, d in G.edges(data=True)
            if d.get("relation") == "imports_from"
        }

    def test_label_extraction_folds_the_namespace_separator(self):
        from codebeacon.graph.build import _import_to_label

        assert _import_to_label("App\\Models\\User") == "User"
        assert _import_to_label("\\App\\Contracts\\PaymentGateway") == "PaymentGateway"
        # Dot- and slash-separated imports must be unaffected.
        assert _import_to_label("com.example.service.UserSvc") == "UserSvc"
        assert _import_to_label("@/components/Button") == "Button"

    def test_use_statements_produce_import_edges(self, tmp_path):
        edges = self._import_edges(self._graph(tmp_path))
        # Zero edges before the fix, for every Laravel project in an index.
        assert ("UserService", "User") in edges
        # A leading-backslash (fully qualified) use must bind identically —
        # upstream reported only this spelling; on codebeacon both were broken.
        assert ("UserService", "PaymentGateway") in edges
        # Only reachable together with the interface/trait node patterns: the
        # trait had no node to bind to before G-0953-2.
        assert ("UserService", "HasUuid") in edges

    def test_psr4_root_mapping_still_binds(self, tmp_path):
        """The case that isolates the label tier from the path resolver.

        When a file's path mirrors its namespace, the module resolver binds the
        import by path and the label never matters. Composer's PSR-4 root
        mapping (``App\\`` → ``src/``) breaks that mirror, which is the common
        real-world layout — and there the label tier is the only thing left, so
        this is what the separator fix actually holds up.
        """
        _need("php")
        from codebeacon.common.types import ProjectInfo
        from codebeacon.graph.build import build_graph
        from codebeacon.wave import auto_wave

        (tmp_path / "src").mkdir()
        gateway = tmp_path / "src" / "Gateway.php"
        gateway.write_text(
            "<?php\nnamespace App\\Contracts;\ninterface PaymentGateway {}\n",
            encoding="utf-8",
        )
        service = tmp_path / "src" / "Service.php"
        service.write_text(
            "<?php\nnamespace App;\n"
            "use App\\Contracts\\PaymentGateway;\nclass UserService {}\n",
            encoding="utf-8",
        )
        project = ProjectInfo(
            name="php", path=str(tmp_path), framework="laravel",
            language="php", signature_file="composer.json",
        )
        G = build_graph([auto_wave(project, [str(gateway), str(service)])])
        assert ("UserService", "PaymentGateway") in self._import_edges(G)


# ── G-0953-1 — JS/TS class heritage (handed over from F5) ────────────────────

class TestJsClassHeritage:
    """express.scm had no heritage pattern, so plain JS/TS classes carried
    extends=[] and the express/node/react family had no producer for the
    interface→implementation DI path at all.

    The pattern captures the heritage CONTAINER on purpose. Naming the parts
    is impossible across the three grammars this query is allowlisted for:
    `name: (identifier)` is an Impossible pattern under typescript and tsx,
    `name: (type_identifier)` is an Invalid node type under javascript, and
    either one would make run_query raise GrammarQueryError for every file of
    the other grammar.
    """

    JS = (
        "class BaseDb {}\n"
        "class Db extends BaseDb {}\n"
        "class Mixed extends Mixin(Base) {}\n"
        "export class ExportedChild extends BaseDb {}\n"
    )
    TS = (
        "class Base {}\n"
        "class TsChild extends Base implements IFace, IOther {}\n"
    )

    def _by_name(self, tmp_path, filename, source):
        f = tmp_path / filename
        f.write_text(source, encoding="utf-8")
        return {s.name: s for s in extract_services(str(f), "express")[0]}

    def test_javascript_extends_is_captured(self, tmp_path):
        _need("javascript")
        svcs = self._by_name(tmp_path, "db.js", self.JS)
        assert svcs["Db"].extends == ["BaseDb"]
        assert svcs["ExportedChild"].extends == ["BaseDb"]
        assert svcs["BaseDb"].extends == []

    def test_typescript_extends_and_implements(self, tmp_path):
        _need("typescript")
        svcs = self._by_name(tmp_path, "db.ts", self.TS)
        # TS wraps each half in extends_clause / implements_clause; JS has
        # neither node type. Both must land in the same two fields.
        assert svcs["TsChild"].extends == ["Base"]
        assert svcs["TsChild"].implements == ["IFace", "IOther"]

    @pytest.mark.parametrize("filename,grammar", [("m.js", "javascript"), ("m.ts", "typescript")])
    def test_mixin_factory_resolves_to_the_factory_not_the_call(
        self, tmp_path, filename, grammar,
    ):
        _need(grammar)
        svcs = self._by_name(tmp_path, filename, "class Mixed extends Mixin(Base) {}\n")
        # Without unwrapping the call the two grammars DISAGREE on the same
        # source: TS's extends_clause `value` field is the whole call
        # expression ("Mixin(Base)") while JS yields just "Mixin".
        assert svcs["Mixed"].extends == ["Mixin"]

    def test_heritage_resolves_a_base_class_in_another_file(self, tmp_path):
        """The payoff: SymbolTable already consumes ServiceInfo.extends, so a
        base class declared elsewhere now resolves. This was a pure producer
        gap — nothing downstream needed changing."""
        _need("javascript")
        from codebeacon.common.symbols import SymbolTable
        from codebeacon.common.types import Node, UnresolvedRef

        base = tmp_path / "base.js"
        base.write_text("class BaseDb {}\n", encoding="utf-8")
        child = tmp_path / "child.js"
        child.write_text("class Db extends BaseDb {}\n", encoding="utf-8")

        nodes = []
        for path in (base, child):
            for svc in extract_services(str(path), "express")[0]:
                nodes.append(Node(
                    id=f"p::{svc.name}", label=svc.name, type="class",
                    source_file=str(path), line=svc.line,
                    metadata={"extends": list(svc.extends),
                              "implements": list(svc.implements)},
                ))
        table = SymbolTable()
        table.build(nodes)
        edge = table.resolve_ref(UnresolvedRef(
            source_node_id="p::Consumer", ref_type="inject",
            ref_name="BaseDb", framework="express",
        ))
        # BaseDb now maps to its subclass Db through _implements_map.
        assert edge is not None
        assert edge.target == "p::Db"


# ── G-0950-3 — CommonJS member exports (handed over from F5) ─────────────────

class TestCommonJsMemberExports:
    # The wrapper call is deliberately spread across lines so the reported line
    # can distinguish the wrapper call site from the wrapped definition.
    SRC = (
        "function userRepo() {}\n"                    # 1
        "exports.userRepo = userRepo;\n"              # 2
        "exports.handler = wrap(\n"                   # 3
        "  function actualHandler(req) {\n"           # 4
        "    return req;\n"                           # 5
        "  }\n"                                       # 6
        ");\n"                                        # 7
        "module.exports.lazy = wrap(() => {\n"        # 8
        "  return 1;\n"                               # 9
        "});\n"                                       # 10
        "exports[dynamicKey] = something;\n"          # 11
    )

    def _names(self, tmp_path):
        _need("javascript")
        f = tmp_path / "userRepo.js"
        f.write_text(self.SRC, encoding="utf-8")
        return {s.name: s for s in extract_services(str(f), "express")[0]}

    def test_all_member_export_forms_become_nodes(self, tmp_path):
        svcs = self._names(tmp_path)
        # Only exported CLASSES had a pattern, so a CommonJS module's entire
        # public surface produced no nodes at all.
        assert {"userRepo", "handler", "lazy"} <= set(svcs)

    def test_wrapper_never_becomes_the_export_identity(self, tmp_path):
        svcs = self._names(tmp_path)
        # The node is the exported property, not the wrapping call.
        assert "wrap" not in svcs
        assert svcs["handler"].name == "handler"
        assert svcs["lazy"].name == "lazy"

    def test_computed_export_is_skipped(self, tmp_path):
        svcs = self._names(tmp_path)
        # `exports[key] = …` is a subscript_expression — its name is not
        # knowable statically, so it is excluded by construction.
        assert "dynamicKey" not in svcs
        assert "something" not in svcs

    def test_line_points_at_the_wrapped_definition(self, tmp_path):
        svcs = self._names(tmp_path)
        # `exports.handler = wrap(` is line 3; the function it wraps — the
        # actual definition — starts on line 4.
        assert svcs["handler"].line == 4
        # An inline arrow starts on the assignment line itself.
        assert svcs["lazy"].line == 8
        assert svcs["userRepo"].line == 2
