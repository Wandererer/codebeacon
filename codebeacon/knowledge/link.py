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

* **authored wikilink** (``EXTRACTED``) — an Obsidian-style ``[[target]]`` the
  note's author typed by hand. It resolves vault-wide by basename (what
  Obsidian itself does), or by path suffix when the target is slashed, and
  falls back to an exact code-symbol label when it names no note. An authored
  link is deliberate, so it is trusted like a path reference rather than being
  left to the prose heuristic below.

* **name mention** (``AMBIGUOUS``) — a note whose body mentions a node's exact
  label on a word boundary is linked with an ambiguous edge, but only when the
  label is a *distinctive* identifier: a compound symbol like ``PaymentService``
  or ``get_subway_time``, never a bare single word like ``User`` or ``payment``
  that collides with ordinary prose. A single word signals nothing, so it is
  dropped rather than trusted.

A wrong ADR→service edge is worse than a missing one — it silently misattributes
a decision — so every heuristic errs toward dropping.

Why this layer (not a scan enrich pass)
---------------------------------------
``codebeacon scan`` guarantees that code nodes stay AST-owned and deterministic
(see ``semantic_pipeline.ALLOWED_LLM_NODE_TYPES``). Knowledge notes are not code,
so they are minted *after* the scan, from the ``knowledge`` subcommand, and
written back as an overlay. Keeping the overlay out of the graph build preserves
the scan's determinism invariant.

That leaves the overlay to be rebuilt rather than re-extracted, which
:func:`reapply_knowledge` does at the end of a scan: the code graph is finalised
first, then the overlay is minted onto it from the same notes by the same
heuristics in the same order. The invariant holds, and a plain ``scan`` no
longer silently discards what ``codebeacon knowledge`` produced.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codebeacon.common.types import (
    KNOWLEDGE_MENTIONS_RELATION,
    KNOWLEDGE_NODE_TYPE,
    KNOWLEDGE_REFERENCES_RELATION,
)
from codebeacon.knowledge.generator import (
    KNOWLEDGE_MAP_FOOTER,
    KnowledgeResult,
    Note,
    build_knowledge_map,
)


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
#
# The segment repetition is BOUNDED rather than ``+``. Unbounded, a line made of
# a dense slash run with no valid extension at the end (a pasted tree listing, a
# minified blob) costs O(n^2): the engine restarts at every segment boundary and
# re-walks the rest of the line each time. Measured on the unbounded form: 40k
# chars took 10.2s and 80k took 40.6s, a clean 4x per doubling. Bounding the
# repetition caps the work per start position, which flattens it to linear —
# the same inputs take 27ms and 54ms.
#
# The bound costs nothing real. A path deeper than 24 segments matches its last
# 24 instead of the whole run, and ``_match_path_ref`` compares by path SUFFIX
# (``_path_suffix_match``), so the shorter ref resolves to exactly the same
# node. It matters because knowledge/ ingests markdown from whatever tree is
# being scanned — including third-party repos — and since the overlay is
# re-applied on every scan (R2), this runs far more often than it used to.
_MAX_PATH_SEGMENTS = 24
_PATH_TOKEN_RE = re.compile(
    r"(?:\.?/)?(?:[\w.-]+/){1," + str(_MAX_PATH_SEGMENTS) + r"}[\w.-]+\.\w{1,8}"
)


