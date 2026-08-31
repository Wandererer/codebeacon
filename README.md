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

## What's new in 0.7.1

The largest audit release yet: a dual upstream-parity sweep (graphify v0.9.13–v0.9.53 / issues #1777–#3235, plus codesight #50–#55) verified against codebeacon with mandatory reproduction — **~70 confirmed defects fixed** by ten parallel fixers, every fix mutation-tested, then adversarially reviewed by the lead with real-CLI integration runs. Suite: 885 → 1,481 tests.

- **The JS/TS graph roughly doubled** — exported lowercase arrows, `const`s, and object-literal members (`export const useAuthStore = …`, `authUtils.clear`) finally become nodes: on a real 865-file Next.js app, component nodes went **960 → 2,237** and files contributing nothing fell 406 → 108. Imports now resolve by **path** first (relative specifiers, `tsconfig`/`jsconfig` aliases with `extends` chains and `${configDir}`, package suffixes) before falling back to labels — so `from codebeacon.graph.build import …` can no longer bind to an unrelated `build` symbol, and the "High-Impact Files" list in CLAUDE.md reflects reality. Plain-JS `class X extends Y` heritage and dynamic `await import()` edges are captured too.
- **Route prefixes compose like the real frameworks** — verified against running FastAPI/Express/Flask servers: `include_router(prefix=)` composes with the router's own prefix, attribute-form includes (`app.include_router(pkg.router, …)`, `@pkg.router.get`) no longer vanish, same-file cascaded mounts multiply out, a router mounted twice yields both routes, and Flask's `register_blueprint(url_prefix=)` correctly *overrides*. Known limit: a mount chain crossing **files** still isn't composed.
- **Interface→impl DI resolution actually works now** — a serialization boundary in the extraction pipeline had been silently discarding `implements`/`extends` since 0.6.x, so the whole feature was dead end-to-end while the wiki looked right. Fixed, cache-invalidated, and boundary-tested through the real pipeline. DI binding is also evidence-gated now: no more cross-language or cross-project fabrications (a Spring service can no longer "inject" a React component), ambiguous multi-implementation cases bind only via the `*Impl` naming convention at an explicit `AMBIGUOUS` confidence, and a duplicate edge records its second relation under a new `also` attribute instead of overwriting.
- **Node identity is deterministic and extension-aware** — `Button.tsx` and `Button.jsx` are two nodes (previously one silently absorbed the other — 6.3% of declarations on codebeacon's own repo); node IDs no longer depend on thread completion order or the checkout directory, so wiki/obsidian filenames stop flapping between runs. Colliding labels get the shortest distinguishing path suffix. (IDs of previously-collapsed nodes will churn once on upgrade.)
- **The ignore layer matches git much more closely** — nested `.gitignore` files apply to their own subtree (a monorepo's `app/.gitignore` no longer gets ignored, which used to pull tens of thousands of build files into the scan), `.git/info/exclude` is honored, linked worktrees are detected structurally instead of doubling the corpus, and BOM'd / UTF-16 / NFD-encoded ignore files decode instead of silently dropping rules. Ambiguous directory names (`env/`, `build/`, `public/`, `coverage/`, …) are pruned only with corroborating evidence — a UVM `env/` testbench or a Python package named `coverage/` stays in the graph. Matching is ~19× faster, and a new `ignored.json` diagnostic records *why* every subtree was skipped.
- **The shrink guard now guards the paths that matter** — it used to be disarmed by the mere presence of `--update`, i.e. on exactly the unattended paths (watch, git hooks, CI); a permission error could silently halve your committed graph. It now attributes every removed node to its source file (deleted / newly-ignored / **unexplained** — only the last refuses, with a real `--force` flag), stays armed everywhere, treats an unreadable subtree as "unknown, don't waive", and warns when edges collapse even though nodes held steady.
- **`scan → knowledge → scan` no longer wedges** — 0.7.0's documented flow either exited 1 ("refusing to shrink") or silently discarded your notes overlay. The guard is tier-aware now and the knowledge overlay is **auto-reapplied after every scan**; deleting a note prunes exactly that note. Authored `[[wikilinks]]` finally create edges (they were parsed and then dropped — 100% loss), notes carry `node_kind`/frontmatter, and generated files (CLAUDE.md, KNOWLEDGE.md) are no longer re-ingested as notes.
- **A committed index stays clean** — an unchanged rescan now rewrites **zero** committed files (was: every one of them, ~31k-file churn upstream): `built_at_ts` derives from the commit, exports write only on content change, and the machine-local AST cache git-ignores itself. HTML exports (`beacon.html`, `callflow.html`) ship their JS **offline by default** (vendored d3 + mermaid under `_assets/`) — matching the air-gapped posture; set `output.html_assets: cdn` to keep the old behavior. Absolute build-machine paths no longer leak into any artifact.
- **MCP answers you can trust programmatically** — tool failures return `isError: true` with the actionable message (instead of success-shaped error prose, or a protocol error the client swallows); name resolution prefers an exact match before substrings, so `blast_radius("User")` no longer answers about `UserServiceImpl`; every tool honors a `token_budget` (default 2,000 tokens) and announces truncation against the true total.
- **Robustness & security sweep** — `.csproj` XML is parsed with a DOCTYPE/ENTITY screen; model-facing text (MCP output, CLAUDE.md) neutralizes chat-template control tokens by form (`<|…|>`, `[INST]`); `hook install` works in git worktrees and never leaves a repo half-configured; `install`/`upgrade` back up a hand-edited SKILL.md instead of clobbering it, and an unterminated marker can no longer delete user content below it; a cp949/latin-1 CLAUDE.md doesn't crash the scan; `codebeacon … | head` exits cleanly; watch mode no longer re-triggers itself on Linux inotify events; Leiden clustering is seeded, so communities stop drifting 12% per rescan.

Upgrade notes: node IDs for previously-collapsed declarations churn once; semantic `task_id`s are invalidated once (tasks now hash the whole file, fixing "edits past char 4,000 never re-analyzed"); the AST cache is invalidated once (schema stamp); new edge attribute `also`, new confidence value `AMBIGUOUS`, new `verification` marker on semantic-minted externals. If your repo already committed `.codebeacon/cache/`, run `git rm --cached -r .codebeacon/cache` once — the new self-ignoring `.gitignore` cannot untrack files that are already tracked.

---

## What's new in 0.7.0

A capability release rather than a bug sweep: codebeacon grows a live file-watcher, links your design notes into the code graph, ships two new front-ends (an npm launcher for the MCP server and a GitHub Action), and tightens what it indexes by default. Every feature stays local-first — the core scan still needs no network, no cloud, and no model.

- **`codebeacon watch` keeps the index live** — a debounced file-watcher (`codebeacon watch [path] [--debounce 2.0] [--once] [--exclude PATTERN]`) re-syncs the graph whenever watched source files change. A burst of edits — a 500-file `git checkout`, a branch switch — coalesces into a single resync, and the watcher reuses the scanner's exact ignore rules so writing the index never wakes it into a loop over its own `.codebeacon/` output. Needs the new optional extra: `pip install 'codebeacon[watch]'` (watchdog).
- **Design notes link into the code graph** — `codebeacon knowledge` now writes its notes (ADRs, meeting notes, retros, specs) *into* `beacon.json` when an index already exists: an explicit file-path reference becomes a trusted `references` edge, and a distinctive symbol mention (`PaymentService`, never a bare `User`) becomes an `AMBIGUOUS` `mentions` edge — so an agent reading the graph learns *why* a service is shaped the way it is. Because `codebeacon scan` rebuilds the code graph from source alone and drops this overlay, **re-run `codebeacon knowledge` after a scan** to restore the links.
- **`beacon_knowledge` MCP tool** — a new tool searches notes by keyword and/or lists the notes linked to a given code node, exposing the decision trail behind the code directly over MCP.
- **npm launcher for the MCP server** — `@codebeacon/mcp` lets MCP clients start the server the npx-first way they expect (`"command": "npx", "args": ["-y", "@codebeacon/mcp"]`). The zero-dependency Node shim resolves a working codebeacon via PATH → `uvx` → `pipx run` → `python3 -m codebeacon` and forwards stdio untouched. See [`npm/README.md`](npm/README.md). (Ships with 0.7.0; not yet published to npm.)
- **GitHub Action for PR context** — a composite action comments on every pull request with the affected slice of your committed knowledge graph: the wiki articles the change touches, the upstream blast radius, and any high-impact hub files it edits — an architecture-drift check for AI-era review. Requires a committed `.codebeacon/` index, `fetch-depth: 0`, and `permissions: pull-requests: write`. See [`action/README.md`](action/README.md) and [`action/examples/pr-context.yml`](action/examples/pr-context.yml).
- **Workspace CLAUDE.md stays under ~200 lines** — in a multi-project workspace the root `CLAUDE.md` now keeps only the shared overview and moves per-project detail into scoped `.claude/rules/codebeacon-<project>.md` files whose `paths:` frontmatter loads them only when that project's files are touched (following Anthropic's own guidance for context files). Single-project output is unchanged; set `output.context_map.rules_split: false` for the old monolithic file. Duplicate project rows are also collapsed.
- **Test fixtures are ignored by default** — `tests/fixtures/`, `test/fixtures/`, and `__fixtures__/` at any depth are now default-ignored, so a project's synthetic test inputs stop injecting fake routes and services into the graph (codebeacon's own self-scan had reported a fixture `main.py` as five "routes"). It is the lowest-precedence rule, so a `.codebeaconignore` line `!tests/fixtures/` re-includes them, and pointing a scan *at* a fixture directory still collects it.
- **Warp route extraction is real now** — Warp's filter-combinator routes are actually extracted: `warp::path!(...)` and `warp::path("x")` segments, method combinators (`warp::get()` / `post()` / …), and `.map` / `.and_then` handlers are correlated by their enclosing binding into whole routes. Honest limits (spelled out in the query header): filters joined by `.or(...)` inside one binding collapse into a single concatenated route, and `warp::path::param()` filter-call segments and closure handlers are left unresolved.

---

## What's new in 0.6.9

The largest audit release to date: a dual upstream-parity sweep (the first-ever full audit of codesight's tracker, plus graphify v0.9.4–v0.9.12 / issues through #1776) combined with an independent multi-agent bug hunt over codebeacon itself. Every candidate was reproduced before fixing, every fix was mutation-tested, and an adversarial second review then attacked the fixes themselves — catching 18 further holes before release. **48 real bugs fixed.**

- **Your CLAUDE.md is safe now** — on a hand-written CLAUDE.md (e.g. from `/init`), the merge step could mistake the user's own `## Architecture` / `## Common Commands` sections for codebeacon output and delete them. The strip now runs only on files that positively fingerprint as codebeacon-generated, and it is anchored to the generated block — your sections survive. `codebeacon.yaml` is also written atomically now (and through symlinks, preserving file modes), so an interrupted write can't destroy a hand-curated config.
- **Files no longer vanish from the index silently** — uppercase extensions (`App.PY`, `Page.TSX`) were skipped; source modules named after credentials (`api_key_manager.go`, `access_token_service.py`) were dropped by the secret-file heuristic; one non-UTF-8 byte in a `.gitignore` crashed the whole scan; and a repo checked out under a folder named `build/` or `dist/` had its **entire graph erased** by the artifact filter matching ancestor directories. All fixed; skipped symlinks now get one grouped warning instead of silence.
- **`.gitignore` handling now matches git exactly** — negation semantics (`dir/` + `!dir/keep.txt`) are differential-tested against `git check-ignore` across every rule shape; a file under an excluded directory can no longer be re-included, exactly like git. The standard `dir/*` + `!dir/keep` rescue idiom works as before.
- **Same-named projects coexist** — two (or three) sub-projects all named `frontend` used to collapse into one: colliding node IDs silently dropped routes, and their wiki/obsidian folders overwrote each other. Duplicate names are now auto-disambiguated with a parent-directory prefix.
- **Route extraction got a correctness overhaul** — Express `app.use('/api', router)` mount prefixes are applied and chained `router.route(x).get().post()` yields every verb; Flask `register_blueprint` / FastAPI `include_router` prefixes no longer depend on where they appear in the file; Spring's `@RequestMapping(method = RequestMethod.X)` records the real verb instead of `ANY`; Next.js catch-all segments (`[...slug]`) are no longer garbled and `@slot` parallel routes are stripped from URLs; Laravel's canonical `class X extends Model` finally produces an entity (previously only fully-qualified bases matched — and `ViewModel` no longer sneaks in).
- **Phantom graph edges eliminated** — a lowercase import like `CONFIG` no longer case-folds onto an unrelated `Config` class (the false god-node pattern), imports never bind across a language boundary (`import time` → `time.ts`), DI bindings prefer the registering project instead of the first same-named class anywhere, and a same-named service + entity in one directory no longer collapse into a single node.
- **Exports are Windows-proof and crash-proof** — obsidian note names strip the full Windows-illegal character set (Flask `<string:id>` routes used to break the export on Windows) and guard reserved device names; `None` labels no longer crash the wiki, call-flow HTML, or obsidian exporters; git hooks are written with LF line endings so they execute on Windows; and long project names can't blow past filesystem limits mid-export.
- **One bad input can't kill long-running surfaces** — the MCP server survives malformed JSON-RPC messages instead of dying; a corrupt `beacon.json` or AST cache (including invalid UTF-8 and null/malformed collections) is backed up and reported instead of crashing `affected`, `serve`, or the merge driver.
- **Byte-reproducible output** — node ordering no longer tracks thread-completion order and shared-entity annotations are sorted, so scanning an unchanged tree twice produces byte-identical `beacon.json`, wiki, and CLAUDE.md. The Leiden clustering backend (silently broken by a graspologic API change — it *never* ran) is back in service.
- **The config you write is the config that runs** — documented `codebeacon.yaml` settings (`wave.*`, `output.wiki/obsidian`, `context_map.targets`, `semantic.enabled`) were parsed and then ignored; they now drive the pipeline, `--list-only` is honored inside workspaces, and `codebeacon upgrade` gives the right command for uv-venv installs. Bonus consistency: the Projects table, Notes column, and Architecture section of CLAUDE.md now agree on one "Services" count, matching the wiki.

---

## What's new in 0.6.8

A graphify-parity audit of upstream v0.8.41–v0.9.3 (reported issues through #1568). Every candidate was reproduced against codebeacon before fixing and re-checked by an adversarial review pass; **7 real bugs** confirmed, headlined by a data-loss trap and a privacy leak.

- **`--obsidian-dir` can no longer delete your notes** — pointed at an existing Obsidian vault, the export swept *every* `.md` under it before regenerating, so it could wipe a real vault. codebeacon now refuses any directory it doesn't own (only a genuinely empty dir, or one carrying its `.codebeacon-vault.json` marker, is adopted) and skips the export with a clear message instead of deleting.
- **`.gitignore` is no longer silently disabled by `.codebeaconignore`** — adding a `.codebeaconignore` used to *replace* the repo's `.gitignore`, so a file excluded only by `.gitignore` (a neutrally-named `prod-dump.sql`, `customer-data.*`) would get indexed into the committed `.codebeacon/` artifacts. The two are now merged (`.codebeaconignore` wins on conflict); adding it can only ever exclude *more*.
- **No machine-absolute paths in committed artifacts** — edge/link `source_file` values (the bulk of `beacon.json`) and the `Source:` lines in wiki/obsidian notes kept absolute `/Users/you/...` paths, so the committed index wasn't portable and leaked local paths. All are now project-relative (edges included, and cross-project `shares_db_entity` files too).
- **Same-named symbols in different directories no longer overwrite each other's notes** — wiki/obsidian filenames were derived from the label with no case-folding, so on macOS/Windows `UserService` and `userService` collided and one note was silently lost. Filenames are now collision-salted and case-folded; punctuation-only labels (`@`) fall back to `unnamed` instead of a broken `@.md`.
- **A corrupt `beacon.json` no longer crashes** — `codebeacon affected`, the MCP server, and `--wiki-only` runs now back up a corrupt/truncated graph and report a clear "re-run scan" message instead of a raw traceback.
- **More React components are captured** — `react.scm` missed function-expression components (`const X = function() {…}`), bare-imported HOCs (`const X = forwardRef(…)` without the `React.` prefix), and non-exported `function X()` components. All three are now extracted.
- **Wiki links never dangle** — a link to a page that was never written is downgraded to plain text, and a link to an article in a sibling bucket (a service → its entity) is repaired to the correct relative path instead of pointing at a missing file.

---

## What's new in 0.6.7

Follow-ups to the 0.6.6 graphify-parity audit: grammar drift now fails loudly instead of silently, and ignore-file negations no longer slow scans down.

- **Grammar drift is a loud failure, not a silent empty graph** — when a tree-sitter query can't compile against a grammar it's *supposed* to support (e.g. a node-type rename in a future grammar bump), `run_query` now raises and the file is recorded as an `ExtractionFailure` instead of silently extracting nothing. Together with the 0.6.6 upper-bound pins and the "every query compiles against every grammar it claims" test, drift is now caught three independent ways.
- **A single `!` negation in `.codebeaconignore` no longer forces a full-tree walk** — one negation rule anywhere used to disable directory pruning *everywhere*, so the scanner descended into every excluded directory (`node_modules`, `build`, …) even when the negation couldn't possibly rescue anything there. Each ignored directory is now kept only if a negation could actually re-include a file beneath *it*; unrelated `!` rules cost nothing.
- **Ignore globs compile once** — the gitignore-style matcher memoizes each pattern's compiled regex instead of rebuilding it on every path check, speeding up discovery on deep trees with large ignore files. (Semantics unchanged.)

---

## What's new in 0.6.6

A graphify-parity audit of upstream v0.8.37–v0.8.40 (and reported issues through #1362): a verify-then-adversarially-refute sweep of 32 candidates confirmed **6 real bugs**. The headline — three framework extractors were silently producing *nothing*.

- **TypeScript Express / Koa / Fastify apps now extract routes** — `express.scm` hard-coded the JavaScript class-name node type, which is an "Impossible pattern" under the TypeScript grammar, so the whole query failed to compile and the error was swallowed: **TS Express apps extracted 0 routes**. (JavaScript apps worked, and the only test fixture was `.js`, so it went unnoticed.) The identical root cause hit `vue.scm` (Vue SFCs with a plain `<script>` → 0 components). Both now use a grammar-neutral node wildcard that compiles under JS and TS.
- **Kotlin files in Spring projects no longer error** — `spring_boot.scm` is a Java-grammar query but was allowed to run against Kotlin, emitting `Invalid node type: marker_annotation` and dropping every `.kt` file. Kotlin is now gated off cleanly (Kotlin Spring Boot would need its own query).
- **Tree-sitter grammars are pinned with upper bounds** — `pyproject.toml` pinned grammars open-ended (`>=0.23`), so a future grammar release that renames AST node types could silently re-break the queries. Every grammar now has a compatible-range ceiling, and a new test asserts every shipped `.scm` compiles against every grammar it claims to support.
- **The extraction cache is versioned** — after upgrading codebeacon, an incremental `--update` could reuse results extracted by the *old* version for unchanged files (a content hash can't detect that the extractor itself changed). The cache is now stamped with the codebeacon version and discarded on mismatch.
- **Accented / non-ASCII names resolve on macOS** — `codebeacon query` / `path` / MCP and `affected` now Unicode-NFC-normalise labels and paths, so a name copied from a macOS filename (stored as NFD) matches the NFC label in the graph (e.g. `Auditoría`).
- Plus: a corrupt extraction `cache.json` is backed up and rebuilt instead of being silently reset and then overwritten.

---

## What's new in 0.6.5

`codebeacon upgrade` now works everywhere — it previously assumed a plain pip install and died silently on machines where that wasn't true.

- **Install-manager detection** — the upgrade command detects how codebeacon was installed and runs the matching tool: `pip install --upgrade` for pip installs, `pipx upgrade codebeacon` for pipx, `uv tool upgrade codebeacon` for uv. pipx/uv tool venvs ship *without* a `pip` module, so the old unconditional `python -m pip` call failed before doing anything.
- **Upgrade verification** — after the upgrade a fresh interpreter re-reads the installed version and reports `0.6.4 -> 0.6.5`. If the version didn't change but PyPI has a newer release, you get a warning that the `codebeacon` on your PATH may belong to a different Python environment — instead of a false "Upgrade complete".
- **Actionable failures** — a pip-less environment prints the exact commands to run; a PEP 668 `externally-managed-environment` refusal explains the fix (pipx or a virtualenv) instead of dumping a raw pip error. The command also shows the current vs. latest-on-PyPI version up front.

---

## What's new in 0.6.4

Deep-dive cleanup — outputs land where you look for them, and two silent-data-loss bugs found while verifying it on a 47-project workspace.

- **Deep-dive writes to exactly two levels** — each *repo root* (a directory with its own `.git` or `codebeacon.yaml`) and the *scan root*. A monorepo's framework folders (`mono/landing`, `mono/server`) no longer each grow a `.codebeacon/` + CLAUDE.md; their combined graph lives at `mono/.codebeacon/`, and the scan root carries the full workspace graph so any project can be found from one place. Running deep-dive *inside* a monorepo now produces a single root output instead of one per subfolder.
- **Cache keys are framework-namespaced** — a repo group shares one cache, and a parent project walking over a nested project's files first (`desktop/` as sveltekit over `desktop/src-tauri`) used to poison the cache with empty results that the nested project (tauri) then reused, silently dropping all of its routes and entities.
- **Grammar-load race fixed** — two parallel extraction workers hitting an uncached tree-sitter grammar each built their own `Language` instance; the losing thread's files then failed an identity check and extracted to **nothing** — no warning, no failure record, just a couple of files randomly missing all their routes on big scans. First load is now locked to a single shared instance (verified stable across 20 consecutive full scans).

---

## What's new in 0.6.3

Bug-fix release — a graphify-parity audit (upstream Jun 3–10) plus an independent audit of codebeacon's own code: **16 fixes**, verified end-to-end with a 47-project `--deep-dive` workspace scan (5,226 nodes / 8,715 edges).

- **Git hooks now fire everywhere** — the post-commit rebuild hook pins the installing Python interpreter into the script and detaches via `subprocess` instead of `nohup`, so it works in GUI git clients (Sublime Merge, GitKraken), CI runners, and on Windows — environments where the `codebeacon` launcher isn't on `PATH` and the old hook silently did nothing. Re-run `codebeacon hook install` to pick up the fix; the merge driver is pinned the same way.
- **Commented-out JS/TS imports no longer create edges** — the barrel re-export and `require()` regex passes now strip `//` and `/* */` comments (string-literal aware) first. A commented `export * from './legacy'` used to produce a phantom edge and false import cycles.
- **`from pkg import name` binds the real target (Python)** — the import extractor now captures the imported names, so `from auth.services import UserService` links to the `UserService` node and `from src.services import enricher` links to the submodule. Previously only the module path's last segment was tried, leaving test files disconnected. Aliases (`import x as y`) resolve to the true symbol name.
- **"High-Impact Files" is actually high-impact** — the hub ranking (CLAUDE.md, `analyze`) counted import *fan-out* via the edge's `source_file` (always the importer), so entry points outranked real shared modules with per-node-inflated counts ("imported by 392 files" in a 60-file repo). Both copies now count distinct importing files per imported file.
- **DI `injects` edges carry real file paths** — resolved dependency-injection edges stamped the graph node ID (`proj::Name`) into `source_file`; they now carry the source node's actual file.
- **Ktor nested route prefixes concatenate** — `route("/api") { route("/v1") { get("/users") } }` extracts `/api/v1/users` instead of dropping every outer prefix.
- **Same-path routes both matched** — when two services expose the same URL (gateway + upstream), `calls_api` enrichment no longer silently keeps only the last one.
- **Config tolerates sparse YAML** — `output:` / `wave:` / `semantic:` left empty no longer crash with `AttributeError`; a stray bare `-` under `projects:` raises a clean config error instead of a `TypeError`.
- **Language detection skips vendored dirs** — the fallback language vote prunes `node_modules` / `.git` / `dist`, so a Python repo with vendored JS is no longer detected as *javascript* (and discovery no longer crawls tens of thousands of vendored files).
- **Wiki links match their files** — link targets now use the exact same filename transform the generator writes with, so labels containing spaces, `#`, parentheses, or generics no longer produce dead links.
- Plus: deterministic enrichment edge order, a `None`-label build guard, a thread-safe extraction cache, FastAPI `Depends()` ghost refs removed, and Obsidian service-folder names byte-capped.

---

## What's new in 0.6.2

- **Deterministic community IDs** — equal-sized communities were numbered by partitioner enumeration order, churning 77–88 % of `beacon.json` on a no-op rescan; identical groupings now always get identical IDs.
- **Note filenames byte-capped** — an 85+-character CJK class name overflowed the 255-byte filesystem limit and crashed the whole wiki/Obsidian export with `ENAMETOOLONG`; capped at 200 UTF-8 bytes with a collision-safe hash suffix.
- **DI edges restored for FastAPI / Laravel / ASP.NET** — resolved `Depends()` / `bind()` / `AddScoped<>` references were keyed by file path while nodes are keyed by project, so the edges were silently dropped; they're remapped onto final node IDs now.
- **Interface → implementation DI revived** — `implements`/`extends` metadata was never populated by any extractor, so interface-typed injection never resolved; Spring, ASP.NET, NestJS, and Angular now wire it through.

---

## What's new in 0.6.1

Patch release — extraction correctness and reproducible output.

- **Six framework extractors restored** — the `laravel`, `angular`, `aspnet`, `actix`, `ktor`, and `vapor` tree-sitter queries had drifted out of sync with current grammar versions and silently extracted **nothing**: the query failed to compile and the error was swallowed as a warning. All six now compile and extract against the shipped grammars (Laravel `scope:`/`name:` fields, Angular `export class` decorators, ASP.NET `invocation_expression` fields, Actix sibling-anchored attributes, Kotlin 1.x node renames, Swift 0.0.1 node set), each with a regression test so they can't silently break again.
- **Reproducible `beacon.json`** — node `source_file` paths are rewritten relative to each project root before serialization, so scanning the same commit on two machines produces a byte-identical graph instead of churning absolute paths in diffs.
- **`affected` no longer over-reports** — changed-file seed matching is path-segment aligned, so `src/user.py` no longer drags in unrelated nodes such as `foosrc/user.py`.
- **`semantic-apply` crash fix** — a `confidence_score: null` in an archived/migrated JSONL edge no longer aborts the run with a `TypeError`; it coerces to the safe default like the rest of the pipeline.
- **NetworkX 3.6 forward-compat** — `beacon.json` is written with an explicit `edges="links"` key so an upstream default change can't silently alter the on-disk format; the MCP server now loads through the same compatibility shim.
- **Obsidian vault hygiene** — stale-note cleanup sweeps the whole vault (root + nested), and the cross-language import filter keys off the note's real source language instead of a filename suffix that never matched.
- **gitignore semantics** — anchored patterns like `build/*.js` no longer let `*` cross `/`, so nested files are not wrongly ignored.
- **Next.js App Router** — JS-based `page.js` / `page.jsx` routes are now discovered (previously only `.ts` / `.tsx`).
- **DI attribution fixes** — FastAPI `Depends()` and Angular constructor injection are attributed to the enclosing function/class by byte range instead of the first/last one in the file; Razor `@using` no longer emits duplicate edges.

---

## What's new in 0.6.0

- **`codebeacon affected`** — given a list of changed files (or a `--base <ref>` git diff), prints every graph node downstream of the change. Built for CI risk-scoring and PR review.
- **`.NET` project files** — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` are now parsed: `<ProjectReference>` / `<PackageReference>` become graph edges, Razor `@inherits` / `@inject` / `@using` link Blazor pages to their backing types.
- **JS/TS barrel re-exports** — `export { X } from './mod'` and `export * from './mod'` now produce explicit `re_exports` edges so Next.js / monorepo barrels stop showing zero imports.
- **`--exclude PATTERN` flag** for `scan` / `sync`, plus automatic fallback to `.gitignore` when `.codebeaconignore` is absent.
- **`codebeacon install --project [PATH]`** — install the `/codebeacon` skill into `<PATH>/.claude/` instead of `~/.claude/`, so teams can pin a SKILL.md version per repo.
- **Wiki self-heals** — `--update` runs now prune `wiki/<project>/{controllers,services,entities,components}/*.md` files whose graph node no longer exists.
- **Shrink-guard relaxed for explicit deletions** — `--update` mode no longer refuses to write a smaller `beacon.json` when the cache already accounted for deleted files; the guard still fires on silent corruption.
- **Cross-file declaration merge** — Swift `extension Foo`, C# partial classes, Ruby reopened classes union their `fields` / `methods` into one canonical node instead of the last writer winning.
- **Hardened query** — `BeaconIndex` uses `casefold()` so German `ß`, Turkish `i/İ`, Greek `σ/ς`, and CJK labels round-trip correctly.
- **Richer semantic context** — each task chunk now ships graph callers + callees as `neighbors` so the LLM stays grounded in real node labels; `SKILL.md` adds **Step 0 — Constrained query expansion** so `/codebeacon query` flows can't invent phantom tokens.
- **`semantic-apply` zero-yield guard** — if every chunk archived 0 edges, the CLI exits 1 so CI catches silent LLM failures.
- **ArkTS (`.ets`) and worktree-safety** — `.ets` is collected; nested `worktrees/` dirs are skipped to stop double-counting linked worktrees.

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
- **Knowledge mode (`codebeacon knowledge`)** — scan markdown notes (ADRs, meeting notes, retros, specs, research) and produce a single `KNOWLEDGE.md` next to `.codebeacon/`. Auto-classifies by filename and heading patterns, parses Obsidian YAML frontmatter and `[[backlinks]]`, surfaces a top-level "Key Decisions" + "Open Questions" rollup so an agent learns *why* the codebase looks the way it does. Pure heuristics — no LLM call. When a `beacon.json` already exists, the notes are also **linked into the graph**: explicit file-path references become trusted `references` edges and distinctive symbol mentions become `AMBIGUOUS` `mentions` edges. This overlay is dropped by the next `codebeacon scan` (which rebuilds the code graph from source alone), so re-run `codebeacon knowledge` after a scan to restore it.
- **Watch mode (`codebeacon watch`)** — a debounced file-watcher re-syncs the index whenever watched source files change, coalescing a burst of edits (a 500-file `git checkout`) into a single resync and reusing the scanner's exact ignore rules so it never loops on its own `.codebeacon/` output. Optional extra: `pip install 'codebeacon[watch]'`.
- **Bare-path shortcut** — `codebeacon ./src` is now equivalent to `codebeacon scan ./src`; when the first argument isn't a registered subcommand, `scan` is auto-injected, so muscle memory from `graphify <path>` / `codesight <path>` works here too.
- **Hardened semantic pipeline** — `semantic-apply` guards against malformed agent JSONL (null/list/code-fence lines, missing fields), coerces broken `confidence_score` values (None/NaN/string/out-of-range) to a safe default, snapshots `beacon.json` → `beacon.json.bak` before merging so the AST baseline is always recoverable, and regenerates `beacon.html` + `callflow.html` so visual exports reflect the newly-inferred edges.
- **Sensitive file/dir guard** — `secrets/`, `credentials/`, `.ssh/`, `.aws/`, `.gnupg/` directories are always skipped; filenames matching credential patterns (`api_token`, `oauth_token`, `private_key`, `client_secret`; underscore *and* hyphen variants) are excluded from the source-file collector before they reach extractors.

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
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`); `.sln` / `.csproj` / `.fsproj` / `.vbproj` parsed for `ProjectReference` + `PackageReference` |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) collected — extractors framework-agnostic |

> **How the "27 frameworks" count works.** Coverage is grounded in tree-sitter
> queries, and frameworks in the same grammar family share query files — Rocket
> reuses Actix-Web's attribute-macro pattern, the JS/TS web frameworks share the
> class/decorator queries, and so on. That sharing is what makes broad coverage
> tractable, but it also means depth varies per framework: some are exercised by
> extensive fixtures, others by a single query pattern. Where a framework has
> known limits, they're documented at the source — e.g. Warp's `.or(...)` and
> `warp::path::param()` caveats live in the query header
> ([`codebeacon/extract/queries/actix.scm`](codebeacon/extract/queries/actix.scm)).
> If a specific framework matters to you, scan a representative repo and check
> the routes/services it actually extracts before relying on the number.

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

This upgrades the package using whichever tool installed it (`pip`, `pipx upgrade`, or `uv tool upgrade` — detected automatically), verifies the installed version actually changed, then re-runs `codebeacon install` so `~/.claude/skills/codebeacon/SKILL.md` is overwritten with the new release's copy. Restart your Claude Code session for the new SKILL.md to load. If codebeacon is installed in editable mode (`pip install -e .`), the package step is skipped — pass `--force` to upgrade anyway.

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
| `beacon_knowledge` | Search knowledge notes (ADRs, meetings, retros, specs) or list the notes linked to a code node — the *why* behind the code |
| `beacon_pr_context` | Given changed files (or a `base` ref), return the wiki articles in their blast radius — read the docs that matter before a PR review |

### npm launcher (`@codebeacon/mcp`)

MCP clients that prefer to launch servers with `npx` can use the thin Node
wrapper instead of pointing at the `codebeacon` binary directly:

```json
{
  "mcpServers": {
    "codebeacon": {
      "command": "npx",
      "args": ["-y", "@codebeacon/mcp", "--dir", "/path/to/your/repo/.codebeacon"]
    }
  }
}
```

The wrapper bundles no Python — it resolves an installed codebeacon on the host
(PATH → `uvx` → `pipx run` → `python3 -m codebeacon`) and forwards stdio to
`codebeacon serve` untouched. See [`npm/README.md`](npm/README.md) for the full
per-client config snippets. (Shipping with 0.7.0; not yet published to npm.)

---

## GitHub Action — PR context

Comment on every pull request with the affected slice of your committed
knowledge graph — the wiki articles the change touches, the upstream blast
radius, and any high-impact hub files it edits. It reframes review around
**architecture drift**: instead of reading a diff in isolation, the comment
points at the parts of the system that actually move.

```yaml
# .github/workflows/pr-context.yml
name: codebeacon PR context
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write        # required to post/update the comment
jobs:
  pr-context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0       # required — full history so the base is diffable
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: codebeacon/codebeacon/action@v1
        with:
          base: ${{ github.base_ref }}
```

The Action does **not** scan on the runner — it reads the `.codebeacon/` index
you commit to the repo (codebeacon's model is that the graph is a
git-committable artifact). If the index is missing it posts one-time setup
guidance instead of failing the build, and it updates a single marked comment in
place rather than stacking duplicates. See [`action/README.md`](action/README.md)
and [`action/examples/pr-context.yml`](action/examples/pr-context.yml) for inputs
and edge-case behaviour.

---

## Installation Options

```bash
pip install codebeacon              # all language grammars included
pip install codebeacon[cluster]     # + Leiden community detection (graspologic)
pip install codebeacon[watch]       # + live file-watcher for `codebeacon watch` (watchdog)
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
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # repeatable gitignore-style patterns merged with
                                          # .codebeaconignore / .gitignore

# Config-driven mode
codebeacon init [path]                    # auto-generate codebeacon.yaml
codebeacon sync                           # run from codebeacon.yaml (auto-appends new workspace projects)
codebeacon sync --config <file>           # use a specific config file
codebeacon sync --no-rediscover           # don't auto-append newly added projects (hand-curated yaml mode)
codebeacon sync --exclude PATTERN         # same flag, same semantics

# Watch mode — keep the index live as you edit (needs the `watch` extra)
codebeacon watch [path]                    # re-sync on file changes (default path: cwd)
codebeacon watch . --debounce 2.0          # quiet-window before a resync fires; coalesces bursts
codebeacon watch . --once                  # process one debounce cycle then exit
codebeacon watch . --exclude 'docs/**'     # extra gitignore-style pattern (repeatable)

# PR / CI: what does this diff actually break?
codebeacon affected --base main           # walk upstream callers of every changed file
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # explicit paths, no git needed

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
codebeacon install                        # install Claude Code skill (user scope: ~/.claude/)
codebeacon install --project [PATH]       # install into <PATH>/.claude/ (team-shared, repo-pinned)
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
    rules_split: true          # multi-project workspaces: keep CLAUDE.md under
                               # ~200 lines and move per-project detail into
                               # scoped .claude/rules/codebeacon-<project>.md
                               # files. Set false for the old monolithic CLAUDE.md.
                               # No effect on single-project scans.

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

**Default fixture exclusion.** `tests/fixtures/`, `test/fixtures/`, and `__fixtures__/` are ignored by default at any depth — test-fixture trees are synthetic inputs for a project's *own* test suite, not product surface, and indexing them injects fake routes and services. This is the lowest-precedence rule, so a `.codebeaconignore` line `!tests/fixtures/` re-includes them, and pointing a scan directly *at* a fixture directory still collects it.

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

## Air-Gapped & Compliance-Friendly

codebeacon's core pipeline — tree-sitter AST parsing → knowledge graph → wiki
and context map — runs **entirely on your machine**. It requires:

- **No network.** The scan makes no outbound calls; nothing about your source
  code leaves the host.
- **No cloud service.** There is no backend, no account, no telemetry.
- **No LLM — not even a local one.** The graph, wiki, `beacon.json`, and
  `CLAUDE.md` are all produced by deterministic AST analysis. (The optional
  AI-semantic layer is a *separate*, opt-in step owned by the `/codebeacon`
  agent — it never runs unless you invoke it; see
  [Privacy & Security](#privacy--security) — and the CLI ships no API client,
  key handling, or model name.)

That architecture makes codebeacon suitable for **air-gapped and tightly
regulated environments** — healthcare, defense, legal, finance — where source
code cannot touch third-party services. To be precise about what that does and
does not mean: codebeacon makes **no compliance certification claims** (no
HIPAA, FedRAMP, CMMC, SOC 2, or similar). What it offers is an architecture that
keeps code on-premises, so it can *fit* within environments governed by those
policies. Verifying that codebeacon meets the specific controls of your
environment remains your responsibility.

**Offline install.** Because it is a normal Python package with vendored
grammars, codebeacon installs without internet access on the target host:
download the wheel and its dependencies on a connected machine, transfer them
across the air gap, and install from the local files.

```bash
# On a connected machine (include the grammar extras you need — [full] grabs all):
pip download 'codebeacon[full]' -d ./codebeacon-offline

# Transfer ./codebeacon-offline across the air gap, then on the target host:
pip install --no-index --find-links ./codebeacon-offline 'codebeacon[full]'
```

The base install bundles Python + JavaScript/TypeScript grammars; other
languages are ordinary wheels pulled in by extras (`[jvm]`, `[backend]`,
`[full]`, …), so include the extras you need in the download and nothing is
fetched at runtime.

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
