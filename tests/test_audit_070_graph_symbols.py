"""Audit 0.7.1 — graph build, node identity, edge semantics and symbol binding.

Covers the F4 batch:

| Ruling | Items | Subject |
|---|---|---|
| R7 | GI-2207, GI-2460, G-0937-1, G-0939-2, G-0949-15, G-0916-14, G-0927-11, C-53b | bare-name binding guards |
| R8 | GI-1829, GI-2810, G-0923-6, G-0919-3, G-0922-7, G-0949-3 | node identity |
| R9 | G-0946-11, GI-2391, GI-2236, G-0943-2, V5-EXTRA-1 | edge precedence + import fan-out |
| —  | G-0941-11 | PHP namespace separator |
| —  | CG-JS-MODULE-RESOLUTION (G-0927-10, GI-2340, G-0949-18) | tsconfig / path resolution |
| —  | G-0921-4, G-0924-4 | self-loop guard, merge attribute loss |

Every test here reproduces the verified defect, so reverting its fix flips the
assertion (mutation-checked).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from codebeacon.common.types import (
    ComponentInfo, Edge, Node, ProjectInfo, ServiceInfo, UnresolvedRef,
)
from codebeacon.common.symbols import SymbolTable
from codebeacon.graph.build import (
    _import_to_label,
    _merge_cross_file_decls,
    _remap_import_edges,
    build_graph,
)
from codebeacon.wave import WaveResult, auto_wave


# ── helpers ───────────────────────────────────────────────────────────────────

def _project(name="api", path="/projects/api", framework="spring-boot",
             language="java") -> ProjectInfo:
    return ProjectInfo(name=name, path=path, framework=framework,
                       language=language, signature_file="pom.xml")


def _svc(name, source_file, deps=None, implements=None, extends=None,
         framework="spring-boot", line=1) -> ServiceInfo:
    return ServiceInfo(
        name=name, class_name=name, source_file=source_file, line=line,
        framework=framework, dependencies=deps or [],
        implements=implements or [], extends=extends or [],
    )


def _node(nid, label, source_file, ntype="class", line=1, metadata=None) -> Node:
    meta = {"project": nid.split("::")[0]}
    meta.update(metadata or {})
    return Node(id=nid, label=label, type=ntype, source_file=source_file,
                line=line, metadata=meta)


def _edge(source, target, relation="imports_from") -> Edge:
    return Edge(source=source, target=target, relation=relation,
                confidence="EXTRACTED", confidence_score=1.0, source_file=source)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _scan(root: Path, name: str, framework: str, language: str) -> WaveResult:
    """Run real Pass-1 extraction over every file under ``root``."""
    from codebeacon.discover.scanner import collect_files
    project = ProjectInfo(name=name, path=str(root), framework=framework,
                          language=language, signature_file="x")
    return auto_wave(project=project, files=collect_files(str(root)), cache=None)


# ── R9: relation precedence on a duplicate (u, v) pair ────────────────────────

class TestEdgeRelationPrecedence:
    """G-0946-11 / GI-2391: NetworkX keeps one attr dict per ordered pair, so the
    last writer erased the earlier relation. A Spring service that both imports
    and injects a repository kept only ``injects`` — and ``hub_files`` then
    reported no hubs at all, because it looks for import relations."""

    def _wave(self):
        return WaveResult(
            project=_project(),
            services=[
                _svc("UserService", "/projects/api/UserService.java",
                     deps=["UserRepository"]),
                _svc("UserRepository", "/projects/api/UserRepository.java"),
            ],
            import_edges=[_edge("/projects/api/UserService.java",
                                "com.api.UserRepository")],
        )

    def test_both_relations_survive_the_collision(self):
        G = build_graph([self._wave()], apply_filters=False)
        data = G["api::UserService"]["api::UserRepository"]
        assert data["relation"] == "imports_from"
        assert "injects" in data.get("also", [])

    def test_hub_files_sees_the_import_again(self):
        from codebeacon.graph.analyze import hub_files
        G = build_graph([self._wave()], apply_filters=False)
        hubs = {Path(h.file_path).name: h.import_count for h in hub_files(G)}
        assert hubs.get("UserRepository.java") == 1

    def test_specific_relation_outranks_a_generic_one_either_way(self):
        """Order must not decide: a generic ``references`` loses to
        ``imports_from`` whichever is written first."""
        nodes = [_node("p::A", "A", "/p/a.py"), _node("p::B", "B", "/p/b.py")]
        forward = [_edge("p::A", "p::B", "references"),
                   _edge("p::A", "p::B", "imports_from")]
        for edges in (forward, list(reversed(forward))):
            from codebeacon.graph.build import _build_nx_graph
            G = _build_nx_graph(nodes, edges, {n.id: n for n in nodes})
            data = G["p::A"]["p::B"]
            assert data["relation"] == "imports_from"
            assert data["also"] == ["references"]

    def test_no_also_attribute_without_a_collision(self):
        nodes = [_node("p::A", "A", "/p/a.py"), _node("p::B", "B", "/p/b.py")]
        from codebeacon.graph.build import _build_nx_graph
        G = _build_nx_graph(nodes, [_edge("p::A", "p::B")], {n.id: n for n in nodes})
        assert "also" not in G["p::A"]["p::B"]


# ── G-0921-4: self-loops ──────────────────────────────────────────────────────

class TestSelfLoopGuard:
    def test_class_depending_on_its_own_type_yields_no_edge(self):
        st = SymbolTable()
        st.build([_node("p::UserService", "UserService", "/p/UserService.java")])
        edge = st.resolve_ref(UnresolvedRef(
            source_node_id="p::UserService", ref_type="depends",
            ref_name="UserService", framework="spring-boot"))
        assert edge is None

    def test_builder_drops_a_self_loop_of_any_relation(self):
        nodes = [_node("p::A", "A", "/p/a.py")]
        from codebeacon.graph.build import _build_nx_graph
        G = _build_nx_graph(nodes, [_edge("p::A", "p::A", "injects")],
                            {n.id: n for n in nodes})
        assert list(nx_self_loops(G)) == []


def nx_self_loops(G):
    return [(u, v) for u, v in G.edges() if u == v]


# ── R9 / GI-2236 / G-0943-2: import fan-out gate ──────────────────────────────

class TestImportFanOutGate:
    """A file-level import was re-emitted once per declaration in the importing
    file, regardless of which declaration used it — a measured 9.3× inflation
    and an 83% false-positive rate on the three-class repro."""

    def _corpus(self, tmp_path: Path) -> WaveResult:
        _write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
        _write(tmp_path, "pkg/__init__.py", "")
        _write(tmp_path, "pkg/alpha.py", "def alpha_thing(n: int):\n    return n\n")
        _write(tmp_path, "pkg/beta.py", "def beta_thing(n: int):\n    return n\n")
        _write(tmp_path, "pkg/consumer.py", (
            "from pkg.alpha import alpha_thing\n"
            "from pkg.beta import beta_thing\n"
            "\n"
            "def only_uses_alpha(n: int):\n"
            "    return alpha_thing(n)\n"
            "\n"
            "def uses_nothing(n: int):\n"
            "    return 1\n"
            "\n"
            "def also_uses_nothing(n: int):\n"
            "    return 2\n"
        ))
        return _scan(tmp_path, "xp", "python", "python")

    def test_only_the_referencing_declaration_gets_the_edge(self, tmp_path):
        """Three declarations × two imports used to emit six edges, five of them
        false. The one genuine reference must be the only edge into Alpha."""
        G = build_graph([self._corpus(tmp_path)], apply_filters=False)
        into_alpha = sorted(
            (u, v) for u, v, d in G.edges(data=True)
            if d.get("relation") == "imports_from" and v == "xp::alpha_thing"
        )
        assert into_alpha == [("xp::only_uses_alpha", "xp::alpha_thing")], into_alpha

    def test_fan_out_is_one_edge_per_import_not_per_declaration(self, tmp_path):
        """The unused import still lands — once, on the file's first
        declaration (R9's file-level fallback) — instead of on all three."""
        G = build_graph([self._corpus(tmp_path)], apply_filters=False)
        imports = [(u, v) for u, v, d in G.edges(data=True)
                   if d.get("relation") == "imports_from"]
        assert len(imports) == 2, imports
        into_beta = [u for u, v in imports if v == "xp::beta_thing"]
        assert into_beta == ["xp::only_uses_alpha"], into_beta


# ── R8: node identity ─────────────────────────────────────────────────────────

class TestNodeIdentity:
    def test_same_name_different_extension_stays_two_nodes(self):
        """GI-1829: src/Button.tsx and src/Button.jsx collapsed onto one node,
        and the loser vanished from the graph, the wiki and ``affected``."""
        wave = WaveResult(
            project=_project("web", "/projects/web", "react", "typescript"),
            components=[
                ComponentInfo(name="Button", source_file="/projects/web/src/Button.tsx",
                              line=1, framework="react"),
                ComponentInfo(name="Button", source_file="/projects/web/src/Button.jsx",
                              line=1, framework="react"),
            ],
        )
        G = build_graph([wave], apply_filters=False)
        buttons = [n for n, d in G.nodes(data=True) if d.get("label", "").startswith("Button")]
        assert len(buttons) == 2, buttons
        files = {Path(G.nodes[n]["source_file"]).name for n in buttons}
        assert files == {"Button.tsx", "Button.jsx"}

    def test_three_same_named_functions_in_one_directory_stay_three_nodes(self):
        """GI-2810: three files each declaring ``load`` produced ONE node."""
        wave = WaveResult(
            project=_project("app", "/projects/app", "python", "python"),
            services=[
                _svc("load", f"/projects/app/src/handler_{s}.py", framework="python")
                for s in ("a", "b", "c")
            ],
        )
        G = build_graph([wave], apply_filters=False)
        loads = [n for n, d in G.nodes(data=True) if d.get("label", "").startswith("load")]
        assert len(loads) == 3, loads
        assert len({G.nodes[n]["source_file"] for n in loads}) == 3

    def test_unrelated_same_named_classes_keep_their_own_methods(self):
        """G-0923-6: the merge keyed on the parent DIRECTORY, so two unrelated
        files in one directory had their methods unioned onto one survivor."""
        wave = WaveResult(
            project=_project("app", "/projects/app", "python", "python"),
            services=[
                _svc("Repo", "/projects/app/src/a.py", framework="python"),
                _svc("Repo", "/projects/app/src/b.py", framework="python"),
            ],
        )
        wave.services[0].methods = ["read"]
        wave.services[1].methods = ["write"]
        G = build_graph([wave], apply_filters=False)
        method_sets = sorted(
            tuple(sorted(d.get("methods", [])))
            for _, d in G.nodes(data=True) if d.get("type") == "class"
        )
        assert method_sets == [("read",), ("write",)]

    @pytest.mark.parametrize("ext,framework", [
        (".swift", "vapor"), (".cs", "aspnet"), (".rb", "rails"), (".kt", "spring-boot"),
    ])
    def test_reopened_declaration_languages_still_merge(self, ext, framework):
        """Swift ``extension``, C# ``partial``, Ruby reopen and Kotlin genuinely
        re-open a declaration across files — that merge must survive."""
        wave = WaveResult(
            project=_project("api", "/projects/api", framework, "x"),
            services=[
                _svc("Repo", f"/projects/api/Repo{ext}", framework=framework),
                _svc("Repo", f"/projects/api/Repo+More{ext}", framework=framework),
            ],
        )
        wave.services[0].methods = ["read"]
        wave.services[1].methods = ["write"]
        G = build_graph([wave], apply_filters=False)
        assert "api::Repo" in G.nodes
        assert set(G.nodes["api::Repo"]["methods"]) == {"read", "write"}

    def test_collision_salt_is_project_relative(self):
        """R8: the double-collision hash salted on the ABSOLUTE directory, so
        the same repo produced different node ids on a different machine."""
        def ids_for(root: str) -> list[str]:
            wave = WaveResult(
                project=_project("api", root, "spring-boot", "java"),
                services=[
                    _svc("User", f"{root}/com/{d}/models/User.java")
                    for d in ("a", "b", "c")
                ],
            )
            return sorted(build_graph([wave], apply_filters=False).nodes)

        assert ids_for("/home/alice/checkout") == ids_for("/opt/ci/workspace/job42")

    def test_colliding_labels_are_made_distinct(self):
        """G-0922-7: two nodes both read ``User (models)``, so free-text
        discovery through query / MCP / wiki could not tell them apart."""
        root = "/repo"
        wave = WaveResult(
            project=_project("api", root, "spring-boot", "java"),
            services=[_svc("User", f"{root}/com/{d}/models/User.java")
                      for d in ("a", "b", "c")],
        )
        G = build_graph([wave], apply_filters=False)
        labels = [d["label"] for _, d in G.nodes(data=True)]
        assert len(labels) == len(set(labels)) == 3, labels


# ── G-0924-4: scalar metadata loss on merge ───────────────────────────────────

class TestMergeKeepsScalarMetadata:
    def test_table_name_survives_from_the_second_record(self):
        a = Node(id="p::User", label="User", type="entity",
                 source_file="app/models/user.rb", line=1,
                 metadata={"fields": [{"name": "id"}], "table_name": "",
                           "framework": "rails"})
        b = Node(id="p::User", label="User", type="entity",
                 source_file="app/models/user.rb", line=40,
                 metadata={"fields": [{"name": "email"}], "table_name": "users",
                           "framework": "rails", "relations": ["has_many :posts"]})
        merged = _merge_cross_file_decls([a, b])[0]
        assert merged.metadata["table_name"] == "users"
        assert {f["name"] for f in merged.metadata["fields"]} == {"id", "email"}

    def test_a_present_scalar_is_never_overwritten(self):
        a = Node(id="p::User", label="User", type="entity", source_file="a.rb",
                 line=1, metadata={"table_name": "people"})
        b = Node(id="p::User", label="User", type="entity", source_file="a.rb",
                 line=9, metadata={"table_name": "users"})
        assert _merge_cross_file_decls([a, b])[0].metadata["table_name"] == "people"

    def test_donor_order_is_deterministic(self):
        def merge(order):
            recs = {
                "b": Node(id="p::U", label="U", type="entity", source_file="b.rb",
                          line=1, metadata={"table_name": "from_b"}),
                "c": Node(id="p::U", label="U", type="entity", source_file="c.rb",
                          line=1, metadata={"table_name": "from_c"}),
            }
            first = Node(id="p::U", label="U", type="entity", source_file="a.rb",
                         line=1, metadata={"table_name": ""})
            return _merge_cross_file_decls([first] + [recs[k] for k in order])[0]
        assert merge(["b", "c"]).metadata["table_name"] == "from_b"
        assert merge(["c", "b"]).metadata["table_name"] == "from_b"


# ── G-0941-11: PHP namespace separator ────────────────────────────────────────

class TestPhpImportLabel:
    @pytest.mark.parametrize("raw,expected", [
        ("App\\Models\\User", "User"),
        ("\\App\\Contracts\\PaymentGateway", "PaymentGateway"),
        ("Illuminate\\Database\\Eloquent\\Model", "Model"),
        # untouched shapes
        ("com.example.repo.UserRepository", "UserRepository"),
        ("@/components/Button", "Button"),
        ("./UserPage", "UserPage"),
    ])
    def test_label_extraction(self, raw, expected):
        assert _import_to_label(raw) == expected

    def test_php_use_statement_produces_a_graph_edge(self, tmp_path):
        """The unit test alone would not have caught the shipped state: every
        PHP import was dropped at label lookup, so every Laravel project in an
        index had an empty import graph."""
        _write(tmp_path, "composer.json", '{"require": {"laravel/framework": "^10"}}')
        _write(tmp_path, "app/Models/User.php",
               "<?php\nnamespace App\\Models;\nclass User {}\n")
        _write(tmp_path, "app/UserService.php", (
            "<?php\n"
            "namespace App;\n"
            "use App\\Models\\User;\n"
            "class UserService {\n"
            "    public function find(): User { return new User(); }\n"
            "}\n"
        ))
        G = build_graph([_scan(tmp_path, "php", "laravel", "php")],
                        apply_filters=False)
        assert G.has_edge("php::UserService", "php::User")


# ── R7: bare-name binding guards ──────────────────────────────────────────────

class TestRuntimeImportGuard:
    """G-0916-14 / G-0927-11: four services writing ``import java.util.List``
    made a domain ``model/List.java`` the repository's top hub."""

    def _java_corpus(self, tmp_path: Path, import_line: str) -> WaveResult:
        _write(tmp_path, "pom.xml", "<project/>")
        _write(tmp_path, "src/main/java/com/ex/model/List.java", (
            "package com.ex.model;\n"
            "import org.springframework.stereotype.Service;\n"
            "@Service\n"
            "public class List {\n"
            "    public String title() { return \"wishlist\"; }\n"
            "}\n"
        ))
        for name in ("Alpha", "Beta", "Gamma"):
            _write(tmp_path, f"src/main/java/com/ex/svc/{name}Service.java", (
                "package com.ex.svc;\n"
                f"{import_line}\n"
                "import org.springframework.stereotype.Service;\n"
                "@Service\n"
                f"public class {name}Service {{\n"
                "    private List items;\n"
                "}\n"
            ))
        return _scan(tmp_path, "app", "spring-boot", "java")

    def test_stdlib_import_does_not_bind_a_same_named_domain_class(self, tmp_path):
        G = build_graph([self._java_corpus(tmp_path, "import java.util.List;")],
                        apply_filters=False)
        into_list = [(u, v) for u, v, d in G.edges(data=True)
                     if v.endswith("::List")]
        assert into_list == [], into_list

    def test_a_real_project_import_of_the_same_name_still_binds(self, tmp_path):
        G = build_graph([self._java_corpus(tmp_path, "import com.ex.model.List;")],
                        apply_filters=False)
        into_list = {u for u, v, d in G.edges(data=True) if v.endswith("::List")}
        assert len(into_list) == 3, into_list


class TestGoRuntimeGuardScope:
    """Review finding R-1. The runtime guard for Go originally read "a first
    segment without a dot is stdlib" — which condemns every internal import of a
    module declared as ``module myapp``. Dotless module paths are still normal
    in private code (the indexed shotgun_code repo is one), so that heuristic
    silently dropped a whole project's internal import graph."""

    @pytest.mark.parametrize("path", [
        "myapp/internal/db", "myapp/pkg/handler", "shotgun_code/core",
        "internal/db", "github.com/x/y/models",
    ])
    def test_module_paths_are_not_runtime(self, path):
        from codebeacon.common.filters import is_runtime_import
        assert is_runtime_import(path, ".go") is False

    @pytest.mark.parametrize("path", [
        "fmt", "os", "net/http", "encoding/json", "path/filepath", "time",
        "context", "sync", "crypto/sha256",
    ])
    def test_real_stdlib_is_still_denied(self, path):
        from codebeacon.common.filters import is_runtime_import
        assert is_runtime_import(path, ".go") is True

    def test_dotless_module_import_binds_end_to_end(self, tmp_path):
        """The repro through the real extractor and builder. A Go import names
        a PACKAGE, so it can only reach a declaration through the label tier —
        which the runtime guard runs before. Deny the import and the edge is
        gone, with no second chance."""
        _write(tmp_path, "go.mod", "module myapp\n\ngo 1.22\n")
        _write(tmp_path, "internal/store/store.go",
               "package store\n\ntype Store struct{}\n")
        _write(tmp_path, "handler/handler.go", (
            "package handler\n\n"
            'import (\n\t"fmt"\n\t"myapp/internal/store"\n)\n\n'
            "type Handler struct{ s *store.Store }\n\n"
            "func Serve() { fmt.Println(store.Store{}) }\n"
        ))
        wave = _scan(tmp_path, "myapp", "gin", "go")
        assert "myapp/internal/store" in {e.target for e in wave.import_edges}

        G = build_graph([wave], apply_filters=False)
        assert G.has_edge("myapp::Handler", "myapp::Store"), (
            "the internal import was dropped as if it were stdlib",
            sorted(G.edges()))

    def test_stdlib_import_still_binds_nothing(self, tmp_path):
        """The other half of the guard: a domain package named like a stdlib
        one must not collect edges from files that only import the runtime."""
        _write(tmp_path, "go.mod", "module myapp\n\ngo 1.22\n")
        _write(tmp_path, "log/log.go", (
            "package log\n\ntype Entry struct{}\n\n"
            "func NewEntry() *Entry { return &Entry{} }\n"
        ))
        _write(tmp_path, "svc/svc.go", (
            "package svc\n\n"
            'import "log"\n\n'
            "type Svc struct{}\n\n"
            "func Run() { log.Println(\"x\") }\n"
        ))
        G = build_graph([_scan(tmp_path, "myapp", "gin", "go")],
                        apply_filters=False)
        log_nodes = [n for n, d in G.nodes(data=True)
                     if Path(d.get("source_file", "")).name == "log.go"]
        into_log = [(u, v) for u, v, d in G.edges(data=True) if v in log_nodes]
        assert into_log == [], into_log


class TestGenericSupertypeGuard:
    """G-0949-15: ``class AppError extends Exception`` registered
    ``Exception → [AppError]``, so a bare ``Exception`` reference from anywhere
    resolved to that unrelated class."""

    def test_extends_exception_does_not_make_a_class_the_resolution_target(self):
        st = SymbolTable()
        st.build([
            _node("api::AppError", "AppError", "/api/AppError.php",
                  metadata={"extends": ["Exception"]}),
            _node("api::Handler", "Handler", "/api/Handler.php"),
        ])
        assert st.resolve_ref(UnresolvedRef(
            source_node_id="api::Handler", ref_type="depends",
            ref_name="Exception", framework="laravel")) is None

    def test_a_real_interface_still_resolves(self):
        st = SymbolTable()
        st.build([
            _node("api::UserServiceImpl", "UserServiceImpl", "/api/UserServiceImpl.java",
                  metadata={"implements": ["UserService"]}),
            _node("api::OrderService", "OrderService", "/api/OrderService.java"),
        ])
        edge = st.resolve_ref(UnresolvedRef(
            source_node_id="api::OrderService", ref_type="depends",
            ref_name="UserService", framework="spring-boot"))
        assert edge is not None and edge.target == "api::UserServiceImpl"


class TestDiEvidenceGuard:
    """GI-2207 / G-0937-1: a DI reference carries nothing but a type name, so a
    Java service was wired to a React component in another project at full
    confidence."""

    def _nodes(self, target_file, target_project="web"):
        return [
            _node("orders::OrderService", "OrderService", "/repo/orders/OrderService.java"),
            _node(f"{target_project}::PaymentClient", "PaymentClient", target_file),
        ]

    def _ref(self):
        return UnresolvedRef(source_node_id="orders::OrderService",
                             ref_type="depends", ref_name="PaymentClient",
                             framework="spring-boot")

    def test_cross_language_bind_is_refused(self):
        st = SymbolTable()
        st.build(self._nodes("/repo/web/src/PaymentClient.tsx"))
        assert st.resolve_ref(self._ref()) is None

    def test_cross_project_bind_without_evidence_is_refused(self):
        st = SymbolTable()
        st.build(self._nodes("/repo/billing/PaymentClient.java", "billing"))
        assert st.resolve_ref(self._ref()) is None

    def test_cross_project_shared_library_still_binds(self):
        st = SymbolTable()
        st.build(
            self._nodes("/repo/shared/lib/PaymentClient.java", "shared"),
            project_roots={"shared": "/repo/shared", "orders": "/repo/orders"},
        )
        edge = st.resolve_ref(self._ref())
        assert edge is not None and edge.target == "shared::PaymentClient"
        assert edge.confidence == "INFERRED"

    def test_cross_project_bind_backed_by_a_real_import_is_allowed(self):
        st = SymbolTable()
        st.build(
            self._nodes("/repo/billing/PaymentClient.java", "billing"),
            import_edges=[_edge("orders::OrderService", "billing::PaymentClient")],
        )
        edge = st.resolve_ref(self._ref())
        assert edge is not None and edge.target == "billing::PaymentClient"

    def test_injects_is_filtered_cross_language_end_to_end(self):
        java = WaveResult(
            project=_project("orders", "/repo/orders"),
            services=[_svc("OrderService", "/repo/orders/OrderService.java",
                           deps=["PaymentClient"])],
        )
        web = WaveResult(
            project=_project("web", "/repo/web", "react", "typescript"),
            components=[ComponentInfo(name="PaymentClient", framework="react",
                                      source_file="/repo/web/src/PaymentClient.tsx",
                                      line=1)],
        )
        G = build_graph([java, web])
        assert [(u, v) for u, v, d in G.edges(data=True)
                if d.get("relation") == "injects"] == []


class TestAmbiguousInterfaceResolution:
    """R7d: with several implementations surviving the evidence check, picking
    one is a guess — and it flipped run to run purely on node order."""

    def _nodes(self):
        return [
            _node("app::OrderService", "OrderService", "/repo/app/OrderService.java"),
            _node("app::StripeGateway", "StripeGateway", "/repo/app/StripeGateway.java",
                  metadata={"implements": ["PaymentGateway"]}),
            _node("app::MockGateway", "MockGateway", "/repo/app/MockGateway.java",
                  metadata={"implements": ["PaymentGateway"]}),
        ]

    def _ref(self):
        return UnresolvedRef(source_node_id="app::OrderService", ref_type="depends",
                             ref_name="PaymentGateway", framework="spring-boot")

    def test_two_equally_plausible_impls_do_not_bind(self):
        st = SymbolTable()
        st.build(self._nodes())
        assert st.resolve_ref(self._ref()) is None

    def test_result_is_stable_across_node_orderings(self):
        nodes = self._nodes()
        results = []
        for order in ([0, 1, 2], [0, 2, 1], [2, 1, 0]):
            st = SymbolTable()
            st.build([nodes[i] for i in order])
            edge = st.resolve_ref(self._ref())
            results.append(edge.target if edge else None)
        assert len(set(results)) == 1, results

    def test_a_conventional_impl_binds_but_says_it_was_ambiguous(self):
        nodes = self._nodes()
        nodes[1] = _node("app::PaymentGatewayImpl", "PaymentGatewayImpl",
                         "/repo/app/PaymentGatewayImpl.java",
                         metadata={"implements": ["PaymentGateway"]})
        st = SymbolTable()
        st.build(nodes)
        edge = st.resolve_ref(self._ref())
        assert edge is not None
        assert edge.target == "app::PaymentGatewayImpl"
        assert edge.confidence == "AMBIGUOUS"


class TestPathConsistentImportBinding:
    """C-53b: ``from pkg.build import thing`` bound to a same-named symbol in a
    completely different file — 16 fabricated edges on codebeacon's own corpus,
    which then published a wrong entry in the CLAUDE.md high-impact list."""

    def test_module_import_never_binds_a_same_named_symbol_elsewhere(self, tmp_path):
        _write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
        _write(tmp_path, "pkg/__init__.py", "")
        _write(tmp_path, "pkg/build.py", "def make_thing(n: int):\n    return n\n")
        # A same-named declaration in a DIFFERENT file — the decoy the old
        # last-segment label match bound to.
        _write(tmp_path, "pkg/other.py", "def build(n: int):\n    return n\n")
        _write(tmp_path, "pkg/consumer.py",
               "from pkg.build import make_thing\n\n"
               "def go(n: int):\n    return make_thing(n)\n")
        G = build_graph([_scan(tmp_path, "pkg", "python", "python")],
                        apply_filters=False)
        targets = [v for u, v, d in G.edges(data=True)
                   if d.get("relation") == "imports_from" and u.endswith("::go")]
        assert targets, "the import edge disappeared entirely"
        for target in targets:
            assert Path(G.nodes[target]["source_file"]).name == "build.py", (
                target, G.nodes[target]["source_file"])


# ── V5-EXTRA-1: semantic reference edges reach the graph ──────────────────────

class TestSemanticReferenceRemap:
    def test_ast_reference_edge_is_remapped_onto_node_ids(self, tmp_path):
        """extract/semantic.py stamped a FILE PATH as the edge source, so every
        one of its edges was discarded by the builder: ``scan --semantic``
        added nothing at all to the graph."""
        _write(tmp_path, "pom.xml", "<project/>")
        _write(tmp_path, "src/main/java/com/ex/PaymentGateway.java", (
            "package com.ex;\n"
            "import org.springframework.stereotype.Service;\n"
            "@Service\n"
            "public class PaymentGateway {}\n"
        ))
        _write(tmp_path, "src/main/java/com/ex/OrderService.java", (
            "package com.ex;\n"
            "import org.springframework.stereotype.Service;\n"
            "/**\n * @see PaymentGateway\n */\n"
            "@Service\n"
            "public class OrderService {}\n"
        ))
        from codebeacon.discover.scanner import collect_files
        project = ProjectInfo(name="fx", path=str(tmp_path), framework="spring-boot",
                              language="java", signature_file="pom.xml")
        wave = auto_wave(project=project, files=collect_files(str(tmp_path)),
                         cache=None, semantic=True)
        assert any(e.relation == "references" for e in wave.import_edges), (
            "fixture did not produce a semantic reference to remap")
        G = build_graph([wave], apply_filters=False)
        refs = [(u, v) for u, v, d in G.edges(data=True)
                if d.get("relation") == "references"]
        assert refs == [("fx::OrderService", "fx::PaymentGateway")], refs


# ── CG-JS-MODULE-RESOLUTION ───────────────────────────────────────────────────

class TestTsConfigResolution:
    """G-0927-10 / GI-2340 / G-0949-18. Resolution used to be by last-path
    segment, so ``@/lib/utils`` looked for a declaration called ``utils`` and
    missed the ``cn`` it actually exports — 60.4% of a real Next.js app's
    internal imports were dropped with their target file sitting on disk."""

    def _app(self, tmp_path: Path, tsconfig: str, extra: dict | None = None,
             alias: str = "@") -> Path:
        """A minimal Next.js app importing ``cn`` through a path alias.

        ``alias`` defaults to ``@``; tests that need a genuine negative control
        pass ``~`` instead, because ``@/`` also has a config-free convention
        fallback and would resolve even with a broken tsconfig.
        """
        _write(tmp_path, "package.json", json.dumps({"name": "app",
                                                     "dependencies": {"next": "14"}}))
        _write(tmp_path, "tsconfig.json", tsconfig)
        _write(tmp_path, "src/lib/utils.ts",
               "export function cn(...parts: string[]) { return parts.join(' '); }\n")
        _write(tmp_path, "src/app/page.tsx", (
            f'import {{ cn }} from "{alias}/lib/utils";\n'
            "export default function Page() { return cn('a'); }\n"
        ))
        for rel, text in (extra or {}).items():
            _write(tmp_path, rel, text)
        return tmp_path

    def _edges(self, root: Path):
        G = build_graph([_scan(root, "app", "nextjs", "typescript")],
                        apply_filters=False)
        return G, sorted((u, v) for u, v, d in G.edges(data=True)
                         if d.get("relation") == "imports_from")

    def test_alias_resolves_to_the_symbol_not_the_file_basename(self, tmp_path):
        root = self._app(tmp_path, json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}))
        _, edges = self._edges(root)
        assert ("app::Page", "app::cn") in edges, edges

    def test_extends_chain_carries_base_url_and_paths(self, tmp_path):
        root = self._app(
            tmp_path,
            json.dumps({"extends": "./tsconfig.base.json"}),
            extra={"tsconfig.base.json": json.dumps(
                {"compilerOptions": {"baseUrl": ".", "paths": {"~/*": ["./src/*"]}}})},
            alias="~",
        )
        _, edges = self._edges(root)
        assert ("app::Page", "app::cn") in edges, edges

    def test_config_dir_placeholder_expands(self, tmp_path):
        root = self._app(tmp_path, json.dumps(
            {"compilerOptions": {"paths": {"~/*": ["${configDir}/src/*"]}}}), alias="~")
        _, edges = self._edges(root)
        assert ("app::Page", "app::cn") in edges, edges

    def test_jsonc_and_null_compiler_options_do_not_raise(self, tmp_path):
        root = self._app(tmp_path, (
            "{\n"
            "  // a comment, and a URL that must survive: https://example.com\n"
            "  /* block */\n"
            '  "compilerOptions": { "baseUrl": ".", "paths": { "~/*": ["./src/*"] }, },\n'
            "}\n"
        ), alias="~")
        _, edges = self._edges(root)
        assert ("app::Page", "app::cn") in edges, edges

        # ``"compilerOptions": null`` is valid JSON and crashed upstream's
        # loader on attribute access. Both the loader and a whole build over it
        # must survive.
        from codebeacon.graph.jsmodules import _load_alias_map
        _write(tmp_path, "tsconfig.json", json.dumps({"compilerOptions": None}))
        amap = _load_alias_map(str(tmp_path))
        assert amap.paths == {} and amap.base_url is None
        self._edges(root)  # must not raise

    def test_alias_map_is_reloaded_after_the_config_changes(self, tmp_path):
        """`codebeacon watch` and `serve` are long-lived: a cache that outlives
        one build would keep serving the alias map from before the edit."""
        # "~/" has no convention fallback, so this is a real negative control.
        root = self._app(
            tmp_path,
            json.dumps({"compilerOptions": {"baseUrl": ".",
                                            "paths": {"~/*": ["./nowhere/*"]}}}),
            alias="~",
        )
        _, before = self._edges(root)
        assert ("app::Page", "app::cn") not in before, before

        _write(root, "tsconfig.json", json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"~/*": ["./src/*"]}}}))
        _, after = self._edges(root)
        assert ("app::Page", "app::cn") in after, after

    def test_one_resolver_rechecks_the_config_by_mtime(self, tmp_path):
        """The per-build resolver above covers `scan`; this covers any caller
        that holds a resolver across a config edit, which is what makes the
        alias cache safe to reuse at all."""
        import os
        from codebeacon.graph.jsmodules import ModuleResolver

        root = self._app(tmp_path, json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"~/*": ["./nowhere/*"]}}}),
            alias="~")
        utils = str(root / "src/lib/utils.ts")
        page = str(root / "src/app/page.tsx")
        resolver = ModuleResolver([utils, page], {"app": str(root)})
        assert resolver.resolve("~/lib/utils", page) == ([], None)

        config = root / "tsconfig.json"
        config.write_text(json.dumps(
            {"compilerOptions": {"baseUrl": ".", "paths": {"~/*": ["./src/*"]}}}),
            encoding="utf-8")
        stamp = os.stat(config).st_mtime_ns + 1_000_000_000
        os.utime(config, ns=(stamp, stamp))
        assert resolver.resolve("~/lib/utils", page) == ([utils], None)

    def test_relative_import_resolves_without_any_config(self, tmp_path):
        _write(tmp_path, "package.json", json.dumps({"name": "app"}))
        _write(tmp_path, "src/lib/utils.ts", "export function cn() { return 1; }\n")
        _write(tmp_path, "src/app/page.tsx", (
            'import { cn } from "../lib/utils";\n'
            "export default function Page() { return cn(); }\n"
        ))
        _, edges = self._edges(tmp_path)
        assert ("app::Page", "app::cn") in edges, edges


