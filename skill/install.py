"""Install the codebeacon Claude Code skill.

Copies SKILL.md to ~/.claude/skills/codebeacon/SKILL.md and appends
the trigger block to ~/.claude/CLAUDE.md (idempotent).

Can be run directly:
    python skill/install.py

Or via the CLI:
    codebeacon install
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


SKILL_SRC = Path(__file__).parent.parent / "codebeacon" / "skill" / "SKILL.md"

CLAUDE_TRIGGER_BLOCK = """\
# codebeacon
- **codebeacon** (`~/.claude/skills/codebeacon/SKILL.md`) - scan source code → knowledge graph + wiki. Trigger: `/codebeacon`
When the user types `/codebeacon`, invoke the Skill tool with `skill: "codebeacon"` before doing anything else.
"""

TRIGGER_MARKER = "# codebeacon"


def install(verbose: bool = True, project: str | Path | None = None) -> None:
    """Install the codebeacon skill.

    Args:
        verbose: print progress lines.
        project: when given, install into ``<project>/.claude/skills/codebeacon/``
                 instead of the user-global ``~/.claude/``. Project-scoped
                 installs let teams pin a SKILL.md version per repo so a
                 ``codebeacon upgrade`` in one checkout doesn't change every
                 collaborator's runtime. Mirrors graphify #b347492.

    Steps:
    1. Copy SKILL.md to ``<scope>/skills/codebeacon/SKILL.md``
    2. Append trigger block to ``<scope>/CLAUDE.md`` (if not already present)
    """
    if project is not None:
        scope_root = Path(project).resolve() / ".claude"
        trigger_path_label = ".claude/skills/codebeacon/SKILL.md"
    else:
        scope_root = Path.home() / ".claude"
        trigger_path_label = "~/.claude/skills/codebeacon/SKILL.md"

    skills_dir = scope_root / "skills" / "codebeacon"
    skill_dest = skills_dir / "SKILL.md"
    claude_md = scope_root / "CLAUDE.md"

    # ── Step 1: copy SKILL.md ──────────────────────────────────────────────────
    if not SKILL_SRC.exists():
        print(f"Error: SKILL.md not found at {SKILL_SRC}", file=sys.stderr)
        sys.exit(1)

    skills_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SKILL_SRC, skill_dest)
    if verbose:
        print(f"  Copied SKILL.md → {skill_dest}")

    # ── Step 2: add trigger to CLAUDE.md ──────────────────────────────────────
    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
    else:
        existing = ""

    if TRIGGER_MARKER in existing:
        if verbose:
            print(f"  Trigger already present in {claude_md} — skipping.")
    else:
        # Re-template the trigger block so the path matches the active scope.
        trigger_block = (
            "# codebeacon\n"
            f"- **codebeacon** (`{trigger_path_label}`) - scan source code "
            "→ knowledge graph + wiki. Trigger: `/codebeacon`\n"
            'When the user types `/codebeacon`, invoke the Skill tool with '
            '`skill: "codebeacon"` before doing anything else.\n'
        )
        separator = "\n" if existing and not existing.endswith("\n\n") else ""
        claude_md.write_text(existing + separator + trigger_block, encoding="utf-8")
        if verbose:
            print(f"  Added codebeacon trigger to {claude_md}")

    if verbose:
        scope_kind = "project" if project is not None else "user"
        print(f"\ncodebeacon skill installed ({scope_kind} scope).")
        print("Start a new Claude Code session and type /codebeacon to use it.")


if __name__ == "__main__":
    install()
