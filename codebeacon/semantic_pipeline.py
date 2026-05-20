"""AI-semantic pipeline: prepare candidate tasks + apply LLM results.

Model choice belongs to the agent running the ``/codebeacon`` skill —
codebeacon only does the AST-side work and consumes the results.

Pipeline shape (0.4.0+):

  1. ``prepare()`` reads ``beacon.json``, re-applies every archived edge
     in ``semantic/original/*.jsonl`` to the fresh graph (so rescans don't
     lose prior inferences), prunes archive entries that point at nodes no
     longer in the graph, then writes a fresh batch of candidates to
     ``semantic/pending/chunk_NNN.jsonl`` (one chunk per ``--chunk-size``
     tasks, capped by ``--max-tasks``).

  2. The skill (Claude Code) iterates ``semantic/pending/`` chunk-by-chunk,
     runs the analysis with whatever model the agent is currently running
     on, and writes a matching ``semantic/results/chunk_NNN.jsonl`` per
     chunk.

  3. ``apply()`` merges each result chunk into ``beacon.json`` (as
     ``references`` edges, ``confidence=INFERRED``, ``confidence_score=0.7``),
     **moves** the corresponding ``pending/chunk_NNN.jsonl`` into
     ``original/`` (carrying both the task spec and the applied edges), and
     regenerates wiki + obsidian + context map.

Files:
  .codebeacon/semantic/pending/chunk_NNN.jsonl   (awaiting agent)
  .codebeacon/semantic/results/chunk_NNN.jsonl   (agent writes here)
  .codebeacon/semantic/original/chunk_NNN.jsonl  (durable archive after apply)
  .codebeacon/semantic/original/_legacy.jsonl    (auto-migrated from 0.3.x)

Schema:
  task   : {task_id, source_node_id, file_path, framework, excerpt, hint}
  result : {task_id, source_node_id, edges: [{target_name, relation?, confidence_score?}]}
  original: {task_id, source_node_id, file_path?, edges: [...]}

``task_id`` is ``SHA1(file_path + node_id + excerpt_hash[:8])[:16]`` — the
excerpt hash means a file whose semantic content changed between scans
gets a fresh task_id, so the agent re-analyses it instead of being
silently skipped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import networkx as nx

MAX_EXCERPT_CHARS = 4000

# Layout
SEMANTIC_DIRNAME = "semantic"
PENDING_SUBDIR = "pending"
RESULTS_SUBDIR = "results"
ORIGINAL_SUBDIR = "original"
LEGACY_ARCHIVE_FILENAME = "original.jsonl"   # 0.3.x single-file archive
LEGACY_MIGRATED_NAME = "_legacy.jsonl"       # destination inside original/


# ── Public dataclasses ────────────────────────────────────────────────────────

@dataclass
class PrepareResult:
    pending_dir: Path
    new_tasks: int
    chunks: int
    reapplied_edges: int
    pruned_archive: int
    archive_size: int


@dataclass
class ApplyResult:
    applied: int
    skipped: int
    chunks_archived: int
    archive_size: int


# ── Path helpers ──────────────────────────────────────────────────────────────

def _semantic_root(beacon_dir: Path) -> Path:
    return beacon_dir / SEMANTIC_DIRNAME


def _pending_dir(beacon_dir: Path) -> Path:
    return _semantic_root(beacon_dir) / PENDING_SUBDIR


def _results_dir(beacon_dir: Path) -> Path:
    return _semantic_root(beacon_dir) / RESULTS_SUBDIR


def _original_dir(beacon_dir: Path) -> Path:
    return _semantic_root(beacon_dir) / ORIGINAL_SUBDIR


def _migrate_legacy_archive(beacon_dir: Path) -> None:
    """If a 0.3.x single-file archive exists, move it to original/_legacy.jsonl.

    Idempotent: no-op if already migrated.
    """
    legacy = _semantic_root(beacon_dir) / LEGACY_ARCHIVE_FILENAME
    if not legacy.exists():
        return
    target = _original_dir(beacon_dir) / LEGACY_MIGRATED_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        # Merge: append legacy after target (preserves both)
        with open(legacy, encoding="utf-8") as src, open(target, "a", encoding="utf-8") as dst:
            for line in src:
                if line.strip():
                    dst.write(line if line.endswith("\n") else line + "\n")
        legacy.unlink()
    else:
        shutil.move(str(legacy), str(target))


# ── Internals ─────────────────────────────────────────────────────────────────

@dataclass
class _Candidate:
    file_path: str
    node_id: str
    framework: str
    score: int


def _excerpt_hash(excerpt: str) -> str:
    return hashlib.sha1(excerpt.encode("utf-8", errors="replace")).hexdigest()[:8]


def _task_id(file_path: str, node_id: str, excerpt: str) -> str:
    """task_id is content-aware: changes when the analysed excerpt changes."""
    fingerprint = f"{file_path}|{node_id}|{_excerpt_hash(excerpt)}"
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]


def _read_excerpt(file_path: str) -> Optional[str]:
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text[:MAX_EXCERPT_CHARS]


def _is_type_name(token: str) -> bool:
    token = (token or "").strip()
    if not token or len(token) < 2:
        return False
    primitives = {
        "int", "long", "float", "double", "boolean", "void", "string",
        "String", "Integer", "Long", "Float", "Double", "Boolean", "Object",
        "any", "unknown", "never", "undefined", "null", "true", "false",
        "str", "bytes", "list", "dict", "tuple", "set", "bool", "type",
    }
    return token not in primitives and token[0].isupper()


def _iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield dict records from a JSONL file, skipping anything malformed.

    Hardened against the same hazards graphify guards on the LLM side
    (graphify 0.8.11 / #924): an agent can write blank lines, ``null``,
    a bare array, a string, or trailing markdown fences when its API
    backend returns an empty ``choices`` list or ``choices[0].message =
    None`` — without this guard, downstream ``obj.get("task_id")``
    raises ``AttributeError`` on the first non-dict record and the
    whole apply step bails out.
    """
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            # Strip stray code-fence wrappers some models emit despite
            # the JSON-only instruction (```json … ``` blocks).
            if line.startswith("```"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                # null, list, str, number — all valid JSON but unusable.
                continue
            yield obj


def _read_archive(beacon_dir: Path) -> list[dict]:
    """Read all archived entries across ``original/*.jsonl``."""
    odir = _original_dir(beacon_dir)
    if not odir.exists():
        return []
    entries: list[dict] = []
    for path in sorted(odir.glob("*.jsonl")):
        entries.extend(_iter_jsonl(path))
    return entries


def _pick_candidates(G: nx.DiGraph) -> list[_Candidate]:
    """Score files and return them ordered by descending score.

    Every source file that contributes at least one non-``external`` node to
    the graph gets a base score of ``1`` — so prepare emits candidates for
    **every folder**, not just the high-coupling ones. God-folder, hub, and
    unresolved-target signals stack on top as ordering boosts:

      * +1 base for any file that has at least one real node.
      * +2 per edge from a node in this file to an ``external`` (unresolved)
        target — regex can't catch these because the target isn't in the AST.
      * +3 once if the file lives inside a god-node folder (top-20 cross-
        boundary coupling).
      * +min(import_count, 5) hub-file boost — files imported by many other
        files often document architectural references in their comments.

    Score governs ordering within the emission cap, but the base score
    guarantees full coverage of every folder.
    """
    from codebeacon.graph.analyze import (
        god_nodes as _god_nodes,
        hub_files as _hub_files,
        _infer_project_paths,
    )

    project_paths = _infer_project_paths(G)

    file_score: dict[str, int] = defaultdict(int)
    file_node: dict[str, str] = {}
    file_framework: dict[str, str] = {}

    external_nodes = {
        n for n, d in G.nodes(data=True) if d.get("type") == "external"
    }

    # Base score: any source-bearing, non-external node gives its file a +1.
    # Done in a single pass that also records the first real node per file
    # and the file's framework label.
    for node_id, data in G.nodes(data=True):
        if data.get("type") == "external":
            continue
        sf = data.get("source_file", "")
        if not sf:
            continue
        if sf not in file_score:
            file_score[sf] = 1
        file_node.setdefault(sf, node_id)
        if sf not in file_framework:
            fw = data.get("framework") or data.get("project") or ""
            if fw:
                file_framework[sf] = fw

    # +2 per edge into an external (unresolved) target.
    for src, tgt, edata in G.edges(data=True):
        if tgt in external_nodes:
            src_data = G.nodes.get(src, {})
            sf = src_data.get("source_file") or edata.get("source_file") or ""
            if not sf:
                continue
            file_score[sf] = file_score.get(sf, 0) + 2
            file_node.setdefault(sf, src)
            fw = src_data.get("framework") or src_data.get("project") or ""
            if fw and sf not in file_framework:
                file_framework[sf] = fw

    god_folder_keys: set[str] = set()
    try:
        for gn in _god_nodes(G, project_paths=project_paths):
            god_folder_keys.add(f"{gn.project}/{gn.folder_path}")
    except Exception:
        pass

    god_boost_seen: set[str] = set()
    for _node_id, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        if not sf or data.get("type") == "external" or sf in god_boost_seen:
            continue
        proj = data.get("project", "")
        dirname = os.path.dirname(os.path.abspath(sf))
        if proj and proj in project_paths:
            try:
                rel = os.path.relpath(dirname, project_paths[proj])
            except ValueError:
                rel = dirname
        else:
            rel = dirname
        key = f"{proj}/{rel}"
        if key in god_folder_keys:
            file_score[sf] += 3
            god_boost_seen.add(sf)

    try:
        for hf in _hub_files(G):
            if hf.file_path:
                file_score[hf.file_path] += min(hf.import_count, 5)
    except Exception:
        pass

    candidates: list[_Candidate] = []
    for sf, score in file_score.items():
        if score <= 0:
            continue
        if sf not in file_node:
            file_node[sf] = sf
        candidates.append(_Candidate(
            file_path=sf,
            node_id=file_node[sf],
            framework=file_framework.get(sf, ""),
            score=score,
        ))
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _label_index(G: nx.DiGraph) -> dict[str, str]:
    """label → node_id for resolving edge targets named by string."""
    out: dict[str, str] = {}
    for node_id, data in G.nodes(data=True):
        label = data.get("label")
        if isinstance(label, str) and label and label not in out:
            out[label] = node_id
    return out


# Graphify-aligned relation taxonomy. Anything outside this set falls back to
# ``references`` so a hallucinating LLM cannot inject novel edge labels into
# beacon.json (downstream wiki/MCP code assumes a closed set).
ALLOWED_RELATIONS: frozenset[str] = frozenset({
    "calls",
    "implements",
    "references",
    "cites",
    "conceptually_related_to",
    "shares_data_with",
    "semantically_similar_to",
    "rationale_for",
})

ALLOWED_CONFIDENCE: frozenset[str] = frozenset({
    "EXTRACTED", "INFERRED", "AMBIGUOUS",
})

# Non-code file types the LLM may introduce as new nodes. Code nodes stay
# AST-owned — that is the invariant that keeps the graph deterministic.
ALLOWED_LLM_NODE_TYPES: frozenset[str] = frozenset({
    "concept", "document", "paper",
})


def _normalize_relation(raw: Optional[str]) -> str:
    rel = (raw or "").strip().lower()
    if rel in ALLOWED_RELATIONS:
        return rel
    return "references"


def _normalize_confidence(raw: Optional[str]) -> str:
    conf = (raw or "").strip().upper()
    if conf in ALLOWED_CONFIDENCE:
        return conf
    return "INFERRED"


def _coerce_score(raw: object, default: float = 0.7) -> float:
    """Coerce ``raw`` into a [0.0, 1.0] confidence_score.

    Agents occasionally emit ``null``, strings (``"0.9"``), or out-of-range
    values; calling ``float(None)`` would raise ``TypeError`` and abort the
    whole apply step. This helper falls back to ``default`` whenever the
    value is unusable.
    """
    if raw is None:
        return default
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return default
    if score != score:  # NaN guard
        return default
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _merge_edge(
    G: nx.DiGraph,
    label_idx: dict[str, str],
    source_node_id: str,
    target_name: str,
    relation: str = "references",
    score: float = 0.7,
    confidence: str = "INFERRED",
) -> bool:
    if not _is_type_name(target_name):
        return False
    if source_node_id not in G:
        return False
    target_id = label_idx.get(target_name, target_name)
    source_file = G.nodes[source_node_id].get("source_file", "")
    if target_id not in G:
        G.add_node(
            target_id,
            label=target_name,
            type="external",
            source_file="",
            line=0,
            project="",
        )
    if G.has_edge(source_node_id, target_id):
        return False
    G.add_edge(
        source_node_id,
        target_id,
        relation=_normalize_relation(relation),
        confidence=_normalize_confidence(confidence),
        confidence_score=float(score),
        source_file=source_file,
    )
    return True


def _merge_node(
    G: nx.DiGraph,
    label_idx: dict[str, str],
    node_id: str,
    label: str,
    file_type: str,
    source_file: str,
) -> bool:
    """Add an LLM-contributed node iff its file_type is non-code and the id is fresh.

    Code nodes always come from AST extraction; allowing the LLM to mint them
    would let hallucinated symbols slip into beacon.json. Concept/document/paper
    nodes have no AST owner, so the LLM is the only producer.

    Updates ``label_idx`` in place when the node is added so subsequent edges
    in the same chunk can resolve targets by label.
    """
    ftype = (file_type or "").strip().lower()
    if ftype not in ALLOWED_LLM_NODE_TYPES:
        return False
    if not node_id or not label:
        return False
    if node_id in G:
        return False
    G.add_node(
        node_id,
        label=label,
        type=ftype,
        source_file=source_file or "",
        line=0,
        project="",
    )
    label_idx.setdefault(label, node_id)
    return True


def _reapply_archive(G: nx.DiGraph, archive: list[dict]) -> tuple[int, list[dict]]:
    """Replay every archived node + edge onto the fresh graph (idempotent).

    Returns ``(reapplied, kept_archive)``. Archive entries whose source node
    is missing from the graph (after node replay) are dropped from
    ``kept_archive`` — they correspond to deleted code and would otherwise
    stick around forever, polluting the dedup set.

    Backward-compat: 0.3.1-format entries carry only ``edges`` (no
    ``nodes``/``hyperedges`` keys); those keys default to ``[]`` so the same
    replay code path handles both formats. Hyperedges are persisted in the
    archive but not yet projected into the graph — see ``apply()`` for the
    pending schema work.
    """
    label_idx = _label_index(G)
    reapplied = 0
    kept: list[dict] = []
    # Pass 1: replay nodes so subsequent edge targets can resolve to them.
    # This must run for every entry, even ones whose source is missing —
    # a concept node from chunk A may be referenced by an edge from chunk B
    # whose source is still alive.
    for entry in archive:
        for node in entry.get("nodes") or []:
            _merge_node(
                G, label_idx,
                node_id=node.get("id", ""),
                label=node.get("label", ""),
                file_type=node.get("file_type", ""),
                source_file=node.get("source_file", ""),
            )
    # Pass 2: replay edges, drop entries whose source is missing.
    for entry in archive:
        source = entry.get("source_node_id")
        if not source or source not in G:
            continue
        kept.append(entry)
        for edge in entry.get("edges") or []:
            target = (edge or {}).get("target_name")
            if not target:
                continue
            if _merge_edge(
                G, label_idx, source, target,
                relation=edge.get("relation") or "references",
                score=float(edge.get("confidence_score", 0.7)),
                confidence=edge.get("confidence") or "INFERRED",
            ):
                reapplied += 1
    return (reapplied, kept)


_CHUNK_RE = re.compile(r"^chunk_(\d+)\.jsonl$")


def _chunk_filename(idx: int) -> str:
    return f"chunk_{idx:03d}.jsonl"


def _highest_chunk_index(directory: Path) -> int:
    """Largest chunk_NNN found in *directory*, or 0 if none."""
    if not directory.exists():
        return 0
    top = 0
    for path in directory.glob("chunk_*.jsonl"):
        m = _CHUNK_RE.match(path.name)
        if not m:
            continue
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        if n > top:
            top = n
    return top


# ── Public API ────────────────────────────────────────────────────────────────

def prepare(
    beacon_dir: str | Path,
    max_tasks: int = 0,
    chunk_size: int = 20,
) -> PrepareResult:
    """Re-apply archive and emit chunked tasks files for new candidates.

    Args:
        beacon_dir: path to the ``.codebeacon`` directory.
        max_tasks: cap on new tasks emitted this run; ``0`` (default) means
            no cap — every scored candidate is emitted. The scorer gives a
            base score of 1 to every source-bearing file, so coverage spans
            every folder.
        chunk_size: tasks per chunk file (default 20).

    Returns:
        :class:`PrepareResult` with the pending directory, counts, and the
        size of the durable archive after pruning.

    Raises:
        FileNotFoundError: when ``beacon.json`` is missing.
    """
    from codebeacon.graph.write import load_beacon, write_beacon

    beacon_dir = Path(beacon_dir)
    beacon_path = beacon_dir / "beacon.json"
    if not beacon_path.exists():
        raise FileNotFoundError(
            f"{beacon_path} not found — run `codebeacon scan` or `codebeacon sync` first."
        )

    _migrate_legacy_archive(beacon_dir)

    G, _meta = load_beacon(beacon_path)
    archive = _read_archive(beacon_dir)
    pre_count = len(archive)
    reapplied, kept_archive = _reapply_archive(G, archive)
    pruned = pre_count - len(kept_archive)

    # If we pruned anything, rewrite the archive to drop stale entries.
    # Coalesce everything into a single _legacy.jsonl file for the kept
    # entries — the chunked layout is created on the next apply().
    if pruned > 0:
        odir = _original_dir(beacon_dir)
        odir.mkdir(parents=True, exist_ok=True)
        for path in odir.glob("*.jsonl"):
            path.unlink()
        legacy_path = odir / LEGACY_MIGRATED_NAME
        with open(legacy_path, "w", encoding="utf-8") as fh:
            for entry in kept_archive:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if reapplied:
        write_beacon(G, beacon_dir, force=True)

    done_task_ids = {e.get("task_id") for e in kept_archive if e.get("task_id")}

    # Clear any prior pending/ + results/ from a previous incomplete cycle
    # so the agent doesn't pick up stale chunks.
    pdir = _pending_dir(beacon_dir)
    rdir = _results_dir(beacon_dir)
    if pdir.exists():
        for path in pdir.glob("chunk_*.jsonl"):
            path.unlink()
    if rdir.exists():
        for path in rdir.glob("chunk_*.jsonl"):
            path.unlink()
    pdir.mkdir(parents=True, exist_ok=True)

    chunk_size = max(1, chunk_size)
    written = 0
    chunks = 0
    current_chunk: list[dict] = []

    # Chunk numbering is monotonic across the lifetime of this .codebeacon
    # directory: it picks up where the durable archive in original/ left off.
    # That way apply() never overwrites an existing original/chunk_NNN.jsonl
    # when this prepare run emits new chunks.
    chunk_base = _highest_chunk_index(_original_dir(beacon_dir))

    def _flush_chunk() -> None:
        nonlocal chunks, current_chunk
        if not current_chunk:
            return
        chunks += 1
        path = pdir / _chunk_filename(chunk_base + chunks)
        with open(path, "w", encoding="utf-8") as fh:
            for task in current_chunk:
                fh.write(json.dumps(task, ensure_ascii=False) + "\n")
        current_chunk = []

    for cand in _pick_candidates(G):
        if max_tasks > 0 and written >= max_tasks:
            break
        excerpt = _read_excerpt(cand.file_path)
        if not excerpt:
            continue
        tid = _task_id(cand.file_path, cand.node_id, excerpt)
        if tid in done_task_ids:
            continue
        task = {
            "task_id": tid,
            "source_node_id": cand.node_id,
            "file_path": cand.file_path,
            "framework": cand.framework,
            "excerpt": excerpt,
            "hint": (
                "List explicit class/type/service references that appear in "
                "comments, docstrings, or annotations — not in code logic."
            ),
        }
        current_chunk.append(task)
        written += 1
        if len(current_chunk) >= chunk_size:
            _flush_chunk()

    _flush_chunk()

    return PrepareResult(
        pending_dir=pdir,
        new_tasks=written,
        chunks=chunks,
        reapplied_edges=reapplied,
        pruned_archive=pruned,
        archive_size=len(kept_archive),
    )


def _snapshot_beacon(beacon_path: Path) -> Optional[Path]:
    """Copy ``beacon.json`` to ``beacon.json.bak`` before semantic overwrite.

    Mirrors graphify's ``backup_if_protected`` behaviour (graphify 0.8.13
    #834): semantic and curated edges represent work the user can't easily
    reconstruct, so we keep one rolling backup in case the merged graph
    ends up worse than the AST-only baseline. The shrink guard in
    :func:`graph.write.write_beacon` already catches a strictly smaller
    graph, but the snapshot covers same-size graphs whose edges changed
    semantically.

    Returns the snapshot path, or ``None`` if the source doesn't exist or
    the copy itself failed (best-effort — never block the apply pipeline).
    """
    if not beacon_path.exists():
        return None
    snapshot = beacon_path.with_suffix(beacon_path.suffix + ".bak")
    try:
        shutil.copy2(beacon_path, snapshot)
        return snapshot
    except OSError:
        return None


def apply(beacon_dir: str | Path) -> ApplyResult:
    """Merge every ``results/chunk_*.jsonl`` into ``beacon.json``.

    For each chunk that yielded at least one valid result row, the
    corresponding ``pending/chunk_*.jsonl`` is **moved** to
    ``original/chunk_*.jsonl`` with the inferred edges spliced into each
    task record. The ``results/`` file is deleted afterwards. Chunks with
    no matching pending file are still archived from their result data
    alone (defensive — covers manual editing).

    Returns counts and the resulting archive size.
    """
    from codebeacon.graph.write import load_beacon, write_beacon
    from codebeacon.graph.cluster import cluster, apply_communities

    beacon_dir = Path(beacon_dir)
    beacon_path = beacon_dir / "beacon.json"
    if not beacon_path.exists():
        raise FileNotFoundError(f"{beacon_path} not found.")

    _migrate_legacy_archive(beacon_dir)

    rdir = _results_dir(beacon_dir)
    pdir = _pending_dir(beacon_dir)
    odir = _original_dir(beacon_dir)
    odir.mkdir(parents=True, exist_ok=True)

    if not rdir.exists() or not any(rdir.glob("chunk_*.jsonl")):
        raise FileNotFoundError(
            f"No result chunks under {rdir} — the skill must write "
            f"semantic/results/chunk_NNN.jsonl files first."
        )

    # One-shot backup of the pre-semantic beacon. Cheap (single file copy),
    # gives the user something to diff against if the merged graph turns
    # out worse than the AST baseline.
    _snapshot_beacon(beacon_path)

    G, _meta = load_beacon(beacon_path)
    label_idx = _label_index(G)

    applied = 0
    skipped = 0
    chunks_archived = 0

    for result_path in sorted(rdir.glob("chunk_*.jsonl")):
        chunk_name = result_path.name
        results_by_tid: dict[str, dict] = {}
        for obj in _iter_jsonl(result_path):
            tid = obj.get("task_id")
            if tid:
                results_by_tid[tid] = obj

        # Pull the original task spec (preserves file_path / excerpt for
        # auditability of the archive).
        pending_path = pdir / chunk_name
        pending_tasks: dict[str, dict] = {}
        if pending_path.exists():
            for task in _iter_jsonl(pending_path):
                tid = task.get("task_id")
                if tid:
                    pending_tasks[tid] = task

        archive_lines: list[dict] = []

        # Pass 1 within this chunk: register LLM-contributed nodes BEFORE
        # edges, so edges in the same result can reference fresh concept ids.
        kept_nodes_by_tid: dict[str, list[dict]] = {}
        for tid, obj in results_by_tid.items():
            kept_nodes: list[dict] = []
            for node in obj.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                nid = node.get("id", "")
                if _merge_node(
                    G, label_idx,
                    node_id=nid,
                    label=node.get("label", ""),
                    file_type=node.get("file_type", ""),
                    source_file=node.get("source_file", ""),
                ):
                    kept_nodes.append({
                        "id": nid,
                        "label": node.get("label", ""),
                        "file_type": node.get("file_type", ""),
                        "source_file": node.get("source_file", ""),
                    })
            if kept_nodes:
                kept_nodes_by_tid[tid] = kept_nodes

        for tid, obj in results_by_tid.items():
            source = obj.get("source_node_id")
            if not source or source not in G:
                skipped += 1
                continue
            task_spec = pending_tasks.get(tid) or {}
            kept_edges: list[dict] = []
            for edge in obj.get("edges") or []:
                if not isinstance(edge, dict):
                    skipped += 1
                    continue
                target = edge.get("target_name")
                if not target or not isinstance(target, str):
                    skipped += 1
                    continue
                score = _coerce_score(edge.get("confidence_score"), default=0.7)
                if _merge_edge(
                    G, label_idx, source, target,
                    relation=edge.get("relation") or "references",
                    score=score,
                    confidence=edge.get("confidence") or "INFERRED",
                ):
                    kept_edges.append({
                        "target_name": target,
                        "relation": _normalize_relation(edge.get("relation")),
                        "confidence": _normalize_confidence(edge.get("confidence")),
                        "confidence_score": score,
                    })
                    applied += 1
                else:
                    skipped += 1
            # Hyperedges: archive but do NOT project into the graph yet.
            # beacon.json, build_graph, wiki, obsidian, HTML viewer, and MCP
            # all need schema work first — that lands in a follow-up.
            kept_hyperedges = [
                {
                    "id": he.get("id", ""),
                    "label": he.get("label", ""),
                    "nodes": [n for n in (he.get("nodes") or []) if isinstance(n, str)],
                    "relation": he.get("relation", "participate_in"),
                    "confidence": _normalize_confidence(he.get("confidence")),
                    "confidence_score": _coerce_score(he.get("confidence_score"), default=0.7),
                }
                for he in (obj.get("hyperedges") or [])
                if isinstance(he, dict) and he.get("nodes")
            ]
            archive_lines.append({
                "task_id": tid,
                "source_node_id": source,
                "file_path": task_spec.get("file_path", ""),
                "nodes": kept_nodes_by_tid.get(tid, []),
                "edges": kept_edges,
                "hyperedges": kept_hyperedges,
            })

        if archive_lines:
            archive_path = odir / chunk_name
            with open(archive_path, "w", encoding="utf-8") as fh:
                for entry in archive_lines:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            chunks_archived += 1

        # Drop the result + pending files now that the chunk is archived.
        try:
            result_path.unlink()
        except OSError:
            pass
        if pending_path.exists():
            try:
                pending_path.unlink()
            except OSError:
                pass

    archive_size = len(_read_archive(beacon_dir))

    if applied == 0:
        return ApplyResult(
            applied=0, skipped=skipped,
            chunks_archived=chunks_archived,
            archive_size=archive_size,
        )

    communities = cluster(G)
    apply_communities(G, communities)
    write_beacon(G, beacon_dir, force=True)

    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.contextmap.generator import generate_context_map
    from codebeacon.export.callflow_html import write_callflow_html
    from codebeacon.export.tree_html import write_tree_html

    generate_wiki(G, communities, str(beacon_dir))
    try:
        generate_obsidian_vault(G, communities, str(beacon_dir))
    except Exception:
        pass
    try:
        generate_context_map(G=G, output_dir=str(beacon_dir), projects=[], obsidian_dir=None)
    except Exception:
        pass
    # Regenerate the visual exports so callflow.html's cross-community table
    # and beacon.html's tree pick up the freshly-inferred edges. Without this,
    # the HTML on disk still reflects the AST-only graph and misses the new
    # `references`, `cites`, `conceptually_related_to`, etc. edges the agent
    # just produced — analogous to graphify 0.8.12 #925 (Relationships
    # section stayed empty when downstream readers used stale community
    # state).
    try:
        write_callflow_html(G, beacon_dir)
    except (OSError, ValueError):
        pass
    try:
        write_tree_html(G, beacon_dir)
    except (OSError, ValueError):
        pass

    return ApplyResult(
        applied=applied,
        skipped=skipped,
        chunks_archived=chunks_archived,
        archive_size=archive_size,
    )