@dataclass
class LinkResult:
    """Outcome of :func:`link_knowledge_to_graph`."""

    beacon_path: Path
    knowledge_nodes: int      # note nodes materialised into the graph
    reference_edges: int      # EXTRACTED path-based edges
    mention_edges: int        # AMBIGUOUS name-based edges
    linked_notes: int         # notes that gained at least one edge
    wikilink_edges: int = 0   # EXTRACTED edges from authored [[wikilinks]]


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
    exact_labels = _exact_label_index(G)

    root = Path(result.root)
    knowledge_nodes = 0
    reference_edges = 0
    mention_edges = 0
    wikilink_edges = 0
    linked_notes = 0

    # Pass 1: materialise every note node first, so a [[wikilink]] can resolve
    # to a note that appears later in the vault ordering.
    for note in result.notes:
        G.add_node(_note_node_id(note), **_note_attrs(note))
        knowledge_nodes += 1
    note_index = _index_notes(result.notes)

    # Pass 2: resolve each note's references now that all targets exist.
    for note in result.notes:
        text = _read_note(root, note.path)
        node_id = _note_node_id(note)

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

        # Authored [[wikilinks]] rank with path references: the author typed
        # this link on purpose, which is at least as trustworthy as a path
        # token in prose, and strictly better evidence than a bare-name
        # collision in the mention pass below.
        for target_id in resolve_wikilinks(note, note_index, exact_labels):
            if target_id == node_id or target_id in referenced:
                continue
            _add_link(G, node_id, target_id, KNOWLEDGE_REFERENCES_RELATION,
                      _REFERENCE_CONFIDENCE, note.path)
            referenced.add(target_id)
            wikilink_edges += 1

        for target_id in extract_name_mentions(text, mention_candidates):
            if target_id in referenced:
                continue
            _add_link(G, node_id, target_id, KNOWLEDGE_MENTIONS_RELATION,
                      _MENTION_CONFIDENCE, note.path)
            referenced.add(target_id)
            mention_edges += 1

        if referenced:
            linked_notes += 1

    # ``overlay_write`` states what this pass actually is: we loaded beacon.json
    # and are adding our own tier back onto it. The guard then holds us to the
    # rule that matters — a code node may not disappear underneath an overlay
    # pass — instead of per-source accounting it cannot do here (the document we
    # loaded carries project-relative paths and we have no roots to resolve them).
    wr = write_beacon(G, beacon_dir, repo_path=beacon_dir, overlay_write=True)

    _write_overlay_state(beacon_dir, result, knowledge_nodes)

    return LinkResult(
        beacon_path=wr.path,
        knowledge_nodes=knowledge_nodes,
        reference_edges=reference_edges,
        mention_edges=mention_edges,
        linked_notes=linked_notes,
        wikilink_edges=wikilink_edges,
    )


def reapply_knowledge(root: Path, outdir: Path) -> int:
    """Re-mint the knowledge overlay onto the graph a scan has just written.

    ``codebeacon scan`` rebuilds the code graph from source alone, which drops
    the note overlay a prior ``codebeacon knowledge`` had linked in. This is the
    scan-side repair: it re-runs the note scan and the link pass so a rescan is
    idempotent with respect to the overlay instead of silently discarding it.

    The overlay is only rebuilt for a repo that opted in by running
    ``codebeacon knowledge`` at least once — detected via the state file this
    module writes, or failing that a ``KNOWLEDGE.md`` carrying our own header
    and footer. A hand-written ``KNOWLEDGE.md`` is never overwritten.

    Args:
        root:   the scanned project root (used when no state file records a
                more specific note directory).
        outdir: the ``.codebeacon`` directory holding ``beacon.json``.

    Returns:
        ``> 0`` — that many note nodes were re-linked into ``beacon.json``.
        ``0``   — no overlay to reapply; nothing was written, nothing to report.
        ``-1``  — an overlay was detected but could not be rebuilt. A warning
                  naming the cause has already been printed to stderr.

    Never raises: a scan must not fail because the overlay could not be
    restored, but it must never drop the overlay silently either.
    """
    root = Path(root)
    outdir = Path(outdir)

    try:
        plan = _plan_reapply(root, outdir)
    except OSError as exc:
        print(f"  Warning: knowledge overlay not reapplied ({exc}).", file=sys.stderr)
        return -1
    if plan is None:
        return 0
    scan_root, knowledge_out, write_map = plan

    if not scan_root.is_dir():
        print(
            f"  Warning: knowledge overlay not reapplied — note directory "
            f"{scan_root} is missing. Re-run `codebeacon knowledge` once the "
            f"notes are back.",
            file=sys.stderr,
        )
        return -1

    try:
        result = build_knowledge_map(scan_root, knowledge_out, write_output=write_map)
        link = link_knowledge_to_graph(result, outdir)
    except (OSError, ValueError) as exc:
        print(
            f"  Warning: knowledge overlay not reapplied ({exc}). "
            f"Run `codebeacon knowledge` to restore it.",
            file=sys.stderr,
        )
        return -1

    if link is None:
        print(
            f"  Warning: knowledge overlay not reapplied — no beacon.json in "
            f"{outdir}.",
            file=sys.stderr,
        )
        return -1
    return link.knowledge_nodes


# ── Overlay state (how a scan learns an overlay exists) ───────────────────────

# Written next to ``beacon.json`` by every successful link pass. It records the
# directory the notes were scanned from and where ``KNOWLEDGE.md`` was written,
# so a later unattended scan can rebuild the overlay exactly as the user's
# original ``codebeacon knowledge`` invocation did — including the case where
# they pointed it at a subdirectory (``codebeacon knowledge docs/``).
_STATE_FILENAME = "knowledge-state.json"
_STATE_VERSION = 1


