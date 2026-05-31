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
                    given, each node's absolute ``source_file`` is rewritten to a
                    path relative to its project root in the serialised output,
                    so ``beacon.json`` is byte-identical across machines that
                    scan the same commit. Mirrors graphify #999.

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
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.pop("meta", {}) if isinstance(data, dict) else {}
    return _load_with_edge_compat(data), meta


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


def _relativize_node_paths(
    payload: dict,
    project_roots: Optional[dict[str, str]],
) -> None:
    """Rewrite absolute node ``source_file`` paths to project-relative POSIX paths.

    Mutates the serialised ``payload`` in place; the caller's in-memory graph is
    untouched. Absolute paths such as ``/Users/alice/repo/src/a.py`` make
    ``beacon.json`` differ on every machine and churn git diffs even when the
    code is identical. Storing ``src/a.py`` (relative to the file's project
    root) makes the artifact byte-stable across machines. Mirrors graphify #999.

    A node is rewritten only when (a) ``project_roots`` is supplied, (b) its
    ``project`` has a known root, (c) the path is absolute, and (d) the file
    actually lives under that root. Anything else is left exactly as-is, so
    external stubs, cross-drive paths (Windows), and unmapped projects never
    regress to a broken relative path.
    """
    if not project_roots:
        return
    roots = {name: os.path.abspath(path) for name, path in project_roots.items()}
    for node in payload.get("nodes", []):
        sf = node.get("source_file")
        if not sf or not os.path.isabs(sf):
            continue
        root = roots.get(node.get("project", ""))
        if not root:
            continue
        try:
            rel = os.path.relpath(os.path.abspath(sf), root)
        except ValueError:
            # Different drive on Windows — no relative path exists.
            continue
        if rel == ".." or rel.startswith(".." + os.sep):
            # Source lives outside its declared project root; a fragile
            # ``../../`` path is worse than keeping the absolute one.
            continue
        node["source_file"] = rel.replace(os.sep, "/")


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
