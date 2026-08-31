"""Sanitization, escaping, and git-state helpers shared by writers.

Four concerns:

1. ``sanitize_label`` strips control characters and bidi marks from labels that
   may end up in YAML frontmatter, Markdown headings, MCP tool output, or HTML
   embeds. The graph stores raw source-file identifiers, so a node label can
   contain anything tree-sitter pulled out of source.

2. ``escape_frontmatter_value`` escapes a single quoted YAML scalar so that
   U+2028/U+2029 (which YAML 1.1 treats as line breaks), tab, and C0 controls
   do not break the parser.

3. ``defang_model_tokens`` neutralizes chat-template control markers found in
   text that is handed to an LLM (MCP tool output, generated CLAUDE.md), so a
   string lifted out of a scanned repository cannot forge a turn boundary.

4. ``git_head`` returns the current git HEAD commit (full SHA) for the working
   directory, or empty string when not inside a repo. Used to stamp
   ``built_at_commit`` on every graph write.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from functools import lru_cache
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


# Filesystem limits used when the real ones cannot be probed. POSIX minimums
# are far lower, but every mainstream Linux/macOS filesystem is at least this.
_FALLBACK_NAME_MAX = 255
_FALLBACK_PATH_MAX = 1024
# Windows has no pathconf; MAX_PATH is 260 unless long paths are opted into.
_WINDOWS_NAME_MAX = 255
_WINDOWS_PATH_MAX = 260

# Bytes a caller may still append after the capped stem: ".md" (3) plus the
# "_h" + 6 hex characters ``dedup_stem`` salts a colliding note with (8).
_FILENAME_RESERVE = 12


@lru_cache(maxsize=128)
def _fs_limits(dest: str) -> tuple[int, int]:
    """(NAME_MAX, PATH_MAX) for ``dest``, probed once per directory.

    ``os.pathconf`` needs a path that exists, and export destinations are
    routinely created later in the run, so we walk up to the nearest existing
    ancestor. Anything that fails (Windows, a filesystem that does not answer,
    a bogus value) falls back to the conservative constants above — the probe
    may only ever *lower* the budget, never raise it above ``limit``.
    """
    if os.name == "nt":
        return _WINDOWS_NAME_MAX, _WINDOWS_PATH_MAX
    name_max, path_max = _FALLBACK_NAME_MAX, _FALLBACK_PATH_MAX
    probe = Path(dest)
    for candidate in (probe, *probe.parents):
        try:
            if not candidate.exists():
                continue
            name_max = int(os.pathconf(candidate, "PC_NAME_MAX")) or name_max
            path_max = int(os.pathconf(candidate, "PC_PATH_MAX")) or path_max
        except (OSError, ValueError, AttributeError, KeyError):
            pass
        break
    return name_max, path_max


def _budget_for(limit: int, dest_dir: str | Path | None) -> int:
    """Byte budget for a filename stem written into ``dest_dir``.

    Without a destination the caller gets the plain ``limit`` — the historical
    behaviour, and the right answer when the stem's home is unknown. With one,
    the budget also has to fit inside the filesystem's NAME_MAX (eCryptfs caps
    it near 143 bytes, well under our 200) *and* inside PATH_MAX once the
    destination directory's own length is subtracted, which is what a deeply
    nested output directory blows through (graphify #2109/#943).
    """
    if dest_dir is None:
        return limit
    name_max, path_max = _fs_limits(str(dest_dir))
    dest_len = len(os.fsencode(str(dest_dir)))
    budget = min(
        limit,
        name_max - _FILENAME_RESERVE,
        path_max - dest_len - 1 - _FILENAME_RESERVE,
    )
    # Never return a budget so small that the collision hash cannot fit; if the
    # destination is genuinely unwritable no stem length saves it, and the
    # caller's per-file OSError guard reports that one file honestly.
    return max(budget, 16)


def cap_filename(name: str, limit: int = 200, *, dest_dir: str | Path | None = None) -> str:
    """Cap a filename stem to a safe number of UTF-8 *bytes*, collision-safely.

    A node label long enough to overflow the filesystem's per-component limit —
    roughly 85 CJK characters at 3 bytes each, or 255 ASCII — makes
    ``Path.write_text`` raise ``OSError`` (ENAMETOOLONG) and aborts the *entire*
    obsidian / wiki export, not just the one note. The default cap of 200 bytes
    leaves headroom for the trailing ``.md`` and any ``_N`` dedup suffix the
    caller appends.

    ``dest_dir`` makes the budget destination-aware. 200 bytes is only safe when
    NAME_MAX is 255 *and* the directory the file lands in is short; neither is
    guaranteed (an eCryptfs home caps names near 143 bytes, and a deep output
    tree can exhaust PATH_MAX with a name every filesystem would accept on its
    own). Passing the destination probes the real limits and lowers the budget
    to fit; omitting it keeps the historical fixed cap.

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

    A stem with no alphanumeric character (empty, whitespace-only, or all
    punctuation such as ``"@"`` or ``"***"``) would produce a broken or hidden
    filename (``@.md``, ``.md``); it falls back to ``"unnamed"`` (graphify #1409).
    """
    if not any(c.isalnum() for c in name):
        return "unnamed"
    budget = _budget_for(limit, dest_dir)
    encoded = name.encode("utf-8")
    if len(encoded) <= budget:
        return name
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    keep = max(budget - 9, 0)  # room for "_" + 8 hex chars
    truncated = encoded[:keep].decode("utf-8", "ignore")
    return f"{truncated}_{digest}"


def undot_filename(stem: str) -> str:
    """Rewrite a leading ``.`` so the file is neither hidden nor unsweepable.

    A node legitimately labelled ``.env`` / ``.gitignore`` / ``.eslintrc``
    produces ``.env.md``, which is invisible in Obsidian *and* — because the
    stale-note sweep skips every dot-path to protect ``.obsidian/`` and the
    ownership marker — immune to codebeacon's own cleanup, so it accumulates
    forever across rescans (graphify #929-8). ``.env`` becomes ``dot-env``; a
    stem that is nothing but dots empties out, so ``cap_filename``'s
    no-alphanumeric guard turns it into ``"unnamed"`` rather than a bare
    ``dot-``.
    """
    if not stem.startswith("."):
        return stem
    rest = stem.lstrip(".")
    return f"dot-{rest}" if rest else ""


def dedup_stem(stem: str, node_id: str, claimed: dict[str, str], scope: str = "") -> str:
    """Return a filesystem-unique, case-folded stem for ``stem``.

    ``claimed`` maps a lowercased ``"<scope>/<stem>"`` key → the node_id that owns
    it, and is mutated in place. When a DIFFERENT node would map to an
    already-claimed key (a collision on a case-insensitive filesystem — macOS
    APFS, Windows NTFS — where ``UserService`` and ``userService`` are the same
    file), the stem is salted with a short stable hash of ``node_id`` so both
    notes survive as distinct files instead of one silently overwriting the
    other (graphify #1453/#1504/#1522).

    The salt is prefixed ``_h`` so the suffix never looks like the ``_<digits>``
    dedup markers other export steps strip. ``scope`` namespaces the claim (e.g.
    the wiki subdirectory) so files in different directories never false-collide.
    """
    key = f"{scope}/{stem.lower()}" if scope else stem.lower()
    owner = claimed.get(key)
    if owner is None or owner == node_id:
        claimed[key] = node_id
        return stem
    salted = f"{stem}_h{hashlib.sha1(node_id.encode('utf-8')).hexdigest()[:6]}"
    salted_key = f"{scope}/{salted.lower()}" if scope else salted.lower()
    claimed[salted_key] = node_id
    return salted


def safe_wiki_filename(label: str, *, dest_dir: str | Path | None = None) -> str:
    """Filename stem for a wiki article: filesystem-safe and byte-capped.

    Lives here (not in wiki/generator.py) because BOTH sides of every wiki
    link must agree on it: the generator names the file with it, and the
    templates build `./<stem>.md` links with it. When the two used different
    transforms, any label with a character outside [-_.\\w] (spaces, `#`,
    parentheses, `<>` from generics) produced a file at one path and links
    pointing at another — every such link was dead on arrival.

    A ``None`` label (a node whose ``label`` attribute is absent or explicitly
    ``None``) short-circuits to ``"unnamed"`` instead of crashing on the
    character iteration, so a single mis-shaped node can't abort the whole
    wiki/obsidian export (G06).

    A leading ``.`` is rewritten (``.env`` → ``dot-env``) so the article is not
    a hidden file, and so the wiki article and the obsidian note — which applies
    the same rule — keep matching names.
    """
    if not isinstance(label, str):
        return "unnamed"
    cleaned = "".join(c if c.isalnum() or c in "-_." else "_" for c in label)
    return cap_filename(undot_filename(cleaned), dest_dir=dest_dir)


# ── Chat-template control-marker defanging ────────────────────────────────────

# Bracketed instruction markers, matched by FORM rather than by vendor: an
# all-caps token (optionally closing) inside square brackets that names a turn
# or tool boundary. Deliberately an explicit set, not `[A-Z_]+`, because
# codebeacon's own output is full of legitimate all-caps brackets — every
# obsidian connection line ends in `[EXTRACTED]`, and route labels carry
# `[GET /users]`.
_INSTRUCTION_TAG_RE = re.compile(
    r"\[/?(?:INST|SYS|SYSTEM|AVAILABLE_TOOLS|TOOL_CALLS|TOOL_RESULTS?|"
    r"BOS|EOS|PAD|UNK|CLS|SEP|MASK)\]"
)

# Llama-2 style `<<SYS>>` / `<</SYS>>` fences.
_SYS_FENCE_RE = re.compile(r"<</?SYS>>")

# A line that opens with a conversation role header. Leading markdown markers
# (list bullet, blockquote, heading) are allowed because that is exactly how an
# injected header would hide inside a wiki excerpt.
#
# The prefix is ONE character class with ONE quantifier, deliberately. Spelling
# it as nested quantifiers (`(?:[-*>#]+[ \t]*)*`) is the natural way to say
# "markers, then space, repeated" and it backtracks exponentially on a line made
# only of those characters — a directory named `----------------------------`
# is enough to wedge the context-map step, turning a defence against hostile
# repository content into a denial of service caused by it. Newline is excluded
# from the class so a match can never straddle two lines.
_ROLE_HEADER_RE = re.compile(
    r"(?im)^([-*>#\t ]*)"
    r"(system|assistant|user|human|developer|tool)([ \t]*):"
)


def defang_model_tokens(text: str) -> str:
    """Neutralize chat-template control markers in ``text``.

    codebeacon reads identifiers, headings, and comments out of whatever
    repository it is pointed at, then hands them to an LLM — through MCP tool
    results and through the generated CLAUDE.md / context map. A file in a
    scanned repo can therefore put ``<|im_start|>system`` or a bare ``System:``
    line in front of the model as if it were part of the conversation.

    The transform separates each marker's characters instead of deleting them,
    so nothing an operator needs to read is lost — ``<|im_start|>`` renders as
    ``< |im_start| >`` and a forged ``System:`` header as ``System :`` — while
    no exact control-token string survives:

    * ``<|`` and ``|>`` special-token delimiters are broken apart;
    * ``[INST]``-family and ``<<SYS>>`` instruction tags gain inner spaces;
    * a line-leading conversation role header loses its colon adjacency.

    Matching is by form, never by vendor, so a template this code has never
    heard of is covered as long as it uses one of these shapes. Non-strings
    coerce to ``""`` so a caller can pass a possibly-``None`` field.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    out = text.replace("<|", "< |").replace("|>", "| >")
    out = _INSTRUCTION_TAG_RE.sub(lambda m: f"[ {m.group(0)[1:-1]} ]", out)
    out = _SYS_FENCE_RE.sub(lambda m: f"< {m.group(0)[2:-2]} >", out)
    out = _ROLE_HEADER_RE.sub(r"\1\2\3 :", out)
    return out


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
