"""Markdown templates for codebeacon wiki articles.

Each function takes structured data and returns a markdown string.
No file I/O here — callers decide where to write.
"""

from __future__ import annotations

from typing import Any

from codebeacon.common.safety import safe_wiki_filename, sanitize_label


# How many cross-project edges the platform overview lists before capping.
_CROSS_CONNECTION_CAP = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def truncation_note(total: int, shown: int) -> str:
    """A one-line note stating what a capped list left out, or "" if nothing.

    Every capped list in the wiki used to render silently, so a reader looking
    at 30 of 80 cross-project connections had no way to know 50 were missing —
    and on a repo whose hub file is imported by 160 others, the cap hides
    exactly the part that matters (graphify #953-14).
    """
    if total <= shown:
        return ""
    return f"_… and {total - shown} more (showing {shown} of {total})_"


def _md_cell(value: str) -> str:
    """Escape a value for a GFM table cell that is wrapped in a code span.

    Only ``|`` needs escaping here: it opens a new column even inside a code
    span, silently truncating the row and dropping later columns (a
    regex-alternation route path such as Spring's ``/user/{id:[0-9]+|new}`` is
    the realistic trigger — BH-S3). GFM's table parser rewrites ``\\|`` back to a
    literal pipe before the code span is read, so the value still renders whole.
    ``]``/backtick are deliberately left untouched: a backslash is literal inside
    a code span, so escaping them there would only leak the backslash, and none
    occurs in a real method/path/handler/file cell.

    Coerces to ``str`` first so a mis-shaped route dict carrying ``None`` renders
    as the old f-string did (``None``) instead of raising (G06).
    """
    return str(value).replace("|", "\\|")


def _md_link_text(value: str) -> str:
    """Escape a value used as inline-link display text ``[<value>](...)``.

    An unbalanced ``[`` / ``]`` closes the display text early and drops the link
    (``[page [GET /signup]](...)`` → broken). Real class/entity/component labels
    are source identifiers and never contain brackets, so this is defensive, but
    page-component labels and future graph sources can (BH-S3). Coerces to
    ``str`` so a ``None`` slipping through can't raise (G06).

    A newline is just as fatal and far more likely: a label carrying one breaks
    the ``[text](target)`` syntax across two lines and the link stops rendering
    at all, even though the file it points at is correct.
    ``sanitize_label`` folds it (and tabs, C0 controls, bidi marks) to a space,
    matching the transform the filename side now applies (graphify #929-6).
    """
    return sanitize_label(value).replace("[", "\\[").replace("]", "\\]")


def _rel_link(label: str, project: str) -> str:
    """Produce a relative markdown link (same project).

    The link target must be the exact stem the generator writes the file
    under (``safe_wiki_filename``) — space-encoding alone left links to any
    label with `#`, parentheses, generics, etc. pointing at missing files.
    The display text is bracket-escaped so a label with `[`/`]` can't break the
    link syntax (BH-S3).
    """
    return f"[{_md_link_text(label)}](./{safe_wiki_filename(label)}.md)"


def _back_link(project_name: str) -> str:
    # Articles live one directory down (proj/<bucket>/<name>.md); the project
    # index is at proj/index.md, so link up one level. `../` also keeps the
    # dead-link downgrader (which only rewrites `./` targets) from touching it.
    # graphify #1444.
    return f"_Back to [{project_name}/index.md](../index.md)_"


# ── Controller article ────────────────────────────────────────────────────────

def controller_article(
    label: str,
    routes: list[dict[str, Any]],
    source_file: str,
    called_by: list[str],
    calls: list[str],
    project_name: str,
) -> str:
    """Wiki article for a controller / router handler class.

    Args:
        label:        class name (e.g. "UserController")
        routes:       list of dicts with keys: method, path, handler, line
        source_file:  relative source path
        called_by:    list of node labels that call this controller
        calls:        list of node labels this controller calls/injects
        project_name: owning project name
    """
    lines = [
        f"# {label}",
        "",
        f"> **Navigation aid.** Route list and file locations extracted via AST."
        f" Read the source files listed below before implementing or modifying this subsystem.",
        "",
    ]

    if routes:
        lines += [f"The {label} subsystem handles **{len(routes)} route(s)**.", "", "## Routes", ""]
        for r in sorted(routes, key=lambda x: x.get("path", "")):
            method = r.get("method", "GET")
            path = r.get("path", "")
            handler = r.get("handler", "")
            tags = r.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- `{method}` `{path}`{tag_str}")
            lines.append(f"  `{source_file}`")
    else:
        lines += ["## Routes", "", "_No routes extracted._"]

    lines += ["", "## Source Files", "", "Read these before implementing or modifying this subsystem:"]
    lines.append(f"- `{source_file}`")

    if calls:
        lines += ["", "## Calls / Injects", ""]
        for name in sorted(set(calls)):
            lines.append(f"- {_rel_link(name, project_name)}")

    if called_by:
        lines += ["", "## Called By", ""]
        for name in sorted(set(called_by)):
            lines.append(f"- {_rel_link(name, project_name)}")

    lines += ["", "---", _back_link(project_name)]
    return "\n".join(lines) + "\n"


