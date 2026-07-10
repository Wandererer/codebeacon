"""Regression tests for the 0.6.9 graph + filter audit (group F-A).

Covers eight confirmed defects:

  G01  casefold import resolution folds a SCREAMING_SNAKE constant (CONFIG)
       onto a same-spelled type (class Config) → false god-node hub.
  G04  import edges bind across language families (Python `import time`
       → a TS `time` component under a shared-marker dir).
  G08  enrich_shared_db iterates an unordered set, so shared_entities order
       (and the singular shared_entity) is PYTHONHASHSEED-dependent.
  BH-G1 binding-DI ref remap ignores project affinity → self-loop wired to
       the wrong project's same-named class.
  BH-G2 same-dir declaration merge collapses different node types (a Go GORM
       model extracted as both a class service AND an entity) → entity lost.
  BH-G4 surprising_connections misclassifies legitimate invokes_command (IPC)
       edges as unexpected coupling.
  BH-S1 filter_build_artifacts matches ancestor directory names in the
       absolute path → the whole graph is erased under a `build/` checkout.
  BH-S2 _is_shared_lib matches ancestor directory names → filter_cross_service
       wrongly keeps spurious cross-service edges under a `core/` checkout.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import networkx as nx
import pytest

from codebeacon.common.types import (
    ComponentInfo, EntityInfo, Edge, ProjectInfo, ServiceInfo, UnresolvedRef, Node,
)
from codebeacon.common.filters import (
    families_compatible,
    filter_build_artifacts,
    filter_cross_language,
    filter_cross_service,
    _is_shared_lib,
)
from codebeacon.graph.build import build_graph, _remap_unresolved_sources
from codebeacon.graph.enrich import enrich_shared_db
from codebeacon.graph.analyze import surprising_connections
from codebeacon.wave import WaveResult


# ── helpers ───────────────────────────────────────────────────────────────────

def _project(name="api", framework="fastapi", path=None, language="python"):
    return ProjectInfo(
        name=name, path=path or f"/projects/{name}",
        framework=framework, language=language, signature_file="req.txt",
    )


def _svc(name, source_file, framework="fastapi", deps=None, implements=None,
         methods=None):
    return ServiceInfo(
        name=name, class_name=name, source_file=source_file, line=1,
        framework=framework, dependencies=deps or [],
        implements=implements or [], methods=methods or [],
    )


def _fnode(nid, source_file, ntype="class", project=""):
    return Node(id=nid, label=nid, type=ntype, source_file=source_file, line=1,
                metadata={"project": project} if project else {})


def _fedge(src, tgt, relation="imports"):
    return Edge(source=src, target=tgt, relation=relation, confidence="EXTRACTED",
                confidence_score=1.0, source_file="")


# ── G01: casefold constant/type collision ─────────────────────────────────────

class TestG01CasefoldConstantCollision:
    def test_screaming_snake_import_does_not_fold_onto_type(self):
        """`from app_settings import CONFIG` must NOT create an imports_from edge
        onto a same-spelled `class Config` — CONFIG is a module constant, not a
        casefolded alias of the type."""
        w = WaveResult(
            project=_project(),
            services=[_svc("Consumer", "/projects/api/consumer.py")],
            entities=[EntityInfo(name="Config", table_name="config",
                                 source_file="/projects/api/config_model.py",
                                 line=1, framework="sqlalchemy")],
            import_edges=[Edge(
                source="/projects/api/consumer.py",
                target="app_settings.CONFIG",
                relation="imports_from", confidence="EXTRACTED",
                confidence_score=1.0, source_file="/projects/api/consumer.py",
            )],
        )
        G = build_graph([w], apply_filters=False)
        bad = [
            (s, t) for s, t, d in G.edges(data=True)
            if d.get("relation") == "imports_from" and t == "api::Config"
        ]
        assert bad == [], f"casefold folded CONFIG onto the Config type: {bad}"

    def test_lowercase_alias_prefers_declaration_over_constant(self):
        """G01 ruling: when a lowercase alias `./path` has BOTH a non-all-caps
        declaration (`Path`) and an all-caps constant (`PATH`) sharing the
        casefolded name, prefer the declaration and never bind the constant
        (reverse Path→PATH direction)."""
        w = WaveResult(
            project=_project(),
            services=[
                _svc("Consumer", "/projects/api/consumer.py"),
                _svc("Path", "/projects/api/path_model.py"),   # declaration
                # a node whose LABEL is the SCREAMING_SNAKE constant PATH
                _svc("PATH", "/projects/api/constants.py"),
            ],
            import_edges=[Edge(
                source="/projects/api/consumer.py", target="./path",
                relation="imports_from", confidence="EXTRACTED",
                confidence_score=1.0, source_file="/projects/api/consumer.py",
            )],
        )
        G = build_graph([w], apply_filters=False)
        targets = {
            t for s, t, d in G.edges(data=True)
            if d.get("relation") == "imports_from" and s == "api::Consumer"
        }
        assert "api::Path" in targets, f"lowercase alias did not bind Path: {targets}"
        assert "api::PATH" not in targets, (
            f"lowercase alias folded onto the constant PATH: {targets}"
        )

    def test_lowercase_alias_resolves_onto_only_allcaps_acronym(self):
        """G01 ruling: an all-caps label is as often a legit acronym *type*
        (API/HTTP/URL/PDF) as a module constant, so when it is the ONLY
        candidate a lowercase path alias `./api` must still resolve onto a
        component literally named `API` — the isupper() candidate filter must
        never drop the fallback to zero and erase a real dependency edge."""
        w = WaveResult(
            project=_project("ui", "react", language="typescript"),
            services=[_svc("Caller", "/proj/caller.tsx", framework="react")],
            components=[ComponentInfo(name="API", source_file="/proj/api.tsx",
                                      line=1, framework="react")],
            import_edges=[Edge(
                source="/proj/caller.tsx", target="./api",
                relation="imports_from", confidence="EXTRACTED",
                confidence_score=1.0, source_file="/proj/caller.tsx",
            )],
        )
        G = build_graph([w], apply_filters=False)
        ok = any(
            t == "ui::API" and d.get("relation") == "imports_from"
            for _, t, d in G.edges(data=True)
        )
        assert ok, "lowercase alias api→API was dropped by the isupper filter"

    def test_intended_mixed_case_alias_still_resolves(self):
        """The feature the casefold fallback exists for — a path alias
        `@/utils/card` resolving to component `Card` — must keep working."""
        w = WaveResult(
            project=_project("ui", "react", language="typescript"),
            services=[_svc("Caller", "/proj/caller.tsx", framework="react")],
            components=[ComponentInfo(name="Card", source_file="/proj/Card.tsx",
                                      line=1, framework="react")],
            import_edges=[Edge(
                source="/proj/caller.tsx", target="@/utils/card",
                relation="imports_from", confidence="EXTRACTED",
                confidence_score=1.0, source_file="/proj/caller.tsx",
            )],
        )
        G = build_graph([w], apply_filters=False)
        ok = any(
            t == "ui::Card" and d.get("relation") == "imports_from"
            for _, t, d in G.edges(data=True)
        )
        assert ok, "intended card→Card casefold alias regressed"


# ── G04: cross-language import binding ────────────────────────────────────────

class TestG04CrossLanguageBinding:
    def test_python_import_does_not_bind_to_ts_component(self):
        """A Python `import time` must not bind across the language boundary to
        an unrelated TS component literally named `time`."""
        api = WaveResult(
            project=_project("api", "fastapi", path="/repo/api"),
            services=[_svc("Handler", "/repo/api/handlers.py")],
            import_edges=[Edge(
                source="/repo/api/handlers.py", target="time",
                relation="imports_from", confidence="EXTRACTED",
                confidence_score=1.0, source_file="/repo/api/handlers.py",
            )],
        )
        ui = WaveResult(
            project=_project("ui", "react", path="/repo/ui", language="typescript"),
            components=[ComponentInfo(name="time",
                                      source_file="/repo/ui/src/lib/time.tsx",
                                      line=1, framework="react")],
        )
        G = build_graph([api, ui], apply_filters=True)
        cross = [
            (s, t) for s, t, d in G.edges(data=True)
            if d.get("relation") == "imports_from" and t == "ui::time"
        ]
        assert cross == [], f"python→ts cross-language edge survived: {cross}"

    def test_filter_generalizes_beyond_java_ts(self):
        """filter_cross_language now drops any different-family import, e.g.
        Python ↔ Go, not just the old hardcoded Java↔TS pair."""
        nodes = {
            "py": _fnode("py", "svc/handler.py"),
            "go": _fnode("go", "svc/handler.go"),
        }
        assert filter_cross_language([_fedge("py", "go", "imports")], nodes) == []
        # same family preserved
        nodes2 = {"a": _fnode("a", "a.py"), "b": _fnode("b", "b.py")}
        assert len(filter_cross_language([_fedge("a", "b", "imports")], nodes2)) == 1

    def test_re_exports_cross_language_is_dropped(self):
        """re_exports edges are now inspected by the language filter (they
        previously bypassed it entirely)."""
        nodes = {
            "jvm": _fnode("jvm", "src/A.java"),
            "web": _fnode("web", "src/b.ts"),
        }
        assert filter_cross_language([_fedge("jvm", "web", "re_exports")], nodes) == []

    def test_families_compatible_semantics(self):
        assert families_compatible(".py", ".pyi")      # same family
        assert families_compatible(".py", ".weird")    # unknown target → keep
        assert not families_compatible(".py", ".tsx")  # different families


# ── G08: shared_db enrichment determinism ─────────────────────────────────────

class TestG08SharedDbDeterminism:
    def test_shared_entities_sorted_and_seed_independent(self, tmp_path):
        """enrich_shared_db must emit shared_entities in a deterministic order
        regardless of PYTHONHASHSEED (it iterated an unordered set)."""
        script = textwrap.dedent(
            """
            import json
            import networkx as nx
            from codebeacon.graph.enrich import enrich_shared_db

            G = nx.DiGraph()
            G.add_node("projA::ClassA", label="ClassA", type="class",
                       project="projA", source_file="/repo/a/ClassA.py", line=1)
            G.add_node("projB::ClassB", label="ClassB", type="class",
                       project="projB", source_file="/repo/b/ClassB.py", line=1)
            ents = [f"projA::Ent{i}" for i in range(8)]
            for e in ents:
                G.add_node(e, label=e.split("::")[1], type="entity",
                           project="projA", source_file="/repo/shared/x.py", line=1)
            for e in ents:
                G.add_edge("projA::ClassA", e, relation="imports")
                G.add_edge("projB::ClassB", e, relation="imports")
            enrich_shared_db(G)
            link = G["projA::ClassA"]["projB::ClassB"]
            print(json.dumps({
                "shared_entities": link["shared_entities"],
                "shared_entity": link["shared_entity"],
            }))
            """
        )

        def run(seed):
            out = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, env=_env_with_seed(seed),
            )
            assert out.returncode == 0, out.stderr
            return json.loads(out.stdout)

        a = run("1")
        b = run("2")
        assert a == b, f"shared_db enrichment differs across hash seeds:\n{a}\n{b}"
        assert a["shared_entities"] == sorted(a["shared_entities"])
        assert a["shared_entity"] == sorted(a["shared_entities"])[0]

    def test_shared_entities_accumulation_is_sorted_in_process(self):
        """A same-pair collision accumulates shared_entities in sorted order."""
        G = nx.DiGraph()
        G.add_node("p1::A", label="A", type="class", project="p1",
                   source_file="/r/a.py", line=1)
        G.add_node("p2::B", label="B", type="class", project="p2",
                   source_file="/r/b.py", line=1)
        ents = ["p1::Zeta", "p1::Alpha", "p1::Mike"]
        for e in ents:
            G.add_node(e, label=e.split("::")[1], type="entity", project="p1",
                       source_file="/r/shared.py", line=1)
            G.add_edge("p1::A", e, relation="imports")
            G.add_edge("p2::B", e, relation="imports")
        enrich_shared_db(G)
        got = G["p1::A"]["p2::B"]["shared_entities"]
        assert got == sorted(got) == ["p1::Alpha", "p1::Mike", "p1::Zeta"]


def _env_with_seed(seed):
    import os
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    return env


# ── BH-G1: DI binding project affinity ────────────────────────────────────────

class TestBHG1BindingProjectAffinity:
    def _waves(self):
        billing = WaveResult(
            project=_project("billing", "aspnet", path="/repo/billing", language="csharp"),
            services=[_svc("Logger", "/repo/billing/Logger.cs", framework="aspnet")],
        )
        shipping = WaveResult(
            project=_project("shipping", "aspnet", path="/repo/shipping", language="csharp"),
            services=[_svc("Logger", "/repo/shipping/Services/Logger.cs",
                           framework="aspnet", implements=["ILogger"])],
            unresolved=[UnresolvedRef(
                source_node_id="/repo/shipping/Startup.cs::Logger",
                ref_type="bind", ref_name="ILogger", framework="aspnet",
            )],
        )
        return billing, shipping

    def test_binding_resolves_to_registering_project_not_first_project(self):
        billing, shipping = self._waves()
        G = build_graph([billing, shipping], apply_filters=True)
        injects = [(s, t) for s, t, d in G.edges(data=True)
                   if d.get("relation") == "injects"]
        assert injects, "DI binding edge was dropped entirely"
        for s, t in injects:
            assert not (s == "billing::Logger" and t == "billing::Logger"), (
                "binding wired to the WRONG (billing) project's same-named class"
            )
        assert any("shipping::" in s or "shipping::" in t for s, t in injects), (
            "binding did not reference the registering shipping project"
        )

    def test_result_is_independent_of_wave_order(self):
        billing, shipping = self._waves()
        g1 = build_graph([billing, shipping], apply_filters=True)
        billing2, shipping2 = self._waves()  # fresh refs (remap mutates in place)
        g2 = build_graph([shipping2, billing2], apply_filters=True)

        def injects(g):
            return sorted((s, t) for s, t, d in g.edges(data=True)
                          if d.get("relation") == "injects")

        assert injects(g1) == injects(g2) == [("shipping::Logger", "shipping::Logger")]

    def test_equidistant_registration_tie_broken_by_sorted_id(self):
        """BH-G1 ruling: when the DI registration file is EQUIDISTANT from two
        same-named impls in different projects (a composition-root Startup.cs
        outside both impl subtrees), the source remap must pick a deterministic
        winner (lexicographically smallest node id) rather than whichever wave
        was ingested first — pinning the 'order-free' contract on a real tie."""
        billing = _fnode("billing::Logger", "/repo/billing/Logger.cs",
                         project="billing")
        shipping = _fnode("shipping::Logger", "/repo/shipping/Logger.cs",
                          project="shipping")
        reg = "/repo/bootstrap/Startup.cs::Logger"  # equidistant from both impls

        def remap(node_order):
            ref = UnresolvedRef(
                source_node_id=reg, ref_type="bind",
                ref_name="ILogger", framework="aspnet",
            )
            _remap_unresolved_sources(node_order, [ref])
            return ref.source_node_id

        first = remap([billing, shipping])
        second = remap([shipping, billing])
        assert first == second == "billing::Logger", (first, second)


# ── #48: beacon.json node order must be byte-reproducible ──────────────────────

class TestNodeOrderDeterminism:
    def _wave(self, order):
        svcs = [
            _svc("Zebra", "/repo/app/zebra.py"),
            _svc("Alpha", "/repo/app/alpha.py"),
            _svc("Mango", "/repo/app/mango.py"),
        ]
        return WaveResult(
            project=_project("app", path="/repo/app"),
            services=[svcs[i] for i in order],
        )

    def test_node_sequence_independent_of_input_order(self):
        """build_graph must insert nodes in stable id order so beacon.json is
        byte-reproducible run-to-run, independent of ThreadPoolExecutor
        wave-completion order (#48)."""
        g1 = build_graph([self._wave([0, 1, 2])], apply_filters=True)
        g2 = build_graph([self._wave([2, 0, 1])], apply_filters=True)
        assert list(g1.nodes()) == list(g2.nodes())
        # specifically the id-sorted order
        assert list(g1.nodes()) == sorted(g1.nodes())
        assert list(g1.nodes()) == ["app::Alpha", "app::Mango", "app::Zebra"]


# ── BH-G2: cross-type same-dir collapse ───────────────────────────────────────

class TestBHG2CrossTypeCollapse:
    def test_same_dir_service_and_entity_coexist(self):
        """A service Foo and an entity Foo in the SAME directory are distinct
        symbols and must both survive — not collapse into one class node."""
        w = WaveResult(
            project=_project(),
            services=[_svc("Foo", "/projects/api/models/foo_service.rb",
                           framework="active-record", methods=["do_work"])],
            entities=[EntityInfo(name="Foo", table_name="foos",
                                 source_file="/projects/api/models/foo.rb", line=1,
                                 framework="active-record",
                                 fields=[{"name": "id", "type": "int",
                                          "annotations": []}])],
        )
        G = build_graph([w], apply_filters=False)
        types = sorted(d.get("type") for _, d in G.nodes(data=True))
        assert "class" in types and "entity" in types, types
        assert G.number_of_nodes() == 2
        # the class keeps its method; the entity keeps its fields + table_name
        class_id = next(n for n, d in G.nodes(data=True) if d["type"] == "class")
        entity_id = next(n for n, d in G.nodes(data=True) if d["type"] == "entity")
        assert G.nodes[class_id].get("methods") == ["do_work"]
        assert [f["name"] for f in G.nodes[entity_id].get("fields", [])] == ["id"]
        assert G.nodes[entity_id].get("table_name") == "foos"
        # and the entity did not inherit the service's methods
        assert not G.nodes[entity_id].get("methods")

    def test_go_gorm_model_service_and_entity_both_survive(self):
        """The guaranteed Go/GORM trigger: one model extracted as a class
        service AND a gorm entity from the same file."""
        w = WaveResult(
            project=_project("app", "gin", path="/repo/app", language="go"),
            services=[_svc("User", "/repo/app/user.go", framework="gin")],
            entities=[EntityInfo(name="User", table_name="", line=1,
                                 source_file="/repo/app/user.go", framework="gorm",
                                 fields=[{"name": "Name", "type": "string",
                                          "annotations": []}])],
        )
        G = build_graph([w], apply_filters=True)
        entity_nodes = [n for n, d in G.nodes(data=True) if d["type"] == "entity"]
        assert entity_nodes, "GORM entity was dropped by the cross-type collapse"

    def test_same_type_same_dir_still_merges(self):
        """Guard against over-correction: two SAME-type declarations in the same
        dir (Ruby reopened class / Swift extension) must still merge, not split."""
        w = WaveResult(
            project=_project(),
            entities=[
                EntityInfo(name="User", table_name="users", line=1,
                           source_file="/proj/User.swift", framework="fluent",
                           fields=[{"name": "id", "type": "Int", "annotations": []}]),
                EntityInfo(name="User", table_name="users", line=1,
                           source_file="/proj/User+Profile.swift", framework="fluent",
                           fields=[{"name": "name", "type": "String",
                                    "annotations": []}]),
            ],
        )
        G = build_graph([w], apply_filters=False)
        assert G.number_of_nodes() == 1
        names = {f["name"] for f in G.nodes["api::User"].get("fields", [])}
        assert names == {"id", "name"}


# ── BH-G4: IPC edges are not "surprising" ─────────────────────────────────────

class TestBHG4IpcNotSurprising:
    def _ipc_graph(self):
        G = nx.DiGraph()
        G.add_node("frontend::Page", type="component", label="Page",
                   project="desktop", source_file="desktop/+page.svelte")
        G.add_node("src-tauri::get_config", type="route", method="INVOKE",
                   label="get_config [INVOKE /tauri/get_config]", project="src-tauri",
                   source_file="src-tauri/commands.rs")
        G.add_edge("frontend::Page", "src-tauri::get_config",
                   relation="invokes_command", confidence="EXTRACTED",
                   confidence_score=1.0, source_file="desktop/+page.svelte")
        return G, {"frontend::Page": 0, "src-tauri::get_config": 1}

    def test_invokes_command_excluded(self):
        G, comm = self._ipc_graph()
        assert surprising_connections(G, comm) == []

    def test_injects_still_surprising(self):
        """The exclusion is targeted — an unexpected injects edge across
        communities is still reported."""
        G = nx.DiGraph()
        G.add_node("a::A", label="A")
        G.add_node("b::B", label="B")
        G.add_edge("a::A", "b::B", relation="injects")
        res = surprising_connections(G, {"a::A": 0, "b::B": 1})
        assert len(res) == 1 and res[0].relation == "injects"


# ── BH-S1: artifact filter must not match ancestor dirs ───────────────────────

class TestBHS1ArtifactAncestor:
    def test_checkout_under_build_dir_keeps_graph(self):
        """A repo checked out under an ancestor literally named `build` must not
        have its entire graph erased."""
        root = "/Users/ci/build/my-repo"     # 'build' is an ANCESTOR of the root
        w = WaveResult(
            project=_project("app", "spring-boot", path=root, language="java"),
            services=[
                _svc("UserController", f"{root}/src/main/java/UserController.java",
                     framework="spring-boot", deps=["UserService"]),
                _svc("UserService", f"{root}/src/main/java/UserService.java",
                     framework="spring-boot"),
            ],
        )
        G = build_graph([w], apply_filters=True)
        assert G.number_of_nodes() == 2, "graph erased by ancestor 'build' dir"

    def test_in_project_build_dir_still_filtered(self):
        """A genuine build/ directory INSIDE the project is still excluded."""
        root = "/Users/ci/build/my-repo"
        w = WaveResult(
            project=_project("app", "spring-boot", path=root, language="java"),
            services=[
                _svc("Gen", f"{root}/build/generated/Gen.java", framework="spring-boot"),
                _svc("Real", f"{root}/src/main/java/Real.java", framework="spring-boot"),
            ],
        )
        G = build_graph([w], apply_filters=True)
        assert sorted(G.nodes()) == ["app::Real"]

    def test_filter_unit_relativizes_to_root(self):
        root = "/home/x/output/proj"
        nodes = [_fnode("app::A", f"{root}/src/A.java", project="app")]
        keep, _ = filter_build_artifacts(nodes, [], {"app": root})
        assert len(keep) == 1  # ancestor 'output' below-root check strips it
        # and without a root, the ancestor still (legacy) matches — proving the
        # root is what fixes it
        drop, _ = filter_build_artifacts(nodes, [], None)
        assert len(drop) == 0


# ── BH-S2: shared-lib heuristic must not match ancestor dirs ──────────────────

class TestBHS2SharedLibAncestor:
    def test_false_cross_service_edge_dropped_under_core_root(self):
        """A false cross-service edge (svc-a importing a symbol that only exists
        in svc-b, target NOT a genuine shared lib) must still be dropped when the
        repo is checked out under an ancestor named `core`. End-to-end through
        build_graph, which now derives project_roots from project.path."""
        croot = "/home/dev/core/monorepo"
        pa = _project("svc-a", "react", path=f"{croot}/service-a", language="typescript")
        pb = _project("svc-b", "react", path=f"{croot}/service-b", language="typescript")
        wa = WaveResult(
            project=pa,
            components=[ComponentInfo(name="Widget",
                                      source_file=f"{croot}/service-a/src/Widget.tsx",
                                      line=1, framework="react")],
            # imports "Bridge", a name that resolves ONLY to svc-b → a genuine
            # cross-service edge that reaches filter_cross_service.
            import_edges=[Edge(
                source=f"{croot}/service-a/src/Widget.tsx", target="./Bridge",
                relation="imports_from", confidence="EXTRACTED", confidence_score=1.0,
                source_file=f"{croot}/service-a/src/Widget.tsx")],
        )
        wb = WaveResult(
            project=pb,
            components=[ComponentInfo(name="Bridge",
                                      source_file=f"{croot}/service-b/src/Bridge.tsx",
                                      line=1, framework="react")],
        )
        G = build_graph([wa, wb], apply_filters=True)
        cross = [(s, t) for s, t, d in G.edges(data=True)
                 if d.get("relation") == "imports_from"]
        assert cross == [], f"false cross-service edge kept under 'core' root: {cross}"

    def test_genuine_shared_lib_below_root_still_kept(self):
        """A target genuinely under a `shared/` dir INSIDE the project must
        still be treated as a shared library and preserved."""
        root = "/home/dev/core/mono"
        nodes = {
            "svc-a::Widget": _fnode("svc-a::Widget", f"{root}/svc-a/Widget.tsx",
                                    project="svc-a"),
            "shared::Utils": _fnode("shared::Utils", f"{root}/shared/utils/Utils.ts",
                                    ntype="class", project="shared"),
        }
        roots = {"svc-a": f"{root}/svc-a", "shared": f"{root}/shared"}
        service_roots = {"svc-a::Widget": "svc-a", "shared::Utils": "shared"}
        edges = [_fedge("svc-a::Widget", "shared::Utils", "imports")]
        kept = filter_cross_service(edges, nodes, service_roots, roots)
        assert len(kept) == 1

    def test_is_shared_lib_ignores_ancestor_when_root_given(self):
        f = "/home/user/common/repo/svc/src/Foo.java"
        assert _is_shared_lib(f, root="/home/user/common/repo/svc") is False
        # real shared segment below root is still detected
        g = "/home/user/common/repo/svc/shared/Foo.java"
        assert _is_shared_lib(g, root="/home/user/common/repo/svc") is True
