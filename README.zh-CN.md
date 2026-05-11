<!-- translation-of: README.md | based-on-commit: initial -->

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
  源代码 AST 分析与 AI 上下文生成 — 统一多框架知识图谱
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## 为什么选择 codebeacon？

每次打开新的 AI 编码会话时，助手都从零开始。它不了解你的路由结构、服务层、实体模型，也不知道微服务之间的调用关系。每次会话都要花大量时间粘贴文件、解释结构、重建上下文。

现有工具只能部分解决这个问题。路由分析器能解析控制器，但遗漏服务依赖。知识图谱工具能捕获关系，但忽略 API 接口。结果是你不得不同时运行两个工具、手动拼接输出，并在代码库变更时重复这一过程。

**codebeacon 将这两种方法统一到一个 CLI 中。** 一条命令扫描整个代码库，使用 tree-sitter 抽象语法树分析，解析跨文件的依赖注入，检测架构社区簇，并将即用型上下文映射直接写入 `CLAUDE.md`、`.cursorrules` 和 `AGENTS.md`，让 AI 助手从会话开始就已经了解你的代码库。

---

## 核心功能

- **统一流水线** — 路由/控制器分析 + 知识图谱集于一体，无需手动拼接
- **27 个框架，9 种语言** — Spring Boot、NestJS、Django、FastAPI、Flask、Rails、Express、Fastify、Koa、React、Next.js、Vue、Nuxt、Angular、SvelteKit、Gin、Echo、Fiber、Laravel、Actix-Web、Axum、Tauri、Rocket、Warp、ASP.NET Core、Vapor、Ktor
- **基于 tree-sitter** — 结构化抽象语法树解析，而非正则表达式；语言语法默认内置
- **两阶段依赖注入解析** — Pass 1 提取本地 AST 节点；Pass 2 构建全局符号表，解析单阶段工具遗漏的接口→实现映射
- **Wave 合并架构** — 文件以并行块处理后全局合并；大型单仓库也不会出现内存问题
- **多种输出格式** — JSON 知识图谱、Markdown Wiki、Obsidian Vault、AI 上下文映射、MCP 服务器、交互式 HTML
- **可视化浏览** — 每次扫描自动重新生成 `beacon.html`（D3 可折叠树）与 `callflow.html`（按社区分组的 Mermaid 架构图）
- **社区检测** — Leiden/Louvain 聚类揭示真实的架构边界
- **增量缓存** — SHA-256 + mtime/size 快速路径；同步工具（Obsidian/iCloud/Nextcloud）造成的仅 mtime 跳动不会触发重新提取
- **置信度提升** — 当显式 import 证明绑定关系时，跨文件 `calls` 边自动从 INFERRED 提升为 EXTRACTED
- **安全写入** — beacon.json 拥有 shrink guard（部分运行的失败不会覆盖完整图谱）和 `built_at_commit` 印记，REPORT.md 会标记相对于当前 HEAD 是否已 stale
- **多开发者友好** — `codebeacon hook install` 注册 `beacon.json` 的 git merge driver 和 post-commit 增量重建 hook，同一分支上两位开发者同时扫描不会产生合并冲突
- **强化的输出** — YAML frontmatter 与 MCP 标签会清除 U+2028/U+2029、C0 控制字符与双向标记；源代码中的恶意标识符无法破坏 Obsidian YAML 解析器，也无法向 LLM agent 上下文注入控制序列
- **gitignore 风格 `.codebeaconignore`** — last-match-wins、`!` 否定、目录模式（`build/`）、锚定模式（`/secrets.txt`）、行尾空白处理
- **零配置** — 自动检测框架和语言；自动生成 `codebeacon.yaml` 供后续运行
- **深度扫描模式** — `--deep-dive` 为每个子项目生成专属 `.codebeacon/` + `CLAUDE.md`；从**任意**子项目目录执行更新命令，即可自动同步整个工作区的所有项目
- **工作区自动重新发现** — 每次执行 `scan`/`sync` 时,codebeacon 会重新扫描工作区,并将 `codebeacon.yaml` 中尚未登记的新项目自动追加后再进行抽取,新增子项目不会被静默跳过;若手动维护 yaml,可通过 `--no-rediscover` 退出此行为

---

## 快速开始

```bash
pip install codebeacon

codebeacon scan .
```

就这样。codebeacon 自动检测项目类型，提取路由/服务/实体/组件，构建知识图谱，并将所有结果写入 `.codebeacon/`。

多项目工作区：

