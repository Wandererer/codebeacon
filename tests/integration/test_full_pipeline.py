"""End-to-end pipeline regression tests.

Up until 0.6.0 the test suite was strong on individual extractors but had
nothing exercising the full scan → graph → wiki → affected flow on a real
(if small) multi-language workspace. A regression that ONLY showed up when
the pieces composed (e.g. a node ID mismatch between build_graph and
wiki/generator.node_to_wiki_path) would slip through.

These tests stand up the ``tests/fixtures/integration_workspace`` repo and
walk every public surface so any breakage in the seam between subsystems
becomes a visible test failure.

Slow tests (~1-2s each) live here to keep the unit-test loop fast; CI runs
both, the day-to-day TDD inner loop can scope to ``tests/test_*.py``.
"""
from __future__ import annotations

import json
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

# Skip the whole integration module if a required grammar isn't installed.
# We need python + typescript at minimum for the workspace fixture; the
# extras split (0.6.0) keeps them in the default install so this skip is
# defensive against lean CI runners.
pytest.importorskip("tree_sitter_python")
pytest.importorskip("tree_sitter_typescript")


WORKSPACE = Path(__file__).resolve().parents[1] / "fixtures" / "integration_workspace"


@pytest.fixture
def scratch_workspace(tmp_path: Path) -> Path:
    """Copy the read-only fixture into a writable tmp dir so the pipeline
    can scribble .codebeacon/ next to the sources."""
    dest = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, dest)
    return dest


def _discover(workspace: Path):
    from codebeacon.discover.detector import discover_projects
    return discover_projects([str(workspace)])


def _scan_into_graph(workspace: Path):
    """Run Pass 1 (auto_wave) for every project and merge into one graph."""
    from codebeacon.discover.scanner import collect_files
    from codebeacon.graph.build import build_graph
    from codebeacon.wave import auto_wave

    projects = _discover(workspace)
    wave_results = []
    for project in projects:
        files = collect_files(project.path)
        wave = auto_wave(project=project, files=files)
        wave_results.append(wave)
    G = build_graph(wave_results)
    return projects, wave_results, G


# ── Stage-by-stage sanity tests ──────────────────────────────────────────────

class TestDiscoveryAndExtraction:
    def test_discovers_python_and_react_projects(self, scratch_workspace):
        projects = _discover(scratch_workspace)
        names = {p.name for p in projects}
        # Both fixtures should be detected; framework labels can vary by
        # detector heuristics, so we only assert on names.
        assert "api-python" in names
        assert "web" in names

    def test_extraction_produces_zero_failures(self, scratch_workspace):
        """Fixture is tiny and well-formed — a non-empty failures list
        means the extractor regressed, not the fixture."""
        _, wave_results, _ = _scan_into_graph(scratch_workspace)
        for wave in wave_results:
            assert wave.failures == [], (
                f"Unexpected failures in {wave.project.name}: "
                f"{[(f.file_path, f.error) for f in wave.failures]}"
            )

    def test_graph_contains_nodes_from_both_projects(self, scratch_workspace):
        _, _, G = _scan_into_graph(scratch_workspace)
        # Group nodes by project so we can assert *something* came out of
        # each fixture. Extractor heuristics evolve (FastAPI may emit
        # method nodes rather than the class; React detects components),
        # so we don't pin specific labels — only that no project is empty.
        by_project: dict[str, int] = {}
        for _, data in G.nodes(data=True):
            proj = data.get("project") or "_"
            by_project[proj] = by_project.get(proj, 0) + 1
        assert by_project.get("api-python", 0) > 0, (
            f"api-python yielded zero nodes. node distribution: {by_project}"
        )
        assert by_project.get("web", 0) > 0, (
            f"web yielded zero nodes. node distribution: {by_project}"
        )


# ── Full pipeline through pipeline.run_pipeline (writes beacon.json + wiki) ──

class TestFullPipelineWritesArtifacts:
    def test_run_pipeline_writes_beacon_and_wiki(self, scratch_workspace):
        from codebeacon.pipeline import run_pipeline

        projects = _discover(scratch_workspace)
        output_dir = scratch_workspace / ".codebeacon"
        args = Namespace(
            wiki_only=False,
            update=False,
            semantic=False,
            exclude=[],
            obsidian_dir=None,
            max_failure_rate=None,
        )
        rc = run_pipeline(projects, str(output_dir), args)
        assert rc == 0
        assert (output_dir / "beacon.json").exists()
        assert (output_dir / "REPORT.md").exists()
        assert (output_dir / "wiki" / "index.md").exists()

    def test_no_extraction_failures_file_on_clean_run(self, scratch_workspace):
        """A healthy fixture must NOT leave an extraction-failures.json —
        the file's mere presence is a signal to CI / reviewers."""
        from codebeacon.pipeline import run_pipeline

        projects = _discover(scratch_workspace)
        output_dir = scratch_workspace / ".codebeacon"
        args = Namespace(
            wiki_only=False, update=False, semantic=False,
            exclude=[], obsidian_dir=None, max_failure_rate=None,
        )
        run_pipeline(projects, str(output_dir), args)
        assert not (output_dir / "extraction-failures.json").exists()


