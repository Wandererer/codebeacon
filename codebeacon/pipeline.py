"""Single-project and deep-dive extraction pipelines.

Extracted from cli.py in 0.6.0 to keep the CLI module focused on argument
parsing and dispatch. Public entry points:

  * ``run_pipeline(projects, output_dir, args)`` — one combined graph for
    every supplied project; writes ``<output_dir>/beacon.json`` + outputs.
  * ``run_deep_dive_pipeline(projects, workspace_output_dir, args)`` —
    per-project ``.codebeacon/`` outputs plus a combined workspace output.

Both honour ``args.max_failure_rate`` via ``emit_failure_report``: if more
than 1% of attempted files failed extraction (configurable), the pipeline
returns a non-zero exit code instead of writing a partial graph.
"""
from __future__ import annotations

import sys
from pathlib import Path


def emit_failure_report(waves, output_dir: str, args) -> int:
    """Write extraction-failures.json, print summary, return non-zero exit if rate breached.

    Centralised so both ``run_pipeline`` and ``run_deep_dive_pipeline``
    enforce identical thresholds. A repo with N projects gets ONE merged
    report at the workspace root so CI can grep a single file.
    """
    from codebeacon.diagnostics import (
        DEFAULT_MAX_FAILURE_RATE,
        write_extraction_failures,
    )

    report, path = write_extraction_failures(waves, output_dir)
    if report.total_failures == 0:
        return 0

    threshold = getattr(args, "max_failure_rate", None)
    if threshold is None:
        threshold = DEFAULT_MAX_FAILURE_RATE

    pct = report.failure_rate * 100
    print(
        f"\n  Extraction failures: {report.total_failures}/{report.total_attempted} "
        f"files ({pct:.2f}%) — see {path}",
        file=sys.stderr,
    )
    top_errors = sorted(report.by_error_type.items(), key=lambda kv: -kv[1])[:3]
    if top_errors:
        summary = ", ".join(f"{k}={v}" for k, v in top_errors)
        print(f"    Top error types: {summary}", file=sys.stderr)

    if report.failure_rate > threshold:
        print(
            f"  ERROR: failure rate {pct:.2f}% exceeds threshold "
            f"{threshold * 100:.2f}% — partial graph likely. "
            f"Inspect {path} or pass --max-failure-rate to relax.",
            file=sys.stderr,
        )
        return 2
    return 0


