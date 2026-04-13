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

    return list(services.values()), unresolved


def _interpret_fastapi(
    file_path: str, matches: list, framework: str,
) -> tuple[list[ServiceInfo], list[UnresolvedRef]]:
    """FastAPI: Depends() function-based DI."""
    services: list[ServiceInfo] = []
    unresolved: list[UnresolvedRef] = []
    seen_funcs: set[str] = set()

    for _idx, caps in matches:
        # Functions that accept typed parameters (potential services)
        if "service.function" in caps and "service.func_name" in caps:
            name = node_text(caps["service.func_name"][0])
            if name in seen_funcs:
                continue
            seen_funcs.add(name)
            node = caps["service.function"][0]
            services.append(ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=node.start_point[0] + 1,
                framework="fastapi",
            ))

        # Depends(func) calls
        if "service.depends" in caps and "service.depends_func" in caps:
            dep_func = node_text(caps["service.depends_func"][0])
            # Find enclosing function for the unresolved ref
            depends_node = caps["service.depends"][0]
            enclosing = ""
            for svc in services:
                if svc.name in seen_funcs:
                    enclosing = svc.name
            if dep_func not in (s.name for s in services):
                unresolved.append(UnresolvedRef(
                    source_node_id=_nid(file_path, enclosing or "unknown"),
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
    services: dict[int, ServiceInfo] = {}
    unresolved: list[UnresolvedRef] = []

    for _idx, caps in matches:
        if "service.injectable" in caps and "service.class_name" in caps:
            cls = caps["service.injectable"][0]
            name = node_text(caps["service.class_name"][0])
            services[cls.start_byte] = ServiceInfo(
                name=name,
                class_name=name,
                source_file=file_path,
                line=cls.start_point[0] + 1,
                framework="angular",
                annotations=["Injectable"],
            )

        if "service.constructor_di" in caps and "service.inject_type" in caps:
            for dep_node in caps["service.inject_type"]:
                dep = node_text(dep_node)
                # Assign to closest service by position
                for svc in services.values():
                    if dep not in svc.dependencies:
                        svc.dependencies.append(dep)
                    unresolved.append(UnresolvedRef(
                        source_node_id=_nid(file_path, svc.name),
                        ref_type="inject",
                        ref_name=dep,
                        framework="angular",
                    ))
                    break  # assign to first service (constructor_di is inside a class)

    return list(services.values()), unresolved