def _write_overlay_state(beacon_dir: Path, result: KnowledgeResult, nodes: int) -> None:
    """Record how this overlay was produced. Best-effort — never fatal."""
    if result.output_path is not None:
        knowledge_out = str(result.output_path.parent)
    else:
        knowledge_out = result.output_dir
    state = {
        "version": _STATE_VERSION,
        "root": str(result.root),
        "knowledge_out": knowledge_out,
        "notes": nodes,
    }
    # Written on every scan now that the overlay is auto-reapplied (R2), and its
    # content is fully deterministic — so rewriting identical bytes would move
    # the mtime of a committed file on every run and re-fire Obsidian's indexer,
    # sync clients, and codebeacon's own watch mode for no reason (GI-3060).
    try:
        from codebeacon.common.io import write_text_if_changed

        write_text_if_changed(
            beacon_dir / _STATE_FILENAME, json.dumps(state, indent=2) + "\n"
        )
    except OSError:
        pass


def _read_overlay_state(beacon_dir: Path) -> Optional[dict]:
    """Return the recorded overlay state, or ``None`` when absent/unusable."""
    path = beacon_dir / _STATE_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        state = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(state, dict) or state.get("version") != _STATE_VERSION:
        return None
    if not isinstance(state.get("root"), str) or not state["root"]:
        return None
    return state


def _plan_reapply(root: Path, outdir: Path) -> Optional[tuple[Path, Path, bool]]:
    """Decide whether — and how — to rebuild the overlay.

    Returns ``(scan_root, knowledge_out, write_map)`` or ``None`` when this repo
    never opted into a knowledge overlay. ``write_map`` is False when a
    ``KNOWLEDGE.md`` exists that codebeacon did not write, so the note scan
    still feeds the graph overlay without touching the user's file.
    """
    from codebeacon.knowledge.generator import is_generated_knowledge_map

    state = _read_overlay_state(outdir)
    if state is not None:
        scan_root = Path(state["root"])
        out_raw = state.get("knowledge_out") or ""
        knowledge_out = Path(out_raw) if out_raw else scan_root
        existing = knowledge_out / "KNOWLEDGE.md"
        write_map = True
        if existing.exists():
            write_map = is_generated_knowledge_map(
                existing.read_text(encoding="utf-8", errors="replace")
            )
        return scan_root, knowledge_out, write_map

    # No state file (overlay predates it, or the dir was hand-assembled): fall
    # back to a codebeacon-generated KNOWLEDGE.md as the opt-in marker.
    for cand in (outdir.parent, root):
        existing = cand / "KNOWLEDGE.md"
        if not existing.exists():
            continue
        if is_generated_knowledge_map(existing.read_text(encoding="utf-8", errors="replace")):
            return root, cand, True
        return None  # a foreign KNOWLEDGE.md is not an opt-in signal
    return None


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


# A wikilink target may carry an Obsidian heading/block anchor
# (``[[note#Decision]]``, ``[[note^blockid]]``) and may spell out the markdown
# extension. Neither is part of the note's identity.
_WIKILINK_ANCHOR_RE = re.compile(r"[#^].*\Z", re.DOTALL)
_MARKDOWN_SUFFIXES = (".md", ".mdx", ".markdown")


def normalize_wikilink(raw: str) -> str:
    """Reduce a raw ``[[target]]`` capture to a comparable note reference.

    Strips surrounding whitespace, any ``#heading`` / ``^block`` anchor, and a
    spelled-out markdown extension, then normalises separators. Returns ``""``
    when nothing usable is left.
    """
    token = _WIKILINK_ANCHOR_RE.sub("", (raw or "").strip()).strip()
    token = token.replace("\\", "/").strip("/")
    lowered = token.lower()
    for suffix in _MARKDOWN_SUFFIXES:
        if lowered.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return token.strip()


def _note_stem(note_path: str) -> str:
    """The basename of ``note_path`` without its extension."""
    base = note_path.replace("\\", "/").rsplit("/", 1)[-1]
    stem, _, ext = base.rpartition(".")
    return stem if stem and f".{ext.lower()}" in _MARKDOWN_SUFFIXES else base


def _index_notes(notes) -> dict[str, list[Note]]:
    """Map lowercased basename stem → notes, in deterministic tie-break order.

    Obsidian resolves a bare ``[[beta]]`` across the WHOLE vault by basename,
    not relative to the linking note, so the index is vault-wide. Within a
    stem, notes are ordered shallowest-path-first then lexicographically, which
    is the documented tie-break when a basename is ambiguous.
    """
    index: dict[str, list[Note]] = {}
    for note in notes:
        index.setdefault(_note_stem(note.path).lower(), []).append(note)
    for bucket in index.values():
        bucket.sort(key=lambda n: (n.path.count("/"), n.path))
    return index


