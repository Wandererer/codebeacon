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
```

**Do not** create a `.codebeacon_python` file or wrap subsequent commands in `$(cat .codebeacon_python)`. Earlier versions of this skill did that, but if the user's shell has any `cat` alias, function, or hook that swallows arguments, the substitution falls back to reading stdin and hangs forever. Instead, always call codebeacon via Python's module runner so the same interpreter that just did `import codebeacon` is the one that runs the command:

```bash
python3 -m codebeacon <args...>
```

If `python3` is not the interpreter where `pip install codebeacon` landed, resolve it once at the start of your bash block with `command -v` (no subshell-over-cat needed):

```bash
PY="$(command -v python3)"
"$PY" -m codebeacon <args...>
```

### Step 2 — Dispatch on subcommand

Inspect the user-supplied arguments. If the first non-flag arg is one of `sync`, `semantic-prepare`, `semantic-apply`, `serve`, `query`, `path`, `init`, `install`, `upgrade`, `hook`, `merge-driver` — forward the entire argv to codebeacon and stop after the command exits (no auto-semantic for these except `sync`, which IS covered below):

```bash
python3 -m codebeacon <args...>
```

Otherwise the user wants a scan / sync. Continue to Step 3.

### Step 3 — Scan or sync

Identify the target path (first non-flag arg, or `.` if none) and collect every other argument the user supplied — **forward them all** to the underlying `codebeacon` subcommand so flags like `--deep-dive`, `--update`, `--obsidian-dir <p>`, `--semantic` (the regex layer) reach the right place. Drop `--no-semantic`, `--wiki-only`, and `--list-only` from the forwarded set when they're agent-control flags that codebeacon itself doesn't understand; keep the rest.

```bash
TARGET="${1:-.}"
# Replace EXTRA_ARGS with the user's other flags (e.g. --deep-dive --update),
# minus skill-only switches (--no-semantic) which only gate Step 4 below.
EXTRA_ARGS=""

if [ -f "$TARGET/codebeacon.yaml" ]; then
    echo "Found codebeacon.yaml — running sync mode"
    python3 -m codebeacon sync --config "$TARGET/codebeacon.yaml" $EXTRA_ARGS
else
    echo "Scanning $TARGET ..."
    python3 -m codebeacon scan "$TARGET" $EXTRA_ARGS
