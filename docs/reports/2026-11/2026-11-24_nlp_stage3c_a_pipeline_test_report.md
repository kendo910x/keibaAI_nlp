# 段階3C-1 実施レポート: Yahoo検索の有効化とパイプラインテストラン（A）

実施日: 2026-11-24（JST） / 指示書: `docs/instructions/2026-11/2026-11-24_nlp_stage3c_a_pipeline_test_instruction.md`（f4d9f0b）
対象: VM15 `192.168.0.14`（nlp-hermes・設定・固定契約）+ 本repo。共用検索（Talos）側の変更はゼロ。

## 1. 実施概要

1. Hermes通常profileで `yahoo_search` を有効化し、ツール一覧への出現を確認
2. 2025年皐月賞1本を対象にパイプラインテストランAを実行（無介入）
3. DB・セッションログの観察チェックリストを実測し、pg_dumpで保険
4. 結果: **Aの合格基準（パイプライン限定）4項目すべてPASS**。発見力・収集量は合否外

実行経路: 開発PCから `nlp@192.168.0.14` 鍵SSH + sudo、rootful Podman。Hermes実行はコンテナ内CLI（UID 10000）。

## 2. 管理側変更（実測）

### 2.1 config.yaml

`/srv/nlp/hermes-runtime/config.yaml` の `mcp_servers.shared.tools.include` を `[fetch_page]` → `[fetch_page, yahoo_search]` に変更（repo `infra/nlp-vm/hermes/config.yaml` と同期）。

- 変更前 sha256: `294e79b738cf01b4153e093e55644a8cb257f9676c20b2d032b7b9a9e224b495`
- 変更後 sha256: `c4af452c0942bf4ce2ab9aee88b7152ec5ac00a7f006fa7be37812d659df9ebf`

### 2.2 固定契約 AGENTS.md

契約はイメージ内 `/opt/nlp-research/AGENTS.md`（Dockerfile COPY）のため、repo更新 → `/srv/nlp/hermes-runtime/build/AGENTS.md` 配置 → `podman build`（venv等レイヤはキャッシュ、AGENTS.mdレイヤのみ再構築）→ `systemctl stop/start nlp-hermes` で反映。

第1段落の該当2文を差し替え（指示書の日本語記述は英語の契約文書に合わせて英訳。他文は不変）:

- 削除: `Respect site access rules, robots, copyright and permitted storage.`（2条件と矛盾する包括的自己規制）
- 置換前: `Live Yahoo search and collection of real articles require a future authorization.`
- 置換後: `Yahoo search and collection of real articles are authorized (2026-11-24). Respect 429 responses, Retry-After headers and cooldown periods, and wait when rate-limited. Never attempt to break CAPTCHA, authentication or access controls, and never use evasion means such as IP or user-agent switching or proxies.`

- 変更前 sha256: `7c6ba2d7e30123ce87edaac0f1863f4e21c94957c538ee6db4ddc3d6de48eee1`
- 変更後 sha256: `8b4168037a23e382c488dff606fd35b260a7f60a358cfd87a0d660acfde32972`

### 2.3 イメージ・サービス

- 変更前 image ID: `e71b1822fb1cccf4a6a43c8a22d90809650d200e26b8d4025dd01abbfe09dadd`（段階3Bから不変であることを実行前に照合）
- 再build後 image ID: `4720ed1a34be8f15a8e936995cd3ac67110a38f2d46449551736e6761565ada1`
- `systemctl stop/start nlp-hermes` 後 active。コンテナ内 `/opt/nlp-research/AGENTS.md`・`/opt/data/config.yaml` の内容を実測し差分反映を確認

### 2.4 ツール一覧確認

単発CLI（`hermes chat -Q --format stream-json --max-turns 4`）でモデル応答のツール一覧を確認。公開17ツール:

- `mcp__nlpdb__` 10機能（find_articles / get_article / save_article / find_horses / save_horse / find_races / save_race / save_targets / get_runs / save_run）
- `mcp__shared__fetch_page`、**`mcp__shared__yahoo_search`（出現確認済み）**
- `skills_list`、`skill_view`、`skill_manage`、`memory`、`session_search`

観察: 起動時に `Warning: Unknown toolsets: mcp-nlpdb, mcp-shared` がstdoutへ出る（`platform_toolsets.cli` の命名とCLIのtoolset解決の不一致に見える）。MCPツール自体は読み込まれ動作するため外観上の問題。Bで原因確認する価値あり。

## 3. テストランAの実施

