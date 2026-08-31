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

import os
import sys
from pathlib import Path

from codebeacon.common.io import write_text_if_changed
from codebeacon.diagnostics import IgnoredReport


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


def _run_is_incomplete(waves) -> bool:
    """True when this run could not see the whole corpus.

    Two independent signals, both of which make "this file is gone from the
    corpus, so it must have been ignored" an unsound inference:

      * a file was collected but failed extraction, so its nodes are missing
        even though the file is right there on disk;
      * the walk could not read part of the tree (a chmod-000 directory), so
        those files never reached the corpus at all. ``collect_files`` reports
        that through the scanner's diagnostics; the attribute is read
        defensively because it is only populated by scanners that track it.

    The shrink guard uses this to stay armed instead of mistaking an unreadable
    subtree for a deliberate exclusion.
    """
    for wave in waves or []:
        if getattr(wave, "failures", None):
            return True
    return bool(_unreadable_subtrees())


def _unreadable_subtrees() -> list[str]:
    """Directories the scanner could not descend into during this run.

    Contract with the discover layer: it exposes a zero-argument
    ``unreadable_dirs()`` returning the paths a walk had to skip (today a bare
    ``except PermissionError: return`` loses them silently). Read through
    ``diagnostics`` first and the scanner second so either home works, and
    treated as empty when neither provides it — an absent signal must degrade to
    "no known walk errors", never to an import crash mid-scan.
    """
    for module, attr in (
        ("codebeacon.diagnostics", "unreadable_dirs"),
        ("codebeacon.discover.scanner", "unreadable_dirs"),
    ):
        try:
            mod = __import__(module, fromlist=[attr])
            fn = getattr(mod, attr, None)
            if callable(fn):
                return list(fn() or [])
        except Exception:
            continue
    return []


def _ensure_output_dir(output_path: Path) -> int:
    """Create the output directory, or explain why the scan cannot start.

    Scanning a read-only checkout (a Nix store path, a CI cache mount, a
    third-party tree opened for reading) used to end in an unhandled
    PermissionError traceback from ``mkdir`` before a single file was read.
    The cache half of this is handled inside ``Cache``, which degrades to a
    warning; the graph output has nowhere to go, so it is a clean failure with
    the remedy spelled out. Returns 0 on success, 1 on failure.
    """
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Deliberately does NOT name a flag: `scan` has no --output-dir, and
        # pointing users at an option that does not exist is the same defect
        # the old shrink-guard message had.
        print(
            f"Error: cannot create {output_path} — permission denied.\n"
            f"  codebeacon writes its index into the tree it scans, so a "
            f"read-only checkout cannot be scanned in place. Either make the "
            f"directory writable, or copy the tree somewhere writable and scan "
            f"the copy.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Error: cannot create {output_path} ({exc}).", file=sys.stderr)
        return 1
    return 0


def _cache_anchor(projects, fallback: str) -> str:
    """The directory cache keys are stored relative to.

    Must contain EVERY project, otherwise the projects outside it fall back to
    absolute keys and the cache stops being portable between machines — the
    whole point of relative keying. Anchoring on ``projects[0].path`` did
    exactly that for any repo with more than one project.

    Falls back to the first project when no USEFUL common ancestor exists:
    ``commonpath`` raises on separate Windows drives, and for unrelated trees it
    succeeds with the filesystem root, which is worse than useless — every key
    would then embed its whole absolute path minus the leading slash, i.e.
    exactly the machine-specific keys relative anchoring exists to avoid.
    """
    paths = [p.path for p in projects if getattr(p, "path", None)]
    if not paths:
        return fallback
    if len(paths) == 1:
        return paths[0]
    try:
        anchor = os.path.commonpath([os.path.abspath(p) for p in paths])
    except (ValueError, OSError):
        return paths[0]
    if os.path.dirname(anchor) == anchor:   # filesystem root
        return paths[0]
    return anchor


