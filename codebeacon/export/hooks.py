"""Git hook + merge-driver installation for ``codebeacon``.

``codebeacon hook install`` does three things in the current repository:

1. Drops a ``post-commit`` hook that detaches a background incremental rebuild
   (``codebeacon scan . --update``). The hook's directory comes from git
   (``core.hooksPath``, else ``git rev-parse --git-path hooks``) so Husky-managed
   repos don't get a parallel set of hooks and worktree/submodule checkouts —
   where ``.git`` is a FILE — resolve to the shared hooks dir. Rebuild output is
   redirected to ``~/.cache/codebeacon-rebuild.log``.
2. Registers a ``codebeacon`` git merge driver in the local git config that
   calls ``codebeacon merge-driver`` (see :mod:`codebeacon.export.merge`).
3. Adds ``*beacon.json merge=codebeacon`` to ``.gitattributes`` so git uses the
   driver for ``beacon.json`` (and per-project ``beacon.json`` files in
   deep-dive mode).

The hook comes first on purpose: it is the only step that can fail on a path
git owns, and failing after the config edits left the repo half-configured.

Each step is idempotent — running ``codebeacon hook install`` twice is safe.

The installed hook honours two escapes: ``CODEBEACON_SKIP_HOOK=1`` suppresses
the rebuild for a scripted or rebase-heavy commit run, and a commit made inside
a linked worktree is skipped (linked worktrees share the common dir's hooks, so
the rebuild would scan a different checkout than the one that was committed).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from codebeacon.common.textio import read_text_safe


_POST_COMMIT_HOOK_TEMPLATE = r"""#!/usr/bin/env bash
# codebeacon: incremental rebuild after each commit.
# Detaches so `git commit` returns immediately; output goes to the log below.
#
# Skip the rebuild when the commit didn't touch any source files — common
# cases: docs-only commits, version bumps, and (importantly) the codebeacon
# output dir itself. Without this guard a user who tracks `.codebeacon/` in
# git triggers a rebuild on every commit, which rewrites `.codebeacon/` and
# can feed itself indefinitely. Mirrors graphify #1018.
LOG="${HOME}/.cache/codebeacon-rebuild.log"
mkdir -p "$(dirname "$LOG")"

# Escape hatch for scripted/CI/rebase-heavy commit runs:
#   CODEBEACON_SKIP_HOOK=1 git commit -m ...
if [ -n "$CODEBEACON_SKIP_HOOK" ]; then
  exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0

# Linked worktrees share the common dir's hooks, so a commit made in one
# would rebuild THAT checkout's tree using the main checkout's index. Skip
# them; run `codebeacon scan . --update` by hand there instead. Detected by
# --git-dir (per-worktree) diverging from --git-common-dir (shared).
if [ "$(git rev-parse --git-dir 2>/dev/null)" != "$(git rev-parse --git-common-dir 2>/dev/null)" ]; then
  exit 0
fi

# Files touched by the new commit. Falls back to "everything staged" when
# HEAD~1 doesn't exist (initial commit).
CHANGED="$(git diff --name-only HEAD~1 HEAD 2>/dev/null \
  || git diff --name-only --cached 2>/dev/null \
  || true)"

# Exit if no changed files OR if every changed file is under the codebeacon
# output dir / non-source extension. Keep this list in sync with
# scanner.CODE_EXTENSIONS.
CODE_RE='\.(ts|tsx|js|jsx|mjs|cjs|py|go|vue|svelte|rb|java|kt|rs|php|swift|cs|razor|cshtml|sln|csproj|fsproj|vbproj|ex|exs|dart|scala|clj|hs|ets|graphql|gql|proto|sql)$'
if [ -z "$CHANGED" ] || ! echo "$CHANGED" | grep -v '^\.codebeacon/' | grep -E "$CODE_RE" >/dev/null 2>&1; then
  exit 0
fi

