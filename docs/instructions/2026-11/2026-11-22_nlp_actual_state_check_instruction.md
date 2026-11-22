# KeibaAI NLP 実機状態確認 指示書（Hermes停止後・調査のみ）

作成日: 2026-11-22（JST）  
実行担当: 開発PC上のCodex  
対象repo: `kendo910x/keibaAI_nlp`。関連する共用検索の確認先は `kendo910x/OpenWebUI`。  
成果物: `docs/reports/2026-11/2026-11-22_nlp_actual_state_check_report.md`

## 1. 目的と終了地点

Hermes Agentによる構築作業が停止した後の**実機・ローカルファイル・稼働サービスの現在状態を、証拠付きで確定する**。ログ上の到達点を現在の実測と照合し、次の担当が既存作業を失わずに再開できる材料を残す。

今回回答する問いは次の6点。

1. NLP VMは実在し、現在どの電源状態・起動段階にあるか。Ubuntu導入が完了しているか。
2. 実VMX・接続中seed・ゲストが採用した設定は何か。ローカルテンプレートとどこが違うか。
3. 未コミットの構築用ファイルとGit管理外のPoCデータは残っているか。
4. インストーラー停止の原因を現物でどこまで確認できるか。
5. 残存プロセス、共用検索サービス、Hermes/LM Studioの接続設定は現在どうなっているか。
6. 次の復旧作業の対象と、着手前に必要な追加判断は何か。

**調査レポートをGitで引き渡したところで終了する。** VM構築の再開、設定修正、DB構築、PoC移行は今回実施しない。既存の構築指示書は照合資料として読み、そこに記載された変更操作を今回の調査で実行しない。

## 2. 開始前の参照と基準版

まず対象repoの `AGENTS.md` と、対象ディレクトリに追加の規約があればそれを読む。OpenWebUI側を確認する際は同repoの `AGENTS.md` も読む。

| 資料 | repo内パス・参照先 |
| --- | --- |
| 全体引き継ぎ | `docs/handoffs/2026-11/2026-11-22_data_accumulation_handover.md` |
| 最新の配置・範囲 | `docs/design/2026-11-22_nlp_infrastructure_placement.md` |
| 段階2Aの完了条件 | `docs/instructions/2026-11/2026-11-22_nlp_vm_build_instruction.md` |
| 段階2Bの予定 | `docs/instructions/2026-11/2026-11-22_nlp_db_and_poc_migration_instruction.md` |
| 検索基盤の既報 | OpenWebUI `docs/reports/2026-11/2026-11-22_shared_search_exposure_report.md` |
| K8s接続方法 | OpenWebUI `docs/kubernetes_access.md` から案内される既存の接続正本 |
| 同一ESXiでの前例（必要時のみ） | `C:\Users\kendo\home-gateway\docs\reports\2026-11\2026-11-17_ubuntu_gateway_build_and_isolated_validation_report.md` |

本指示書追加前の確認基準:

- KeibaAI NLP: `05e30b267cdf48a473fa83a65bef327224347393`
- OpenWebUI: `cd68ec56267eccee87abf1f740df3eed3fd7eabb`

これらへの巻き戻し指定ではない。現在のHEAD・origin/mainと差分を記録し、後続変更があればそれを尊重する。作業ツリーを更新するための `pull` は不要。必要なら `git fetch origin` で参照だけ更新し、`git show origin/main:<path>` 等で読む。未コミット作業を上書きしない。

最新方針は、ESXi専用VM、Podman＋Quadlet、PostgreSQL、初期v3連携なし、Embeddingは後工程、定期バックアップ運用の設計は後続である。今回これらを再設計しない。

## 3. 既知情報と、まだ実機で確認していない点

以下は2026-11-22のGitHub・Hermesログから得た**調査の手掛かり**であり、現在状態の断定ではない。違いがあれば今回の実測を優先する。

