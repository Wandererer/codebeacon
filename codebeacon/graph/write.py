"""Safe serialisation of a built graph to ``beacon.json``.

Two guarantees on every successful write:

- **shrink guard** — refuses to overwrite an existing ``beacon.json`` that has
  more nodes than the graph being written, unless the caller opts in via
  ``force=True``. A partial-extraction failure or interrupted run that produced
  a smaller graph can never destroy a larger, complete prior result.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import networkx as nx
import networkx.readwrite.json_graph as nxjson

from codebeacon.common.safety import git_head


@dataclass
class WriteResult:
    """Result of a :func:`write_beacon` call."""

    path: Path
    node_count: int
    edge_count: int
    prior_node_count: int           # 0 if no prior beacon.json
    built_at_commit: str            # "" if not a git repo
    skipped_shrink: bool = False    # True if write was refused by shrink guard


def write_beacon(
    G: nx.DiGraph,
    output_dir: str | Path,
    *,
    repo_path: str | Path | None = None,
    force: bool = False,
    had_explicit_deletions: bool = False,
    project_roots: Optional[dict[str, str]] = None,
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
                    has shrunk the graph (e.g. mass deletion).
        had_explicit_deletions: caller (e.g. post-commit hook with ``git diff``)
                    has already accounted for deleted files; a smaller graph is
                    expected, so skip the shrink guard without disabling it
                    for other failure modes. Mirrors graphify #6fba4e4.
        project_roots: optional ``{project_name: absolute_root_path}`` map. When
                    given, each node's AND edge's absolute ``source_file`` is
                    rewritten to a path relative to its project root in the
                    serialised output, so ``beacon.json`` is byte-identical
                    across machines that scan the same commit. Mirrors graphify
                    #999 / #1417 (edges were previously left absolute).

    Returns:
        WriteResult describing what was written. When the shrink guard fires,
        ``skipped_shrink`` is True and ``beacon.json`` is left untouched.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    beacon_path = out_dir / "beacon.json"

    new_node_count = G.number_of_nodes()
    new_edge_count = G.number_of_edges()
    prior = _prior_node_count(beacon_path)

    if prior > new_node_count and not force and not had_explicit_deletions:
        print(
            f"Warning: refusing to shrink beacon.json from {prior} → {new_node_count} nodes "
            f"(pass force=True or delete {beacon_path} to overwrite).",
            file=sys.stderr,
        )
        return WriteResult(
            path=beacon_path,
            node_count=new_node_count,
            edge_count=new_edge_count,
            prior_node_count=prior,
            built_at_commit="",
            skipped_shrink=True,
        )

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
            "built_at_ts": int(time.time()),
            "node_count": new_node_count,
            "edge_count": new_edge_count,
        },
        **payload,
    }

    # Atomic write: temp file in same directory + os.replace
    tmp_path = beacon_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, beacon_path)

    return WriteResult(
        path=beacon_path,
        node_count=new_node_count,
        edge_count=new_edge_count,
        prior_node_count=prior,
        built_at_commit=commit,
        skipped_shrink=False,
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
    meta = data.pop("meta", {})
    return _load_with_edge_compat(data), meta


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


def _prior_node_count(beacon_path: Path) -> int:
    """Return the node count of a prior beacon.json, or 0 if absent/unreadable."""
    if not beacon_path.exists():
        return 0
    try:
        data = json.loads(beacon_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    meta = data.get("meta") if isinstance(data, dict) else None
    if isinstance(meta, dict) and isinstance(meta.get("node_count"), int):
        return meta["node_count"]
    # Fall back to counting the nodes array.
    nodes = data.get("nodes") if isinstance(data, dict) else None
    return len(nodes) if isinstance(nodes, list) else 0
