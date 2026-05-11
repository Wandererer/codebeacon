"""Union merge of two ``beacon.json`` files.

Used as a git merge driver so that two developers extracting a knowledge graph
on the same branch never produce conflict markers in ``beacon.json``.

The driver is invoked by git as::

    codebeacon merge-driver <base> <current> <other>

We compute the union of nodes and edges from ``current`` and ``other`` (the
``base`` revision is ignored — graphs are derived artefacts, not user edits, so
"three-way" semantics don't help here). The merged graph is written back to
``current``. The driver always exits 0 so a graph regen never blocks a git
merge; if either input is unreadable, the survivor is used as-is.

Public API:

    merge_files(base, current, other) → int  # exit code (always 0)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def merge_files(base_path: str, current_path: str, other_path: str) -> int:
    """Union-merge ``other`` into ``current``; ``base`` is unused.

    Returns 0 unconditionally — git merge driver convention. Errors are logged
    to stderr but never propagated as a non-zero exit, because failing the
    merge would block the developer from committing real code changes for the
    sake of a derived JSON artefact.
    """
    current = _load(current_path)
    other = _load(other_path)

    if current is None and other is None:
        print("[codebeacon merge-driver] both inputs unreadable; leaving current as-is", file=sys.stderr)
        return 0
    if current is None:
        _write(current_path, other)
        return 0
    if other is None:
        return 0

    merged = _union(current, other)
    _write(current_path, merged)
    return 0


# ── Internals ────────────────────────────────────────────────────────────────

def _load(path: str) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write(path: str, payload: dict) -> None:
    tmp = Path(path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(Path(path))


def _union(a: dict, b: dict) -> dict:
    """Combine two node_link_data dicts by id. ``a`` wins on per-id conflicts.

    The choice of ``a``-wins is deliberate: the developer doing the merge has
    just freshly extracted ``current``, and graphs are derived from source —
    keeping the freshest data is the right tiebreaker.

    NetworkX changed the edge-list key from ``links`` to ``edges`` between
    major versions, and either may appear in the wild. We read from whichever
    is present in ``a`` and write back to the **same** key (preserving the
    document's existing shape), falling back to ``edges`` for new files.
    """
    nodes_a: list[dict] = list(a.get("nodes", []))
    nodes_b: list[dict] = list(b.get("nodes", []))
    seen: set[str] = {str(n.get("id")) for n in nodes_a}
    for n in nodes_b:
        if str(n.get("id")) not in seen:
            nodes_a.append(n)
            seen.add(str(n.get("id")))

    # Resolve the edge key from whichever side has one; both must agree on the
    # output shape so we never end up with both keys in the merged document.
    edge_key_a = "edges" if "edges" in a else ("links" if "links" in a else "edges")
    edges_a: list[dict] = list(a.get("edges") or a.get("links") or [])
    edges_b: list[dict] = list(b.get("edges") or b.get("links") or [])
    seen_edges: set[tuple[str, str, str]] = {
        (str(e.get("source")), str(e.get("target")), str(e.get("relation", "")))
        for e in edges_a
    }
    for e in edges_b:
        key = (str(e.get("source")), str(e.get("target")), str(e.get("relation", "")))
        if key not in seen_edges:
            edges_a.append(e)
            seen_edges.add(key)

    merged: dict[str, Any] = {**a, "nodes": nodes_a}
    # Drop both possible edge keys and re-add the canonical one to prevent the
    # merged document from carrying both ``edges`` and ``links`` simultaneously.
    merged.pop("edges", None)
    merged.pop("links", None)
    merged[edge_key_a] = edges_a

    # Refresh meta counts so a downstream consumer sees an accurate node_count.
    if isinstance(merged.get("meta"), dict):
        merged["meta"] = {
            **merged["meta"],
            "node_count": len(nodes_a),
            "edge_count": len(edges_a),
        }
    return merged
