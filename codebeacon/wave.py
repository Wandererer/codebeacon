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
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from codebeacon.common.types import (
    ComponentInfo,
    Edge,
    EntityInfo,
    ProjectInfo,
    RouteInfo,
    ServiceInfo,
    UnresolvedRef,
)

# Schema version of the per-file extraction payload produced by ``_extract_file``
# and stored verbatim in the AST cache. Bump this whenever the dict gains or
# changes a field, so entries written by an older codebeacon cannot be served
# for an *unchanged* source file — the content hash cannot catch a payload that
# is stale because the serialiser changed, not because the file did.
# 2: ServiceInfo.implements / .extends added (they were silently dropped, which
#    left every interface→impl DI edge unresolved).
WAVE_PAYLOAD_SCHEMA = 2


@dataclass
class ExtractionFailure:
    """A single file that the wave pipeline failed to extract.

    Promoted from a silent ``warnings.warn`` to a first-class result so that
    callers (CLI, MCP, tests) can detect partial graphs deterministically.
    """
    file_path: str
    framework: str
    error: str
    error_type: str  # exception class name, e.g. "UnicodeDecodeError"

    def to_dict(self) -> dict[str, str]:
        return {
            "file_path": self.file_path,
            "framework": self.framework,
            "error": self.error,
            "error_type": self.error_type,
        }


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
    failures: list[ExtractionFailure] = field(default_factory=list)

    @property
    def failure_rate(self) -> float:
        """Failure rate over attempted (non-cache-hit) files."""
        attempted = self.file_count - self.skipped_count
        if attempted <= 0:
            return 0.0
        return len(self.failures) / attempted


# ── Single-file extraction ────────────────────────────────────────────────────

def _extract_file(
    file_path: str,
    framework: str,
    project_path: str,
    cache=None,
    semantic: bool = False,
) -> Union[dict, ExtractionFailure]:
    """Run all extractors on a single file.

    Returns either a result dict (JSON-serializable) or an ``ExtractionFailure``.
    The dict has a '_cache_hit' key if the result came from cache.
    Callers must check ``isinstance(r, ExtractionFailure)`` to separate the
    two paths — the function never returns None so partial graphs cannot be
    masked by silent drops.
    """
    # Check cache before parsing. Keyed by framework too: one cache can serve
    # several projects in a repo group, and the same file extracted under a
    # different framework yields different results. The `semantic` flag is also
    # part of the key: a semantic run folds extra 'references' edges into the
    # same result dict, so a semantic entry is NOT interchangeable with a plain
    # one for an unchanged file — without this, `--update --semantic` reuses a
    # plain cache hit and silently drops the semantic edges (and the reverse
    # leaks references edges into a plain scan).
    cache_ns = f"{framework}::semantic" if semantic else framework
    if cache is not None:
        cached = cache.get(file_path, framework=cache_ns)
        # A payload from an older serialiser is a miss, not a hit: it may be
        # missing fields this version reads (see WAVE_PAYLOAD_SCHEMA).
        if cached is not None and cached.get("_schema") == WAVE_PAYLOAD_SCHEMA:
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
            "_schema": WAVE_PAYLOAD_SCHEMA,
            "routes": [_route_to_dict(r) for r in routes],
            "services": [_service_to_dict(s) for s in services],
            "entities": [_entity_to_dict(e) for e in entities],
            "components": [_component_to_dict(c) for c in components],
            "import_edges": [_edge_to_dict(e) for e in import_edges + semantic_edges],
            "unresolved": [_unresolved_to_dict(u) for u in unresolved],
        }

        if cache is not None:
            fh = cache.file_hash(file_path)
            cache.put(file_path, result, fh, framework=cache_ns)

        return result

    except Exception as exc:
        return ExtractionFailure(
            file_path=file_path,
            framework=framework,
            error=str(exc),
            error_type=type(exc).__name__,
        )


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
            if isinstance(file_result, ExtractionFailure):
                wave_result.failures.append(file_result)
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
) -> list[Union[dict, ExtractionFailure]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Every file is submitted up front (parallelism is unchanged), but the
        # results are collected in SUBMISSION order, not completion order.
        # Downstream, graph/build.py resolves label collisions by first-claimer
        # and common/symbols.py indexes classes in list order, so a completion
        # -ordered merge made node ids — and therefore wiki/obsidian filenames —
        # flip between runs on an unchanged corpus. collect_files() yields a
        # sorted list, so submission order is a stable function of the corpus.
        submitted = [
            (fp, pool.submit(_extract_file, fp, framework, project_path, cache, semantic))
            for fp in chunk
        ]
        results: list[Union[dict, ExtractionFailure]] = []
        for fp, future in submitted:
            try:
                results.append(future.result())
            except Exception as exc:
                # Thread worker itself crashed (e.g. interpreter-level error).
                # Wrap as ExtractionFailure so it surfaces in the same channel
                # as expected extractor errors instead of being lost.
                results.append(ExtractionFailure(
                    file_path=fp,
                    framework=framework,
                    error=str(exc),
                    error_type=type(exc).__name__,
                ))
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
        "implements": list(s.implements),
        "extends": list(s.extends),
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
        implements=d.get("implements", []),
        extends=d.get("extends", []),
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
