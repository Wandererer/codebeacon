"""Regression tests for the 0.7.1 audit — JS/TS extraction (fixer F5).

Pinned defects:

  GI-2110 / G-0931-5 (CG-JS-EXPORT-NODING)
      Every react.scm declaration pattern gated the name on ``^[A-Z]``, so a
      module whose exports are hooks, stores, utils or constants produced ZERO
      nodes and importers of it had nothing to bind to. Measured on a real
      865-file Next.js app: 47.6% of internal import edges pointed at a file
      codebeacon rendered as empty (13.8% after this fix; the rest are barrel
      files and type-only modules, which legitimately declare no runtime symbol).

  G-0938-5 (CG-JS-DYNAMIC-IMPORT)
      ``await import('./mod')`` is a call_expression, not an import_statement,
      so neither the SCM queries nor the require()/re-export regex passes saw
      it: a code-split module had no dependency edge at all.

  V5-EXTRA-3
      `import networkx as nx` reached the graph as the target "networkx as nx"
      (36 occurrences in a self-scan), so an aliased first-party import could
      never bind to its declaration.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from codebeacon.extract.components import extract_components
from codebeacon.extract.dependencies import extract_dependencies

FIXTURES = Path(__file__).parent / "fixtures_070_extract_js"


def _names(path: Path, framework: str = "nextjs") -> list[str]:
    return [c.name for c in extract_components(str(path), framework)]


def _by_name(path: Path, framework: str = "nextjs") -> dict:
    return {c.name: c for c in extract_components(str(path), framework)}


# ── GI-2110 / G-0931-5 — module exports that are not uppercase components ─────

class TestExportNoding:
    def test_lowercase_arrow_export_is_noded(self):
        """The single highest-volume shape: hooks / stores / utils."""
        assert "useAuth" in _names(FIXTURES / "store.ts")

    def test_function_expression_export_is_noded(self):
        assert "helper" in _names(FIXTURES / "store.ts")

    def test_call_expression_export_keeps_the_const_name(self):
        """`export const useAuthStore = create(...)` — the const is the export;
        the wrapper (`create`) must never become the node's identity."""
        names = _names(FIXTURES / "store.ts")
        assert "useAuthStore" in names
        assert "create" not in names

    def test_scalar_consts_are_noded(self):
        """G-0931-5: `export const MAX_RETRIES = 3` had no node, so a named
        import of it could not bind."""
        names = _names(FIXTURES / "store.ts")
        for scalar in ("DEMO_MODE", "MAX_RETRIES", "API_BASE"):
            assert scalar in names

    def test_object_literal_yields_container_plus_callable_members(self):
        """Container AND members — emitting the container must not short-circuit
        descent into its children (upstream's early-return trap)."""
        names = _names(FIXTURES / "store.ts")
        assert "authUtils" in names
        assert {"authUtils.getToken", "authUtils.setToken", "authUtils.clear"} <= set(names)

    def test_object_literal_data_pairs_are_not_noded(self):
        """`storageKey: "t"` is configuration, not module API surface."""
        assert "authUtils.storageKey" not in _names(FIXTURES / "store.ts")

    def test_member_labels_are_qualified(self):
        """A bare `getToken` / `clear` label would be matched by build.py's
        module-basename→label import binding and fabricate edges into unrelated
        files, so members carry their container's name."""
        names = _names(FIXTURES / "store.ts")
        for bare in ("getToken", "setToken", "clear"):
            assert bare not in names

    def test_deferred_export_clause_is_noded_with_alias(self):
        """`const x = …; export { x, y as z }` — the declare-then-export idiom."""
        names = _names(FIXTURES / "store.ts")
        assert "reducer" in names
        assert "showToast" in names   # the alias is the importable name
        assert "toast" not in names

    def test_re_exports_do_not_mint_local_nodes(self):
        """`export { Other } from './other'` declares nothing HERE — the symbol
        belongs to the other file (dependencies.py already emits re_exports)."""
        names = _names(FIXTURES / "store.ts")
        assert "Other" not in names
        assert "star" not in names

    def test_unexported_lowercase_declaration_is_not_noded(self):
        """Only EXPORTED declarations are ungated; a file-local lowercase const
        is an implementation detail, not module surface."""
        assert "internalOnly" not in _names(FIXTURES / "store.ts")

    def test_type_only_exports_are_not_noded(self):
        """A type-only export names no runtime symbol."""
        names = _names(FIXTURES / "types_only.ts")
        assert "OnlyAType" not in names
        assert "InlineType" not in names
        assert "Reexported" not in names
        assert "realValue" in names

    def test_uppercase_components_keep_their_identity_and_line(self):
        """Regression guard: the pre-existing component patterns still win, and
        the new ungated pattern must not move their line number."""
        comps = _by_name(FIXTURES / "store.ts")
        src = (FIXTURES / "store.ts").read_text().splitlines()
        assert "Badge" in comps and "Page" in comps
        assert src[comps["Badge"].line - 1].startswith("export const Badge")
        assert src[comps["Page"].line - 1].startswith("export default function Page")

    def test_new_nodes_carry_their_own_declaration_line(self):
        comps = _by_name(FIXTURES / "store.ts")
        src = (FIXTURES / "store.ts").read_text().splitlines()
        assert src[comps["MAX_RETRIES"].line - 1].strip().startswith("export const MAX_RETRIES")
        assert src[comps["authUtils.clear"].line - 1].strip().startswith("clear:")

    def test_hooks_scope_to_the_enclosing_exported_hook(self):
        """A hook call inside an exported lowercase arrow belongs to it, not to
        every component in the file."""
        comps = _by_name(FIXTURES / "store.ts")
        assert "useAuthStore" in comps["useAuth"].hooks
        assert "useAuthStore" not in comps["Page"].hooks

    def test_javascript_grammar_parity(self):
        """react.scm is allowlisted for javascript as well as typescript/tsx —
        the same shapes must extract from a .js file."""
        names = _names(FIXTURES / "store.js", framework="react")
        assert {"useAuthStore", "DEMO_MODE", "authUtils", "authUtils.getToken",
                "authUtils.setToken", "useAuth", "legacyVar", "formatDate",
                "showToast"} <= set(names)
        assert "authUtils.storageKey" not in names

    def test_route_segment_config_is_not_a_page_component(self, tmp_path: Path):
        """Next.js App Router route files export `metadata` / `revalidate`
        beside the page. Now that those are noded, they must not all be
        presented as "Page Component" in the wiki."""
        page = tmp_path / "app" / "blog" / "page.tsx"
        page.parent.mkdir(parents=True)
        page.write_text(
            "export const metadata = { title: 'Blog' };\n"
            "export const revalidate = 60;\n"
            "export default function BlogPage() { return null; }\n"
        )
        comps = {c.name: c for c in extract_components(str(page), "nextjs", str(tmp_path))}
        assert comps["BlogPage"].is_page
        assert not comps["metadata"].is_page
        assert not comps["revalidate"].is_page

    def test_page_marking_falls_back_when_nothing_looks_like_a_component(self, tmp_path: Path):
        """SvelteKit's `+page` stem and route files of plain functions have no
        uppercase name to prefer — the pre-0.7.1 mark-everything behaviour."""
        page = tmp_path / "pages" / "legacy.tsx"
        page.parent.mkdir(parents=True)
        page.write_text("export function formatDate() {}\nexport const slug = 'x';\n")
        comps = extract_components(str(page), "nextjs", str(tmp_path))
        assert comps and all(c.is_page for c in comps)

    @pytest.mark.parametrize("grammar", ["javascript", "typescript", "tsx"])
    def test_react_query_compiles_against_every_allowed_grammar(self, grammar: str):
        """A pattern naming a node type one grammar lacks ("Invalid node type")
        or one it cannot reach ("Impossible pattern") fails at COMPILE time and
        takes every file of that grammar down with it."""
        from tree_sitter import Query

        from codebeacon.extract.base import get_language, load_query_file

        lang = get_language(grammar)
        if lang is None:
            pytest.skip(f"grammar {grammar} not installed")
        Query(lang, load_query_file("react"))


