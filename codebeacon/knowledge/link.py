"""Link knowledge notes into the code knowledge graph.

Why this exists
---------------
``codebeacon knowledge`` classifies markdown notes (ADRs, meeting notes,
retrospectives, specs, research) into a standalone ``KNOWLEDGE.md``. On its own
that map is architecturally isolated from ``beacon.json`` — an ADR that decided
the shape of ``PaymentService`` carries no edge to the ``PaymentService`` node,
so an agent reading the graph never learns *why* the code looks the way it does.

This pass closes that gap. When a ``beacon.json`` already exists (from a prior
``codebeacon scan``) each note becomes a ``knowledge`` node and is linked to the
code it references, using two conservative heuristics that mirror the
precision-over-recall ethos of ``common/filters.py``:

* **path reference** (``EXTRACTED``) — a note that names a source file in
  backticks or as an ``src/…``-style path is linked to the node(s) whose
  ``source_file`` shares that path suffix. A file path is an unambiguous
  pointer, so the edge is trusted.

* **name mention** (``AMBIGUOUS``) — a note whose body mentions a node's exact
  label on a word boundary is linked with an ambiguous edge, but only when the
  label is a *distinctive* identifier: a compound symbol like ``PaymentService``
  or ``get_subway_time``, never a bare single word like ``User`` or ``payment``
  that collides with ordinary prose. A single word signals nothing, so it is
  dropped rather than trusted.

A wrong ADR→service edge is worse than a missing one — it silently misattributes
a decision — so both heuristics err toward dropping.

Why this layer (not a scan enrich pass)
---------------------------------------
``codebeacon scan`` guarantees that code nodes stay AST-owned and deterministic
(see ``semantic_pipeline.ALLOWED_LLM_NODE_TYPES``). Knowledge notes are not code,
so they are minted *after* the scan, from the ``knowledge`` subcommand, and
written back as an overlay. Re-running ``scan`` rebuilds the code graph from
source alone and drops the overlay; re-run ``codebeacon knowledge`` to restore
it. Keeping the overlay out of the scan pipeline preserves the scan's
determinism invariant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codebeacon.common.types import (
    KNOWLEDGE_MENTIONS_RELATION,
    KNOWLEDGE_NODE_TYPE,
    KNOWLEDGE_REFERENCES_RELATION,
)
from codebeacon.knowledge.generator import KnowledgeResult, Note


# Node types a knowledge note may point at. Routes carry a ``handler [GET /x]``
# label that never reads as a clean identifier, so they are reachable by path
# reference but never by name mention.
_LINKABLE_TYPES: frozenset[str] = frozenset({"class", "service", "entity", "component", "route"})
_MENTIONABLE_TYPES: frozenset[str] = frozenset({"class", "service", "entity", "component"})

# Confidence bands mirror the rest of the graph: EXTRACTED is trusted (1.0,
# same as the http_api / ipc enrichers), AMBIGUOUS sits below INFERRED's 0.8
# because a bare-name match is genuinely uncertain.
_REFERENCE_CONFIDENCE = ("EXTRACTED", 1.0)
_MENTION_CONFIDENCE = ("AMBIGUOUS", 0.5)

# A name mention must clear this length. Short labels ("id", "db", "app") are
# almost always prose collisions.
_MIN_MENTION_LEN = 4

# A clean identifier — the only label shape eligible for a name-mention edge.
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

# Distinctive-but-generic identifiers that clear the shape guard yet still read
# as English. Kept small and explicit, in the spirit of ``filters.py``'s marker
# sets — the structural guards below do most of the work.
_MENTION_STOPWORDS: frozenset[str] = frozenset({
    "README", "CHANGELOG", "TODO", "getData", "setData", "getValue", "setValue",
})

# A path-like token in free prose: at least one directory separator and a file
# extension, e.g. ``app/models/user.py``. The leading slash / ``./`` is allowed
# so ``/api/routes.ts`` and ``./lib/x.ts`` are captured.
_PATH_TOKEN_RE = re.compile(r"(?:\.?/)?(?:[\w.-]+/)+[\w.-]+\.\w{1,8}")


@dataclass
class LinkResult:
    """Outcome of :func:`link_knowledge_to_graph`."""

    beacon_path: Path
    knowledge_nodes: int      # note nodes materialised into the graph
    reference_edges: int      # EXTRACTED path-based edges
    mention_edges: int        # AMBIGUOUS name-based edges
    linked_notes: int         # notes that gained at least one edge


# ── Public API ────────────────────────────────────────────────────────────────


def resolve_beacon_dir(*candidates: object) -> Optional[Path]:
    """Return the first candidate directory that holds a ``beacon.json``.

    ``candidates`` may include ``None`` (skipped) so callers can list several
    conventional locations — ``<out>/.codebeacon``, ``<root>/.codebeacon``, a
    bare ``.codebeacon`` dir — without pre-filtering.
    """
    for cand in candidates:
        if cand is None:
            continue
        d = Path(str(cand))
        if (d / "beacon.json").exists():
            return d
    return None


def link_knowledge_to_graph(
    result: KnowledgeResult,
    beacon_dir: str | Path,
) -> Optional[LinkResult]:
    """Materialise ``result``'s notes as graph nodes and link them to code.

    Loads the graph from ``beacon_dir/beacon.json``, purges any knowledge
    overlay from a previous run, adds one ``knowledge`` node per note, computes
    reference + mention edges, and atomically rewrites ``beacon.json``.

    Returns ``None`` (a no-op) when no ``beacon.json`` is present — the
    ``KNOWLEDGE.md`` map still stands on its own, so a knowledge scan run before
    any code scan simply skips linking.
    """
    from codebeacon.graph.write import load_beacon, write_beacon

    beacon_dir = Path(beacon_dir)
    beacon_json = beacon_dir / "beacon.json"
    if not beacon_json.exists():
        return None

    G, _meta = load_beacon(beacon_json)

    _purge_previous_knowledge(G)
    by_basename = _index_source_files(G)
    mention_candidates = _mention_candidates(G)

    root = Path(result.root)
    knowledge_nodes = 0
    reference_edges = 0
    mention_edges = 0
    linked_notes = 0

    for note in result.notes:
        text = _read_note(root, note.path)
        node_id = _note_node_id(note)
        G.add_node(node_id, **_note_attrs(note))
        knowledge_nodes += 1

        # Path references first — they are the trusted signal, and a pair
        # already linked by an EXTRACTED reference must not be down-graded to a
        # duplicate AMBIGUOUS mention edge.
        referenced: set[str] = set()
        for ref in extract_path_refs(text):
            for target_id in _match_path_ref(ref, by_basename):
                if target_id in referenced:
                    continue
                _add_link(G, node_id, target_id, KNOWLEDGE_REFERENCES_RELATION,
                          _REFERENCE_CONFIDENCE, note.path)
                referenced.add(target_id)
                reference_edges += 1

        for target_id in extract_name_mentions(text, mention_candidates):
            if target_id in referenced:
                continue
            _add_link(G, node_id, target_id, KNOWLEDGE_MENTIONS_RELATION,
                      _MENTION_CONFIDENCE, note.path)
            referenced.add(target_id)
            mention_edges += 1

        if referenced:
            linked_notes += 1

    # ``force`` bypasses the shrink guard: purging the previous overlay can drop
    # nodes for notes that were deleted since the last run, which would trip the
    # guard even though the code portion of the graph is untouched. We loaded the
    # very file we are rewriting, so the code nodes cannot shrink underneath us.
    wr = write_beacon(G, beacon_dir, repo_path=beacon_dir, force=True)

    return LinkResult(
        beacon_path=wr.path,
        knowledge_nodes=knowledge_nodes,
        reference_edges=reference_edges,
        mention_edges=mention_edges,
        linked_notes=linked_notes,
    )


# ── Heuristics (pure, unit-testable) ──────────────────────────────────────────


def extract_path_refs(text: str) -> set[str]:
    """Return the source-file paths a note points at.

    A reference is any path-like token — a directory separator plus a file
    extension — whether it sits in prose (``see app/models/user.py``) or inside
    a backtick span (``\\`src/a/B.java\\``); the backticks are ordinary
    surrounding characters the token regex simply skips over. The directory
    separator is required so a bare filename (``config.py``), which collides
    across a repo, is never treated as a reference.
    """
    return {m.group(0).strip() for m in _PATH_TOKEN_RE.finditer(text)}


def extract_name_mentions(
    text: str,
    candidates: list[tuple[str, re.Pattern[str], str]],
) -> set[str]:
    """Return node ids whose distinctive label appears in ``text``.

    ``candidates`` is the pre-compiled output of :func:`_mention_candidates`.
    """
    if not text:
        return set()
    hits: set[str] = set()
    for _label, pattern, node_id in candidates:
        if pattern.search(text):
            hits.add(node_id)
    return hits


def is_distinctive_label(label: str) -> bool:
    """True when ``label`` is a compound identifier safe to match in prose.

    The guard is structural: a clean identifier, at least ``_MIN_MENTION_LEN``
    long, that is *compound* — it either contains ``_`` or an uppercase letter
    somewhere after the first character (CamelCase). A single word, whether
    lowercase (``payment``) or capitalised (``Payment``, ``Database``), carries
    no internal signal that it means the code symbol rather than the concept, so
    it is rejected. A short stopword set covers the rare generic compound.
    """
    if len(label) < _MIN_MENTION_LEN:
        return False
    if not _IDENTIFIER_RE.match(label):
        return False
    if label in _MENTION_STOPWORDS:
        return False
    compound = ("_" in label) or any(c.isupper() for c in label[1:])
    return compound


# ── Graph mutation helpers ────────────────────────────────────────────────────


def _note_node_id(note: Note) -> str:
    # The ``knowledge::`` prefix keeps every note in one project namespace, so
    # write.py's path-relativizer and the cross-service filters treat the overlay
    # as a cohesive unit and a note id can never collide with a code node id.
    return f"knowledge::{note.path}"


def _note_attrs(note: Note) -> dict:
    """Flatten a Note into NetworkX node attributes (mirrors build._node_attrs)."""
    return {
        "label": note.title,
        "type": KNOWLEDGE_NODE_TYPE,
        "source_file": note.path,
        "line": 1,
        "project": "knowledge",
        "framework": "",
        "category": note.category,
        "summary": note.summary,
        "date": note.date,
        "tags": list(note.tags),
        "note_path": note.path,
    }


def _add_link(G, source_id: str, target_id: str, relation: str,
              confidence: tuple[str, float], note_path: str) -> None:
    conf, score = confidence
    G.add_edge(
        source_id, target_id,
        relation=relation,
        confidence=conf,
        confidence_score=score,
        source_file=note_path,
    )


def _purge_previous_knowledge(G) -> None:
    """Drop all knowledge nodes (and, with them, their edges) from a prior run.

    Removing a node in NetworkX removes its incident edges too, so this clears
    the whole overlay and makes re-linking idempotent — a deleted note leaves no
    stale node behind.
    """
    stale = [n for n, d in G.nodes(data=True) if d.get("type") == KNOWLEDGE_NODE_TYPE]
    G.remove_nodes_from(stale)


def _index_source_files(G) -> dict[str, list[tuple[str, str]]]:
    """Map basename → [(source_file, node_id)] over linkable code nodes."""
    by_basename: dict[str, list[tuple[str, str]]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") not in _LINKABLE_TYPES:
            continue
        sf = str(data.get("source_file", ""))
        if not sf:
            continue
        base = sf.replace("\\", "/").rsplit("/", 1)[-1]
        by_basename.setdefault(base, []).append((sf, node_id))
    return by_basename


def _mention_candidates(G) -> list[tuple[str, re.Pattern[str], str]]:
    """Pre-compile a word-boundary pattern for every distinctive label."""
    out: list[tuple[str, re.Pattern[str], str]] = []
    for node_id, data in G.nodes(data=True):
        if data.get("type") not in _MENTIONABLE_TYPES:
            continue
        label = str(data.get("label", ""))
        if is_distinctive_label(label):
            pattern = re.compile(r"\b" + re.escape(label) + r"\b")
            out.append((label, pattern, node_id))
    return out


def _match_path_ref(ref: str, by_basename: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Return node ids whose source_file shares a segment-suffix with ``ref``."""
    ref_norm = ref.replace("\\", "/").lstrip("/")
    if ref_norm.startswith("./"):
        ref_norm = ref_norm[2:]
    base = ref_norm.rsplit("/", 1)[-1]
    matches: list[str] = []
    for sf, node_id in by_basename.get(base, ()):
        if _path_suffix_match(ref_norm, sf):
            matches.append(node_id)
    return matches


def _path_suffix_match(ref: str, source_file: str) -> bool:
    """True when one path is a segment-boundary suffix of the other.

    Leading ``/`` sentinels anchor the comparison to a path separator so
    ``Service.java`` never matches ``MyService.java`` and ``a/User.py`` never
    matches ``data/User.py``.
    """
    a = "/" + source_file.replace("\\", "/").lstrip("/").rstrip("/")
    b = "/" + ref.replace("\\", "/").lstrip("/").rstrip("/")
    if len(a) <= 1 or len(b) <= 1:
        return False
    return a.endswith(b) or b.endswith(a)


def _read_note(root: Path, rel_path: str) -> str:
    """Read a note's text, tolerating a missing/unreadable file (returns "")."""
    try:
        return (root / rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
