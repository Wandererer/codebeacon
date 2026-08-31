"""0.7.1 audit — pipeline / wave / write regressions (fixer F3).

* CB-V6-1  wave serialisation dropped ``ServiceInfo.implements`` / ``.extends``
  on the dataclass→dict→dataclass round trip that every extraction takes (it is
  the AST-cache payload format). Heritage metadata therefore never reached
  graph/build.py, so interface→impl dependency injection could not resolve:
  ``@Service class UserServiceImpl implements UserService`` + a controller
  asking for ``UserService`` produced zero ``injects`` edges.

* CB-WAVE-ORDER-NONDET  chunk results were merged in completion order, so
  label-collision winners (and therefore node ids and wiki filenames) flipped
  between runs on an unchanged corpus.

* CB-SHRINK-GUARD  the guard compared two integers and was waived by the mere
  presence of ``--update``, which disarmed it on precisely the unattended paths
  (watch, hooks, CI). It is now an identity + per-source diff: see the class
  docstrings below for the four directions it has to get right.

* GI-2276  edge loss was invisible — a rebuild that kept every node but dropped
  most edges wrote silently.

* GI-2988 / R10  ``built_at_ts`` was stamped with ``time.time()`` on every
  write, so a no-op rebuild always dirtied a committed ``beacon.json``.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from codebeacon.common.types import ProjectInfo, ServiceInfo
from codebeacon.extract.services import extract_services
from codebeacon.graph.build import build_graph
from codebeacon.graph.write import load_beacon, write_beacon
from codebeacon.wave import (
    WAVE_PAYLOAD_SCHEMA,
    _dict_to_service,
    _extract_file,
    _service_to_dict,
    auto_wave,
)


# ── CB-V6-1 — heritage metadata survives the wave round trip ─────────────────

SPRING_INTERFACE = """package com.x;

public interface UserService {
    String find(String id);
}
"""

SPRING_IMPL = """package com.x;

import org.springframework.stereotype.Service;

@Service
public class UserServiceImpl implements UserService {
    public String find(String id) { return id; }
}
"""

SPRING_CONTROLLER = """package com.x;

import org.springframework.stereotype.Component;