def _emit_ignored_report(report, output_dir: str) -> None:
    """Write ignored.json and point at it when anything was left out.

    Best-effort: the diagnostic must never be the reason a scan fails.
    """
    from codebeacon.diagnostics import write_ignored_report

    try:
        path = write_ignored_report(report, output_dir)
    except OSError as exc:
        print(f"  Warning: could not write ignored.json ({exc}).", file=sys.stderr)
        return
    if path is None:
        return
    causes = ", ".join(
        f"{reason}={count}"
        for reason, count in sorted(report.counts.items(), key=lambda kv: -kv[1])[:3]
    )
    print(f"    {report.total} paths ignored ({causes}) — see {path.name}")


def _reapply_knowledge_overlay(root, output_path) -> None:
    """Re-mint the knowledge overlay a code-only rebuild has just dropped (R2).

    A scan rebuilds the graph from source, so the note nodes that
    ``codebeacon knowledge`` linked in are gone from the beacon it just wrote.
    Re-running the link pass *here* — after the code graph is final — keeps the
    overlay without weakening the determinism invariant that overlay nodes are
    always minted last.

    ``reapply_knowledge`` is a total function per F10's contract — it never
    raises, and it reports its own failures on stderr. Its return value is the
    whole protocol:

        > 0   that many notes were re-linked; say so.
        0     this repo never opted into an overlay; stay silent.
        -1    an overlay exists but could not be rebuilt; it has already
              warned, so a second message here would only duplicate it.
    """
    from codebeacon.knowledge.link import reapply_knowledge

    notes = reapply_knowledge(Path(root), Path(output_path))
    if notes > 0:
        print(f"    Knowledge overlay reapplied: {notes} notes")


