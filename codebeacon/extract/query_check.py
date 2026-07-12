"""Structural validation of ``.scm`` queries against grammar node-type metadata.

Defense-in-depth for tree-sitter grammar drift — the repo's most persistent bug
class (it recurred in 0.6.6/0.6.7/0.6.9 despite three prior layers: upper-bound
grammar pins, :class:`~codebeacon.extract.base.GrammarQueryError` fail-loud, and
the ``.scm`` compile test in ``tests/test_graphify_parity_0_6_6.py``). Those
layers all key off *compilation*: a query that references a node type the grammar
no longer has raises "Invalid node type" and is caught. This module adds an
*independent*, metadata-driven check — the same idea ast-grep and semgrep use to
type their query layers — so drift is caught structurally, per pattern, with a
precise report, even if tree-sitter's compiler analysis ever relaxes.

Metadata source, in preference order:

  1. ``node-types.json`` — the grammar's own generated node-type manifest, which
     also carries per-node-type field typing (``fields[name].types``). This is
     the richer source, but the pinned PyPI grammar *wheels* do not currently
     ship it (they only bundle the compiled ``.so`` plus highlight/tag queries).
  2. The compiled :class:`tree_sitter.Language` symbol table — always available,
     because it is baked into the ``.so``. It yields the full set of named node
     types and field names (which is what ``node-types.json`` is generated from),
     so node-type / field *existence* is validated even when (1) is absent.

``GrammarModel.source`` records which was used. When only (2) is reachable the
model is "degraded": existence is still checked, but per-node-type field typing
is not (that check requires the ``fields→types`` map only (1) carries).

Public API:

  * :func:`validate_queries` — validate a whole ``query→grammars`` map (defaults
    to :data:`~codebeacon.extract.base.QUERY_GRAMMAR_ALLOWLIST`, the same mapping
    the compile test enumerates). Returns a list of :class:`Violation`.
  * :func:`validate_source` — validate one query string against one grammar.
  * :func:`grammar_model` — the resolved metadata model for a grammar.

Both the test gate (``tests/test_query_node_types.py``) and any future
``doctor``-style CLI diagnostic can call these; this module deliberately adds no
CLI surface of its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from tree_sitter import Language

from .base import (
    _GRAMMAR_MODULES,
    QUERY_GRAMMAR_ALLOWLIST,
    get_language,
    load_query_file,
)

# ── Metadata model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GrammarModel:
    """The node-type surface of one grammar that a query is checked against.

    ``named_types`` — every *named* node type the grammar declares (includes
    supertypes; anonymous/literal tokens are excluded, matching what a query may
    reference by ``(name ...)``). ``field_names`` — every field name declared by
    any node type. ``source`` is ``"node-types.json"`` or ``"symbol-table"``.
    """

    grammar: str
    named_types: frozenset[str]
    field_names: frozenset[str]
    source: str


@dataclass(frozen=True)
class Violation:
    """A query references a node type / field the grammar does not declare."""

    query_file: str  # query stem, e.g. "spring_boot"
    grammar: str  # grammar checked against, e.g. "java"
    line: int  # 1-based line in the .scm where the reference occurs
    kind: str  # "node_type" | "field"
    name: str  # the offending name
    reason: str  # human-readable explanation

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.query_file}.scm:{self.line} x {self.grammar}: {self.reason}"


# ── node-types.json location + parsing ────────────────────────────────────────


def _locate_node_types(grammar: str) -> Optional[Path]:
    """Best-effort search for a grammar package's ``node-types.json``.

    Grammar generators emit ``src/node-types.json``; packagers that include it
    place it at the package root, under ``src/``, or (for multi-dialect packages
    like typescript/php) under a per-dialect subdirectory. We probe those
    locations rather than an unbounded walk. Returns None if the grammar is not
    importable or ships no manifest (the common case for the current wheels).
    """
    module_name = _GRAMMAR_MODULES.get(grammar)
    if not module_name:
        return None
    try:
        mod = __import__(module_name)
    except ImportError:
        return None
    mod_file = getattr(mod, "__file__", None)
    if not mod_file:
        return None
    pkg_dir = Path(mod_file).parent

    direct = [
        pkg_dir / "node-types.json",
        pkg_dir / "src" / "node-types.json",
        pkg_dir.parent / "node-types.json",
    ]
    for cand in direct:
        if cand.is_file():
            return cand

    # Multi-dialect packages nest one manifest per dialect (typescript/, tsx/,
    # php/, php_only/). Prefer the one whose path names the dialect we want.
    dialect = {"tsx": "tsx", "typescript": "typescript", "php": "php"}.get(grammar)
    nested = sorted(
        p
        for depth in ("*/node-types.json", "*/src/node-types.json")
        for p in pkg_dir.glob(depth)
    )
    if dialect:
        for p in nested:
            if dialect in p.parts:
                return p
    return nested[0] if nested else None


def _model_from_node_types(grammar: str, path: Path) -> Optional[GrammarModel]:
    """Build a model from a ``node-types.json`` manifest.

    The manifest is a JSON array of ``{"type","named","fields",...}`` entries.
    We collect every named ``type`` and every key of every ``fields`` map.
    Returns None if the file is unreadable, not the expected shape, or declares
    no named types (so the caller falls back to the symbol table).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None

    named: set[str] = set()
    fields: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        node_type = entry.get("type")
        if isinstance(node_type, str) and entry.get("named"):
            named.add(node_type)
        field_map = entry.get("fields")
        if isinstance(field_map, dict):
            for field_name in field_map:
                if isinstance(field_name, str):
                    fields.add(field_name)
    if not named:
        return None
    return GrammarModel(grammar, frozenset(named), frozenset(fields), "node-types.json")