```bash
codebeacon scan /path/to/workspace   # 自动检测所有项目，生成 codebeacon.yaml
codebeacon sync                      # 后续运行通过配置文件驱动
```

---

## 支持的框架

| 语言 | 框架 |
|------|------|
| Java / Kotlin | Spring Boot、Ktor |
| Python | Django、FastAPI、Flask |
| JavaScript / TypeScript | Express、Fastify、Koa、NestJS、React、Next.js、Vue、Nuxt、Angular、SvelteKit |
| Go | Gin、Echo、Fiber |
| Ruby | Rails |
| PHP | Laravel |
| Rust | Actix-Web、Axum、Tauri、Rocket、Warp |
| C# | ASP.NET Core |
| Swift | Vapor |

---

## 架构

codebeacon 运行两阶段提取流水线：

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         本地 AST            符号表       跨语言     HTTP API
                         按块处理            映射解析     制品过滤    共享 DB
                         (Pass 1)            (Pass 2)              实体边
```

**Pass 1 — Wave 提取：** 通过 `ThreadPoolExecutor` 并行处理文件块。每个文件经过五个提取器：路由、服务、实体、组件和依赖。结果通过 SHA-256 缓存以支持增量重扫。

**Pass 2 — 图构建：** 合并所有 Wave 结果。全局符号表解析未解决的依赖注入引用——处理 Spring 隐式 Bean 连接或 TypeScript 注入 token 等单阶段工具遗漏的接口→实现映射。

**后处理：** HTTP API 边连接前端 URL 调用与后端路由。社区检测（Leiden → Louvain → 连通组件回退）将图划分为架构集群。

---

## 输出结构

扫描后，上下文映射文件在项目根目录就地更新（保留现有用户内容），知识图谱写入 `.codebeacon/`：

```
project-root/
  CLAUDE.md              ← AI 上下文映射（合并 codebeacon 块；保留用户内容）
  .cursorrules           ← Cursor IDE 上下文（相同合并策略）
  AGENTS.md              ← OpenAI Agents / Codex 上下文（相同合并策略）
  .codebeacon/
    beacon.json          ← 完整知识图谱；嵌入 `meta.built_at_commit`
    beacon.html          ← D3 可折叠树查看器（用浏览器打开）
    callflow.html        ← 按社区分组的 Mermaid 调用流程图
    REPORT.md            ← 上帝节点、意外连接、枢纽文件、新鲜度
    wiki/
      index.md           ← 全局索引（约 200 tokens）
      overview.md        ← 平台统计 + 跨项目连接
      routes.md          ← 所有路由表
      cross-project/
        connections.md   ← 跨服务边
      <project>/
        index.md
        routes.md
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian Vault（每个图节点一篇笔记）
```

### 深度扫描模式

使用 `--deep-dive` 时，每个子项目都会获得独立的 `.codebeacon/` + `CLAUDE.md`。Claude Code 按层级加载 `CLAUDE.md`——在 `api-server/` 中打开会话时，同时加载工作区全局概览和项目专属详情。

核心亮点：从**任意子项目**运行更新命令，自动找到父级配置文件并同步整个工作区：

```bash
# 首次深度扫描
codebeacon scan /workspace --deep-dive

# 之后，从任意子项目 — 自动找到父级配置，更新所有项目
cd /workspace/api-server
codebeacon scan . --update
```

输出结构：
```
workspace/
  CLAUDE.md                   ← 合并（所有项目）
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← 合并知识图谱
  api-server/
    CLAUDE.md                 ← 仅 api-server
    .codebeacon/
  frontend/
    CLAUDE.md                 ← 仅 frontend
    .codebeacon/
