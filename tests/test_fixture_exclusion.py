"""Tests for the default exclusion of test-fixture directories.

Synthetic test fixtures (``tests/fixtures/``, ``test/fixtures/``,
``__fixtures__/``) are inputs for a project's *own* test suite, not product
surface, so codebeacon skips them by default — otherwise its self-scan indexes
``tests/fixtures/fastapi/main.py`` and reports 5 phantom "routes". The defaults
sit at the lowest precedence, so a ``.codebeaconignore`` negation re-includes
them, and — because matching is relative to the scan root — pointing the scan
*at* a fixture dir is unaffected.
"""
from __future__ import annotations

from pathlib import Path

from codebeacon.discover.scanner import DEFAULT_IGNORE_PATTERNS, collect_files


class TestFixtureExclusion:
    def test_tests_fixtures_excluded_by_default(self, tmp_path):
        """Files under ``tests/fixtures/`` are dropped without any ignore file."""
        fx = tmp_path / "tests" / "fixtures" / "fastapi"
        fx.mkdir(parents=True)
        (fx / "main.py").write_text("app = 1\n")
        (tmp_path / "real.py").write_text("# product code")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "main.py" not in names
        assert "real.py" in names

    def test_test_fixtures_singular_and_dunder_excluded(self, tmp_path):
        """``test/fixtures/`` and ``__fixtures__/`` are excluded too."""
        singular = tmp_path / "test" / "fixtures"
        singular.mkdir(parents=True)
        (singular / "sample.py").write_text("# fixture")
        dunder = tmp_path / "__fixtures__"
        dunder.mkdir()
        (dunder / "sample.py").write_text("# fixture")
        (tmp_path / "real.py").write_text("# product code")
        collected = collect_files(str(tmp_path))
        assert collected == [str(tmp_path / "real.py")]

    def test_excluded_at_any_depth(self, tmp_path):
        """The ``**/`` prefix prunes a fixtures tree nested under a subpackage."""
        nested = tmp_path / "packages" / "api" / "tests" / "fixtures"
        nested.mkdir(parents=True)
        (nested / "conftest_data.py").write_text("# fixture")
        (tmp_path / "packages" / "api" / "service.py").write_text("# code")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "conftest_data.py" not in names
        assert "service.py" in names

    def test_plain_tests_dir_not_excluded(self, tmp_path):
        """Only ``tests/fixtures``, not the whole ``tests/`` tree, is dropped."""
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_thing.py").write_text("# a real test module")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "test_thing.py" in names

    def test_codebeaconignore_negation_reincludes(self, tmp_path):
        """A ``!tests/fixtures/`` negation opts the tree back in (defaults lose)."""
        fx = tmp_path / "tests" / "fixtures" / "fastapi"
        fx.mkdir(parents=True)
        (fx / "main.py").write_text("app = 1\n")
        (tmp_path / ".codebeaconignore").write_text("!tests/fixtures/\n", encoding="utf-8")
        names = {Path(f).name for f in collect_files(str(tmp_path))}
        assert "main.py" in names

    def test_scanning_fixture_dir_as_root_still_collects(self, tmp_path):
        """Pointing the scan *at* a fixture dir collects it — matching is
        relative to the root, so its files never carry a ``tests/fixtures``
        prefix. Mirrors the test suite scanning ``integration_workspace`` as the
        scan root."""
        root = tmp_path / "tests" / "fixtures" / "integration_workspace"
        api = root / "api-python"
        api.mkdir(parents=True)
        (api / "main.py").write_text("app = 1\n")
        names = {Path(f).name for f in collect_files(str(root))}
        assert "main.py" in names

    def test_defaults_are_lowest_precedence(self, tmp_path):
        """The default patterns precede any user rules so negations can win."""
        # Sanity check on the assembly contract the negation test relies on.
        assert DEFAULT_IGNORE_PATTERNS == [
            "**/tests/fixtures/",
            "**/test/fixtures/",
            "**/__fixtures__/",
        ]