# ── affected → wiki end-to-end ───────────────────────────────────────────────

class TestAffectedToWikiE2E:
    def test_changing_services_py_surfaces_wiki_article(self, scratch_workspace):
        """The headline 0.6.0 synergy: change a service file, get the wiki
        article path back so a reviewing agent reads the right doc."""
        from codebeacon.affected import affected_from_paths
        from codebeacon.pipeline import run_pipeline

        projects = _discover(scratch_workspace)
        output_dir = scratch_workspace / ".codebeacon"
        args = Namespace(
            wiki_only=False, update=False, semantic=False,
            exclude=[], obsidian_dir=None, max_failure_rate=None,
        )
        run_pipeline(projects, str(output_dir), args)

        result = affected_from_paths(
            output_dir,
            [str(scratch_workspace / "api-python" / "src" / "services.py")],
            include_wiki_paths=True,
        )
        # We don't pin the exact path because extractor heuristics (which
        # bucket a class lands in) can shift. The contract: at least ONE
        # wiki path is returned and it actually exists on disk.
        assert result.wiki_paths, (
            f"affected_from_paths returned no wiki paths.\n"
            f"  seed_node_ids: {result.seed_node_ids}\n"
            f"  affected_node_ids: {result.affected_node_ids}"
        )
        for wp in result.wiki_paths:
            assert (output_dir / "wiki" / wp).exists(), (
                f"Wiki path {wp} doesn't exist on disk — node_to_wiki_path "
                f"and generate_wiki are out of sync."
            )


# ── Semantic-apply integration with a synthetic LLM result ────────────────────

class TestSemanticApplyIntegration:
    def test_semantic_apply_writes_stats_file_on_lean_install(self, scratch_workspace):
        """After running scan + a hand-crafted semantic-results.jsonl,
        semantic-apply must surface the hallucination/coercion counts in
        semantic-stats.json. This catches the case where the stats writer
        is accidentally short-circuited on the zero-applied branch."""
        from codebeacon.pipeline import run_pipeline
        from codebeacon.semantic_pipeline import apply

        projects = _discover(scratch_workspace)
        output_dir = scratch_workspace / ".codebeacon"
        args = Namespace(
            wiki_only=False, update=False, semantic=False,
            exclude=[], obsidian_dir=None, max_failure_rate=None,
        )
        run_pipeline(projects, str(output_dir), args)

        # Hand-write a results chunk with mixed signal: one high-confidence
        # known relation (should land), one hallucinated label (should
        # coerce + flag), one below threshold (should drop).
        # Pick any class node from the graph as the source.
        import networkx.readwrite.json_graph as nxjson
        beacon = json.loads((output_dir / "beacon.json").read_text())
        G = nxjson.node_link_graph(beacon, directed=True, multigraph=False)
        class_nodes = [
            nid for nid, data in G.nodes(data=True) if data.get("type") == "class"
        ]
        if not class_nodes:
            pytest.skip("Fixture didn't yield any class nodes — extractor regression covered elsewhere.")

        source_id = class_nodes[0]
        results_dir = output_dir / "semantic" / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "chunk_001.jsonl").write_text(json.dumps({
            "task_id": "t1",
            "source_node_id": source_id,
            "edges": [
                {"target_name": "OkRef", "relation": "references", "confidence_score": 0.9},
                {"target_name": "BadRef", "relation": "frobnicates", "confidence_score": 0.9},
                {"target_name": "TooLow", "relation": "references", "confidence_score": 0.1},
            ],
        }) + "\n", encoding="utf-8")

        result = apply(output_dir)
        assert (output_dir / "semantic-stats.json").exists()
        stats = json.loads((output_dir / "semantic-stats.json").read_text())
        assert stats["edges_total"] == 3
        assert stats["edges_dropped_low_confidence"] == 1
        assert stats["relations_coerced"] == 1
        assert "frobnicates" in stats["unknown_relation_labels"]
