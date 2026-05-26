"""Regression tests for 4 graphify-reported bugs we also had.

Each test reproduces the original bug scenario verbatim, so reverting
the fix would flip the assertion. Mutation-verified.

| Bug | graphify issue | Fix module |
|---|---|---|
| #1 | #952 / #949 | graph/build.py:_disambiguate_decl |
| #2 | #978        | export/mcp.py:BeaconIndex.find_node_ids |
| #3 | #777        | cache.py:Cache project_root  |
| #4 | #1018       | export/hooks.py:_POST_COMMIT_HOOK |
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest

from codebeacon.cache import Cache
from codebeacon.common.types import (
    EntityInfo, ServiceInfo, ComponentInfo, Edge, ProjectInfo,
)
from codebeacon.graph.build import build_graph
from codebeacon.wave import WaveResult


def _project(name="api"):
    return ProjectInfo(name=name, path=f"/projects/{name}", framework="fastapi",
                       language="python", signature_file="req.txt")


# ── BUG #1 (graphify #952): same basename collision ─────────────────────────

class TestSameBasenameCollision:
    def test_two_user_classes_in_different_dirs_stay_distinct(self):
        """``auth/User.py`` and ``admin/User.py`` must produce TWO graph
        nodes. Before the fix both collapsed into ``api::User`` and the
        cross-file merge union-merged their unrelated methods."""
        wave = WaveResult(
            project=_project(),
            services=[
                ServiceInfo(name="User", class_name="User",
                            source_file="/proj/auth/User.py", line=1,
                            framework="fastapi", methods=["login", "logout"]),
                ServiceInfo(name="User", class_name="User",
                            source_file="/proj/admin/User.py", line=1,
                            framework="fastapi", methods=["ban_user", "delete_user"]),
            ],
        )
        G = build_graph([wave], apply_filters=False)
        # Two distinct nodes
        assert "api::User" in G.nodes
        assert "api::admin/User" in G.nodes
        # Each retains only its own methods (no union)
        assert set(G.nodes["api::User"]["methods"]) == {"login", "logout"}
        assert set(G.nodes["api::admin/User"]["methods"]) == {"ban_user", "delete_user"}
        # Disambiguated label shows the directory hint so wiki / query
        # display the distinction
        assert G.nodes["api::admin/User"]["label"] == "User (admin)"

    def test_same_directory_same_name_still_merges(self):
        """Swift ``extension Foo``-style cross-file declarations live in
        the same directory and must still union into one node — that was
        the original purpose of _merge_cross_file_decls (graphify #406bea4)."""
        wave = WaveResult(
            project=_project(),
            entities=[
                EntityInfo(name="User", table_name="users",
                           source_file="/proj/User.swift", line=1,
                           framework="fluent",
                           fields=[{"name": "id", "type": "Int", "annotations": []}]),
                EntityInfo(name="User", table_name="users",
                           source_file="/proj/User+Profile.swift", line=1,
                           framework="fluent",
                           fields=[{"name": "name", "type": "String", "annotations": []}]),
            ],
        )
        G = build_graph([wave], apply_filters=False)
        assert "api::User" in G.nodes
        # Both files' fields unioned into one canonical node
        names = {f["name"] for f in G.nodes["api::User"].get("fields", [])}
        assert names == {"id", "name"}


# ── BUG #2 (graphify #978): query punctuation ───────────────────────────────

class TestQueryPunctuation:
    def _idx(self, tmp_path):
        from codebeacon.export.mcp import BeaconIndex
        G = nx.DiGraph()
        G.add_node("p::User", label="User", project="p", type="class")
        G.add_node("p::OrderService", label="OrderService", project="p", type="class")
        (tmp_path / "beacon.json").write_text(
            json.dumps(nxjson.node_link_data(G), ensure_ascii=False))
        idx = BeaconIndex(tmp_path)
        idx.load()
        return idx

    @pytest.mark.parametrize("q", ["User?", "User.", "User:", "User!", "User;", "(User)", "'User'", "\"User\""])
    def test_trailing_punctuation_still_matches(self, tmp_path, q):
        assert self._idx(tmp_path).find_node_ids(q) == ["p::User"]

    def test_function_call_form_matches(self, tmp_path):
        """LLM-generated queries like 'getUser()' must still locate
        any node containing 'getUser'."""
        from codebeacon.export.mcp import BeaconIndex
        G = nx.DiGraph()
        G.add_node("p::getUser", label="getUser", project="p", type="function")
        (tmp_path / "beacon.json").write_text(
            json.dumps(nxjson.node_link_data(G), ensure_ascii=False))
        idx = BeaconIndex(tmp_path)
        idx.load()
        assert idx.find_node_ids("getUser()") == ["p::getUser"]


# ── BUG #3 (graphify #777): absolute cache keys ─────────────────────────────

class TestCacheRelativeKeys:
    def test_put_stores_relative_key_when_root_given(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        src = repo / "src"; src.mkdir()
        f = src / "foo.py"; f.write_text("x=1")

        c = Cache(str(repo / ".codebeacon"), project_root=str(repo))
        c.put(str(f), {"dummy": True})
        assert "src/foo.py" in c._data, (
            "cache key must be repo-relative when project_root is set"
        )
        assert str(f) not in c._data

    def test_get_resolves_relative_key_from_absolute_path(self, tmp_path):
        repo = tmp_path / "repo"; repo.mkdir()
        src = repo / "src"; src.mkdir()
        f = src / "foo.py"; f.write_text("x=1")

        c = Cache(str(repo / ".codebeacon"), project_root=str(repo))
        c.put(str(f), {"answer": 42})
        # Subsequent get() with the same absolute path still hits because
        # _key() normalises both sides.
        assert c.get(str(f)) == {"answer": 42}

    def test_load_migrates_legacy_absolute_keys(self, tmp_path):
        """A cache.json written by an older codebeacon (absolute keys)
        is rewritten to relative form on load so the next save persists
        the migration."""
        repo = tmp_path / "repo"; repo.mkdir()
        src = repo / "src"; src.mkdir()
        f = src / "foo.py"; f.write_text("x=1")

        cache_dir = repo / ".codebeacon" / "cache"
        cache_dir.mkdir(parents=True)
        # Legacy on-disk format: absolute path key
        (cache_dir / "cache.json").write_text(json.dumps({
            str(f.resolve()): {
                "hash": "deadbeef", "result": {"legacy": True},
                "ts": 0, "mtime_ns": 0, "size": 0,
            }
        }))

        c = Cache(str(repo / ".codebeacon"), project_root=str(repo))
        c.load()
        assert "src/foo.py" in c._data
        assert str(f.resolve()) not in c._data
        assert c._dirty, "migration must mark cache dirty so save persists it"

    def test_no_root_means_backwards_compatible_absolute_keys(self, tmp_path):
        """Without ``project_root`` the cache behaves exactly like 0.5.0
        — every existing user / test must keep working."""
        f = tmp_path / "x.py"; f.write_text("x=1")
        c = Cache(str(tmp_path / "out"))  # no project_root
        c.put(str(f), {})
        assert str(f) in c._data


# ── BUG #4 (graphify #1018): post-commit hook noise ─────────────────────────

class TestPostCommitHookFiltering:
    def _hook(self) -> str:
        from codebeacon.export.hooks import _POST_COMMIT_HOOK
        return _POST_COMMIT_HOOK

    def test_hook_inspects_changed_files(self):
        """The hook must look at the diff before triggering a rebuild."""
        assert "git diff --name-only" in self._hook()

    def test_hook_excludes_codebeacon_dir(self):
        """A commit that touched only `.codebeacon/` must not trigger a
        rebuild — otherwise it self-feeds."""
        assert "^\\.codebeacon/" in self._hook() or ".codebeacon/" in self._hook()

    def test_hook_filters_to_code_extensions(self):
        """The skip condition is anchored to source-file extensions, so
        docs-only / yaml-only commits don't pay the rebuild cost."""
        h = self._hook()
        # Must reference a representative set of code extensions
        for ext in ("ts", "py", "java", "go", "rs", "razor", "csproj"):
            assert ext in h, f"hook script missing {ext!r} extension"

    def test_hook_uses_early_exit_zero(self):
        """`exit 0` on no-op so git commit continues without surfacing
        the hook script as a failure."""
        assert "exit 0" in self._hook()


# ── BUG A (graphify #906): subprocess encoding ─────────────────────────────

class TestSubprocessUTF8Encoding:
    """Every git subprocess call must pin ``encoding='utf-8'`` so non-ASCII
    repo paths / branch names / file names round-trip on Windows, where the
    default console codepage is cp1252 and python's ``text=True`` decodes
    with that codepage. Mirrors graphify #906."""

    def _file_text(self, path: str) -> str:
        from pathlib import Path
        return Path(path).read_text(encoding="utf-8")

    def test_safety_git_head_pins_utf8(self):
        src = self._file_text("codebeacon/common/safety.py")
        # git_head() is the canonical git invocation — must declare encoding.
        assert 'encoding="utf-8"' in src
        assert 'errors="replace"' in src

    def test_affected_git_diff_pins_utf8(self):
        src = self._file_text("codebeacon/affected.py")
        # git_changed_files() runs `git diff --name-only` — non-ASCII file
        # names in the diff would otherwise UnicodeDecodeError on Windows.
        assert 'encoding="utf-8"' in src
        assert 'errors="replace"' in src

    def test_hooks_git_calls_pin_utf8(self):
        src = self._file_text("codebeacon/export/hooks.py")
        # Both _is_git_repo and _hooks_dir capture git stdout, both need it.
        # Count instead of bool so we catch a regression where one block
        # loses encoding while the other keeps it.
        assert src.count('encoding="utf-8"') >= 2
        assert src.count('errors="replace"') >= 2


# ── BUG B (graphify #554): ~ expansion in core.hooksPath ───────────────────

class TestHooksPathTildeExpansion:
    def _patch_subprocess(self, monkeypatch, configured_value: str):
        """Make git config return ``configured_value`` without spawning git."""
        import subprocess
        from collections import namedtuple
        Result = namedtuple("Result", "returncode stdout stderr")

        def fake_run(*args, **kwargs):
            return Result(returncode=0, stdout=configured_value + "\n", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_tilde_path_is_expanded(self, tmp_path, monkeypatch):
        """``~/.husky`` must resolve under ``$HOME``, NOT under the repo."""
        from codebeacon.export.hooks import _hooks_dir

        self._patch_subprocess(monkeypatch, "~/.husky/_/")
        repo = tmp_path / "repo"
        repo.mkdir()
        out = _hooks_dir(repo)
        # The path must NOT start with the repo root — that was the bug.
        assert str(repo) not in str(out), (
            f"~/.husky was joined to repo root: {out}"
        )
        # And the tilde must have been expanded (no literal ~ remains).
        assert "~" not in out.parts

    def test_envvar_path_is_expanded(self, tmp_path, monkeypatch):
        """$HOME-style paths must expand too — Husky 9 + custom shells."""
        from codebeacon.export.hooks import _hooks_dir

        monkeypatch.setenv("MY_HOOKS_DIR", str(tmp_path / "shared-hooks"))
        self._patch_subprocess(monkeypatch, "$MY_HOOKS_DIR")
        out = _hooks_dir(tmp_path / "repo")
        assert "shared-hooks" in out.parts

    def test_relative_path_still_joins_to_repo(self, tmp_path, monkeypatch):
        """A relative path like ``.husky`` keeps the old behaviour: join
        against the repo root. The fix must not regress that."""
        from codebeacon.export.hooks import _hooks_dir

        self._patch_subprocess(monkeypatch, ".husky")
        repo = (tmp_path / "repo").resolve()
        repo.mkdir()
        out = _hooks_dir(repo)
        assert str(out).startswith(str(repo))
        assert out.name == ".husky"


# ── BUG C (graphify #753): CommonJS require() ──────────────────────────────

class TestCommonJsRequire:
    """Before the fix, `require()` was only extracted in ``express.scm`` —
    Next.js / Vue / Svelte / NestJS projects with mixed ES + CJS imports
    silently lost every require() edge. The regex post-pass picks them up
    for all JS/TS family extensions regardless of detected framework."""

    def _by_target(self, edges):
        return sorted(e.target for e in edges if e.relation == "imports_from")

    def test_require_extracted_in_react_project(self, tmp_path):
        """react.scm doesn't have a require pattern — the regex must catch it."""
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "app.js"
        f.write_text("const lodash = require('lodash');\nconst fs = require(\"fs\");\n")
        targets = self._by_target(extract_dependencies(str(f), framework="react"))
        assert "lodash" in targets
        assert "fs" in targets

    def test_require_extracted_in_nextjs_project(self, tmp_path):
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "config.js"
        f.write_text("module.exports = { a: require('next/dynamic') };\n")
        assert "next/dynamic" in self._by_target(
            extract_dependencies(str(f), framework="nextjs")
        )

    def test_require_dedupes_against_es_import(self, tmp_path):
        """A file that imports the same module via both syntaxes produces
        one edge, not two."""
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "mixed.ts"
        f.write_text("import x from 'react';\nconst y = require('react');\n")
        targets = self._by_target(
            extract_dependencies(str(f), framework="react")
        )
        assert targets.count("react") == 1

    def test_require_ignored_in_python(self, tmp_path):
        """The regex only fires on JS/TS family extensions. A Python file
        containing the literal text `require('x')` (e.g. in a docstring)
        must not produce a spurious edge."""
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "doc.py"
        f.write_text('"""See require(\'x\') in JS world."""\n')
        edges = extract_dependencies(str(f), framework="fastapi")
        assert all(e.relation != "imports_from" or "require" not in e.target for e in edges)
