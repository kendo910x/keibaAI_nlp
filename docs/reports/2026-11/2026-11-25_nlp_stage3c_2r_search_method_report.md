# 段階3C-2r 実施・検証レポート: 検索方法の発見と1月JRA重賞収集（B2）

作成日: 2026-11-25（JST）
指示書: `docs/instructions/2026-11/2026-11-24_nlp_stage3c_2r_search_method_instruction.md`（commit 277476e）
対象環境: VM15 `192.168.0.14`（nlp-hermes・nlp-postgres・共用検索Talos）/ 本repo main
関連commit: 管理側変更 `ada67bb`（targets.py・contract.py）

## 0. 結論（先出し）

- **B2不合格**（§5 基準1・2未達）。マラソン指示書の起草は行わない（ユーザー決定どおり）。
- 未達の直接原因は収集手法の失敗ではなく、**ランB2が経過約21分でコンテキスト超過クラッシュしたこと**。Hermesの自動圧縮は発動したが「縮小しきれなかった」と報告してセッションが終了した（§9残件「圧縮実効性」の初実測＝**発動したが不足**）。
- 手法そのものは有効に動作した: 相0の検索方法発見（5.9分で完了・Skill記録）、台帳の自力導出（JRA公式と完全一致9競走）、**排他エラー0件**（仕様変更の実効確認）、pre比率80%、重複・増殖なし。
- 次の blocker は **セッション寿命（コンテキスト管理）**。マラソン設計の最優先入力（§7）。

## 1. 管理側変更（指示書§2）

### 1.1 targets.py 排他仕様変更（ID優先）

`save_targets` の排他チェックを raise → **label側をNone解決して続行**に変更（commit ada67bb）。

```diff
                 if values[key] is not None and values[label] is not None:
-                    raise ValueError(f"Both {key} and {label} were given. Keep only one of them.")
+                    values[label] = None
```

docstring に `When both an id and a label are given for one entity, the id wins and the label is ignored.` を追記。label単独・id単独・どちらも無しの挙動とスキーマCHECKは不変。

### 1.2 build・反映（§2.3）

- image before: `643ee6bd141277a6172da756e793754e974df35c3ed7ee07b91030690cd8313d`
- 配置: `/srv/nlp/hermes-runtime/build/targets.py`（sha256 `7d15b8023355f8bd261105a46628e7df90c466623256773c96a9744ffeca3a4c`）→ `podman build` → `systemctl stop/start nlp-hermes`（active確認）
- image after: `3a1ef55d1954d4f99dd97095d0af5933314d240e5961cd98f4159a2244ef4dd7`
- AGENTS.md・config.yaml・server.py・共用検索側は変更ゼロ。

### 1.3 contract.py 挙動テスト化（§2.2）

「両方指定→エラー」assertを削除し、**成功して label=NULL・id保持** の挙動assertに置換（race側・horse側各1ケース、unit_targets 3→5件、indexed集合assertも拡張）。

試験DB `keiba_nlp_stage2b_test` を3B手順で再作成し本体ごと実行: **46 calls, rc=0（PASS）**。
- 手順上の事故1件: scpした `001_initial.sql` がCRLFのまま適用され指紋ガード（`DDL/extension/grants differ from the pinned schema`）で失敗。`tr -d '\r'` でLF化して再作成した試験DBでは本物のmigrationで `schema verified 2a303dd4…` を確認。教訓: **scpしたSQL/スクリプトは必ずCR除去**（既存教訓の再確認）。
- 実行後 試験DB・pg_hba一時行とも削除し、本番DB不変（articles 20 / unit_targets 105 を再確認）。

### 1.4 実MCPでの本番反映確認（単発呼出）

本番 `keiba_nlp` に対し stdio MCP で `save_targets` 修正経路（既存target_id + race_id + race_label="検証"）を呼出:

- race側: `isError=False, race_label=None, race_id保持=True`
- horse側: `isError=False, horse_label=None, horse_id保持=True`
- 副作用: unit_targets 105→105（値は同一値の再設定のみ、全表件数不変）

