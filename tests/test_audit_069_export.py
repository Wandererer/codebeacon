"""Regression tests for the 0.6.9 export audit (group F-E).

Each class pins one confirmed-and-reproduced bug in the Obsidian / call-flow-HTML
/ git-hook exporters:

  C09    — Obsidian note filenames must not carry Windows-illegal chars
           (< > : " ? *) that idiomatic Flask/Express route labels embed, and
           must not equal a Windows reserved device name (CON/PRN/AUX/…).
  G06    — call-flow HTML and the Obsidian exporter must tolerate an explicit
           None label / type / source_file (build.py keeps such nodes) instead
           of passing None into html.escape / re.sub.
  BH-O1  — step 5's service-folder mkdir must cap the folder name like step 8,
           or a long/multi-byte project name crashes the whole export.
  BH-O2  — step 9's hub note must not overwrite a real extracted note whose
           label equals its own service/project name.
  BH-O3  — the post-commit hook must be written LF-only so Windows newline
           translation can't corrupt its shebang + heredoc terminator.
"""
from __future__ import annotations

from pathlib import Path

import networkx as nx

from codebeacon.export.callflow_html import write_callflow_html
from codebeacon.export.obsidian import (
    _safe_note_name,
    _step5_move_to_subfolders,
    generate_obsidian_vault,
)


# Windows-illegal characters per Win32: < > : " / \ | ? *
_WIN_ILLEGAL = set('<>:"/\\|?*')


def _route_label(handler: str, method: str, path: str) -> str:
    # Exactly as codebeacon/graph/build.py builds a route node label.
    return f"{handler} [{method} {path}]"


# ── C09: no Windows-illegal chars / reserved device names in note filenames ──

class TestSafeNoteNameWindowsSafe:
    def test_flask_typed_converter_leaves_no_illegal_chars(self):
        # <string:id>, <int:id>, <path:x> are the standard Flask/Werkzeug
        # converter syntax — full of < > :.
        for path in ("/jobs/<string:job-id>", "/users/<int:id>", "/f/<path:x>"):
            stem = _safe_note_name(_route_label("h", "GET", path))
            assert not (_WIN_ILLEGAL & set(stem)), (path, stem)

    def test_express_wildcard_query_quote_leave_no_illegal_chars(self):
        cases = [
            _route_label("getItem", "GET", "/items/:id"),       # Express `:id`
            _route_label("catchAll", "GET", "/files/*"),         # wildcard
            _route_label("search", "GET", "/search?q=term"),     # query `?`
            _route_label("weird", "POST", '/a/"quoted"/b'),      # quote `"`
        ]
        for label in cases:
            stem = _safe_note_name(label)
            assert not (_WIN_ILLEGAL & set(stem)), (label, stem)

    def test_existing_wikilink_strips_still_applied(self):
        # The pre-existing / \ # ^ | [ ] strips must not regress.
        stem = _safe_note_name(r'a/b\c#d^e|f[g]h')
        assert not (set(r'/\#^|[]') & set(stem))

    def test_reserved_device_names_fall_back_to_unnamed(self):
        for name in ("CON", "con", "PRN", "aux", "NUL", "COM1", "com9", "LPT1", "lpt9"):
            assert _safe_note_name(name) == "unnamed", name

    def test_reserved_lookalikes_are_kept(self):
        # Only an *exact* bare-stem match is reserved; CONFIG / COM10 / AUXX are fine.
        for name in ("CONFIG", "COM10", "AUXX", "LPT10", "Console"):
            assert _safe_note_name(name) == name, name

    def test_route_note_filename_and_wikilink_stay_consistent(self, tmp_path: Path):
        # Both the note filename and every wikilink target are produced by
        # _safe_note_name, so a caller (the class calling the route) links to
        # exactly the file that was written — even for an illegal-char label.
        route_label = _route_label("get_job", "GET", "/jobs/<string:job-id>")
        G = nx.DiGraph()
        G.add_node("proj::Ctrl", type="class", label="JobController", project="proj",
                   source_file="/r/Ctrl.java", methods=[], dependencies=[], annotations=[])
        G.add_node("proj::route", type="route", label=route_label, project="proj",
                   source_file="/r/routes.py", method="GET", path="/jobs/<string:job-id>",
                   framework="flask", tags=[])
        G.add_edge("proj::Ctrl", "proj::route", relation="calls", confidence="EXTRACTED")
        communities = {"proj::Ctrl": 0, "proj::route": 0}

        generate_obsidian_vault(G, communities, tmp_path)
        vault = tmp_path / "obsidian"

        route_files = [p for p in vault.rglob("*.md") if "get_job" in p.stem]
        assert route_files, "route note was not written"
        route_stem = route_files[0].stem
        assert not (_WIN_ILLEGAL & set(route_stem)), route_stem

        # The controller note must link to that exact stem (possibly svc-qualified).
        ctrl = [p for p in vault.rglob("*.md") if p.stem == "JobController"][0]
        assert route_stem in ctrl.read_text(encoding="utf-8")