@Component
public class UserController {
    private final UserService userService;
    public UserController(UserService userService) { this.userService = userService; }
}
"""


def _mk_spring_project(tmp_path):
    """A Spring Boot project whose controller depends on an *interface* that a
    single ``@Service`` implements — the shape that exercises interface→impl DI."""
    root = tmp_path / "api"
    src = root / "src" / "main" / "java" / "com" / "x"
    src.mkdir(parents=True)
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    files = []
    for name, body in (
        ("UserService.java", SPRING_INTERFACE),
        ("UserServiceImpl.java", SPRING_IMPL),
        ("UserController.java", SPRING_CONTROLLER),
    ):
        p = src / name
        p.write_text(body, encoding="utf-8")
        files.append(str(p))
    project = ProjectInfo(
        name="api", path=str(root), framework="spring-boot",
        language="java", signature_file="pom.xml",
    )
    return project, sorted(files)


class TestServiceRoundTrip:
    def test_round_trip_preserves_implements_and_extends(self):
        svc = ServiceInfo(
            name="UserServiceImpl", class_name="UserServiceImpl",
            source_file="/x/UserServiceImpl.java", line=4,
            framework="spring-boot",
            methods=["find"], dependencies=[], annotations=["Service"],
            implements=["UserService"], extends=["BaseService"],
        )
        rt = _dict_to_service(_service_to_dict(svc))
        assert rt.implements == ["UserService"]
        assert rt.extends == ["BaseService"]

    def test_serialiser_covers_every_dataclass_field(self):
        """A future ServiceInfo field must not be silently dropped the way
        implements/extends were: the dict has to name every field."""
        svc = ServiceInfo(
            name="S", class_name="S", source_file="/x/S.java", line=1,
            framework="spring-boot",
        )
        payload = set(_service_to_dict(svc))
        declared = {f.name for f in dataclasses.fields(ServiceInfo)}
        assert declared - payload == set(), (
            "ServiceInfo fields missing from the wave payload: "
            f"{sorted(declared - payload)}"
        )

    def test_extraction_carries_heritage_into_the_graph(self, tmp_path):
        """End-to-end: extractor → wave → graph. Before the fix the node's
        implements list was empty and the injects edge did not exist."""
        project, files = _mk_spring_project(tmp_path)

        # The extractor itself was always right — pin that, so a failure here
        # points at extract/, not at the serialiser under test.
        impl = [f for f in files if f.endswith("UserServiceImpl.java")][0]
        svcs, _ = extract_services(impl, "spring-boot")
        assert svcs[0].implements == ["UserService"]

        wave = auto_wave(project=project, files=files)
        by_name = {s.name: s for s in wave.services}
        assert by_name["UserServiceImpl"].implements == ["UserService"]

        graph = build_graph([wave])
        assert graph.nodes["api::UserServiceImpl"]["implements"] == ["UserService"]
        injects = [
            (u, v) for u, v, d in graph.edges(data=True)
            if d.get("relation") == "injects"
        ]
        assert ("api::UserController", "api::UserServiceImpl") in injects


class TestWavePayloadSchema:
    def test_stale_payload_is_a_miss_not_a_hit(self, tmp_path):
        """A cache entry written by a pre-fix codebeacon lacks implements/extends.
        Its content hash still matches, so only the schema stamp can reject it."""
        from codebeacon.cache import Cache

        project, files = _mk_spring_project(tmp_path)
        impl = [f for f in files if f.endswith("UserServiceImpl.java")][0]
        outdir = str(tmp_path / ".codebeacon")

        cache = Cache(outdir, project_root=str(project.path))
        stale = {
            "routes": [], "entities": [], "components": [],
            "import_edges": [], "unresolved": [],
            "services": [{
                "name": "UserServiceImpl", "class_name": "UserServiceImpl",
                "source_file": impl, "line": 4, "framework": "spring-boot",
                "methods": [], "dependencies": [], "annotations": ["Service"],
            }],
        }
        cache.put(impl, stale, cache.file_hash(impl), framework="spring-boot")

        result = _extract_file(impl, "spring-boot", str(project.path), cache=cache)
        assert not result.get("_cache_hit")
        assert result["services"][0]["implements"] == ["UserService"]

    def test_current_payload_still_hits(self, tmp_path):
        """The stamp must not defeat caching for entries this version wrote."""
        from codebeacon.cache import Cache

        project, files = _mk_spring_project(tmp_path)
        impl = [f for f in files if f.endswith("UserServiceImpl.java")][0]
        outdir = str(tmp_path / ".codebeacon")

        cache = Cache(outdir, project_root=str(project.path))
        first = _extract_file(impl, "spring-boot", str(project.path), cache=cache)
        assert first["_schema"] == WAVE_PAYLOAD_SCHEMA
        second = _extract_file(impl, "spring-boot", str(project.path), cache=cache)
        assert second["_cache_hit"] is True
        assert second["services"][0]["implements"] == ["UserService"]


# ── CB-SHRINK-GUARD — identity + per-source accounting ───────────────────────

def _mk_corpus(tmp_path, names):
    """A project root holding one trivial source file per name."""
    root = tmp_path / "src"
    root.mkdir(exist_ok=True)
    paths = []
    for name in names:
        p = root / name
        p.write_text(f"# {name}\n", encoding="utf-8")
        paths.append(str(p))
    return root, paths


def _code_graph(root, names, *, edges=(), node_type="class"):
    """A graph whose nodes are attributed to real files under ``root``."""
    G = nx.DiGraph()
    for name in names:
        G.add_node(
            f"p::{name}", label=name, type=node_type, project="p",
            source_file=str(root / name), line=1,
        )
    for u, v in edges:
        G.add_edge(
            f"p::{u}", f"p::{v}", relation="calls",
            confidence="EXTRACTED", confidence_score=1.0, source_file="",
        )
    return G


class TestShrinkGuardAllowsExplainedLoss:
    """A shrink the run can attribute to a real cause must go through, loudly.

    Before the redesign these needed ``--update`` (which disarmed the guard for
    everything else) or, for the ignore case, hit an unrecoverable rc=1."""

    def test_deleted_source_is_waived_and_reported(self, tmp_path, capsys):
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py", "c.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py", "c.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        (root / "c.py").unlink()
        survivors = [f for f in files if not f.endswith("c.py")]
        wr = write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                          project_roots={"p": str(root)}, corpus=survivors)

        assert wr.skipped_shrink is False
        assert wr.audit.deleted_sources and not wr.audit.unexplained_sources
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 2
        err = capsys.readouterr().err
        assert "1 source file(s) deleted" in err
        assert "c.py" in err

    def test_newly_ignored_source_is_waived(self, tmp_path, capsys):
        """R3: an ignore rule that drops files is allowed and loud — no --force.

        This is the dead end from the verifier's repro: adding a pattern to
        .codebeaconignore and re-scanning used to exit 1 and write nothing."""
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py", "c.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py", "c.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        # c.py is still on disk; it just is not collected any more.
        kept = [f for f in files if not f.endswith("c.py")]
        wr = write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                          project_roots={"p": str(root)}, corpus=kept)

        assert wr.skipped_shrink is False
        assert wr.audit.excluded_sources and not wr.audit.unexplained_sources
        assert "newly excluded by ignore rules" in capsys.readouterr().err


class TestShrinkGuardRefusesUnexplainedLoss:
    """The directions that must still refuse — including under ``--update``."""

    def test_extractor_regression_refuses(self, tmp_path, capsys):
        """The file was collected and re-extracted, yet its nodes are gone.
        Nothing about the corpus changed, so the extractor did."""
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py", "c.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py", "c.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        wr = write_beacon(_code_graph(root, ["a.py"]), out,
                          project_roots={"p": str(root)}, corpus=files)

        assert wr.skipped_shrink is True
        assert wr.audit.unexplained == 2
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 3, "prior graph must survive"
        err = capsys.readouterr().err
        assert "--force" in err, "the message must name a real CLI flag"

    def test_incomplete_run_cannot_claim_exclusion(self, tmp_path, capsys):
        """G-0918-1: an unreadable subtree looks exactly like an ignore rule —
        its files are on disk and absent from the corpus. When the run admits it
        could not see everything, that inference is withdrawn."""
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py", "c.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py", "c.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        kept = [f for f in files if not f.endswith("c.py")]
        wr = write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                          project_roots={"p": str(root)}, corpus=kept,
                          incomplete=True)

        assert wr.skipped_shrink is True
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 3
        assert "could not read the whole tree" in capsys.readouterr().err

    def test_deletion_is_still_waived_when_incomplete(self, tmp_path):
        """Incompleteness must not turn a genuine deletion into a refusal:
        an unreadable directory still exists(), a deleted file does not."""
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        (root / "b.py").unlink()
        wr = write_beacon(_code_graph(root, ["a.py"]), out,
                          project_roots={"p": str(root)},
                          corpus=[files[0]], incomplete=True)
        assert wr.skipped_shrink is False

    def test_force_overrides_and_says_so(self, tmp_path, capsys):
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py", "c.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py", "c.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        wr = write_beacon(_code_graph(root, ["a.py"]), out, force=True,
                          project_roots={"p": str(root)}, corpus=files)

        assert wr.skipped_shrink is False
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 1
        assert "--force: overwriting despite" in capsys.readouterr().err

    def test_overlay_writer_without_corpus_cannot_drop_code_nodes(self, tmp_path):
        """G-0927-2: the knowledge/semantic writers supply no corpus because
        they only ever add. If one loses code nodes, that is a bug, not a
        rebuild — and it must not be able to overwrite the graph."""
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        wr = write_beacon(_code_graph(root, ["a.py"]), out,
                          project_roots={"p": str(root)})
        assert wr.skipped_shrink is True


class TestShrinkGuardTiers:
    """Overlay nodes are minted by a different pass; they take no part in the
    baseline in either direction."""

    def test_scan_after_knowledge_does_not_wedge(self, tmp_path, capsys):
        """G-0935-1: the documented 0.7.0 workflow is scan → knowledge → rescan.
        Counting the overlay made the rescan exit 1 and write nothing at all."""
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"

        enriched = _code_graph(root, ["a.py", "b.py"])
        for i in range(3):
            enriched.add_node(
                f"knowledge::note{i}", label=f"note{i}", type="knowledge",
                project="", source_file=f"docs/note{i}.md", line=1,
            )
        write_beacon(enriched, out, project_roots={"p": str(root)}, corpus=files)
        assert json.loads((out / "beacon.json").read_text())["meta"]["node_count"] == 5

        # A plain code-only rescan: 5 → 2 total nodes, but the code tier is intact.
        wr = write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                          project_roots={"p": str(root)}, corpus=files)
        assert wr.skipped_shrink is False
        assert wr.audit.prior_overlay == 3
        assert wr.audit.prior_baseline == 2
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 2

    def test_external_stubs_do_not_count(self, tmp_path):
        """``external`` nodes are edge stubs minted by graph/build.py; they
        disappear with the edge that created them and are not a loss."""
        root, files = _mk_corpus(tmp_path, ["a.py"])
        out = tmp_path / "out"
        G = _code_graph(root, ["a.py"])
        G.add_node("requests", label="requests", type="external",
                   source_file="", line=0, project="")
        G.add_edge("p::a.py", "requests", relation="imports",
                   confidence="INFERRED", confidence_score=0.5, source_file="")
        write_beacon(G, out, project_roots={"p": str(root)}, corpus=files)

        wr = write_beacon(_code_graph(root, ["a.py"]), out,
                          project_roots={"p": str(root)}, corpus=files)
        assert wr.skipped_shrink is False


class TestEdgeAccounting:
    """GI-2276 — a rebuild that keeps every node but loses most edges used to
    write silently and report the post-loss count as an ordinary result."""

    def test_edge_collapse_warns_with_stable_nodes(self, tmp_path, capsys):
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py", "c.py", "d.py"])
        out = tmp_path / "out"
        names = ["a.py", "b.py", "c.py", "d.py"]
        rich = _code_graph(root, names, edges=[
            ("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "d.py"),
            ("a.py", "c.py"), ("a.py", "d.py"), ("b.py", "d.py"),
        ])
        write_beacon(rich, out, project_roots={"p": str(root)}, corpus=files)

        poor = _code_graph(root, names, edges=[("a.py", "b.py")])
        wr = write_beacon(poor, out, project_roots={"p": str(root)}, corpus=files)

        assert wr.skipped_shrink is False, "edge loss warns, it does not refuse"
        err = capsys.readouterr().err
        assert "edge count collapsed 6 → 1" in err
        assert "node set held steady" in err

    def test_stable_edges_are_quiet(self, tmp_path, capsys):
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"
        G = _code_graph(root, ["a.py", "b.py"], edges=[("a.py", "b.py")])
        write_beacon(G, out, project_roots={"p": str(root)}, corpus=files)
        capsys.readouterr()
        write_beacon(G, out, project_roots={"p": str(root)}, corpus=files)
        assert "collapsed" not in capsys.readouterr().err


class TestBuiltAtTimestamp:
    """GI-2988 / R10 — a no-op rebuild must not dirty a committed beacon.json."""

    def test_noop_rebuild_is_byte_identical(self, tmp_path, monkeypatch):
        """The clock must not leak into the artifact. Two writes a second apart
        used to differ in exactly one field, which is enough to dirty a
        committed beacon.json on every hook-driven rebuild — so the wall clock
        is advanced here rather than relied upon to stand still."""
        import codebeacon.graph.write as write_mod

        ticks = iter(range(1_700_000_000, 1_700_001_000, 37))
        monkeypatch.setattr(write_mod.time, "time", lambda: next(ticks))

        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)
        first = (out / "beacon.json").read_bytes()

        write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)
        assert (out / "beacon.json").read_bytes() == first

    def test_real_change_updates_the_graph(self, tmp_path):
        """The stability must not extend to a genuinely different graph."""
        root, files = _mk_corpus(tmp_path, ["a.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        root2, files2 = _mk_corpus(tmp_path, ["a.py", "b.py"])
        write_beacon(_code_graph(root2, ["a.py", "b.py"]), out,
                     project_roots={"p": str(root2)}, corpus=files2)
        data = json.loads((out / "beacon.json").read_text())
        assert data["meta"]["node_count"] == 2

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_timestamp_follows_the_commit(self, tmp_path):
        """In a git repo the stamp is the commit's own time, so two machines
        building the same commit produce the same bytes."""
        root = tmp_path / "repo"
        root.mkdir()
        run = lambda *a: subprocess.run(a, cwd=root, capture_output=True, check=True)
        run("git", "init", "-q")
        run("git", "config", "user.email", "t@example.com")
        run("git", "config", "user.name", "T")
        (root / "a.py").write_text("# a\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-qm", "init")
        commit_ts = int(subprocess.run(
            ["git", "show", "-s", "--format=%ct", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True).stdout.strip())

        out = root / ".codebeacon"
        wr = write_beacon(_code_graph(root, ["a.py"]), out, repo_path=root,
                          project_roots={"p": str(root)}, corpus=[str(root / "a.py")])
        meta = json.loads((out / "beacon.json").read_text())["meta"]
        assert meta["built_at_ts"] == commit_ts
        assert meta["built_at_commit"] == wr.built_at_commit


# ── G-0921-7 — the guard must stay armed on the unattended paths ─────────────

FASTAPI_MAIN = """from fastapi import FastAPI
app = FastAPI()

