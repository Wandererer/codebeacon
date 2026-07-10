"""Audit 0.6.9 — detector fixes (group F-C).

Covers four defects in ``codebeacon/discover/detector.py``:

* **C10** — multi-manifest tie-break. ``detect_framework`` was pure
  first-match-wins over ``SIGNATURE_MAP``, so a Python repo carrying an
  incidental root ``package.json`` (prettier/husky/tailwind) was silently
  misdetected as ``node`` — zeroing out extraction for its ``.py`` sources.
* **G10** — duplicate project names. A project's ``name`` is its identity for
  every downstream surface (graph node-ID prefix + ``project`` attr, wiki /
  obsidian folder, contextmap stats key, ``project_roots``). Two projects
  sharing a directory name (appA/frontend + appB/frontend) conflated: collapsed
  route nodes, merged folders, summed stat rows.
* **C17** (detector part) — parallel-route ``@slot`` segments were left in
  App-Router URL paths.
* **G02** (detector part) — uppercase file extensions (``.PY``, ``.TSX``) were
  ignored by the language vote and the Next.js/Nuxt fs-route walker.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.discover.detector import (
    detect_framework,
    discover_projects,
    _detect_language_from_files,
    _fs_routes_from_dir,
    _app_router_path,
)


# ── C10: multi-manifest tie-break ────────────────────────────────────────────

class TestMultiManifestTieBreak:
    def test_pyproject_with_stray_package_json_is_python(self, tmp_path):
        """pyproject(fastapi) + a docs-tooling package.json → fastapi/python,
        NOT node. Reproduces the silent Python-misdetected-as-node bug."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\ndependencies = ["fastapi", "uvicorn"]\n'
        )
        (tmp_path / "package.json").write_text(
            '{"name": "docs", "devDependencies": {"prettier": "^3.0.0"}}'
        )
        (tmp_path / "main.py").write_text("app = 1\n")
        (tmp_path / "utils.py").write_text("x = 1\n")
        (tmp_path / "models.py").write_text("y = 1\n")
        fw, lang, _ = detect_framework(str(tmp_path))
        assert (fw, lang) == ("fastapi", "python")

    def test_requirements_django_with_stray_package_json_is_django(self, tmp_path):
        """requirements(Django) + stray package.json → django/python."""
        (tmp_path / "requirements.txt").write_text("Django>=4.2\n")
        (tmp_path / "package.json").write_text(
            '{"devDependencies": {"prettier": "^3.0.0"}}'
        )
        (tmp_path / "manage.py").write_text("import django\n")
        (tmp_path / "views.py").write_text("z = 1\n")
        fw, lang, _ = detect_framework(str(tmp_path))
        assert (fw, lang) == ("django", "python")

    def test_package_json_with_stray_requirements_stays_node(self, tmp_path):
        """The tie-break is symmetric: a Node repo with a stray requirements.txt
        (a helper script, not the project language) must stay react/typescript."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18", "react-dom": "^18"}}'
        )
        (tmp_path / "requirements.txt").write_text("black\n")  # dev helper
        (tmp_path / "App.tsx").write_text("export const App = () => null\n")
        (tmp_path / "index.tsx").write_text("import './App'\n")
        fw, lang, _ = detect_framework(str(tmp_path))
        assert (fw, lang) == ("react", "typescript")

    def test_go_mod_with_stray_package_json_stays_go(self, tmp_path):
        """go.mod(gin) + stray package.json with dominant .go sources → gin.
        (go.mod already precedes package.json in SIGNATURE_MAP, but this is now
        a multi-manifest root so the language vote must still land on Go.)"""
        (tmp_path / "go.mod").write_text(
            "module x\n\nrequire github.com/gin-gonic/gin v1.9.0\n"
        )
        (tmp_path / "package.json").write_text(
            '{"devDependencies": {"prettier": "^3.0.0"}}'
        )
        (tmp_path / "main.go").write_text("package main\n")
        (tmp_path / "handlers.go").write_text("package main\n")
        fw, lang, _ = detect_framework(str(tmp_path))
        assert (fw, lang) == ("gin", "go")

    def test_single_manifest_behavior_unchanged(self, tmp_path):
        """A lone manifest keeps exact first-match-wins behavior (no file walk
        needed): pom.xml alone → spring-boot even with no source files."""
        (tmp_path / "pom.xml").write_text("<project/>")
        assert detect_framework(str(tmp_path))[:2] == ("spring-boot", "java")

    def test_multi_manifest_no_source_falls_back_to_order(self, tmp_path):
        """When 2+ manifests coexist but there are no code files to vote on, the
        SIGNATURE_MAP priority order (package.json before requirements) decides,
        exactly as before — no crash on an empty language vote."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"express": "^4"}}'
        )
        (tmp_path / "requirements.txt").write_text("flask\n")
        fw, _, _ = detect_framework(str(tmp_path))
        assert fw == "express"

    def test_gemfile_with_colocated_js_frontend_stays_rails(self, tmp_path):
        """A Rails repo with a real, file-heavy colocated JS frontend
        (react-on-rails / jsbundling) must stay rails even when .jsx sources
        outnumber .rb. Gemfile precedes package.json in SIGNATURE_MAP, so the
        order winner is kept and the language vote never fires. Regression: the
        broad tie-break used to flip this to react (backend went invisible)."""
        (tmp_path / "Gemfile").write_text('gem "rails"\n')
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18", "react-dom": "^18"}}'
        )
        (tmp_path / "a.rb").write_text("x = 1\n")
        (tmp_path / "b.rb").write_text("y = 1\n")
        for i in range(5):
            (tmp_path / f"c{i}.jsx").write_text("export const c = () => null\n")
        assert detect_framework(str(tmp_path))[:2] == ("rails", "ruby")

    def test_pom_xml_with_colocated_js_frontend_stays_spring_boot(self, tmp_path):
        """A Spring repo with a colocated, file-heavy frontend
        (frontend-maven-plugin) stays spring-boot even when .tsx sources
        outnumber .java — pom.xml precedes package.json, so order wins."""
        (tmp_path / "pom.xml").write_text("<project/>")
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18", "react-dom": "^18"}}'
        )
        (tmp_path / "A.java").write_text("class A {}\n")
        (tmp_path / "B.java").write_text("class B {}\n")
        for i in range(5):
            (tmp_path / f"c{i}.tsx").write_text("export const c = () => null\n")
        assert detect_framework(str(tmp_path))[:2] == ("spring-boot", "java")

    def test_package_json_first_with_pyproject_js_dominant_stays_node(self, tmp_path):
        """The narrowed tie-break still fires when package.json is the
        highest-priority signature: package.json + a stray pyproject.toml with a
        JS-dominant tree → react/typescript (not python)."""
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"react": "^18", "react-dom": "^18"}}'
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "helper"\ndependencies = ["black"]\n'
        )
        for i in range(5):
            (tmp_path / f"c{i}.tsx").write_text("export const c = () => null\n")
        assert detect_framework(str(tmp_path))[:2] == ("react", "typescript")


