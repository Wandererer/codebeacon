"""Regression tests for the 0.6.8 graphify-parity audit (graphify v0.8.41–v0.9.3).

Each class pins one confirmed-and-reproduced bug:

  #1506  — obsidian export must not delete a user-managed vault
  #1363  — .codebeaconignore must MERGE with .gitignore, not replace it
  #1417  — absolute paths must not leak into beacon.json links
  #1504/#1522/#1453/#1409 — export filenames collide on case-insensitive FS /
           punctuation-only labels (converged: derive from a case-folded,
           collision-salted, unnamed-guarded stem)
  #1536  — load_beacon must not crash on a corrupt/truncated beacon.json
  #1322  — react.scm must capture function-expression + bare-import HOC components
  #1444  — wiki links to non-existent articles must downgrade to plain text
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest


def _mini_graph() -> tuple[nx.DiGraph, dict]:
    G = nx.DiGraph()
    G.add_node(
        "proj::UserService",
        type="class",
        label="UserService",
        project="proj",
        source_file="/abs/proj/UserService.java",
    )
    return G, {"proj::UserService": 0}


# ── #1506 — obsidian vault-deletion guard ──────────────────────────────────────

class TestObsidianVaultGuard:
    def test_refuses_to_wipe_user_vault(self, tmp_path: Path):
        from codebeacon.export.obsidian import generate_obsidian_vault

        user_vault = tmp_path / "my-vault"
        user_vault.mkdir()
        precious = user_vault / "MyDailyNote.md"
        precious.write_text("my irreplaceable notes", encoding="utf-8")

        G, comms = _mini_graph()
        with pytest.raises(ValueError, match="user-managed"):
            generate_obsidian_vault(G, comms, str(tmp_path / "out"),
                                    obsidian_dir=str(user_vault))

        # The refusal must happen BEFORE any unlink — the note survives intact.
        assert precious.exists()
        assert precious.read_text(encoding="utf-8") == "my irreplaceable notes"

    def test_adopts_empty_dir_and_stamps_marker(self, tmp_path: Path):
        from codebeacon.export.obsidian import generate_obsidian_vault, _VAULT_MARKER

        empty_vault = tmp_path / "empty-vault"
        empty_vault.mkdir()
        G, comms = _mini_graph()
        generate_obsidian_vault(G, comms, str(tmp_path / "out"),
                                obsidian_dir=str(empty_vault))
        assert (empty_vault / _VAULT_MARKER).exists()

    def test_rerun_on_owned_vault_is_allowed(self, tmp_path: Path):
        from codebeacon.export.obsidian import generate_obsidian_vault

        vault = tmp_path / "cb-vault"
        vault.mkdir()
        G, comms = _mini_graph()
        # first run adopts + stamps
        generate_obsidian_vault(G, comms, str(tmp_path / "out"), obsidian_dir=str(vault))
        # second run recognises the marker and does not raise
        generate_obsidian_vault(G, comms, str(tmp_path / "out"), obsidian_dir=str(vault))

    def test_default_dir_is_never_refused(self, tmp_path: Path):
        from codebeacon.export.obsidian import generate_obsidian_vault

        out = tmp_path / "out"
        out.mkdir()
        # simulate a stale prior note in the default vault
        (out / "obsidian").mkdir()
        (out / "obsidian" / "stale.md").write_text("stale", encoding="utf-8")
        G, comms = _mini_graph()
        # obsidian_dir=None → default, always owned, sweep proceeds without raising
        generate_obsidian_vault(G, comms, str(out), obsidian_dir=None)
        assert not (out / "obsidian" / "stale.md").exists()


# ── #1363 — merge .gitignore with .codebeaconignore (security) ─────────────────

class TestIgnoreMerge:
    def test_gitignore_still_applies_when_codebeaconignore_present(self, tmp_path: Path):
        from codebeacon.discover.scanner import read_ignore_file

        (tmp_path / ".gitignore").write_text("prod-dump.sql\nsecrets.env\n", encoding="utf-8")
        (tmp_path / ".codebeaconignore").write_text("*.tmp\n", encoding="utf-8")

        lines = read_ignore_file(tmp_path)
        # the merge must keep BOTH sources — the gitignored secret is not dropped
        assert "prod-dump.sql" in lines
        assert "secrets.env" in lines
        assert "*.tmp" in lines

    def test_gitignored_secret_is_actually_skipped_end_to_end(self, tmp_path: Path):
        from codebeacon.discover.scanner import collect_files

        (tmp_path / ".gitignore").write_text("prod-dump.sql\n", encoding="utf-8")
        (tmp_path / ".codebeaconignore").write_text("*.tmp\n", encoding="utf-8")
        (tmp_path / "prod-dump.sql").write_text("SECRET", encoding="utf-8")
        (tmp_path / "app.py").write_text("print('ok')", encoding="utf-8")

        collected = {Path(p).name for p in collect_files(tmp_path)}
        assert "app.py" in collected
        assert "prod-dump.sql" not in collected  # would leak without the merge

    def test_codebeaconignore_wins_on_conflict(self, tmp_path: Path):
        from codebeacon.discover.scanner import read_ignore_file

        # .gitignore excludes *.log; .codebeaconignore re-includes one via negation
        (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (tmp_path / ".codebeaconignore").write_text("!keep.log\n", encoding="utf-8")
        lines = read_ignore_file(tmp_path)
        # tool file appended last → its negation is last-match-wins
        assert lines.index("!keep.log") > lines.index("*.log")

    def test_only_gitignore_still_works(self, tmp_path: Path):
        from codebeacon.discover.scanner import read_ignore_file

        (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
        assert "build/" in read_ignore_file(tmp_path)

    def test_only_codebeaconignore_still_works(self, tmp_path: Path):
        from codebeacon.discover.scanner import read_ignore_file

        (tmp_path / ".codebeaconignore").write_text("node_modules/\n", encoding="utf-8")
        assert "node_modules/" in read_ignore_file(tmp_path)


# ── #1417 — absolute paths must not leak into artifacts ────────────────────────

class TestPathPortability:
    def test_beacon_json_links_are_relativized(self, tmp_path: Path):
        from codebeacon.graph.write import write_beacon

        root = tmp_path / "proj"
        (root / "pkg").mkdir(parents=True)
        abs_a = str(root / "pkg" / "a.py")
        abs_b = str(root / "pkg" / "b.py")

        G = nx.DiGraph()
        G.add_node("proj::a", type="function", label="a", project="proj", source_file=abs_a)
        G.add_node("proj::b", type="function", label="b", project="proj", source_file=abs_b)
        G.add_edge("proj::a", "proj::b", relation="imports_from",
                   source_file=abs_a, source="proj::a", target="proj::b")

        out = tmp_path / "out"
        write_beacon(G, out, project_roots={"proj": str(root)})
        data = json.loads((out / "beacon.json").read_text(encoding="utf-8"))

        node_sf = {n["id"]: n.get("source_file") for n in data["nodes"]}
        assert node_sf["proj::a"] == "pkg/a.py"

        link = data["links"][0]
        # #1417: the edge's source_file must be relative, not absolute
        assert link["source_file"] == "pkg/a.py"
        assert not link["source_file"].startswith("/")

    def test_no_absolute_paths_anywhere_in_beacon(self, tmp_path: Path):
        from codebeacon.graph.write import write_beacon

        root = tmp_path / "proj"
        root.mkdir()
        abs_a = str(root / "a.py")
        G = nx.DiGraph()
        G.add_node("proj::a", type="function", label="a", project="proj", source_file=abs_a)
        G.add_edge("proj::a", "proj::a", relation="calls", source_file=abs_a, source="proj::a")
        out = tmp_path / "out"
        write_beacon(G, out, project_roots={"proj": str(root)})
        raw = (out / "beacon.json").read_text(encoding="utf-8")
        assert str(root) not in raw  # no machine-absolute path leaked

    def test_relativize_source_file_helper(self, tmp_path: Path):
        from codebeacon.graph.write import relativize_source_file

        root = tmp_path / "r"
        (root / "s").mkdir(parents=True)
        assert relativize_source_file(str(root / "s" / "x.py"), str(root)) == "s/x.py"
        # already-relative or foreign paths pass through untouched
        assert relativize_source_file("s/x.py", str(root)) == "s/x.py"
        assert relativize_source_file("", str(root)) == ""
        assert relativize_source_file("/elsewhere/y.py", str(root)) == "/elsewhere/y.py"

    def test_wiki_emits_relative_source(self, tmp_path: Path):
        from codebeacon.wiki.generator import generate_wiki

        root = tmp_path / "proj"
        root.mkdir()
        abs_svc = str(root / "UserService.java")
        G = nx.DiGraph()
        G.add_node("proj::UserService", type="class", label="UserService",
                   project="proj", source_file=abs_svc, methods=[], dependencies=[],
                   annotations=[])
        out = tmp_path / "out"
        generate_wiki(G, {"proj::UserService": 0}, out,
                      project_roots={"proj": str(root)})
        article = (out / "wiki" / "proj" / "services" / "UserService.md")
        text = article.read_text(encoding="utf-8")
        assert str(root) not in text          # no absolute path
        assert "UserService.java" in text     # relative path present


# ── #1504/#1522/#1453/#1409 — export filename collision (converged) ────────────

class TestFilenameCollision:
    def test_dedup_stem_salts_case_collision(self):
        from codebeacon.common.safety import dedup_stem

        claimed: dict[str, str] = {}
        a = dedup_stem("UserService", "proj::A", claimed)
        b = dedup_stem("userService", "proj::B", claimed)  # case-collision
        assert a == "UserService"
        assert b != "userService" and b.lower() != "userservice"  # salted, distinct
        # same node re-asking for its stem is idempotent (no runaway salting)
        assert dedup_stem("UserService", "proj::A", claimed) == "UserService"

    def test_dedup_stem_scope_prevents_false_collision(self):
        from codebeacon.common.safety import dedup_stem

        claimed: dict[str, str] = {}
        c = dedup_stem("User", "proj::C", claimed, "controllers")
        s = dedup_stem("User", "proj::S", claimed, "services")
        assert c == "User" and s == "User"  # different dirs → no collision

    def test_cap_filename_unnamed_fallback(self):
        from codebeacon.common.safety import cap_filename

        assert cap_filename("@") == "unnamed"
        assert cap_filename("***") == "unnamed"
        assert cap_filename("   ") == "unnamed"
        assert cap_filename("") == "unnamed"
        assert cap_filename("Normal") == "Normal"  # unaffected

    def test_safe_note_name_never_empty_or_punct(self):
        from codebeacon.export.obsidian import _safe_note_name

        assert _safe_note_name("@") == "unnamed"
        assert _safe_note_name("") == "unnamed"

    def test_obsidian_case_collision_both_notes_survive(self, tmp_path: Path):
        from codebeacon.export.obsidian import generate_obsidian_vault

        G = nx.DiGraph()
        G.add_node("proj::A", type="class", label="UserService", project="proj",
                   source_file="/r/a/UserService.java", methods=[], dependencies=[],
                   annotations=[])
        G.add_node("proj::B", type="class", label="userService", project="proj",
                   source_file="/r/b/userService.js", methods=[], dependencies=[],
                   annotations=[])
        out = tmp_path / "out"
        generate_obsidian_vault(G, {"proj::A": 0, "proj::B": 0}, str(out))

        all_md = "\n".join(p.read_text(encoding="utf-8")
                           for p in (out / "obsidian").rglob("*.md"))
        # Without the case-fold dedup one note overwrote the other at step 1.
        assert "UserService.java" in all_md
        assert "userService.js" in all_md

    def test_wiki_case_collision_both_articles_survive(self, tmp_path: Path):
        from codebeacon.wiki.generator import generate_wiki

        G = nx.DiGraph()
        G.add_node("proj::A", type="class", label="OrderService", project="proj",
                   source_file="/r/OrderService.java", methods=[], dependencies=[],
                   annotations=[])
        G.add_node("proj::B", type="class", label="orderService", project="proj",
                   source_file="/r/orderService.java", methods=[], dependencies=[],
                   annotations=[])
        out = tmp_path / "out"
        generate_wiki(G, {"proj::A": 0, "proj::B": 0}, str(out))
        svc = list((out / "wiki" / "proj" / "services").glob("*.md"))
        assert len(svc) == 2  # both survived; the second was salted


# ── #1536 — load_beacon must not crash on a corrupt beacon.json ────────────────

class TestCorruptBeaconLoad:
    def test_corrupt_beacon_raises_clear_error_and_is_backed_up(self, tmp_path: Path):
        from codebeacon.graph.write import load_beacon

        bad = tmp_path / "beacon.json"
        bad.write_text('{"nodes": [{"id": "x"}, {trunca', encoding="utf-8")  # truncated

        with pytest.raises(ValueError, match="corrupt or truncated"):
            load_beacon(bad)

        # the corrupt file is preserved as a .corrupt sidecar, not left in place
        backups = list(tmp_path.glob("beacon.json.*.corrupt"))
        assert len(backups) == 1

    def test_missing_beacon_still_raises_oserror(self, tmp_path: Path):
        from codebeacon.graph.write import load_beacon

        # a missing file is NOT corruption — it must behave as before (OSError),
        # not get a spurious .corrupt backup
        with pytest.raises(OSError):
            load_beacon(tmp_path / "does_not_exist.json")
        assert not list(tmp_path.glob("*.corrupt"))

    def test_valid_beacon_still_loads(self, tmp_path: Path):
        from codebeacon.graph.write import write_beacon, load_beacon

        G = nx.DiGraph()
        G.add_node("p::a", type="function", label="a", project="p")
        write_beacon(G, tmp_path)
        G2, meta = load_beacon(tmp_path / "beacon.json")
        assert "p::a" in G2.nodes
        assert meta.get("version") == 1


# ── #1322 — react.scm must capture fn-expression + bare-import HOC components ───

class TestReactComponentForms:
    PROBE = (
        "export const ArrowComp = () => <div/>;\n"
        "export const FnExprComp = function() { return <div/>; };\n"
        "const BareRef = forwardRef((props, ref) => <div ref={ref}/>);\n"
        "const ReactRef = React.forwardRef((props, ref) => <div/>);\n"
        "function DeclComp() { return <div/>; }\n"
    )

    def test_all_component_forms_captured(self, tmp_path: Path):
        from codebeacon.extract.components import extract_components

        probe = tmp_path / "probe.jsx"
        probe.write_text(self.PROBE, encoding="utf-8")
        names = {c.name for c in extract_components(str(probe), "react")}
        # Regression: FnExprComp / BareRef / DeclComp were silently dropped.
        assert {"ArrowComp", "FnExprComp", "BareRef", "ReactRef", "DeclComp"} <= names


# ── #1444 — wiki links to non-existent articles downgrade to plain text ─────────

class TestWikiDanglingLinks:
    def test_dangling_dependency_link_is_plain_text(self, tmp_path: Path):
        from codebeacon.wiki.generator import generate_wiki

        G = nx.DiGraph()
        # OrderService depends on PaymentGateway (no node → no article) and on
        # AuditService (has a node → an article file is written).
        G.add_node("proj::OrderService", type="class", label="OrderService",
                   project="proj", source_file="/r/OrderService.java", methods=[],
                   annotations=[], dependencies=["PaymentGateway", "AuditService"])
        G.add_node("proj::AuditService", type="class", label="AuditService",
                   project="proj", source_file="/r/AuditService.java", methods=[],
                   annotations=[], dependencies=[])
        out = tmp_path / "out"
        generate_wiki(G, {"proj::OrderService": 0, "proj::AuditService": 0}, str(out))

        art = (out / "wiki" / "proj" / "services" / "OrderService.md").read_text(encoding="utf-8")
        # dangling target → downgraded to plain text, no dead link
        assert "(./PaymentGateway.md)" not in art
        assert "PaymentGateway" in art
        # real target in the same directory → link preserved
        assert "(./AuditService.md)" in art

    def test_back_link_preserved_and_points_up(self, tmp_path: Path):
        # Regression (#1444 round-2): the downgrader must NOT strip the back-link;
        # the project index is one level up from a bucket article.
        from codebeacon.wiki.generator import generate_wiki

        G = nx.DiGraph()
        G.add_node("proj::Ctrl", type="class", label="Ctrl", project="proj",
                   source_file="/r/Ctrl.java", methods=[], annotations=["@RestController"],
                   dependencies=[])
        out = tmp_path / "out"
        generate_wiki(G, {"proj::Ctrl": 0}, str(out))
        art = (out / "wiki" / "proj" / "controllers" / "Ctrl.md").read_text(encoding="utf-8")
        assert "(../index.md)" in art          # back-link preserved, points up
        assert (out / "wiki" / "proj" / "index.md").exists()

    def test_downgrader_repairs_cross_bucket_and_strips_only_dangling(self, tmp_path: Path):
        from codebeacon.wiki.generator import _downgrade_dead_links

        proj = tmp_path / "wiki" / "proj"
        (proj / "services").mkdir(parents=True)
        (proj / "entities").mkdir(parents=True)
        (proj / "entities" / "Order.md").write_text("# Order\n", encoding="utf-8")
        # A service article links to Order (in a sibling bucket) and to Ghost (none)
        (proj / "services" / "Svc.md").write_text(
            "[Order](./Order.md) and [Ghost](./Ghost.md)\n", encoding="utf-8")

        _downgrade_dead_links(tmp_path / "wiki")
        out = (proj / "services" / "Svc.md").read_text(encoding="utf-8")
        assert "[Order](../entities/Order.md)" in out  # cross-bucket repaired
        assert "(./Ghost.md)" not in out and "Ghost" in out  # dangling → plain text

    def test_cross_bucket_repair_is_deterministic(self, tmp_path: Path):
        # Round-3 (#1444): when two buckets share a stem, the repair target must be
        # stable across platforms (rglob order is unspecified → sort before picking).
        from codebeacon.wiki.generator import _downgrade_dead_links

        proj = tmp_path / "wiki" / "proj"
        for bucket in ("components", "entities", "services"):
            (proj / bucket).mkdir(parents=True)
        (proj / "components" / "Order.md").write_text("# Order (component)\n", encoding="utf-8")
        (proj / "entities" / "Order.md").write_text("# Order (entity)\n", encoding="utf-8")
        (proj / "services" / "Svc.md").write_text("[Order](./Order.md)\n", encoding="utf-8")

        _downgrade_dead_links(tmp_path / "wiki")
        out = (proj / "services" / "Svc.md").read_text(encoding="utf-8")
        # sorted-first bucket wins deterministically: components < entities
        assert "[Order](../components/Order.md)" in out


class TestVaultNotOwnedError:
    def test_is_valueerror_subclass(self):
        from codebeacon.export.obsidian import VaultNotOwnedError
        assert issubclass(VaultNotOwnedError, ValueError)


# ── #1536 round-2 — corrupt-load must not crash callers ────────────────────────

class TestCorruptBeaconCallers:
    def test_non_dict_beacon_is_treated_as_corruption(self, tmp_path: Path):
        from codebeacon.graph.write import load_beacon

        bad = tmp_path / "beacon.json"
        bad.write_text("[1, 2, 3]", encoding="utf-8")  # valid JSON, wrong shape
        with pytest.raises(ValueError, match="not a beacon document"):
            load_beacon(bad)
        assert list(tmp_path.glob("beacon.json.*.corrupt"))

    def test_mcp_index_load_does_not_raise_uncaught(self, tmp_path: Path):
        # serve() catches (FileNotFoundError, ValueError); confirm a corrupt
        # beacon makes BeaconIndex.load raise ValueError (the type serve catches),
        # not a bare JSONDecodeError/AttributeError.
        from codebeacon.export.mcp import BeaconIndex

        (tmp_path / "beacon.json").write_text("{ truncated", encoding="utf-8")
        idx = BeaconIndex(tmp_path)
        with pytest.raises(ValueError):
            idx.load()


# ── #1506 round-2 — guard must refuse a note-empty real vault ──────────────────

class TestVaultGuardTightened:
    def test_refuses_note_empty_real_vault(self, tmp_path: Path):
        from codebeacon.export.obsidian import generate_obsidian_vault, _VAULT_MARKER

        vault = tmp_path / "real-vault"
        (vault / ".obsidian").mkdir(parents=True)
        (vault / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
        (vault / "Board.canvas").write_text("{}", encoding="utf-8")  # no .md yet

        G, comms = _mini_graph()
        with pytest.raises(ValueError, match="user-managed"):
            generate_obsidian_vault(G, comms, str(tmp_path / "out"), obsidian_dir=str(vault))
        # refused before stamping — the user's config is untouched
        assert not (vault / _VAULT_MARKER).exists()
        assert (vault / ".obsidian" / "app.json").exists()
        assert (vault / "Board.canvas").exists()


# ── #1417 round-2 — cross-project edge source_file relativized ─────────────────

class TestCrossProjectRelativize:
    def test_shared_entity_edge_file_relativized(self, tmp_path: Path):
        from codebeacon.graph.write import write_beacon

        root_a = tmp_path / "a"; root_a.mkdir()
        root_b = tmp_path / "b"; (root_b / "db").mkdir(parents=True)
        entity_file = str(root_b / "db" / "Order.java")  # lives in project B

        G = nx.DiGraph()
        G.add_node("a::Svc", type="class", label="Svc", project="a",
                   source_file=str(root_a / "Svc.java"))
        G.add_node("b::Order", type="entity", label="Order", project="b",
                   source_file=entity_file)
        # a shares_db_entity edge from A's service carries B's entity file
        G.add_edge("a::Svc", "b::Order", relation="shares_db_entity",
                   source_file=entity_file, source="a::Svc", target="b::Order")

        out = tmp_path / "out"
        write_beacon(G, out, project_roots={"a": str(root_a), "b": str(root_b)})
        data = json.loads((out / "beacon.json").read_text(encoding="utf-8"))
        link = data["links"][0]
        assert link["source_file"] == "db/Order.java"  # relativized against B's root
        assert str(tmp_path) not in json.dumps(data)   # nothing absolute anywhere
