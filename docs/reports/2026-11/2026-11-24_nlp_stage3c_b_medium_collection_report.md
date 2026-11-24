# 段階3C-2 実施レポート: 中規模収集ラン（B）— 開催日程の自力発見と巡回

実施日: 2026-11-24（JST） / 指示書: `docs/instructions/2026-11/2026-11-24_nlp_stage3c_b_medium_collection_instruction.md`（add091c）
対象: VM15 `192.168.0.14`（nlp-hermes・server.py/targets.py）+ 本repo。共用検索（Talos）側の変更はゼロ。

## 0. 結論（先に）

- **§9の停止条件発動によりランBを途中停止**（経過約20.7分）。ループガードのnlpdb全体停止が2回発生（18:08頃46秒・18:09頃3秒、いずれもsave_targetsの排他エラー起因）
- 合格基準は **2・3・4・5がPASS、1（記事30件以上）は未達**。未達の原因は停止条件による早期停止（§6どおり過程分析を§7に記録）
- 日程自力発見・race_key場コード・Skill自己改善は実測で機能確認。**shared.3のJRA/NAR可読は回帰なし**（公式10 fetch、文字化け0）
- 運用上の過失（管理側）: 1回目の停止操作でpkillパターンが実コマンドラインと不一致（`python -P -c "...main()) chat -Q..."`）で殺し損ね、18:16〜18:24に収集が継続した。18:24:28に完全停止を確認（プロセス消滅・ログサイズ不変）。最終実測は完全停止後に行い、本レポートの数値はすべて停止後実測

## 1. 前提確認

- 共用検索shared.3を機能実測で確認: JRA皐月賞結果ページ（Shift_JIS）→ `charset: Shift_JIS` 復号可読、NARトップ（UTF-8）→ 可読。**文字化け回帰なし**（E4/E5動作）。VM15側のURL・設定変更ゼロ
- 前提として `/healthz` は status ok（image digestの直接照合はkubectl未設定のため、機能実測をもって代替）

## 2. 管理側変更（§3）

### 2.1 server.py docstring（race_key静的テーブル）

- `save_race`: race_key書式（`YYYYMMDD/<場コード>/<レース番号>`、schema CHECK）、domain_id規約（JRA/NAR、UNIQUE）、皐月賞例（`20250420/06/11`）、JRA場コード表（01札幌〜10小倉）、NAR場コード表（30門別〜61中京(NAR)）を追加
- `find_races`: 書式とdomain_id規約のみ追加（表なし）
- 反映実測（単発CLI）: 「中山と大井の場コード」の質問にモデルが **中山=06・大井=44** と正答（docstringがモデルへ到達）。MCP `list_tools` のdescription内でも場コード表・例を確認

### 2.2 targets.py 排他エラー文言

- 変更前: `Specify either {key} or {label}` → 変更後: `Both {key} and {label} were given. Keep only one of them.`（排他仕様・挙動は不変）
- 反映実測: race_id+race_label同時指定のsave_targetsで `Both race_id and race_label were given. Keep only one of them.` を受信（ロールバックされDB不変）
- `tests/contract.py` に新文言assertケースを1件追加（`Both race_id and race_label were given. Keep only one of them.`）。構文チェック（py_compile）PASS。**試験DB（keiba_nlp_stage2b_test）は3B回収済みで未再作成のため、contract.py本体の実行は未実施**（新文言自体は実MCP呼出で実測済み）

### 2.3 build・反映

- 変更前 image ID: `4720ed1a34be8f15a8e936995cd3ac67110a38f2d46449551736e6761565ada1`（3C-1終了時）
- 変更後 image ID: `643ee6bd141277a6172da756e793754e974df35c3ed7ee07b91030690cd8313d`
- build入力sha256: server.py `e3e3117b…` / targets.py `349b587f…`
- `systemctl stop/start nlp-hermes` 後 active。AGENTS.md・config.yamlは不変

### 2.4 起動時警告（§3.4任意・非ブロッキング）

`Unknown toolsets: mcp-nlpdb, mcp-shared` の発生箇所を特定: `hermes/agent/subagent_lifecycle.py:469`（platform_toolsetsの名称検証）と `model_tools.py:309`。`platform_toolsets.cli` の `mcp-nlpdb`/`mcp-shared` はtoolset登録名と一致しないが、MCPツールは `mcp_servers` 経由で正常読込（17ツール動作）。**外観上の問題で、config.yaml不変方針のため無修正**。マラソンで整理する価値あり

## 3. ランB実行記録

| 項目 | 実測 |
|---|---|
| 開始 | 18:03:48（tmux runB、`--max-turns 1200`、外側timeout 12600s、タスク文1,308 B verbatim、sha256 `b0ef319d…`） |
| 停止条件検出 | 18:14の定期観察でガード全体停止2回を確認（1回目 18:08頃46s・2回目 18:09頃3s）→ §9により停止判断 |
| 1次停止（不備） | 18:16 pkillパターン不一致で殺し損ね（下記）。この間収集継続 |
| 完全停止 | 18:24:28（`pkill -f "max-turns 1200"`、プロセス消滅・runB.jsonlサイズ不変を確認）。**実効経過20.7分** |
| runB.jsonl | 398,511 B（`/srv/nlp/runs/2026-11-24_stage3c_b/` に保全） |
| collection_runs B | `3c1f7d92-…` status=runningのまま保全（最終save_run 18:13:54。§9「進捗を保全」） |

