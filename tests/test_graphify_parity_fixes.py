"""Regression tests for 4 bugs found by auditing recent graphify changes.

Each test reproduces the original bug scenario, so reverting the fix flips
the assertion (mutation-verified).

| Bug | graphify ref | Fix module |
|---|---|---|
| Non-deterministic community IDs        | f5f3a1c | graph/cluster.py:_relabel_stable |
| ENAMETOOLONG on long node labels       | 690b4e5 | common/safety.py:cap_filename |
| Dropped DI edges (file-path ref source)| —*      | graph/build.py:_remap_unresolved_sources |
| Dead interface→impl DI resolution      | 88a8e3b | extract/services.py + graph/build.py |

*The third was surfaced while checking graphify ad0c8c0 (root-level symbol
 node IDs). codebeacon keys nodes ``project::Name`` rather than by file-path
 prefix, so ad0c8c0 itself does not apply — but the audit exposed a distinct,
 real bug: the per-file extractors stamp ``UnresolvedRef.source_node_id`` as
 ``file_path::Name``, which never matches a graph node, so binding-style DI
 edges (FastAPI Depends, Laravel bind, ASP.NET AddScoped) were silently lost.

The fourth mirrors graphify 88a8e3b (TS class heritage). SymbolTable read
``metadata["implements"]/["extends"]`` for interface→impl DI resolution, but no
extractor ever populated them — so the resolution path was dead in production.
The fix wires Spring/ASP.NET's already-captured interfaces into structured
fields and adds TS class-heritage capture for NestJS/Angular.
"""
from __future__ import annotations

import networkx as nx
import pytest

from codebeacon.common.safety import cap_filename
from codebeacon.common.types import ProjectInfo, ServiceInfo, UnresolvedRef
from codebeacon.export.obsidian import _safe_note_name
from codebeacon.extract.services import extract_services
from codebeacon.graph.build import build_graph
from codebeacon.graph.cluster import cluster, _relabel_stable
from codebeacon.wave import WaveResult
from codebeacon.wiki.generator import _safe_filename, generate_wiki


# ── Fix 1: deterministic community IDs (graphify f5f3a1c) ──────────────────────

class TestCommunityIdStability:
    def test_relabel_ties_broken_by_member_ids(self):
        """Equal-sized communities are ordered by their sorted member IDs, so the
        assignment is fully determined by the grouping — not the partitioner's
        enumeration order."""
        raw = {"E": 7, "F": 7, "A": 2, "B": 2, "C": 9, "D": 9}
        out = _relabel_stable(raw)
        # {A,B} < {C,D} < {E,F} lexicographically → 0, 1, 2.
        assert out == {"A": 0, "B": 0, "C": 1, "D": 1, "E": 2, "F": 2}

    def test_identical_groupings_get_identical_ids(self):
        """The same grouping expressed with different raw integer labels (and a
        different dict order) must collapse to the same final mapping."""
        run_a = _relabel_stable({"E": 7, "F": 7, "A": 2, "B": 2, "C": 9, "D": 9})
        run_b = _relabel_stable({"C": 0, "D": 0, "A": 5, "B": 5, "E": 1, "F": 1})
        assert run_a == run_b

    def test_larger_community_gets_lower_id(self):
        """Size is the primary key: the bigger community sorts first → ID 0."""
        out = _relabel_stable({"A": 3, "B": 3, "C": 3, "Z": 8})
        assert out["A"] == 0 and out["B"] == 0 and out["C"] == 0
        assert out["Z"] == 1

    def test_cluster_deterministic_under_node_permutation(self):
        """cluster() over an unchanged graph yields an identical node→community
        map regardless of the order nodes/edges were inserted in."""
        triangles = [("A", "B", "C"), ("D", "E", "F"), ("G", "H", "I")]

        def build(order):
            G = nx.DiGraph()
            for (x, y, z) in order:
                G.add_edges_from([(x, y), (y, z), (z, x)])
            return G

        forward = cluster(build(triangles))
        reversed_ = cluster(build(list(reversed(triangles))))
        assert forward == reversed_
        # Each disconnected triangle is its own community.
        assert len(set(forward.values())) == 3


# ── Fix 2: filename byte-cap (graphify 690b4e5) ────────────────────────────────

