"""Audit 0.7.1 — cache / watch / cluster fixes (fixer F2).

Confirmed defects covered here:

  CG-GHOST-ROOT (graphify v0.9.30 + v0.9.41)
        A cached payload embeds the source paths of the tree it was extracted
        from, but nothing recorded *which* tree. Copying a repo (or renaming its
        directory) with its committed ``.codebeacon/`` therefore replayed the
        old checkout's absolute paths into the new one's beacon.json and wiki.
        Every entry now carries its project-root anchor and a root change is a
        miss.

  CG-KEY-ANCHOR (graphify #1904 + v0.9.17)
        ``run_pipeline`` anchors one shared Cache at ``projects[0].path``, so in
        a multi-project workspace every project but the first fell back to
        absolute keys — publishing local absolute paths into a committed cache.
        Out-of-root files now key relatively too. Separately, ``load()``'s
        absolute-key migration tested ``Path(key).is_absolute()`` on the
        *namespaced* key ("fastapi::/abs/x.py"), which is never absolute, so the
        migration could not fire for any real entry.

  CG-STALE-STAT (graphify v0.9.40 + v0.9.42)
        The (mtime_ns, size) fast path served stale content after a same-length
        rewrite under a preserved mtime — routine under cp -p / rsync -a /
        tar -x / Docker COPY and on coarse-timestamp filesystems. ctime_ns joins
        the tuple; a mismatch only downgrades to the content hash.

  CG-CORRUPT-ENTRY (graphify v0.9.42 + #2405)
        All entries live in one JSON file, so a single mangled entry parses
        fine and reached an unguarded merge: a raw TypeError/KeyError traceback
        that never mentioned the cache, recoverable only by deleting cache.json
        by hand. Bad entries are now quarantined and counted.

  CG-CACHE-LIVENESS (graphify v0.9.27)
        Nothing ever evicted an entry, so deleted files kept their payloads for
        the life of the repo.

  CG-READONLY (graphify v0.9.14, cache half)
        A cache directory that cannot be written now warns instead of raising.

  CB-ATOMIC-WRITE (graphify v0.9.18, cache.json half)
        cache.json is read on every ``--update`` but was written with a
        truncating ``write_text``.

  CG-WATCH-EVENTS (graphify v0.9.50)
        ``on_any_event`` filtered on path only, so on Linux (inotify emits
        IN_OPEN / IN_CLOSE_NOWRITE) a resync's own reads re-armed the debouncer:
        a self-sustaining rebuild loop that never idles.

  CB-CLUSTER-DRIFT (graphify v0.9.51 + V5-EXTRA-2)
        Leiden ran unseeded: two clusterings of the same unchanged graph moved
        12% of nodes between communities. And the backends drop isolated nodes,
        so those came back with no community at all.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import networkx as nx
import pytest

from codebeacon import __version__
from codebeacon.cache import Cache, _payload_defect
from codebeacon.graph import cluster as cluster_mod
from codebeacon.graph.cluster import apply_communities, cluster


# ── helpers ───────────────────────────────────────────────────────────────────

def _payload(**over) -> dict:
    """A structurally valid wave payload, shaped like ``wave._extract_file``."""
    body = {
        "_schema": 2,
        "routes": [], "services": [], "entities": [],
        "components": [], "import_edges": [], "unresolved": [],
    }
    body.update(over)
    return body


def _route(source_file: str) -> dict:
    return {
        "method": "GET", "path": "/x", "handler": "h", "source_file": source_file,
        "line": 1, "framework": "fastapi", "prefix": "", "tags": [],
    }


def _project(tmp_path: Path, name: str = "proj") -> tuple[Path, Path]:
    """Create ``<tmp>/<name>/app/main.py`` and return (root, source file)."""
    root = tmp_path / name
    (root / "app").mkdir(parents=True)
    src = root / "app" / "main.py"
    src.write_text("x = 1\n", encoding="utf-8")
    return root, src


# ── CG-GHOST-ROOT ─────────────────────────────────────────────────────────────

class TestCacheRootAnchor:
    def test_entry_from_another_root_is_a_miss(self, tmp_path, capsys):
        """A cache carried to a different checkout must not be served.

        The key is repo-relative and so collides exactly; only the recorded
        anchor can tell the two trees apart.
        """
        root_a, src_a = _project(tmp_path, "checkout-A")
        cache_a = Cache(str(root_a / ".codebeacon"), project_root=str(root_a))
        cache_a.put(str(src_a), _payload(routes=[_route(str(src_a))]), framework="fastapi")
        cache_a.save()

        root_b, src_b = _project(tmp_path, "checkout-B")
        entries = json.loads(
            (root_a / ".codebeacon" / "cache" / "cache.json").read_text(encoding="utf-8")
        )
        cache_dir_b = root_b / ".codebeacon" / "cache"
        cache_dir_b.mkdir(parents=True)
        (cache_dir_b / "cache.json").write_text(json.dumps(entries), encoding="utf-8")

        cache_b = Cache(str(root_b / ".codebeacon"), project_root=str(root_b))
        cache_b.load()
        assert cache_b.get(str(src_b), framework="fastapi") is None
        cache_b.report_anomalies()
        assert "different project root" in capsys.readouterr().err

    def test_same_root_still_hits(self, tmp_path):
        """The anchor must not defeat ordinary warm-cache reuse."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(routes=[_route(str(src))]), framework="fastapi")
        cache.save()

        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        assert fresh.get(str(src), framework="fastapi") is not None
        assert fresh.is_fresh(str(src), "fastapi") is True

    def test_foreign_entry_is_dropped_not_kept(self, tmp_path):
        """A quarantined foreign entry is removed so the next put() replaces it
        instead of the cache carrying two roots' worth of dead payloads."""
        root_a, src_a = _project(tmp_path, "A")
        cache_a = Cache(str(root_a / ".codebeacon"), project_root=str(root_a))
        cache_a.put(str(src_a), _payload(), framework="fastapi")

        root_b, src_b = _project(tmp_path, "B")
        cache_b = Cache(str(root_b / ".codebeacon"), project_root=str(root_b))
        cache_b._data = dict(cache_a._data)
        key = cache_b._key(str(src_b), "fastapi")
        assert key in cache_b._data  # the relative key collides exactly

        cache_b.get(str(src_b), framework="fastapi")
        assert key not in cache_b._data