運用教訓（管理側）: Hermes CLI実体のコマンドラインは `python -P -c "...'hermes'... main()) chat -Q ..."` であり、`pkill -f "hermes chat"` は不一致。停止確認はプロセス一覧とログサイズ不変の2点で行うこと。

## 4. 観察チェックリスト実測（§5、すべて停止後実測）

### 4.1 DB（SQL実測）

開始時（A終了後）: articles 10 / unit_targets 64 / races 1。停止後最終:

| 項目 | 実測 |
|---|---|
| 記事件数 | 20（B追加10。full 8 / excerpt 12 のうちB分は full 5・excerpt 5） |
| ドメイン分布 | 全体9。B追加記事のホスト: news.netkeiba.com 3 / nar.netkeiba.com 3 / radionikkei.jp 3 / jra-van.jp 1 / nikkansports 1（**B単体5ホスト**・netkeiba系2ホスト） |
| 2026年1〜3月カバーレース | **7**（日経新春杯1/18・クイーン賞2/11・フェブラリーS2/22・ダイオライト記念3/11・黒船賞3/24・マーチS3/29・高松宮記念3/29） |
| race_key記入率 | B作成レース7/7（100%）にdomain_id+race_key。サンプル5件目視: 日経新春杯/08京都・クイーン賞/43船橋・フェブS/05東京・ダイオライト/43船橋・黒船賞/54高知 — **場コード5件すべて正**（黒船賞のレース番号04はnar.netkeiba race_id `202654032404` の構造からの導出と整合） |
| phase分布 | post 78 / pre 27 / mixed 0（A観察5延续: mixed未使用） |
| unit | 全文20 + **部分範囲41**（Bは引用・範囲unitを多用。A観察5は改善方向） |
| 重複・ゴミ | UNIQUE重複0 / URL重複0 / unit範囲重複0 / 馬・レース未紐づきtarget 0 |
| 再実行増殖テスト | B記事1件（radionikkei full）をMCP実経路で再save_article → 同一ID・20→20件不変。**増殖なし** |

### 4.2 セッションログ

- **日程自力発見**: JRA/NAR公式fetch 10回（jra.go.jpトップ、replay/2026/g1.html、jyusyo.html、keiba.go.jpトップ、dirtgraderace/2026/racelist、gradedrace/schedule 等）。`site:jra.go.jp`/`site:keiba.go.jp` 検索も使用。403（/datafile/seiseki/g1/直、/funsite/）とJS主体ページ（keibaCalendar、dgtop）を回避して成功ページへ自力到達。台帳確定内容はsave_run progressに記録（JRA G1 2/22・3/29、NAR Jpn 8競走）→ **過程あり、PASS**
- **巡回**: yahoo_search 15回（日程系2・レース結果/展望系13）。fetch_page 28回: ok 17 / partial 1（jyusyo）/ blocked 4（JRA 403×2、routifyミラー403×2）/ error 2（keibaCalendar、dgtop）。**例示のYahoo競馬トップは未訪問**。自力発見サイト（例示外）: news.netkeiba.com、nar.netkeiba.com、radionikkei.jp、jra-van.jp、keibalab.jp、nikkansports.com、note.com、（到達したが不採用: sportsbull.jp=JS、blog.f-keiba.com=PDFのみ）
- **Skillイベント**: skill_manage 3回。1回目description 160字で失敗→2回目71字で失敗→3回目60字以内で**作成成功**（`nlpdb-keiba-article-collection`）。内容は実測と整合（公式カレンダーURL・403パス・iframe問題・場コード・バッチ注意）。memory呼出0
- **ループガード**: nlpdb全体停止 **2回**（46s・3s、save_targets排他起因）。以降の再発なし
- **429・blocked・fetch_failed**: 実429 0件（ログ内"429"5件はタイムスタンプ・UUIDの部分一致）。blocked/errorは即スキップしprogressに記録。回避試行なし
- **圧縮**: 発動0（20分ではcontext閾値未達。長時間ランの実効性は未検証のまま）
- **統計**: tool_use 113（fetch_page 28 / yahoo_search 15 / save_targets 17 / save_horse 23 / save_article 10 / save_race 7 / skill_manage 3 / save_run 2 / find_* 6 / get_runs 1 / skills_list 1）。失敗: save_targets 7（すべて排他。新文言でも同一ミスを7回繰り返した後自前で見切り）+ skill_manage 2（description長）
- **自己申告乖離**: progress記録（18:13時点）articles_saved 6・yahoo 9・fetch 12に対し実測10・15・28。**進捗JSONは参考値、会計はDB実測**（A観察7延续）

### 4.3 禁止行為の不在