| 対象 | 既知情報 |
| --- | --- |
| 開発PCのNLP repo | `C:\Users\kendo\keiba_nlp` |
| ESXi | `192.168.0.5`、既存SSH接続名 `esxi-divroom` |
| 新VM | VMID **15**、名前 **keiba-nlp**、`[datastore1] keiba-nlp/keiba-nlp.vmx` |
| 新VMの予定構成 | 2 vCPU・8GB・100GB thin・EFI・仮想HW14・E1000・ポートグループ `VLAN 101` |
| 新VMの予定IP | `192.168.0.14/24`、管理ユーザー `nlp`。SSH成功は過去ログで未確認 |
| 既存VM | VMID14は `ubuntu-gateway`。新VMと取り違えない |
| 最後の電源操作 | 16:37:17 JST、VMID15をOFF→ON。その後16:39:12に同じインストーラーエラーの報告 |
| エラー | `neither identity nor user-data provided` |
| seedの最後の変更 | 実VMXは `sata0:1` のVFAT由来VMDKへ変更。ローカルVMXテンプレートはseed ISO接続のままの可能性 |
| ローカル構築物 | 下記5ファイルの作成記録あり。段階2Aでcommit/pushした記録なし |
| 共用検索 | `192.168.0.11:30081/mcp`。既報ではPod 2/2、Python MCPクライアントの実呼出成功。Hermes/LM Studio自身の実呼出は未確認 |
| Hermes停止 | 16:41:24、`Prompt used 262132 of 262144 context tokens; no room to answer`。元の長い会話をそのまま再投入する必要はない |

## 4. 実施範囲

### 許可する確認

- 既存の接続設定・認証を用いた、開発PC・ESXi・対象VMへの読み取り目的の接続。対象が明確な既存Webコンソールの閲覧も可。
- 既存のKubernetes接続情報による、対象Deployment/Pod/Serviceの読み取り。
- 指定宛先への少数の疎通確認、検索サービスのhealth確認、条件が整う場合のMCP初期化・`tools/list`。
- 既存ファイルの属性・hash・構造確認、対象ログの限定読取り。必要な小さい証拠ファイルを開発PCの非Git一時領域へコピーして解析すること。
- 調査レポートの作成・そのレポートだけのcommit/push。必要なGit参照更新・報告書用の一時worktree作成。

### 今回行わない操作

- VMの電源ON/OFF・reset・再起動・再登録・削除・snapshot、VMX変更、ISO/seedの接続変更、インストール再実行。
- ゲストディスクのmount・修復、パッケージ導入、サービスのstart/stop/restart/reload、FW/ネットワーク/認証設定の変更。
- Pod再作成、Deployment/Service/Secret変更、Hermes/LM Studioの再起動・設定変更、残存プロセスのkill。
- DB作成・DDL・移行・dump/restore、Embedding、実Yahoo検索、記事取得、負荷試験。
- v3・mini-v3・EVO-X2への変更やDB参照。既存gateway/Talos VMの調査は対象識別と既存接続経路の確認に必要な範囲だけ。
- `git reset`、`git clean`、stash、元作業ツリーのcheckout、無関係な変更のcommit。バックアップ基盤の追加や大量データの複製。

これらの変更がないと確認できない項目は、理由と必要な操作を「未確認」として残す。確認のために修正を先行しない。既存接続が使える範囲の読取りについて、途中で改めて承認を取り直す必要はない。

## 5. 確認手順

### A. 開発PCの作業ツリー・Git外データ・残存プロセス

最初に開始時刻（JST）、実行ホスト、branch、HEAD、origin/main、作業ツリー差分を記録する。`git status --short --branch`、差分のファイル一覧、未追跡ファイル一覧から始め、ファイル内容は必要な対象だけ読む。remote URLに資格情報が含まれる場合は除去して記録する。

次の5ファイルについて、存在・サイズ・更新日時・SHA-256・tracked/untracked/modified・Git版との差分を一覧にする。

- `infra/nlp-vm/README.md`
- `infra/nlp-vm/vmx/keiba-nlp.vmx.tpl`
- `infra/nlp-vm/autoinstall/user-data.tpl`
- `infra/nlp-vm/autoinstall/meta-data.tpl`
- `infra/nlp-vm/quadlet/nlp-demo.container`

