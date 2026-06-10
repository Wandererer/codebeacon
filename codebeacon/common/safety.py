"""Sanitization, escaping, and git-state helpers shared by writers.

Three concerns:

1. ``sanitize_label`` strips control characters and bidi marks from labels that
   may end up in YAML frontmatter, Markdown headings, MCP tool output, or HTML
   embeds. The graph stores raw source-file identifiers, so a node label can
   contain anything tree-sitter pulled out of source.

2. ``escape_frontmatter_value`` escapes a single quoted YAML scalar so that
   U+2028/U+2029 (which YAML 1.1 treats as line breaks), tab, and C0 controls
   do not break the parser.

3. ``git_head`` returns the current git HEAD commit (full SHA) for the working
   directory, or empty string when not inside a repo. Used to stamp
   ``built_at_commit`` on every graph write.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

# C0 controls = U+0000..U+001F minus U+0009 (\t), U+000A (\n), U+000D (\r).
# We strip all of them — even \t/\n/\r — when a single-line label is required.
_LABEL_STRIP_RE = re.compile(r"[\x00-\x1f\x7f  ​-‏‪-‮]")

# For frontmatter values we additionally need to escape literal backslash and
# single quote because the value lives between single quotes (YAML 1.2 single
# quoted scalar style: doubling '' produces a literal quote).
_FRONTMATTER_NEEDS_ESCAPE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f  ]")


def sanitize_label(value: object) -> str:
    """Return a single-line string safe for labels, headings, and YAML scalars.

    - None and non-strings collapse to "".
    - Tabs, newlines, and carriage returns are first turned into a space so
      they fold into the collapse pass rather than vanishing.
    - All other C0 controls, DEL, U+2028, U+2029, and bidi marks are removed.
    - Internal whitespace is then collapsed to single spaces and stripped.
    """
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    text = _LABEL_STRIP_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def escape_frontmatter_value(value: object) -> str:
    """Return a string that is safe to place between YAML single quotes.

    The returned value should be wrapped in single quotes by the caller, e.g.
    ``f"key: '{escape_frontmatter_value(v)}'"``. Embedded single quotes are
    doubled (YAML 1.2 single-quoted scalar). Line-break-equivalent characters
    that some parsers treat as newlines (U+2028, U+2029) are stripped.
    """
    if value is None:
        return ""
    text = str(value)
    text = _FRONTMATTER_NEEDS_ESCAPE.sub("", text)
    # Newlines and tabs become spaces to keep the scalar single-line.
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # Double single quotes per YAML single-quoted scalar rules.
    text = text.replace("'", "''")
    return text


def cap_filename(name: str, limit: int = 200) -> str:
    """Cap a filename stem to ``limit`` UTF-8 *bytes*, collision-safely.

    A single path component is capped at 255 bytes by every mainstream
    filesystem, so a node label long enough to overflow that — roughly 85 CJK
    characters at 3 bytes each, or 255 ASCII — makes ``Path.write_text`` raise
    ``OSError`` (ENAMETOOLONG) and aborts the *entire* obsidian / wiki export,
    not just the one note. We cap to 200 bytes to leave headroom for the
    trailing ``.md`` and any ``_N`` dedup suffix the caller appends.

    Two properties matter:

    * The budget is counted in **bytes**, not characters, so multi-byte scripts
      (CJK, emoji) cannot slip past a character-count guard.
    * When truncation actually happens we append ``_<sha1[:8]>`` of the original
      name, so two labels sharing a long common prefix
      (``"z"*250 + "_ALPHA"`` vs ``"z"*250 + "_BETA"``) still resolve to
      distinct files instead of silently colliding.

    Truncation slices the UTF-8 byte string and decodes with ``"ignore"`` so a
    multi-byte character straddling the cut is dropped rather than producing
    mojibake. Short names are returned untouched. Mirrors graphify 690b4e5.
    """
    encoded = name.encode("utf-8")
    if len(encoded) <= limit:
        return name
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    keep = max(limit - 9, 0)  # room for "_" + 8 hex chars
    truncated = encoded[:keep].decode("utf-8", "ignore")
    return f"{truncated}_{digest}"


def safe_wiki_filename(label: str) -> str:
    """Filename stem for a wiki article: filesystem-safe and byte-capped.

    Lives here (not in wiki/generator.py) because BOTH sides of every wiki
    link must agree on it: the generator names the file with it, and the
    templates build `./<stem>.md` links with it. When the two used different
    transforms, any label with a character outside [-_.\\w] (spaces, `#`,
    parentheses, `<>` from generics) produced a file at one path and links
    pointing at another — every such link was dead on arrival.
    """
    cleaned = "".join(c if c.isalnum() or c in "-_." else "_" for c in label)
    return cap_filename(cleaned)


def git_head(repo_path: str | Path) -> str:
    """Return the full HEAD commit SHA for ``repo_path``, or "" if not a repo.

    Runs ``git rev-parse HEAD`` with a 3s timeout. Any error returns "".
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            # Pin UTF-8 so a non-ASCII branch name in `git symbolic-ref` /
            # `git rev-parse --abbrev-ref` doesn't crash with cp1252 on
            # Windows. Mirrors graphify #906.
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""
