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
- **Multiple output formats** — JSON knowledge graph, Markdown wiki, Obsidian vault, AI context maps, MCP server
- **Community detection** — Leiden/Louvain clustering reveals your actual architectural boundaries
- **Incremental cache** — SHA-256 based; only re-extracts files that changed since the last scan
- **Zero configuration** — auto-detects frameworks and languages; generates `codebeacon.yaml` for repeat runs
- **Deep-dive mode** — `--deep-dive` generates per-project `.codebeacon/` + `CLAUDE.md` for every sub-project; running `codebeacon scan . --update` from any sub-project folder automatically syncs all projects in the workspace

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
    beacon.json          ← full knowledge graph (node-link JSON, queryable)
    REPORT.md            ← god nodes, surprising connections, hub files
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
/codebeacon                  # scan current directory
/codebeacon /path/to/project # scan a specific path
/codebeacon sync             # re-scan from codebeacon.yaml
```

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
codebeacon scan . --update                # incremental: only re-extract changed files
codebeacon scan . --wiki-only             # skip re-extraction, regenerate wiki/obsidian/context map from existing beacon.json
codebeacon scan . --obsidian-dir <path>   # write Obsidian vault to custom location
codebeacon scan . --semantic              # enable LLM semantic extraction
codebeacon scan . --list-only             # detect frameworks only, don't extract
codebeacon scan /workspace --deep-dive    # per-project + combined workspace outputs

# Config-driven mode
codebeacon init [path]                    # auto-generate codebeacon.yaml
codebeacon sync                           # run from codebeacon.yaml
codebeacon sync --config <file>           # use a specific config file

# Query the knowledge graph (coming soon)
codebeacon query <term>                   # search nodes and edges
codebeacon path <source> <target>         # shortest path between two nodes

# Integrations
codebeacon serve [--dir .codebeacon]      # start MCP server (stdio)
codebeacon install                        # install Claude Code skill
```

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
  enabled: false               # override with --semantic flag

deep_dive: false               # set to true to generate per-project outputs
```

### .codebeaconignore

Place a `.codebeaconignore` file at your project root to exclude directories or files from scanning. Syntax is the same as `.gitignore` — one pattern per line, `#` for comments.

```
# .codebeaconignore
generated/
build/
*.generated.ts
fixtures/
```

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

All processing is local. Your source code never leaves your machine.

- Tree-sitter AST parsing runs entirely in-process
- No telemetry, no analytics, no network calls during normal operation
- The `--semantic` flag (disabled by default) activates two extraction modes:
  1. **Structured comment parsing** (no LLM required) — infers cross-references from Javadoc (`@see`, `{@link}`), Python docstrings (`:class:`, `:func:`), and JSDoc (`@see`, `@param` types)
  2. **LLM inference** (optional) — when `ANTHROPIC_API_KEY` is set, sends code excerpts to the Claude API for deeper relationship inference; only enable it explicitly

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
