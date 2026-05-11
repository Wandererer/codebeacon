<p align="center">
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.md"><img src="https://img.shields.io/badge/lang-English-blue" alt="English"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.ko.md"><img src="https://img.shields.io/badge/lang-한국어-red" alt="Korean"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.ja.md"><img src="https://img.shields.io/badge/lang-日本語-green" alt="Japanese"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.zh-CN.md"><img src="https://img.shields.io/badge/lang-简体中文-orange" alt="Chinese"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.es.md"><img src="https://img.shields.io/badge/lang-Español-yellow" alt="Spanish"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.fr.md"><img src="https://img.shields.io/badge/lang-Français-blueviolet" alt="French"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.de.md"><img src="https://img.shields.io/badge/lang-Deutsch-lightgrey" alt="German"></a>
  <a href="https://github.com/Wandererer/codebeacon/blob/main/README.pt-BR.md"><img src="https://img.shields.io/badge/lang-Português_(BR)-brightgreen" alt="Portuguese (Brazil)"></a>
</p>

<h1 align="center">codebeacon</h1>

<p align="center">
  Source code AST analysis and AI context generation — unified multi-framework knowledge graph
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## Why codebeacon?

Every time you open a new AI coding session, your assistant starts blind. It doesn't know your routes, your service layer, your entity model, or how your microservices call each other. You spend the first chunk of every session just getting the AI back up to speed — pasting files, explaining structure, re-establishing context.

Existing tools solve this partially. Route analyzers map your controllers but miss service dependencies. Knowledge graph tools capture relationships but ignore your API surface. You end up running both, stitching output manually, and repeating it every time the codebase changes.

**codebeacon unifies both approaches in a single CLI.** One command scans your entire codebase with tree-sitter AST parsing, resolves dependency injection across files, detects community clusters in your architecture, and writes a ready-to-use context map directly into `CLAUDE.md`, `.cursorrules`, and `AGENTS.md` — so your AI assistant walks into every session already knowing your codebase.

---

## Key Features

- **Unified pipeline** — route/controller analysis + knowledge graph in one tool, no manual stitching
- **27 frameworks, 9 languages** — Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor
- **Tree-sitter based** — structural AST parsing, not regex; all language grammars included out of the box
- **Two-pass DI resolution** — Pass 1 extracts local AST nodes; Pass 2 builds a global symbol table and resolves Interface → Implementation mappings that single-pass tools miss
- **Wave merge architecture** — files processed in parallel chunks, results merged globally; handles large monorepos without memory blowouts
- **Multiple output formats** — JSON knowledge graph, Markdown wiki, Obsidian vault, AI context maps, MCP server, interactive HTML
- **Visual exploration** — `beacon.html` (D3 collapsible tree) and `callflow.html` (Mermaid architecture diagrams grouped by community), regenerated on every scan
- **Community detection** — Leiden/Louvain clustering reveals your actual architectural boundaries
- **Incremental cache** — SHA-256 + mtime/size fast path; mtime-only bumps from sync tools (Obsidian/iCloud/Nextcloud) never trigger needless re-extraction
- **Confidence promotion** — cross-file `calls` edges are promoted from INFERRED to EXTRACTED when an explicit import proves the binding
- **Safe writes** — beacon.json has a shrink guard (a partial run can never overwrite a complete graph) and stamps `built_at_commit` so REPORT.md flags stale outputs against the current HEAD
- **Multi-developer friendly** — `codebeacon hook install` registers a git merge driver for `beacon.json` and a post-commit incremental rebuild hook, so two devs scanning the same branch never produce merge conflicts in the graph
- **Hardened output** — YAML frontmatter and MCP labels are sanitized: U+2028/U+2029, C0 controls, and bidi marks are stripped before they reach Obsidian, Cursor, or the agent
- **gitignore-style `.codebeaconignore`** — last-match-wins with `!` negation, dir patterns (`build/`), anchored patterns (`/secrets.txt`), trailing-whitespace rules
- **Zero configuration** — auto-detects frameworks and languages; generates `codebeacon.yaml` for repeat runs
- **Deep-dive mode** — `--deep-dive` generates per-project `.codebeacon/` + `CLAUDE.md` for every sub-project; running `codebeacon scan . --update` from any sub-project folder automatically syncs all projects in the workspace
- **Workspace auto-rediscovery** — on every `scan` / `sync`, codebeacon re-scans the workspace and appends any new project folders to `codebeacon.yaml` before extraction, so freshly added sub-projects are never silently skipped; pass `--no-rediscover` to opt out for hand-curated configs
- **Graphify-style semantic enrichment** — after AST extraction, the skill dispatches one parallel subagent per chunk to emit `{nodes, edges, hyperedges}` with 8 relation types (`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`) and EXTRACTED/INFERRED/AMBIGUOUS confidence; on Claude Code the subagent runs one tier below the host model (Opus→Sonnet, Sonnet→Haiku) so spend stays proportional to corpus size. AST owns code nodes; LLM only contributes `concept`/`document`/`paper` nodes. Existing 0.3.x archives replay through the new schema unchanged.

