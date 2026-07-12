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

## 0.7.0 の新機能

バグ修正のスイープというより機能リリースです:codebeacon にライブのファイルウォッチャーが加わり、設計ノートをコードグラフに繋ぎ、2つの新しいフロントエンド(MCP サーバー用の npm ランチャーと GitHub Action)を提供し、デフォルトでインデックスする対象を絞り込みました。すべての機能はローカルファーストのままです — コアスキャンは相変わらずネットワークも、クラウドも、モデルも必要としません。

- **`codebeacon watch` がインデックスをライブに保ちます** — デバウンスされたファイルウォッチャー(`codebeacon watch [path] [--debounce 2.0] [--once] [--exclude PATTERN]`)が、監視中のソースファイルが変わるたびにグラフを再同期します。編集の集中 — 500ファイルの `git checkout`、ブランチ切り替え — は単一の再同期にまとめられ、ウォッチャーはスキャナーとまったく同じ無視ルールを再利用するため、インデックスを書き込む動作が自身の `.codebeacon/` 出力を巡るループでウォッチャーを起こすことはありません。新しいオプションの extra が必要です:`pip install 'codebeacon[watch]'`(watchdog)。
- **設計ノートがコードグラフに繋がります** — `codebeacon knowledge` は、インデックスが既に存在する場合、ノート(ADR、会議メモ、レトロ、仕様)を `beacon.json` の *中に* 書き込むようになりました:明示的なファイルパス参照は信頼された `references` エッジになり、特徴的なシンボルの言及(`PaymentService`、単なる `User` は決して対象外)は `AMBIGUOUS` な `mentions` エッジになります — こうしてグラフを読むエージェントは、ある service が *なぜ* その形をしているのかを学びます。`codebeacon scan` はコードグラフをソースだけから再構築してこのオーバーレイを捨てるため、リンクを復元するには **スキャンの後に `codebeacon knowledge` を再実行してください**。
- **`beacon_knowledge` MCP ツール** — 新しいツールがキーワードでノートを検索し、あるいは指定したコードノードに繋がったノートを一覧して、コードの背後にある意思決定の軌跡を MCP 越しに直接公開します。
- **MCP サーバー用の npm ランチャー** — `@codebeacon/mcp` により、MCP クライアントは期待どおりの npx ファーストの方法でサーバーを起動できます(`"command": "npx", "args": ["-y", "@codebeacon/mcp"]`)。依存関係ゼロの Node シムが、動作する codebeacon を PATH → `uvx` → `pipx run` → `python3 -m codebeacon` の順に解決し、stdio を手を加えずそのまま転送します。[`npm/README.md`](npm/README.md) を参照。(0.7.0 に同梱、npm へはまだ公開されていません。)
- **PR コンテキスト用の GitHub Action** — コンポジットアクションが、すべてのプルリクエストに、コミットされた知識グラフのうち影響を受けたスライスをコメントします:変更が触れる wiki 記事、上流のブラスト半径、そして編集された高影響のハブファイル — AI 時代のレビューのためのアーキテクチャドリフト検査です。コミットされた `.codebeacon/` インデックス、`fetch-depth: 0`、`permissions: pull-requests: write` が必要です。[`action/README.md`](action/README.md) と [`action/examples/pr-context.yml`](action/examples/pr-context.yml) を参照。
- **ワークスペースの CLAUDE.md が約200行以下に収まります** — マルチプロジェクトのワークスペースでは、ルートの `CLAUDE.md` が共有の概要だけを保ち、プロジェクトごとの詳細を、`paths:` フロントマターがそのプロジェクトのファイルに触れたときだけ読み込むスコープ付きの `.claude/rules/codebeacon-<project>.md` ファイルに移すようになりました(コンテキストファイルに関する Anthropic 自身のガイダンスに従っています)。単一プロジェクトの出力は変わりません。従来の一枚岩ファイルが欲しい場合は `output.context_map.rules_split: false` を設定してください。重複するプロジェクト行もまとめられます。
- **テストフィクスチャがデフォルトで無視されます** — どの深さの `tests/fixtures/`、`test/fixtures/`、`__fixtures__/` もデフォルトで無視されるようになり、プロジェクトの合成テスト入力が偽のルートや service をグラフに注入しなくなります(codebeacon 自身のセルフスキャンは、フィクスチャの `main.py` を5つの「ルート」として報告していました)。これは最も優先度の低いルールなので、`.codebeaconignore` に `!tests/fixtures/` の行を入れれば再び含められ、スキャンをフィクスチャディレクトリ *に* 向ければ依然として収集されます。
- **Warp のルート抽出が本物になりました** — Warp のフィルタ・コンビネータのルートが実際に抽出されます:`warp::path!(...)` と `warp::path("x")` のセグメント、メソッドコンビネータ(`warp::get()` / `post()` / …)、そして `.map` / `.and_then` ハンドラが、それらを囲むバインディングを基準に相関づけられ、まるごとのルートになります。正直な限界(クエリヘッダーに明記):1つのバインディング内で `.or(...)` で繋がれたフィルタは単一の連結ルートに潰れ、`warp::path::param()` のフィルタ呼び出しセグメントとクロージャハンドラは未解決のまま残ります。

