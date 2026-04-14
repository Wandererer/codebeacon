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
  ソースコード AST 解析と AI コンテキスト生成 — 統合マルチフレームワーク・ナレッジグラフ
</p>

<p align="center">
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/v/codebeacon" alt="PyPI"></a>
  <a href="https://pypi.org/project/codebeacon/"><img src="https://img.shields.io/pypi/pyversions/codebeacon" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://github.com/Wandererer/codebeacon/stargazers"><img src="https://img.shields.io/github/stars/Wandererer/codebeacon" alt="GitHub Stars"></a>
  <a href="https://github.com/Wandererer/codebeacon/commits/main"><img src="https://img.shields.io/github/last-commit/Wandererer/codebeacon" alt="Last Commit"></a>
</p>

---

## なぜ codebeacon なのか

AI コーディングセッションを新しく開くたびに、アシスタントは白紙の状態から始まります。ルート構造も、サービス層も、エンティティモデルも、マイクロサービス間の呼び出し関係も把握していません。毎回のセッションでファイルを貼り付け、構造を説明し、コンテキストを再設定するために多くの時間を費やすことになります。

既存のツールはこの問題を部分的にしか解決できません。ルートアナライザーはコントローラーを把握しますが、サービスの依存関係を見逃します。ナレッジグラフツールは関係をキャプチャしますが、API サーフェスを無視します。結果として、両方のツールを実行し、出力を手動でつなぎ合わせ、コードベースが変わるたびに繰り返す羽目になります。

**codebeacon は、この 2 つのアプローチを 1 つの CLI に統合します。** コマンド 1 つでコードベース全体を tree-sitter AST で解析し、ファイル間の依存性注入を解決し、アーキテクチャのコミュニティクラスターを検出した上で、`CLAUDE.md`、`.cursorrules`、`AGENTS.md` にすぐ使えるコンテキストマップを生成します。AI アシスタントがセッション開始時からコードベースをすでに理解している状態になります。

---

## 主な機能

- **統合パイプライン** — ルート/コントローラー解析 + ナレッジグラフを 1 つのツールで、手動接続不要
- **24 フレームワーク、9 言語** — Spring Boot、NestJS、Django、FastAPI、Flask、Rails、Express、Fastify、Koa、React、Next.js、Vue、Nuxt、Angular、SvelteKit、Gin、Echo、Fiber、Laravel、Actix-Web、Axum、ASP.NET Core、Vapor、Ktor
- **tree-sitter ベース** — 正規表現ではなく構造的 AST パース；言語グラマーをデフォルトで同梱
- **2 パス DI 解決** — Pass 1 でローカル AST ノードを抽出、Pass 2 でグローバルシンボルテーブルを構築して Interface → Implementation のマッピングを解決
- **Wave マージアーキテクチャ** — ファイルを並列チャンクで処理して結果をグローバルにマージ；大規模モノレポでもメモリ問題なし
- **多様な出力形式** — JSON ナレッジグラフ、Markdown ウィキ、Obsidian Vault、AI コンテキストマップ、MCP サーバー
- **コミュニティ検出** — Leiden/Louvain クラスタリングで実際のアーキテクチャ境界を発見
- **インクリメンタルキャッシュ** — SHA-256 ベース；前回スキャン以降に変更されたファイルのみ再抽出
- **ゼロ設定** — フレームワークと言語を自動検出；繰り返し実行のために `codebeacon.yaml` を自動生成
- **ディープダイブモード** — `--deep-dive` で各サブプロジェクトに専用の `.codebeacon/` + `CLAUDE.md` を生成；**どのサブプロジェクトからでも**更新コマンドを実行するだけでワークスペース全体が自動同期

---

## クイックスタート

```bash
pip install codebeacon

codebeacon scan .
```

以上です。codebeacon がプロジェクトタイプを検出し、ルート/サービス/エンティティ/コンポーネントを抽出し、ナレッジグラフを構築して、すべての結果を `.codebeacon/` に書き込みます。

