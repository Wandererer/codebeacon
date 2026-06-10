"""Regression tests for the graphify-parity audit of upstream Jun 3-10 work.

Each fix mirrors a graphify issue/release that also reproduced in codebeacon:

| # | graphify ref      | codebeacon site                                      |
|---|-------------------|------------------------------------------------------|
| 1 | #1193             | extract/dependencies.py — comment-blind regex passes |
| 2 | #1146             | Python SCM queries + import.item handling            |
| 3 | #1090 (family)    | graph/enrich.py — set-iteration edge order           |
| 4 | #1194 / #1195     | graph/build.py — None-label crash guard              |
| 5 | #1127 / #1161     | export/hooks.py — interpreter pin + portable detach  |
| 6 | 690b4e5 follow-up | export/obsidian.py — uncapped service folder names   |
"""
from __future__ import annotations

import sys
from pathlib import Path

from codebeacon.common.types import Edge, Node


def _targets(edges, relation):
    return [e.target for e in edges if e.relation == relation]


# ── Fix 1 (graphify #1193): commented-out imports must not become edges ─────

class TestJsCommentStripping:
    def test_line_comment_removed(self):
        from codebeacon.extract.dependencies import _strip_js_comments
        out = _strip_js_comments("const a = 1; // export * from './ghost'\nconst b = 2;")
        assert "ghost" not in out
        assert "const b = 2;" in out

    def test_block_comment_removed(self):
        from codebeacon.extract.dependencies import _strip_js_comments
        out = _strip_js_comments("/* const x = require('./ghost') */ const y = 3;")
        assert "ghost" not in out
        assert "const y = 3;" in out

    def test_string_literals_preserved(self):
        from codebeacon.extract.dependencies import _strip_js_comments
        src = "const url = 'http://example.com/a'; const t = `tpl // not comment`;"
        assert _strip_js_comments(src) == src

    def test_escaped_quote_inside_string(self):
        from codebeacon.extract.dependencies import _strip_js_comments
        src = "const s = 'it\\'s // fine'; const z = 1;"
        assert _strip_js_comments(src) == src

    def test_commented_reexport_and_require_produce_no_edges(self, tmp_path):
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "barrel.ts"
        f.write_text(
            "// export * from './ghost'\n"
            "/* const legacy = require('./ghost2') */\n"
            "export * from './real';\n"
            "const live = require('./real2');\n",
            encoding="utf-8",
        )
        edges = extract_dependencies(str(f), framework="react")
        assert _targets(edges, "re_exports") == ["./real"]
        assert "./real2" in _targets(edges, "imports_from")
        all_targets = {e.target for e in edges}
        assert "./ghost" not in all_targets
        assert "./ghost2" not in all_targets


# ── Fix 2 (graphify #1146): `from pkg import name` binds the real target ────

class TestPythonNamedImportResolution:
    def test_imported_symbol_emitted_as_dotted_target(self, tmp_path):
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "consumer.py"
        f.write_text(
            "from auth.services import UserService\n"
            "from src.services import ai_blog_enricher\n",
            encoding="utf-8",
        )
        targets = _targets(extract_dependencies(str(f), framework="fastapi"), "imports_from")
        # Module-path edges are kept...
        assert "auth.services" in targets
        # ...and the imported names now resolve to their own dotted targets.
        assert "auth.services.UserService" in targets
        assert "src.services.ai_blog_enricher" in targets

    def test_alias_resolves_to_real_name(self, tmp_path):
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "consumer.py"
        f.write_text("from pkg.mod import helper as h\n", encoding="utf-8")
        targets = _targets(extract_dependencies(str(f), framework="fastapi"), "imports_from")
        # The symbol is `helper`; the local alias `h` must not be the target.
        assert "pkg.mod.helper" in targets
        assert "pkg.mod.h" not in targets

    def test_wildcard_import_still_yields_module_edge(self, tmp_path):
        from codebeacon.extract.dependencies import extract_dependencies
        f = tmp_path / "consumer.py"
        f.write_text("from pkg.mod import *\n", encoding="utf-8")
        targets = _targets(extract_dependencies(str(f), framework="fastapi"), "imports_from")
        assert "pkg.mod" in targets

    def test_dotted_target_remaps_to_class_node(self):
        from codebeacon.graph.build import _remap_import_edges
        nodes = [
            Node(id="app::UserService", label="UserService", type="class",
                 source_file="auth/services/user_service.py", line=1, metadata={}),
            Node(id="app::Consumer", label="Consumer", type="class",
                 source_file="api/consumer.py", line=1, metadata={}),
        ]
        edges = [Edge(source="api/consumer.py", target="auth.services.UserService",
                      relation="imports_from", confidence="EXTRACTED",
                      confidence_score=1.0, source_file="api/consumer.py")]
        remapped = _remap_import_edges(nodes, edges)
        assert any(e.source == "app::Consumer" and e.target == "app::UserService"
                   for e in remapped)


# ── Fix 3 (graphify #1090 family): deterministic enrichment edge order ──────