```

---

## AI 集成

### Claude Code 技能 (`/codebeacon`)

将 codebeacon 安装为 Claude Code 斜杠命令：

```bash
pip install codebeacon
codebeacon install
```

此命令将 `SKILL.md` 复制到 `~/.claude/skills/codebeacon/`，并在 `~/.claude/CLAUDE.md` 中注册 `/codebeacon` 触发器。重启 Claude Code 会话后，输入 `/codebeacon` 即可扫描当前目录。

```
/codebeacon                  # 扫描当前目录
/codebeacon /path/to/project # 扫描指定路径
/codebeacon sync             # 从 codebeacon.yaml 重新扫描
```

### MCP 服务器

将 codebeacon 作为 MCP 服务器运行，可让任何兼容 MCP 的客户端直接查询知识图谱。

**第一步 — 扫描项目：**
```bash
codebeacon scan .
```

**第二步 — 添加到 MCP 客户端配置：**

**Claude Code**（项目根目录的 `.claude.json` 或全局 `~/.claude.json`）：
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

**Cursor**（`~/.cursor/mcp.json`）：
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

**连接后可用的 MCP 工具：**

| 工具 | 说明 |
|------|------|
| `beacon_wiki_index` | 全局项目概览（路由、服务、实体数量） |
| `beacon_wiki_article` | 按路径读取指定 Wiki 文章 |
| `beacon_query` | 按标签子字符串搜索节点 |
| `beacon_path` | 两节点间的最短依赖路径 |
| `beacon_blast_radius` | 上游调用方及下游受影响节点 |
| `beacon_routes` | 全部 HTTP 路由列表（可按项目筛选） |
| `beacon_services` | 全部服务/类列表（可按项目筛选） |

---

## 安装选项

```bash
pip install codebeacon              # 默认内置所有语言语法
pip install codebeacon[cluster]     # + Leiden 社区检测（graspologic）
pip install --upgrade codebeacon    # 升级到最新版本并同步更新依赖
```

Java、Kotlin、Python、JavaScript、TypeScript、Go、Ruby、PHP、C#、Rust、Swift、HTML、Svelte 解析器均默认安装，无需额外标志。

---

## CLI 参考

```bash
# 扫描项目或工作区
codebeacon scan <path> [选项]
codebeacon scan .                         # 当前目录
codebeacon scan /workspace                # 工作区根目录（多项目）
codebeacon scan . --update                # 增量：仅重新提取变更文件
codebeacon scan . --wiki-only             # 跳过重新提取，从现有 beacon.json 重新生成 Wiki/obsidian/上下文映射
codebeacon scan . --obsidian-dir <path>   # 将 Obsidian Vault 写入自定义位置
codebeacon scan . --semantic              # 启用结构化注释引用提取 (Javadoc/JSDoc/docstring)
codebeacon scan . --list-only             # 仅检测框架，不提取
codebeacon scan /workspace --deep-dive    # 各项目独立输出 + 工作区合并输出

# 配置驱动模式
codebeacon init [path]                    # 自动生成 codebeacon.yaml
codebeacon sync                           # 基于 codebeacon.yaml 运行(自动追加工作区中的新项目)
codebeacon sync --config <file>           # 使用指定配置文件
codebeacon sync --no-rediscover           # 不自动追加新项目(手动维护 yaml 模式)

# 查询知识图谱
codebeacon query <term> [--dir .codebeacon] [--limit N]   # 通过标签子串搜索节点
codebeacon path <source> <target> [--dir .codebeacon]     # 最短依赖路径

# 多开发者支持（git plumbing）
codebeacon hook install [path]            # 安装 merge driver + post-commit 增量重建 hook
codebeacon merge-driver <base> <cur> <other>  # `hook install` 后由 git 自动调用；对 beacon.json 做 union 合并

# AI 语义增强 (LLM 由代理执行，codebeacon 仅做记账)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N]
                                          # 把之前的归档重新应用到 fresh beacon.json，
                                          # 然后只为档案里没有的 NEW 候选 (god-node 文件夹
                                          # + unresolved 目标) 生成 .codebeacon/
                                          # semantic-tasks.jsonl
codebeacon semantic-apply   [--dir .codebeacon]
                                          # 读取 .codebeacon/semantic-results.jsonl，
                                          # 作为 INFERRED references 边并入 beacon.json，
                                          # 追加到 .codebeacon/semantic/original.jsonl 档案，
                                          # 清理 pending 文件，重新生成
                                          # wiki/obsidian/上下文映射

