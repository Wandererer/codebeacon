"""Audit 0.7.1 — F10: semantic ingest hardening + knowledge overlay lifecycle.

Every test here pins a defect that was reproduced against the 0.7.0 code before
being fixed. Grouped by the verdict that motivated it:

  G-0918-4 / G-0932-3  ingest validation on BOTH paths (apply + archive replay)
  G-0949-12            node-only contributions must persist
  G-0948-5             pretty-printed results recovered; pending kept on total loss
  G-0949-21            excerpt truncation announced; task_id tracks the whole file
  G-0918-5             unresolved edge targets stamped literal / unverified
  G-0949-13 (resid. A) a result row must name its own task's source node
  GI-2413 / G-0948-8 / G-0953-9   authored [[wikilinks]] become graph edges
  G-0946-5             node_kind + bounded frontmatter passthrough
  G-0949-14 / G-0952-1 (R2)       scan re-applies the knowledge overlay
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import networkx as nx
import pytest

from codebeacon.graph.write import load_beacon, write_beacon
from codebeacon.knowledge.generator import (
    MAX_FRONTMATTER_KEYS,
    _STAMP_RE,
    build_knowledge_map,
    is_generated_knowledge_map,
)
from codebeacon.knowledge.link import (
    _match_path_ref,
    extract_path_refs,
    link_knowledge_to_graph,
    normalize_wikilink,
    reapply_knowledge,
)
from codebeacon.semantic_pipeline import (
    MAX_EXCERPT_CHARS,
    _iter_jsonl,
    _pick_candidates,
    _reapply_archive,
    _ReplayStats,
    _slice_excerpt,
    _validate_llm_edge,
    _validate_llm_node,
    apply,
    prepare,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_beacon(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A small real repo + .codebeacon with two Java services and one edge."""
    root = tmp_path / "repo"
    src = root / "src"
    src.mkdir(parents=True)
    (src / "UserService.java").write_text(
        "package a;\n// Uses the OrderService for checkout\n"
        "class UserService { void go(){} }\n",
        encoding="utf-8",
    )
    (src / "OrderService.java").write_text(
        "package a;\nclass OrderService { void checkout(){} }\n", encoding="utf-8"
    )
    beacon_dir = root / ".codebeacon"
    beacon_dir.mkdir(parents=True)
    G = nx.DiGraph()
    G.add_node(
        "svc:UserService", label="UserService", type="service", project="p",
        source_file=str(src / "UserService.java"), line=1, framework="spring-boot",
    )
    G.add_node(
        "svc:OrderService", label="OrderService", type="service", project="p",
        source_file=str(src / "OrderService.java"), line=1, framework="spring-boot",
    )
    G.add_edge("svc:UserService", "svc:OrderService", relation="calls",
               confidence="EXTRACTED")
    write_beacon(G, beacon_dir, force=True)
    return root, beacon_dir, src