def _exact_label_index(G) -> dict[str, list[str]]:
    """Map exact code-node label → node ids, sorted for determinism.

    Separate from :func:`_mention_candidates` on purpose. That index is gated
    by :func:`is_distinctive_label` because a bare word in prose is usually a
    coincidence — but an authored ``[[PaymentService]]`` is not prose, it is a
    deliberate link, so the shape guard would only cost recall here.
    """
    index: dict[str, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("type") not in _MENTIONABLE_TYPES:
            continue
        label = str(data.get("label", ""))
        if label:
            index.setdefault(label, []).append(node_id)
    for bucket in index.values():
        bucket.sort()
    return index


def resolve_wikilinks(
    note: Note,
    note_index: dict[str, list[Note]],
    exact_labels: dict[str, list[str]],
) -> list[str]:
    """Return the graph node ids ``note``'s authored ``[[wikilinks]]`` point at.

    Resolution order per link, mirroring what an Obsidian user expects:

    1. A slashed target (``[[Entities/beta]]``) matches a note whose path shares
       a segment-boundary suffix — the same matcher path references use, so a
       target reachable under a different spelling still resolves.
    2. A bare target (``[[beta]]``) resolves vault-wide by basename. A sibling
       in the linking note's own directory wins; otherwise the deterministic
       shallowest-then-lexicographic first entry does.
    3. A target that names no note but exactly matches ONE code node's label
       becomes a reference to that node. More than one match is left to the
       ambiguous name-mention pass rather than guessing between them.

    Ids are returned in a deterministic order (sorted by the authored token) so
    the resulting edge set is stable across runs.
    """
    out: list[str] = []
    seen: set[str] = set()
    note_dir = note.path.replace("\\", "/").rsplit("/", 1)[0] if "/" in note.path else ""

    for raw in sorted(note.backlinks):
        token = normalize_wikilink(raw)
        if not token:
            continue

        target_note: Optional[Note] = None
        if "/" in token:
            target_note = _match_note_path(token, note_index)
        else:
            bucket = note_index.get(token.lower())
            if bucket:
                target_note = _prefer_sibling(bucket, note_dir)

        if target_note is not None:
            node_id = _note_node_id(target_note)
            if node_id not in seen:
                seen.add(node_id)
                out.append(node_id)
            continue

        # Not a note — an authored link to a code symbol.
        candidates = exact_labels.get(token.split("/")[-1], ())
        if len(candidates) == 1 and candidates[0] not in seen:
            seen.add(candidates[0])
            out.append(candidates[0])
    return out


def _match_note_path(token: str, note_index: dict[str, list[Note]]) -> Optional[Note]:
    """Resolve a slashed wikilink target against the note index by path suffix."""
    stem = _note_stem(token).lower()
    for candidate in note_index.get(stem, ()):
        if _path_suffix_match(token, _strip_markdown_suffix(candidate.path)):
            return candidate
    return None


def _strip_markdown_suffix(path: str) -> str:
    lowered = path.lower()
    for suffix in _MARKDOWN_SUFFIXES:
        if lowered.endswith(suffix):
            return path[: -len(suffix)]
    return path


def _prefer_sibling(bucket: list[Note], note_dir: str) -> Note:
    """Pick from an ambiguous basename bucket: sibling first, else first entry.

    ``bucket`` is already in shallowest-then-lexicographic order, so the
    fallback is deterministic.
    """
    for candidate in bucket:
        cand_dir = (
            candidate.path.replace("\\", "/").rsplit("/", 1)[0]
            if "/" in candidate.path else ""
        )
        if cand_dir == note_dir:
            return candidate
    return bucket[0]


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
    attrs = {
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
        # One node per note FILE. Stated explicitly so a future heading-level
        # tier can be distinguished without changing what "knowledge" means —
        # minting a node per heading would multiply a 1,000-note vault into
        # ~10,000 nodes and is a decision on its own, not a free add.
        "node_kind": "page",
    }
    if note.frontmatter:
        # The vault's own conventions (status, owner, epic, …), already
        # sanitized and capped by the generator.
        attrs["frontmatter"] = dict(note.frontmatter)
    return attrs


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
    # Graph iteration order is not a contract; sort so a note that matches
    # several nodes in the same file produces a stable edge order.
    return sorted(matches)


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
