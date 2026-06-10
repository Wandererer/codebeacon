"""Regression tests for bugs found by the 2026-06-10 independent audit.

These are codebeacon-native bugs (not graphify ports):

| # | Site                                  | Bug                                              |
|---|---------------------------------------|--------------------------------------------------|
| 1 | config.py                             | null YAML sections / project entries crash       |
| 2 | common/symbols.py                     | injects edges stamped node ID into source_file   |
| 3 | graph/analyze.py hub_files            | counted import fan-out instead of fan-in         |
| 4 | extract/routes.py _interpret_ktor     | nested route() prefixes dropped (innermost only) |
| 5 | extract/services.py FastAPI Depends   | ghost "<file>::unknown" UnresolvedRef            |
| 6 | discover/detector.py language vote    | rglob descended into node_modules/.git           |
| 7 | wiki templates vs generator filenames | links built with a different transform           |
| 8 | graph/enrich.py route_map             | same-path routes overwrote each other            |
| 9 | cache.py                              | shared across threads with no lock               |
"""
from __future__ import annotations

import threading

import networkx as nx
import pytest

from codebeacon.common.types import Node, UnresolvedRef


# ── 1. config.py null tolerance ──────────────────────────────────────────────

class TestConfigNullTolerance:
    def _write(self, tmp_path, body: str):
        p = tmp_path / "codebeacon.yaml"
        p.write_text(body, encoding="utf-8")
        return p

    def test_empty_sections_fall_back_to_defaults(self, tmp_path):
        from codebeacon.config import load_config
        p = self._write(tmp_path, (
            "version: 1\n"
            "projects:\n"
            "  - name: app\n"
            "    path: .\n"
            "output:\n"      # present but null
            "wave:\n"
            "semantic:\n"
        ))
        cfg = load_config(p)
        assert cfg.output.dir == ".codebeacon"
        assert cfg.wave.chunk_size == 300
        assert cfg.semantic.enabled is False

    def test_null_project_entry_raises_value_error(self, tmp_path):
        from codebeacon.config import load_config
        p = self._write(tmp_path, (
            "version: 1\n"
            "projects:\n"
            "  -\n"           # bare dash → None entry
            "  - name: app\n"
            "    path: .\n"
        ))
        with pytest.raises(ValueError):
            load_config(p)


# ── 2. injects edges carry a real source_file ────────────────────────────────

class TestInjectsEdgeSourceFile:
    def test_resolved_edge_source_file_is_file_path(self):
        from codebeacon.common.symbols import SymbolTable
        table = SymbolTable()
        table.build([
            Node(id="app::OrderController", label="OrderController", type="class",
                 source_file="src/order_controller.py", line=1, metadata={}),
            Node(id="app::OrderService", label="OrderService", type="class",
                 source_file="src/order_service.py", line=1, metadata={}),
        ])
        edge = table.resolve_ref(UnresolvedRef(
            source_node_id="app::OrderController",
            ref_type="depends", ref_name="OrderService", framework="fastapi",
        ))
        assert edge is not None
        assert edge.source_file == "src/order_controller.py"
        assert "::" not in edge.source_file


# ── 3. hub_files counts who is imported, not who imports ─────────────────────

