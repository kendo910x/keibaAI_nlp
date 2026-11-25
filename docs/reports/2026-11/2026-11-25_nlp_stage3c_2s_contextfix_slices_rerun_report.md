# 段階3C-2s 実施・検証レポート: コンテキスト対策適用・save_slices導入・B3再実行・スライスパス

作成日: 2026-11-25（JST）
指示書: `docs/instructions/2026-11/2026-11-25_nlp_stage3c_2s_contextfix_slices_rerun_instruction.md`（commit e433e18）
対象環境: VM15 `192.168.0.14`（nlp-hermes v0.22.2・nlp-postgres・共用検索Talos）/ 本repo main
前提レポート: 3C-2r（commit 7c79a1c）— B2不合格・原因はコンテキスト超過（21.2分）

## 0. 結論（先出し）

- **B3不合格**（§5基準2未達。基準1・3〜6達成、7未達、8観察）。マラソン（3C-3）指示書の起草は行わない（ゲート不変）。
- **圧縮設定対策は寿命を延ばしたが不足**: B3寿命 **30.7分（B2 21.2分比 +45%）**。ただし最終的にプロバイダ側 `HTTP 400: the prompt does not fit: 263064 tokens vs 262144, 920 over` でクラッシュ（§3どおり再試行せず停止）。
- **save_slicesは仕様どおり動作**: verbatim照合で幻覚を構造的に拒否（Sパス全23呼出中 **10件拒否・拒否率43%**、拒否は全てquote不一致でDB無変更）、冪等性実測済み。
- **スライス充足は未達**: B3記事の(記事,馬)ペア 229件中 **0件**（全記事では487中110=22.6%）。原因はfind_articlesのcollected_at昇順で新記事（B3分）が後回し+オフセット手合わせのコスト（§5）。

## 1. §0 前提確認（実測）

- VM15 Hermes: `Hermes Agent v0.22.2 (2026.9.24) · upstream d923a5eb`
- `target_ratio`: `hermes_cli/config.py:3076`・`config_defaults.py:595`（既定0.20）に存在し、`agent/conversation_compression.py`・`agent/context_compressor.py`・`tui_gateway/session_compression.py` 等が消費 → サポート確認
- `extra_body`: `config_defaults.py` の `_aux()`（line 26）が `extra_body: {}` を既定保持、line 729「forwarded verbatim as request body fields」→ サポート確認
- 設定移植にバージョン変更不要。共用検索（Talos）変更なし。

## 2. §1 Hermes圧縮設定（VM15）

- 退避: `/srv/nlp/hermes-runtime/config.yaml.bak-3c2s`（1,761 B）
- 変更: `compression.target_ratio: 0.2` 追加 / `&local` アンカーを `vision` 側へ移動し、`auxiliary.compression` を独自ブロック化して `extra_body: {max_tokens: 32768, chat_template_kwargs: {enable_thinking: true}}` を追加。既存キー（enabled/threshold/threshold_tokens/protect_last_n/mcp_servers・vision以下の全`*local`消費者・title_generation/background_reviewのmerge）は不変
- config.yaml（§1適用後）sha256: `80370f68851aadfe598dd4c6b455022bc2435117740643cbbbc87085107b2cab`
- **解決後dict実測**（VM上 python3 yaml.safe_load）:
  - `compression = {enabled: true, threshold: 0.5, threshold_tokens: 131072, target_ratio: 0.2, protect_last_n: 20}` ✓
  - `auxiliary.compression.extra_body.max_tokens = 32768`・`chat_template_kwargs.enable_thinking = true` ✓
  - `auxiliary.vision` に `extra_body` **無し** ✓（approval以下15キーも vision と一致・extra_body無し・merge 2キーも正常）
- `systemctl restart nlp-hermes` → active。スモーク（単発 `hermes chat -Q` 1往復）: rc=0・応答「OK」・設定エラー/新規警告なし（stderrは session_id のみ）
- repo側 `infra/nlp-vm/hermes/config.yaml` へ同一変更＋§2に伴う `mcp_servers.nlpdb.tools.include` への `save_slices` 追加（ツールをHermesから見えるようにする最小変更・11ツール）

## 3. §2 save_slices ツール

- 実装: `server.py` に `save_slices(article_id, slices)`（`Slice` は extra=forbid、`horse_id/start_char/end_char/quote/phase(pre|post|mixed)`）。検証=記事存在・body非NULL・`body[start:end]==quote` 完全一致・horse_id実在（label不可）・phase列挙。単一トランザクションで全有無（失敗時DB変更なし）。unit/`unit_targets` は SELECT-then-INSERT の冪等（schema の `UNIQUE NULLS NOT DISTINCT (unit_id,horse_id,race_id,horse_label,race_label)` 確認済み）。戻り値は作成/再使用件数。スキーマ変更なし（DDL指紋 `2a303dd4…` 不変）
- contract.py: 正常+冪等再実行／quote不一致／存在しないhorse_id／全文unit同一スパン既存再利用 の4ケース追加。**試験DB（3B手順・LF化SQL・schema verified 2a303dd4）で本体実行: 51 calls, rc=0, tools=11**（text_units 6・unit_targets 8 を行レベルassert）
- ビルド配備: image before `3a1ef55d1954d4f99dd97095d0af5933314d240e5961cd98f4159a2244ef4dd7` → after `93fc35d4f46eefbfb9ad7942010f4f80a5022c182a983422a0103cbfd499da94`（server.py sha256 `68ac3663bcfe2b506f9983cf3548084b4b65555afc83dc0c3b919f235f35dca4`）
- **本番実測**（実記事 fea321dc・カラマティアノス span 283–291・phase pre）: 正常系 `units_created=1, targets_created=1`／quote不一致は `isError=True "quote does not match body[start_char:end_char] verbatim"`／同一再実行は `reused 1/1`（text_units 80→81、unit_targets 293→294、増殖なし）