マルチプロジェクトワークスペースの場合：

```bash
codebeacon scan /path/to/workspace   # すべてのプロジェクトを自動検出、codebeacon.yaml を生成
codebeacon sync                      # 以降の実行は設定ファイルベースで
```

---

## 対応フレームワーク

| 言語 | フレームワーク |
|------|-------------|
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

## アーキテクチャ

codebeacon は 2 パス抽出パイプラインで動作します：

```
[Config] → [Discover] → [Wave / Extract] → [Resolve] → [Filter] → [Enrich] → [Graph] → [Wiki] → [ContextMap] → [Export]
                              │                  │           │          │
                         ローカル AST        シンボル     クロス言語   HTTP API
                         チャンク単位        テーブル     アーティ     共有 DB
                         (Pass 1)           マッチング   ファクト     エンティティ
                                            (Pass 2)    除去        エッジ
```

**Pass 1 — Wave 抽出：** `ThreadPoolExecutor` でファイルを並列チャンク処理します。各ファイルでルート、サービス、エンティティ、コンポーネント、依存関係の 5 つの抽出器を実行します。インクリメンタル再スキャンのために SHA-256 でキャッシュします。

**Pass 2 — グラフ構築：** すべての Wave 結果をマージします。グローバルシンボルテーブルが未解決の依存性注入参照を解決します — Spring の暗黙的な Bean 配線や TypeScript のインジェクショントークンのような、単一パスツールが見逃す Interface→Implementation マッピングを処理します。

**後処理：** HTTP API エッジがフロントエンドの URL 呼び出しとバックエンドルートを接続します。コミュニティ検出（Leiden → Louvain → 連結コンポーネントフォールバック）がグラフをアーキテクチャクラスターに分割します。

---

## 出力構造

スキャン後、コンテキストマップファイルはプロジェクトルートで更新され（既存のユーザーコンテンツは保持）、ナレッジグラフは `.codebeacon/` に生成されます：

```
project-root/
  CLAUDE.md              ← AI コンテキストマップ (codebeacon ブロックをマージ；ユーザーコンテンツ保持)
  .cursorrules           ← Cursor IDE コンテキスト (同じマージ方式)
  AGENTS.md              ← OpenAI Agents / Codex コンテキスト (同じマージ方式)
  .codebeacon/
    beacon.json          ← 完全なナレッジグラフ (ノード-リンク JSON、クエリ可能)
    REPORT.md            ← ゴッドノード、驚くべき接続、ハブファイル
    wiki/
      index.md           ← グローバルインデックス (~200 トークン)
      overview.md        ← プラットフォーム統計 + クロスプロジェクト接続
      routes.md          ← 全ルートテーブル
      cross-project/
        connections.md   ← クロスサービスエッジ
      <project>/
        index.md
        routes.md
        controllers/<Name>.md
        services/<Name>.md
        entities/<Name>.md
        components/<Name>.md
    obsidian/            ← Obsidian Vault (グラフノードごとに 1 ノート)
```

### ディープダイブモード

`--deep-dive` を使うと、各サブプロジェクトが独自の `.codebeacon/` + `CLAUDE.md` を持ちます。Claude Code は `CLAUDE.md` を階層的にロードするため、`api-server/` でセッションを開くとワークスペース全体の概要とプロジェクト固有の詳細が両方ロードされます。

最大のポイント：**どのサブプロジェクトから実行しても**、親の設定ファイルを自動検出してワークスペース全体を更新します：

```bash
# 初回ディープダイブスキャン
codebeacon scan /workspace --deep-dive

# 以降、どのサブプロジェクトからでも — 親の設定を見つけ、全プロジェクトを更新
cd /workspace/api-server
codebeacon scan . --update
```

出力構造：
```
workspace/
  CLAUDE.md                   ← 統合 (全プロジェクト)
  codebeacon.yaml             ← deep_dive: true
  .codebeacon/                ← 統合ナレッジグラフ
  api-server/
    CLAUDE.md                 ← api-server のみ
    .codebeacon/
  frontend/
    CLAUDE.md                 ← frontend のみ
    .codebeacon/
```

