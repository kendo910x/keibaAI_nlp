# NLP専用VM 導入復旧・受入指示書（段階2A / VMID 15）

作成日: 2026-11-22（JST）  
実行担当: 開発PC上のCodex  
対象repo: `kendo910x/keibaAI_nlp`  
作成時の基準: `origin/main` = `095c0ecdf20a71d4078211f915c0f2a363dc3a94`

## 1. 目的・終了地点

既存のVMID **15** `keiba-nlp` を使い、誤ったautoinstall設定を修正してUbuntu Serverの導入を完了する。インストール媒体を外した本体ディスクからのEFI起動、`nlp` の鍵SSH、固定IP、時刻、rootful Podman、Quadletの通常再起動後の復帰まで実測し、段階2Aを引き渡す。

今回の入力は既存VM、開発PCに残る構築用5ファイル、接続実績のあるVFAT seed、および実機状態確認レポートである。新しいVMは作成しない。PostgreSQL・PoC移行・Hermes収集ジョブ・共用検索の修正は後続タスクとする。

本書は、ユーザーから本書の**実行を依頼されたCodex**が行う作業範囲を定める。指示書の作成・commitだけでは実機操作を開始しない。実行を依頼された後は、第4節の範囲内の操作を一連の復旧作業として進め、同じ範囲について再度の包括承認を求めない。停止条件に該当した場合は、その事実と必要な追加判断を報告する。

## 2. 開始時に読むもの・既存指示書との関係

