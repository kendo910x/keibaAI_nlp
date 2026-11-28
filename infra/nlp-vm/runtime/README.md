# VM15の本番収集と閲覧

VM15はJRA過去名簿の有限収集と、毎朝06:40 JSTの日次収集を同じ本番DBで実行する。2026年11月28日に運転を開始した。端末を閉じても、サーバ上のsystemdとHermes Cronが続行する。記事の独立解釈・馬別要約は後日の指示まで保留。[開始時の実測・検証](../../../docs/reports/2026-11/2026-11-28_nlp_production_collection_report.md) ・ [本番Dashboard](http://192.168.0.14:8786/) ・ [原文検索](http://192.168.0.14:8786/articles)

## 状態を見る、止める、再開する

VM15の管理シェルで、目的に合うコマンドを一つ選ぶ。

| 操作 | VM15のコマンド | 結果 |
|---|---|---|
| 現在の状態を見る | `sudo nlp-collectionctl status` | 過去・日次のID、入力、初回探索済み・残る頭数、残る候補、保存・再利用、媒体待機、最後の作業完了、Cronの次回予定を表示 |
| 過去収集だけ止める | `sudo nlp-collectionctl pause-history` | 停止意図をDBに書き、短い作業の保存区切りで過去ワーカーを止める。日次は運転を続ける |
| 過去収集を再開する | `sudo nlp-collectionctl resume-history` | 同じ名簿・計画IDの未完了位置から再開。全停止中はその指定が優先される |
| すべての収集を止める | `sudo nlp-collectionctl pause-all` | 過去・日次・子処理を止め、朝予定を一時停止。DBと閲覧画面は利用可能 |
| 全体の運転を再開する | `sudo nlp-collectionctl resume-all` | 朝予定と未完了の計画を有効化する。当日06:40以降は当日分の不足を補う。以前に指定した過去だけの停止は個別に解除できる |

停止要求の時刻は `control.changed_at`、停止成立は対象計画の `state=paused` と作業中の有無で確認する。予定済みの再試行は媒体名・理由・待機期限を持つ。共有通信・ブラウザー・空き容量の一時障害は全体で待機し、DB接続障害でプロセスが終了した場合も同じ作業を再開する。すべてのワーカーが同じ永続停止指定を参照する。

## 毎時の稼働確認

Dashboardホームの「原文収集」で現在の運転状態、全経路・媒体別の再試行時刻と理由、直近の毎時監視を読める。ロックを持つ日次ワーカーへ過去収集が順番を譲っている間は、過去計画に「日次収集を優先して待機」と表示する。計画詳細の「直近の作業完了 JST」は保存や候補処理が確定した時刻で、「計画の最終状態更新 JST」には再試行時の状態変更も含まれる。

VM15の既存の `nlp-review-health.timer` は毎時最初の点検で、本文版数・最終保存時刻、各稼働計画の完了・残り・既知URL再利用、最終作業完了を記録する。共通障害、ワーカー中断、実行可能な作業が1時間以上進まない状態を「要確認」とする。手動停止、媒体待機、進行している日次へ過去が順番を譲る時間を区別する。最新値はDashboard、時系列はVM15の `sudo journalctl -u nlp-review-health.service --since today -g collection_progress` で確認できる。開発PCが閉じていてもVM側の記録は続く。このほか、Codexの毎時監視がDashboard・CLIとサーバ記録を照合する。

## 計画と保存先

| 用途 | 本番 | 旧試験の隔離先 |
|---|---|---|
| DB・ロール | `keiba_nlp` ／ `nlp_app`・`nlp_viewer` | `keiba_nlp_trial` ／ `nlp_trial_app`・`nlp_trial_viewer` |
| 原文・観測・再開データ | `/srv/nlp/runtime/data` と本番DB | `/srv/nlp/trial/data` と検証DB。試験資料は撤去済み |
| Hermesプロファイル | `/srv/nlp/hermes` | `/srv/nlp/trial/hermes`。検証ワーカー停止 |
| 閲覧 | [本番8786](http://192.168.0.14:8786/) | [検証8787](http://192.168.0.14:8787/) |

[過去計画](http://192.168.0.14:8786/run/0c09da69-a0a8-5a9d-9b50-c50060cf82da)の入力は `/srv/nlp/runtime/work/inputs/history-jra.json.gz` の54,591頭。同名の入力馬も馬IDを保持する。初回探索済み馬と残る馬、保存済み一覧の未取得候補、実リンクから追加した次ページを分けて読む。全名簿および後続仕事が落ち着くまで過去計画は進行中となる。日次は以後も続く。[当日の日次計画](http://192.168.0.14:8786/run/a054e74c-9b53-597f-8fc3-f73ad2a10f13)

過去の常設unitは `nlp-plan@0c09da69-a0a8-5a9d-9b50-c50060cf82da.service`。Hermesによる過去の探索判断は `nlp-history-choice.service` で行う。日次はネイティブCron `keiba-morning`（`949b8a4e3644`、`40 6 * * *`）。`nlp-hermes-tick.timer` が毎分予定を評価し、`nlp-daily-raw.service` が残る候補を消化する。同じJST日の再呼出しは同じ計画IDを返す。長い停止からの復帰時は最新の開催、保存した前回の一覧と重複期間、未完了の仕事から新着を拾う。

原文を読むには本番の「記事を探す」から見出しを選ぶ。詳細に保存本文、公開部分のみかどうか、掲載・更新表示、取得時刻、元記事へのリンクがある。計画詳細で発見経路を確認できる。掲載日不明の資料も保存し、後の解釈用に区別する。将来の処理順は当週に関わる資料を先に、続いて掲載日の新しいものから扱う。

## 配備と障害復旧

配備版はホストの `/srv/nlp/runtime/RELEASE` に記録する。アプリは `/srv/nlp/runtime/app`、管理者配備の設定・プロンプトは `/srv/nlp/runtime/work`。各コンテナは読取専用の `/run/keiba/database` で対象DBを照合する。通常の収集MCPは計画にひも付く入口を使い、旧MCPは読取専用。サーバ設定 `article_interpretation=false` がMCP・CLI・常駐解釈の起動をガードする。本文版と発見経路は別に記録するため、複数の馬や日次から同じ記事に到達しても同じ本文版を使える。

再配備には固定したGit版を使う。Windowsでアーカイブを作成するときは `git -c core.autocrlf=false -c core.eol=lf archive` を使う。VM15に展開した版で `bash infra/nlp-vm/runtime/install-files.sh "$release_commit"` を実行する。DB変更がある場合はその版のマイグレーションを対象DBへ適用する。更新前のSkill・設定のみを私有領域へ保持する。現地Skillの変更保護が表示された場合は、採用する差分をGitと配備先で照合する。再配備時は元の運転・停止状態を記録し、必要なワーカーとDashboardに新しいコードを読み込ませてから元の状態に戻す。

## 容量とバックアップ

`df -h /srv/nlp` が書込み先の空き容量を示す。収集は新しい作業の前に空きを確認し、512 MiB未満なら全経路を待機にする。運用中のバックアップには既存の手動手順を使う。運転状態を控えて書込みを区切りで停止し、DB・ファイル・設定を同じ復旧点として管理者専用の領域に保存する。

```bash
umask 077
dest="/srv/nlp/backups/collection-$(date +%Y%m%dT%H%M%S)"
mkdir -m 700 -p "$dest"
podman exec -u postgres nlp-postgres pg_dump -Fc keiba_nlp > "$dest/corpus.dump"
tar -C /srv/nlp -czf "$dest/runtime.tgz" runtime/data runtime/work runtime/RELEASE hermes hermes-runtime/config.yaml
sha256sum "$dest/corpus.dump" "$dest/runtime.tgz" > "$dest/SHA256SUMS"
podman exec -i -u postgres nlp-postgres pg_restore --list < "$dest/corpus.dump" > "$dest/catalog.txt"
```

復元確認は別の空DB・ファイル領域で行い、復旧点の版・取得・計画・再開位置、Cron、設定と所有者を照合する。旧検証資料の復元経路は11月28日に撤去した。[11月27日以前の手順書の履歴](https://github.com/kendo910x/keibaAI_nlp/blob/2ac690e271d9b7aeffb9bb2ebeef15ee58b3ac67/infra/nlp-vm/runtime/README.md)
