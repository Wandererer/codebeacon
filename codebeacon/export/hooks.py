"""Git hook + merge-driver installation for ``codebeacon``.

``codebeacon hook install`` does three things in the current repository:

1. Registers a ``codebeacon`` git merge driver in ``.git/config`` that calls
   ``codebeacon merge-driver`` (see :mod:`codebeacon.export.merge`).
2. Adds ``*beacon.json merge=codebeacon`` to ``.gitattributes`` so git uses the
   driver for ``beacon.json`` (and per-project ``beacon.json`` files in
   deep-dive mode).
3. Drops a ``post-commit`` hook that detaches a background incremental rebuild
   (``codebeacon scan . --update``). The hook respects ``core.hooksPath`` so
   Husky-managed repos don't get a parallel set of hooks. Rebuild output is
   redirected to ``~/.cache/codebeacon-rebuild.log``.

Each step is idempotent — running ``codebeacon hook install`` twice is safe.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


_POST_COMMIT_HOOK = r"""#!/usr/bin/env bash
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

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0

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

(
  nohup codebeacon scan . --update >>"$LOG" 2>&1 &
) >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0
"""


def install_hooks(repo_path: str | Path) -> int:
    """Install the merge driver, ``.gitattributes`` entry, and post-commit hook.

    Returns 0 on success, non-zero only when ``repo_path`` is not a git working
    tree. All sub-steps print their result so the user can see what changed.
    """
    repo = Path(repo_path).resolve()
    if not _is_git_repo(repo):
        print(f"Error: {repo} is not inside a git working tree.", file=sys.stderr)
        return 1

    _register_merge_driver(repo)
    _patch_gitattributes(repo)
    _install_post_commit(repo)
    print("\ncodebeacon hooks installed.")
    print("  - merge driver registered (.git/config)")
    print("  - merge=codebeacon entry in .gitattributes")
    print("  - post-commit rebuild hook installed")
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
    codebeacon = shutil.which("codebeacon") or "codebeacon"
    cmd = f'{codebeacon} merge-driver "%O" "%A" "%B"'
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
    existing = ga.read_text(encoding="utf-8") if ga.exists() else ""
    if "merge=codebeacon" in existing:
        return
    suffix = "" if not existing or existing.endswith("\n") else "\n"
    ga.write_text(existing + suffix + "*beacon.json merge=codebeacon\n", encoding="utf-8")


def _install_post_commit(repo: Path) -> None:
    """Write the ``post-commit`` hook into the right hooks path."""
    hooks_dir = _hooks_dir(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "post-commit"
    if hook.exists() and "codebeacon" in hook.read_text(encoding="utf-8"):
        return
    hook.write_text(_POST_COMMIT_HOOK, encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _hooks_dir(repo: Path) -> Path:
    """Return the hooks directory, honouring ``core.hooksPath``.

    ``core.hooksPath`` may be:

    * an absolute path (``/home/x/.husky``) — returned as-is,
    * a tilde-prefixed path (``~/.husky``) — expanded against ``$HOME``,
    * relative (``.husky``) — joined to the repo root.

    Mirrors graphify #554: without the tilde expansion, installing the
    hook into a Husky-managed repo writes the file at
    ``<repo>/~/.husky/post-commit``, which git never executes.
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
    return repo / ".git" / "hooks"
