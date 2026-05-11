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


_POST_COMMIT_HOOK = """#!/usr/bin/env bash
# codebeacon: incremental rebuild after each commit.
# Detaches so `git commit` returns immediately; output goes to the log below.
LOG="${HOME}/.cache/codebeacon-rebuild.log"
mkdir -p "$(dirname "$LOG")"
(
  cd "$(git rev-parse --show-toplevel)"
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
    """Return the hooks directory, honouring ``core.hooksPath``."""
    try:
        out = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        configured = out.stdout.strip()
        if configured:
            return (repo / configured).resolve() if not Path(configured).is_absolute() else Path(configured)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return repo / ".git" / "hooks"
