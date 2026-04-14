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
- **24 个框架，9 种语言** — Spring Boot、NestJS、Django、FastAPI、Flask、Rails、Express、Fastify、Koa、React、Next.js、Vue、Nuxt、Angular、SvelteKit、Gin、Echo、Fiber、Laravel、Actix-Web、Axum、ASP.NET Core、Vapor、Ktor
- **基于 tree-sitter** — 结构化抽象语法树解析，而非正则表达式；语言语法默认内置
- **两阶段依赖注入解析** — Pass 1 提取本地 AST 节点；Pass 2 构建全局符号表，解析单阶段工具遗漏的接口→实现映射
- **Wave 合并架构** — 文件以并行块处理后全局合并；大型单仓库也不会出现内存问题
- **多种输出格式** — JSON 知识图谱、Markdown Wiki、Obsidian Vault、AI 上下文映射、MCP 服务器
- **社区检测** — Leiden/Louvain 聚类揭示真实的架构边界
- **增量缓存** — 基于 SHA-256；仅重新提取自上次扫描以来发生变更的文件
- **零配置** — 自动检测框架和语言；自动生成 `codebeacon.yaml` 供后续运行

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
| Rust | Actix-Web、Axum |
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
    beacon.json          ← 完整知识图谱（节点-链接 JSON，可查询）
    REPORT.md            ← 上帝节点、意外连接、枢纽文件
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
codebeacon scan . --semantic              # 启用 LLM 语义提取
codebeacon scan . --list-only             # 仅检测框架，不提取

# 配置驱动模式
codebeacon init [path]                    # 自动生成 codebeacon.yaml
codebeacon sync                           # 基于 codebeacon.yaml 运行
codebeacon sync --config <file>           # 使用指定配置文件

# 查询知识图谱（即将推出）
codebeacon query <term>                   # 搜索节点和边
codebeacon path <source> <target>         # 两节点间最短路径

# 集成
codebeacon serve [--dir .codebeacon]      # 启动 MCP 服务器（stdio）
codebeacon install                        # 安装 Claude Code 技能
```

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
  enabled: false               # 通过 --semantic 标志覆盖
```

### .codebeaconignore

在项目根目录放置 `.codebeaconignore` 文件可将特定目录或文件排除在扫描之外。语法与 `.gitignore` 相同 — 每行一个模式，`#` 为注释。

```
# .codebeaconignore
generated/
build/
*.generated.ts
fixtures/
```

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

所有处理均在本地完成。源代码不会离开你的设备。

- tree-sitter AST 解析完全在进程内运行
- 正常操作期间无遥测、无分析、无网络调用
- `--semantic` 标志（默认禁用）激活两种提取模式：
  1. **结构化注释解析**（无需 LLM） — 从 Javadoc（`@see`、`{@link}`）、Python 文档字符串（`:class:`、`:func:`）和 JSDoc（`@see`、`@param` 类型）中推断交叉引用
  2. **LLM 推断**（可选） — 设置 `ANTHROPIC_API_KEY` 后，向 Claude API 发送代码片段进行深度关系推断；仅在明确启用时使用

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