# Interpreter pinned at install time so the hook still works where the
# `codebeacon` launcher is not on PATH — GUI git clients and CI runners
# don't inherit a login shell's PATH, which made the old `nohup codebeacon`
# form silently no-op. The heredoc detaches via subprocess so no `nohup`
# is needed (it doesn't exist on Windows). Mirrors graphify #1127/#1161.
CODEBEACON_PYTHON=__CODEBEACON_PYTHON__

if [ -x "$CODEBEACON_PYTHON" ]; then
  "$CODEBEACON_PYTHON" - "$LOG" <<'CODEBEACON_PY' >>"$LOG" 2>&1
import subprocess, sys
kwargs = {"stdin": subprocess.DEVNULL}
if sys.platform == "win32":
    kwargs["creationflags"] = 0x00000208  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
else:
    kwargs["start_new_session"] = True
log = open(sys.argv[1], "ab")
subprocess.Popen(
    [sys.executable, "-m", "codebeacon", "scan", ".", "--update"],
    stdout=log, stderr=log, **kwargs,
)
CODEBEACON_PY
else
  # Pinned interpreter vanished (reinstall, deleted venv) — fall back to PATH.
  (
    nohup codebeacon scan . --update >>"$LOG" 2>&1 &
  ) >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi
exit 0
"""


def _render_post_commit_hook() -> str:
    """Render the hook with the current interpreter pinned.

    ``as_posix()`` keeps the path usable from git's bundled sh on Windows
    (``C:/Python311/python.exe``); single quotes stop spaces or shell
    metacharacters in the path from being interpreted.
    """
    python_path = "'" + Path(sys.executable).as_posix().replace("'", "'\\''") + "'"
    # Plain token replacement — str.format would choke on the template's own
    # shell braces (`${HOME}`, the heredoc's dict literal).
    return _POST_COMMIT_HOOK_TEMPLATE.replace("__CODEBEACON_PYTHON__", python_path)


def install_hooks(repo_path: str | Path) -> int:
    """Install the merge driver, ``.gitattributes`` entry, and post-commit hook.

    Returns 0 on success, non-zero only when ``repo_path`` is not a git working
    tree. All sub-steps print their result so the user can see what changed.
    """
    repo = Path(repo_path).resolve()
    if not _is_git_repo(repo):
        print(f"Error: {repo} is not inside a git working tree.", file=sys.stderr)
        return 1

    # The hook is written FIRST because it is the only step that can fail on a
    # path git owns (an unwritable hooks dir, a hooksPath pointing at a file).
    # Failing after the merge-driver and .gitattributes edits used to leave the
    # repo half-configured — the shape C-50 hit in a worktree checkout.
    try:
        hook_path = _install_post_commit(repo)
    except OSError as exc:
        print(
            f"Error: could not install the post-commit hook ({exc}).\n"
            "No changes were made — fix the hooks path (see `git config "
            "core.hooksPath` and `git rev-parse --git-path hooks`) and re-run.",
            file=sys.stderr,
        )
        return 1

    _register_merge_driver(repo)
    _patch_gitattributes(repo)
    print("\ncodebeacon hooks installed.")
    print(f"  - merge driver registered ({_config_path(repo)})")
    print(f"  - merge=codebeacon entry in {repo / '.gitattributes'}")
    print(f"  - post-commit rebuild hook: {hook_path}")
    return 0


def _is_git_repo(repo: Path) -> bool:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            # All git invocations pin UTF-8 + replace so non-ASCII repo
            # paths / branch names don't blow up on Windows cp1252.
            # Mirrors graphify #906.
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        return out.returncode == 0 and out.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _register_merge_driver(repo: Path) -> None:
    """Register the ``codebeacon`` merge driver in ``.git/config``."""
    codebeacon = shutil.which("codebeacon")
    if codebeacon:
        cmd = f'"{Path(codebeacon).as_posix()}" merge-driver "%O" "%A" "%B"'
    else:
        # Launcher not on PATH (uv tool / pipx install, GUI client) — invoke
        # the module through the pinned interpreter instead.
        cmd = f'"{Path(sys.executable).as_posix()}" -m codebeacon merge-driver "%O" "%A" "%B"'
    subprocess.run(
        ["git", "config", "--local", "merge.codebeacon.name", "codebeacon union merge"],
        cwd=str(repo),
        check=False,
    )
    subprocess.run(
        ["git", "config", "--local", "merge.codebeacon.driver", cmd],
        cwd=str(repo),
        check=False,
    )


def _patch_gitattributes(repo: Path) -> None:
    """Add ``*beacon.json merge=codebeacon`` to ``.gitattributes`` if missing."""
    ga = repo / ".gitattributes"
    existing = read_text_safe(ga) if ga.exists() else ""
    if "merge=codebeacon" in existing:
        return
    suffix = "" if not existing or existing.endswith("\n") else "\n"
    # Append rather than rewrite: a .gitattributes that is not valid UTF-8 (or
    # that some other tool is editing) keeps its original bytes byte-for-byte.
    with ga.open("a", encoding="utf-8", newline="") as fh:
        fh.write(suffix + "*beacon.json merge=codebeacon\n")


def _install_post_commit(repo: Path) -> Path:
    """Write the ``post-commit`` hook into the right hooks path.

    Returns the hook's path so the caller can report where it landed (which is
    *not* ``<repo>/.git/hooks`` in a worktree or submodule checkout). Raises
    ``OSError`` when the hooks directory cannot be created or written.
    """
    hooks_dir = _hooks_dir(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "post-commit"
    content = _render_post_commit_hook()
    if hook.exists():
        existing = read_text_safe(hook)
        if existing == content:
            return hook
        # A codebeacon-authored hook (our marker header) gets refreshed so
        # re-running `hook install` picks up template fixes; anything else
        # that merely mentions codebeacon is the user's — leave it alone.
        if "codebeacon: incremental rebuild" not in existing and "codebeacon" in existing:
            return hook
    # newline="\n" pins LF so Python's default newline translation doesn't turn
    # every '\n' into '\r\n' on Windows — a CRLF shebang (`env: bash\r`) and a
    # CRLF heredoc terminator both make the shell hook unrunnable there.
    hook.write_text(content, encoding="utf-8", newline="\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


def _git_path(repo: Path, what: str) -> Path | None:
    """Resolve ``git rev-parse --git-path <what>`` against *repo*.

    git answers with a path relative to the working tree in an ordinary
    checkout (``.git/hooks``) and with an absolute one where the git dir lives
    elsewhere — a linked worktree, a submodule, ``$GIT_DIR``. Returns ``None``
    when git is unavailable or the command fails.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-path", what],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0:
        return None
    value = out.stdout.strip()
    if not value:
        return None
    p = Path(value)
    return p if p.is_absolute() else (repo / p)