class TestJsoncStripping:
    @pytest.mark.parametrize("text,expected", [
        ('{"a": 1 // trailing\n}', {"a": 1}),
        ('{"a": /* mid */ 1}', {"a": 1}),
        ('{"a": [1, 2,],}', {"a": [1, 2]}),
        ('{"url": "https://x/y"}', {"url": "https://x/y"}),
        ('{"path": "C:\\\\dir"}', {"path": "C:\\dir"}),
    ])
    def test_round_trip(self, text, expected):
        from codebeacon.graph.jsmodules import strip_jsonc
        assert json.loads(strip_jsonc(text)) == expected


# ── contracts the JS/TS extractor depends on (F5 interaction) ─────────────────

class TestQualifiedMemberLabels:
    """Object-literal members carry a QUALIFIED label (``userRepo.findById``)
    exactly so the import label tier cannot bind them: a bare ``create`` in the
    label map would be matched by any ``./create`` import in the repo. Node
    identity indexes labels and plain declaration names, and neither may strip
    the leading dot segment."""

    def _nodes(self):
        return [
            _node("web::Page", "Page", "/repo/web/src/page.tsx", ntype="component"),
            _node("web::userRepo", "userRepo", "/repo/web/src/repo.ts", ntype="component"),
            _node("web::userRepo.create", "userRepo.create", "/repo/web/src/repo.ts",
                  ntype="component", line=2),
        ]

    def test_bare_import_does_not_bind_a_qualified_member(self):
        remapped = _remap_import_edges(
            self._nodes(), [_edge("/repo/web/src/page.tsx", "./create")])
        assert [e.target for e in remapped] == []

    def test_the_container_is_still_reachable_by_its_own_name(self):
        remapped = _remap_import_edges(
            self._nodes(), [_edge("/repo/web/src/page.tsx", "./userRepo")])
        assert [e.target for e in remapped] == ["web::userRepo"]


