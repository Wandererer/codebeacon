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
    content = _render_post_commit_hook()
    if hook.exists():
        existing = hook.read_text(encoding="utf-8")
        if existing == content:
            return
        # A codebeacon-authored hook (our marker header) gets refreshed so
        # re-running `hook install` picks up template fixes; anything else
        # that merely mentions codebeacon is the user's — leave it alone.
        if "codebeacon: incremental rebuild" not in existing and "codebeacon" in existing:
            return
    # newline="\n" pins LF so Python's default newline translation doesn't turn
    # every '\n' into '\r\n' on Windows — a CRLF shebang (`env: bash\r`) and a
    # CRLF heredoc terminator both make the shell hook unrunnable there.
    hook.write_text(content, encoding="utf-8", newline="\n")
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
