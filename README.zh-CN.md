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

## 0.6.4 新功能

Deep-dive 清理 — 输出落在你查找它们的位置，外加在 47 个项目的工作区上验证时发现的两个静默数据丢失缺陷。

- **Deep-dive 恰好只写入两个层级** — 各*仓库根*（拥有自己的 `.git` 或 `codebeacon.yaml` 的目录）与*扫描根*。monorepo 的框架文件夹（`mono/landing`、`mono/server`）不再各自堆积 `.codebeacon/` + CLAUDE.md；它们的合并图位于 `mono/.codebeacon/`，扫描根则承载完整的工作区图，任何项目都能从一处找到。在 monorepo *内部*运行 deep-dive 现在产生单一的根输出，而不是每个子文件夹一份。
- **缓存键以框架作命名空间** — 一个仓库组共享同一份缓存，而父项目先遍历嵌套项目的文件时（作为 sveltekit 的 `desktop/` 走过 `desktop/src-tauri`），曾用空结果毒化缓存，嵌套项目（tauri）随后复用这些空结果，静默丢失其全部路由和实体。
- **修复语法加载竞态** — 两个并行提取 worker 同时命中未缓存的 tree-sitter 语法时，各自构建了自己的 `Language` 实例；落败线程的文件随后通不过同一性检查，提取结果为**空**——没有警告，没有失败记录，只是大规模扫描中少数文件随机丢失全部路由。首次加载现在锁定为单一共享实例（已验证连续 20 次完整扫描保持稳定）。

---

## 0.6.3 新功能

缺陷修复版本 — 一次 graphify-parity 审计（上游 6 月 3–10 日）加上对 codebeacon 自身代码的独立审计：**16 项修复**，并以 47 个项目的 `--deep-dive` 工作区扫描（5,226 节点 / 8,715 边）做了端到端验证。

- **Git 钩子在任何环境都能触发** — post-commit 重建钩子将安装时的 Python 解释器固定进脚本，并用 `subprocess` 而非 `nohup` 脱离父进程，因此在 GUI git 客户端（Sublime Merge、GitKraken）、CI runner 和 Windows 上均可工作——这些环境里 `codebeacon` 启动器不在 `PATH` 中，旧钩子会悄悄什么都不做。重新运行 `codebeacon hook install` 即可获得修复；merge driver 也以同样方式固定。
- **注释掉的 JS/TS 导入不再产生边** — barrel re-export 与 `require()` 的正则扫描现在会先（在识别字符串字面量的前提下）剥离 `//` 与 `/* */` 注释。被注释的 `export * from './legacy'` 此前会产生幻影边和虚假的 import 循环。
- **`from pkg import name` 绑定到真实目标（Python）** — 导入提取器现在捕获被导入的名称，因此 `from auth.services import UserService` 链接到 `UserService` 节点，`from src.services import enricher` 链接到子模块。此前只尝试模块路径的最后一段，导致测试文件与图断连。别名（`import x as y`）解析为真实符号名。
- **"High-Impact Files" 真正高影响** — hub 排名（CLAUDE.md、`analyze`）此前经由边的 `source_file`（始终是导入方）统计 import 的*扇出*，使入口文件以按节点膨胀的计数（60 个文件的仓库里出现 "imported by 392 files"）压过真正的共享模块。两处副本现在都按被导入文件统计去重后的导入方文件数。
- **DI `injects` 边携带真实文件路径** — 已解析的依赖注入边曾把图节点 ID（`proj::Name`）写进 `source_file`；现在携带源节点的实际文件。
- **Ktor 嵌套 route 前缀正确拼接** — `route("/api") { route("/v1") { get("/users") } }` 提取出 `/api/v1/users`，而不是丢掉所有外层前缀。
- **同路径路由都能匹配** — 当两个服务暴露相同 URL（gateway + upstream）时，`calls_api` 富化不再悄悄只保留最后一个。
- **配置容忍稀疏 YAML** — `output:` / `wave:` / `semantic:` 留空不再以 `AttributeError` 崩溃；`projects:` 下游离的裸 `-` 抛出清晰的配置错误而非 `TypeError`。
- **语言检测跳过 vendored 目录** — 回退语言投票会剪除 `node_modules` / `.git` / `dist`，因此含 vendored JS 的 Python 仓库不再被判定为 *javascript*（discovery 也不再爬取数万个 vendored 文件）。
- **wiki 链接与文件一致** — 链接目标现在使用与生成器写文件时完全相同的文件名变换，含空格、`#`、括号或泛型的标签不再产生死链。
- 另有：确定性的富化边顺序、`None` 标签构建守护、线程安全的提取缓存、移除 FastAPI `Depends()` 幻影引用，以及 Obsidian 服务文件夹名的字节上限。

