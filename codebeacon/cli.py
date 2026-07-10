"""codebeacon CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codebeacon import __version__
from codebeacon.pipeline import (
    run_deep_dive_pipeline,
    run_pipeline,
)


def _cmd_scan(args: argparse.Namespace) -> int:
    from codebeacon.config import find_config, load_config, generate_config
    from codebeacon.discover.detector import discover_projects, extract_convention_routes
    from codebeacon.discover.scanner import collect_files

    paths = [str(Path(p).resolve()) for p in args.paths]

    if getattr(args, "watch", False):
        print("Warning: --watch is not yet implemented. Ignoring.", file=sys.stderr)

    # If single path: check for local config first, then walk up to parent directories.
    # This lets `codebeacon scan . --update` from any sub-project find and sync the
    # workspace config without requiring the user to know the workspace root.
    if len(paths) == 1:
        config_path = find_config(paths[0])
        if not config_path:
            config_path = find_config(paths[0], walk_up=True)
        # --list-only is a read-only "what would be scanned" query. Never let
        # the sync auto-switch turn it into a full extraction (which writes
        # outputs and can rewrite codebeacon.yaml via auto-rediscovery); fall
        # through to plain discovery + listing instead.
        if config_path and not args.list_only:
            print(f"Found {config_path} — switching to sync mode")
            args.config = str(config_path)
            return _cmd_sync(args)

    try:
        projects = discover_projects(paths)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not projects:
        print("No projects found.", file=sys.stderr)
        return 1

    multi = len(projects) > 1 or (len(projects) == 1 and projects[0].is_multi)

    if multi:
        print(f"Scanning {len(projects)} project(s)...")
    else:
        print(f"Scanning {projects[0].path} ...")

    max_name = max(len(p.name) for p in projects)
    max_fw = max(len(p.framework) for p in projects)

    for p in projects:
        sig = f"({Path(p.signature_file).name})" if p.signature_file else "(code files)"
        print(f"  {p.name:<{max_name}}  {p.framework:<{max_fw}}  {sig}")

    # Show convention routes for file-system frameworks
    for p in projects:
        routes = extract_convention_routes(p)
        if routes:
            print(f"  → {p.name}: {len(routes)} file-system routes detected")

    # Determine output dir
    if len(args.paths) == 1:
        output_base = Path(paths[0])
    else:
        output_base = Path.cwd()

    output_dir = str(output_base / ".codebeacon")
    print(f"  Output: {output_dir}")

    # --list-only lists detected projects and stops before writing anything —
    # no auto-generated codebeacon.yaml, no extraction, no context-map files.
    if args.list_only:
        return 0

    deep_dive = getattr(args, "deep_dive", False)

    # Auto-generate codebeacon.yaml on multi-project first scan
    if multi and len(args.paths) == 1:
        yaml_path = output_base / "codebeacon.yaml"
        if not yaml_path.exists():
            generate_config(projects, output_dir, yaml_path, deep_dive=deep_dive)
            print(f"  Generated {yaml_path} — next time run: codebeacon sync")

    if deep_dive:
        return run_deep_dive_pipeline(projects, output_dir, args)
    return run_pipeline(projects, output_dir, args)


def _cmd_sync(args: argparse.Namespace) -> int:
    from codebeacon.config import (
        load_config, find_config, discover_new_projects, append_projects_to_yaml,
    )
    from codebeacon.discover.detector import detect_framework
    from codebeacon.common.types import ProjectInfo

    config_path = getattr(args, "config", None)
    if not config_path:
        # Walk up from CWD so `codebeacon sync` works from any sub-project directory
        config_path = find_config(Path.cwd(), walk_up=True)
    if not config_path:
        print("Error: No codebeacon.yaml found in current directory or any parent.", file=sys.stderr)
        print("Run 'codebeacon scan <path>' or 'codebeacon init' to create one.", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1

    # Auto-discover projects added to the workspace since the yaml was last written.
    # Skip when `--no-rediscover` is set so users with hand-curated yaml configs
    # can opt out.
    if not getattr(args, "no_rediscover", False):
        new_projects = discover_new_projects(config)
        if new_projects:
            print(f"Found {len(new_projects)} new project(s); adding to {config.config_file}:")
            for p in new_projects:
                print(f"  + {p.name:<20}  {p.framework:<15}  {p.path}")
            append_projects_to_yaml(config.config_file, new_projects)
            config = load_config(config.config_file)

    # Wire parsed codebeacon.yaml settings through to the pipeline via `args`,
    # honoring precedence: explicit CLI flags > codebeacon.yaml > built-in
    # defaults. The pipeline reads these with getattr(..., <default>) so the
    # `scan` path (no config) keeps its defaults and run_pipeline's positional
    # signature stays unchanged. --semantic on the CLI OR semantic.enabled in
    # the yaml turns the semantic step on.
    args.semantic = getattr(args, "semantic", False) or config.semantic.enabled
    args.wave_chunk_size = config.wave.chunk_size
    args.wave_max_parallel = config.wave.max_parallel
    args.output_wiki = config.output.wiki
    args.output_obsidian = config.output.obsidian
    args.context_map_targets = config.output.context_map_targets

    print(f"Using {config.config_file}")
    print(f"Processing {len(config.projects)} project(s)...")

    for p in config.projects:
        fw, lang, sig = detect_framework(p.path)
        effective_fw = p.type if p.type != "auto" else fw
        print(f"  {p.name:<20}  {effective_fw:<15}  {p.path}")

    # Resolve output.dir relative to the config file's directory when it is a
    # relative path.  Without this, running `codebeacon sync` from a sub-project
    # would create .codebeacon/ in the wrong directory.
    output_dir = config.output.dir
    if not Path(output_dir).is_absolute():
        output_dir = str(Path(config.config_file).parent / output_dir)

    print(f"  Output: {output_dir}")

    projects_info = []
    for p in config.projects:
        fw, lang, sig = detect_framework(p.path)
        effective_fw = p.type if p.type != "auto" else fw
        from codebeacon.common.types import ProjectInfo
        projects_info.append(ProjectInfo(
            name=p.name,
            path=p.path,
            framework=effective_fw,
            language=lang,
            signature_file=sig or "",
        ))

    deep_dive = config.deep_dive or getattr(args, "deep_dive", False)
    if deep_dive:
        return run_deep_dive_pipeline(projects_info, output_dir, args)
    return run_pipeline(projects_info, output_dir, args)


def _cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path) if args.path else Path.cwd()
    yaml_path = target / "codebeacon.yaml"

    if yaml_path.exists():
        print(f"Config already exists: {yaml_path}")
        return 0

    from codebeacon.discover.detector import discover_projects
    from codebeacon.config import generate_config

    try:
        projects = discover_projects([str(target)])
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    generate_config(projects, ".codebeacon", yaml_path)
    print(f"Created {yaml_path}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    """Search the beacon graph for nodes whose label contains ``args.term``.

    Reuses :class:`codebeacon.export.mcp.BeaconIndex` so query semantics match
    what an MCP client gets — one source of truth for the lookup logic.
    """
    from codebeacon.export.mcp import BeaconIndex, tool_beacon_query

    beacon_dir = _resolve_beacon_dir(args)
    idx = BeaconIndex(beacon_dir)
    try:
        idx.load()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(tool_beacon_query(idx, {"term": args.term, "limit": int(getattr(args, "limit", 20))}))
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    """Print the shortest dependency path between two named nodes."""
    from codebeacon.export.mcp import BeaconIndex, tool_beacon_path

    beacon_dir = _resolve_beacon_dir(args)
    idx = BeaconIndex(beacon_dir)
    try:
        idx.load()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(tool_beacon_path(idx, {"source": args.source, "target": args.target}))
    return 0


def _resolve_beacon_dir(args: argparse.Namespace) -> Path:
    """Resolve which ``.codebeacon`` directory the user wants to query."""
    candidate = getattr(args, "dir", None) or ".codebeacon"
    p = Path(candidate)
    return p if p.is_absolute() else Path.cwd() / p


def _cmd_merge_driver(args: argparse.Namespace) -> int:
    """Git merge driver entry point — never block a merge."""
    from codebeacon.export.merge import merge_files
    return merge_files(args.base, args.current, args.other)


def _cmd_hook(args: argparse.Namespace) -> int:
    """``codebeacon hook install`` — wire git hooks + merge driver."""
    from codebeacon.export.hooks import install_hooks
    if args.hook_action != "install":
        print(f"Unknown hook action: {args.hook_action}", file=sys.stderr)
        return 1
    target = Path(getattr(args, "path", ".") or ".").resolve()
    return install_hooks(target)


def _cmd_knowledge(args: argparse.Namespace) -> int:
    """``codebeacon knowledge`` — scan markdown notes → ``KNOWLEDGE.md``.

    Pairs with the existing ``codebeacon scan`` (code → graph). The two
    outputs together give an agent both *what* the code does and *why*
    the team decided to build it this way (see codesight 1.9.3
    ``--mode knowledge`` for the original framing).
    """
    from codebeacon.knowledge import build_knowledge_map

    root = Path(args.path or ".").resolve()
    if not root.exists():
        print(f"  Error: path not found: {root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"  Error: not a directory: {root}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).resolve() if args.output_dir else root

    print(f"  Scanning markdown notes under {root} ...")
    result = build_knowledge_map(root, output_dir)
    counts = result.counts()
    total = len(result.notes)
    print(f"    {total} notes found")
    if counts:
        bits = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        print(f"    Categories: {bits}")
    if result.output_path:
        print(f"  Wrote {result.output_path}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from pathlib import Path
    from codebeacon.export.mcp import serve

    beacon_dir = Path(getattr(args, "dir", ".codebeacon"))
    if not beacon_dir.is_absolute():
        beacon_dir = Path.cwd() / beacon_dir
    serve(beacon_dir)
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    import shutil
    import sys
    from pathlib import Path

    # SKILL.md is shipped inside the package at codebeacon/skill/SKILL.md
    skill_src = Path(__file__).parent / "skill" / "SKILL.md"
    if not skill_src.exists():
        print(f"Error: SKILL.md not found at {skill_src}", file=sys.stderr)
        return 1

    # Project scope: ``codebeacon install --project [PATH]`` writes into
    # ``<PATH>/.claude/`` so teams can pin a SKILL.md version per repo
    # instead of mutating every collaborator's ~/.claude. Mirrors graphify
    # #b347492.
    project = getattr(args, "project", None)
    if project is not None:
        scope_root = Path(project or ".").resolve() / ".claude"
        trigger_path_label = ".claude/skills/codebeacon/SKILL.md"
        scope_kind = "project"
    else:
        scope_root = Path.home() / ".claude"
        trigger_path_label = "~/.claude/skills/codebeacon/SKILL.md"
        scope_kind = "user"

    skills_dir = scope_root / "skills" / "codebeacon"
    skill_dest = skills_dir / "SKILL.md"
    claude_md = scope_root / "CLAUDE.md"

    skills_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dest)
    print(f"  Copied SKILL.md → {skill_dest}")

    trigger_block = (
        "\n# codebeacon\n"
        f"- **codebeacon** (`{trigger_path_label}`) - scan source code "
        "→ knowledge graph + wiki. Trigger: `/codebeacon`\n"
        'When the user types `/codebeacon`, invoke the Skill tool with '
        '`skill: "codebeacon"` before doing anything else.\n'
    )
    existing = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    if "# codebeacon" in existing:
        print(f"  Trigger already present in {claude_md} — skipping.")
    else:
        separator = "\n" if existing and not existing.endswith("\n\n") else ""
        claude_md.write_text(existing + separator + trigger_block, encoding="utf-8")
        print(f"  Added codebeacon trigger to {claude_md}")

    print(f"\ncodebeacon skill installed ({scope_kind} scope).")
    print("Start a new Claude Code session and type /codebeacon to use it.")
    return 0


def _detect_install_kind() -> str:
    """Classify how this codebeacon was installed.

    Returns one of ``"editable"``, ``"pipx"``, ``"uv-tool"``, or ``"pip"``.
    pipx and uv-tool manage their own venvs (which usually ship *without* a
    pip module), so ``python -m pip install --upgrade`` is the wrong tool
    there — each needs its own upgrade command.
    """
    try:
        from importlib.metadata import Distribution
        dist = Distribution.from_name("codebeacon")
        direct_url = dist.read_text("direct_url.json") or ""
        if '"editable": true' in direct_url:
            return "editable"
    except Exception:
        pass

    parts = Path(sys.prefix).resolve().parts
    if "pipx" in parts:
        return "pipx"
    if "uv" in parts and "tools" in parts:
        return "uv-tool"
    return "pip"


def _is_uv_venv() -> bool:
    """True when this interpreter runs inside a ``uv venv``-created environment.

    uv stamps a ``uv = <version>`` line into the venv's ``pyvenv.cfg``. Such a
    venv ships without a pip module by default, yet — unlike a pipx/uv-tool
    managed venv — it is NOT upgraded with ``pipx``/``uv tool``; the right
    command is ``uv pip install --upgrade`` targeting the venv itself.
    """
    cfg = Path(sys.prefix) / "pyvenv.cfg"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.split("=", 1)[0].strip().lower() == "uv":
                return True
    except OSError:
        pass
    return False


def _pypi_latest_version(timeout: float = 5.0) -> str | None:
    """Best-effort lookup of the newest codebeacon release on PyPI."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(
            "https://pypi.org/pypi/codebeacon/json", timeout=timeout
        ) as resp:
            return json.load(resp)["info"]["version"]
    except Exception:
        return None


