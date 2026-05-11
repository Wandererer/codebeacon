"""Detect project-local Claude Code slash commands and skills.

Surfaces `.claude/commands/*.md` and `.claude/skills/*.md` (plus subdir-style
`.claude/skills/<name>/SKILL.md`) in CLAUDE.md so agents discover what's
available before reaching for generic solutions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Skill:
    name: str
    description: str
    path: str  # repo-relative


_SKILL_DIRS = (".claude/commands", ".claude/skills")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
# Inline form: `description: text…` (anything but `|` or `>` start).
_DESCRIPTION_INLINE_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)
# Block scalar form: `description: |` or `description: >` (optionally with chomp/indent indicators).
_DESCRIPTION_BLOCK_RE = re.compile(r"^description:\s*([|>][+-]?\d*)\s*$", re.MULTILINE)


def detect_skills(repo_root: Path) -> list[Skill]:
    skills: list[Skill] = []
    seen: set[str] = set()
    for rel_dir in _SKILL_DIRS:
        base = repo_root / rel_dir
        if not base.is_dir():
            continue
        # Flat .md/.txt files: name = stem
        for entry in sorted(base.iterdir()):
            if entry.is_file() and entry.suffix in (".md", ".txt"):
                if entry.stem in seen:
                    continue
                seen.add(entry.stem)
                skills.append(_make_skill(entry.stem, entry, repo_root))
            # Subdir-style: <name>/SKILL.md → name = directory name
            elif entry.is_dir():
                skill_md = entry / "SKILL.md"
                if skill_md.is_file() and entry.name not in seen:
                    seen.add(entry.name)
                    skills.append(_make_skill(entry.name, skill_md, repo_root))
    return skills


def _make_skill(name: str, path: Path, repo_root: Path) -> Skill:
    content = _read_safe(path)
    desc = _extract_description(content)
    try:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel = str(path)
    return Skill(name=name, description=desc, path=rel)


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_description(content: str) -> str:
    fm = _FRONTMATTER_RE.match(content)
    if fm:
        fm_body = fm.group(1)
        # Try block scalar first: `description: |` / `description: >` followed by indented lines.
        block_match = _DESCRIPTION_BLOCK_RE.search(fm_body)
        if block_match:
            block = _read_yaml_block(fm_body, block_match.end())
            if block:
                return _first_sentence(block)
        inline_match = _DESCRIPTION_INLINE_RE.search(fm_body)
        if inline_match:
            value = inline_match.group(1).strip().strip('"\'')
            # Guard against `description: |` slipping through (block_match should catch
            # it, but if the indicator had trailing junk we don't want to keep `|`).
            if value and value not in ("|", ">"):
                return _first_sentence(value)
        body = content[fm.end():]
    else:
        body = content
    for line in body.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return _first_sentence(stripped)
    return ""


def _read_yaml_block(fm_body: str, start: int) -> str:
    """Read indented lines after a `description: |` / `>` marker.

    Stops at the first dedent (line whose indent is ≤ 0 relative to base) or EOF.
    Joins lines with a single space — good enough for a one-line display.
    """
    rest = fm_body[start:].lstrip("\n")
    if not rest:
        return ""
    lines = rest.splitlines()
    base_indent: int | None = None
    collected: list[str] = []
    for line in lines:
        if not line.strip():
            if collected:
                collected.append("")
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is None:
            base_indent = indent
            if base_indent == 0:
                break
        if indent < base_indent:
            break
        collected.append(line[base_indent:].rstrip())
    return " ".join(s for s in collected if s).strip()


def _first_sentence(text: str, max_len: int = 200) -> str:
    """Return the first sentence (up to a period) or truncate to keep the line short."""
    text = " ".join(text.split())  # collapse whitespace
    period = text.find(". ")
    if 0 < period < max_len:
        return text[: period + 1]
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def format_skills_section(skills: list[Skill]) -> str:
    if not skills:
        return ""
    lines = ["## Claude Skills", ""]
    lines.append("Project-local slash commands available to Claude Code agents:")
    lines.append("")
    for s in sorted(skills, key=lambda x: x.name):
        suffix = f" — {s.description}" if s.description else ""
        lines.append(f"- `/{s.name}`{suffix}")
    dirs = sorted({str(Path(s.path).parent) for s in skills})
    lines += ["", f"_Source: {', '.join(dirs)}_", ""]
    return "\n".join(lines)