# ── CG-KEY-ANCHOR ─────────────────────────────────────────────────────────────

class TestCacheKeyAnchoring:
    def test_out_of_root_file_keys_relatively(self, tmp_path):
        """The second project of a workspace scan is outside the shared cache's
        anchor; its key must still be relative, never an absolute local path."""
        ws = tmp_path / "ws"
        alpha, alpha_src = _project(ws, "alpha")
        _beta, beta_src = _project(ws, "beta")

        cache = Cache(str(ws / ".codebeacon"), project_root=str(alpha))
        cache.put(str(alpha_src), _payload(), framework="fastapi")
        cache.put(str(beta_src), _payload(), framework="fastapi")

        paths = [k.rsplit("::", 1)[-1] for k in cache._data]
        assert paths, "expected two entries"
        assert not any(Path(p).is_absolute() for p in paths), paths
        assert "../beta/app/main.py" in paths

    def test_out_of_root_entry_round_trips(self, tmp_path):
        """A relative ``..`` key must still resolve back to the same file."""
        ws = tmp_path / "ws"
        alpha, _ = _project(ws, "alpha")
        _beta, beta_src = _project(ws, "beta")

        cache = Cache(str(ws / ".codebeacon"), project_root=str(alpha))
        cache.put(str(beta_src), _payload(routes=[_route(str(beta_src))]), framework="fastapi")
        cache.save()

        fresh = Cache(str(ws / ".codebeacon"), project_root=str(alpha))
        fresh.load()
        assert fresh.get(str(beta_src), framework="fastapi") is not None

    def test_namespaced_absolute_keys_migrate_on_load(self, tmp_path):
        """``Path("fastapi::/abs/x.py").is_absolute()`` is False, so the
        migration silently never fired for a real (namespaced) entry."""
        root, src = _project(tmp_path)
        cache_dir = root / ".codebeacon" / "cache"
        cache_dir.mkdir(parents=True)
        entry = {
            "hash": "h", "result": _payload(), "ts": 0,
            "mtime_ns": 0, "size": 0, "ctime_ns": 0, "root": "",
        }
        (cache_dir / "cache.json").write_text(json.dumps({
            "_cb_version": __version__,
            "entries": {
                f"fastapi::{src.resolve()}": dict(entry),
                f"fastapi::semantic::{src.resolve()}": dict(entry),
            },
        }), encoding="utf-8")

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.load()

        assert set(cache._data) == {
            "fastapi::app/main.py", "fastapi::semantic::app/main.py",
        }
        assert cache._dirty, "migration must mark the cache dirty so save persists it"

    def test_relative_keys_are_left_alone(self, tmp_path):
        """Already-relative keys must survive load() untouched."""
        root, _ = _project(tmp_path)
        cache_dir = root / ".codebeacon" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "cache.json").write_text(json.dumps({
            "_cb_version": __version__,
            "entries": {"fastapi::app/main.py": {"result": _payload(), "root": ""}},
        }), encoding="utf-8")

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.load()
        assert set(cache._data) == {"fastapi::app/main.py"}
        assert not cache._dirty


