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
