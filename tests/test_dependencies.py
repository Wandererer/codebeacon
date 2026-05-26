"""Tests for codebeacon.extract.dependencies — JS/TS barrel re-exports.

Mirrors graphify #1494874. tree-sitter SCM queries pick up `import` /
`require`, but NOT `export { X } from './m'` style re-exports. Those
are how Next.js / monorepo barrels expose their public API, and missing
them means the import-edge graph shows 0 imports for hundreds of files.

The regex post-processor in dependencies.py covers:

* ``export { Foo, Bar as Baz } from './mod'``
* ``export * from './mod'``
* ``export * as ns from './mod'``

…across `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`. Non-JS/TS files
are untouched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.extract.dependencies import extract_dependencies


def _by_relation(edges, relation: str) -> list[str]:
    return sorted(e.target for e in edges if e.relation == relation)


def test_named_re_export(tmp_path):
    f = tmp_path / "index.ts"
    f.write_text("export { Foo, Bar as Baz } from './mod';\n")
    edges = extract_dependencies(str(f), framework="react")
    assert _by_relation(edges, "re_exports") == ["./mod"]


def test_star_re_export(tmp_path):
    f = tmp_path / "index.ts"
    f.write_text("export * from './all';\n")
    assert _by_relation(extract_dependencies(str(f), "react"), "re_exports") == ["./all"]


def test_star_namespace_re_export(tmp_path):
    f = tmp_path / "index.ts"
    f.write_text("export * as ns from './ns';\n")
    assert _by_relation(extract_dependencies(str(f), "react"), "re_exports") == ["./ns"]


def test_all_three_forms_in_one_file(tmp_path):
    f = tmp_path / "index.ts"
    f.write_text(
        "export { Foo } from './a';\n"
        "export * from './b';\n"
        "export * as ns from './c';\n"
    )
    assert _by_relation(extract_dependencies(str(f), "react"), "re_exports") == [
        "./a", "./b", "./c",
    ]


def test_dedupes_repeated_target(tmp_path):
    """Two `export … from './mod'` lines should produce one edge, not two."""
    f = tmp_path / "index.ts"
    f.write_text(
        "export { Foo } from './mod';\n"
        "export { Bar } from './mod';\n"
    )
    edges = _by_relation(extract_dependencies(str(f), "react"), "re_exports")
    assert edges == ["./mod"]


def test_ignored_in_python_file(tmp_path):
    """The regex is JS/TS-only. A Python file with `export` text in a string
    must not produce re_exports edges."""
    f = tmp_path / "mod.py"
    f.write_text('x = "export { X } from \'./y\'"\n')
    edges = extract_dependencies(str(f), framework="fastapi")
    assert all(e.relation != "re_exports" for e in edges)


def test_regular_import_still_works_alongside(tmp_path):
    """Adding the regex pass must not break the SCM-driven `imports_from`
    extraction in the same file."""
    f = tmp_path / "index.tsx"
    f.write_text(
        "import React from 'react';\n"
        "export { Button } from './Button';\n"
    )
    edges = extract_dependencies(str(f), framework="react")
    imports = _by_relation(edges, "imports_from")
    re_exports = _by_relation(edges, "re_exports")
    assert "react" in imports
    assert "./Button" in re_exports