@app.get('/a')
def a():
    return 1
"""

FASTAPI_MOD = """from fastapi import APIRouter
router = APIRouter()

@router.get('/m{n}')
def h{n}():
    return 1
"""


def _fastapi_project(tmp_path, n_mods=3):
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (root / "app" / "main.py").write_text(FASTAPI_MAIN, encoding="utf-8")
    for i in range(n_mods):
        (root / "app" / f"mod{i}.py").write_text(
            FASTAPI_MOD.format(n=i), encoding="utf-8")
    return ProjectInfo(
        name="proj", path=str(root), framework="fastapi",
        language="python", signature_file="requirements.txt",
    )


def _scan_args(**over):
    import argparse
    base = dict(
        update=False, semantic=False, exclude=[], max_failure_rate=None,
        force=False, obsidian_dir=None,
        # The wiki/obsidian/context-map exporters are irrelevant here and are
        # owned by other fixers in this tree; keep the test on the graph path.
        output_wiki=False, output_obsidian=False, context_map_targets=[],
    )
    base.update(over)
    return argparse.Namespace(**base)


class TestGuardStaysArmedUnderUpdate:
    """G-0921-7: the waiver was ``had_explicit_deletions=args.update``, i.e. the
    guard was off whenever ``--update`` was passed — which is how watch, the
    post-commit hook and CI all invoke a scan."""

    def test_update_does_not_disarm_the_guard(self, tmp_path, monkeypatch, capsys):
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path)
        out = str(tmp_path / "proj" / ".codebeacon")
        assert pipeline.run_pipeline([project], out, _scan_args()) == 0
        before = json.loads(
            (tmp_path / "proj" / ".codebeacon" / "beacon.json").read_text()
        )["meta"]["node_count"]
        assert before > 1

        # Simulate an extractor regression: every file is still collected and
        # re-extracted, but the router modules now yield nothing. Their contents
        # are edited first so the incremental cache misses them — otherwise the
        # second run serves the good cached payloads and nothing shrinks, which
        # would make this test pass for the wrong reason.
        for i in range(3):
            p = tmp_path / "proj" / "app" / f"mod{i}.py"
            p.write_text(p.read_text(encoding="utf-8") + "\n# touched\n",
                         encoding="utf-8")

        import codebeacon.extract.routes as routes_mod
        real = routes_mod.extract_routes

        def crippled(file_path, framework, project_path=None):
            if "mod" in file_path:
                return []
            return real(file_path, framework, project_path)

        monkeypatch.setattr(routes_mod, "extract_routes", crippled)

        rc = pipeline.run_pipeline([project], out, _scan_args(update=True))

        assert rc == 1, "an unexplained shrink under --update must fail the run"
        after = json.loads(
            (tmp_path / "proj" / ".codebeacon" / "beacon.json").read_text()
        )["meta"]["node_count"]
        assert after == before, "the prior graph must be left intact"
        assert "--force" in capsys.readouterr().err

    def test_update_after_real_deletion_still_succeeds(self, tmp_path, capsys):
        """The bookend: the guard must not make ordinary deletions painful."""
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path)
        out = str(tmp_path / "proj" / ".codebeacon")
        assert pipeline.run_pipeline([project], out, _scan_args()) == 0
        before = json.loads(
            (tmp_path / "proj" / ".codebeacon" / "beacon.json").read_text()
        )["meta"]["node_count"]

        (tmp_path / "proj" / "app" / "mod0.py").unlink()
        rc = pipeline.run_pipeline([project], out, _scan_args(update=True))

        assert rc == 0
        after = json.loads(
            (tmp_path / "proj" / ".codebeacon" / "beacon.json").read_text()
        )["meta"]["node_count"]
        assert after < before
        assert "source file(s) deleted" in capsys.readouterr().err


# ── R2 — a code-only rescan must not silently drop the knowledge overlay ─────

class TestKnowledgeOverlayReapply:
    """The documented 0.7.0 workflow is scan → knowledge → (re)scan. The rescan
    rebuilds the graph from source alone, so without a reapply step it discards
    every note node the link pass added."""

    def _with_notes(self, tmp_path):
        project = _fastapi_project(tmp_path, n_mods=1)
        notes = tmp_path / "proj" / "docs"
        notes.mkdir()
        (notes / "adr-001.md").write_text(
            "# ADR 001: routing\n\nWe route through `app/main.py`.\n",
            encoding="utf-8",
        )
        return project

    def test_rescan_restores_the_overlay(self, tmp_path):
        from codebeacon import pipeline
        from codebeacon.knowledge.generator import build_knowledge_map
        from codebeacon.knowledge.link import link_knowledge_to_graph

        project = self._with_notes(tmp_path)
        out = tmp_path / "proj" / ".codebeacon"
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0

        # The user opts in by running `codebeacon knowledge` once.
        result = build_knowledge_map(Path(project.path), Path(project.path))
        linked = link_knowledge_to_graph(result, out)
        assert linked is not None and linked.knowledge_nodes > 0
        graph, _ = load_beacon(out / "beacon.json")
        before = {n for n, d in graph.nodes(data=True) if d.get("type") == "knowledge"}
        assert before

        # A plain rescan afterwards: the code graph is rebuilt from source, and
        # the overlay has to come back with it.
        assert pipeline.run_pipeline([project], str(out), _scan_args(update=True)) == 0
        graph2, _ = load_beacon(out / "beacon.json")
        after = {n for n, d in graph2.nodes(data=True) if d.get("type") == "knowledge"}
        assert after == before, "the note overlay was dropped by the rescan"

    def test_repo_without_notes_is_untouched(self, tmp_path, capsys):
        """No opt-in, no overlay, no noise."""
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=1)
        out = tmp_path / "proj" / ".codebeacon"
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0
        assert "Knowledge overlay" not in capsys.readouterr().out
        graph, _ = load_beacon(out / "beacon.json")
        assert not [n for n, d in graph.nodes(data=True) if d.get("type") == "knowledge"]

    def test_unbuildable_overlay_does_not_fail_the_scan_or_double_warn(
        self, tmp_path, monkeypatch, capsys
    ):
        """F10's contract: reapply_knowledge never raises and reports its own
        failures, signalling them with -1. The scan carries on, and the caller
        must NOT add a second warning on top of the one already printed."""
        from codebeacon import pipeline
        import codebeacon.knowledge.link as link_mod

        project = _fastapi_project(tmp_path, n_mods=1)
        out = tmp_path / "proj" / ".codebeacon"

        def unbuildable(root, outdir):
            print("  Warning: knowledge overlay not reapplied (notes missing).",
                  file=sys.stderr)
            return -1

        monkeypatch.setattr(link_mod, "reapply_knowledge", unbuildable)
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0

        captured = capsys.readouterr()
        assert captured.err.count("not reapplied") == 1, "duplicated warning"
        assert "Knowledge overlay reapplied" not in captured.out

    def test_zero_notes_is_silent(self, tmp_path, monkeypatch, capsys):
        """0 means this repo never opted in — no output at all."""
        from codebeacon import pipeline
        import codebeacon.knowledge.link as link_mod

        project = _fastapi_project(tmp_path, n_mods=1)
        out = tmp_path / "proj" / ".codebeacon"
        monkeypatch.setattr(link_mod, "reapply_knowledge", lambda root, outdir: 0)
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0
        captured = capsys.readouterr()
        assert "Knowledge overlay" not in captured.out
        assert "Knowledge overlay" not in captured.err

    def test_reapplied_count_is_reported(self, tmp_path, monkeypatch, capsys):
        from codebeacon import pipeline
        import codebeacon.knowledge.link as link_mod

        project = _fastapi_project(tmp_path, n_mods=1)
        out = tmp_path / "proj" / ".codebeacon"
        monkeypatch.setattr(link_mod, "reapply_knowledge", lambda root, outdir: 7)
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0
        assert "Knowledge overlay reapplied: 7 notes" in capsys.readouterr().out


class TestShrinkGuardSurvivesRelabelling:
    """Node ids are a derived naming scheme, not the data. This release changes
    how colliding declarations are disambiguated (R8), which renames nodes
    without losing any — the guard must not read that as mass deletion."""

    def test_renamed_ids_with_same_sources_are_not_a_loss(self, tmp_path):
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        # Same files, same node count per file, entirely different ids.
        renamed = nx.DiGraph()
        for name in ["a.py", "b.py"]:
            renamed.add_node(
                f"p::pkg/{name}@ab12", label=name, type="class", project="p",
                source_file=str(root / name), line=1,
            )
        wr = write_beacon(renamed, out, project_roots={"p": str(root)}, corpus=files)

        assert wr.skipped_shrink is False
        assert wr.audit.unexplained == 0
        graph, _ = load_beacon(out / "beacon.json")
        assert set(graph.nodes) == {"p::pkg/a.py@ab12", "p::pkg/b.py@ab12"}

    def test_a_file_losing_one_of_its_nodes_is_still_caught(self, tmp_path):
        """The bookend: per-source accounting must not become a blanket waiver.
        Two nodes from one file dropping to one is still an unexplained loss."""
        root, files = _mk_corpus(tmp_path, ["a.py"])
        out = tmp_path / "out"
        G = nx.DiGraph()
        for cls in ("Alpha", "Beta"):
            G.add_node(f"p::{cls}", label=cls, type="class", project="p",
                       source_file=str(root / "a.py"), line=1)
        write_beacon(G, out, project_roots={"p": str(root)}, corpus=files)

        smaller = nx.DiGraph()
        smaller.add_node("p::Alpha", label="Alpha", type="class", project="p",
                         source_file=str(root / "a.py"), line=1)
        wr = write_beacon(smaller, out, project_roots={"p": str(root)}, corpus=files)

        assert wr.skipped_shrink is True
        assert wr.audit.unexplained == 1


class TestPipelineWiring:
    """The guard is only as good as what the pipeline hands it."""

    def test_newly_ignored_file_no_longer_dead_ends(self, tmp_path, capsys):
        """G-0916-2 end-to-end: adding a pattern to .codebeaconignore and
        re-scanning used to exit 1, write nothing, and advise passing a
        ``force=True`` Python kwarg that no CLI flag exposed. It needs the
        corpus to reach write_beacon to be recognised as an exclusion."""
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=3)
        out = str(tmp_path / "proj" / ".codebeacon")
        assert pipeline.run_pipeline([project], out, _scan_args()) == 0
        before = json.loads(
            (tmp_path / "proj" / ".codebeacon" / "beacon.json").read_text()
        )["meta"]["node_count"]

        (tmp_path / "proj" / ".codebeaconignore").write_text(
            "app/mod*.py\n", encoding="utf-8")
        rc = pipeline.run_pipeline([project], out, _scan_args())

        assert rc == 0, "an ignore rule is a legitimate reason to shrink"
        after = json.loads(
            (tmp_path / "proj" / ".codebeacon" / "beacon.json").read_text()
        )["meta"]["node_count"]
        assert after < before
        assert "newly excluded by ignore rules" in capsys.readouterr().err

    def test_extraction_failures_mark_the_run_incomplete(self):
        """The signal the guard leans on to stay armed. A wave that lost files
        to extractor errors cannot be used to conclude anything about what the
        corpus deliberately excludes."""
        from codebeacon.pipeline import _run_is_incomplete
        from codebeacon.wave import ExtractionFailure, WaveResult

        clean = WaveResult(project=None, file_count=3)
        assert _run_is_incomplete([clean]) is False

        degraded = WaveResult(project=None, file_count=3)
        degraded.failures.append(ExtractionFailure(
            file_path="/x/a.py", framework="fastapi",
            error="boom", error_type="ValueError",
        ))
        assert _run_is_incomplete([degraded]) is True
        assert _run_is_incomplete([clean, degraded]) is True

    def test_unreadable_dirs_mark_the_run_incomplete(self, monkeypatch):
        """The other half of the contract: whatever the discover layer reports
        as unwalkable also arms the guard. Read defensively, because an absent
        hook must degrade to "nothing known", never to a crash mid-scan."""
        from codebeacon import pipeline
        from codebeacon.wave import WaveResult

        clean = WaveResult(project=None, file_count=1)
        monkeypatch.setattr(pipeline, "_unreadable_subtrees", lambda: [])
        assert pipeline._run_is_incomplete([clean]) is False

        monkeypatch.setattr(pipeline, "_unreadable_subtrees", lambda: ["/x/locked"])
        assert pipeline._run_is_incomplete([clean]) is True

    def test_missing_discover_hook_is_not_an_error(self, monkeypatch):
        from codebeacon.pipeline import _unreadable_subtrees
        import codebeacon.diagnostics as diag
        import codebeacon.discover.scanner as scanner

        monkeypatch.delattr(diag, "unreadable_dirs", raising=False)
        monkeypatch.delattr(scanner, "unreadable_dirs", raising=False)
        assert _unreadable_subtrees() == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
class TestUnreadableSubtree:
    """G-0918-1 in its original form. The subtle part is that a file under a
    chmod-000 directory reports as *absent*: ``os.path.exists`` swallows EACCES
    exactly like ENOENT, so a naive on-disk check calls the whole subtree
    'deleted' and waives the very loss the guard exists to catch."""

    def test_unreadable_file_is_not_mistaken_for_a_deleted_one(self, tmp_path):
        from codebeacon.graph.write import _classify_loss, _path_state

        locked = tmp_path / "locked"
        locked.mkdir()
        victim = locked / "a.py"
        victim.write_text("# a\n", encoding="utf-8")
        os.chmod(locked, 0o000)
        try:
            assert os.path.exists(victim) is False, (
                "precondition: this is why the naive check was wrong"
            )
            assert _path_state(str(victim)) == "unknown"
            assert _classify_loss(str(victim), set(), incomplete=True) == "unexplained"
        finally:
            os.chmod(locked, 0o755)

        victim.unlink()
        assert _path_state(str(victim)) == "absent"
        assert _classify_loss(str(victim), set(), incomplete=True) == "deleted"

    def test_guard_refuses_a_shrink_behind_an_unreadable_dir(self, tmp_path):
        root = tmp_path / "src"
        root.mkdir()
        (root / "keep.py").write_text("# keep\n", encoding="utf-8")
        locked = root / "locked"
        locked.mkdir()
        (locked / "gone.py").write_text("# gone\n", encoding="utf-8")

        out = tmp_path / "out"
        G = nx.DiGraph()
        for rel in ("keep.py", "locked/gone.py"):
            G.add_node(f"p::{rel}", label=rel, type="class", project="p",
                       source_file=str(root / rel), line=1)
        write_beacon(G, out, project_roots={"p": str(root)},
                     corpus=[str(root / "keep.py"), str(root / "locked" / "gone.py")])

        os.chmod(locked, 0o000)
        try:
            shrunk = nx.DiGraph()
            shrunk.add_node("p::keep.py", label="keep.py", type="class",
                            project="p", source_file=str(root / "keep.py"), line=1)
            wr = write_beacon(shrunk, out, project_roots={"p": str(root)},
                              corpus=[str(root / "keep.py")], incomplete=True)
        finally:
            os.chmod(locked, 0o755)

        assert wr.skipped_shrink is True, "silent loss behind an unreadable dir"
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 2


# ── Lead ruling — overlay writes are audited for ADDITIVITY, not per-source ──

class TestOverlayWrite:
    """An overlay pass (`codebeacon knowledge`, `semantic apply`) loads
    beacon.json, adds its own tier and writes back. Per-source accounting
    cannot judge it: the document it loaded stores project-RELATIVE paths and
    it has no project_roots to put them back with, so every prior node resolved
    to nothing and a pure ADD was reported as total loss."""

    def _scanned(self, tmp_path):
        root = tmp_path / "src"
        root.mkdir()
        for name in ("A.java", "B.java"):
            (root / name).write_text(f"class {name[0]} {{}}\n", encoding="utf-8")
        out = tmp_path / ".codebeacon"
        G = nx.DiGraph()
        for name in ("A.java", "B.java"):
            G.add_node(f"p::{name[0]}", label=name[0], type="class", project="p",
                       source_file=str(root / name), line=1)
        G.add_edge("p::A", "p::B", relation="calls", confidence="EXTRACTED",
                   confidence_score=1.0, source_file="")
        write_beacon(G, out, repo_path=tmp_path, project_roots={"p": str(root)},
                     corpus=[str(root / "A.java"), str(root / "B.java")])
        return root, out

    def test_pure_add_is_not_reported_as_loss(self, tmp_path, capsys):
        root, out = self._scanned(tmp_path)
        graph, _ = load_beacon(out / "beacon.json")
        # Exactly what knowledge/link.py does — note the relative source paths
        # it reads back, and that it passes no project_roots.
        assert graph.nodes["p::A"]["source_file"] == "A.java"
        graph.add_node("knowledge::n.md", label="N", type="knowledge",
                       project="knowledge", source_file="n.md", line=1)
        graph.add_edge("knowledge::n.md", "p::A", relation="references",
                       confidence="EXTRACTED", confidence_score=1.0, source_file="")

        wr = write_beacon(graph, out, repo_path=tmp_path, overlay_write=True)

        assert wr.skipped_shrink is False
        assert wr.audit.unexplained == 0
        after, _ = load_beacon(out / "beacon.json")
        assert after.number_of_nodes() == 3
        err = capsys.readouterr().err
        assert "unexplained" not in err and "--force" not in err

    def test_overlay_dropping_a_node_is_refused_even_with_force(self, tmp_path, capsys):
        """force is for a rebuild whose shrink the accounting cannot explain.
        An overlay pass is not a rebuild, so it does not get that escape."""
        root, out = self._scanned(tmp_path)
        graph, _ = load_beacon(out / "beacon.json")
        graph.remove_node("p::B")

        wr = write_beacon(graph, out, repo_path=tmp_path,
                          overlay_write=True, force=True)

        assert wr.skipped_shrink is True
        after, _ = load_beacon(out / "beacon.json")
        assert after.number_of_nodes() == 2, "prior graph must survive"
        err = capsys.readouterr().err
        assert "must only ADD" in err
        assert "p::B" in err
        assert "--force" not in err, "force must not be advertised here"


class TestEdgeBaselineExcludesOverlay:
    """GI-2276, symmetric: the edge baseline is code-tier on BOTH sides, so the
    first code-only rebuild after `codebeacon knowledge` does not read the
    overlay's own references/mentions edges as a collapse."""

    def test_code_only_rebuild_after_knowledge_reports_no_collapse(
        self, tmp_path, capsys
    ):
        root = tmp_path / "src"
        root.mkdir()
        names = ["a.py", "b.py"]
        for n in names:
            (root / n).write_text(f"# {n}\n", encoding="utf-8")
        files = [str(root / n) for n in names]
        out = tmp_path / "out"

        code = _code_graph(root, names, edges=[("a.py", "b.py")])
        write_beacon(code, out, project_roots={"p": str(root)}, corpus=files)

        # Overlay pass adds 3 note nodes and 4 references edges.
        enriched, _ = load_beacon(out / "beacon.json")
        for i in range(3):
            enriched.add_node(f"knowledge::n{i}.md", label=f"n{i}", type="knowledge",
                              project="knowledge", source_file=f"n{i}.md", line=1)
            enriched.add_edge(f"knowledge::n{i}.md", "p::a.py", relation="references",
                              confidence="EXTRACTED", confidence_score=1.0, source_file="")
        enriched.add_edge("knowledge::n0.md", "p::b.py", relation="references",
                          confidence="EXTRACTED", confidence_score=1.0, source_file="")
        write_beacon(enriched, out, overlay_write=True)
        assert json.loads((out / "beacon.json").read_text())["meta"]["edge_count"] == 5
        capsys.readouterr()

        # The next code-only scan drops back to 1 edge in the document, but the
        # code tier never changed: 1 -> 1. No collapse warning.
        wr = write_beacon(_code_graph(root, names, edges=[("a.py", "b.py")]), out,
                          project_roots={"p": str(root)}, corpus=files)
        assert wr.skipped_shrink is False
        assert wr.audit.prior_edge_count == 1
        assert wr.audit.new_edge_count == 1
        assert "collapsed" not in capsys.readouterr().err

    def test_a_real_code_edge_collapse_is_still_caught(self, tmp_path, capsys):
        """Bookend: excluding overlay edges must not blind the check."""
        root = tmp_path / "src"
        root.mkdir()
        names = ["a.py", "b.py", "c.py", "d.py"]
        for n in names:
            (root / n).write_text(f"# {n}\n", encoding="utf-8")
        files = [str(root / n) for n in names]
        out = tmp_path / "out"
        rich = _code_graph(root, names, edges=[
            ("a.py", "b.py"), ("b.py", "c.py"), ("c.py", "d.py"),
            ("a.py", "c.py"), ("a.py", "d.py"), ("b.py", "d.py"),
        ])
        write_beacon(rich, out, project_roots={"p": str(root)}, corpus=files)
        capsys.readouterr()
        write_beacon(_code_graph(root, names, edges=[("a.py", "b.py")]), out,
                     project_roots={"p": str(root)}, corpus=files)
        assert "edge count collapsed 6 → 1" in capsys.readouterr().err