---

## 0.6.2 新功能

- **确定性的 community ID** — 等大小的 community 曾按分区器枚举顺序编号，一次 no-op 重扫会翻搅 `beacon.json` 的 77–88 %；相同的分组现在总是得到相同的 ID。
- **笔记文件名字节上限** — 一个 85+ 字符的 CJK 类名超出文件系统 255 字节限制，以 `ENAMETOOLONG` 让整个 wiki/Obsidian 导出崩溃；现已限制为 200 个 UTF-8 字节并附加防碰撞哈希后缀。
- **恢复 FastAPI / Laravel / ASP.NET 的 DI 边** — 已解析的 `Depends()` / `bind()` / `AddScoped<>` 引用按文件路径作键，而节点按项目作键，导致这些边被静默丢弃；现在重映射到最终节点 ID。
- **复活接口 → 实现的 DI** — `implements`/`extends` 元数据从未被任何提取器填充，接口类型注入从未解析；Spring、ASP.NET、NestJS、Angular 现已接通。

---

## 0.6.1 新功能

补丁版本 — 提取正确性与可复现输出。

- **修复六个框架提取器** — `laravel`、`angular`、`aspnet`、`actix`、`ktor`、`vapor` 的 tree-sitter 查询与当前文法版本脱节，**提取不到任何内容**：查询无法编译，错误被当作警告吞掉。现已让六者都能针对随附文法编译并提取（Laravel 的 `scope:`/`name:` 字段、Angular 的 `export class` 装饰器、ASP.NET 的 `invocation_expression` 字段、Actix 的兄弟节点锚定、Kotlin 1.x 节点改名、Swift 0.0.1 节点集），并为每个添加回归测试，防止再次悄然失效。
- **可复现的 `beacon.json`** — 序列化前将节点的 `source_file` 路径改写为相对各项目根目录，因此在两台机器上扫描同一提交会生成逐字节相同的图，而不再在 diff 中翻搅绝对路径。
- **`affected` 不再过度报告** — 变更文件的种子匹配按路径段对齐，因此 `src/user.py` 不再拉入 `foosrc/user.py` 之类无关节点。
- **`semantic-apply` 崩溃修复** — 归档/迁移的 JSONL 边中的 `confidence_score: null` 不再以 `TypeError` 中断运行，而是像管线其余部分一样归一到安全默认值。
- **NetworkX 3.6 前向兼容** — `beacon.json` 以显式 `edges="links"` 键写出，使上游默认值变化不会悄悄改变磁盘格式；MCP 服务器也经由同一兼容层加载。
- **Obsidian 库整理** — 过期笔记清理覆盖整个库（根目录 + 嵌套），跨语言导入过滤器以笔记的真实源语言为准，而非从不匹配的文件名后缀。
- **gitignore 语义** — `build/*.js` 等锚定模式中的 `*` 不再跨越 `/`，因此嵌套文件不会被误忽略。
- **Next.js App Router** — 现在会发现基于 JS 的 `page.js` / `page.jsx` 路由（此前仅 `.ts` / `.tsx`）。
- **DI 归属修复** — FastAPI 的 `Depends()` 与 Angular 构造函数注入按字节范围归属到其外围函数/类，而非文件中的首个/末个；Razor 的 `@using` 不再产生重复边。

---

## 0.6.0 新功能

