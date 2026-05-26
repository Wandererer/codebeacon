"""Compute the graph-level blast radius of a set of changed files.

Use case: in CI, given a PR's diff, list every node (controller, service,
entity, component, route) that is downstream of the changed source files.
The reviewer or risk-scoring agent can then narrow attention to just that
slice instead of the whole graph.

Public API:
    affected_from_paths(beacon_dir, changed_paths, depth=3) -> AffectedResult

The CLI wrapper in :mod:`codebeacon.cli` accepts either an explicit list
of paths or a git ref pair (``--base``/``--head``) and shells out to
``git diff --name-only`` to derive ``changed_paths``.

Mirrors graphify #e44e6e9 ("v8 affected").
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import networkx as nx


@dataclass
class AffectedResult:
    seed_files: list[str] = field(default_factory=list)
    seed_node_ids: list[str] = field(default_factory=list)
    affected_node_ids: list[str] = field(default_factory=list)
    affected_summary: list[dict] = field(default_factory=list)
    # Wiki article paths (relative to wiki/) corresponding to affected nodes.
    # Populated when ``affected_from_paths`` was called with the wiki
    # mapping enabled. Routes/external/concept nodes contribute no entry.
    wiki_paths: list[str] = field(default_factory=list)

    def as_markdown(self) -> str:
        if not self.seed_files:
            return "No changed files supplied."
        if not self.seed_node_ids:
            return (
                f"None of {len(self.seed_files)} changed files matched a graph "
                f"node — the diff may be in docs, config, or tests only."
            )
        lines = [
            f"## Affected nodes ({len(self.affected_node_ids)})",
            f"_Seed_: {len(self.seed_files)} changed file(s) → {len(self.seed_node_ids)} matched node(s)",
            "",
        ]
        for entry in self.affected_summary:
            lines.append(
                f"- **{entry['label']}** ({entry['type']}) — `{entry['source_file']}`"
            )
        return "\n".join(lines)

    def as_wiki_paths(self, base: str = "wiki") -> str:
        """Render as a newline-separated list of wiki article paths.

        Used by ``codebeacon affected --as wiki`` so a CI step (or a
        Claude Code agent doing PR review) can pipe the output into
        ``cat`` and get the exact set of articles to consult — no graph
        knowledge required on the consumer side.
        """
        if not self.wiki_paths:
            return ""
        prefix = base.rstrip("/")
        return "\n".join(f"{prefix}/{p}" for p in self.wiki_paths)


def affected_from_paths(
    beacon_dir: str | Path,
    changed_paths: Iterable[str],
    *,
    depth: int = 3,
    limit: int = 100,
    include_wiki_paths: bool = False,
    wiki_dir: str | Path | None = None,
) -> AffectedResult:
    """Return graph nodes affected by changes in ``changed_paths``.

    ``depth`` caps how many downstream hops we walk; the default of 3
    matches how a reviewer usually thinks ("this changed → who calls it →
    who calls them → which routes serve those"). ``limit`` truncates the
    final node list so very wide graphs don't dump 10k entries.
    """
    from codebeacon.graph.write import load_beacon

    beacon_dir = Path(beacon_dir)
    beacon_path = beacon_dir / "beacon.json"
    if not beacon_path.exists():
        raise FileNotFoundError(f"{beacon_path} not found. Run 'codebeacon scan' first.")
    G, _meta = load_beacon(beacon_path)

    # Normalise seed paths to POSIX with forward slashes; node source_file may
    # be absolute or repo-relative depending on how it was extracted, so we
    # match by suffix (a relative suffix of the absolute node path).
    seeds = [str(p).replace("\\", "/") for p in changed_paths]

    seed_node_ids: list[str] = []
    for node_id, data in G.nodes(data=True):
        src = (data.get("source_file") or "").replace("\\", "/")
        if not src:
            continue
        if any(src.endswith(seed) or seed.endswith(src) for seed in seeds):
            seed_node_ids.append(node_id)

    # Walk *upstream* (predecessors): callers, controllers that depend on the
    # changed service, entities referenced by changed code, etc. The blast
    # radius for a code change is "who depends on me", not "what do I depend
    # on", so we use predecessors.
    affected: set[str] = set()
    frontier = list(seed_node_ids)
    for _ in range(max(0, depth)):
        next_frontier: list[str] = []
        for nid in frontier:
            for pred in G.predecessors(nid):
                if pred in affected or pred in seed_node_ids:
                    continue
                affected.add(pred)
                next_frontier.append(pred)
        if not next_frontier:
            break
        frontier = next_frontier

    affected_ids = sorted(affected)[:limit]
    summary = []
    for nid in affected_ids:
        data = G.nodes[nid]
        summary.append({
            "id": nid,
            "label": data.get("label", nid),
            "type": data.get("type", ""),
            "source_file": data.get("source_file", ""),
        })

    wiki_paths: list[str] = []
    if include_wiki_paths:
        # Defer the import so this module stays cheap to load (no tree-sitter,
        # no template engine) when callers only want the markdown summary.
        from codebeacon.wiki.generator import node_to_wiki_path

        # The reviewer also cares about the seed nodes themselves, not just the
        # upstream nodes — those are the documents most directly affected.
        wiki_dir_path = Path(wiki_dir) if wiki_dir else (beacon_dir / "wiki")
        seen: set[str] = set()
        for nid in [*seed_node_ids, *affected_ids]:
            wp = node_to_wiki_path(G, nid)
            if not wp or wp in seen:
                continue
            # Only surface paths that actually exist on disk — a fresh scan
            # may have nodes whose wiki articles weren't generated (e.g.
            # filtered by community pruning), and listing ghost paths would
            # waste the consumer's time chasing 404s.
            if (wiki_dir_path / wp).exists():
                wiki_paths.append(wp)
                seen.add(wp)

    return AffectedResult(
        seed_files=list(seeds),
        seed_node_ids=seed_node_ids,
        affected_node_ids=affected_ids,
        affected_summary=summary,
        wiki_paths=wiki_paths,
    )


def git_changed_files(base: str, head: str = "HEAD", *, repo: str | Path | None = None) -> list[str]:
    """Return the file list of ``git diff --name-only base..head``.

    Returns an empty list (with a printed warning) if git is unavailable or
    the refs don't resolve — better to degrade than to crash a CI pipeline.
    """
    cmd = ["git", "diff", "--name-only", f"{base}...{head}"]
    try:
        out = subprocess.check_output(
            cmd,
            cwd=str(repo) if repo else None,
            text=True,
            # Pin UTF-8 so non-ASCII file paths (한글 / 日本語 / Umlaut /
            # Cyrillic) round-trip on Windows where the default console
            # codepage is cp1252. Mirrors graphify #906.
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"warning: git diff failed ({exc}); returning empty change set.")
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]