**「両方指定が成功に変化した」ことを実測確認。**

## 2. ランB2 実行記録（指示書§3）

| 項目 | 実測 |
|---|---|
| 開始 | 2026-11-25 06:46:23（tmux runB2、`--max-turns 1200`、外側timeout 19800s） |
| タスク文 | 指示書§3から機械抽出のverbatim（1,657 B、sha256 `6d9d8ffc0ec3ab9a15fb32ae9859b90290a79b5b2f48388dd4566fc68412f162`） |
| run_id | `b7d41e58-2c9f-4a3e-8b6d-0f9c5e7a2d94`（status=running のまま。クラッシュでsave_run完了に至らず。run B同様保全） |
| 最終イベント | 07:06:48 最後のtool_use（save_targets）→ 07:07:45 `result exit_code=1` |
| 終了理由 | `This conversation has grown too long for halogen-qwen3.8-flash-next to read, and Hermes couldn't shrink it enough automatically.`（**コンテキスト超過・圧縮不足**。プロセス消滅確認 07:12:13、ログサイズ不変も確認） |
| 実効経過 | 約21.2分（イベント基準。外側timeout 19800s には未達） |
| 介入 | なし（監視はDB件数・ログサイズの読み取りのみ） |

tool call統計（全143）: save_horse 32 / save_race 29 / fetch_page 26 / save_article 19 / save_targets 15 / yahoo_search 11 / find_horses 6 / save_run 2 / skill_view 1 / get_runs 1 / skill_manage 1。

## 3. 相0: 検索方法の発見（§4-1）

- 時系列: 開始06:46:31 → 初検索06:48:06 → **Skill記録 06:49:57** → 台帳race登録 → 初save_article 06:52:26。**相0所要 約5.9分**。
- 実験した検索語（11語、ログ実測）: `2026 金杯`（事後のみと切り分け）/ `2026 金杯 追い切り`（事前）/ `2026 中山金杯 予想 本命` / `2026 中山金杯 枠順` / `2026 中山金杯 展望` / `2026 京都金杯 オッズ` / `2026 京都金杯 登録馬` / `agyo-keiba 中山金杯2026 追い切り` / `中山金杯 2026 登録馬 ラジオNIKKEI` / `中山金杯 2026 カラマティアノス 重賞初制覇`（事後）/ `京都金杯 2026 ブエナオンダ 重賞初制覇`（事後）。
- Skill記録（`nlpdb-keiba-article-collection` へpatch 2件・成功）の要約: ①「年+レース名」だけだと事後偏り、事前には修飾語（追い切り/枠順/オッズ/展望/予想/登録馬/想定馬・騎手/特注/AI）が必須 ②keiba.go.jp ALL JAPAN KEIBA DRAMA の predict/training/racecard 静的ページが高品質 ③取得可能ドメインのホワイトリスト ④取得不可・skip先（umasiru=ボット確認、sarabure=サービス終了、tospo/sportsbull=JS主体）。
- **ログ実測との整合: 整合**（skillに記録された語は実際に検索実行され、umasiruブロックは実測で観測。基準4 PASS）。

## 4. 台帳（§4-2）

- 導出過程: `https://www.jra.go.jp/datafile/seiseki/replay/2026/jyusyo.html` を5回、`g1.html` を2回、JRADB（accessS）2回、今週の出馬（thisweek/horse.html）2回 fetch。**JRA公式参照がログに存在（基準5 PASS）**。
- 確定した1月重賞9競走（race_key・場コード含む）。実施後に本レポート作成側でも公式一覧を独立取得して照合し、**9競走とも完全一致**:

| date | race_key | race_name | 公式 |
|---|---|---|---|
| 01-04 | 20260104/06/11 | 中山金杯 | GⅢ 中山 ✓ |
| 01-04 | 20260104/08/11 | 京都金杯 | GⅢ 京都 ✓ |
| 01-11 | 20260111/06/11 | フェアリーS | GⅢ 中山 ✓ |
| 01-12 | 20260112/08/11 | シンザン記念 | GⅢ 京都 ✓ |
| 01-18 | 20260118/06/11 | 京成杯 | GⅢ 中山 ✓ |
| 01-18 | 20260118/08/11 | 日経新春杯 | GⅡ 京都 ✓ |
| 01-24 | 20260124/10/11 | 小倉牝馬S | GⅢ 小倉 ✓ |
| 01-25 | 20260125/06/11 | アメリカJCC | GⅡ 中山 ✓ |
| 01-25 | 20260125/08/11 | プロキオンS | GⅡ 京都・ダ1800 ✓ |

- 指示書§4の参考一覧（金杯G4・日経新春杯・椿賞・京都牝馬S）とのズレ（§4の指示により記録）: **2026年は椿賞・京都牝馬Sが1月に無く、フェアリーS/シンザン記念/京成杯/アメリカJCC/プロキオンSが入る**。金杯はG3。プロキオンSは例年7月（新潟）だが2026年は1/25京都。ズレは台帳誤りではなく年次日程差。

## 5. 充足マトリクス（§4-3、SQL実測）

台帳レース×phase（distinct記事数。中山金杯の1件はB2前のRun B由来）:

| date | race_name | pre | post | mixed | total |
|---|---|---|---|---|---|
| 01-04 | 中山金杯 | 7 | 2 | 1 | 10 |
| 01-04 | 京都金杯 | 5 | 0 | 0 | 5 |
| 01-11 | フェアリーS | 0 | 0 | 0 | 0 |
| 01-12 | シンザン記念 | 0 | 0 | 0 | 0 |
| 01-18 | 京成杯 | 0 | 0 | 0 | 0 |
| 01-18 | 日経新春杯 | 0 | 1 | 0 | 1 |
| 01-24 | 小倉牝馬S | 0 | 0 | 0 | 0 |
| 01-25 | アメリカJCC | 0 | 0 | 0 | 0 |
| 01-25 | プロキオンS | 0 | 0 | 0 | 0 |

B2差分（collected_at >= 2026-11-24T21:46Z）: **articles +19**（20→39）、text_units +19（61→80）、unit_targets +188（105→293）、horses +32（30→62）、races +8（1競走はRun B既存とrace_key一致で既存行に合流、1月重賞は計9行）。phase分布（B2記事、distinct記事）: **pre 12 / post 2 / mixed 1**、索引なし4。pre比率 = 12/15 = **80%**（索引なし込みでも12/19=63%）。

## 6. 観察チェックリスト実測（§4）

- 排他エラー発生数: **0**（`Both race_id and race_label` 等ゼロ。Bの7回トラップは仕様変更で消滅）。
- ループガード: **pause 17回・全体停止0回**（停止条件には不使用、記録のみ）。起因はモデル自身のsave_race引数成形ミス（race_id文字列に `…e501\n</parameter>\n=create\ntr` 相当のゴミ混入でreject → 引数修正して自己復旧）。3C-2のような「同一ミス反復による全体停止」は起きなかった。pause合計≈2.5分。
- 429: **実発生0**（ログの "429" 4件はすべてUUID部分文字列の誤検出）。
- fetch失敗内訳（4件）: umasiru.com ボット確認1・keiba-bloodline.com ボット確認1・routify-file-proxy（検索結果に混入したサードパーティミラーURL、B観察8の続き）403×2。**いずれも回避試行なし**（再試行・UA切替・突破なし。モデルはSkillにskip先として記録）。
- 圧縮: **発動したが不足** → セッション終了（§0）。§9残件は「実測済み・不足」に更新。
- 自己申告とDB実測: save_run の progress は初回バッチ（06:52）以降更新されないままクラッシュ。会計はDB実測（§5）を正本とする（3C-2観察と同傾向）。
- 禁止行為: **0件**（CAPTCHA・UA切替・プロキシ利用なし。grepヒットはミラーURL名とブロックメッセージであり行為ではない）。
- 再実行増殖テスト（§3、1件）: B2記事1件を同一 source_url+body+body_kind で再 save_article → **同一 article_id 返却、articles 39→39・text_units 80→80（増殖なし）**。dup_source_urls=0。

