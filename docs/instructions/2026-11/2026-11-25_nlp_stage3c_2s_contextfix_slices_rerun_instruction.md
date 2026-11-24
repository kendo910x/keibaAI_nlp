# 段階3C-2s 指示書: コンテキスト対策適用・馬別スライス導入・B2再実行（B3）

作成日: 2026-11-25（JST）
前提: 3C-2r指示書（commit 5c2ae0c）のB2は§5基準1・2未達の不合格。直接原因はコンテキスト超過クラッシュ（レポート `7c79a1c` §0・§2）。
本指示書の目的: (1) Hermes圧縮設定に実証済みの対策を適用し、(2) 馬別スライスの保存手段（`save_slices`）と後処理段を追加し、(3) 3C-2rのタスク文をそのまま再実行する（B3）。

役割分担（3C-2r§3と同じ）: **研究タスク（相0・台帳・収集・スライス）の実行者はVM15のHermes**。コーディングエージェントは起動・観察・実測・記録と§1§2の管理側変更まで。研究タスクを代行しない。タスク文は `--query-file` でverbatim転送し、解釈・補足しない。

## 0. 前提確認

- VM15 Hermes は v0.22.2。`target_ratio`（hermes_cli/config.py・session_compression.py）と `auxiliary.*.extra_body`（config_defaults.py の `_aux()`）を両方サポートすることを確認済み。設定移植はバージョン変更不要。
- 対策の出典: 開発PCの Hermes v0.23.3 で同種の圧縮不足問題を解決した設定（`target_ratio: 0.2` + 圧縮モデルの `extra_body`）。
- 共用検索（Talos側）は本指示書でも変更しない。

## 1. 管理側変更1: Hermes圧縮設定（VM15）

対象ファイル: `/srv/nlp/hermes-runtime/config.yaml`（VM15）。編集前に `config.yaml.bak-3c2s` へ退避する。

意味的な変更は次の2点のみ。既存の他キー（`enabled`・`threshold`・`threshold_tokens`・`protect_last_n`・`mcp_servers` 等）は変更しない。

1. `compression:` に **`target_ratio: 0.2`** を追加する。
2. `auxiliary.compression:` に **`extra_body`** を追加する。ただし現行ファイルは `compression: &local` アンカーを `vision`/`approval`/`skills_hub`/`mcp` が共有しているため、**`extra_body` が *local 側に漏れないよう**アンカーを `vision` 側へ移し、compression 独自ブロックにする。目標形:

```yaml
compression:
  enabled: true
  threshold: 0.50
  threshold_tokens: 131072
  target_ratio: 0.2
  protect_last_n: 20
auxiliary:
  compression:
    provider: custom
    model: halogen-qwen3.8-flash-next
    base_url: http://192.168.0.13:8731/v1
    extra_body:
      max_tokens: 32768
      chat_template_kwargs:
        enable_thinking: true
  vision: &local
    provider: custom
    model: halogen-qwen3.8-flash-next
    base_url: http://192.168.0.13:8731/v1
  approval: *local
  skills_hub: *local
  mcp: *local
```

現行ファイルに上記以外のキー（`timeout`・`api_key` 等）が実在する場合は保持したまま、上記の構造変更だけを適用すること。

検証（すべて実測記録）:
- `python3 -c "import yaml,..."` で `yaml.safe_load` 成功と、解決後dictの `compression.target_ratio == 0.2`・`auxiliary.compression.extra_body.max_tokens == 32768`・`auxiliary.vision` に `extra_body` が**無い**ことを確認
- `systemctl restart nlp-hermes` → active 確認
- スモーク: 単発 `hermes chat -Q` で1往復し、設定エラー・起動警告が増えていないこと
- repo側 `infra/nlp-vm/hermes/config.yaml` にも同一変更を反映し、§7のcommitに含める

## 2. 管理側変更2: `save_slices` ツール（nlpdb MCP）

目的: 馬別スライス（記事本文からの意味的切り出し）を、幻覚不可で保存できるようにする。**スキーマ変更は行わない**（`text_units`・`unit_targets` をそのまま使う。DDL指紋ガード `2a303dd4…` 不変）。

新規ツール（server.py）:

```
save_slices(article_id, slices)
  slices: list of { horse_id: UUID, start_char: int, end_char: int,
                    quote: str, phase: "pre"|"post"|"mixed" }
```

サーバー側検証（いずれか失敗で ValueError、DB変更なし）:
- 記事が存在し `body` が非NULL
- **`body[start_char:end_char] == quote` が完全一致**（verbatim照合。LLM出力の幻覚を機械的に排除）
- `horse_id` が horses に実在（labelは受け付けない。`find_horses` で解決してから呼ぶ）
- `phase` は列挙値のみ

挙動:
- `text_units` に `(article_id, start_char, end_char)` の行を作成（UNIQUE制約済み。既存なら再使用）。全文unit（start=0, end=len(body)）はそのまま残す
- `unit_targets` に `(unit_id, horse_id, phase)` を作成。既存の重複防止は schema の制約を確認のうえ、SELECT-then-INSERT の冪等実装とする
- 戻り値: 作成・既存再使用の件数
- 1記事1呼び出しを基本とする（記事単位で即時保存させ、セッション断絶時の再開点にする）

contract.py に挙動ケース追加（試験DBは3B手順・CRLF除去済みのSQLで作成）:
1. 正常スライス成功→unit/target作成、再実行で冪等（増殖なし）
2. quote不一致→ValueError
3. 存在しないhorse_id→ValueError
4. 全文unitと同一スパン→既存unit再使用