# ── CG-STALE-STAT ─────────────────────────────────────────────────────────────

class TestCacheCtimeFastPath:
    def test_same_size_rewrite_under_preserved_mtime_is_a_miss(self, tmp_path):
        """cp -p / rsync -t / tar -x restore the old mtime; with equal lengths
        the (mtime, size) fast path served the *previous* content."""
        root, src = _project(tmp_path)
        src.write_text("VERSION_ONE\n", encoding="utf-8")
        before = os.stat(src)

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(routes=[_route(str(src))]), framework="py")
        cache.save()

        src.write_text("VERSION_TWO\n", encoding="utf-8")  # identical length
        os.utime(src, ns=(before.st_atime_ns, before.st_mtime_ns))

        # A later run — stat results are memoized within a run, so the staleness
        # this guards against is always cross-run.
        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        assert fresh.get(str(src), framework="py") is None
        assert fresh.is_fresh(str(src), "py") is False

    def test_untouched_file_still_hits_without_hashing(self, tmp_path):
        """The fast path must stay a fast path — no hash on an unchanged file."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        cache.save()

        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        fresh._hash_memo.clear()
        assert fresh.is_fresh(str(src), "py") is True
        assert str(src) not in fresh._hash_memo

    def test_entry_without_ctime_falls_through_to_the_hash(self, tmp_path):
        """Entries written before ctime_ns existed must not be invalidated en
        masse: they take the hash path, match, and get refreshed in place."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        key = cache._key(str(src), "py")
        del cache._data[key]["ctime_ns"]

        assert cache.get(str(src), framework="py") is not None
        assert cache._data[key]["ctime_ns"] == os.stat(src).st_ctime_ns


# ── CG-CORRUPT-ENTRY ──────────────────────────────────────────────────────────