class TestSameLineDeclarations:
    def test_members_sharing_one_line_still_get_a_searchable_region(self, tmp_path):
        """A one-line ``export const x = { a() {}, b() {} }`` puts several nodes
        on the same line; each must still see the line it is on, or the gate can
        never match it and every import falls back to the file-level anchor."""
        from codebeacon.graph.build import _BodyMentions
        src = _write(tmp_path, "repo.ts",
                     "import { db } from './db';\n"
                     "export const x = { a() { return db; }, b() { return 1; } };\n")
        file_to_nodes = {str(src): ["p::x", "p::x.a", "p::x.b"]}
        node_line = {"p::x": 2, "p::x.a": 2, "p::x.b": 2}
        mentions = _BodyMentions(file_to_nodes, node_line)
        assert mentions.mentioning(str(src), {"db"}) == ["p::x", "p::x.a", "p::x.b"]


# ── determinism of the remap itself ───────────────────────────────────────────

class TestRemapDeterminism:
    def test_target_choice_does_not_depend_on_node_order(self):
        """The candidate list was consumed in wave-completion order, so which
        same-named node an import bound to flipped between runs."""
        nodes = [
            _node("p::Consumer", "Consumer", "/repo/p/consumer.py"),
            _node("q::Widget", "Widget", "/repo/q/widget.py"),
            _node("r::Widget", "Widget", "/repo/r/widget.py"),
        ]
        edges = [_edge("/repo/p/consumer.py", "Widget")]
        picks = set()
        for order in ([0, 1, 2], [0, 2, 1], [2, 1, 0]):
            remapped = _remap_import_edges([nodes[i] for i in order], list(edges))
            picks.update(e.target for e in remapped if e.relation == "imports_from")
        assert len(picks) == 1, picks