def run_pipeline(projects, output_dir: str, args) -> int:
    """Run the full extraction pipeline for a list of projects."""
    from codebeacon.graph.analyze import analyze, report_to_markdown
    import json
    from pathlib import Path

    output_path = Path(output_dir)
    if _ensure_output_dir(output_path) != 0:
        return 1

    wiki_only = getattr(args, "wiki_only", False)

    # project_name → absolute root. Hoisted above the wiki_only split because
    # BOTH branches need it: the HTML exporters inside the full-scan branch, and
    # the wiki/obsidian generators below, which run either way. Keeping one
    # binding also stops the same dict being rebuilt inline at three call sites.
    project_roots = {p.name: p.path for p in projects}
    html_assets = getattr(args, "html_assets", "local")

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
        try:
            G, meta = load_beacon(beacon_path)
        except ValueError as exc:  # corrupt beacon.json (graphify #1536)
            print(f"  Error: {exc}", file=sys.stderr)
            return 1
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
        cache_root = _cache_anchor(projects, output_dir)
        cache = Cache(output_dir, project_root=cache_root)
        # --force is the single escape hatch: it bypasses the shrink guard AND
        # the incremental cache, so one flag recovers from both a refused write
        # and a poisoned cache entry (G-0917-7).
        force = bool(getattr(args, "force", False))
        if getattr(args, "update", False) and not force:
            cache.load()

        wave_results = []
        corpus: list[str] = []
        extra_ignore = list(getattr(args, "exclude", []) or [])
        # One report across every project: an over-broad ignore rule and a clean
        # scan both report N files and exit 0, so what got left out is recorded
        # with a cause instead of being invisible (R12).
        ignored = IgnoredReport()
        for project in projects:
            print(f"\n  Extracting {project.name} ({project.framework}) ...")
            files = collect_files(project.path, extra_ignore=extra_ignore,
                                  report=ignored)
            corpus.extend(files)
            print(f"    {len(files)} source files found")

            def progress(done, total, _name=project.name):
                pct = int(done / total * 100) if total else 100
                print(f"    [{pct:3d}%] {done}/{total} files processed", end="\r")

            wave = auto_wave(
                project=project,
                files=files,
                chunk_size=getattr(args, "wave_chunk_size", None) or 300,
                max_parallel=getattr(args, "wave_max_parallel", None) or 5,
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
        _emit_ignored_report(ignored, output_dir)

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

        # Persist beacon.json first; the shrink/desync guard prevents the report
        # from racing ahead of a half-written graph. The guard stays ARMED under
        # --update, watch and hook rebuilds — those are the unattended paths it
        # exists for — and instead of a blanket waiver it is handed the corpus,
        # so a node loss can be attributed to a deleted or newly-excluded file.
        wr = write_beacon(
            G,
            output_path,
            repo_path=projects[0].path if projects else output_path,
            force=force,
            project_roots=project_roots,
            corpus=corpus,
            incomplete=_run_is_incomplete(wave_results),
        )
        if wr.skipped_shrink:
            print(
                "  Aborting outputs because nodes went missing without an explanation.",
                file=sys.stderr,
            )
            return 1

        _reapply_knowledge_overlay(
            projects[0].path if projects else output_path, output_path,
        )

        # Analysis (after write, so the report can quote the stamped commit)
        report = analyze(G, communities, cohesion, project_paths=project_roots)
        report.built_at_commit = wr.built_at_commit
        report.current_commit = wr.built_at_commit  # same run; not stale yet
        # write_text_if_changed, not write_text: REPORT.md is derived entirely
        # from the graph, so an unchanged rebuild reproduces it byte for byte.
        # Rewriting identical bytes still moves mtime, which re-triggers editor
        # indexers and file-sync clients watching .codebeacon/.
        report_path = output_path / "REPORT.md"
        write_text_if_changed(report_path, report_to_markdown(report))

        # Visual exports — best-effort, never block the pipeline. The exporters
        # degrade internally too (an unwritable page is one skipped file, not an
        # abort), so these wrappers are belt-and-braces.
        try:
            tree_path = write_tree_html(
                G, output_path,
                project_roots=project_roots, html_assets=html_assets,
            )
            print(f"    Wrote {tree_path.name}")
        except (OSError, ValueError) as exc:
            print(f"    Warning: tree HTML failed: {exc}", file=sys.stderr)
        try:
            flow_path = write_callflow_html(
                G, output_path,
                project_roots=project_roots, html_assets=html_assets,
            )
            print(f"    Wrote {flow_path.name}")
        except (OSError, ValueError) as exc:
            print(f"    Warning: callflow HTML failed: {exc}", file=sys.stderr)

    # Which exporters run is gated by output.* in codebeacon.yaml, wired onto
    # `args` by _cmd_sync (getattr defaults keep the plain-scan path writing
    # everything). context_map.targets picks which of CLAUDE.md/.cursorrules/
    # AGENTS.md get written.
    obsidian_dir = getattr(args, "obsidian_dir", None)
    gen_wiki = getattr(args, "output_wiki", True)
    gen_obsidian = getattr(args, "output_obsidian", True)
    context_targets = getattr(args, "context_map_targets", None)
    rules_split = getattr(args, "rules_split", True)

    # Wiki generation (always runs — whether full scan or --wiki-only)
    if gen_wiki:
        print("  Generating wiki ...")
        from codebeacon.wiki.generator import generate_wiki
        # The exporters are idempotent (staging + content compare), so these
        # counts are churn, not volume: on an unchanged repo they read 0 and
        # the committed tree stays clean.
        changed = generate_wiki(G, communities, output_dir, project_roots=project_roots)
        print(f"    Wiki written to {output_dir}/wiki/ ({changed} page(s) changed)")

    # Obsidian vault generation
    if gen_obsidian:
        print("  Generating Obsidian vault ...")
        from codebeacon.export.obsidian import generate_obsidian_vault, VaultNotOwnedError
        obs_stats: dict[str, int] = {}
        try:
            n_notes = generate_obsidian_vault(
                G, communities, output_dir, obsidian_dir=obsidian_dir,
                project_roots=project_roots, stats=obs_stats,
            )
        except VaultNotOwnedError as exc:  # --obsidian-dir points at a non-empty user vault (#1506)
            print(f"    Skipping Obsidian export: {exc}", file=sys.stderr)
            n_notes = 0
        print(
            f"    {n_notes} notes written to "
            f"{obsidian_dir or output_dir + '/obsidian'}/ "
            f"({obs_stats.get('changed', 0)} changed, "
            f"{obs_stats.get('removed', 0)} removed)"
        )

    # Context Map generation (CLAUDE.md / .cursorrules / AGENTS.md)
    if context_targets is None or context_targets:
        print("  Generating context map ...")
        from codebeacon.contextmap.generator import generate_context_map
        written = generate_context_map(
            G=G,
            output_dir=output_dir,
            projects=projects,
            obsidian_dir=obsidian_dir,
            targets=context_targets,
            rules_split=rules_split,
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


def _project_group_root(project_path, workspace_root) -> "Path":
    """Return the repo boundary that owns ``project_path``.

    Walks from the project up to (exclusive) the workspace root and returns
    the OUTERMOST directory marked as an independent project — one with its
    own ``.git`` or ``codebeacon.yaml``. A detected framework folder inside a
    monorepo (``mono/landing``) therefore resolves to ``mono``, while a
    standalone project resolves to itself. Falls back to the project path
    when no boundary exists between it and the workspace root.
    """
    from pathlib import Path

    def _is_boundary(d: Path) -> bool:
        return (d / ".git").exists() or (d / "codebeacon.yaml").exists()

    p = Path(project_path).resolve()
    ws = Path(workspace_root).resolve()
    if p == ws:
        return p
    best = None
    cur = p
    while cur != ws and ws in cur.parents:
        if _is_boundary(cur):
            best = cur
        cur = cur.parent
    if best is not None:
        return best
    # No boundary strictly below the workspace root. If the workspace root
    # itself is a repo (deep-dive run INSIDE a monorepo), the project belongs
    # to it; otherwise — a loose collection of template folders — the project
    # stands alone.
    return ws if _is_boundary(ws) else p


def _group_projects(projects, workspace_root) -> list:
    """Group detected projects by their owning repo boundary, order-preserving.

    Returns ``[(group_root: Path, [ProjectInfo, ...]), ...]``. Deep-dive
    outputs land at exactly two levels — each group root and the workspace
    root — never inside a group's subfolders, so ``mono/landing/.codebeacon``
    no longer appears: ``mono/.codebeacon`` carries the combined
    landing+server+desktop graph instead, and the workspace root carries
    everything.
    """
    grouped: dict = {}
    order: list = []
    for p in projects:
        root = _project_group_root(p.path, workspace_root)
        if root not in grouped:
            grouped[root] = []
            order.append(root)
        grouped[root].append(p)
    return [(root, grouped[root]) for root in order]


def run_deep_dive_pipeline(projects, workspace_output_dir: str, args) -> int:
    """Run deep-dive pipeline: per-project-group outputs + combined workspace output.

    Detected projects are first grouped by repo boundary (``.git`` /
    ``codebeacon.yaml``) — see :func:`_group_projects`.

    Phase 1 — Extract each project; the cache lives at its group root.
    Phase 2 — Build one combined graph per group and write outputs under
              <group_root>/.codebeacon/ (skipped when the group root IS the
              workspace root — Phase 3 already writes there).
    Phase 3 — Build a combined workspace graph and write outputs under
              workspace/.codebeacon/.

    Claude Code loads CLAUDE.md hierarchically, so opening a session in a
    project directory loads both the workspace overview AND that project's
    details, while the project's own subfolders stay untouched.
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
    # The workspace root is the directory whose index this is —
    # workspace_output_dir is always "<root>/.codebeacon".
    workspace_root = workspace_path.resolve().parent
    wiki_only = getattr(args, "wiki_only", False)
    obsidian_dir = getattr(args, "obsidian_dir", None)
    # Hoisted above the wiki_only split for the same reason as in run_pipeline:
    # the workspace HTML exporters run inside the full-scan branch while the
    # wiki/obsidian generators below run either way, and both need these.
    workspace_roots = {p.name: p.path for p in projects}
    html_assets = getattr(args, "html_assets", "local")

    # Exporter gates + wave sizing from codebeacon.yaml (wired onto `args` by
    # _cmd_sync). getattr defaults preserve the plain --deep-dive scan path,
    # which has no config and writes every exporter at the default wave size.
    gen_wiki = getattr(args, "output_wiki", True)
    gen_obsidian = getattr(args, "output_obsidian", True)
    context_targets = getattr(args, "context_map_targets", None)
    gen_context = context_targets is None or bool(context_targets)
    rules_split = getattr(args, "rules_split", True)
    wave_chunk_size = getattr(args, "wave_chunk_size", None) or 300
    wave_max_parallel = getattr(args, "wave_max_parallel", None) or 5

    if len(projects) <= 1:
        print(
            "Warning: --deep-dive with a single project produces identical per-project "
            "and workspace outputs. Running standard pipeline instead.",
            file=sys.stderr,
        )
        return run_pipeline(projects, workspace_output_dir, args)

    grouped = _group_projects(projects, workspace_root)

    # ── Phase 1: Extract all projects ──────────────────────────────────────────
    # project_waves tracks (project, wave_result) pairs explicitly so that index
    # alignment never diverges even if one project's extraction is skipped.
    # group_waves collects the same waves per repo boundary for Phase 2.
    project_waves: list[tuple] = []
    group_waves: dict = {root: [] for root, _ in grouped}
    group_corpus: dict = {root: [] for root, _ in grouped}
    force = bool(getattr(args, "force", False))

    if not wiki_only:
        from codebeacon.discover.scanner import collect_files
        from codebeacon.cache import Cache
        from codebeacon.wave import auto_wave

        extra_ignore = list(getattr(args, "exclude", []) or [])
        ignored = IgnoredReport()
        for group_root, group_projects in grouped:
            # One cache per group, shared by its projects and stored at the
            # group root — writing it per-project would scatter .codebeacon/
            # dirs into a monorepo's subfolders, and per-project Cache
            # instances saving to one file would overwrite each other.
            cache = Cache(str(group_root / ".codebeacon"), project_root=str(group_root))
            if getattr(args, "update", False) and not force:
                cache.load()

            for project in group_projects:
                print(f"\n  Extracting {project.name} ({project.framework}) ...")
                files = collect_files(project.path, extra_ignore=extra_ignore,
                                      report=ignored)
                group_corpus[group_root].extend(files)
                print(f"    {len(files)} source files found")

                def progress(done, total, _name=project.name):
                    pct = int(done / total * 100) if total else 100
                    print(f"    [{pct:3d}%] {done}/{total} files processed", end="\r")

                wave = auto_wave(
                    project=project,
                    files=files,
                    chunk_size=wave_chunk_size,
                    max_parallel=wave_max_parallel,
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

                project_waves.append((project, wave))
                group_waves[group_root].append(wave)

            cache.save()

        _emit_ignored_report(ignored, workspace_output_dir)

        # Gate: workspace-level failure report covering every project.
        gate = emit_failure_report(
            [w for _, w in project_waves], workspace_output_dir, args,
        )
        if gate != 0:
            return gate

    # ── Phase 2: Per-group graph + outputs ──────────────────────────────────────
    # One output per repo boundary, at that repo's root. A group whose root IS
    # the workspace root is skipped — Phase 3 writes the combined output there.
    print("\n  Generating per-project outputs ...")

    if wiki_only:
        for group_root, group_projects in grouped:
            if group_root == workspace_root:
                continue
            label = group_root.name
            proj_output_dir = str(group_root / ".codebeacon")
            beacon_path = Path(proj_output_dir) / "beacon.json"
            if not beacon_path.exists():
                print(
                    f"  Warning: {beacon_path} not found — skipping {label}.",
                    file=sys.stderr,
                )
                continue

            try:
                G, meta = load_beacon(beacon_path)
            except ValueError as exc:  # corrupt group beacon → skip, keep going (#1536)
                print(f"  Warning: {exc} — skipping {label}.", file=sys.stderr)
                continue
            communities: dict = {}
            for node_id, node_data in G.nodes(data=True):
                if "community" in node_data:
                    communities[node_id] = node_data["community"]
            report = analyze(G, communities, {})
            report.built_at_commit = meta.get("built_at_commit", "")
            report.current_commit = git_head(str(group_root))
            n_communities = len(set(communities.values())) if communities else 0

            write_project_artifact_outputs(
                G, communities, group_projects, proj_output_dir, label=label,
                wiki=gen_wiki, obsidian=gen_obsidian, targets=context_targets,
                rules_split=rules_split,
            )
    else:
        for group_root, group_projects in grouped:
            if group_root == workspace_root:
                continue
            label = group_root.name
            waves = group_waves.get(group_root, [])
            if not waves:
                continue
            proj_output_dir = str(group_root / ".codebeacon")
            if _ensure_output_dir(Path(proj_output_dir)) != 0:
                # One unwritable group must not sink the whole deep dive; the
                # other groups and the workspace graph are still worth having.
                continue

            print(f"\n  Building graph for {label} ...")
            G = build_graph(waves)
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

            group_roots = {p.name: p.path for p in group_projects}
            wr = write_beacon(
                G,
                proj_output_dir,
                repo_path=str(group_root),
                force=force,
                project_roots=group_roots,
                corpus=group_corpus.get(group_root) or [],
                incomplete=_run_is_incomplete(waves),
            )
            if wr.skipped_shrink:
                print(
                    f"    Warning: refused to shrink {label} graph; keeping prior beacon.json.",
                    file=sys.stderr,
                )
            else:
                _reapply_knowledge_overlay(group_root, Path(proj_output_dir))

            report = analyze(G, communities, cohesion, project_paths=group_roots)
            report.built_at_commit = wr.built_at_commit
            report.current_commit = wr.built_at_commit
            write_text_if_changed(
                Path(proj_output_dir) / "REPORT.md", report_to_markdown(report)
            )

            try:
                write_tree_html(G, proj_output_dir, project_roots=group_roots,
                                html_assets=html_assets)
                write_callflow_html(G, proj_output_dir, project_roots=group_roots,
                                    html_assets=html_assets)
            except (OSError, ValueError) as exc:
                print(f"    Warning: HTML export failed for {label}: {exc}", file=sys.stderr)

            write_project_artifact_outputs(
                G, communities, group_projects, proj_output_dir, label=label,
                wiki=gen_wiki, obsidian=gen_obsidian, targets=context_targets,
                rules_split=rules_split,
            )

    # ── Phase 3: Combined workspace graph + outputs ────────────────────────────
    print("\n  Building combined workspace graph ...")
    if _ensure_output_dir(workspace_path) != 0:
        return 1

    if wiki_only:
        beacon_path = workspace_path / "beacon.json"
        if not beacon_path.exists():
            print(
                f"  Error: {beacon_path} not found. Run a full scan first before using --wiki-only.",
                file=sys.stderr,
            )
            return 1
        try:
            G_all, meta_all = load_beacon(beacon_path)
        except ValueError as exc:  # corrupt combined beacon.json (graphify #1536)
            print(f"  Error: {exc}", file=sys.stderr)
            return 1
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
            force=force,
            project_roots=workspace_roots,
            corpus=[f for files in group_corpus.values() for f in files],
            incomplete=_run_is_incomplete(all_waves),
        )
        if wr_all.skipped_shrink:
            print(
                "  Aborting workspace outputs because nodes went missing without an explanation.",
                file=sys.stderr,
            )
            return 1

        _reapply_knowledge_overlay(workspace_output_dir, workspace_path)

        report_all = analyze(G_all, communities_all, cohesion_all, project_paths=workspace_roots)
        report_all.built_at_commit = wr_all.built_at_commit
        report_all.current_commit = wr_all.built_at_commit
        write_text_if_changed(
            workspace_path / "REPORT.md", report_to_markdown(report_all)
        )

        try:
            write_tree_html(G_all, workspace_path, project_roots=workspace_roots,
                            html_assets=html_assets)
            write_callflow_html(G_all, workspace_path, project_roots=workspace_roots,
                                html_assets=html_assets)
        except (OSError, ValueError) as exc:
            print(f"    Warning: workspace HTML export failed: {exc}", file=sys.stderr)

    if gen_wiki:
        print("  Generating combined wiki ...")
        changed = generate_wiki(
            G_all, communities_all, workspace_output_dir, project_roots=workspace_roots)
        print(f"    Wiki written to {workspace_output_dir}/wiki/ ({changed} page(s) changed)")

    if gen_obsidian:
        from codebeacon.export.obsidian import VaultNotOwnedError
        print("  Generating combined Obsidian vault ...")
        obs_stats: dict[str, int] = {}
        try:
            n_notes = generate_obsidian_vault(
                G_all, communities_all, workspace_output_dir,
                obsidian_dir=obsidian_dir, project_roots=workspace_roots,
                stats=obs_stats,
            )
        except VaultNotOwnedError as exc:  # --obsidian-dir points at a non-empty user vault (#1506)
            print(f"    Skipping Obsidian export: {exc}", file=sys.stderr)
            n_notes = 0
        print(
            f"    {n_notes} notes written to "
            f"{obsidian_dir or workspace_output_dir + '/obsidian'}/ "
            f"({obs_stats.get('changed', 0)} changed, "
            f"{obs_stats.get('removed', 0)} removed)"
        )

    if gen_context:
        print("  Generating combined context map ...")
        written = generate_context_map(
            G=G_all,
            output_dir=workspace_output_dir,
            projects=projects,
            obsidian_dir=obsidian_dir,
            targets=context_targets,
            rules_split=rules_split,
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


def write_project_artifact_outputs(
    G, communities, projects, proj_output_dir: str, label: str | None = None,
    wiki: bool = True, obsidian: bool = True, targets: list | None = None,
    rules_split: bool = True,
) -> None:
    """Write wiki, obsidian, and context map for one project group's output dir.

    ``projects`` is the list of detected projects belonging to this group (a
    repo may contain several — landing/server/desktop in one monorepo). The
    obsidian vault always lands inside proj_output_dir/obsidian/ (no custom
    path), keeping each group self-contained under its own .codebeacon/.

    ``wiki``/``obsidian``/``targets`` gate the three exporters from
    codebeacon.yaml's ``output.*`` (defaults keep every exporter on).
    """
    from codebeacon.wiki.generator import generate_wiki
    from codebeacon.export.obsidian import generate_obsidian_vault
    from codebeacon.contextmap.generator import generate_context_map

    projects = list(projects)
    label = label or (projects[0].name if projects else "?")
    project_roots = {p.name: p.path for p in projects}

    if wiki:
        print(f"  [{label}] Generating wiki ...")
        changed = generate_wiki(G, communities, proj_output_dir, project_roots=project_roots)
        print(f"    {changed} page(s) changed")

    if obsidian:
        print(f"  [{label}] Generating Obsidian vault ...")
        obs_stats: dict[str, int] = {}
        generate_obsidian_vault(
            G, communities, proj_output_dir, obsidian_dir=None,
            project_roots=project_roots, stats=obs_stats,
        )
        print(f"    {obs_stats.get('changed', 0)} note(s) changed, "
              f"{obs_stats.get('removed', 0)} removed")

    if targets is None or targets:
        print(f"  [{label}] Generating context map ...")
        written = generate_context_map(
            G=G,
            output_dir=proj_output_dir,
            projects=projects,
            obsidian_dir=None,
            targets=targets,
            rules_split=rules_split,
        )
        for path in written:
            print(f"    {path}")