# ── G06: None-tolerance in call-flow HTML and Obsidian ──────────────────────

class TestNoneToleranceExporters:
    def _none_graph(self) -> nx.DiGraph:
        G = nx.DiGraph()
        # A normal node so a community with >= 2 members actually renders.
        G.add_node("proj::A", label="A", type="class", source_file="/r/a.py",
                   project="proj", framework="x", community=0,
                   annotations=[], methods=[], dependencies=[])
        # Explicit None label / type / source_file — all tolerated by build.py.
        G.add_node("proj::B", label=None, type=None, source_file=None,
                   project="proj", framework="x", community=0,
                   annotations=[], methods=[], dependencies=[])
        G.add_edge("proj::A", "proj::B", relation="calls", confidence="EXTRACTED")
        return G

    def test_callflow_html_tolerates_none_type_and_source_file(self, tmp_path: Path):
        # Would previously crash: html.escape(None) from the row builder because
        # dict.get(key, "") does not default on an *explicit* None value.
        out = write_callflow_html(self._none_graph(), tmp_path)
        page = out.read_text(encoding="utf-8")
        # None coerces to empty, never the literal "None" text in a cell.
        assert "<td>None</td>" not in page
        assert "<code>None</code>" not in page

    def test_safe_note_name_none_returns_unnamed(self):
        assert _safe_note_name(None) == "unnamed"
        assert _safe_note_name("") == "unnamed"

    def test_obsidian_tolerates_none_label(self, tmp_path: Path):
        # Would previously crash in _safe_note_name(None) / _type_display(None).
        communities = {"proj::A": 0, "proj::B": 0}
        total = generate_obsidian_vault(self._none_graph(), communities, tmp_path)
        assert total >= 2
        # The None-label node still produced a note (named from its node_id).
        stems = {p.stem for p in (tmp_path / "obsidian").rglob("*.md")}
        assert any("proj" in s and "B" in s for s in stems)


# ── BH-O1: step 5 caps the service-folder name ──────────────────────────────

