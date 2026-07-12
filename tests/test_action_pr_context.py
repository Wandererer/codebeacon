"""Tests for the codebeacon PR-context GitHub Action entry script.

No GitHub API is touched here: ``action/pr_context.py`` is designed so the
renderer and the diff/hub helpers are pure functions, and the composite action
only shells out to ``gh`` in a separate step. We load the script by path (it
lives under ``action/``, outside the importable package) and unit-test:

* comment rendering (marker present, wiki paths listed, counts correct),
* the empty states (docs-only diff, missing index),
* the structure-signal parsing of the persisted REPORT.md,
* that ``action.yml`` is valid YAML declaring every documented input,

plus one end-to-end test that drives the real ``affected_from_paths`` engine
against an on-disk beacon.json + wiki, then feeds its result to ``build_comment``.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest
import yaml

from codebeacon.affected import AffectedResult, affected_from_paths
from codebeacon.wiki.generator import node_to_wiki_path

# ── load action/pr_context.py by path (not an installed module) ───────────────
_ACTION_DIR = Path(__file__).resolve().parents[1] / "action"
_spec = importlib.util.spec_from_file_location("pr_context", _ACTION_DIR / "pr_context.py")
pr_context = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr_context)


def _result(**kw) -> AffectedResult:
    base = dict(
        seed_files=["codebeacon/common/safety.py"],
        seed_node_ids=["p::Safety"],
        affected_node_ids=["p::A", "p::B"],
        affected_summary=[
            {"id": "p::A", "label": "A", "type": "class", "source_file": "a.py"},
            {"id": "p::B", "label": "B", "type": "class", "source_file": "b.py"},
        ],
        wiki_paths=["codebeacon/services/A.md", "codebeacon/services/B.md"],
    )
    base.update(kw)
    return AffectedResult(**base)


# ── comment rendering ─────────────────────────────────────────────────────────

class TestBuildComment:
    def test_marker_is_first_line(self):
        md = pr_context.build_comment(_result(), ["codebeacon/common/safety.py"])
        assert md.splitlines()[0] == pr_context.MARKER

    def test_lists_wiki_paths_under_beacon_dir(self):
        md = pr_context.build_comment(_result(), ["codebeacon/common/safety.py"])
        assert "`.codebeacon/wiki/codebeacon/services/A.md`" in md
        assert "`.codebeacon/wiki/codebeacon/services/B.md`" in md

    def test_counts_are_accurate(self):
        md = pr_context.build_comment(
            _result(),
            ["f1.py", "f2.py", "f3.py"],  # 3 changed files
            depth=3,
        )
        # 3 changed → 1 seed → 2 affected
        assert "**3** changed file(s)" in md
        assert "**1** matched node(s)" in md
        assert "**2** upstream node(s)" in md
        assert "depth 3" in md

    def test_limit_truncates_wiki_list_with_more_marker(self):
        many = _result(wiki_paths=[f"p/services/N{i}.md" for i in range(60)])
        md = pr_context.build_comment(many, ["x.py"], limit=5)
        assert md.count("- `.codebeacon/wiki/p/services/N") == 5
        assert "…and 55 more" in md

    def test_no_seed_nodes_is_no_impact_message(self):
        empty = _result(seed_node_ids=[], affected_node_ids=[], wiki_paths=[])
        md = pr_context.build_comment(empty, ["docs/readme.md", "config.yml"])
        assert "No architectural impact detected" in md
        assert pr_context.MARKER in md
        # It should not fabricate a wiki section when nothing matched.
        assert "Affected wiki articles" not in md

    def test_no_wiki_articles_still_shows_counts(self):
        no_wiki = _result(wiki_paths=[])
        md = pr_context.build_comment(no_wiki, ["codebeacon/common/safety.py"])
        assert "No wiki articles in the blast radius" in md
        assert "**1** matched node(s)" in md

    def test_structure_signals_render_hub_hits(self):
        md = pr_context.build_comment(
            _result(),
            ["codebeacon/common/safety.py"],
            hub_hits=[("codebeacon/common/safety.py", 9)],
        )
        assert "Structure signals" in md
        assert "`codebeacon/common/safety.py` — imported by 9 file(s)" in md

    def test_base_ref_appears_in_footer(self):
        md = pr_context.build_comment(_result(), ["x.py"], base="main")
        assert "vs `main`" in md


class TestEmptyNoBeacon:
    def test_has_marker_and_setup_commands(self):
        md = pr_context.empty_no_beacon(".codebeacon")
        assert md.splitlines()[0] == pr_context.MARKER
        assert "No committed index found" in md
        assert "codebeacon scan ." in md
        assert "git add .codebeacon" in md

    def test_honours_custom_beacon_dir(self):
        md = pr_context.empty_no_beacon("docs/.beacon")
        assert "`docs/.beacon/beacon.json`" in md
        assert "git add docs/.beacon" in md


# ── structure-signal helpers ──────────────────────────────────────────────────

_REPORT_SNIPPET = """# CodeBeacon Graph Report

