"""AI-semantic pipeline: prepare candidate tasks + apply LLM results.

This module replaces the in-process LLM call that used to live in
``codebeacon.extract.semantic``. Model choice now belongs to the agent
running the ``/codebeacon`` skill — codebeacon only does the AST-side work
and consumes the results.

Pipeline shape:

  1. ``prepare()`` reads ``beacon.json``, re-applies every archived edge
     in ``semantic/original.jsonl`` to the fresh graph (so rescans don't
     lose prior inferences), then picks the candidate files that are NOT
     yet in the archive and writes them to ``semantic-tasks.jsonl``.

  2. The skill (Claude Code) loops over the tasks, runs the analysis with
     whatever model the agent is currently running on, and appends results
     to ``semantic-results.jsonl``.

  3. ``apply()`` merges the results into ``beacon.json`` (as ``references``
     edges, ``confidence=INFERRED``, ``confidence_score=0.7``), appends
     them to the archive, clears the pending tasks/results files, and
     regenerates wiki + obsidian + context map.

Files:
  .codebeacon/semantic-tasks.jsonl     (pending — new since last archive)
  .codebeacon/semantic-results.jsonl   (skill writes LLM output here)
  .codebeacon/semantic/original.jsonl  (durable archive of applied results)

Schema:
  task   : {task_id, source_node_id, file_path, framework, excerpt, hint}
  result : {task_id, source_node_id, edges: [{target_name, relation?, confidence_score?}]}

``task_id`` is the SHA1 of (file_path + node_id) so prepare/apply are
idempotent and partial result files can be safely re-applied.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import networkx as nx

MAX_EXCERPT_CHARS = 4000
TASKS_FILENAME = "semantic-tasks.jsonl"
RESULTS_FILENAME = "semantic-results.jsonl"
ARCHIVE_DIRNAME = "semantic"
ARCHIVE_FILENAME = "original.jsonl"


# ── Public dataclasses ────────────────────────────────────────────────────────

@dataclass
class PrepareResult:
    tasks_path: Path
    new_tasks: int
    reapplied_edges: int
    archive_size: int


@dataclass
class ApplyResult:
    applied: int
    skipped: int
    archive_size: int


# ── Internals ─────────────────────────────────────────────────────────────────

@dataclass
class _Candidate:
    file_path: str
    node_id: str
    framework: str
    score: int


def _archive_path(beacon_dir: Path) -> Path:
    return beacon_dir / ARCHIVE_DIRNAME / ARCHIVE_FILENAME


def _read_archive(beacon_dir: Path) -> list[dict]:
    path = _archive_path(beacon_dir)
    if not path.exists():
        return []
    entries: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _append_archive(beacon_dir: Path, entry: dict) -> None:
    path = _archive_path(beacon_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _task_id(file_path: str, node_id: str) -> str:
    return hashlib.sha1(f"{file_path}|{node_id}".encode("utf-8")).hexdigest()[:16]


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


def _pick_candidates(G: nx.DiGraph) -> list[_Candidate]:
    """Score files and return them ordered by descending score.

    Signal sources (additive):
      * +2 per edge from a node in this file to an ``external`` (unresolved)
        target — regex can't catch these because the target isn't in the AST.
      * +3 once if the file lives inside a god-node folder.
      * +min(import_count, 5) hub-file boost — a file imported by many other
        files often documents architectural references in its comments.

    Well-resolved graphs (no ``external`` nodes at all) still surface
    candidates via the god-folder and hub signals — this is the common case
    once symbol resolution has wired everything up.
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

    for src, tgt, edata in G.edges(data=True):
        if tgt in external_nodes:
            src_data = G.nodes.get(src, {})
            sf = src_data.get("source_file") or edata.get("source_file") or ""
            if not sf:
                continue
            file_score[sf] += 2
            file_node.setdefault(sf, src)
            fw = src_data.get("framework") or src_data.get("project") or ""
            if fw and sf not in file_framework:
                file_framework[sf] = fw

    for node_id, data in G.nodes(data=True):
        if data.get("type") == "external":
            continue
        sf = data.get("source_file", "")
        if not sf:
            continue
        file_node.setdefault(sf, node_id)
        if sf not in file_framework:
            fw = data.get("framework") or data.get("project") or ""
            if fw:
                file_framework[sf] = fw

    # ── God-folder boost. Match by (project, relative folder), which is the
    # same key shape :func:`god_nodes` uses internally. Before the fix this
    # compared an abs path against a rel path and silently never matched.
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

    # ── Hub-file boost.
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
            # A hub-only candidate could miss a node mapping if no node lives
            # inside the file — fall back to the file path as the synthetic
            # source_node_id so the apply step still has something to attach
            # the inferred edges to (the agent ultimately writes results
            # keyed by the task_id we emit).
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


def _merge_edge(
    G: nx.DiGraph,
    label_idx: dict[str, str],
    source_node_id: str,
    target_name: str,
    relation: str = "references",
    score: float = 0.7,
) -> bool:
    """Add a single inferred edge. Returns True if added, False if skipped."""
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
        relation=relation or "references",
        confidence="INFERRED",
        confidence_score=float(score),
        source_file=source_file,
    )
    return True


