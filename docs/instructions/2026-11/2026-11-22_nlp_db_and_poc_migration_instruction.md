# NLP専用DB（PostgreSQL）構築とPoCデータ移行 指示書

作成日: 2026-11-22（JST） / 対象: NLP VM `192.168.0.14`（段階2A構築済み想定）+ `kendo910x/keibaAI_nlp`（`infra/nlp-vm/db/`、`scripts/`）
設計出典: 本repo `docs/design/2026-11-22_nlp_infrastructure_placement.md` §5-1（自己完結キー）、引き継ぎ書 `docs/handoffs/2026-11/2026-11-22_data_accumulation_handover.md` §3（PoCデータの品質）・§6（保存原則）

## 1. 目的

NLP VM に原文・出典・探索履歴の永続保存先（PostgreSQL）を構築し、PoC の皐月賞記事24件（開発PC `keiba_nlp/data/poc/g1_passages.jsonl`、Git管理外・実体23,714B・2026-11-22実測）を移行する。
完了時点: SQLで「記事→race_key/horse_key対応付け」を確認でき、移行再実行で重複が増えず、pg_dump→リストアで復元できる。**エージェント・Embedding・v3連携は範囲外（段階3以降）**。

## 2. 開始前に読むもの

- 本repo `AGENTS.md`、上記設計メモ、引き継ぎ書 §3・§6
- 段階2Aレポート `docs/reports/2026-11/2026-11-22_nlp_vm_build_report.md`（VMの実測状態）
- PoCレポート `docs/reports/2026-11/2026-11-22_g1_article_autonomous_search_poc_report.md`（`g1_passages.jsonl` のフィールド定義と品質内訳）

## 3. 確定設計（2026-11-22 ユーザー合意済み。再議論しない）

1. **PostgreSQL 16**（docker.io 公式イメージ、tag+digest固定）を **quadlet** で起動。データは `/srv/nlp/pgdata`（ホスト側）。`shared_buffers=512MB`・`max_connections=50`（8GB VM 向け）
2. DB `keiba_nlp` / アプリユーザー `nlp_app`。パスワードは `/srv/nlp/.env`（0600・Git管理外）。**LAN listen・TLSなし**（ufwで5432はLAN許可済み。ユーザー承認済み）
3. **v3連携なし・自己完結キー**（設計メモ §5-1）:
   - `race_key = YYYYMMDD/JJ/RR`。JJ（競馬場コード）は v3 `services/live/service/race_key.py` かJRA公式コード表で**実物確認してから**採用（記憶からの確定禁止）。皐月賞=中山
   - `horse_key` = 馬名正規化（NFKC・空白除去。長音記号・「号」等は保持）。namespace既定 `jra`。生表記は alias に保持し、複数候補・保留を許容して断定しない
4. **pgvector・Embedding生成は入れない**（ベクトル保存は別決定の後続）
5. 移行の冪等キー: `(canonical_url, content_hash)`。再実行で新規0行

## 4. スキーマ v1

マイグレーションSQLは `infra/nlp-vm/db/migrations/`（連番・psql適用）。以下は必須の論理単位と必須列（列名・型・index・追加テーブルは実装裁量）。引き継ぎ書 §6.2（過去取得版を上書きしない／スニペット・要約と原文を区別／保留許容）に反する設計変更は不可。

| テーブル | 必須内容 |
|---|---|
| `collection_tasks` | task_id、目的、実行予算(jsonb)、状態、開始・終了時刻、備考 |
| `search_log` | task_id FK、検索語、backend/tool、結果URL(jsonb)、観測時刻、備考 |
| `races` | `race_key` PK、レース名、race_date、開催コード、レース番号、芝・距離（nullable）、根拠 |
| `horses` | `horse_key` PK、namespace（既定jra）、生年（nullable）、備考 |
| `horse_aliases` | 生表記 PK、horse_key FK、同定根拠 |
| `articles` | article_id、`canonical_url` UNIQUE、domain、媒体、タイトル、公開日時（自由記述raw＋解釈値＋精度enum: day/month/unknown。不明はNULLで架空補完なし）、初回観測時刻、次の再試行時刻、取得試行回数 |
| `article_fetches` | fetch_id、article_id FK、取得日時、取得方法、HTTP状態、`fetch_status` enum: `full`/`excerpt`/`snippet_only`/`unreachable`/`parse_failed`、final_url、`raw_text`（原文はDB内保存）、`content_hash`（sha256）、切り詰めflag。UNIQUE(article_id, content_hash) |
| `passages` | passage_id、fetch_id FK、順序、text、発言者、info_kind（コメント/回顧/予想等）、根拠 |
| `article_targets` / `passage_targets` | 対象種別(race/horse)、race_key/horse_key FK（nullable）、`match_status` enum: `resolved`/`candidate`/`held`、根拠、確認時刻 |
| `derived_artifacts` | kind(summary/embedding)、対象、モデル・revision・次元数・前処理・生成日時、payload位置（**メタのみ。ベクトル実体は後続**） |