# ── F2 handoffs into pipeline.py ─────────────────────────────────────────────

class TestReadOnlyTree:
    """CG-READONLY G-0914-3. The cache half degrades to a warning inside Cache,
    but the output directory has nowhere to go, so the scan must fail cleanly
    instead of ending in an unhandled PermissionError from mkdir."""

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permission bits")
    def test_readonly_tree_gives_an_actionable_message(self, tmp_path, capsys):
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=1)
        root = tmp_path / "proj"
        os.chmod(root, 0o555)
        try:
            rc = pipeline.run_pipeline(
                [project], str(root / ".codebeacon"), _scan_args(),
            )
        finally:
            os.chmod(root, 0o755)

        assert rc == 1
        err = capsys.readouterr().err
        assert "permission denied" in err.lower()
        assert "read-only" in err
        # Must not advertise an option that does not exist on `scan`.
        assert "--output-dir" not in err

    def test_writable_tree_still_works(self, tmp_path):
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=1)
        out = str(tmp_path / "proj" / ".codebeacon")
        assert pipeline.run_pipeline([project], out, _scan_args()) == 0


class TestCacheAnchor:
    """CG-KEY-ANCHOR G-0919-4. One shared Cache serves every project in a run,
    so its anchor has to contain them all — anchoring on projects[0] left every
    other project with absolute keys, defeating the portability the relative
    keying exists for."""

    def _proj(self, path):
        return ProjectInfo(name=Path(path).name, path=str(path), framework="fastapi",
                           language="python", signature_file="requirements.txt")

    def test_anchor_is_the_common_ancestor_of_all_projects(self, tmp_path):
        from codebeacon.pipeline import _cache_anchor

        mono = tmp_path / "mono"
        a, b = mono / "svc-a", mono / "svc-b"
        for p in (a, b):
            p.mkdir(parents=True)
        anchor = _cache_anchor([self._proj(a), self._proj(b)], str(tmp_path))
        assert Path(anchor) == mono

    def test_single_project_anchors_on_itself(self, tmp_path):
        from codebeacon.pipeline import _cache_anchor

        a = tmp_path / "solo"
        a.mkdir()
        assert Path(_cache_anchor([self._proj(a)], str(tmp_path))) == a

    def test_no_projects_falls_back(self, tmp_path):
        from codebeacon.pipeline import _cache_anchor

        assert _cache_anchor([], str(tmp_path)) == str(tmp_path)

    def test_uncommonable_paths_fall_back_without_raising(self, tmp_path):
        """commonpath raises on a drive/root mismatch; that must degrade, not crash."""
        from codebeacon.pipeline import _cache_anchor

        class _P:
            def __init__(self, path):
                self.path = path

        got = _cache_anchor([_P("/abs/one"), _P("relative/two")], str(tmp_path))
        assert got == "/abs/one"

    def test_every_project_gets_a_relative_cache_key(self, tmp_path):
        """The behavioural consequence: with the old anchor, svc-b's entries
        were keyed by absolute path and stopped being portable."""
        from codebeacon.cache import Cache
        from codebeacon.pipeline import _cache_anchor

        mono = tmp_path / "mono"
        a, b = mono / "svc-a", mono / "svc-b"
        for p in (a, b):
            p.mkdir(parents=True)
            (p / "main.py").write_text("x = 1\n", encoding="utf-8")

        anchor = _cache_anchor([self._proj(a), self._proj(b)], str(tmp_path))
        cache = Cache(str(tmp_path / ".codebeacon"), project_root=anchor)
        for p in (a, b):
            key = cache._key(str(p / "main.py"), framework="fastapi")
            assert not os.path.isabs(key.split("::", 1)[1]), (
                f"{key} is absolute — cache is not portable"
            )


