"""Audit 0.6.9 — group F-J regression tests for the semantic pipeline.

Two confirmed bugs are pinned here:

  * G12 (semantic source/scope clobber). ``semantic apply`` trusted two
    LLM-supplied fields verbatim:
      - a concept/document/paper node's ``source_file`` — if it equalled a
        real code node's ``source_file`` (or was an absolute foreign path),
        obsidian's Step-6 "same source_file" dedup would group the LLM note
        with the real note and delete the loser, destroying the real file's
        note. The fix blanks such source_files in ``_merge_node``.
      - a result row's ``source_node_id`` — a mis-attributed row could inject
        edges onto a node that was never dispatched in the chunk. The fix
        skips (and warns on) out-of-scope rows in ``apply()``.

  * BH-S4 (legacy-archive migrate double-append). ``_migrate_legacy_archive``
    appended the 0.3.x ``original.jsonl`` to ``original/_legacy.jsonl`` and
    then unlinked the source — a crash in between double-appended every
    legacy entry on the next run. The fix makes the merge crash-safe
    (temp file + os.replace before unlink) and idempotent (dedupe on task_id).
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import networkx.readwrite.json_graph as nxjson
import pytest

from codebeacon.graph.write import load_beacon
from codebeacon.semantic_pipeline import (
    LEGACY_ARCHIVE_FILENAME,
    LEGACY_MIGRATED_NAME,
    ORIGINAL_SUBDIR,
    SEMANTIC_DIRNAME,
    _archive_entry_key,
    _code_source_files,
    _label_index,
    _merge_node,
    _migrate_legacy_archive,
    apply,
)


# ── Fixtures / helpers ──────────────────────────────────────────────────────

def _graph_with_code_nodes() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node(
        "user_svc", label="UserService", type="service",
        source_file="UserService.java", project="proj", line=1,
    )
    G.add_node(
        "pay_svc", label="PaymentService", type="service",
        source_file="PaymentService.java", project="proj", line=1,
    )
    return G


def _write_beacon(beacon_dir: Path, G: nx.DiGraph) -> None:
    beacon_dir.mkdir(parents=True, exist_ok=True)
    (beacon_dir / "beacon.json").write_text(
        json.dumps(nxjson.node_link_data(G), ensure_ascii=False),
        encoding="utf-8",
    )


def _write_chunk(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _nonblank_lines(p: Path) -> list[str]:
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ── G12 guard 1: source_file sanitation in _merge_node ──────────────────────

class TestMergeNodeSourceFileGuard:
    def test_blanks_source_file_colliding_with_code_node(self):
        """A concept whose source_file equals a real code node's must NOT keep
        it — that shared value is exactly what obsidian Step-6 dedup groups on
        to (wrongly) delete the real note."""
        G = _graph_with_code_nodes()
        idx = _label_index(G)
        assert _merge_node(
            G, idx,
            node_id="spoof", label="PaymentService.java",
            file_type="concept", source_file="PaymentService.java",
        )
        assert G.nodes["spoof"]["source_file"] == ""
        # The real code node is untouched.
        assert G.nodes["pay_svc"]["source_file"] == "PaymentService.java"

    def test_blanks_absolute_foreign_source_file(self):
        G = _graph_with_code_nodes()
        idx = _label_index(G)
        assert _merge_node(
            G, idx,
            node_id="escape", label="Escape",
            file_type="concept", source_file="/etc/passwd",
        )
        assert G.nodes["escape"]["source_file"] == ""

    def test_keeps_noncolliding_relative_source_file(self):
        """A legitimate relative doc path that collides with nothing is kept —
        the guard is surgical, not a blanket wipe."""
        G = _graph_with_code_nodes()
        idx = _label_index(G)
        assert _merge_node(
            G, idx,
            node_id="doc", label="OAuth2 spec",
            file_type="concept", source_file="docs/oauth.md",
        )
        assert G.nodes["doc"]["source_file"] == "docs/oauth.md"

    def test_uses_caller_supplied_protected_set(self):
        """apply()/reapply pass a precomputed snapshot of code source_files;
        the guard must honour it even when G itself has no code node yet."""
        G = nx.DiGraph()
        idx = _label_index(G)
        assert _merge_node(
            G, idx,
            node_id="c", label="C",
            file_type="concept", source_file="PaymentService.java",
            protected_source_files={"PaymentService.java"},
        )
        assert G.nodes["c"]["source_file"] == ""

    def test_code_source_files_excludes_llm_node_types(self):
        G = _graph_with_code_nodes()
        G.add_node(
            "concept1", label="C", type="concept",
            source_file="docs/x.md", project="", line=0,
        )
        protected = _code_source_files(G)
        assert protected == {"UserService.java", "PaymentService.java"}
        assert "docs/x.md" not in protected


class TestApplySourceFileGuardEndToEnd:
    def test_colliding_concept_source_file_blanked_in_graph_and_archive(self, tmp_path):
        """End-to-end: a spoof concept whose source_file collides with a real
        code node must land with a blank source_file both in beacon.json and
        in the durable archive (so a later prepare() replay can't reintroduce
        the collision that deletes the real note)."""
        _write_beacon(tmp_path, _graph_with_code_nodes())
        sem = tmp_path / "semantic"
        _write_chunk(sem / "pending" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "user_svc",
             "file_path": "UserService.java"},
        ])
        _write_chunk(sem / "results" / "chunk_001.jsonl", [
            {
                "task_id": "T1", "source_node_id": "user_svc",
                "nodes": [{
                    "id": "spoof_pay", "label": "PaymentService.java",
                    "file_type": "concept", "source_file": "PaymentService.java",
                }],
                "edges": [{
                    "target_name": "PaymentService.java",
                    "relation": "references", "confidence_score": 0.9,
                }],
            },
        ])

        apply(tmp_path, min_confidence=0.0)

        G2, _ = load_beacon(tmp_path / "beacon.json")
        assert "spoof_pay" in G2
        # The concept did NOT inherit the code node's source_file — the exact
        # collision that would let obsidian Step-6 delete the real note.
        assert G2.nodes["spoof_pay"]["source_file"] == ""
        assert G2.nodes["pay_svc"]["source_file"] == "PaymentService.java"

        archive = _nonblank_lines(sem / "original" / "chunk_001.jsonl")
        entry = json.loads(archive[0])
        assert entry["nodes"][0]["source_file"] == ""


# ── G12 guard 2: out-of-scope source_node_id in apply() ─────────────────────

class TestApplyScopeGuard:
    def test_skips_and_warns_on_undispatched_source_node_id(self, tmp_path):
        """A result row whose source_node_id was never dispatched in this chunk
        must not inject edges onto that (unrelated) node."""
        _write_beacon(tmp_path, _graph_with_code_nodes())
        sem = tmp_path / "semantic"
        _write_chunk(sem / "pending" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "user_svc",
             "file_path": "UserService.java"},
        ])
        # Row claims pay_svc, which was NOT dispatched (only user_svc was).
        _write_chunk(sem / "results" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "pay_svc",
             "edges": [{"target_name": "InjectedByWrongScope",
                        "relation": "references", "confidence_score": 0.9}]},
        ])

        with pytest.warns(UserWarning, match="not dispatched"):
            result = apply(tmp_path, min_confidence=0.0)

        assert result.applied == 0
        # Applied == 0 short-circuits the beacon rewrite, so reloading gives
        # the original graph: the injected edge/target never landed.
        G2, _ = load_beacon(tmp_path / "beacon.json")
        assert "InjectedByWrongScope" not in G2
        assert not any(G2.has_edge("pay_svc", n) for n in G2.nodes)

    def test_allows_dispatched_source_node_id(self, tmp_path):
        """Control: the same fixture but with an in-scope source_node_id must
        apply normally — the guard only blocks mismatches."""
        _write_beacon(tmp_path, _graph_with_code_nodes())
        sem = tmp_path / "semantic"
        _write_chunk(sem / "pending" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "user_svc",
             "file_path": "UserService.java"},
        ])
        _write_chunk(sem / "results" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "user_svc",
             "edges": [{"target_name": "PaymentService",
                        "relation": "references", "confidence_score": 0.9}]},
        ])

        result = apply(tmp_path, min_confidence=0.0)
        assert result.applied == 1
        G2, _ = load_beacon(tmp_path / "beacon.json")
        assert G2.has_edge("user_svc", "pay_svc")

    def test_out_of_scope_row_concept_node_leaks_edgeless_and_unarchived(self, tmp_path):
        """Documented G12 accepted-leak: Pass 1 merges the concept node of an
        out-of-scope row before Guard 2 skips the row. When another in-scope row
        makes applied>0, the graph is persisted and that orphan concept node
        lands in beacon.json — but edgeless, with its colliding source_file
        blanked (Guard 1), and absent from the archive. Accepted because it
        causes no obsidian note deletion and no stray edges. Pins the tolerated
        behaviour so a future 'defer node registration until scope-confirmed'
        change is a conscious decision."""
        _write_beacon(tmp_path, _graph_with_code_nodes())
        sem = tmp_path / "semantic"
        _write_chunk(sem / "pending" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "user_svc",
             "file_path": "UserService.java"},
        ])
        _write_chunk(sem / "results" / "chunk_001.jsonl", [
            # In-scope row: applies one edge so applied>0 → beacon.json rewritten.
            {"task_id": "T1", "source_node_id": "user_svc",
             "edges": [{"target_name": "PaymentService",
                        "relation": "references", "confidence_score": 0.9}]},
            # Out-of-scope row: pay_svc was NOT dispatched. Its concept node's
            # source_file collides with a real code node (blanked by Guard 1).
            {"task_id": "T2", "source_node_id": "pay_svc",
             "nodes": [{"id": "orphan_concept", "label": "OrphanConcept",
                        "file_type": "concept",
                        "source_file": "PaymentService.java"}],
             "edges": [{"target_name": "Whatever",
                        "relation": "references", "confidence_score": 0.9}]},
        ])

        with pytest.warns(UserWarning, match="not dispatched"):
            result = apply(tmp_path, min_confidence=0.0)
        assert result.applied == 1

        G2, _ = load_beacon(tmp_path / "beacon.json")
        # The orphan concept leaked into the persisted graph …
        assert "orphan_concept" in G2
        # … but edgeless and with its colliding source_file blanked, so it
        # cannot drive an obsidian note deletion.
        assert G2.nodes["orphan_concept"]["source_file"] == ""
        assert G2.out_degree("orphan_concept") == 0
        assert G2.in_degree("orphan_concept") == 0
        # The out-of-scope edge never landed anywhere.
        assert "Whatever" not in G2
        assert not any(G2.has_edge("pay_svc", n) for n in G2.nodes)
        # And the leaked node is NOT archived — only the in-scope T1 is.
        archive = _nonblank_lines(sem / "original" / "chunk_001.jsonl")
        assert len(archive) == 1
        entry = json.loads(archive[0])
        assert entry["task_id"] == "T1"
        assert entry.get("nodes", []) == []

    def test_no_pending_file_keeps_defensive_archive_path(self, tmp_path):
        """When no pending file exists (manual-edit / legacy path) there is
        nothing to validate against, so the row must still be archived — the
        scope guard must not over-block this case."""
        _write_beacon(tmp_path, _graph_with_code_nodes())
        sem = tmp_path / "semantic"
        # results/ only — deliberately NO pending/chunk_001.jsonl.
        _write_chunk(sem / "results" / "chunk_001.jsonl", [
            {"task_id": "T1", "source_node_id": "user_svc",
             "edges": [{"target_name": "PaymentService",
                        "relation": "references", "confidence_score": 0.9}]},
        ])

        result = apply(tmp_path, min_confidence=0.0)
        assert result.applied == 1


# ── BH-S4: crash-safe, idempotent legacy-archive migration ──────────────────

def _seed_migration(tmp_path: Path) -> tuple[Path, Path, Path]:
    beacon = tmp_path / ".codebeacon"
    sem = beacon / SEMANTIC_DIRNAME
    odir = sem / ORIGINAL_SUBDIR
    odir.mkdir(parents=True)
    legacy = sem / LEGACY_ARCHIVE_FILENAME
    target = odir / LEGACY_MIGRATED_NAME
    return beacon, legacy, target


class TestMigrateLegacyArchive:
    def test_crash_before_unlink_does_not_double_append_on_rerun(self, tmp_path, monkeypatch):
        """Faithful BH-S4 repro: crash at legacy.unlink() (after the merged
        target is committed), then re-run. The legacy entry must appear once,
        not twice."""
        beacon, legacy, target = _seed_migration(tmp_path)
        target.write_text('{"task_id":"existing","source_node_id":"x","edges":[]}\n')
        legacy.write_text('{"task_id":"legacy1","source_node_id":"y","edges":[]}\n')

        real_unlink = Path.unlink
        state = {"crashed": False}

        def crashing_unlink(self, *a, **kw):
            if not state["crashed"] and self.name == LEGACY_ARCHIVE_FILENAME:
                state["crashed"] = True
                raise RuntimeError("simulated crash before unlink committed")
            return real_unlink(self, *a, **kw)

        monkeypatch.setattr(Path, "unlink", crashing_unlink)
        with pytest.raises(RuntimeError):
            _migrate_legacy_archive(beacon)
        # Legacy survived; target already holds the merged content.
        assert legacy.exists()
        assert state["crashed"] is True
        monkeypatch.undo()

        # Process restarts and re-runs the migration.
        _migrate_legacy_archive(beacon)

        lines = _nonblank_lines(target)
        assert sum('"task_id":"legacy1"' in ln for ln in lines) == 1
        assert sum('"task_id":"existing"' in ln for ln in lines) == 1
        assert not legacy.exists()

    def test_merge_preserves_both_entries_once(self, tmp_path):
        beacon, legacy, target = _seed_migration(tmp_path)
        target.write_text('{"task_id":"existing","source_node_id":"x","edges":[]}\n')
        legacy.write_text('{"task_id":"legacy1","source_node_id":"y","edges":[]}\n')

        _migrate_legacy_archive(beacon)

        lines = _nonblank_lines(target)
        assert len(lines) == 2
        keys = {json.loads(ln)["task_id"] for ln in lines}
        assert keys == {"existing", "legacy1"}
        assert not legacy.exists()

    def test_merge_dedups_entry_already_present_in_target(self, tmp_path):
        """If a prior crashed run already merged legacy1 into target, a re-run
        with legacy still present must not duplicate it."""
        beacon, legacy, target = _seed_migration(tmp_path)
        target.write_text(
            '{"task_id":"existing","source_node_id":"x","edges":[]}\n'
            '{"task_id":"legacy1","source_node_id":"y","edges":[]}\n'
        )
        legacy.write_text('{"task_id":"legacy1","source_node_id":"y","edges":[]}\n')

        _migrate_legacy_archive(beacon)

        lines = _nonblank_lines(target)
        assert sum('"task_id":"legacy1"' in ln for ln in lines) == 1
        assert not legacy.exists()

    def test_same_tid_divergent_edges_keeps_target_copy_only(self, tmp_path):
        """Documented BH-S4 tradeoff: when the migration target and the legacy
        file share a task_id but carry DIVERGENT edge sets (a non-deterministic
        LLM re-analysing the same unchanged file/node/excerpt), the two are
        treated as one — the target copy wins and the legacy copy is dropped
        whole. Divergent same-tid edge sets are intentionally NOT unioned; the
        lost edges are regenerable inferred edges. Pins the accepted behaviour
        so a future 'union the edges' change is a conscious decision."""
        beacon, legacy, target = _seed_migration(tmp_path)
        target.write_text(json.dumps({
            "task_id": "abc", "source_node_id": "svcA",
            "edges": [{"target_name": "TargetX"}],
        }) + "\n")
        legacy.write_text(json.dumps({
            "task_id": "abc", "source_node_id": "svcA",
            "edges": [{"target_name": "TargetY"}],
        }) + "\n")

        _migrate_legacy_archive(beacon)

        lines = _nonblank_lines(target)
        assert len(lines) == 1
        entry = json.loads(lines[0])
        # Only the target copy's edge survives; the divergent legacy edge is
        # dropped (not unioned).
        assert [e["target_name"] for e in entry["edges"]] == ["TargetX"]
        assert not legacy.exists()

    def test_first_time_migration_moves_file(self, tmp_path):
        """No pre-existing target → the plain move path, unchanged."""
        beacon, legacy, target = _seed_migration(tmp_path)
        legacy.write_text('{"task_id":"legacy1","source_node_id":"y","edges":[]}\n')
        assert not target.exists()

        _migrate_legacy_archive(beacon)

        assert not legacy.exists()
        lines = _nonblank_lines(target)
        assert len(lines) == 1
        assert json.loads(lines[0])["task_id"] == "legacy1"

    def test_noop_when_no_legacy_file(self, tmp_path):
        beacon, legacy, target = _seed_migration(tmp_path)
        target.write_text('{"task_id":"existing","source_node_id":"x","edges":[]}\n')
        # No legacy file at all.
        _migrate_legacy_archive(beacon)
        assert _nonblank_lines(target) == [
            '{"task_id":"existing","source_node_id":"x","edges":[]}'
        ]


class TestArchiveEntryKey:
    def test_prefers_task_id(self):
        assert _archive_entry_key('{"task_id":"abc","x":1}') == "tid:abc"
        # Same task_id, different payload → same dedup key.
        assert _archive_entry_key('{"task_id":"abc","x":2}') == "tid:abc"

    def test_falls_back_to_raw_text_without_task_id(self):
        raw = '{"source_node_id":"n","edges":[]}'
        assert _archive_entry_key(raw) == raw

    def test_falls_back_to_raw_text_on_non_json(self):
        assert _archive_entry_key("not json") == "not json"