- 全時刻 `timestamptz`。JST表示はクライアント側
- 同一URLの再取得は fetch を増やす（articles行の書き換えで過去版を失わない）

## 5. PoC移行スクリプト

`scripts/migrate_poc_g1.py`（psycopg、開発PC→VMのPostgreSQLへLAN接続。実行例をREADME化）。入力 `data/poc/g1_passages.jsonl`（24件、フィールド: source_url/media/title/published_at/observed_at/race_label/horse_name/speaker/info_kind/text）。

- **品質分類**: 本文抜粋・検索スニペット由来・原文なしが混在（引き継ぎ書 §3）。text長と info_kind から `fetch_status` を判定し、**全件をfullとして登録しない**。判定根拠をスクリプトにコメント化
- `race_label`（例「皐月賞2024(2024-04-14 中山 芝2000 G1)」）→ races + article_targets(`resolved`)。日付はrecord内から読む（記憶で確定しない）。レース番号が読めない場合は `held`
- `horse_name` → horses + aliases + article_targets(`resolved`、根拠=speaker/info_kind)。textに複数馬が現れる場合は `candidate`
- `published_at` 自由記述（例「2024-04-14（レース当日・時刻不明）」）→ raw＋解釈値＋精度
- `observed_at` → 初回観測。`content_hash=sha256(text)`、`fetch_method='poc_migration'`
- 任意: `data/poc/yahoo_fixed_queries.json`・`yahoo_explore_queries.json` を `search_log` へ（実施したら出典ファイル名を記録）

## 6. 検証（実測をレポートへ）

1. 移行実行: 24/24が処理済み（保留・分類内訳つき）。件数とステータス内訳をSQLで実測
2. 照合確認: 「皐月賞2024に紐づく記事と馬の対応」がSQLで取り出し可能（実例をレポートに転記）
3. **冪等性**: 移行スクリプト再実行 → 新規0行
4. `pg_dump` → `/srv/nlp/dumps/` → 同一VMの使い捨てDBへリストア → 件数一致（バックアップ運用設計は段階4以降。この復元手順の確認のみ）
5. quadlet再起動（`systemctl restart`）→ データ保持
6. VM通常再起動 → PostgreSQL自動起動・データ保持

## 7. 禁止・境界

- v3への接続・DuckDBアクセス・参照データ取込（初期連携なしが確定方針）
- pgvector導入・Embedding生成・ベクトル保存
- 記事本文・`.env`・dump・PoC実データのGit commit
- k8s・OpenWebUI・EVO-X2・mini-v3への変更
- 実Yahoo検索（本タスクは検索基盤を使わない）
- 段階3（エージェント実行）の先取り

## 8. 完了・報告

- 実施レポート: `docs/reports/2026-11/2026-11-22_nlp_db_and_poc_migration_report.md`
- 記録必須: postgresイメージ tag+digest、migration SQL一覧、確定DDL、移行件数とステータス内訳、品質分類の根拠、冪等性確認、dump/restore実測、再起動確認、残件
- 対象ファイルのみ（`infra/nlp-vm/db/`、`infra/nlp-vm/quadlet/` 追加、`scripts/`、レポート）commit/push し、`origin/main` 反映を確認

## 9. 停止条件（該当時は推測で進めず報告）

- 段階2A未完了 / VM・5432へ到達できない
- postgresイメージ取得不可（ゲートウェイ経由のルーティング問題等）
- `g1_passages.jsonl` の構造がPoCレポートの記載と大きく異なる
- 引き継ぎ書 §6.2 の原則（過去版保持・種別区別・保留）とスキーマ両立不可
- JJコードがv3コード・公式表のどちらからも確認できない
