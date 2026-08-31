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

Two properties are load-bearing beyond plain pattern matching:

- **Per-rule scoping** (``_Rule.base``). A ``.gitignore`` living in a
  subdirectory governs only that subtree, exactly like git. Scoping is part of
  the rule's data rather than a special case in the walk, which is what makes a
  nested bare ``*`` confine itself to its own directory instead of zeroing the
  whole corpus (graphify #1873/#1885/#1887).
- **NFC normalisation** on both sides. macOS hands out NFD directory names
  while editors write NFC patterns; git precomposes (``core.precomposeunicode``)
  before matching and so do we, or an accented rule silently matches nothing.
"""

from __future__ import annotations

import fnmatch
import functools
import locale
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Rule:
    pattern: str       # the compiled glob (without leading ! / trailing /)
    negate: bool       # True if the rule started with `!`
    dir_only: bool     # True if the rule ended with `/`
    anchored: bool     # True if the pattern contained `/` (anchored to root)
    base: str = ""     # POSIX rel-dir the rule was loaded from ("" = scan root)


class IgnoreMatcher:
    """Apply a list of gitignore-style patterns to relative POSIX paths.

    Construct with the contents of a single ``.codebeaconignore`` file. Use
    :meth:`is_ignored` to test a path; pass ``is_dir=True`` for directories so
    that ``dir/`` patterns match correctly.

    Paths passed to :meth:`is_ignored` must be relative POSIX paths from the
    matcher's root (use forward slashes, no leading ``./`` or ``/``).
    """

    def __init__(
        self,
        lines: list[str],
        base: str = "",
        *,
        tail_lines: list[str] | None = None,
    ) -> None:
        rules = [r for r in (_parse_line(ln, base) for ln in lines) if r is not None]
        # ``tail_lines`` (the CLI's ``--exclude``) always evaluate last, so a
        # nested ignore file discovered mid-walk can never out-rank an explicit
        # command-line exclusion under last-match-wins.
        tail = [r for r in (_parse_line(ln) for ln in (tail_lines or [])) if r is not None]
        self._rules: list[_Rule] = rules
        self._tail: list[_Rule] = tail
        self._ordered: list[_Rule] = rules + tail
        # Memoised directory verdicts so a full walk stays ~O(files·rules) rather
        # than O(files·depth·rules): the parent-directory recursion below queries
        # the same ancestor dirs repeatedly (see :meth:`_dir_ignored`).
        self._dir_cache: dict[str, bool] = {}

    @classmethod
    def from_file(cls, path: str | Path) -> "IgnoreMatcher":
        text = read_ignore_text(path)
        if text is None:
            return cls([])
        return cls(text.splitlines())

    def nested(self, lines: list[str], base: str) -> "IgnoreMatcher":
        """Return a matcher extending this one with ``lines`` scoped to ``base``.

        ``base`` is the POSIX path of the directory the ignore file was read
        from, relative to the scan root. The new rules are appended *after* the
        inherited ones (so the deeper file wins under last-match-wins, matching
        git) but still *before* the ``tail_lines`` from construction.

        Returns ``self`` unchanged when ``lines`` yields no rules, so the common
        case — a directory with no ignore file, or one holding only comments —
        allocates nothing and the rule list never grows across sibling subtrees
        (graphify #2834).
        """
        base = _nfc(base).strip("/")
        new = [r for r in (_parse_line(ln, base) for ln in lines) if r is not None]
        if not new:
            return self

        child = IgnoreMatcher.__new__(IgnoreMatcher)
        child._rules = self._rules + new
        child._tail = self._tail
        child._ordered = child._rules + child._tail
        # A rule scoped to ``base`` can only match strictly *below* ``base``, so
        # every verdict at or above it is unchanged — carry those over rather
        # than recomputing the ancestor chain on the child's first query.
        child._dir_cache = {}
        d = base
        while d:
            child._dir_cache[d] = self._dir_ignored(d)
            d = _parent_dir(d)
        return child

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Return True if ``rel_path`` is ignored.

        Implements git's directory-first semantics exactly:

        - If the immediate parent **directory** is itself ignored, ``rel_path``
          is ignored too and *cannot* be re-included — git: "It is not possible
          to re-include a file if a parent directory of that file is excluded"
          (``dir/`` + ``!dir/keep`` keeps ``keep`` out). The parent's verdict is
          computed with this same rule, so the check is fully recursive.
        - Otherwise the outcome is decided by the last rule whose pattern
          *self*-matches ``rel_path`` (positive ignores, ``!`` un-ignores).

        This distinguishes the two idioms git treats differently: ``dir/*`` /
        ``*`` exclude a directory's *contents* (the dir itself stays included, so
        ``!dir/keep`` / ``!important/**`` can re-include children), whereas
        ``dir/`` / ``logs/`` exclude the *directory*, so nothing under it can be
        re-included. It also preserves codesight #42: a parent-level ``!.source``
        re-includes ``.source`` itself but a deeper positive ``.source/testfolder``
        still self-matches and stays ignored.
        """
        rel_path = _nfc(rel_path)
        if is_dir:
            return self._dir_ignored(rel_path)
        parent = _parent_dir(rel_path)
        if parent and self._dir_ignored(parent):
            return True
        return self._self_verdict(rel_path, is_dir=False)

    def _dir_ignored(self, rel_dir: str) -> bool:
        """Recursive, memoised verdict for a directory path.

        A directory is ignored if its own parent is ignored (git's sticky
        exclusion) or the last self-matching rule for it is positive.
        """
        cached = self._dir_cache.get(rel_dir)
        if cached is not None:
            return cached
        parent = _parent_dir(rel_dir)
        if parent and self._dir_ignored(parent):
            verdict = True
        else:
            verdict = self._self_verdict(rel_dir, is_dir=True)
        self._dir_cache[rel_dir] = verdict
        return verdict

    def _self_verdict(self, rel_path: str, is_dir: bool) -> bool:
        """Last-match-wins over rules that *self*-match ``rel_path`` directly."""
        result = False
        for rule in self._ordered:
            # Cheap guard first: a `dir/` rule cannot decide a file's verdict, so
            # testing it before the glob spares every dir-only rule a full regex
            # match on every file (the dominant cost at large rule counts).
            if (not rule.dir_only or is_dir) and _matches(rule, rel_path):
                result = not rule.negate
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
        rel_path = _nfc(rel_path)
        last: _Rule | None = None
        for rule in self._ordered:
            if (not rule.dir_only or is_dir) and _matches(rule, rel_path):
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
        rel_dir = _nfc(rel_dir)
        for rule in self._ordered:
            if not rule.negate:
                continue
            if rule.base:
                # The rule only governs its own subtree. If that subtree sits at
                # or below rel_dir it can certainly rescue something beneath it;
                # if the two are disjoint it never can.
                if rule.base == rel_dir or not rel_dir or rule.base.startswith(rel_dir + "/"):
                    return True
                if not rel_dir.startswith(rule.base + "/"):
                    continue
                sub = rel_dir[len(rule.base) + 1:]
            else:
                sub = rel_dir
            if not rule.anchored:
                return True  # unanchored negation can match a file at any depth
            if _anchored_can_match_under(rule.pattern, [s for s in sub.split("/") if s]):
                return True
        return False


# ── Internals ────────────────────────────────────────────────────────────────

# Per gitignore spec: trailing whitespace is stripped unless escaped.
_TRAILING_WS_RE = re.compile(r"(?<!\\)\s+$")


def _nfc(text: str) -> str:
    """Return ``text`` in Unicode NFC, cheaply.

    ``is_normalized`` is a fast C-level check that short-circuits on the
    ASCII-only common path, so this costs essentially nothing for the paths that
    make up virtually every repo while still giving macOS's NFD directory names
    the same form as the NFC patterns editors write into ``.gitignore``.
    """
    return text if unicodedata.is_normalized("NFC", text) else unicodedata.normalize("NFC", text)


# A UTF-16 file starts with one of these; nothing valid in UTF-8 does.
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def read_ignore_text(path: str | Path, *, warn: bool = True) -> str | None:
    """Decode an ignore file, never raising and never silently losing rules.

    Returns ``None`` only when the file is absent or unreadable. Tries, in
    order: UTF-8 (with a BOM stripped — Windows PowerShell writes one by
    default, and a BOM glued to the first pattern disables exactly the rule
    users put first, typically ``secrets/`` or ``*.env``); UTF-16 when the byte
    order mark says so; the platform's preferred encoding; and finally latin-1,
    which cannot fail. Anything past the first attempt is reported on stderr,
    because a dropped exclusion means excluded files get indexed into committed
    ``.codebeacon/`` artefacts.
    """
    try:
        raw = Path(path).read_bytes()
    except (FileNotFoundError, OSError):
        return None

    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass

    attempts: list[str] = []
    if raw[:2] in _UTF16_BOMS:
        attempts.append("utf-16")
    preferred = locale.getpreferredencoding(False)
    if preferred and preferred.lower().replace("-", "") not in ("utf8", "utf16"):
        attempts.append(preferred)
    attempts.append("latin-1")

    for enc in attempts:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError, ValueError):
            continue
        if warn:
            import sys
            print(
                f"    Warning: {path} is not UTF-8; decoded as {enc}. "
                "Re-save it as UTF-8 if its patterns look wrong.",
                file=sys.stderr,
            )
        return text
    return raw.decode("utf-8", errors="replace")


def _parent_dir(rel_path: str) -> str:
    """Return the immediate parent directory of ``rel_path`` (``""`` if top-level).

    For ``"a/b/c.ts"`` this returns ``"a/b"``; for ``"a"`` it returns ``""``.
    """
    segments = [s for s in rel_path.split("/") if s]
    return "/".join(segments[:-1])


def _parse_line(raw: str, base: str = "") -> _Rule | None:
    if raw is None:
        return None
    line = _nfc(_TRAILING_WS_RE.sub("", raw))
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

    return _Rule(
        pattern=line, negate=negate, dir_only=dir_only, anchored=anchored, base=base
    )


def _matches(rule: _Rule, rel_path: str) -> bool:
    """Return True if ``rule`` matches ``rel_path`` (POSIX-style relative path)."""
    if rule.base:
        # A rule read from ``<base>/.gitignore`` governs only paths strictly
        # beneath ``<base>``, and matches against the remainder — so a nested
        # bare ``*`` confines itself to its own directory instead of zeroing the
        # whole corpus, and sibling subtrees are untouched.
        base = rule.base
        if not rel_path.startswith(base) or len(rel_path) <= len(base) or rel_path[len(base)] != "/":
            return False
        rel_path = rel_path[len(base) + 1:]

    pattern = rule.pattern
    # Translate `**` into a special token that fnmatch can't express directly.
    # We handle `**/` and `/**` by trying both stripped and unstripped variants.
    if rule.anchored:
        return _glob_match(pattern, rel_path)
    # Unanchored and `**`-free: the pattern holds no `/` (that is what makes it
    # unanchored) and a segment regex emits `[^/]*` / `[^/]`, which cannot cross
    # a separator — so only the basename can ever match, and the O(depth) suffix
    # loop collapses to a single comparison. Ancestor stickiness is unaffected:
    # it comes from `_dir_ignored`'s parent recursion, not from this loop.
    if "**" not in pattern:
        return _glob_match(pattern, rel_path.rsplit("/", 1)[-1])
    # Unanchored `**`: match against any suffix of the path's segments.
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