class TestIgnoredDiagnostic:
    """R12: an over-broad ignore rule and a clean scan both print N files and
    exit 0. ignored.json is what tells them apart."""

    def test_ignored_paths_are_recorded(self, tmp_path, capsys):
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=3)
        (tmp_path / "proj" / ".codebeaconignore").write_text(
            "app/mod*.py\n", encoding="utf-8")
        out = tmp_path / "proj" / ".codebeacon"
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0

        report = out / "ignored.json"
        assert report.exists()
        data = json.loads(report.read_text())
        recorded = json.dumps(data)
        assert "mod0.py" in recorded
        assert "ignored" in capsys.readouterr().out

    def test_previous_report_never_survives_a_rescan(self, tmp_path):
        """The artefact must describe THIS run. A scan that ignores nothing
        deletes it; one that ignores something replaces it wholesale."""
        from codebeacon import pipeline
        from codebeacon.diagnostics import IgnoredReport, write_ignored_report

        # The delete-on-empty branch, exercised directly: nothing ignored →
        # a report from a previous run is removed rather than left to mislead.
        out = tmp_path / "proj" / ".codebeacon"
        out.mkdir(parents=True)
        stale = out / "ignored.json"
        stale.write_text('{"stale": true}', encoding="utf-8")
        assert write_ignored_report(IgnoredReport(), str(out)) is None
        assert not stale.exists()

        # And through the pipeline, where a real scan does prune things: the
        # file is rewritten, never merged with what was there before.
        project = _fastapi_project(tmp_path, n_mods=1)
        stale.write_text('{"stale": true}', encoding="utf-8")
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0
        if stale.exists():
            assert "stale" not in stale.read_text()


