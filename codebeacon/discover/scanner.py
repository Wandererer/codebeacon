"""Recursive file collector with ignore patterns and hash caching."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from codebeacon.discover.ignore import IgnoreMatcher, read_ignore_text

if TYPE_CHECKING:  # import only for annotations — keeps this module import-light
    from codebeacon.diagnostics import IgnoredReport

# Directory names that are *always* build noise, tooling state or a dedicated
# credential store. A bare name is enough: no repo puts hand-written source in
# a directory called ``node_modules`` or ``.gnupg``.
UNCONDITIONAL_IGNORE_DIRS: set[str] = {
    "node_modules",
    ".git",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "dist",
    ".output",
    ".turbo",
    ".vercel",
    ".codebeacon",
    ".codesight",
    ".ai-codex",
    ".cache",
    ".parcel-cache",
    ".gradle",
    ".idea",
    ".vscode",
    ".DS_Store",
    ".bundle",          # Ruby bundler
    ".terraform",
    # A directory literally named ``worktrees`` is git's own bookkeeping folder
    # (``.git/worktrees``) when it appears at a repo root. Linked worktrees that
    # users actually check out are named freely, and are caught structurally by
    # :func:`_is_linked_worktree` instead.
    "worktrees",
    # Sensitive credential / secret directories — always skip even when they
    # don't start with `.` (so the hidden-dir rule below doesn't cover them).
    # Mirrors graphify's _SENSITIVE_DIRS hardening (graphify 0.8.12). These stay
    # unconditional deliberately: guessing wrong here leaks credentials into a
    # committed index, so the prune is reported rather than relaxed.
    "secrets",
    "credentials",
    ".ssh",
    ".aws",
    ".gcloud",
    ".gnupg",
}

# Directory names that *usually* mean build output but are genuine source
# directories often enough that a bare-name match is a data-loss bug: a UVM
# testbench ``env/``, a Python package named ``coverage``, a Laravel ``public/``
# front controller, a Node CLI's ``bin/``, a project's own vendored ``vendor/``.
# These are pruned only when the directory's own contents corroborate the guess
# — see :func:`_looks_like_build_output`. Each value lists names whose presence
# inside the directory confirms its conventional meaning.
CORROBORATED_IGNORE_DIRS: dict[str, tuple[str, ...]] = {
    "env":      ("pyvenv.cfg", "conda-meta", "bin/activate", "Scripts/activate",
                 "Scripts/activate.bat", "lib/python*"),
    "coverage": (".coverage", "coverage.xml", "coverage-final.json", "lcov.info",
                 "htmlcov", "index.html"),
    "target":   ("CACHEDIR.TAG", ".rustc_info.json", "debug", "release", "classes",
                 "maven-status", "surefire-reports", "generated-sources"),
    "build":    ("CMakeCache.txt", "CMakeFiles", "classes", "libs", "intermediates",
                 "reports", "generated", "outputs"),
    "out":      ("_next", "_astro", "production"),
    "bin":      ("Debug", "Release"),
    "obj":      ("Debug", "Release", "project.assets.json", "project.nuget.cache"),
    "vendor":   ("autoload.php", "composer", "modules.txt", "bundle"),
    "public":   ("_next", "_astro", "hot", "storage"),
    "tmp":      (),
    "temp":     (),
}

# Union of both sets: "names the walk may prune". Kept under the historical name
# because callers (and the watcher) reason about it as one vocabulary.
IGNORE_DIRS: set[str] = UNCONDITIONAL_IGNORE_DIRS | set(CORROBORATED_IGNORE_DIRS)

# Our own output directories. Still pruned (that is the loop guard that stops a
# scan indexing its own artefacts), but never *recorded* in the ignored report:
# their presence is caused by the previous run of the very tool writing the
# report, so listing them makes the artefact describe its own footprint. It also
# makes the report non-idempotent — the first scan writes ignored.json, which
# creates .codebeacon/, which the second scan then has something new to report —
# and that spurious change defeats the point of writing only on a real diff.
_SELF_OUTPUT_DIRS: frozenset[str] = frozenset({".codebeacon", ".codesight", ".ai-codex"})

# Compiled or packaged artefacts. One of these inside an ambiguously-named
# directory is decisive: hand-written source trees do not ship ``.class`` or
# ``.rlib`` files, so this catches ``target/debug`` and ``build/classes`` even
# when the per-name markers above miss a layout.
_BUILD_ARTIFACT_SUFFIXES: set[str] = {
    ".class", ".o", ".obj", ".pyc", ".pyo", ".jar", ".war", ".ear", ".a",
    ".so", ".dylib", ".dll", ".pdb", ".rlib", ".rmeta", ".nupkg", ".whl",
    ".wasm", ".map",
}

# A bundler's output filename: minified, or carrying a content hash. Files like
# ``app-4f2a1b9c.js`` share an extension with source but are never source, so
# they must not count as "this directory holds real code" — without this, a
# Next.js ``out/`` or a Laravel ``public/build`` would look like a source tree.
_HASHED_STEM_RE = re.compile(r"[.\-_][0-9a-f]{8,}$", re.IGNORECASE)


def _looks_generated(name: str) -> bool:
    """True if ``name`` is a bundler artefact rather than authored source."""
    lower = name.lower()
    if ".min." in lower or lower.endswith((".bundle.js", ".chunk.js")):
        return True
    stem = name.rsplit(".", 1)[0]
    return _HASHED_STEM_RE.search(stem) is not None


def _has_marker(path: Path, marker: str) -> bool:
    """True if ``marker`` (optionally a glob) exists directly under ``path``."""
    try:
        if "*" in marker:
            return next(path.glob(marker), None) is not None
        return (path / marker).exists()
    except OSError:
        return False


# Probe budget for :func:`_looks_like_build_output`. Bounded so an ambiguous
# name sitting on top of a 50k-file output tree costs a fixed handful of
# syscalls rather than a full traversal.
_PROBE_MAX_ENTRIES = 500
_PROBE_MAX_DEPTH = 3


def _looks_like_build_output(path: Path, name: str) -> bool:
    """Decide whether an ambiguously-named directory really is build output.

    Three independent signals, cheapest first:

    1. a name-specific marker (``pyvenv.cfg`` in ``env/``, ``debug/`` in a Cargo
       ``target/``, ``autoload.php`` in a composer ``vendor/``);
    2. a compiled artefact anywhere in the top few levels;
    3. no authored source at all in those levels — pruning a directory that
       holds nothing indexable costs nothing, and this is what keeps Rails'
       ``tmp/`` and a static ``public/`` out of the corpus without needing a
       marker for every framework's layout.

    Otherwise the directory is kept: a name collision alone must never drop real
    source. The probe is bounded, and exhausting the budget without finding
    source counts as evidence of output — a directory with 500 non-source
    entries in its first three levels is not a source tree.
    """
    for marker in CORROBORATED_IGNORE_DIRS.get(name, ()):
        if _has_marker(path, marker):
            return True

    found_source = False
    budget = _PROBE_MAX_ENTRIES
    stack: list[tuple[Path, int]] = [(path, 0)]
    while stack and budget > 0:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    budget -= 1
                    if budget <= 0:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth + 1 < _PROBE_MAX_DEPTH:
                                stack.append((Path(entry.path), depth + 1))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    suffix = os.path.splitext(entry.name)[1].lower()
                    if suffix in _BUILD_ARTIFACT_SUFFIXES:
                        return True
                    if suffix in CODE_EXTENSIONS and not _looks_generated(entry.name):
                        found_source = True
        except OSError:
            continue

    return not found_source


def _is_linked_worktree(path: Path) -> bool:
    """True if ``path`` is a linked git worktree checked out inside the repo.

    ``git worktree add wt-feat`` inside the project root leaves a second copy of
    every tracked file, doubling node counts on every scan. Git itself does not
    mark it ignored — ``git status`` merely lists it as untracked — so pattern
    parity cannot catch this; the reliable signal is structural: a linked
    worktree's ``.git`` is a *file* pointing into ``<repo>/.git/worktrees/<name>``.
    """
    dot_git = path / ".git"
    try:
        if not dot_git.is_file():
            return False
        with open(dot_git, "rb") as fh:
            head = fh.read(4096).decode("utf-8", errors="replace")
    except OSError:
        return False
    first = head.splitlines()[0].strip() if head else ""
    if not first.startswith("gitdir:"):
        return False
    target = first[len("gitdir:"):].strip().replace("\\", "/")
    return "/.git/worktrees/" in target or target.endswith("/.git/worktrees")

# Default gitignore-style patterns applied at the *lowest* precedence in
# ``collect_files`` (before ``.gitignore`` / ``.codebeaconignore``), so a user's
# negation — e.g. ``!tests/fixtures/`` — re-includes them. Unlike ``IGNORE_DIRS``
# these are path patterns, not basenames: test-fixture trees are synthetic inputs
# for a project's *own* test suite, not product surface, and indexing them injects
# fake routes/services (codebeacon's self-scan reported tests/fixtures/fastapi/main.py
# as 5 "routes"). The ``**/`` prefix matches at any depth; matching is relative to
# the scan root, so pointing the scan *at* a fixture dir still collects it.
DEFAULT_IGNORE_PATTERNS: list[str] = [
    "**/tests/fixtures/",
    "**/test/fixtures/",
    "**/__fixtures__/",
]

# File basenames that should never be indexed even if their extension matches
# CODE_EXTENSIONS — they almost certainly hold credentials. Underscore-prefixed
# variants (api_token.txt, oauth_token.json) are also caught by the regex in
# ``_is_sensitive_filename`` so we don't need to enumerate every spelling.
#
# The entries whose extension is not itself in CODE_EXTENSIONS (.json, .yaml and
# the extension-less keys) are unreachable from ``_walk`` today, because the
# extension screen rejects those files one step earlier. They stay because
# ``_is_sensitive_filename`` is consulted from other call sites (the watcher,
# the symlink gate) and because CODE_EXTENSIONS plausibly grows to cover .json
# manifests — at which point this set is the only thing standing between a
# service-account key and the index. Deliberately not reordered ahead of the
# extension screen: doing so would warn about every credentials.json in every
# repo, drowning the one signal that matters (a *source module* being dropped).
_SENSITIVE_BASENAMES: set[str] = {
    "credentials",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}

# Substring (with word-boundary or underscore boundary) match for sensitive
# tokens in file basenames: ``api_token.txt``, ``OAuth_Token.json``,
# ``slack-secret.yml``, ``private_key.pem`` — anything that mentions a
# credential keyword should be skipped even if the extension is otherwise a
# code one (e.g. ``.json`` for Cargo manifests). The pattern is intentionally
# narrow: it must be at the start of the basename or follow ``[-_.]``.
#
# The trailing boundary ``(?=\.[^.]+$|$)`` requires the credential phrase to be
# essentially the whole stem — followed only by the file extension or the end of
# the name. This flags real secret dumps (``api_key.txt``, ``client-secret.json``,
# ``private_key.pem``) while letting through source modules merely *named after*
# the concept (``api_key_manager.go``, ``access_token_service.py``,
# ``client_secret_validator.ts``), which a looser ``(?=[-_.]|$)`` boundary
# silently dropped because the ``_`` in ``_manager`` satisfied it.
_SENSITIVE_NAME_RE = re.compile(
    r"(?:^|[-_.])(?:api[-_]?key|api[-_]?token|oauth[-_]?token|"
    r"access[-_]?token|refresh[-_]?token|secret[-_]?key|"
    r"private[-_]?key|client[-_]?secret)"
    r"(?=\.[^.]+$|$)",
    re.IGNORECASE,
)


def _is_sensitive_filename(name: str) -> bool:
    """Return True if ``name`` looks like a credential file.

    Used at file-collection time to skip secrets that happen to share an
    extension with code (e.g. ``service-account.json``, ``api_token.txt``).
    """
    lower = name.lower()
    if lower in _SENSITIVE_BASENAMES:
        return True
    return _SENSITIVE_NAME_RE.search(lower) is not None

CODE_EXTENSIONS: set[str] = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py",
    ".go",
    ".vue", ".svelte",
    # .rake task files are plain Ruby — the ruby grammar parses them verbatim,
    # and rails.scm is selected by framework rather than by extension, so this
    # registration plus EXT_TO_GRAMMAR is the whole of .rake support. The
    # extensionless `Rakefile` cannot be expressed by an extension-keyed set
    # and stays out of scope.
    ".rb", ".rake",
    ".java", ".kt",
    ".rs",
    ".php",
    ".swift",
    ".cs", ".razor", ".cshtml",
    ".sln", ".csproj", ".fsproj", ".vbproj",
    ".ex", ".exs",
    ".dart",
    ".scala",
    ".clj",
    ".hs",
    ".ets",
    ".graphql", ".gql",
    ".proto",
    ".sql",
}


def read_ignore_file(
    root: str | Path,
    filename: str = ".codebeaconignore",
    *,
    gitignore_fallback: bool = True,
) -> list[str]:
    """Return the raw lines of the project's ignore rules (no filtering).

    Reads ``.gitignore`` first (when ``gitignore_fallback``) and appends
    ``.codebeaconignore`` last, so the two are **merged** rather than one
    replacing the other. Because :class:`~codebeacon.discover.ignore.IgnoreMatcher`
    uses gitignore last-match-wins semantics, ``.codebeaconignore`` patterns win
    on conflict (including ``!`` negations), yet adding a ``.codebeaconignore``
    can only ever exclude *more* — it never silently drops the repo's existing
    ``.gitignore`` exclusions.

    This matters for privacy: a file excluded only by ``.gitignore`` (e.g. a
    neutrally-named ``prod-dump.sql`` or ``customer-data.*``) must keep being
    skipped even after a ``.codebeaconignore`` is added, or it would get indexed
    into the committed ``.codebeacon/`` artifacts (graphify #1363).

    Pattern parsing is delegated to :class:`codebeacon.discover.ignore.IgnoreMatcher`,
    which implements gitignore semantics (negation, dir-only, anchored, trailing
    whitespace handling).
    """
    root_path = Path(root)
    lines: list[str] = []

    # Decoding is delegated to ``read_ignore_text``, which strips a UTF-8 BOM,
    # recovers UTF-16 and legacy single-byte files, and never raises — a rule
    # lost to a decoding accident means excluded files get indexed into the
    # committed ``.codebeacon/`` artefacts.

    # $GIT_DIR/info/exclude first: git's own precedence puts it below .gitignore.
    if gitignore_fallback:
        exclude = _git_info_exclude(root_path)
        if exclude is not None:
            text = read_ignore_text(exclude)
            if text is not None:
                lines.extend(text.splitlines())

        # .gitignore next (still lower precedence than .codebeaconignore).
        text = read_ignore_text(root_path / ".gitignore")
        if text is not None:
            lines.extend(text.splitlines())

    # .codebeaconignore last, so its patterns win on conflict and only ever add.
    text = read_ignore_text(root_path / filename)
    if text is not None:
        lines.extend(text.splitlines())

    return lines


def _git_info_exclude(root: Path) -> Path | None:
    """Resolve the git metadata exclude file for ``root``, or None if absent.

    Handles both shapes git uses for ``.git``: a plain directory, and a *file*
    holding ``gitdir: <path>`` (linked worktrees and submodules). For a linked
    worktree the excludes live in the shared common dir, which the ``commondir``
    file points at, so follow that when present.

    Resolution is deliberately anchored on ``root/.git`` rather than the
    ``GIT_DIR`` environment variable. ``info/exclude`` patterns are relative to
    the repository's working tree, so they are only meaningful when the scan
    root *is* that working tree — and ``GIT_DIR`` is set for us in exactly the
    case where it would not be: codebeacon's own git hooks, which git runs with
    ``GIT_DIR`` pointing at the enclosing repo while the scan may be aimed at a
    subproject. Honouring it there would silently reinterpret every pattern
    against the wrong root.
    """
    git_dir: Path | None = None
    dot_git = root / ".git"
    try:
        if dot_git.is_dir():
            git_dir = dot_git
        elif dot_git.is_file():
            first = dot_git.read_text(encoding="utf-8", errors="replace").splitlines()
            if first and first[0].strip().startswith("gitdir:"):
                pointed = Path(first[0].strip()[len("gitdir:"):].strip())
                git_dir = pointed if pointed.is_absolute() else (root / pointed)
    except OSError:
        return None

    if git_dir is None:
        return None

    try:
        common = git_dir / "commondir"
        if common.is_file():
            rel = common.read_text(encoding="utf-8", errors="replace").strip()
            if rel:
                pointed = Path(rel)
                git_dir = pointed if pointed.is_absolute() else (git_dir / pointed)
    except OSError:
        pass

    return git_dir / "info" / "exclude"


def _dir_prune_reason(name: str, path: Path | None = None) -> str | None:
    """Why the walk would skip a directory called ``name``, or None to descend.

    ``path`` is the directory itself. It is optional because the watcher reasons
    about paths it has not necessarily seen on disk; without it the ambiguous
    names fall back to the historical bare-name prune, since guessing "keep" for
    every ``build/`` would wake a resync on every compile.
    """
    if name in UNCONDITIONAL_IGNORE_DIRS:
        return "ignore_dir"
    if name.startswith("."):
        # Hidden dirs — skip most except known config dirs
        return "hidden_dir"
    if path is not None and _is_linked_worktree(path):
        return "git_worktree"
    if name in CORROBORATED_IGNORE_DIRS:
        if path is None:
            return "ignore_dir"
        return "build_output" if _looks_like_build_output(path, name) else None
    return None


def _should_ignore_dir(name: str, path: Path | None = None) -> bool:
    return _dir_prune_reason(name, path) is not None


def _dir_walk_decision(
    name: str, rel: str, matcher: IgnoreMatcher, path: Path | None = None
) -> str | None:
    """Prune reason for the directory ``name`` at ``rel``, or None to descend.

    Same decision as :func:`_dir_would_be_walked`, but it names the cause so the
    ``ignored`` diagnostic can say *why* a subtree is missing from the corpus.
    """
    if matcher.is_explicitly_included(rel, is_dir=True):
        return None
    reason = _dir_prune_reason(name, path)
    if reason is not None:
        return reason
    if matcher.is_ignored(rel, is_dir=True) and not matcher.could_unignore_under(rel):
        return "pattern"
    return None


def _dir_would_be_walked(
    name: str, rel: str, matcher: IgnoreMatcher, path: Path | None = None
) -> bool:
    """Whether :func:`_walk` would descend into the directory ``name`` at ``rel``.

    Single source of truth for the dir-prune decision, shared by the real walk
    and the symlink-warning gate so the two can never drift.

    ``!pattern`` in ``.codebeaconignore`` can opt a directory back in that the
    default skips (hidden dirs, IGNORE_DIRS) would otherwise drop. Only an
    explicit *self* match counts — a parent-level negation does not auto
    re-include nested dot-folders (mirrors codesight #42 / 0bedd0d).

    An ignored directory is pruned only when no negation rule could re-include a
    file beneath it. A per-directory ``could_unignore_under`` check (not a
    global "any negation → descend everywhere" flag) so an unrelated ``!foo``
    rule doesn't force descent into every excluded subtree (graphify #1274).
    Unanchored negations are treated conservatively (descend), so no rescuable
    file is lost.
    """
    return _dir_walk_decision(name, rel, matcher, path) is None


NESTED_IGNORE_FILES: tuple[str, ...] = (".gitignore", ".codebeaconignore")

# Directories the walk could not descend into, per scan root. The pipeline's
# shrink guard needs this as a zero-argument query (it runs long after the
# collection loop and has no report object to hand), so the last walk's result
# is kept here rather than only in an optional report.
#
# Keyed by root so one pipeline run covering several projects unions their
# results, while a *repeat* of a root — the next iteration of ``codebeacon
# watch`` — starts a fresh generation instead of keeping a resolved permission
# problem armed forever.
_UNREADABLE_BY_ROOT: dict[str, list[str]] = {}
_UNREADABLE_LIMIT = 200


def unreadable_dirs() -> list[str]:
    """Directories the most recent scan generation could not read.

    Contract consumed by :func:`codebeacon.pipeline._unreadable_subtrees`: an
    unreadable subtree means the corpus is incomplete through no decision of the
    user's, so the shrink guard must stay armed rather than read the missing
    files as deliberate exclusions.
    """
    out: list[str] = []
    for paths in _UNREADABLE_BY_ROOT.values():
        out.extend(paths)
    return out[:_UNREADABLE_LIMIT]


def reset_unreadable_dirs() -> None:
    """Forget recorded walk errors (start a new scan generation explicitly)."""
    _UNREADABLE_BY_ROOT.clear()


def _record_unreadable(root: Path, dirs: list[str]) -> None:
    key = str(root)
    if key in _UNREADABLE_BY_ROOT:
        # Same root twice means a previous generation ended.
        _UNREADABLE_BY_ROOT.clear()
    _UNREADABLE_BY_ROOT[key] = [str(root / d) if d != "." else str(root) for d in dirs]


def collect_files(
    root: str | Path,
    max_depth: int = 15,
    extra_ignore: list[str] | None = None,
    *,
    report: "IgnoredReport | None" = None,
) -> list[str]:
    """Recursively collect code files under root.

    Returns absolute paths sorted by directory then filename. Honours
    ``.codebeaconignore`` using gitignore semantics — negation (``!pattern``)
    re-includes paths that would otherwise be skipped. Ignore files found in
    subdirectories apply to their own subtree, as in git.

    Pass ``report`` (a :class:`codebeacon.diagnostics.IgnoredReport`) to record
    *why* each pruned subtree, dropped file and unreadable directory is missing
    from the result. It is optional and costs nothing when omitted; an
    over-broad rule is otherwise indistinguishable from a clean scan.
    """
    root = Path(root).resolve()
    # Defaults first (lowest precedence): a user's .gitignore/.codebeaconignore —
    # read next — wins on conflict under last-match-wins, so ``!tests/fixtures/``
    # re-includes a fixture tree the defaults would otherwise prune. ``--exclude``
    # goes in the tail, which always evaluates last, so no nested ignore file
    # discovered mid-walk can override an explicit command-line exclusion.
    lines = list(DEFAULT_IGNORE_PATTERNS)
    lines.extend(read_ignore_file(root))
    matcher = IgnoreMatcher(lines, tail_lines=list(extra_ignore or []))

    result: list[str] = []
    skipped_symlinks: list[str] = []
    dropped_sensitive: list[str] = []
    unreadable: list[str] = []
    _walk(
        root, root, 0, max_depth, matcher, result,
        skipped_symlinks, dropped_sensitive, unreadable, report,
    )
    if skipped_symlinks:
        # We deliberately do NOT follow symlinks (loop / double-counting / escape
        # risk), but silently dropping symlinked source is surprising — surface
        # it once, grouped, so shared code isn't lost without a trace.
        joined = ", ".join(sorted(skipped_symlinks))
        print(
            f"    Warning: skipped {len(skipped_symlinks)} symlink(s), not "
            f"followed: {joined}",
            file=sys.stderr,
        )
    if dropped_sensitive:
        # A credential-shaped basename is dropped on purpose, but the drop must
        # be auditable: without this a source module called ``api_key.py``
        # vanishes from the index with no trace at all.
        joined = ", ".join(sorted(dropped_sensitive))
        print(
            f"    Warning: excluded {len(dropped_sensitive)} credential-looking "
            f"file(s): {joined}",
            file=sys.stderr,
        )
    _record_unreadable(root, unreadable)
    if unreadable:
        # An unreadable subtree makes the corpus silently incomplete, which
        # downstream guards must be able to tell apart from a genuine deletion.
        joined = ", ".join(sorted(unreadable))
        print(
            f"    Warning: permission denied, {len(unreadable)} directory tree(s) "
            f"not scanned (corpus is incomplete): {joined}",
            file=sys.stderr,
        )
    return sorted(result)


def _walk(
    base: Path,
    current: Path,
    depth: int,
    max_depth: int,
    matcher: IgnoreMatcher,
    result: list[str],
    skipped_symlinks: list[str],
    dropped_sensitive: list[str],
    unreadable: list[str],
    report: "IgnoredReport | None" = None,
) -> None:
    rel_dir = current.relative_to(base).as_posix() if current != base else ""
    if depth > max_depth:
        if report is not None:
            report.add_dir(rel_dir, "depth_limit")
        return
    try:
        entries = sorted(current.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        unreadable.append(rel_dir or ".")
        if report is not None:
            report.add_permission_denied(rel_dir or ".")
        return

    # An ignore file in this directory scopes to this subtree, exactly like git.
    # The names are already in ``entries``, so discovering one costs no extra
    # syscall, and the child matcher lives only for this branch of the recursion
    # — sibling subtrees never inherit it.
    if rel_dir:
        present = {e.name for e in entries}
        nested_lines: list[str] = []
        for fname in NESTED_IGNORE_FILES:
            if fname in present:
                text = read_ignore_text(current / fname)
                if text is not None:
                    nested_lines.extend(text.splitlines())
        if nested_lines:
            matcher = matcher.nested(nested_lines, rel_dir)

    for entry in entries:
        rel = entry.relative_to(base).as_posix()
        if entry.is_symlink():
            # We deliberately do NOT follow symlinks, but a link that carries
            # code the real walk would otherwise collect is worth surfacing.
            # Only record it when the same IGNORE_DIRS / hidden-dir / matcher
            # checks the walk applies would NOT have pruned it anyway — else a
            # symlinked node_modules / dist / .venv (or an ignore-matched path)
            # is wrongly reported as lost "shared code" (BH-D3).
            try:
                carries_code = False
                if entry.is_dir():
                    carries_code = _dir_would_be_walked(entry.name, rel, matcher, entry)
                elif entry.is_file() and entry.suffix.lower() in CODE_EXTENSIONS:
                    carries_code = not _is_sensitive_filename(
                        entry.name
                    ) and not matcher.is_ignored(rel, is_dir=False)
                if carries_code:
                    skipped_symlinks.append(rel)
                    if report is not None:
                        report.add_file(rel, "symlink")
            except OSError:
                pass  # broken/unstattable symlink — nothing useful to report
            continue
        if entry.is_dir():
            reason = _dir_walk_decision(entry.name, rel, matcher, entry)
            if reason is not None:
                # Record the directory, not its contents: one entry per pruned
                # subtree is what keeps the report bounded no matter how many
                # files sit beneath it.
                if report is not None and entry.name not in _SELF_OUTPUT_DIRS:
                    report.add_dir(rel, reason)
                continue
            _walk(
                base, entry, depth + 1, max_depth, matcher, result,
                skipped_symlinks, dropped_sensitive, unreadable, report,
            )
        elif entry.is_file():
            # Normalise case so uppercase/mixed-case extensions (App.PY, Index.JS,
            # Page.TSX) — valid, importable source on case-insensitive filesystems
            # — aren't silently dropped. Matches extract/semantic.py, common/
            # filters.py and semantic_pipeline.py, which already lowercase suffixes.
            if entry.suffix.lower() not in CODE_EXTENSIONS:
                continue
            if _is_sensitive_filename(entry.name):
                dropped_sensitive.append(rel)
                if report is not None:
                    report.add_file(rel, "sensitive_filename")
                continue
            if matcher.is_ignored(rel, is_dir=False):
                if report is not None:
                    report.add_file(rel, "pattern")
                continue
            result.append(str(entry))


def hash_file(path: str | Path) -> str:
    """Return SHA-256 hex digest (first 12 chars) of file content."""
    try:
        content = Path(path).read_bytes()
        return hashlib.sha256(content).hexdigest()[:12]
    except OSError:
        return ""


def load_hash_cache(cache_dir: str | Path) -> dict:
    """Load the file hash cache from cache_dir/cache.json."""
    cache_path = Path(cache_dir) / "cache.json"
    try:
        return json.loads(cache_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"version": 1, "hashes": {}}


def save_hash_cache(cache_dir: str | Path, cache: dict) -> None:
    """Persist the hash cache; non-fatal if it fails."""
    try:
        cache_path = Path(cache_dir) / "cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def get_changed_files(files: list[str], cache: dict) -> tuple[list[str], dict]:
    """Return files whose hash differs from cache, and the updated hash map."""
    hashes = cache.get("hashes", {})
    changed: list[str] = []
    new_hashes: dict[str, str] = dict(hashes)

    for f in files:
        h = hash_file(f)
        if hashes.get(f) != h:
            changed.append(f)
            new_hashes[f] = h

    # Remove entries for files that no longer exist
    existing = set(files)
    new_hashes = {k: v for k, v in new_hashes.items() if k in existing}

    return changed, {"version": 1, "hashes": new_hashes}
