# KeibaAI NLP 実機状態確認レポート

| 項目 | 現在の実測 | 証拠／観測時刻（2026-11-22 JST） | 未確認・次に必要なこと |
| --- | --- | --- | --- |
| 対象VMの同定・電源 | VMID 15、`keiba-nlp`、`[datastore1] keiba-nlp/keiba-nlp.vmx` の三者が一致。電源ON | 17:09–17:10 ESXiのVM一覧と `get.summary`。14番は `ubuntu-gateway` | 復旧時も同じ三者を照合する |
| Ubuntu導入段階・現在のエラー | インストールISOのlive環境。Subiquityが初期ユーザーの設定読込みで停止。Ubuntuの導入は未完了 | 17:14の画面と17:22–17:27のゲスト内ログに `neither identity nor user-data provided`。100 GiBの本体ディスクに子パーティションの表示なし | 修正したseedでの導入は後続 |
| IP/SSH・live環境か導入済みか | `.14` へのpingは0/2、TCP 22はタイムアウト。ゲストは `ubuntu-server`、rootは `/cow` のoverlay | 17:10 SPRから疎通。17:22–17:27に `findmnt`、`lsblk`、`ip -br addr`。`enp0s17` はリンクローカルIPv6のみ | `nlp` の鍵認証と導入後の固定IPv4は未検証 |
| 実VMXとテンプレート | OSのISOはIDE 1:0。SATA 0:1はローカルでseed ISO、実機で8 MiBのseed VMDK | 17:10–17:14 `device.getdevices`、VMX、起動ログ。17:29に全設定キーを再比較 | 後続で媒体方式とテンプレートを揃える |
| 接続seedと実効設定 | `/dev/sdb` の `CIDATA` をNoCloudが採用。手元の展開済みuser-data、実メディア内ファイル、cloud-initキャッシュのSHA-256が一致。実効YAMLとも構造・値が一致 | 17:22–17:27 `grub-fstest`、`sha256sum`、`cloud-id`、ゲスト内YAML比較 | 実効設定では `identity` と `user-data` が両方欠落 |
| ローカル5ファイル・Git差分 | 指定5件は全て存在し、全て未追跡。元ツリーにtracked差分・ステージ済み差分はない | 17:09 `git ls-files`、属性、SHA-256。17:28に一覧再照合 | 既存ファイルを復旧作業の入力として保持 |
| PoCデータ | JSONLは31,060 B、24件、異なるURL 24件、空text 1件。由来を示す3フィールドは全24件に残る | 17:09–17:11 全行JSON解析・属性・SHA-256。17:28にハッシュ再照合 | DB移行は後続 |
| Podman/Quadlet・DBの有無 | 導入済みOSに到達する条件を満たさず、段階2Aの受入確認は今回未実施 | 17:22–17:27 liveの起動元・ディスク構成を確認 | 対象OS上の版、unit、DB、再起動復帰は未確認 |
| 残存プロセス | 構築時から継続するVM監視・SSH転送・ISO作成プロセスは対象照合で検出0件。Hermesと旧ローカル検索用のPythonは生存 | 17:10、17:20 SPRのプロセス名・PID・親PID・開始時刻・用途を照合 | 過去の監視終了通知からインストール成否を判定しない |
| 検索サービス・クライアント設定 | Deployment 1/1、Pod 2/2 Ready、両コンテナ再起動0。health HTTP 200、Python MCPの `tools/list` は2件。両アプリにURL登録あり | 17:11–17:13 K8s・HTTP・MCP、17:20–17:28 アプリ設定と同期記録 | Hermes・LM Studio自身の検索／本文取得の成功は未確認 |

## 調査範囲と基準版

開発PC `SPR`（Windows 11 Pro 10.0.26300、PowerShell 7.6.9）から調査した。実機観測開始は17:09:35、最終観測は17:29:33 JST。対象はNLP専用VM、開発PCの構築物・PoCファイル、および共用検索の既存経路。両repoの作業規約、引き継ぎ書、配置設計、段階2A・2B指示書、OpenWebUIの共用検索レポートと接続ガイドを参照した。K8s接続正本はDivRoomの `3df2143` のGitオブジェクトから読んだ。[今回の指示書](../../instructions/2026-11/2026-11-22_nlp_actual_state_check_instruction.md)・[配置設計](../../design/2026-11-22_nlp_infrastructure_placement.md)・[段階2Aの受入条件](../../instructions/2026-11/2026-11-22_nlp_vm_build_instruction.md)・[段階2Bの予定](../../instructions/2026-11/2026-11-22_nlp_db_and_poc_migration_instruction.md)

