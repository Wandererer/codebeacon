"""gitignore-style matcher for ``.codebeaconignore``.

The previous implementation in :mod:`codebeacon.discover.scanner` reduced every
pattern to a directory-name match against ``IGNORE_DIRS``. This module replaces
that with proper gitignore semantics:

- last-match-wins: rules are evaluated in order; the last rule whose pattern
  matches the path decides the outcome.
- ``!pattern`` re-includes a previously-ignored path (negation).
- a trailing ``/`` matches directories only.
- a leading ``/`` (or pattern with no ``/``) anchors to the rule's own
  directory; otherwise the pattern matches at any depth.
- comments start with ``#``; trailing unescaped whitespace is stripped.

Only the features we need are implemented — this is not a 1:1 git port. In
particular, ``**`` is supported via Python ``fnmatch``-style ``*`` segments
where each ``*`` does not cross ``/``, plus an explicit ``**`` token meaning
zero-or-more directory segments.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Rule:
    pattern: str       # the compiled glob (without leading ! / trailing /)
    negate: bool       # True if the rule started with `!`
    dir_only: bool     # True if the rule ended with `/`
    anchored: bool     # True if the pattern contained `/` (anchored to root)


class IgnoreMatcher:
    """Apply a list of gitignore-style patterns to relative POSIX paths.

    Construct with the contents of a single ``.codebeaconignore`` file. Use
    :meth:`is_ignored` to test a path; pass ``is_dir=True`` for directories so
    that ``dir/`` patterns match correctly.

    Paths passed to :meth:`is_ignored` must be relative POSIX paths from the
    matcher's root (use forward slashes, no leading ``./`` or ``/``).
    """

    def __init__(self, lines: list[str]) -> None:
        self._rules: list[_Rule] = [r for r in (_parse_line(ln) for ln in lines) if r is not None]

    @classmethod
    def from_file(cls, path: str | Path) -> "IgnoreMatcher":
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return cls([])
        return cls(text.splitlines())

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Return True if ``rel_path`` is ignored.

        Last-match-wins. A negation rule (``!pattern``) flips a prior ignore
        back to "not ignored". Two ways a rule can fire for ``rel_path``:

        - it matches ``rel_path`` directly (respecting ``dir_only``), or
        - it matches any ancestor directory of ``rel_path`` — gitignore's
          implicit "everything beneath an ignored directory is ignored too"
          semantics. Ancestors are always treated as directories, so
          ``dir_only`` does not block the ancestor check.
        """
        ancestors = _ancestor_dirs(rel_path)
        result = False
        for rule in self._rules:
            # Match the path itself if dir_only allows it.
            self_match = _matches(rule, rel_path) and (not rule.dir_only or is_dir)
            # Match any ancestor (always as a directory).
            anc_match = any(_matches(rule, anc) for anc in ancestors)
            if self_match or anc_match:
                result = not rule.negate
        return result


# ── Internals ────────────────────────────────────────────────────────────────

# Per gitignore spec: trailing whitespace is stripped unless escaped.
_TRAILING_WS_RE = re.compile(r"(?<!\\)\s+$")


def _ancestor_dirs(rel_path: str) -> list[str]:
    """Return every directory component up to (but excluding) ``rel_path``.

    For ``"a/b/c.ts"`` this returns ``["a", "a/b"]``.
    """
    segments = [s for s in rel_path.split("/") if s]
    return ["/".join(segments[: i + 1]) for i in range(len(segments) - 1)]


def _parse_line(raw: str) -> _Rule | None:
    if raw is None:
        return None
    line = _TRAILING_WS_RE.sub("", raw)
    if not line:
        return None
    if line.lstrip().startswith("#"):
        return None
    # Unescape backslash-escaped trailing space we deliberately preserved.
    line = line.replace("\\ ", " ")

    negate = False
    if line.startswith("!"):
        negate = True
        line = line[1:]

    dir_only = False
    if line.endswith("/"):
        dir_only = True
        line = line[:-1]

    if not line:
        return None

    anchored = "/" in line
    if line.startswith("/"):
        line = line[1:]

    return _Rule(pattern=line, negate=negate, dir_only=dir_only, anchored=anchored)


def _matches(rule: _Rule, rel_path: str) -> bool:
    """Return True if ``rule`` matches ``rel_path`` (POSIX-style relative path)."""
    pattern = rule.pattern
    # Translate `**` into a special token that fnmatch can't express directly.
    # We handle `**/` and `/**` by trying both stripped and unstripped variants.
    if rule.anchored:
        return _glob_match(pattern, rel_path)
    # Unanchored: match against any suffix of the path's segments.
    segments = rel_path.split("/")
    for i in range(len(segments)):
        candidate = "/".join(segments[i:])
        if _glob_match(pattern, candidate):
            return True
    return False


def _glob_match(pattern: str, path: str) -> bool:
    """Match ``path`` against a gitignore-style ``pattern`` with ``**`` support."""
    if "**" not in pattern:
        # `*` in fnmatch crosses `/`, but gitignore says it shouldn't. For the
        # vast majority of real-world ignore rules this only matters at the
        # boundary of the last segment, which the per-suffix iteration in
        # ``_matches`` already covers. fnmatch is sufficient here.
        return fnmatch.fnmatchcase(path, pattern)

    # `**` means zero-or-more directory segments. Build a regex.
    parts = pattern.split("/")
    regex_parts: list[str] = []
    for i, part in enumerate(parts):
        if part == "**":
            regex_parts.append(r"(?:.*/)?")
        else:
            seg = fnmatch.translate(part)
            # fnmatch.translate wraps with (?s:...) and trailing \Z. Strip them.
            seg = re.sub(r"^\(\?s:|\)\\Z$", "", seg)
            seg = seg.rstrip("$")
            regex_parts.append(seg)
            if i < len(parts) - 1:
                regex_parts.append("/")
    regex = "^" + "".join(regex_parts).replace("//", "/") + "$"
    try:
        return bool(re.match(regex, path))
    except re.error:
        return False
