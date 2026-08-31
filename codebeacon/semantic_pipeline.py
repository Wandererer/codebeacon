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
  task   : {task_id, source_node_id, file_path, framework, excerpt, hint,
            excerpt_truncated, excerpt_chars, file_chars}
  result : {task_id, source_node_id, edges: [{target_name, relation?, confidence_score?}]}
  original: {task_id, source_node_id, file_path?, edges: [...]}

``task_id`` is ``SHA1(file_path + node_id + content_hash[:8])[:16]``, where
``content_hash`` digests the **whole file** — so an edit anywhere re-dispatches
it. (Through 0.7.0 the digest covered only the first ``MAX_EXCERPT_CHARS``,
which made the id blind to every change past that cut; 0.7.1 invalidates prior
task_ids once, and the affected files are re-analysed on the next prepare.)

A file larger than ``MAX_EXCERPT_CHARS`` is handed to the agent as a head+tail
slice with the elision marked inline, and the task says so explicitly via
``excerpt_truncated`` / ``excerpt_chars`` / ``file_chars``.

Everything under ``semantic/`` is agent-authored or hand-editable, so both
ingest paths (``apply`` and ``_reapply_archive``) validate every row through
``_validate_llm_node`` / ``_validate_llm_edge``: a malformed row is skipped and
counted, never allowed to abort the merge or reach beacon.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import networkx as nx

from codebeacon.common.safety import sanitize_label
from codebeacon.common.types import KNOWLEDGE_NODE_TYPE
from codebeacon.diagnostics import SemanticApplyStats

MAX_EXCERPT_CHARS = 4000

# Head/tail split of a truncated excerpt. References cluster in the imports at
# the top of a file and in comments throughout, so a pure prefix cut drops the
# tail of a large file entirely (G-0949-21: 98.3% of a 231k-char Java file).
_EXCERPT_HEAD_RATIO = 0.7

# Bounds on agent-authored identifiers. An LLM (or a hand-edited archive) can
# emit anything; these caps stop one row from inflating beacon.json and from
# carrying an unbounded label into wiki text and MCP output.
MAX_LLM_ID_CHARS = 200
MAX_LLM_LABEL_CHARS = 512
MAX_LLM_TARGET_CHARS = 200

# Provenance stamped on an `external` node this pipeline mints for an edge
# target the AST never saw: "literal" when the name occurs in the analysed
# source, "unverified" when it does not.
_VERIFICATION_VALUES: frozenset[str] = frozenset({"literal", "unverified"})

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
    # Hallucination accounting (since 0.6.0). See codebeacon.diagnostics.
    # ``stats`` is None for legacy callers (tests) that don't pass an
    # accumulator; the CLI always populates it.
    stats: Optional["object"] = None  # diagnostics.SemanticApplyStats
    # Node contributions, counted separately from ``applied`` (which stays
    # edge-only for callers that print it). A result row carrying a concept
    # node and no edges is a real contribution and must persist — see
    # :func:`apply`'s persistence gate.
    nodes_applied: int = 0


@dataclass
class SemanticIngestStats(SemanticApplyStats):
    """``SemanticApplyStats`` plus the ingest-validation counters.

    Kept as a subclass rather than new fields on the base so the extra
    counters flow through ``asdict`` into ``semantic-stats.json`` unchanged,
    and so an older reader of that file simply sees additional keys.
    """
    # Rows an agent (or a hand-edited archive) emitted in an unusable shape:
    # a non-string id/label, an unhashable label, an oversized identifier.
    # Each is skipped individually — one bad row must never abort a merge.
    nodes_rejected_invalid: int = 0
    edges_rejected_invalid: int = 0
    # Nodes that actually reached the graph this run.
    nodes_accepted: int = 0
    # Result chunks whose file yielded no usable row under any parse strategy.
    chunks_unrecoverable: int = 0
    # Edge targets that minted a NEW external node, split by whether the name
    # literally occurs in the analysed source (see ``verification`` node attr).
    edge_targets_literal: int = 0
    edge_targets_unverified: int = 0


@dataclass
class _ReplayStats:
    """Counters filled in by :func:`_reapply_archive` (optional out-param)."""
    nodes_added: int = 0
    nodes_rejected_invalid: int = 0
    edges_rejected_invalid: int = 0
    entries_rejected_invalid: int = 0


# Edges with confidence_score below this threshold are dropped during apply().
# An LLM that emits ``confidence_score: 0.3`` is admitting it doesn't know —
# letting that into the graph contradicts the "deterministic graph" promise
# that downstream wiki/MCP consumers rely on. Override with --min-confidence.
DEFAULT_MIN_CONFIDENCE_SCORE = 0.5


# ── Path helpers ──────────────────────────────────────────────────────────────

def _semantic_root(beacon_dir: Path) -> Path:
    return beacon_dir / SEMANTIC_DIRNAME


def _pending_dir(beacon_dir: Path) -> Path:
    return _semantic_root(beacon_dir) / PENDING_SUBDIR


def _results_dir(beacon_dir: Path) -> Path:
    return _semantic_root(beacon_dir) / RESULTS_SUBDIR


def _original_dir(beacon_dir: Path) -> Path:
    return _semantic_root(beacon_dir) / ORIGINAL_SUBDIR


