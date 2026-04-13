"""Automatic wave / segment processing (Pass 1).

auto_wave() splits source files into chunks and processes them in parallel
using a ThreadPoolExecutor. Each file is run through all extractors:
  routes, services, entities, components, dependencies.

Results are merged into a WaveResult.
Pass 2 (symbol resolution + graph wiring) happens in graph/build.py after
all waves complete.
"""

from __future__ import annotations

import concurrent.futures
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from codebeacon.common.types import (
    ComponentInfo,
    Edge,
    EntityInfo,
    ProjectInfo,
    RouteInfo,
    ServiceInfo,
    UnresolvedRef,
)


@dataclass
class WaveResult:
    """Aggregated Pass-1 extraction results across all chunks for one project."""
    project: ProjectInfo
    routes: list[RouteInfo] = field(default_factory=list)
    services: list[ServiceInfo] = field(default_factory=list)
    entities: list[EntityInfo] = field(default_factory=list)
    components: list[ComponentInfo] = field(default_factory=list)
    import_edges: list[Edge] = field(default_factory=list)
    unresolved: list[UnresolvedRef] = field(default_factory=list)
    file_count: int = 0
    skipped_count: int = 0   # cache hits


# ── Single-file extraction ────────────────────────────────────────────────────

def _extract_file(
    file_path: str,
    framework: str,
    project_path: str,
    cache=None,
    semantic: bool = False,
) -> Optional[dict]:
    """Run all extractors on a single file.

    Returns a plain dict (JSON-serializable) or None on hard failure.
    The dict has a '_cache_hit' key if the result came from cache.
    """
    # Check cache before parsing
    if cache is not None:
        cached = cache.get(file_path)
        if cached is not None:
            return {"_cache_hit": True, **cached}

    try:
        from codebeacon.extract.routes import extract_routes
        from codebeacon.extract.services import extract_services
        from codebeacon.extract.entities import extract_entities
        from codebeacon.extract.components import extract_components
        from codebeacon.extract.dependencies import extract_dependencies

        routes = extract_routes(file_path, framework, project_path)
        services, unresolved = extract_services(file_path, framework)
        entities = extract_entities(file_path, framework)
        components = extract_components(file_path, framework, project_path)
        import_edges = extract_dependencies(file_path, framework)

        # Optional semantic extraction (structured comment parsing)
        semantic_edges: list[Edge] = []
        if semantic:
            from codebeacon.extract.semantic import extract_semantic_refs
            semantic_edges = extract_semantic_refs(file_path, framework)

        result: dict[str, Any] = {
            "routes": [_route_to_dict(r) for r in routes],
            "services": [_service_to_dict(s) for s in services],
            "entities": [_entity_to_dict(e) for e in entities],
            "components": [_component_to_dict(c) for c in components],
            "import_edges": [_edge_to_dict(e) for e in import_edges + semantic_edges],
            "unresolved": [_unresolved_to_dict(u) for u in unresolved],
        }

        if cache is not None:
            fh = cache.file_hash(file_path)
            cache.put(file_path, result, fh)

        return result

    except Exception as exc:
        warnings.warn(f"Extraction failed [{framework}] {file_path}: {exc}", stacklevel=2)
        return None


# ── Main public function ──────────────────────────────────────────────────────

def auto_wave(
    project: ProjectInfo,
    files: list[str],
    chunk_size: int = 300,
    max_parallel: int = 5,
    cache=None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    semantic: bool = False,
) -> WaveResult:
    """Process all files in parallel chunks and merge results (Pass 1).

    Args:
        project: the ProjectInfo for the project being scanned
        files: absolute file paths to process
        chunk_size: files per wave chunk (controls peak memory)
        max_parallel: max ThreadPoolExecutor workers per chunk
        cache: optional Cache instance for incremental processing
        progress_callback: optional callable(processed_count, total_count)

    Returns:
        WaveResult with all extraction data merged.
        Pass 2 (symbol resolve + graph wiring) is NOT done here.
    """
    wave_result = WaveResult(project=project, file_count=len(files))

    if not files:
        return wave_result

    processed = 0
    chunks = [files[i: i + chunk_size] for i in range(0, len(files), chunk_size)]

    for chunk in chunks:
        chunk_results = _process_chunk(chunk, project.framework, project.path, cache, max_parallel, semantic)
        for file_result in chunk_results:
            if file_result is None:
                continue
            if file_result.get("_cache_hit"):
                wave_result.skipped_count += 1
            _merge_file_result(file_result, wave_result)

        processed += len(chunk)
        if progress_callback:
            progress_callback(processed, len(files))

    return wave_result