ビルド・配備は 3508fa4 と同一手順（`/srv/nlp/hermes-runtime/build/` 配置→podman build→systemctl restart）。image ID を before/after 実測記録。単発MCP呼出で本番実測（実記事1件で正常系・quote不一致系の両方）を確認する。

## 3. フェーズB3: 3C-2rタスク文の再実行

- タスク文: 3C-2r指示書§3の機械抽出verbatim（1,657 B、sha256 `6d9d8ffc0ec3ab9a15fb32ae9859b90290a79b5b2f48388dd4566fc68412f162`）。**改変禁止**。DBは継続（articles 39・台帳9競走は既存。台帳再導出ではなく充足を続ける）
- 起動: tmux、`--max-turns 1200`、外側timeout 19800s（3C-2rと同一予算）
- 監視: DB件数・ログサイズの読み取りのみ。停止確認は「実コマンドライン一致パターン＋プロセス一覧＋ログ不変」の3点（Bの教訓）
- 停止条件: 3C-2r§9（30分正味進捗なし）を踏襲。**圧縮設定適用後に再びコンテキスト超過クラッシュが起きた場合は、再試行せず停止してレポート**（設定対策の実測結果そのものが成果）
- 記録: セッション寿命（開始〜終了まで分単位）を記録し、B2の21.2分と比較する

## 4. フェーズS: 馬別スライスパス（B3終了後・別セッション）

収集セッションとは**別のHermesセッション**で実行する（収集のコンテキストを消費しない）。タスク文は以下をverbatimで `--query-file` 転送:

```
あなたは nlpdb の馬別スライス実行者です。本文（body_kind が full または excerpt）を持ち、かつ馬ターゲットが1件以上付いている記事について、馬別スライス（全文unit以外のunit）が未登録の記事を1件ずつ処理してください。
1. get_article で本文・馬ターゲット・既存unit一覧を取得する。
2. 各馬について、その馬が語られている文字範囲を意味判断で特定する。代名詞・「この馬」・別名・枠番などの間接参照で語られている範囲もその馬に含める。見出し構造に依存しない。
3. save_slices を記事ごとに1回呼び、各馬について horse_id・start_char・end_char・quote（本文からの逐語コピー。照合される）・phase（既存ターゲットに合わせる）を渡す。
4. 複数の馬が同じ範囲について語られている場合はスパンの重複登録でよい。
5. 記事は1件処理ごとに即保存する。コンテキストの残りが少なくなったら、最後に保存した記事までを完了として、未処理記事数を報告して停止する。
禁止: 本文の要約・言い換えをquoteにすること。存在しないhorse_idの推測。
```

- 予算: 経過120分・外側timeout 9000s。進捗管理はDB実測（スライス済み記事/未処理記事）で実施し、セッション断絶時は残りで再開してよい（冪等）
- 進捗JSONや自己申告は参考値とし、会計はSQL実測を正本とする（B/B2の教訓）

## 5. 合格基準

1〜6 は 3C-2r§5 と同一（B3終了時点のDB実測）:
1. 記事総計40件以上
2. 台帳9競走のうち80%以上に5件以上
3. phase pre 60%以上（B3追加分）
4. 相0の検索方法発見とSkill記録がログと整合
5. 台帳導出にJRA/NAR公式参照が存在
6. 禁止行為なし・重複0・再実行増殖なし

追加:
7. スライス充足: B3記事（本文あり・馬ターゲットあり）の (記事, 馬) ペアの **90%以上**にスライスが付き、全スライスがサーバー側verbatim照合を通過（通過しない保存はツールが構造的に拒否するため、実測は「拒否率」として報告）
8. コンテキスト対策実測: B3セッション寿命を記録し、B2の21.2分比を報告（寿命延伸の成否自体は合否条件ではなく観察項目。ただしクラッシュ再発時は§3どおり停止）

**基準1〜3のいずれか未達のままマラソン（3C-3）指示書を起草しない**（ゲート不変）。

## 6. 禁止事項

- DBスキーマ変更（DDL指紋ガード対象）、共用検索・Talos側変更
- §1以外のconfig.yaml変更、§2以外のイメージ内容変更
- 実Yahoo検索のテスト利用、CAPTCHA突破・UA切替・プロキシ利用（B3/Sとも、Hermesにもコーディングエージェントにも）
- 秘密・記事本文・セッションログ全文のGit commit（ログはVM15のGit外ディレクトリ保全）

## 7. 成果物・レポート

- commit: `infra/nlp-vm/hermes/server.py`・`tests/contract.py`・`infra/nlp-vm/hermes/config.yaml`・レポート1本。レポートは `docs/reports/2026-11/2026-11-25_nlp_stage3c_2s_contextfix_slices_rerun_report.md`
- レポート必須記録: 設定変更before/after（解決後dictの実測）・image before/after・`save_slices` 本番実測・B3セッション寿命とB2比・充足マトリクス（台帳×phase）・スライス覆盖率と拒否率・§5判定表・過失の自己申告
- pg_dump: `/srv/nlp/dumps/keiba_nlp_<日付>_stage3c_2s.sql`（sha256記録）
- ラン成果物（Git外）: `/srv/nlp/runs/2026-11-25_stage3c_2s_b3/` と `.../slices/`（task文・jsonl・err・monitor.log）
- run行は status 更新できなければ保全（B/B2と同様）
