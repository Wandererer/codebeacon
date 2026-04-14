---
name: codebeacon
description: Scan a codebase → AST extraction → knowledge graph → wiki + CLAUDE.md context map. Supports 27 frameworks (Spring Boot, NestJS, Django, FastAPI, Flask, Rails, Express, Fastify, Koa, React, Next.js, Vue, Nuxt, Angular, SvelteKit, Gin, Echo, Fiber, Laravel, Actix-Web, Axum, Tauri, Rocket, Warp, ASP.NET Core, Vapor, Ktor).
trigger: /codebeacon
---

# /codebeacon

Scan source code with AST analysis → build a knowledge graph → generate a navigable wiki + `CLAUDE.md` context map ready for AI agents.

## Usage

```
/codebeacon                         # scan current directory
/codebeacon <path>                  # scan specific path or workspace root
/codebeacon <path> --update         # incremental: only reprocess changed files
/codebeacon <path> --wiki-only      # regenerate wiki without re-extracting
/codebeacon <path> --deep-dive      # per-project outputs + combined workspace
/codebeacon sync                    # sync from codebeacon.yaml (multi-project)
/codebeacon serve <path>            # start MCP server pointing at .codebeacon/
```

## What You Must Do When Invoked

If no path was given, use `.` (current directory). Do not ask the user for a path.

Follow these steps in order.

### Step 1 — Ensure codebeacon is installed

```bash
python3 -c "import codebeacon" 2>/dev/null || pip install codebeacon -q --break-system-packages 2>&1 | tail -5
python3 -c "import sys; open('.codebeacon_python', 'w').write(sys.executable)"
```

In every subsequent bash block, replace `python3` with `$(cat .codebeacon_python)`.

If import succeeds, print nothing and move to Step 2.

### Step 2 — Detect mode and run

Check if `codebeacon.yaml` exists in the target directory:

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

The command prints wave progress as it goes:
- Framework detection per project
- `[pct%] done/total files processed` (wave progress per project)
- Route / Service / Entity / Component counts after each project
- Final: `Nodes: N, Edges: E, Communities: K`

Let it run to completion. Do not interrupt.

### Step 3 — Report results

After the command exits, read the REPORT.md:

```bash
TARGET="${1:-.}"
OUTPUT_DIR="$TARGET/.codebeacon"
[ -f "$OUTPUT_DIR/REPORT.md" ] && head -40 "$OUTPUT_DIR/REPORT.md"
```

Then summarise for the user:
- Which projects/frameworks were detected
- Total nodes, edges, communities
- Output location (`CLAUDE.md` at project root, `.codebeacon/wiki/`, `.codebeacon/beacon.json`, etc.)
- Any god nodes or surprising connections worth mentioning

### Step 4 — (Optional) MCP serve

If the user asked for `serve`:

```bash
TARGET="${1:-.}"
$(cat .codebeacon_python) -m codebeacon serve --dir "$TARGET/.codebeacon"
```

This blocks — run it only when the user explicitly wants an MCP server.

## Output structure

```
project-root/
  CLAUDE.md              ← AI context map (codebeacon block merged; user content preserved)
  .cursorrules           ← Cursor IDE context (same merge strategy)
  AGENTS.md              ← OpenAI Agents context (same merge strategy)
  .codebeacon/
    beacon.json          ← full knowledge graph (node-link JSON)
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
    obsidian/            ← Obsidian vault (one note per node)
```

## Supported frameworks

| Language | Frameworks |
|----------|-----------|
| Java/Kotlin | Spring Boot, Ktor |
| Python | Django, FastAPI, Flask |
| JavaScript/TypeScript | Express, Fastify, Koa, NestJS, React, Next.js, Vue, Nuxt, Angular, SvelteKit |
| Go | Gin, Echo, Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web, Axum, Tauri, Rocket, Warp |
| C# | ASP.NET Core |
| Swift | Vapor |
