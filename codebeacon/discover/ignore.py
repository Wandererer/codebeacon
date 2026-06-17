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
import functools
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

        Semantics (closer to gitignore than naive last-match-wins):

        - A *self* match — the rule's pattern matches ``rel_path`` directly —
          can flip the verdict either way (positive ignores, ``!`` un-ignores).
        - A *positive ancestor* match — the rule matches an ancestor directory
          of ``rel_path`` — implicitly ignores the descendant (gitignore's
          "everything under an ignored directory is ignored too" rule).
        - A *negation* matching only via an ancestor does **not** re-include
          the descendant. Mirrors gitignore's rule that a child cannot be
          re-included once its parent is excluded, and prevents parent-level
          negations from silently overriding explicit positive ignores at
          deeper paths (see codesight #42 / 0bedd0d). To opt into recursive
          re-inclusion, write an explicit ``!path/**`` rule that self-matches
          the descendants you want back.
        """
        ancestors = _ancestor_dirs(rel_path)
        result = False
        for rule in self._rules:
            self_match = _matches(rule, rel_path) and (not rule.dir_only or is_dir)
            anc_match = any(_matches(rule, anc) for anc in ancestors)
            if self_match:
                result = not rule.negate
            elif anc_match and not rule.negate:
                # Positive ancestor match is sticky; descendants stay ignored.
                # Negation-via-ancestor deliberately does nothing here.
                result = True
        return result

    def is_explicitly_included(self, rel_path: str, is_dir: bool = False) -> bool:
        """Return True if the last *self*-matching rule for ``rel_path`` is a negation.

        Used by the scanner to let users opt back into entries that the
        default heuristics (hidden dirs, ``IGNORE_DIRS``) would otherwise
        skip — e.g. ``!.source`` in ``.codebeaconignore`` re-includes the
        ``.source`` directory itself. Ancestor matches are intentionally
        ignored: a parent-level ``!.source`` must not silently re-include
        nested dot-folders like ``.source/.vs``.
        """
        last: _Rule | None = None
        for rule in self._rules:
            if _matches(rule, rel_path) and (not rule.dir_only or is_dir):
                last = rule
        return last is not None and last.negate

    def could_unignore_under(self, rel_dir: str) -> bool:
        """Return True if some negation (``!``) rule could re-include a path
        strictly *under* ``rel_dir``.

        The scanner uses this to decide whether descending into a directory that
        is itself ignored is worthwhile: only if a ``!`` rule could rescue a
        file beneath it. This replaces the old global "any negation anywhere →
        descend into every ignored directory" flag, which wasted the entire
        excluded subtree's traversal whenever a single *unrelated* ``!`` rule
        existed (graphify #1274).

        Conservative by construction — it returns True whenever a negation
        *might* reach below ``rel_dir`` (always for unanchored ``!`` rules,
        which match at any depth), so a directory is pruned only when no
        negation could possibly rescue a file inside it. It never drops a file
        that should have been re-included; at worst it descends needlessly.
        Recall that a negation only re-includes via a *self*-match, never via an
        ancestor match (see :meth:`is_ignored`), so an anchored ``!a/b/c`` can
        only matter under ``a/``.
        """
        dir_segs = [s for s in rel_dir.split("/") if s]
        for rule in self._rules:
            if not rule.negate:
                continue
            if not rule.anchored:
                return True  # unanchored negation can match a file at any depth
            if _anchored_can_match_under(rule.pattern, dir_segs):
                return True
        return False


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


def _anchored_can_match_under(pattern: str, dir_segs: list[str]) -> bool:
    """True if anchored glob ``pattern`` can match a path that has ``dir_segs``
    as a *proper* prefix — i.e. some file/subpath beneath that directory.

    Segment-wise alignment of the pattern against ``dir_segs`` with ``**``
    consuming zero-or-more segments; the remaining pattern must be able to match
    at least one further segment (the file). Used only by
    :meth:`IgnoreMatcher.could_unignore_under`.
    """
    pat = pattern.split("/")

    def rec(pi: int, si: int) -> bool:
        if si == len(dir_segs):
            # All directory segments consumed — the pattern must still be able
            # to match >=1 further segment beneath rel_dir. Anything left in the
            # pattern (a glob segment, or a trailing **) can. Nothing left means
            # the pattern matches rel_dir itself, not something under it.
            return pi < len(pat)
        if pi == len(pat):
            return False
        seg = pat[pi]
        if seg == "**":
            return rec(pi + 1, si) or rec(pi, si + 1)  # ** matches 0+ segments
        if _glob_match(seg, dir_segs[si]):
            return rec(pi + 1, si + 1)
        return False

    return rec(0, 0)


def _segment_glob_regex(segment: str) -> str:
    """Translate a single glob segment to regex where `*`/`?` do NOT cross `/`.

    gitignore semantics: within a path segment, `*` matches any run of
    non-separator characters and `?` matches a single one. This is the key
    difference from :func:`fnmatch.fnmatchcase`, whose `*`/`?` happily cross
    `/` and would make e.g. ``src/*.py`` match ``src/a/b.py``.
    """
    out: list[str] = []
    i, n = 0, len(segment)
    while i < n:
        c = segment[i]
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i + 1
            if j < n and segment[j] in "!^":
                j += 1
            if j < n and segment[j] == "]":
                j += 1
            while j < n and segment[j] != "]":
                j += 1
            if j >= n:
                out.append(re.escape(c))  # unterminated class → literal '['
            else:
                inner = segment[i + 1:j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                out.append("[" + inner + "]")
                i = j + 1
                continue
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


@functools.lru_cache(maxsize=4096)
def _compile_glob(pattern: str) -> tuple[re.Pattern[str] | None, bool]:
    """Compile a gitignore glob to a regex **once** (memoized per pattern).

    Returns ``(compiled, use_fnmatch)``:
      - ``(re.Pattern, False)`` — match with the compiled regex.
      - ``(None, True)``  — non-``**`` pattern whose regex was invalid; the
        caller falls back to :func:`fnmatch.fnmatchcase` (legacy behaviour).
      - ``(None, False)`` — ``**`` pattern whose regex was invalid; never matches.

    Previously the regex string was rebuilt and re-compiled on *every*
    :func:`_glob_match` call (graphify #1261 — the dominant per-file cost when a
    deep tree is matched against a large rule set). Patterns are few and bounded,
    so an LRU cache collapses this to one compile per distinct pattern.
    """
    if "**" not in pattern:
        # Segment-aware match: `*`/`?` must not cross `/`.
        try:
            return re.compile("^" + _segment_glob_regex(pattern) + "$"), False
        except re.error:
            return None, True  # fall back to fnmatch

    # `**` means zero-or-more directory segments. Build a regex.
    parts = pattern.split("/")
    regex_parts: list[str] = []
    for i, part in enumerate(parts):
        if part == "**":
            if i == len(parts) - 1:
                # Trailing `**` matches one-or-more descendant segments. The
                # preceding part already emitted a `/`, so consume the rest.
                regex_parts.append(r".+")
            else:
                regex_parts.append(r"(?:.*/)?")
        else:
            regex_parts.append(_segment_glob_regex(part))
            if i < len(parts) - 1:
                regex_parts.append("/")
    regex = "^" + "".join(regex_parts).replace("//", "/") + "$"
    try:
        return re.compile(regex), False
    except re.error:
        return None, False  # invalid `**` regex → never matches


def _glob_match(pattern: str, path: str) -> bool:
    """Match ``path`` against a gitignore-style ``pattern`` with ``**`` support."""
    compiled, use_fnmatch = _compile_glob(pattern)
    if compiled is not None:
        return bool(compiled.match(path))
    if use_fnmatch:
        return fnmatch.fnmatchcase(path, pattern)
    return False