def _config_path(repo: Path) -> Path:
    """Where ``git config --local`` writes for this checkout (display only)."""
    return _git_path(repo, "config") or (repo / ".git" / "config")


def _hooks_dir(repo: Path) -> Path:
    """Return the hooks directory, honouring ``core.hooksPath``.

    ``core.hooksPath`` may be:

    * an absolute path (``/home/x/.husky``) — returned as-is,
    * a tilde-prefixed path (``~/.husky``) — expanded against ``$HOME``,
    * relative (``.husky``) — joined to the repo root.

    Mirrors graphify #554: without the tilde expansion, installing the
    hook into a Husky-managed repo writes the file at
    ``<repo>/~/.husky/post-commit``, which git never executes.

    With no ``core.hooksPath`` set, the directory comes from
    ``git rev-parse --git-path hooks`` rather than a hardcoded
    ``<repo>/.git/hooks``: in a ``git worktree`` checkout (and in a submodule)
    ``.git`` is a FILE, so the old guess raised ``NotADirectoryError`` and the
    hook was never installed (C-50).
    """
    try:
        out = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        configured = out.stdout.strip()
        if configured:
            # Expand ~ and ${VAR} so user-set hooks paths actually resolve.
            expanded = os.path.expandvars(os.path.expanduser(configured))
            p = Path(expanded)
            return p.resolve() if p.is_absolute() else (repo / p).resolve()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    resolved = _git_path(repo, "hooks")
    if resolved is not None:
        return resolved
    return repo / ".git" / "hooks"