# 集成
codebeacon serve [--dir .codebeacon]      # 启动 MCP 服务器（stdio）
codebeacon install                        # 安装 Claude Code 技能
```

---

## AI 语义增强（通过 `/codebeacon` 技能）

tree-sitter 解析找到 AST 里**有**的东西。**AI 语义**找到**只在注释里**的东西 — Javadoc 中的 `@see UserService`、Python docstring 中的 `:class:`OrderRepository``、写在路由处理器旁边的契约引用。codebeacon 为此提供两层：

| 层 | 标志 | 成本 | 捕获内容 |
|---|---|---|---|
| 结构化注释解析 | `--semantic` | 免费、本地、无需 LLM | Javadoc `@see` / `{@link}`、JSDoc `@see` / `@param` 类型、Python `:class:` / `:func:` / `See Also` |
| **AI 语义** | `/codebeacon` 技能中自动 | 使用代理的**当前模型** — **无需额外 API 密钥** | 正则无法捕获的类/类型/服务引用（自由散文、间接提及、纯类型提示等） |

CLI 自身**绝不**调用任何 LLM API。AI 语义层有意由 `/codebeacon` Claude Code 技能内**运行中的代理拥有** — 这样用户选择的模型（Opus / Sonnet / Haiku 等）会被直接使用，codebeacon 自身既不需要 `ANTHROPIC_API_KEY` 也不需要任何云端配置。

### 执行流程

在 Claude Code 中调用 `/codebeacon` 时：

1. `scan` / `sync` 从 AST 构建 `beacon.json`（不调用 LLM）。
2. `codebeacon semantic-prepare` 把已有归档重新应用到新图上，然后写出**只包含新候选**的 `.codebeacon/semantic-tasks.jsonl` — 评分高（unresolved 目标边 + god-node 文件夹）且从未被处理过的文件。
3. 技能遍历 tasks 文件。对每一行，代理（使用当前会话的模型）读取 `excerpt` 字段并内联返回推断的 references。结果写入 `.codebeacon/semantic-results.jsonl`。
4. `codebeacon semantic-apply` 将结果作为 `INFERRED references` 边并入 `beacon.json`，**追加到 `.codebeacon/semantic/original.jsonl`**（持久归档），清理待处理文件，并重新生成 wiki + obsidian + 上下文映射。
5. 下次扫描：`semantic-prepare` 把归档重新应用到新构建的图上（以免重扫丢失历史推断），并只把**自上次归档以来新发现的候选**写入 tasks 文件。已处理的文件通过 `task_id`（`file_path|node_id` 的 SHA1）跳过。

→ 增量、幂等增强。代理不会重复分析同一文件，累积的 AI 信号在每次重扫后依然保留。

### 直接 CLI 使用

不走技能（如 CI 场景）也可以用同样的两条命令手动运行，自己生成 `semantic-results.jsonl`：

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50

# 自己写 .codebeacon/semantic-results.jsonl；每行：
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### 关闭

调用技能时传 `--no-semantic`（或 `--wiki-only`、`--list-only`）会完全跳过 AI 步骤。如果给 `scan` / `sync` 传 `--semantic`，结构化注释层仍然会运行。

---

## 可视化浏览

每次扫描都会在 `beacon.json` 旁边写出两个自包含的 HTML 文件：

```
.codebeacon/beacon.html      # D3 v7 可折叠树 — 任意浏览器打开即可
.codebeacon/callflow.html    # 按社区一张 Mermaid 架构图
```

无需构建步骤、无需静态服务器、无需复制粘贴。打开文件，点击展开项目 → 类型 → 节点；悬停查看源路径和度数。`callflow.html` 按社区对图谱分组，每组用 Mermaid 流程图渲染，跨社区的出边在可折叠的表格中列出。

---

## 多开发者工作流

两位开发者在同一分支上运行 `codebeacon scan` 会产生略有不同的 `beacon.json` — 历史上是合并冲突的高发地带。`codebeacon hook install` 解决这个问题：

```bash
codebeacon hook install            # 在仓库根目录
```

它会注册：

- **git merge driver**，将两个 `beacon.json` union 合并为一个（节点按 ID 去重，边按 `(source, target, relation)` 去重）
- 将 `*beacon.json` 指向该 driver 的 `.gitattributes` 条目
- **post-commit hook**，在后台执行 `codebeacon scan . --update`，让图谱不落后于提交。输出写入 `~/.cache/codebeacon-rebuild.log`

merge driver 始终以 0 退出 — 图谱重建绝不会阻塞实际的合并。

---

## 安全保证

每次成功扫描都由 writer 强制执行以下不变量：

| 守卫 | 阻止的情况 |
|---|---|
| **Shrink guard** | 部分提取失败或中断的运行不能覆盖更大、更完整的 `beacon.json`。可通过 API 中 `force=True` 绕过 |
| **原子写入** | `beacon.json` 通过 `os.replace` 写入，文件要么完整要么未触碰 — 不存在写一半的图谱 |
| **`built_at_commit` 印记** | `beacon.json` 嵌入 `meta.built_at_commit`（完整 SHA），`REPORT.md` 显示 short SHA。HEAD 超前时，报告会用一行修复提示标记 `⚠ stale` |
| **Frontmatter / 标签强化** | YAML frontmatter 值采用单引号并转义 U+2028、U+2029、Tab、C0 控制字符；MCP 工具输出会让所有标签经过同一 sanitizer。源代码中的恶意标识符无法破坏 Obsidian 的 YAML 解析器，也无法向 LLM agent 上下文注入控制序列 |

---

## 配置

运行 `codebeacon init` 生成 `codebeacon.yaml`，或手动编写：

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # 可选：省略时自动检测

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
  chunk_size: 300              # 每块文件数
  max_parallel: 5              # 并行线程数

semantic:
  enabled: false               # 仅结构化注释提取; --semantic 标志覆盖。
                               # AI 语义不在这里 — 它由 /codebeacon 技能
                               # (= 正在运行的代理) 触发。

deep_dive: false               # 设为 true 可生成各项目独立输出
```

