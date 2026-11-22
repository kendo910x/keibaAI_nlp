# NLP専用VM構築 指示書（ESXi CLI / Ubuntu 24.04 / podman+quadlet）

作成日: 2026-11-22（JST） / 対象: ESXi `192.168.0.5`（esxi-divroom）への新VM + `kendo910x/keibaAI_nlp`（`infra/nlp-vm/`）
設計出典: 本repo `docs/design/2026-11-22_nlp_infrastructure_placement.md`（commit `4f9ebb4`）
前例: home-gateway `docs/reports/2026-11/2026-11-17_ubuntu_gateway_build_and_isolated_validation_report.md`（開発PCのローカルパス・Git管理外）— **同一ESXi・同一OSでVM作成〜OS導入までCLI完結の実証済み**（VMID14、2026-11-17 15:17〜16:44 JST）

## 1. 目的

ESXi `192.168.0.5` に NLP専用VM `keiba-nlp` を新設する。段階2B（専用DB）、段階3（研究エージェント）、後日（Embeddingワーカー）の配置先となる常時起動環境を作る。
完了時点: 開発PCからSSH到達、podman+quadlet 稼働、`/srv/nlp/` 作成済み、quadlet demo unit が再起動後も自動復帰。**実際のDB構築は本指示書の範囲外（段階2B）**。

## 2. 開始前に読むもの

- 本repo `AGENTS.md`、上記設計メモ
- home-gateway 構築レポート（vmx仕様・ISO検証・autoinstall・EFI/E1000/open-vm-tools の実測前例。ESXi 6.7.0 build-13006603・datastore1 VMFS6 同一環境）

## 3. 確定設計（2026-11-22 ユーザー合意済み。再議論しない）

| 項目 | 値 |
|---|---|
| VM名 / 配置 | `keiba-nlp` / `[datastore1] keiba-nlp/keiba-nlp.vmx` |
| OS | Ubuntu Server 24.04 LTS amd64（前例は 24.04.5）。datastore既存ISOを再利用、無ければ再取得し **Canonical署名済み一覧でSHA-256検証**（前例ISO: `97f3d7ff…` と一致すれば可） |
| スペック | 2vCPU / 8GB / 100GB thin、LVMでディスク全体を1VG化（拡張前提） |
| 仮想HW | 仮想HW 14・EFI・LSI Logic・E1000×1（ポートグループ `VLAN 101`） |
| ネットワーク | 静的 `192.168.0.14/24`、GW `192.168.0.1`、DNS `192.168.0.1`（前例の本番ゲートウェイ）。実行時に第4項-1で競合再確認 |
| 作成方法 | **CLI完結（ESXi root SSH）**: vmx作成 → `vim-cmd` 登録 → ISO接続 → autoinstall seed。無償ライセンスで govc write 不可（前例どおり vim-cmd 系）。UI手作業は不要 |
| VM内基盤 | **podman（rootful）+ quadlet + systemd のみ**。k8s・Compose 等を入れない |
| データ配置 | `/srv/nlp/{pgdata,articles,dumps,quadlet}`。quadlet unit は本repo `infra/nlp-vm/quadlet/` でGit管理し、VMの `/etc/containers/systemd/` から参照 |
| アクセス | ユーザー `nlp`（sudo、開発PCの既存SSH鍵、SSHパスワード認証無効）。コンソールパスワードは実行者が生成し開発PCのローカル秘密置き場（例 `DivRoom/.secrets/`）へ。Git commit しない |
| FW | ufw: default deny incoming、`22` と `5432` のみ `192.168.0.0/24` から許可（5432は段階2B用）。LAN限定・認証なしはユーザー承認済み |

## 4. 実施手順

1. **事前確認**: ESXi SSH到達 / datastore1 空き ≥120GB / `.14` 競合再確認（ping・ゲートウェイ隣接テーブル。ubuntu-gateway本番は `.1` へ移行済みで解放状態、2026-11-22実測）/ 既存VMID一覧から未使用ID選択（**14はubuntu-gateway使用中**）/ ISO所在確認とSHA-256検証
2. **VM作成**: 前例準拠でvmx作成（NIC1枚・thin 100GB・EFI・HW14）→ `vim-cmd` 登録 → 自動起動グループへ登録しない → ISO接続 → 電源ON
3. **autoinstall（NoCloud seed）**: hostname `keiba-nlp`、timezone `Asia/Tokyo`、LVM全ディスク、ユーザー `nlp`（SSH鍵・sudo・パスワードログイン無効）、パッケージ `openssh-server open-vm-tools chrony ufw podman`、sshd `PasswordAuthentication no`。seedテンプレは `infra/nlp-vm/autoinstall/` にパラメータ化してGit管理（秘密値をcommitしない）
4. **導入後**: `apt full-upgrade` → ufw設定・有効化 → quadletディレクトリ `/srv/nlp/quadlet` を `/etc/containers/systemd/` から参照 → repoの `infra/nlp-vm/quadlet/` を配置
5. **repo反映**: vmxテンプレ・autoinstall seedテンプレ・quadlet unit を `infra/nlp-vm/` に commit/push

## 5. 検証（実測値をレポートへ。測定していない項目にPASSと書かない）

1. `ping 192.168.0.14` / `ssh nlp@192.168.0.14`（鍵のみ）
2. `hostname` / `timedatectl`（JST）/ `chronyc tracking`（同期）/ `lvs`・`df`（LVM・100GB）
3. `podman run --rm docker.io/library/alpine echo ok` / `podman info` で cgroup v2
4. quadlet demo unit（常時停止する軽量コンテナ）→ `systemctl start` → **通常再起動して自動復帰**（起動時間目安も記録）
5. `ufw status verbose`（22/5432許可・その他deny）
6. 既存VM（ubuntu-gateway `.1`・talos-01 `.11`）・ESXi既存設定への変更が0件であること

## 6. 禁止・境界

- 既存VM・ポートグループ・uplink・管理ネットワーク・ESXi設定への変更（新規VM登録とdatastoreへのファイル作成のみ）
- k8s・Compose・自動起動グループ登録・`22`/`5432` 以外のLAN公開
- 秘密（パスワード・秘密鍵・seed実値）のGit commit
- PostgreSQL等の実DB構築・段階2Bのスキーマ作業
- 実Yahoo検索・外部Web収集（本タスクは使わない）

## 7. 完了・報告

- 実施レポート: `docs/reports/2026-11/2026-11-22_nlp_vm_build_report.md`
- 記録必須: VMID・vmxパス・ISO出所とSHA-256・podman等パッケージバージョン・検証各項目のPASS/FAIL・ディスク構成実測（lvs/df）・再起動復帰・残件
- 対象ファイルのみ commit/push し、`origin/main` 反映を確認

## 8. 停止条件（該当時は推測で進めず報告）

- `.14` の競合が実行時に実測された
- datastore1 空きが120GB未満
- ISOのSHA-256が検証一覧と一致しない
- ESXi SSHが到達できない、または前例と異なる制約でCLI作成が不可能
- EFI/E1000構成で起動しない（前例と矛盾）
