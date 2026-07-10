"""0.6.9 io-cache-mcp-merge audit — 5 robustness regressions (group F-H).

Each test drives the exact failure mode confirmed by the verifier, not just the
happy path:

* BH-E1  wave._extract_file: the incremental cache key omitted the `semantic`
  extraction flag, so `--update --semantic` reused a plain cache entry and
  silently dropped the semantic 'references' edges (and vice-versa).
* BH-E2  Cache.load: a cache.json with invalid UTF-8 raised UnicodeDecodeError
  (a ValueError, not an OSError) which escaped the corrupt-backup handler and
  crashed the whole scan instead of self-healing.
* BH-IO1 load_beacon: a syntactically-valid beacon.json whose nodes/links/edges
  field is JSON null crashed with a raw TypeError/KeyError instead of the
  documented backup + ValueError self-heal.
* BH-IO2 merge_files: a `"nodes": null` (or non-list / non-dict) input crashed
  the git merge driver, breaking its documented always-exit-0 contract.
* BH-IO3 mcp.serve: a single malformed-but-valid-JSON message (top-level array,
  or tools/call with array `params`) took down the whole persistent server.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from codebeacon.cache import Cache
from codebeacon.common.types import ProjectInfo
from codebeacon.export.merge import merge_files
from codebeacon.graph.write import load_beacon
from codebeacon.wave import auto_wave


# ── BH-E1 — semantic flag must namespace the incremental cache key ────────────

SEMANTIC_FIXTURE = '''"""Module docstring."""


def widget():
    """Build a widget.

    See Also
    --------
    Gadget
    """
    return 1
'''


def _mk_python_project(tmp_path: Path) -> tuple[ProjectInfo, list[str]]:
    proj_root = tmp_path / "proj"
    src = proj_root / "src"
    src.mkdir(parents=True)
    fixture = src / "foo.py"
    fixture.write_text(SEMANTIC_FIXTURE, encoding="utf-8")
    project = ProjectInfo(
        name="proj", path=str(proj_root), framework="python",
        language="python", signature_file=str(proj_root / "pyproject.toml"),
    )
    return project, [str(fixture)]


def _references(wave_result) -> list[str]:
    return [e.target for e in wave_result.import_edges if e.relation == "references"]


class TestSemanticCacheKey:
    def test_update_semantic_after_plain_scan_still_extracts_refs(self, tmp_path):
        """Run 1 plain, Run 2 --update --semantic on the UNCHANGED file must NOT
        reuse the plain cache entry — the semantic 'references' edge must appear."""
        project, files = _mk_python_project(tmp_path)
        outdir = str(tmp_path / ".codebeacon")

        cache1 = Cache(outdir, project_root=str(project.path))
        w1 = auto_wave(project=project, files=files, cache=cache1, semantic=False)
        cache1.save()
        assert _references(w1) == []  # plain scan writes no semantic edges

        cache2 = Cache(outdir, project_root=str(project.path))
        cache2.load()
        w2 = auto_wave(project=project, files=files, cache=cache2, semantic=True)

        # Before the fix: w2 was a silent cache hit (skipped_count == 1) with no
        # semantic edges. After: the semantic namespace misses the plain entry,
        # re-extracts, and surfaces the reference.
        assert w2.skipped_count == 0
        assert _references(w2) == ["Gadget"]

    def test_plain_update_after_semantic_scan_does_not_leak_refs(self, tmp_path):
        """The reverse leak: a plain --update must not reuse a semantic entry and
        emit 'references' edges the user never asked for."""
        project, files = _mk_python_project(tmp_path)
        outdir = str(tmp_path / ".codebeacon")

        cache1 = Cache(outdir, project_root=str(project.path))
        w1 = auto_wave(project=project, files=files, cache=cache1, semantic=True)
        cache1.save()
        assert _references(w1) == ["Gadget"]

        cache2 = Cache(outdir, project_root=str(project.path))
        cache2.load()
        w2 = auto_wave(project=project, files=files, cache=cache2, semantic=False)
        assert w2.skipped_count == 0
        assert _references(w2) == []

    def test_semantic_reruns_are_cache_hits(self, tmp_path):
        """Two identical --semantic runs on an unchanged file SHOULD hit the
        cache — the namespace must not defeat caching for matching flags."""
        project, files = _mk_python_project(tmp_path)
        outdir = str(tmp_path / ".codebeacon")

        cache1 = Cache(outdir, project_root=str(project.path))
        auto_wave(project=project, files=files, cache=cache1, semantic=True)
        cache1.save()

        cache2 = Cache(outdir, project_root=str(project.path))
        cache2.load()
        w2 = auto_wave(project=project, files=files, cache=cache2, semantic=True)
        assert w2.skipped_count == 1
        assert _references(w2) == ["Gadget"]  # semantic edge preserved via cache


# ── BH-E2 — Cache.load self-heals an invalid-UTF-8 cache.json ─────────────────

class TestCacheInvalidUtf8:
    def test_invalid_utf8_cache_is_backed_up_not_crashed(self, tmp_path):
        cdir = tmp_path / ".codebeacon" / "cache"
        cdir.mkdir(parents=True)
        # A write truncated mid multi-byte sequence → invalid UTF-8 bytes.
        (cdir / "cache.json").write_bytes(
            b'{"_cb_version": "x", "entries": {\xff\xfe garbage'
        )

        c = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        c.load()  # before the fix this raised UnicodeDecodeError

        assert c._data == {}
        backups = list(cdir.glob("cache.json.*.corrupt"))
        assert backups, "invalid-UTF-8 cache.json must be preserved, not lost"
        assert not (cdir / "cache.json").exists()

    def test_recovered_cache_saves_fresh(self, tmp_path):
        cdir = tmp_path / ".codebeacon" / "cache"
        cdir.mkdir(parents=True)
        (cdir / "cache.json").write_bytes(b"\xff\xfe\xfd not utf-8 at all")

        c = Cache(str(tmp_path / ".codebeacon"), project_root=str(tmp_path))
        c.load()
        c._data["x::src/a.py"] = {"result": {"routes": []}}
        c._dirty = True
        c.save()
        # The rebuilt cache is valid, readable JSON again.
        reloaded = json.loads((cdir / "cache.json").read_text(encoding="utf-8"))
        assert reloaded["entries"]["x::src/a.py"] == {"result": {"routes": []}}


# ── BH-IO1 — load_beacon treats null nodes/links/edges as corruption ──────────

class TestLoadBeaconNullCollections:
    @pytest.mark.parametrize("doc,bad_key", [
        ({"meta": {"version": 1}, "nodes": None, "links": []}, "nodes"),
        ({"meta": {"version": 1}, "nodes": [], "links": None}, "links"),
        ({"meta": {"version": 1}, "nodes": [], "edges": None}, "edges"),
        ({"nodes": "oops", "links": []}, "nodes"),  # non-list, non-null too
    ])
    def test_null_collection_raises_valueerror_and_backs_up(self, tmp_path, doc, bad_key):
        p = tmp_path / "beacon.json"
        p.write_text(json.dumps(doc), encoding="utf-8")

        with pytest.raises(ValueError, match=f"'{bad_key}' is"):
            load_beacon(p)
        # corrupt file preserved, not left in place
        assert list(tmp_path.glob("beacon.json.*.corrupt"))
        assert not p.exists()

    def test_valid_empty_document_still_loads(self, tmp_path):
        p = tmp_path / "beacon.json"
        p.write_text(json.dumps({"meta": {"version": 1}, "nodes": [], "links": []}),
                     encoding="utf-8")
        G, meta = load_beacon(p)
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0
        assert not list(tmp_path.glob("*.corrupt"))

    @pytest.mark.parametrize("doc", [
        # A LIST whose elements are non-dict / malformed: passes the is-list guard
        # but node_link_graph raises a raw AttributeError/KeyError (not ValueError).
        # Shape-enumeration can't catch these, so the construction is wrapped.
        {"meta": {"version": 1}, "nodes": [1, 2, 3], "links": []},
        {"meta": {"version": 1}, "nodes": ["a", "b"], "links": []},
        {"meta": {"version": 1}, "nodes": [{"id": "a"}], "links": [{"weird": 1}]},
        {"meta": {"version": 1}, "nodes": [{"id": "a"}, {"id": "b"}],
         "links": [{"nosrc": 1}]},
        {"meta": {"version": 1}, "nodes": [{"id": "a"}], "edges": ["x"]},
    ])
    def test_list_of_non_dict_elements_raises_valueerror_and_backs_up(self, tmp_path, doc):
        p = tmp_path / "beacon.json"
        p.write_text(json.dumps(doc), encoding="utf-8")

        # A raw TypeError/KeyError/AttributeError here would escape callers that
        # catch only ValueError (serve, pipeline). The construction wrapper must
        # normalise it to the same backup + ValueError contract as null/non-list.
        with pytest.raises(ValueError, match="could not build a graph"):
            load_beacon(p)
        assert list(tmp_path.glob("beacon.json.*.corrupt"))
        assert not p.exists()


# ── BH-IO2 — merge_files keeps the always-exit-0 contract on null nodes ───────

class TestMergeNullNodes:
    def test_current_nodes_null_uses_other(self, tmp_path):
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        cur.write_text(json.dumps({"nodes": None, "edges": []}))
        other.write_text(json.dumps({"nodes": [{"id": "a"}], "edges": []}))

        assert merge_files("", str(cur), str(other)) == 0
        # corrupt current was treated as unreadable → survivor (other) written in
        merged = json.loads(cur.read_text())
        assert [n["id"] for n in merged["nodes"]] == ["a"]

    def test_other_nodes_null_keeps_current(self, tmp_path):
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        cur.write_text(json.dumps({"nodes": [{"id": "x"}], "edges": []}))
        other.write_text(json.dumps({"nodes": None, "edges": []}))

        assert merge_files("", str(cur), str(other)) == 0
        merged = json.loads(cur.read_text())
        assert [n["id"] for n in merged["nodes"]] == ["x"]

    def test_non_dict_input_does_not_crash(self, tmp_path):
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        cur.write_text(json.dumps([1, 2, 3]))  # valid JSON, wrong shape
        other.write_text(json.dumps({"nodes": [{"id": "b"}], "edges": []}))
        assert merge_files("", str(cur), str(other)) == 0
        assert [n["id"] for n in json.loads(cur.read_text())["nodes"]] == ["b"]

    def test_both_null_leaves_current_untouched(self, tmp_path):
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        raw_cur = json.dumps({"nodes": None, "edges": []})
        cur.write_text(raw_cur)
        other.write_text(json.dumps({"nodes": None, "edges": []}))
        assert merge_files("", str(cur), str(other)) == 0
        # both unreadable → current left exactly as-is
        assert cur.read_text() == raw_cur

    def test_other_nodes_list_of_non_dict_keeps_current(self, tmp_path):
        # `nodes` is a LIST (passes _load) but holds non-dict elements: _union
        # crashes on n.get(). The always-exit-0 contract requires the driver to
        # swallow that and leave current as-is rather than exit non-zero.
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        raw_cur = json.dumps({"nodes": [{"id": "x"}], "edges": []})
        cur.write_text(raw_cur)
        other.write_text(json.dumps({"nodes": [1, 2, 3], "edges": []}))
        assert merge_files("", str(cur), str(other)) == 0
        assert cur.read_text() == raw_cur

    def test_current_nodes_list_of_non_dict_leaves_current_untouched(self, tmp_path):
        cur = tmp_path / "current.json"
        other = tmp_path / "other.json"
        raw_cur = json.dumps({"nodes": [{"id": "a"}, "oops"], "edges": []})
        cur.write_text(raw_cur)
        other.write_text(json.dumps({"nodes": [{"id": "b"}], "edges": []}))
        # current's own nodes are malformed → _union crashes; driver exits 0 and
        # leaves current byte-identical (no partial write).
        assert merge_files("", str(cur), str(other)) == 0
        assert cur.read_text() == raw_cur


# ── BH-IO3 — one malformed JSON-RPC message must not kill the server ──────────

class _FakeStdin:
    def __init__(self, lines):
        self._it = iter(lines)

    def __iter__(self):
        return self._it


def _drive_serve(monkeypatch, lines) -> str:
    """Run serve()'s stdin loop over `lines` and return captured stdout."""
    from codebeacon.export import mcp

    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdin", _FakeStdin([l + "\n" for l in lines]))
    monkeypatch.setattr(sys, "stdout", captured)
    # serve() must return normally (loop ends when stdin is exhausted), never
    # propagate an exception out of the process.
    mcp.serve(Path("/nonexistent-beacon-dir-for-test"))
    return captured.getvalue()