def _write_chunk(beacon_dir: Path, sub: str, name: str, rows: list) -> Path:
    d = beacon_dir / "semantic" / sub
    d.mkdir(parents=True, exist_ok=True)
    with open(d / name, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return d / name


def _beacon_nodes(beacon_dir: Path) -> dict:
    data = json.loads((beacon_dir / "beacon.json").read_text(encoding="utf-8"))
    return {n["id"]: n for n in data["nodes"]}


# ── G-0918-4 / G-0932-3: ingest validation ───────────────────────────────────


HOSTILE_NODES = [
    pytest.param({"id": "c:x", "label": {"nested": "obj"}, "file_type": "concept"},
                 id="dict-label"),
    pytest.param({"id": "c:x", "label": 999, "file_type": "concept"},
                 id="int-label"),
    pytest.param({"id": "c:x", "label": "ok", "file_type": 3},
                 id="int-file-type"),
    pytest.param({"id": 7, "label": "ok", "file_type": "concept"},
                 id="int-id"),
    pytest.param({"id": "c:x", "label": "H" * 200_000, "file_type": "concept"},
                 id="oversized-label"),
    pytest.param({"id": "c:" + "y" * 5_000, "label": "ok", "file_type": "concept"},
                 id="oversized-id"),
    pytest.param({"id": "c:x", "label": "", "file_type": "concept"},
                 id="empty-label"),
    pytest.param("JustAString", id="not-a-dict"),
]


class TestIngestValidation:
    """A malformed row is skipped and counted — never allowed to abort a merge."""

    @pytest.mark.parametrize("bad_node", HOSTILE_NODES)
    def test_apply_survives_hostile_node_and_keeps_good_edge(
        self, tmp_path: Path, bad_node
    ):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"),
            "excerpt": "// Uses the OrderService for checkout",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "nodes": [bad_node],
            "edges": [{"target_name": "PaymentGateway", "confidence_score": 0.9}],
        }])

        result = apply(beacon_dir)  # must not raise

        assert result.applied == 1, "one bad node row must not cost the good edge"
        assert result.stats.nodes_rejected_invalid == 1
        nodes = _beacon_nodes(beacon_dir)
        assert "PaymentGateway" in nodes
        for node in nodes.values():
            assert isinstance(node.get("label"), str)
            assert len(node.get("label", "")) <= 512

    def test_control_characters_are_stripped_from_accepted_labels(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"), "excerpt": "x",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "nodes": [{"id": "c:nul", "label": "Check\x00out", "file_type": "concept"}],
            "edges": [],
        }])

        apply(beacon_dir)

        label = _beacon_nodes(beacon_dir)["c:nul"]["label"]
        assert "\x00" not in label
        assert label == "Checkout"

    @pytest.mark.parametrize("bad_edge", [
        pytest.param({"target_name": 42}, id="int-target"),
        pytest.param({"target_name": "X" * 100_000}, id="oversized-target"),
        pytest.param({"target_name": "Gateway", "relation": 5}, id="int-relation"),
        pytest.param({"target_name": "Gateway", "confidence": 5}, id="int-confidence"),
        pytest.param("OrderService", id="not-a-dict"),
    ])
    def test_apply_survives_hostile_edge(self, tmp_path: Path, bad_edge):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"), "excerpt": "x",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "edges": [bad_edge, {"target_name": "AuditLog", "confidence_score": 0.9}],
        }])

        result = apply(beacon_dir)  # must not raise

        assert "AuditLog" in _beacon_nodes(beacon_dir)
        if bad_edge in ({"target_name": "Gateway", "relation": 5},
                        {"target_name": "Gateway", "confidence": 5}):
            # Sanitized rather than rejected: the target itself was fine.
            assert result.applied == 2
        else:
            assert result.applied == 1
            assert result.stats.edges_rejected_invalid == 1

    @pytest.mark.parametrize("entry", [
        pytest.param({"source_node_id": "svc:UserService", "nodes": ["JustAString"]},
                     id="node-not-dict"),
        pytest.param({"source_node_id": "svc:UserService",
                      "edges": [{"target_name": 42}]}, id="edge-target-int"),
        pytest.param({"source_node_id": "svc:UserService", "edges": ["OrderService"]},
                     id="edge-not-dict"),
        pytest.param({"source_node_id": "svc:UserService", "nodes": {"id": "c:1"}},
                     id="nodes-is-dict"),
        pytest.param("not-an-entry-at-all", id="entry-not-dict"),
    ])
    def test_archive_replay_survives_malformed_entry(self, tmp_path: Path, entry):
        """G-0932-3: the replay path enforces the SAME contract as apply()."""
        root, beacon_dir, src = _make_beacon(tmp_path)
        good = {
            "task_id": "T-good", "source_node_id": "svc:UserService",
            "edges": [{"target_name": "PaymentGateway", "confidence_score": 0.9}],
        }
        _write_chunk(beacon_dir, "original", "_legacy.jsonl", [entry, good])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = prepare(beacon_dir)  # must not raise

        assert result.reapplied_edges >= 1, "a good entry after a bad one must apply"
        assert "PaymentGateway" in _beacon_nodes(beacon_dir)

    def test_validators_are_pure_and_reject_in_isolation(self):
        assert _validate_llm_node({"id": "c:x", "label": {"a": 1},
                                   "file_type": "concept"}) is None
        assert _validate_llm_node("nope") is None
        assert _validate_llm_edge({"target_name": None}) is None
        assert _validate_llm_edge({"target_name": "Ok"})["target_name"] == "Ok"


# ── G-0949-12: node-only contributions must persist ──────────────────────────


class TestNodeOnlyPersistence:
    def test_node_only_result_reaches_beacon_json(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"), "excerpt": "x",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "nodes": [{"id": "c:checkout", "label": "Checkout Flow",
                       "file_type": "concept"}],
            "edges": [],
        }])

        result = apply(beacon_dir)

        assert result.applied == 0, "the row genuinely contributed no edge"
        assert result.nodes_applied == 1
        assert "c:checkout" in _beacon_nodes(beacon_dir), \
            "a node-only contribution must be persisted, not stranded in the archive"

    def test_node_only_archive_entry_survives_prepare(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "original", "_legacy.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "nodes": [{"id": "c:checkout", "label": "Checkout Flow",
                       "file_type": "concept"}],
            "edges": [],
        }])

        prepare(beacon_dir)

        assert "c:checkout" in _beacon_nodes(beacon_dir)

    def test_replay_stats_report_node_count(self, tmp_path: Path):
        G = nx.DiGraph()
        G.add_node("svc:A", label="A", type="service", source_file="a.java")
        stats = _ReplayStats()
        reapplied, kept = _reapply_archive(G, [{
            "task_id": "T", "source_node_id": "svc:A",
            "nodes": [{"id": "c:1", "label": "One", "file_type": "concept"}],
            "edges": [],
        }], stats)
        assert reapplied == 0 and stats.nodes_added == 1


# ── G-0948-5: result parsing recovery ────────────────────────────────────────