- **`codebeacon affected`** — 接收变更文件列表（或通过 `--base <ref>` 读取 git diff），输出受影响的所有图节点。面向 CI 风险评分与 PR 审查。
- **`.NET` 项目文件** — 现已解析 `.sln`、`.csproj`、`.fsproj`、`.vbproj`、`.razor`、`.cshtml`。`<ProjectReference>` / `<PackageReference>` 成为图的边；Razor 的 `@inherits` / `@inject` / `@using` 将 Blazor 页面与其后端类型链接。
- **JS/TS barrel re-export** — `export { X } from './mod'` 与 `export * from './mod'` 会生成显式的 `re_exports` 边，Next.js / monorepo 的 barrel 不再被显示为 0 个 import。
- **`--exclude PATTERN` 选项**（`scan` / `sync` 通用）+ 当 `.codebeaconignore` 不存在时自动回退读取 `.gitignore`。
- **`codebeacon install --project [PATH]`** — 将 `/codebeacon` skill 安装到 `<PATH>/.claude/` 而不是 `~/.claude/`，便于团队按仓库锁定 SKILL.md 版本。
- **wiki 自我修复** — `--update` 运行会自动删除 `wiki/<project>/{controllers,services,entities,components}/` 下对应图节点已经不存在的 `.md` 文件。
- **明确删除时绕过 shrink-guard** — `--update` 模式下，若缓存已记录文件删除，更小的 `beacon.json` 写入不再被拒绝；针对 silent corruption 的守护仍然生效。
- **跨文件声明 union 合并** — Swift `extension Foo`、C# partial class、Ruby reopened class 的 `fields` / `methods` 不再被最后一个写入覆盖，而是合并为唯一的规范节点。
- **query 强化** — `BeaconIndex` 改用 `casefold()`，德语 `ß`、土耳其语 `i/İ`、希腊语 `σ/ς` 和 CJK 标签匹配均正确。
- **更丰富的语义上下文** — 每个 task chunk 现在附带图的 caller / callee 作为 `neighbors`，让 LLM 紧贴真实节点标签。`SKILL.md` 新增 **Step 0 — Constrained query expansion**，明确禁止 `/codebeacon query` 流程发明 phantom token。
- **`semantic-apply` zero-yield 守护** — 若所有 chunk 都以 0 边归档，CLI 以 exit 1 退出，便于 CI 捕获 LLM 的静默失败。
- **ArkTS (`.ets`) 与 worktree 安全性** — 收集 `.ets`，跳过嵌套的 `worktrees/` 目录，避免 linked worktree 被重复索引。

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
- **Graphify 风格的语义增强** — AST 抽取后,技能会按 chunk 并行派发一个 subagent,各自生成 `{nodes, edges, hyperedges}` 的完整知识图谱片段。支持 8 种关系(`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`)与三级置信度(EXTRACTED/INFERRED/AMBIGUOUS)。在 Claude Code 中,subagent 会自动降级到比宿主模型低一级(Opus→Sonnet、Sonnet→Haiku),让花费与语料规模成比例。代码节点由 AST 独占,LLM 仅可贡献 `concept`/`document`/`paper` 节点。已有的 0.3.x 归档可透明地在新 schema 下重放
- **知识模式 (`codebeacon knowledge`)** — 扫描 Markdown 笔记(ADR、会议记录、复盘、规格、调研)在 `.codebeacon/` 旁生成单一 `KNOWLEDGE.md`。按文件名 / 标题模式自动分类,解析 Obsidian YAML frontmatter 与 `[[backlinks]]`,顶部提供 "Key Decisions" + "Open Questions" 汇总,让 agent 了解代码库*为什么*长成这样。纯启发式,不调用 LLM
- **路径简写** — `codebeacon ./src` 现等价于 `codebeacon scan ./src`;首参数不是已注册子命令时会自动注入 `scan`,沿用 `graphify <path>` / `codesight <path>` 的手感
- **加固的 semantic 流水线** — `semantic-apply` 会拦截 agent JSONL 中的异常行(null / 数组 / code-fence / 缺少必要字段),将损坏的 `confidence_score`(None / NaN / 字符串 / 越界)coerce 为安全默认值,在合并前对 `beacon.json` → `beacon.json.bak` 做快照确保 AST 基线始终可恢复,并重新生成 `beacon.html` / `callflow.html`,让新推断的边在可视化中体现
- **敏感文件 / 目录护栏** — `secrets/`、`credentials/`、`.ssh/`、`.aws/`、`.gnupg/` 始终跳过;符合凭证模式(`api_token`、`oauth_token`、`private_key`、`client_secret`;下划线*与*连字符变体)的文件名在到达抽取器之前就在收集阶段排除

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
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`)；`.sln` / `.csproj` / `.fsproj` / `.vbproj` 解析 `ProjectReference` + `PackageReference` |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) 收集 — extractor 与 framework 无关 |

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
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # 可重复的 gitignore 风格模式
                                          # 与 .codebeaconignore / .gitignore 合并

# 配置驱动模式
codebeacon init [path]                    # 自动生成 codebeacon.yaml
codebeacon sync                           # 基于 codebeacon.yaml 运行(自动追加工作区中的新项目)
codebeacon sync --config <file>           # 使用指定配置文件
codebeacon sync --no-rediscover           # 不自动追加新项目(手动维护 yaml 模式)
codebeacon sync --exclude PATTERN         # 同一选项,同一语义

# PR / CI: 这个 diff 实际会影响什么?
codebeacon affected --base main           # 沿上游 walk 变更文件的调用者
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # 显式路径 — 不依赖 git

# 查询知识图谱
codebeacon query <term> [--dir .codebeacon] [--limit N]   # 通过标签子串搜索节点
codebeacon path <source> <target> [--dir .codebeacon]     # 最短依赖路径

# 多开发者支持（git plumbing）
codebeacon hook install [path]            # 安装 merge driver + post-commit 增量重建 hook
codebeacon merge-driver <base> <cur> <other>  # `hook install` 后由 git 自动调用；对 beacon.json 做 union 合并

# AI 语义增强 (LLM 由代理执行，codebeacon 仅做记账)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # 把 .codebeacon/semantic/original/*.jsonl 归档重新应用到
                                          # 新 beacon.json + 清理指向已消失节点的 stale 条目，
                                          # 然后将新候选写入 .codebeacon/semantic/pending/
                                          # chunk_NNN.jsonl (每个 chunk 含 --chunk-size 个，默认 10)。
                                          # task_id 含内容哈希 - 文件内容变化会自动重新发布。
codebeacon semantic-apply   [--dir .codebeacon]
                                          # 把代理写好的 .codebeacon/semantic/results/chunk_NNN.jsonl
                                          # 每个文件作为 INFERRED references 边合并入 beacon.json，
                                          # 并把 pending/chunk_NNN.jsonl 移动到 original/chunk_NNN.jsonl
                                          # (持久归档)。删除 results，重新生成 wiki/obsidian/上下文映射。

# 集成
codebeacon serve [--dir .codebeacon]      # 启动 MCP 服务器（stdio）
codebeacon install                        # 安装 Claude Code 技能 (user 作用域: ~/.claude/)
codebeacon install --project [PATH]       # 安装到 <PATH>/.claude/ (团队共享、仓库锁定)
codebeacon upgrade                        # pip 升级 + 刷新 ~/.claude/skills/codebeacon/SKILL.md
                                          # （editable 安装下用 `--force` 强制升级）
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
2. `codebeacon semantic-prepare` 把 `.codebeacon/semantic/original/*.jsonl` 归档重新应用到新图，并**清理**指向已消失节点的 stale 条目，然后把新 task 写入 `.codebeacon/semantic/pending/chunk_NNN.jsonl`（每个 chunk ≤ `--chunk-size` 个，默认 10）。chunk 编号从持久归档的下一个开始，绝不冲突。
3. 技能**一次处理一个 pending chunk**。对每个 `pending/chunk_NNN.jsonl`，代理（使用当前会话的模型）读取每个 task 的 `excerpt`，并写入同名的 `semantic/results/chunk_NNN.jsonl`。
4. `codebeacon semantic-apply` 把结果作为 `INFERRED references` 边并入 `beacon.json`，并把每个已完成的 `pending/chunk_NNN.jsonl` **移动**到 **`semantic/original/chunk_NNN.jsonl`**（一并写入应用过的边以便审计）。results 文件被删除，重新生成 wiki + obsidian + 上下文映射。
5. 下次扫描：`semantic-prepare` 把 `original/` 下所有 chunk 的边重新应用到新构建的图（保留历史推断），并跳过已存在的 `task_id`。`task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])` — 文件语义内容变化会自动得到新 id 并被重新分析。

→ 增量、幂等增强。代理不会对同一 (文件, 内容) 重复分析，累积的 AI 信号每次重扫都保留，chunk 切分还让代理的工作集保持小巧。

### 直接 CLI 使用

不走技能（如 CI 场景）也可以用同样的两条命令手动运行，自己生成 `results/chunk_NNN.jsonl`：

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# 此时已生成 .codebeacon/semantic/pending/chunk_001.jsonl ...
# 对每个 pending chunk，写一份同名的 results/chunk_NNN.jsonl。每行：
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