def run_pipeline(projects, output_dir: str, args) -> int:
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

        from codebeacon.graph.write import load_beacon
        G, meta = load_beacon(beacon_path)
        print(f"  Loaded graph from {beacon_path}")
        print(f"    Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

        # Reconstruct communities from node attributes set by a prior scan
        communities: dict = {}
        for node_id, node_data in G.nodes(data=True):
            if "community" in node_data:
                communities[node_id] = node_data["community"]
        n_communities = len(set(communities.values())) if communities else 0

        report = analyze(G, communities, {})
        report.built_at_commit = meta.get("built_at_commit", "")
        from codebeacon.common.safety import git_head
        report.current_commit = git_head(output_path)
    else:
        from codebeacon.discover.scanner import collect_files
        from codebeacon.cache import Cache
        from codebeacon.wave import auto_wave
        from codebeacon.graph.build import build_graph
        from codebeacon.graph.enrich import (
            enrich_http_api, enrich_shared_db, enrich_ipc_invoke,
            promote_confirmed_calls,
        )
        from codebeacon.graph.cluster import cluster, apply_communities, score_all
        from codebeacon.graph.write import write_beacon
        from codebeacon.export.tree_html import write_tree_html
        from codebeacon.export.callflow_html import write_callflow_html

        # Always carry a cache so each scan populates it for the next run.
        # `--update` controls whether we *load* the existing cache to skip
        # unchanged files; a fresh scan starts with an empty in-memory cache
        # (so every file is re-extracted from scratch) but still writes the
        # cache out, so the next `--update` invocation has something to hit.
        # The project root is passed so cache keys end up repo-relative —
        # makes ``.codebeacon/cache/cache.json`` portable across machines
        # for teams that share the directory in git.
        cache_root = projects[0].path if projects else output_dir
        cache = Cache(output_dir, project_root=cache_root)
        if getattr(args, "update", False):
            cache.load()

        wave_results = []
        extra_ignore = list(getattr(args, "exclude", []) or [])
        for project in projects:
            print(f"\n  Extracting {project.name} ({project.framework}) ...")
            files = collect_files(project.path, extra_ignore=extra_ignore)
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
            if wave.failures:
                print(f"    {len(wave.failures)} files failed extraction (see extraction-failures.json)")
            wave_results.append(wave)

        cache.save()

        # Gate: if extraction failure rate breaches the threshold, write the
        # failures file and bail before producing a half-built graph that
        # would silently mislead downstream wiki / MCP consumers.
        gate = emit_failure_report(wave_results, output_dir, args)
        if gate != 0:
            return gate

        print("\n  Building knowledge graph ...")
        G = build_graph(wave_results)
        print(f"    Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

        # Enrichment
        api_edges = enrich_http_api(G)
        db_edges = enrich_shared_db(G)
        ipc_edges = enrich_ipc_invoke(G)
        promoted = promote_confirmed_calls(G)
        enriched_parts = []
        if api_edges: enriched_parts.append(f"+{api_edges} calls_api")
        if db_edges: enriched_parts.append(f"+{db_edges} shares_db_entity")
        if ipc_edges: enriched_parts.append(f"+{ipc_edges} invokes_command")
        if promoted: enriched_parts.append(f"{promoted} calls promoted to EXTRACTED")
        if enriched_parts:
            print(f"    Enriched: {', '.join(enriched_parts)}")

        # Community detection
        print("  Detecting communities ...")
        communities = cluster(G)
        apply_communities(G, communities)
        cohesion = score_all(G, communities)
        n_communities = len(set(communities.values())) if communities else 0
        print(f"    {n_communities} communities detected")

        # Persist beacon.json first; shrink/desync guard refuses to overwrite a
        # larger prior graph and prevents the report from racing ahead of a
        # half-written graph. In `--update` mode the cache already accounted
        # for deleted files (see Cache.evict_missing), so a smaller graph is
        # the expected outcome and the guard would otherwise fire on every
        # delete-heavy run.
        wr = write_beacon(
            G,
            output_path,
            repo_path=projects[0].path if projects else output_path,
            had_explicit_deletions=getattr(args, "update", False),
            project_roots={p.name: p.path for p in projects},
        )
        if wr.skipped_shrink:
            print(
                "  Aborting outputs because the new graph is smaller than the existing one.",
                file=sys.stderr,
            )
            return 1

        # Analysis (after write, so the report can quote the stamped commit)
        report = analyze(G, communities, cohesion, project_paths={p.name: p.path for p in projects})
        report.built_at_commit = wr.built_at_commit
        report.current_commit = wr.built_at_commit  # same run; not stale yet
        report_path = output_path / "REPORT.md"
        report_path.write_text(report_to_markdown(report), encoding="utf-8")

        # Visual exports — best-effort, never block the pipeline.
        try:
            tree_path = write_tree_html(G, output_path)
            print(f"    Wrote {tree_path.name}")
        except (OSError, ValueError) as exc:
            print(f"    Warning: tree HTML failed: {exc}", file=sys.stderr)
        try:
            flow_path = write_callflow_html(G, output_path)
            print(f"    Wrote {flow_path.name}")
        except (OSError, ValueError) as exc:
            print(f"    Warning: callflow HTML failed: {exc}", file=sys.stderr)

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


def run_deep_dive_pipeline(projects, workspace_output_dir: str, args) -> int:
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
    from codebeacon.graph.enrich import (
        enrich_http_api, enrich_shared_db, enrich_ipc_invoke,
        promote_confirmed_calls,
    )
    from codebeacon.graph.cluster import cluster, apply_communities, score_all
    from codebeacon.graph.write import write_beacon, load_beacon
    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.export.tree_html import write_tree_html
    from codebeacon.export.callflow_html import write_callflow_html
    from codebeacon.contextmap.generator import generate_context_map
    from codebeacon.common.safety import git_head
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
        return run_pipeline(projects, workspace_output_dir, args)

    # ── Phase 1: Extract all projects ──────────────────────────────────────────
    # project_waves tracks (project, wave_result) pairs explicitly so that index
    # alignment never diverges even if one project's extraction is skipped.
    project_waves: list[tuple] = []

    if not wiki_only:
        from codebeacon.discover.scanner import collect_files
        from codebeacon.cache import Cache
        from codebeacon.wave import auto_wave

        extra_ignore = list(getattr(args, "exclude", []) or [])
        for project in projects:
            proj_output_dir = str(Path(project.path) / ".codebeacon")

            # Same rule as the single-project pipeline: always create + save the
            # cache so a fresh scan primes it for the next `--update`. Keys
            # are written repo-relative so cache.json is portable across
            # machines / collaborators.
            cache = Cache(proj_output_dir, project_root=project.path)
            if getattr(args, "update", False):
                cache.load()

            print(f"\n  Extracting {project.name} ({project.framework}) ...")
            files = collect_files(project.path, extra_ignore=extra_ignore)
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
            if wave.failures:
                print(f"    {len(wave.failures)} files failed extraction (see extraction-failures.json)")

            cache.save()

            project_waves.append((project, wave))

        # Gate: workspace-level failure report covering every project.
        gate = emit_failure_report(
            [w for _, w in project_waves], workspace_output_dir, args,
        )
        if gate != 0:
            return gate

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

            G, meta = load_beacon(beacon_path)
            communities: dict = {}
            for node_id, node_data in G.nodes(data=True):
                if "community" in node_data:
                    communities[node_id] = node_data["community"]
            report = analyze(G, communities, {})
            report.built_at_commit = meta.get("built_at_commit", "")
            report.current_commit = git_head(project.path)
            n_communities = len(set(communities.values())) if communities else 0

            write_project_artifact_outputs(
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
            promoted = promote_confirmed_calls(G)
            parts = []
            if api_edges: parts.append(f"+{api_edges} calls_api")
            if db_edges: parts.append(f"+{db_edges} shares_db_entity")
            if promoted: parts.append(f"{promoted} calls promoted")
            if parts:
                print(f"    Enriched: {', '.join(parts)}")

            communities = cluster(G)
            apply_communities(G, communities)
            cohesion = score_all(G, communities)
            n_communities = len(set(communities.values())) if communities else 0
            print(f"    {n_communities} communities")

            wr = write_beacon(
                G,
                proj_output_dir,
                repo_path=project.path,
                had_explicit_deletions=getattr(args, "update", False),
                project_roots={project.name: project.path},
            )
            if wr.skipped_shrink:
                print(
                    f"    Warning: refused to shrink {project.name} graph; keeping prior beacon.json.",
                    file=sys.stderr,
                )

            report = analyze(G, communities, cohesion, project_paths={project.name: project.path})
            report.built_at_commit = wr.built_at_commit
            report.current_commit = wr.built_at_commit
            (Path(proj_output_dir) / "REPORT.md").write_text(
                report_to_markdown(report), encoding="utf-8"
            )

            try:
                write_tree_html(G, proj_output_dir)
                write_callflow_html(G, proj_output_dir)
            except (OSError, ValueError) as exc:
                print(f"    Warning: HTML export failed for {project.name}: {exc}", file=sys.stderr)

            write_project_artifact_outputs(
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
        G_all, meta_all = load_beacon(beacon_path)
        print(f"  Loaded combined graph from {beacon_path}")
        print(f"    Nodes: {G_all.number_of_nodes()}, Edges: {G_all.number_of_edges()}")
        communities_all: dict = {}
        for node_id, node_data in G_all.nodes(data=True):
            if "community" in node_data:
                communities_all[node_id] = node_data["community"]
        n_communities_all = len(set(communities_all.values())) if communities_all else 0
        report_all = analyze(G_all, communities_all, {})
        report_all.built_at_commit = meta_all.get("built_at_commit", "")
        report_all.current_commit = git_head(workspace_output_dir)
    else:
        all_waves = [w for _, w in project_waves]
        G_all = build_graph(all_waves)
        print(f"    Nodes: {G_all.number_of_nodes()}, Edges: {G_all.number_of_edges()}")

        api_edges = enrich_http_api(G_all)
        db_edges = enrich_shared_db(G_all)
        promoted = promote_confirmed_calls(G_all)
        parts = []
        if api_edges: parts.append(f"+{api_edges} calls_api")
        if db_edges: parts.append(f"+{db_edges} shares_db_entity")
        if promoted: parts.append(f"{promoted} calls promoted")
        if parts:
            print(f"    Enriched: {', '.join(parts)}")

        print("  Detecting communities ...")
        communities_all = cluster(G_all)
        apply_communities(G_all, communities_all)
        cohesion_all = score_all(G_all, communities_all)
        n_communities_all = len(set(communities_all.values())) if communities_all else 0
        print(f"    {n_communities_all} communities detected")

        wr_all = write_beacon(
            G_all,
            workspace_path,
            repo_path=workspace_output_dir,
            had_explicit_deletions=getattr(args, "update", False),
            project_roots={p.name: p.path for p in projects},
        )
        if wr_all.skipped_shrink:
            print(
                "  Aborting workspace outputs because the combined graph is smaller than the existing one.",
                file=sys.stderr,
            )
            return 1

        report_all = analyze(G_all, communities_all, cohesion_all, project_paths={p.name: p.path for p in projects})
        report_all.built_at_commit = wr_all.built_at_commit
        report_all.current_commit = wr_all.built_at_commit
        (workspace_path / "REPORT.md").write_text(
            report_to_markdown(report_all), encoding="utf-8"
        )

        try:
            write_tree_html(G_all, workspace_path)
            write_callflow_html(G_all, workspace_path)
        except (OSError, ValueError) as exc:
            print(f"    Warning: workspace HTML export failed: {exc}", file=sys.stderr)

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


def write_project_artifact_outputs(G, communities, project, proj_output_dir: str) -> None:
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