class TestResultParseRecovery:
    def test_pretty_printed_object_is_recovered(self, tmp_path: Path):
        p = tmp_path / "chunk_001.jsonl"
        p.write_text(json.dumps({"task_id": "T1", "edges": []}, indent=2),
                     encoding="utf-8")
        rows = list(_iter_jsonl(p))
        assert [r["task_id"] for r in rows] == ["T1"]

    def test_pretty_printed_list_is_recovered(self, tmp_path: Path):
        p = tmp_path / "chunk_001.jsonl"
        p.write_text(
            json.dumps([{"task_id": "T1"}, {"task_id": "T2"}, "junk"], indent=2),
            encoding="utf-8",
        )
        assert [r["task_id"] for r in _iter_jsonl(p)] == ["T1", "T2"]

    def test_fenced_pretty_printed_is_recovered(self, tmp_path: Path):
        p = tmp_path / "chunk_001.jsonl"
        p.write_text("```json\n" + json.dumps({"task_id": "T1"}, indent=2) + "\n```\n",
                     encoding="utf-8")
        assert [r["task_id"] for r in _iter_jsonl(p)] == ["T1"]

    def test_line_oriented_path_still_wins(self, tmp_path: Path):
        """The whole-file retry must not fire when the fast path worked."""
        p = tmp_path / "chunk_001.jsonl"
        p.write_text('{"task_id":"A"}\nnarration line\n{"task_id":"B"}\n',
                     encoding="utf-8")
        assert [r["task_id"] for r in _iter_jsonl(p)] == ["A", "B"]

    def test_unrecoverable_chunk_keeps_its_pending_file(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        pending = _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"), "excerpt": "x",
        }])
        results = beacon_dir / "semantic" / "results" / "chunk_001.jsonl"
        results.parent.mkdir(parents=True, exist_ok=True)
        results.write_text("total garbage, not json at all\n", encoding="utf-8")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = apply(beacon_dir)

        assert pending.exists(), \
            "the dispatched work order must survive an unusable result file"
        assert result.stats.chunks_unrecoverable == 1


# ── G-0949-21: excerpt truncation + whole-file task_id ───────────────────────


class TestExcerptTruncation:
    def test_slice_keeps_head_and_tail_within_budget(self):
        text = "HEAD" + ("x" * 300_000) + "TAIL"
        sliced, truncated = _slice_excerpt(text)
        assert truncated is True
        assert len(sliced) <= MAX_EXCERPT_CHARS
        assert sliced.startswith("HEAD")
        assert sliced.endswith("TAIL"), "the tail of a large file must survive"
        assert "elided" in sliced, "the cut must be announced inline"

    def test_short_file_is_untouched(self):
        sliced, truncated = _slice_excerpt("short file")
        assert (sliced, truncated) == ("short file", False)

    @staticmethod
    def _dispatch(beacon_dir: Path, src: Path, body: str) -> dict:
        """Rewrite the analysed file, re-run prepare, return its task."""
        (src / "UserService.java").write_text(body, encoding="utf-8")
        prepare(beacon_dir)
        chunks = sorted((beacon_dir / "semantic" / "pending").glob("chunk_*.jsonl"))
        tasks = [t for c in chunks for t in _iter_jsonl(c)
                 if t["file_path"].endswith("UserService.java")]
        assert tasks, "expected UserService.java to be dispatched"
        return tasks[0]

    def _prepare_one_task(self, tmp_path: Path, body: str) -> dict:
        _root, beacon_dir, src = _make_beacon(tmp_path)
        return self._dispatch(beacon_dir, src, body)

    def test_task_announces_truncation(self, tmp_path: Path):
        task = self._prepare_one_task(tmp_path, "class UserService {}\n" + "z" * 250_000)
        assert task["excerpt_truncated"] is True
        assert task["file_chars"] > MAX_EXCERPT_CHARS
        assert task["excerpt_chars"] == len(task["excerpt"])
        assert "partial view" in task["hint"], \
            "the agent must be told it is seeing a slice"

    def test_task_id_tracks_edits_the_agent_never_sees(self, tmp_path: Path):
        """The edit lands in the ELIDED MIDDLE — invisible in the excerpt.

        Targeting the middle rather than the tail is what makes this test
        pin the content hash specifically: the head+tail slice would pick up a
        tail edit on its own, so a tail-edit assertion stays green even when
        task_id is computed from the excerpt.
        """
        def body(middle: str) -> str:
            return ("class UserService {}\n" + "A" * 100_000
                    + middle + "B" * 100_000 + "// tail\n")

        # Same repo, same file path, rewritten in place — otherwise the path
        # component of the fingerprint would make the ids differ on its own.
        # Equal-length middles too: the elision marker quotes the file size, so
        # a length change would alter the excerpt through the marker.
        _root, beacon_dir, src = _make_beacon(tmp_path)
        first = self._dispatch(beacon_dir, src, body("// refs OrderServiceXX"))
        second = self._dispatch(beacon_dir, src, body("// refs PaymentGateway"))

        assert first["excerpt"] == second["excerpt"], (
            "precondition: the edited region must be outside the excerpt"
        )
        assert first["task_id"] != second["task_id"], (
            "a change anywhere in the file must re-dispatch it, even where the "
            "excerpt cannot show it"
        )

    def test_small_file_task_has_no_truncation_flag_set(self, tmp_path: Path):
        task = self._prepare_one_task(tmp_path, "class UserService { void go(){} }\n")
        assert task["excerpt_truncated"] is False
        assert "partial view" not in task["hint"]