CAPTCHA 0・UA切替0・プロキシ利用0。観察事項: 検索結果に現れた第三者ミラーURL（aliyuncsのroutifyプロキシ）を2回fetch（いずれ403。うち1回は署名をでっち上げたURLを自作して403）。原文サイトのアクセス制御突破ではなく失敗・反復なしだが、**検索結果のミラー/キャッシュは出典独立性の観点で注意**

## 5. 合格基準判定（§6）

| # | 基準 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 記事30件以上・5ドメイン以上・2026年1〜3月レース5以上 | **未達** | B追加10件(<30) / B単体5ホスト(達成) / レース7(達成)。原因は§9停止による早期打ち切り（下記§6分析） |
| 2 | 日程自力発見の過程がログに存在 | **PASS** | 公式fetch10回+site:検索+progressに台帳 |
| 3 | race_key 50%以上・サンプル5件目視誤りなし | **PASS** | 7/7記入、5件場コードすべて正 |
| 4 | Skill作成/更新1件以上・内容が実測と整合 | **PASS** | 1件作成（2回の失敗から自己修正）、内容は実測URL・403・場コードと一致 |
| 5 | 禁止行為なし・DBクリーン・再実行で増殖なし | **PASS** | 禁止0・重複0・再save同一ID不変 |

総合: **停止条件発動による途中停止で合否判定は「部分達成（1未達）」**。§6どおり過程分析を下記に記録し、マラソン設計への入力とする。

## 6. 未達原因の過程分析（マラソン設計への観察入力）

1. **save_targetsの排他は依然LLMトラップ**: 文言改善後も同一ミス7回（race_id+race_labelを「念のため」両方埋める癖）。文言だけでは防げない。マラソンでは (a) ID優先でlabelを黙って無視する仕様変更、または (b) label→IDの自動解決、のいずれかを検討（仕様変更は別承認）
2. **ループガード粒度**: 単一ツールの引数エラーがnlpdb全体（10ツール）の停止を招く。Bでは2回で停止条件に到達。ガードをツール別・メソッド別にしないと、マラソンの長時間運転では局所ミスが収集全体を止める
3. **停止条件そのものの設計**: 全体停止2回という閾値は短時間に到達し得る（Bでは開始6分で2回）。マラソンでは「ガード停止回数」ではなく「同一原因の反復」や「正味進捗の停止」を停止条件にすると誤停止が減る
4. **発見力は向上**: A（検索7・1媒体偏り）に対しBは公式カレンダー起点→site:検索→NAR含む7レース・5ホスト。例示外サイト（radionikkei・nar.netkeiba・jra-van）を自力発見。日程自力発見は実用可
5. **収集速度の実測**: 20.7分で記事10件・target 41（B分）。30件には単純換算で60分+。ガード停止・失敗リトライの overhead を見ると、排他問題解決がスループット改善の最優先
6. **mixed phase未使用**: 記事単位のpre/postのみ。部分unit引用は使われるようになった（41 unit）が、同一記事内の事前/事後混在のmixed判定は未観察
7. **自己申告の乖離**: 進捗JSONは遅延・過少（18:13で6件、実10件）。再開・監査はDB実測が正本
8. **検索結果のミラーURL**: サードパーティキャッシュ（routify等）が混入。本文取得できても転載・出典独立性の問題。Skill/契約での扱いをマラソンで決める
9. **圧縮は未発動**: 20分・113呼出では閾値未達。長時間ラン観察はマラソン継続
10. **管理側運用**: 停止操作は実コマンドラインに一致するパターン+プロセス一覧+ログ不変の3点確認（本ランの過失）

## 7. 実行後の保全

- pg_dump: `/srv/nlp/dumps/keiba_nlp_20261124_stage3c_b.sql`（112,809 B、sha256 `12f011d1507daf2011f85bed485be647b35ad1a873edf4082d57001ecf5a3d18`）
- セッションログ・タイムライン・DB詳細ダンプ（本文含む・Git外）: `/srv/nlp/runs/2026-11-24_stage3c_b/`（runB.jsonl 398,511 B、runB_timeline.txt、db_detail.txt、taskB.txt）
- Hermes Skill `nlpdb-keiba-article-collection` はVM15永続領域に残置（全文は本レポートに転記しない）
- collection_runs B（`3c1f7d92-…`）はstatus=runningのまま保全。次ランの再開判断材料として残す

## 8. 残件

- contract.py本体の実行（試験DB再作成が必要。3B手順で可能）— 新文言assertは未実行
- 合格基準1未達（記事30件）。排他問題（§6-1/2）を解消した3C-2rまたは3C-3での再挑戦を推奨
- 圧縮・長時間運転の実効性観察（マラソン）
- 起動時toolset警告の整理（外観上）
- ESXiホスト時刻ずれ等の既存独立残件は対象外

## 9. commit

- 対象: `infra/nlp-vm/hermes/server.py`、`infra/nlp-vm/hermes/targets.py`、`infra/nlp-vm/hermes/tests/contract.py`、本レポート
- 記事本文・セッションログ全文・Skill全文・秘密値はcommitしない
