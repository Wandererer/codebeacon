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


SKILL_SRC = Path(__file__).parent / "SKILL.md"

CLAUDE_TRIGGER_BLOCK = """\
# codebeacon
- **codebeacon** (`~/.claude/skills/codebeacon/SKILL.md`) - scan source code → knowledge graph + wiki. Trigger: `/codebeacon`
When the user types `/codebeacon`, invoke the Skill tool with `skill: "codebeacon"` before doing anything else.
"""

TRIGGER_MARKER = "# codebeacon"


def install(verbose: bool = True) -> None:
    """Install the codebeacon skill.

    Steps:
    1. Copy SKILL.md to ~/.claude/skills/codebeacon/SKILL.md
    2. Append trigger block to ~/.claude/CLAUDE.md (if not already present)
    """
    claude_dir = Path.home() / ".claude"
    skills_dir = claude_dir / "skills" / "codebeacon"
    skill_dest = skills_dir / "SKILL.md"
    claude_md = claude_dir / "CLAUDE.md"

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
        # Append with a leading newline if file is non-empty
        separator = "\n" if existing and not existing.endswith("\n\n") else ""
        claude_md.write_text(existing + separator + CLAUDE_TRIGGER_BLOCK, encoding="utf-8")
        if verbose:
            print(f"  Added codebeacon trigger to {claude_md}")

    if verbose:
        print("\ncodebeacon skill installed.")
        print("Start a new Claude Code session and type /codebeacon to use it.")


if __name__ == "__main__":
    install()
