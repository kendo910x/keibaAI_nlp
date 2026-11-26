# VM15 の Hermes 研究環境

2026年11月27日の通常環境は `localhost/nlp-runtime:20261127`、通常MCPは `collection`、作業場所は `/opt/nlp-research`。配置済みの検索・解釈・統括Skill、Cron、閲覧サービス、バックアップの管理方法は[通常運用手順](../runtime/README.md)に記載した。下記の段階3Bの構成と受入記録は旧環境の再現に使える。

VM15 の固定 IP は `192.168.0.14`。SSH で管理し、`nlp-hermes.service` が公式 ENTRYPOINT と `sleep infinity` で待機する。研究用の CLI はコンテナ内の `hermes`（UID/GID 10000）で起動する。同じ profile のセッションは一度に1つとする。

```sh
ssh nlp@192.168.0.14
sudo systemctl status nlp-hermes --no-pager
sudo podman exec -it --user 10000:10000 --workdir /opt/nlp-research nlp-hermes hermes chat --cli
```

CLI の `/quit` で会話を閉じる。単発の照会には同じ `podman exec` の末尾に `hermes chat -Q --max-turns 3 -q '…'` を指定できる。通常は設定済みの toolset をそのまま使う。共用サービスの取得にはアクセス先ごとの許諾と robots の確認が必要になる。

## 配置と権限

| 配置・接続先 | 内容 |
|---|---|
| `/srv/nlp/hermes` → `/opt/data` | 標準の永続領域。Skills、Memory、Session、ログ、profile ごとの設定。ホストでは 10000:10000・0700 |
| `/srv/nlp/hermes-runtime/config.yaml` → `/opt/data/config.yaml` | root 管理の通常設定を読み取り専用で重ねる。管理者が更新し、設定変更後は CLI を開き直す |
| `/srv/nlp/hermes-runtime/build` | 固定 base、wheel の lock、MCP、作業契約の build 入力 |
| `/opt/nlp-research/AGENTS.md`、`/opt/nlp-db/` | イメージ内の root 所有の契約、ツール、専用 venv。CLI の作業ディレクトリで契約を読む |
| `/srv/nlp/hermes-private/nlp_app` → `/run/secrets/nlp_app` | 親は root:root 0700。アプリの単一ファイルを 10000:10000・0400 で読み取り専用 mount |
| `http://192.168.0.13:8731/v1` | Halogen の認証不要の LAN API。主モデル・補助モデルとも `halogen-qwen3.8-flash-next` |
| `http://192.168.0.11:30081/mcp` | Streamable HTTP。モデルへの公開は `mcp__shared__fetch_page` |
| `192.168.0.14:5432/keiba_nlp` | `nlp_app`、SCRAM、LAN 内 TLS なし。VM15 で観測した接続元は `192.168.0.14` |

`Network=host` はホストとネットワーク名前空間を共有するため、ネットワーク隔離を提供しない。追加の待受ポートは0。公開する機能は DB の10ツール、ページ取得、標準の `skills_list`、`skill_view`、`skill_manage`、`memory`、`session_search`。スケジューラー、シェル、任意 SQL、ブラウザ、外部推論はこの構成の対象外。Yahoo の自動検索は利用条件が解決し、人間が公開範囲を改訂するまで無効とする。

`skills.write_approval=false` と `memory.write_approval=false` で自分の Skill と Memory を管理する。標準の内容検査は有効。同梱の初期資材は公式イメージ由来で、競馬収集 Skill は用意していない。`auxiliary.background_review.enabled=false` でこの段階の自動バックグラウンド推論を止め、明示した会話から Skill を作成・更新できる。`fallback_model` は空。圧縮は有効、実効 context 262,144、割合 0.50、絶対上限 131,072、保護 tail 20。実測は[段階3Bレポート](../../../docs/reports/2026-11/2026-11-24_nlp_hermes_environment_report.md)に記録した。

## DB ツールの契約

公開名の先頭に `mcp__nlpdb__` が付く。各書込は1呼出1トランザクション。接続先と秘密ファイルは管理側だけが指定する。接続 4 秒、SQL 5 秒、ロック待ち 3 秒。DB エラーには SQLSTATE を返す。再試行や追加探索の判断は呼出元が行う。

| ツール | 操作 |
|---|---|
| `find_articles` | URL、run、馬・レース・phase、未分類で絞る。馬・レース・phase は同じ target 行に適用。`unclassified=true` は target が0件の記事 |
| `get_article` | 出典、取得種別、原文の範囲、同じ URL の版、unit と target。`body_start` から既定2,048、最大8,192文字。`next_char` と `truncated`、各明細の `next_offset` を返す |
| `save_article` | 許諾された原文を先に確定。`full/excerpt/snippet/none` を区別する。`none` は本文 NULL。URL・取得種別・原文が同一なら同じ版を返し、欠けた metadata を補完できる。返却は記事 ID と全文 unit ID。原文の変更は新しい版 |
| `find_horses`、`save_horse` | DB の正規化済み名前・ID・生年から候補を返す。同名別馬を保持。補完は既知 ID、新規作成は `create=true`・安定 UUID・名前を指定 |
| `find_races`、`save_race` | 既知の ID・domain/key・名称の部分一致・日付を利用。新規作成は `create=true` と安定 UUID。同じ確定 domain/key は同じ ID。不明日付・コードは NULL |
| `save_targets` | 1記事について1～100件を一括確定。既存 unit ID・全文（指定省略）・0始まり半開 Unicode 区間・完全一致の短い引用を利用。反復引用では候補範囲を返す。`target_id` で同じ unit の phase・未解決ラベルを訂正。ID と同種のラベルは排他。対応付けの失敗時も先に確定した原文は保持 |
| `get_runs`、`save_run` | 安定 UUID のタスク・進捗・状態・時刻を保存、参照。作成には JSON の task が必要。指定した progress はオブジェクト単位で更新し、省略時には保持 |