class TestCacheEntryQuarantine:
    @pytest.mark.parametrize("bad, needle", [
        ("not-a-dict", "not an object"),
        (_payload(routes="nope"), "routes is str"),
        (_payload(routes=["nope"]), "routes holds str"),
        (_payload(routes=[{"method": "GET"}]), "missing"),
        (None, "not an object"),
    ])
    def test_corrupt_payload_is_a_miss_not_a_crash(self, tmp_path, bad, needle, capsys):
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        key = cache._key(str(src), "py")
        cache._data[key]["result"] = bad

        assert cache.get(str(src), framework="py") is None
        assert key not in cache._data, "an unusable entry must be quarantined"

        cache.report_anomalies()
        err = capsys.readouterr().err
        assert "unusable cache entr" in err
        assert needle in err

    def test_non_dict_entry_is_quarantined(self, tmp_path):
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        key = cache._key(str(src), "py")
        cache._data[key] = "junk"

        assert cache.get(str(src), framework="py") is None
        assert cache.is_fresh(str(src), "py") is False
        assert key not in cache._data

    def test_anomalies_are_reported_once(self, tmp_path, capsys):
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        cache._data[cache._key(str(src), "py")]["result"] = "junk"
        cache.get(str(src), framework="py")

        cache.report_anomalies()
        first = capsys.readouterr().err
        cache.report_anomalies()
        assert first.count("unusable cache entr") == 1
        assert capsys.readouterr().err == ""

    def test_a_plain_miss_is_not_an_anomaly(self, tmp_path, capsys):
        """The common case — key absent — must stay silent."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))

        assert cache.get(str(src), framework="py") is None
        assert cache.is_fresh(str(src), "py") is False
        cache.report_anomalies()
        assert capsys.readouterr().err == ""

    def test_a_real_extraction_payload_validates(self, tmp_path):
        """Drift guard: whatever ``wave._extract_file`` actually serialises must
        pass the boundary validator, or warm caches would break wholesale."""
        from codebeacon.wave import _extract_file

        root = tmp_path / "proj"
        (root / "app").mkdir(parents=True)
        src = root / "app" / "main.py"
        src.write_text(
            "from fastapi import FastAPI\n"
            "from app.svc import UserService\n\n"
            "app = FastAPI()\n\n"
            "@app.get('/users')\n"
            "def list_users():\n"
            "    return UserService().all()\n",
            encoding="utf-8",
        )
        result = _extract_file(str(src), "fastapi", str(root))
        assert isinstance(result, dict), result
        assert result.get("routes"), "fixture must produce at least one route"
        assert _payload_defect(result) == ""


# ── CG-CACHE-LIVENESS ─────────────────────────────────────────────────────────

class TestCacheLivenessPrune:
    def test_entry_for_a_deleted_file_is_pruned(self, tmp_path):
        root, keep = _project(tmp_path)
        gone = root / "app" / "gone.py"
        gone.write_text("y = 1\n", encoding="utf-8")

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(keep), _payload(), framework="py")
        cache.put(str(gone), _payload(), framework="py")
        cache.save()

        gone.unlink()
        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        fresh.get(str(keep), framework="py")   # the run's corpus
        fresh.save()

        assert set(fresh._data) == {"py::app/main.py"}

    def test_still_present_file_is_kept_even_when_newly_ignored(self, tmp_path):
        """R3: liveness needs *both* conditions. A file that dropped out of the
        corpus but still exists keeps its payload for the day the ignore rule is
        reverted — and a partial run can never evict a good entry."""
        root, keep = _project(tmp_path)
        ignored = root / "app" / "legacy.py"
        ignored.write_text("z = 1\n", encoding="utf-8")

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(keep), _payload(), framework="py")
        cache.put(str(ignored), _payload(), framework="py")
        cache.save()

        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        fresh.get(str(keep), framework="py")
        fresh.save()

        assert "py::app/legacy.py" in fresh._data

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores mode bits")
    def test_unreadable_subtree_keeps_its_entries_instead_of_crashing(self, tmp_path):
        """``Path.exists()`` swallows only the "not there" errno family, so a
        chmod-000 subtree raised PermissionError straight out of ``save()`` and
        killed the scan before the shrink guard was ever consulted.

        An unprobeable path must count as LIVE: dropping an entry we could not
        stat is the unsafe direction, and it would contradict the scanner rule
        that an unreadable file is never a deliberate exclusion.
        """
        root, keep = _project(tmp_path)
        secret = root / "secret"
        secret.mkdir()
        hidden = secret / "app.py"
        hidden.write_text("x = 1\n", encoding="utf-8")

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(keep), _payload(), framework="py")
        cache.put(str(hidden), _payload(), framework="py")
        cache.save()

        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        fresh.get(str(keep), framework="py")  # secret/ is no longer in the corpus

        os.chmod(secret, 0o000)
        try:
            fresh.save()  # must not raise
            assert "py::secret/app.py" in fresh._data
            assert "py::app/main.py" in fresh._data
        finally:
            os.chmod(secret, 0o755)

    def test_a_run_that_consulted_nothing_never_prunes(self, tmp_path):
        """No gets, no puts: not an extraction pass, so there is no evidence
        about what is live and the cache must be left alone."""
        root, _ = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache._data["py::app/vanished.py"] = {"result": _payload(), "root": cache._anchor}
        cache._dirty = True
        cache.save()

        fresh = Cache(str(root / ".codebeacon"), project_root=str(root))
        fresh.load()
        assert "py::app/vanished.py" in fresh._data


# ── CG-READONLY + CB-ATOMIC-WRITE ─────────────────────────────────────────────

class TestCacheIsIdempotent:
    """R-2: a no-op rescan must leave cache.json byte-identical.

    Two independent causes, both only reachable on the *plain* (non
    ``--update``) path — which never calls ``load()``, so every file takes the
    cold path and is re-``put()``:

    * ``put()`` stamped ``"ts": time.time()`` on every entry. Nothing ever read
      it, so its whole observable effect was to make all entries differ.
    * entries landed in ``_data`` in ThreadPoolExecutor completion order, so the
      serialised key order varied run to run even for identical content.

    That left cache.json as the last artifact dirtying a committed
    ``.codebeacon/`` on a no-op run.
    """

    def _extract(self, root: Path, files: list[str]) -> bytes:
        """One cold scan: a fresh Cache, no load() — exactly the plain path."""
        from codebeacon.wave import _extract_file

        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        for f in files:
            _extract_file(f, "fastapi", str(root), cache=cache)
        cache.save()
        return (root / ".codebeacon" / "cache" / "cache.json").read_bytes()

    def _fixture(self, tmp_path: Path) -> tuple[Path, list[str]]:
        root = tmp_path / "proj"
        (root / "app").mkdir(parents=True)
        (root / "app" / "main.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n\n"
            "@app.get('/a')\n"
            "def a():\n    return 1\n",
            encoding="utf-8",
        )
        # Several files, so a varying completion order has something to shuffle.
        for i in range(6):
            (root / "app" / f"r{i}.py").write_text(
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n\n"
                f"@app.get('/r{i}')\n"
                f"def r{i}():\n    return {i}\n",
                encoding="utf-8",
            )
        (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        files = sorted(str(p) for p in (root / "app").glob("*.py"))
        return root, files

    def test_plain_rescan_is_byte_identical(self, tmp_path):
        root, files = self._fixture(tmp_path)
        first = self._extract(root, files)
        second = self._extract(root, files)
        assert hashlib.md5(first).hexdigest() == hashlib.md5(second).hexdigest()
        assert first == second

    def test_entry_order_is_canonical_not_completion_order(self, tmp_path):
        """Serialised key order must follow the keys, not the order put() ran."""
        root, files = self._fixture(tmp_path)
        forward = Cache(str(root / ".codebeacon"), project_root=str(root))
        backward = Cache(str(root / ".codebeacon2"), project_root=str(root))
        for f in files:
            forward.put(f, _payload(), framework="fastapi")
        for f in reversed(files):
            backward.put(f, _payload(), framework="fastapi")
        forward.save()
        backward.save()

        a = (root / ".codebeacon" / "cache" / "cache.json").read_text(encoding="utf-8")
        b = (root / ".codebeacon2" / "cache" / "cache.json").read_text(encoding="utf-8")
        assert a == b
        keys = list(json.loads(a)["entries"])
        assert keys == sorted(keys)

    def test_no_wall_clock_stamp_is_written(self, tmp_path):
        """The field itself must be gone — a stable-looking cache that still
        carries a timestamp would churn again the moment anything reorders."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        entry = cache._data[cache._key(str(src), "py")]
        assert "ts" not in entry

    def test_a_real_change_still_rewrites(self, tmp_path):
        """Idempotence must not be bought by refusing to persist real work."""
        root, files = self._fixture(tmp_path)
        first = self._extract(root, files)
        (root / "app" / "main.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n\n"
            "@app.get('/changed')\n"
            "def changed():\n    return 2\n",
            encoding="utf-8",
        )
        second = self._extract(root, files)
        assert first != second
        assert b"/changed" in second


