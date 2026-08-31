"""Frontend component extraction for React, Vue, Svelte, Angular.

Public API:
    extract_components(file_path, framework, project_path="") -> list[ComponentInfo]

Extracts:
  - React: uppercase function/arrow components, hooks, props
  - Vue: defineComponent / SFC, composables, props
  - Svelte: SFC files, exported props, runes
  - Angular: @Component class, selector, templateUrl
"""
from __future__ import annotations

from pathlib import Path

from codebeacon.common.types import ComponentInfo
from codebeacon.extract.base import (
    extract_sfc_sections,
    load_query_file,
    node_text,
    parse_file,
    parse_sfc_script,
    run_query,
    GrammarQueryError,
)


# ── Framework → query file stem ───────────────────────────────────────────────

_FW_TO_QUERY: dict[str, str] = {
    "react":     "react",
    "nextjs":    "react",
    "node":      "react",
    "vue":       "vue",
    "nuxt":      "vue",
    "sveltekit": "svelte",
    "angular":   "angular",
}


# ── Public function ───────────────────────────────────────────────────────────

def extract_components(
    file_path: str,
    framework: str,
    project_path: str = "",
) -> list[ComponentInfo]:
    """Extract frontend component declarations from *file_path*."""
    fw = framework.lower()
    query_name = _FW_TO_QUERY.get(fw)
    if not query_name:
        return []

    query_src = load_query_file(query_name)
    if not query_src:
        return []

    # SFC dispatch
    ext = Path(file_path).suffix.lower()
    if ext in (".vue", ".svelte"):
        sfc = extract_sfc_sections(file_path)
        if sfc is None:
            return []
        parsed = parse_sfc_script(sfc)
    else:
        parsed = parse_file(file_path)

    if parsed is None:
        return []
    root, lang = parsed

    from codebeacon.extract.base import is_grammar_allowed
    if not is_grammar_allowed(query_name, lang):
        return []

    try:
        matches = run_query(lang, query_src, root)
    except GrammarQueryError:
        raise  # grammar drift on a supported grammar → surfaced as ExtractionFailure
    except Exception:
        return []

    _interpreters = {
        "react":   _interpret_react,
        "vue":     _interpret_vue,
        "svelte":  _interpret_svelte,
        "angular": _interpret_angular,
    }

    interpreter = _interpreters.get(query_name)
    if interpreter is None:
        return []

    try:
        components = interpreter(file_path, matches, fw)
    except Exception:
        components = []

    # For SFC files, ensure at least one component with the filename as name
    if ext in (".vue", ".svelte") and not components:
        stem = Path(file_path).stem
        components = [ComponentInfo(
            name=stem,
            source_file=file_path,
            line=1,
            framework=fw,
        )]

    # Derive route info for page components
    if project_path:
        _annotate_page_routes(components, file_path, fw, project_path)

    return components


# ── Helpers ───────────────────────────────────────────────────────────────────

def _annotate_page_routes(
    components: list[ComponentInfo],
    file_path: str,
    framework: str,
    project_path: str,
) -> None:
    """Mark components as page components and set route_path for file-system routed frameworks."""
    try:
        rel = Path(file_path).relative_to(Path(project_path))
    except ValueError:
        return

    parts = rel.parts
    is_page = False
    route_path = ""

    if framework in ("nextjs", "react"):
        if parts and parts[0] == "pages":
            is_page = True
        elif len(parts) >= 2 and parts[0] == "app":
            stem = Path(parts[-1]).stem
            if stem in ("page", "layout", "route"):
                is_page = True
    elif framework == "nuxt":
        if parts and parts[0] == "pages":
            is_page = True
    elif framework == "sveltekit":
        if len(parts) >= 3 and parts[0] == "src" and parts[1] == "routes":
            stem = Path(parts[-1]).stem
            if stem.startswith("+"):
                is_page = True

    if is_page:
        # A route file's page component is its default export. The named exports
        # beside it are route-segment config (Next.js App Router `metadata`,
        # `revalidate`, `dynamic`) or helpers — now that those are noded too,
        # marking them all would present every one as a "Page Component" in the
        # wiki. Uppercase is the component naming convention; when nothing in the
        # file follows it (SvelteKit's `+page` stem, an anonymous SFC, a route
        # file of plain functions) fall back to marking everything.
        named = [c for c in components if c.name[:1].isupper()]
        for comp in (named or components):
            comp.is_page = True