# ── R2 fallout: the overlay must not become semantic-analysis input ──────────


class TestCandidateScoping:
    """Only source code is dispatched for semantic analysis.

    Before R2 a scan dropped the overlay, so overlay nodes were rarely present
    when semantic-prepare ran. Now that the overlay survives every scan, a
    1,000-note vault would otherwise dispatch 1,000 spurious LLM tasks — and
    knowledge notes already have their own linker.
    """

    def test_overlay_nodes_are_not_semantic_candidates(self, tmp_path: Path):
        _root, beacon_dir, src = _make_beacon(tmp_path)
        G, _ = load_beacon(beacon_dir / "beacon.json")
        G.add_node("knowledge::docs/adr.md", label="ADR", type="knowledge",
                   project="knowledge", source_file="docs/adr.md")
        G.add_node("c:concept", label="A Concept", type="concept",
                   project="", source_file="docs/concept.md")
        G.add_node("ExternalThing", label="ExternalThing", type="external",
                   project="", source_file="")

        files = {c.file_path for c in _pick_candidates(G)}

        assert "docs/adr.md" not in files, "a knowledge note is not code to analyse"
        assert "docs/concept.md" not in files, "an LLM-minted node is not input"
        assert any(f.endswith("UserService.java") for f in files), \
            "real source files must still be dispatched"

    def test_boost_pass_cannot_smuggle_an_overlay_file_back_in(
        self, tmp_path: Path, monkeypatch
    ):
        """The scoring boosts use ``+=`` on a defaultdict.

        That mints a file_score entry for a path the base pass skipped, so
        excluding overlay nodes there is not enough on its own — the final
        emission has to re-check. Driven through the hub-file boost, whose
        input is a file path rather than a node.
        """
        import codebeacon.graph.analyze as analyze

        _root, beacon_dir, _src = _make_beacon(tmp_path)
        G, _ = load_beacon(beacon_dir / "beacon.json")
        G.add_node("knowledge::docs/adr.md", label="ADR", type="knowledge",
                   project="knowledge", source_file="docs/adr.md")

        class _FakeHub:
            file_path = "docs/adr.md"
            import_count = 5

        monkeypatch.setattr(analyze, "hub_files", lambda _G: [_FakeHub()])

        files = {c.file_path for c in _pick_candidates(G)}
        assert "docs/adr.md" not in files

    def test_prepare_emits_no_task_for_a_note(self, tmp_path: Path):
        root, beacon_dir = _make_vault(tmp_path)
        result = build_knowledge_map(root, root)
        link_knowledge_to_graph(result, beacon_dir)

        prepare(beacon_dir)

        dispatched = [
            t["file_path"]
            for c in (beacon_dir / "semantic" / "pending").glob("chunk_*.jsonl")
            for t in _iter_jsonl(c)
        ]
        assert dispatched, "precondition: some code file was dispatched"
        assert not any(p.endswith(".md") for p in dispatched)


# ── G-0918-5: evidence marking on unresolved edge targets ────────────────────


class TestUnverifiedMarking:
    def test_literal_and_unverified_targets_are_distinguished(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"),
            "excerpt": "// mentions PaymentGateway explicitly",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "edges": [
                {"target_name": "PaymentGateway", "confidence_score": 0.9},
                {"target_name": "TotallyMadeUpGateway", "confidence_score": 0.9},
            ],
        }])

        result = apply(beacon_dir)

        nodes = _beacon_nodes(beacon_dir)
        assert nodes["PaymentGateway"]["verification"] == "literal"
        assert nodes["TotallyMadeUpGateway"]["verification"] == "unverified"
        assert result.stats.edge_targets_literal == 1
        assert result.stats.edge_targets_unverified == 1

    def test_ast_extracted_nodes_are_not_stamped(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"), "excerpt": "OrderService",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "edges": [{"target_name": "OrderService", "confidence_score": 0.9}],
        }])

        apply(beacon_dir)

        assert "verification" not in _beacon_nodes(beacon_dir)["svc:OrderService"]

    def test_verification_survives_archive_replay(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "original", "_legacy.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "edges": [{"target_name": "MadeUp", "confidence_score": 0.9,
                       "verification": "unverified"}],
        }])

        prepare(beacon_dir)

        assert _beacon_nodes(beacon_dir)["MadeUp"]["verification"] == "unverified"

    @pytest.mark.parametrize("bogus", ["trusted", "", 1, {"a": 1}, None])
    def test_archive_cannot_inject_an_arbitrary_verification_value(
        self, tmp_path: Path, bogus
    ):
        """The archive is hand-editable; only our own two values are honoured."""
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "original", "_legacy.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "edges": [{"target_name": "MadeUp", "confidence_score": 0.9,
                       "verification": bogus}],
        }])

        prepare(beacon_dir)

        node = _beacon_nodes(beacon_dir)["MadeUp"]
        assert node.get("verification") is None, (
            "an unrecognised provenance string must not reach the graph"
        )

    def test_validator_normalizes_verification(self):
        assert _validate_llm_edge({"target_name": "A",
                                   "verification": "literal"})["verification"] == "literal"
        assert _validate_llm_edge({"target_name": "A",
                                   "verification": "made-up"})["verification"] is None