def _archive_entry_key(line: str) -> str:
    """Stable dedup key for one archive JSONL line.

    Prefers ``task_id`` — the archive's natural primary key, mirrored by the
    ``done_task_ids`` set in :func:`prepare` — so re-running a merge cannot
    reintroduce an entry that is already present. Falls back to the raw text
    for lines without a task_id so non-conforming rows still dedupe exactly.

    Design note (BH-S4): because :func:`_migrate_legacy_archive` dedups legacy
    entries against the migration target on this key, two entries that share a
    ``task_id`` are treated as ONE — the target copy wins and the legacy copy
    is dropped whole. If a non-deterministic LLM re-analysed the same unchanged
    file/node/excerpt across a 0.3.x run and a newer run, both entries carry the
    same task_id but may carry DIVERGENT edge sets; those divergent edges are
    intentionally NOT unioned. task_id is the archive's primary key, so a single
    winner keeps the archive consistent with ``done_task_ids``, and any edges
    lost from the dropped copy are regenerable inferred edges on the next
    prepare/apply cycle.
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return line
    if isinstance(obj, dict):
        tid = obj.get("task_id")
        if tid:
            return f"tid:{tid}"
    return line


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
        # Merge legacy into target. This must be BOTH crash-safe and
        # idempotent: a plain append-then-unlink double-appends every legacy
        # entry if the process dies after the append but before the unlink,
        # because the re-run re-enters this branch and appends again (BH-S4).
        # Fix: build the merged content in memory (skipping legacy entries
        # already present in target, keyed on task_id), write it to a temp
        # file, os.replace it onto target atomically, and only then unlink
        # the legacy source. A crash anywhere in that sequence leaves target
        # either untouched or fully merged — never doubled — so re-running is
        # a no-op that finishes the migration.
        merged: list[str] = []
        seen: set[str] = set()
        with open(target, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                merged.append(line)
                seen.add(_archive_entry_key(line))
        with open(legacy, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                key = _archive_entry_key(line)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(line)
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for line in merged:
                fh.write(line + "\n")
        os.replace(tmp, target)
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


def _task_id(file_path: str, node_id: str, content_hash: str) -> str:
    """task_id is content-aware: changes when the analysed FILE changes.

    ``content_hash`` digests the whole file, not the excerpt handed to the
    agent. Hashing the excerpt made the id blind to every edit past
    :data:`MAX_EXCERPT_CHARS`, so a large file could be rewritten wholesale and
    never be re-dispatched (G-0949-21). Callers pass
    :attr:`_Excerpt.content_hash`.
    """
    fingerprint = f"{file_path}|{node_id}|{content_hash}"
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]


@dataclass
class _Excerpt:
    """The slice of a file handed to the agent, plus what was left out."""

    text: str            # what the agent sees (already sliced)
    file_chars: int      # size of the whole file
    truncated: bool
    content_hash: str    # digest of the WHOLE file — drives task_id


def _slice_excerpt(text: str, budget: int = MAX_EXCERPT_CHARS) -> tuple[str, bool]:
    """Return ``(excerpt, truncated)`` — a head+tail slice within ``budget``.

    A plain prefix cut throws away the end of a large file entirely, and
    references cluster at both ends: imports and class declarations at the top,
    explanatory comments and helper usage at the bottom. So an oversized file
    contributes a head and a tail with an explicit elision marker between them,
    which also tells the reader (human or agent) that content is missing at
    exactly the point where it is missing.
    """
    if len(text) <= budget:
        return text, False
    marker_template = (
        "\n\n… [codebeacon: {n} of {total} characters elided — "
        "this excerpt is the head and tail of the file] …\n\n"
    )
    # Reserve room for the marker, sized with a placeholder count of the same
    # magnitude so the final string cannot exceed the budget.
    reserve = len(marker_template.format(n=len(text), total=len(text)))
    body = max(budget - reserve, 0)
    if body < 200:
        # Budget too small to be worth slicing — fall back to a plain prefix.
        return text[:budget], True
    head_len = int(body * _EXCERPT_HEAD_RATIO)
    tail_len = body - head_len
    elided = len(text) - head_len - tail_len
    marker = marker_template.format(n=elided, total=len(text))
    return text[:head_len] + marker + text[len(text) - tail_len:], True


def _read_excerpt(file_path: str) -> Optional[_Excerpt]:
    """Read ``file_path`` and return the agent-facing excerpt, or ``None``."""
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    sliced, truncated = _slice_excerpt(text)
    return _Excerpt(
        text=sliced,
        file_chars=len(text),
        truncated=truncated,
        content_hash=_excerpt_hash(text),
    )


_NEIGHBOR_CAP = 12  # avoid blowing chunk size on god-nodes


def _neighbor_context(G: nx.DiGraph, node_id: str) -> dict:
    """Return a compact (callers, callees) label snapshot for ``node_id``.

    Callers come from inbound edges (who depends on me), callees from
    outbound edges (what do I depend on). Both are deduped, capped, and
    annotated with the source-file basename so cross-language matches
    are easier for the LLM to reason about ("Foo.java" vs "foo.py").
    """
    if node_id not in G:
        return {"callers": [], "callees": []}

    def _summarise(other_id: str) -> dict:
        data = G.nodes[other_id]
        sf = data.get("source_file", "") or ""
        return {
            "label": data.get("label", other_id),
            "type": data.get("type", ""),
            "source_file": Path(sf).name if sf else "",
            "language": _infer_language(sf),
        }

    callers, callees = [], []
    seen_in: set[str] = set()
    seen_out: set[str] = set()
    for pred in G.predecessors(node_id):
        if pred in seen_in or len(callers) >= _NEIGHBOR_CAP:
            continue
        seen_in.add(pred)
        callers.append(_summarise(pred))
    for succ in G.successors(node_id):
        if succ in seen_out or len(callees) >= _NEIGHBOR_CAP:
            continue
        seen_out.add(succ)
        callees.append(_summarise(succ))
    return {"callers": callers, "callees": callees}


_EXT_TO_LANG = {
    ".py": "python", ".java": "java", ".kt": "kotlin", ".swift": "swift",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".vue": "vue", ".svelte": "svelte",
}


def _infer_language(source_file: str) -> str:
    ext = Path(source_file).suffix.lower()
    return _EXT_TO_LANG.get(ext, "")


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

    Line-oriented reading already tolerates code fences and interleaved
    narration. The one shape it cannot see is a *pretty-printed* JSON object
    or array spanning many lines, which some agents emit despite the JSONL
    instruction; every line of it fails to parse, so the file reads as empty
    and the dispatched work is discarded. When the fast path recovers nothing
    from a non-empty file we retry once over the whole text (G-0948-5).
    """
    yielded = 0
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
            yielded += 1
            yield obj

    if yielded:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for obj in _parse_whole_json(text):
        yield obj


