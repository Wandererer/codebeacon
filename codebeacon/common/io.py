"""Helpers shared by everything that writes a committed artifact.

Two concerns, both about what ends up in ``.codebeacon/``: writing a file only
when its content actually changed, and never writing a build machine's absolute
path into a file other people will read.

Every exporter (wiki, obsidian, HTML) regenerates its whole output on each run.
Writing unconditionally means a scan that produced a byte-identical corpus still
touches every file: mtimes move, Obsidian/IDE indexers and codebeacon's own
``watch`` mode re-fire, sync clients re-upload, and any tooling that keys off
"changed since" sees the entire ``.codebeacon/`` tree as dirty. Since README
documents committing ``.codebeacon/`` (the GitHub Action requires it), that is a
per-scan cost paid by every user (graphify #3060).

``write_text_if_changed`` is the single write primitive the export layer uses:
it reads what is already on disk, and writes only when the content differs.

Comparison is on DECODED TEXT, not bytes. A byte comparison would be wrong on
Windows, where ``Path.write_text`` translates ``\\n`` to ``\\r\\n`` on the way out
but ``read_text`` translates it back on the way in — the file on disk never
matches the string we were asked to write, so a byte compare would report
"changed" every single time and the helper would be a no-op.
"""

from __future__ import annotations

from pathlib import Path


def write_text_if_changed(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
) -> bool:
    """Write ``content`` to ``path`` only if it differs from what is there.

    Returns ``True`` when the file was written (created or changed), ``False``
    when the on-disk content already matched and the write was skipped.

    Any failure to read the existing file — missing, unreadable, or holding
    bytes that are not valid ``encoding`` (a corrupted or hand-edited artifact)
    — is treated as "changed", so the write still happens and the file
    self-heals. Only a successful read that compares equal skips the write.
    """
    target = Path(path)
    try:
        if target.read_text(encoding=encoding) == content:
            return False
    except (OSError, UnicodeDecodeError, ValueError):
        pass  # unreadable / absent / wrong encoding → rewrite it
    target.write_text(content, encoding=encoding)
    return True


def portable_source_path(
    source_file: str,
    project: str,
    project_roots: dict[str, str] | None,
    output_dir: str | Path,
) -> str:
    """A ``source_file`` fit to publish: relative to the repo, or unchanged.

    The in-memory graph deliberately keeps absolute paths — the analysis passes
    need them — and each writer relativizes at emit time. Writers that skipped
    that step published the developer's home directory into a committed,
    shared artifact: a privacy leak (the path contains their username, and the
    PR-context GitHub Action republishes it to every collaborator) and a dead
    reference for anyone reading it on another machine (graphify #3223).

    ``project_roots`` is authoritative when the caller has it. Otherwise the
    repository root is inferred from the output directory — ``.codebeacon`` sits
    at the root of the tree it describes — which is enough to make the path
    portable even when the caller cannot name the project. A path that belongs
    to neither is returned unchanged; a wrong relative path would be worse than
    an honest absolute one.
    """
    # Imported here rather than at module scope: this is the common layer, and
    # the helper is a courtesy to the graph/export layers rather than a
    # dependency of them.
    from codebeacon.graph.write import relativize_source_file

    if not source_file:
        return ""
    roots: list[str] = []
    if project_roots:
        preferred = project_roots.get(project)
        if preferred:
            roots.append(preferred)
        roots.extend(r for r in project_roots.values() if r != preferred)
    out = Path(output_dir)
    roots.append(str(out.parent if out.name == ".codebeacon" else out))

    best = source_file
    for root in roots:
        candidate = relativize_source_file(source_file, root)
        # relativize_source_file returns the input unchanged when the file is
        # not under the root; the shortest result is the deepest containing
        # root, which is the most specific answer.
        if candidate != source_file and len(candidate) < len(best):
            best = candidate
    return best
