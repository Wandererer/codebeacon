"""Obsidian vault export with 12-step post-processing.

Generates a fully organised Obsidian vault from the codebeacon knowledge graph.

Public API:
    generate_obsidian_vault(G, communities, output_dir, obsidian_dir=None) → int
        Returns number of notes written.

12-step pipeline:
    (1)  Basic note generation — one .md per graph node
    (2)  Broken wikilink fix — case-mismatch normalisation
    (3)  Cross-language imports edge removal — Java↔TS/TSX, preserves calls_api
    (4)  Community tag fix — Community_N → service folder name from source_file
    (5)  source_file-based service subfolder move
    (6)  Same source_file dedup — priority: .java.md > bare > _N
    (7)  Members section injection — from methods/fields metadata
    (8)  Remaining root-level notes → service folder
    (9)  Service index hub note creation + backlinks from all notes
    (10) Wikilink qualification — [[X]] → [[svc/X]]
    (11) Cross-service false link removal — preserves calls_api / shares_db_entity
    (12) .obsidian/graph.json colour groups — one colour per service
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx


# ── Regexes ────────────────────────────────────────────────────────────────────

_SOURCE_RE   = re.compile(r'^source_file:\s*["\']([^"\']*)["\']', re.MULTILINE)
_COMM_FRONT  = re.compile(r'^community:\s*["\'][^"\']*["\']', re.MULTILINE)
_COMM_YAML   = re.compile(r'  - community/[^\n]+\n')
_COMM_BODY   = re.compile(r'#community/\S+')
_WIKILINK_RE = re.compile(r'\[\[([^\]/|#\]]+?)\]\]')
_SUFFIX_RE   = re.compile(r'^(.+?)_\d+$')

_IMPORT_RELS = frozenset({"imports", "imports_from"})
_KEEP_RELS   = frozenset({"calls_api", "shares_db_entity"})  # always preserved cross-service

# Language-file-extension sets for cross-language filter
_JAVA_EXTS = frozenset({".java", ".kt"})
_TS_EXTS   = frozenset({".ts", ".tsx", ".js", ".jsx"})


# ── Public entry point ─────────────────────────────────────────────────────────

def generate_obsidian_vault(
    G: nx.DiGraph,
    communities: dict[str, int],
    output_dir: str | Path,
    obsidian_dir: str | Path | None = None,
) -> int:
    """Generate a fully post-processed Obsidian vault.

    Args:
        G:            knowledge graph (output of graph/build.py + enrich.py)
        communities:  node_id → community_id mapping
        output_dir:   codebeacon output root (.codebeacon/)
        obsidian_dir: override vault path; defaults to output_dir/obsidian/

    Returns:
        Total number of notes written.
    """
    vault = Path(obsidian_dir) if obsidian_dir else Path(output_dir) / "obsidian"
    vault.mkdir(parents=True, exist_ok=True)

    # Step 1 — basic note generation
    _step1_generate_notes(G, communities, vault)

    # Step 2 — broken wikilink normalisation
    _step2_fix_wikilinks(vault)

    # Step 3 — cross-language imports removal (Java↔TS)
    _step3_remove_cross_language(vault)

    # Step 4 — Community_N tag → service folder name
    _step4_fix_community_tags(vault)

    # Step 5 — move notes to service subfolders
    _step5_move_to_subfolders(vault)

    # Step 6 — deduplicate same source_file notes
    _step6_dedup_notes(vault)

    # Step 7 — inject Members section from methods/fields
    _step7_inject_members(G, vault)

    # Step 8 — move any remaining root-level notes
    _step8_move_remaining(vault)

    # Step 9 — service index hub notes + backlinks
    _step9_hub_notes(vault)

    # Step 10 — qualify wikilinks [[X]] → [[svc/X]]
    _step10_qualify_wikilinks(vault)

    # Step 11 — remove cross-service false links
    _step11_remove_cross_service_links(vault)

    # Step 12 — write .obsidian/graph.json
    _step12_graph_json(vault)

    total = sum(1 for _ in vault.rglob("*.md"))
    return total


# ── Step 1: Generate notes ─────────────────────────────────────────────────────

def _step1_generate_notes(
    G: nx.DiGraph,
    communities: dict[str, int],
    vault: Path,
) -> None:
    """One Obsidian note per graph node (skipping external stubs)."""

    # Build edge index: node_id → [(neighbour_id, edge_data, direction)]
    # direction: "out" = G[node→neighbour], "in" = G[neighbour→node]
    out_edges: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    in_edges:  dict[str, list[tuple[str, dict]]] = defaultdict(list)

    for src, tgt, data in G.edges(data=True):
        out_edges[src].append((tgt, data))
        in_edges[tgt].append((src, data))

    for node_id, data in G.nodes(data=True):
        ntype = data.get("type", "unknown")
        if ntype == "external":
            continue  # skip stub nodes

        project   = data.get("project", "_unknown")
        label     = data.get("label", node_id)
        source_file = data.get("source_file", "")
        framework = data.get("framework", "")
        community_id = communities.get(node_id, -1)

        note_name = _safe_note_name(label)
        content   = _build_note(
            node_id    = node_id,
            label      = label,
            ntype      = ntype,
            data       = data,
            project    = project,
            source_file = source_file,
            framework  = framework,
            community_id = community_id,
            out_edges  = out_edges.get(node_id, []),
            in_edges   = in_edges.get(node_id, []),
            G          = G,
        )

        note_path = vault / f"{note_name}.md"
        note_path.write_text(content, encoding="utf-8")


def _build_note(
    node_id: str,
    label: str,
    ntype: str,
    data: dict,
    project: str,
    source_file: str,
    framework: str,
    community_id: int,
    out_edges: list[tuple[str, dict]],
    in_edges: list[tuple[str, dict]],
    G: nx.DiGraph,
) -> str:
    """Render a single Obsidian note from node data."""

    # ── Frontmatter ──
    lines = [
        "---",
        f'source_file: "{source_file}"',
        f'type: "code"',
        f'community: "{project}"',
        "tags:",
        "  - codebeacon/code",
        f"  - codebeacon/{ntype}",
        "  - codebeacon/EXTRACTED",
        f"  - community/{project}",
        "---",
        "",
        f"# {label}",
        "",
    ]

    # ── Type header ──
    type_label = _type_display(ntype, data, framework)
    lines.append(f"**Type:** {type_label}")
    if framework:
        lines.append(f"**Framework:** {framework}")
    if source_file:
        lines.append(f"**Source:** `{source_file}`")
    lines.append("")

    # ── Type-specific body ──
    if ntype == "class":
        _append_class_body(lines, data)
    elif ntype == "entity":
        _append_entity_body(lines, data)
    elif ntype == "component":
        _append_component_body(lines, data)
    elif ntype == "route":
        _append_route_body(lines, data)

    # ── Connections ──
    all_conn_lines = []

    # Outgoing edges
    for tgt_id, edata in sorted(out_edges, key=lambda x: x[0]):
        tgt_data = G.nodes.get(tgt_id, {})
        if tgt_data.get("type") == "external":
            continue
        tgt_label = tgt_data.get("label", tgt_id)
        tgt_name  = _safe_note_name(tgt_label)
        relation  = edata.get("relation", "")
        conf      = edata.get("confidence", "EXTRACTED")
        all_conn_lines.append(f"- [[{tgt_name}]] - `{relation}` [{conf}]")

    # Incoming edges (reverse direction labelled)
    for src_id, edata in sorted(in_edges, key=lambda x: x[0]):
        src_data = G.nodes.get(src_id, {})
        if src_data.get("type") == "external":
            continue
        src_label = src_data.get("label", src_id)
        src_name  = _safe_note_name(src_label)
        relation  = edata.get("relation", "")
        conf      = edata.get("confidence", "EXTRACTED")
        # Label incoming as reverse perspective
        reverse = _reverse_relation(relation)
        all_conn_lines.append(f"- [[{src_name}]] - `{reverse}` [{conf}]")

    if all_conn_lines:
        lines += ["## Connections", ""]
        lines += sorted(set(all_conn_lines))
        lines.append("")

    # ── Footer tags + service backlink ──
    lines.append(f"#codebeacon/code #codebeacon/{ntype} #community/{project}")
    lines.append("")
    lines.append(f"**Service:** [[{project}]]")

    return "\n".join(lines) + "\n"


def _append_class_body(lines: list[str], data: dict) -> None:
    annotations = data.get("annotations", [])
    methods     = data.get("methods", [])
    dependencies = data.get("dependencies", [])

    if annotations:
        lines += ["### Annotations", ""]
        for ann in annotations:
            lines.append(f"- `{ann}`")
        lines.append("")

    if methods:
        lines += ["### Methods", ""]
        for m in methods:
            lines.append(f"- `{m}()`")
        lines.append("")

    if dependencies:
        lines += ["### Fields (Injected)", ""]
        for dep in dependencies:
            lines.append(f"- `{dep}`")
        lines.append("")


def _append_entity_body(lines: list[str], data: dict) -> None:
    table_name = data.get("table_name", "")
    fields     = data.get("fields", [])
    relations  = data.get("relations", [])

    if table_name:
        lines.append(f"**Table:** `{table_name}`")
        lines.append("")

    if fields:
        lines += ["### Fields", ""]
        for f in fields:
            name = f.get("name", "")
            ftype = f.get("type", "")
            anns = f.get("annotations", [])
            ann_str = f" ({', '.join(anns)})" if anns else ""
            lines.append(f"- `{ftype} {name}`{ann_str}")
        lines.append("")

    if relations:
        lines += ["### Relations", ""]
        for r in relations:
            rtype = r.get("type", "")
            target = r.get("target", "")
            lines.append(f"- `{rtype}` → `{target}`")
        lines.append("")


def _append_component_body(lines: list[str], data: dict) -> None:
    props     = data.get("props", [])
    hooks     = data.get("hooks", [])
    is_page   = data.get("is_page", False)
    route_path = data.get("route_path", "")

    if is_page and route_path:
        lines.append(f"**Route:** `{route_path}`")
        lines.append("")

    if props:
        lines += ["### Props", ""]
        for p in props:
            lines.append(f"- `{p}`")
        lines.append("")

    if hooks:
        lines += ["### Hooks", ""]
        for h in hooks:
            lines.append(f"- `{h}`")
        lines.append("")


def _append_route_body(lines: list[str], data: dict) -> None:
    method = data.get("method", "")
    path   = data.get("path", "")
    tags   = data.get("tags", [])

    if method and path:
        lines.append(f"**Route:** `{method} {path}`")
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
    lines.append("")


def _type_display(ntype: str, data: dict, framework: str) -> str:
    """Human-readable type label."""
    if ntype == "class":
        anns = data.get("annotations", [])
        for a in anns:
            al = a.lower()
            if "restcontroller" in al or "controller" in al:
                return "REST Controller"
            if "service" in al:
                return "Service"
            if "repository" in al:
                return "Repository"
            if "component" in al:
                return "Component"
        label = data.get("label", "")
        if label.endswith("Controller"):
            return "Controller"
        if label.endswith("Repository"):
            return "Repository"
        return "Service"
    mapping = {
        "entity":    "Entity",
        "component": "Frontend Component",
        "route":     "API Route",
    }
    return mapping.get(ntype, ntype.title())


def _reverse_relation(relation: str) -> str:
    """Invert an edge label for the incoming-edge perspective."""
    inv = {
        "imports":          "imported_by",
        "imports_from":     "imported_by",
        "calls":            "called_by",
        "injects":          "injected_by",
        "calls_api":        "api_called_by",
        "shares_db_entity": "shares_db_entity",
    }
    return inv.get(relation, f"←{relation}")


def _safe_note_name(label: str) -> str:
    """Convert node label to a safe filename stem (no path separators)."""
    # Replace characters that confuse Obsidian wikilinks
    return re.sub(r'[/\\#^|[\]]', "_", label).strip()


# ── Step 2: Fix broken wikilinks ──────────────────────────────────────────────

def _step2_fix_wikilinks(vault: Path) -> None:
    """Normalise wikilinks whose target has a case mismatch."""
    existing = {f.stem: f.stem for f in vault.glob("*.md")}

    def _norm(s: str) -> str:
        return re.sub(r"[\s_-]", "", s).lower()

    norm_to_actual: dict[str, str] = {_norm(k): k for k in existing}
    broken_map: dict[str, str] = {}

    for md in vault.glob("*.md"):
        for m in _WIKILINK_RE.finditer(md.read_text(errors="ignore")):
            stem = m.group(1)
            if stem not in existing:
                nrm = _norm(stem)
                if nrm in norm_to_actual:
                    broken_map[stem] = norm_to_actual[nrm]

    if not broken_map:
        return

    for md in vault.glob("*.md"):
        content = md.read_text(errors="ignore")
        new_c = content
        for broken, correct in broken_map.items():
            new_c = new_c.replace(f"[[{broken}]]", f"[[{correct}]]")
        if new_c != content:
            md.write_text(new_c, encoding="utf-8")


# ── Step 3: Cross-language imports removal ────────────────────────────────────

def _step3_remove_cross_language(vault: Path) -> None:
    """Remove Java↔TS import edges from notes. Preserves calls_api."""

    # Patterns that match Java→TS or TS→Java import connection lines
    # e.g.:  - [[SomeJavaClass.java]] - `imports_from` [EXTRACTED]
    ts_drop   = re.compile(r"^- \[\[[^\]]*\.(?:tsx?|jsx?)\]\] - `imports(?:_from)?` .*\n?", re.MULTILINE)
    java_drop = re.compile(r"^- \[\[[^\]]*\.(?:java|kt)\]\] - `imports(?:_from)?` .*\n?", re.MULTILINE)

    for md in vault.glob("*.md"):
        name = md.name
        content = md.read_text(errors="ignore")
        new_c = content

        if name.endswith((".ts.md", ".tsx.md", ".js.md", ".jsx.md")):
            new_c = ts_drop.sub("", new_c)
        elif name.endswith((".java.md", ".kt.md")):
            new_c = java_drop.sub("", new_c)

        if new_c != content:
            md.write_text(new_c, encoding="utf-8")


# ── Step 4: Fix community tags ────────────────────────────────────────────────

def _step4_fix_community_tags(vault: Path) -> None:
    """Replace Community_N / Community_None tags with service folder from source_file."""

    for md in vault.glob("*.md"):
        content = md.read_text(errors="ignore")
        m = _SOURCE_RE.search(content)
        folder = m.group(1).split("/")[0] if m and m.group(1) else None

        new_c = content
        if folder:
            new_c = _COMM_FRONT.sub(f'community: "{folder}"', new_c)
            new_c = _COMM_YAML.sub(f"  - community/{folder}\n", new_c)
            new_c = _COMM_BODY.sub(f"#community/{folder}", new_c)
        else:
            new_c = _COMM_FRONT.sub('community: ""', new_c)
            new_c = _COMM_YAML.sub("", new_c)
            new_c = _COMM_BODY.sub("", new_c)

        if new_c != content:
            md.write_text(new_c, encoding="utf-8")


# ── Step 5: Move to service subfolders ───────────────────────────────────────

def _step5_move_to_subfolders(vault: Path) -> None:
    """Move root-level notes into <vault>/<service>/ based on source_file."""

    for md in list(vault.glob("*.md")):
        content = md.read_text(errors="ignore")
        m = _SOURCE_RE.search(content)
        folder = m.group(1).split("/")[0] if m and m.group(1) else "_unknown"

        dest_dir = vault / folder
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / md.name

        if not dest.exists():
            md.rename(dest)
        else:
            # collision — keep dest (dedup in step 6)
            md.unlink()


# ── Step 6: Deduplicate same source_file ──────────────────────────────────────

def _step6_dedup_notes(vault: Path) -> None:
    """Keep one note per source_file; remove duplicates.

    Priority: file-extension.md  >  bare name  >  _N suffix
    """
    by_src: dict[str, list[Path]] = defaultdict(list)

    for md in vault.rglob("*.md"):
        content = md.read_text(errors="ignore")
        m = _SOURCE_RE.search(content)
        if m and m.group(1):
            by_src[m.group(1)].append(md)

    remap: dict[str, str] = {}

    for sf, files in by_src.items():
        if len(files) < 2:
            continue
        primary = _pick_primary(files)
        for f in files:
            if f != primary:
                remap[f.stem] = primary.stem
                f.unlink()

    # Rewrite wikilinks pointing at deleted notes
    if remap:
        for md in vault.rglob("*.md"):
            content = md.read_text(errors="ignore")
            new_c = content
            for old, new in remap.items():
                new_c = new_c.replace(f"[[{old}]]", f"[[{new}]]")
            if new_c != content:
                md.write_text(new_c, encoding="utf-8")


def _pick_primary(files: list[Path]) -> Path:
    """Choose the canonical note from a group with the same source_file."""
    # Prefer: has a file-extension in stem (e.g. Foo.java.md)
    for ext in (".java", ".kt", ".ts", ".tsx", ".js", ".py", ".go", ".cs", ".rs", ".rb", ".php"):
        for f in files:
            if f.stem.endswith(ext):
                return f
    # Prefer: no _N suffix
    for f in files:
        if not _SUFFIX_RE.match(f.stem):
            return f
    return files[0]


# ── Step 7: Members section injection ────────────────────────────────────────

def _step7_inject_members(G: nx.DiGraph, vault: Path) -> None:
    """Add ## Members section to notes from class node methods/fields metadata.

    In codebeacon's graph there are no method child-nodes; method names are
    stored directly in the class node's `methods` metadata list.
    """
    # Build: source_file → methods list from graph
    sf_methods: dict[str, list[str]] = {}

    for node_id, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        if not sf:
            continue
        methods = data.get("methods", [])
        fields  = data.get("dependencies", [])  # injected fields
        members = [f".{m}()" for m in methods] + [f"{dep}" for dep in fields]
        if members:
            existing = sf_methods.get(sf, [])
            sf_methods[sf] = list(dict.fromkeys(existing + members))

    # Build: source_file → vault note path
    sf_to_note: dict[str, Path] = {}
    for md in vault.rglob("*.md"):
        content = md.read_text(errors="ignore")
        m = _SOURCE_RE.search(content)
        if m and m.group(1):
            sf_to_note[m.group(1)] = md

    _SKIP = re.compile(r"^\.(?:get[A-Z]|set[A-Z]|is[A-Z]|has[A-Z]|builder|toString|hashCode|equals|canEqual)")

    for sf, members in sf_methods.items():
        note = sf_to_note.get(sf)
        if not note:
            continue

        real = sorted(set(m for m in members if not _SKIP.match(m)))
        if not real:
            continue

        content = note.read_text(errors="ignore")
        if "## Members" in content:
            continue

        member_block = "\n## Members\n" + "\n".join(f"- `{m}`" for m in real) + "\n"

        # Insert before ## Connections or before footer tags
        conn_match = re.search(r"\n## Connections\n", content)
        tag_match  = re.search(r"\n#codebeacon/", content)
        pos = conn_match.start() if conn_match else (tag_match.start() if tag_match else len(content.rstrip()))

        content = content[:pos] + member_block + content[pos:]
        note.write_text(content, encoding="utf-8")


# ── Step 8: Move remaining root-level notes ───────────────────────────────────

def _step8_move_remaining(vault: Path) -> None:
    """Move any notes still at root level to their service subfolder."""

    for md in list(vault.glob("*.md")):
        content = md.read_text(errors="ignore")
        m = _SOURCE_RE.search(content)
        if m and m.group(1):
            svc = m.group(1).split("/")[0]
            dest_dir = vault / svc
            dest_dir.mkdir(exist_ok=True)
            dest = dest_dir / md.name
            if not dest.exists():
                md.rename(dest)
            else:
                md.unlink()
        else:
            # Orphan without source_file — delete
            md.unlink()


# ── Step 9: Hub notes + backlinks ─────────────────────────────────────────────

def _step9_hub_notes(vault: Path) -> None:
    """Create a service/<service>.md index hub note + add backlinks."""

    service_dirs = [d for d in vault.iterdir() if d.is_dir() and not d.name.startswith(".")]

    for svc_dir in service_dirs:
        svc = svc_dir.name
        notes = sorted(svc_dir.glob("*.md"), key=lambda f: f.name)

        # Hub note content
        lines = [
            "---",
            f'type: "folder-index"',
            f'community: "{svc}"',
            "tags:",
            "  - codebeacon/folder-index",
            f"  - community/{svc}",
            "---",
            "",
            f"# {svc}",
            "",
            f"Service folder — {len(notes)} node(s)",
            "",
            "## All Files",
            "",
        ]
        for note in sorted(notes, key=lambda f: f.stem):
            if note.stem != svc:
                lines.append(f"- [[{svc}/{note.stem}]]")

        lines += ["", f"#codebeacon/folder-index #community/{svc}"]
        hub_path = svc_dir / f"{svc}.md"
        hub_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Add back-link from each note → service hub
        for note in notes:
            if note.stem == svc:
                continue
            content = note.read_text(errors="ignore")
            if f"[[{svc}]]" not in content:
                note.write_text(content.rstrip() + f"\n\n**Service:** [[{svc}]]\n", encoding="utf-8")


# ── Step 10: Qualify wikilinks ────────────────────────────────────────────────

def _step10_qualify_wikilinks(vault: Path) -> None:
    """Rewrite [[X]] → [[svc/X]] to disambiguate same-name notes in different services."""

    # Build: stem → set of services containing that stem
    stem_svcs: dict[str, set[str]] = defaultdict(set)
    for md in vault.rglob("*.md"):
        stem_svcs[md.stem].add(md.parent.name)

    all_svc_names = {d.name for d in vault.iterdir() if d.is_dir() and not d.name.startswith(".")}

    for md in vault.rglob("*.md"):
        my_svc = md.parent.name
        content = md.read_text(errors="ignore")

        def _qualify(m: re.Match) -> str:
            stem = m.group(1).strip()
            # Don't qualify service index links
            if stem in all_svc_names:
                return m.group(0)
            # Already qualified (contains /)
            if "/" in stem:
                return m.group(0)
            svcs = stem_svcs.get(stem, set())
            if not svcs:
                return m.group(0)
            if my_svc in svcs:
                return f"[[{my_svc}/{stem}]]"
            if len(svcs) == 1:
                only = next(iter(svcs))
                return f"[[{only}/{stem}]]"
            # Ambiguous — leave unqualified
            return m.group(0)

        new_c = _WIKILINK_RE.sub(_qualify, content)
        if new_c != content:
            md.write_text(new_c, encoding="utf-8")


# ── Step 11: Remove cross-service false links ─────────────────────────────────

def _step11_remove_cross_service_links(vault: Path) -> None:
    """Remove wikilinks pointing to a different service (except calls_api/shares_db_entity)."""

    all_svc_names = {d.name for d in vault.iterdir() if d.is_dir() and not d.name.startswith(".")}

    # Build stem → service mapping (post qualification, most links have svc/stem)
    stem_to_svc: dict[str, str] = {}
    for md in vault.rglob("*.md"):
        stem_to_svc[md.stem] = md.parent.name

    # Identify frontend service names heuristically
    _front_prefixes = ("front-", "dring-", "app-", "web-", "ui-")

    def _is_frontend(svc: str) -> bool:
        return any(svc.startswith(p) for p in _front_prefixes)

    for md in vault.rglob("*.md"):
        src_svc = md.parent.name
        content = md.read_text(errors="ignore")
        lines = content.split("\n")
        new_lines = []
        changed = False

        for line in lines:
            # Always keep lines with intentional cross-service relations
            if any(rel in line for rel in ("calls_api", "api_called_by", "shares_db_entity", "Called By", "API Connections")):
                new_lines.append(line)
                continue

            has_cross = False
            for m in _WIKILINK_RE.finditer(line):
                link = m.group(1).strip()
                if link in all_svc_names:
                    continue  # service index links are fine
                if "/" in link:
                    tgt_svc = link.split("/")[0]
                else:
                    tgt_svc = stem_to_svc.get(link, "")

                if tgt_svc in all_svc_names and tgt_svc != src_svc:
                    src_front = _is_frontend(src_svc)
                    tgt_front = _is_frontend(tgt_svc)
                    # Remove front↔front or front↔backend false edges
                    if src_front or tgt_front:
                        has_cross = True
                        break

            if has_cross and line.strip().startswith("- [["):
                changed = True
                continue  # drop the entire bullet line

            new_lines.append(line)

        if changed:
            md.write_text("\n".join(new_lines), encoding="utf-8")


# ── Step 12: .obsidian/graph.json ────────────────────────────────────────────

def _step12_graph_json(vault: Path) -> None:
    """Write Obsidian graph view config with per-service colour groups."""

    obsidian_config = vault / ".obsidian"
    obsidian_config.mkdir(exist_ok=True)

    service_dirs = sorted(
        [d for d in vault.iterdir() if d.is_dir() and not d.name.startswith(".")],
        key=lambda d: d.name,
    )

    color_groups = []
    for svc_dir in service_dirs:
        svc = svc_dir.name
        rgb = int(hashlib.md5(svc.encode()).hexdigest()[:6], 16)
        color_groups.append({
            "query": f"path:{svc}",
            "color": {"a": 1, "rgb": rgb},
        })

    graph_config = {
        "collapse-filter":    True,
        "search":             "",
        "showTags":           False,
        "showAttachments":    False,
        "hideUnresolved":     False,
        "showOrphans":        True,
        "collapse-color-groups": False,
        "colorGroups":        color_groups,
        "collapse-display":   False,
        "showArrow":          True,
        "textFadeMultiplier": 0,
        "nodeSizeMultiplier": 1,
        "lineSizeMultiplier": 1,
        "collapse-forces":    True,
        "centerStrength":     0.5,
        "repelStrength":      10,
        "linkStrength":       1,
        "linkDistance":       250,
        "scale":              0.05,
        "close":              False,
    }

    (obsidian_config / "graph.json").write_text(
        json.dumps(graph_config, indent=2),
        encoding="utf-8",
    )