---

## Quick Start

```bash
pip install codebeacon

codebeacon scan .
```

That's it. codebeacon detects your project types, extracts routes/services/entities/components, builds a knowledge graph, and writes everything to `.codebeacon/`.

For a multi-project workspace:

```bash
codebeacon scan /path/to/workspace   # auto-detects all projects, generates codebeacon.yaml
codebeacon sync                      # subsequent runs via config
```

---

## Supported Frameworks

| Language | Frameworks |
|----------|-----------|
| Java / Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript / TypeScript | Express, Fastify, Koa, NestJS, React, Next.js, Vue, Nuxt, Angular, SvelteKit |
| Go | Gin, Echo, Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web, Axum, Tauri, Rocket, Warp |
| C# | ASP.NET Core |
| Swift | Vapor |

---

## Architecture

codebeacon runs a two-pass extraction pipeline:

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         Local AST           Symbol      Cross-lang  HTTP API
                         per chunk           table       artifact    Shared DB
                         (Pass 1)           matching    removal     entity edges
                                            (Pass 2)
```

**Pass 1 — Wave extraction:** Files are processed in parallel chunks via `ThreadPoolExecutor`. Each file runs through five extractors: routes, services, entities, components, and dependencies. Results are cached by SHA-256 for incremental re-scans.

**Pass 2 — Graph build:** All wave results are merged. A global symbol table resolves unresolved dependency injection references — mapping interfaces to implementations in the way Spring's implicit Bean wiring or TypeScript's injection tokens require. Filters remove build artifacts, spurious cross-language imports, and false cross-service edges.

**Post-processing:** HTTP API edges connect frontend URL calls to matching backend routes. Community detection (Leiden → Louvain → connected components fallback) partitions the graph into architectural clusters. A structural report identifies god nodes, surprising cross-cluster connections, and hub files.

---

## Output Structure

After a scan, context map files are updated at the project root (existing user content is preserved) and the knowledge graph lands in `.codebeacon/`:

```
project-root/
  CLAUDE.md              ← AI context map (codebeacon block merged; user content kept)
  .cursorrules           ← Cursor IDE context (same merge strategy)
  AGENTS.md              ← OpenAI Agents / Codex context (same merge strategy)
  .codebeacon/
    beacon.json          ← full knowledge graph; embeds `meta.built_at_commit`
    beacon.html          ← D3 collapsible-tree viewer (open in browser)
    callflow.html        ← Mermaid call-flow diagrams grouped by community
    REPORT.md            ← god nodes, surprising connections, hub files, freshness
    wiki/
      index.md           ← global index (~200 tokens)
      overview.md        ← platform stats + cross-project connections
      routes.md          ← all routes table
      cross-project/
        connections.md   ← cross-service edges
      <project>/
        index.md
        routes.md
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian vault (one note per graph node)
    semantic/
      pending/           ← prepare writes chunk_NNN.jsonl here (≤ --chunk-size tasks each)
        chunk_001.jsonl
        chunk_002.jsonl
      results/           ← agent writes a matching chunk_NNN.jsonl per pending file
        chunk_001.jsonl
      original/          ← apply moves done chunks here (durable archive)
        chunk_001.jsonl
        chunk_002.jsonl  ← (older runs accumulate; chunk numbers are monotonic)
