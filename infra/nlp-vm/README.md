# VM15 `keiba-nlp` の導入と受入

2026年11月27日以降の収集・閲覧の配置、運用開始待ちの3処理、再開時の管理コマンドは[VM15の通常運用手順](runtime/README.md)を参照する。

対象は既存の VMID 15、`[datastore1] keiba-nlp/keiba-nlp.vmx`。構成は EFI、HW14、2 vCPU、8 GiB、LSI Logic の 100 GiB thin VMDK、VLAN 101 の E1000 1枚。作業範囲、停止条件、V1〜V11 は[復旧指示書](../../docs/instructions/2026-11/2026-11-22_nlp_vm_recovery_instruction.md)、実施した工程と電源・媒体の最終状態は[実測レポート](../../docs/reports/2026-11/2026-11-22_nlp_vm_recovery_report.md)に記録する。

2026-11-22の受入では両媒体を切断し、Ubuntu 24.04.5を本体からEFI起動した。管理接続は `nlp@192.168.0.14`。通常再起動後にrootful Podmanの `nlp-demo` が自動起動し、`pgdata` は空、TCP 5432の待受は0件だった。

## インストール媒体の用意

1. 開発PCで既存の5ファイルを保全し、Git作業用のコピーを使う。実値を含む作業先のWindows ACLを本人とSYSTEMに限定する。開発PCのPoCの件数・サイズ・SHA-256を作業前後に照合する。
2. Ubuntu Server 24.04.5 LTS amd64のISOを、CanonicalのCD Image鍵 `843938DF228D22F7B3742BC0D94AA3F0EFE21092` で検証した `SHA256SUMS` と照合する。今回のISOは `97f3d7ffb032c3eb3b23d2c8be9cc76e60c2c1f2c0146ba5ba9fe01cafae0fd8`。ESXiで接続中のファイルも全体をハッシュする。[Canonicalの検証手順](https://ubuntu.com/tutorials/how-to-verify-ubuntu)
3. ISO内の `casper/ubuntu-server-minimal.ubuntu-server.installer.squashfs` から `var/lib/snapd/seed/snaps/subiquity_7424.snap` を取り出す。snapのSHA-256は `2d9ce94e9dc4af41e310cfb0f1f5508fd8eaa5aa821a1aa0e7bd30c03c843f00`。展開した `meta/snap.yaml` の版、server・controller・filesystemモデル・使用コントローラーのソースとCanonicalタグの対応を確認する。検証に使うスキーマのSHA-256は `0e022b0dd2232868eab0039c8efa5b19d6f7c5ce2a751c7936080dde6cba95d4`。[Canonical 24.04.5の固定スキーマ](https://github.com/canonical/subiquity/blob/7639acf9b526966633f0b50c1397fd4f2cae4254/autoinstall-schema.json)
4. Linuxユーザーランドの一般ユーザーで次を実行する。必要なものはPython 3、PyYAML、jsonschema、OpenSSL、OpenSSHクライアント、dosfstools、mtools。引数はすべてパス。既存のコンソール用パスワードと開発PCの管理用公開鍵を指定する。出力は保護済み領域に新規作成するディレクトリとする。

```sh
python3 infra/nlp-vm/make_seed.py "$schema_file" "$console_password_file" "$admin_public_key" "$new_private_dir"
```

スクリプトはSHA-512 cryptハッシュを生成し、公開鍵の鍵種・本体を埋め、重複キー・未展開箇所・スキーマ・対象ディスク指定を確認する。8 MiBの `cidata.img` にVFATラベル `CIDATA` を付け、`user-data` と `meta-data` を書き込む。両ファイルを読み戻してバイト単位で照合し、サイズとSHA-256を表示する。媒体識別子は `keiba-nlp-vm15-recovery-20261122-r2`。展開ファイル・媒体・コンソール秘密・生ログは保護済み領域だけに保存する。再生成するとパスワードのソルトと媒体のハッシュが変わる。

## 既存VMへの接続と導入前の確認

- 実VMのVMID・名前・VMX、VMX内の `scsi0:0` と100 GiBの記述子・extent、MAC `00:0c:29:3a:81:3b`、空き容量、`.14` の隣接情報を確認する。既存live環境で `findmnt /`、`lsblk`、`wipefs -n /dev/sda`、`pvs; vgs; lvs` を調べる。本体のudev ID_PATH `pci-0000:00:10.0-scsi-0:0:0:0`、容量、署名、子デバイスを照合する。旧エラー、seed、各時計を保全し、既知のVM15コンソールで**入力と画面読取りの両方**が使えることを確認する。
- ESXi上に新規の8 MiB VMDKを `vmkfstools -c 8m -d thin nlp-seed-recovery-r2.vmdk` で用意する。名前の空きを確認し、記述子の `RW 16384 VMFS` と**その記述子が指す新規・未接続のextent**を確認する。8 MiBの検証済み生イメージをそのextentだけに `dd` の `conv=notrunc` で複写し、サイズと全体SHA-256を再照合する。旧seed・本体VMDK・元のVMXは保全する。
- A〜C完了後にliveゲストを正常停止して電源OFFを確認する。導入時はOS ISOを `ide1:0`、新VFAT seedの**記述子**を `sata0:1` のdiskとして接続する。`vmx/keiba-nlp.vmx.tpl` は項目の見本。実VMXで変更するのは媒体・起動・VM15固有の時刻同期設定。UUID・MAC・PCIスロットを含む実VMXの全置換やVM再登録は行わない。設定再読込み後にデバイスと差分を確認する。
- ESXi 6.7では `tools.syncTime` が周期同期、テンプレートの7個の `time.synchronize.*` がTools起動・復帰等での単発同期に対応する。VM15で両方を無効にし、ホスト時計の遅れを別件として記録する。[Broadcomの旧版向け設定](https://knowledge.broadcom.com/external/article?legacyId=1189)

### 復旧用seedの待機解除

新bootの `early-commands` は `timeout 600` で最大600秒待つ。revision 7424では早期設定を読み、ここを実行し、通常設定を再読込みしてからコントローラーの起動・適用に進む。解除前にVM15のコンソールから以下を確認する。

実機では、既存のESXi SSHからVMID 15専用のWebMKSチケットをメモリ内で取得し、ESXiの証明書を照合したTLSの共有コンソールを使用した。liveのtty2に切り替えて確認し、解除後はtty1に戻ってインストーラーの確認に応答した。チケットや接続URLはログに出さない。

1. EFI、snap revision 7424、MAC、`/dev/sda` が本体100 GiBであること、署名・子パーティション・LVMがないこと、`/dev/sdb` が8 MiBのCIDATAであること。`lsblk -o NAME,SIZE,TYPE,MODEL,HCTL,FSTYPE,LABEL`、`ls -l /dev/disk/by-path` 等で対応付ける。
2. 媒体のファイル・cloud-initキャッシュのハッシュ、instance-id、採用したデータソース、`/autoinstall.yaml` の実効設定を照合する。YAMLは外側の `autoinstall` をそろえて構造比較し、結果だけを出力する。
3. UTCを信頼できるNTP等と照合し、必要ならこのliveゲストでシステム時刻を補正し、ISO同梱の `busybox hwclock -w -u` で仮想RTCに書き戻す。取得遅延、UTC差、`vmware-toolbox-cmd timesync status` とVMXの単発同期設定を記録する。
4. 上の照合が成立してからrootで `touch /run/keiba-nlp-recovery-ready`。ISOが確認を表示した場合も同じ照合後に進める。600秒で解除されなければ早期コマンドは失敗する。進捗を短い間隔で監視し、エラー時には証拠を保全する。

## インストール後の構成と受入

- installerの正常終了と電源OFFを確認して、ISOとseedの両方を切断し、自動再接続を解除する。EFIで本体を起動し、保存されたSubiquity・curtinの完了記録、Ubuntu 24.04、hostname、GPT・ESP/FAT・`/boot/efi`・LVM rootと容量対応を照合する。
- 管理接続は `nlp@192.168.0.14`。コンソールでホスト公開鍵の指紋を照合し、開発PCの既存known_hostsを退避して該当エントリだけを更新する。鍵SSH、sudo、sshd実効設定と別接続を確認する。固定IPv4は `.14/24`、GW/DNSは `.1`。chronyの同期・UTC差を確かめてから正規APTの更新を行う。
- UFWはLAN `192.168.0.0/24` からTCP 22を先に許可し、同じLANから5432を許可。incomingの既定deny、有効化後の新規SSH、5432の待受なしを確認する。`/srv/nlp/{pgdata,articles,dumps,quadlet}` の所有・権限を記録し、`pgdata` は空で保持する。
- rootful Podmanの版・cgroup v2を確認する。公式 `docker.io/library/alpine:3.23` のindex digestはQuadletの `Image=` に固定した。最初に同じdigestをpullし、`podman run --rm --network=none <固定イメージ> echo ok` の終了コードを記録する。
- `quadlet/nlp-demo.container` を `/srv/nlp/quadlet/` に配置し、`/etc/containers/systemd/nlp-demo.container` から参照する。rootで `systemctl daemon-reload`、`systemctl start nlp-demo.service`。生成元・生成unit・コンテナrunningを確認する。自動起動はQuadletの `WantedBy=multi-user.target`。通常rebootの前後でboot IDと時刻を記録し、手動startなしでSSH・固定IP・DNS・chrony・UFW・サービスとコンテナが復帰した時点を測る。
