"""Detect git hooks (lefthook / husky / raw) so agents know what gates a commit.

Surfaces lifecycle→command mapping in CLAUDE.md with an explicit warning that
hooks block the operation on failure. Raw hooks are suppressed for any
lifecycle already covered by a managed tool (lefthook/husky install raw hooks
that just delegate).
"""

from __future__ import annotations

import json
import re
import stat as stat_mod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class HookCommand:
    name: str
    run: str


@dataclass(slots=True)
class GitHook:
    lifecycle: str
    tool: str  # "lefthook" | "husky" | "raw"
    source: str  # repo-relative file path
    commands: list[HookCommand] = field(default_factory=list)


_HOOK_NAMES = frozenset({
    "pre-commit", "commit-msg", "prepare-commit-msg", "post-commit",
    "pre-push", "post-merge", "post-checkout", "pre-rebase", "post-rewrite",
})

_LIFECYCLE_ORDER = (
    "pre-commit", "prepare-commit-msg", "commit-msg", "post-commit",
    "pre-rebase", "post-checkout", "post-merge", "pre-push", "post-rewrite",
)

_TOOL_LABEL = {"lefthook": "lefthook", "husky": "husky", "raw": "raw git hook"}


def detect_hooks(repo_root: Path) -> list[GitHook]:
    lefthook = _parse_lefthook(repo_root)
    husky = _parse_husky(repo_root)
    managed = {h.lifecycle for h in lefthook} | {h.lifecycle for h in husky}
    raw = [h for h in _parse_raw(repo_root) if h.lifecycle not in managed]
    return [*lefthook, *husky, *raw]


# ── lefthook ─────────────────────────────────────────────────────────────────

def _parse_lefthook(root: Path) -> list[GitHook]:
    for name in ("lefthook.yml", "lefthook.yaml", "lefthook.json"):
        path = root / name
        if not path.is_file():
            continue
        content = _read_safe(path)
        try:
            if name.endswith(".json"):
                return _lefthook_from_json(json.loads(content), name)
            return _lefthook_from_yaml(content, name)
        except (ValueError, json.JSONDecodeError):
            return []
    return []


def _lefthook_from_yaml(content: str, source: str) -> list[GitHook]:
    """Minimal indent-aware parser. Handles: lifecycle > commands > name > run.

    Skips full YAML support (anchors, multi-line scalars) — enough for the
    common lefthook structure.
    """
    by_lifecycle: dict[str, list[HookCommand]] = {}
    current_lc: str | None = None
    in_commands = False
    current_cmd: str | None = None

    for raw in content.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        trimmed = raw.strip()

        if indent == 0 and trimmed.endswith(":"):
            key = trimmed[:-1]
            current_lc = key if key in _HOOK_NAMES else None
            in_commands = False
            current_cmd = None
            if current_lc:
                by_lifecycle.setdefault(current_lc, [])
            continue

        if current_lc is None:
            continue

        if indent == 2 and trimmed in ("commands:", "scripts:"):
            in_commands = True
            continue

        if in_commands and indent == 4 and trimmed.endswith(":") and not trimmed.startswith("run:"):
            current_cmd = trimmed[:-1]
            continue

        if in_commands and current_cmd and indent == 6 and trimmed.startswith("run:"):
            run = trimmed[4:].strip().strip("'\"")
            by_lifecycle[current_lc].append(HookCommand(name=current_cmd, run=run))
            continue

        if not in_commands and indent == 2 and trimmed.startswith("run:"):
            run = trimmed[4:].strip().strip("'\"")
            by_lifecycle[current_lc].append(HookCommand(name=current_lc, run=run))

    return [
        GitHook(lifecycle=lc, tool="lefthook", source=source, commands=cmds)
        for lc, cmds in by_lifecycle.items() if cmds
    ]


def _lefthook_from_json(obj: dict, source: str) -> list[GitHook]:
    hooks: list[GitHook] = []
    for lc in _HOOK_NAMES:
        block = obj.get(lc)
        if not isinstance(block, dict):
            continue
        cmds_block = block.get("commands") or block.get("scripts")
        if not isinstance(cmds_block, dict):
            continue
        commands = [
            HookCommand(name=name, run=cmd["run"])
            for name, cmd in cmds_block.items()
            if isinstance(cmd, dict) and isinstance(cmd.get("run"), str)
        ]
        if commands:
            hooks.append(GitHook(lifecycle=lc, tool="lefthook", source=source, commands=commands))
    return hooks


# ── husky ────────────────────────────────────────────────────────────────────

def _parse_husky(root: Path) -> list[GitHook]:
    husky_dir = root / ".husky"
    if not husky_dir.is_dir():
        return []
    hooks: list[GitHook] = []
    for entry in sorted(husky_dir.iterdir()):
        if not entry.is_file() or entry.name not in _HOOK_NAMES:
            continue
        commands = _extract_shell_commands(_read_safe(entry))
        if commands:
            hooks.append(GitHook(
                lifecycle=entry.name, tool="husky",
                source=f".husky/{entry.name}", commands=commands,
            ))
    return hooks


# ── raw .git/hooks ───────────────────────────────────────────────────────────

def _parse_raw(root: Path) -> list[GitHook]:
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        return []
    hooks: list[GitHook] = []
    for entry in sorted(hooks_dir.iterdir()):
        if not entry.is_file() or entry.name.endswith(".sample"):
            continue
        if entry.name not in _HOOK_NAMES:
            continue
        try:
            mode = entry.stat().st_mode
        except OSError:
            continue
        if not (mode & (stat_mod.S_IXUSR | stat_mod.S_IXGRP | stat_mod.S_IXOTH)):
            continue
        commands = _extract_shell_commands(_read_safe(entry))
        if commands:
            hooks.append(GitHook(
                lifecycle=entry.name, tool="raw",
                source=f".git/hooks/{entry.name}", commands=commands,
            ))
    return hooks


# ── shared helpers ───────────────────────────────────────────────────────────

_SHEBANG_RE = re.compile(r"^#!")


def _extract_shell_commands(content: str) -> list[HookCommand]:
    out: list[HookCommand] = []
    for line in content.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or _SHEBANG_RE.match(s) or s.startswith(". "):
            continue
        first = s.split(maxsplit=1)[0]
        out.append(HookCommand(name=first, run=s))
    return out


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ── formatting ───────────────────────────────────────────────────────────────

def format_hooks_section(hooks: list[GitHook]) -> str:
    if not hooks:
        return ""
    lines = ["## Git Hooks", ""]
    lines.append(
        "> **Note for agents:** these hooks fire on git operations and block "
        "the operation on failure. Fix the underlying issue rather than "
        "bypassing with `--no-verify`."
    )
    lines.append("")

    def _key(h: GitHook) -> tuple[int, str]:
        try:
            return (_LIFECYCLE_ORDER.index(h.lifecycle), h.tool)
        except ValueError:
            return (len(_LIFECYCLE_ORDER), h.lifecycle)

    for hook in sorted(hooks, key=_key):
        label = _TOOL_LABEL.get(hook.tool, hook.tool)
        lines.append(f"### `{hook.lifecycle}` — {label}")
        lines.append("")
        for cmd in hook.commands:
            lines.append(f"- **{cmd.name}**: `{cmd.run}`")
        lines.append("")
    sources = sorted({h.source for h in hooks})
    lines += [f"_Source: {', '.join(sources)}_", ""]
    return "\n".join(lines)
