"""Tests for the new safety / write / merge / promotion / ignore modules.

These guard the cross-cutting safety story added in 0.3.0:

- ``write_beacon`` refuses to shrink beacon.json without ``force``.
- ``built_at_commit`` is embedded and surfaced in REPORT.md.
- frontmatter / label sanitization strips the characters that would otherwise
  break YAML parsing or leak control sequences into MCP tool output.
- ``IgnoreMatcher`` implements last-match-wins + negation + dir-pruning.
- ``promote_confirmed_calls`` lifts INFERRED to EXTRACTED only when proven.
- ``Cache`` uses an mtime+size fast path and a content-hash fallback.
- ``merge_files`` unions two beacon.json files.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import networkx as nx
import pytest

from codebeacon.cache import Cache
from codebeacon.common.safety import escape_frontmatter_value, sanitize_label
from codebeacon.discover.ignore import IgnoreMatcher
from codebeacon.export.merge import merge_files
from codebeacon.graph.analyze import GraphReport, report_to_markdown
from codebeacon.graph.enrich import promote_confirmed_calls
from codebeacon.graph.write import load_beacon, write_beacon


class TestSanitize:
    def test_strips_c0_controls(self):
        assert sanitize_label("foo\x00bar\x1fbaz") == "foobarbaz"

    def test_strips_line_separators(self):
        assert sanitize_label("a b c") == "abc"

    def test_collapses_whitespace(self):
        assert sanitize_label("  a   b\tc  ") == "a b c"

    def test_handles_none(self):
        assert sanitize_label(None) == ""


class TestFrontmatter:
    def test_doubles_single_quotes(self):
        assert escape_frontmatter_value("it's") == "it''s"

    def test_strips_line_separators(self):
        assert escape_frontmatter_value("a b c") == "abc"

    def test_replaces_newlines_with_space(self):
        assert escape_frontmatter_value("line1\nline2\tx") == "line1 line2 x"

    def test_strips_c0_minus_whitespace(self):
        # \x01 is removed, but \n and \t are normalised (not removed).
        assert escape_frontmatter_value("a\x01b\nc") == "ab c"


class TestIgnoreMatcher:
    @pytest.mark.parametrize("rules,path,is_dir,want", [
        (["build/"], "build", True, True),
        (["build/"], "build", False, False),
        (["build/"], "build/foo.ts", False, True),
        (["build/"], "build/sub/x.ts", False, True),
        (["build/", "!build/keep.ts"], "build/foo.ts", False, True),
        (["build/", "!build/keep.ts"], "build/keep.ts", False, False),
        (["generated"], "generated/auto.py", False, True),
        (["generated"], "src/manual.py", False, False),
        (["/secrets.txt"], "secrets.txt", False, True),
        (["/secrets.txt"], "foo/secrets.txt", False, False),
        (["*.log"], "foo/bar.log", False, True),
        (["*.gen.ts", "!api.gen.ts"], "api.gen.ts", False, False),
        (["*.gen.ts", "!api.gen.ts"], "other.gen.ts", False, True),
        (["# comment", "", "build/"], "build/foo", False, True),
    ])
    def test_cases(self, rules, path, is_dir, want):
        assert IgnoreMatcher(rules).is_ignored(path, is_dir=is_dir) == want


class TestWriteBeacon:
    def test_writes_meta_block(self, tmp_path):
        G = nx.DiGraph()
        G.add_node("a", label="A")
        wr = write_beacon(G, tmp_path)
        data = json.loads((tmp_path / "beacon.json").read_text())
        assert data["meta"]["version"] == 1
        assert data["meta"]["node_count"] == 1
        assert "built_at_ts" in data["meta"]
        assert wr.skipped_shrink is False

    def test_shrink_guard_refuses_smaller_overwrite(self, tmp_path):
        G_big = nx.DiGraph()
        for i in range(5):
            G_big.add_node(f"n{i}")
        write_beacon(G_big, tmp_path)

        G_small = nx.DiGraph()
        G_small.add_node("only")
        wr = write_beacon(G_small, tmp_path)
        assert wr.skipped_shrink is True

        # Original 5-node graph still on disk
        on_disk, _ = load_beacon(tmp_path / "beacon.json")
        assert on_disk.number_of_nodes() == 5

    def test_force_bypasses_shrink_guard(self, tmp_path):
        G_big = nx.DiGraph()
        G_big.add_node("a"); G_big.add_node("b"); G_big.add_node("c")
        write_beacon(G_big, tmp_path)

        G_small = nx.DiGraph()
        G_small.add_node("only")
        wr = write_beacon(G_small, tmp_path, force=True)
        assert wr.skipped_shrink is False
        on_disk, _ = load_beacon(tmp_path / "beacon.json")
        assert on_disk.number_of_nodes() == 1

    def test_had_explicit_deletions_bypasses_shrink_guard(self, tmp_path):
        """Mirrors graphify #6fba4e4.

        ``--update`` mode informs the cache of deleted files, so a smaller
        post-update graph is the expected outcome — not silent corruption.
        Without this bypass, every delete-heavy commit would leave stale
        nodes on disk and force the user to pass --force (which disables
        the guard for legitimate failure modes too)."""
        G_big = nx.DiGraph()
        for i in range(5):
            G_big.add_node(f"n{i}")
        write_beacon(G_big, tmp_path)

        # Caller explicitly knows 4 files were deleted → smaller graph OK
        G_small = nx.DiGraph()
        G_small.add_node("n0")
        wr = write_beacon(G_small, tmp_path, had_explicit_deletions=True)
        assert wr.skipped_shrink is False
        on_disk, _ = load_beacon(tmp_path / "beacon.json")
        assert on_disk.number_of_nodes() == 1

    def test_shrink_guard_still_fires_without_explicit_deletions(self, tmp_path):
        """Regression bookend: ``had_explicit_deletions=False`` (default) MUST
        still refuse silent shrinkage. Otherwise the new flag would have
        effectively disabled the guard for every caller."""
        G_big = nx.DiGraph()
        for i in range(5):
            G_big.add_node(f"n{i}")
        write_beacon(G_big, tmp_path)

        G_small = nx.DiGraph()
        G_small.add_node("only")
        wr = write_beacon(G_small, tmp_path, had_explicit_deletions=False)
        assert wr.skipped_shrink is True

    def test_load_strips_meta(self, tmp_path):
        G = nx.DiGraph()
        G.add_node("a", label="A")
        write_beacon(G, tmp_path)
        loaded, meta = load_beacon(tmp_path / "beacon.json")
        # Meta is returned separately, not as a graph attribute
        assert loaded.number_of_nodes() == 1
        assert meta.get("version") == 1


class TestReportBuildCommit:
    def test_renders_stale_warning(self):
        r = GraphReport(node_count=1, edge_count=0, built_at_commit="a" * 40, current_commit="b" * 40)
        out = report_to_markdown(r)
        assert "stale" in out
        assert "aaaaaaaa" in out  # short SHA
        assert "bbbbbbbb" in out

    def test_renders_fresh_line(self):
        r = GraphReport(node_count=1, edge_count=0, built_at_commit="abcdef0123", current_commit="abcdef0123")
        out = report_to_markdown(r)
        assert "stale" not in out
        assert "abcdef01" in out


class TestPromoteConfirmedCalls:
    def test_promotes_when_import_proves_binding(self):
        G = nx.DiGraph()
        G.add_node("A", source_file="a.py")
        G.add_node("B", source_file="b.py")
        G.add_node("bFn", source_file="b.py")
        G.add_edge("A", "B", relation="imports_from", confidence="EXTRACTED", confidence_score=1.0)
        G.add_edge("A", "bFn", relation="calls", confidence="INFERRED", confidence_score=0.5)
        assert promote_confirmed_calls(G) == 1
        assert G["A"]["bFn"]["confidence"] == "EXTRACTED"
        assert G["A"]["bFn"]["confidence_score"] == 1.0

    def test_does_not_promote_without_import(self):
        G = nx.DiGraph()
        G.add_node("A", source_file="a.py")
        G.add_node("C", source_file="c.py")
        G.add_edge("A", "C", relation="calls", confidence="INFERRED", confidence_score=0.5)
        assert promote_confirmed_calls(G) == 0
        assert G["A"]["C"]["confidence"] == "INFERRED"

    def test_skips_same_file(self):
        G = nx.DiGraph()
        G.add_node("A", source_file="a.py")
        G.add_node("aHelper", source_file="a.py")
        G.add_edge("A", "aHelper", relation="calls", confidence="INFERRED", confidence_score=0.5)
        # Same file → not "cross-file", nothing to promote
        assert promote_confirmed_calls(G) == 0


class TestCacheMtimeFastPath:
    def test_fast_path_skips_hashing(self, tmp_path):
        src = tmp_path / "foo.py"
        src.write_text("x = 1\n")
        cache = Cache(str(tmp_path))
        cache.put(str(src), {"result": "v1"})

        cache.save()
        fresh = Cache(str(tmp_path))
        fresh.load()
        # Stat-only fast path — should not need to hash
        fresh._hash_memo.clear()
        assert fresh.is_fresh(str(src)) is True
        assert str(src) not in fresh._hash_memo

    def test_mtime_bump_content_unchanged(self, tmp_path):
        src = tmp_path / "foo.py"
        src.write_text("x = 1\n")
        cache = Cache(str(tmp_path))
        cache.put(str(src), {"result": "v1"})
        cache.save()

        # Bump mtime forward — sync tool simulation
        future = time.time() + 1000
        os.utime(src, (future, future))

        fresh = Cache(str(tmp_path))
        fresh.load()
        # Slow path runs but content hash matches; returns cached result.
        assert fresh.get(str(src)) == {"result": "v1"}
        # stat fields refreshed in-place
        assert fresh._data[str(src)]["mtime_ns"] == os.stat(src).st_mtime_ns

    def test_content_change_invalidates(self, tmp_path):
        src = tmp_path / "foo.py"
        src.write_text("x = 1\n")
        cache = Cache(str(tmp_path))
        cache.put(str(src), {"result": "v1"})
        cache.save()

        src.write_text("x = 2\n")
        fresh = Cache(str(tmp_path))
        fresh.load()
        assert fresh.get(str(src)) is None


class TestMergeDriver:
    def test_unions_nodes_and_edges(self, tmp_path):
        base = tmp_path / "base.json"
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        base.write_text(json.dumps({"nodes": [], "links": []}))
        cur.write_text(json.dumps({
            "nodes": [{"id": "a"}, {"id": "b"}],
            "links": [{"source": "a", "target": "b", "relation": "calls"}],
            "meta": {"version": 1, "node_count": 2, "edge_count": 1},
        }))
        other.write_text(json.dumps({
            "nodes": [{"id": "b"}, {"id": "c"}],
            "links": [{"source": "b", "target": "c", "relation": "calls"}],
        }))
        assert merge_files(str(base), str(cur), str(other)) == 0
        merged = json.loads(cur.read_text())
        assert {n["id"] for n in merged["nodes"]} == {"a", "b", "c"}
        assert merged["meta"]["node_count"] == 3
        assert merged["meta"]["edge_count"] == 2

    def test_real_write_beacon_roundtrip(self, tmp_path):
        """Two graphs written by write_beacon (modern NetworkX 'edges' key)
        merge without dropping edges. This is the bug graphify hit in 0.7.10
        when the key shifted from 'links' to 'edges'."""
        G1 = nx.DiGraph()
        G1.add_node("a"); G1.add_node("b")
        G1.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
        G2 = nx.DiGraph()
        G2.add_node("b"); G2.add_node("c")
        G2.add_edge("b", "c", relation="calls", confidence="EXTRACTED")

        d1 = tmp_path / "d1"; d2 = tmp_path / "d2"
        write_beacon(G1, d1); write_beacon(G2, d2)

        # Use d1 as the "current" file and d2 as "other"
        cur = d1 / "beacon.json"
        assert merge_files("", str(cur), str(d2 / "beacon.json")) == 0

        merged_doc = json.loads(cur.read_text())
        # Whichever key the writer used must survive into the merged doc.
        edges = merged_doc.get("edges", merged_doc.get("links", []))
        assert len(edges) == 2, f"expected 2 edges after union, got {len(edges)}: {edges}"

        # And load_beacon should round-trip the merged result.
        merged_G, _ = load_beacon(cur)
        assert merged_G.number_of_nodes() == 3
        assert merged_G.number_of_edges() == 2

    def test_links_input_preserves_links_key(self, tmp_path):
        """A legacy 'links' input keeps the 'links' shape after merge."""
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        cur.write_text(json.dumps({
            "nodes": [{"id": "a"}],
            "links": [{"source": "a", "target": "a"}],
        }))
        other.write_text(json.dumps({"nodes": [{"id": "b"}], "links": []}))
        assert merge_files("", str(cur), str(other)) == 0
        doc = json.loads(cur.read_text())
        assert "links" in doc and "edges" not in doc

    def test_always_returns_zero_even_on_garbage(self, tmp_path):
        # Even when both inputs are broken, we never block git
        base = tmp_path / "base.json"
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        cur.write_text("not json")
        other.write_text("not json either")
        assert merge_files(str(base), str(cur), str(other)) == 0


class TestLoadBeaconCompat:
    def test_legacy_links_key(self, tmp_path):
        """An older beacon.json with 'links' (legacy NetworkX) still loads."""
        p = tmp_path / "legacy.json"
        p.write_text(json.dumps({
            "directed": True, "multigraph": False, "graph": {},
            "nodes": [{"id": "a"}, {"id": "b"}],
            "links": [{"source": "a", "target": "b", "relation": "calls"}],
        }))
        G, meta = load_beacon(p)
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 1
        assert meta == {}

    def test_modern_edges_key(self, tmp_path):
        """A current beacon.json with 'edges' (modern NetworkX) loads too."""
        G = nx.DiGraph()
        G.add_node("a"); G.add_node("b")
        G.add_edge("a", "b", relation="calls")
        write_beacon(G, tmp_path)
        loaded, _ = load_beacon(tmp_path / "beacon.json")
        assert loaded.number_of_nodes() == 2
        assert loaded.number_of_edges() == 1