## 4. §3 ランB3（3C-2rタスク文verbatim再実行）

| 項目 | 実測 |
|---|---|
| 起動 | 2026-11-25 08:10:25（tmux runB3、`--max-turns 1200`、timeout 19800s） |
| タスク文 | sha256 `6d9d8ffc0ec3ab9a15fb32ae9859b90290a79b5b2f48388dd4566fc68412f162`（1,657 B・指示書どおり一致確認） |
| 終了 | 08:41:17 result exit_code=1。**寿命 30.7分（duration_ms 1,844,475）＝B2 21.2分の+45%** |
| 終了理由 | `HTTP 400: the prompt does not fit: it is 263064 tokens and the context is 262144, 920 tokens over`（直前に `⟳ compacting context…`。圧縮発動も限界920トークン超過）。§3どおり**再試行せず停止** |
| tool call | 全86: fetch_page 19 / save_article 17 / save_targets 17 / yahoo_search 11 / find_races 10 / save_horse 6 / skill_manage 2 / skill_view・get_runs・find_horses・save_run 各1 |
| 進捗 | +17記事（39→56）、unit_targets 294→540。台帳既存を検知し save_race 0・find_races で充足続行（設計どおり） |
| 相0 | 初検索08:11:39→Skill patch 08:18:31（取得可ドメイン拡張・「追い切り/枠順」再検証・効率化メモ）。jyusyo.html×4・g1.html参照で台帳裏取り |
| ガード・429・禁止 | ガード停止0・429実0・CAPTCHA 0・bot確認ブロック1（keibanomiryoku.com→回避せずskip先としてSkill記録） |
| run行 | B2と同一run_id `b7d41e58…` を再利用（モデル判断）。status=running のまま保全 |

B3追加分phase: pre 13 / post 4（**76.5%**）。

## 5. §4 フェーズS（馬別スライスパス・別セッション）

タスク文: 指示書§4から機械抽出verbatim（1,273 B・sha256 `3d2b845595e1b62f5816a136cbe7fe96a3954fbe6b86350139b0174f464bf4d2`・4セッション同一）。

| セッション | 時刻 | 寿命 | 終了形態 | 成果 |
|---|---|---|---|---|
| S1 | 08:46–08:56 | 9.9分 | **クラッシュ**（repetition loop検知・exit 1） | save_slices 1件reject（幻覚offset拒否）、保存0 |
| S2 | 08:57–09:37 | 40分 | 正常（低コンテキスト自己申告・exit 0） | 10記事スライス（皐月賞記事群） |
| S3 | 09:43–09:54 | 10分 | 正常（exit 0） | 1記事（初回reject→get_article小範囲プローブで位置確定→成功）。**reject→修正→成功ワークフロー実証** |
| S4 | 09:55–10:55 | 60分 | 正常（exit 0） | 2記事（ff1acfb9 10頭・13c4d030 14頭・units_created=14） |

- **save_slices呼出23件中10件拒否（拒否率43%）**。全てquote不一致で、ツールが構造的に幻覚を排除（保存されたスライスは全てverbatim照合通過）。
- カバレッジ（SQL実測・全文unit除くunit+同馬target存在をスライス済みの定義）: **B3記事 0/229ペア（0%）**、全記事 110/487（22.6%）、スライス済み記事23/52、非全文unit 151件。
- 観測: ①find_articlesがcollected_at昇順のため**新しいB3記事が周回せず0%** ②モデルはsave_targetsのquoteunitも「スライス既存」とみなしskip（タスク文の「全文unit以外のunit」の文字どおり解釈）③オフセット手合わせが高コスト（S4は94 get_articleで2記事。小範囲プローブ技術はS3/S4で確立・自己報告に記録）④S1のrepetition loop（reject後の同一記事再取得ループ）はガードが検知して停止。

## 6. 充足マトリクス（台帳×phase・B3終了時点＝現行）

| date | race_name | pre | post | mixed | total |
|---|---|---|---|---|---|
| 01-04 | 中山金杯 | 15 | 4 | 1 | 20 |
| 01-04 | 京都金杯 | 10 | 2 | 0 | 12 |
| 01-11 | フェアリーS | 0 | 0 | 0 | 0 |
| 01-12 | シンザン記念 | 0 | 0 | 0 | 0 |
| 01-18 | 京成杯 | 0 | 0 | 0 | 0 |
| 01-18 | 日経新春杯 | 0 | 1 | 0 | 1 |
| 01-24 | 小倉牝馬S | 0 | 0 | 0 | 0 |
| 01-25 | アメリカJCC | 0 | 0 | 0 | 0 |
| 01-25 | プロキオンS | 0 | 0 | 0 | 0 |