実値seed等は `%LOCALAPPDATA%\hermes\cache\scratch\` の当該作業用ファイルを対象に、パス・更新日時・小さいファイルのhashを確認する。全ドライブや他プロジェクトを広く走査しない。`DivRoom/.secrets/keiba-nlp-console.pass` は存在と保管状態だけを記録し、値を出力・再生成しない。

`data/poc/g1_passages.jsonl` は存在・サイズ・SHA-256・JSONとして読める件数・URL重複数・text空件数・フィールド構成を確認する。既報は24件、URL重複0、text空1件である。`summary`・`text_kind`・`notes` 等の由来情報も保持されているか確認する。本文の大量表示、再生成、移行は不要。既存Embedding結果・Yahoo検索結果はファイル一覧とサイズを確認すればよい。

Hermesが開始した監視、SSH、転送、ISO作成等の関連プロセスが残っていれば、PID・開始時刻・用途・稼働状態を記録する。過去のPIDを現在の同一プロセスとみなさない。コマンドラインは秘密値を含まない項目だけ出力し、プロセスは停止しない。

### B. ESXi上の対象VM・ファイル・実VMX

既存SSH接続でVM一覧を読み、**VMID・名前・VMXパスの三者**を照合してから対象を選ぶ。15番だけを根拠に操作しない。違う場合は候補を一覧化し、同定できないVMへの追加接続を止める。

既存コマンドの読取り例は `vim-cmd vmsvc/getallvms`、同定済みVMの `power.getstate`、`get.summary`、`get.config`。使えるものだけで次を確認する。

- 現在の電源、VMware Tools/guest情報、ESXiが把握するIP。古いguest情報の可能性を区別する。
- CPU・RAM・仮想HW・firmware、NICの種類・MAC・接続先・接続状態。
- 本体ディスクとseedの接続先、実ファイルパス、デバイス種類、CD-ROM/ISO、起動順。
- `keiba-nlp` ディレクトリ内の関連VMX・VMDK記述子・seed・ISOの存在/サイズ/更新日時。100GBディスク本体の全件hashやコピーは不要。
- 対象VMの直近 `vmware.log` 等から、今回の起動・メディア接続・明確なエラーに関係する短い範囲。ログ全文は出力しない。

ローカル `keiba-nlp.vmx.tpl` と実VMXを項目別に比較し、「想定値／ローカル／実機／差分」の表を作る。MAC等の自動生成値やテンプレートの未展開値は、意味のある構成差分と区別する。

### C. 現在の画面・IP・OS導入段階

VMがONなら、既存手段で現在のコンソール表示を確認できる場合に記録する。既存の読取りシェルへ安全に入れる場合はDへ進む。Enter等の入力がインストール続行や再試行を誘発する可能性がある画面では入力しない。VMがOFFなら起動せず、その事実を報告する。

`.14` へ少数のping・TCP22確認を行い、既存の鍵と接続設定でSSH可能なら、接続先が新VMであることをhostname・MAC等で照合する。SSHホスト鍵が既存登録と変わっていた場合は、自動削除や検証無効化で通さず不一致を記録する。旧gateway準備IPの再利用であるため、対象VMの既存コンソール等からホスト公開鍵のfingerprintを独立確認できた場合は、元のknown_hostsを変更せず今回専用の一時known_hostsにその鍵を固定して接続してよい。独立確認できなければ未確認とする。StrictHostKeyCheckingの無効化、パスワードの推測、新しい認証設定は行わない。

接続できれば、インストール用live環境と導入済みOSを区別する。`/etc/os-release` だけで導入完了とせず、起動元、root filesystemのデバイス、`/proc/cmdline`、インストーラー状態を組み合わせる。

**ping成功・VMware Tools情報・電源OFFのいずれも、それ単独ではOS導入成功の証拠にしない。** 過去の `INSTALL_DONE_POWERSTATE` 通知は手動OFFにも反応しているため、成功判定に流用しない。

### D. seed・実効autoinstall設定・エラーの照合

次の4層を分けて確認する。取得できない層は未確認とする。

1. 開発PCの `user-data.tpl`。
2. 展開済みのseed入力ファイル。
3. VMXが参照する実メディア内の設定。
4. ゲストの `/autoinstall.yaml` と既存ログに残る、実際に採用された設定。

メディア内の読取りは既存のアーカイブ/ディスク解析ツールで非破壊に可能な場合だけ行う。解析目的のmount・追加パッケージ導入・VMDK変換は行わない。ファイルが存在することやhash一致だけで、ゲストが採用した設定まで確認できたとは扱わない。

ゲストへ既存接続できる場合は、存在する範囲で `/proc/cmdline`、`/autoinstall.yaml`、`/var/log/installer/` 内のSubiquity/curtinログ、cloud-initログを読む。起動時刻に対応するエラーと処理段階を特定し、過去bootのエラーと分ける。パスやログ名が異なる場合は近傍の既存ファイルを確認する。

重点確認は次のとおり。秘密値を含む設定全文を表示せず、キーの配置と判定だけを出力する。

| 確認点 | 調べること |
| --- | --- |
| 初期ユーザー | `autoinstall.identity` または `autoinstall.user-data` の有無。`users` がどの階層にあるか |
| SSH・パスワード項目 | `allow_pw` / `allow-pw`、`plainlocktext` 等の項目名が、その実行版の仕様に合うか。値は出力しない |
| UEFI・storage | firmwareとstorage設定が整合し、EFI起動に必要な領域・マウント等を定義しているか。実ディスクへ変更は加えない |
| エラー | `neither identity nor user-data provided` が現在bootのログにもあるか、前後の処理はどこか |
| seed採用 | NoCloud検出、採用したデータソース、実効設定との一致をどこまで証明できるか |

先行レビューでは、ログ内テンプレートに `identity` / `user-data` がなく `users` が `autoinstall` 直下にあり、表示エラーと一致していた。ただし今回は**現物が既に修正されている可能性も含めて確認する**。この原因を前提として他の証拠を読み替えない。

参照は [Ubuntu autoinstall公式仕様](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html)、[Subiquityのidentity処理](https://github.com/canonical/subiquity/blob/main/subiquity/server/controllers/identity.py)、必要時の [cloud-init仕様](https://docs.cloud-init.io/en/latest/reference/modules.html#users-and-groups) とする。実行版が分かれば記録し、最新版の仕様だけで互換性を断定しない。

### E. 導入済みOSへ到達した場合だけ、段階2Aの到達点を確認

ログの予想と異なり既に導入が完了している場合は、次を読み取る。未導入ならこの節は未実施とし、先へ進めるための構築をしない。

- hostname、時刻/タイムゾーン、ネットワーク、root/LVM/EFI領域の現在構成。
- Podman/Quadlet/systemdの存在・版・既存unit・active/enabled状態。コンテナの新規起動はしない。
- `/srv/nlp/` の既存ディレクトリ、unitの配置・参照先、永続化先。
- SSH/FWの現在設定を必要な項目だけ確認。
- PostgreSQLや収集エージェントが既にあれば、存在・稼働状態・image/version・データ配置のみ記録。資格情報・DB内容を取得せず、接続/起動のための設定変更をしない。

現在のactive/enabled状態と「再起動後に復帰を試験済み」は区別する。今回再起動試験は行わない。導入完了の痕跡だけで過去の全受入項目をPASSにしない。

### F. 共用検索基盤とクライアント設定の現在状態

VM調査の結果にかかわらず、既存接続で確認できる範囲を一巡する。接続情報が使えない場合は理由を記録して終了し、復旧・再設定はしない。

- Kubernetes操作は既存接続正本に従い、kubeconfig・context・namespaceを明示する。対象は `openwebui` namespaceの `google-search-mcp` Deploymentと関連Pod、`google-search-mcp-streamable` Service。
- 現在のReady数、再起動数、imageとimageID/digest、Service/NodePort、必要時の直近エラーを読む。既報digestは `sha256:4ef494f2dbf0c6f41541bbf90f125398d062c8a1e2891e4e448becf5450ad1a9`、NodePortは30081。
- `http://192.168.0.11:30081/healthz` を1回確認。既存クライアントが使える場合だけ `/mcp` の初期化・`tools/list` を確認する。既報ツールは `yahoo_search` と `fetch_page`。実ツール呼出による外部検索・記事取得はしない。
- HermesのMCP設定とLM Studioの `mcp.json` は、該当サーバーの接続方式・URL・有効状態だけを抽出する。設定ファイル全文や認証情報を表示しない。起動中クライアントの読取り可能な状態から、設定読込み済みか分かる場合のみ追記する。
- `healthz` 成功、`tools/list` 成功、設定登録、クライアント自身の検索成功は別の確認結果として記録する。今回未実施の実呼出をPASSにしない。