def _reapply_archive(G: nx.DiGraph, archive: list[dict]) -> int:
    """Replay every archived result onto the fresh graph. Idempotent.

    Rescans rebuild ``beacon.json`` from scratch, so without this step the
    AI inferences would silently disappear between runs.
    """
    label_idx = _label_index(G)
    reapplied = 0
    for entry in archive:
        source = entry.get("source_node_id")
        if not source:
            continue
        for edge in entry.get("edges") or []:
            target = (edge or {}).get("target_name")
            if not target:
                continue
            if _merge_edge(
                G, label_idx, source, target,
                relation=edge.get("relation") or "references",
                score=float(edge.get("confidence_score", 0.7)),
            ):
                reapplied += 1
    return reapplied


# ── Public API ────────────────────────────────────────────────────────────────

def prepare(beacon_dir: str | Path, max_tasks: int = 50) -> PrepareResult:
    """Re-apply archive and emit a tasks file for any NEW candidates.

    Raises ``FileNotFoundError`` if ``beacon.json`` is missing — the caller
    is expected to have run a scan first.
    """
    from codebeacon.graph.write import load_beacon, write_beacon

    beacon_dir = Path(beacon_dir)
    beacon_path = beacon_dir / "beacon.json"
    if not beacon_path.exists():
        raise FileNotFoundError(
            f"{beacon_path} not found — run `codebeacon scan` or `codebeacon sync` first."
        )

    G, _meta = load_beacon(beacon_path)
    archive = _read_archive(beacon_dir)
    reapplied = _reapply_archive(G, archive)
    if reapplied:
        # Persist the rehydrated graph so downstream readers (wiki, MCP) see
        # the archived edges even if the user only ran prepare.
        write_beacon(G, beacon_dir, force=True)

    done_task_ids = {entry.get("task_id") for entry in archive if entry.get("task_id")}

    tasks_path = beacon_dir / TASKS_FILENAME
    written = 0
    with open(tasks_path, "w", encoding="utf-8") as fh:
        for cand in _pick_candidates(G):
            if written >= max_tasks:
                break
            tid = _task_id(cand.file_path, cand.node_id)
            if tid in done_task_ids:
                continue
            excerpt = _read_excerpt(cand.file_path)
            if not excerpt:
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
            fh.write(json.dumps(task, ensure_ascii=False) + "\n")
            written += 1

    return PrepareResult(
        tasks_path=tasks_path,
        new_tasks=written,
        reapplied_edges=reapplied,
        archive_size=len(archive),
    )


def apply(beacon_dir: str | Path) -> ApplyResult:
    """Merge ``semantic-results.jsonl`` into ``beacon.json`` and archive it.

    After merge:
      * results & pending-tasks files are cleared (their content lives in
        the archive now);
      * wiki, obsidian vault, and context map are regenerated so downstream
        artifacts reflect the new edges.

    Returns counts and the resulting archive size.
    """
    from codebeacon.graph.write import load_beacon, write_beacon
    from codebeacon.graph.cluster import cluster, apply_communities

    beacon_dir = Path(beacon_dir)
    beacon_path = beacon_dir / "beacon.json"
    results_path = beacon_dir / RESULTS_FILENAME
    tasks_path = beacon_dir / TASKS_FILENAME
    if not beacon_path.exists():
        raise FileNotFoundError(f"{beacon_path} not found.")
    if not results_path.exists():
        raise FileNotFoundError(
            f"{results_path} not found — the skill must write LLM results here first."
        )

    G, _meta = load_beacon(beacon_path)
    label_idx = _label_index(G)

    applied = 0
    skipped = 0
    archive_appends: list[dict] = []

    with open(results_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            source = obj.get("source_node_id")
            task_id = obj.get("task_id")
            if not source or source not in G:
                skipped += 1
                continue
            kept_edges: list[dict] = []
            for edge in obj.get("edges") or []:
                target = (edge or {}).get("target_name")
                if not target:
                    skipped += 1
                    continue
                if _merge_edge(
                    G, label_idx, source, target,
                    relation=edge.get("relation") or "references",
                    score=float(edge.get("confidence_score", 0.7)),
                ):
                    kept_edges.append({
                        "target_name": target,
                        "relation": edge.get("relation") or "references",
                        "confidence_score": float(edge.get("confidence_score", 0.7)),
                    })
                    applied += 1
                else:
                    skipped += 1
            # Archive every task_id we saw — including "no inferences" responses.
            # Otherwise the next semantic-prepare would re-emit the same task
            # because it has no record that the agent already processed it.
            if task_id:
                archive_appends.append({
                    "task_id": task_id,
                    "source_node_id": source,
                    "edges": kept_edges,
                })

    for entry in archive_appends:
        _append_archive(beacon_dir, entry)

    # Always clear the pending files — even when nothing applied, the user
    # has decided "this batch is done" by invoking apply. Leaving stale
    # tasks/results around would cause the next prepare to confuse the skill.
    try:
        results_path.unlink()
    except OSError:
        pass
    try:
        tasks_path.unlink()
    except OSError:
        pass

    archive_size = len(_read_archive(beacon_dir))

    if applied == 0:
        return ApplyResult(applied=0, skipped=skipped, archive_size=archive_size)

    communities = cluster(G)
    apply_communities(G, communities)
    write_beacon(G, beacon_dir, force=True)

    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.contextmap.generator import generate_context_map

    generate_wiki(G, communities, str(beacon_dir))
    try:
        generate_obsidian_vault(G, communities, str(beacon_dir))
    except Exception:
        pass
    try:
        generate_context_map(G=G, output_dir=str(beacon_dir), projects=[], obsidian_dir=None)
    except Exception:
        pass

    return ApplyResult(applied=applied, skipped=skipped, archive_size=archive_size)
