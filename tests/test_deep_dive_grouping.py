"""Deep-dive outputs land at exactly two levels: group roots + workspace root.

A "group root" is the repo boundary (`.git` / `codebeacon.yaml`) that owns a
detected project. Framework folders inside a monorepo (mono/landing,
mono/server) must NOT each get a `.codebeacon/` + CLAUDE.md — their content
belongs in mono's root output, and the workspace root carries everything.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from codebeacon.common.types import ProjectInfo
from codebeacon.pipeline import _group_projects, _project_group_root


def _proj(path: Path, name: str | None = None, framework: str = "fastapi") -> ProjectInfo:
    return ProjectInfo(
        name=name or path.name,
        path=str(path),
        framework=framework,
        language="python",
        signature_file="pyproject.toml",
    )


# ── _project_group_root ──────────────────────────────────────────────────────

class TestProjectGroupRoot:
    def test_monorepo_subfolder_resolves_to_repo_root(self, tmp_path):
        ws = tmp_path
        mono = ws / "mono"
        (mono / ".git").mkdir(parents=True)
        landing = mono / "landing"
        landing.mkdir()
        assert _project_group_root(landing, ws) == mono.resolve()

    def test_codebeacon_yaml_marks_boundary_too(self, tmp_path):
        ws = tmp_path
        mono = ws / "mono"
        mono.mkdir()
        (mono / "codebeacon.yaml").write_text("version: 1\n", encoding="utf-8")
        server = mono / "apps" / "server"
        server.mkdir(parents=True)
        assert _project_group_root(server, ws) == mono.resolve()

    def test_outermost_boundary_wins(self, tmp_path):
        # mono has .git AND mono/landing has its own .git (vendored repo):
        # the group is still mono — outputs belong at the outermost repo root.
        ws = tmp_path
        mono = ws / "mono"
        (mono / ".git").mkdir(parents=True)
        landing = mono / "landing"
        (landing / ".git").mkdir(parents=True)
        assert _project_group_root(landing, ws) == mono.resolve()

    def test_standalone_project_is_its_own_group(self, tmp_path):
        ws = tmp_path
        solo = ws / "solo"
        (solo / ".git").mkdir(parents=True)
        assert _project_group_root(solo, ws) == solo.resolve()

    def test_no_boundary_falls_back_to_project_itself(self, tmp_path):
        # Template collections: ws/templates/express-html with no .git anywhere
        # below ws — each detected folder stays its own group.
        ws = tmp_path
        proj = ws / "templates" / "express-html"
        proj.mkdir(parents=True)
        assert _project_group_root(proj, ws) == proj.resolve()

    def test_project_at_workspace_root(self, tmp_path):
        assert _project_group_root(tmp_path, tmp_path) == tmp_path.resolve()


# ── _group_projects ──────────────────────────────────────────────────────────

class TestGroupProjects:
    def test_groups_monorepo_members_and_preserves_order(self, tmp_path):
        ws = tmp_path
        mono = ws / "mono"
        (mono / ".git").mkdir(parents=True)
        landing = mono / "landing"; landing.mkdir()
        server = mono / "server"; server.mkdir()
        solo = ws / "solo"
        (solo / ".git").mkdir(parents=True)

        projects = [_proj(landing), _proj(solo), _proj(server)]
        grouped = _group_projects(projects, ws)

        roots = [root for root, _ in grouped]
        assert roots == [mono.resolve(), solo.resolve()]
        mono_members = dict(grouped)[mono.resolve()]
        assert [p.name for p in mono_members] == ["landing", "server"]


# ── Shared group cache: framework-namespaced keys ────────────────────────────

class TestCacheFrameworkNamespace:
    def test_same_file_different_framework_is_a_miss(self, tmp_path):
        """A monorepo group shares one cache. desktop (sveltekit) walks over
        desktop/src-tauri first and caches its (empty) view of the Rust files;
        the src-tauri (tauri) project must NOT reuse those entries."""
        from codebeacon.cache import Cache
        f = tmp_path / "main.rs"
        f.write_text("fn main() {}\n", encoding="utf-8")
        cache = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        cache.put(str(f), {"routes": []}, framework="sveltekit")
        assert cache.get(str(f), framework="sveltekit") is not None
        assert cache.get(str(f), framework="tauri") is None
        cache.put(str(f), {"routes": [{"path": "/x"}]}, framework="tauri")
        assert cache.get(str(f), framework="tauri")["routes"]

    def test_invalidate_clears_all_namespaces(self, tmp_path):
        from codebeacon.cache import Cache
        f = tmp_path / "a.ts"
        f.write_text("export const x = 1\n", encoding="utf-8")
        cache = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        cache.put(str(f), {"routes": []}, framework="sveltekit")
        cache.put(str(f), {"routes": []}, framework="tauri")
        cache.invalidate(str(f))
        assert cache.get(str(f), framework="sveltekit") is None
        assert cache.get(str(f), framework="tauri") is None


# ── Grammar load race: one Language instance per grammar ────────────────────

class TestGrammarLoadThreadSafety:
    def test_concurrent_first_load_yields_single_instance(self, monkeypatch):
        """Two wave workers hitting an uncached grammar must get THE SAME
        Language object. Duplicate instances make is_grammar_allowed()'s
        identity check fail for the loser thread's files, which then extract
        to [] with no warning — files randomly lose all their routes."""
        import time
        from concurrent.futures import ThreadPoolExecutor
        import tree_sitter_python
        from codebeacon.extract import base

        monkeypatch.delitem(base._LANG_CACHE, "python", raising=False)
        orig = tree_sitter_python.language

        def slow_language(*a, **k):
            time.sleep(0.05)  # hold the race window open
            return orig(*a, **k)

        monkeypatch.setattr(tree_sitter_python, "language", slow_language)
        with ThreadPoolExecutor(max_workers=8) as pool:
            langs = list(pool.map(lambda _: base.get_language("python"), range(8)))

        assert all(lang is langs[0] for lang in langs)
        assert base._LANG_CACHE["python"] is langs[0]
        # And the identity-based gate accepts the shared instance.
        assert base.is_grammar_allowed("fastapi", langs[0])


# ── End-to-end: where outputs land ───────────────────────────────────────────

class TestDeepDiveOutputPlacement:
    def _make_workspace(self, ws: Path):
        """mono repo (landing + server) and a standalone repo, plus files."""
        mono = ws / "mono"
        (mono / ".git").mkdir(parents=True)
        landing = mono / "landing"; landing.mkdir()
        (landing / "app.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.get('/landing')\ndef landing_home():\n    return {}\n",
            encoding="utf-8",
        )
        server = mono / "server"; server.mkdir()
        (server / "api.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.get('/server')\ndef server_home():\n    return {}\n",
            encoding="utf-8",
        )
        solo = ws / "solo"
        (solo / ".git").mkdir(parents=True)
        (solo / "main.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.get('/solo')\ndef solo_home():\n    return {}\n",
            encoding="utf-8",
        )
        return mono, landing, server, solo

    def test_outputs_only_at_group_roots_and_workspace_root(self, tmp_path):
        from codebeacon.pipeline import run_deep_dive_pipeline
        ws = tmp_path
        mono, landing, server, solo = self._make_workspace(ws)
        projects = [
            _proj(landing), _proj(server), _proj(solo),
        ]
        args = Namespace(
            wiki_only=False, obsidian_dir=None, update=False,
            semantic=False, exclude=[], max_failure_rate=1.0,
        )
        rc = run_deep_dive_pipeline(projects, str(ws / ".codebeacon"), args)
        assert rc == 0

        # Outputs exist at the two sanctioned levels...
        assert (ws / ".codebeacon" / "beacon.json").exists()
        assert (mono / ".codebeacon" / "beacon.json").exists()
        assert (solo / ".codebeacon" / "beacon.json").exists()
        # ...and nowhere inside a group's subfolders.
        assert not (landing / ".codebeacon").exists()
        assert not (server / ".codebeacon").exists()
        assert not (landing / "CLAUDE.md").exists()
        assert not (server / "CLAUDE.md").exists()

        # The mono root graph contains BOTH sub-projects' content.
        import json
        data = json.loads((mono / ".codebeacon" / "beacon.json").read_text(encoding="utf-8"))
        labels = {n.get("label", "") for n in data["nodes"]}
        assert any("landing" in lb for lb in labels)
        assert any("server" in lb for lb in labels)

    def test_workspace_root_group_is_left_to_phase3(self, tmp_path):
        """Deep-dive run INSIDE a monorepo: every project groups to the scan
        root itself, so only the root output is written (no duplicate pass)."""
        from codebeacon.pipeline import run_deep_dive_pipeline
        ws = tmp_path
        (ws / ".git").mkdir()
        landing = ws / "landing"; landing.mkdir()
        (landing / "app.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.get('/l')\ndef l():\n    return {}\n",
            encoding="utf-8",
        )
        server = ws / "server"; server.mkdir()
        (server / "api.py").write_text(
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.get('/s')\ndef s():\n    return {}\n",
            encoding="utf-8",
        )
        projects = [_proj(landing), _proj(server)]
        args = Namespace(
            wiki_only=False, obsidian_dir=None, update=False,
            semantic=False, exclude=[], max_failure_rate=1.0,
        )
        rc = run_deep_dive_pipeline(projects, str(ws / ".codebeacon"), args)
        assert rc == 0
        assert (ws / ".codebeacon" / "beacon.json").exists()
        assert not (landing / ".codebeacon").exists()
        assert not (server / ".codebeacon").exists()