# ── Service article ───────────────────────────────────────────────────────────

def service_article(
    label: str,
    methods: list[str],
    dependencies: list[str],
    source_file: str,
    called_by: list[str],
    calls: list[str],
    related_entities: list[str],
    annotations: list[str],
    project_name: str,
) -> str:
    """Wiki article for a service / component class.

    This is the ★ core article type — it includes method signatures, DI
    dependencies, call graph edges, and related entities.

    Args:
        label:            class name
        methods:          list of method name strings
        dependencies:     injected type names (may be unresolved)
        source_file:      relative source path
        called_by:        node labels with incoming call/inject edges
        calls:            node labels with outgoing call/inject edges
        related_entities: entity node labels imported/used by this service
        annotations:      framework annotations (e.g. @Service, @Injectable)
        project_name:     owning project name
    """
    ann_str = f" `{'` `'.join(annotations)}`" if annotations else ""
    lines = [
        f"# {label}",
        "",
        f"**Type:** Service{ann_str}",
        f"**Source:** `{source_file}`",
        "",
    ]

    if methods:
        lines += ["## Methods", ""]
        for m in methods:
            lines.append(f"- `{m}()`")
        lines.append("")

    if dependencies:
        lines += ["## DI Dependencies", ""]
        for dep in sorted(set(dependencies)):
            lines.append(f"- {_rel_link(dep, project_name)}")
        lines.append("")

    if calls:
        lines += ["## Calls", ""]
        for name in sorted(set(calls)):
            lines.append(f"- {_rel_link(name, project_name)}")
        lines.append("")

    if called_by:
        lines += ["## Called By", ""]
        for name in sorted(set(called_by)):
            lines.append(f"- {_rel_link(name, project_name)}")
        lines.append("")

    if related_entities:
        lines += ["## Related Entities", ""]
        for ent in sorted(set(related_entities)):
            lines.append(f"- {_rel_link(ent, project_name)}")
        lines.append("")

    lines += ["---", _back_link(project_name)]
    return "\n".join(lines) + "\n"


# ── Entity article ────────────────────────────────────────────────────────────

def entity_article(
    label: str,
    table_name: str,
    fields: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    source_file: str,
    used_by: list[str],
    framework: str,
    project_name: str,
) -> str:
    """Wiki article for an ORM entity / model.

    Args:
        label:       entity class name
        table_name:  database table name (may be empty)
        fields:      list of dicts: {name, type, annotations}
        relations:   list of dicts: {type, target}
        source_file: relative source path
        used_by:     node labels referencing this entity
        framework:   ORM framework (jpa, django-orm, sqlalchemy, …)
        project_name: owning project name
    """
    table_line = f"**Table:** `{table_name}`  " if table_name else ""
    lines = [
        f"# {label}",
        "",
        f"**Type:** Entity ({framework})  ",
        f"{table_line}**Source:** `{source_file}`",
        "",
    ]

    if fields:
        lines += ["## Fields", ""]
        for f in fields:
            name = f.get("name", "")
            ftype = f.get("type", "")
            anns = f.get("annotations", [])
            ann_str = f" `{'` `'.join(anns)}`" if anns else ""
            lines.append(f"- `{ftype} {name}`{ann_str}")
        lines.append("")

    if relations:
        lines += ["## Relations", ""]
        for r in relations:
            rtype = r.get("type", "")
            target = r.get("target", "")
            lines.append(f"- `{rtype}` → {_rel_link(target, project_name)}")
        lines.append("")

    if used_by:
        lines += ["## Used By", ""]
        for name in sorted(set(used_by)):
            lines.append(f"- {_rel_link(name, project_name)}")
        lines.append("")

    lines += ["---", _back_link(project_name)]
    return "\n".join(lines) + "\n"