class TestCacheGitignore:
    """DESIGN RULING: cache data is machine-local by construction, so a
    consumer repo that commits .codebeacon/ must never pick it up.

    ``st_ctime_ns`` in the validity tuple and the per-entry root anchor both
    fail to survive a clone, so a committed entry is a guaranteed miss for
    anyone else — it can only cost diff noise.
    """

    def test_save_writes_a_self_ignoring_gitignore(self, tmp_path):
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        cache.save()

        marker = root / ".codebeacon" / "cache" / ".gitignore"
        assert marker.read_text(encoding="utf-8") == "*\n"

    def test_gitignore_is_never_restamped(self, tmp_path):
        """Rewriting it would be its own churn, and would clobber user edits."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        cache.save()

        marker = root / ".codebeacon" / "cache" / ".gitignore"
        marker.write_text("*\n# hand-edited\n", encoding="utf-8")
        before = marker.stat().st_mtime_ns

        cache.put(str(src), _payload(routes=[_route(str(src))]), framework="py")
        cache.save()

        assert marker.stat().st_mtime_ns == before
        assert "hand-edited" in marker.read_text(encoding="utf-8")

    def test_git_excludes_the_whole_cache_directory(self, tmp_path):
        """The pattern must cover cache.json *and* the marker itself, so git
        tracks neither and any scan can recreate the marker locally."""
        git = shutil.which("git")
        if git is None:
            pytest.skip("git not available")

        root, src = _project(tmp_path)
        subprocess.run([git, "init", "-q", str(root)], check=True, capture_output=True)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        cache.save()

        for target in (".codebeacon/cache/cache.json", ".codebeacon/cache/.gitignore"):
            done = subprocess.run(
                [git, "check-ignore", "-q", target], cwd=root, capture_output=True,
            )
            assert done.returncode == 0, f"{target} must be git-ignored"

        # And the rest of .codebeacon/ is still committable — that is the
        # product contract; only the cache subdirectory is excluded.
        (root / ".codebeacon" / "beacon.json").write_text("{}", encoding="utf-8")
        done = subprocess.run(
            [git, "check-ignore", "-q", ".codebeacon/beacon.json"],
            cwd=root, capture_output=True,
        )
        assert done.returncode == 1, "only the cache dir may be excluded"

    def test_unwritable_marker_does_not_cost_the_cache(self, tmp_path, monkeypatch):
        """A .gitignore we cannot write is a nuisance, not a reason to lose the
        cache write that follows it."""
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        real_write = Path.write_text

        def selective(self, *args, **kwargs):
            if self.name == ".gitignore":
                raise OSError(13, "Permission denied")
            return real_write(self, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", selective)
        cache.put(str(src), _payload(), framework="py")
        cache.save()  # must not raise

        assert (root / ".codebeacon" / "cache" / "cache.json").exists()


class TestCacheWriteResilience:
    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores mode bits")
    def test_unwritable_tree_warns_instead_of_raising(self, tmp_path, capsys):
        root, src = _project(tmp_path)
        os.chmod(root, 0o555)
        try:
            cache = Cache(str(root / ".codebeacon"), project_root=str(root))
            cache.put(str(src), _payload(), framework="py")
            cache.save()  # must not raise
        finally:
            os.chmod(root, 0o755)
        assert "could not write" in capsys.readouterr().err

    def test_failed_write_leaves_the_previous_cache_intact(self, tmp_path, capsys):
        root, src = _project(tmp_path)
        cache = Cache(str(root / ".codebeacon"), project_root=str(root))
        cache.put(str(src), _payload(), framework="py")
        cache.save()

        cache_file = root / ".codebeacon" / "cache" / "cache.json"
        before = cache_file.read_text(encoding="utf-8")

        cache._data["py::app/other.py"] = {"result": _payload(), "root": cache._anchor}
        cache._dirty = True
        real_write = Path.write_text

        def explode(self, *args, **kwargs):
            if self.name.endswith(".tmp"):
                raise OSError(28, "No space left on device")
            return real_write(self, *args, **kwargs)

        Path.write_text = explode
        try:
            cache.save()  # must not raise
        finally:
            Path.write_text = real_write

        assert cache_file.read_text(encoding="utf-8") == before
        assert not list(cache_file.parent.glob("*.tmp")), "temp file must be cleaned up"
        assert "could not write" in capsys.readouterr().err


# ── CG-WATCH-EVENTS ───────────────────────────────────────────────────────────

class TestWatchScannerParity:
    """The watcher's ignore decision must equal ``collect_files``' for the same
    file — otherwise an edit the scan would index never triggers a resync, and
    the index silently drifts from the tree.

    ``_dir_prune_reason`` needs a directory's *path* to tell a real ``env/`` or
    ``build/`` from one that only shares the name, and falls back to pruning on
    the bare name when it has none. ``is_watchable_path`` passed no path, so
    every ambiguously-named directory holding real source broke parity.
    """

    # name → marker that makes a same-named directory genuinely build output.
    AMBIGUOUS = {
        "env": "pyvenv.cfg", "coverage": "lcov.info", "build": None, "out": None,
        "public": None, "vendor": "autoload.php", "target": None, "tmp": None,
        "temp": None, "bin": None, "obj": None,
    }

    def _tree(self, tmp_path: Path) -> Path:
        root = tmp_path / "proj"
        (root / "app").mkdir(parents=True)
        (root / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
        (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        for name, marker in self.AMBIGUOUS.items():
            source_dir = root / name
            source_dir.mkdir()
            (source_dir / "agent.py").write_text(
                "def handler():\n    return 1\n", encoding="utf-8")
            output_dir = root / "svc" / name
            output_dir.mkdir(parents=True)
            (output_dir / "bundle.py").write_text("x = 1\n", encoding="utf-8")
            if marker:
                (output_dir / marker).write_text("generated\n", encoding="utf-8")
            else:
                (output_dir / "artifact.o").write_bytes(b"\x00")
        return root

    def _collected(self, root: Path) -> set:
        from codebeacon.discover.scanner import collect_files
        return {Path(f).resolve() for f in collect_files(str(root))}

    def test_source_under_an_ambiguous_dir_name_is_watchable(self, tmp_path):
        from codebeacon.watch import build_ignore_matcher, is_watchable_path

        root = self._tree(tmp_path)
        collected = self._collected(root)
        matcher = build_ignore_matcher(root)

        for name in self.AMBIGUOUS:
            path = (root / name / "agent.py").resolve()
            assert path in collected, f"{name}/agent.py must be collected"
            assert is_watchable_path(root, path, matcher), (
                f"scan collects {name}/agent.py but the watcher ignores it"
            )

    def test_real_build_output_is_still_pruned_by_both(self, tmp_path):
        """Parity must not be bought by making the watcher indiscriminate."""
        from codebeacon.watch import build_ignore_matcher, is_watchable_path

        root = self._tree(tmp_path)
        collected = self._collected(root)
        matcher = build_ignore_matcher(root)

        for name in self.AMBIGUOUS:
            path = (root / "svc" / name / "bundle.py").resolve()
            assert path not in collected, f"svc/{name} is build output"
            assert not is_watchable_path(root, path, matcher)

    def test_every_collected_file_is_watchable(self, tmp_path):
        """The differential in full: scan-collects ⇒ watchable, no exceptions."""
        from codebeacon.watch import build_ignore_matcher, is_watchable_path

        root = self._tree(tmp_path)
        matcher = build_ignore_matcher(root)
        unwatchable = [
            p for p in self._collected(root)
            if not is_watchable_path(root, p, matcher)
        ]
        assert unwatchable == []


class TestWatchEventFilter:
    def _handler(self, root: Path):
        from codebeacon.watch import Debouncer, _make_handler, build_ignore_matcher

        class _Base:
            pass

        debouncer = Debouncer(0.01)
        return _make_handler(_Base, root, build_ignore_matcher(root), debouncer), debouncer

    class _Event:
        """Minimal stand-in for a watchdog event (watchdog is an optional extra)."""

        def __init__(self, event_type: str, src_path: str):
            self.event_type = event_type
            self.src_path = src_path
            self.is_directory = False

    @pytest.mark.parametrize("event_type", ["opened", "closed_no_write"])
    def test_read_only_events_do_not_arm_the_debouncer(self, tmp_path, event_type):
        """On Linux a resync's own reads emit these; without the filter each
        resync re-triggers itself and the watcher never idles."""
        src = tmp_path / "app.py"
        src.write_text("x = 1\n", encoding="utf-8")
        handler, debouncer = self._handler(tmp_path)

        handler.on_any_event(self._Event(event_type, str(src)))
        assert debouncer.take() == set()

    @pytest.mark.parametrize(
        "event_type", ["created", "modified", "moved", "deleted", "closed"]
    )
    def test_write_events_still_arm_the_debouncer(self, tmp_path, event_type):
        src = tmp_path / "app.py"
        src.write_text("x = 1\n", encoding="utf-8")
        handler, debouncer = self._handler(tmp_path)

        handler.on_any_event(self._Event(event_type, str(src)))
        assert debouncer.take() == {str(src)}

    def test_real_watchdog_read_events_are_filtered(self, tmp_path):
        """Same assertion against watchdog's own event classes, so the string
        constants cannot drift from the library's."""
        watchdog_events = pytest.importorskip("watchdog.events")
        src = tmp_path / "app.py"
        src.write_text("x = 1\n", encoding="utf-8")
        handler, debouncer = self._handler(tmp_path)

        for name in ("FileOpenedEvent", "FileClosedNoWriteEvent"):
            event_cls = getattr(watchdog_events, name, None)
            if event_cls is None:  # older watchdog without the class
                continue
            handler.on_any_event(event_cls(str(src)))
            assert debouncer.take() == set(), name

        handler.on_any_event(watchdog_events.FileModifiedEvent(str(src)))
        assert debouncer.take() == {str(src)}


