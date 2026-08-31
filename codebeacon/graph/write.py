"""Safe serialisation of a built graph to ``beacon.json``.

Two guarantees on every successful write:

- **shrink guard** — refuses to overwrite an existing ``beacon.json`` when nodes
  disappear for a reason the run cannot account for. Rather than comparing two
  totals, it compares how many nodes each **source file** contributed before and
  after, and every shortfall has to be attributable: the file was **deleted**
  from disk, or it is **no longer collected** (newly ignored/excluded). Anything
  else — an extractor regression, a partial run, an unreadable subtree — is
  unexplained and refuses the write.

  Accounting per source file rather than per node id is deliberate: ids are a
  derived naming scheme, so a change to how colliding declarations are
  disambiguated renames nodes wholesale without losing any, and an id-level diff
  would read that as mass deletion.

  Nodes that are not AST-owned (the knowledge/semantic overlay, and ``external``
  edge stubs) sit outside the baseline entirely, so a code-only rebuild neither
  counts them against itself nor wedges after ``codebeacon knowledge``.

- **desync guard** — the report file is written *after* the graph file is
  durably committed (``os.replace`` atomically). If the JSON write fails for
  any reason, the previous report is preserved instead of pointing at a
  half-written graph.

Every write also stamps a ``meta`` block at the top of the JSON document:

    {
      "meta": {
        "version": 1,
        "built_at_commit": "<git HEAD>",
        "built_at_ts":     <unix epoch>,
        "node_count":      <int>,
        "edge_count":      <int>
      },
      "directed": ...,
      "nodes":   [...],
      "links":   [...]
    }

Callers should use :func:`write_beacon` rather than touching ``beacon.json``
directly.
"""

from __future__ import annotations

import json
import os
import sys
import time
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import networkx as nx
import networkx.readwrite.json_graph as nxjson

from codebeacon.common.safety import git_head
from codebeacon.common.types import KNOWLEDGE_NODE_TYPE

# Node types that are NOT owned by the AST extraction pass and therefore take no
# part in the shrink baseline:
#
#   * the knowledge overlay (``knowledge``) and the LLM-minted semantic types
#     (``concept``/``document``/``paper`` — see
#     ``semantic_pipeline.ALLOWED_LLM_NODE_TYPES``, duplicated here because that
#     module imports this one). They are re-applied after a scan rather than
#     re-extracted by it, so a code-only rebuild legitimately does not contain
#     them and must not be judged against a baseline that does.
#   * ``external`` stubs, which graph/build.py mints for unresolved edge targets.
#     They have no source file of their own and vanish with the edge that
#     created them.
OVERLAY_NODE_TYPES = frozenset({
    KNOWLEDGE_NODE_TYPE, "concept", "document", "paper",
})
DERIVED_NODE_TYPES = frozenset({"external"})

# An edge collapse this severe is reported loudly even when the node set is
# intact: it is the signature of a binding/resolution regression, which a
# node-count comparison cannot see (GI-2276).
EDGE_COLLAPSE_RATIO = 0.5


@dataclass
class ShrinkAudit:
    """Per-source accounting for a proposed overwrite of ``beacon.json``.

    ``unexplained`` is the only field that refuses a write; the rest exist so
    the run can print *why* a graph got smaller instead of silently shrinking.
    """

    prior_total: int = 0            # every node in the prior document
    prior_baseline: int = 0         # …minus overlay/derived tiers
    prior_overlay: int = 0
    new_count: int = 0
    new_baseline: int = 0
    prior_edge_count: int = 0
    new_edge_count: int = 0
    deleted_sources: list[str] = field(default_factory=list)   # gone from disk
    excluded_sources: list[str] = field(default_factory=list)  # on disk, not collected
    unexplained_sources: list[str] = field(default_factory=list)
    unexplained: int = 0            # node count behind unexplained_sources
    incomplete: bool = False        # the run could not see the whole corpus

    @property
    def explained(self) -> int:
        return len(self.deleted_sources) + len(self.excluded_sources)

    def cause_summary(self) -> str:
        """One-line per-cause delta, e.g. ``3 deleted, 1 newly excluded``."""
        parts = []
        if self.deleted_sources:
            parts.append(f"{len(self.deleted_sources)} source file(s) deleted")
        if self.excluded_sources:
            parts.append(f"{len(self.excluded_sources)} newly excluded by ignore rules")
        if self.unexplained_sources:
            parts.append(f"{len(self.unexplained_sources)} unaccounted for")
        return ", ".join(parts)