class TestHubFilesDirection:
    def test_heavily_imported_file_ranks_first(self):
        from codebeacon.graph.analyze import hub_files
        G = nx.DiGraph()
        G.add_node("app::utils", source_file="src/utils.py")
        for i in range(3):
            nid = f"app::consumer{i}"
            G.add_node(nid, source_file=f"src/consumer{i}.py")
            G.add_edge(nid, "app::utils", relation="imports_from",
                       source_file=f"src/consumer{i}.py")
        # One entry point importing two libs — high fan-OUT, must not win.
        G.add_node("app::main", source_file="src/main.py")
        G.add_edge("app::main", "app::consumer0", relation="imports_from",
                   source_file="src/main.py")
        G.add_edge("app::main", "app::consumer1", relation="imports_from",
                   source_file="src/main.py")

        hubs = hub_files(G)
        assert hubs[0].file_path == "src/utils.py"
        assert hubs[0].import_count == 3

    def test_count_is_distinct_files_not_edges(self):
        # Import edges are remapped per-node, so one importing file with many
        # nodes used to inflate the count by its node count.
        from codebeacon.graph.analyze import hub_files
        G = nx.DiGraph()
        G.add_node("app::utils", source_file="src/utils.py")
        for i in range(5):  # five nodes, all in the SAME importing file
            nid = f"app::big{i}"
            G.add_node(nid, source_file="src/big_module.py")
            G.add_edge(nid, "app::utils", relation="imports_from",
                       source_file="src/big_module.py")
        hubs = hub_files(G)
        assert hubs[0].import_count == 1

    def test_contextmap_hub_files_matches_analyze_semantics(self):
        from codebeacon.contextmap.generator import _hub_files
        G = nx.DiGraph()
        G.add_node("app::utils", source_file="src/utils.py")
        for i in range(3):
            nid = f"app::consumer{i}"
            G.add_node(nid, source_file=f"src/consumer{i}.py")
            G.add_edge(nid, "app::utils", relation="imports_from",
                       source_file=f"src/consumer{i}.py")
        G.add_node("app::main", source_file="src/main.py")
        G.add_edge("app::main", "app::consumer0", relation="imports_from",
                   source_file="src/main.py")
        G.add_edge("app::main", "app::consumer1", relation="imports_from",
                   source_file="src/main.py")
        ranked = _hub_files(G)
        assert ranked[0] == ("src/utils.py", 3)


# ── 4. Ktor nested prefixes concatenate ──────────────────────────────────────

class _FakeNode:
    def __init__(self, text: str = "", start_line: int = 0, end_line: int = 0):
        self.text = text.encode("utf-8")
        self.start_point = (start_line, 0)
        self.end_point = (end_line, 0)


class TestKtorNestedPrefixes:
    def test_outer_and_inner_prefixes_join(self):
        from codebeacon.extract.routes import _interpret_ktor
        matches = [
            (0, {"route.prefix_scope": [_FakeNode(start_line=0, end_line=10)],
                 "route.route_prefix": [_FakeNode('"/api"')]}),
            (0, {"route.prefix_scope": [_FakeNode(start_line=1, end_line=9)],
                 "route.route_prefix": [_FakeNode('"/v1"')]}),
            (1, {"route.method_call": [_FakeNode(start_line=5)],
                 "route.method": [_FakeNode("get")],
                 "route.path": [_FakeNode('"/users"')]}),
        ]
        routes = _interpret_ktor("Routing.kt", matches, "ktor")
        assert len(routes) == 1
        assert routes[0].path == "/api/v1/users"
        assert routes[0].method == "GET"

    def test_sibling_scope_not_applied(self):
        from codebeacon.extract.routes import _interpret_ktor
        matches = [
            (0, {"route.prefix_scope": [_FakeNode(start_line=0, end_line=4)],
                 "route.route_prefix": [_FakeNode('"/admin"')]}),
            (0, {"route.prefix_scope": [_FakeNode(start_line=6, end_line=10)],
                 "route.route_prefix": [_FakeNode('"/public"')]}),
            (1, {"route.method_call": [_FakeNode(start_line=8)],
                 "route.method": [_FakeNode("get")],
                 "route.path": [_FakeNode('"/health"')]}),
        ]
        routes = _interpret_ktor("Routing.kt", matches, "ktor")
        assert routes[0].path == "/public/health"


# ── 5. FastAPI Depends outside a matched function emits no ghost ref ─────────