### .codebeaconignore

在项目根目录放置 `.codebeaconignore` 文件可将特定目录或文件排除在扫描之外。语义与 `.gitignore` 一致 — last-match-wins、`!` 否定、锚定模式（`/foo`）、目录专用模式（`build/`）、注释：

```
# .codebeaconignore

# 目录
build/
generated/
fixtures/

# 仅锚定到根
/scripts/local-only.ts

# 通配符模式
*.gen.ts
**/snapshots/**

# 即使 build/ 被忽略也重新包含特定文件
!build/manifest.ts
```

`!pattern` 重新包含先前被忽略的路径；后面的规则覆盖前面的规则。Walker 会修剪名称匹配规则集的目录，但当存在 `!` 否定规则时会推迟修剪，转而对每个文件单独检查。

---

## 对比

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| 路由 / 控制器分析 | ✅ | ❌ | ✅ |
| 服务 / DI 图 | 部分 | ✅ | ✅ |
| 接口 → 实现解析 | ❌ | ❌ | ✅ |
| 实体 / ORM 模型提取 | ✅ | ❌ | ✅ |
| 前端组件分析 | ✅ | ❌ | ✅ |
| 社区检测 | ❌ | ✅ | ✅ |
| Obsidian Vault 导出 | ❌ | ✅ | ✅ |
| MCP 服务器 | ✅ | ❌ | ✅ |
| AI 上下文映射 (CLAUDE.md) | ✅ | ✅ | ✅ |
| 多项目工作区 | 部分 | ❌ | ✅ |
| 基于 Python | ❌ | ✅ | ✅ |

codebeacon 不是两个工具的替代品，而是两者的统合——在共享的提取和图层之上，实现两个工具各自功能的并集。

---

## 基准测试

| 代码库 | 技术栈 | 文件数 | 节点 | 边 | 社区 | 扫描时间 |
|-------|-------|-------|-----|---|-----|---------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3个项目) | 444 | 382 | 553 | 175 | ~12s |

---

## 隐私与安全

所有 AST 处理均在本地完成。直接运行 codebeacon 时，源代码不会离开你的设备。

- tree-sitter AST 解析完全在进程内运行
- 正常操作期间无遥测、无分析、无网络调用
- CLI 本身 **绝不主动调用任何 LLM 提供方** — codebeacon 包内没有 API 客户端、没有密钥处理、没有模型名
- `--semantic` 只激活 **结构化注释解析**（Javadoc `@see` / `{@link}`、JSDoc `@see` / `@param` 类型、Python `:class:` / `:func:` / `See Also`）。完全本地。
- **AI 语义**（更深的 LLM 推断层）由 `/codebeacon` Claude Code 技能触发。代理读取 `semantic-tasks.jsonl`，使用 **当前会话所选的模型** 进行分析，然后写出 `semantic-results.jsonl`。Python CLI 仅负责准备任务批次和合并结果，甚至不知道用了哪个模型。调用技能时传 `--no-semantic` 即可完全跳过 LLM 步骤。

---

## 贡献

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

添加新框架支持的最简单入口是在 `codebeacon/extract/queries/` 中编写 tree-sitter 查询文件。完整指南请参阅 [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md)。

欢迎贡献：新框架查询、语言解析器、输出格式和基准数据集。

---

## 许可证

MIT — 参见 [LICENSE](LICENSE) 文件。

---

## 致谢

基于 [tree-sitter](https://tree-sitter.github.io/tree-sitter/)（结构化 AST 解析）、[NetworkX](https://networkx.org/)（图操作）和 [graspologic](https://microsoft.github.io/graspologic/)（Leiden 社区检测）构建。

灵感来自 [codesight](https://github.com/Houseofmvps/codesight) 和 [graphify](https://github.com/safishamsi/graphify) 的互补方法。