# ── CB-CLUSTER-DRIFT ──────────────────────────────────────────────────────────

def _two_triangles() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_edges_from([
        ("a", "b"), ("b", "c"), ("a", "c"),
        ("c", "d"),
        ("d", "e"), ("e", "f"), ("d", "f"),
    ])
    return G


def _ambiguous_graph() -> nx.DiGraph:
    """Blocks with enough inter-block noise that the partition is genuinely
    ambiguous — the shape real code graphs have, and the one where an unseeded
    Leiden lands somewhere different on nearly every run (measured: 4 distinct
    partitions in 5 consecutive unseeded calls). A crisp set of cliques would
    hide the bug, since every backend agrees on those no matter the seed."""
    blocks = nx.random_partition_graph([25] * 8, 0.35, 0.06, seed=7)
    G = nx.DiGraph()
    G.add_edges_from(sorted((str(u), str(v)) for u, v in blocks.edges()))
    return G


class TestClusterDeterminism:
    def test_repeated_clustering_is_identical(self):
        G = _ambiguous_graph()
        first = cluster(G)
        for _ in range(4):
            assert cluster(G) == first

    def test_node_insertion_order_does_not_change_the_partition(self):
        """The backends see a canonically ordered graph, so two graphs that are
        equal but were built in different orders must cluster identically."""
        G = _ambiguous_graph()
        shuffled = nx.DiGraph()
        shuffled.add_edges_from(sorted(G.edges(), reverse=True))
        assert cluster(shuffled) == cluster(G)

    def test_canonical_undirected_is_order_stable(self):
        G = _two_triangles()
        reversed_G = nx.DiGraph()
        reversed_G.add_edges_from(reversed(list(G.edges())))
        left = cluster_mod._canonical_undirected(G)
        right = cluster_mod._canonical_undirected(reversed_G)
        assert list(left.edges()) == list(right.edges())
        assert list(left.nodes()) == list(right.nodes())


