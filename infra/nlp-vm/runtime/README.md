# VM15の収集・閲覧を管理する

> **2026-11-27最新指示：本番の研究・試験データを清掃し、検証領域を分離する。** [実行指示書](../../../docs/instructions/2026-11/2026-11-27_nlp_production_cleanup_test_isolation_instruction.md)を先に読む。以下は分離前の配置と運用手順を含む。研究データを通常DBへ取り込む手順は再実行しない。試験は検証用DB・永続領域・プロファイルで行い、現在の文書更新を実機清掃完了と解釈しない。カバー率調査は終了し、本番の各開始例は別途の開始指示まで実行しない。

[競馬資料庫](http://192.168.0.14:8786/)で稼働状況、記事、実行履歴を閲覧する。VM15は `192.168.0.14`、管理はSSHユーザー `nlp`、以下はVM15の管理者シェルでのコマンド。データと運転はサーバにある。2026年11月27日の引き渡しでは、毎朝の予定は未登録、全名簿の計画と常駐解釈は未起動。下の開始例はユーザーが指定した処理の開始時に使う。

## 配置と読取り

| 構成 | 通常環境 |
|---|---|
| Hermes | `nlp-hermes.service`、通常プロファイル `/srv/nlp/hermes`（コンテナ内 `/opt/data`）、UID/GID 10000。固定Hermesの公式Cronを使う |
| 実装 | `/srv/nlp/runtime/app` → `/opt/keiba`。配備コミットは `/srv/nlp/runtime/RELEASE`。コード、設定、作業規約はエージェントから読み取り専用 |
| Skill | `/opt/data/skills/{keiba-search,keiba-interpret,keiba-coordinate}`。各Skillの `references/work-rules.md` に共通規約を複製。通常作業ディレクトリは `/opt/nlp-research` |
| 取得・解釈 | 通常PostgreSQLの `collection.versions / captures / interpretations`。取得IDから元URL・本文版・解釈入力が引ける。旧DBは `public` に保存。`observations` は一覧、版への経路、名簿、取得の観測 |
| 進捗とファイル | `collection.plans / work_items`。私有ファイルは `/srv/nlp/runtime/data` → `/var/lib/keiba`。本文、観測ID、名簿、方針、標本はこの領域。対象を途中で増減しても完了位置はDBに残る |
| 閲覧 | `nlp-dashboard.service`、VM15のLANアドレスのTCP 8786のみ。読取ロール `nlp_viewer` に必要な表・ビューのSELECTを付与。旧DBも別一覧で読める |
| 健康確認 | `nlp-review-health.timer` が5分ごとにモデル一覧、共用MCPのツール、公開月別一覧のHTTP状態、Cron用タイマー、常駐解釈の状態を記録。本文保存・モデル回答生成は行わない |

```bash
kt() { podman exec --user 10000:10000 nlp-hermes /opt/nlp-db/venv/bin/python -B /opt/keiba/jobs.py "$@"; }
hc() { podman exec --user 10000:10000 nlp-hermes hermes cron "$@"; }
hc list
hc status
systemctl is-active nlp-dashboard nlp-hermes nlp-review-health.timer
df -h /srv/nlp
du -sh /srv/nlp/runtime/data /srv/nlp/hermes
```

## 過去名簿

`history` は既存の `rosters/history-jra.json.gz` から馬・活動年・指定媒体の対象を固定する。SHA-256、対象馬数、期間は計画に保存する。同じ名簿・条件の作成は同じIDを返す。既定は馬名の媒体内検索とラジオNIKKEIの月別一覧。月別一覧の続きは観測IDとoffsetを使う。本文がある既知URLは再利用し、必要な再訪は `capture_url(revisit=true)`。更新版は同じURLに追加する。

```bash
# 開始指示後。IDの作成と実行は別操作。
id=$(kt history)
systemctl enable --now "nlp-plan@$id.service"
kt status "$id"
kt stop "$id"
# 現在の作業単位が終わり、状態がpausedになってから実行する。
systemctl disable "nlp-plan@$id.service"
kt resume "$id"
systemctl enable --now "nlp-plan@$id.service"
```

`--year 2021 --limit 2` はその年に活動した先頭2頭に限定できる。`--source blog --year 2018` は対象年の回顧検索、`--media-only --year 2021 --media radio` は指定年の月別アーカイブだけを追加する。個別に終わった失敗・一部失敗は `new_id=$(kt retry-failed "$id")` でその対象だけの別計画にできる。停止中の計画は起動時の `--respect-stop` が尊重する。作業中の異常終了は、同じIDから最後の未確定単位を再試行する。既知URL、保存版、解釈入力の照合により再利用する。

## 毎朝の収集

提案は毎日 **06:40 JST**。現在は本運用の次回予定なし。指定された当日と直近の開催リンクから登録・出馬表・結果を取り込み、前回の同段階の名簿と比較する。登録のない一般競走も出馬表を読める。新しく見つかった名前を当日の有限計画に追加する。新着はラジオNIKKEI・馬トク報知・競馬ブック・デイリーうま屋を用意した。親は追加の馬名、競走、媒体、再訪、切り上げを選ぶ。[朝のプロンプト](morning.prompt.txt)

```bash
# 毎朝の開始が指定された時だけ登録する。
hc create --name keiba-morning --deliver local --failure-deliver local \
  --skill keiba-coordinate --skill keiba-search --workdir /opt/nlp-research \
  '40 6 * * *' "$(cat /srv/nlp/runtime/work/morning.prompt.txt)"
systemctl enable --now nlp-hermes-tick.timer
hc list
hc status
```

タイマーは毎分公式 `hermes cron tick` を呼ぶ。登録スケジュールを評価してセッションを起動するのはHermes。CLIとCronそれぞれに `mcp-collection` とSkillを設定した。Cronセッションは日次計画の作成・一部処理・追加探索を担当し、残った対象は同じIDをサーバで処理する。同日の本運用計画は一つ。端末もブラウザーも閉じられる。変更には `hc list` で正確なIDを確認し、`hc edit --help`、`hc pause ID`、`hc resume ID` を使う。全名簿の起動や常駐解釈は別に指定する。

## 独立解釈

```bash
# 少数の指定版。IDはDashboardの「取得ID」。
id=$(kt interpret --capture "$capture_id")
kt run "$id"
kt status "$id"
# 常駐解釈の開始・停止が指定された場合。
systemctl enable --now nlp-interpret.service
systemctl disable --now nlp-interpret.service
```

保存時刻・掲載／更新表示・本文を渡し、Skill・モデル設定・正確な入力が一致する成功結果を再利用する。旧入力の成功も旧版の結果として読める。連続処理は新着優先で、同じ失敗入力は1日置く。他記事は処理可能。単一モデルのロックは記事単位。日次Cronと独立推論が同じロックを使う。全名簿・解釈は日次収集に区切りで順番を譲る。常用環境で手動のHermesセッションを起動する際も `podman exec --user 10000:10000 nlp-hermes flock /var/lib/keiba/local-model.lock hermes …` を用いる。

## バックアップ・復旧

11月27日の変更前バックアップは `/srv/nlp/backups/runtime-20261127/`。変更前DB、通常Hermesの設定とホーム、研究用2プロファイル、旧QuadletとHBAを保管した。DBと観測ファイル・名簿を対で戻す。秘密ファイルはホスト私有領域で管理し、バックアップの保管先も管理者限定とする。

```bash
# 保存時は書込処理を区切りで止め、状態を確認して実行する。
umask 077
dest="/srv/nlp/backups/collection-$(date +%Y%m%dT%H%M%S)"
mkdir -m 700 -p "$dest"
podman exec -u postgres nlp-postgres pg_dump -Fc keiba_nlp > "$dest/corpus.dump"
tar -C /srv/nlp -czf "$dest/runtime.tgz" runtime/data runtime/work runtime/RELEASE hermes hermes-runtime/config.yaml
sha256sum "$dest/corpus.dump" "$dest/runtime.tgz" > "$dest/SHA256SUMS"
podman exec -i -u postgres nlp-postgres pg_restore --list < "$dest/corpus.dump" > "$dest/catalog.txt"
```

復元はまず空の隔離DBへ `pg_restore --exit-on-error --no-owner --no-acl -d 復元先` を実行する。ロール・拡張を揃え、通常DBに切り替える前にURL・版・解釈・旧資料・計画件数とIDの対応を照合する。指定した復旧点のDBと同時点のファイルを私有の別ディレクトリへ展開し、所有者10000、Skill・設定、Cron状態、保存元を確認する。元のサービスや現在の正本を上書きする切替は復旧依頼の対象を確認して行う。DB保存前に残った観測ファイルは、書込を区切りで止めて `corpus.import_directory(Path("/var/lib/keiba"), "server-recovery")` で再照合できる。

## 再配備

WindowsのGitから配備アーカイブを作る場合は `git -c core.autocrlf=false -c core.eol=lf archive` を用いる。VM15上のシェル・設定・SkillにGitのblobと同じ改行を渡せる。

VM15の既存Hermes基盤・PostgreSQLと `nlp_app` を使用する。初回はDB変更前バックアップを取り、閲覧ロールをLOGIN権限のみで作り、`default_transaction_read_only=on` とする。パスワードはVM15内で生成し、`/srv/nlp/hermes-private/nlp_viewer`（10000:10000、0400）に置く。HBAの許可元はVM15自身の `192.168.0.14/32`。[HBA](../db/pg_hba.conf)・[通常DBの追加スキーマと権限](../db/migrations/002_collection_runtime.sql)

研究プロファイルを含む旧コンテナを退避してから、`/srv/nlp/runtime/research` 配下へ両方を復元してbindする。元の `keiba-routes-20261126/data` を私有の `runtime/data` にコピーし、初回だけ `corpus.import_directory(..., "research-20261126")` を使う。原文と解釈は元ID、進捗は観測IDで取り込む。稼働中のデータに古い名簿コピーを上書きしない。

```bash
# 固定版のGitアーカイブをVM15の私有ステージへ展開してから実行。
podman build -t localhost/nlp-runtime:20261127 -f infra/nlp-vm/runtime/Dockerfile infra/nlp-vm/runtime
bash infra/nlp-vm/runtime/install-files.sh "$release_commit"
systemctl restart nlp-hermes nlp-dashboard
systemctl enable --now nlp-review-health.timer
systemctl start nlp-review-health.service
```

配備スクリプトは既存の通常Skillと設定を時刻付きで退避する。運用タイマー・常駐解釈の有効化は上の個別手順による。閲覧はVM15のLANインターフェース `enp0s17`、送信元 `192.168.0.0/24`、宛先 `192.168.0.14:8786/tcp` への接続を許可した。