# ── G10: duplicate project names ─────────────────────────────────────────────

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestDuplicateProjectNames:
    def test_two_frontend_dirs_get_distinct_names(self, tmp_path):
        """appA/frontend + appB/frontend must not both be named 'frontend'."""
        for app in ("appA", "appB"):
            _write(
                tmp_path / app / "frontend" / "package.json",
                '{"dependencies": {"react": "^18", "react-dom": "^18"}}',
            )
            _write(
                tmp_path / app / "frontend" / "src" / "App.tsx",
                "export const App = () => null\n",
            )
        projects = discover_projects([str(tmp_path)])
        names = [p.name for p in projects]
        assert len(names) == 2
        assert len(set(names)) == 2, f"names collided: {names}"
        assert set(names) == {"appA-frontend", "appB-frontend"}

    def test_unique_names_untouched(self, tmp_path):
        """A workspace with already-distinct dir names is left verbatim."""
        _write(tmp_path / "web" / "package.json",
               '{"dependencies": {"react": "^18", "react-dom": "^18"}}')
        _write(tmp_path / "web" / "src" / "App.tsx", "export const A = () => null\n")
        _write(tmp_path / "api" / "requirements.txt", "flask\n")
        _write(tmp_path / "api" / "app.py", "app = 1\n")
        names = {p.name for p in discover_projects([str(tmp_path)])}
        assert names == {"web", "api"}

    def test_second_order_clash_gets_hash_salt(self, tmp_path):
        """When the parent-dir prefix ALSO collides (x/svc/api + y/svc/api both
        become 'svc-api'), a path hash breaks the residual clash so the final
        names are still unique."""
        for top in ("x", "y"):
            _write(tmp_path / top / "svc" / "api" / "requirements.txt", "flask\n")
            _write(tmp_path / top / "svc" / "api" / "app.py", "app = 1\n")
        # discover_projects only descends 2 levels, so hand the leaf dirs directly.
        leaves = [
            str(tmp_path / "x" / "svc" / "api"),
            str(tmp_path / "y" / "svc" / "api"),
        ]
        names = [p.name for p in discover_projects(leaves)]
        assert len(set(names)) == 2, f"second-order clash not broken: {names}"
        assert all(n.startswith("svc-api-") for n in names), names

    def test_name_has_no_nodeid_or_path_delimiters(self, tmp_path):
        """The disambiguated name becomes a wiki/obsidian folder and node-id
        prefix — it must not contain '/', '::' or '@'."""
        for app in ("appA", "appB"):
            _write(tmp_path / app / "frontend" / "requirements.txt", "flask\n")
            _write(tmp_path / app / "frontend" / "app.py", "app = 1\n")
        for p in discover_projects([str(tmp_path)]):
            assert "/" not in p.name
            assert "::" not in p.name
            assert "@" not in p.name


