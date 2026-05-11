---
name: codebeacon
description: Scan a codebase → AST extraction → knowledge graph → wiki + CLAUDE.md context map. Supports 27 frameworks (Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor).
trigger: /codebeacon
---

# /codebeacon

Scan source code with AST analysis → build a knowledge graph → generate a navigable wiki + `CLAUDE.md` context map ready for AI agents. After scan/sync, run AI-semantic enrichment **automatically** using whatever model the agent is currently running on (no hardcoded model, no extra API key).

## Usage

```
/codebeacon                              # scan current directory + auto AI-semantic
/codebeacon <path>                       # scan specific path + auto AI-semantic
/codebeacon <path> --update              # incremental scan + auto AI-semantic
/codebeacon <path> --wiki-only           # wiki only (no scan, no semantic)
/codebeacon <path> --no-semantic         # skip AI-semantic
/codebeacon sync                         # multi-project sync + auto AI-semantic
/codebeacon semantic-prepare [--dir D]   # emit a fresh tasks file only (no scan)
/codebeacon semantic-apply   [--dir D]   # merge a results file written by the agent
/codebeacon serve <path>                 # start MCP server pointing at .codebeacon/
/codebeacon query <term>                 # search the graph
/codebeacon path <src> <tgt>             # shortest path
/codebeacon init [<path>]                # interactive codebeacon.yaml
/codebeacon install                      # install/update this skill
/codebeacon upgrade                      # pip upgrade codebeacon + refresh this SKILL.md (then restart Claude Code)
```

If no path was given, use `.` (current directory). Do not ask the user for a path.

## What You Must Do When Invoked

Follow the steps in order. Do not skip Step 4 unless `--no-semantic` is set or the user explicitly asked for `--wiki-only`.

### Step 1 — Ensure codebeacon is installed

```bash
python3 -c "import codebeacon" 2>/dev/null || pip install codebeacon -q --break-system-packages 2>&1 | tail -5
python3 -c "import sys; open('.codebeacon_python', 'w').write(sys.executable)"
```

In every subsequent bash block, replace `python3` with `$(cat .codebeacon_python)`.

### Step 2 — Dispatch on subcommand

Inspect the user-supplied arguments. If the first non-flag arg is one of `sync`, `semantic-prepare`, `semantic-apply`, `serve`, `query`, `path`, `init`, `install`, `hook`, `merge-driver` — forward the entire argv to codebeacon and stop after the command exits (no auto-semantic for these except `sync`, which IS covered below):

```bash
$(cat .codebeacon_python) -m codebeacon <args...>
```

Otherwise the user wants a scan / sync. Continue to Step 3.

### Step 3 — Scan or sync

```bash
TARGET="${1:-.}"

if [ -f "$TARGET/codebeacon.yaml" ]; then
    echo "Found codebeacon.yaml — running sync mode"
    $(cat .codebeacon_python) -m codebeacon sync --config "$TARGET/codebeacon.yaml"
else
    echo "Scanning $TARGET ..."
    $(cat .codebeacon_python) -m codebeacon scan "$TARGET"
fi
```

The command prints wave progress (framework detection per project, `[pct%] done/total files`, then route/service/entity counts, then `Nodes: N, Edges: E, Communities: K`). Let it run to completion.

### Step 4 — AI-semantic enrichment (automatic)

Skip this step if the user passed `--no-semantic`, `--wiki-only`, or `--list-only`.

#### 4a. Prepare the task batch

```bash
TARGET="${1:-.}"
$(cat .codebeacon_python) -m codebeacon semantic-prepare --dir "$TARGET/.codebeacon"
```

This rehydrates the archive (`semantic/original.jsonl`) onto the freshly built graph and writes `.codebeacon/semantic-tasks.jsonl` containing only **new** candidates (god-node folders + files with unresolved targets) that have never been processed before. If the printed `new task(s)` count is `0`, skip 4b and 4c — there is nothing new to do.

#### 4b. Run the analysis (you, the running agent)