先行コードレビューでは「短い429待機が共有状態に反映されない」「再試行の429で新しいRetry-Afterを読まない」という所見がある。現在のコード/配備版が同じかを確認するにとどめ、実429の発生試験や修正は行わない。配備digestとソースの対応が証明できなければ、その点も未確認として残す。

## 6. 証拠・報告の扱い

各結果に観測時刻（JST）、対象、使用した読取り方法、証拠の要点を付ける。状態の区分は **実測確認済み／既存ログのみ／推定／未確認／今回未実施** を使い分ける。失敗した接続も結果として記録し、未確認を埋めるための変更作業はしない。

秘密値、パスワードhash、SSH秘密鍵、PAT、kubeconfig、実値seed、記事本文、ログ全文はGit・チャットへ載せない。設定は必要なキーだけを抽出し、パスワード等は存在/形式の判定だけにする。生の証拠が必要なら開発PCの非Git一時領域に必要最小限だけ保持し、報告には保管場所と秘匿化した要点を記載する。

同じ失敗の反復やインストール完了待ちは不要。一回の確認で判断できない変化だけを短く再確認し、長時間監視タスクは作成しない。調査中に別の作業者による構築・書込みが進行していたら、その範囲の比較を中断し、時点差として報告する。

## 7. レポートの必須内容・完了条件