class TestSourceKeyingSymmetry:
    """The prior and new sides of the audit must be keyed the SAME way.

    They were not: the prior side resolved relative paths against project roots
    while the new side normalised whatever it found against the cwd. For a
    caller with no roots — an overlay writer handing back a graph it loaded —
    the two never matched, so a pure ADD counted as total loss.

    The subtlety is that matching and disk-probing are different jobs: a path we
    cannot place must still MATCH (so counts line up) while remaining
    unprobeable (so it is never waived as 'deleted')."""

    def test_relative_graph_without_roots_matches_itself(self, tmp_path):
        from codebeacon.graph.write import _audit_shrink

        out = tmp_path / "out"
        src = tmp_path / "src"
        src.mkdir()
        (src / "A.java").write_text("class A {}\n", encoding="utf-8")
        G = nx.DiGraph()
        G.add_node("p::A", label="A", type="class", project="p",
                   source_file=str(src / "A.java"), line=1)
        write_beacon(G, out, project_roots={"p": str(tmp_path)},
                     corpus=[str(src / "A.java")])

        # Loaded back: source_file is now "src/A.java", and no roots are given.
        reloaded, _ = load_beacon(out / "beacon.json")
        assert reloaded.nodes["p::A"]["source_file"] == "src/A.java"
        audit = _audit_shrink(out / "beacon.json", reloaded, corpus=None,
                              project_roots=None, incomplete=False)
        assert audit.unexplained == 0

    def test_unplaceable_path_is_never_waived_as_deleted(self, tmp_path):
        """The safety half. A prior node whose file cannot be located must not
        be reported as a deletion just because nothing was found on disk — that
        is the os.path.exists conflation again, one level up."""
        from codebeacon.graph.write import _audit_shrink, _prior_source_key

        key, probe = _prior_source_key("src/A.java", "p", None)
        assert key == "src/A.java", "must still match the new side"
        assert probe is None, "must not invent a path to stat"

        out = tmp_path / "out"
        src = tmp_path / "src"
        src.mkdir()
        (src / "A.java").write_text("class A {}\n", encoding="utf-8")
        G = nx.DiGraph()
        G.add_node("p::A", label="A", type="class", project="p",
                   source_file=str(src / "A.java"), line=1)
        write_beacon(G, out, project_roots={"p": str(tmp_path)},
                     corpus=[str(src / "A.java")])

        # An overlay-shaped write that genuinely DROPS the node, with no roots:
        # unattributable, so refused — not waived as a deletion.
        empty = nx.DiGraph()
        audit = _audit_shrink(out / "beacon.json", empty, corpus=None,
                              project_roots=None, incomplete=False)
        assert audit.unexplained == 1
        assert audit.deleted_sources == []