Read every line of `.codebeacon/semantic-tasks.jsonl`. Each line is a JSON object:

```json
{"task_id": "...", "source_node_id": "...", "file_path": "...",
 "framework": "...", "excerpt": "≤4000 chars of source", "hint": "..."}
```

For each task, answer this prompt using the model you are currently running on (whatever the user picked — Opus, Sonnet, Haiku, whatever). Do **not** invoke `anthropic.Anthropic()` or any external API; the analysis is part of your own turn.

> Analyze the source excerpt below. List only explicit **class/type/service** references that appear in **comments, docstrings, or type annotations / decorators** — NOT in code logic. Skip primitive types (int, String, list, etc.). Return a JSON array of strings. If none found, return `[]`.
>
> File: `{file_path}` · Framework: `{framework}`
>
> ````
> {excerpt}
> ````

For each task, append one line to `.codebeacon/semantic-results.jsonl`:

```json
{"task_id": "...", "source_node_id": "...",
 "edges": [{"target_name": "UserService", "relation": "references", "confidence_score": 0.7}, ...]}
```

If the task has no inferred edges, still write a result line with `"edges": []` so the apply step can archive it and not re-emit the same task next time.

Keep batches small (≤10 tasks per inner loop) — do not blast through hundreds of LLM turns in one go. If `new task(s)` was capped at 50 by `--max-tasks`, the next scan will pick up the remainder.

#### 4c. Apply the results

```bash
TARGET="${1:-.}"
$(cat .codebeacon_python) -m codebeacon semantic-apply --dir "$TARGET/.codebeacon"
```

This merges the new edges into `beacon.json` (as `INFERRED references`), appends them to the durable archive at `.codebeacon/semantic/original.jsonl`, clears the pending `semantic-tasks.jsonl` / `semantic-results.jsonl`, and regenerates wiki + obsidian + context map. On the next scan, `semantic-prepare` will read the archive and only emit truly new candidates.

### Step 5 — Report results

```bash
TARGET="${1:-.}"
OUTPUT_DIR="$TARGET/.codebeacon"
[ -f "$OUTPUT_DIR/REPORT.md" ] && head -40 "$OUTPUT_DIR/REPORT.md"
```

Summarise for the user:
- Which projects/frameworks were detected
- Total nodes, edges, communities
- AI-semantic: new tasks processed this run, archive size, applied edge count
- Output location (`.codebeacon/wiki/`, `.codebeacon/CLAUDE.md`, etc.)
- Any god nodes or surprising connections worth mentioning

### Step 6 — (Optional) MCP serve

If the user asked for `serve`:

```bash
TARGET="${1:-.}"
$(cat .codebeacon_python) -m codebeacon serve --dir "$TARGET/.codebeacon"
```

This blocks — run it only when the user explicitly wants an MCP server.

## Output structure

```
.codebeacon/
  beacon.json              ← full knowledge graph (node-link JSON)
  REPORT.md                ← god nodes, surprising connections, hub files
  CLAUDE.md                ← AI context map (also written to project root)
  .cursorrules             ← Cursor IDE context
  AGENTS.md                ← OpenAI Agents context
  semantic-tasks.jsonl     ← pending AI-semantic batch (deleted after apply)
  semantic-results.jsonl   ← agent-written results (deleted after apply)
  semantic/
    original.jsonl         ← durable archive of every applied semantic result
  wiki/
    index.md               ← global index (~200 tokens)
    overview.md            ← platform stats + cross-project connections
    routes.md              ← all routes table
    cross-project/
      connections.md       ← cross-service edges
    <project>/
      index.md
      routes.md
      controllers/<Name>.md
      services/<Name>.md
      entities/<Name>.md
      components/<Name>.md
  obsidian/                ← Obsidian vault (one note per node)
```

## Supported frameworks

| Language | Frameworks |
|----------|-----------|
| Java/Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript/TypeScript | Express, NestJS, React, Vue, Angular, Svelte |
| Go | Gin |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web |
| C# | ASP.NET Core |
| Swift | Vapor |