def _is_type_only(node) -> bool:
    """True for a TypeScript type-only export — ``export type { T }`` or the
    per-specifier ``export { type T, runtime }`` form.

    The ``type`` keyword is an anonymous child of the export_statement (or of the
    export_specifier), so it never appears in a capture; it has to be read off
    the node. A type-only export names no runtime symbol, so noding it would
    invent a declaration that does not exist at runtime.
    """
    return any(child.type == "type" and not child.is_named for child in node.children)


# ── Per-framework interpreters ────────────────────────────────────────────────

_REACT_PARENT_KEYS = (
    "component.export_func", "component.export_func_upper",
    "component.export_default_func", "component.export_arrow",
    "component.local_arrow", "component.hoc",
    "component.hoc_local", "component.hoc_bare_export",
    "component.hoc_bare_local", "component.export_fnexpr",
    "component.local_fnexpr", "component.local_func",
    "export.decl", "export.object", "export.clause",
)


def _interpret_react(
    file_path: str, matches: list, framework: str,
) -> list[ComponentInfo]:
    """React/Next.js: exported functions/arrows/symbols + hooks + props."""
    components: dict[str, ComponentInfo] = {}  # name → ComponentInfo
    comp_ranges: dict[str, tuple[int, int] | None] = {}  # name → (start_byte, end_byte)
    props: list[str] = []
    hook_sites: list[tuple[int, str]] = []    # (byte pos, hook name)
    import_sites: list[tuple[int, str]] = []  # (byte pos, import path)
    # `export { x }` specifiers are applied after the main loop so an inline
    # declaration of the same name always wins the line number, whatever order
    # tree-sitter returns the two patterns in.
    clause_specs: list[tuple[str, object]] = []  # (name, export_statement node)

    def _record(name: str, parent) -> None:
        """Register a declaration node, first spelling wins."""
        if not name or name in components:
            return
        components[name] = ComponentInfo(
            name=name,
            source_file=file_path,
            line=parent.start_point[0] + 1 if parent is not None else 1,
            framework=framework,
        )
        comp_ranges[name] = (
            (parent.start_byte, parent.end_byte) if parent is not None else None
        )

    for _idx, caps in matches:
        # Line + byte range come from the parent export/declaration node
        parent = None
        for k in _REACT_PARENT_KEYS:
            if k in caps:
                parent = caps[k][0]
                break

        # Exported function component
        for cap_key in ("component.func_name", "component.arrow_name", "component.memo_name"):
            if cap_key in caps:
                _record(node_text(caps[cap_key][0]), parent)

        # Exported module symbol of any case (hook, store, util, constant)
        if "export.name" in caps:
            for name_node in caps["export.name"]:
                _record(node_text(name_node), parent)

        # Callable members of an exported object literal. The member label is
        # qualified (`repo.findById`) — a bare `create` / `get` / `remove` would
        # be matched by graph/build.py's module-basename→label import binding and
        # fabricate edges into unrelated files.
        if "export.member" in caps and "export.owner" in caps:
            owner = node_text(caps["export.owner"][0])
            for member_node in caps["export.member"]:
                member = node_text(member_node)
                if owner and member:
                    _record(f"{owner}.{member}", member_node.parent or parent)

        # export { x, y as z } — deferred, and never for a re-export
        if "export.spec" in caps and "export.clause" in caps:
            stmt = caps["export.clause"][0]
            if stmt.child_by_field_name("source") is None and not _is_type_only(stmt):
                for spec in caps["export.spec"]:
                    if _is_type_only(spec):
                        continue
                    named = spec.child_by_field_name("alias") or spec.child_by_field_name("name")
                    if named is not None:
                        clause_specs.append((node_text(named), stmt))

        # Hooks — record call site so it can be scoped to its enclosing component
        if "hook.name" in caps:
            node = caps["hook.name"][0]
            hook_sites.append((node.start_byte, node_text(node)))

        # Props destructuring
        if "prop.name" in caps:
            for pn in caps["prop.name"]:
                p = node_text(pn)
                if p not in props:
                    props.append(p)

        # Imports (for imported component tracking)
        if "import.path" in caps:
            node = caps["import.path"][0]
            path = node_text(node).strip("'\"")
            if not path.startswith("."):
                import_sites.append((node.start_byte, path))

    for name, stmt in clause_specs:
        _record(name, stmt)

    def _owner(pos: int) -> str | None:
        """Innermost component whose byte range encloses ``pos`` (None if file-level)."""
        best: str | None = None
        best_start = -1
        for cname, rng in comp_ranges.items():
            if rng is None:
                continue
            start, end = rng
            if start <= pos <= end and start > best_start:
                best, best_start = cname, start
        return best

    # A hook/import enclosed by a component belongs only to that component; one that
    # nothing encloses (e.g. a top-level import) is genuinely file-level and shared.
    for pos, hname in hook_sites:
        owner = _owner(pos)
        targets = [components[owner]] if owner else list(components.values())
        for c in targets:
            if hname not in c.hooks:
                c.hooks.append(hname)

    for pos, ipath in import_sites:
        owner = _owner(pos)
        targets = [components[owner]] if owner else list(components.values())
        for c in targets:
            if ipath not in c.imports:
                c.imports.append(ipath)

    # Props are assigned only to the first component (typically the main one).
    comp_list = list(components.values())
    if comp_list:
        comp_list[0].props = props[:]

    return comp_list