def _strip_code_fences(text: str) -> str:
    """Drop whole-line ``` fences so a fenced document parses as JSON."""
    kept = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(kept)


def _parse_whole_json(text: str) -> list[dict]:
    """Parse ``text`` as one JSON document; return the dict rows it holds."""
    if not text.strip():
        return []
    try:
        obj = json.loads(_strip_code_fences(text))
    except (json.JSONDecodeError, ValueError, RecursionError):
        return []
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [item for item in obj if isinstance(item, dict)]
    return []


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

    # Files that are eligible to be analysed at all. The semantic pass exists to
    # infer references out of SOURCE CODE, so the overlay tiers are excluded:
    # a knowledge note already has its own linker (knowledge/link.py) reading
    # the same markdown with better-targeted heuristics, and concept/document/
    # paper nodes are LLM output, not input. This matters now that a scan
    # re-applies the knowledge overlay (R2) — without it, a 1,000-note vault
    # would dispatch 1,000 spurious tasks on the next semantic-prepare.
    analysable_files: set[str] = set()

    # Base score: any source-bearing, non-external node gives its file a +1.
    # Done in a single pass that also records the first real node per file
    # and the file's framework label.
    for node_id, data in G.nodes(data=True):
        if str(data.get("type", "")) in _NON_ANALYSABLE_NODE_TYPES:
            continue
        sf = data.get("source_file", "")
        if not sf:
            continue
        analysable_files.add(sf)
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
        # Single chokepoint: the boost passes above use ``+=`` on a defaultdict
        # and can mint an entry for a file the base pass deliberately skipped,
        # so eligibility is re-checked here rather than in each boost.
        if sf not in analysable_files:
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


def _code_source_files(G: nx.DiGraph) -> set[str]:
    """Set of ``source_file`` strings owned by real (AST) code nodes.

    LLM-minted node types (concept/document/paper) are excluded — they have
    no AST owner, so their ``source_file`` must never be allowed to collide
    with a code node's (see the G12 guard in :func:`_merge_node`).
    """
    out: set[str] = set()
    for _node_id, data in G.nodes(data=True):
        if (data.get("type") or "") in ALLOWED_LLM_NODE_TYPES:
            continue
        sf = data.get("source_file")
        if sf:
            out.add(sf)
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

# Node types whose source file is NOT a candidate for semantic analysis:
# ``external`` stubs have no file at all, the LLM-minted tiers are this
# pipeline's own output, and knowledge notes belong to the knowledge linker.
# Kept local rather than imported from graph/write.py to avoid a module cycle
# (that module mirrors the same tiering for the shrink baseline).
_NON_ANALYSABLE_NODE_TYPES: frozenset[str] = (
    ALLOWED_LLM_NODE_TYPES | {"external", KNOWLEDGE_NODE_TYPE}
)


def _normalize_relation(raw: Optional[str]) -> str:
    rel = (raw or "").strip().lower()
    if rel in ALLOWED_RELATIONS:
        return rel
    return "references"


def _classify_relation(raw: Optional[str]) -> tuple[str, bool]:
    """Return ``(normalized_label, was_known)`` for one LLM-emitted relation.

    ``was_known`` is True when the raw label matched ``ALLOWED_RELATIONS``
    exactly (after strip+lower). False means the LLM hallucinated a label
    and we coerced it to ``references`` — callers should count these so
    apply() can surface a hallucination spike instead of silently absorbing it.
    """
    rel = (raw or "").strip().lower()
    if rel in ALLOWED_RELATIONS:
        return rel, True
    return "references", False


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