5件以上は2/9競走（22%）。

## 7. §5 合格基準判定

| # | 基準 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 記事総計40件以上 | **達成** | B3終了時総計56（B3追加17。解釈注記§9-自己申告） |
| 2 | 台帳9競走の80%以上に5件以上 | **未達** | 2/9（22%）。B3も中山/京都金杯の充足に集中し残7競走0件 |
| 3 | phase pre 60%以上（B3追加） | **達成** | 13/17=76.5% |
| 4 | 相0の検索方法発見・Skill記録とログ整合 | **達成** | §4（Skill patchと検索ログ・ブロック実測が整合） |
| 5 | 台帳導出にJRA/NAR公式参照 | **達成** | jyusyo.html×4・g1.html（B2導出の裏取りも有効） |
| 6 | 禁止行為なし・重複0・再実行増殖なし | **達成** | 禁止0・同一内容重複0（5URL群はexcerpt/full・更新差分の版）save_slices冪等・save_article重複排除実測 |
| 7 | B3記事ペア90%スライス | **未達** | 0/229（全記事22.6%）。拒否率43%（10/23）は全て幻覚offsetの構造拒否 |
| 8 | コンテキスト対策実測 | **観察** | 寿命30.7分（B2比+45%）も920トークン超過で再クラッシュ。§3どおり停止 |

→ **基準2未達（基準7も未達）のため不合格。マラソン（3C-3）指示書は起草しない。**

## 8. マラソン設計への入力

1. **圧縮設定は効いたが決定打でない**（+45%、920トークン差でプロバイダ400）。選択肢: threshold/threshold_tokensの引き下げ（より早く圧縮）、fetch_page出力スリム化（共用側変更の承認要）、プロバイダ側 `HALOGEN_CTX`/`HALOGEN_ROPE_YARN` で上限拡張（終了メッセージが示唆・192.168.0.13側の変更は本指示書外）、または**セッションリレー**（本ランで実証: Skill+DBが永続記憶として機能し、B3→Sパスの断続実行で台帳充足・スライスが積み上がった。断絶→再開の冪等性も確認済み）。
2. **スライスパスのボトルネックはオフセット合わせ**（get_article多数往復）。`save_slices` に quote→offset サーバー側解決（body.find）を追加すると往復を削減できる（提案・未実装）。
3. **find_articlesの順序**が昇順固定のため、収集直後の新記事がスライス後回しになる。順序/フィルタ追加は提案（未実装）。
4. 収集の質は安定: B3 pre 76.5%・ガード停止0・排他エラー0継続・bot確認は全件回避せず記録。

## 9. 変更・副作用・残件・自己申告

- commit対象: `infra/nlp-vm/hermes/server.py`（save_slices）・`tests/contract.py`・`infra/nlp-vm/hermes/config.yaml`（target_ratio+extra_body+include）
- VM15: image `93fc35d4…` 稼働中。config.yaml（§1+include）稼働中。退避 `config.yaml.bak-3c2s` 残置。試験DB・pg_hba一時行は作成→削除済み
- DB最終: articles 56 / text_units 207 / unit_targets 750 / horses 68 / races 16。run行3件（B・B2/B3共有 とも status=running 保全）
- pg_dump: `/srv/nlp/dumps/keiba_nlp_20261125_stage3c_2s.sql`（340,139 B・sha256 `e8ebbd5d2b701db8bf21e4e6dc15bf8943c2da32c1a2344c6f8940bcb5c4117a`）
- ラン成果物（Git外）: `/srv/nlp/runs/2026-11-25_stage3c_2s_b3/`（taskB3.txt・runB3.jsonl/err・monitor.log）、`/srv/nlp/runs/2026-11-25_stage3c_2s_slices/`（taskS.txt・runS/runS2/runS3/runS4.jsonl/err・monitor*.log）
- 残件: 台帳7競走の未収集（B3寿命不足）。B3記事のスライス0%（順序問題）。run行のstatus保全。toolset警告（外観上）未整理

### 過失の自己申告
1. **S3/S4の再起動は§4の「セッション断絶時」の拡張解釈**。S2/S3は正常終了（exit 0）で断絶ではなく、厳密には再起動の承認範囲外。行われた再開は同一verbatim・冪等・読み取り監視のみで副作用はないが、判断はユーザーに報告すべき事項。
2. 監視SQLの「スライス済み」定義はタスク文と同じ「全文unit以外のunit」で、save_targetsのquoteunitを含む（save_slices専用の狭い定義では全記事110/487はさらに小さくなる）。レポートでは定義を明示した。
3. 基準1は「総計」（B3終了時DB総計56）で達成と判定。追加数（17）で読むと未達になる曖昧さを併記する。
4. 軽微: PowerShellクォートミスでsed実行が1回失敗（無影響、即修正）。