| repo | 調査時のbranch・ローカルHEAD | 調査時のリモートと差分 |
| --- | --- | --- |
| `kendo910x/keibaAI_nlp` | `main`、`05e30b267cdf48a473fa83a65bef327224347393`（指示書追加前の基準版と一致） | 開始時のローカル `origin/main` も同版。`ls-remote` と `fetch` 後は指定の `4207b16519c2a1d8ab7d3490ec35116b8e943537`。間のtracked差分は今回の指示書1件追加のみ |
| `kendo910x/OpenWebUI` | `main`、`cd68ec56267eccee87abf1f740df3eed3fd7eabb` | 指示書の基準、ローカル `origin/main`、実リモートが一致。tracked差分なし。開始時から検索サーバーの `__pycache__/yahoo_search_server.cpython-314.pyc` 1件が未追跡 |

## 停止原因と採用された設定

**実測確認済み。** 対象VMは `/dev/sr0` の Ubuntu Server 24.04.5 LTS amd64を `/cdrom` に持ち、カーネル引数に `BOOT_IMAGE=/casper/vmlinuz` がある。rootは `/cow`（overlay）、`/rofs` はsquashfs。`/dev/sda` が100 GiB、`/dev/sdb` が8 MiBのvfat。`/dev/sda` にパーティション・LVM・マウント先の表示はない。VMware Toolsは `guestToolsRunning` で、ゲスト内でも `enp0s17` に `fe80::20c:29ff:fe3a:813b/64` を確認した。想定の `192.168.0.14/24` は付いていない。TCP接続が成立せず、SSH認証・ホスト鍵交換には至っていない。旧IPの既存 `known_hosts` エントリは保持した。

| 確認層 | 観測結果 |
| --- | --- |
| 1. ローカル `user-data.tpl` | `autoinstall.users` があり、`autoinstall.identity` と `autoinstall.user-data` がない。`ssh.allow_pw` と、ユーザー項目 `plainlocktext` がある |
| 2. 展開済み `scratch/seed/user-data` | テンプレートとYAML構造が一致。値が異なるのは予定されたパスワード欄と公開鍵欄の2か所だけ。未展開プレースホルダー0。ファイルSHA-256は `8b5d20f963a1bb96285d3c6378459410bd492a6084bbf8b1a130654e8bd54dc3` |
| 3. 接続中の実メディア | ゲストから `/dev/sdb` をハッシュし、ローカルとESXiの `nlp-seed.img` のSHA-256 `e4d055fa6da3b8a7d423f549140a7422b85e46654d7ad2dfbe52f04d5d5645f8` と一致。既存 `grub-fstest` でマウントせずに `/user-data`・`/meta-data` を読み、各ハッシュも手元の展開済みファイルと一致。ESXiから稼働中のflatを直接開くと `Device or resource busy` だったため、ゲストで同定したseedデバイスを用いた |
| 4. ゲストが採用した内容 | OS側cloud-init `26.1-0ubuntu1~24.04.1`。`cloud-id` は `nocloud`。`/var/lib/cloud/instance/datasource` と `/var/log/cloud-init.log` に `DataSourceNoCloud`・`/dev/sdb` が残る。`/var/lib/cloud/instance/user-data.txt` は層2・3のuser-dataとバイト一致。`/autoinstall.yaml` （SHA-256先頭 `f6d7287a0b6e`）は外側の `autoinstall` を外した形式で、YAMLとして読み込むとキャッシュの `autoinstall` 配下と値を含めて完全一致した |