# ── Ingest validation (the untrusted-input boundary) ──────────────────────────
#
# Everything under ``semantic/`` is agent-authored or hand-editable text, so it
# is untrusted input in the ordinary sense: it can be any JSON shape at all.
# Before 0.7.1 only ``file_type`` and ``source_file`` were checked, which left
# four ways for a single bad row to take down a whole run — an unhashable label
# aborted the merge on ``label_idx.setdefault``, a non-string ``file_type``
# aborted it on ``.strip()``, and a non-string or NUL-bearing label was accepted
# and then broke every later export from a durable beacon.json.
#
# Both ingest paths (``apply`` and ``_reapply_archive``) now run every node and
# edge through the same pair of validators. The contract is deliberate: a row
# that fails is SKIPPED and COUNTED, never raised — one malformed row must not
# cost the user the rest of the chunk.


def _validate_llm_node(node: object) -> Optional[dict]:
    """Return a sanitized node dict, or ``None`` when the row is unusable.

    ``id`` and ``label`` must be non-empty strings within
    :data:`MAX_LLM_ID_CHARS` / :data:`MAX_LLM_LABEL_CHARS` after
    :func:`common.safety.sanitize_label`, which is what strips the NUL bytes,
    C0 controls, and bidi marks that later break the obsidian and wiki writers.
    ``file_type`` must be a string (``_merge_node`` calls ``.strip()`` on it).
    """
    if not isinstance(node, dict):
        return None
    nid = node.get("id")
    label = node.get("label")
    if not isinstance(nid, str) or not isinstance(label, str):
        return None
    if len(nid) > MAX_LLM_ID_CHARS or len(label) > MAX_LLM_LABEL_CHARS:
        return None
    nid = sanitize_label(nid)
    label = sanitize_label(label)
    if not nid or not label:
        return None
    file_type = node.get("file_type", "")
    if not isinstance(file_type, str):
        return None
    source_file = node.get("source_file", "")
    if not isinstance(source_file, str) or len(source_file) > MAX_LLM_ID_CHARS:
        source_file = ""
    else:
        source_file = sanitize_label(source_file)
    return {
        "id": nid,
        "label": label,
        "file_type": file_type,
        "source_file": source_file,
    }


def _validate_llm_edge(edge: object) -> Optional[dict]:
    """Return a sanitized edge dict, or ``None`` when the row is unusable.

    ``target_name`` must be a bounded, non-empty string — it becomes an
    external node's label when it does not resolve, so an unbounded or
    control-bearing value would land in the graph verbatim. ``relation`` and
    ``confidence`` are dropped to ``None`` when non-string, because
    ``_classify_relation`` / ``_normalize_confidence`` call ``.strip()`` on
    them and would otherwise raise on an int.
    """
    if not isinstance(edge, dict):
        return None
    target = edge.get("target_name")
    if not isinstance(target, str) or len(target) > MAX_LLM_TARGET_CHARS:
        return None
    target = sanitize_label(target)
    if not target:
        return None
    relation = edge.get("relation")
    if not isinstance(relation, str):
        relation = None
    confidence = edge.get("confidence")
    if not isinstance(confidence, str):
        confidence = None
    # Only the two values this pipeline mints are honoured on the way back in;
    # the archive is hand-editable, and an arbitrary string here would end up
    # as a node attribute that consumers read as provenance. The isinstance
    # check has to come first: `x in frozenset` raises TypeError on an
    # unhashable x, which is the very failure mode this validator exists to
    # stop (an unhashable label aborting a whole merge — G-0918-4).
    verification = edge.get("verification")
    if not isinstance(verification, str) or verification not in _VERIFICATION_VALUES:
        verification = None
    return {
        "target_name": target,
        "relation": relation,
        "confidence": confidence,
        "confidence_score": edge.get("confidence_score"),
        "verification": verification,
    }


def _merge_edge(
    G: nx.DiGraph,
    label_idx: dict[str, str],
    source_node_id: str,
    target_name: str,
    relation: str = "references",
    score: float = 0.7,
    confidence: str = "INFERRED",
    verification: Optional[str] = None,
) -> bool:
    """Add one inferred edge. ``verification`` stamps a NEWLY MINTED target.

    An unresolved ``target_name`` mints an ``external`` node, and that node is
    the graph's only record of a name the agent supplied rather than the AST
    extracted. ``verification`` (``"literal"`` when the name occurs in the
    analysed source, ``"unverified"`` when it does not) makes the distinction
    legible to consumers instead of leaving an inferred stub indistinguishable
    from an AST-extracted unresolved import (G-0918-5). It is only applied to a
    node this call creates — an existing node's provenance is not ours to
    rewrite.
    """
    if not _is_type_name(target_name):
        return False
    if source_node_id not in G:
        return False
    target_id = label_idx.get(target_name, target_name)
    source_file = G.nodes[source_node_id].get("source_file", "")
    if target_id not in G:
        attrs = {
            "label": target_name,
            "type": "external",
            "source_file": "",
            "line": 0,
            "project": "",
        }
        if verification:
            attrs["verification"] = verification
        G.add_node(target_id, **attrs)
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


def _target_occurs_in_source(
    target: str,
    task_spec: dict,
    cache: dict[str, str],
) -> bool:
    """True when ``target`` appears literally in the analysed source text.

    Checks the excerpt first — it is already in memory and is exactly what the
    agent was shown. When the excerpt was a partial view, a name living in the
    elided middle would read as unverified even though it is right there in the
    file, so a truncated task falls back to reading the file once per run.
    """
    if not target:
        return False
    excerpt = task_spec.get("excerpt")
    if isinstance(excerpt, str) and target in excerpt:
        return True
    if not task_spec.get("excerpt_truncated"):
        return False
    file_path = task_spec.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return False
    text = cache.get(file_path)
    if text is None:
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        cache[file_path] = text
    return bool(text) and target in text