def _interpret_vue(
    file_path: str, matches: list, framework: str,
) -> list[ComponentInfo]:
    """Vue: defineComponent / export default class + composables + defineProps."""
    name = ""
    line = 1
    props: list[str] = []
    composables: list[str] = []
    imports: list[str] = []

    for _idx, caps in matches:
        # defineComponent({ name: "..." })
        if "component.name" in caps:
            name = node_text(caps["component.name"][0])
            if "component.define" in caps:
                line = caps["component.define"][0].start_point[0] + 1

        # export default class ComponentName
        if "component.class_name" in caps:
            name = node_text(caps["component.class_name"][0])
            if "component.class" in caps:
                line = caps["component.class"][0].start_point[0] + 1

        # defineComponent without name (anonymous)
        if "component.define_anon" in caps and not name:
            name = Path(file_path).stem

        # defineProps({ key: ... })
        if "prop.name" in caps:
            for pn in caps["prop.name"]:
                p = node_text(pn)
                if p not in props:
                    props.append(p)

        # Composable usage (useX)
        if "composable.name" in caps:
            c = node_text(caps["composable.name"][0])
            if c not in composables:
                composables.append(c)

        # Imports
        if "import.path" in caps:
            path = node_text(caps["import.path"][0]).strip("'\"")
            if path not in imports:
                imports.append(path)

    if not name:
        name = Path(file_path).stem

    return [ComponentInfo(
        name=name,
        source_file=file_path,
        line=line,
        framework=framework,
        props=props,
        hooks=composables,
        imports=imports,
    )]


def _interpret_svelte(
    file_path: str, matches: list, framework: str,
) -> list[ComponentInfo]:
    """Svelte: SFC with export let props, runes, stores."""
    name = Path(file_path).stem
    props: list[str] = []
    hooks: list[str] = []
    imports: list[str] = []

    for _idx, caps in matches:
        # export let prop (Svelte 4)
        if "prop.name" in caps:
            for pn in caps["prop.name"]:
                p = node_text(pn)
                if p not in props:
                    props.append(p)

        # Svelte 5 runes ($state, $derived, etc.)
        if "rune.name" in caps:
            r = node_text(caps["rune.name"][0])
            if r not in hooks:
                hooks.append(r)

        # Stores (writable, readable)
        if "store.name" in caps:
            s = node_text(caps["store.name"][0])
            if s not in hooks:
                hooks.append(s)

        # Component name override
        if "component.name" in caps:
            name = node_text(caps["component.name"][0])

        # Imports
        if "import.path" in caps:
            path = node_text(caps["import.path"][0]).strip("'\"")
            if path not in imports:
                imports.append(path)

    return [ComponentInfo(
        name=name,
        source_file=file_path,
        line=1,
        framework=framework,
        props=props,
        hooks=hooks,
        imports=imports,
    )]


def _interpret_angular(
    file_path: str, matches: list, framework: str,
) -> list[ComponentInfo]:
    """Angular: @Component({ selector, templateUrl }) class."""
    components: list[ComponentInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "component.class" in caps and "component.class_name" in caps:
            name = node_text(caps["component.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            selector = node_text(caps["component.selector"][0]) if "component.selector" in caps else ""
            node = caps["component.class"][0]
            comp = ComponentInfo(
                name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="angular",
            )
            if selector:
                comp.hooks.append(f"selector:{selector}")
            components.append(comp)

        # templateUrl capture (separate pattern)
        if "component.template_url_decorator" in caps and "component.template_url" in caps:
            template_url = node_text(caps["component.template_url"][0])
            # Assign to last component in list
            if components:
                components[-1].imports.append(template_url)

    return components
