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

## 0.7.1 の新機能

これまでで最大の監査リリースです:二重のアップストリーム・パリティ・スイープ(graphify v0.9.13–v0.9.53 / issue #1777–#3235、加えて codesight #50–#55)を、再現必須の原則で codebeacon に突き合わせて検証しました — 10個の並列フィクサーが**確定した欠陥およそ70件を修正**し、すべての修正を mutation テストにかけ、その後リードが実 CLI での統合実行を伴う敵対的レビューを行いました。テストスイート:885 → 1,481件。

- **JS/TS グラフがほぼ倍増しました** — export された小文字のアロー関数、`const`、そしてオブジェクトリテラルのメンバー(`export const useAuthStore = …`、`authUtils.clear`)がついにノードになります:実際の865ファイルの Next.js アプリで、コンポーネントノードは **960 → 2,237** に増え、何も寄与していなかったファイルは 406 → 108 に減りました。import は今やラベルへのフォールバックの前に、まず**パス**で解決されます(相対指定子、`extends` チェーンと `${configDir}` に対応した `tsconfig`/`jsconfig` エイリアス、パッケージサフィックス) — そのため `from codebeacon.graph.build import …` が無関係な `build` シンボルに結び付くことはなくなり、CLAUDE.md の「High-Impact Files」リストが現実を反映します。素の JS の `class X extends Y` の継承と、動的な `await import()` のエッジも捕捉されます。
- **ルートのプレフィックスが実際のフレームワークどおりに合成されます** — 稼働中の FastAPI/Express/Flask サーバーを基準に検証しました:`include_router(prefix=)` はルーター自身のプレフィックスと合成され、属性形式の include(`app.include_router(pkg.router, …)`、`@pkg.router.get`)がもう消えることはなく、同一ファイル内でカスケードしたマウントは掛け合わされて展開され、2回マウントされたルーターは両方のルートを産出し、Flask の `register_blueprint(url_prefix=)` は正しく *上書き* します。既知の限界:**ファイル**をまたぐマウントチェーンは依然として合成されません。
- **インターフェース→実装の DI 解決が実際に動くようになりました** — 抽出パイプラインのシリアライズ境界が 0.6.x 以来 `implements`/`extends` を静かに捨てていたため、wiki は正しく見えるのに機能全体がエンドツーエンドで死んでいました。修正し、キャッシュを無効化し、実際のパイプラインを通す境界テストで固めました。DI のバインディングには証拠のゲートも設けました:言語をまたぐ、あるいはプロジェクトをまたぐ捏造はもうありません(Spring の service が React コンポーネントを「注入」することはできません)。実装が複数ある曖昧なケースは `*Impl` の命名規約による場合のみ、明示的な `AMBIGUOUS` 信頼度でバインドされ、重複したエッジは上書きする代わりに、新しい `also` 属性の下に2つ目の関係を記録します。
- **ノードの同一性が決定的で、拡張子を認識します** — `Button.tsx` と `Button.jsx` は2つのノードです(以前は一方がもう一方を静かに吸収していました — codebeacon 自身のリポでは宣言の6.3%)。ノード ID はもうスレッドの完了順やチェックアウトディレクトリに依存しないため、wiki/obsidian のファイル名が実行のたびに入れ替わることがなくなります。衝突するラベルには、区別できる最短のパスサフィックスが付きます。(以前に潰れていたノードの ID は、アップグレード時に一度だけ入れ替わります。)
- **ignore 層が git にずっと近く一致します** — ネストした `.gitignore` は自身のサブツリーに適用され(モノレポの `app/.gitignore` が無視されて数万のビルドファイルがスキャンに引き込まれることがなくなりました)、`.git/info/exclude` が尊重され、リンクされた worktree はコーパスを二重にする代わりに構造的に検出され、BOM 付き / UTF-16 / NFD エンコードの ignore ファイルは静かにルールを落とすのではなくデコードされます。曖昧なディレクトリ名(`env/`、`build/`、`public/`、`coverage/`、…)は裏付けとなる証拠があるときにのみ刈り込まれます — UVM の `env/` テストベンチや `coverage/` という名前の Python パッケージはグラフに残ります。マッチングは約19倍高速になり、新しい `ignored.json` 診断が、すべてのサブツリーがスキップされた *理由* を記録します。
- **shrink ガードが、本当に重要な経路を守るようになりました** — 以前は `--update` があるというだけで解除されていましたが、それはまさに無人の経路(watch、git hook、CI)でした。権限エラー1つで、コミットされたグラフが静かに半減しかねなかったのです。今では削除されたすべてのノードをそのソースファイルに帰属させ(削除された / 新たに ignore された / **説明がつかない** — 拒否するのは最後のものだけで、本物の `--force` フラグが用意されています)、あらゆる経路で武装したままとなり、読み取れないサブツリーを「不明、免除しない」として扱い、ノードは変わらないのにエッジが潰れたときには警告します。
- **`scan → knowledge → scan` がもう詰まりません** — 0.7.0 で文書化されていたフローは、終了コード1(「refusing to shrink」)で終わるか、ノートのオーバーレイを静かに捨てるかのどちらかでした。ガードはティアを認識するようになり、knowledge のオーバーレイは**すべてのスキャンの後に自動で再適用**されます。ノートを削除すると、まさにそのノートだけが刈り取られます。書いた `[[wikilinks]]` がついにエッジを生成し(パースされたうえで捨てられていました — 損失100%)、ノートは `node_kind`/フロントマターを持ち、生成されたファイル(CLAUDE.md、KNOWLEDGE.md)がノートとして再取り込みされることはなくなりました。
- **コミットされたインデックスがきれいなままです** — 変更のない再スキャンが書き換えるコミット対象ファイルは、今や**ゼロ**です(以前はそのすべて。アップストリームでは約31,000ファイルの変動)。`built_at_ts` はコミットから導出され、エクスポートは内容が変わったときにのみ書き込まれ、マシンローカルの AST キャッシュは自分自身を git-ignore します。HTML エクスポート(`beacon.html`、`callflow.html`)は JS を**デフォルトでオフライン**同梱します(d3 + mermaid を `_assets/` 配下にベンダリング) — エアギャップの姿勢に沿ったものです。従来の挙動を保ちたい場合は `output.html_assets: cdn` を設定してください。ビルドマシンの絶対パスが、どの成果物にも漏れることはなくなりました。
- **プログラムから信頼できる MCP の応答** — ツールの失敗は、実行可能なメッセージとともに `isError: true` を返します(成功の形をしたエラー散文や、クライアントが飲み込んでしまうプロトコルエラーの代わりに)。名前解決は部分文字列より完全一致を優先するため、`blast_radius("User")` が `UserServiceImpl` について答えることはなくなりました。すべてのツールが `token_budget`(デフォルト2,000トークン)を尊重し、真の総量に対する切り詰めを告知します。
- **堅牢性とセキュリティのスイープ** — `.csproj` の XML は DOCTYPE/ENTITY のスクリーンを通してパースされます。モデルに提示されるテキスト(MCP 出力、CLAUDE.md)は、チャットテンプレートの制御トークンを形態(`<|…|>`、`[INST]`)に基づいて無力化します。`hook install` は git worktree で動作し、リポジトリを設定が半端なまま放置することがありません。`install`/`upgrade` は手で編集した SKILL.md を上書きせずにバックアップし、終端されていないマーカーがその下のユーザーコンテンツを削除できなくなりました。cp949/latin-1 の CLAUDE.md がスキャンをクラッシュさせません。`codebeacon … | head` はきれいに終了します。watch モードが Linux の inotify イベントで自分自身を再トリガーすることはなくなりました。Leiden クラスタリングにはシードが与えられ、再スキャンのたびにコミュニティが12%ずつ漂流することがなくなりました。

アップグレードノート:以前に潰れていた宣言のノード ID が一度だけ入れ替わります。semantic の `task_id` が一度だけ無効化されます(タスクはファイル全体をハッシュするようになり、「4,000文字以降の編集が二度と再分析されない」問題が解消しました)。AST キャッシュが一度だけ無効化されます(スキーマスタンプ)。新しいエッジ属性 `also`、新しい信頼度の値 `AMBIGUOUS`、semantic が発行した external ノードに付く新しい `verification` マーカー。リポジトリが既に `.codebeacon/cache/` をコミットしている場合は、`git rm --cached -r .codebeacon/cache` を一度実行してください — 新しい自己無視の `.gitignore` は、既に追跡中のファイルを追跡解除できません。

過去のリリース履歴は [CHANGELOG.md](CHANGELOG.md) を参照してください(英語)。

---

## なぜ codebeacon なのか

AI コーディングセッションを新しく開くたびに、アシスタントは白紙の状態から始まります。ルート構造も、サービス層も、エンティティモデルも、マイクロサービス間の呼び出し関係も把握していません。毎回のセッションでファイルを貼り付け、構造を説明し、コンテキストを再設定するために多くの時間を費やすことになります。

既存のツールはこの問題を部分的にしか解決できません。ルートアナライザーはコントローラーを把握しますが、サービスの依存関係を見逃します。ナレッジグラフツールは関係をキャプチャしますが、API サーフェスを無視します。結果として、両方のツールを実行し、出力を手動でつなぎ合わせ、コードベースが変わるたびに繰り返す羽目になります。

**codebeacon は、この 2 つのアプローチを 1 つの CLI に統合します。** コマンド 1 つでコードベース全体を tree-sitter AST で解析し、ファイル間の依存性注入を解決し、アーキテクチャのコミュニティクラスターを検出した上で、`CLAUDE.md`、`.cursorrules`、`AGENTS.md` にすぐ使えるコンテキストマップを生成します。AI アシスタントがセッション開始時からコードベースをすでに理解している状態になります。

---

## 主な機能

- **統合パイプライン** — ルート/コントローラー解析 + ナレッジグラフを 1 つのツールで、手動接続不要
- **27 フレームワーク、9 言語** — Spring Boot、NestJS、Django、FastAPI、Flask、Rails、Express、Fastify、Koa、React、Next.js、Vue、Nuxt、Angular、SvelteKit、Gin、Echo、Fiber、Laravel、Actix-Web、Axum、Tauri、Rocket、Warp、ASP.NET Core、Vapor、Ktor
- **tree-sitter ベース** — 正規表現ではなく構造的 AST パース；言語グラマーをデフォルトで同梱
- **2 パス DI 解決** — Pass 1 でローカル AST ノードを抽出、Pass 2 でグローバルシンボルテーブルを構築して Interface → Implementation のマッピングを解決
- **Wave マージアーキテクチャ** — ファイルを並列チャンクで処理して結果をグローバルにマージ；大規模モノレポでもメモリ問題なし
- **多様な出力形式** — JSON ナレッジグラフ、Markdown ウィキ、Obsidian Vault、AI コンテキストマップ、MCP サーバー、インタラクティブ HTML
- **ビジュアル探索** — `beacon.html`(D3 折りたたみツリー) と `callflow.html`(コミュニティ別 Mermaid アーキテクチャ図) を全スキャンで自動再生成
- **コミュニティ検出** — Leiden/Louvain クラスタリングで実際のアーキテクチャ境界を発見
- **インクリメンタルキャッシュ** — SHA-256 + mtime/size 高速パス；Obsidian/iCloud/Nextcloud のような mtime のみの更新では再抽出をトリガしない
- **信頼度プロモーション** — 明示的な import がバインディングを証明する場合、ファイル間 `calls` エッジを INFERRED から EXTRACTED へ自動昇格
- **安全な書き込み** — beacon.json には shrink guard(部分実行が完全なグラフを上書きできない)と `built_at_commit` スタンプがあり、REPORT.md は現在の HEAD に対して stale 状態を表示
- **マルチ開発者対応** — `codebeacon hook install` で `beacon.json` の git マージドライバと post-commit インクリメンタル再ビルドフックを登録；同じブランチで複数の開発者が同時にスキャンしてもマージ競合が発生しない
- **ハードニング済み出力** — YAML フロントマターと MCP ラベルは U+2028/U+2029、C0 制御文字、bidi マークをすべて除去；ソースコード中の悪意ある識別子が Obsidian YAML パーサを破壊したり、LLM エージェントのコンテキストに制御シーケンスを注入することを防止
- **gitignore 互換 `.codebeaconignore`** — last-match-wins、`!` 否定、ディレクトリパターン(`build/`)、アンカーパターン(`/secrets.txt`)、末尾空白処理
- **ゼロ設定** — フレームワークと言語を自動検出；繰り返し実行のために `codebeacon.yaml` を自動生成
- **ディープダイブモード** — `--deep-dive` で各サブプロジェクトに専用の `.codebeacon/` + `CLAUDE.md` を生成；**どのサブプロジェクトからでも**更新コマンドを実行するだけでワークスペース全体が自動同期
- **ワークスペース自動再検出** — `scan`/`sync` 実行のたびにワークスペースを再スキャンし、`codebeacon.yaml` に未登録の新規プロジェクトを自動追加してから抽出を開始するため、新しく追加されたサブプロジェクトが見落とされることがない；yaml を手動で管理している場合は `--no-rediscover` でオプトアウト可能
- **Graphify 風のセマンティック強化** — AST 抽出後、スキルがチャンクごとに 1 つのサブエージェントを並列でディスパッチし、`{nodes, edges, hyperedges}` のフル知識グラフ断片を抽出。関係 8 種（`calls`/`implements`/`references`/`cites`/`conceptually_related_to`/`shares_data_with`/`semantically_similar_to`/`rationale_for`）+ 信頼度 3 段階（EXTRACTED/INFERRED/AMBIGUOUS）をサポート。Claude Code ではサブエージェントがホストモデルより 1 段階下（Opus→Sonnet、Sonnet→Haiku）に自動ダウングレードされ、コーパスサイズに比例したコストを維持。コードノードは AST が担当し、LLM は `concept`/`document`/`paper` ノードのみ寄与可能。既存の 0.3.x アーカイブは新スキーマで透過的にリプレイされる
- **ナレッジモード (`codebeacon knowledge`)** — マークダウンノート（ADR、議事録、ふりかえり、仕様、リサーチ）をスキャンし、`.codebeacon/` の隣に単一の `KNOWLEDGE.md` を生成。ファイル名・見出しパターンで自動分類、Obsidian の YAML frontmatter と `[[backlinks]]` をパースし、最上部に「Key Decisions」+「Open Questions」のロールアップを提示することで、コードベースが*なぜ*このような形になっているのかをエージェントに伝える。ヒューリスティックのみで LLM 呼び出しなし
- **パス省略形** — `codebeacon ./src` が `codebeacon scan ./src` と等価に。先頭引数が登録済みサブコマンドでない場合は `scan` が自動注入されるため、`graphify <path>` / `codesight <path>` の操作感もそのまま使える
- **強化された semantic パイプライン** — `semantic-apply` がエージェント JSONL の不正行（null/リスト/code-fence/必須フィールド欠落）をガードし、壊れた `confidence_score`（None/NaN/文字列/範囲外）を安全なデフォルトに coerce、merge 直前に `beacon.json` → `beacon.json.bak` をスナップショットして AST ベースラインを常に復元可能にし、`beacon.html`/`callflow.html` も再生成して新たに推論されたエッジが可視化に反映される
- **機密ファイル・ディレクトリのガード** — `secrets/`、`credentials/`、`.ssh/`、`.aws/`、`.gnupg/` を常にスキップ。credential パターン（`api_token`、`oauth_token`、`private_key`、`client_secret`; アンダースコア*と*ハイフン両方の変種）に一致するファイル名は、抽出器に到達する前にコレクタ段階で除外

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
| Rust | Actix-Web、Axum、Tauri、Rocket、Warp |
| C# | ASP.NET Core, Blazor (`.razor`, `.cshtml`); `.sln` / `.csproj` / `.fsproj` / `.vbproj` から `ProjectReference` + `PackageReference` を解析 |
| Swift | Vapor |
| ArkTS | `.ets` (HarmonyOS) を収集 — extractor は framework-agnostic |

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
    beacon.json          ← 完全なナレッジグラフ；`meta.built_at_commit` 埋め込み
    beacon.html          ← D3 折りたたみツリービューア (ブラウザで開く)
    callflow.html        ← コミュニティ別 Mermaid コールフロー図
    REPORT.md            ← ゴッドノード、驚くべき接続、ハブファイル、フレッシュネス
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
codebeacon scan . --semantic              # 構造化コメント参照（Javadoc/JSDoc/docstring）の抽出を有効化
codebeacon scan . --list-only             # フレームワーク検出のみ、抽出なし
codebeacon scan /workspace --deep-dive    # プロジェクト別 + 統合ワークスペース出力
codebeacon scan . --exclude 'docs/**' --exclude '*.gen.ts'
                                          # 繰り返し可能な gitignore スタイルパターン
                                          # .codebeaconignore / .gitignore とマージ

# 設定ベースモード
codebeacon init [path]                    # codebeacon.yaml を自動生成
codebeacon sync                           # codebeacon.yaml ベースで実行 (新規ワークスペースプロジェクトを自動追加)
codebeacon sync --config <file>           # 特定の設定ファイルを使用
codebeacon sync --no-rediscover           # 新規プロジェクトの自動追加を無効化 (手動キュレーションモード)
codebeacon sync --exclude PATTERN         # 同じフラグ、同じ意味

# PR / CI: この diff は実際に何を壊すのか?
codebeacon affected --base main           # 変更ファイルの上流呼び出し元を walk
codebeacon affected --base origin/main --head HEAD --depth 4 --limit 200
codebeacon affected src/foo.py src/bar.py  # 明示パス — git なしでも動作

# ナレッジグラフのクエリ
codebeacon query <term> [--dir .codebeacon] [--limit N]   # ラベル部分文字列でノード検索
codebeacon path <source> <target> [--dir .codebeacon]     # 最短依存関係パス

# マルチ開発者サポート (git plumbing)
codebeacon hook install [path]            # merge driver + post-commit インクリメンタル再ビルドのインストール
codebeacon merge-driver <base> <cur> <other>  # `hook install` 後 git が呼び出す；beacon.json を union マージ

# AI-セマンティック補強 (LLM はエージェント、整合性管理は codebeacon)
codebeacon semantic-prepare [--dir .codebeacon] [--max-tasks N] [--chunk-size N]
                                          # .codebeacon/semantic/original/*.jsonl アーカイブを fresh
                                          # beacon.json に再適用 + 失われたノードを指す stale エントリ
                                          # を prune し、新規候補のみを .codebeacon/semantic/pending/
                                          # chunk_NNN.jsonl に書き出す (chunk あたり --chunk-size 件、
                                          # 既定 10)。task_id にコンテンツハッシュが入っているので、
                                          # ファイル内容が変わると自動で再発行される。
codebeacon semantic-apply   [--dir .codebeacon]
                                          # エージェントが書いた .codebeacon/semantic/results/
                                          # chunk_NNN.jsonl をそれぞれ INFERRED references エッジ
                                          # として beacon.json にマージし、pending/chunk_NNN.jsonl
                                          # を original/chunk_NNN.jsonl に移動 (永続アーカイブ)。
                                          # results は削除、wiki/obsidian/コンテキストマップを再生成。

# インテグレーション
codebeacon serve [--dir .codebeacon]      # MCP サーバー起動 (stdio)
codebeacon install                        # Claude Code スキルをインストール (user スコープ: ~/.claude/)
codebeacon install --project [PATH]       # <PATH>/.claude/ にインストール (チーム共有・リポジトリ固定)
codebeacon upgrade                        # pip で更新 + ~/.claude/skills/codebeacon/SKILL.md を再生成
                                          # (`--force` で editable インストール時も強制実行)
```

---

## AI-セマンティック補強（`/codebeacon` スキル経由）

tree-sitter パースは AST に**ある**ものを見つけます。**AI-セマンティック**は**コメントのみにある**ものを見つけます — Javadoc 中の `@see UserService`、Python docstring 中の `:class:`OrderRepository``、ルートハンドラの横に書かれた契約上の参照など。codebeacon はこのために 2 層を提供します：

| レイヤー | フラグ | コスト | 捕捉対象 |
|---|---|---|---|
| 構造化コメントパース | `--semantic` | 無料、ローカル、LLM 不要 | Javadoc `@see` / `{@link}`、JSDoc `@see` / `@param` 型、Python `:class:` / `:func:` / `See Also` |
| **AI-セマンティック** | `/codebeacon` スキルで自動 | エージェントの**現在のモデル**を使用 — **API キー不要** | 正規表現が捕えられないクラス／型／サービス参照（自由文、間接的言及、型ヒントのみ等） |

CLI 自体は LLM API 呼び出しを **行いません**。AI-セマンティック層は意図的に `/codebeacon` Claude Code スキル内で**実行中のエージェントが所有**します — そうすることでユーザーが選んだモデル（Opus / Sonnet / Haiku など）がそのまま使われ、codebeacon 自体は `ANTHROPIC_API_KEY` もクラウド設定も必要としません。

### 実行フロー

Claude Code で `/codebeacon` を呼び出すと：

1. `scan` / `sync` が AST から `beacon.json` を構築（LLM 呼び出しなし）。
2. `codebeacon semantic-prepare` が `.codebeacon/semantic/original/*.jsonl` アーカイブを新グラフに再適用し、グラフから消えたノードを指す stale エントリを **prune**。続いて新規 task を `.codebeacon/semantic/pending/chunk_NNN.jsonl` に書き出す（`--chunk-size` 単位、既定 10）。chunk 番号は永続アーカイブの続きから始まるため衝突しません。
3. スキルは pending chunk を**1 つずつ**処理。各 `pending/chunk_NNN.jsonl` について、エージェント（現在セッションのモデル）が task の `excerpt` を読み、同名の `semantic/results/chunk_NNN.jsonl` を書きます。
4. `codebeacon semantic-apply` が結果を `INFERRED references` エッジとして `beacon.json` にマージし、完了済み `pending/chunk_NNN.jsonl` を **`semantic/original/chunk_NNN.jsonl`** に**移動**（適用済みエッジを一緒に記録）。results は削除、wiki + obsidian + コンテキストマップを再生成。
5. 次回スキャン時：`semantic-prepare` が `original/` の全 chunk のエッジを新グラフに再適用（過去の推論を保全）し、既に処理済みの `task_id` はスキップ。`task_id` = `SHA1(file_path | node_id | excerpt_hash[:8])` — ファイルのセマンティック内容が変われば自動的に新しい id になり再解析されます。

→ 増分かつ冪等の補強。同じ (ファイル, 内容) を二度分析せず、蓄積された AI シグナルは毎回の再スキャンを生き延び、chunk 分割でエージェントの作業セットも小さく保てます。

### 直接 CLI 使用

スキルを介さず（例：CI）に同じ 2 コマンドで手動運用し、`results/chunk_NNN.jsonl` を自分で書くこともできます：

```bash
codebeacon scan .
codebeacon semantic-prepare --dir .codebeacon --max-tasks 50 --chunk-size 10

# .codebeacon/semantic/pending/chunk_001.jsonl ... が生成される。
# 各 pending chunk について同名の results/chunk_NNN.jsonl を書く。各行：
#   {"task_id":"...", "source_node_id":"...", "edges":[
#     {"target_name":"UserService","relation":"references","confidence_score":0.7}
#   ]}

codebeacon semantic-apply --dir .codebeacon
```

### オプトアウト

スキル呼び出し時に `--no-semantic`（または `--wiki-only`、`--list-only`）を渡せば AI ステップは完全にスキップされます。`--semantic` を `scan` / `sync` に渡すと構造化コメント層は引き続き動作します。

---

## ビジュアル探索

毎回のスキャンで `beacon.json` の隣に self-contained な HTML ファイルが 2 つ書き出されます：

```
.codebeacon/beacon.html      # D3 v7 折りたたみツリー — どのブラウザでも開ける
.codebeacon/callflow.html    # Mermaid アーキテクチャ図、コミュニティごとに 1 つ
```

ビルド不要、静的サーバー不要、コピペ不要。ファイルを開いて、プロジェクト → タイプ → ノードの順にクリックして展開；ホバーするとソースパスと次数が表示。`callflow.html` はグラフをコミュニティでグループ化し、それぞれを Mermaid フローチャートで描画。コミュニティ外への出力エッジは折りたたみテーブルに一覧表示。

---

## マルチ開発者ワークフロー

同じブランチで 2 人の開発者が `codebeacon scan` を実行すると、わずかに異なる `beacon.json` が出力されます — 歴史的にマージ競合のホットスポット。`codebeacon hook install` がこれを解決します：

```bash
codebeacon hook install            # リポジトリのルートで
```

以下を登録します：

- 2 つの `beacon.json` を 1 つに union マージする **git マージドライバ** (ノードは ID で、エッジは `(source, target, relation)` で重複排除)
- `*beacon.json` をドライバに向ける `.gitattributes` エントリ
- グラフがコミットから取り残されないよう、バックグラウンドで `codebeacon scan . --update` を走らせる **post-commit フック**。出力は `~/.cache/codebeacon-rebuild.log` へ

マージドライバは常に 0 で終了 — グラフ再生成は実際のマージを絶対にブロックしません。

---

## 安全性の保証

毎回の成功したスキャンでライターが強制する不変条件：

| ガード | 防げるもの |
|---|---|
| **Shrink guard** | 部分抽出失敗や中断された実行が、より大きく完全な `beacon.json` を上書きできない。API から `force=True` でバイパス可能 |
| **アトミック書き込み** | `beacon.json` は `os.replace` 経由で書かれるため、ファイルは完全か未変更のどちらか — 半書きグラフは存在しない |
| **`built_at_commit` スタンプ** | `beacon.json` は `meta.built_at_commit` (完全 SHA) を埋め込み、`REPORT.md` は short SHA を表示。HEAD がそれより進んでいる場合、1 行の対処ヒント付きで `⚠ stale` を表示 |
| **Frontmatter / ラベルのハードニング** | YAML フロントマター値は single-quoted で U+2028、U+2029、タブ、C0 制御文字をエスケープ；MCP ツール出力はすべてのラベルを同じ sanitizer に通す。ソースコード中の悪意ある識別子は Obsidian の YAML パーサを壊したり、LLM エージェントのコンテキストに制御シーケンスを注入できない |

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
  enabled: false               # 構造化コメント抽出のみ。--semantic で上書き。
                               # AI-セマンティックはこのキーに無い ―
                               # /codebeacon スキル (= 実行中のエージェント)
                               # が trigger する。

deep_dive: false               # true にすると各プロジェクト別出力を生成
```

### .codebeaconignore

プロジェクトルートに `.codebeaconignore` ファイルを置くと、スキャンから特定のディレクトリやファイルを除外できます。`.gitignore` のセマンティクスと一致 — last-match-wins、`!` 否定、アンカーパターン(`/foo`)、ディレクトリ専用パターン(`build/`)、コメント：

```
# .codebeaconignore

# ディレクトリ
build/
generated/
fixtures/

# ルートにのみアンカー
/scripts/local-only.ts

# グロブパターン
*.gen.ts
**/snapshots/**

# build/ が無視されていても特定ファイルは再包含
!build/manifest.ts
```

`!pattern` は以前に無視されたパスを再包含；後の規則が前の規則を上書きします。ウォーカーはルールセットに名前が一致するディレクトリを刈り取りますが、`!` 否定規則があるときは刈り取りを遅延し、各ファイルごとに検査します。

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

AST 処理はすべてローカルで実行されます。codebeacon を直接呼び出す限り、ソースコードはマシンの外に出ません。

- tree-sitter AST パースはプロセス内でのみ実行
- テレメトリ、分析、通常操作中のネットワーク呼び出しなし
- CLI 自体は **LLM プロバイダーを一切呼び出しません** — codebeacon パッケージには API クライアントもキー処理もモデル名もありません
- `--semantic` は **構造化コメントパースのみ** を有効化します（Javadoc `@see` / `{@link}`、JSDoc `@see` / `@param` 型、Python `:class:` / `:func:` / `See Also`）。完全ローカル。
- **AI-セマンティック**（LLM ベースの深い推論層）は `/codebeacon` Claude Code スキルが起動します。エージェントが `semantic-tasks.jsonl` を読み、**現在セッションのモデル** で解析を実行して `semantic-results.jsonl` を書き戻します。Python CLI はタスクバッチの準備と結果の統合のみを担当し、どのモデルが使われたかすら知りません。スキル呼び出しに `--no-semantic` を渡せば LLM ステップは完全にスキップされます。

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