@dataclass
class WriteResult:
    """Result of a :func:`write_beacon` call."""

    path: Path
    node_count: int
    edge_count: int
    prior_node_count: int           # 0 if no prior beacon.json
    built_at_commit: str            # "" if not a git repo
    skipped_shrink: bool = False    # True if write was refused by shrink guard
    audit: Optional[ShrinkAudit] = None
    unchanged: bool = False         # content matched disk; the file was not touched


def write_beacon(
    G: nx.DiGraph,
    output_dir: str | Path,
    *,
    repo_path: str | Path | None = None,
    force: bool = False,
    had_explicit_deletions: bool = False,
    project_roots: Optional[dict[str, str]] = None,
    corpus: Optional[Iterable[str]] = None,
    incomplete: bool = False,
    overlay_write: bool = False,
) -> WriteResult:
    """Atomically write ``beacon.json`` with shrink and desync guards.

    Args:
        G:          the graph to serialise.
        output_dir: directory where ``beacon.json`` lives.
        repo_path:  directory passed to ``git rev-parse HEAD``. Defaults to
                    ``output_dir`` so the commit hash always reflects the
                    repository being scanned, not the CWD of whoever ran
                    ``codebeacon``.
        force:      bypass the shrink guard. Use only when a legitimate refactor
                    has shrunk the graph in a way the accounting cannot see.
        had_explicit_deletions: **deprecated and ignored as a waiver.** It used
                    to mean "the caller knows files were deleted, skip the
                    guard", and was wired to the mere presence of ``--update``,
                    which disarmed the guard on exactly the unattended paths
                    (watch, hooks, CI) it exists to protect. Deletions are now
                    detected from ``corpus`` instead. Accepted so old callers
                    keep working.
        project_roots: optional ``{project_name: absolute_root_path}`` map. When
                    given, each node's AND edge's absolute ``source_file`` is
                    rewritten to a path relative to its project root in the
                    serialised output, so ``beacon.json`` is byte-identical
                    across machines that scan the same commit. Mirrors graphify
                    #999 / #1417 (edges were previously left absolute). It is
                    also what lets the shrink audit resolve a prior document's
                    relative paths back to real files.
        corpus:     the source files this run actually collected. Supplying it
                    is what allows a shrink to be *explained*: a removed node
                    whose file is absent from the corpus and from disk was
                    deleted, and one absent from the corpus but still on disk
                    was newly excluded by an ignore rule. Without it, any AST
                    node loss is unexplained (correct for the overlay writers,
                    which only ever add).
        overlay_write: this write comes from an overlay pass (``codebeacon
                    knowledge``, ``semantic apply``) that loaded the graph and
                    is adding its own tier to it. Such a writer has no corpus
                    and no project roots, so the per-source accounting cannot
                    judge it; it is held to a stricter rule instead — the write
                    must be purely ADDITIVE. Any node id present before and
                    missing after is refused, ``force`` included, because an
                    overlay pass has no business removing nodes.
        incomplete: the run could not see the whole corpus — an unreadable
                    directory, or a file that failed extraction. Set this and
                    the "still on disk, so it must have been ignored" inference
                    is switched off, because an unreadable subtree is
                    indistinguishable from a newly-excluded one. Genuine
                    deletions are still waived.

    Returns:
        WriteResult describing what was written. When the shrink guard fires,
        ``skipped_shrink`` is True and ``beacon.json`` is left untouched.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    beacon_path = out_dir / "beacon.json"

    new_node_count = G.number_of_nodes()
    new_edge_count = G.number_of_edges()

    audit = _audit_shrink(
        beacon_path, G,
        corpus=corpus, project_roots=project_roots, incomplete=incomplete,
        overlay_write=overlay_write,
    )
    prior = audit.prior_total

    # An overlay write that drops nodes is refused even under force: force is
    # for a rebuild whose shrink the accounting cannot explain, and an overlay
    # pass is not a rebuild.
    if audit.unexplained and (overlay_write or not force):
        _print_refusal(beacon_path, audit, overlay_write=overlay_write)
        return WriteResult(
            path=beacon_path,
            node_count=new_node_count,
            edge_count=new_edge_count,
            prior_node_count=prior,
            built_at_commit="",
            skipped_shrink=True,
            audit=audit,
        )

    _print_deltas(audit, forced=bool(audit.unexplained and force))

    commit = git_head(repo_path if repo_path is not None else out_dir)
    # Pin edges="links" explicitly: networkx 3.6 flips the default to
    # edges="edges", which would silently change the on-disk key. Our loader
    # (_load_with_edge_compat) and the documented schema both expect "links".
    payload = nxjson.node_link_data(G, edges="links")
    # Strip absolute machine paths from node source_file before serialising, so
    # the artifact is reproducible across machines. Operates on the payload copy
    # only — the in-memory graph keeps absolute paths for the analysis/wiki
    # passes that run right after this write.
    _relativize_node_paths(payload, project_roots)
    payload = {
        "meta": {
            "version": 1,
            "built_at_commit": commit,
            "built_at_ts": _built_at_ts(
                beacon_path, payload, commit,
                repo_path if repo_path is not None else out_dir,
            ),
            "node_count": new_node_count,
            "edge_count": new_edge_count,
        },
        **payload,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)

    # Byte-stability (the built_at_ts work above) stops the CONTENT changing on
    # a no-op rebuild; this stops the FILE being touched at all. They are not
    # the same thing: an unconditional rewrite of identical bytes still moves
    # mtime, which is what re-triggers editors' indexers, file-sync clients and
    # anything watching the tree. Compare against what is already there and skip
    # the whole tmp-write-and-rename when it matches.
    unchanged = _file_holds(beacon_path, text)
    if not unchanged:
        # Atomic write: temp file in same directory + os.replace
        tmp_path = beacon_path.with_suffix(".json.tmp")
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, beacon_path)

    return WriteResult(
        path=beacon_path,
        node_count=new_node_count,
        edge_count=new_edge_count,
        prior_node_count=prior,
        built_at_commit=commit,
        skipped_shrink=False,
        audit=audit,
        unchanged=unchanged,
    )


def load_beacon(beacon_path: str | Path) -> tuple[nx.DiGraph, dict]:
    """Load a beacon.json written by :func:`write_beacon`.

    Returns ``(graph, meta)``. ``meta`` is the dict stamped by
    :func:`write_beacon`; legacy files without a ``meta`` block return ``{}``.

    Tolerates the edge-key shift across NetworkX versions: older releases
    serialised the edge list under ``links`` while current ones use ``edges``.
    We normalise to whichever key the underlying ``node_link_graph`` expects so
    that an older file produced before the upgrade still loads.
    """
    path = Path(beacon_path)
    text = path.read_text(encoding="utf-8")  # missing/unreadable → OSError, as before
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # A corrupt/truncated beacon.json must not crash `affected`, the MCP
        # server, or diagnostics with a raw traceback. Preserve the bad file for
        # debugging (so a later scan can't silently clobber it) and raise a
        # clear, actionable error. Mirrors cache.py's corrupt-cache handling
        # (graphify #1536).
        _backup_corrupt_beacon(path)
        raise ValueError(
            f"{path} is corrupt or truncated ({exc}). It has been preserved with "
            f"a .corrupt suffix; re-run `codebeacon scan` to rebuild it."
        ) from exc
    if not isinstance(data, dict):
        # Valid JSON but not a beacon document (top-level null/list/string/number)
        # — treat as corruption too, so downstream node_link_graph doesn't crash
        # with a cryptic AttributeError (graphify #1536).
        _backup_corrupt_beacon(path)
        raise ValueError(
            f"{path} is not a beacon document (top-level JSON is "
            f"{type(data).__name__}, expected object). It has been preserved with "
            f"a .corrupt suffix; re-run `codebeacon scan` to rebuild it."
        )
    for coll in ("nodes", "links", "edges"):
        if coll in data and not isinstance(data[coll], list):
            # Present-but-non-list collection (e.g. JSON null) is structurally
            # corrupt: node_link_graph would crash with a raw TypeError/KeyError
            # that callers catching only ValueError (pipeline, serve) can't
            # absorb. Route it through the same backup + ValueError path (#1536).
            _backup_corrupt_beacon(path)
            raise ValueError(
                f"{path} is corrupt: '{coll}' is {type(data[coll]).__name__}, "
                f"expected a list. It has been preserved with a .corrupt suffix; "
                f"re-run `codebeacon scan` to rebuild it."
            )
    meta = data.pop("meta", {})
    try:
        graph = _load_with_edge_compat(data)
    except (TypeError, KeyError, AttributeError, ValueError, nx.NetworkXError) as exc:
        # Shape-enumeration is a losing game: the collection can be a list yet
        # hold non-dict or malformed-dict elements (missing id/source/target)
        # that make node_link_graph raise a raw TypeError/KeyError/AttributeError
        # rather than a ValueError. Callers (serve, pipeline) catch only
        # ValueError, so normalise ANY construction failure into the same
        # backup + ValueError path as the other corruption checks (#1536).
        _backup_corrupt_beacon(path)
        raise ValueError(
            f"{path} is corrupt: could not build a graph from it ({exc}). It has "
            f"been preserved with a .corrupt suffix; re-run `codebeacon scan` to "
            f"rebuild it."
        ) from exc
    return graph, meta


def _backup_corrupt_beacon(path: Path) -> None:
    """Move a corrupt ``beacon.json`` aside so a later write can't overwrite it.

    Best-effort; the graph is reproducible by re-scanning. Mirrors
    ``cache.py._backup_corrupt`` (graphify #1536).
    """
    try:
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.{ts}.corrupt")
        path.replace(backup)
        print(
            f"codebeacon: {path} was corrupt; preserved as {backup.name}.",
            file=sys.stderr,
        )
    except OSError:
        pass


def _load_with_edge_compat(data: dict) -> nx.DiGraph:
    """Call ``node_link_graph`` with the correct edge key for both shapes."""
    # If the document has neither key, hand it through unchanged — the graph
    # will just have no edges.
    if "edges" in data and "links" not in data:
        try:
            return nxjson.node_link_graph(data, directed=True, multigraph=False, edges="edges")
        except TypeError:
            # NetworkX < 3.x doesn't accept ``edges`` kwarg — rename in place.
            data["links"] = data.pop("edges")
            return nxjson.node_link_graph(data, directed=True, multigraph=False)
    if "links" in data and "edges" not in data:
        try:
            return nxjson.node_link_graph(data, directed=True, multigraph=False, edges="links")
        except TypeError:
            return nxjson.node_link_graph(data, directed=True, multigraph=False)
    # Either both keys are present (unusual — pick edges) or neither.
    if "edges" in data:
        data.pop("links", None)
        try:
            return nxjson.node_link_graph(data, directed=True, multigraph=False, edges="edges")
        except TypeError:
            data["links"] = data.pop("edges")
            return nxjson.node_link_graph(data, directed=True, multigraph=False)
    return nxjson.node_link_graph(data, directed=True, multigraph=False)


def _rel_or_none(sf: Optional[str], root: Optional[str]) -> Optional[str]:
    """Relative POSIX path of ``sf`` under ``root``, or ``None`` to leave as-is.

    Returns ``None`` (meaning "don't rewrite") when ``sf`` is empty, not
    absolute, has no known root, sits on a different drive (Windows), or lives
    outside the root (a fragile ``../../`` path is worse than the absolute one).
    """
    if not sf or not os.path.isabs(sf) or not root:
        return None
    try:
        rel = os.path.relpath(os.path.abspath(sf), root)
    except ValueError:
        return None
    if rel == ".." or rel.startswith(".." + os.sep):
        return None
    return rel.replace(os.sep, "/")


def relativize_source_file(sf: Optional[str], project_root: Optional[str]) -> str:
    """Public helper: source_file relative to ``project_root``, else unchanged.

    Used by the wiki/obsidian generators at emit time so committed artifacts
    (``.codebeacon/wiki``, ``.codebeacon/obsidian``) never embed machine-absolute
    paths, without mutating the in-memory graph that ``analyze`` still needs
    absolute (graphify #1417).
    """
    root = os.path.abspath(project_root) if project_root else None
    rel = _rel_or_none(sf, root)
    return rel if rel is not None else (sf or "")


def _relativize_node_paths(
    payload: dict,
    project_roots: Optional[dict[str, str]],
) -> None:
    """Rewrite absolute ``source_file`` paths on nodes AND links to project-relative.

    Mutates the serialised ``payload`` in place; the caller's in-memory graph is
    untouched. Absolute paths such as ``/Users/alice/repo/src/a.py`` make
    ``beacon.json`` differ on every machine and churn git diffs even when the
    code is identical. Storing ``src/a.py`` (relative to the file's project
    root) makes the artifact byte-stable across machines. Mirrors graphify #999.

    Nodes carry an explicit ``project``; links (edges) do not, so a link's
    project is inferred from its ``source`` node id (``project::name``). Before
    this covered links too, every edge kept an absolute ``source_file`` — the
    bulk of a repo's committed ``beacon.json`` leaked local paths (graphify
    #1417). Anything without a known root / off-drive / outside the root is left
    exactly as-is.
    """
    if not project_roots:
        return
    roots = {name: os.path.abspath(path) for name, path in project_roots.items()}
    root_values = list(dict.fromkeys(roots.values()))

    def _rel_any(sf: Optional[str], preferred_project: str) -> Optional[str]:
        # Try the declared/inferred project's root first, then EVERY root, and
        # keep the shortest relative path — i.e. the most-specific (deepest)
        # containing root, so a file under a nested project isn't relativized
        # against an ancestor root. This also relativizes edges whose source_file
        # belongs to a different project than the source node (e.g.
        # shares_db_entity edges carry the shared entity's file — graphify #1417
        # [4]) and degrades gracefully when two projects share a basename [5].
        best: Optional[str] = None
        candidates = ([roots[preferred_project]] if preferred_project in roots else []) + root_values
        for root in candidates:
            r = _rel_or_none(sf, root)
            if r is not None and (best is None or len(r) < len(best)):
                best = r
        return best

    for node in payload.get("nodes", []):
        rel = _rel_any(node.get("source_file"), node.get("project", ""))
        if rel is not None:
            node["source_file"] = rel
    for link in payload.get("links", []):
        project = str(link.get("source", "")).split("::", 1)[0]
        rel = _rel_any(link.get("source_file"), project)
        if rel is not None:
            link["source_file"] = rel


# ── Shrink accounting ─────────────────────────────────────────────────────────

def _norm(path: str) -> str:
    """Canonical form for comparing a corpus path with a reconstructed one.

    ``realpath`` on both sides so a project reached through a symlinked parent
    (``/tmp`` → ``/private/tmp`` on macOS) still matches.
    """
    try:
        return os.path.realpath(os.path.abspath(path))
    except (OSError, ValueError):
        return path


def _read_prior_document(beacon_path: Path) -> Optional[dict]:
    """Prior beacon.json as a dict, or None when absent/unreadable/corrupt.

    A corrupt prior is deliberately treated as "no baseline": the write goes
    ahead and replaces it, which is the only way out of a truncated file.
    """
    if not beacon_path.exists():
        return None
    try:
        data = json.loads(beacon_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _node_tier(node_type: str) -> str:
    """``"overlay"``, ``"derived"`` or ``"ast"`` for a node's ``type``."""
    if node_type in OVERLAY_NODE_TYPES:
        return "overlay"
    if node_type in DERIVED_NODE_TYPES:
        return "derived"
    return "ast"


def _prior_source_key(
    source_file: str,
    project: str,
    project_roots: Optional[dict[str, str]],
) -> tuple[Optional[str], Optional[str]]:
    """``(match_key, probe_path)`` for a source_file read out of a prior beacon.

    Two different jobs, deliberately separated:

    * **match_key** pairs a prior node with the new graph's nodes from the same
      file. It only has to be computed the SAME way on both sides.
    * **probe_path** is an absolute path we are willing to stat. It is None
      when the path could not be placed on disk, and a caller must never read
      "not found" from a None probe — that is the difference between "the file
      is gone" and "I don't know where the file is".

    Prior documents store project-relative paths (``_relativize_node_paths``),
    so the project root is put back before the file can be looked for. The
    node's own ``project`` is tried first, then every other root, so a node
    whose project was renamed still resolves. With no roots at all — an overlay
    writer, which loads the document and hands it straight back — nothing can be
    placed, and the raw stored string becomes the match key instead. That keeps
    both sides keyed alike, which is the whole requirement for counting.
    """
    if not source_file:
        return None, None
    if os.path.isabs(source_file):
        resolved = _norm(source_file)
        return resolved, resolved
    if not project_roots:
        # Nothing to anchor against. Match on the stored string; refuse to
        # guess an absolute path we could then wrongly declare deleted.
        return source_file, None
    ordered = ([project_roots[project]] if project in project_roots else []) + [
        r for name, r in project_roots.items() if name != project
    ]
    for root in ordered:
        candidate = _norm(os.path.join(root, source_file))
        if os.path.exists(candidate):
            return candidate, candidate
    # Nothing on disk matches; place it under the node's own project so
    # "deleted" can still be concluded.
    if project in project_roots:
        placed = _norm(os.path.join(project_roots[project], source_file))
        return placed, placed
    return source_file, None


def _audit_shrink(
    beacon_path: Path,
    G: nx.DiGraph,
    *,
    corpus: Optional[Iterable[str]],
    project_roots: Optional[dict[str, str]],
    incomplete: bool,
    overlay_write: bool = False,
) -> ShrinkAudit:
    """Attribute every node the new graph drops to a cause.

    The baseline is the prior document's AST-owned nodes. Overlay and derived
    nodes are ignored on both sides: the knowledge/semantic overlay is minted
    by a separate pass (and re-applied after the scan), and ``external`` stubs
    exist only for as long as the edge that created them.
    """
    audit = ShrinkAudit(
        new_count=G.number_of_nodes(),
        incomplete=incomplete,
    )
    new_ast_ids = {
        n for n, d in G.nodes(data=True)
        if _node_tier(str(d.get("type", ""))) == "ast"
    }
    audit.new_baseline = len(new_ast_ids)
    # Edge counts are code-tier too, mirroring the node baseline: an overlay
    # pass adds `references`/`mentions` edges, and counting those on one side
    # only turns the next code-only rebuild into a phantom "edge collapse".
    audit.new_edge_count = sum(
        1 for u, v in G.edges() if u in new_ast_ids and v in new_ast_ids
    )

    data = _read_prior_document(beacon_path)
    if data is None:
        return audit

    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return audit
    audit.prior_total = len(nodes)

    prior_ast_ids: set = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if _node_tier(str(node.get("type", ""))) == "ast":
            prior_ast_ids.add(node.get("id"))
    links = data.get("links") or data.get("edges")
    audit.prior_edge_count = sum(
        1 for e in links
        if isinstance(e, dict)
        and e.get("source") in prior_ast_ids and e.get("target") in prior_ast_ids
    ) if isinstance(links, list) else 0

    if overlay_write:
        # An overlay pass loads beacon.json, adds its own tier and writes back.
        # Source-file accounting cannot judge it: the document it loaded holds
        # project-RELATIVE paths and it has no project_roots to put them back
        # with, so every prior node would resolve to nothing and read as lost.
        # What an overlay write must satisfy is simpler: it may not touch the
        # CODE tier. Every AST-owned node that was there has to still be there,
        # and a missing one is a bug in the overlay writer rather than a
        # rebuild, so it is refused even under force.
        #
        # Its OWN tier is its business. `codebeacon knowledge` sweeps stale note
        # nodes before re-linking (knowledge/link.py), so a note whose .md file
        # was deleted legitimately disappears — treating that as a violation
        # would wedge the overlay at its first deletion and leave the stale node
        # on disk forever, which is the opposite of what the guard is for.
        present = set(G.nodes)
        for node in nodes:
            if not isinstance(node, dict):
                continue
            tier = _node_tier(str(node.get("type", "")))
            if tier == "overlay":
                audit.prior_overlay += 1
                continue
            if tier == "derived":
                continue
            audit.prior_baseline += 1
            if node.get("id") not in present:
                audit.unexplained_sources.append(str(node.get("id")))
                audit.unexplained += 1
        return audit

    corpus_set = {_norm(p) for p in corpus} if corpus is not None else None

    # Account per SOURCE FILE rather than per node id. Node ids are a derived
    # naming scheme — a disambiguation rule change renames every colliding node
    # without losing a thing — so diffing ids alone would read a relabelling as
    # mass deletion. What actually has to hold is that each file still
    # contributes the nodes it used to, which is also the granularity at which
    # a loss can be attributed to a cause.
    prior_by_source: dict[Optional[str], int] = {}
    probe_for: dict[Optional[str], Optional[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        tier = _node_tier(str(node.get("type", "")))
        if tier == "overlay":
            audit.prior_overlay += 1
            continue
        if tier == "derived":
            continue
        audit.prior_baseline += 1
        key, probe = _prior_source_key(
            str(node.get("source_file") or ""), str(node.get("project") or ""),
            project_roots,
        )
        prior_by_source[key] = prior_by_source.get(key, 0) + 1
        probe_for[key] = probe

    # A scan's in-memory graph keeps ABSOLUTE source paths (only the serialised
    # copy is relativized), so it normalises to the same absolute form the prior
    # side resolved to. A caller that handed us a graph loaded straight off disk
    # still has the RELATIVE strings, which is why a relative path is left
    # alone rather than joined onto the cwd — both sides then key alike.
    new_by_source: dict[Optional[str], int] = {}
    for _, attrs in G.nodes(data=True):
        if _node_tier(str(attrs.get("type", ""))) != "ast":
            continue
        sf = str(attrs.get("source_file") or "")
        if not sf:
            key = None
        else:
            key = _norm(sf) if os.path.isabs(sf) else sf
        new_by_source[key] = new_by_source.get(key, 0) + 1

    for source, prior_n in sorted(
        prior_by_source.items(), key=lambda kv: (kv[0] is None, kv[0] or "")
    ):
        lost = prior_n - new_by_source.get(source, 0)
        if lost <= 0:
            continue
        cause = _classify_loss(probe_for.get(source), corpus_set, incomplete)
        if cause == "deleted":
            audit.deleted_sources.append(source or "?")
        elif cause == "excluded":
            audit.excluded_sources.append(source or "?")
        else:
            audit.unexplained_sources.append(source or "<no source file>")
            audit.unexplained += lost

    return audit


def _path_state(path: str) -> str:
    """``"present"``, ``"absent"`` or ``"unknown"`` for ``path``.

    Deliberately not ``os.path.exists``: that returns False both for a file
    that is genuinely gone and for one whose parent directory we are not
    allowed to traverse. Waiving a shrink on the second would be exactly the
    silent data loss this guard exists to stop, so the two are kept apart —
    ENOENT is proof of deletion, EACCES is proof of nothing.
    """
    try:
        os.lstat(path)
        return "present"
    except (FileNotFoundError, NotADirectoryError):
        return "absent"
    except (OSError, ValueError):
        return "unknown"


def _classify_loss(
    source: Optional[str],
    corpus: Optional[set[str]],
    incomplete: bool,
) -> str:
    """Why did the nodes from ``source`` disappear? deleted / excluded / unexplained."""
    if source is None:
        # No usable path — an overlay-less node with no source_file, or a
        # relative path with no root to place it under. Never guess.
        return "unexplained"
    state = _path_state(source)
    if state == "absent":
        # Positively confirmed gone, which is a real deletion whether or not a
        # corpus was supplied and whether or not the run was otherwise partial.
        return "deleted"
    if state == "unknown":
        # We could not even look. Never waive a loss on a failed probe.
        return "unexplained"
    if corpus is None:
        # No corpus to check against (an overlay writer, which should only ever
        # add nodes). A file that still exists losing its nodes is a regression.
        return "unexplained"
    if source in corpus:
        # Collected and re-extracted this run, yet its nodes are gone: the
        # extractor, not the corpus, changed.
        return "unexplained"
    if incomplete:
        # Not collected, but the run admits it could not see everything, so
        # "must have been ignored" is not a conclusion we are entitled to.
        return "unexplained"
    return "excluded"


def _print_refusal(
    beacon_path: Path, audit: ShrinkAudit, *, overlay_write: bool = False
) -> None:
    """Explain a refused write and name the flag that overrides it."""
    if overlay_write:
        # No --force advice here: force does not (and must not) unlock this.
        print(
            f"Error: refusing to write beacon.json — an overlay pass must only "
            f"ADD to the graph, but {audit.unexplained} node(s) that were there "
            f"before are missing from what it produced.",
            file=sys.stderr,
        )
        for node_id in audit.unexplained_sources[:5]:
            print(f"    dropped: {node_id}", file=sys.stderr)
        if len(audit.unexplained_sources) > 5:
            print(
                f"    … and {len(audit.unexplained_sources) - 5} more",
                file=sys.stderr,
            )
        print(
            "    This is a bug in the overlay writer; beacon.json is unchanged. "
            "Re-run `codebeacon scan` to rebuild the code graph.",
            file=sys.stderr,
        )
        return
    print(
        f"Warning: refusing to shrink beacon.json from {audit.prior_baseline} → "
        f"{audit.new_baseline} code nodes — {audit.unexplained} node(s) from "
        f"{len(audit.unexplained_sources)} source file(s) disappeared without an "
        f"explanation.",
        file=sys.stderr,
    )
    for source in audit.unexplained_sources[:5]:
        print(f"    unaccounted: {source}", file=sys.stderr)
    if len(audit.unexplained_sources) > 5:
        print(
            f"    … and {len(audit.unexplained_sources) - 5} more",
            file=sys.stderr,
        )
    if audit.explained:
        print(f"    (explained: {audit.cause_summary()})", file=sys.stderr)
    if audit.incomplete:
        print(
            "    This run could not read the whole tree, so files that are "
            "still on disk but were not scanned cannot be assumed ignored. "
            "Fix the permissions and re-scan.",
            file=sys.stderr,
        )
    print(
        f"    Re-run with --force to overwrite anyway (or delete {beacon_path}).",
        file=sys.stderr,
    )


def _print_deltas(audit: ShrinkAudit, *, forced: bool) -> None:
    """Report what changed on every write, so an allowed loss is never silent."""
    if audit.prior_total == 0:
        return
    if forced:
        print(
            f"  --force: overwriting despite {audit.unexplained} unexplained "
            f"missing node(s).",
            file=sys.stderr,
        )
    if audit.new_baseline < audit.prior_baseline:
        print(
            f"  Graph shrank: {audit.prior_baseline} → {audit.new_baseline} "
            f"code nodes ({audit.cause_summary()}).",
            file=sys.stderr,
        )
        for source in (audit.deleted_sources + audit.excluded_sources)[:5]:
            print(f"    removed: {source}", file=sys.stderr)
    if (
        audit.prior_edge_count > 0
        and audit.new_edge_count < audit.prior_edge_count * EDGE_COLLAPSE_RATIO
        and audit.new_baseline >= audit.prior_baseline
    ):
        # Nodes held steady but the edges collapsed — a resolution regression
        # that no node-count comparison can see (GI-2276).
        print(
            f"  Warning: edge count collapsed {audit.prior_edge_count} → "
            f"{audit.new_edge_count} while the node set held steady. This is "
            f"usually a binding/resolution regression, not a code change.",
            file=sys.stderr,
        )


def _commit_timestamp(repo_path: str | Path, commit: str) -> Optional[int]:
    """Author/commit epoch of ``commit``, or None when it cannot be read."""
    if not commit:
        return None
    try:
        out = subprocess.run(
            ["git", "show", "-s", "--format=%ct", commit],
            cwd=str(repo_path), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=3, check=False,
        )
        if out.returncode == 0:
            return int(out.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return None


def _built_at_ts(
    beacon_path: Path,
    payload: dict,
    commit: str,
    repo_path: str | Path,
) -> int:
    """Timestamp for the meta block, chosen to keep beacon.json byte-stable.

    ``int(time.time())`` made every rebuild rewrite the file even when nothing
    about the graph changed — and with ``.codebeacon/`` committed plus the
    post-commit rebuild hook, each no-op rebuild dirtied the tree and re-fired
    the hook. So: use the timestamp of the commit being described, which is
    identical on every machine that builds the same commit; failing that (a
    dirty tree, no git), keep the previous value when the graph content is
    unchanged; only a genuinely new graph outside git gets "now".
    """
    at_commit = _commit_timestamp(repo_path, commit)
    if at_commit is not None:
        return at_commit
    prior = _read_prior_document(beacon_path)
    if prior is not None:
        prior_meta = prior.pop("meta", {})
        # Compare the SERIALISED forms. The prior document came back through
        # json.loads (tuples are already lists, non-str keys already strings)
        # while ``payload`` is still in memory, so a direct dict comparison
        # would report a spurious difference for graphs that round-trip fine.
        new_form = _canonical(payload)
        if (
            isinstance(prior_meta, dict)
            and new_form is not None                # two None's are not a match
            and _canonical(prior) == new_form
        ):
            previous = prior_meta.get("built_at_ts")
            if isinstance(previous, int):
                return previous
    return int(time.time())


def _file_holds(path: Path, text: str) -> bool:
    """True when ``path`` already contains exactly ``text``.

    Any failure to read — absent, unreadable, or not valid UTF-8 — answers
    False, so the write goes ahead and a damaged artifact self-heals. Only a
    successful read that compares equal suppresses the write.
    """
    try:
        return path.read_text(encoding="utf-8") == text
    except (OSError, UnicodeDecodeError, ValueError):
        return False


def _canonical(doc: dict) -> Optional[str]:
    """Serialised form of a beacon document, or None if it will not serialise."""
    try:
        return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return None
