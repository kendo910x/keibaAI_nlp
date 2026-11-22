# VM15 Ubuntu導入復旧・段階2A実測レポート

**段階2AのV1〜V11はすべてPASS。** VM15はISO・seedを切断した本体ディスクから起動し、通常再起動後23.3秒でQuadletとコンテナの自動復帰を確認した。ESXiホストの約37時間23分の時計ずれは別件として残る。

2026-11-22 JST。開発PC SPR、ESXi 6.7.0 build 13006603、VMID 15 `keiba-nlp` を使用した。[復旧指示書（84c306d）](https://github.com/kendo910x/keibaAI_nlp/blob/84c306dd97c54ecb948d7548d7ae971f5b2a37eb/docs/instructions/2026-11/2026-11-22_nlp_vm_recovery_instruction.md)・[前回の実機確認（095c0ec）](https://github.com/kendo910x/keibaAI_nlp/blob/095c0ecdf20a71d4078211f915c0f2a363dc3a94/docs/reports/2026-11/2026-11-22_nlp_actual_state_check_report.md)

## 開始時の実機と保全

18:33に着手。開発PCの元の `main` は `05e30b267cdf48a473fa83a65bef327224347393`、fetch後の `origin/main` は `84c306dd97c54ecb948d7548d7ae971f5b2a37eb`。tracked・staged差分0、未追跡5ファイル。元のツリーを保ち、指示書コミットから独立worktreeを作成した。非公開の証拠はSPRの `%LOCALAPPDATA%\keiba-nlp-recovery\vm15-20261122-183354` に保存。ACLは作業ユーザーとSYSTEM。退避物の明細は `original-files.json`。

| 退避した元ファイル | バイト | SHA-256 |
| --- | ---: | --- |
| README.md | 1,826 | `b7022dcbcdcaac5963596eab88ebd7db0ef380edb2d2d18f016b54da206ae196` |
| vmx/keiba-nlp.vmx.tpl | 2,323 | `efac2cb1a51bc745fe07c782ec94d84a6c5b7bdead1414fe267948be97431500` |
| autoinstall/user-data.tpl | 2,649 | `1f62c5382f21c944cbef0b52870c9c6e840718905dd582a8171c074b09ead6d7` |
| autoinstall/meta-data.tpl | 64 | `81e3d93d40c12bea793b0441d230ae998c4d7b7bef3f7b29b0c9e139746271a9` |
| quadlet/nlp-demo.container | 334 | `90e82a5bdf175180b229f15fd9aaed26e7bb8a9ee5374f9ef5705876cc368258` |

- VM15・名前・`[datastore1] keiba-nlp/keiba-nlp.vmx`、2 vCPU、8 GiB、EFI、MAC `00:0c:29:3a:81:3b` が一致。本体 `scsi0:0` はLSI Logicの100 GiB thin、209,715,200セクター。初期の本体extentの割当は0 KiB。datastore1空き937,699,328 KiB。SPRのpingと隣接表、ゲートウェイの隣接表に `.14` の応答・有効MACはなく、`.1` はLAN直結経路とDNS応答を確認した。
- Windowsの画面操作はアクセス拒否。ESXiのUSBキー入力APIは現ライセンスで拒否された。既存のホスト鍵検証付きSSHからVM15専用のWebMKSチケットを取得し、ESXiの証明書を照合したTLS上で共有コンソールに接続した。診断シェルのコマンドと応答を確認し、新bootにも同じ経路を使った。チケットはメモリ内だけで使用した。
- 旧bootは `b4898b63-a499-4272-8baf-4463483c10ce`、rootは `/cow`。本体は `/dev/sda`、107,374,182,400 B、`ID_PATH=pci-0000:00:10.0-scsi-0:0:0:0`、子デバイス・wipefs署名・PV/VG/LVなし。SATAの `/dev/sdb` は8 MiBのCIDATA。旧instance-idは `keiba-nlp-20261122`。旧seed全体のSHA-256は `e4d055fa6da3b8a7d423f549140a7422b85e46654d7ad2dfbe52f04d5d5645f8`。ゲストの実デバイスと同一の旧イメージを退避した。Subiquity 24.04.5 revision 7424の旧ログに `neither identity nor user-data provided` が4行。IPv4なし、Toolsの周期同期はDisabled。
- 18:33 JSTの開発PC UTCは11月22日09:33:54、ESXi UTCは11月20日20:10:37。約37時間23分遅れ。Windowsの時刻サービスは未同期だったため、開発PCから `ntp.ubuntu.com` の応答と往復時間を直接測定した。

## 修正と事前検証

初期ユーザーを `identity` に移してSHA-512 cryptを指定し、管理公開鍵を `ssh.authorized-keys`、パスワードSSHを `allow-pw: false` に統一した。固定IPはMACで照合し、導入対象は実機のSCSI接続パスに固定した。guided LVMの残余割当、installer更新停止、導入前600秒待機と終了時poweroffを指定。VMX見本をVFAT VMDKに合わせた。デモはネットワークを無効にし、公式Alpine 3.23のマニフェストをdigestで固定した。

| 照合対象 | 実測 |
| --- | --- |
| OS ISO | Canonical CD Image署名鍵 `843938DF228D22F7B3742BC0D94AA3F0EFE21092` の `VALIDSIG`。署名済み一覧・SPRの全ファイル・ESXi上の接続ISOのSHA-256が `97f3d7ffb032c3eb3b23d2c8be9cc76e60c2c1f2c0146ba5ba9fe01cafae0fd8` で一致 |
| 対象版 | ISOのinstaller squashfsから取り出した `subiquity_7424.snap` は `2d9ce94e9dc4af41e310cfb0f1f5508fd8eaa5aa821a1aa0e7bd30c03c843f00`、metaは24.04.5。Canonicalタグのcommit `7639acf9b526966633f0b50c1397fd4f2cae4254` とserver・controller・型・filesystemモデル・使用コントローラー計15ファイルをバイト照合、全件一致。固定JSON Schemaを一般ユーザーで展開済みYAMLに適用、終了0。7424のモデルで `id_path` とudevの `ID_PATH` の照合を確認 |
| ネットワーク・待機 | Netplan生成結果に実MAC、`.14/24`、default via `.1`、DNS `.1`。7424のサーバーコードで早期コマンド完了後に通常設定を読込み、コントローラーの起動・適用へ移る順を確認 |
| 最終seed | `keiba-nlp-vm15-recovery-20261122-r2`。VFAT/CIDATA 8,388,608 B、SHA-256 `43ed16bf06ac208766be041f3f1d6264b5968378dc731651105bfece4fb24e53`。user-data 1,824 B `22bfafb486bbf3d2bc6324abb23479314343b619a006b19eb6ad094a9d27e79a`、meta-data 75 B `90bdb87a54230ad42d1bdfc72349ed67b188920bb330659b571b2aac4591fdc8`。VFATから両ファイルを読み戻してバイト一致 |
| ESXi新媒体 | 新規 `nlp-seed-recovery-r2.vmdk` の記述子SHA-256 `f81c73ff46e1c281f1ed2789419ea4a5299c91f4ade6450c77fc95dd4b43a7a9`。新extentの16,384セクターと全体SHA-256が新しいローカル媒体に一致。`vmkfstools -e` でチェーン整合を確認 |

最初のローカル候補r1はデバイス名指定で事前検証した。VM15コンソールで安定した接続パスを取得したため、r2を再生成・再検証して初めて接続した。旧seedは別ファイルで保持した。

## 導入時の観測

| JST | 実測 |
| --- | --- |
| 18:58–18:59 | 旧liveから正常poweroffし、コンソールの終了確認後にホストで電源OFFを確認。元VMXを保全し、新seedへの変更とVM15個別の時刻設定を反映。導入時の差分は `sata0:1.fileName` と `time.synchronize.{continue,restore,resume.disk,shrink,tools.startup,tools.enable,resume.host}` の8キー。`tools.syncTime=FALSE` は設定済み。再読込み後にISO、本体100 GiB、seed 8 MiB、MACを確認 |
| 18:59–19:01 | EFIのIDE CDROM起動をESXiログで確認。新liveのboot ID `35b9773a-37fd-4f92-976b-28b3c44877f4`。7424、600秒待機、NoCloud、r2、EFIとMACを再確認。SCSI接続パスは本体1台、SATAのseedは別。子パーティション・署名・LVMなし。実媒体2ファイルのハッシュ一致、媒体user-dataとcloud-initキャッシュのバイト一致、ラッパー正規化後に `/autoinstall.yaml` と構造一致 |
| 19:01–19:02 | 補正前の新liveは11月20日20:37:50 UTC。Canonical NTP stratum 2、往復0.233秒を基準にゲスト時刻を補正し、ISO内のBusyBoxで仮想RTCをUTCへ反映。独立再照合時のゲストは11月22日10:02:18.584 UTC、取得区間は10:02:18.274–18.617 UTC、NTP往復0.301秒。待機を解除した |
| 19:03–19:05 | 本体・設定・時刻確認後にstock ISOの `Continue with autoinstall?` に応答。curtinのpartitioning完了、OS展開、curthooks・kernel導入への進行を確認 |
| 19:07–19:10 | OpenSSH・Tools・chrony・UFW・Podmanを導入しセキュリティ更新へ進行。ターゲットで `sda1 vfat /target/boot/efi`、`sda2 ext4 /target/boot`、`sda3 LVM2_member` とLVの `/target` を実測。ホストから電源OFFを確認 |
| 19:10–19:13 | `ide1:0.present/startConnected` と `sata0:1.present/startConnected` をそれぞれFALSE、`boot.order` を `hdd` に変更。再読込み後のデバイス一覧は本体VMDKのみ。ESXiのEFIログが `About to do EFI boot: Ubuntu` を記録。導入済みOS上の `subiquity-server-debug.log` に `SUCCESS: curtin command install`、`Install/install/postinstall: SUCCESS`、`Install/install: SUCCESS`。保存された148,091 Bの `curtin-install.log` でもEFI・GRUB・kernel・完了処理を確認 |
| 19:13–19:15 | 本体コンソールで `nlp` ログイン。導入途中に見えたターゲット鍵と初回本体起動の鍵が異なったため、本体コンソールで実際の鍵を再取得した。3種の公開鍵を開発PCからの新規接続と照合。旧known_hostsを退避し、`.14` の3行だけを更新、残り17行のバイト一致。鍵SSH、sudo、時刻同期を確認したあと、署名検証を有効にした正規Ubuntuリポジトリの `apt-get update` と `full-upgrade` がともに終了0。38更新、追加・削除・保留0。続いてUFW・保存先・Podman・Quadletを設定 |
| 19:15–19:18 | 19:15:36.709 JSTにゲストから通常の `systemctl reboot` を1回実行。新しいboot IDで鍵SSH・サービス・コンテナ・chrony・固定IP・DNS・UFWを確認。19:17:59 JSTにもUTC差を再測定。ESXiはVM15電源ON・Tools稼働・`keiba-nlp`・`192.168.0.14` を報告 |

## 段階2Aの受入結果

| ID | 結果 | 実測した根拠 |
| --- | --- | --- |
| V1 対象と導入媒体 | PASS | VMID・名前・VMX・本体の接続と容量をホスト／ゲスト両側で照合。署名済みISO、新seedの生成・読戻し・VMFS extent・起動時デバイス、7424、採用した設定を照合 |
| V2 Ubuntu本体起動 | PASS | ISO・seedのデバイスと自動接続を解除。EFI、Ubuntu 24.04.5 LTS、hostname `keiba-nlp`、kernel `6.8.0-151-generic`。本体2回の起動ともext4 rootは `/dev/mapper/ubuntu--vg-ubuntu--lv` |
| V3 ディスク構成 | PASS | 本体100 GiB・GPT。sda1は1 GiBのESP/vfatを `/boot/efi`、sda2は2 GiBのext4を `/boot`、sda3は `ubuntu-vg` のPV。PV・VG・root LVは96.95 GiB、24,818 extents、空き0。初回の `df -hT /` は95G、使用6.8G、利用可能84G |
| V4 管理接続 | PASS | ECDSA・Ed25519・RSAの3公開鍵について、固定順の照合値 `3e95e37c69d85defd455dc1525253eaf757b9171068f11ff6db50374507f3f97` が本体コンソールとSSHで一致。Ed25519指紋 `SHA256:7ZfAYskmNrEPnyKLghiXN4oVp1PqmQ7BxtEgK9fTnzc`。既存の管理鍵で `nlp`（UID 1000）が接続し、既存秘密を用いたsudoでUID 0。開発PCに対するsshd実効値はpublickey有効、password・keyboard-interactive無効。別接続でサーバーが提示した認証方式は `publickey` のみ |
| V5 ネットワーク | PASS | 再起動前後ともMAC一致、`enp0s17 192.168.0.14/24`、static default via `192.168.0.1`、リンクDNS `192.168.0.1`。`archive.ubuntu.com` のIPv4名前解決成功 |
| V6 時刻 | PASS | live待機中にUTC補正。導入済みOSはAsia/Tokyo・RTC UTC・VMware Tools周期同期Disabled。chronyは初回 `^* 138.2.23.206`、再起動後 `^* 85.121.50.82`（同期元はいずれもstratum 2）、ゲストstratum 3、Leap Normal、`NTPSynchronized=yes`。独立したCanonical NTPとのUTC差上限は初回0.332秒、再起動後0.359秒、再測定0.834秒。SSHでの取得区間とNTP往復の半分を含む |
| V7 FW | PASS | UFW有効・incoming既定deny。IPv4のTCP 22と5432だけを `192.168.0.0/24` から許可。有効化後の新規鍵SSH成功、再起動後にも同じ実効ルール。TCP 5432のLISTENは0、導入済みPostgreSQLパッケージ0 |
| V8 Podman | PASS | rootful Podman `4.9.3+ds1-1ubuntu0.2`、rootless=false、cgroup v2、systemd manager。公式Alpine `3.23` のindex `sha256:469c9ea410b9215eaee7976ba6c0639039b444be8e5d638f7abbada189971eb2`、linux/amd64 `sha256:644c1ad8fc45cc581ab1b5ea7ec1bebc9b037fd4801ad697ca124deb3f9c9332` を照合。固定digestをpullし、ネットワークなしの `echo ok` は出力 `ok`、終了0 |
| V9 Quadletと通常再起動 | PASS | `/etc/containers/systemd/nlp-demo.container` は `/srv/nlp/quadlet/nlp-demo.container` を参照。Git対象と配置ファイルのSHA-256は `4bc99f9d7369b6741aad5e4f0ca7a3dfb5674c8fcfd12f64915f63b56d068590`。生成先 `/run/systemd/generator/nlp-demo.service`、状態generated、multi-user.targetの依存に存在。再起動後に手動startなしでサービスactive/running、コンテナrunning、network=none、公開ポート0。確認時の再開始回数0 |
| V10 保存先・データ保全 | PASS | 全てroot:root。`/srv/nlp/pgdata` 0700・空、`articles` と `dumps` 0750、`quadlet` 0755。PoCは開始時と終了時とも24件・31,060 B・SHA-256 `e2eaf61190353c4b10cc3175b8a24dfe9b69d577c42189df192700266810ad16`。退避した5ファイルすべてが元の作業ツリーと一致 |
| V11 範囲とGit引渡し | PASS | 実機変更はVM15とその媒体に限定。開発PCは作業用ファイルと照合済みknown_hostsを更新した。他VM・ESXi全体・共用検索・v3の設定変更0件。対象は修正版6ファイルと本レポート。最終commitと `origin/main` の照合結果は引渡しメッセージに記載 |

通常再起動前のboot IDは `00b2d3e7-6681-49d9-978c-9edc30f08a7b`、再起動後は `c10b57c4-11e9-4703-a55b-323e9631bdc2`。再起動要求を起点に、開発PCから**鍵SSHを23.0秒、サービスとコンテナの両方を23.3秒、chrony再同期を30.52秒**で初めて観測した。時間はポーリングを含む。再起動後のfailed unitは0件。復帰したコンテナの開始時刻は19:15:58.094 JST。

## 最終状態と引渡し

**段階2A完了。** VM15は本体から稼働し、管理接続は `nlp@192.168.0.14`。ISOと両seedは未接続。旧seed、新seedの記述子・extent、VMX退避物は保持した。切断後の新extentは生成時と同じSHA-256。ESXiが記述子にTools関連の2キーを追加し、最終記述子SHA-256は `9289dec9abe4fe5112712f7ca3d97ae6e06f972e3e24c67f58dacc1690de0581`。新媒体の作業用アップロード複製はローカルおよび切断後のextentとの一致を確認して削除した。新seedとVMX退避物はESXi上でrootの0600。ESXiのホスト時計は11月22日19:16 JSTの照合時も約37時間23分遅れで、ホストログの時刻にはこの差が残る。

修正版は [883604f](https://github.com/kendo910x/keibaAI_nlp/commit/883604fe82ce29ce7ed808558427fb63e9059eb6)。元の開発ツリーとPoCは保全し、独立worktreeから対象を限定して引き渡した。時刻照合は `utc-samples.jsonl` と `guest-utc.jsonl`、通常再起動は `reboot-measurement.json`、ゲストの検証値は `e-*-observed.txt`、媒体交換は前述の非公開領域のVMX・記述子・コンソール画像に保存した。

後続は、ESXiホスト全体の時計・NTP、共用検索の429待機と再試行、段階2BのDB設計・PoC 24件移行、収集ジョブの中断再開、既報の別サービスの認証情報更新。これらは今回の実施対象外で、既存の検索・LLM・v3の稼働系には変更を加えていない。
