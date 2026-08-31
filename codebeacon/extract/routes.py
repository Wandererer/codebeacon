"""Route extraction for all 24 supported frameworks.

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
    GrammarQueryError,
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
    "tornado":     "flask",
    "aiohttp":     "flask",
    "python":      "fastapi",
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
    "tauri":       "tauri",
    "rocket":      "actix",
    "warp":        "actix",
    "vapor":       "vapor",
    "ktor":        "ktor",
    "vue":         "vue",
    "nuxt":        "vue",
    "node":        "express",
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
    except GrammarQueryError:
        raise  # grammar drift on a supported grammar → surfaced as ExtractionFailure
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
        "tauri":       _interpret_tauri,
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


# ── Mount graph resolution (FastAPI / Express / Flask) ───────────────────────
#
# All three frameworks let a router/blueprint be mounted into ANOTHER
# router/blueprint, and let the same router be mounted more than once. A flat
# `name → prefix` dict therefore lost two things at once: the outer prefixes of
# a cascade (`app.include_router(mid, "/root")` above
# `mid.include_router(inner, "/x")`), and every mount but the last for a router
# published at two versions. Both are silent — the wrong path is written to
# wiki/routes.md with no warning.
#
# The resolver below walks the mount graph instead, returning the LIST of
# effective prefixes a router serves under. Composition differs per framework
# and was settled by running the real servers:
#   FastAPI  compose: include_prefix + the router's own APIRouter(prefix=)
#   Express  compose: mount path only (express.Router() carries no own prefix)
#   Flask    OVERRIDE: register_blueprint(url_prefix=) REPLACES the
#            blueprint's own url_prefix; absent, the blueprint's own applies.
# Cross-FILE mounts are out of scope — resolving them needs (module, varname)
# router identity, which the extractor does not have.

_MAX_MOUNT_DEPTH = 16        # cycle/pathological-nesting guard
_MAX_EFFECTIVE_PREFIXES = 32  # a diamond of mounts is multiplicative


def _tail_name(text: str) -> str:
    """Last dotted segment of a (possibly attribute) expression's text.

    ``consumer.consumer_router`` → ``consumer_router``. Routers are keyed on
    this so a router reached through its module matches the same router
    reached by a bare local name.
    """
    return text.rsplit(".", 1)[-1].strip()


def _resolve_alias(name: str, aliases: dict[str, str]) -> str:
    """Follow an alias chain to its final target, with a cycle guard."""
    seen: set[str] = set()
    while name in aliases and name not in seen:
        seen.add(name)
        name = aliases[name]
    return name


def _effective_prefixes(
    name: str,
    own: dict[str, str],
    parents: dict[str, list[tuple[str, Optional[str]]]],
    compose_own: bool,
    _seen: frozenset = frozenset(),
) -> list[str]:
    """Every URL prefix *name* is served under, outermost mount resolved.

    *own* maps a router to the prefix it declares itself; *parents* maps a
    router to the ``(mounting_router, mount_prefix)`` pairs that mount it, where
    a mount_prefix of ``None`` means "no prefix was given at mount time".
    *compose_own* selects composition (FastAPI/Express) over override (Flask).
    An unmounted router resolves to its own prefix alone.
    """
    own_prefix = own.get(name, "")
    if name not in parents or name in _seen or len(_seen) >= _MAX_MOUNT_DEPTH:
        return [own_prefix]

    out: list[str] = []
    for parent, mount_prefix in parents[name]:
        if compose_own:
            local = _join(mount_prefix or "", own_prefix)
        else:
            local = own_prefix if mount_prefix is None else mount_prefix
        for up in _effective_prefixes(parent, own, parents, compose_own, _seen | {name}):
            joined = _join(up, local)
            if joined not in out:
                out.append(joined)
            if len(out) >= _MAX_EFFECTIVE_PREFIXES:
                return out
    return out or [own_prefix]


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
    # Strip only real code extensions. Path(part).stem mis-parses the dots inside
    # a catch-all directory like "[...all]" as an extension (stem → "[.."), so the
    # catch-all regex below never fired.
    name = re.sub(r"\.(mjs|cjs|mts|cts|tsx?|jsx?|vue|svelte)$", "", part)
    if re.match(r"^\(.*\)$", name):
        return ""  # Next.js route group
    if name.startswith("@"):
        return ""  # Next.js parallel-route slot (@modal) — never part of the URL
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

        # Pre-4.3 idiom: @RequestMapping(method = RequestMethod.X) — explicit verb
        if "route.method_with_verb" in caps and "route.request_method" in caps:
            m = caps["route.method_with_verb"][0]
            key = m.start_byte
            verb = node_text(caps["route.request_method"][0])
            if key not in methods:
                methods[key] = {"ann": "", "handler": "", "path": "", "line": m.start_point[0] + 1, "end": m.end_byte, "verb": verb}
            else:
                methods[key]["verb"] = verb

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
        method = _norm_method(minfo["ann"])
        # @RequestMapping normalises to "ANY"; a captured method=RequestMethod.X
        # attribute is the declared verb and takes precedence.
        if method == "ANY" and minfo.get("verb"):
            method = minfo["verb"].upper()
        routes.append(RouteInfo(
            method=method,
            path=_join(class_prefix, minfo["path"]),
            handler=f"{class_name}.{minfo['handler']}",
            source_file=file_path,
            line=minfo["line"],
            framework="spring-boot",
        ))
    return routes


def _interpret_express(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Express / Koa / Fastify route extraction.

    Handles three shapes:
      - app.METHOD("/path", handler)
      - router.route("/path").get(h).post(h)…  — every verb in the chain
      - app.use("/prefix", router) mount prefixes, applied to that router's routes

    Mounts are resolved transitively and may be repeated: a router mounted into
    a router serves under the whole chain, and a router mounted twice serves
    under both paths (both verified against a running Express server).
    """
    # Pass 1 — the mount graph: app.use("/prefix", router)
    mounts: dict[str, list[tuple[str, Optional[str]]]] = {}
    for _idx, caps in matches:
        if "route.use_mount" in caps and "route.mount_router" in caps:
            router = node_text(caps["route.mount_router"][0])
            parent = node_text(caps["route.mount_parent"][0]) if "route.mount_parent" in caps else ""
            prefix = _clean(node_text(caps["route.use_prefix"][0])) if "route.use_prefix" in caps else ""
            if router:
                mounts.setdefault(router, []).append((parent, prefix))

    def _prefixes(obj: str) -> list[str]:
        # express.Router() carries no prefix of its own, so composition is
        # purely the chain of mount paths.
        return _effective_prefixes(obj, {}, mounts, compose_own=True)

    # Chained-route anchors: identifier.route("/path") with byte range for verb correlation
    anchors: list[tuple[int, int, str, str]] = []  # (start, end, path, object)
    for _idx, caps in matches:
        if "route.chain_anchor" in caps and "route.chain_path" in caps:
            node = caps["route.chain_anchor"][0]
            anchors.append((
                node.start_byte, node.end_byte,
                _clean(node_text(caps["route.chain_path"][0])),
                node_text(caps["route.chain_object"][0]) if "route.chain_object" in caps else "",
            ))

    routes: list[RouteInfo] = []

    # Pass 2 — app.METHOD("/path", handler)
    for _idx, caps in matches:
        if "route.path" not in caps:
            continue

        method_str = node_text(caps["route.method"][0]).lower() if "route.method" in caps else "get"
        if method_str == "use":
            continue  # prefix mounts, not routes

        path = _clean(node_text(caps["route.path"][0]))
        obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
        line = caps["route.path"][0].start_point[0] + 1

        for prefix in _prefixes(obj):
            routes.append(RouteInfo(
                method=_norm_method(method_str),
                path=_join(prefix, path),
                handler=obj,
                source_file=file_path,
                line=line,
                framework=framework,
            ))

    # Pass 3 — chained verbs: correlate each verb to the .route(path) anchor whose
    # byte range it encloses (the anchor is the innermost node of the chain).
    for _idx, caps in matches:
        if "route.chain_verb" not in caps or "route.chain_method" not in caps:
            continue
        vnode = caps["route.chain_verb"][0]
        method_str = node_text(caps["route.chain_method"][0]).lower()
        for astart, aend, apath, aobj in anchors:
            if vnode.start_byte <= astart and aend <= vnode.end_byte:
                for prefix in _prefixes(aobj):
                    routes.append(RouteInfo(
                        method=_norm_method(method_str),
                        path=_join(prefix, apath),
                        handler=aobj,
                        source_file=file_path,
                        line=vnode.start_point[0] + 1,
                        framework=framework,
                    ))
                break

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


