#!/usr/bin/env python3
"""Entry script for the codebeacon PR-context GitHub Action.

Given a pull request's diff, this renders a markdown comment describing the
slice of the committed knowledge graph that the change touches:

* the affected wiki articles (the docs a reviewer should read first),
* seed / blast-radius node counts,
* an "architecture drift" structure-signal section that flags when a PR
  edits a high-impact hub file (widely imported → a change ripples out).

The heavy lifting lives in ``codebeacon.affected.affected_from_paths`` — this
script only resolves the diff (handling actions/checkout's shallow clone),
reads the *already persisted* ``REPORT.md`` for hub-file data (never re-scans),
and formats the comment. The comment body is written to ``--output`` and a
``has_comment`` step output is appended to ``$GITHUB_OUTPUT`` so the composite
action's next step can upsert the PR comment via ``gh``.

Design note: everything except ``main`` is a pure function so the renderer and
diff resolver can be unit-tested without a GitHub API or a live repo.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

from codebeacon.affected import AffectedResult, affected_from_paths

# HTML comment marker so the upsert step can find and PATCH the existing
# comment instead of stacking a new one on every push. Must stay byte-stable.
MARKER = "<!-- codebeacon-pr-context -->"

_HOMEPAGE = "https://github.com/codebeacon/codebeacon"


# ── git diff resolution ───────────────────────────────────────────────────────

def _run_git(cargs: Sequence[str], repo: str | Path | None = None) -> tuple[int, str, str]:
    """Run ``git <cargs>`` and return ``(returncode, stdout, stderr)``.

    Pins UTF-8 so non-ASCII paths (한글 / 日本語 / Umlaut) round-trip on
    runners whose console codepage isn't UTF-8. Never raises — a missing git
    binary surfaces as a non-zero return code, not a traceback.
    """
    try:
        proc = subprocess.run(
            ["git", *cargs],
            cwd=str(repo) if repo else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:  # git not installed / not on PATH
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _fetch_base(base: str, repo: str | Path | None = None) -> str | None:
    """Best-effort fetch of the base branch; return a ref that resolves.

    actions/checkout produces a shallow clone whose only ref is the PR head,
    so ``origin/<base>`` usually doesn't exist yet. We fetch its tip, then
    return the first candidate ref that ``rev-parse`` can verify. Returns
    ``None`` when nothing resolves (caller then degrades gracefully).
    """
    base = (base or "").strip()
    if not base:
        return None
    # --depth=1 keeps the fetch cheap; the example workflow uses fetch-depth: 0
    # on checkout so the merge base is present for a three-dot diff.
    _run_git(["fetch", "--no-tags", "--depth=1", "origin", base], repo=repo)
    for candidate in (f"origin/{base}", base, f"refs/remotes/origin/{base}"):
        rc, _out, _err = _run_git(["rev-parse", "--verify", "--quiet", candidate], repo=repo)
        if rc == 0:
            return candidate
    return None


def _diff_name_only(base_ref: str, head: str, repo: str | Path | None = None) -> tuple[bool, list[str]]:
    """Return ``(ok, files)`` for ``git diff --name-only``.

    Tries the three-dot form first (changes on HEAD since it diverged from
    base — what a reviewer means by "this PR"), then falls back to two-dot if
    the merge base isn't in a shallow clone. ``ok`` distinguishes a genuinely
    empty diff (no changes) from an unresolvable base ref.
    """
    for spec in (f"{base_ref}...{head}", f"{base_ref}..{head}"):
        rc, out, _err = _run_git(["diff", "--name-only", spec], repo=repo)
        if rc == 0:
            return True, [line.strip() for line in out.splitlines() if line.strip()]
    return False, []


def resolve_changed_files(
    base: str,
    head: str = "HEAD",
    repo: str | Path | None = None,
    *,
    fetch: bool = True,
) -> list[str]:
    """Resolve the PR's changed files from a git diff against ``base``.

    Returns an empty list (never raises) when ``base`` is blank or the base
    ref can't be resolved — a context commenter must degrade quietly rather
    than fail the build.
    """
    base = (base or "").strip()
    if not base:
        return []
    base_ref = base
    if fetch:
        resolved = _fetch_base(base, repo)
        if resolved:
            base_ref = resolved
    ok, files = _diff_name_only(base_ref, head, repo=repo)
    if not ok:
        print(
            f"codebeacon: could not diff against '{base}' — the checkout may be "
            "shallow. Set `fetch-depth: 0` on actions/checkout.",
            file=sys.stderr,
        )
        return []
    return files


# ── structure signals (from the persisted REPORT.md) ──────────────────────────

# Matches a "Hub Files (Most Imported)" bullet, e.g.
#   - /repo/codebeacon/common/safety.py (9 imports)
_HUB_LINE = re.compile(r"^-\s+(?P<path>.+?)\s+\((?P<count>\d+)\s+imports?\)\s*$")


def parse_hub_files(report_text: str) -> list[tuple[str, int]]:
    """Extract ``(path, import_count)`` from the Hub Files section of REPORT.md.

    Reads only the already-persisted analysis — the Action never runs a scan.
    Returns an empty list if the section is absent (older/partial index).
    """
    hubs: list[tuple[str, int]] = []
    in_section = False
    for line in report_text.splitlines():
        if line.startswith("## "):
            in_section = line.strip().lower().startswith("## hub files")
            continue
        if not in_section:
            continue
        m = _HUB_LINE.match(line)
        if m:
            hubs.append((m.group("path"), int(m.group("count"))))
    return hubs


def _suffix_match(a: str, b: str) -> bool:
    """True when one path is a segment-aligned suffix of the other.

    Same rule as ``affected_from_paths`` — reconciles the absolute paths that
    REPORT.md stores with the repo-relative paths a git diff yields, without
    bogus hits like ``foosrc/x.py`` matching ``src/x.py``.
    """
    a = a.replace("\\", "/")
    b = b.replace("\\", "/")
    if a == b:
        return True
    return ("/" + a).endswith("/" + b) or ("/" + b).endswith("/" + a)


def high_impact_changes(
    changed_files: Iterable[str],
    hub_files: Sequence[tuple[str, int]],
) -> list[tuple[str, int]]:
    """Changed files that are also known hub files, as ``(shown_path, count)``.

    ``shown_path`` is the repo-relative changed path (not REPORT.md's absolute
    path) so the comment never leaks the local checkout path of whoever built
    the index. Sorted by import count descending.
    """
    changed = list(changed_files)
    hits: list[tuple[str, int]] = []
    seen: set[str] = set()
    for hub_path, count in hub_files:
        if hub_path in seen:
            continue
        for cf in changed:
            if _suffix_match(hub_path, cf):
                hits.append((cf, count))
                seen.add(hub_path)
                break
    hits.sort(key=lambda h: h[1], reverse=True)
    return hits


# ── comment rendering ─────────────────────────────────────────────────────────

def _footer(base: str | None, depth: int, beacon_dir: str) -> str:
    ref = f" vs `{base}`" if base else ""
    return (
        f"<sub>🔦 Generated by [codebeacon]({_HOMEPAGE}) · blast-radius depth "
        f"{depth}{ref} · index committed in `{beacon_dir}/`. Stale? Re-run "
        f"`codebeacon scan . --update` and commit.</sub>"
    )


def build_comment(
    result: AffectedResult,
    changed_files: Sequence[str],
    *,
    hub_hits: Sequence[tuple[str, int]] = (),
    beacon_dir: str = ".codebeacon",
    base: str | None = None,
    depth: int = 3,
    limit: int = 50,
) -> str:
    """Render the PR-context comment body (always begins with ``MARKER``)."""
    n_changed = len(changed_files)
    n_seed = len(result.seed_node_ids)
    n_affected = len(result.affected_node_ids)
    wiki = result.wiki_paths

    lines = [
        MARKER,
        "",
        "## 🔦 codebeacon — PR context",
        "",
        "Architecture-drift check: the knowledge-graph slice this PR touches, so "
        "review stays anchored to the parts of the system that actually move.",
        "",
    ]

    if n_seed == 0:
        lines.append(
            f"**No architectural impact detected.** None of the {n_changed} changed "
            "file(s) map to a graph node — the diff looks like docs, config, or "
            "tests only."
        )
        lines.append("")
        lines.append(_footer(base, depth, beacon_dir))
        return "\n".join(lines)

    lines.append(
        f"**{n_changed}** changed file(s) → **{n_seed}** matched node(s) → "
        f"**{n_affected}** upstream node(s) in the blast radius (depth {depth})."
    )
    lines.append("")

    if hub_hits:
        lines.append("### ⚠️ Structure signals")
        lines.append("")
        lines.append(
            "This PR changes high-impact hub file(s) — widely imported, so the change "
            "ripples across the codebase. Worth extra review care:"
        )
        lines.append("")
        for path, count in hub_hits:
            lines.append(f"- `{path}` — imported by {count} file(s)")
        lines.append("")

    if wiki:
        shown = list(wiki[:limit])
        lines.append(f"### Affected wiki articles ({len(wiki)})")
        lines.append("")
        lines.append("Read these first — they document the affected slice:")
        lines.append("")
        for wp in shown:
            lines.append(f"- `{beacon_dir}/wiki/{wp}`")
        if len(wiki) > len(shown):
            lines.append(f"- …and {len(wiki) - len(shown)} more")
        lines.append("")
    else:
        lines.append(
            "_No wiki articles in the blast radius — affected nodes are routes / "
            "external nodes with no generated article, or the index is partial._"
        )
        lines.append("")

    lines.append(_footer(base, depth, beacon_dir))
    return "\n".join(lines)


def empty_no_beacon(beacon_dir: str = ".codebeacon") -> str:
    """Comment shown when no committed index is found — guides the user to add one."""
    return "\n".join([
        MARKER,
        "",
        "## 🔦 codebeacon — PR context",
        "",
        f"**No committed index found** (`{beacon_dir}/beacon.json` is missing).",
        "",
        "codebeacon reads a knowledge graph that lives in your repo as a "
        "git-committable artifact. To enable PR context, generate it once and "
        "commit it:",
        "",
        "```bash",
        "pip install codebeacon",
        "codebeacon scan .",
        f'git add {beacon_dir} && git commit -m "chore: add codebeacon index"',
        "```",
        "",
        _footer(None, 0, beacon_dir),
    ])


# ── step-output plumbing ──────────────────────────────────────────────────────

def _set_output(name: str, value: str, github_output: str | None) -> None:
    """Append ``name=value`` to the ``$GITHUB_OUTPUT`` file (no-op if unset)."""
    path = github_output or os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
    except OSError as exc:
        print(f"codebeacon: could not write step output ({exc}).", file=sys.stderr)


def _emit_comment(args: argparse.Namespace, body: str) -> None:
    """Persist the comment body and flag ``has_comment=true`` for the next step."""
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body + "\n")
    _set_output("has_comment", "true", args.github_output)


def _skip(args: argparse.Namespace, reason: str) -> int:
    print(f"codebeacon: {reason}")
    _set_output("has_comment", "false", args.github_output)
    return 0


# ── entry point ───────────────────────────────────────────────────────────────

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pr_context.py",
        description="Render a codebeacon PR-context comment from a git diff.",
    )
    p.add_argument("--base", default=os.environ.get("GITHUB_BASE_REF", ""),
                   help="Git ref to diff the PR against (e.g. main).")
    p.add_argument("--head", default="HEAD", help="New side of the diff (default: HEAD).")
    p.add_argument("--beacon-dir", dest="beacon_dir", default=".codebeacon",
                   help="Path to the committed .codebeacon index directory.")
    p.add_argument("--depth", type=int, default=3, help="Upstream blast-radius walk depth.")
    p.add_argument("--limit", type=int, default=50, help="Max wiki articles to list.")
    p.add_argument("--repo", default=".", help="Repository working directory for git.")
    p.add_argument("--output", default=os.environ.get("CODEBEACON_COMMENT_FILE") or "",
                   help="File to write the comment body to (default: stdout).")
    p.add_argument("--github-output", dest="github_output", default=None,
                   help="Path to the $GITHUB_OUTPUT file (default: env).")
    p.add_argument("--fail-on-error", dest="fail_on_error", action="store_true",
                   help="Exit non-zero on internal errors (default: never fail the build).")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    beacon_dir = Path(args.beacon_dir)

    changed = resolve_changed_files(args.base, args.head, repo=args.repo)
    if not changed:
        return _skip(args, "no changed files resolved from the diff — skipping comment.")

    if not (beacon_dir / "beacon.json").exists():
        # A missing index is a config gap, not an error: comment with guidance.
        _emit_comment(args, empty_no_beacon(args.beacon_dir))
        print(f"codebeacon: no index at {beacon_dir}/beacon.json — posted setup guidance.")
        return 0

    try:
        result = affected_from_paths(
            beacon_dir,
            changed,
            depth=args.depth,
            limit=args.limit,
            include_wiki_paths=True,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"codebeacon: affected analysis failed: {exc}", file=sys.stderr)
        _set_output("has_comment", "false", args.github_output)
        return 1 if args.fail_on_error else 0

    hub_hits: list[tuple[str, int]] = []
    report_path = beacon_dir / "REPORT.md"
    if report_path.exists():
        try:
            hub_hits = high_impact_changes(changed, parse_hub_files(report_path.read_text(encoding="utf-8")))
        except OSError:
            hub_hits = []

    body = build_comment(
        result,
        changed,
        hub_hits=hub_hits,
        beacon_dir=args.beacon_dir,
        base=args.base or None,
        depth=args.depth,
        limit=args.limit,
    )
    _emit_comment(args, body)
    print(
        f"codebeacon: {len(changed)} changed file(s), {len(result.seed_node_ids)} seed "
        f"node(s), {len(result.affected_node_ids)} affected, {len(result.wiki_paths)} "
        f"wiki article(s), {len(hub_hits)} hub hit(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
