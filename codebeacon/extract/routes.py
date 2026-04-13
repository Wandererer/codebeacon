"""Route extraction for all 17 supported frameworks.

Public API:
    extract_routes(file_path, framework, project_path="") -> list[RouteInfo]

Design:
  - Run the framework's .scm query once per file
  - Iterate matches, build lookup dicts by start_byte, correlate
  - SFC dispatch (.vue/.svelte) handled at the top before parse_file
  - Convention-based routes (Next.js/Nuxt/SvelteKit file-system) augment AST results
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from codebeacon.common.types import RouteInfo
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
    "spring-boot": "spring_boot",
    "express":     "express",
    "koa":         "express",
    "fastify":     "express",
    "nestjs":      "nestjs",
    "nextjs":      "react",
    "react":       "react",
    "fastapi":     "fastapi",
    "django":      "django",
    "flask":       "flask",
    "gin":         "gin",
    "echo":        "gin",
    "fiber":       "gin",
    "go":          "gin",
    "rails":       "rails",
    "laravel":     "laravel",
    "aspnet":      "aspnet",
    "actix":       "actix",
    "axum":        "actix",
    "rust":        "actix",
    "vapor":       "vapor",
    "ktor":        "ktor",
    "vue":         "vue",
    "nuxt":        "vue",
    "sveltekit":   "svelte",
    "angular":     "angular",
}

# HTTP method name normalisation
_HTTP_METHODS: dict[str, str] = {
    # lowercase REST
    "get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH",
    "delete": "DELETE", "del": "DELETE", "options": "OPTIONS",
    "head": "HEAD", "any": "ANY", "all": "ANY", "use": "ANY",
    # Spring Boot annotations
    "GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT",
    "PatchMapping": "PATCH", "DeleteMapping": "DELETE", "RequestMapping": "ANY",
    # NestJS decorators
    "Get": "GET", "Post": "POST", "Put": "PUT", "Patch": "PATCH",
    "Delete": "DELETE", "Options": "OPTIONS", "Head": "HEAD", "All": "ANY",
    # ASP.NET attributes
    "HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT",
    "HttpPatch": "PATCH", "HttpDelete": "DELETE",
    "HttpOptions": "OPTIONS", "HttpHead": "HEAD",
    # ASP.NET Minimal API
    "MapGet": "GET", "MapPost": "POST", "MapPut": "PUT",
    "MapPatch": "PATCH", "MapDelete": "DELETE",
}

# Rails / Laravel resource → 7 REST routes
_RESOURCE_ACTIONS: list[tuple[str, str, str]] = [
    ("GET",    "{name}",            "index"),
    ("GET",    "{name}/new",        "new"),
    ("POST",   "{name}",            "create"),
    ("GET",    "{name}/{id}",       "show"),
    ("GET",    "{name}/{id}/edit",  "edit"),
    ("PUT",    "{name}/{id}",       "update"),
    ("DELETE", "{name}/{id}",       "destroy"),
]


# ── Public function ───────────────────────────────────────────────────────────

def extract_routes(
    file_path: str,
    framework: str,
    project_path: str = "",
) -> list[RouteInfo]:
    """Extract routes from *file_path* for the given *framework*.

    For file-system routing frameworks (Next.js, Nuxt, SvelteKit), also pass
    *project_path* to compute convention-based routes from the file path.
    """
    fw = framework.lower()

    # 1. File-system (convention) routes — always computed first
    convention = _convention_routes(file_path, fw, project_path)

    query_name = _FW_TO_QUERY.get(fw)
    if not query_name:
        return convention

    query_src = load_query_file(query_name)
    if not query_src:
        return convention

    # 2. SFC dispatch (.vue / .svelte) — extract <script> before parsing
    ext = Path(file_path).suffix.lower()
    if ext in (".vue", ".svelte"):
        sfc = extract_sfc_sections(file_path)
        if sfc is None:
            return convention
        parsed = parse_sfc_script(sfc)
    else:
        parsed = parse_file(file_path)

    if parsed is None:
        return convention
    root, lang = parsed

    # Skip queries where the file's grammar is incompatible with the query.
    # e.g. Rust files in a sveltekit project, JS files for TypeScript-only queries.
    from codebeacon.extract.base import is_grammar_allowed
    if not is_grammar_allowed(query_name, lang):
        return convention

    # 3. Run query once, then dispatch to per-framework interpreter
    try:
        matches = run_query(lang, query_src, root)
    except Exception:
        return convention

    _interpreters = {
        "spring_boot": _interpret_spring_boot,
        "express":     _interpret_express,
        "nestjs":      _interpret_nestjs,
        "fastapi":     _interpret_fastapi,
        "django":      _interpret_django,
        "flask":       _interpret_flask,
        "gin":         _interpret_gin,
        "rails":       _interpret_rails,
        "laravel":     _interpret_laravel,
        "aspnet":      _interpret_aspnet,
        "actix":       _interpret_actix,
        "vapor":       _interpret_vapor,
        "ktor":        _interpret_ktor,
        "react":       _interpret_react,
        "vue":         _interpret_vue,
        "svelte":      _interpret_svelte,
        "angular":     _interpret_angular,
    }

    interpreter = _interpreters.get(query_name)
    if interpreter is None:
        return convention

    try:
        ast_routes = interpreter(file_path, matches, fw)
    except Exception:
        ast_routes = []

    return ast_routes + convention


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    """Strip surrounding quotes and whitespace from a string literal node text."""
    s = s.strip()
    if len(s) >= 2 and s[0] in ('"', "'", "`") and s[-1] == s[0]:
        return s[1:-1]
    return s


def _join(*parts: str) -> str:
    """Join URL path segments, always starting with '/'."""
    segments: list[str] = []
    for p in parts:
        p = _clean(p).strip("/")
        if p:
            segments.append(p)
    return "/" + "/".join(segments) if segments else "/"


def _norm_method(name: str) -> str:
    return _HTTP_METHODS.get(name, name.upper() if name else "ANY")


def _expand_resource(
    resource: str,
    prefix: str,
    file_path: str,
    framework: str,
    line: int,
) -> list[RouteInfo]:
    """Expand a `resources :name` or `Route::resource("name")` into 7 REST routes."""
    resource = resource.lstrip(":").strip("'\"")
    # Simple singularization for the id param
    singular = resource[:-1] if resource.endswith("s") else resource
    id_param = f":{singular}_id"
    routes: list[RouteInfo] = []
    for method, path_tpl, action in _RESOURCE_ACTIONS:
        path = path_tpl.replace("{name}", resource).replace("{id}", id_param)
        routes.append(RouteInfo(
            method=method,
            path=_join(prefix, path),
            handler=f"{resource}#{action}",
            source_file=file_path,
            line=line,
            framework=framework,
        ))
    return routes


# ── Convention-based file-system routes ──────────────────────────────────────

def _convention_routes(file_path: str, framework: str, project_path: str) -> list[RouteInfo]:
    if not project_path:
        return []
    try:
        rel = Path(file_path).relative_to(Path(project_path))
    except ValueError:
        return []

    parts = rel.parts
    route_path: Optional[str] = None

    if framework in ("nextjs", "react"):
        if parts and parts[0] == "pages":
            route_path = _pages_to_route(parts[1:])
        elif len(parts) >= 2 and parts[0] == "app":
            route_path = _app_to_route(parts[1:])
    elif framework == "nuxt":
        if parts and parts[0] == "pages":
            route_path = _pages_to_route(parts[1:])
    elif framework == "sveltekit":
        if len(parts) >= 3 and parts[0] == "src" and parts[1] == "routes":
            route_path = _sveltekit_to_route(parts[2:])

    if route_path is None:
        return []

    stem = Path(parts[-1]).stem.lstrip("+") if parts else "index"
    return [RouteInfo(
        method="GET",
        path=route_path,
        handler=stem,
        source_file=file_path,
        line=1,
        framework=framework,
        tags=["file-system-route"],
    )]


def _seg(part: str) -> str:
    """Convert a file path segment to a URL segment (handle [param], [...catch])."""
    name = Path(part).stem  # strip extension
    if re.match(r"^\(.*\)$", name):
        return ""  # Next.js route group
    name = re.sub(r"\[\.\.\.(\w+)\]", r"*", name)
    name = re.sub(r"\[(\w+)\]", r":\1", name)
    return name if name not in ("index",) else ""


def _pages_to_route(parts) -> str:
    segments = [s for p in parts for s in [_seg(p)] if s]
    return "/" + "/".join(segments) if segments else "/"


def _app_to_route(parts) -> Optional[str]:
    if not parts:
        return "/"
    stem_last = Path(parts[-1]).stem
    if stem_last not in ("page", "route", "layout"):
        return None
    segments = [s for p in parts[:-1] for s in [_seg(p)] if s]
    return "/" + "/".join(segments) if segments else "/"


def _sveltekit_to_route(parts) -> Optional[str]:
    if not parts:
        return "/"
    stem_last = Path(parts[-1]).stem
    if not stem_last.startswith("+"):
        return None
    segments = [s for p in parts[:-1] for s in [_seg(p)] if s]
    return "/" + "/".join(segments) if segments else "/"


# ── Per-framework interpreters ────────────────────────────────────────────────

def _interpret_spring_boot(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Spring Boot: @RestController class prefix + @GetMapping/@PostMapping method paths.

    Two-pass: first collect ALL class info + prefixes (match ordering may vary),
    then process handler methods.
    """
    # Pass 1 – controller classes and class-level prefixes
    classes: dict[int, dict] = {}      # class start_byte → {name, prefix, start, end}
    class_prefixes: dict[int, str] = {}  # class_mapping start_byte → prefix

    for _idx, caps in matches:
        if "route.controller_class" in caps:
            cls = caps["route.controller_class"][0]
            name = node_text(caps["route.class_name"][0]) if "route.class_name" in caps else ""
            classes.setdefault(cls.start_byte, {
                "name": name, "prefix": "",
                "start": cls.start_byte, "end": cls.end_byte,
            })

        if "route.class_mapping" in caps and "route.class_path" in caps:
            mapping = caps["route.class_mapping"][0]
            prefix = _clean(node_text(caps["route.class_path"][0]))
            class_prefixes[mapping.start_byte] = prefix

    # Apply prefixes to classes (match by same start_byte or containment)
    for mapping_start, prefix in class_prefixes.items():
        for c in classes.values():
            if c["start"] == mapping_start or (c["start"] <= mapping_start <= c["end"]):
                c["prefix"] = prefix
                break

    # Pass 2 – handler methods
    methods: dict[int, dict] = {}  # method start_byte → {ann, handler, path, line, end}

    for _idx, caps in matches:
        if "route.handler_method" in caps:
            m = caps["route.handler_method"][0]
            key = m.start_byte
            ann = node_text(caps["route.method_annotation"][0]) if "route.method_annotation" in caps else ""
            handler = node_text(caps["route.method_name"][0]) if "route.method_name" in caps else ""
            if key not in methods:
                methods[key] = {"ann": ann, "handler": handler, "path": "", "line": m.start_point[0] + 1, "end": m.end_byte}
            else:
                if ann and not methods[key]["ann"]:
                    methods[key]["ann"] = ann

        if "route.method_with_path" in caps:
            m = caps["route.method_with_path"][0]
            key = m.start_byte
            path = _clean(node_text(caps["route.path_value"][0])) if "route.path_value" in caps else ""
            handler = node_text(caps["route.method_name_with_path"][0]) if "route.method_name_with_path" in caps else ""
            if key not in methods:
                methods[key] = {"ann": "", "handler": handler, "path": path, "line": m.start_point[0] + 1, "end": m.end_byte}
            else:
                methods[key]["path"] = path
                if handler and not methods[key]["handler"]:
                    methods[key]["handler"] = handler

    # Combine
    routes: list[RouteInfo] = []
    for start, minfo in methods.items():
        class_prefix = ""
        class_name = ""
        for c in classes.values():
            if c["start"] <= start <= c["end"]:
                class_prefix = c["prefix"]
                class_name = c["name"]
                break
        routes.append(RouteInfo(
            method=_norm_method(minfo["ann"]),
            path=_join(class_prefix, minfo["path"]),
            handler=f"{class_name}.{minfo['handler']}",
            source_file=file_path,
            line=minfo["line"],
            framework="spring-boot",
        ))
    return routes