```

### Deep Dive Mode

With `--deep-dive`, each sub-project also gets its own `.codebeacon/` directory and `CLAUDE.md`, so AI sessions opened inside a sub-project have full project-specific context:

```
workspace/
  CLAUDE.md                   ← combined (all projects)
  .cursorrules
  AGENTS.md
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← combined knowledge graph
    beacon.json
    wiki/
    obsidian/
  api-server/
    CLAUDE.md                 ← api-server only
    .codebeacon/              ← api-server graph
      beacon.json
      wiki/
      obsidian/
  frontend/
    CLAUDE.md                 ← frontend only
    .codebeacon/              ← frontend graph
      beacon.json
      wiki/
      obsidian/
```

Claude Code loads `CLAUDE.md` hierarchically, so opening a session in `api-server/` loads both the parent workspace overview **and** the project-specific details.

To update from any sub-project directory after the initial scan:

```bash
# Initial deep-dive scan
codebeacon scan /workspace --deep-dive

# Later, from any sub-project — finds the parent config and updates ALL projects
cd /workspace/api-server
codebeacon scan . --update
```

---

## AI Integration

### Claude Code Skill (`/codebeacon`)

Install codebeacon as a Claude Code slash command:

```bash
pip install codebeacon
codebeacon install
```

This copies `SKILL.md` to `~/.claude/skills/codebeacon/` and registers the `/codebeacon` trigger in `~/.claude/CLAUDE.md`. Restart your Claude Code session, then type `/codebeacon` to scan the current directory.

```
/codebeacon                       # scan current directory + auto AI-semantic
/codebeacon /path/to/project      # scan a specific path  + auto AI-semantic
/codebeacon sync                  # re-scan from codebeacon.yaml + auto AI-semantic
/codebeacon <path> --no-semantic  # scan only, skip the AI-semantic step
/codebeacon <path> --wiki-only    # regenerate wiki from existing beacon.json
/codebeacon semantic-prepare      # emit a fresh tasks file only
/codebeacon semantic-apply        # merge a results file the agent already wrote
/codebeacon serve <path>          # start MCP server pointing at .codebeacon/
/codebeacon query <term>          # search the graph
/codebeacon path <src> <tgt>      # shortest path
/codebeacon upgrade               # pip upgrade + refresh this skill (then restart Claude Code)
```

By default `scan` and `sync` invocations automatically run the **AI-semantic** pipeline at the end (see the [AI-Semantic Enrichment](#ai-semantic-enrichment-via-the-codebeacon-skill) section). The agent uses whatever model your Claude Code session is currently running on — Opus, Sonnet, Haiku — codebeacon never hardcodes a model and never needs an API key.

### Updating to a new version

Run **one** command from anywhere:

```bash
codebeacon upgrade
```

This pip-upgrades the package, then re-runs `codebeacon install` so `~/.claude/skills/codebeacon/SKILL.md` is overwritten with the new release's copy. Restart your Claude Code session for the new SKILL.md to load. If codebeacon is installed in editable mode (`pip install -e .`), the pip step is skipped — pass `--force` to upgrade anyway.

### MCP Server

Run codebeacon as a persistent MCP server so any MCP-compatible client can query your knowledge graph directly.

**Step 1 — scan your project:**
```bash
codebeacon scan .
```

**Step 2 — add to your MCP client config:**

**Claude Code** (`.claude.json` in project root or `~/.claude.json` globally):
```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "codebeacon",
      "args": ["serve"]
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "codebeacon",
      "args": ["serve", "--dir", "/path/to/.codebeacon"]
    }
  }
}
```

**Available MCP tools** once connected:

| Tool | Description |
|------|-------------|
| `beacon_wiki_index` | Global project overview (routes, services, entities count) |
| `beacon_wiki_article` | Read a specific wiki article by path |
| `beacon_query` | Search nodes by label substring |
| `beacon_path` | Shortest dependency path between two nodes |
| `beacon_blast_radius` | Upstream callers + downstream affected nodes |
| `beacon_routes` | List all HTTP routes, filterable by project |
| `beacon_services` | List all services/classes, filterable by project |

---

## Installation Options

```bash
pip install codebeacon              # all language grammars included
pip install codebeacon[cluster]     # + Leiden community detection (graspologic)
pip install --upgrade codebeacon    # upgrade to latest version with all dependencies
```

All language parsers (Java, Kotlin, Python, JavaScript, TypeScript, Go, Ruby, PHP, C#, Rust, Swift, HTML, Svelte) are bundled by default — no extra flags needed.

---

## CLI Reference

```bash
# Scan a project or workspace
codebeacon scan <path> [options]
codebeacon scan .                         # current directory
codebeacon scan /workspace                # workspace root (multi-project)
codebeacon scan . --update                # incremental: mtime/size fast path + content-hash fallback
codebeacon scan . --wiki-only             # skip re-extraction, regenerate wiki/obsidian/context map from existing beacon.json
codebeacon scan . --obsidian-dir <path>   # write Obsidian vault to custom location
codebeacon scan . --semantic              # enable structured-comment semantic extraction (Javadoc/JSDoc/docstring refs)
codebeacon scan . --list-only             # detect frameworks only, don't extract
codebeacon scan /workspace --deep-dive    # per-project + combined workspace outputs