class TestClusterBackendsAreSeeded:
    """The behavioural tests above catch drift statistically; these pin the seed
    itself, so removing it from any one backend is caught outright."""

    def test_graspologic_leiden_gets_the_seed(self, monkeypatch):
        partition = pytest.importorskip("graspologic.partition")
        seen: dict = {}
        real = partition.leiden

        def spy(graph, **kwargs):
            seen.update(kwargs)
            return real(graph, **kwargs)

        monkeypatch.setattr(partition, "leiden", spy)
        assert cluster_mod._try_graspologic(_two_triangles()) is not None
        assert seen.get("random_seed") == cluster_mod._SEED

    def test_leidenalg_gets_the_seed(self, monkeypatch):
        leidenalg = pytest.importorskip("leidenalg")
        pytest.importorskip("igraph")
        seen: dict = {}
        real = leidenalg.find_partition

        def spy(graph, partition_type, **kwargs):
            seen.update(kwargs)
            return real(graph, partition_type, **kwargs)

        monkeypatch.setattr(leidenalg, "find_partition", spy)
        assert cluster_mod._try_leidenalg(_two_triangles()) is not None
        assert seen.get("seed") == cluster_mod._SEED

    def test_louvain_fallback_gets_the_seed(self, monkeypatch):
        seen: dict = {}
        real = nx.community.louvain_communities

        def spy(graph, **kwargs):
            seen.update(kwargs)
            return real(graph, **kwargs)

        monkeypatch.setattr(nx.community, "louvain_communities", spy)
        assert cluster_mod._try_louvain(_two_triangles()) is not None
        assert seen.get("seed") == cluster_mod._SEED