def _model_from_language(grammar: str, lang: Language) -> GrammarModel:
    """Build a model from the compiled grammar's symbol table (always available).

    Enumerates every named node kind and every field name baked into the ``.so``
    — the exact data ``node-types.json`` is generated from. Supertypes are named
    kinds and are included; a query may legitimately reference them.
    """
    named: set[str] = set()
    for kind_id in range(lang.node_kind_count):
        name = lang.node_kind_for_id(kind_id)
        if name and lang.node_kind_is_named(kind_id):
            named.add(name)
    # Supertypes are already named kinds, but union them defensively in case a
    # binding excludes them from the visible id range.
    for super_id in lang.supertypes:
        name = lang.node_kind_for_id(super_id)
        if name:
            named.add(name)

    fields: set[str] = set()
    for field_id in range(1, lang.field_count + 1):
        field_name = lang.field_name_for_id(field_id)
        if field_name:
            fields.add(field_name)

    return GrammarModel(grammar, frozenset(named), frozenset(fields), "symbol-table")


_MODEL_CACHE: dict[str, Optional[GrammarModel]] = {}


def grammar_model(grammar: str) -> Optional[GrammarModel]:
    """Resolve the metadata model for *grammar*, or None if it is unavailable.

    Prefers ``node-types.json``; falls back to the compiled symbol table. Returns
    None only when the grammar is not installed at all — the same condition under
    which the extractor skips its files, so it is a clean skip, not a violation.
    Cached: models are derived from stable grammar binaries.
    """
    if grammar in _MODEL_CACHE:
        return _MODEL_CACHE[grammar]

    model: Optional[GrammarModel] = None
    manifest = _locate_node_types(grammar)
    if manifest is not None:
        model = _model_from_node_types(grammar, manifest)
    if model is None:
        lang = get_language(grammar)
        if lang is not None:
            model = _model_from_language(grammar, lang)

    _MODEL_CACHE[grammar] = model
    return model


def clear_model_cache() -> None:
    """Drop the cached models (used by tests that isolate grammar loading)."""
    _MODEL_CACHE.clear()


# ── .scm reference scanner ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Ref:
    kind: str  # "node_type" | "field"
    name: str
    line: int


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Chars that may appear in a predicate name after '#': eq?, match?, any-of?,
# not-eq?, set!, is-not? ...
_PREDICATE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-?!.")


