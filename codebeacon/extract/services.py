"""Service / DI extraction for all supported frameworks.

Public API:
    extract_services(file_path, framework) -> tuple[list[ServiceInfo], list[UnresolvedRef]]

Design:
  - Run the framework's .scm query once per file
  - Collect service classes/functions + DI dependencies
  - DI dependencies are returned as UnresolvedRef (resolved later in Pass 2)
  - UnresolvedRef.source_node_id uses f"{file_path}::{class_name}" format
"""
from __future__ import annotations

from pathlib import Path

from codebeacon.common.types import ServiceInfo, UnresolvedRef
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


# ── Public function ───────────────────────────────────────────────────────────

def extract_services(
    file_path: str,
    framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Extract service classes and DI dependencies from *file_path*."""
    fw = framework.lower()
    query_name = _FW_TO_QUERY.get(fw)
    if not query_name:
        return [], []

    query_src = load_query_file(query_name)
    if not query_src:
        return [], []

    # SFC dispatch
    ext = Path(file_path).suffix.lower()
    if ext in (".vue", ".svelte"):
        sfc = extract_sfc_sections(file_path)
        if sfc is None:
            return [], []
        parsed = parse_sfc_script(sfc)
    else:
        parsed = parse_file(file_path)

    if parsed is None:
        return [], []
    root, lang = parsed

    from codebeacon.extract.base import is_grammar_allowed
    if not is_grammar_allowed(query_name, lang):
        return [], []

    try:
        matches = run_query(lang, query_src, root)
    except Exception:
        return [], []

    _interpreters = {
        "spring_boot": _interpret_spring_boot,
        "express":     _interpret_express,
        "nestjs":      _interpret_nestjs,
        "fastapi":     _interpret_fastapi,
        "django":      _interpret_noop,
        "flask":       _interpret_noop,
        "gin":         _interpret_gin,
        "rails":       _interpret_rails,
        "laravel":     _interpret_laravel,
        "aspnet":      _interpret_aspnet,
        "actix":       _interpret_actix,
        "tauri":       _interpret_tauri,
        "vapor":       _interpret_vapor,
        "ktor":        _interpret_ktor,
        "react":       _interpret_noop,
        "vue":         _interpret_noop,
        "svelte":      _interpret_noop,
        "angular":     _interpret_angular,
    }

    interpreter = _interpreters.get(query_name, _interpret_noop)
    try:
        return interpreter(file_path, matches, fw)
    except Exception:
        return [], []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nid(file_path: str, name: str) -> str:
    """Build a stable node ID for UnresolvedRef.source_node_id."""
    return f"{file_path}::{name}"


def _collect_heritage(matches: list) -> dict[str, tuple[list[str], list[str]]]:
    """Collect ``class_name → (extends, implements)`` from heritage captures.

    The ``@service.with_heritage`` query pattern (TS frameworks) emits one match
    per heritage type, so a class with ``implements IFoo, OnInit`` produces two
    matches that both carry ``@service.heritage_class``. We fold them back into
    per-class lists, de-duplicating while preserving declaration order. Feeds the
    structured ``ServiceInfo.extends`` / ``.implements`` fields that
    ``SymbolTable`` reads for interface→implementation DI resolution.
    """
    extends: dict[str, list[str]] = {}
    implements: dict[str, list[str]] = {}
    for _idx, caps in matches:
        if "service.heritage_class" not in caps:
            continue
        cname = node_text(caps["service.heritage_class"][0])
        for node in caps.get("service.extends", []):
            val = node_text(node)
            bucket = extends.setdefault(cname, [])
            if val and val not in bucket:
                bucket.append(val)
        for node in caps.get("service.implements", []):
            val = node_text(node)
            bucket = implements.setdefault(cname, [])
            if val and val not in bucket:
                bucket.append(val)
    return {
        cname: (extends.get(cname, []), implements.get(cname, []))
        for cname in set(extends) | set(implements)
    }


def _interpret_noop(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    return [], []


# ── Per-framework interpreters ────────────────────────────────────────────────

def _interpret_spring_boot(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Spring Boot: @Service/@Component/@Repository + @Autowired / constructor injection."""
    services: dict[int, ServiceInfo] = {}      # class start_byte → ServiceInfo
    unresolved: list[UnresolvedRef] = []
    # class byte ranges for DI correlation
    class_ranges: dict[int, tuple[int, int, str]] = {}  # start → (start, end, class_name)

    for _idx, caps in matches:
        # @Service / @Component / @Repository class
        if "service.class" in caps and "service.class_name" in caps:
            cls = caps["service.class"][0]
            name = node_text(caps["service.class_name"][0])
            ann = node_text(caps["service.annotation"][0]) if "service.annotation" in caps else ""
            key = cls.start_byte
            if key not in services:
                services[key] = ServiceInfo(
                    name=name,
                    class_name=name,
                    source_file=file_path,
                    line=cls.start_point[0] + 1,
                    framework="spring-boot",
                    annotations=[ann] if ann else [],
                )
                class_ranges[key] = (cls.start_byte, cls.end_byte, name)
            elif ann and ann not in services[key].annotations:
                services[key].annotations.append(ann)

        # Implemented interfaces
        if "service.with_interface" in caps and "service.interface" in caps:
            cls = caps["service.with_interface"][0]
            iface = node_text(caps["service.interface"][0])
            for key, info in services.items():
                start, end, _ = class_ranges.get(key, (0, 0, ""))
                if start <= cls.start_byte <= end:
                    if iface not in info.annotations:
                        info.annotations.append(f"implements:{iface}")
                    # Structured field too: SymbolTable reads metadata["implements"]
                    # (not the annotation string) to drive interface→impl DI
                    # resolution. The annotation is kept for the wiki display.
                    if iface not in info.implements:
                        info.implements.append(iface)
                    break

        # @Autowired field injection
        if "di.autowired_field" in caps and "di.field_type" in caps:
            field_node = caps["di.autowired_field"][0]
            dep_type = node_text(caps["di.field_type"][0])
            # Find enclosing class
            for key, (start, end, cls_name) in class_ranges.items():
                if start <= field_node.start_byte <= end:
                    if dep_type not in services[key].dependencies:
                        services[key].dependencies.append(dep_type)
                    unresolved.append(UnresolvedRef(
                        source_node_id=_nid(file_path, cls_name),
                        ref_type="autowired",
                        ref_name=dep_type,
                        framework="spring-boot",
                    ))
                    break

        # Constructor injection
        if "di.constructor" in caps and "di.ctor_param_type" in caps:
            ctor_node = caps["di.constructor"][0]
            for param_type_node in caps["di.ctor_param_type"]:
                dep_type = node_text(param_type_node)
                for key, (start, end, cls_name) in class_ranges.items():
                    if start <= ctor_node.start_byte <= end:
                        if dep_type not in services[key].dependencies:
                            services[key].dependencies.append(dep_type)
                        unresolved.append(UnresolvedRef(
                            source_node_id=_nid(file_path, cls_name),
                            ref_type="autowired",
                            ref_name=dep_type,
                            framework="spring-boot",
                        ))
                        break

    return list(services.values()), unresolved


def _interpret_express(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Express/Koa/Fastify: exported classes as services (no DI framework)."""
    services: list[ServiceInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.name" in caps:
            name = node_text(caps["service.name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps.get("service.export_class", caps.get("service.class", [None]))[0]
            line = node.start_point[0] + 1 if node else 1
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=line,
                framework=framework,
            ))
    return services, []


def _interpret_nestjs(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """NestJS: @Injectable + constructor injection.

    Injectable decorator is sibling of class_declaration in export_statement.
    Constructor DI is matched separately via service.constructor_di pattern.
    Uses byte-position matching to correlate DI with enclosing class.
    """
    services: dict[str, ServiceInfo] = {}  # class_name → ServiceInfo
    # Track byte ranges for each service's enclosing export_statement
    svc_ranges: dict[str, tuple[int, int]] = {}  # class_name → (start, end)
    unresolved: list[UnresolvedRef] = []

    # Pass 1: collect @Injectable classes
    for _idx, caps in matches:
        for key in ("service.injectable", "service.injectable_noexport"):
            if key in caps and "service.class_name" in caps:
                name = node_text(caps["service.class_name"][0])
                if name not in services:
                    cls = caps[key][0]
                    services[name] = ServiceInfo(
                        name=name,
                        class_name=name,
                        source_file=file_path,
                        line=cls.start_point[0] + 1,
                        framework="nestjs",
                        annotations=["Injectable"],
                    )
                    svc_ranges[name] = (cls.start_byte, cls.end_byte)
                break

    # Pass 2: collect constructor DI, matching to enclosing class by position
    for _idx, caps in matches:
        if "service.constructor_di" in caps and "service.inject_type" in caps:
            ctor_node = caps["service.constructor_di"][0]
            ctor_start = ctor_node.start_byte
            # Find enclosing service by byte range
            enclosing_name = ""
            for name, (start, end) in svc_ranges.items():
                if start <= ctor_start <= end:
                    enclosing_name = name
                    break
            if not enclosing_name:
                continue
            svc = services[enclosing_name]
            for dep_node in caps["service.inject_type"]:
                dep = node_text(dep_node)
                if dep not in svc.dependencies:
                    svc.dependencies.append(dep)
                unresolved.append(UnresolvedRef(
                    source_node_id=_nid(file_path, enclosing_name),
                    ref_type="inject",
                    ref_name=dep,
                    framework="nestjs",
                ))

    # Attach class heritage (extends / implements) so interface-typed providers
    # resolve to their implementing service via SymbolTable._implements_map.
    heritage = _collect_heritage(matches)
    for svc in services.values():
        ext, impl = heritage.get(svc.name, ([], []))
        if ext:
            svc.extends = ext
        if impl:
            svc.implements = impl

    return list(services.values()), unresolved


def _interpret_fastapi(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """FastAPI: Depends() function-based DI."""
    services: list[ServiceInfo] = []
    unresolved: list[UnresolvedRef] = []
    seen_funcs: set[str] = set()
    # name → (start_byte, end_byte) of the enclosing function_definition, so a
    # Depends() call can be attributed to the function it actually sits inside
    # (a function_definition node spans its parameter list where Depends lives).
    func_ranges: list[tuple[int, int, str]] = []

    # Pass 1: collect candidate functions.
    for _idx, caps in matches:
        if "service.function" in caps and "service.func_name" in caps:
            name = node_text(caps["service.func_name"][0])
            if name in seen_funcs:
                continue
            seen_funcs.add(name)
            node = caps["service.function"][0]
            func_ranges.append((node.start_byte, node.end_byte, name))
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="fastapi",
            ))

    # Pass 2: attribute each Depends() call to its enclosing function by byte
    # range, preferring the innermost (smallest) containing range.
    service_names = {s.name for s in services}
    for _idx, caps in matches:
        if "service.depends" in caps and "service.depends_func" in caps:
            dep_func = node_text(caps["service.depends_func"][0])
            if dep_func in service_names:
                continue
            depends_start = caps["service.depends"][0].start_byte
            enclosing = ""
            best_span = None
            for start, end, name in func_ranges:
                if start <= depends_start <= end:
                    span = end - start
                    if best_span is None or span < best_span:
                        best_span = span
                        enclosing = name
            # No enclosing matched function (untyped params, module-level
            # Depends, FastAPI(dependencies=[...])) — skip rather than emit a
            # ghost "<file>::unknown" source that can never resolve to a node.
            if not enclosing:
                continue
            unresolved.append(UnresolvedRef(
                source_node_id=_nid(file_path, enclosing),
                ref_type="depends",
                ref_name=dep_func,
                framework="fastapi",
            ))

    return services, unresolved


def _interpret_gin(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Go: service structs with embedded field types as dependencies."""
    services: list[ServiceInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if ("service.struct" in caps or "service.struct_plain" in caps) and "service.struct_name" in caps:
            name = node_text(caps["service.struct_name"][0])
            if name in seen:
                continue
            seen.add(name)
            deps = [node_text(n) for n in caps.get("service.field_type", [])]
            node = caps.get("service.struct", caps.get("service.struct_plain", [None]))[0]
            line = node.start_point[0] + 1 if node else 1
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=line,
                framework=framework,
                dependencies=deps,
            ))
    return services, []


def _interpret_rails(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Rails: plain Ruby classes as services."""
    services: list[ServiceInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.class" in caps and "service.class_name" in caps:
            name = node_text(caps["service.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["service.class"][0]
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="rails",
            ))
    return services, []


def _interpret_laravel(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Laravel: service classes + $this->app->bind() DI bindings."""
    services: list[ServiceInfo] = []
    unresolved: list[UnresolvedRef] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.class" in caps and "service.class_name" in caps:
            name = node_text(caps["service.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["service.class"][0]
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="laravel",
            ))

        if "di.binding" in caps and "di.interface" in caps and "di.implementation" in caps:
            iface = node_text(caps["di.interface"][0])
            impl = node_text(caps["di.implementation"][0])
            unresolved.append(UnresolvedRef(
                source_node_id=_nid(file_path, impl),
                ref_type="bind",
                ref_name=iface,
                framework="laravel",
            ))

    return services, unresolved


def _interpret_aspnet(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """ASP.NET: service classes with interfaces + AddScoped<IFoo, FooImpl>() DI."""
    services: list[ServiceInfo] = []
    unresolved: list[UnresolvedRef] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.class" in caps and "service.class_name" in caps:
            name = node_text(caps["service.class_name"][0])
            if name in seen:
                continue
            seen.add(name)
            iface = node_text(caps["service.interface"][0]) if "service.interface" in caps else ""
            node = caps["service.class"][0]
            svc = ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="aspnet",
            )
            if iface:
                svc.annotations.append(f"implements:{iface}")
                # Structured field drives interface→impl DI resolution; the C#
                # base_list's first identifier is conventionally the interface
                # (IFoo) when a class registers via AddScoped<IFoo, FooImpl>().
                svc.implements.append(iface)
            services.append(svc)

        if "di.generic_registration" in caps and "di.service_type" in caps and "di.impl_type" in caps:
            iface = node_text(caps["di.service_type"][0])
            impl = node_text(caps["di.impl_type"][0])
            unresolved.append(UnresolvedRef(
                source_node_id=_nid(file_path, impl),
                ref_type="bind",
                ref_name=iface,
                framework="aspnet",
            ))

    return services, unresolved


def _interpret_actix(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Actix/Axum: AppState and other service structs."""
    services: list[ServiceInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.struct" in caps and "service.struct_name" in caps:
            name = node_text(caps["service.struct_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["service.struct"][0]
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework=framework,
            ))
    return services, []


def _interpret_vapor(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Vapor: route configuration functions as services."""
    services: list[ServiceInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.func" in caps and "service.func_name" in caps:
            name = node_text(caps["service.func_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["service.func"][0]
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="vapor",
            ))
    return services, []


def _interpret_ktor(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Ktor: Koin DI single{}/factory{} + regular Kotlin classes."""
    services: list[ServiceInfo] = []
    unresolved: list[UnresolvedRef] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        # Koin: single { UserService(get()) }
        if "service.koin_binding" in caps and "service.koin_type" in caps:
            name = node_text(caps["service.koin_type"][0])
            if name not in seen:
                seen.add(name)
                node = caps["service.koin_binding"][0]
                services.append(ServiceInfo(
                    name=name,
                    class_name=name,
                    source_file=file_path,
                    line=node.start_point[0] + 1,
                    framework="ktor",
                    annotations=["koin"],
                ))

        # Regular class
        if "service.class" in caps and "service.class_name" in caps:
            name = node_text(caps["service.class_name"][0])
            if name not in seen:
                seen.add(name)
                node = caps["service.class"][0]
                services.append(ServiceInfo(
                    name=name,
                    class_name=name,
                    source_file=file_path,
                    line=node.start_point[0] + 1,
                    framework="ktor",
                ))

    return services, unresolved


def _interpret_angular(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Angular: @Injectable + constructor DI."""
    services: dict[int, ServiceInfo] = {}  # class start_byte → ServiceInfo
    svc_ranges: list[tuple[int, int, int]] = []  # (start, end, start_key)
    unresolved: list[UnresolvedRef] = []

    # Pass 1: collect @Injectable classes with their byte ranges. Exported
    # classes capture as `service.injectable` (decorator on export_statement);
    # bare classes as `service.injectable_noexport`.
    for _idx, caps in matches:
        inj_key = ("service.injectable" if "service.injectable" in caps
                   else "service.injectable_noexport" if "service.injectable_noexport" in caps
                   else None)
        if inj_key and "service.class_name" in caps:
            cls = caps[inj_key][0]
            name = node_text(caps["service.class_name"][0])
            if cls.start_byte not in services:
                services[cls.start_byte] = ServiceInfo(
                    name=name,
                    class_name=name,
                    source_file=file_path,
                    line=cls.start_point[0] + 1,
                    framework="angular",
                    annotations=["Injectable"],
                )
                svc_ranges.append((cls.start_byte, cls.end_byte, cls.start_byte))

    # Pass 2: attribute each constructor DI dep to the @Injectable class that
    # actually encloses it (byte-range containment), not blindly the first one.
    for _idx, caps in matches:
        if "service.constructor_di" in caps and "service.inject_type" in caps:
            ctor_start = caps["service.constructor_di"][0].start_byte
            key = None
            best_span = None
            for start, end, start_key in svc_ranges:
                if start <= ctor_start <= end:
                    span = end - start
                    if best_span is None or span < best_span:
                        best_span = span
                        key = start_key
            if key is None:
                continue
            svc = services[key]
            for dep_node in caps["service.inject_type"]:
                dep = node_text(dep_node)
                if dep not in svc.dependencies:
                    svc.dependencies.append(dep)
                unresolved.append(UnresolvedRef(
                    source_node_id=_nid(file_path, svc.name),
                    ref_type="inject",
                    ref_name=dep,
                    framework="angular",
                ))

    # Attach class heritage (extends / implements) so interface-typed providers
    # resolve to their implementing service via SymbolTable._implements_map.
    heritage = _collect_heritage(matches)
    for svc in services.values():
        ext, impl = heritage.get(svc.name, ([], []))
        if ext:
            svc.extends = ext
        if impl:
            svc.implements = impl

    return list(services.values()), unresolved


def _interpret_tauri(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """Tauri: Managed state structs (containing Mutex/RwLock/Arc fields)."""
    services: list[ServiceInfo] = []
    seen: set[str] = set()

    for _idx, caps in matches:
        if "service.struct" in caps and "service.struct_name" in caps:
            name = node_text(caps["service.struct_name"][0])
            if name in seen:
                continue
            seen.add(name)
            node = caps["service.struct"][0]
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="tauri",
                annotations=["managed_state"],
            ))
    return services, []