class TestFastapiNoGhostUnresolved:
    def test_untyped_handler_yields_no_unknown_ref(self, tmp_path):
        pytest.importorskip("tree_sitter_python")
        from codebeacon.extract.services import extract_services
        f = tmp_path / "api.py"
        f.write_text(
            "from fastapi import Depends\n"
            "\n"
            "async def handler(request):\n"           # untyped param → not matched
            "    user = Depends(get_current_user)\n"
            "\n"
            "def typed_handler(svc: OrderService = Depends(order_service)):\n"
            "    return svc\n",
            encoding="utf-8",
        )
        _services, unresolved = extract_services(str(f), "fastapi")
        ghost = [u for u in unresolved if u.source_node_id.endswith("::unknown")]
        assert ghost == []


# ── 6. language vote skips vendored dirs ─────────────────────────────────────

class TestLanguageVoteSkipsVendored:
    def test_node_modules_does_not_outvote_real_code(self, tmp_path):
        from codebeacon.discover.detector import _detect_language_from_files
        nm = tmp_path / "node_modules" / "leftpad"
        nm.mkdir(parents=True)
        for i in range(20):
            (nm / f"vendor{i}.js").write_text("//", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
        (tmp_path / "util.py").write_text("x = 1\n", encoding="utf-8")
        assert _detect_language_from_files(tmp_path) == "python"


# ── 7. wiki links point at the file the generator actually writes ────────────

class TestWikiLinkFilenameAgreement:
    AWKWARD = ["AuthGuard (JWT)", "User.ProfileService", "Repo<User>", "이상한 이름#1"]

    def test_rel_link_matches_generator_filename(self):
        from codebeacon.wiki.generator import _safe_filename
        from codebeacon.wiki.templates import _rel_link
        for label in self.AWKWARD:
            link = _rel_link(label, "app")
            target = link[link.index("(./") + 3 : link.rindex(".md)")]
            assert target == _safe_filename(label), label

    def test_project_index_links_match_generator_filename(self):
        from codebeacon.wiki.generator import _safe_filename
        from codebeacon.wiki.templates import project_index
        md = project_index(
            project_name="app", framework="fastapi", stats={},
            controllers=["AuthGuard (JWT)"], services=["User.ProfileService"],
            entities=[], components=[],
        )
        assert f"(./controllers/{_safe_filename('AuthGuard (JWT)')}.md)" in md
        assert f"(./services/{_safe_filename('User.ProfileService')}.md)" in md


# ── 8. same-path routes in two services both get calls_api edges ─────────────

class TestEnrichSamePathRoutes:
    def test_both_routes_matched(self, tmp_path):
        from codebeacon.graph.enrich import enrich_http_api
        src = tmp_path / "client.ts"
        src.write_text('fetch("/api/users");\n', encoding="utf-8")

        G = nx.DiGraph()
        G.add_node("gw::route_users", type="route", path="/api/users", project="gateway")
        G.add_node("up::route_users", type="route", path="/api/users", project="upstream")
        G.add_node("front::UserList", type="component", project="front",
                   source_file=str(src))
        added = enrich_http_api(G)
        assert added == 2
        assert G.has_edge("front::UserList", "gw::route_users")
        assert G.has_edge("front::UserList", "up::route_users")


# ── 9. cache survives concurrent use ─────────────────────────────────────────

class TestCacheThreadSafety:
    def test_concurrent_get_put_no_errors(self, tmp_path):
        from concurrent.futures import ThreadPoolExecutor
        from codebeacon.cache import Cache
        files = []
        for i in range(16):
            f = tmp_path / f"f{i}.py"
            f.write_text(f"x = {i}\n", encoding="utf-8")
            files.append(str(f))
        cache = Cache(str(tmp_path / "out"))
        errors: list[BaseException] = []

        def worker(path: str) -> None:
            try:
                for _ in range(50):
                    if cache.get(path) is None:
                        cache.put(path, {"routes": [], "services": []})
            except BaseException as exc:  # noqa: BLE001 — recording for assert
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, files * 4))
        assert errors == []
        assert all(cache.get(p) is not None for p in files)

    def test_cache_has_lock(self):
        from codebeacon.cache import Cache
        c = Cache(".")
        assert isinstance(c._lock, type(threading.RLock()))