def _parse_include_router(call_node) -> Optional[tuple[str, str, str]]:
    """Pull ``(includer, child_router, mount_prefix)`` from an include_router call.

    Done in Python rather than in the query because the shapes multiply:
    the includer may be an identifier or an attribute chain
    (``api.v1.app.include_router``), and the child router may be positional,
    an attribute, or the ``router=`` keyword. Enumerating the cross product in
    ``.scm`` needs one pattern per combination — and every extra pattern is
    another chance for two of them to fire on the same call.

    Returns None when no child router can be identified (e.g. the router is the
    result of a call, which this extractor cannot name).
    """
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return None
    obj = fn.child_by_field_name("object")
    includer = _tail_name(node_text(obj)) if obj is not None else ""

    args = call_node.child_by_field_name("arguments")
    if args is None:
        return None

    child = ""
    prefix = ""
    for arg in args.named_children:
        if arg.type == "keyword_argument":
            key = arg.child_by_field_name("name")
            value = arg.child_by_field_name("value")
            if key is None or value is None:
                continue
            key_name = node_text(key)
            if key_name == "prefix" and value.type == "string":
                prefix = _clean(node_text(value))
            elif key_name == "router" and not child:
                child = _tail_name(node_text(value))
        elif not child and arg.type in ("identifier", "attribute"):
            child = _tail_name(node_text(arg))

    if not child:
        return None
    return includer, child, prefix