def _scan_refs(src: str) -> list[_Ref]:
    """Extract every referenced *named node type* and *field name* from a query.

    A deliberately small S-expression tokenizer — not a full query parser. It
    keys off two syntactic positions that uniquely identify each reference:

      * node type  — an identifier whose previous significant char is ``(``
                      (i.e. ``(call_expression`` → ``call_expression``);
      * field name — an identifier immediately followed by ``:``
                      (i.e. ``arguments:`` → ``arguments``), or ``!ident``.

    It ignores everything a query may otherwise contain: comments (``; ...``),
    string/anonymous literals (``"..."``), capture names (``@a.b``), predicates
    (``(#eq? ...)``), the wildcards ``_`` / ``(_)``, and anchors/quantifiers
    (``. * + ?``). Skipping strings and comments is essential — the ``.scm``
    files carry regex predicates like ``"^(get|post)$"`` and prose comments with
    ``field:``-shaped text that would otherwise be mistaken for references.
    """
    refs: list[_Ref] = []
    i = 0
    n = len(src)
    line = 1
    last_sig = ""  # last significant (non-space, non-comment) char seen

    while i < n:
        c = src[i]

        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue

        if c == ";":  # comment to end of line
            while i < n and src[i] != "\n":
                i += 1
            continue

        if c == '"':  # string / anonymous literal — skip, honouring escapes
            i += 1
            while i < n:
                ch = src[i]
                if ch == "\\":
                    if src[i + 1 : i + 2] == "\n":
                        line += 1
                    i += 2
                    continue
                if ch == "\n":
                    line += 1
                elif ch == '"':
                    i += 1
                    break
                i += 1
            last_sig = '"'
            continue

        if c == "@":  # capture name @ident.path — skip
            i += 1
            while i < n and (src[i].isalnum() or src[i] in "_.-"):
                i += 1
            last_sig = "@"
            continue

        if c == "#":  # predicate name inside (#...) — skip so it is not a node type
            i += 1
            while i < n and src[i] in _PREDICATE_CHARS:
                i += 1
            last_sig = "#"
            continue

        if c == "!":  # negated field: !ident references a field name
            match = _IDENT_RE.match(src, i + 1)
            if match:
                refs.append(_Ref("field", match.group(0), line))
                i = match.end()
                last_sig = "x"
                continue
            last_sig = c
            i += 1
            continue

        match = _IDENT_RE.match(src, i)
        if match:
            name = match.group(0)
            end = match.end()
            if end < n and src[end] == ":":  # field name
                refs.append(_Ref("field", name, line))
                i = end + 1
                last_sig = ":"
                continue
            if last_sig == "(" and name != "_":  # node type (skip the wildcard)
                refs.append(_Ref("node_type", name, line))
            i = end
            last_sig = "x"
            continue

        # Any other single char (parentheses, brackets, anchors, quantifiers).
        last_sig = c
        i += 1

    return refs


# ── Validation ────────────────────────────────────────────────────────────────


def validate_source(query_file: str, src: str, grammar: str) -> list[Violation]:
    """Validate one query string against one grammar's metadata model.

    Returns [] when the grammar is not installed (clean skip, mirroring the
    extractor), otherwise one :class:`Violation` per referenced node type / field
    that the grammar does not declare.
    """
    model = grammar_model(grammar)
    if model is None:
        return []

    violations: list[Violation] = []
    for ref in _scan_refs(src):
        if ref.kind == "node_type":
            if ref.name not in model.named_types:
                violations.append(
                    Violation(
                        query_file=query_file,
                        grammar=grammar,
                        line=ref.line,
                        kind="node_type",
                        name=ref.name,
                        reason=(
                            f"named node type '{ref.name}' does not exist in the "
                            f"{grammar} grammar (checked via {model.source}) — the "
                            f"query would compile-fail or silently capture nothing"
                        ),
                    )
                )
        elif ref.name not in model.field_names:
            violations.append(
                Violation(
                    query_file=query_file,
                    grammar=grammar,
                    line=ref.line,
                    kind="field",
                    name=ref.name,
                    reason=(
                        f"field '{ref.name}:' does not exist in the {grammar} "
                        f"grammar (checked via {model.source})"
                    ),
                )
            )
    return violations


def validate_queries(
    query_map: Optional[Mapping[str, frozenset[str]]] = None,
) -> list[Violation]:
    """Validate every ``.scm`` query against the grammars it claims to support.

    *query_map* maps a query stem to the set of grammar names it is expected to
    compile against; it defaults to
    :data:`~codebeacon.extract.base.QUERY_GRAMMAR_ALLOWLIST`, the same contract
    the compile test enumerates. Queries with no ``.scm`` on disk, and grammars
    that are not installed, are skipped cleanly (they are not violations).
    """
    if query_map is None:
        query_map = QUERY_GRAMMAR_ALLOWLIST

    violations: list[Violation] = []
    for query_file in sorted(query_map):
        src = load_query_file(query_file)
        if src is None:
            # No .scm on disk — e.g. a framework served by a non-tree-sitter
            # side channel. Nothing to validate structurally; skip.
            continue
        for grammar in sorted(query_map[query_file]):
            violations.extend(validate_source(query_file, src, grammar))
    return violations