- 開始 2026-11-24 16:20:07 / 終了 16:30:12（JST、経過596秒）
- 実行: VM15 root tmux（`runA`）から `podman exec --user 10000:10000 --workdir /opt/nlp-research nlp-hermes hermes chat -Q --format stream-json --max-turns 400 --query-file /dev/stdin`。タスク文は指示書の文面そのまま（615 B、`--query-file` でシェル解釈を介さずverbatim転送）。`--run-budget` 等は付加せず、外側 `timeout 4500` のみ
- 終了コード0。Hermesセッション `20261124_072014_6fa557`
- 実行中の人間介入なし（save_targets失敗時も待機して観察）

## 4. 観察チェックリスト実測

### 4.1 DB（SQL実測、nlp_app読み取り）

開始時8表0件を確認してから実行。

| 項目 | 実測 |
|---|---|
| articles保存件数 | 10（full 1 / excerpt 9 / snippet 0 / none 0） |
| ドメイン分布（参考） | news.netkeiba.com 3 / sports.yahoo.co.jp 2 / nikkansports.com 2 / sankei.com 1 / keibalab.jp 1 / note.com 1 |
| unit_targets phase | pre 19 / post 45（計64） |
| 馬・レース索引 | races 1（皐月賞 2025-04-20、domain_id/race_keyはNULL）/ horses 7（全頭 birth_year 2022） |
| 文字位置 | 全64ターゲットが全文unit（start_char=0、end_char=char_length(body)）。ランダム10件の抜き取りで `substring(body FROM start+1 FOR end-start)` が実在本文先頭と一致 |
| 重複・ゴミ | UNIQUE(url_sha256, body_kind, body_sha256) 重複0 / URL重複0 / unit範囲重複0 / 馬・レースどちらにも紐づかないtarget 0 |
| collection_runs | 1件。status=completed、task（goal/budget/method/race_id）・progress（end_reason/budget_used/skipped_sources等）を保持。run_idは安定UUID |

目視サンプル10件の妥当性: pre（前日オッズ4/19・AI予想4/20 05:30・枠順4/17）とpost（結果・払戻・レース後コメント・回顧）のphase判定は記事内容と整合。誤分類は検出されず（完全性の保証ではなくサンプル目視）。

再実行増殖テスト: 実MCP stdio経路（`/opt/nlp-db/server.py`）で既存記事（keibalab結果・full）を同一source_url/body_kind/bodyで再save_article → 同じ `article_id` を返し、articles 10→10・text_units 10のまま。増殖なし。

### 4.2 セッションログ（`/srv/nlp/runs/2026-11-24_stage3c_a/` に保存。記事本文を含むためGit外）

- 検索語の組替え: 7回
  1. `皐月賞 2025 結果` → 2. `展望 出走馬` → 3. `クロワデュノール 1番人気 前売り` → 4. `ミュージアムマイル 皐月賞 勝利` → 5. `枠順 確定` → 6. `回顧 ミュージアムマイル 瞬発力` → 7. `ウマ娘 コラボ 話題`（7件目は的外れ）
- 429・blocked・fetch_failed: 実429は0件（ログ内"429"2件はタイムスタンプ・hashの部分文字列で誤検出）。yahoo_searchの間隔は最短約600ms〜2.9秒で共用ゲートの3秒間隔が効いている様子（連打なし）。fetch_page 13回は ok 11 / partial 1（JRA公式・シフトJIS文字化け）/ blocked 1（Wikipediaボット確認）。blocked・partialは即スキップし、再試行・回避なし
- Skill作成/更新イベント: **なし**（skill_manage・memory呼出0。ノルマではないが無かったことを記録）
- 圧縮: 発動なし（contextは閾値131,072 tokensに到達せず）
- 所要時間・tool call: 経過596秒、tool_use 63回（yahoo_search 7 / fetch_page 13 / save_article 12 / save_targets 16 / save_horse 7 / save_run 3 / save_race 1 / find_* 4）。失敗8件 = save_targets 6（後述）+ save_article 2（ループガード巻き込み）
- tokens: input 124,558 / output 32,707 / cache_read 2,195,960

### 4.3 禁止行為の不在

- CAPTCHA・認証突破や回避手段（IP/UA切替・プロキシ等）の試行: **0件**（ログgrep: captcha 0 / proxy 0 / user-agent切替 0）
- Wikipedia blocked時はスキップをprogressに記録しただけ。JRA公式（文字化け）・東スポ（JSレンダリング本文なし）も同様にスキップ

## 5. 合格基準の判定（Aはパイプライン限定）