def _responses(out: str) -> list[dict]:
    return [json.loads(line) for line in out.splitlines() if line.strip()]


class TestServeSurvivesMalformedMessage:
    @pytest.mark.parametrize("bad_line", ["[1,2,3]", '"a string"', "42", "true", "null"])
    def test_non_object_message_does_not_kill_server(self, monkeypatch, bad_line):
        out = _drive_serve(monkeypatch, [
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
            bad_line,
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
        ])
        resp = _responses(out)
        by_id = {r.get("id"): r for r in resp}
        # both real requests were answered → the server survived the bad line
        assert 1 in by_id and "result" in by_id[1]
        assert 2 in by_id and "result" in by_id[2]
        # the bad line produced an Invalid Request error, not a crash
        assert any(r.get("error", {}).get("code") == -32600 for r in resp)

    def test_tools_call_with_array_params_does_not_kill_server(self, monkeypatch):
        out = _drive_serve(monkeypatch, [
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
            '{"jsonrpc":"2.0","id":9,"method":"tools/call","params":["a","b"]}',
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
        ])
        by_id = {r.get("id"): r for r in _responses(out)}
        assert 1 in by_id and "result" in by_id[1]
        # array params normalised to {} → unknown-tool error, server keeps going
        assert 9 in by_id and by_id[9].get("error", {}).get("code") == -32601
        assert 2 in by_id and "result" in by_id[2]

    def test_serve_survives_unexpected_dispatch_error(self, monkeypatch):
        # Defense-in-depth: even if _dispatch raises an error it doesn't validate
        # itself, serve() must reply with a scoped internal error (-32603) and
        # keep processing later requests rather than letting one line kill it.
        from codebeacon.export import mcp

        real_dispatch = mcp._dispatch

        def boom(idx, message):
            if isinstance(message, dict) and message.get("id") == 99:
                raise RuntimeError("kaboom")
            return real_dispatch(idx, message)

        monkeypatch.setattr(mcp, "_dispatch", boom)
        out = _drive_serve(monkeypatch, [
            '{"jsonrpc":"2.0","id":99,"method":"tools/list"}',
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
        ])
        by_id = {r.get("id"): r for r in _responses(out)}
        assert by_id[99].get("error", {}).get("code") == -32603
        assert 2 in by_id and "result" in by_id[2]