# ── G-0949-13 residual A: a row must name its own task's source ──────────────


class TestTaskSourceMismatch:
    def test_row_naming_another_dispatched_task_source_is_skipped(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "svc:UserService",
             "file_path": str(src / "UserService.java"), "excerpt": "a"},
            {"task_id": "T2", "source_node_id": "svc:OrderService",
             "file_path": str(src / "OrderService.java"), "excerpt": "b"},
        ])
        # T1's result row claims T2's source — both ARE dispatched, so the
        # existing scope guard waves it through.
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:OrderService",
            "edges": [{"target_name": "WrongPlace", "confidence_score": 0.9}],
        }])

        with pytest.warns(UserWarning, match="was dispatched for"):
            result = apply(beacon_dir)

        assert result.applied == 0
        assert "WrongPlace" not in _beacon_nodes(beacon_dir)

    def test_matching_source_still_applies(self, tmp_path: Path):
        root, beacon_dir, src = _make_beacon(tmp_path)
        _write_chunk(beacon_dir, "pending", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "file_path": str(src / "UserService.java"), "excerpt": "a",
        }])
        _write_chunk(beacon_dir, "results", "chunk_001.jsonl", [{
            "task_id": "T1", "source_node_id": "svc:UserService",
            "edges": [{"target_name": "RightPlace", "confidence_score": 0.9}],
        }])
        assert apply(beacon_dir).applied == 1


# ── GI-2413 / G-0948-8 / G-0953-9: authored [[wikilinks]] ────────────────────


