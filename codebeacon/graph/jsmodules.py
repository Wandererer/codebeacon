"""Path-based module resolution for import edges.

Until 0.7.1 an import edge was bound to its target by *label*: the last segment
of the import string was matched against declaration names. That is how
``from codebeacon.graph.build import build_graph`` came to bind to
``SymbolTable.build`` in a completely different file (C-53b), and how 60.4% of
a real Next.js app's internal imports were dropped even though every one of
their target files existed on disk (G-0927-10).

This module resolves an import string to the actual **file** it names, using
the same rules the language's own loader would:

* relative specifiers against the importing file's directory;
* TypeScript/JavaScript path aliases from ``tsconfig.json`` / ``jsconfig.json``
  (``extends`` chains, ``baseUrl``, TS 5.5 ``${configDir}``);
* dotted package paths (Java/Kotlin/Python) and slashed module paths, matched
  against the scanned corpus by path suffix.

Only files that were actually scanned can be returned, so a resolution is
always evidence that the two files are really connected.

The resolver is created per ``build_graph`` call and holds its own alias cache.
It must never become a module-global: ``codebeacon watch`` and ``serve`` are
long-lived processes, and a process-lifetime cache would keep serving an alias
map from before the user edited their tsconfig (G-0949-18). Even within one
instance every config is re-checked by mtime.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

from codebeacon.common.filters import lang_family

# Extension candidates to try when an import names a module without one.
_FAMILY_EXTS: dict[str, tuple[str, ...]] = {
    "web": (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".d.ts"),
    "python": (".py", ".pyi"),
    "jvm": (".java", ".kt", ".kts"),
    "csharp": (".cs",),
    "php": (".php",),
    "go": (".go",),
    "ruby": (".rb",),
    "rust": (".rs",),
    "swift": (".swift",),
}

# Directory-index spellings, tried after the direct file candidates.
_FAMILY_INDEX: dict[str, tuple[str, ...]] = {
    "web": ("index.ts", "index.tsx", "index.js", "index.jsx", "index.mjs"),
    "python": ("__init__.py",),
}

_ALL_EXTS: tuple[str, ...] = tuple(
    dict.fromkeys(e for exts in _FAMILY_EXTS.values() for e in exts)
)

# Families whose import strings separate packages with "." rather than "/".
_DOTTED_FAMILIES = frozenset({"jvm", "python", "csharp"})


# ── tsconfig / jsconfig ───────────────────────────────────────────────────────

_LINE_COMMENT = re.compile(r"//[^\n\r]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas so ``json.loads`` accepts a tsconfig.

    String literals are protected: a ``"https://…"`` value must survive the
    line-comment pass intact.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    j += 1
                    break
                j += 1
            out.append(text[i:j])
            i = j
            continue
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                m = _LINE_COMMENT.match(text, i)
                i = m.end() if m else n
                continue
            if nxt == "*":
                m = _BLOCK_COMMENT.match(text, i)
                i = m.end() if m else n
                continue
        out.append(ch)
        i += 1
    return _TRAILING_COMMA.sub(r"\1", "".join(out))


class _AliasMap:
    """Resolved ``paths`` / ``baseUrl`` for one project root."""

    __slots__ = ("base_url", "paths", "stamps")

    def __init__(self) -> None:
        # Absolute baseUrl directory, or None.
        self.base_url: Optional[str] = None
        # pattern → [absolute target templates]
        self.paths: dict[str, list[str]] = {}
        # (config path, mtime_ns) for every file that contributed — used to
        # detect an edit made while a watch/serve process is still running.
        self.stamps: tuple[tuple[str, int], ...] = ()

    def stale(self) -> bool:
        for path, mtime in self.stamps:
            try:
                if os.stat(path).st_mtime_ns != mtime:
                    return True
            except OSError:
                return True
        return False


def _read_config(path: str) -> Optional[dict]:
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        data = json.loads(strip_jsonc(raw))
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_extends(spec: str, from_dir: str) -> Optional[str]:
    """Locate the config named by an ``extends`` value.

    npm-published bases (``@tsconfig/node18/tsconfig.json``) live in
    node_modules, which is never scanned — they carry compiler settings, not
    project path aliases, so skipping them costs nothing.
    """
    if not spec or spec.startswith("@") or not spec.startswith("."):
        return None
    cand = os.path.normpath(os.path.join(from_dir, spec))
    if os.path.isfile(cand):
        return cand
    for suffix in (".json", "/tsconfig.json", "/jsconfig.json"):
        if os.path.isfile(cand + suffix):
            return cand + suffix
    return None


def _load_alias_map(root: str) -> _AliasMap:
    """Build the effective alias map for ``root``, following ``extends``.

    Values declared closer to the leaf win. ``baseUrl`` and every ``paths``
    target are resolved against the directory of the config that DECLARES them,
    which is the rule TypeScript itself applies and the one upstream got wrong
    twice (GI-2340).
    """
    amap = _AliasMap()
    start = None
    for name in ("tsconfig.json", "jsconfig.json"):
        cand = os.path.join(root, name)
        if os.path.isfile(cand):
            start = cand
            break
    if start is None:
        return amap

    # Walk leaf → base, collecting each config's own contribution.
    chain: list[tuple[str, dict]] = []
    seen: set[str] = set()
    current: Optional[str] = start
    stamps: list[tuple[str, int]] = []
    while current and current not in seen and len(chain) < 16:
        seen.add(current)
        try:
            stamps.append((current, os.stat(current).st_mtime_ns))
        except OSError:
            stamps.append((current, -1))
        data = _read_config(current)
        if data is None:
            break
        chain.append((current, data))
        ext = data.get("extends")
        current = _resolve_extends(ext, os.path.dirname(current)) if isinstance(ext, str) else None

    amap.stamps = tuple(stamps)

    # Apply base → leaf so a leaf declaration overwrites its base.
    for config_path, data in reversed(chain):
        config_dir = os.path.dirname(config_path)
        opts = data.get("compilerOptions")
        # ``"compilerOptions": null`` is valid JSON and crashed upstream's
        # loader on attribute access.
        if not isinstance(opts, dict):
            continue
        base_url = opts.get("baseUrl")
        if isinstance(base_url, str) and base_url:
            amap.base_url = os.path.normpath(
                os.path.join(config_dir, _expand_config_dir(base_url, config_dir))
            )
        paths = opts.get("paths")
        if isinstance(paths, dict):
            anchor = amap.base_url or config_dir
            for pattern, targets in paths.items():
                if not isinstance(pattern, str) or not isinstance(targets, list):
                    continue
                resolved: list[str] = []
                for target in targets:
                    if not isinstance(target, str):
                        continue
                    expanded = _expand_config_dir(target, config_dir)
                    base = config_dir if expanded != target else anchor
                    resolved.append(os.path.normpath(os.path.join(base, expanded)))
                if resolved:
                    amap.paths[pattern] = resolved
    return amap


def _expand_config_dir(value: str, config_dir: str) -> str:
    """Expand TS 5.5 ``${configDir}`` against the DECLARING config's directory."""
    if "${configDir}" not in value:
        return value
    return value.replace("${configDir}", config_dir.rstrip(os.sep) or ".")