class TestFilenameByteCap:
    def test_short_label_untouched(self):
        assert cap_filename("UserService") == "UserService"

    def test_ascii_overflow_capped_to_byte_limit(self):
        out = cap_filename("A" * 300)
        assert len(out.encode("utf-8")) <= 200

    def test_cjk_byte_overflow_capped(self):
        """A character-count guard would pass 100 CJK chars; the byte guard must
        not (each char is 3 UTF-8 bytes = 300 bytes)."""
        out = cap_filename("가" * 100)
        assert len(out.encode("utf-8")) <= 200
        # Truncation must not leave a mangled half-character.
        out.encode("utf-8").decode("utf-8")  # raises if mojibake slipped in

    def test_long_shared_prefix_stays_distinct(self):
        a = cap_filename("z" * 250 + "_ALPHA")
        b = cap_filename("z" * 250 + "_BETA")
        assert a != b

    def test_wiki_safe_filename_is_capped(self):
        assert len(_safe_filename("X" * 400).encode("utf-8")) <= 200

    def test_obsidian_safe_note_name_is_capped(self):
        assert len(_safe_note_name("Y" * 400).encode("utf-8")) <= 200

    def test_generate_wiki_survives_pathological_label(self, tmp_path):
        """A 400-char class label must not crash wiki generation with
        ENAMETOOLONG; the article is written under a capped filename."""
        long_label = "Service" + "Z" * 400
        G = nx.DiGraph()
        G.add_node(
            "api::" + long_label,
            label=long_label,
            type="class",
            project="api",
            framework="fastapi",
            source_file="/projects/api/svc.py",
            line=1,
            community=0,
            annotations=["@Service"],
        )
        generate_wiki(G, {"api::" + long_label: 0}, str(tmp_path))  # no OSError
        written = list((tmp_path / "wiki").rglob("*.md"))
        assert written, "expected at least one wiki article"
        assert all(len(p.name.encode("utf-8")) <= 255 for p in written)


# ── Fix 3: file-path UnresolvedRef source remap (build.py) ─────────────────────

def _project(name: str = "api") -> ProjectInfo:
    return ProjectInfo(
        name=name, path=f"/projects/{name}",
        framework="fastapi", language="python", signature_file="requirements.txt",
    )


def _svc(name: str, source_file: str, deps: list[str] | None = None) -> ServiceInfo:
    return ServiceInfo(
        name=name, class_name=name, source_file=source_file, line=1,
        framework="fastapi", dependencies=deps or [],
    )