def _make_vault(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with a code graph and a multi-folder note vault."""
    root, beacon_dir, src = _make_beacon(tmp_path)
    (root / "docs" / "Concepts").mkdir(parents=True)
    (root / "docs" / "Entities").mkdir(parents=True)
    (root / "docs" / "Concepts" / "alpha.md").write_text(
        "# Alpha\n\nLinks to [[beta]], [[Entities/gamma]] and [[UserService]].\n",
        encoding="utf-8",
    )
    (root / "docs" / "Entities" / "beta.md").write_text(
        "# Beta\n\nBack to [[alpha]].\n", encoding="utf-8"
    )
    (root / "docs" / "Entities" / "gamma.md").write_text(
        "# Gamma\n\nNothing here.\n", encoding="utf-8"
    )
    return root, beacon_dir


class TestKnowledgeWikilinks:
    def test_cross_folder_wikilinks_materialise_edges(self, tmp_path: Path):
        root, beacon_dir = _make_vault(tmp_path)
        result = build_knowledge_map(root, root)
        link = link_knowledge_to_graph(result, beacon_dir)

        assert link is not None
        assert link.wikilink_edges >= 3, "authored links must not be dead data"

        G, _ = load_beacon(beacon_dir / "beacon.json")
        alpha = "knowledge::docs/Concepts/alpha.md"
        assert G.has_edge(alpha, "knowledge::docs/Entities/beta.md"), \
            "a bare [[beta]] must resolve vault-wide, not sibling-only"
        assert G.has_edge(alpha, "knowledge::docs/Entities/gamma.md"), \
            "a slashed [[Entities/gamma]] must resolve by path suffix"
        assert G.has_edge("knowledge::docs/Entities/beta.md", alpha)

    def test_code_symbol_wikilink_is_extracted_not_ambiguous(self, tmp_path: Path):
        root, beacon_dir = _make_vault(tmp_path)
        result = build_knowledge_map(root, root)
        link_knowledge_to_graph(result, beacon_dir)

        G, _ = load_beacon(beacon_dir / "beacon.json")
        edge = G.edges["knowledge::docs/Concepts/alpha.md", "svc:UserService"]
        assert edge["confidence"] == "EXTRACTED", (
            "an authored [[UserService]] is deliberate — it must outrank the "
            "AMBIGUOUS prose-mention heuristic"
        )

    def test_ambiguous_basename_resolves_deterministically_to_sibling(
        self, tmp_path: Path
    ):
        root, beacon_dir, _src = _make_beacon(tmp_path)
        for folder in ("Concepts", "Entities"):
            (root / "docs" / folder).mkdir(parents=True)
            (root / "docs" / folder / "shared.md").write_text(
                f"# Shared {folder}\n", encoding="utf-8"
            )
        (root / "docs" / "Concepts" / "linker.md").write_text(
            "# Linker\n\nSee [[shared]].\n", encoding="utf-8"
        )
        result = build_knowledge_map(root, root)
        link_knowledge_to_graph(result, beacon_dir)

        G, _ = load_beacon(beacon_dir / "beacon.json")
        linker = "knowledge::docs/Concepts/linker.md"
        assert G.has_edge(linker, "knowledge::docs/Concepts/shared.md"), \
            "a sibling must win an ambiguous basename"
        assert not G.has_edge(linker, "knowledge::docs/Entities/shared.md")

    def test_path_extraction_is_linear_on_a_dense_slash_run(self):
        """The path-token regex must not go quadratic on hostile prose.

        knowledge/ reads markdown from whatever tree is scanned, third-party
        repos included, and R2 runs it on every scan. Unbounded segment
        repetition cost 10.2s on 40k chars and 40.6s on 80k; the bounded form
        is linear. Asserted as a wall-clock ceiling generous enough not to be
        flaky on a loaded machine, but far below the quadratic curve.
        """
        import time

        hostile = "a/" * 20_000 + "x"  # 40k chars, no valid extension
        start = time.perf_counter()
        refs = extract_path_refs(hostile)
        elapsed = time.perf_counter() - start

        assert refs == set(), "no valid path token is present"
        assert elapsed < 2.0, f"took {elapsed:.1f}s — the segment bound is gone"

    def test_bounding_the_path_regex_does_not_change_what_resolves(self):
        """A path deeper than the bound still links to the same node.

        The bound trims a very deep ref to its tail, and _match_path_ref
        compares by path suffix, so the resolved node is unchanged. This is
        what makes the performance bound free rather than a recall trade.
        """
        deep = "/".join("abcdefghijklmnopqrstuvwxyz") + "/final.py"
        refs = extract_path_refs(f"see {deep} for details")
        assert len(refs) == 1
        ref = refs.pop()

        by_basename = {"final.py": [(deep, "node:1")]}
        assert _match_path_ref(ref, by_basename) == ["node:1"]

    def test_wikilink_anchors_and_extensions_are_normalized(self):
        assert normalize_wikilink("beta#Decision") == "beta"
        assert normalize_wikilink("Entities/beta.md") == "Entities/beta"
        assert normalize_wikilink("   ") == ""

    def test_unresolvable_wikilink_is_dropped_not_invented(self, tmp_path: Path):
        root, beacon_dir, _src = _make_beacon(tmp_path)
        (root / "docs").mkdir()
        (root / "docs" / "solo.md").write_text(
            "# Solo\n\nSee [[NoSuchNoteAnywhere]].\n", encoding="utf-8"
        )
        result = build_knowledge_map(root, root)
        link = link_knowledge_to_graph(result, beacon_dir)

        assert link.wikilink_edges == 0
        G, _ = load_beacon(beacon_dir / "beacon.json")
        assert "NoSuchNoteAnywhere" not in G

    def test_wikilinks_are_surfaced_in_knowledge_md(self, tmp_path: Path):
        root, _beacon_dir = _make_vault(tmp_path)
        result = build_knowledge_map(root, root)
        text = result.output_path.read_text(encoding="utf-8")
        assert "[[beta]]" in text, "parsed backlinks need a visible consumer"


# ── G-0946-5: node_kind + frontmatter passthrough ────────────────────────────


class TestKnowledgeSchema:
    def test_node_kind_and_frontmatter_reach_the_node(self, tmp_path: Path):
        root, beacon_dir, _src = _make_beacon(tmp_path)
        (root / "docs").mkdir()
        (root / "docs" / "adr-1.md").write_text(
            "---\ntitle: ADR 1\nstatus: accepted\nowner: platform\n"
            "epic: checkout\n---\n\n# ADR 1\n\nBody.\n",
            encoding="utf-8",
        )
        result = build_knowledge_map(root, root)
        link_knowledge_to_graph(result, beacon_dir)

        G, _ = load_beacon(beacon_dir / "beacon.json")
        data = G.nodes["knowledge::docs/adr-1.md"]
        assert data["node_kind"] == "page"
        assert data["frontmatter"] == {
            "epic": "checkout", "owner": "platform", "status": "accepted",
        }
        assert "title" not in data["frontmatter"], \
            "promoted keys must not be duplicated onto the node"

    def test_frontmatter_is_capped_and_sanitized(self, tmp_path: Path):
        root, beacon_dir, _src = _make_beacon(tmp_path)
        (root / "docs").mkdir()
        keys = "\n".join(f"k{i:03d}: v{i}" for i in range(40))
        (root / "docs" / "wide.md").write_text(
            f"---\ntitle: Wide\n{keys}\nnasty: 'a\x01b'\n---\n\n# Wide\n",
            encoding="utf-8",
        )
        result = build_knowledge_map(root, root)
        note = next(n for n in result.notes if n.path.endswith("wide.md"))

        assert len(note.frontmatter) <= MAX_FRONTMATTER_KEYS
        assert all("\x01" not in v for v in note.frontmatter.values())

    def test_hash_line_inside_frontmatter_is_not_read_as_the_title(
        self, tmp_path: Path
    ):
        root, _beacon_dir, _src = _make_beacon(tmp_path)
        (root / "docs").mkdir()
        (root / "docs" / "c.md").write_text(
            "---\n# a yaml comment\ntitle: Real Title\n---\n\n# Heading\n",
            encoding="utf-8",
        )
        result = build_knowledge_map(root, root)
        note = next(n for n in result.notes if n.path.endswith("c.md"))
        assert note.title == "Real Title"


# ── R2 / G-0949-14 / G-0952-1: overlay survives a rescan ─────────────────────


class TestKnowledgeOverlayLifecycle:
    def _linked_vault(self, tmp_path: Path) -> tuple[Path, Path]:
        root, beacon_dir = _make_vault(tmp_path)
        result = build_knowledge_map(root, root)
        link_knowledge_to_graph(result, beacon_dir)
        return root, beacon_dir

    def test_reapply_restores_the_overlay_after_a_code_only_write(
        self, tmp_path: Path
    ):
        root, beacon_dir = self._linked_vault(tmp_path)
        before = {n for n in load_beacon(beacon_dir / "beacon.json")[0]
                  if str(n).startswith("knowledge::")}
        assert before, "precondition: the overlay was linked"

        # Simulate what `codebeacon scan` does: rebuild from code alone.
        G, _ = load_beacon(beacon_dir / "beacon.json")
        G.remove_nodes_from(list(before))
        write_beacon(G, beacon_dir, force=True)
        assert not any(str(n).startswith("knowledge::")
                       for n in load_beacon(beacon_dir / "beacon.json")[0])

        assert reapply_knowledge(root, beacon_dir) == len(before)

        after = {n for n in load_beacon(beacon_dir / "beacon.json")[0]
                 if str(n).startswith("knowledge::")}
        assert after == before

    def test_reapply_is_a_no_op_without_an_overlay(self, tmp_path: Path):
        root, beacon_dir, _src = _make_beacon(tmp_path)
        assert reapply_knowledge(root, beacon_dir) == 0
        assert not (root / "KNOWLEDGE.md").exists(), \
            "a repo that never opted in must not gain a KNOWLEDGE.md from a scan"

    def test_foreign_knowledge_md_is_never_clobbered(self, tmp_path: Path):
        root, beacon_dir, _src = _make_beacon(tmp_path)
        handwritten = "# My own notes\n\nNot codebeacon's file.\n"
        (root / "KNOWLEDGE.md").write_text(handwritten, encoding="utf-8")

        assert reapply_knowledge(root, beacon_dir) == 0
        assert (root / "KNOWLEDGE.md").read_text(encoding="utf-8") == handwritten

    def test_reapply_warns_when_the_note_directory_is_gone(
        self, tmp_path: Path, capsys
    ):
        root, beacon_dir = self._linked_vault(tmp_path)
        state = json.loads((beacon_dir / "knowledge-state.json").read_text())
        state["root"] = str(tmp_path / "vanished")
        (beacon_dir / "knowledge-state.json").write_text(json.dumps(state))

        assert reapply_knowledge(root, beacon_dir) == -1
        assert "not reapplied" in capsys.readouterr().err, \
            "an overlay that cannot be rebuilt must never vanish silently"

    def test_reapply_is_idempotent(self, tmp_path: Path):
        root, beacon_dir = self._linked_vault(tmp_path)
        first = reapply_knowledge(root, beacon_dir)
        second = reapply_knowledge(root, beacon_dir)
        assert first == second > 0

    def test_overlay_is_rebuilt_without_touching_a_replaced_knowledge_md(
        self, tmp_path: Path
    ):
        """The user opted in, then hand-replaced KNOWLEDGE.md with their own.

        The state file still records the opt-in, so the overlay is rebuilt —
        but the file they now own must be left exactly as they wrote it.
        """
        root, beacon_dir = self._linked_vault(tmp_path)
        mine = "# My own map\n\nHand-written, do not touch.\n"
        (root / "KNOWLEDGE.md").write_text(mine, encoding="utf-8")

        assert reapply_knowledge(root, beacon_dir) > 0
        assert (root / "KNOWLEDGE.md").read_text(encoding="utf-8") == mine

    def test_missing_beacon_json_warns_rather_than_raising(
        self, tmp_path: Path, capsys
    ):
        root, beacon_dir = self._linked_vault(tmp_path)
        (beacon_dir / "beacon.json").unlink()

        assert reapply_knowledge(root, beacon_dir) == -1
        assert "no beacon.json" in capsys.readouterr().err

    def test_an_overlay_write_still_cannot_drop_a_code_node(self, tmp_path: Path):
        """The half of the overlay_write contract that must never be relaxed.

        The three overlay call sites declare ``overlay_write=True``, which trades
        per-source accounting (impossible without project roots) for a stricter
        additivity rule. That rule exists to protect AST-owned nodes: an overlay
        pass loads the graph and adds a tier, so a code node going missing is a
        bug in the overlay writer, not a rebuild. Pinned here from the caller
        side so a future loosening of the guard cannot pass unnoticed.
        """
        _root, beacon_dir, _src = _make_beacon(tmp_path)
        G, _ = load_beacon(beacon_dir / "beacon.json")
        G.remove_node("svc:OrderService")
        G.add_node("knowledge::n.md", label="N", type="knowledge",
                   project="knowledge", source_file="n.md")

        wr = write_beacon(G, beacon_dir, repo_path=beacon_dir, overlay_write=True)

        assert wr.skipped_shrink is True, "an overlay pass must not drop code nodes"
        after, _ = load_beacon(beacon_dir / "beacon.json")
        assert "svc:OrderService" in after, "beacon.json must be left untouched"

    def test_excerpt_slice_never_exceeds_the_budget(self):
        """Bounds check on the head+tail arithmetic, including the reserve."""
        from codebeacon.semantic_pipeline import _slice_excerpt as slice_

        for size in (0, 1, 199, MAX_EXCERPT_CHARS - 1, MAX_EXCERPT_CHARS,
                     MAX_EXCERPT_CHARS + 1, 50_000, 1_000_000):
            out, truncated = slice_("x" * size)
            assert len(out) <= MAX_EXCERPT_CHARS, size
            assert truncated == (size > MAX_EXCERPT_CHARS)
        for budget in (0, 1, 50, 199, 200, 201, 399):
            out, _ = slice_("y" * 1000, budget=budget)
            assert len(out) <= budget, budget

    def test_repeated_runs_do_not_touch_unchanged_artifacts(self, tmp_path: Path):
        """Idempotent writes: mtime must not move when nothing changed.

        `.codebeacon/` is committed and R2 rebuilds the overlay on every scan,
        so an unconditional write would wake Obsidian's indexer, sync clients,
        and watch mode on every run (GI-3060).
        """
        root, beacon_dir = self._linked_vault(tmp_path)
        km = root / "KNOWLEDGE.md"
        state = beacon_dir / "knowledge-state.json"
        before = (km.stat().st_mtime_ns, state.stat().st_mtime_ns)

        for _ in range(3):
            assert reapply_knowledge(root, beacon_dir) > 0

        assert (km.stat().st_mtime_ns, state.stat().st_mtime_ns) == before

    def test_an_unchanged_map_keeps_its_original_date_stamp(self, tmp_path: Path):
        """A new day is not a change. Mirrors R10's built_at_ts preservation."""
        root, beacon_dir = self._linked_vault(tmp_path)
        km = root / "KNOWLEDGE.md"
        km.write_text(
            km.read_text(encoding="utf-8").replace(
                _STAMP_RE.search(km.read_text(encoding="utf-8")).group(1),
                "2020-01-01",
            ),
            encoding="utf-8",
        )
        mtime = km.stat().st_mtime_ns

        build_knowledge_map(root, root)

        assert "2020-01-01" in km.read_text(encoding="utf-8")
        assert km.stat().st_mtime_ns == mtime

    def test_a_real_change_still_rewrites_the_map(self, tmp_path: Path):
        root, beacon_dir = self._linked_vault(tmp_path)
        km = root / "KNOWLEDGE.md"
        before = km.read_text(encoding="utf-8")

        (root / "docs" / "Concepts" / "new.md").write_text(
            "# Brand New Note\n\nAdded later.\n", encoding="utf-8"
        )
        build_knowledge_map(root, root)

        after = km.read_text(encoding="utf-8")
        assert after != before and "Brand New Note" in after

    def test_generated_map_is_recognised_but_a_foreign_one_is_not(self):
        assert is_generated_knowledge_map(
            "# Knowledge Map — demo\n\n---\n_Generated by codebeacon · 2026-01-01_\n"
        )
        assert not is_generated_knowledge_map("# Knowledge Map — demo\n")
        assert not is_generated_knowledge_map("we use codebeacon here\n")
        assert not is_generated_knowledge_map("")

    def test_context_maps_are_not_ingested_as_notes(self, tmp_path: Path):
        """CLAUDE.md / AGENTS.md are codebeacon's own output, not knowledge.

        A scan writes them into the repo root, so with the overlay now rebuilt
        on every scan they would otherwise be re-ingested as notes on each run.
        """
        root, beacon_dir, _src = _make_beacon(tmp_path)
        (root / "CLAUDE.md").write_text(
            "<!-- codebeacon:start -->\n# CLAUDE.md\n\nLookup strategy.\n\n"
            "_Generated by [codebeacon](https://github.com/codebeacon/codebeacon) "
            "· 2026-01-01_\n<!-- codebeacon:end -->\n",
            encoding="utf-8",
        )
        (root / "AGENTS.md").write_text(
            "# AGENTS.md\n\n_Generated by [codebeacon](https://x) · 2026-01-01_\n",
            encoding="utf-8",
        )
        (root / "real-note.md").write_text("# A Real Note\n\nMine.\n", encoding="utf-8")

        result = build_knowledge_map(root, root)

        paths = {n.path for n in result.notes}
        assert paths == {"real-note.md"}, f"unexpected notes ingested: {paths}"

    def test_a_users_own_claude_md_without_our_markers_is_still_a_note(
        self, tmp_path: Path
    ):
        root, _beacon_dir, _src = _make_beacon(tmp_path)
        (root / "CLAUDE.md").write_text(
            "# CLAUDE.md\n\nHand-written house rules, no codebeacon block.\n",
            encoding="utf-8",
        )
        result = build_knowledge_map(root, root)
        assert "CLAUDE.md" in {n.path for n in result.notes}