レポート冒頭に、次の判定表を置く。

| 項目 | 現在の実測 | 証拠/時刻 | 未確認・次に必要なこと |
| --- | --- | --- | --- |
| 対象VMの同定・電源 |  |  |  |
| Ubuntu導入段階・現在のエラー |  |  |  |
| IP/SSH・live環境か導入済みか |  |  |  |
| 実VMXとテンプレート |  |  |  |
| 接続seedと実効設定 |  |  |  |
| ローカル5ファイル・Git差分 |  |  |  |
| PoCデータ |  |  |  |
| Podman/Quadlet・DBの有無 |  |  |  |
| 残存プロセス |  |  |  |
| 検索サービス・クライアント設定 |  |  |  |

続けて以下を簡潔に記載する。

1. 調査開始/終了、実行環境、読んだ指示書、両repoの基準SHAとローカル差分。
2. 実機・手元・GitHubの食い違い。先行レビューのどの判断が確認/修正/保留になったか。
3. 保持すべき既存ファイル・データの場所。削除・作り直しを前提にしない再開地点。
4. 現物で裏付けた停止原因と、まだ裏付けのない候補。
5. 次の修正タスク案。対象・変更候補・検証方法を短く書き、今回実行しない。
6. 実施した操作と副作用。設定・電源・サービス・元データに変更を加えていないこと、接続による通常ログ等と調査成果物の作成を区別する。

全項目が成功することは完了条件ではない。**調査可能な項目を確認し、未確認の理由と必要な次の手段が明記されていれば、この調査は完了としてよい。**

## 8. Gitでの引渡し

書き込むtracked成果物は、原則として冒頭に指定した**今回の調査レポート1ファイルだけ**とする。元の構築物・既存指示書・AGENTS.md・OpenWebUIのコードやレポートは変更しない。

dirtyな元作業ツリーや他タスクを巻き込まずに報告する。必要なら最新origin/mainを基準とする一時worktree等でレポートだけをcommit/pushする。既存変更のreset/clean/stashや、修正途中の構築物の一括commitで作業ツリーを整えない。Git外のPoCデータを取り込まない。

公開前にレポートの差分・秘密値非含有・今回の実測と記述の一致を確認し、push後に自commitがorigin/mainに含まれることを確認する。調査基準SHAはレポートへ、レポートの公開commit SHAは最終報告へ示す。開始前からの未コミット差分を残した場合は、その旨を明記する。

最終回答は、**実機の現在地、停止原因の確度、残っている成果物、未確認事項、次の修正範囲、レポートURLとcommit SHA**を示して終了する。