# Config-driven mode
codebeacon init [path]                    # auto-generate codebeacon.yaml
codebeacon sync                           # run from codebeacon.yaml (auto-appends new workspace projects)
codebeacon sync --config <file>           # use a specific config file
codebeacon sync --no-rediscover           # don't auto-append newly added projects (hand-curated yaml mode)

# AI-semantic enrichment (the agent does the LLM work, codebeacon does the bookkeeping)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # rehydrate archive (.codebeacon/semantic/original/*.jsonl) onto
                                          # the fresh graph, prune entries pointing at missing nodes,
                                          # then emit every NEW candidate (god folders + hub files +
                                          # unresolved targets) into .codebeacon/semantic/pending/
                                          # chunk_NNN.jsonl (--chunk-size tasks per file, default 10).
                                          # `--max-tasks` is an optional cap (0 = no cap = emit all).
                                          # task_id includes a content hash, so a file whose semantic
                                          # content changes between scans is automatically re-emitted.
codebeacon semantic-apply   [--dir .codebeacon]
                                          # for each .codebeacon/semantic/results/chunk_NNN.jsonl the
                                          # agent has written, merge edges (INFERRED references) into
                                          # beacon.json and MOVE the pending chunk into
                                          # .codebeacon/semantic/original/chunk_NNN.jsonl (durable
                                          # archive). Regenerates wiki/obsidian/context map.

# Query the knowledge graph
codebeacon query <term> [--dir .codebeacon] [--limit N]   # search nodes by label substring
codebeacon path <source> <target> [--dir .codebeacon]     # shortest dependency path

# Multi-developer support (git plumbing)
codebeacon hook install [path]            # install merge driver + post-commit incremental rebuild
codebeacon merge-driver <base> <cur> <other>  # invoked by git after `hook install`; union-merges beacon.json

# Integrations
codebeacon serve [--dir .codebeacon]      # start MCP server (stdio)
codebeacon install                        # install Claude Code skill
codebeacon upgrade                        # pip install --upgrade + refresh ~/.claude/skills/codebeacon/SKILL.md
                                          # (`--force` to upgrade even when installed in editable mode)