def _installed_version(python: str) -> str | None:
    """Read codebeacon.__version__ via a fresh interpreter.

    The current process keeps running pre-upgrade code, so the only way to
    see what an upgrade actually installed is to ask a new process.
    """
    import subprocess

    try:
        out = subprocess.run(
            [python, "-c", "import codebeacon; print(codebeacon.__version__)"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


def _cmd_upgrade(args: argparse.Namespace) -> int:
    """``codebeacon upgrade`` — upgrade the package + refresh SKILL.md.

    Picks the upgrade command matching how codebeacon was installed
    (pip / pipx / uv tool), verifies the installed version actually changed,
    then reinvokes `codebeacon install` so ~/.claude/skills/codebeacon/SKILL.md
    is refreshed to whatever shipped in the new release. Editable installs are
    detected and skipped (a pip upgrade would clobber the dev checkout).
    """
    import shutil
    import subprocess
    import sys as _sys
    from codebeacon import __version__ as _current

    print(f"Current version: codebeacon {_current}", flush=True)
    latest = _pypi_latest_version()
    if latest:
        print(f"Latest on PyPI:  codebeacon {latest}", flush=True)

    kind = _detect_install_kind()

    if kind == "editable" and not getattr(args, "force", False):
        print(
            "Detected an editable (pip install -e .) install — skipping package upgrade.\n"
            "Use `git pull` to get new code, or pass --force to upgrade anyway.",
            file=_sys.stderr,
        )
    else:
        if kind == "pipx":
            cmd = [shutil.which("pipx") or "pipx", "upgrade", "codebeacon"]
        elif kind == "uv-tool":
            cmd = [shutil.which("uv") or "uv", "tool", "upgrade", "codebeacon"]
        else:
            import importlib.util
            if importlib.util.find_spec("pip") is None:
                if _is_uv_venv():
                    # A `uv venv` has no pip module, but `pipx`/`uv tool` don't
                    # manage it either — both fail with "not installed". The
                    # working command is `uv pip install` into this venv.
                    print(
                        "This environment was created by `uv venv` and has no "
                        "pip module, so codebeacon cannot upgrade itself "
                        "in-process.\n"
                        "Upgrade it with uv (run inside this environment):\n"
                        "  uv pip install --upgrade codebeacon",
                        file=_sys.stderr,
                    )
                else:
                    print(
                        "This Python environment has no pip module, so codebeacon "
                        "cannot upgrade itself here.\n"
                        "Upgrade with the tool that installed it, e.g.:\n"
                        "  pipx upgrade codebeacon\n"
                        "  uv tool upgrade codebeacon",
                        file=_sys.stderr,
                    )
                return 1
            cmd = [_sys.executable, "-m", "pip", "install", "--upgrade", "codebeacon"]

        print(f"$ {' '.join(cmd)}")
        try:
            rc = subprocess.call(cmd)
        except FileNotFoundError:
            print(f"Could not run `{cmd[0]}` — is it on your PATH?", file=_sys.stderr)
            return 1
        if rc != 0:
            print("Upgrade command failed.", file=_sys.stderr)
            if kind == "pip":
                print(
                    "If the error above mentions 'externally-managed-environment', "
                    "this Python is managed by your OS or package manager. Install "
                    "codebeacon with pipx (`pipx install codebeacon`) or inside a "
                    "virtualenv instead.",
                    file=_sys.stderr,
                )
            return rc

        # Verify the upgrade actually took effect — a "successful" command
        # that leaves the old version in place should be reported, not hidden.
        new_version = _installed_version(_sys.executable)
        if new_version and new_version != _current:
            print(f"Upgraded: codebeacon {_current} -> {new_version}", flush=True)
        elif new_version == _current:
            if latest and latest != _current:
                print(
                    f"Warning: still on codebeacon {_current} after the upgrade, "
                    f"but PyPI has {latest}. The `codebeacon` on your PATH may "
                    "belong to a different Python environment — check "
                    "`which codebeacon` (or `where codebeacon` on Windows).",
                    file=_sys.stderr,
                )
            else:
                print("Already up to date.", flush=True)

    # Refresh SKILL.md by reinvoking the install command. We exec it in a
    # subprocess so the freshly-installed entry point is used (the current
    # process is still running the OLD code from before pip upgrade).
    print("\nRefreshing /codebeacon Claude Code skill ...", flush=True)
    rc = subprocess.call([_sys.executable, "-m", "codebeacon", "install"])
    if rc != 0:
        return rc

    print(
        "\nUpgrade complete. Restart your Claude Code session so the new "
        "SKILL.md is loaded.",
        flush=True,
    )
    return 0


def _cmd_semantic_prepare(args: argparse.Namespace) -> int:
    from codebeacon.semantic_pipeline import prepare

    beacon_dir = Path(args.dir).resolve()
    try:
        result = prepare(
            beacon_dir,
            max_tasks=args.max_tasks,
            chunk_size=args.chunk_size,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(
        f"semantic-prepare: {result.new_tasks} new task(s) across "
        f"{result.chunks} chunk(s) → {result.pending_dir}\n"
        f"  re-applied {result.reapplied_edges} archived edge(s); "
        f"pruned {result.pruned_archive} stale; archive size: {result.archive_size}"
    )
    return 0


def _cmd_affected(args: argparse.Namespace) -> int:
    """``codebeacon affected`` — list graph nodes downstream of a diff."""
    from codebeacon.affected import affected_from_paths, git_changed_files

    beacon_dir = Path(getattr(args, "dir", ".codebeacon"))
    if not beacon_dir.is_absolute():
        beacon_dir = Path.cwd() / beacon_dir

    paths = list(getattr(args, "paths", []) or [])
    base = getattr(args, "base", None)
    if base:
        head = getattr(args, "head", "HEAD") or "HEAD"
        paths.extend(git_changed_files(base, head))

    if not paths:
        print(
            "Error: no changed paths supplied. Pass file paths positionally or "
            "use --base <ref> [--head <ref>] to derive them from git.",
            file=sys.stderr,
        )
        return 1

    output_format = (getattr(args, "as_format", None) or "markdown").lower()
    try:
        result = affected_from_paths(
            beacon_dir,
            paths,
            depth=int(getattr(args, "depth", 3)),
            limit=int(getattr(args, "limit", 100)),
            include_wiki_paths=(output_format == "wiki"),
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if output_format == "wiki":
        # The output is intentionally machine-readable: one wiki path per
        # line, no banner, no markdown — pipe directly into ``cat`` or
        # feed to an agent prompt without parsing. Empty stdout (no wiki
        # paths) means "no affected article" — exit 0 still, the diff
        # itself is informative.
        rendered = result.as_wiki_paths(base=str(beacon_dir / "wiki"))
        if rendered:
            print(rendered)
        return 0

    print(result.as_markdown())
    return 0


def _cmd_semantic_apply(args: argparse.Namespace) -> int:
    from codebeacon.semantic_pipeline import DEFAULT_MIN_CONFIDENCE_SCORE, apply

    beacon_dir = Path(args.dir).resolve()
    min_conf = getattr(args, "min_confidence", None)
    if min_conf is None:
        min_conf = DEFAULT_MIN_CONFIDENCE_SCORE
    try:
        result = apply(beacon_dir, min_confidence=min_conf)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(
        f"semantic-apply: applied {result.applied} edge(s), "
        f"skipped {result.skipped}; archived {result.chunks_archived} chunk(s); "
        f"archive size: {result.archive_size}"
    )

    # Surface hallucination/coercion stats so a regression in the LLM step
    # is visible without diffing beacon.json. The full breakdown lives in
    # .codebeacon/semantic-stats.json.
    stats = result.stats
    if stats is not None and stats.edges_total:
        drop_pct = (stats.edges_dropped_low_confidence / stats.edges_total) * 100
        coerce_pct = (stats.relations_coerced / stats.edges_total) * 100
        print(
            f"  edges seen: {stats.edges_total} | "
            f"low-confidence dropped: {stats.edges_dropped_low_confidence} ({drop_pct:.1f}%) | "
            f"unknown relations coerced: {stats.relations_coerced} ({coerce_pct:.1f}%) | "
            f"min_confidence={min_conf}"
        )
        if stats.unknown_relation_labels:
            top = sorted(stats.unknown_relation_labels.items(), key=lambda kv: -kv[1])[:5]
            top_str = ", ".join(f"{k}={v}" for k, v in top)
            print(f"  top unknown labels: {top_str}")
    # Zero-yield guard: if the agent processed at least one chunk but produced
    # zero usable edges, the LLM step almost certainly silently failed (bad
    # JSON, empty completions, wrong schema). CI relies on the exit code to
    # catch this — printing a friendly message and returning 0 would hide it.
    # Mirrors graphify #3238b32.
    if result.chunks_archived > 0 and result.applied == 0:
        print(
            "semantic-apply: every chunk archived 0 edges. The skill output "
            "is likely malformed (bad JSON, empty completions, or wrong "
            "schema). Inspect semantic/results/*.jsonl before re-running.",
            file=sys.stderr,
        )
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codebeacon",
        description="Source code AST analysis for AI context generation",
    )
    parser.add_argument("--version", action="version", version=f"codebeacon {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # scan
    scan_p = sub.add_parser("scan", help="Scan one or more project directories")
    scan_p.add_argument("paths", nargs="+", metavar="PATH", help="Project or workspace path(s)")
    scan_p.add_argument("--semantic", action="store_true", help="Enable LLM semantic extraction")
    scan_p.add_argument("--update", action="store_true", help="Only reprocess changed files")
    scan_p.add_argument("--watch", action="store_true", help="Watch for file changes (coming soon)")
    scan_p.add_argument("--wiki-only", action="store_true", help="Only generate wiki")
    scan_p.add_argument("--obsidian-dir", metavar="PATH", help="Custom Obsidian vault path")
    scan_p.add_argument("--list-only", action="store_true", help="Only list detected projects, don't extract")
    scan_p.add_argument(
        "--deep-dive",
        action="store_true",
        help="Generate per-project .codebeacon/ + CLAUDE.md for each sub-project, plus a combined workspace output",
    )
    scan_p.add_argument(
        "--no-rediscover",
        action="store_true",
        help="When auto-switching to sync mode, do NOT scan the workspace for newly added projects",
    )
    scan_p.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=[],
        help="Extra gitignore-style pattern to skip (repeatable). Merged with .codebeaconignore/.gitignore.",
    )
    scan_p.add_argument(
        "--max-failure-rate", type=float, default=None,
        metavar="RATE",
        help="Fail (non-zero exit) when extraction failure rate exceeds RATE (0.0-1.0). Default 0.01 = 1%%.",
    )
    scan_p.set_defaults(func=_cmd_scan)

    # sync
    sync_p = sub.add_parser("sync", help="Run extraction based on codebeacon.yaml")
    sync_p.add_argument("--config", metavar="FILE", help="Path to codebeacon.yaml")
    sync_p.add_argument("--semantic", action="store_true")
    sync_p.add_argument("--update", action="store_true")
    sync_p.add_argument(
        "--deep-dive",
        action="store_true",
        help="Override config: force deep-dive mode",
    )
    sync_p.add_argument(
        "--no-rediscover",
        action="store_true",
        help="Skip scanning the workspace for newly added projects",
    )
    sync_p.add_argument(
        "--exclude",
        metavar="PATTERN",
        action="append",
        default=[],
        help="Extra gitignore-style pattern to skip (repeatable). Merged with .codebeaconignore/.gitignore.",
    )
    sync_p.add_argument(
        "--max-failure-rate", type=float, default=None,
        metavar="RATE",
        help="Fail (non-zero exit) when extraction failure rate exceeds RATE (0.0-1.0). Default 0.01 = 1%%.",
    )
    sync_p.set_defaults(func=_cmd_sync)

    # init
    init_p = sub.add_parser("init", help="Interactively create codebeacon.yaml")
    init_p.add_argument("path", nargs="?", default="", help="Target directory (default: cwd)")
    init_p.set_defaults(func=_cmd_init)

    # query
    query_p = sub.add_parser("query", help="Search nodes and edges in the graph")
    query_p.add_argument("term", help="Search term (case-insensitive substring)")
    query_p.add_argument("--dir", metavar="DIR", default=".codebeacon",
                         help="Path to .codebeacon output directory (default: .codebeacon)")
    query_p.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    query_p.set_defaults(func=_cmd_query)

    # path
    path_p = sub.add_parser("path", help="Find shortest path between two nodes")
    path_p.add_argument("source", help="Source node name")
    path_p.add_argument("target", help="Target node name")
    path_p.add_argument("--dir", metavar="DIR", default=".codebeacon",
                        help="Path to .codebeacon output directory (default: .codebeacon)")
    path_p.set_defaults(func=_cmd_path)

    # serve
    serve_p = sub.add_parser("serve", help="Start MCP server (stdio)")
    serve_p.add_argument(
        "--dir",
        metavar="DIR",
        default=".codebeacon",
        help="Path to .codebeacon output directory (default: .codebeacon)",
    )
    serve_p.set_defaults(func=_cmd_serve)

    # install (Claude Code skill)
    install_p = sub.add_parser("install", help="Install Claude Code skill")
    install_p.add_argument(
        "--project",
        nargs="?",
        const=".",
        default=None,
        metavar="PATH",
        help="Install into <PATH>/.claude/ instead of ~/.claude/ (default: cwd)",
    )
    install_p.set_defaults(func=_cmd_install)

    # upgrade (pip upgrade + refresh skill)
    upgrade_p = sub.add_parser(
        "upgrade",
        help="Upgrade codebeacon via pip and refresh ~/.claude/skills/codebeacon/SKILL.md",
    )
    upgrade_p.add_argument(
        "--force", action="store_true",
        help="Upgrade even when codebeacon is installed in editable (-e) mode",
    )
    upgrade_p.set_defaults(func=_cmd_upgrade)

    # semantic-prepare
    sem_prep = sub.add_parser(
        "semantic-prepare",
        help="Pick AI-semantic candidate files and write .codebeacon/semantic-tasks.jsonl",
    )
    sem_prep.add_argument(
        "--dir", metavar="DIR", default=".codebeacon",
        help="Path to .codebeacon output directory (default: .codebeacon)",
    )
    sem_prep.add_argument(
        "--max-tasks", type=int, default=0,
        help="Cap on new tasks to emit; 0 = no cap, emit every scored candidate (default: 0)",
    )
    sem_prep.add_argument(
        "--chunk-size", type=int, default=20,
        help="Tasks per chunk file (default: 20)",
    )
    sem_prep.set_defaults(func=_cmd_semantic_prepare)

    # semantic-apply
    sem_apply = sub.add_parser(
        "semantic-apply",
        help="Merge .codebeacon/semantic-results.jsonl edges into beacon.json + regenerate wiki",
    )
    sem_apply.add_argument(
        "--dir", metavar="DIR", default=".codebeacon",
        help="Path to .codebeacon output directory (default: .codebeacon)",
    )
    sem_apply.add_argument(
        "--min-confidence", type=float, default=None,
        metavar="SCORE",
        help="Drop LLM edges with confidence_score below this threshold (0.0-1.0). Default: 0.5.",
    )
    sem_apply.set_defaults(func=_cmd_semantic_apply)

    # affected — graph blast radius for a set of changed files / a git diff
    aff_p = sub.add_parser(
        "affected",
        help="List graph nodes affected by changed files or a git diff",
    )
    aff_p.add_argument("paths", nargs="*", metavar="PATH", help="Changed file paths")
    aff_p.add_argument(
        "--base", metavar="REF",
        help="Git ref to diff against (e.g. main, origin/main, HEAD~5)",
    )
    aff_p.add_argument(
        "--head", metavar="REF", default="HEAD",
        help="Git ref for the new side of the diff (default: HEAD)",
    )
    aff_p.add_argument(
        "--depth", type=int, default=3,
        help="Max upstream hops to walk (default 3)",
    )
    aff_p.add_argument(
        "--limit", type=int, default=100,
        help="Max nodes to print (default 100)",
    )
    aff_p.add_argument(
        "--dir", metavar="DIR", default=".codebeacon",
        help="Path to .codebeacon output directory (default: .codebeacon)",
    )
    aff_p.add_argument(
        "--as", dest="as_format", metavar="FORMAT",
        choices=["markdown", "wiki"], default="markdown",
        help="Output format: 'markdown' (default, human-readable) or 'wiki' (one wiki article path per line).",
    )
    aff_p.set_defaults(func=_cmd_affected)

    # merge-driver (git plumbing — invoked by git, not directly by humans)
    md_p = sub.add_parser(
        "merge-driver",
        help="Git merge driver for beacon.json (invoked by git after 'codebeacon hook install')",
    )
    md_p.add_argument("base", help="Path to base version of beacon.json")
    md_p.add_argument("current", help="Path to current (HEAD) version; merged result is written here")
    md_p.add_argument("other", help="Path to other branch's version")
    md_p.set_defaults(func=_cmd_merge_driver)

    # knowledge — map .md notes (ADRs, meetings, retros, specs) into KNOWLEDGE.md
    knowledge_p = sub.add_parser(
        "knowledge",
        help="Scan markdown notes (ADRs, meetings, retros, specs) → KNOWLEDGE.md",
    )
    knowledge_p.add_argument(
        "path", nargs="?", default=".",
        help="Directory to scan recursively (default: cwd)",
    )
    knowledge_p.add_argument(
        "--output-dir", metavar="DIR", default=None,
        help="Where to write KNOWLEDGE.md (default: scanned path)",
    )
    knowledge_p.set_defaults(func=_cmd_knowledge)

    # hook install
    hook_p = sub.add_parser("hook", help="Install git hooks + merge driver in the current repo")
    hook_sub = hook_p.add_subparsers(dest="hook_action", metavar="<action>")
    hook_sub.required = True
    hook_install = hook_sub.add_parser("install", help="Install hooks in the repo at PATH (default: cwd)")
    hook_install.add_argument("path", nargs="?", default=".", help="Repository path (default: cwd)")
    hook_p.set_defaults(func=_cmd_hook)

    return parser


# Known subcommands — used by main() to decide whether a bare first arg should
# be auto-dispatched to ``scan``. Keep this in sync with ``build_parser()``.
_KNOWN_SUBCOMMANDS: set[str] = {
    "scan", "sync", "init", "query", "path", "serve", "install", "upgrade",
    "semantic-prepare", "semantic-apply", "affected", "merge-driver",
    "hook", "knowledge",
}


def _maybe_inject_scan(argv: list[str]) -> list[str]:
    """If the first positional arg is a path-like value, prepend ``scan``.

    Mirrors graphify's ``graphify <path>`` shortcut. Anything starting with
    ``-`` is a flag, anything in ``_KNOWN_SUBCOMMANDS`` is a real subcommand,
    and ``--version``/``--help`` are left alone. Everything else (a path, a
    URL, or a typo) becomes ``scan <arg>`` so users don't see an unfriendly
    ``unknown command`` error for the most common invocation.
    """
    if not argv:
        return argv
    first = argv[0]
    if first in _KNOWN_SUBCOMMANDS:
        return argv
    if first.startswith("-"):
        return argv
    return ["scan", *argv]


def _ensure_utf8_stdio() -> None:
    """Stop ``UnicodeEncodeError`` from killing a command on a non-UTF-8 console.

    Our output uses non-ASCII glyphs (``→``, ``⚠``, box-drawing) in warnings and
    reports. On Windows the default console codepage is cp1252, where a single
    ``print("⚠ ...")`` raises ``UnicodeEncodeError`` and aborts the whole
    command. Forcing each stream to UTF-8 with ``errors="replace"`` degrades a
    legacy console to mojibake instead of crashing. Best-effort: streams that
    are redirected, detached, or lack ``reconfigure`` are left untouched.
    Mirrors graphify #992.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # Stream already detached/closed or doesn't support reconfigure.
            pass


def main() -> None:
    _ensure_utf8_stdio()
    parser = build_parser()
    argv = _maybe_inject_scan(sys.argv[1:])
    args = parser.parse_args(argv)
    sys.exit(args.func(args))