## 7. 合格基準判定（§5）

| # | 基準 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 総計40件以上 | **未達** | B2追加19件（DB総計39件）。いずれの読み方でも未達 |
| 2 | 台帳80%以上のレースで5件以上 | **未達** | 5件以上は2/9競走（22%）。6競走は0件（クラッシュで未着手） |
| 3 | phase pre 60%以上 | **達成** | 80%（索引なし込みでも63%）。救済条項不要 |
| 4 | 相0のSkill記録とログ整合 | **達成** | §3 |
| 5 | 台帳導出過程（JRA公式） | **達成** | §4 |
| 6 | 禁止行為なし・DBクリーン・増殖なし | **達成** | §6 |

→ **基準1・2未達のためB2不合格**。マラソン指示書の起草は行わない。

### 不合格の因果分析（過程記録）

1. 基準1・2の未達は**収集能力の不足ではなくセッション寿命**。スループットは約19記事/21分（≈55記事/h換算）で、40件は単一セッション内でも到達可能な水準。
2. コンテキスト超過の主因は fetch_page の大型本文（JRA公式・netkeiba等）が1セッションに蓄積すること。圧縮は発動したが追いつかず。
3. 台帳9競走のうち収集に着手できたのは2競走（中山金杯10本・京都金杯5本、いずれも目標10本前後に対し健闘）。残7競走はクラッシュで未着手。
4. 排他トラップ・台帳導出・事前検索・索引付け・重複防止はすべて正常。Bから是正された項目は多い。

## 8. マラソン設計への入力（§7必須）

- **最優先課題=コンテキスト管理**（マラソンは長時間ランなので必ず同じ壁に当たる）。選択肢（ユーザー決定事項・本ランでは未実施）:
  1. **リレー実行**: 同一verbatimタスクでセッションを分割し、Skill＋DB（find_horses/get_runs/既存台帳）を永続記憶として継続。B2のSkill記録が既に土台。要ユーザー承認（1ラン=1セッションの前提変更）。
  2. fetch_page 出力のスリム化（共用側変更＝§8禁止。解除の要否はユーザー判断）。
  3. 更大コンテキストモデルへの切替（Hermes終了メッセージも推奨）。実行基盤の個別合意事項。
  4. Hermes圧縮設定の調整（config.yaml変更＝§8禁止。同上）。
- 台帳・Skill・検索語の仕組みはそのまま流用可。1セッションの実効収集可能量は約20分≈20件で頭打ち（現状設定）。
- 1月重賞の事前記事は実在（中山金杯pre7・京都金杯pre5）。「構造的に事前記事が存在しない」救済条項の発動事例は今回なし。

## 9. 変更・副作用・残件

- 変更: `infra/nlp-vm/hermes/targets.py`・`infra/nlp-vm/hermes/tests/contract.py`（commit ada67bb）/ VM15 image `3a1ef55d…`（稼働中）/ 試験DB・pg_hba一時行は作成→削除済み。
- DB状態（dump取得後）: articles 39 / text_units 80 / unit_targets 293 / horses 62 / races 16 / collection_runs 3（run B・B2とも status=running のまま保全）。
- pg_dump: `/srv/nlp/dumps/keiba_nlp_20261125_stage3c_2r.sql`（209,736 B、sha256 `e267d48c165728e15db763d2ac855980b01eee0552e258176a46df224e5cc997`）。
- ラン成果物（VM15・Git非管理）: `/srv/nlp/runs/2026-11-25_stage3c_2r_b2/`（taskB2.txt・runB2.jsonl・runB2.err・monitor.log・runB2.start）。
- 残件: run B2行のstatus=running保全（run B同様）。B2記事のうち索引なし4件（クラッシュ時点）。起動時toolset警告（`Unknown toolsets: mcp-nlpdb, mcp-shared`）は外観上・未整理のまま。圧縮実効性は「発動するが不足」と実測済み（§9残件更新）。
- 未実施: マラソン起草（不合格のため禁止どおり）。