# ── GI-2527 — the html_assets escape hatch has to reach the exporters ────────

class TestHtmlAssetsThreading:
    """F7 vendored the JS and F8 landed the config key, but nothing in
    pipeline.py passed the value on, so `output: {html_assets: cdn}` parsed
    correctly and then died before the exporters — the opt-out was dead config.
    The default (offline) worked throughout, so only the escape hatch broke."""

    def _scan(self, tmp_path, **over):
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=1)
        out = tmp_path / "proj" / ".codebeacon"
        rc = pipeline.run_pipeline([project], str(out), _scan_args(**over))
        assert rc == 0
        return out

    def test_cdn_mode_emits_cdn_urls(self, tmp_path):
        from codebeacon.export.assets import cdn_url

        out = self._scan(tmp_path, html_assets="cdn")
        # The two pages pull different libraries, so each is checked against
        # its own upstream URL rather than one assumed CDN host.
        for page, library in (("beacon.html", "d3"), ("callflow.html", "mermaid")):
            html = (out / page).read_text(encoding="utf-8")
            assert cdn_url(library) in html, f"{page} is not on the CDN"
            assert 'src="_assets/' not in html, f"{page} still references local assets"
        assert not (out / "_assets").exists(), "cdn mode must not vendor anything"

    def test_local_mode_is_offline_and_is_the_default(self, tmp_path):
        """The default must stay offline — that is the whole point of GI-2527."""
        out = self._scan(tmp_path)          # no html_assets on args at all
        for page in ("beacon.html", "callflow.html"):
            html = (out / page).read_text(encoding="utf-8")
            assert 'src="_assets/' in html, f"{page} lost its vendored assets"
            assert "http://" not in html and "https://" not in html.split("<body")[0], (
                f"{page} reaches the network in the offline default"
            )
        assert (out / "_assets").is_dir()

    def test_pages_carry_no_absolute_machine_paths(self, tmp_path):
        out = self._scan(tmp_path)
        html = (out / "beacon.html").read_text(encoding="utf-8")
        assert str(tmp_path) not in html, "absolute machine path leaked into the page"

    def test_exporters_receive_explicit_project_roots(self, tmp_path, monkeypatch):
        """The other half of the contract. This one is a call-contract test on
        purpose: the exporters infer roots when none are given, and for a
        single-project scan the inference lands on the same answer — so output
        alone cannot tell the two apart. What was actually asked for is that the
        pipeline stop relying on that inference, and the kwarg is that."""
        from codebeacon import pipeline
        import codebeacon.export.tree_html as tree_mod
        import codebeacon.export.callflow_html as flow_mod

        seen: dict[str, dict] = {}
        for name, mod, fn in (
            ("tree", tree_mod, tree_mod.write_tree_html),
            ("flow", flow_mod, flow_mod.write_callflow_html),
        ):
            def spy(G, out_dir, *, _n=name, _f=fn, **kwargs):
                seen[_n] = kwargs
                return _f(G, out_dir, **kwargs)
            monkeypatch.setattr(mod, fn.__name__, spy)

        project = _fastapi_project(tmp_path, n_mods=1)
        out = tmp_path / "proj" / ".codebeacon"
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0

        assert set(seen) == {"tree", "flow"}, "an exporter was not called"
        for name, kwargs in seen.items():
            assert kwargs.get("project_roots") == {project.name: project.path}, (
                f"{name} exporter did not get explicit roots"
            )
            assert kwargs.get("html_assets") == "local"