class TestUnresolvedSourceRemap:
    def test_filepath_source_remapped_creates_injects_edge(self):
        """FastAPI Depends(): the dependency is staged ONLY as a file-path
        UnresolvedRef (no svc.dependencies). Before the remap, the resolved edge
        carried source ``/projects/api/main.py::get_items`` — absent from the
        graph — and was dropped. It must now land as an injects edge."""
        wave = WaveResult(
            project=_project(),
            services=[
                _svc("get_items", "/projects/api/main.py"),
                _svc("get_db", "/projects/api/deps.py"),
            ],
            unresolved=[
                UnresolvedRef(
                    source_node_id="/projects/api/main.py::get_items",
                    ref_type="depends",
                    ref_name="get_db",
                    framework="fastapi",
                )
            ],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.has_edge("api::get_items", "api::get_db")
        assert G["api::get_items"]["api::get_db"]["relation"] == "injects"

    def test_binding_ref_remapped_by_name_when_file_differs(self):
        """Laravel/ASP.NET binding DI stamps the *registration site* file onto
        the ref, but the intended source is the implementation class declared
        elsewhere. The by-name fallback must still recover the edge."""
        wave = WaveResult(
            project=_project(),
            services=[
                _svc("UserRepo", "/projects/api/repos/UserRepo.php"),
                _svc("UserRepoInterface", "/projects/api/contracts/UserRepoInterface.php"),
            ],
            unresolved=[
                UnresolvedRef(
                    source_node_id="/projects/api/Provider.php::UserRepo",
                    ref_type="bind",
                    ref_name="UserRepoInterface",
                    framework="laravel",
                )
            ],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.has_edge("api::UserRepo", "api::UserRepoInterface")

    def test_already_correct_source_still_resolves(self):
        """A ref already in ``project::Name`` form (the Spring/NestJS path via
        svc.dependencies) must be left untouched and still resolve."""
        wave = WaveResult(
            project=_project(),
            services=[
                _svc("OrderService", "/projects/api/order.py", deps=["UserService"]),
                _svc("UserService", "/projects/api/user.py"),
            ],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.has_edge("api::OrderService", "api::UserService")

    def test_unresolvable_ref_is_dropped_not_crashed(self):
        """A file-path ref whose name matches no node resolves to nothing and is
        dropped silently — exactly as before — without raising."""
        wave = WaveResult(
            project=_project(),
            services=[_svc("Lonely", "/projects/api/lonely.py")],
            unresolved=[
                UnresolvedRef(
                    source_node_id="/projects/api/lonely.py::Ghost",
                    ref_type="depends",
                    ref_name="NoSuchThing",
                    framework="fastapi",
                )
            ],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.number_of_nodes() >= 1  # built cleanly, no edge invented
        assert not any(
            r == "injects" for *_, r in G.edges(data="relation")
        )


# ── Fix 4: interface→impl DI resolution (graphify 88a8e3b) ─────────────────────

def _impl_svc(name: str, source_file: str, implements=None, extends=None,
              deps=None) -> ServiceInfo:
    return ServiceInfo(
        name=name, class_name=name, source_file=source_file, line=1,
        framework="spring-boot", dependencies=deps or [],
        implements=implements or [], extends=extends or [],
    )


class TestInterfaceDiResolution:
    def test_interface_typed_dependency_resolves_to_implementer(self):
        """A class injects an *interface*; the concrete implementer carries it in
        structured ``implements`` metadata. SymbolTable must bridge the two into
        an injects edge. Before the fix, ``metadata["implements"]`` was never
        populated, so this resolution path was dead and no edge appeared."""
        wave = WaveResult(
            project=ProjectInfo(
                name="api", path="/projects/api", framework="spring-boot",
                language="java", signature_file="pom.xml",
            ),
            services=[
                _impl_svc("UserServiceImpl", "/projects/api/UserServiceImpl.java",
                          implements=["IUserService"]),
                _impl_svc("OrderService", "/projects/api/OrderService.java",
                          deps=["IUserService"]),
            ],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.has_edge("api::OrderService", "api::UserServiceImpl")
        assert G["api::OrderService"]["api::UserServiceImpl"]["relation"] == "injects"

    def test_implements_metadata_reaches_the_node(self):
        """The structured field must survive into node metadata (what
        SymbolTable reads) — not just live on the ServiceInfo."""
        wave = WaveResult(
            project=ProjectInfo(
                name="api", path="/projects/api", framework="spring-boot",
                language="java", signature_file="pom.xml",
            ),
            services=[_impl_svc("FooImpl", "/projects/api/FooImpl.java",
                                implements=["IFoo"], extends=["BaseFoo"])],
        )
        G = build_graph([wave], apply_filters=False)
        assert G.nodes["api::FooImpl"].get("implements") == ["IFoo"]
        assert G.nodes["api::FooImpl"].get("extends") == ["BaseFoo"]

    def test_heritage_unions_across_files(self):
        """A class re-declared across two files (same dir) must union its
        ``implements`` — the cross-file merge must treat them like methods."""
        proj = ProjectInfo(
            name="api", path="/projects/api", framework="spring-boot",
            language="csharp", signature_file="api.csproj",
        )
        wave = WaveResult(
            project=proj,
            services=[
                _impl_svc("Repo", "/projects/api/Repo.cs", implements=["IRead"]),
                _impl_svc("Repo", "/projects/api/Repo.cs", implements=["IWrite"]),
            ],
        )
        G = build_graph([wave], apply_filters=False)
        impls = set(G.nodes["api::Repo"].get("implements", []))
        assert {"IRead", "IWrite"} <= impls

    def test_nestjs_class_heritage_captured(self, tmp_path):
        """NestJS extends/implements must be captured against the real
        tree-sitter-typescript grammar (guards against grammar drift)."""
        src = tmp_path / "user.service.ts"
        src.write_text(
            "import { Injectable } from '@nestjs/common';\n"
            "export class BaseRepo {}\n"
            "@Injectable()\n"
            "export class UserService extends BaseRepo "
            "implements IUserService, OnModuleInit {\n"
            "  constructor(private readonly mailer: MailerService) {}\n"
            "}\n",
            encoding="utf-8",
        )
        services, _ = extract_services(str(src), "nestjs")
        us = {s.name: s for s in services}.get("UserService")
        assert us is not None
        assert us.extends == ["BaseRepo"]
        assert "IUserService" in us.implements and "OnModuleInit" in us.implements
        # Constructor DI is unaffected by the heritage addition.
        assert "MailerService" in us.dependencies

    def test_angular_class_heritage_captured(self, tmp_path):
        src = tmp_path / "auth.service.ts"
        src.write_text(
            "import { Injectable } from '@angular/core';\n"
            "@Injectable({providedIn:'root'})\n"
            "export class AuthService extends BaseAuth implements CanActivate {\n"
            "  constructor(private http: HttpClient) {}\n"
            "}\n",
            encoding="utf-8",
        )
        services, _ = extract_services(str(src), "angular")
        a = {s.name: s for s in services}.get("AuthService")
        assert a is not None
        assert a.extends == ["BaseAuth"]
        assert a.implements == ["CanActivate"]