# ── Resolver ──────────────────────────────────────────────────────────────────

class ModuleResolver:
    """Resolve import strings to scanned files. One instance per graph build."""

    def __init__(
        self,
        known_files: Iterable[str],
        project_roots: Optional[dict[str, str]] = None,
    ) -> None:
        self._files: set[str] = set()
        self._by_basename: dict[str, list[str]] = {}
        self._by_basename_cf: dict[str, list[str]] = {}
        for raw in known_files:
            if not raw:
                continue
            path = os.path.normpath(raw).replace("\\", "/")
            self._files.add(path)
            base = path.rsplit("/", 1)[-1]
            self._by_basename.setdefault(base, []).append(path)
            self._by_basename_cf.setdefault(base.casefold(), []).append(path)
        for bucket in (self._by_basename, self._by_basename_cf):
            for key, paths in bucket.items():
                bucket[key] = sorted(dict.fromkeys(paths))
        self._roots = dict(project_roots or {})
        self._alias_cache: dict[str, _AliasMap] = {}

    # -- public API ------------------------------------------------------------

    def resolve(
        self,
        raw_import: str,
        importer: str,
        project_root: Optional[str] = None,
    ) -> tuple[list[str], Optional[str]]:
        """Resolve ``raw_import`` seen in ``importer``.

        Returns ``(files, symbol)``: the scanned files the import names (empty
        when it names nothing we scanned — an npm package, a stdlib module, a
        generated file) and, when the import string carried a trailing symbol
        that is *not* part of the path, that symbol's name.
        """
        text = (raw_import or "").strip().strip("'\"")
        if not text or text.startswith("node:"):
            return [], None
        text = text.replace("\\", "/")
        ext = Path(importer).suffix.lower() if importer else ""
        fam = lang_family(ext)

        if text.startswith("./") or text.startswith("../") or text in (".", ".."):
            if not importer:
                return [], None
            base = os.path.dirname(importer)
            hit = self._try_path(os.path.join(base, text), fam)
            return (hit, None) if hit else ([], None)

        if fam == "web":
            hit = self._resolve_web_alias(text, importer, project_root)
            if hit:
                return hit, None

        return self._tail_match(text, fam)

    # -- internals -------------------------------------------------------------

    def _alias_map(self, root: str) -> _AliasMap:
        amap = self._alias_cache.get(root)
        if amap is None or amap.stale():
            amap = _load_alias_map(root)
            self._alias_cache[root] = amap
        return amap

    def _resolve_web_alias(
        self, text: str, importer: str, project_root: Optional[str]
    ) -> list[str]:
        root = project_root or self._root_for(importer)
        if not root:
            return []
        amap = self._alias_map(root)

        for pattern, targets in sorted(amap.paths.items(), key=_alias_specificity):
            tail = _alias_match(pattern, text)
            if tail is None:
                continue
            for target in targets:
                cand = target.replace("*", tail) if "*" in target else target
                hit = self._try_path(cand, "web")
                if hit:
                    return hit

        if amap.base_url:
            hit = self._try_path(os.path.join(amap.base_url, text), "web")
            if hit:
                return hit

        # No tsconfig (or no matching alias): fall back to the near-universal
        # "@/" → src convention so a project without a config still resolves.
        if text.startswith("@/"):
            rest = text[2:]
            for base in (os.path.join(root, "src"), root, os.path.join(root, "app")):
                hit = self._try_path(os.path.join(base, rest), "web")
                if hit:
                    return hit
        return []

    def _root_for(self, importer: str) -> Optional[str]:
        best: Optional[str] = None
        norm = os.path.normpath(importer).replace("\\", "/")
        for path in self._roots.values():
            candidate = os.path.normpath(path).replace("\\", "/")
            if norm.startswith(candidate.rstrip("/") + "/") and (
                best is None or len(candidate) > len(best)
            ):
                best = candidate
        return best

    def _try_path(self, candidate: str, fam: Optional[str]) -> list[str]:
        """Return the scanned file ``candidate`` names, trying extensions."""
        norm = os.path.normpath(candidate).replace("\\", "/")
        if norm in self._files:
            return [norm]
        exts = _FAMILY_EXTS.get(fam or "", _ALL_EXTS)
        for ext in exts:
            if norm + ext in self._files:
                return [norm + ext]
        for index in _FAMILY_INDEX.get(fam or "", ()):
            if f"{norm}/{index}" in self._files:
                return [f"{norm}/{index}"]
        return []

    def _tail_match(
        self, text: str, fam: Optional[str]
    ) -> tuple[list[str], Optional[str]]:
        """Match a package/module path against the corpus by path suffix.

        ``com.ex.repo.UserRepository`` and ``pkg/sub/mod`` both reduce to a path
        suffix; a scanned file whose path ends with that suffix (plus a language
        extension) is the module the import names. When the full suffix matches
        nothing, the last segment is retried as a *symbol* inside its parent
        module — the shape Python's ``from pkg.mod import helper`` produces.
        """
        if fam in _DOTTED_FAMILIES and "/" not in text:
            parts = [p for p in text.split(".") if p]
        else:
            parts = [p for p in text.replace(".", "/").split("/") if p]
        if not parts:
            return [], None

        hit = self._suffix_lookup(parts, fam)
        if hit:
            return hit, None
        if len(parts) >= 2:
            hit = self._suffix_lookup(parts[:-1], fam)
            if hit:
                return hit, parts[-1]
        return [], None

    def _suffix_lookup(self, parts: list[str], fam: Optional[str]) -> list[str]:
        # A single bare segment is far too weak a signal to bind on: "utils"
        # would match every utils.ts in the corpus.
        if len(parts) < 2:
            return []
        suffix = "/".join(parts)
        last = parts[-1]
        exts = _FAMILY_EXTS.get(fam or "", _ALL_EXTS)
        indexes = _FAMILY_INDEX.get(fam or "", ())

        # (basename to look up, characters to trim off the path to recover the
        # module path it stands for). ``pkg/sub/__init__.py`` stands for the
        # module ``pkg/sub``, so the whole "/__init__.py" tail comes off.
        forms: list[tuple[str, int]] = [(last + ext, len(ext)) for ext in exts]
        forms += [(index, len(index) + 1) for index in indexes]

        # Exact match first; a case-insensitive pass then covers conventions
        # that re-case directory names (PSR-4 ``App\Models`` ↔ ``app/Models``).
        for fold in (False, True):
            bucket = self._by_basename_cf if fold else self._by_basename
            want = suffix.casefold() if fold else suffix
            matches: list[str] = []
            for basename, trim in forms:
                key = basename.casefold() if fold else basename
                for path in bucket.get(key, ()):
                    module = path[: len(path) - trim]
                    compare = module.casefold() if fold else module
                    if compare == want or compare.endswith("/" + want):
                        matches.append(path)
            if matches:
                return sorted(dict.fromkeys(matches))
        return []


def _alias_match(pattern: str, text: str) -> Optional[str]:
    """Return the ``*`` capture when ``pattern`` matches ``text``, else None."""
    if "*" not in pattern:
        return "" if pattern == text else None
    head, _, tail = pattern.partition("*")
    if not text.startswith(head) or not text.endswith(tail):
        return None
    if len(text) < len(head) + len(tail):
        return None
    return text[len(head): len(text) - len(tail)] if tail else text[len(head):]


def _alias_specificity(item: tuple[str, list[str]]) -> tuple[int, int, str]:
    """Longest literal prefix first — TypeScript prefers the most specific alias."""
    pattern = item[0]
    return (0 if "*" not in pattern else 1, -len(pattern.split("*")[0]), pattern)