# ── Component article ─────────────────────────────────────────────────────────

def component_article(
    label: str,
    props: list[str],
    hooks: list[str],
    imports: list[str],
    is_page: bool,
    route_path: str,
    source_file: str,
    framework: str,
    project_name: str,
) -> str:
    """Wiki article for a frontend component (React/Vue/Svelte/Angular).

    Args:
        label:       component name
        props:       prop names
        hooks:       used hooks/composables
        imports:     imported component names
        is_page:     True if this is a page-level route component
        route_path:  derived route path for page components
        source_file: relative source path
        framework:   "react", "vue", "svelte", "angular"
        project_name: owning project name
    """
    kind = "Page Component" if is_page else "Component"
    lines = [
        f"# {label}",
        "",
        f"**Type:** {kind} ({framework})  ",
        f"**Source:** `{source_file}`",
    ]

    if is_page and route_path:
        lines.append(f"**Route:** `{route_path}`")

    lines.append("")

    if props:
        lines += ["## Props", ""]
        for p in props:
            lines.append(f"- `{p}`")
        lines.append("")

    if hooks:
        lines += ["## Hooks / Composables", ""]
        for h in hooks:
            lines.append(f"- `{h}`")
        lines.append("")

    if imports:
        lines += ["## Imports", ""]
        for name in sorted(set(imports)):
            lines.append(f"- {_rel_link(name, project_name)}")
        lines.append("")

    lines += ["---", _back_link(project_name)]
    return "\n".join(lines) + "\n"


# ── Routes summary ────────────────────────────────────────────────────────────

def routes_summary(
    routes_by_project: dict[str, list[dict[str, Any]]],
) -> str:
    """Full routes.md — all routes across all projects in a table.

    Args:
        routes_by_project: project_name → list of route dicts
                           Each route dict: {method, path, handler, source_file, framework}
    """
    lines = [
        "# Routes Summary",
        "",
        "All API routes extracted across all projects.",
        "",
    ]

    for project_name, routes in sorted(routes_by_project.items()):
        if not routes:
            continue
        lines += [f"## {project_name}", "", f"| Method | Path | Handler | File |", "| --- | --- | --- | --- |"]
        for r in sorted(routes, key=lambda x: (x.get("path", ""), x.get("method", ""))):
            # Pipe-escape each cell: an unescaped `|` in a regex-constrained
            # route path (Spring/ASP.NET/Express alternation) otherwise opens a
            # phantom column and drops the File cell entirely (BH-S3).
            method = _md_cell(r.get("method", ""))
            path = _md_cell(r.get("path", ""))
            handler = _md_cell(r.get("handler", ""))
            sf = _md_cell(r.get("source_file", ""))
            lines.append(f"| `{method}` | `{path}` | `{handler}` | `{sf}` |")
        lines.append("")

    return "\n".join(lines) + "\n"


# ── Project index ─────────────────────────────────────────────────────────────

def _index_entry(item: Any) -> tuple[str, str]:
    """Normalise one index entry to ``(display label, on-disk stem)``.

    The generator passes ``(label, bucket, stem)`` so the link points at the
    file it actually wrote — including the salted stem a second same-labelled
    node lands on, which a stem re-derived from the label could never name
    (graphify #3032). A bare string is still accepted and falls back to deriving
    the stem, which is correct whenever no collision occurred.
    """
    if isinstance(item, (tuple, list)) and len(item) >= 2:
        return str(item[0]), str(item[-1])
    return str(item), safe_wiki_filename(item)