def _merge_node(
    G: nx.DiGraph,
    label_idx: dict[str, str],
    node_id: str,
    label: str,
    file_type: str,
    source_file: str,
    protected_source_files: Optional[set[str]] = None,
) -> bool:
    """Add an LLM-contributed node iff its file_type is non-code and the id is fresh.

    Code nodes always come from AST extraction; allowing the LLM to mint them
    would let hallucinated symbols slip into beacon.json. Concept/document/paper
    nodes have no AST owner, so the LLM is the only producer.

    Updates ``label_idx`` in place when the node is added so subsequent edges
    in the same chunk can resolve targets by label.

    ``protected_source_files`` is the set of code nodes' ``source_file``
    values (see :func:`_code_source_files`); when ``None`` it is derived from
    ``G`` on the fly. It powers the G12 guard below.
    """
    ftype = (file_type or "").strip().lower()
    if ftype not in ALLOWED_LLM_NODE_TYPES:
        return False
    if not node_id or not label:
        return False
    if node_id in G:
        return False
    # G12 guard: a concept/document/paper node's source_file is an
    # unverifiable LLM string. If it is an absolute path, or collides with a
    # real code node's source_file, obsidian's Step-6 "same source_file"
    # dedup would group the LLM note with the real code note and delete the
    # loser — and the LLM note can win _pick_primary, destroying the real
    # file's note. Blank those out (a legitimate relative doc path such as
    # "docs/oauth.md" is kept). This also stops foreign paths (e.g.
    # /etc/passwd) from being stored verbatim in the graph.
    sf = source_file or ""
    if sf:
        protected = protected_source_files
        if protected is None:
            protected = _code_source_files(G)
        if os.path.isabs(sf) or sf in protected:
            sf = ""
    G.add_node(
        node_id,
        label=label,
        type=ftype,
        source_file=sf,
        line=0,
        project="",
    )
    label_idx.setdefault(label, node_id)
    return True


def _entry_list(entry: dict, key: str) -> list:
    """Return ``entry[key]`` when it is a list, else ``[]``.

    The archive is durable plain JSONL that survives every rescan — a 0.3.x
    migration, a hand-edit, or a partial write can leave ``nodes`` as a dict or
    a string. Iterating a dict yields its keys, so the old
    ``entry.get(key) or []`` handed ``str`` objects to ``node.get`` and aborted
    ``prepare()`` outright (G-0932-3).
    """
    value = entry.get(key)
    return value if isinstance(value, list) else []