class TestEnrichDeterminism:
    def test_api_urls_sorted(self, tmp_path):
        from codebeacon.graph.enrich import _extract_api_urls
        f = tmp_path / "client.ts"
        f.write_text(
            'fetch("/api/zebra");\nfetch("/api/alpha");\nfetch("/api/mango");\n',
            encoding="utf-8",
        )
        urls = _extract_api_urls(str(f))
        assert urls == sorted(urls)
        assert urls == ["/api/alpha", "/api/mango", "/api/zebra"]

    def test_ipc_commands_sorted(self, tmp_path):
        from codebeacon.graph.enrich import _extract_ipc_commands
        f = tmp_path / "front.ts"
        f.write_text('invoke("zz_cmd"); invoke("aa_cmd"); invoke("mm_cmd");',
                      encoding="utf-8")
        cmds = _extract_ipc_commands(str(f))
        assert cmds == ["aa_cmd", "mm_cmd", "zz_cmd"]


# ── Fix 4 (graphify #1194): None node label must not abort the build ────────

class TestNoneLabelGuard:
    def test_remap_survives_none_label(self):
        from codebeacon.graph.build import _remap_import_edges
        nodes = [
            Node(id="app::Broken", label=None, type="class",  # type: ignore[arg-type]
                 source_file="a/broken.py", line=1, metadata={}),
            Node(id="app::Card", label="Card", type="component",
                 source_file="ui/card.tsx", line=1, metadata={}),
            Node(id="app::Page", label="Page", type="component",
                 source_file="ui/page.tsx", line=1, metadata={}),
        ]
        edges = [Edge(source="ui/page.tsx", target="@/components/ui/card",
                      relation="imports_from", confidence="EXTRACTED",
                      confidence_score=1.0, source_file="ui/page.tsx")]
        # Must not raise, and healthy nodes must still resolve.
        remapped = _remap_import_edges(nodes, edges)
        assert any(e.source == "app::Page" and e.target == "app::Card"
                   for e in remapped)


# ── Fix 5 (graphify #1127/#1161): hook works off-PATH, no nohup primary ─────

class TestHookInterpreterPin:
    def _hook(self) -> str:
        from codebeacon.export.hooks import _render_post_commit_hook
        return _render_post_commit_hook()

    def test_hook_pins_current_interpreter(self):
        assert Path(sys.executable).as_posix() in self._hook()

    def test_hook_invokes_module_not_path_launcher(self):
        h = self._hook()
        assert '"-m", "codebeacon"' in h
        assert "CODEBEACON_PY" in h  # heredoc detach block present

    def test_hook_detach_is_cross_platform(self):
        h = self._hook()
        assert "start_new_session" in h
        assert "creationflags" in h  # Windows DETACHED_PROCESS branch

    def test_install_refreshes_stale_codebeacon_hook(self, tmp_path, monkeypatch):
        from codebeacon.export import hooks as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        stale = hooks_dir / "post-commit"
        stale.write_text(
            "#!/usr/bin/env bash\n"
            "# codebeacon: incremental rebuild after each commit.\n"
            "nohup codebeacon scan . --update &\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(hooks_mod, "_hooks_dir", lambda repo: hooks_dir)
        hooks_mod._install_post_commit(tmp_path)
        refreshed = stale.read_text(encoding="utf-8")
        assert "CODEBEACON_PYTHON=" in refreshed

    def test_install_preserves_user_hook_mentioning_codebeacon(self, tmp_path, monkeypatch):
        from codebeacon.export import hooks as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        custom = hooks_dir / "post-commit"
        original = "#!/bin/sh\n# my custom hook, also runs codebeacon sometimes\nmake lint\n"
        custom.write_text(original, encoding="utf-8")
        monkeypatch.setattr(hooks_mod, "_hooks_dir", lambda repo: hooks_dir)
        hooks_mod._install_post_commit(tmp_path)
        assert custom.read_text(encoding="utf-8") == original


# ── Fix 6 (690b4e5 follow-up): service folder / hub note names capped ───────

class TestObsidianServiceFolderCap:
    def test_long_community_name_capped_and_hub_writes(self, tmp_path):
        from codebeacon.export.obsidian import _step8_move_remaining, _step9_hub_notes
        vault = tmp_path / "vault"
        vault.mkdir()
        long_name = "서비스" * 100  # 900 UTF-8 bytes — over any filesystem limit
        note = vault / "node.md"
        note.write_text(
            "---\n"
            "type: 'class'\n"
            f"community: '{long_name}'\n"
            "---\n"
            "body\n",
            encoding="utf-8",
        )
        _step8_move_remaining(vault)  # must not raise ENAMETOOLONG
        dirs = [d for d in vault.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        assert len(dirs[0].name.encode("utf-8")) <= 255
        _step9_hub_notes(vault)  # hub note `<svc>/<svc>.md` must also fit
        hub = dirs[0] / f"{dirs[0].name}.md"
        assert hub.exists()
