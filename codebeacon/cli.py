"""codebeacon CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codebeacon import __version__


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
        if config_path:
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

    deep_dive = getattr(args, "deep_dive", False)

    # Auto-generate codebeacon.yaml on multi-project first scan
    if multi and len(args.paths) == 1:
        yaml_path = output_base / "codebeacon.yaml"
        if not yaml_path.exists():
            generate_config(projects, output_dir, yaml_path, deep_dive=deep_dive)
            print(f"  Generated {yaml_path} — next time run: codebeacon sync")

    if args.list_only:
        return 0

    if deep_dive:
        return _run_deep_dive_pipeline(projects, output_dir, args)
    return _run_pipeline(projects, output_dir, args)


def _run_pipeline(projects, output_dir: str, args) -> int:
    """Run the full extraction pipeline for a list of projects."""
    from codebeacon.graph.analyze import analyze, report_to_markdown
    import json
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    wiki_only = getattr(args, "wiki_only", False)

    if wiki_only:
        # --wiki-only: skip extraction, load existing graph and regenerate outputs
        beacon_path = output_path / "beacon.json"
        if not beacon_path.exists():
            print(
                f"Error: {beacon_path} not found. Run a full scan first before using --wiki-only.",
                file=sys.stderr,
            )
            return 1

        import networkx.readwrite.json_graph as nxjson
        data = json.loads(beacon_path.read_text(encoding="utf-8"))
        G = nxjson.node_link_graph(data, directed=True, multigraph=False)
        print(f"  Loaded graph from {beacon_path}")
        print(f"    Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

        # Reconstruct communities from node attributes set by a prior scan
        communities: dict = {}
        for node_id, node_data in G.nodes(data=True):
            if "community" in node_data:
                communities[node_id] = node_data["community"]
        n_communities = len(set(communities.values())) if communities else 0

        report = analyze(G, communities, {})
    else:
        from codebeacon.discover.scanner import collect_files
        from codebeacon.cache import Cache
        from codebeacon.wave import auto_wave
        from codebeacon.graph.build import build_graph
        from codebeacon.graph.enrich import enrich_http_api, enrich_shared_db, enrich_ipc_invoke
        from codebeacon.graph.cluster import cluster, apply_communities, score_all

        cache = Cache(output_dir)
        if getattr(args, "update", False):
            cache.load()
        else:
            cache = None  # fresh scan, no cache

        wave_results = []
        for project in projects:
            print(f"\n  Extracting {project.name} ({project.framework}) ...")
            files = collect_files(project.path)
            print(f"    {len(files)} source files found")

            def progress(done, total, _name=project.name):
                pct = int(done / total * 100) if total else 100
                print(f"    [{pct:3d}%] {done}/{total} files processed", end="\r")

            wave = auto_wave(
                project=project,
                files=files,
                chunk_size=300,
                max_parallel=5,
                cache=cache,
                progress_callback=progress,
                semantic=getattr(args, "semantic", False),
            )
            print()  # newline after progress

            stats = (
                f"    Routes: {len(wave.routes)}, Services: {len(wave.services)}, "
                f"Entities: {len(wave.entities)}, Components: {len(wave.components)}"
            )
            if wave.skipped_count:
                stats += f" (cache hits: {wave.skipped_count})"
            print(stats)
            wave_results.append(wave)

        if cache is not None:
            cache.save()

        print("\n  Building knowledge graph ...")
        G = build_graph(wave_results)
        print(f"    Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

        # Enrichment
        api_edges = enrich_http_api(G)
        db_edges = enrich_shared_db(G)
        ipc_edges = enrich_ipc_invoke(G)
        enriched_parts = []
        if api_edges: enriched_parts.append(f"+{api_edges} calls_api")
        if db_edges: enriched_parts.append(f"+{db_edges} shares_db_entity")
        if ipc_edges: enriched_parts.append(f"+{ipc_edges} invokes_command")
        if enriched_parts:
            print(f"    Enriched: {', '.join(enriched_parts)} edges")

        # Community detection
        print("  Detecting communities ...")
        communities = cluster(G)
        apply_communities(G, communities)
        cohesion = score_all(G, communities)
        n_communities = len(set(communities.values())) if communities else 0
        print(f"    {n_communities} communities detected")

        # Analysis
        report = analyze(G, communities, cohesion, project_paths={p.name: p.path for p in projects})

        # Save outputs
        import networkx.readwrite.json_graph as nxjson
        beacon_path = output_path / "beacon.json"
        beacon_path.write_text(
            json.dumps(nxjson.node_link_data(G), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        report_path = output_path / "REPORT.md"
        report_path.write_text(report_to_markdown(report), encoding="utf-8")

    # Wiki generation (always runs — whether full scan or --wiki-only)
    print("  Generating wiki ...")
    from codebeacon.wiki.generator import generate_wiki
    generate_wiki(G, communities, output_dir)
    print(f"    Wiki written to {output_dir}/wiki/")

    # Obsidian vault generation
    obsidian_dir = getattr(args, "obsidian_dir", None)
    print("  Generating Obsidian vault ...")
    from codebeacon.export.obsidian import generate_obsidian_vault
    n_notes = generate_obsidian_vault(G, communities, output_dir, obsidian_dir=obsidian_dir)
    print(f"    {n_notes} notes written to {obsidian_dir or output_dir + '/obsidian'}/")

    # Context Map generation (CLAUDE.md / .cursorrules / AGENTS.md)
    print("  Generating context map ...")
    from codebeacon.contextmap.generator import generate_context_map
    written = generate_context_map(
        G=G,
        output_dir=output_dir,
        projects=projects,
        obsidian_dir=obsidian_dir,
    )
    for path in written:
        print(f"    {path}")

    print(f"\n  Output: {output_dir}")
    if wiki_only:
        print(f"    wiki/, obsidian/, CLAUDE.md regenerated from existing graph")
    else:
        print(f"    beacon.json, REPORT.md, wiki/, obsidian/, CLAUDE.md written")
    print(f"  Done. {report.node_count} nodes, {report.edge_count} edges, {n_communities} communities.")
    return 0


def _run_deep_dive_pipeline(projects, workspace_output_dir: str, args) -> int:
    """Run deep-dive pipeline: per-project outputs + combined workspace output.

    Phase 1 — Extract each project with its own per-project cache.
    Phase 2 — Build a per-project graph and write outputs under project/.codebeacon/.
    Phase 3 — Build a combined workspace graph and write outputs under workspace/.codebeacon/.

    Claude Code loads CLAUDE.md hierarchically, so opening a session in a sub-project
    directory loads both the parent workspace overview AND the project-specific details.
    """
    import json
    from pathlib import Path
    from codebeacon.graph.analyze import analyze, report_to_markdown
    from codebeacon.graph.build import build_graph
    from codebeacon.graph.enrich import enrich_http_api, enrich_shared_db, enrich_ipc_invoke
    from codebeacon.graph.cluster import cluster, apply_communities, score_all
    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.contextmap.generator import generate_context_map
    import networkx.readwrite.json_graph as nxjson

    workspace_path = Path(workspace_output_dir)
    wiki_only = getattr(args, "wiki_only", False)
    obsidian_dir = getattr(args, "obsidian_dir", None)

    if len(projects) <= 1:
        print(
            "Warning: --deep-dive with a single project produces identical per-project "
            "and workspace outputs. Running standard pipeline instead.",
            file=sys.stderr,
        )
        return _run_pipeline(projects, workspace_output_dir, args)

    # ── Phase 1: Extract all projects ──────────────────────────────────────────
    # project_waves tracks (project, wave_result) pairs explicitly so that index
    # alignment never diverges even if one project's extraction is skipped.
    project_waves: list[tuple] = []

    if not wiki_only:
        from codebeacon.discover.scanner import collect_files
        from codebeacon.cache import Cache
        from codebeacon.wave import auto_wave

        for project in projects:
            proj_output_dir = str(Path(project.path) / ".codebeacon")

            cache = None
            if getattr(args, "update", False):
                cache = Cache(proj_output_dir)
                cache.load()

            print(f"\n  Extracting {project.name} ({project.framework}) ...")
            files = collect_files(project.path)
            print(f"    {len(files)} source files found")

            def progress(done, total, _name=project.name):
                pct = int(done / total * 100) if total else 100
                print(f"    [{pct:3d}%] {done}/{total} files processed", end="\r")

            wave = auto_wave(
                project=project,
                files=files,
                chunk_size=300,
                max_parallel=5,
                cache=cache,
                progress_callback=progress,
                semantic=getattr(args, "semantic", False),
            )
            print()  # newline after progress

            stats_str = (
                f"    Routes: {len(wave.routes)}, Services: {len(wave.services)}, "
                f"Entities: {len(wave.entities)}, Components: {len(wave.components)}"
            )
            if wave.skipped_count:
                stats_str += f" (cache hits: {wave.skipped_count})"
            print(stats_str)

            if cache is not None:
                cache.save()

            project_waves.append((project, wave))

    # ── Phase 2: Per-project graph + outputs ───────────────────────────────────
    print("\n  Generating per-project outputs ...")

    if wiki_only:
        for project in projects:
            proj_output_dir = str(Path(project.path) / ".codebeacon")
            beacon_path = Path(proj_output_dir) / "beacon.json"
            if not beacon_path.exists():
                print(
                    f"  Warning: {beacon_path} not found — skipping {project.name}.",
                    file=sys.stderr,
                )
                continue

            data = json.loads(beacon_path.read_text(encoding="utf-8"))
            G = nxjson.node_link_graph(data, directed=True, multigraph=False)
            communities: dict = {}
            for node_id, node_data in G.nodes(data=True):
                if "community" in node_data:
                    communities[node_id] = node_data["community"]
            report = analyze(G, communities, {})
            n_communities = len(set(communities.values())) if communities else 0

            _write_project_artifact_outputs(
                G, communities, project, proj_output_dir,
            )
    else:
        for project, wave in project_waves:
            proj_output_dir = str(Path(project.path) / ".codebeacon")
            Path(proj_output_dir).mkdir(parents=True, exist_ok=True)

            print(f"\n  Building graph for {project.name} ...")
            G = build_graph([wave])
            print(f"    Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

            api_edges = enrich_http_api(G)
            db_edges = enrich_shared_db(G)
            if api_edges or db_edges:
                print(f"    Enriched: +{api_edges} calls_api, +{db_edges} shares_db_entity edges")

            communities = cluster(G)
            apply_communities(G, communities)
            cohesion = score_all(G, communities)
            n_communities = len(set(communities.values())) if communities else 0
            print(f"    {n_communities} communities")

            report = analyze(G, communities, cohesion, project_paths={project.name: project.path})

            beacon_path = Path(proj_output_dir) / "beacon.json"
            beacon_path.write_text(
                json.dumps(nxjson.node_link_data(G), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (Path(proj_output_dir) / "REPORT.md").write_text(
                report_to_markdown(report), encoding="utf-8"
            )

            _write_project_artifact_outputs(
                G, communities, project, proj_output_dir,
            )

    # ── Phase 3: Combined workspace graph + outputs ────────────────────────────
    print("\n  Building combined workspace graph ...")
    workspace_path.mkdir(parents=True, exist_ok=True)

    if wiki_only:
        beacon_path = workspace_path / "beacon.json"
        if not beacon_path.exists():
            print(
                f"  Error: {beacon_path} not found. Run a full scan first before using --wiki-only.",
                file=sys.stderr,
            )
            return 1
        data = json.loads(beacon_path.read_text(encoding="utf-8"))
        G_all = nxjson.node_link_graph(data, directed=True, multigraph=False)
        print(f"  Loaded combined graph from {beacon_path}")
        print(f"    Nodes: {G_all.number_of_nodes()}, Edges: {G_all.number_of_edges()}")
        communities_all: dict = {}
        for node_id, node_data in G_all.nodes(data=True):
            if "community" in node_data:
                communities_all[node_id] = node_data["community"]
        n_communities_all = len(set(communities_all.values())) if communities_all else 0
        report_all = analyze(G_all, communities_all, {})
    else:
        all_waves = [w for _, w in project_waves]
        G_all = build_graph(all_waves)
        print(f"    Nodes: {G_all.number_of_nodes()}, Edges: {G_all.number_of_edges()}")

        api_edges = enrich_http_api(G_all)
        db_edges = enrich_shared_db(G_all)
        if api_edges or db_edges:
            print(f"    Enriched: +{api_edges} calls_api, +{db_edges} shares_db_entity edges")

        print("  Detecting communities ...")
        communities_all = cluster(G_all)
        apply_communities(G_all, communities_all)
        cohesion_all = score_all(G_all, communities_all)
        n_communities_all = len(set(communities_all.values())) if communities_all else 0
        print(f"    {n_communities_all} communities detected")

        report_all = analyze(G_all, communities_all, cohesion_all, project_paths={p.name: p.path for p in projects})

        beacon_path = workspace_path / "beacon.json"
        beacon_path.write_text(
            json.dumps(nxjson.node_link_data(G_all), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (workspace_path / "REPORT.md").write_text(
            report_to_markdown(report_all), encoding="utf-8"
        )

    print("  Generating combined wiki ...")
    generate_wiki(G_all, communities_all, workspace_output_dir)
    print(f"    Wiki written to {workspace_output_dir}/wiki/")

    print("  Generating combined Obsidian vault ...")
    n_notes = generate_obsidian_vault(
        G_all, communities_all, workspace_output_dir, obsidian_dir=obsidian_dir
    )
    print(f"    {n_notes} notes written to {obsidian_dir or workspace_output_dir + '/obsidian'}/")

    print("  Generating combined context map ...")
    written = generate_context_map(
        G=G_all,
        output_dir=workspace_output_dir,
        projects=projects,
        obsidian_dir=obsidian_dir,
    )
    for path in written:
        print(f"    {path}")

    print(f"\n  Output: {workspace_output_dir}")
    if wiki_only:
        print(f"    Combined wiki/, obsidian/, CLAUDE.md regenerated from existing graphs.")
        print(f"    Per-project wiki/, obsidian/, CLAUDE.md also regenerated.")
    else:
        print(f"    beacon.json, REPORT.md, wiki/, obsidian/, CLAUDE.md written (workspace + per-project).")
    print(
        f"  Done. {report_all.node_count} nodes, {report_all.edge_count} edges, "
        f"{n_communities_all} communities (combined workspace)."
    )
    return 0


def _write_project_artifact_outputs(G, communities, project, proj_output_dir: str) -> None:
    """Write wiki, obsidian, and context map for a single project's output directory.

    Per-project obsidian always lands inside proj_output_dir/obsidian/ (no custom path),
    keeping each project self-contained under its own .codebeacon/ directory.
    """
    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.contextmap.generator import generate_context_map

    print(f"  [{project.name}] Generating wiki ...")
    generate_wiki(G, communities, proj_output_dir)

    print(f"  [{project.name}] Generating Obsidian vault ...")
    generate_obsidian_vault(G, communities, proj_output_dir, obsidian_dir=None)

    print(f"  [{project.name}] Generating context map ...")
    written = generate_context_map(
        G=G,
        output_dir=proj_output_dir,
        projects=[project],
        obsidian_dir=None,
    )
    for path in written:
        print(f"    {path}")


def _cmd_sync(args: argparse.Namespace) -> int:
    from codebeacon.config import load_config, find_config
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
        return _run_deep_dive_pipeline(projects_info, output_dir, args)
    return _run_pipeline(projects_info, output_dir, args)


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
    print(f"[query] Not yet implemented (Task 8). Query: {args.term}")
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    print(f"[path] Not yet implemented (Task 8). From: {args.source}, To: {args.target}")
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

    claude_dir = Path.home() / ".claude"
    skills_dir = claude_dir / "skills" / "codebeacon"
    skill_dest = skills_dir / "SKILL.md"
    claude_md = claude_dir / "CLAUDE.md"

    skills_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dest)
    print(f"  Copied SKILL.md → {skill_dest}")

    trigger_block = (
        "\n# codebeacon\n"
        "- **codebeacon** (`~/.claude/skills/codebeacon/SKILL.md`) - scan source code → knowledge graph + wiki. Trigger: `/codebeacon`\n"
        "When the user types `/codebeacon`, invoke the Skill tool with `skill: \"codebeacon\"` before doing anything else.\n"
    )
    existing = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
    if "# codebeacon" in existing:
        print(f"  Trigger already present in {claude_md} — skipping.")
    else:
        separator = "\n" if existing and not existing.endswith("\n\n") else ""
        claude_md.write_text(existing + separator + trigger_block, encoding="utf-8")
        print(f"  Added codebeacon trigger to {claude_md}")

    print("\ncodebeacon skill installed.")
    print("Start a new Claude Code session and type /codebeacon to use it.")
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
    sync_p.set_defaults(func=_cmd_sync)

    # init
    init_p = sub.add_parser("init", help="Interactively create codebeacon.yaml")
    init_p.add_argument("path", nargs="?", default="", help="Target directory (default: cwd)")
    init_p.set_defaults(func=_cmd_init)

    # query
    query_p = sub.add_parser("query", help="Search nodes and edges in the graph")
    query_p.add_argument("term", help="Search term")
    query_p.set_defaults(func=_cmd_query)

    # path
    path_p = sub.add_parser("path", help="Find shortest path between two nodes")
    path_p.add_argument("source", help="Source node name")
    path_p.add_argument("target", help="Target node name")
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

    # install
    install_p = sub.add_parser("install", help="Install Claude Code skill")
    install_p.set_defaults(func=_cmd_install)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