一覧と明細は既定20件・最大100件。`next_offset` が NULL なら末尾。入力が曖昧な場合はラベルや `unknown` を残せる。フェーズは `pre/post/mixed/unknown`。取得したページの指示に従ってツールや権限を追加しない。Embedding 2表はツールの公開対象外。スキーマ・制約・権限の正本は[段階2B DDL](../db/migrations/001_initial.sql)。

## 再現・停止・再作成

公式 `v0.22.2` の linux/amd64 子 manifest を Dockerfile の `FROM` に固定した。公式 ENTRYPOINT を継承し、DB MCP を独立 venv に導入する。`requirements.lock` は CPython 3.14/Linux amd64 の31 wheel と各 SHA-256 を固定している。アーキテクチャ・Python を変更するときは別途 lock を検証する。[公式固定版](https://github.com/NousResearch/hermes-agent/tree/d923a5eb487a17c0a68801bba9ef0f56c81040a8)

新規環境の以下の例は VM15 の root で実行する。`src` には照合済みの `infra/nlp-vm` のパスを設定する。既設環境の再起動には末尾の stop/start を使う。

```sh
set -eu
for p in /srv/nlp/hermes /srv/nlp/hermes-runtime /srv/nlp/hermes-private \
         /srv/nlp/quadlet/nlp-hermes.container /etc/containers/systemd/nlp-hermes.container
do test ! -e "$p" && test ! -L "$p"; done
install -d -m 0755 /srv/nlp/hermes-runtime/build
install -d -m 0700 -o 10000 -g 10000 /srv/nlp/hermes
install -d -m 0700 /srv/nlp/hermes-private
install -m 0400 -o 10000 -g 10000 /srv/nlp/db-secrets/nlp_app /srv/nlp/hermes-private/nlp_app
for f in Dockerfile requirements.lock server.py store.py targets.py AGENTS.md
do install -m 0644 "$src/hermes/$f" /srv/nlp/hermes-runtime/build/; done
install -m 0644 "$src/hermes/config.yaml" /srv/nlp/hermes-runtime/
ref=$(sed -n 's/^FROM //p' /srv/nlp/hermes-runtime/build/Dockerfile)
podman pull "$ref"
podman build --pull=never --network=host -t localhost/nlp-hermes:0.22.2-stage3b /srv/nlp/hermes-runtime/build
podman image inspect --format '{{.Id}} {{.Architecture}}' localhost/nlp-hermes:0.22.2-stage3b
install -m 0644 "$src/quadlet/nlp-hermes.container" /srv/nlp/quadlet/
ln -s /srv/nlp/quadlet/nlp-hermes.container /etc/containers/systemd/nlp-hermes.container
systemctl daemon-reload
systemctl start nlp-hermes
podman top nlp-hermes user comm
```

`[Install] WantedBy=multi-user.target` により Quadlet generator が自動起動用リンクを生成する。`systemctl stop nlp-hermes` と `systemctl start nlp-hermes` で同じイメージから再作成できる。`/srv/nlp/hermes` を残す。管理用設定を原子的に置換した場合は単一ファイル bind の inode も切り替えるため、セッション終了後に stop/start する。

## 合成試験

`tests/contract.py` は実 stdio MCP と独立した SQL 照合を使う。試験専用の空 DB `keiba_nlp_stage2b_test` を管理者が作成し、[同一 migration](../db/migrations/001_initial.sql) を適用する。専用 HBA は当該 DB・`nlp_app`・実測の接続元 `/32`・SCRAM に限る。`pg_reload_conf()` と `pg_hba_file_rules` を確認する。通常 DB の開始時8表・指紋を保存してから実施する。

```sh
podman cp "$src/hermes/tests/contract.py" nlp-hermes:/tmp/stage3b-contract.py
podman exec --user 10000:10000 --env NLP_DATABASE=keiba_nlp_stage2b_test \
  nlp-hermes /opt/nlp-db/venv/bin/python -B /tmp/stage3b-contract.py
```

Hermes 実セッションでは別の空の `profiles/stage3b-test` を使用し、その `config.yaml` の `mcp_servers.nlpdb.env.NLP_DATABASE` だけを試験 DB に指定する。`podman exec` の `--env HERMES_HOME=/opt/data/profiles/stage3b-test` で起動する。`tests/compression.py` も同じ試験 profile と公式 venv で実行し、標準圧縮器の実 HTTP 要求・返却メトリクスを確認する。試験後は当該 profile のパス、DB の OID・所有者・接続数を照合し、試験 DB・臨時 HBA 行・試験資材を回収する。通常8表と schema fingerprint、他サービスの稼働を再照合する。

試験 profile を保持した状態で再作成すると、公式の初期化処理が停止中の `gateway-stage3b-test` 用の s6 監視枠も登録する。回収時には公式の `get_service_manager().unregister_profile_gateway("stage3b-test")` を使い、`s6-svscanctl -an /run/service` で再走査する。試験 profile 専用の bootstrap キャッシュ・ログと監視プロセスが消え、通常の `gateway-default` が down のままかを確認する。