# ── G-0938-5 — dynamic import() ──────────────────────────────────────────────

class TestDynamicImport:
    def _targets(self) -> list[str]:
        return [e.target for e in extract_dependencies(str(FIXTURES / "dyn.ts"), "nextjs")]

    def test_module_and_function_scope_dynamic_imports_are_edges(self):
        targets = self._targets()
        assert "@/lib/constants" in targets   # inside an exported async function
        assert "./db" in targets              # nested two functions deep

    def test_commented_out_dynamic_imports_are_ignored(self):
        targets = self._targets()
        assert not any("commented" in t for t in targets)

    def test_non_literal_specifier_is_skipped(self):
        """`import(modName)` — the module is only known at runtime."""
        targets = self._targets()
        assert "modName" not in targets
        assert "./computed" not in targets

    def test_lookalike_calls_are_not_imports(self):
        """`myimport(...)` and `registry.import(...)` are not dynamic imports."""
        targets = self._targets()
        assert "./not-an-import" not in targets
        assert "./also-not" not in targets

    def test_statically_imported_module_is_not_double_counted(self):
        targets = self._targets()
        assert targets.count("./statik") == 1

    def test_relation_matches_static_imports(self):
        edges = extract_dependencies(str(FIXTURES / "dyn.ts"), "nextjs")
        dynamic = [e for e in edges if e.target == "./db"]
        assert [e.relation for e in dynamic] == ["imports_from"]


# ── V5-EXTRA-3 — alias clause in the import target ───────────────────────────

class TestImportAliasStripping:
    def test_rust_aliased_use_loses_the_alias(self):
        """`use crate::services::user_service as user_svc` — the alias is a local
        binding, not part of the dependency's identity."""
        targets = {e.target for e in extract_dependencies(str(FIXTURES / "aliased.rs"), "actix")}
        assert "crate::services::user_service" in targets
        assert "foo::bar" in targets
        assert not any(" as " in t for t in targets)

    def test_python_aliased_imports_lose_the_alias(self):
        """Python is now fixed twice over: fastapi.scm captures the dotted_name
        of an aliased_import directly, and this pass strips any alias clause a
        query still lets through. Both layers must agree."""
        targets = {e.target for e in extract_dependencies(str(FIXTURES / "aliased.py"), "fastapi")}
        assert "networkx" in targets
        assert "pkg.mod" in targets          # an aliased FIRST-party import can now bind
        assert "networkx as nx" not in targets
        assert "pkg.mod as m" not in targets

    def test_unaliased_imports_are_untouched(self):
        targets = {e.target for e in extract_dependencies(str(FIXTURES / "aliased.py"), "fastapi")}
        assert "plain_module" in targets
        assert "pkg.other.Thing" in targets

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("networkx as nx", "networkx"),
            ("pkg.mod as m", "pkg.mod"),
            ("foo::bar as baz", "foo::bar"),
            ("App\\Models\\User as U", "App\\Models\\User"),
            ("plain", "plain"),
            ("./my as file", "./my as file"),   # a path, not an alias clause
            ("@/lib/as as x", "@/lib/as as x"),
            ("pkg.mod as", "pkg.mod as"),
        ],
    )
    def test_alias_stripping_shapes(self, raw: str, expected: str):
        from codebeacon.extract.dependencies import _strip_import_alias

        assert _strip_import_alias(raw) == expected
