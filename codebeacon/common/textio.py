"""Tolerant text reads for the files codebeacon merges into rather than owns.

CLAUDE.md, AGENTS.md, .cursorrules, .gitattributes and an existing post-commit
hook are all *user* files that codebeacon reads, edits, and writes back. Reading
them with a bare ``read_text(encoding="utf-8")`` makes a legacy-codepage file
(cp949 on a Korean Windows box, cp1252 on a European one) raise an uncaught
``UnicodeDecodeError`` — which killed a whole ``codebeacon scan`` at its very
last step, after every extraction, wiki and obsidian file had been written, and
left ``codebeacon install`` half-done.

The rules here:

* ``utf-8-sig`` first, so a UTF-8 BOM is consumed instead of being carried into
  the rewritten file as a stray ``\\ufeff``.
* undecodable bytes degrade to U+FFFD instead of aborting the run, with a
  warning on stderr naming the file — the round-trip IS lossy and the user has
  to know.
* callers that write the text back get :func:`read_text_status` so they can
  preserve the original bytes (``backup_original``) before clobbering them.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["read_text_safe", "read_text_status", "backup_original"]

_BACKUP_SUFFIX = ".codebeacon-bak"


def read_text_status(path: str | Path) -> tuple[str, bool]:
    """Return ``(text, lossy)`` for *path*.

    ``lossy`` is True when at least one byte could not be decoded as UTF-8 and
    was replaced — i.e. writing the returned text back would not round-trip.
    """
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig"), False
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), True


def read_text_safe(path: str | Path, *, warn: bool = True) -> str:
    """Read *path* as text, never raising ``UnicodeDecodeError``."""
    text, lossy = read_text_status(path)
    if lossy and warn:
        print(
            f"warning: {path} is not valid UTF-8 — undecodable bytes were "
            "replaced. Re-save the file as UTF-8 to keep its contents intact.",
            file=sys.stderr,
        )
    return text


def backup_original(path: str | Path) -> Path | None:
    """Copy *path*'s raw bytes aside before a lossy rewrite.

    Returns the backup path, or ``None`` when the source is missing or the
    backup could not be written (never raises — a failed backup must not turn
    into a failed scan). Existing backups are numbered rather than overwritten
    so a second bad run cannot destroy the first rescue copy.
    """
    src = Path(path)
    try:
        data = src.read_bytes()
    except OSError:
        return None
    candidate = src.with_name(src.name + _BACKUP_SUFFIX)
    n = 1
    while candidate.exists():
        candidate = src.with_name(f"{src.name}{_BACKUP_SUFFIX}.{n}")
        n += 1
    try:
        candidate.write_bytes(data)
    except OSError:
        return None
    return candidate