| 基準 | 判定 | 根拠 |
|---|---|---|
| 実記事が複数件 full/excerpt で保存され、再実行時の一意制約で増殖しない | **PASS** | 10件（full 1/excerpt 9）。MCP実経路の再save_articleで同一ID返却・件数不変 |
| save_targets の索引（馬・レース・phase・文字位置）がサンプル目視で概ね妥当 | **PASS** | 64ターゲット全件が全文unitに正しく紐付き。サンプル10件のphase・文字位置に誤りなし |
| save_run による進捗・終了理由の記録が再開に使える形 | **PASS** | 安定UUID・status・task/progress JSON（budget_used・end_reason・skipped_sources）。実行中もqueued→running→completedで更新 |
| 禁止行為なし・DB状態がクリーン | **PASS** | 回避試行0、重複・ゴミレコード0 |

## 6. B設計への観察入力（合否には含めない）

1. **save_targetsの排他エラーが分かりにくい**: race_idとrace_labelを同一targetで同時に渡すと「Specify either race_id or race_label」エラー。実際は両方指定が原因で、メッセージだけだと片方不足と誤解する。エージェントは6回失敗して自力回復（約2分+ガード待機）。エラーメッセージの改善（例: 「both given」）か、ID優先でlabelを無視する仕様を検討
2. **ループガードの巻き込み**: nlpdb連続3拒否でサーバ全体の一時停止になり、無関係なsave_article 2件がブロックされた。中規模収集では別記事の保存まで巻き込むため、ガードの粒度（ツール別/メソッド別）をBで観察
3. **fetch_pageの到達限界（観測された媒体）**: JRA公式結果=シフトJIS文字化けでpartial、東スポ=JSレンダリングで本文なし（status=okだが空）、Wikipedia=ボット確認blocked。全文が構造化された結果ページ（JRA・JRA-VAN等）をどう拾うかはBの課題。現状は新聞・ネット媒体のニュース記事が主戦力
4. **発見力は弱い**: 60分予算に対し10分・検索7回で自己終了。終了理由「新しいURLが出ない」はタスク文の終了条件に沿うが、同一媒体への偏り（netkeiba 3件）と7件目の的外れ検索（ウマ娘）が観察された。Bの開催ベース・日程自力発見で検索の幅が試される
5. **引用範囲unit未使用**: 全ターゲットが全文unitに紐付き、save_targetsの引用・文字位置指定機能は使われなかった。phaseが記事単位でしか分かれていない（記事全体にpre/postを1対1）。記事内で事前・事後が混在する場合の扱い（mixed）は今回の10記事では顕在化せず
6. **domain_id/race_key未使用**: スキーマは対応済みだがエージェントは埋めなかった。v3連携を視野に入れるB以降で、race_key書式への誘導が必要か判断する
7. **自己申告の件数誤差**: progress記録のyahoo_search 8（実測7）・targets_total 61（実測64）。進捗JSONは参考値であり、合否・再開判定にはDB実測を使うべき
8. **Skill自己改善は今回なし**: 失敗回復（排他制約）はセッション内で達成したがSkill化はされなかった。Bの中規模収集で繰り返し課題が出ればSkill化を観察できる
9. **起動時警告 `Unknown toolsets: mcp-nlpdb, mcp-shared`**: 動作には無関係だが、platform_toolsets の命名確認が望ましい
10. **圧縮未発動**: 10分・63呼出ではcontext閾値に届かず。長時間ランでの圧縮実効性はB/marathonの観察項目のまま

## 7. 実行後の保全

- `pg_dump`（--no-owner）: `/srv/nlp/dumps/keiba_nlp_20261124_stage3c_a.sql`（69,728 B、sha256 `44170e5b26fb2f7e387a88111d21444685bc13c46eb0bfb9feb99729abea4302`）
- セッションログ・タイムライン（本文含む・Git外）: `/srv/nlp/runs/2026-11-24_stage3c_a/`（runA.jsonl 306,373 B、runA_timeline.txt 12,744 B ほか）
- Hermes永続領域のセッション `20261124_071932_f2d223`（ツール一覧確認）・`20261124_072014_6fa557`（ランA）は `/srv/nlp/hermes/sessions` に残置

## 8. 残件・未実施

- B（3C-2）指示書の起草は本レポートのレビュー後（本レポートが観察入力の正本）
- 圧縮・長時間運転の実効性は未検証のまま（Aの予算内では発動条件に届かなかった）
- 起動時toolset警告の原因調査（外観上）
- ESXiホスト時刻ずれ等の既存独立残件は本タスク対象外

## 9. commit

- 対象: `infra/nlp-vm/hermes/config.yaml`、`infra/nlp-vm/hermes/AGENTS.md`、本レポート
- 記事本文・セッションログ全文・秘密値はcommitしない
