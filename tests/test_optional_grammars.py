"""Optional grammar handling — pyproject.toml extras split (0.6.0).

Pre-0.6.0 all 14 tree-sitter grammars were unconditional dependencies, so
``pip install codebeacon`` pulled ~150MB onto every install even if the user
only scanned Python repos. 0.6.0 keeps Python + JS/TS in the default and
moves the rest to extras (``[java]``, ``[backend]``, ``[full]``, etc.).

The runtime already had graceful-skip plumbing — ``get_language()`` returns
None and extractors fall through — but it was never tested. These tests pin
that contract so a future refactor doesn't accidentally turn a missing
grammar into a hard crash for users on a lean install.
"""
from __future__ import annotations

import pytest

from codebeacon.extract import base


@pytest.fixture(autouse=True)
def _isolate_lang_cache():
    """Each grammar lookup memoises Language objects in ``_LANG_CACHE``.
    Without isolation, a test that mocks out an import would leave a
    cached ``None`` entry that poisons later tests (the Spring-Boot
    extractor would then see Java grammar = missing and skip routes).

    Snapshot before, restore after. Autouse so every test in this file
    is covered without each test having to remember to apply it.
    """
    snapshot = dict(base._LANG_CACHE)
    try:
        yield
    finally:
        base._LANG_CACHE.clear()
        base._LANG_CACHE.update(snapshot)


class TestGracefulSkipWhenGrammarMissing:
    def test_get_language_returns_none_for_unknown_name(self):
        # Unknown grammar names should NOT crash — the extractor pipeline
        # has hundreds of files and one rogue ext shouldn't kill the scan.
        assert base.get_language("klingon") is None

    def test_get_language_returns_none_when_module_import_fails(self, monkeypatch):
        """If a grammar module fails to import (user is on a lean install
        and never ran ``pip install codebeacon[java]``), ``get_language``
        must return None with a one-time warning — not raise."""
        # Bypass the cache so we exercise the import path
        base._LANG_CACHE.pop("java", None)

        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "tree_sitter_java":
                raise ImportError("not installed")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.warns(UserWarning, match="Grammar 'java' not installed"):
            assert base.get_language("java") is None

    def test_warning_mentions_correct_pip_extra(self, monkeypatch):
        """The warning should tell the user exactly which extra to install."""
        base._LANG_CACHE.pop("csharp", None)
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name == "tree_sitter_c_sharp":
                raise ImportError("nope")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        with pytest.warns(UserWarning, match=r"codebeacon\[csharp\]"):
            base.get_language("csharp")


class TestPipExtraMapping:
    """Each language name in _GRAMMAR_MODULES should resolve to a pip extra
    that exists in pyproject.toml. Otherwise the error message lies to
    users and tells them to install an extra that does not exist."""

    # These slugs must match the keys in pyproject.toml [project.optional-dependencies].
    # Listed here so the test fails loudly if either side drifts.
    EXPECTED_PIP_EXTRAS_IN_PYPROJECT = {
        "java", "kotlin", "go", "ruby", "php", "csharp",
        "rust", "swift", "html", "svelte",
    }

    def test_per_language_extras_resolve(self):
        """Languages NOT in the default install must map to an extra slug."""
        non_default_languages = set(base._GRAMMAR_MODULES) - {"python", "javascript", "typescript", "tsx"}
        for lang in non_default_languages:
            extra = base._pip_extra(lang)
            assert extra in self.EXPECTED_PIP_EXTRAS_IN_PYPROJECT, (
                f"_pip_extra({lang!r}) → {extra!r}, but pyproject.toml has no "
                f"matching [project.optional-dependencies] entry."
            )

    def test_pyproject_actually_declares_each_extra(self):
        """Read pyproject.toml and verify each expected extra exists."""
        try:
            import tomllib  # py311+
        except ImportError:
            import tomli as tomllib  # type: ignore

        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        with open(root / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        extras = set(data["project"]["optional-dependencies"].keys())
        missing = self.EXPECTED_PIP_EXTRAS_IN_PYPROJECT - extras
        assert not missing, f"Missing extras in pyproject.toml: {missing}"


class TestDefaultInstallContainsCommonGrammars:
    """The default install must succeed in scanning Python + JS + TS repos
    so first-time users don't see a wall of warnings."""

    @pytest.mark.parametrize("grammar", ["python", "javascript", "typescript"])
    def test_default_grammar_loadable(self, grammar):
        # In CI / dev these are always installed; the test asserts that the
        # default-install grammar list (in pyproject.toml dependencies)
        # actually corresponds to grammars that load cleanly.
        lang = base.get_language(grammar)
        assert lang is not None, (
            f"Grammar {grammar!r} listed as a default dependency but won't "
            f"load — pyproject.toml is out of sync with extract/base.py."
        )