fi
```

The command prints wave progress (framework detection per project, `[pct%] done/total files`, then route/service/entity counts, then `Nodes: N, Edges: E, Communities: K`). Let it run to completion. With `--deep-dive`, each sub-project also gets its own `.codebeacon/` directory, and Step 4 below will run `semantic-prepare` / `semantic-apply` per project as well as for the workspace root.

### Step 4 — AI-semantic enrichment (automatic)

Skip this step if the user passed `--no-semantic`, `--wiki-only`, or `--list-only`.

**Run on the workspace root `.codebeacon/` only.** Even with `--deep-dive`, the workspace beacon contains the union of every project's nodes, so a single enrichment cycle covers the whole codebase. Per-project `.codebeacon/` directories stay AST-only — Claude Code loads `CLAUDE.md` hierarchically, so a session opened inside any sub-project still inherits the workspace AI signal. Do **not** loop over sub-project beacon dirs; everything lives at `$TARGET/.codebeacon/semantic/`.

```bash
TARGET="${1:-.}"
BEACON_DIR="$TARGET/.codebeacon"
```

#### 4a. Prepare the task chunks

```bash
python3 -m codebeacon semantic-prepare --dir "$BEACON_DIR"
```

This rehydrates the archive at `$BEACON_DIR/semantic/original/*.jsonl` onto the freshly built graph (and prunes entries that point at nodes the graph no longer contains), then writes `$BEACON_DIR/semantic/pending/chunk_NNN.jsonl` files containing only **new** candidates that have never been processed at their current content hash. If the printed `new task(s)` count is `0`, skip 4b and 4c — nothing new to do.

`--chunk-size N` controls how many tasks land in each chunk file (default 20). Every source-bearing file gets a base score of 1, so coverage spans every folder — god-folder, hub, and unresolved-target boosts only affect ordering. Files that change between scans get a fresh `task_id` automatically, because the id mixes in a short hash of the analysed excerpt.

> **Do not pass `--max-tasks` from this skill.** The default is `0`, which means "emit every scored candidate" — that is the intended behaviour. If you look at the node count and feel the urge to add `--max-tasks 50` or `--max-tasks 12` "to be safe", **don't**. The user wants full coverage. `--max-tasks` exists only for direct CLI invocations where a human has explicitly asked for a smaller batch. The skill must call `codebeacon semantic-prepare --dir "$BEACON_DIR"` with **no** `--max-tasks` flag.

#### 4b. Dispatch parallel subagents (1–5 chunks each)

Group the `chunk_NNN.jsonl` files under `$BEACON_DIR/semantic/pending/` into **batches of 1–5 chunks per subagent**, then dispatch one subagent per batch **all in a single message** so the harness runs them concurrently. Do NOT iterate chunks sequentially in your own turn; that defeats the parallelism.

**Batch sizing rules (apply in order):**

1. **≤5 chunks total:** one chunk per subagent — maximum parallelism for small graphs.
2. **6–25 chunks:** aim for **3 chunks per subagent** — balances per-spawn overhead against parallelism.
3. **>25 chunks:** **5 chunks per subagent** — caps the subagent fan-out around ~10 concurrent workers, avoiding harness-side rate limits on parallel Agent dispatch.

A subagent that owns 1–5 chunks reads each pending file in turn and writes the matching `chunk_NNN.jsonl` under `semantic/results/`. The apply step matches results to pending chunks by filename, so the batching is invisible downstream — only the dispatch layout changes.

Example batching for 12 chunks (`chunk_001.jsonl` … `chunk_012.jsonl`):
- Subagent A: 001, 002, 003
- Subagent B: 004, 005, 006
- Subagent C: 007, 008, 009
- Subagent D: 010, 011, 012

Four parallel Agent calls in one message instead of twelve.

**Picking the subagent model — depends on the host runtime:**

| Host runtime | Subagent primitive | Model selection |
| --- | --- | --- |
| **Claude Code** | `Agent` tool, `model` param | One tier below the host model (see table below) |
| Codex CLI | `spawn_agent` (requires `multi_agent=true` in `~/.codex/config.toml`) | No model picker in subagent API — use the host's default |
| Cursor / OpenCode / Aider / Gemini CLI / others | Whatever native subagent / parallel dispatch primitive the host exposes | No model picker — use the host's default |
| Host has no subagent primitive | Fall back to in-turn sequential processing | Same model as the host |

**Claude Code model-downgrade table:**

| Your current model | Subagent `model` parameter |
| --- | --- |
| `opus`   | `sonnet` |
| `sonnet` | `haiku`  |
| `haiku`  | `haiku`  (no further downgrade) |

The narrow extraction task is well within Haiku/Sonnet quality, and downgrading by a tier on Claude Code keeps the spend proportional to the corpus size. If `$ANTHROPIC_MODEL` or the harness banner makes the tier unambiguous, use that. Otherwise default to `haiku`.

For non-Claude hosts: do **not** invent a model downgrade — most other agents don't expose a model picker on their subagent APIs, and forcing one risks an unsupported value. Trust the host's default.

For each **batch of 1–5 chunks**, spawn one Agent like this (multiple Agent calls in the same assistant message for parallelism):

```
Agent({
  description: "semantic chunks NNN-MMM",
  subagent_type: "general-purpose",
  model: "<downgraded model from table above>",
  prompt: """
You are a graphify-style semantic extraction agent for codebeacon. Process the
following chunk files IN ORDER and write one result file per chunk:

  Pending chunks (read each in turn):
    <ABS_PATH>/semantic/pending/chunk_NNN.jsonl
    <ABS_PATH>/semantic/pending/chunk_NN+1.jsonl
    ... (up to 5 chunk paths in this batch)

  For each pending chunk you process, write the matching results file at:
    <ABS_PATH>/semantic/results/chunk_<same_index>.jsonl

Every line in a pending chunk is one task with this shape:

  {"task_id": "...", "source_node_id": "...", "file_path": "...",
   "framework": "...", "excerpt": "≤4000 chars of source", "hint": "..."}

For each task, analyze the `excerpt` and emit a knowledge-graph fragment
that captures semantic relationships AST extraction misses. Output ONLY
valid JSON per line — no markdown fences, no preamble, no commentary.

Per-task output schema:
  {
    "task_id": "<copied from input>",
    "source_node_id": "<copied from input>",
    "nodes": [                                          # optional
      {"id": "rfc6749_oauth2", "label": "OAuth2 RFC 6749",
       "file_type": "concept|document|paper",
       "source_file": "<task.file_path>"}
    ],
    "edges": [
      {"target_name": "UserService",
       "relation": "calls|implements|references|cites|conceptually_related_to|
                    shares_data_with|semantically_similar_to|rationale_for",
       "confidence": "EXTRACTED|INFERRED|AMBIGUOUS",
       "confidence_score": 0.7}
    ],
    "hyperedges": [                                     # optional
      {"id": "auth_login_flow", "label": "Auth Login Flow",
       "nodes": ["auth_loginservice","auth_userrepo","rfc6749_oauth2"],
       "relation": "participate_in|implement|form",
       "confidence": "INFERRED", "confidence_score": 0.7}
    ]
  }

Extraction rules:
- EXTRACTED (score 1.0): relation is explicit in the source — import, call,
  citation in a comment, decorator argument, type annotation.
- INFERRED (score 0.55-0.95, discrete: .55/.65/.75/.85/.95): reasonable
  inference from shared data shapes, naming patterns, or co-mentioned
  concepts. Prefer fewer, higher-confidence edges over noise.
- AMBIGUOUS: uncertain — emit, flag for review, do not omit.
- Skip primitives (int, String, list, bool, ...) as `target_name`.
- New nodes (`nodes` array) only for file_type ∈ {concept, document, paper}.
  Never invent code nodes — AST owns those.
- Hyperedges: 3+ participants in a shared flow/pattern only. Use sparingly.
- If a task yields no signal, still emit a result line with empty
  arrays — the apply step needs it to archive the task and skip it next
  scan.

For each pending chunk, write the per-line JSON results to the matching
file under `semantic/results/` — same filename as the pending chunk
(e.g. `chunk_007.jsonl` → `chunk_007.jsonl`). One result line per input
task. Process the chunks in the order listed above; do not interleave.
""",
})
```

Replace `<ABS_PATH>` with the absolute `$BEACON_DIR` and list the 1–5 chunk file paths owned by this subagent in the prompt's "Pending chunks" section.

**Why subagents instead of doing it in your own turn?** (a) parallelism — N chunks run concurrently instead of serially; (b) context isolation — the host turn keeps a clean transcript; (c) the downgraded model handles narrow JSON extraction at a fraction of the cost.

If `--no-parallel-semantic` is passed (advanced flag), fall back to doing the analysis in your own turn, one chunk at a time, with the same prompt and schema.

#### 4c. Apply the results

```bash
python3 -m codebeacon semantic-apply --dir "$BEACON_DIR"
```

For every `results/chunk_NNN.jsonl` written in 4b, this merges the inferred edges into `beacon.json` (as `INFERRED references`), **moves** the matching `pending/chunk_NNN.jsonl` into `$BEACON_DIR/semantic/original/chunk_NNN.jsonl` (with the applied edges spliced in for auditability), deletes the result file, and finally regenerates wiki + obsidian + context map. On the next scan, `semantic-prepare` reads the archive and skips any task whose content hash is already on file.

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
python3 -m codebeacon serve --dir "$TARGET/.codebeacon"
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
  semantic/
    pending/
      chunk_001.jsonl      ← prepare writes one chunk per --chunk-size tasks
      chunk_002.jsonl
    results/
      chunk_001.jsonl      ← agent writes a matching file per chunk
      chunk_002.jsonl
    original/
      chunk_001.jsonl      ← apply moves done chunks here (durable archive)
      chunk_002.jsonl
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