---

## AI 連携

### Claude Code スキル (`/codebeacon`)

codebeacon を Claude Code スラッシュコマンドとしてインストール:

```bash
pip install codebeacon
codebeacon install
```

`SKILL.md` を `~/.claude/skills/codebeacon/` にコピーし、`/codebeacon` トリガーを `~/.claude/CLAUDE.md` に登録します。Claude Code セッションを再起動後、`/codebeacon` と入力するとカレントディレクトリをスキャンします。

```
/codebeacon                  # カレントディレクトリをスキャン
/codebeacon /path/to/project # 特定のパスをスキャン
/codebeacon sync             # codebeacon.yaml から再スキャン
```

### MCP サーバー

codebeacon を MCP サーバーとして起動すると、MCP 対応クライアントから知識グラフを直接クエリできます。

**ステップ 1 — プロジェクトをスキャン:**
```bash
codebeacon scan .
```

**ステップ 2 — MCP クライアント設定に追加:**

**Claude Code** (プロジェクトルートの `.claude.json` またはグローバルの `~/.claude.json`):
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

**接続後に利用可能な MCP ツール:**

| ツール | 説明 |
|--------|------|
| `beacon_wiki_index` | プロジェクト全体の概要（ルート・サービス・エンティティ数） |
| `beacon_wiki_article` | パスで指定した Wiki 記事を読む |
| `beacon_query` | ラベルの部分文字列でノードを検索 |
| `beacon_path` | 2 ノード間の最短依存パス |
| `beacon_blast_radius` | 上流の呼び出し元と下流の影響ノード |
| `beacon_routes` | 全 HTTP ルート一覧（プロジェクトでフィルター可） |
| `beacon_services` | 全サービス/クラス一覧（プロジェクトでフィルター可） |

---

## インストールオプション

```bash
pip install codebeacon              # 言語グラマーをデフォルトで同梱
pip install codebeacon[cluster]     # + Leiden コミュニティ検出 (graspologic)
pip install --upgrade codebeacon    # 最新バージョン + 依存関係を同時更新
```

Java、Kotlin、Python、JavaScript、TypeScript、Go、Ruby、PHP、C#、Rust、Swift、HTML、Svelte のパーサーがデフォルトでインストールされます。追加フラグは不要です。

---

## CLI リファレンス

```bash
# プロジェクトまたはワークスペースのスキャン
codebeacon scan <path> [オプション]
codebeacon scan .                         # カレントディレクトリ
codebeacon scan /workspace                # ワークスペースルート (マルチプロジェクト)
codebeacon scan . --update                # インクリメンタル：変更ファイルのみ再抽出
codebeacon scan . --wiki-only             # 再抽出をスキップし、既存の beacon.json からウィキ/obsidian/コンテキストマップを再生成
codebeacon scan . --obsidian-dir <path>   # Obsidian Vault をカスタム場所に書き込み
codebeacon scan . --semantic              # LLM セマンティック抽出を有効化
codebeacon scan . --list-only             # フレームワーク検出のみ、抽出なし
codebeacon scan /workspace --deep-dive    # プロジェクト別 + 統合ワークスペース出力

# 設定ベースモード
codebeacon init [path]                    # codebeacon.yaml を自動生成
codebeacon sync                           # codebeacon.yaml ベースで実行
codebeacon sync --config <file>           # 特定の設定ファイルを使用

# ナレッジグラフのクエリ (近日公開)
codebeacon query <term>                   # ノードとエッジを検索
codebeacon path <source> <target>         # 2 ノード間の最短パス

# インテグレーション
codebeacon serve [--dir .codebeacon]      # MCP サーバー起動 (stdio)
codebeacon install                        # Claude Code スキルをインストール
```

---

## 設定

`codebeacon init` で `codebeacon.yaml` を生成するか、直接記述します：

