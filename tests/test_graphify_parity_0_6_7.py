"""Graphify-parity audit follow-ups shipped in 0.6.7.

The deferred items from the 0.6.6 sweep (see test_graphify_parity_0_6_6.py):

1. **`.codebeaconignore` negation no longer disables all directory pruning**
   (graphify #1274). A single unrelated ``!`` rule used to set a global
   "descend into every ignored directory" flag; now each ignored directory is
   kept only if a negation could actually re-include a file beneath *it*.

2. **`run_query` surfaces grammar-compile errors loudly** (graphify v0.8.39's
   loud-failure layer). A tree-sitter "Invalid node type" / "Impossible
   pattern" — i.e. grammar drift on a grammar the query is *supposed* to support
   — now raises ``GrammarQueryError`` and becomes a first-class
   ``ExtractionFailure`` instead of a silent ``[]``.

3. **Ignore-glob regexes are compiled once** (graphify #1261) — perf; semantics
   are unchanged (and pinned by the existing ignore tests + the sanity check
   below).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from codebeacon.discover.ignore import IgnoreMatcher
from codebeacon.discover.scanner import collect_files


# ── #1274: per-directory negation pruning ────────────────────────────────────

class TestIgnoreNegationPruning:
    def test_anchored_negation_does_not_descend_unrelated_subtree(self):
        m = IgnoreMatcher(["build/", "!src/gen/keep.ts"])
        # The negation lives under src/ — it can never rescue anything in build/.
        assert m.could_unignore_under("build") is False
        assert m.could_unignore_under("src") is True
        assert m.could_unignore_under("src/gen") is True

    def test_unanchored_negation_is_conservative(self):
        # `!keep.ts` can match at any depth, so every ignored dir must be
        # descended (correctness over pruning).
        m = IgnoreMatcher(["build/", "!keep.ts"])
        assert m.could_unignore_under("build") is True

    def test_no_negation_never_unignores(self):
        m = IgnoreMatcher(["build/", "dist/"])
        assert m.could_unignore_under("build") is False
        assert m.could_unignore_under("dist") is False

    def test_double_star_negation_scoped_to_its_subtree(self):
        m = IgnoreMatcher(["dist/", "!dist/**"])
        assert m.could_unignore_under("dist") is True
        assert m.could_unignore_under("build") is False

    def test_end_to_end_rescue_without_descending_unrelated_dir(self, tmp_path):
        """0.6.9 git parity update: the rescue uses git's idiom ``src/gen/*``
        (exclude the *contents*, keep the dir), because ``src/gen/`` +
        ``!src/gen/keep.ts`` no longer re-includes — see the test below."""
        root = tmp_path.resolve()
        (root / "src" / "gen").mkdir(parents=True)
        (root / "build" / "sub").mkdir(parents=True)
        (root / "src" / "app.py").write_text("x = 1")
        (root / "src" / "gen" / "keep.ts").write_text("export const x = 1")
        (root / "build" / "junk.py").write_text("y = 2")
        (root / ".codebeaconignore").write_text(
            "build/\nsrc/gen/*\n!src/gen/keep.ts\n"
        )
        files = collect_files(str(root))
        # The negated file is rescued (contents-excluded dir, git idiom)…
        assert any(f.endswith("keep.ts") for f in files)
        # …and the unrelated ignored subtree's files stay excluded.
        assert not any("junk" in f for f in files)
        assert any(f.endswith("app.py") for f in files)

    def test_no_reinclude_under_excluded_dir_end_to_end(self, tmp_path):
        """0.6.9 git parity: with the *directory* excluded (``src/gen/``), an
        explicit self-negation no longer rescues a file beneath it — matches
        ``git check-ignore`` ("cannot re-include a file if a parent directory
        is excluded"). Use ``src/gen/*`` + ``!src/gen/keep.ts`` like git."""
        root = tmp_path.resolve()
        (root / "src" / "gen").mkdir(parents=True)
        (root / "src" / "gen" / "keep.ts").write_text("export const x = 1")
        (root / "src" / "app.py").write_text("x = 1")
        (root / ".codebeaconignore").write_text(
            "src/gen/\n!src/gen/keep.ts\n"
        )
        files = collect_files(str(root))
        assert not any(f.endswith("keep.ts") for f in files)
        assert any(f.endswith("app.py") for f in files)


# ── v0.8.39: run_query loud failure ──────────────────────────────────────────

class TestRunQueryLoudFailure:
    def test_run_query_raises_on_compile_error_but_not_on_valid(self):
        from codebeacon.extract.base import (
            GrammarQueryError, get_language, get_parser, run_query,
        )
        lang = get_language("python")
        if lang is None:
            pytest.skip("python grammar not installed")
        tree = get_parser("python").parse(b"x = 1\n")
        # Valid query → returns (no raise).
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            run_query(lang, "(identifier) @id", tree.root_node)
        # References a node type the grammar doesn't have → compile error.
        with pytest.raises(GrammarQueryError):
            run_query(lang, "(this_node_type_does_not_exist) @x", tree.root_node)

    def test_extractor_propagates_grammar_error_as_extraction_failure(
        self, tmp_path, monkeypatch
    ):
        from codebeacon.wave import _extract_file, ExtractionFailure
        import codebeacon.extract.routes as routes_mod

        # Force a drift-broken query for an allowed grammar (fastapi→python is
        # allowlisted, so the gate passes and run_query reaches Query()).
        monkeypatch.setattr(
            routes_mod, "load_query_file",
            lambda name: "(this_node_type_does_not_exist) @x",
        )
        f = tmp_path / "main.py"
        f.write_text("x = 1\n")
        result = _extract_file(str(f), "fastapi", str(tmp_path))
        assert isinstance(result, ExtractionFailure), (
            "a grammar-compile error must surface as ExtractionFailure, not a "
            "silent empty extraction"
        )
        assert result.error_type == "GrammarQueryError"


# ── #1261: glob-compile memoization is semantics-preserving ───────────────────

class TestGlobMemoizationSanity:
    @pytest.mark.parametrize(
        "rules,path,is_dir,expected",
        [
            (["*.log"], "debug.log", False, True),
            (["*.log"], "src/debug.log", False, True),       # unanchored, any depth
            (["/build"], "build", True, True),               # anchored to root
            (["/build"], "src/build", True, False),          # not at root
            (["src/**/*.ts"], "src/a/b/c.ts", False, True),  # ** crosses segments
            (["src/*.ts"], "src/a/b.ts", False, False),      # * must not cross /
        ],
    )
    def test_glob_semantics_unchanged(self, rules, path, is_dir, expected):
        assert IgnoreMatcher(rules).is_ignored(path, is_dir=is_dir) is expected