# ── Write suppression — byte-stability is not the same as not writing ────────

class TestNoOpRebuildTouchesNothing:
    """R10's second half. Making the CONTENT stable stopped git seeing a diff,
    but the files were still rewritten unconditionally, so mtime moved on every
    rebuild — which is what re-triggers editor indexers, file-sync clients and
    anything watching the tree. F7 measured 4 artifacts still churning on an
    identical rescan; beacon.json and REPORT.md were the two in my files."""

    def _mtime(self, path):
        return path.stat().st_mtime_ns

    def test_identical_beacon_is_not_rewritten(self, tmp_path):
        root, files = _mk_corpus(tmp_path, ["a.py", "b.py"])
        out = tmp_path / "out"
        G = _code_graph(root, ["a.py", "b.py"])
        wr1 = write_beacon(G, out, project_roots={"p": str(root)}, corpus=files)
        assert wr1.unchanged is False, "first write must actually write"
        before = self._mtime(out / "beacon.json")

        wr2 = write_beacon(_code_graph(root, ["a.py", "b.py"]), out,
                           project_roots={"p": str(root)}, corpus=files)
        assert wr2.unchanged is True
        assert self._mtime(out / "beacon.json") == before, "file was touched"
        assert not (out / "beacon.json.tmp").exists(), "temp file left behind"

    def test_changed_beacon_is_still_written(self, tmp_path):
        """The bookend: suppression must not swallow a real update."""
        root, files = _mk_corpus(tmp_path, ["a.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)

        root2, files2 = _mk_corpus(tmp_path, ["a.py", "b.py"])
        wr = write_beacon(_code_graph(root2, ["a.py", "b.py"]), out,
                          project_roots={"p": str(root2)}, corpus=files2)
        assert wr.unchanged is False
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 2

    def test_damaged_beacon_self_heals(self, tmp_path):
        """A file that cannot be read must never compare equal — otherwise a
        corrupted artifact would be preserved by the very optimisation meant to
        avoid pointless writes."""
        root, files = _mk_corpus(tmp_path, ["a.py"])
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py"]), out,
                     project_roots={"p": str(root)}, corpus=files)
        (out / "beacon.json").write_bytes(b"\xff\xfe not utf-8 at all")

        wr = write_beacon(_code_graph(root, ["a.py"]), out,
                          project_roots={"p": str(root)}, corpus=files)
        assert wr.unchanged is False
        graph, _ = load_beacon(out / "beacon.json")
        assert graph.number_of_nodes() == 1

    def test_pipeline_rescan_touches_neither_beacon_nor_report(self, tmp_path):
        """End-to-end through run_pipeline, which is where it matters."""
        from codebeacon import pipeline

        project = _fastapi_project(tmp_path, n_mods=2)
        out = tmp_path / "proj" / ".codebeacon"
        assert pipeline.run_pipeline([project], str(out), _scan_args()) == 0
        before = {
            name: self._mtime(out / name) for name in ("beacon.json", "REPORT.md")
        }

        assert pipeline.run_pipeline([project], str(out), _scan_args(update=True)) == 0
        for name, was in before.items():
            assert self._mtime(out / name) == was, f"{name} was rewritten"


class TestOverlayTierBoundary:
    """An overlay write owns its own tier and nothing else.

    My first cut of the additivity check flagged ANY missing prior id, which
    broke `codebeacon knowledge`: link.py sweeps stale note nodes before
    re-linking, so deleting a note legitimately removes its overlay node. The
    guard refused that write, which left the stale node on disk permanently —
    the opposite of what it exists to do. Both directions are pinned here."""

    def _with_two_notes(self, tmp_path):
        root = tmp_path / "src"
        root.mkdir()
        (root / "a.py").write_text("# a\n", encoding="utf-8")
        out = tmp_path / "out"
        G = _code_graph(root, ["a.py"])
        for name in ("a.md", "b.md"):
            G.add_node(f"knowledge::{name}", label=name, type="knowledge",
                       project="knowledge", source_file=name, line=1)
        write_beacon(G, out, project_roots={"p": str(root)},
                     corpus=[str(root / "a.py")])
        return root, out

    def test_overlay_may_drop_its_own_stale_nodes(self, tmp_path):
        """A deleted note must be able to leave the graph."""
        root, out = self._with_two_notes(tmp_path)
        graph, _ = load_beacon(out / "beacon.json")
        graph.remove_node("knowledge::b.md")       # b.md was deleted on disk

        wr = write_beacon(graph, out, overlay_write=True)

        assert wr.skipped_shrink is False
        after, _ = load_beacon(out / "beacon.json")
        notes = sorted(
            n for n, d in after.nodes(data=True) if d.get("type") == "knowledge"
        )
        assert notes == ["knowledge::a.md"], "stale overlay node lingered"

    def test_overlay_still_may_not_drop_a_code_node(self, tmp_path):
        """The half that must stay strict."""
        root, out = self._with_two_notes(tmp_path)
        graph, _ = load_beacon(out / "beacon.json")
        graph.remove_node("p::a.py")

        wr = write_beacon(graph, out, overlay_write=True, force=True)

        assert wr.skipped_shrink is True
        after, _ = load_beacon(out / "beacon.json")
        assert "p::a.py" in after.nodes

    def test_relink_after_note_deletion_end_to_end(self, tmp_path):
        """The real path that regressed: knowledge link → delete a note →
        relink. Exercised through the actual knowledge module, not a hand-built
        graph, so the guard is judged against how link.py really writes."""
        from codebeacon.knowledge.generator import build_knowledge_map
        from codebeacon.knowledge.link import link_knowledge_to_graph

        root = tmp_path / "src"
        root.mkdir()
        (root / "a.py").write_text("# a\n", encoding="utf-8")
        out = tmp_path / "out"
        write_beacon(_code_graph(root, ["a.py"]), out,
                     project_roots={"p": str(root)}, corpus=[str(root / "a.py")])

        vault = tmp_path / "notes"
        vault.mkdir()
        for name in ("a.md", "b.md"):
            (vault / name).write_text(
                f"# {name}\n\nAbout `a.py`.\n", encoding="utf-8")

        link_knowledge_to_graph(build_knowledge_map(vault, tmp_path / "kout"), out)
        graph, _ = load_beacon(out / "beacon.json")
        assert sum(
            1 for _, d in graph.nodes(data=True) if d.get("type") == "knowledge"
        ) == 2

        (vault / "b.md").unlink()
        link_knowledge_to_graph(build_knowledge_map(vault, tmp_path / "kout"), out)
        graph2, _ = load_beacon(out / "beacon.json")
        notes = sorted(
            n for n, d in graph2.nodes(data=True) if d.get("type") == "knowledge"
        )
        assert notes == ["knowledge::a.md"]
        assert "p::a.py" in graph2.nodes, "the code tier must survive a relink"