class TestStep5CapsFolderName:
    def test_step5_does_not_crash_on_long_community(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        long_name = "서비스" * 100  # 900 UTF-8 bytes — over any filesystem limit
        note = vault / "node.md"
        note.write_text(
            "---\nsource_file: 'a/Foo.py'\ntype: 'code'\n"
            f"community: '{long_name}'\n---\n# Foo\n",
            encoding="utf-8",
        )
        _step5_move_to_subfolders(vault)  # must NOT raise ENAMETOOLONG
        dirs = [d for d in vault.iterdir() if d.is_dir()]
        assert len(dirs) == 1
        assert len(dirs[0].name.encode("utf-8")) <= 255

    def test_generate_vault_survives_long_project_name(self, tmp_path: Path):
        long_name = "서비스" * 100
        G = nx.DiGraph()
        G.add_node("n1", type="class", label="Foo", project=long_name,
                   source_file="a/Foo.py", methods=[], dependencies=[], annotations=[])
        G.add_node("n2", type="class", label="Bar", project=long_name,
                   source_file="a/Bar.py", methods=[], dependencies=[], annotations=[])
        G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")
        total = generate_obsidian_vault(G, {"n1": 0, "n2": 0}, tmp_path)
        assert total >= 2  # export completed instead of aborting mid-way


# ── BH-O2: step 9 hub note must not clobber a same-named real note ───────────

class TestStep9HubDoesNotOverwriteRealNote:
    def _payment_graph(self) -> tuple[nx.DiGraph, dict]:
        G = nx.DiGraph()
        # Real class whose LABEL == its own PROJECT/service directory name.
        G.add_node("n_svc", type="class", project="PaymentService",
                   label="PaymentService",
                   source_file="src/com/x/PaymentService.java", framework="spring-boot",
                   annotations=["@Service"], methods=["chargeCard", "refund"],
                   dependencies=["PaymentRepository"])
        # Sibling so the folder has >= 2 nodes.
        G.add_node("n_ctrl", type="class", project="PaymentService",
                   label="PaymentController",
                   source_file="src/com/x/PaymentController.java", framework="spring-boot",
                   annotations=["@RestController"], methods=["charge"],
                   dependencies=["PaymentService"])
        G.add_edge("n_ctrl", "n_svc", relation="injects", confidence="EXTRACTED")
        return G, {"n_svc": 0, "n_ctrl": 0}

    def test_real_note_content_preserved(self, tmp_path: Path):
        G, communities = self._payment_graph()
        generate_obsidian_vault(G, communities, tmp_path)
        note = (tmp_path / "obsidian" / "PaymentService" / "PaymentService.md")
        content = note.read_text(encoding="utf-8")
        # The extracted class content survives — not the synthetic hub body.
        assert "chargeCard" in content
        assert "refund" in content
        assert "@Service" in content
        assert "folder-index" not in content

    def test_hub_written_under_salted_name(self, tmp_path: Path):
        G, communities = self._payment_graph()
        generate_obsidian_vault(G, communities, tmp_path)
        folder = tmp_path / "obsidian" / "PaymentService"
        # Hub relocated so it doesn't clobber the real note; it still indexes
        # the folder (folder-index + a link to the sibling controller).
        hub = folder / "PaymentService_index.md"
        assert hub.exists()
        hub_content = hub.read_text(encoding="utf-8")
        assert "folder-index" in hub_content
        assert "PaymentController" in hub_content

    def test_common_case_hub_still_at_service_name(self, tmp_path: Path):
        # No label==project collision → hub keeps its <svc>/<svc>.md home.
        G = nx.DiGraph()
        G.add_node("n1", type="class", project="billing", label="Invoice",
                   source_file="a/Invoice.java", methods=[], dependencies=[], annotations=[])
        G.add_node("n2", type="class", project="billing", label="Ledger",
                   source_file="a/Ledger.java", methods=[], dependencies=[], annotations=[])
        G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")
        generate_obsidian_vault(G, {"n1": 0, "n2": 0}, tmp_path)
        hub = tmp_path / "obsidian" / "billing" / "billing.md"
        assert hub.exists()
        assert "folder-index" in hub.read_text(encoding="utf-8")


# ── BH-O3: post-commit hook written LF-only (no Windows CRLF translation) ────

class TestPostCommitHookNewline:
    def test_hook_bytes_contain_no_cr(self, tmp_path, monkeypatch):
        from codebeacon.export import hooks as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr(hooks_mod, "_hooks_dir", lambda repo: hooks_dir)
        hooks_mod._install_post_commit(tmp_path)
        data = (hooks_dir / "post-commit").read_bytes()
        assert b"\r" not in data
        assert data.split(b"\n", 1)[0] == b"#!/usr/bin/env bash"

    def test_hook_write_pins_lf_newline(self, tmp_path, monkeypatch):
        # os.linesep is cached by the io layer, so on macOS newline=None writes
        # LF regardless — the byte check above can't distinguish fixed from
        # reverted here. Assert the load-bearing detail: the write pins newline
        # to LF so Windows can't CRLF-translate the shebang / heredoc terminator.
        from codebeacon.export import hooks as hooks_mod
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr(hooks_mod, "_hooks_dir", lambda repo: hooks_dir)

        recorded: dict[str, object] = {}
        orig_write_text = Path.write_text

        def spy(self, data, *args, **kwargs):
            if self.name == "post-commit":
                recorded["newline"] = kwargs.get("newline", "__MISSING__")
            return orig_write_text(self, data, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", spy)
        hooks_mod._install_post_commit(tmp_path)
        assert recorded.get("newline") in ("", "\n")