def project_index(
    project_name: str,
    framework: str,
    stats: dict[str, int],
    controllers: list[Any],
    services: list[Any],
    entities: list[Any],
    components: list[Any],
) -> str:
    """Per-project index.md.

    Args:
        project_name: project name
        framework:    detected framework
        stats:        {routes, services, entities, components, ...}
        controllers:  controller entries — ``(label, bucket, stem)`` or a label
        services:     service entries, same shape
        entities:     entity entries, same shape
        components:   component entries, same shape
    """
    lines = [
        f"# {project_name}",
        "",
        f"**Framework:** {framework}",
        f"**Routes:** {stats.get('routes', 0)}  ",
        f"**Services:** {stats.get('services', 0)}  ",
        f"**Entities:** {stats.get('entities', 0)}  ",
        f"**Components:** {stats.get('components', 0)}",
        "",
    ]

    for heading, bucket, names in (
        ("Controllers", "controllers", controllers),
        ("Services", "services", services),
        ("Entities", "entities", entities),
        ("Components", "components", components),
    ):
        if not names:
            continue
        lines += [f"## {heading}", ""]
        for entry in sorted(names, key=lambda e: _index_entry(e)):
            # Link target is the stem the generator actually wrote the file
            # under; the display text stays the raw label but is escaped so a
            # label with `[`/`]` or a newline can't break the link (BH-S3).
            label, stem = _index_entry(entry)
            lines.append(f"- [{bucket}/{_md_link_text(label)}](./{bucket}/{stem}.md)")
        lines.append("")

    lines += ["---", "_Back to [index.md](../index.md)_"]
    return "\n".join(lines) + "\n"


# ── Platform overview ─────────────────────────────────────────────────────────

def platform_overview(
    projects: list[dict[str, Any]],
    cross_connections: list[dict[str, Any]],
    total_stats: dict[str, int],
) -> str:
    """Platform-wide overview.md.

    Args:
        projects: list of dicts: {name, framework, route_count, service_count, entity_count}
        cross_connections: list of dicts: {source, target, relation}
        total_stats: {nodes, edges, communities, routes, services, entities, components}
    """
    lines = [
        "# Platform Overview",
        "",
        "## Statistics",
        "",
        f"| Metric | Count |",
        "| --- | --- |",
        f"| Graph nodes | {total_stats.get('nodes', 0)} |",
        f"| Graph edges | {total_stats.get('edges', 0)} |",
        f"| Communities | {total_stats.get('communities', 0)} |",
        f"| Routes | {total_stats.get('routes', 0)} |",
        f"| Services | {total_stats.get('services', 0)} |",
        f"| Entities | {total_stats.get('entities', 0)} |",
        f"| Components | {total_stats.get('components', 0)} |",
        "",
    ]

    if projects:
        lines += [
            "## Projects",
            "",
            "| Project | Framework | Routes | Services | Entities |",
            "| --- | --- | --- | --- | --- |",
        ]
        for p in sorted(projects, key=lambda x: x.get("name", "")):
            name = p.get("name", "")
            fw = p.get("framework", "")
            lines.append(
                f"| [{name}](./{name}/index.md) | {fw}"
                f" | {p.get('route_count', 0)}"
                f" | {p.get('service_count', 0)}"
                f" | {p.get('entity_count', 0)} |"
            )
        lines.append("")

    if cross_connections:
        lines += ["## Cross-Project Connections", ""]
        for cc in cross_connections[:_CROSS_CONNECTION_CAP]:
            src = cc.get("source", "")
            tgt = cc.get("target", "")
            rel = cc.get("relation", "")
            lines.append(f"- `{src}` →[{rel}]→ `{tgt}`")
        note = truncation_note(len(cross_connections), _CROSS_CONNECTION_CAP)
        if note:
            lines.append(note)
        lines.append("")

    return "\n".join(lines) + "\n"


# ── Global index (short, ~200 tokens) ────────────────────────────────────────

def global_index(
    projects: list[dict[str, Any]],
    total_stats: dict[str, int],
) -> str:
    """Root index.md — kept short for quick loading in AI context.

    Args:
        projects: list of dicts: {name, framework}
        total_stats: aggregate statistics
    """
    lines = [
        "# CodeBeacon Wiki",
        "",
        f"**{total_stats.get('nodes', 0)} nodes · "
        f"{total_stats.get('edges', 0)} edges · "
        f"{total_stats.get('communities', 0)} communities**",
        "",
        "## Projects",
        "",
    ]
    for p in sorted(projects, key=lambda x: x.get("name", "")):
        name = p.get("name", "")
        fw = p.get("framework", "")
        lines.append(f"- [{name}](./{name}/index.md) — {fw}")

    lines += [
        "",
        "## Quick Links",
        "",
        "- [Platform Overview](./overview.md)",
        "- [All Routes](./routes.md)",
        "- [Cross-Project Connections](./cross-project/connections.md)",
    ]

    return "\n".join(lines) + "\n"