1. repoの [AGENTS.md](../../../AGENTS.md) と対象ディレクトリに追加された規約。
2. [実機状態確認レポート（固定版）](https://github.com/kendo910x/keibaAI_nlp/blob/095c0ecdf20a71d4078211f915c0f2a363dc3a94/docs/reports/2026-11/2026-11-22_nlp_actual_state_check_report.md)。以下の状態は同日17:09–17:29 JSTの観測であり、実行開始時に再照合する。
3. [元のVM構築指示書](2026-11-22_nlp_vm_build_instruction.md) と [配置設計](../../design/2026-11-22_nlp_infrastructure_placement.md)。
4. 開発PCの `C:\Users\kendo\keiba_nlp\infra\nlp-vm\` の現物。必要な場合だけ既存home-gateway構築レポートを参照し、別VMの設定をそのまま適用しない。

本書は、元のVM構築指示書のうち「新規VM作成」を「既存VM15の復旧」に置き換える。初期ユーザーの作り方、EFI/LVMの設定方法、seed媒体、時刻の事前確認、demoの判定方法は本書で具体化する。元のユーザー名 `nlp`、ネットワーク、配置、FW方針、後続工程との境界は維持する。段階2Bは自動的に続行しない。

## 3. 起点となる実測と修正方針

| 実測済みの状態 | 今回の扱い |
| --- | --- |
| VMID15・`keiba-nlp`・`[datastore1] keiba-nlp/keiba-nlp.vmx` が一致。電源ON、診断シェルで待機 | 作業前に三者を再照合し、現bootの証拠を保全してから電源操作する |
| OS ISOのlive環境。rootは `/cow`、100 GiB本体は子パーティションなし | 導入済みOSと扱わない。本体の現在の内容を再確認して導入対象を確定する |
| 8 MiBのVFAT `CIDATA` をNoCloudが採用。展開ファイル・実媒体・cloud-initキャッシュが一致 | VFAT seed方式を継続する。媒体方式を試行錯誤する工程へ戻らない |
| `autoinstall.users` があり、`identity`・`user-data` がない。実行ログに `neither identity nor user-data provided` | `autoinstall.identity` で管理ユーザーを定義する |
| `ssh.allow_pw`・`plainlocktext`、EFI System Partitionを欠くstorage定義 | 正しいSSH項目とパスワードハッシュに修正し、guided LVMでEFI構成を生成する |
| 実VMはseed VMDK、手元VMXテンプレートは古いseed ISOを指定 | テンプレートとREADMEを実際に採用する媒体方式にそろえる |
| ESXi時計はSPRの実時刻より約37時間23分遅れ、ゲストもずれている | 新しいインストーラーbootでも、APT等の取得前にゲスト時刻を確認・補正する |
| PoCは24件・31,060 B、本文空1件、URL重複0件 | 内容を変更・移行せず、作業前後の同一性を確認する |

これらは上記レポートを根拠とする。Hermesのコンテキスト上限による会話停止は、Subiquityの設定エラーとは別の事象であり、今回のVM復旧にHermesの再開は必要ない。

## 4. 許可する操作と対象の限定

| 対象 | 本書を実行する際の操作範囲 |
| --- | --- |
| 開発PC・repo | 関連ファイルの読取り・退避・修正、Git参照更新、必要なら独立worktree作成、対象ファイルのcommit/pushと反映確認 |
| ESXi `192.168.0.5` / `esxi-divroom` | 既存の認証経路で読取り。VM15の正常停止・起動、seedファイルの追加・交換、媒体切断、必要最小限のVM15設定反映。VM15に限定した時刻同期設定の調整 |
| VM15の本体ディスク | 第6節で同定し、初回導入前に空状態を再確認した `scsi0:0` の100 GiB VMDKに、Ubuntuをインストールするためのパーティション作成・フォーマット。今回の導入だけが作った不完全なOSの再導入は第8節の条件による |
| VM15ゲスト | 固定IP・管理ユーザー・鍵SSH・sudo・時刻・FW・公式パッケージ・保存ディレクトリ・Podman/Quadletの設定、通常再起動、受入確認 |
| 外部取得 | Ubuntu/Canonicalの公式配布物・公式仕様、Ubuntuの正規パッケージ、検証用の小さな公式コンテナイメージ。検索API・記事収集・LLM推論は呼び出さない |

他VM、ESXiホスト全体の時計/NTP・管理ネットワーク、vSwitch/ポートグループ、自動起動グループ、Talos/OpenWebUI/EVO-X2/v3の設定を変更しない。既存Hermes/LM Studio/検索用プロセスの停止や設定変更も行わない。別サービスのBasic認証情報変更は別タスクとする。

既存のESXi SSHを優先する。コンソールが必要なら対象VM15の既知の画面・接続を利用し、ブラウザ全タブ一覧や資格情報を含むURLを出力しない。パスワード・秘密鍵・実値seed・生のインストーラーログをチャットやGitに貼らない。

## 5. 維持する構成

| 項目 | 値・条件 |
| --- | --- |
| VM | VMID15、`keiba-nlp`、2 vCPU、8 GiB RAM、100 GiB thin、HW14、EFI、LSI Logic、E1000×1 |
| 本体 | `[datastore1] keiba-nlp/keiba-nlp.vmdk`、`scsi0:0`。8 MiB seedをインストール先に含めない |
| NIC | ポートグループ `VLAN 101`、報告時MAC `00:0c:29:3a:81:3b`、ゲスト名 `enp0s17`。MACで対象を照合し、名前の推測に依存しない |
| IP / GW / DNS | `192.168.0.14/24` / `192.168.0.1` / `192.168.0.1` |
| OS / installer | 既存Ubuntu Server 24.04.5 LTS amd64 ISOを検証して再利用。報告時Subiquity 24.04.5、snap revision7424。自動更新を抑え、検証版と実行版をそろえる |
| ユーザー | `nlp`、hostname `keiba-nlp`。既存管理用SSH鍵、sudo利用可、SSHパスワード認証無効 |
| 時刻 | 表示 `Asia/Tokyo`、時刻比較はUTCを併記。導入後の同期はchrony、仮想RTCはUTC |
| 保存先 | `/srv/nlp/{pgdata,articles,dumps,quadlet}`。今回DBデータは作らない |
| コンテナ | rootful Podman + Quadlet + systemd。k8s/Composeは導入しない |
| FW | UFW有効、incoming既定deny、LAN `192.168.0.0/24` からTCP22/5432を許可。5432は将来用ルールのみで、DBは起動しない |

## 6. 実施手順

### A. 現在地の再確認と保全

1. repoのbranch・HEAD・`origin/main`・tracked/staged/untracked差分を記録する。`fetch` 後、本書のcommitを含む最新mainを確認する。他の変更を上書きせず、必要ならmainから別worktreeを作り、今回の5ファイルだけを保全コピーして修正する。`reset --hard`、`clean`、強制pushは使わない。
2. 次の5ファイルを、元の内容・サイズ・SHA-256が追える形でローカルに退避する。退避物に実値があれば非公開領域で扱い、実値入りコピーをrepoに追加しない。

   | `infra/nlp-vm/` からの相対パス | 今回の役割 |
   | --- | --- |
   | `README.md` | 再現手順・媒体方式・検証・導入後の状態を更新 |
   | `vmx/keiba-nlp.vmx.tpl` | VFAT seed VMDKと起動段階の指定を整合 |
   | `autoinstall/user-data.tpl` | identity・SSH・network・EFI/LVM・時刻確認手順を修正 |
   | `autoinstall/meta-data.tpl` | hostnameと今回seedのinstance-idを整合 |
   | `quadlet/nlp-demo.container` | ポート公開しない軽量demoの起動・自動復帰を検証 |

3. `data/poc/g1_passages.jsonl` の存在・サイズ・行数・SHA-256を確認する。基準は **24件、31,060 B、SHA-256 `e2eaf61190353c4b10cc3175b8a24dfe9b69d577c42189df192700266810ad16`**。内容を表示せず、作業前後の照合値を残す。相違があれば上書きせず変更の由来を調べる。
4. ESXiのVM一覧、VM15の電源・設定・デバイス・VMX/VMDK記述子を読み、VMID/名前/VMX、本体の接続先・パス・容量、seed、MACを対応付ける。ゲストでは `findmnt`、`lsblk`、LVM状態等を読み取り、本体の空状態とlive環境を確認する。`/dev/sda` という名前だけで対象を決めない。新bootでも操作できるVM15のコンソール経路をここで確保し、導入前待機中の確認・時刻補正・解除に使う。
5. datastore1空き120 GB以上（元の構築指示書の条件）、`.14` の競合がないこと、GW/DNSの前提を再確認する。ping不達だけでIP空きを断定せず、既存の許可された経路で隣接情報等も照合する。広域スキャンは行わない。
6. ISOの完全なSHA-256とCanonical署名済み一覧の対応を確認する。検証済み同一ファイルを裏付ける記録が不足していれば再計算・署名検証する。先頭数桁やファイル名一致だけで済ませず、検証済みISOが使える限り再ダウンロードしない。
7. 現bootのエラー、採用seed、インストーラー版、VM設定、SPR/ESXi/ゲスト各時計を必要な範囲で保全する。VM単位の時刻同期設定と必要な変更もここで調査し、停止を要する変更はD1の電源OFF中にまとめる。時刻補正前のログをJSTの実時刻と誤認しない。ログ全文はローカルだけに保持する。

### B. autoinstall・VMXテンプレートの修正

NoCloudの `user-data` は `#cloud-config` で始め、`autoinstall` 配下に `version: 1` と必要な定義を置く。以下は今回採用する設計であり、現物のテンプレートへ反映する。

| 箇所 | 修正内容 |
| --- | --- |
| 初期ユーザー | `autoinstall.identity` に `hostname: keiba-nlp`、`username: nlp`、`password` のハッシュを置く。`autoinstall.users` は除去し、`user-data.users` と二重定義しない |
| パスワード | 既存 `C:\Users\kendo\DivRoom\.secrets\keiba-nlp-console.pass` を安全に読み、対象OSが受け付けるcrypt形式へ変換。テンプレートはプレースホルダー、展開値は引用したハッシュ。平文・ハッシュを出力しない。`plainlocktext` は除去 |
| SSH | `ssh.install-server: true`、`ssh.authorized-keys` に管理用公開鍵、`ssh.allow-pw: false`。`allow_pw` は除去。秘密鍵をseedへ入れない |
| ネットワーク | 実MACに対応するNICへ `.14/24`、default route `.1`、DNS `.1`。対象版が受け付けるnetplan構文を使用し、DHCPとの二重設定を避ける |
| storage | `storage.layout.name: lvm`、`sizing-policy: all`。本体だけに一意に一致する `match` を指定し、旧 `storage.config` は除去する |
| installer | `refresh-installer.update: false`。正常終了後は `shutdown: poweroff` とし、媒体を外してから本体起動を確認する |
| パッケージ等 | `openssh-server`、`open-vm-tools`、`chrony`、`ufw`、`podman`。timezoneは `Asia/Tokyo`。必要な設定は導入後にも実効値を確認する |
| meta-data | 今回のseedを識別できるinstance-idとhostname。過去seedのキャッシュと混同しない |

`identity`、SSH、LVM、終了動作の仕様は [Canonical autoinstall reference](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html) を参照する。最新版の説明だけでrevision7424に適合すると判断せず、後述の対象版検証を行う。

storageはEFI起動下のguided LVMを用い、GPT・ESP/FAT・`/boot/efi` とLVM rootが作られることを実機で確かめる。旧テンプレートのroot90G/swap4G固定は引き継がない。rootにはVGの残余を割り当てるが、ESP・boot等の領域があるためrootの `df` が100 GiBになるとは扱わない。暗号化・TPM等の新しい要件は追加しない。

ディスクの `match` は、対象版で使用できるserial/path等と実機対応を確認して決める。空のmatch・`largest` 単独・推測したby-idを使用しない。安定IDが得られずパスを使う場合は、**新bootで同じパスが本体100 GiBに対応することを確認するまで導入を開始しない**。

VMXテンプレートはVFAT seed VMDKの接続方式を表現し、READMEにインストール時と導入後の媒体状態を分けて記載する。実VMXへは必要な差分だけ反映し、UUID・MAC・PCIスロット等をテンプレート値で上書きしない。`boot.order` の文字列変更だけで有効な起動順が変わったと判断しない。

### C. 対象版での事前検証・新seedの作成

1. 展開前後のYAMLを解析し、重複キー・未展開プレースホルダー・旧不正項目がないこと、identity/SSH/network/storageの値が今回の対象と一致することを確認する。機密値そのものは検証結果に出さない。
2. ISO/実行snap **7424** のスキーマ・コントローラー定義、またはその版との対応を説明できるvalidatorで、展開済み設定を事前検証する。cloud-init側の構文確認だけでSubiquity検証に代えない。使った版・方法・終了結果を記録する。公式validatorを使用する場合はsudoで起動しない。[検証手順と限界](https://canonical-subiquity.readthedocs-hosted.com/en/latest/howto/autoinstall-validation.html)
3. スキーマ検証は実ディスクへのmatchやEFI起動の保証ではないため、D節の実機確認と第7節の受入を別に行う。版対応や検証結果を確かめられないまま「latestで通った」として進めない。
4. 新bootの時計と対象を確認できるよう、復旧用seedに**時間制限付きの導入前待機**を設ける。例は `early-commands` で `/run/keiba-nlp-recovery-ready` を待ち、10分以内に解除されなければ非0終了する方式。ディスク書込み・APT等の取得に進む前に待機することを対象版の動作で確かめる。解除はCodexがD節の確認後に行うもので、追加のユーザー承認待ちではない。永久ループやホスト時計を前提とした期限判定を使わない。
5. 8 MiB、ラベル `CIDATA` の新しいVFAT seedを別ファイルとして生成する。新seedとVMDK記述子の対応を確認し、生成物から `user-data`・`meta-data` を読み戻して展開済みファイルとバイト単位で照合する。各ファイルと媒体のSHA-256を記録する。
6. 新しいseedを非公開で保持し、旧seedも識別して退避する。旧 `nlp-seed.iso` を今回の入力に混ぜない。接続中のseed flatへ書き込まない。テンプレート・検証方法・媒体生成手順のみをGit管理可能な形で残す。

### D. seed交換・新bootの確認・Ubuntu導入

1. A〜Cの確認が完了してから、現在のliveゲストを正常停止する。電源OFFをESXiで確認し、旧seedを保持したまま検証済み新seedへ接続を切り替える。VM15のVMXは媒体・起動・必要なVM単位の時刻同期設定だけを変更し、設定再読込み後に差分とデバイス接続を確認する。応答のあるゲストをハード停止しない。
2. OS ISO + 新seedで起動する。導入前待機中はA4で確保したコンソール経由で、VM15、EFI boot、実行Subiquity版、新seedのinstance-id/ファイルハッシュ、cloud-initの採用設定と `/autoinstall.yaml` の意味的な一致を確認する。外側のcloud-configラッパーが異なるため、すべての層で単純なファイルハッシュ一致を要求しない。early-commandsはinstallerのディスク/ネットワークprobe前なので、この時点で `.14` のSSHや生成済みstorage計画を前提にしない。
3. このbootの本体ディスクの接続・容量・空状態と、設定したmatchが本体1台だけに対応することを再照合する。seed 8 MiBが一致しないことを確認する。異なるseed、異なる版、別ディスク、想定外の既存データなら待機を解除しない。installerが実際に生成・適用した構成は、解除後のログとV3で確認する。
4. **このbootのゲスト時計**を信頼できるUTCと照合する。利用可能な同期手段を使い、なければ同期状態を確認した開発PCの現在UTCを用いてゲスト内だけを補正する。前bootで直した時計が維持されるとは仮定しない。時刻が成立する前にAPT・TLS取得・インストールを先行させない。時刻比較の取得遅延も含めて記録する。
5. A7で決めD1で適用したVM単位の時刻同期設定と、新bootの実効状態を確認する。live環境にchronyがあるとは仮定せず、待機中にパッケージ追加を要求しない。導入後はE4でchronyとVMware Toolsの競合を確認する。VM単位の変更はESXi6.7と使用Tools版に対応した方法に限定し、単発のホスト同期と周期同期を混同しない。ホスト全体の時計変更が必要なら今回の範囲で無断実施しない。[VMwareの時刻管理方針](https://knowledge.broadcom.com/external/article?legacyId=1006427)
6. 対象・設定・時刻の確認後に待機を解除して導入する。30〜60秒程度の短い観測と要点の記録で進捗を追い、ログ全文の反復出力や無期限の監視を避ける。10分以上進展が見えなければログと処理状態を調べ、単に遅いという理由で再起動しない。
7. 正常終了の根拠を確認する。電源OFFだけでは成功と判定せず、導入後に保存されたinstaller/curtinログ等と照合する。途中エラーなら同じseedをそのまま再実行せず、エラー箇所・書込み到達点を保全して原因を特定する。

### E. 本体起動・OS設定・Podman/Quadlet

1. 導入終了と電源OFFを確認後、**OS ISOとseedの両方を切断**し、自動再接続も解除する。OS本体VMDKを残してEFIディスク起動できる設定にする。VM15を起動し、導入済みOS、hostname、root実デバイス、ESP、LVMを確認する。
2. 新しいSSHホスト鍵をコンソール等の信頼できる経路で照合し、開発PCから `nlp@192.168.0.14` へ既存鍵で接続する。以前の `.14` のknown_hosts情報はバックアップし、照合済みの対象エントリだけ更新する。全削除やホスト鍵検証の無効化で回避しない。
3. `nlp` のsudo実行を確認する。パスワードが必要なら既存のコンソール秘密を安全に入力し、`sudo -n` の失敗だけで権限なしと判定しない。便宜のために新しい無制限NOPASSWD設定を追加しない。SSHは実効設定と別接続で鍵認証・パスワード認証無効を確認する。
4. chronyの同期先・同期状態とゲストUTCを確認したうえで、正規リポジトリの `apt update` / `apt full-upgrade` と必要パッケージの導入状態を確認する。証明書・APT署名・有効期限検証を無効化して時計問題を回避しない。メジャーリリースのアップグレードは行わない。
5. UFWはLANからのSSH許可を先に用意して有効化し、別SSH接続でも到達することを確認する。22/5432の送信元制限とincoming既定denyを実測する。5432にサービスを追加せず、新しい外部公開はしない。
6. `/srv/nlp/{pgdata,articles,dumps,quadlet}` を作成し、所有者・権限を記録する。`pgdata` は空で保持し、DB用UID等は後続で決める。公開書込み可能な権限にしない。
7. rootfulで `podman info`、バージョン、cgroup v2を確認する。小さな公式Alpineイメージの明示タグを解決しdigestを記録・固定して、`echo ok` 相当のコンテナを1回実行し終了コード0を確認する。再起動検証前に同じイメージを取得済みにする。
8. `nlp-demo.container` はネットワークポートを公開しない軽量の待機プロセスとし、Git対象ファイルを `/srv/nlp/quadlet/` に配置、`/etc/containers/systemd/` から参照させる。`[Install]` の `WantedBy=multi-user.target` 等、導入版のQuadletで有効な自動起動方法を設定し、`daemon-reload` 後に生成された `nlp-demo.service` を起動する。
9. Quadletの生成unitは通常の手書きunitと同じ `systemctl enable` 手順に固定しない。生成元・生成されたunit・サービスとコンテナのrunning状態を照合する。`active (exited)` だけを常駐成功と扱わない。[Podman Quadlet仕様](https://docs.podman.io/en/stable/markdown/podman-systemd.unit.5.html)
10. 受入前のboot IDと時刻を記録し、ゲストから通常rebootを1回行う。ISO/seed未接続のまま、SSH、固定IP、経路/DNS、chrony、FW、demoの自動復帰を確認する。ESXi自動起動グループや他VMの再起動は試験しない。

## 7. 受入条件

以下を実測した場合に限り「段階2A完了」とする。結果は **PASS / FAIL / 未確認** と証拠を併記し、未確認をPASSに置き換えない。

| ID | 受入項目 | 必要な実測・判定 |
| --- | --- | --- |
| V1 | 対象と導入媒体 | VMID15/名称/VMX/本体VMDKの対応、ISOの検証、新seedの読戻し・採用設定・実行版が確認できる |
| V2 | Ubuntu本体起動 | ISO/seed未接続。Ubuntu 24.04 LTS、hostname `keiba-nlp`、`/sys/firmware/efi`、rootが本体のLVMであり `/cow` でない |
| V3 | ディスク構成 | GPT・ESP/FAT・`/boot/efi`、boot/LVM/rootの対応、`lsblk`・`pvs/vgs/lvs`・`df` の容量を記録。本体100 GiBを使用し、VG残余がrootに割当済み |
| V4 | 管理接続 | `nlp` の鍵SSHとsudoが成功。sshd実効設定でパスワードによるSSHログインが無効。ホスト鍵照合済み |
| V5 | ネットワーク | `.14/24`、default route `.1`、DNS `.1` の実効値と名前解決を確認。通常再起動後も成立 |
| V6 | 時刻 | live/導入後の外部取得前に実時刻を確認。導入後と通常再起動後にchronyが同期し、正常な同期先と状態を確認。同期収束後、信頼できるUTCとの差は取得遅延を考慮して5秒以内。同期方式・補正前後・未解消のホスト時刻問題を記録 |
| V7 | FW | UFW有効、incoming既定deny、22/5432の許可元がLANに限定。別SSH接続に成功。DB listenerは未導入 |
| V8 | Podman | rootful、cgroup v2、パッケージ版、イメージのtag/digest、単発コンテナの正常終了を記録 |
| V9 | Quadletと再起動 | 生成元ファイルを追跡できる。通常rebootでboot IDが変わり、手動startなしでdemo serviceとコンテナがactive/runningへ戻る。復帰時間も記録 |
| V10 | 保存先・既存データ | 指定4ディレクトリの存在・権限、PoCの作業前後ハッシュ・24件が一致。既存5ファイルの変更内容と退避が追跡できる |
| V11 | 範囲とGit引渡し | 本作業による他VM/ホスト全体/検索/v3の設定変更0件。修正版・README・レポートを対象限定でcommit/pushし、`origin/main` の内容を確認 |

Toolsの稼働、ping応答、監視プロセス終了、画面上の完了表示だけでは、上の受入を代替しない。時刻は手動補正直後だけでなく、chronyの同期と通常再起動後の再収束を確認する。

## 8. 失敗時の扱い・停止条件

まず失敗点に関係するログ・設定・現在状態を保存し、同じ入力での再試行を繰り返さない。対象と原因が明確で本書の範囲内なら、修正→対象版検証→媒体読戻し→必要な項目の再検証を行う。無関係な全検証の反復はしない。

次の場合は、その先の変更操作を止めて報告する。

- VMID・名前・VMX・ディスクの対応が確定できない、または初回導入前の本体に想定外のパーティション・LVM・保存データがある。
- `.14` の競合、datastore空き不足、ISO検証不一致、対象版への適合未確認、seed読戻し不一致、意図しない設定の採用がある。
- 時刻を成立させるためにESXi全体の時計変更が必要、または再起動後もゲストの時刻同期が安定しない。
- 同じエラーの原因が特定できないまま別媒体への交換・再インストール・ディスク初期化を繰り返す必要が生じる。
- 本体のEFI起動、鍵認証、ネットワーク、Quadlet等の不具合を、本書の範囲内で説明・解消できない。
- 他VM・共用検索・v3・別サービスの認証情報など、対象外への変更が必要になる。

インストール開始後のディスク書込みは、旧seedや旧VMXに戻しても取り消せない。途中まで書き込まれた本体は、まず修復で済むかを確認する。再導入が必要な場合は、次のすべてを満たせば今回の実行範囲内で進めてよい。満たすことを確認できなければ停止する。

- VM15の同じ100 GiB本体を再同定できた。
- 内容は今回の導入だけが作った不完全なOSであり、他者の作業や追加データがない。
- エラー原因を特定・修正し、設定の対象版検証とseed読戻しを再度完了した。
- 必要な診断証拠を本体以外へ保全し、再導入の理由・対象・失う内容を記録した。

原因未特定の再フォーマットや、設定を変えない同一試行の反復は行わない。

中断時は、VMの電源、接続媒体、どのディスクへ何を書いたか、現在のIP/SSH、最後に成功した工程、失敗箇所、採用seedの識別子、証拠のローカル所在、再開に必要な判断を記録する。診断待ちにできる場合は、無期限の再試行を止め、インストールが再開しない状態で保持する。

## 9. 成果物・Git引渡し

原則として次の成果物を対象にする。媒体生成・検証に再利用が必要な短いスクリプトを追加する場合は `infra/nlp-vm/` 内に限定し、秘密値の引数・標準出力・ログへの露出を避ける。新しい汎用基盤は作らない。

- `infra/nlp-vm/README.md`
- `infra/nlp-vm/vmx/keiba-nlp.vmx.tpl`
- `infra/nlp-vm/autoinstall/user-data.tpl`
- `infra/nlp-vm/autoinstall/meta-data.tpl`
- `infra/nlp-vm/quadlet/nlp-demo.container`
- `docs/reports/2026-11/2026-11-22_nlp_vm_recovery_report.md`（実行日が変われば日付・配置月も実行日に合わせる）

READMEには、必要パラメータ、秘密値のローカル供給、対象版での検証、VFAT seedの生成・読戻し、媒体交換、復旧用の導入前待機と解除、ISO/seedを外す時点、導入後の起動、VM単位の時刻対処、Quadlet配置を記載する。実VMXを上書きする用途のテンプレートではないことも明示する。

レポートには、実行環境・開始終了時刻・参照SHA、開始時との差、VMXの変更キー、ISO/seedの識別情報、修正理由、インストール完了根拠、V1〜V11の結果、通常再起動の結果、時刻補正と残る影響、PoC保全、実施/未実施、最終VM状態、残件、実装commitを残す。生ログは抜粋する前に秘密がないことを確認する。

対象ファイルだけをstageし、秘密・実値seed・パスワードハッシュ・PoC本文・生ログが混ざっていないか差分を確認してcommit/pushする。リモートが進んでいれば取り込み方を確認し、他の成果物を上書きしない。`origin/main` のSHAと本文一致を確認して引き渡す。レポート自身を含む最終commit SHAは、自己参照で書換えを繰り返さず最終チャットに提示すればよい。

## 10. 後続へ引き継ぐ事項

段階2Aの受入後も、次は別の指示書・実行タスクで扱う。

1. **共用検索**: 短い429待機を含む共有クールダウン、再試行時の共通gate、2回目429のRetry-After反映を修正・検証する。Hermes/LM Studioの設定登録と、各アプリ自身の実呼出成功を区別する。
2. **段階2B**: DB指示書のデータサイズを31,060 Bへ訂正し、PoC全13フィールドの由来保存、同一内容再取得と再実行の扱い、馬名の複数候補を整理してからPostgreSQL・24件移行を実施する。今回DBを先行構築しない。
3. **収集ジョブ**: VM・DB・検索の成立後、小さな1ジョブで探索→取得→由来付き保存→中断再開→再実行を検証する。
4. **ESXi時計**: 約37時間のずれの原因・NTPをホスト全体への影響込みで別途扱う。VM側の受入が成立しても、ホスト問題を解消済みと報告しない。
5. **別サービスの認証情報**: タブ一覧のツール出力に現れたBasic認証の該当パスワードと保存先を別途更新する。値を本repoの指示書・レポートへ転載しない。

本タスクは、上記の残件を具体化して記録し、段階2Aの検証結果を引き渡したところで終了する。