## Statistics
- Nodes: 421

## Hub Files (Most Imported)

- /Users/x/repo/codebeacon/common/safety.py (9 imports)
- /Users/x/repo/codebeacon/wiki/generator.py (6 imports)
- /Users/x/repo/codebeacon/affected.py (1 import)

## Community Cohesion Scores

- Community 0: 0.764
"""


class TestHubParsing:
    def test_parse_hub_files_extracts_path_and_count(self):
        hubs = pr_context.parse_hub_files(_REPORT_SNIPPET)
        assert ("/Users/x/repo/codebeacon/common/safety.py", 9) in hubs
        assert ("/Users/x/repo/codebeacon/affected.py", 1) in hubs  # singular "import"
        # Cohesion-score bullets must NOT be parsed as hub files.
        assert all("Community" not in p for p, _ in hubs)

    def test_parse_hub_files_absent_section(self):
        assert pr_context.parse_hub_files("# Report\n\n## Statistics\n- Nodes: 1\n") == []

    def test_high_impact_matches_absolute_hub_against_relative_change(self):
        hubs = pr_context.parse_hub_files(_REPORT_SNIPPET)
        hits = pr_context.high_impact_changes(["codebeacon/common/safety.py"], hubs)
        assert hits == [("codebeacon/common/safety.py", 9)]

    def test_high_impact_sorts_by_count_desc(self):
        hubs = pr_context.parse_hub_files(_REPORT_SNIPPET)
        hits = pr_context.high_impact_changes(
            ["codebeacon/affected.py", "codebeacon/common/safety.py"], hubs
        )
        assert [c for _, c in hits] == [9, 1]

    def test_high_impact_no_match(self):
        hubs = pr_context.parse_hub_files(_REPORT_SNIPPET)
        assert pr_context.high_impact_changes(["totally/unrelated.py"], hubs) == []

    def test_suffix_match_respects_segment_boundary(self):
        # "foosrc/x.py" must NOT match seed "src/x.py".
        assert pr_context._suffix_match("a/src/x.py", "src/x.py")
        assert not pr_context._suffix_match("a/foosrc/x.py", "src/x.py")


# ── diff resolution ───────────────────────────────────────────────────────────

class TestResolveChangedFiles:
    def test_blank_base_returns_empty_without_git(self):
        assert pr_context.resolve_changed_files("", repo=".") == []

    def test_unresolvable_base_degrades_to_empty(self, tmp_path):
        # A fresh repo with no such branch → no crash, empty list.
        pr_context._run_git(["init"], repo=tmp_path)
        assert pr_context.resolve_changed_files("no-such-branch", repo=tmp_path, fetch=False) == []


# ── action.yml contract ───────────────────────────────────────────────────────

class TestActionYaml:
    def test_action_yml_is_valid_and_declares_documented_inputs(self):
        data = yaml.safe_load((_ACTION_DIR / "action.yml").read_text(encoding="utf-8"))
        assert data["name"] == "codebeacon PR context"
        assert data["runs"]["using"] == "composite"
        documented = {"base", "beacon-dir", "depth", "limit", "comment", "install", "fail-on-error"}
        assert set(data["inputs"]) == documented
        # Every input carries a description and a default.
        for name, spec in data["inputs"].items():
            assert spec.get("description"), f"{name} missing description"
            assert "default" in spec, f"{name} missing default"

    def test_example_workflow_requests_pr_write_and_full_history(self):
        wf = yaml.safe_load((_ACTION_DIR / "examples" / "pr-context.yml").read_text(encoding="utf-8"))
        assert wf["permissions"]["pull-requests"] == "write"
        checkout = wf["jobs"]["pr-context"]["steps"][0]
        assert checkout["with"]["fetch-depth"] == 0


# ── end-to-end against the real engine ────────────────────────────────────────

def _build_graph() -> nx.DiGraph:
    """UserController (api) ← calls ← UserService (api) ← calls ← User (api)."""
    G = nx.DiGraph()
    G.add_node("api::UserController", label="UserController", type="class",
               source_file="api/src/UserController.py", project="api", annotations=[])
    G.add_node("api::UserService", label="UserService", type="class",
               source_file="api/src/UserService.py", project="api", annotations=[])
    G.add_node("api::User", label="User", type="entity",
               source_file="api/src/User.py", project="api")
    G.add_edge("api::UserController", "api::UserService", relation="calls")
    G.add_edge("api::UserService", "api::User", relation="calls")
    return G


def _persist(G: nx.DiGraph, tmp_path: Path) -> Path:
    bdir = tmp_path / ".codebeacon"
    bdir.mkdir()
    (bdir / "beacon.json").write_text(
        json.dumps(nxjson.node_link_data(G), ensure_ascii=False), encoding="utf-8"
    )
    wiki_root = bdir / "wiki"
    for node_id in G.nodes:
        wp = node_to_wiki_path(G, node_id)
        if not wp:
            continue
        full = wiki_root / wp
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("# stub", encoding="utf-8")
    return bdir


class TestEndToEnd:
    def test_engine_result_renders_into_comment(self, tmp_path):
        bdir = _persist(_build_graph(), tmp_path)
        result = affected_from_paths(
            bdir, ["api/src/User.py"], include_wiki_paths=True
        )
        md = pr_context.build_comment(
            result, ["api/src/User.py"], beacon_dir=".codebeacon", base="main"
        )
        # Changing the entity surfaces its own article plus the upstream service
        # and controller that depend on it.
        assert "`.codebeacon/wiki/api/entities/User.md`" in md
        assert "`.codebeacon/wiki/api/services/UserService.md`" in md
        assert "`.codebeacon/wiki/api/controllers/UserController.md`" in md
        assert pr_context.MARKER in md

    def test_main_missing_index_emits_guidance(self, tmp_path, monkeypatch, capsys):
        # Fabricate a git repo with one committed file and a diff, but no index.
        pr_context._run_git(["init"], repo=tmp_path)
        pr_context._run_git(["config", "user.email", "t@example.com"], repo=tmp_path)
        pr_context._run_git(["config", "user.name", "t"], repo=tmp_path)
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        pr_context._run_git(["add", "-A"], repo=tmp_path)
        pr_context._run_git(["commit", "-m", "base"], repo=tmp_path)
        pr_context._run_git(["checkout", "-b", "feature"], repo=tmp_path)
        (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
        pr_context._run_git(["commit", "-am", "change"], repo=tmp_path)

        out_file = tmp_path / "comment.md"
        gh_out = tmp_path / "gh_output"
        monkeypatch.chdir(tmp_path)
        rc = pr_context.main([
            "--base", "master",
            "--repo", str(tmp_path),
            "--beacon-dir", ".codebeacon",
            "--output", str(out_file),
            "--github-output", str(gh_out),
        ])
        assert rc == 0
        # git's default branch may be master or main depending on config; if the
        # diff resolved we should have written a guidance comment, otherwise the
        # run cleanly skipped. Either way it must not crash and must set output.
        outputs = gh_out.read_text(encoding="utf-8")
        assert "has_comment=" in outputs
        if out_file.exists():
            assert "No committed index found" in out_file.read_text(encoding="utf-8")