Subiquityは **24.04.5、snap revision 7424**。起動画面の `Identity/load_autoinstall_data` と `load_autoinstall_config` に同じエラーが出ている。このbootの `/var/log/installer/subiquity-server-debug.log` 95・96・108・109行で同じ文言が4回記録された。タイムスタンプ付きの2行はゲスト時計 `2026-11-20 18:15:29,202`。実行中のsnapの `subiquity/server/controllers/identity.py` 136行に `user-data` の分岐、147行にこの例外がある。実効設定の `users` は `autoinstall` 直下にあり、この分岐の条件を満たさない。**このbootの直接の停止原因は初期ユーザー定義の階層にある。** seedの接続と採用は成功している。[Ubuntu autoinstall仕様](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html#user-data)・[Canonicalのidentity実装](https://github.com/canonical/subiquity/blob/main/subiquity/server/controllers/identity.py)

次の2点も現物で確認した。いずれも今回の停止を起こした箇所とは別に検証が必要になる。

- **SSH・パスワード項目。** 展開済み・実効設定に `ssh.allow_pw` がある。revision 7424の `ssh.py` 44・62行で定義・参照する名前は `allow-pw`。展開後の `plainlocktext` は非空のスカラーで、モジュラーcrypt形式のハッシュではない。ゲストのcloud-initスキーマにはこの項目の定義がなく、`passwd`、`hashed_passwd`、`lock_passwd` 等の定義を確認した。導入後の実際の認証動作は未確認。[UbuntuのSSH設定](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html#ssh)・[cloud-initのユーザー設定](https://docs.cloud-init.io/en/latest/reference/modules.html#users-and-groups)
- **UEFIとstorage。** 実VMはEFI。設定はGPT指定の `/dev/sda` を直接 `vg-nlp` の構成デバイスとし、root 90G・swap 4Gを定義する。EFI System Partition、FATフォーマット、`/boot/efi` マウントの定義はない。設定ロード中に停止しており、このbootの `/var/log/installer/` 直下にcurtinのログは見当たらない。ディスク作成やブートローダー導入で生じる結果は未検証。

## ESXiの設定・ファイル・時刻

`ssh esxi-divroom` で `getallvms`、`power.getstate`、`get.summary`、`get.config`、`device.getdevices`、実VMX・VMDK記述子と現行 `vmware.log` の該当箇所を読み取った。時刻には大きなずれがある。**SPR 11月22日17:11:05 JST時点でESXiは11月20日18:47:50 UTC**、約37時間23分遅い。ESXiの `bootTime` は11月20日18:14:01 UTCで、この差を用いた概算はSPRの11月22日16:37:16 JST。既報の16:37:17の手動ONと整合する。VMware Toolsの名称・電源通知だけでは導入完了を判定していない。

| 項目 | 設計の想定 | ローカルVMXテンプレート | 実機 | 差分・根拠 |
| --- | --- | --- | --- | --- |
| VM・CPU・RAM | `keiba-nlp`、2 vCPU、8 GiB | 2 vCPU、2コア/ソケット、8192 MiB | 同左、HW14、`ubuntu-64` | 一致 |
| firmware／起動順 | EFI、構築時はOSのISO起動 | `firmware=efi`、Secure Boot無効、`boot.order=cdrom`、delay 0 | VMXは同じ。APIの `bootOrder` は未設定 | 今回の実際の起動先はログの `EFI VMware Virtual IDE CDROM Drive (IDE 1:0)` で確認 |
| NIC | E1000×1、VLAN 101 | E1000、起動時接続、MAC自動、PCIスロット32 | E1000、VLAN 101、実接続あり。MAC `00:0c:29:3a:81:3b`、スロット17 | スロットと自動生成値。ゲストのインターフェース名は `enp0s17` |
| 本体ディスク | 100 GiB thin、LSI Logic | `scsi0:0=keiba-nlp.vmdk`、コントローラスロット160 | 同パス、100 GiB thin、スロット16 | 容量・thinはAPIと記述子で確認。テンプレート単体には容量の指定なし |
| OSのISO | Ubuntu Server 24.04 LTS | `ide1:0`、`iso/ubuntu-24.04.5-live-server-amd64.iso` | 同じISOが接続中 | ログにCD-ROM接続とEFIからの起動。ローカルISOのmanifestにもrev 7424 |
| seed | NoCloud入力を供給 | `sata0:1`、`cdrom-image`、`keiba-nlp/nlp-seed.iso` | `sata0:1`、`disk`、`nlp-seed.vmdk` → `nlp-seed-flat.vmdk` | 主要な構成差。実メディアは8 MiBのFAT12、ラベル `CIDATA`。旧ISOは残存、現VMに未接続 |
| UUIDほか | VM固有値 | BIOS・location UUIDはプレースホルダー | 展開値あり。MAC、swap・実行時情報などをESXiが追記 | 共通キーで値が異なるのはUUID 2個、PCIスロット2個、seedの型・パスの計6個 |

仮想ディスク記述子は本体 `RW 209715200`、seed `RW 16384`（512 Bセクター）。現行ログには両ディスクのopen、OSのISO接続、EFI起動がこの順で残る。CD-ROMの未対応命令 `0x52` も記録されているが、ゲストはその後に起動し、上記の設定例外に到達した。次表のmtimeは補正前のESXi時計で、日付は全て2026-11-20 UTC。

| `[datastore1]` 配下。接頭辞省略時は `keiba-nlp/` | バイト数 | mtime | 用途 |
| --- | ---: | --- | --- |
| `keiba-nlp.vmx`／`keiba-nlp.vmx~` | 3,032／3,014 | 各18:14:01 | 実VMX／既存の退避版。現行VMX SHA-256 `e5a7bc09d4da1a377591e82742b80d56a591b3d20fc7101b5b583401b18e0f74` |
| `keiba-nlp.vmdk`／`keiba-nlp-flat.vmdk` | 536／107,374,182,400 | 17:38:42／17:36:06 | 本体記述子・論理長。flatの全件読取りは今回未実施 |
| `nlp-seed.vmdk`／`nlp-seed-flat.vmdk` | 467／8,388,608 | 各18:13:59 | 接続中のseed記述子と実体 |
| `nlp-seed.img`／`nlp-seed.iso` | 8,388,608／376,832 | 18:13:49／17:36:06 | 手元の同名ファイルと各ハッシュが一致。旧ISOのuser-dataは展開済み最新版と異なる |
| `iso/ubuntu-24.04.5-live-server-amd64.iso` | 4,080,486,400 | 17:37:18 | 接続中のOSのISO。今回、全件ハッシュ・署名の再検証は未実施 |

## 開発PCに残る構築物とPoC

`C:\Users\kendo\keiba_nlp\infra\nlp-vm\` 配下の5件。時刻は11月22日JST。全件が未追跡で、元HEADと調査時の `origin/main` のどちらにも比較対象のGit版はない。

| 相対パス | B | 更新時刻 | SHA-256 |
| --- | ---: | --- | --- |
| `README.md` | 1,826 | 15:52:13 | `b7022dcbcdcaac5963596eab88ebd7db0ef380edb2d2d18f016b54da206ae196` |
| `vmx/keiba-nlp.vmx.tpl` | 2,323 | 16:27:59 | `efac2cb1a51bc745fe07c782ec94d84a6c5b7bdead1414fe267948be97431500` |
| `autoinstall/user-data.tpl` | 2,649 | 16:33:24 | `1f62c5382f21c944cbef0b52870c9c6e840718905dd582a8171c074b09ead6d7` |
| `autoinstall/meta-data.tpl` | 64 | 15:51:58 | `81e3d93d40c12bea793b0441d230ae998c4d7b7bef3f7b29b0c9e139746271a9` |
| `quadlet/nlp-demo.container` | 334 | 15:51:58 | `90e82a5bdf175180b229f15fd9aaed26e7bb8a9ee5374f9ef5705876cc368258` |

展開・作成途中のファイルは `%LOCALAPPDATA%\hermes\cache\scratch\` に残る。次は当該作業分のみ。実値seedはローカルに保持する。

| 相対パス | B | 更新時刻（JST） | SHA-256 |
| --- | ---: | --- | --- |
| `seed/user-data` | 3,202 | 16:36:41 | `8b5d20f963a1bb96285d3c6378459410bd492a6084bbf8b1a130654e8bd54dc3` |
| `seed/meta-data` | 64 | 16:36:41 | `81e3d93d40c12bea793b0441d230ae998c4d7b7bef3f7b29b0c9e139746271a9` |
| `seed/nlp-seed.img` | 8,388,608 | 16:36:59 | `e4d055fa6da3b8a7d423f549140a7422b85e46654d7ad2dfbe52f04d5d5645f8` |
| `seed/nlp-seed.iso` | 376,832 | 15:59:09 | `4f574d9dabf03fc878b67ea47b538c921f0193dae554d1384c8720646612e033` |
| `keiba-nlp.vmx` | 2,225 | 15:59:27 | `ac08a05319dc9fe171a1878b8a059035f8eca55bbc3b89d9fe8d3c03150c7de6` |
| `user-data.tpl` | 2,684 | 15:58:49 | `f4a85377a26ee1cfc3d00a009acc81b5c83d0b621c77896a4b566cd63f16977d` |
| `SHA256SUMS`／`SHA256SUMS.gpg` | 893／833 | 15:55:36／15:55:37 | `728064ecf411f4ab702d9c3ca0a938ce672771424c028a1b52b2449f7eb5a068`／`f9be4b4a527b63f14dde0387edcb7a02ba3ac43d537b1674a5aeae19c6f23827` |
| `ubuntu-24.04.5-live-server-amd64.iso` | 4,080,486,400 | 15:55:35 | 大容量のため今回のハッシュ対象外 |

`C:\Users\kendo\DivRoom\.secrets\keiba-nlp-console.pass` は存在し、25 B、更新15:52:19。属性とACLだけを読んだ。ACLは親からの継承で、SYSTEM・Administrators・ローカルユーザーのフル制御のほか、CodexSandboxUsers等の変更権限がある。

`data/poc/g1_passages.jsonl` は `.gitignore` の `data/` 対象。更新07:18:41、**31,060 B**、SHA-256 `e2eaf61190353c4b10cc3175b8a24dfe9b69d577c42189df192700266810ad16`。24行を個別にJSONとして読めた。`source_url` の空欄0、同一文字列の重複0、`text` の空欄1。全24件に `source_url, media, title, published_at, observed_at, race_label, horse_name, speaker, info_kind, text, summary, text_kind, notes` が揃い、`summary`・`text_kind`・`notes` は全件で非空。段階2B指示書がJSONLのサイズとして記載した23,714 Bは、今回の実測では次表のEmbedding結果のサイズと一致する。

| 同じ `data/poc/` 配下の既存結果 | B |
| --- | ---: |
| `embedding_search_g1_results.json` | 23,714 |
| `embedding_search_results_fp32.json` | 7,882 |
| `embedding_search_results.json` | 7,886 |
| `yahoo_explore_queries.json` | 6,617 |
| `yahoo_fixed_queries.json` | 4,215 |

## Hermes・残存プロセスと共用検索

**開発PCで実測。** CIMでプロセスの実行名・開始時刻・親PIDと用途を照合した。17:10の並行調査が一時的に起動したSSH／PowerShellを除外し、17:20にも構築開始前後のプロセスを確認した。対象VMの監視、転送、ISO作成を続ける該当プロセスは検出しなかった。

| 開始（JST） | 生存していたプロセス | 確認した役割 |
| --- | --- | --- |
| 06:41:46 | Python PID 26840 | Hermes gateway |
| 08:02:07 | Python PID 26508 → 2504 | gateway配下の旧ローカル `yahoo_search_server.py`。Hermesログにも同時刻のstdio登録記録 |
| 14:37:49–14:38:25 | mcpo配下のPython。検索サーバーのPID 24816 → 28364も生存 | ローカル検索PoCのプロセス系列。VM構築とは別 |
| 14:58:24 | LM Studio親PID 7284、子プロセスあり | アプリ起動中 |
| 17:01:36 | Hermes Agent PID 30080ほか同時刻のGUIプロセス | GUI起動中。先の構築セッションの継続を示す証拠はない |

**既存ログのみ。** 指示書にある16:41:24の `262132 / 262144` は先行セッションの報告。ローカル `agent.log` と `errors.log` では16:43:40–42に入力262177・上限262144のコンテキストエラーを確認した。時刻・数値が異なる記録として扱う。これはHermes側の会話処理の停止であり、ゲストのSubiquity例外は上記の別証拠で確定した。

| 確認点 | 実測／確認の限界 |
| --- | --- |
| K8s | 既存 `kubectl` にDivRoomのtalos用 `kubeconfig`、context `admin@divroom`、namespace `openwebui` を毎回明示。`google-search-mcp` はgeneration／observed 5、desired／ready／available各1。Pod `google-search-mcp-695ff976f6-c2dh2` はRunning、両コンテナReady・再起動各0 |
| イメージ | `google-search-mcp` と `yahoo-search-streamable` の指定image・稼働imageIDはともに `ghcr.io/kendo910x/openwebui-google-search-mcp@sha256:4ef494f2dbf0c6f41541bbf90f125398d062c8a1e2891e4e448becf5450ad1a9` |
| ServiceとHTTP | `google-search-mcp-streamable` は `NodePort 30081/TCP` → `8001/http-stream`、ClusterIP `10.105.48.123`。SPRから `http://192.168.0.11:30081/healthz` を1回GET、HTTP 200、`status=ok` |
| MCP | 既存venvのPython MCP 1.30.0で `/mcp` を初期化。protocol `2025-11-25`、サーバー `yahoo-search 1.30.0`。`tools/list` は `yahoo_search`・`fetch_page`。実ツール呼出0 |
| Hermes | `%LOCALAPPDATA%\hermes\config.yaml` の `mcp_servers.yahoo_search` はリモートURL `http://192.168.0.11:30081/mcp`、stdioコマンド・明示的な無効指定なし。生存中の旧stdioプロセスは確認したが、現在のGateway／GUIがこのHTTP先からツールを登録した記録は確認できなかった |
| LM Studio | `~/.lmstudio/mcp.json` の `yahoo-search` は同じリモートURLのみ。`.internal/last-synced-mcp-state.json` の当該エントリとも一致（14:58:28 JST更新）。アプリの設定同期まで確認。接続・ツール呼出の成功は未確認 |

**429の先行レビュー2点は配備ソース上でも確認済み。** ビルドrunのhead SHAは `173e031859acb2fffa0fdb5625160bfc8c0b5ccc`。publishログでこのSHAタグと `v0.3.2-mcpo0.0.20-shared.1` のpush digestが上記の稼働imageIDに一致した。調査時の `cd68ec5` までビルド対象ディレクトリにGit差分はない。ソース252–257行の20秒以下の分岐は共有クールダウン期限を更新せず当該呼出だけsleepして再試行する。261–263行は2回目の429の `Retry-After` を読まず、現在時刻＋既定30秒を共有期限にする。今回は実429の発生試験・待機試験・変更を行っていない。[ビルド・公開ジョブ](https://github.com/kendo910x/OpenWebUI/actions/runs/44990329269/job/137109764566)・[配備ソース](https://github.com/kendo910x/OpenWebUI/blob/173e031859acb2fffa0fdb5625160bfc8c0b5ccc/infra/google-search-mcp/yahoo_search_server.py#L242-L270)・[共用検索の既報](https://github.com/kendo910x/OpenWebUI/blob/cd68ec56267eccee87abf1f740df3eed3fd7eabb/docs/reports/2026-11/2026-11-22_shared_search_exposure_report.md)

## 再開地点・次の判断

1. **段階2Aの修正対象を選ぶ。** 手元の5ファイルと既存VM 15を起点とする。Server用の `identity` で初期ユーザー・ホスト名を作る方式か、`user-data.users` で初回起動時に作る方式かを決める。前者を採る場合は `identity.password` が要求するハッシュを用意する。いずれも鍵・パスワード項目、SSH設定を整理し、8 MiBのseedを対象ディスクから除いたうえで、本体にEFI System PartitionとLVMを明示する。実機で採用されたVFAT方式を維持する場合はVMXテンプレート・READMEも合わせる。
2. **再試行の前に確認する。** 対象版のスキーマで展開済み設定を検証し、生成後の媒体から読み戻す。実VMへの媒体交換・電源操作・本体ディスクへのインストールは後続タスクで範囲と実施可否を決める。その際はVMID・名前・VMX、ディスク容量と接続先を再照合する。
3. **導入後に受入を行う。** システムディスクからのEFI起動、root/LVM、`.14` の鍵SSH、時刻、FW、Podman/Quadlet、通常再起動後の復帰を段階2A指示書で検証する。その受入後に段階2BのDB・24件の移行を扱う。共用検索は独立に、必要な場合だけクライアント実呼出と429処理を別タスクで検証する。

**操作と副作用。** 既存SSH、K8sのget、health、MCP初期化・一覧取得、Git参照更新を行った。ESXiの画面読取りは対象VM 15に限定し、HTTPSでは既知のSSH経路で照合したホスト証明書を使った。ユーザーが開いたHost Clientで「Press enter to start a shell」を確認して一度だけ診断シェルに入り、上記の照会を実施した。ゲストは電源ONのまま、最後の画面はlive診断シェルのプロンプト。認証・接続・シェルの通常記録と、レポート用の一時worktreeが生じる。停止画面と照合後の画面は `%TEMP%\keiba-nlp-state-pzpvp2co\vm15-screen.png`・`vm15-shell.png` に限ってローカル保存した。

VM・Pod・サービス・認証の設定変更、電源操作、インストールの再実行、ディスクのマウント／修復、DB操作、記事取得、v3への接続は行っていない。元作業ツリー・実値seed・Git外のPoCファイルは調査前の場所に保持した。Git引き渡しの対象は本レポート1ファイル。
