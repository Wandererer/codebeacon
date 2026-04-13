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
)


# ── Framework → query file stem ───────────────────────────────────────────────

_FW_TO_QUERY: dict[str, str] = {
    "react":     "react",
    "nextjs":    "react",
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

    try:
        matches = run_query(lang, query_src, root)
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
        for comp in components:
            comp.is_page = True


# ── Per-framework interpreters ────────────────────────────────────────────────

def _interpret_react(
    file_path: str, matches: list, framework: str,
) -> list[ComponentInfo]:
    """React/Next.js: exported uppercase functions/arrows + hooks + props."""
    components: dict[str, ComponentInfo] = {}  # name → ComponentInfo
    hooks: list[str] = []
    props: list[str] = []
    imports: list[str] = []

    for _idx, caps in matches:
        # Exported function component
        for cap_key in ("component.func_name", "component.arrow_name", "component.memo_name"):
            if cap_key in caps:
                name = node_text(caps[cap_key][0])
                if name and name not in components:
                    # Determine line from the parent export/declaration
                    parent_key = None
                    for k in ("component.export_func", "component.export_func_upper",
                              "component.export_default_func", "component.export_arrow",
                              "component.local_arrow", "component.hoc"):
                        if k in caps:
                            parent_key = k
                            break
                    line = caps[parent_key][0].start_point[0] + 1 if parent_key else 1
                    components[name] = ComponentInfo(
                        name=name,
                        source_file=file_path,
                        line=line,
                        framework=framework,
                    )

        # Hooks
        if "hook.name" in caps:
            hook_name = node_text(caps["hook.name"][0])
            if hook_name not in hooks:
                hooks.append(hook_name)

        # Props destructuring
        if "prop.name" in caps:
            for pn in caps["prop.name"]:
                p = node_text(pn)
                if p not in props:
                    props.append(p)

        # Imports (for imported component tracking)
        if "import.path" in caps:
            path = node_text(caps["import.path"][0]).strip("'\"")
            if path not in imports and not path.startswith("."):
                imports.append(path)

    # Assign file-level hooks/imports to all components.
    # Props are assigned only to the first component (typically the main one).
    comp_list = list(components.values())
    for i, comp in enumerate(comp_list):
        comp.hooks = hooks[:]
        comp.imports = imports[:]
        if i == 0:
            comp.props = props[:]

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