```yaml
version: 1

projects:
  - name: api-server
    path: ./api-server
    type: spring-boot          # 省略可：自動検出されます

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
  chunk_size: 300              # チャンクあたりのファイル数
  max_parallel: 5              # 並列スレッド数

semantic:
  enabled: false               # --semantic フラグでオーバーライド

deep_dive: false               # true にすると各プロジェクト別出力を生成
```

### .codebeaconignore

プロジェクトルートに `.codebeaconignore` ファイルを置くと、スキャンから特定のディレクトリやファイルを除外できます。`.gitignore` と同じ文法 — 1 行に 1 パターン、`#` はコメント。

```
# .codebeaconignore
generated/
build/
*.generated.ts
fixtures/
```

---

## 比較

| | codesight | graphify | **codebeacon** |
|---|---|---|---|
| ルート / コントローラー解析 | ✅ | ❌ | ✅ |
| サービス / DI グラフ | 部分的 | ✅ | ✅ |
| Interface → Impl 解決 | ❌ | ❌ | ✅ |
| エンティティ / ORM モデル抽出 | ✅ | ❌ | ✅ |
| フロントエンドコンポーネント解析 | ✅ | ❌ | ✅ |
| コミュニティ検出 | ❌ | ✅ | ✅ |
| Obsidian Vault エクスポート | ❌ | ✅ | ✅ |
| MCP サーバー | ✅ | ❌ | ✅ |
| AI コンテキストマップ (CLAUDE.md) | ✅ | ✅ | ✅ |
| マルチプロジェクトワークスペース | 部分的 | ❌ | ✅ |
| Python ベース | ❌ | ✅ | ✅ |

codebeacon は両ツールの代替ではなく統合です — 共有の抽出・グラフレイヤーの上で、それぞれのツールが行うことの和集合を実装しています。

---

## ベンチマーク

| コードベース | スタック | ファイル数 | ノード | エッジ | コミュニティ | スキャン時間 |
|------------|--------|----------|-------|-------|------------|------------|
| multi-service SaaS app | SvelteKit + Next.js + Spring Boot (3プロジェクト) | 444 | 382 | 553 | 175 | ~12s |

---

## プライバシーとセキュリティ

すべての処理はローカルで行われます。ソースコードは外部に送信されません。

- tree-sitter AST パースはプロセス内でのみ実行
- テレメトリ、分析、通常操作中のネットワーク呼び出しなし
- `--semantic` フラグ（デフォルト無効）は 2 つの抽出モードを有効化します：
  1. **構造化コメント解析**（LLM 不要） — Javadoc（`@see`、`{@link}`）、Python ドキュメント文字列（`:class:`、`:func:`）、JSDoc（`@see`、`@param` 型）からクロスリファレンスを推論
  2. **LLM 推論**（オプション） — `ANTHROPIC_API_KEY` が設定されている場合、Claude API にコードの抜粋を送信して深い関係推論を実行；明示的に有効化した場合のみ使用

---

## コントリビューション

```bash
git clone https://github.com/Wandererer/codebeacon
cd codebeacon
pip install -e ".[dev,cluster]"
pytest
```

新しいフレームワークサポートを追加する最も簡単なエントリーポイントは、`codebeacon/extract/queries/` に tree-sitter クエリファイルを書くことです。完全なガイドは [`codebeacon/extract/queries/README.md`](codebeacon/extract/queries/README.md) を参照してください。

---

## ライセンス

MIT — [LICENSE](LICENSE) ファイルを参照。

---

## 謝辞

構造的 AST パースのための [tree-sitter](https://tree-sitter.github.io/tree-sitter/)、グラフ操作のための [NetworkX](https://networkx.org/)、Leiden コミュニティ検出のための [graspologic](https://microsoft.github.io/graspologic/) を基盤として構築されています。

[codesight](https://github.com/Houseofmvps/codesight) と [graphify](https://github.com/safishamsi/graphify) の相互補完的なアプローチからインスピレーションを受けました。