def _interpret_fastapi(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """FastAPI @app.get/@router.post with transitive APIRouter mount resolution.

    FastAPI COMPOSES prefixes: ``APIRouter(prefix="/users")`` mounted with
    ``include_router(router, prefix="/api/v1")`` serves ``/api/v1/users/…``
    (verified against a real ``app.openapi()``). The former single prefix map
    let the include write clobber the declaration write — Python forces the
    router to be assigned before it is included, so the loss was deterministic,
    not order-dependent.
    """
    decl_prefix: dict[str, str] = {}                          # router → own prefix
    aliases: dict[str, str] = {}                              # local name → router
    parents: dict[str, list[tuple[str, Optional[str]]]] = {}  # router → mounts
    seen_calls: set[int] = set()                              # dedupe by call node
    routes: list[RouteInfo] = []

    # Pass 1 — the whole mount graph, before any route is emitted. An include
    # normally sits BELOW the handlers it prefixes, so nothing can be resolved
    # in a single interleaved pass.
    for _idx, caps in matches:
        if "route.router_decl" in caps and "route.prefix" in caps:
            name = node_text(caps["route.router_name"][0]) if "route.router_name" in caps else ""
            if name:
                decl_prefix[name] = _clean(node_text(caps["route.prefix"][0]))

        if "route.alias" in caps and "route.alias_name" in caps and "route.alias_target" in caps:
            local = node_text(caps["route.alias_name"][0])
            target = _tail_name(node_text(caps["route.alias_target"][0]))
            if target and local != target:
                aliases.setdefault(local, target)

        if "router.include_call" in caps:
            node = caps["router.include_call"][0]
            if node.start_byte not in seen_calls:
                seen_calls.add(node.start_byte)
                parsed = _parse_include_router(node)
                if parsed is not None:
                    includer, child, prefix = parsed
                    parents.setdefault(child, []).append((includer, prefix))

    # An alias only stands in for a router that has no identity of its own. A
    # name that declares its own prefix, or that is mounted under its own name,
    # is the real router — following an alias past it would discard exactly the
    # information the resolver needs.
    for local in [n for n in aliases if n in decl_prefix or n in parents]:
        del aliases[local]

    # Pass 2 — emit one route per effective mount prefix.
    for _idx, caps in matches:
        if "route.handler" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            method = node_text(caps["route.method"][0]) if "route.method" in caps else "get"
            obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
            handler = node_text(caps["route.func_name"][0]) if "route.func_name" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            router = _resolve_alias(_tail_name(obj), aliases)
            for prefix in _effective_prefixes(router, decl_prefix, parents, compose_own=True):
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
    """Flask @app.route / Blueprint with transitive url_prefix resolution.

    Flask's composition rule is the opposite of FastAPI's and was settled
    against a real ``app.url_map``: a ``register_blueprint(bp, url_prefix=…)``
    REPLACES the blueprint's own ``url_prefix`` rather than composing with it.
    Only the registrar's own effective prefix composes — which is what makes
    Flask 2.0 nested blueprints (``parent.register_blueprint(child)``) work.
    """
    bp_prefixes: dict[str, str] = {}                            # blueprint → own url_prefix
    registrations: dict[str, list[tuple[str, Optional[str]]]] = {}
    routes: list[RouteInfo] = []

    # Pass 1 — collect declarations and registrations first. A registration
    # normally sits BELOW the @bp.route decorators it re-prefixes.
    for _idx, caps in matches:
        if "blueprint.decl" in caps and "blueprint.name" in caps:
            name = node_text(caps["blueprint.name"][0])
            prefix = _clean(node_text(caps["blueprint.url_prefix"][0])) if "blueprint.url_prefix" in caps else ""
            bp_prefixes[name] = prefix

        if "app.register" in caps and "app.register_bp" in caps:
            name = node_text(caps["app.register_bp"][0])
            parent = node_text(caps["app.register_parent"][0]) if "app.register_parent" in caps else ""
            # None (not "") when no url_prefix was passed: the resolver reads
            # None as "keep the blueprint's own prefix". An empty string would
            # instead mean "registered at the root", wrongly erasing the
            # blueprint's own url_prefix on the dominant bare-register idiom.
            prefix = (
                _clean(node_text(caps["app.register_prefix"][0]))
                if "app.register_prefix" in caps else None
            )
            registrations.setdefault(name, []).append((parent, prefix))

    # Pass 2 — emit one route per effective registration prefix.
    for _idx, caps in matches:
        if "route.handler" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            obj = node_text(caps["route.object"][0]) if "route.object" in caps else ""
            handler = node_text(caps["route.func_name"][0]) if "route.func_name" in caps else ""
            line = caps["route.path"][0].start_point[0] + 1
            method_nodes = caps.get("route.methods", [])

            for prefix in _effective_prefixes(obj, bp_prefixes, registrations, compose_own=False):
                full_path = _join(prefix, path)
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
    routes: list[RouteInfo] = []
    # Pass 1: collect Route::prefix(...)->group(...) blocks with their byte
    # ranges. The @route.prefix_group node spans the whole group statement
    # (closure body included), so a route's prefix is the concatenation of the
    # prefixes of every group whose range encloses it — properly scoped, unlike
    # a flat stack that never pops and leaks prefixes across sibling groups.
    groups: list[tuple[int, int, str]] = []  # (start_byte, end_byte, prefix)
    for _idx, caps in matches:
        if "route.prefix_group" in caps and "route.prefix" in caps:
            node = caps["route.prefix_group"][0]
            groups.append((node.start_byte, node.end_byte,
                           _clean(node_text(caps["route.prefix"][0]))))

    def _scoped_prefix(pos: int) -> str:
        # Enclosing groups, outermost first (ascending start_byte).
        enclosing = sorted(
            ((s, p) for s, e, p in groups if s <= pos <= e),
            key=lambda t: t[0],
        )
        return "/".join(p for _s, p in enclosing if p)

    for _idx, caps in matches:
        if "route.call" in caps and "route.path" in caps:
            path = _clean(node_text(caps["route.path"][0]))
            method = node_text(caps["route.method"][0]) if "route.method" in caps else "get"
            controller = node_text(caps["route.controller"][0]) if "route.controller" in caps else ""
            path_node = caps["route.path"][0]
            line = path_node.start_point[0] + 1
            prefix = _scoped_prefix(path_node.start_byte)
            routes.append(RouteInfo(
                method=method.upper(),
                path=_join(prefix, path),
                handler=controller,
                source_file=file_path,
                line=line,
                framework="laravel",
            ))

        elif "route.resource" in caps and "route.resource_name" in caps:
            name_node = caps["route.resource_name"][0]
            resource = _clean(node_text(name_node))
            line = name_node.start_point[0] + 1
            prefix = _scoped_prefix(name_node.start_byte)
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
    """Actix proc macros (#[get(...)]) + Axum Router::new().route(...) + Warp filters.

    The three Rust web frameworks share ``actix.scm``; each is a disjoint set of
    captures, so a file only ever produces routes for the style it actually uses.
    """
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

    routes.extend(_warp_routes(file_path, matches, framework))
    return routes


def _warp_macro_segments(tokens_text: str) -> list[str]:
    """Turn a ``warp::path!`` token_tree text into URL segments.

    ``("users" / u32)`` → ``["users", "{param}"]``. String tokens become literal
    segments; a typed token (``u32``, ``String``, ``Uuid`` — captured by the
    grammar as identifier / primitive_type / type_identifier) is a positional
    path parameter, rendered ``{param}`` (Warp path! params are unnamed). Tokens
    that are neither (e.g. the ``..`` rest pattern) are not nameable and dropped.
    """
    inner = tokens_text.strip()
    if len(inner) >= 2 and inner[0] in "([{" and inner[-1] in ")]}":
        inner = inner[1:-1]
    segments: list[str] = []
    for raw in inner.split("/"):
        part = raw.strip()
        if not part:
            continue
        if part[0] in ('"', "'"):
            segments.append(_clean(part))
        elif part[0].isalpha() or part[0] == "_":
            segments.append("{param}")
    return segments


def _warp_routes(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Warp filter-combinator chains.

    A Warp route is a filter chain, e.g.
    ``warp::path!("users" / u32).and(warp::get()).and_then(get_user)`` — path,
    method, and handler are three unrelated nodes along one method-call chain.
    ``actix.scm`` captures each piece plus the let_declaration/block scopes; here
    every piece is bucketed by its *innermost* enclosing scope and each bucket is
    folded into a single route (path segments concatenated in source order, the
    first method combinator and first identifier handler winning).

    Honest limits: multiple filters joined by ``.or(...)`` inside ONE binding
    collapse into a single concatenated path; a filter bound to its own ``let``
    and reused via ``.and(var)`` yields a partial route; ``warp::path::param()``
    and closure handlers are not resolved.
    """
    scopes: list[tuple[int, int]] = []
    anchors: list[tuple[int, int, list[str]]] = []  # (start_byte, row, segments)
    methods: list[tuple[int, str]] = []             # (start_byte, method name)
    handlers: list[tuple[int, str]] = []            # (start_byte, handler name)

    for _idx, caps in matches:
        if "route.warp_scope" in caps:
            n = caps["route.warp_scope"][0]
            scopes.append((n.start_byte, n.end_byte))
        if "route.warp_path_macro" in caps and "route.warp_macro_tokens" in caps:
            n = caps["route.warp_path_macro"][0]
            segs = _warp_macro_segments(node_text(caps["route.warp_macro_tokens"][0]))
            if segs:
                anchors.append((n.start_byte, n.start_point[0], segs))
        if "route.warp_path_call" in caps and "route.warp_seg" in caps:
            n = caps["route.warp_path_call"][0]
            seg = _clean(node_text(caps["route.warp_seg"][0]))
            if seg:
                anchors.append((n.start_byte, n.start_point[0], [seg]))
        if "route.warp_method_call" in caps and "route.warp_method" in caps:
            n = caps["route.warp_method_call"][0]
            methods.append((n.start_byte, node_text(caps["route.warp_method"][0])))
        if "route.warp_handler_call" in caps and "route.warp_handler" in caps:
            n = caps["route.warp_handler_call"][0]
            handlers.append((n.start_byte, node_text(caps["route.warp_handler"][0])))

    if not anchors:
        return []

    def _bucket(pos: int) -> tuple[int, int]:
        # Innermost enclosing scope = the enclosing one with the largest start
        # (scopes nest, so deeper = later start). No enclosing scope → a
        # per-position singleton, so an unscoped anchor still yields its route.
        best: Optional[tuple[int, int]] = None
        for s, e in scopes:
            if s <= pos <= e and (best is None or s > best[0]):
                best = (s, e)
        return best if best is not None else (pos, pos)

    grouped: dict[tuple[int, int], dict] = {}
    for start, row, segs in anchors:
        grouped.setdefault(
            _bucket(start), {"anchors": [], "methods": [], "handlers": []},
        )["anchors"].append((start, row, segs))
    for start, method in methods:
        key = _bucket(start)
        if key in grouped:
            grouped[key]["methods"].append((start, method))
    for start, handler in handlers:
        key = _bucket(start)
        if key in grouped:
            grouped[key]["handlers"].append((start, handler))

    routes: list[RouteInfo] = []
    for key in sorted(grouped):
        g = grouped[key]
        g["anchors"].sort()
        segments = [s for _start, _row, segs in g["anchors"] for s in segs]
        method = min(g["methods"])[1] if g["methods"] else ""
        handler = min(g["handlers"])[1] if g["handlers"] else ""
        routes.append(RouteInfo(
            method=_norm_method(method.lower()) if method else "ANY",
            path=_join(*segments),
            handler=handler,
            source_file=file_path,
            line=g["anchors"][0][1] + 1,
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
            # Concatenate ALL enclosing prefix scopes, outermost first —
            # Ktor nests them: route("/api") { route("/v1") { get("/users") }}
            # serves /api/v1/users. Keeping only the last (innermost) match
            # silently dropped every outer prefix.
            enclosing = sorted(
                (
                    (start, pfx)
                    for start, end, pfx in prefix_scopes
                    if start <= call_node.start_point[0] <= end
                ),
                key=lambda t: t[0],
            )
            routes.append(RouteInfo(
                method=method.upper(),
                path=_join(*(pfx for _, pfx in enclosing), path),
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


def _interpret_tauri(file_path: str, matches: list, framework: str) -> list[RouteInfo]:
    """Tauri: #[tauri::command] functions as IPC endpoints (routes).

    The frontend calls these via invoke("command_name", { args }).
    Attributes and function_items are siblings in tree-sitter-rust, so
    we collect the end-lines of all #[tauri::command] attributes, then
    match each function whose start line follows an attribute end line.
    """
    routes: list[RouteInfo] = []

    # Collect end-lines of #[tauri::command] attributes
    cmd_attr_ends: set[int] = set()
    for _idx, caps in matches:
        if "route.tauri_attr" in caps:
            attr_node = caps["route.tauri_attr"][0]
            cmd_attr_ends.add(attr_node.end_point[0])

    if not cmd_attr_ends:
        return []

    # Match function_items that start right after an attribute
    seen: set[str] = set()
    for _idx, caps in matches:
        if "route.func" in caps and "route.func_name" in caps:
            func_node = caps["route.func"][0]
            func_start_line = func_node.start_point[0]
            # Function must start on the line immediately after the attribute
            if func_start_line in cmd_attr_ends or (func_start_line - 1) in cmd_attr_ends:
                name = node_text(caps["route.func_name"][0])
                if name in seen:
                    continue
                seen.add(name)
                routes.append(RouteInfo(
                    method="INVOKE",
                    path=f"/tauri/{name}",
                    handler=name,
                    source_file=file_path,
                    line=func_node.start_point[0] + 1,
                    framework="tauri",
                ))
    return routes