def _reapply_archive(
    G: nx.DiGraph,
    archive: list[dict],
    stats: Optional[_ReplayStats] = None,
) -> tuple[int, list[dict]]:
    """Replay every archived node + edge onto the fresh graph (idempotent).

    Returns ``(reapplied, kept_archive)`` where ``reapplied`` counts EDGES.
    Pass a :class:`_ReplayStats` as ``stats`` to also learn how many nodes were
    replayed and how many malformed rows were skipped — the node count matters
    because an archive entry may legitimately carry nodes and no edges.

    Archive entries whose source node is missing from the graph (after node
    replay) are dropped from ``kept_archive`` — they correspond to deleted code
    and would otherwise stick around forever, polluting the dedup set.

    Backward-compat: 0.3.1-format entries carry only ``edges`` (no
    ``nodes``/``hyperedges`` keys); those keys default to ``[]`` so the same
    replay code path handles both formats. Hyperedges are persisted in the
    archive but not yet projected into the graph — see ``apply()`` for the
    pending schema work.

    Every row goes through :func:`_validate_llm_node` / :func:`_validate_llm_edge`,
    the same contract ``apply()`` enforces, so a poisoned archive degrades to
    skipped rows instead of a traceback the user can only fix by hand-editing
    JSONL.
    """
    label_idx = _label_index(G)
    # Snapshot code nodes' source_files once so replayed concept/document/
    # paper nodes get the same G12 source_file guard as a fresh apply().
    protected_sf = _code_source_files(G)
    stats = stats if stats is not None else _ReplayStats()
    reapplied = 0
    kept: list[dict] = []
    # Pass 1: replay nodes so subsequent edge targets can resolve to them.
    # This must run for every entry, even ones whose source is missing —
    # a concept node from chunk A may be referenced by an edge from chunk B
    # whose source is still alive.
    for entry in archive:
        if not isinstance(entry, dict):
            stats.entries_rejected_invalid += 1
            continue
        for node in _entry_list(entry, "nodes"):
            clean = _validate_llm_node(node)
            if clean is None:
                stats.nodes_rejected_invalid += 1
                continue
            if _merge_node(
                G, label_idx,
                node_id=clean["id"],
                label=clean["label"],
                file_type=clean["file_type"],
                source_file=clean["source_file"],
                protected_source_files=protected_sf,
            ):
                stats.nodes_added += 1
    # Pass 2: replay edges, drop entries whose source is missing.
    for entry in archive:
        if not isinstance(entry, dict):
            continue
        source = entry.get("source_node_id")
        if not isinstance(source, str) or not source or source not in G:
            continue
        kept.append(entry)
        for edge in _entry_list(entry, "edges"):
            clean = _validate_llm_edge(edge)
            if clean is None:
                stats.edges_rejected_invalid += 1
                continue
            if _merge_edge(
                G, label_idx, source, clean["target_name"],
                relation=clean["relation"] or "references",
                score=_coerce_score(clean["confidence_score"], 0.7),
                confidence=clean["confidence"] or "INFERRED",
                verification=clean["verification"],
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
    replay = _ReplayStats()
    reapplied, kept_archive = _reapply_archive(G, archive, replay)
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

    # Persist whenever the replay changed the graph at all. Gating on the edge
    # count alone stranded an archived node-only contribution: it was replayed
    # into the in-memory graph on every prepare() and written out on none of
    # them (G-0949-12).
    if reapplied or replay.nodes_added:
        # Overlay pass: loaded the graph, replayed our own tier onto it, adding
        # only. See write_beacon's ``overlay_write`` contract.
        write_beacon(G, beacon_dir, overlay_write=True)
    if replay.nodes_rejected_invalid or replay.edges_rejected_invalid or \
            replay.entries_rejected_invalid:
        warnings.warn(
            f"semantic-prepare: skipped malformed archive rows "
            f"({replay.entries_rejected_invalid} entries, "
            f"{replay.nodes_rejected_invalid} nodes, "
            f"{replay.edges_rejected_invalid} edges) in "
            f"{_original_dir(beacon_dir)} — the rest of the archive was replayed.",
            stacklevel=2,
        )

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
        if excerpt is None or not excerpt.text:
            continue
        tid = _task_id(cand.file_path, cand.node_id, excerpt.content_hash)
        if tid in done_task_ids:
            continue
        neighbors = _neighbor_context(G, cand.node_id)
        hint = (
            "List explicit class/type/service references that appear in "
            "comments, docstrings, annotations, or are clearly implied "
            "by the surrounding excerpt. Prefer names that already "
            "appear under `neighbors.callers` or `neighbors.callees` — "
            "those are confirmed graph nodes; inventing new names that "
            "aren't in the graph adds noise."
        )
        if excerpt.truncated:
            # The agent must know it is reasoning about a slice, or it will
            # answer "the references in this file are X" as though it had read
            # the whole thing (G-0949-21).
            hint += (
                " NOTE: `excerpt` is a partial view of this file "
                f"({len(excerpt.text)} of {excerpt.file_chars} characters, "
                "head and tail only — the elision point is marked inline). "
                "Draw conclusions only from what you can see and do not "
                "assume the listing is exhaustive."
            )
        task = {
            "task_id": tid,
            "source_node_id": cand.node_id,
            "file_path": cand.file_path,
            "framework": cand.framework,
            "excerpt": excerpt.text,
            # Truncation is announced in the task itself as well as in the
            # hint, so a programmatic consumer (or a later apply) can tell a
            # partial view from a complete one without re-reading the file.
            "excerpt_truncated": excerpt.truncated,
            "excerpt_chars": len(excerpt.text),
            "file_chars": excerpt.file_chars,
            # Cross-language semantic context: the LLM gets the immediate
            # callers and callees as label hints so it can name references
            # that exist in the graph instead of inventing them. Mirrors
            # graphify #ab4e542. Both lists are capped to keep the chunk
            # payload predictable.
            "neighbors": neighbors,
            "hint": hint,
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


def _best_effort(what: str, fn, *args, **kwargs) -> None:
    """Run a post-merge export, reporting any failure without raising.

    Used only for work that happens after ``beacon.json`` is committed. The
    contract is deliberately two-sided: the merge survives a broken exporter,
    and a broken exporter is never silent.
    """
    try:
        fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — an export must not undo the merge
        print(
            f"  Warning: {what} regeneration failed after semantic-apply "
            f"({type(exc).__name__}: {exc}). beacon.json is up to date; "
            f"re-run `codebeacon scan` to rebuild the exports.",
            file=sys.stderr,
        )


def apply(
    beacon_dir: str | Path,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE_SCORE,
) -> ApplyResult:
    """Merge every ``results/chunk_*.jsonl`` into ``beacon.json``.

    For each chunk that yielded at least one valid result row, the
    corresponding ``pending/chunk_*.jsonl`` is **moved** to
    ``original/chunk_*.jsonl`` with the inferred edges spliced into each
    task record. The ``results/`` file is deleted afterwards. Chunks with
    no matching pending file are still archived from their result data
    alone (defensive — covers manual editing).

    ``min_confidence`` drops any LLM-emitted edge whose ``confidence_score``
    falls below this threshold (default 0.5). The dropped edges are still
    counted in ``ApplyResult.stats`` so a hallucination spike is visible to
    CI without having to diff beacon.json manually.

    Returns counts and the resulting archive size.
    """
    from codebeacon.graph.write import load_beacon, write_beacon
    from codebeacon.graph.cluster import cluster, apply_communities
    from codebeacon.diagnostics import write_semantic_stats

    stats = SemanticIngestStats()

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
    # Snapshot code nodes' source_files once for the G12 _merge_node guard.
    # The LLM can only add concept/document/paper nodes (never code nodes),
    # so this set is stable for the whole apply run.
    protected_sf = _code_source_files(G)

    applied = 0
    skipped = 0
    chunks_archived = 0
    nodes_applied = 0
    # Per-run cache of file text, used only when an excerpt was truncated and
    # the literal-occurrence check has to look at the part the agent never saw.
    source_text_cache: dict[str, str] = {}

    for result_path in sorted(rdir.glob("chunk_*.jsonl")):
        chunk_name = result_path.name
        results_by_tid: dict[str, dict] = {}
        for obj in _iter_jsonl(result_path):
            tid = obj.get("task_id")
            if isinstance(tid, str) and tid:
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

        # G12 guard 2: the set of source_node_ids actually dispatched in this
        # chunk. A result row may only attach edges to a node that was
        # dispatched here — otherwise a mis-attributed row (LLM or manual
        # edit) could inject edges onto an arbitrary unrelated node. Empty
        # when there is no pending file (manual-edit / legacy path), in which
        # case we keep the defensive "archive from results alone" behaviour.
        dispatched_sources = {
            t.get("source_node_id")
            for t in pending_tasks.values()
            if t.get("source_node_id")
        }

        archive_lines: list[dict] = []

        # Pass 1 within this chunk: register LLM-contributed nodes BEFORE
        # edges, so edges in the same result can reference fresh concept ids.
        #
        # Accepted-leak note (G12): Pass 1 merges nodes for EVERY result row,
        # including a row whose source_node_id is later skipped as out-of-scope
        # by Guard 2 in the Pass-2 loop below. Such a row's concept node
        # therefore lands in G, and if another in-scope row in this chunk makes
        # applied>0 it is persisted to beacon.json even though the out-of-scope
        # row itself is never archived (so _reapply_archive never replays or
        # prunes it). This leak is intentionally tolerated: the node is edgeless
        # (Guard 2 drops the row's edges) and any source_file colliding with a
        # real code node was already blanked by the G12 guard in _merge_node, so
        # it drives NO obsidian note deletion — the cost is at most one
        # disconnected, harmless concept node per skipped row. Deferring node
        # registration until Guard 2 confirms scope would close the leak but
        # adds cross-pass coupling for no correctness gain.
        kept_nodes_by_tid: dict[str, list[dict]] = {}
        for tid, obj in results_by_tid.items():
            kept_nodes: list[dict] = []
            for node in _entry_list(obj, "nodes"):
                clean = _validate_llm_node(node)
                if clean is None:
                    stats.nodes_rejected_invalid += 1
                    continue
                nid = clean["id"]
                if _merge_node(
                    G, label_idx,
                    node_id=nid,
                    label=clean["label"],
                    file_type=clean["file_type"],
                    source_file=clean["source_file"],
                    protected_source_files=protected_sf,
                ):
                    nodes_applied += 1
                    stats.nodes_accepted += 1
                    kept_nodes.append({
                        "id": nid,
                        "label": clean["label"],
                        "file_type": clean["file_type"],
                        # Archive the sanitized source_file the graph actually
                        # stored (G12 may have blanked it) so replay can't
                        # reintroduce a collision.
                        "source_file": G.nodes[nid].get("source_file", ""),
                    })
            if kept_nodes:
                kept_nodes_by_tid[tid] = kept_nodes

        for tid, obj in results_by_tid.items():
            source = obj.get("source_node_id")
            if not source or source not in G:
                skipped += 1
                continue
            if dispatched_sources and source not in dispatched_sources:
                # Out-of-scope: this source_node_id was never dispatched in
                # this chunk. Skip the whole row so its edges can't land on
                # an unrelated node (G12 guard 2).
                warnings.warn(
                    f"semantic-apply: {chunk_name} result row source_node_id "
                    f"{source!r} was not dispatched in this chunk — skipping.",
                    stacklevel=2,
                )
                skipped += 1
                continue
            task_spec = pending_tasks.get(tid) or {}
            # A row must name the source node its OWN task was dispatched for.
            # Without this, a row carrying task T1's id but T2's source lands
            # T1's edges on T2's node — both are in ``dispatched_sources``, so
            # the scope guard above waves it through — and stamps T1 done
            # though its file was never analysed (V9 G-0949-13 residual A).
            expected_source = task_spec.get("source_node_id")
            if expected_source and source != expected_source:
                warnings.warn(
                    f"semantic-apply: {chunk_name} result row task_id {tid!r} "
                    f"names source_node_id {source!r} but was dispatched for "
                    f"{expected_source!r} — skipping.",
                    stacklevel=2,
                )
                skipped += 1
                continue
            kept_edges: list[dict] = []
            for raw_edge in _entry_list(obj, "edges"):
                stats.edges_total += 1
                edge = _validate_llm_edge(raw_edge)
                if edge is None:
                    stats.edges_rejected_invalid += 1
                    skipped += 1
                    continue
                target = edge["target_name"]

                raw_score = edge.get("confidence_score")
                score = _coerce_score(raw_score, default=0.7)
                # _coerce_score returns the clamped/defaulted value silently.
                # We track "had to coerce" so a flood of None/NaN scores is
                # visible — those usually signal an LLM prompt regression.
                if raw_score is None or (
                    isinstance(raw_score, (int, float))
                    and (raw_score != raw_score or raw_score < 0.0 or raw_score > 1.0)
                ):
                    stats.confidence_score_coerced += 1

                rel_label, was_known = _classify_relation(edge.get("relation"))
                if not was_known:
                    raw_rel = (edge.get("relation") or "").strip().lower() or "<empty>"
                    stats.unknown_relation_labels[raw_rel] = (
                        stats.unknown_relation_labels.get(raw_rel, 0) + 1
                    )
                    stats.relations_coerced += 1

                # Threshold drop. Counted separately from "merge returned False"
                # so the stats file can tell low-confidence from dedup-collision.
                if score < min_confidence:
                    stats.edges_dropped_low_confidence += 1
                    skipped += 1
                    continue

                # Evidence check (G-0918-5). A target that does not resolve to
                # an existing node mints an `external` stub, which is otherwise
                # indistinguishable from an AST-extracted unresolved import.
                # Stamp whether the name literally occurs in the analysed
                # source, so consumers can weigh an inferred stub accordingly.
                verification = None
                if label_idx.get(target, target) not in G:
                    verification = (
                        "literal"
                        if _target_occurs_in_source(target, task_spec, source_text_cache)
                        else "unverified"
                    )

                if _merge_edge(
                    G, label_idx, source, target,
                    relation=rel_label,
                    score=score,
                    confidence=edge.get("confidence") or "INFERRED",
                    verification=verification,
                ):
                    if verification == "literal":
                        stats.edge_targets_literal += 1
                    elif verification == "unverified":
                        stats.edge_targets_unverified += 1
                    kept_edges.append({
                        "target_name": target,
                        "relation": rel_label,
                        "confidence": _normalize_confidence(edge.get("confidence")),
                        "confidence_score": score,
                        # Archived so a replay onto a fresh graph re-mints the
                        # stub with the same provenance instead of losing it.
                        **({"verification": verification} if verification else {}),
                    })
                    applied += 1
                    stats.edges_accepted += 1
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

        # Drop the result file now that the chunk is archived.
        try:
            result_path.unlink()
        except OSError:
            pass
        # The pending file is the record of what was DISPATCHED. Deleting it
        # when the result yielded nothing at all destroys the agent's work
        # order along with its output, leaving the user nothing to retry
        # (G-0948-5). Keep it so the chunk can simply be re-run.
        recovered_nothing = not archive_lines and not results_by_tid
        if recovered_nothing:
            stats.chunks_unrecoverable += 1
            warnings.warn(
                f"semantic-apply: {chunk_name} yielded no usable result rows — "
                f"keeping {pending_path} so the chunk can be re-run.",
                stacklevel=2,
            )
        elif pending_path.exists():
            try:
                pending_path.unlink()
            except OSError:
                pass

    archive_size = len(_read_archive(beacon_dir))

    # Persist hallucination stats whether or not any edge was applied — a run
    # that drops 100% of edges due to low confidence is exactly the case CI
    # needs to flag, and that information lives only in the stats file.
    write_semantic_stats(stats, beacon_dir)

    # Persistence gate. ``applied`` counts EDGES; a row contributing a concept
    # node and no edges is still a real contribution, and gating on edges alone
    # archived it, stamped its task_id done, and never wrote it to beacon.json
    # — so it was neither persisted nor ever re-requested (G-0949-12).
    if applied == 0 and nodes_applied == 0:
        return ApplyResult(
            applied=0, skipped=skipped,
            chunks_archived=chunks_archived,
            archive_size=archive_size,
            stats=stats,
            nodes_applied=0,
        )

    communities = cluster(G)
    apply_communities(G, communities)
    # Overlay pass: the merged graph is the loaded one plus this run's inferred
    # nodes and edges. See write_beacon's ``overlay_write`` contract.
    write_beacon(G, beacon_dir, overlay_write=True)

    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.contextmap.generator import generate_context_map
    from codebeacon.export.callflow_html import write_callflow_html
    from codebeacon.export.tree_html import write_tree_html

    # Every export below runs AFTER beacon.json is durably committed, so none of
    # them may take the merge down with them — an agent's analysis is expensive
    # to reproduce and a wiki bug is not a reason to lose it. Equally, none may
    # fail invisibly: a swallowed export crash is how a half-written obsidian
    # vault (2 notes instead of 5) stayed undetected through a whole release
    # (G-0918-4). So each one warns by name and the command carries on.
    _best_effort("wiki", generate_wiki, G, communities, str(beacon_dir))
    _best_effort("obsidian vault", generate_obsidian_vault, G, communities,
                 str(beacon_dir))
    _best_effort("context map", generate_context_map, G=G,
                 output_dir=str(beacon_dir), projects=[], obsidian_dir=None)
    # Regenerate the visual exports so callflow.html's cross-community table
    # and beacon.html's tree pick up the freshly-inferred edges. Without this,
    # the HTML on disk still reflects the AST-only graph and misses the new
    # `references`, `cites`, `conceptually_related_to`, etc. edges the agent
    # just produced — analogous to graphify 0.8.12 #925 (Relationships
    # section stayed empty when downstream readers used stale community
    # state).
    _best_effort("callflow HTML", write_callflow_html, G, beacon_dir)
    _best_effort("tree HTML", write_tree_html, G, beacon_dir)

    return ApplyResult(
        applied=applied,
        skipped=skipped,
        chunks_archived=chunks_archived,
        archive_size=archive_size,
        stats=stats,
        nodes_applied=nodes_applied,
    )
