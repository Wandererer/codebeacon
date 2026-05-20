"""Markdown knowledge scanner — decisions, meetings, retros, specs, research.

Why this exists
---------------
``codebeacon scan`` answers "what does the code do" by parsing routes,
services, entities, etc. ``codebeacon knowledge`` answers the orthogonal
question "why is it this way" by reading the markdown notes the team
already keeps next to (or inside) the repo: ADRs, RFCs, meeting notes,
retrospectives, design specs, research write-ups.

Detection signals (no LLM call needed)
--------------------------------------
For each ``.md`` / ``.mdx`` / ``.markdown`` file we collect:

* YAML frontmatter (Obsidian, Notion exports, MkDocs, Jekyll) — ``title``,
  ``tags``, ``date``, ``status``, ``decision`` fields.
* The first H1 (``# ...``) — used as ``title`` when no frontmatter title.
* The first paragraph after the H1 — used as a one-line summary.
* Obsidian-style ``[[backlinks]]`` and ``#tags``.
* Date stamps in frontmatter, filename prefix (``2026-03-20-…``), or
  the first occurrence of ``YYYY-MM-DD`` in the body.

We then classify each note via filename keywords + heading patterns:

* **Decision** — filename matches ``adr-*``, ``decision-*``, contains
  ``## Decision`` heading, or starts a sentence with "Decided to" /
  "Going with" / "Chose X over Y".
* **Meeting** — filename mentions ``standup``, ``sync``, ``1on1``,
  ``meeting``, ``weekly``, or body has ``Attendees:`` / ``Action items:``.
* **Retrospective** — filename mentions ``retro``, ``retrospective``, or
  body has "What went well" / "Stop doing" / "Continue doing".
* **Spec** — filename mentions ``prd``, ``spec``, ``roadmap``, ``rfc``,
  or body has ``## Goals`` + ``## Requirements``.
* **Research** — filename mentions ``research``, ``analysis``,
  ``benchmark``, ``comparison``.
* **Session** — filename mentions ``session``, ``daily``, ``weekly``.
* **Note** — everything else.

The output is a single ``KNOWLEDGE.md`` written into ``output_dir`` (next
to ``.codebeacon/`` by default) that mirrors the codesight 1.9.3 layout —
a header line with the per-category counts, then "Key Decisions",
"Open Questions" (lines containing a literal "?"), and a categorized
note index.

Design notes
------------
* Pure-Python, no external markdown parser. The structure we care about
  (frontmatter, first H1, headings, ``[[backlinks]]``) is regex-friendly
  enough that pulling in ``markdown-it`` or ``mistune`` would be more
  weight than the value.
* No LLM call. codebeacon's ``scan`` path already gates AI-semantic
  enrichment behind the skill; ``knowledge`` runs purely off heuristics
  so it can ship offline and finish on a 1000-note vault in seconds.
* All paths are relative to ``root`` in the output for portability.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


MARKDOWN_EXTENSIONS = {".md", ".mdx", ".markdown"}
SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "env",
    "dist", "build", "out", ".next", ".nuxt", ".svelte-kit",
    "__pycache__", ".codebeacon", ".codesight", ".ai-codex",
    "vendor", "target", ".gradle", ".idea", ".vscode",
    ".terraform", "tmp", "temp", "coverage",
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_BACKLINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")
_TAG_RE = re.compile(r"(?<![A-Za-z0-9_/])#([A-Za-z][A-Za-z0-9_/-]*)")
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_.]")
_ATTENDEES_RE = re.compile(r"^Attendees\s*:", re.MULTILINE | re.IGNORECASE)
_ACTION_ITEMS_RE = re.compile(r"^Action items?\s*:", re.MULTILINE | re.IGNORECASE)

# Heading text that strongly implies the note type.
_DECISION_HEADING_RE = re.compile(r"^#{1,6}\s+Decision\b", re.MULTILINE | re.IGNORECASE)
_RETRO_HEADING_RE = re.compile(
    r"^#{1,6}\s+(?:What went well|Stop doing|Continue doing|Start doing|"
    r"Went well|Didn'?t go well|Action items)\b",
    re.MULTILINE | re.IGNORECASE,
)
_GOALS_HEADING_RE = re.compile(r"^#{1,6}\s+Goals\b", re.MULTILINE | re.IGNORECASE)
_REQUIREMENTS_HEADING_RE = re.compile(
    r"^#{1,6}\s+Requirements\b", re.MULTILINE | re.IGNORECASE
)

# Sentence-style decision signals in the body.
_DECISION_BODY_RE = re.compile(
    r"\b(?:decided to|going with|chose [A-Z]\w*\s+over|we (?:will use|are using))\b",
    re.IGNORECASE,
)


@dataclass
class Note:
    """A single classified markdown note."""

    path: str  # relative POSIX path from scan root
    title: str
    category: str  # decision | meeting | retro | spec | research | session | note
    summary: str  # one-line description from first paragraph or frontmatter
    date: str  # ``YYYY-MM-DD`` or ""
    tags: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass
class KnowledgeResult:
    """Aggregate output of a knowledge scan."""

    root: str
    notes: list[Note] = field(default_factory=list)
    output_path: Optional[Path] = None

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for n in self.notes:
            out[n.category] = out.get(n.category, 0) + 1
        return out


# ── Public API ──────────────────────────────────────────────────────────────


def build_knowledge_map(
    root: str | Path,
    output_dir: str | Path,
) -> KnowledgeResult:
    """Scan ``root`` for markdown notes and write ``KNOWLEDGE.md`` to ``output_dir``.

    Args:
        root: directory to scan recursively for ``.md`` files.
        output_dir: where to write ``KNOWLEDGE.md`` (typically the project
                    root — the file lives next to ``.codebeacon/``, not
                    inside it, so a casual ``ls`` surfaces it).
    """
    root_path = Path(root).resolve()
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    notes: list[Note] = []
    for md_path in _walk_markdown(root_path):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = md_path.relative_to(root_path).as_posix()
        note = _classify(text, rel, md_path.name)
        if note is not None:
            notes.append(note)

    notes.sort(key=lambda n: (n.date or "0000-00-00", n.path), reverse=True)
    result = KnowledgeResult(root=str(root_path), notes=notes)

    out_file = output_path / "KNOWLEDGE.md"
    out_file.write_text(_render_markdown(result), encoding="utf-8")
    result.output_path = out_file
    return result


# ── File walker ─────────────────────────────────────────────────────────────


def _walk_markdown(root: Path) -> Iterable[Path]:
    """Yield ``.md``/``.mdx``/``.markdown`` files under ``root``.

    Honours ``SKIP_DIRS`` but does *not* read ``.codebeaconignore`` —
    knowledge scanning is intentionally permissive (a docs folder named
    in ``.codebeaconignore`` for the code scan is usually exactly what
    we want to include here).
    """
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in-place so os.walk doesn't descend into them.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in MARKDOWN_EXTENSIONS:
                yield Path(dirpath) / name


# ── Per-note parsing ────────────────────────────────────────────────────────


def _classify(text: str, rel_path: str, filename: str) -> Optional[Note]:
    """Parse one markdown file and return a classified Note (or None on empty)."""
    if not text.strip():
        return None

    frontmatter, body = _split_frontmatter(text)
    title = _extract_title(frontmatter, body, filename)
    summary = _extract_summary(frontmatter, body, title)
    date = _extract_date(frontmatter, body, filename)
    tags = _extract_tags(frontmatter, body)
    backlinks = sorted(set(_BACKLINK_RE.findall(body)))
    category = _classify_category(filename, body, frontmatter)
    open_questions = _extract_open_questions(body)

    return Note(
        path=rel_path,
        title=title,
        category=category,
        summary=summary,
        date=date,
        tags=tags,
        backlinks=backlinks,
        open_questions=open_questions,
    )


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    frontmatter = _parse_simple_yaml(m.group(1))
    body = text[m.end():]
    return frontmatter, body


def _parse_simple_yaml(block: str) -> dict[str, str]:
    """Minimal scalar-only YAML parser — title/tags/date/status/decision.

    Anything more structured (nested mappings, multi-line scalars) is
    ignored. We only need a flat key→string view to populate the
    classifier; ``tags`` is the one list-valued field we expand into a
    comma-separated value the caller post-splits.
    """
    out: dict[str, str] = {}
    current_key: Optional[str] = None
    list_accum: list[str] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        # List items can be indented (``  - decision``) inside a YAML mapping —
        # strip leading whitespace before checking the dash so the simple
        # accumulator picks them up.
        stripped = line.strip()
        if stripped.startswith("- ") and current_key:
            list_accum.append(stripped[2:].strip().strip('"').strip("'"))
            out[current_key] = ", ".join(list_accum)
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if not value:
                # Possibly a multi-line list — start accumulator.
                current_key = key
                list_accum = []
                out[key] = ""
                continue
            value = value.strip('"').strip("'")
            out[key] = value
            current_key = key
            list_accum = []
    return out


def _extract_title(
    frontmatter: dict[str, str], body: str, filename: str
) -> str:
    if frontmatter.get("title"):
        return frontmatter["title"]
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()
    # Fall back to filename stem, dropping the date prefix if any.
    stem = os.path.splitext(filename)[0]
    stem = _FILENAME_DATE_RE.sub("", stem)
    return stem.replace("_", " ").replace("-", " ").strip() or filename


def _extract_summary(
    frontmatter: dict[str, str], body: str, title: str
) -> str:
    """Return a one-line summary — first paragraph after the H1, or empty."""
    if frontmatter.get("summary"):
        return _flatten(frontmatter["summary"])
    if frontmatter.get("description"):
        return _flatten(frontmatter["description"])

    # Find body content after the first H1 (if any).
    h1 = _H1_RE.search(body)
    after = body[h1.end():] if h1 else body

    for chunk in re.split(r"\n\s*\n", after.strip(), maxsplit=4):
        line = _flatten(chunk)
        if not line:
            continue
        # Skip subheadings, frontmatter-style key lines, and tag-only lines.
        if line.startswith("#"):
            continue
        if line.startswith(("Attendees:", "Date:", "Status:", "Tags:")):
            continue
        return line[:240]
    return ""


def _extract_date(
    frontmatter: dict[str, str], body: str, filename: str
) -> str:
    for key in ("date", "created", "updated", "decision-date"):
        raw = frontmatter.get(key, "").strip()
        if raw:
            m = _DATE_RE.search(raw)
            if m:
                return m.group(1)
    m = _FILENAME_DATE_RE.match(filename)
    if m:
        return m.group(1)
    m = _DATE_RE.search(body)
    if m:
        return m.group(1)
    return ""


def _extract_tags(frontmatter: dict[str, str], body: str) -> list[str]:
    tags: set[str] = set()
    raw = frontmatter.get("tags", "")
    if raw:
        for part in re.split(r"[,\s]+", raw):
            part = part.strip().lstrip("#").lower()
            if part:
                tags.add(part)
    for m in _TAG_RE.finditer(body):
        tags.add(m.group(1).lower())
    return sorted(tags)


def _extract_open_questions(body: str) -> list[str]:
    """Pull lines from an ``## Open Questions`` block, or "- ...?" bullets.

    Used to populate the top-level "Open Questions" section in
    ``KNOWLEDGE.md``. Caps at 5 per note so a free-form Q&A dump doesn't
    drown out everything else.
    """
    questions: list[str] = []

    section_match = re.search(
        r"^#{1,6}\s+Open Questions?\s*$\n(.*?)(?=^#{1,6}\s|\Z)",
        body,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    if section_match:
        for line in section_match.group(1).splitlines():
            line = line.strip(" -*•").strip()
            if line.endswith("?") and len(line) > 5:
                questions.append(line)
    else:
        # Fallback: bullets that end in "?"
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•")) and stripped.rstrip().endswith("?"):
                q = stripped.lstrip("-*• ").strip()
                if len(q) > 5:
                    questions.append(q)
    return questions[:5]


def _classify_category(
    filename: str, body: str, frontmatter: dict[str, str]
) -> str:
    name = filename.lower()
    fm_type = (frontmatter.get("type") or frontmatter.get("category") or "").lower()

    # Frontmatter wins when explicit.
    if fm_type in {"adr", "decision"}:
        return "decision"
    if fm_type in {"meeting", "standup", "1on1"}:
        return "meeting"
    if fm_type in {"retro", "retrospective"}:
        return "retro"
    if fm_type in {"prd", "spec", "rfc"}:
        return "spec"
    if fm_type in {"research", "analysis"}:
        return "research"

    if re.match(r"^(adr-|adr_|decision[-_])", name):
        return "decision"
    if _DECISION_HEADING_RE.search(body):
        return "decision"

    if any(token in name for token in ("standup", "1on1", "1-on-1", "meeting", "sync")):
        return "meeting"
    if _ATTENDEES_RE.search(body) and _ACTION_ITEMS_RE.search(body):
        return "meeting"

    if any(token in name for token in ("retro", "retrospective", "postmortem")):
        return "retro"
    if _RETRO_HEADING_RE.search(body):
        return "retro"

    if any(token in name for token in ("prd", "spec", "roadmap", "rfc")):
        return "spec"
    if _GOALS_HEADING_RE.search(body) and _REQUIREMENTS_HEADING_RE.search(body):
        return "spec"

    if any(token in name for token in ("research", "analysis", "benchmark", "comparison")):
        return "research"

    if any(token in name for token in ("session", "daily", "weekly", "journal")):
        return "session"

    if _DECISION_BODY_RE.search(body):
        return "decision"

    return "note"


def _flatten(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ── Markdown renderer ───────────────────────────────────────────────────────


_CATEGORY_ORDER = [
    ("decision", "Decision Records"),
    ("spec", "Specs & PRDs"),
    ("research", "Research"),
    ("meeting", "Meeting Notes"),
    ("retro", "Retrospectives"),
    ("session", "Session Logs"),
    ("note", "Other Notes"),
]


def _render_markdown(result: KnowledgeResult) -> str:
    counts = result.counts()
    notes = result.notes
    total = len(notes)

    project_name = os.path.basename(result.root.rstrip("/")) or "knowledge"

    decisions = [n for n in notes if n.category == "decision"]
    open_questions: list[tuple[str, str]] = []
    for n in notes:
        for q in n.open_questions:
            open_questions.append((n.path, q))

    date_range = _date_range(notes)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    out: list[str] = []
    out.append(f"# Knowledge Map — {project_name}")
    parts = [f"{total} notes"]
    if counts.get("decision"):
        parts.append(f"{counts['decision']} decisions")
    if open_questions:
        parts.append(f"{len(open_questions)} open questions")
    parts.append(date_range or today)
    out.append(f"> {' · '.join(parts)}")
    out.append("")

    if decisions:
        out.append(f"## Key Decisions ({len(decisions)})")
        for n in decisions[:25]:
            line = f"- [{n.date or '????-??-??'}] {n.title}"
            if n.summary:
                line += f" — {n.summary}"
            out.append(line)
        out.append("")

    if open_questions:
        out.append(f"## Open Questions ({len(open_questions)})")
        for path, q in open_questions[:25]:
            out.append(f"- {q}  _({path})_")
        out.append("")

    out.append(f"## Note Index ({total})")
    for cat_key, cat_title in _CATEGORY_ORDER:
        bucket = [n for n in notes if n.category == cat_key]
        if not bucket:
            continue
        out.append("")
        out.append(f"### {cat_title} ({len(bucket)})")
        for n in bucket:
            line = f"- `{n.path}`"
            if n.date:
                line += f" — {n.date}"
            line += f" — {n.title}"
            if n.summary and n.summary != n.title:
                summary = n.summary
                if len(summary) > 140:
                    summary = summary[:140] + "…"
                line += f" — {summary}"
            out.append(line)

    out.append("")
    out.append("---")
    out.append(f"_Generated by codebeacon · {today}_")
    out.append("")
    return "\n".join(out)


def _date_range(notes: list[Note]) -> str:
    dates = sorted({n.date for n in notes if n.date})
    if not dates:
        return ""
    if len(dates) == 1:
        return dates[0]
    return f"{dates[0]} → {dates[-1]}"
