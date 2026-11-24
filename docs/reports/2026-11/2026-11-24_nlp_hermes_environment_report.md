# 段階3B 実測レポート　VM15 の Hermes 研究環境

2026-11-24（JST）、VM15 `keiba-nlp` に Hermes CLI を配備し、H1〜H10 を受け入れた。通常 profile は SSH から利用できる待機状態。通常 DB の開始時・終了時とも全8表が0件。実 Yahoo 検索0件、競馬記事の取得・保存0件、収集スケジュール0件。実通信した公開試験ページは HTTPBingo の1件だった。

実装版 `756260c4fd6cae3fa8221086e9b181ea2670beec` を `origin/main` に push し、リモート SHA と稼働中の配備ファイルを照合した。操作方法・ツール引数・再現手順は [VM15 Hermes README](../../../infra/nlp-vm/hermes/README.md) に記載した。

## 照合した版と実機

- 作業開始時の最新 `origin/main` は指示書 `11dfee55edfec5e278848819d18a117b5049fca4`。検証基準 `5566b0237235a1a32ff6a6d6f5d92a6fdc7a63f9`、共用検索基準 `e33a4ae4451b6cb9aec502a8ce00d1ec84b93064`。旧作業ツリーの未追跡5ファイルと PoC を保全するため、独立 worktree で作業した。[指示書](../../instructions/2026-11/2026-11-24_nlp_hermes_environment_instruction.md)・[段階2B](2026-11-24_nlp_db_build_report.md)・[段階3A](https://github.com/kendo910x/OpenWebUI/blob/e33a4ae4451b6cb9aec502a8ce00d1ec84b93064/docs/reports/2026-11/2026-11-24_shared_search_redeploy_report.md)
- Ubuntu Server 24.04.5、2 vCPU、利用可能な物理メモリ総量 8,327,036,928 B、rootful Podman 4.9.3。`enp0s17` の固定 IP は `192.168.0.14`。SSH の ED25519 ホスト鍵 `SHA256:7ZfAYskmNrEPnyKLghiXN4oVp1PqmQ7BxtEgK9fTnzc` を照合。chrony の Leap status は Normal。開始・終了時の可用メモリは 7,770,898,432 → 7,639,162,880 B、対象ディスクの空きは 88,755,400,704 → 85,235,363,840 B。
- 公式安定版 `v0.22.2` のリリース commit は `d923a5eb487a17c0a68801bba9ef0f56c81040a8`。イメージ内 CI スタンプと一致した。調査時の `v0.23.3` は会話を gateway に渡すため、通常 CLI が直接 `AIAgent` を起動する版を選定した。[採用版の起動実装](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/hermes_cli/cli_agent_setup_mixin.py#L610)・[v0.23.3 の起動実装](https://github.com/NousResearch/hermes-agent/blob/v0.23.3/hermes_cli/cli_agent_setup_mixin.py#L641)
- 公式 index は `sha256:36099926da316742423544e055d4734777105ffe6341873af5459b957d0c2919`。Dockerfile の linux/amd64 子 manifest は `sha256:a11574b7fe8e1631d7d88d556677dac693bc058abf558cdeb899155688c1bf05`。base の image ID は `sha256:02e7aa0e84123fa0e9b22686e7a2bfb7d85fd59821d4d28812a3e07f3061cf41`。[公式リリース](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.2)
- 派生 image は `localhost/nlp-hermes:0.22.2-stage3b`、実 ID は `sha256:e71b1822fb1cccf4a6a43c8a22d90809650d200e26b8d4025dd01abbfe09dadd`。x86_64・CPython 3.14.7。公式 Hermes 側の MCP SDK は 2.0.0、独立 venv 側は MCP SDK 1.30.0・psycopg/psycopg-binary 3.3.9。固定した31 wheel すべてのハッシュを build 時に検証し、配備後に31件の実インストール版を再照合した。

## 受入結果

| ID | 判定 | 実測 |
|---|---|---|
| H1 | PASS | `podman inspect` で host network、privileged=false、公開ポート0、memory=3,221,225,472 B、CPU quota/period=150000/100000。Hermes CLI と stdio は 10000:10000。アプリ秘密・通常設定は読取専用、実行コードと固定契約は書込不可。マウントは専用の永続領域、通常設定、アプリ秘密の3つ |
| H2 | PASS | Quadlet の生成 unit・multi-user.target のリンク、起動・停止・再起動後の SSH 経由 CLI を確認。公式の s6 初期化後、非rootの `sleep infinity` で待機。既存と同じ TCP/UDP 待受集合、gateway/cron の稼働0。PostgreSQL は接続受付、demo・DB は開始時と同じコンテナ ID |
| H3 | PASS | 実 CLI の応答モデルは `halogen-qwen3.8-flash-next`。`/v1/models`、`/props`、4スロットの `n_ctx` すべてが設定と整合。実効閾値 131,072 / 262,144。試験用の低い閾値で、標準圧縮器のローカル補助要求と縮約を実測 |
| H4 | PASS | 実セッションで `mcp__shared__fetch_page` 1呼出。`final_url=https://httpbingo.org/html`、`truncated=false`。footer は `[STATUS] status=ok http=200 retry=0 waited=0.0s`、観測 13:52:15 JST。通常 profile の公開一覧に Yahoo は含まれない |
| H5 | PASS | 空の使い捨て DB に stdio MCP で10機能・44呼出。本文・同一版の再送・新版・欠損、同名別馬、確定レース ID 再利用、Unicode 区間・重複引用、複数対象と phase 訂正、FK 失敗のロールバック、run 再開、ページ境界を検証。全8表を独立 SQL で照合 |
| H6 | PASS | 実 Hermes が `save_run → save_article → save_targets → get_article → save_run → get_runs` の6呼出。記事 ID、全文 unit ID、原文、参照結果、確定した進捗が実レコードと一致 |
| H7 | PASS | 試験 profile の `skill_manage` で無害な試験 Skill を作成し、`AMBER` を `COBALT` に更新。`memory(add)` で試験 Memory を保存。個別承認なし。Skill ファイル、Memory ファイル、SQLite のセッションと tool 結果を照合 |
| H8 | PASS | 通常停止後の再作成は1回。コンテナ `73a1763d6029` → `5bf4532b4439`、image ID 同一。既存5セッションの ID と各メッセージ数（計31件）が一致。Skill・Memory・試験設定はファイルごとの SHA-256 が一致。新セッションの `skill_view` と `get_runs` で更新済み Skill と保存した進捗を取得 |
| H9 | PASS | 使い捨て DB、臨時 HBA、試験 profile、試験スクリプト・s6 の監視枠・同枠のログとキャッシュを回収。通常 profile の試験 Skill・Memory・セッションとスケジュールは0。Skills/Memory の書込可・設定の読取専用を確認。通常の DB MCP 経由で run 一覧0件 |
| H10 | PASS | 実装の Git 正本と、VM ホスト上8ファイル・稼働コンテナ内6ファイルの SHA-256 が一致。README、固定依存、Quadlet、契約、試験は実装 commit、本書はその後続のレポート commit。段階3Cの判断事項を末尾に記録 |

### 圧縮の測定範囲

Halogen の LAN API は認証不要。`custom` の主・補助モデルを `http://192.168.0.13:8731/v1` に固定し、`fallback_model=[]` を確認した。割合 `0.50` だけではこの版の標準圧縮器は 196,608 を返したため、同版が対応する `compression.threshold_tokens=131072` を追加し、配備した設定を読み直して実効値 131,072・保護 tail 20 を検証した。

試験 profile の標準圧縮器に閾値900・保護 tail 3 を指定し、合成履歴24メッセージ、推定3,194トークンで通常の発火条件を通過した。実際の補助要求は Halogen の `/v1/chat/completions` に1回、HTTP 200。`method=llm_summary`、`fallback_used=false`、約70秒。結果は4メッセージ・推定2,162トークン（差1,032）。測定対象は短い履歴による基本動作であり、最大長までの連続運転・枯渇耐性は未測定。[固定版の圧縮器](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/agent/context_compressor.py)

### ツール公開と実セッション

通常・試験 profile で標準の MCP discovery とモデル向け schema 生成を実行し、次の16件を確認した。固定契約の見出しが全試験セッションの保存済み system prompt に入った。共用ページの実呼出前に HTTPBingo の用途と robots の禁止先 `/deny` を照合した。[HTTPBingo](https://httpbingo.org/)・[robots.txt](https://httpbingo.org/robots.txt)

| 種類 | 確認した公開名 |
|---|---|
| DB | `mcp__nlpdb__find_articles`、`mcp__nlpdb__get_article`、`mcp__nlpdb__save_article`、`mcp__nlpdb__find_horses`、`mcp__nlpdb__save_horse`、`mcp__nlpdb__find_races`、`mcp__nlpdb__save_race`、`mcp__nlpdb__save_targets`、`mcp__nlpdb__get_runs`、`mcp__nlpdb__save_run` |
| 外部取得 | `mcp__shared__fetch_page` |
| 標準機能 | `skills_list`、`skill_view`、`skill_manage`、`memory`、`session_search` |

初回はテスト用 CLI の `-t mcp-shared` 指定で server が認識されず、tool 呼出は0件だった。profile の設定をそのまま使ったセッションで1回の取得が成立した。DB セッションの合成記事 ID は `da1207f9-e7bc-43dc-88e6-569889ce7ef4`。取得種別 `excerpt`、全文 unit `[0,15)`、未解決の馬・レースのラベルと `pre` を保存した。run `00000000-0000-4000-8000-000000000031` は `completed`、進捗 `{"indexed":1}`。記事保存・記事参照・進捗参照・再作成後の進捗参照の4応答を DB の値と照合した。

Skill 試験では CLI の toolset を限定した回で Memory だけが保存された。通常の公開設定で再実行すると、74文字の Skill 説明が標準の60文字制限で拒否され、Hermes 自身が短くして作成に成功し、続けて更新した。再作成前後の Skill ファイル SHA-256 は `d1ed20556e6523c3598b436cd025851b31f4c7dd77951912f838ee2d669316d9`。Memory の SHA-256 は `9a508e4e61604af1a1e0098f3755ac4d80305440bdaa31423623961fa85180ab`。管理者による試験 Skill/Memory の手書きは0件。生ログ・セッション本文・取得ページ本文は Git に含めていない。

## DB・VM・開発PCの保全

`nlp_app` で採用イメージから通常 DB に接続し、`inet_client_addr()=192.168.0.14`、`current_database()=keiba_nlp`、`current_user=nlp_app` を確認した。既存 LAN 行が利用でき、通常 DB の HBA 追加は0行。試験 DB だけに `hostnossl keiba_nlp_stage2b_test nlp_app 192.168.0.14/32 scram-sha-256` を一時適用した。開発中に試験ハーネスの引数名衝突を修正し、タスクが作った DB の OID、所有者、接続0を照合して空の fixture から再測定した。

| 表 | 通常開始 13:34 JST | H5 合成全件照合時 | 通常終了 14:03 JST |
|---|---:|---:|---:|
| articles | 0 | 3 | 0 |
| collection_runs | 0 | 1 | 0 |
| horses | 0 | 2 | 0 |
| races | 0 | 2 | 0 |
| text_units | 0 | 4 | 0 |
| unit_targets | 0 | 3 | 0 |
| embedding_configs | 0 | 0 | 0 |
| embeddings | 0 | 0 | 0 |

H5 の後に H6 の合成1記事・1全文 unit・1 target・1 run を試験 DB に追加した。回収前にアプリ秘密との完全一致を Hermes の永続領域内の通常ファイル713件で検査し、一致は0件。臨時 HBA 除去・reload 後は試験 DB への接続が HBA で拒否され、HBA parse error は0件。所有者 postgres、OID `18267`、接続0を確認して試験 DB を削除し、不存在を確認した。HBA の開始・終了 SHA-256 は `1bdb2a03ea220d99967c9ca4094a6653684332094506ee7a3d6cec1810964755`。

通常 DB は PostgreSQL 16.16 / pgvector 0.8.7。8表の内容を集約した開始・終了ハッシュは `9f8704b8d65fa84766d90672dfc8e106b167935f1d61dbda06384a4dcbf00c2b`、catalog fingerprint は `2a303dd483dd85e517a71b60870e7d06b1151da55f39b44b629aafb38a863b3e` で各々一致した。既設 `nlp-postgres` は `4c5c29a9f459`、`nlp-demo` は `c33dfb5e58f2` のまま稼働。UFW は LAN の22/tcp・5432/tcp のまま。ESXi、Talos、OpenWebUI、EVO-X2、v3 への設定変更・再起動は0件。開発 PC の未追跡5ファイルの SHA-256、PoC 6ファイル・81,374 B の時刻・サイズ集約と個別内容ハッシュを再照合した。

## 配備物と引渡し

ホストの build 入力6ファイル、通常設定、Quadlet の8ファイルを Git blob と照合した。さらにコンテナ内の MCP 3ファイル、lock、固定契約、通常設定の6ファイルを同じ版と照合した。代表値は次のとおり。

| ファイル | SHA-256 |
|---|---|
| `config.yaml` | `294e79b738cf01b4153e093e55644a8cb257f9676c20b2d032b7b9a9e224b495` |
| `requirements.lock` | `4218a43895e62ec51ae09c02a7a0f8c484373c6c794857d1aa9e9112a640a7b8` |
| `nlp-hermes.container` | `58fa81422124dd91910d8fb2ec41a16ce7f2cb45c71e5123a981e0bcb7d4eb2e` |

段階3Cの判断事項は、Hermes に与える最初の研究課題、利用条件を満たす検索経路、実際の探索で Skill をどう作成・改善するか。実収集、長期運転、Embedding・予測力の評価は後続の検証対象となる。