```

---

## AI-Semantic Enrichment (via the `/codebeacon` skill)

Tree-sitter parsing finds what's in the AST. **AI-semantic** finds what's only in the *comments* — the `@see UserService` in a Javadoc, the `:class:`OrderRepository`` in a Python docstring, the contractual references documented next to a route handler. codebeacon ships two layers for this:

| Layer | Flag | Cost | What it catches |
|---|---|---|---|
| Structured-comment parsing | `--semantic` | free, local, no LLM | Javadoc `@see` / `{@link}`, JSDoc `@see` / `@param` types, Python `:class:` / `:func:` / `See Also` |
| **AI-semantic** | auto in `/codebeacon` skill | uses the agent's existing model — **no extra API key** | unresolved class/type/service references that regex can't catch (free-form prose, indirect mentions, type-only hints) |

The CLI itself never makes an LLM API call. The AI-semantic layer is intentionally **owned by the running agent** inside the `/codebeacon` Claude Code skill — that way the user's model choice (Opus / Sonnet / Haiku / anything) is honored, and codebeacon never needs `ANTHROPIC_API_KEY` or any cloud configuration.

### How it runs

When you invoke `/codebeacon` in Claude Code:

1. `scan` / `sync` builds `beacon.json` from the AST (no LLM).
2. `codebeacon semantic-prepare` rehydrates the archive at `.codebeacon/semantic/original/*.jsonl` onto the fresh graph, **prunes** archive entries whose source node no longer exists, and writes new task chunks to `.codebeacon/semantic/pending/chunk_NNN.jsonl` (≤ `--chunk-size` tasks per file, default 10). Chunk numbers continue from where the durable archive left off, so they never collide.
3. The skill iterates the pending chunks **one chunk at a time**. For each `pending/chunk_NNN.jsonl`, the agent (using its current model) reads each task's `excerpt` and writes a matching `semantic/results/chunk_NNN.jsonl`.
4. `codebeacon semantic-apply` merges the results as `INFERRED references` edges into `beacon.json` and **moves** each finished `pending/chunk_NNN.jsonl` into `semantic/original/chunk_NNN.jsonl` (with the applied edges spliced in for auditability). Result files are deleted; wiki + obsidian + context map regenerated.
5. Next scan: `semantic-prepare` reads every chunk under `original/`, applies their edges to the freshly built graph (so historical inferences don't disappear), and skips any task whose `task_id` is already on file. `task_id` is `SHA1(file_path | node_id | excerpt_hash[:8])` — a file whose semantic content changes earns a new id and gets re-analysed automatically.

This gives you incremental, idempotent enrichment: the agent never re-analyses the same `(file, content)` twice, accumulated AI signal survives every rescan, and chunked files keep the agent's working set small.

### Direct CLI usage

If you're not running through the skill (e.g. CI), you can drive the same two commands manually and supply your own `results/chunk_NNN.jsonl` files:

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# .codebeacon/semantic/pending/chunk_001.jsonl ... now exist.
# For each pending chunk, write a matching results/chunk_NNN.jsonl. Each line:
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### Opt out

Pass `--no-semantic` (or `--wiki-only`, or `--list-only`) when invoking the skill to skip the AI step entirely. The structured-comment layer still runs when you pass `--semantic` to `scan` / `sync`.

---

## Visual Exploration

Every scan writes two self-contained HTML files alongside `beacon.json`:

```
.codebeacon/beacon.html      # D3 v7 collapsible tree — open in any browser
.codebeacon/callflow.html    # Mermaid architecture diagrams, one per community
```

No build step, no static server, no copy-paste. Open the file, click to expand
projects → types → nodes; hover for source paths and degree. `callflow.html`
groups your graph by community and renders each as a Mermaid flowchart, with
the cross-community out-edges listed in a collapsed table.

---

## Multi-Developer Workflow

Two developers running `codebeacon scan` on the same branch produce two
slightly different `beacon.json` files — historically a merge conflict
hotspot. `codebeacon hook install` solves this:

```bash
codebeacon hook install            # in the repo root
```

This registers:

- a **git merge driver** that union-merges two `beacon.json` files into one
  (nodes deduped by ID, edges deduped by `(source, target, relation)`),
- a `.gitattributes` entry pointing `*beacon.json` at the driver,
- a **post-commit hook** that runs `codebeacon scan . --update` in the
  background so the graph never falls behind your commits. Output goes to
  `~/.cache/codebeacon-rebuild.log`.

The merge driver always exits 0 — a graph regen never blocks a real merge.

---

## Safety Guarantees

A few invariants the writer enforces on every successful scan:

| Guard | What it prevents |
|---|---|
| **Shrink guard** | A partial-extraction failure or interrupted run can never overwrite a larger complete `beacon.json`. Pass `force=True` from the API to bypass. |
| **Atomic write** | `beacon.json` is written via `os.replace`, so the file is either complete or untouched — no half-written graphs. |
| **`built_at_commit` stamp** | `beacon.json` embeds `meta.built_at_commit` (full SHA) and `REPORT.md` shows the short SHA. If HEAD has advanced past it, the report flags the graph as `⚠ stale` with a one-line remediation hint. |
| **Frontmatter / label hardening** | YAML frontmatter values are single-quoted and escape U+2028, U+2029, tabs, and C0 controls; MCP tool output runs every label through the same sanitizer. A malicious identifier in source code cannot break Obsidian's YAML parser or inject control sequences into an LLM agent's context. |

---

## Configuration

Run `codebeacon init` to generate `codebeacon.yaml`, or write it manually:

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # optional: auto-detected if omitted

  - name: frontend
    path: ./frontend
    type: react

output:
  dir: .codebeacon
  wiki: true
  obsidian: true
  context_map:
    targets: [CLAUDE.md, .cursorrules, AGENTS.md]

wave:
  auto: true
  chunk_size: 300              # files per chunk
  max_parallel: 5              # parallel threads

semantic:
  enabled: false               # structured-comment extraction; override with --semantic.
                               # AI-semantic does NOT live here — it is invoked by the
                               # /codebeacon skill, see "AI-Semantic Enrichment" above.

deep_dive: false               # set to true to generate per-project outputs
```

### .codebeaconignore

Place a `.codebeaconignore` file at your project root to exclude directories or files from scanning. Syntax matches `.gitignore` — last-match-wins with `!` negation, anchored patterns (`/foo`), dir-only patterns (`build/`), and comments:

```
# .codebeaconignore

# directories
build/
generated/
fixtures/

# anchored to root only
/scripts/local-only.ts

# glob patterns
*.gen.ts
**/snapshots/**

# re-include a specific file even though build/ is ignored
!build/manifest.ts
```

`!pattern` re-includes a previously-ignored path; later rules override earlier ones. The walker prunes directories whose name matches the rule set, but defers pruning when any negation rule could un-ignore a nested file.

---

## How It Compares

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| Route / controller analysis | ✅ | ❌ | ✅ |
| Service / DI graph | partial | ✅ | ✅ |
| Interface → Impl resolution | ❌ | ❌ | ✅ |
| Entity / ORM model extraction | ✅ | ❌ | ✅ |
| Frontend component analysis | ✅ | ❌ | ✅ |
| Community detection | ❌ | ✅ | ✅ |
| Obsidian vault export | ❌ | ✅ | ✅ |
| MCP server | ✅ | ❌ | ✅ |
| AI context map (CLAUDE.md) | ✅ | ✅ | ✅ |
| Multi-project workspace | partial | ❌ | ✅ |
| Python-based | ❌ | ✅ | ✅ |

codebeacon is not a replacement for either tool — it's the union of what both do, built around a shared extraction and graph layer.

---

## Benchmarks

| Codebase | Stack | Files | Nodes | Edges | Communities | Scan time |
|----------|-------|-------|-------|-------|-------------|-----------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3 projects) | 444 | 382 | 553 | 175 | ~12s |

---

## Privacy & Security

All AST processing is local. Your source code never leaves your machine when you run codebeacon directly.

- Tree-sitter AST parsing runs entirely in-process
- No telemetry, no analytics, no network calls during normal operation
- The CLI **never calls an LLM provider on its own** — codebeacon ships no API client, no key handling, no model name
- `--semantic` activates **structured-comment parsing only** (Javadoc `@see` / `{@link}`, JSDoc `@see` / `@param` types, Python `:class:` / `:func:` / `See Also`). Fully local.
- **AI-semantic** (the deeper LLM-driven layer) is invoked by the `/codebeacon` Claude Code skill. The agent reads `semantic-tasks.jsonl`, runs the analysis under whatever model the user already picked, and writes `semantic-results.jsonl`. The Python CLI only prepares the task batch and merges the results — it has no idea which model was used. Pass `--no-semantic` in the skill to skip the LLM step entirely.

---

## Contributing

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

The easiest entry point for adding new framework support is writing a tree-sitter query file in `codebeacon/extract/queries/`. See [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md) for the full guide — it walks through grammar setup, `.scm` query syntax, capture naming conventions, and how to wire up a new extractor.

Contributions welcome: new framework queries, language parsers, output formats, and benchmark datasets.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgments

Built on [tree-sitter](https://tree-sitter.github.io/tree-sitter/) for structural AST parsing, [NetworkX](https://networkx.org/) for graph operations, and [graspologic](https://microsoft.github.io/graspologic/) for Leiden community detection.

Inspired by the complementary approaches of [codesight](https://github.com/Houseofmvps/codesight) and [graphify](https://github.com/safishamsi/graphify).