---

## 0.6.9 の新機能

これまでで最大規模の監査リリースです。二重のアップストリーム・パリティ・スイープ(codesight のトラッカーに対する史上初の完全監査に加え、graphify v0.9.4–v0.9.12 / issue は #1776 まで)と、codebeacon 自体に対する独立したマルチエージェント・バグハントを組み合わせました。各候補は修正前に再現し、各修正は mutation テストにかけ、さらに敵対的な2次レビューが修正自体を攻撃して、リリース前にさらに18個の穴を捕まえました。**実バグ48件を修正。**

- **CLAUDE.md が安全になりました** — 手書きの CLAUDE.md(例:`/init` 由来)では、マージステップがユーザー自身の `## Architecture` / `## Common Commands` セクションを codebeacon の出力と誤認して削除する可能性がありました。ストリップ処理は今や codebeacon 生成物だと確実に判別されたファイルでのみ、生成ブロックにアンカリングして実行されます — あなたのセクションは残ります。`codebeacon.yaml` もアトミックに(シンボリックリンク越しでも、ファイルモードを保持しつつ)書き込まれるようになり、中断された書き込みが手作業で整えた設定を破壊できなくなりました。
- **ファイルがインデックスから静かに消えなくなりました** — 大文字の拡張子(`App.PY`、`Page.TSX`)がスキップされ、資格情報にちなんだ名前のソースモジュール(`api_key_manager.go`、`access_token_service.py`)がシークレットファイル・ヒューリスティックで除外され、`.gitignore` 内の非 UTF-8 バイト1個がスキャン全体をクラッシュさせ、`build/` や `dist/` という名前のフォルダ配下にチェックアウトしたリポは、アーティファクトフィルタが祖先ディレクトリにマッチして**グラフ全体が消去**されていました。すべて修正済みです。スキップされたシンボリックリンクは、沈黙の代わりにグループ化された警告を1つ出すようになりました。
- **`.gitignore` の扱いが git と完全に一致するようになりました** — 否定セマンティクス(`dir/` + `!dir/keep.txt`)を、あらゆるルール形態にわたって `git check-ignore` と differential テストしています。git とまったく同じく、除外されたディレクトリ配下のファイルは再び含めることができません。標準の救済イディオム `dir/*` + `!dir/keep` は従来どおり動作します。
- **同名プロジェクトが共存します** — すべて `frontend` という名前の2つ(または3つ)のサブプロジェクトが以前は1つに潰れていました:ノード ID の衝突でルートが静かに脱落し、それぞれの wiki/obsidian フォルダが互いを上書きしていました。重複する名前は今や親ディレクトリのプレフィックスで自動的に区別されます。
- **ルート抽出を正確性の観点から全面的に見直しました** — Express の `app.use('/api', router)` マウントプレフィックスが適用され、チェーンした `router.route(x).get().post()` があらゆる verb を産出します。Flask の `register_blueprint` / FastAPI の `include_router` プレフィックスがファイル内の出現位置に依存しなくなりました。Spring の `@RequestMapping(method = RequestMethod.X)` が `ANY` ではなく実際の verb を記録します。Next.js の catch-all セグメント(`[...slug]`)が壊れなくなり、`@slot` 並列ルートが URL から除去されます。Laravel の教科書的な `class X extends Model` がついにエンティティを生成します(以前は完全修飾されたベースのみがマッチ — `ViewModel` はもう紛れ込みません)。
- **幽霊グラフエッジを排除しました** — `CONFIG` のような小文字の import が無関係な `Config` クラスに大文字小文字の畳み込みで結び付く(偽の god-node パターン)ことがなくなり、import が言語境界を越えてバインドすることは決してなく(`import time` → `time.ts`)、DI バインディングはどこかにある最初の同名クラスではなく登録元のプロジェクトを優先し、1つのディレクトリ内の同名の service + entity が単一ノードに潰れなくなりました。
- **エクスポートが Windows 堅牢かつクラッシュ堅牢になりました** — obsidian のノート名は Windows で不正な文字セット全体を除去し(Flask の `<string:id>` ルートは Windows でエクスポートを壊していました)、予約デバイス名を防御します。`None` ラベルは wiki・call-flow HTML・obsidian エクスポーターをもうクラッシュさせません。git hook は LF 改行で書き込まれ、Windows でも実行されます。そして長いプロジェクト名がエクスポート途中でファイルシステムの上限を超えることもなくなりました。
- **不正な入力1つで長時間稼働のプロセスを殺せなくなりました** — MCP サーバーは不正な JSON-RPC メッセージで死なずに生き延びます。破損した `beacon.json` や AST キャッシュ(無効な UTF-8 や null/不正なコレクションを含む)はバックアップして報告され、`affected`・`serve`・マージドライバーをクラッシュさせません。
- **バイト単位で再現可能な出力** — ノードの順序がスレッドの完了順を追わなくなり、共有エンティティの注釈がソートされるため、変更のないツリーを2回スキャンするとバイト単位で同一の `beacon.json`・wiki・CLAUDE.md が生成されます。graspologic の API 変更で静かに壊れていた(*一度も*実行されなかった)Leiden クラスタリングバックエンドも復帰しました。
- **書いた設定が実際に走る設定です** — 文書化された `codebeacon.yaml` の設定(`wave.*`、`output.wiki/obsidian`、`context_map.targets`、`semantic.enabled`)はパースされたうえで無視されていましたが、今やパイプラインを実際に駆動します。ワークスペース内で `--list-only` が尊重され、`codebeacon upgrade` は uv venv インストールに正しいコマンドを案内します。おまけの一貫性:CLAUDE.md の Projects 表・Notes 列・Architecture セクションが単一の「Services」件数で一致し、wiki とも揃いました。

---

## 0.6.8 の新機能

アップストリーム v0.8.41–v0.9.3(報告された issue は #1568 まで)の graphify パリティ監査です。各候補は修正前に codebeacon 上で実際に再現し、敵対的レビューパスで再確認しました。**実バグ7件**を確認、データ損失トラップとプライバシー漏洩が目玉です。

- **`--obsidian-dir` がノートを削除しなくなりました** — 既存の Obsidian vault を指定すると、再生成前にその配下の*すべて*の `.md` を一掃していたため、実際の vault を空にしてしまう可能性がありました。codebeacon は所有していないディレクトリを拒否するようになり(完全に空のディレクトリ、または `.codebeacon-vault.json` マーカーを持つディレクトリのみ採用)、削除する代わりに明確なメッセージとともにエクスポートをスキップします。
- **`.codebeaconignore` によって `.gitignore` が静かに無効化されなくなりました** — `.codebeaconignore` を追加すると以前はリポジトリの `.gitignore` を*置き換えて*いたため、`.gitignore` だけで除外されているファイル(中立的な名前の `prod-dump.sql`、`customer-data.*`)がコミットされる `.codebeacon/` 成果物にインデックスされる可能性がありました。両者は今やマージされます(競合時は `.codebeaconignore` が優先);追加しても除外が*増える*だけになりました。
- **コミットされる成果物にマシン絶対パスが含まれなくなりました** — エッジ/リンクの `source_file` 値(`beacon.json` の大半)と wiki/obsidian ノートの `Source:` 行が絶対パス `/Users/you/...` を保持していたため、コミットされたインデックスに可搬性がなく、ローカルパスが漏洩していました。すべてプロジェクト相対になりました(エッジ、およびプロジェクト横断の `shares_db_entity` ファイルも含む)。
- **異なるディレクトリの同名シンボルがノートを上書きしなくなりました** — wiki/obsidian のファイル名は大文字小文字を畳み込まずにラベルから生成されていたため、macOS/Windows で `UserService` と `userService` が衝突し、片方のノートが静かに失われていました。ファイル名は衝突耐性のソルトと大文字小文字の畳み込みを行うようになり、記号のみのラベル(`@`)は壊れた `@.md` の代わりに `unnamed` にフォールバックします。
- **破損した `beacon.json` でクラッシュしなくなりました** — `codebeacon affected`、MCP サーバー、`--wiki-only` 実行は、破損/切り詰められたグラフをバックアップし、生のトレースバックの代わりに明確な「scan を再実行してください」メッセージを報告するようになりました。
- **より多くの React コンポーネントを捕捉するようになりました** — `react.scm` は関数式コンポーネント(`const X = function() {…}`)、`React.` プレフィックスなしの bare import HOC(`const X = forwardRef(…)`)、および非エクスポートの `function X()` コンポーネントを見落としていました。この3つすべてが抽出されるようになりました。
- **wiki のリンクがリンク切れにならなくなりました** — 一度も書き込まれなかったページへのリンクはプレーンテキストに格下げされ、隣接バケット内の記事(サービス→そのエンティティ)へのリンクは、存在しないファイルを指す代わりに正しい相対パスに修復されます。

---

## 0.6.7 の新機能

0.6.6 の graphify パリティ監査のフォローアップ: grammar ドリフトが静かに埋もれず明示的に失敗するようになり、ignore ファイルの否定ルールがスキャンを遅くしなくなりました。

- **grammar ドリフトは「静かな空グラフ」ではなく明示的な失敗に** — tree-sitter クエリがサポートすべき grammar に対してコンパイルに失敗すると（将来の grammar 更新でのノード型改名など）、`run_query` が例外を送出し、該当ファイルは静かに 0 件抽出される代わりに `ExtractionFailure` として記録されます。0.6.6 の上限ピン + 「すべてのクエリが、サポートを宣言したすべての grammar に対してコンパイルされる」テストと合わせ、ドリフトが 3 つの独立した方法で検出されます。
- **`.codebeaconignore` の単一の `!` 否定が、もはやツリー全体の走査を強制しない** — どこかにある否定ルール 1 つがディレクトリ枝刈りを*全体的に*無効化していたため、その否定が中で何も復活させられない場合でも、スキャナはすべての除外ディレクトリ（`node_modules`、`build` など）へ降りていました。いまや無視されたディレクトリは、否定が実際に*その下*のファイルを再包含しうる場合にのみ走査され、無関係な `!` ルールはコストになりません。
- **ignore glob を一度だけコンパイル** — gitignore 形式のマッチャは、パス検査ごとに正規表現を再構築する代わりに、パターンごとにコンパイル済み正規表現をメモ化します（大きな ignore ファイルを持つ深いツリーでの探索が高速化）。意味は不変です。

---

## 0.6.6 の新機能

アップストリーム v0.8.37–v0.8.40（および #1362 までの報告 issue）の graphify パリティ監査: 32 候補を「検証してから敵対的に反証する」方式で精査し、**実バグ 6 件**を確定しました。要点 — フレームワーク抽出器 3 つが静かに*何も*生成していませんでした。

- **TypeScript の Express/Koa/Fastify アプリがルートを抽出するように** — `express.scm` が JavaScript のクラス名ノード型をハードコードしており、これは TypeScript grammar では「Impossible pattern」となるため、クエリ全体がコンパイルに失敗し、そのエラーが握りつぶされていました: **TS の Express アプリはルート 0 件**。（JavaScript アプリは正常で、テストフィクスチャが `.js` のみだったため見過ごされていました。）同じ原因が `vue.scm` にもありました（素の `<script>` の Vue SFC → コンポーネント 0 件）。両者とも JS・TS の双方でコンパイルされる grammar 中立なノードワイルドカードに修正しました。
- **Spring プロジェクトの Kotlin ファイルがエラーを出さないように** — `spring_boot.scm` は Java grammar のクエリですが Kotlin に対して実行が許可されており、`Invalid node type: marker_annotation` を出してすべての `.kt` ファイルを捨てていました。いまや Kotlin はきれいに除外されます（Kotlin Spring Boot には専用クエリが必要）。
- **tree-sitter grammar に上限ピンを追加** — `pyproject.toml` が grammar を上限なし（`>=0.23`）でピンしていたため、AST ノード型を改名する将来の grammar リリースがクエリを静かに再び壊しうる状態でした。いまやすべての grammar に互換範囲の上限があり、出荷されるすべての `.scm` が、サポートを宣言したすべての grammar に対してコンパイルされることを検証する新しいテストを追加しました。
- **抽出キャッシュをバージョン管理** — codebeacon のアップグレード後、変更のないファイルに対して増分 `--update` が*旧*バージョンの抽出結果を再利用しうる状態でした（コンテンツハッシュは抽出器自体の変更を検出できません）。キャッシュには codebeacon バージョンが刻印され、不一致時に破棄されます。
- **アクセント付き / 非 ASCII 名が macOS で解決される** — `codebeacon query` / `path` / MCP と `affected` がラベルとパスを Unicode NFC 正規化するようになり、macOS のファイル名からコピーした名前（NFD で保存）がグラフ内の NFC ラベルに一致します（例: `Auditoría`）。
- さらに: 破損した `cache.json` を静かにリセットして上書きする代わりに、バックアップして再構築します。

---

## 0.6.5 の新機能

`codebeacon upgrade` がどの環境でも動作するようになりました — 従来は通常の pip インストールを前提としており、そうでないマシンでは何もせずに静かに失敗していました。

- **インストールマネージャの自動検出** — upgrade コマンドが codebeacon のインストール方法を検出し、対応するツールを実行します: pip なら `pip install --upgrade`、pipx なら `pipx upgrade codebeacon`、uv なら `uv tool upgrade codebeacon`。pipx/uv tool の venv には `pip` モジュールが*存在しない*ため、従来の無条件な `python -m pip` 呼び出しは何もできずに失敗していました。
- **アップグレード検証** — アップグレード後、新しいインタープリタでインストール済みバージョンを再読込し `0.6.4 -> 0.6.5` のように報告します。バージョンが変わっていないのに PyPI に新しいリリースがある場合は、偽の「Upgrade complete」ではなく、PATH 上の `codebeacon` が別の Python 環境のものかもしれないと警告します。
- **対処可能な失敗メッセージ** — pip のない環境では実行すべき正確なコマンドを表示し、PEP 668 `externally-managed-environment` の拒否には生の pip エラーの代わりに解決策（pipx または virtualenv）を説明します。実行時には現在のバージョンと PyPI の最新バージョンも併記します。

---

## 0.6.4 の新機能

Deep-dive のクリーンアップ — 出力が探す場所に置かれるようになり、47 プロジェクトのワークスペースで検証中に見つかったサイレントなデータ損失バグ 2 件を修正。

- **Deep-dive はちょうど二つのレベルにのみ書き込む** — 各*リポジトリルート*（自身の `.git` または `codebeacon.yaml` を持つディレクトリ）と*スキャンルート*です。モノレポのフレームワークフォルダ（`mono/landing`、`mono/server`）がそれぞれ `.codebeacon/` + CLAUDE.md を抱え込むことはなくなり、結合グラフは `mono/.codebeacon/` に置かれ、スキャンルートがワークスペース全体のグラフを持つため、どのプロジェクトも一箇所から見つけられます。モノレポの*内部*で deep-dive を実行すると、サブフォルダごとに一つずつではなく単一のルート出力が生成されます。
- **キャッシュキーがフレームワークで名前空間化** — リポジトリグループは一つのキャッシュを共有しますが、親プロジェクトがネストしたプロジェクトのファイルを先に走査すると（`desktop/src-tauri` の上を sveltekit として歩く `desktop/`）、空の結果でキャッシュを汚染し、ネストしたプロジェクト（tauri）がそれを再利用して、自身の route とエンティティをすべて黙って失っていました。
- **文法ロードの競合を修正** — キャッシュされていない tree-sitter 文法に並列の抽出ワーカー二つが同時に到達すると、それぞれが自前の `Language` インスタンスを構築し、負けたスレッドのファイルはアイデンティティチェックに失敗して**何も**抽出されませんでした — 警告も失敗記録もなく、大規模スキャンで数ファイルの route がランダムに丸ごと欠落するだけでした。初回ロードは単一の共有インスタンスにロックされるようになりました（連続 20 回のフルスキャンで安定を確認済み）。

---

## 0.6.3 の新機能

バグ修正リリース — graphify-parity 監査（上流 6 月 3–10 日）に codebeacon 自身のコードの独立監査を加えた **16 件の修正**。47 プロジェクトの `--deep-dive` ワークスペーススキャン（5,226 ノード / 8,715 エッジ）でエンドツーエンド検証済み。

- **Git フックがどこでも発火** — post-commit 再ビルドフックがインストール時の Python インタープリタをスクリプトに固定し、`nohup` の代わりに `subprocess` でデタッチするため、GUI の git クライアント（Sublime Merge、GitKraken）、CI ランナー、Windows といった、`codebeacon` ランチャーが `PATH` に無く旧フックが黙って何もしなかった環境でも動作します。`codebeacon hook install` を再実行すると修正が反映され、merge driver も同じ方式で固定されます。
- **コメントアウトされた JS/TS import がエッジを作らない** — バレル re-export と `require()` の正規表現パスが、先に `//` と `/* */` コメントを（文字列リテラルを認識した上で）除去します。コメントアウトされた `export * from './legacy'` がファントムエッジと偽の import 循環を生んでいました。
- **`from pkg import name` が本来のターゲットに結び付く（Python）** — import 抽出器が import された名前を捕捉するようになり、`from auth.services import UserService` は `UserService` ノードへ、`from src.services import enricher` はサブモジュールへリンクします。従来はモジュールパスの最終セグメントしか試さず、テストファイルがグラフから切り離されていました。エイリアス（`import x as y`）は真のシンボル名に解決されます。
- **「High-Impact Files」が本当に high-impact に** — ハブランキング（CLAUDE.md、`analyze`）がエッジの `source_file`（常に import する側）経由で import の*ファンアウト*を数えていたため、エントリポイントがノード単位で水増しされたカウント（60 ファイルのリポジトリで「imported by 392 files」）で本物の共有モジュールを押しのけていました。両方のコピーが、import されるファイルごとに重複しない import 元ファイル数を数えるようになりました。
- **DI `injects` エッジが実ファイルパスを持つ** — 解決済みの dependency-injection エッジが `source_file` にグラフノード ID（`proj::Name`）を刻んでいましたが、ソースノードの実際のファイルを持つようになりました。
- **Ktor のネストした route プレフィックスが連結される** — `route("/api") { route("/v1") { get("/users") } }` が外側のプレフィックスをすべて落とす代わりに `/api/v1/users` を抽出します。
- **同一パスのルートが両方マッチ** — 二つのサービスが同じ URL を公開する場合（gateway + upstream）、`calls_api` エンリッチメントが最後の一つだけを黙って残すことはなくなりました。
- **設定がスパースな YAML を許容** — `output:` / `wave:` / `semantic:` を空のままにしても `AttributeError` でクラッシュしません。`projects:` 配下の裸の `-` は `TypeError` ではなく明確な設定エラーになります。
- **言語検出が vendored ディレクトリをスキップ** — フォールバックの言語投票が `node_modules` / `.git` / `dist` を除外するため、vendored な JS を含む Python リポジトリが *javascript* と判定されません（discovery が数万の vendored ファイルをクロールすることもなくなりました）。
- **wiki リンクがファイルと一致** — リンク先がジェネレータの書き出しと完全に同じファイル名変換を使うため、スペース、`#`、括弧、ジェネリクスを含むラベルがデッドリンクを生まなくなりました。
- さらに: 決定的なエンリッチメントエッジ順序、`None` ラベルのビルドガード、スレッドセーフな抽出キャッシュ、FastAPI `Depends()` のゴースト参照の除去、Obsidian サービスフォルダ名のバイト上限。

---

## 0.6.2 の新機能

- **決定的なコミュニティ ID** — 同サイズのコミュニティがパーティショナーの列挙順で番号付けされ、no-op の再スキャンで `beacon.json` の 77–88 % が入れ替わっていました。同一のグルーピングは常に同一の ID を得るようになりました。
- **ノートファイル名のバイト上限** — 85 文字超の CJK クラス名がファイルシステムの 255 バイト制限を超え、`ENAMETOOLONG` で wiki / Obsidian エクスポート全体をクラッシュさせていました。UTF-8 200 バイトで上限を設け、衝突安全なハッシュサフィックスを付与します。
- **FastAPI / Laravel / ASP.NET の DI エッジを復旧** — 解決済みの `Depends()` / `bind()` / `AddScoped<>` 参照がファイルパスでキー付けされる一方、ノードはプロジェクトでキー付けされていたため、エッジが黙って捨てられていました。最終ノード ID へ再マップされます。
- **インターフェース → 実装の DI を復活** — `implements`/`extends` メタデータをどの抽出器も埋めておらず、インターフェース型の注入が一切解決されませんでした。Spring、ASP.NET、NestJS、Angular で配線されるようになりました。

---

## 0.6.1 の新機能

パッチリリース — 抽出の正確性と再現可能な出力。

- **6 つのフレームワーク抽出器を復旧** — `laravel`・`angular`・`aspnet`・`actix`・`ktor`・`vapor` の tree-sitter クエリが現行の文法バージョンとずれて **何も抽出しない** 状態でした（クエリのコンパイルに失敗し、そのエラーが警告として握り潰されていた）。6 つすべてを同梱の文法でコンパイル・抽出できるよう修正し（Laravel の `scope:`/`name:` フィールド、Angular の `export class` デコレータ、ASP.NET の `invocation_expression` フィールド、Actix の兄弟ノードアンカー、Kotlin 1.x のノード改名、Swift 0.0.1 のノードセット）、再び黙って壊れないよう各々に回帰テストを追加しました。
- **再現可能な `beacon.json`** — シリアライズ前にノードの `source_file` パスを各プロジェクトルート相対に書き換えるため、同じコミットを別マシンでスキャンしてもバイト単位で同一のグラフが得られます（diff に絶対パスの揺れが出ない）。
- **`affected` の過剰報告を修正** — 変更ファイルの seed マッチングをパスセグメント単位に整合させ、`src/user.py` が `foosrc/user.py` のような無関係なノードを巻き込まないようにしました。
- **`semantic-apply` のクラッシュ修正** — アーカイブ/移行済み JSONL エッジの `confidence_score: null` が `TypeError` で実行を中断させる問題を解消し、パイプラインの他部分と同様に安全な既定値へ補正します。
- **NetworkX 3.6 前方互換** — `beacon.json` を `edges="links"` キー明示で書き出し、上流の既定値変更がディスク形式を黙って変えないようにしました。MCP サーバーも同じ互換ローダーを使用します。
- **Obsidian ボルトの整理** — 古いノートの掃除がボルト全体（ルート＋ネスト）を対象にし、言語間 import フィルタはファイル名サフィックスではなくノードの実際のソース言語を基準に動作します。
- **gitignore セマンティクス** — `build/*.js` のようなアンカー付きパターンで `*` が `/` を跨がないよう修正し、ネストしたファイルが誤って無視されないようにしました。
- **Next.js App Router** — JS ベースの `page.js` / `page.jsx` ルートも検出するようになりました（従来は `.ts` / `.tsx` のみ）。
- **DI 帰属の修正** — FastAPI の `Depends()` と Angular のコンストラクタ注入を、ファイル内の最初/最後ではなくバイト範囲で囲む関数・クラスに正しく帰属させます。Razor の `@using` は重複エッジを生成しなくなりました。

---

## 0.6.0 の新機能

- **`codebeacon affected`** — 変更されたファイル一覧（または `--base <ref>` で git diff）を受け取り、その影響範囲にあるグラフノードをすべて出力。CI のリスクスコアリングや PR レビュー向け。
- **`.NET` プロジェクトファイル** — `.sln`, `.csproj`, `.fsproj`, `.vbproj`, `.razor`, `.cshtml` を解析。`<ProjectReference>` / `<PackageReference>` がグラフエッジとなり、Razor `@inherits` / `@inject` / `@using` が Blazor ページを背後の型に接続。
- **JS/TS バレル re-export** — `export { X } from './mod'`, `export * from './mod'` が明示的な `re_exports` エッジを生成。Next.js / モノレポのバレルが import 0 と表示されなくなりました。
- **`--exclude PATTERN` フラグ**（`scan` / `sync` 両方）+ `.codebeaconignore` がない場合は `.gitignore` を自動フォールバック。
- **`codebeacon install --project [PATH]`** — `~/.claude/` ではなく `<PATH>/.claude/` に `/codebeacon` スキルをインストール。チームが SKILL.md のバージョンをリポジトリに固定できます。
- **wiki の自動クリーンアップ** — `--update` 実行時、グラフに存在しなくなった `wiki/<project>/{controllers,services,entities,components}/*.md` を自動削除。
- **明示的削除時は shrink-guard をバイパス** — `--update` モードでキャッシュが既に削除を反映している場合、より小さい `beacon.json` の書き込みを拒否しなくなりました。silent corruption へのガードは維持。
- **Cross-file 宣言の union マージ** — Swift `extension Foo`, C# partial class, Ruby reopened class の `fields` / `methods` が最後の書き込みで上書きされず、単一の canonical ノードにマージされます。
- **query の強化** — `BeaconIndex` が `casefold()` を使うので、ドイツ語 `ß`、トルコ語 `i/İ`、ギリシャ語 `σ/ς`、CJK ラベルのマッチが正しく動作。
- **セマンティックコンテキストの強化** — 各タスクチャンクにグラフの caller / callee が `neighbors` として同梱され、LLM が実在ノードラベルから離れにくくなりました。`SKILL.md` に **Step 0 — Constrained query expansion** を追加し、`/codebeacon query` フローが phantom トークンを発明できないよう明示。
- **`semantic-apply` zero-yield ガード** — すべてのチャンクが 0 エッジでアーカイブされた場合、CLI が exit 1 で終了し、CI が LLM のサイレント失敗を検出できます。
- **ArkTS (`.ets`) と worktree 安全性** — `.ets` を収集、ネストされた `worktrees/` ディレクトリをスキップし、linked worktree の重複インデックスを防止。

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