class TestClusterCoversEveryNode:
    def test_isolated_nodes_get_singleton_communities(self):
        G = _two_triangles()
        G.add_nodes_from(["lonely-1", "lonely-2", "lonely-3"])

        communities = cluster(G)

        assert set(communities) == set(G.nodes())
        assert len({communities[n] for n in ("lonely-1", "lonely-2", "lonely-3")}) == 3
        assert communities["lonely-1"] != communities["a"]

    def test_apply_communities_labels_every_node(self):
        G = _two_triangles()
        G.add_nodes_from(["lonely-1", "lonely-2"])
        apply_communities(G, cluster(G))
        assert all("community" in data for _n, data in G.nodes(data=True))

    def test_singleton_assignment_is_deterministic(self):
        G = _two_triangles()
        G.add_nodes_from(["z-lonely", "a-lonely"])
        assert cluster(G) == cluster(G)

    def test_all_isolates_graph_still_partitions(self):
        """No edges at all: every backend declines, the connected-components
        fallback runs, and every node still gets a community."""
        G = nx.DiGraph()
        G.add_nodes_from(["a", "b", "c"])
        communities = cluster(G)
        assert set(communities) == {"a", "b", "c"}
        assert len(set(communities.values())) == 3

    def test_empty_graph_is_still_empty(self):
        assert cluster(nx.DiGraph()) == {}


class TestCommunityCountIsHonest:
    """Now that isolates get their own communities, a sparsely-connected corpus
    reports mostly communities-of-one (measured: 351 of 366 on a real scan).
    The report has to say so rather than imply 366 real groupings."""

    def _report(self, G):
        from codebeacon.graph.analyze import analyze
        return analyze(G, cluster(G), {})

    def test_singletons_are_named_separately(self):
        from codebeacon.graph.analyze import report_to_markdown

        G = _two_triangles()
        G.add_nodes_from(["lonely-1", "lonely-2", "lonely-3"])
        report = self._report(G)

        assert report.singleton_communities == 3
        assert report.community_count == len(set(cluster(G).values()))
        line = [
            l for l in report_to_markdown(report).splitlines()
            if l.startswith("- Communities:")
        ][0]
        assert "3 single-node" in line
        assert f"{report.community_count - 3} with 2+ members" in line

    def test_plain_count_when_there_are_no_singletons(self):
        from codebeacon.graph.analyze import report_to_markdown

        report = self._report(_two_triangles())
        assert report.singleton_communities == 0
        assert f"- Communities: {report.community_count}" in report_to_markdown(report)


class TestCohesionReportIsBounded:
    def test_report_caps_the_cohesion_list(self):
        """Singleton communities score a meaningless 1.000; the section is
        capped like every other one so they cannot drown the real scores."""
        from codebeacon.graph.analyze import GraphReport, report_to_markdown

        report = GraphReport(cohesion_scores={cid: 0.5 for cid in range(40)})
        md = report_to_markdown(report)
        assert md.count("- Community ") == 10
        assert "- Community 0: 0.500" in md
        assert "- Community 39" not in md