def _process_chunk(
    chunk: list[str],
    framework: str,
    project_path: str,
    cache,
    max_workers: int,
    semantic: bool = False,
) -> list[Optional[dict]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_extract_file, fp, framework, project_path, cache, semantic): fp
            for fp in chunk
        }
        results: list[Optional[dict]] = []
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                fp = futures[future]
                warnings.warn(f"Chunk worker failed for {fp}: {exc}", stacklevel=2)
                results.append(None)
    return results


def _merge_file_result(result: dict, wave: WaveResult) -> None:
    """Merge one file's extraction dict into the WaveResult."""
    for r in result.get("routes", []):
        wave.routes.append(_dict_to_route(r))
    for s in result.get("services", []):
        wave.services.append(_dict_to_service(s))
    for e in result.get("entities", []):
        wave.entities.append(_dict_to_entity(e))
    for c in result.get("components", []):
        wave.components.append(_dict_to_component(c))
    for e in result.get("import_edges", []):
        wave.import_edges.append(_dict_to_edge(e))
    for u in result.get("unresolved", []):
        wave.unresolved.append(_dict_to_unresolved(u))


# ── Serialisation helpers (dataclass ↔ JSON-safe dict) ───────────────────────

def _route_to_dict(r: RouteInfo) -> dict:
    return {
        "method": r.method, "path": r.path, "handler": r.handler,
        "source_file": r.source_file, "line": r.line,
        "framework": r.framework, "prefix": r.prefix,
        "tags": list(r.tags),
    }

def _service_to_dict(s: ServiceInfo) -> dict:
    return {
        "name": s.name, "class_name": s.class_name,
        "source_file": s.source_file, "line": s.line,
        "framework": s.framework,
        "methods": list(s.methods),
        "dependencies": list(s.dependencies),
        "annotations": list(s.annotations),
    }

def _entity_to_dict(e: EntityInfo) -> dict:
    return {
        "name": e.name, "table_name": e.table_name,
        "source_file": e.source_file, "line": e.line,
        "framework": e.framework,
        "fields": list(e.fields),
        "relations": list(e.relations),
    }

def _component_to_dict(c: ComponentInfo) -> dict:
    return {
        "name": c.name, "source_file": c.source_file, "line": c.line,
        "framework": c.framework,
        "props": list(c.props), "hooks": list(c.hooks), "imports": list(c.imports),
        "is_page": c.is_page, "route_path": c.route_path,
    }

def _edge_to_dict(e: Edge) -> dict:
    return {
        "source": e.source, "target": e.target,
        "relation": e.relation, "confidence": e.confidence,
        "confidence_score": e.confidence_score,
        "source_file": e.source_file,
    }

def _unresolved_to_dict(u: UnresolvedRef) -> dict:
    return {
        "source_node_id": u.source_node_id, "ref_type": u.ref_type,
        "ref_name": u.ref_name, "framework": u.framework,
    }


def _dict_to_route(d: dict) -> RouteInfo:
    return RouteInfo(
        method=d["method"], path=d["path"], handler=d["handler"],
        source_file=d["source_file"], line=d["line"],
        framework=d["framework"], prefix=d.get("prefix", ""),
        tags=d.get("tags", []),
    )

def _dict_to_service(d: dict) -> ServiceInfo:
    return ServiceInfo(
        name=d["name"], class_name=d["class_name"],
        source_file=d["source_file"], line=d["line"],
        framework=d["framework"],
        methods=d.get("methods", []),
        dependencies=d.get("dependencies", []),
        annotations=d.get("annotations", []),
    )

def _dict_to_entity(d: dict) -> EntityInfo:
    return EntityInfo(
        name=d["name"], table_name=d["table_name"],
        source_file=d["source_file"], line=d["line"],
        framework=d["framework"],
        fields=d.get("fields", []),
        relations=d.get("relations", []),
    )

def _dict_to_component(d: dict) -> ComponentInfo:
    return ComponentInfo(
        name=d["name"], source_file=d["source_file"], line=d["line"],
        framework=d["framework"],
        props=d.get("props", []), hooks=d.get("hooks", []),
        imports=d.get("imports", []),
        is_page=d.get("is_page", False), route_path=d.get("route_path", ""),
    )

def _dict_to_edge(d: dict) -> Edge:
    return Edge(
        source=d["source"], target=d["target"],
        relation=d["relation"], confidence=d["confidence"],
        confidence_score=d["confidence_score"],
        source_file=d["source_file"],
    )

def _dict_to_unresolved(d: dict) -> UnresolvedRef:
    return UnresolvedRef(
        source_node_id=d["source_node_id"], ref_type=d["ref_type"],
        ref_name=d["ref_name"], framework=d["framework"],
    )