def _interpret_express(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Express / Koa / Fastify route extraction."""
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if "route.path" not in caps:
            continue

        method_str = node_text(caps["route.method"][0]).lower() if "route.method" in caps else "get"
        if method_str == "use":
            continue  # prefix mounts, not routes

        path = _clean(node_text(caps["route.path"][0]))
        obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
        line = caps["route.path"][0].start_point[0] + 1

        routes.append(RouteInfo(
            method=_norm_method(method_str),
            path=path if path.startswith("/") else "/" + path,
            handler=obj,
            source_file=file_path,
            line=line,
            framework=framework,
        ))
    return routes


def _interpret_nestjs(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """NestJS @Controller prefix + @Get/@Post method paths.

    Class decorators are siblings in export_statement; method decorators are
    siblings in class_body. Use start/end byte ranges to correlate.
    """
    controllers: dict[int, dict] = {}
    handlers: list[dict] = []

    for _idx, caps in matches:
        # Controller classes (with or without prefix)
        for cls_key in ("route.controller_with_prefix", "route.controller_no_prefix",
                        "route.controller_with_prefix_noexport"):
            if cls_key in caps:
                cls = caps[cls_key][0]
                name = node_text(caps["route.class_name"][0]) if "route.class_name" in caps else ""
                prefix = _clean(node_text(caps["route.controller_prefix"][0])) if "route.controller_prefix" in caps else ""
                controllers.setdefault(cls.start_byte, {
                    "name": name, "prefix": prefix,
                    "start": cls.start_byte, "end": cls.end_byte,
                })
                break

        # Handler methods (with path)
        if "route.handler" in caps and "route.method_decorator" in caps:
            m = caps["route.handler"][0]  # class_body node
            dec = node_text(caps["route.method_decorator"][0])
            path = _clean(node_text(caps["route.path_value"][0])) if "route.path_value" in caps else ""
            name = node_text(caps["route.method_name"][0]) if "route.method_name" in caps else ""
            handlers.append({
                "start": m.start_byte, "end": m.end_byte,
                "dec": dec, "path": path, "name": name,
                "line": caps["route.method_name"][0].start_point[0] + 1 if "route.method_name" in caps else m.start_point[0] + 1,
            })

        # Handler methods (without path)
        if "route.handler_no_path" in caps and "route.method_decorator" in caps:
            m = caps["route.handler_no_path"][0]
            dec = node_text(caps["route.method_decorator"][0])
            name = node_text(caps["route.method_name"][0]) if "route.method_name" in caps else ""
            handlers.append({
                "start": m.start_byte, "end": m.end_byte,
                "dec": dec, "path": "", "name": name,
                "line": caps["route.method_name"][0].start_point[0] + 1 if "route.method_name" in caps else m.start_point[0] + 1,
            })

    # Deduplicate handlers by method name + line
    seen: set[tuple[str, int]] = set()
    routes: list[RouteInfo] = []
    for hinfo in handlers:
        key = (hinfo["name"], hinfo["line"])
        if key in seen:
            continue
        seen.add(key)
        # Find enclosing controller by byte range
        class_prefix = ""
        class_name = ""
        for c in controllers.values():
            if c["start"] <= hinfo["start"] <= c["end"]:
                class_prefix = c["prefix"]
                class_name = c["name"]
                break
        routes.append(RouteInfo(
            method=_norm_method(hinfo["dec"]),
            path=_join(class_prefix, hinfo["path"]),
            handler=f"{class_name}.{hinfo['name']}",
            source_file=file_path,
            line=hinfo["line"],
            framework="nestjs",
        ))
    return routes


def _interpret_fastapi(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """FastAPI @app.get/@router.post with APIRouter prefix tracking."""
    router_prefixes: dict[str, str] = {}  # router_var_name → prefix
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        # APIRouter(prefix="/api/v1")
        if "route.router_decl" in caps and "route.prefix" in caps:
            name = node_text(caps["route.router_name"][0]) if "route.router_name" in caps else ""
            prefix = _clean(node_text(caps["route.prefix"][0]))
            router_prefixes[name] = prefix

        # app.include_router(router, prefix="...")
        if "router.include" in caps and "router.include_router" in caps:
            name = node_text(caps["router.include_router"][0])
            if "router.include_prefix" in caps:
                router_prefixes[name] = _clean(node_text(caps["router.include_prefix"][0]))

        # @app.get("/path") or @router.post("/path")
        if "route.handler" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            method = node_text(caps["route.method"][0]) if "route.method" in caps else "get"
            obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
            handler = node_text(caps["route.func_name"][0]) if "route.func_name" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            prefix = router_prefixes.get(obj, "")
            routes.append(RouteInfo(
                method=method.upper(),
                path=_join(prefix, path),
                handler=handler,
                source_file=file_path,
                line=line,
                framework="fastapi",
            ))
    return routes


def _interpret_django(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Django urlpatterns path() extraction."""
    routes: list[RouteInfo] = []
    for _idx, caps in matches:
        if "route.urlpatterns" in caps and "route.path_str" in caps:
            path = _clean(node_text(caps["route.path_str"][0]))
            view = node_text(caps["route.view_name"][0]) if "route.view_name" in caps else ""
            line = caps["route.path_str"][0].start_point[0] + 1
            routes.append(RouteInfo(
                method="ANY",
                path=path if path.startswith("/") else "/" + path,
                handler=view,
                source_file=file_path,
                line=line,
                framework="django",
            ))
    return routes


def _interpret_flask(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Flask @app.route / Blueprint with url_prefix tracking."""
    bp_prefixes: dict[str, str] = {}      # blueprint var name → url_prefix
    register_prefixes: dict[str, str] = {} # bp var name → registered prefix
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if "blueprint.decl" in caps and "blueprint.name" in caps:
            name = node_text(caps["blueprint.name"][0])
            prefix = _clean(node_text(caps["blueprint.url_prefix"][0])) if "blueprint.url_prefix" in caps else ""
            bp_prefixes[name] = prefix

        if "app.register" in caps and "app.register_bp" in caps:
            name = node_text(caps["app.register_bp"][0])
            prefix = _clean(node_text(caps["app.register_prefix"][0])) if "app.register_prefix" in caps else ""
            register_prefixes[name] = prefix

        if "route.handler" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
            handler = node_text(caps["route.func_name"][0]) if "route.func_name" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            prefix = register_prefixes.get(obj, bp_prefixes.get(obj, ""))
            full_path = _join(prefix, path)

            method_nodes = caps.get("route.methods", [])
            if method_nodes:
                for mn in method_nodes:
                    routes.append(RouteInfo(
                        method=_clean(node_text(mn)).upper(),
                        path=full_path,
                        handler=handler,
                        source_file=file_path,
                        line=line,
                        framework="flask",
                    ))
            else:
                routes.append(RouteInfo(
                    method="GET",
                    path=full_path,
                    handler=handler,
                    source_file=file_path,
                    line=line,
                    framework="flask",
                ))
    return routes


def _interpret_gin(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Gin / Echo / Fiber route extraction with r.Group() prefix."""
    group_prefixes: dict[str, str] = {}
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if "route.group_decl" in caps and "route.group_prefix" in caps:
            name = node_text(caps["route.group_name"][0]) if "route.group_name" in caps else ""
            prefix = _clean(node_text(caps["route.group_prefix"][0]))
            group_prefixes[name] = prefix

    for _idx, caps in matches:
        if ("route.call" in caps or "route.call_lower" in caps) and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            method = node_text(caps["route.method"][0]) if "route.method" in caps else "GET"
            obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
            handler = node_text(caps["route.handler_name"][0]) if "route.handler_name" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            prefix = group_prefixes.get(obj, "")
            routes.append(RouteInfo(
                method=_norm_method(method.lower()),
                path=_join(prefix, path),
                handler=handler,
                source_file=file_path,
                line=line,
                framework=framework,
            ))
    return routes


def _interpret_rails(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Rails routes.rb: resources DSL + explicit get/post/put/delete."""
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if ("route.resources" in caps or "route.resources_filtered" in caps) and "route.resources_name" in caps:
            resource = node_text(caps["route.resources_name"][0])
            line = caps["route.resources_name"][0].start_point[0] + 1
            routes.extend(_expand_resource(resource, "", file_path, "rails", line))

        elif "route.explicit" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            method = node_text(caps["route.http_method"][0]) if "route.http_method" in caps else "get"
            to = _clean(node_text(caps["route.to"][0])) if "route.to" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            if method == "root":
                path = "/"
                method = "get"
            routes.append(RouteInfo(
                method=method.upper(),
                path=path if path.startswith("/") else "/" + path,
                handler=to,
                source_file=file_path,
                line=line,
                framework="rails",
            ))
    return routes


def _interpret_laravel(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Laravel Route:: static calls and Route::resource expansion."""
    prefix_stack: list[str] = []
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if "route.prefix_group" in caps and "route.prefix" in caps:
            prefix_stack.append(_clean(node_text(caps["route.prefix"][0])))

        elif "route.call" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            method = node_text(caps["route.method"][0]) if "route.method" in caps else "get"
            controller = node_text(caps["route.controller"][0]) if "route.controller" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            prefix = "/".join(prefix_stack) if prefix_stack else ""
            routes.append(RouteInfo(
                method=method.upper(),
                path=_join(prefix, path),
                handler=controller,
                source_file=file_path,
                line=line,
                framework="laravel",
            ))

        elif "route.resource" in caps and "route.resource_name" in caps:
            resource = _clean(node_text(caps["route.resource_name"][0]))
            line = caps["route.resource_name"][0].start_point[0] + 1
            prefix = "/".join(prefix_stack) if prefix_stack else ""
            routes.extend(_expand_resource(resource, prefix, file_path, "laravel", line))

    return routes


def _interpret_aspnet(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """ASP.NET Core attribute routing + Minimal API, with [controller] token replacement."""
    controllers: dict[int, dict] = {}
    routes: list[RouteInfo] = []

    # First pass: collect controller classes
    for _idx, caps in matches:
        if "route.controller_class" in caps:
            cls = caps["route.controller_class"][0]
            name = node_text(caps["route.class_name"][0]) if "route.class_name" in caps else ""
            template = node_text(caps["route.class_attr"][0]) if "route.class_attr" in caps else ""
            controllers.setdefault(cls.start_byte, {
                "name": name, "template": template,
                "start": cls.start_byte, "end": cls.end_byte,
            })
        if "route.controller_bare" in caps:
            cls = caps["route.controller_bare"][0]
            name = node_text(caps["route.class_name"][0]) if "route.class_name" in caps else ""
            controllers.setdefault(cls.start_byte, {
                "name": name, "template": "api/[controller]",
                "start": cls.start_byte, "end": cls.end_byte,
            })

    # Second pass: collect methods + minimal API
    for _idx, caps in matches:
        if "route.method_with_path" in caps or "route.method_bare" in caps:
            key = "route.method_with_path" if "route.method_with_path" in caps else "route.method_bare"
            m = caps[key][0]
            attr = node_text(caps["route.method_attr"][0]) if "route.method_attr" in caps else ""
            method_path = node_text(caps["route.method_path"][0]) if "route.method_path" in caps else ""
            method_name = node_text(caps["route.method_name"][0]) if "route.method_name" in caps else ""
            line = m.start_point[0] + 1

            class_template = ""
            class_name = ""
            for c in controllers.values():
                if c["start"] <= m.start_byte <= c["end"]:
                    class_template = c["template"]
                    class_name = c["name"]
                    break

            ctrl_short = re.sub(r"Controller$", "", class_name, flags=re.IGNORECASE)
            template = class_template.replace("[controller]", ctrl_short.lower()).replace("[Controller]", ctrl_short.lower())

            routes.append(RouteInfo(
                method=_norm_method(attr),
                path=_join(template, method_path),
                handler=f"{class_name}.{method_name}",
                source_file=file_path,
                line=line,
                framework="aspnet",
            ))

        if "route.minimal_api" in caps and "route.map_path" in caps:
            path = node_text(caps["route.map_path"][0])
            method = node_text(caps["route.map_method"][0]) if "route.map_method" in caps else "MapGet"
            line = caps["route.map_path"][0].start_point[0] + 1
            routes.append(RouteInfo(
                method=_norm_method(method),
                path=path if path.startswith("/") else "/" + path,
                handler="",
                source_file=file_path,
                line=line,
                framework="aspnet",
            ))
    return routes


def _interpret_actix(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Actix proc macros (#[get(...)]) + Axum Router::new().route(...)."""
    routes: list[RouteInfo] = []
    for _idx, caps in matches:
        if "route.actix_handler" in caps and "route.path" in caps:
            method = node_text(caps["route.proc_macro"][0]) if "route.proc_macro" in caps else "get"
            path = node_text(caps["route.path"][0])
            func = node_text(caps["route.func_name"][0]) if "route.func_name" in caps else ""
            line = caps["route.actix_handler"][0].start_point[0] + 1
            routes.append(RouteInfo(
                method=method.upper(),
                path=path if path.startswith("/") else "/" + path,
                handler=func,
                source_file=file_path,
                line=line,
                framework=framework,
            ))

        if "route.axum_route" in caps and "route.axum_path" in caps:
            path = node_text(caps["route.axum_path"][0])
            method = node_text(caps["route.axum_method"][0]) if "route.axum_method" in caps else "get"
            handler = node_text(caps["route.axum_handler"][0]) if "route.axum_handler" in caps else ""
            line = caps["route.axum_route"][0].start_point[0] + 1
            routes.append(RouteInfo(
                method=method.upper(),
                path=path if path.startswith("/") else "/" + path,
                handler=handler,
                source_file=file_path,
                line=line,
                framework=framework,
            ))
    return routes


def _interpret_vapor(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Vapor app.get("users", ":id") with grouped() prefix."""
    grouped_prefixes: dict[str, str] = {}
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if "route.grouped_decl" in caps and "route.grouped_prefix" in caps:
            name = node_text(caps["route.grouped_name"][0]) if "route.grouped_name" in caps else ""
            prefix = node_text(caps["route.grouped_prefix"][0])
            grouped_prefixes[name] = prefix

    for _idx, caps in matches:
        if "route.call" in caps and "route.method" in caps:
            method = node_text(caps["route.method"][0])
            if method == "grouped":
                continue
            obj = node_text(caps["route.object"][0]) if "route.object" in caps else "app"
            segments = [node_text(n) for n in caps.get("route.path_segment", [])]
            path = _join(*segments) if segments else "/"
            line = caps["route.call"][0].start_point[0] + 1
            prefix = grouped_prefixes.get(obj, "")
            routes.append(RouteInfo(
                method=method.upper(),
                path=_join(prefix, path),
                handler="",
                source_file=file_path,
                line=line,
                framework="vapor",
            ))
    return routes


def _interpret_ktor(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Ktor nested routing DSL: route("/prefix") { get("/path") { } }."""
    # Collect prefix scopes by line range
    prefix_scopes: list[tuple[int, int, str]] = []
    routes: list[RouteInfo] = []

    for _idx, caps in matches:
        if "route.prefix_scope" in caps and "route.route_prefix" in caps:
            scope = caps["route.prefix_scope"][0]
            prefix = node_text(caps["route.route_prefix"][0])
            prefix_scopes.append((scope.start_point[0], scope.end_point[0], prefix))

    for _idx, caps in matches:
        call_key = None
        if "route.method_call" in caps:
            call_key = "route.method_call"
        elif "route.method_call_simple" in caps:
            call_key = "route.method_call_simple"
        if call_key and "route.path" in caps and "route.method" in caps:
            call_node = caps[call_key][0]
            method = node_text(caps["route.method"][0])
            path = node_text(caps["route.path"][0])
            line = call_node.start_point[0] + 1
            # Find innermost applicable prefix scope
            prefix = ""
            for start, end, pfx in prefix_scopes:
                if start <= call_node.start_point[0] <= end:
                    prefix = pfx
            routes.append(RouteInfo(
                method=method.upper(),
                path=_join(prefix, path),
                handler="",
                source_file=file_path,
                line=line,
                framework="ktor",
            ))
    return routes


def _interpret_react(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """React/Next.js — AST routes (convention routes handled in _convention_routes)."""
    # The react.scm doesn't capture React Router <Route path=...> elements
    # Convention routes (file-system) are sufficient for Next.js
    return []


def _interpret_vue(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Vue Router routes array + Nuxt convention (handled in _convention_routes)."""
    routes: list[RouteInfo] = []
    seen: set[str] = set()
    for _idx, caps in matches:
        if "route.path" in caps:
            path = node_text(caps["route.path"][0])
            if not path.startswith("/"):
                path = "/" + path
            if path in seen:
                continue
            seen.add(path)
            component = node_text(caps["route.component"][0]) if "route.component" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            routes.append(RouteInfo(
                method="GET",
                path=path,
                handler=component,
                source_file=file_path,
                line=line,
                framework=framework,
            ))
    return routes


def _interpret_svelte(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """SvelteKit — convention routes handled in _convention_routes."""
    return []


def _interpret_angular(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Angular Routes array: { path: "users", component: UserListComponent }."""
    routes: list[RouteInfo] = []
    seen: set[str] = set()
    for _idx, caps in matches:
        if "route.routes" in caps and "route.path" in caps:
            path = node_text(caps["route.path"][0])
            if not path.startswith("/"):
                path = "/" + path
            if path in seen:
                continue
            seen.add(path)
            component = node_text(caps["route.component"][0]) if "route.component" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            routes.append(RouteInfo(
                method="GET",
                path=path,
                handler=component,
                source_file=file_path,
                line=line,
                framework="angular",
            ))
    return routes