class TestDuplicateNamesEndToEnd:
    """Full scan → graph → wiki on two same-named projects proves every
    downstream surface separates once discovery makes the name unique."""

    def _build_graph(self, workspace: Path):
        from codebeacon.discover.scanner import collect_files
        from codebeacon.wave import auto_wave
        from codebeacon.graph.build import build_graph

        projects = discover_projects([str(workspace)])
        waves = [
            auto_wave(project=p, files=collect_files(p.path)) for p in projects
        ]
        return projects, build_graph(waves)

    def test_route_nodes_do_not_collapse(self, tmp_path):
        """Two 'api' flask projects, each GET /health, must yield TWO route
        nodes with distinct project attrs — not one silently overwritten."""
        pytest.importorskip("tree_sitter_python")
        for app in ("appA", "appB"):
            _write(tmp_path / app / "api" / "requirements.txt", "flask==3.0.0\n")
            _write(
                tmp_path / app / "api" / "app.py",
                "from flask import Flask\n"
                "app = Flask(__name__)\n\n"
                "@app.route('/health', methods=['GET'])\n"
                "def health():\n"
                "    return {}\n",
            )
        projects, G = self._build_graph(tmp_path)
        assert {p.name for p in projects} == {"appA-api", "appB-api"}
        routes = [
            (nid, d.get("project"))
            for nid, d in G.nodes(data=True)
            if d.get("type") == "route"
        ]
        assert len(routes) == 2, f"route node collapsed: {routes}"
        assert len({proj for _, proj in routes}) == 2

    def test_wiki_folders_separate(self, tmp_path):
        """Two 'frontend' react projects → two distinct wiki folders, so the
        Step-2 'replace {project} with the folder' lookup is navigable again."""
        pytest.importorskip("tree_sitter_typescript")
        from codebeacon.wiki.generator import generate_wiki

        for app in ("appA", "appB"):
            _write(
                tmp_path / app / "frontend" / "package.json",
                '{"dependencies": {"react": "^18", "react-dom": "^18"}}',
            )
            _write(
                tmp_path / app / "frontend" / "src" / "Widget.tsx",
                "import React from 'react';\n"
                "export function Widget() {\n"
                "  const [n] = React.useState(0);\n"
                "  return <div>{n}</div>;\n"
                "}\n",
            )
        projects, G = self._build_graph(tmp_path)
        assert {p.name for p in projects} == {"appA-frontend", "appB-frontend"}

        out = tmp_path / "out"
        generate_wiki(
            G, {}, out, project_roots={p.name: p.path for p in projects}
        )
        wiki = out / "wiki"
        assert (wiki / "appA-frontend").is_dir()
        assert (wiki / "appB-frontend").is_dir()
        assert not (wiki / "frontend").exists(), "folders still merged"


# ── C17: parallel-route @slot stripping ──────────────────────────────────────

class TestParallelRouteSlots:
    APP = Path("/app")

    def _route(self, rel: str) -> str:
        return _app_router_path(self.APP / rel / "page.tsx", self.APP)

    def test_leading_slot_stripped(self):
        assert self._route("@team/settings") == "/settings"

    def test_trailing_slot_stripped(self):
        assert self._route("dashboard/@analytics") == "/dashboard"

    def test_bare_slot_becomes_root(self):
        assert self._route("@team") == "/"

    def test_slot_then_param(self):
        assert self._route("@modal/[id]") == "/:id"

    def test_catch_all_still_correct(self):
        # the @slot strip must not disturb catch-all [...x] → *
        assert self._route("[...slug]") == "/*"

    def test_route_group_still_stripped(self):
        assert self._route("(marketing)/about") == "/about"


# ── G02: case-insensitive extensions ─────────────────────────────────────────

class TestUppercaseExtensions:
    def test_language_vote_counts_uppercase_py(self, tmp_path):
        """A repo whose sources carry uppercase extensions still votes Python."""
        (tmp_path / "Main.PY").write_text("x = 1\n")
        (tmp_path / "Util.Py").write_text("y = 1\n")
        assert _detect_language_from_files(tmp_path) == "python"

    def test_fs_routes_pick_up_uppercase_tsx(self, tmp_path):
        """Next.js pages with an uppercase .TSX suffix still produce a route."""
        pages = tmp_path / "pages"
        pages.mkdir()
        (pages / "About.TSX").write_text("export default () => null\n")
        routes = _fs_routes_from_dir(pages, pages)
        assert "/About" in routes
