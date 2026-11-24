# 段階2B　VM15 NLP専用DB 構築・実測レポート

2026-11-24（JST）に VM15 `keiba-nlp` で B1〜B10 がすべて合格した。通常DB `keiba_nlp` は PostgreSQL 16.16 と pgvector 0.8.7 で稼働し、8表とも0件。検証DBは永続性の照合後に削除した。

| 照合対象 | 値 |
|---|---|
| 指示書・作業基準 | `909360f9b34246cf1b7c9b7c11d8f305540ab12b`。2026-11-24 改訂指示書241行 |
| 参照した段階2A受入版 | `814d5144e495c72e6e1cc5e01498861338a4b064` |
| 実機適用・試験資材のコミット | `c059243fbfc3d587241b09b4c0acfbf2f0bc2cfe`。本レポートはその直後の別コミット |
| 実行経路 | 開発PCから既知のホスト鍵で `nlp@192.168.0.14` に SSH、sudo、rootful Podman。LANクライアントは開発PCの psycopg 3.3.9 |
| 作業ツリー | 最新 `origin/main` から独立した worktree。元の開発 main は `05e30b267cdf48a473fa83a65bef327224347393` |

## 実機の開始状態と配備

11:45台に、Ubuntu Server 24.04.5 LTS、`enp0s17` の固定 `192.168.0.14/24` と MAC `00:0c:29:3a:81:3b`、鍵SSHと sudo、chrony の選択ソース・stratum 3・Leap Normal を照合した。root は LVM/ext4、空き約84 GiB。Podman 4.9.3 配下の既設コンテナは `nlp-demo` のみ。`pgdata` は root:root 0700・空、TCP 5432 の待受は0件、failed unit は0件だった。

公開タグ `docker.io/pgvector/pgvector:0.8.7-pg16-bookworm` のレジストリ応答をハッシュ照合し、linux/amd64 子 manifest を特定した。Quadlet の `Image=` はこのタグと子 digest の組、`Pull=never`。実際に取得したイメージの postgres は UID/GID 999:999、バイナリは `16.16 (Debian 16.16-1.pgdg12+1)`、拡張制御ファイルの既定版は `0.8.7`。[pgvector リリース v0.8.7](https://github.com/pgvector/pgvector/tree/v0.8.7)

| レジストリまたは実機の識別対象 | SHA-256 |
|---|---|
| タグの index | `484e838076e04939d27d3e176e91c86eea96236126023be8d3059761122e579f` |
| linux/amd64 manifest | `018b4a92e634c3a5715f613dd43497e3d8028ae051be7ba6fd127bcffb0e7957` |
| 稼働コンテナの image ID | `b0108689bf51bd54d3129130967d4adf7ba58b395a9ff6653aa598b5fe7d7ba3` |

`/srv/nlp/pgdata` を 999:999・0700 で `/var/lib/postgresql/data` に永続マウントした。シークレットは root:root 0700 の `/srv/nlp/db-secrets/` 配下にアカウント別の0600で保管し、別値であることと両方の SCRAM verifier の存在を確認した。開発PCにはアプリ用秘密だけを検証済み SSH 経路からメモリに渡した。Git対象のうち以下の4ファイルは最終稼働時に配置先とバイト一致した。

| `/srv/nlp/` 以下の配置 | SHA-256 |
|---|---|
| `quadlet/nlp-postgres.container` | `d17873b7493d019b0b1ce0d4f65392dac69876d4eef6cabaa7781b2fb1fe6975` |
| `db/pg_hba.conf` | `1bdb2a03ea220d99967c9ca4094a6653684332094506ee7a3d6cec1810964755` |
| `db/migrations/001_initial.sql` | `3d91d87ae46ffbcdc3bb63f265683a38e270dfb56677061ee541170a347c2642` |
| `db/migrations/catalog_fingerprint.sql` | `53265955e2107e6155dda34d5fc1babb88f72fdaeb7a2722482763a1a3d76c84` |

## 受入結果

| ID | 判定 | 実測した根拠 |
|---|---|---|
| B1 | PASS | 上記の2A基準、VM識別、時刻と初期状態を実機で照合。既設demoのQuadletはGit版と同じSHA-256で、最終状態でもactive |
| B2 | PASS | 稼働イメージIDが上表と一致。両DBで `server_version_num=160016`、`vector=0.8.7`、UTF8、UTC、512MB、最大50接続。生成サービスが multi-user.target の依存にあり、VM起動後も同値 |
| B3 | PASS | 通常・検証とも8表、下表の制約、B-tree 19本、独自trigger 3件を照合。アプリは全表の所有者・ロールメンバーシップとも0件。両DBでmigration再適用前後の全列・件数が一致。検証DBで同じトランザクションに余分な索引を加えると照合が失敗し、切断後にその索引が残らなかった |
| B4 | PASS | 公開表記・媒体・タイトル・馬・レース不明の本文版と全文unitを先行コミット。次の分類トランザクション内で仮の関連付けを作り、不正phaseで失敗させると関連0件、元の本文とunit IDは一致。noneの再登録は同じIDでunit 0件、noneへのunit作成は拒否 |
| B5 | PASS | 完全一致の再登録で追加0件、初回時刻とIDが一致。本文変更、同一本文のsnippet、別のクエリ付きURL、excerpt、noneを区別し計6版。補助平面の文字と結合文字を含む部分範囲が一致。破損hash・必須hash欠落・範囲超過を拒否 |
| B6 | PASS | 架空の同名別馬2頭、同名レース2件、関連7件・phase 4種。正しい馬×レース2組、逆の2組は0件。指定レースは関連4件→2 unit→1親記事。日付不明preは1 unit、他3種の混入0件。馬のみ・レースのみ・未同定表記を保持し、解決済み旧ラベルの残存0件 |
| B7 | PASS | Embedding 0件で原文・関連追加・抽出が成立。未索引unitも未処理候補。設定の順序を変えて同じIDを再利用、誤った設定hashを拒否。同じunitの3次元2 chunkと4次元1 chunkを保存・設定別に抽出。次元・範囲・重複・NaN/Infを拒否。2 chunk目の失敗で部分保存0件、完了済み再実行の追加0件 |
| B8 | PASS | 実接続元 `192.168.0.3`、`current_user=nlp_app`、`ssl=false`。検証DBの書込・抽出も同じLAN経路。誤パスワードは認証失敗、LANからのpostgresと管理DBへのアクセスはHBA拒否。DDL・TEMP・拡張・ロール・保護列UPDATE・DELETE・TRUNCATEの禁止操作10件はすべて `42501` |
| B9 | PASS | サービス通常restart 1回、VM15通常reboot 1回。下記の全列照合・設定・LAN認証・選択NTPソース・failed unit 0件を確認 |
| B10 | PASS | READMEの6ブロックの登録・訂正・抽出SQLを実行。12:03:44 に検証用HBAの除去と拒否、検証DBの名前・所有者・接続数0を確認して当該DBだけを削除。通常DBの各表0件とLAN接続を再確認 |

## スキーマとアクセス制御

以下は通常DBの `pg_catalog` から得た数。検証行数は削除前の値。全FKの削除規則は NO ACTION。照合対象の列・型・既定値・列権限・制約・関数・索引などの定義は migration と同じ SHA-256 `2a303dd483dd85e517a71b60870e7d06b1151da55f39b44b629aafb38a863b3e` だった。

| 表 | PK | FK | UNIQUE制約 | CHECK | 検証行数 | 通常DB最終行数 |
|---|---|---:|---:|---:|---:|---:|
| collection_runs | run_id | 0 | 0 | 1 | 1 | 0 |
| articles | article_id | 1 | 1 | 4 | 6 | 0 |
| horses | horse_id | 0 | 0 | 0 | 2 | 0 |
| races | race_id | 0 | 0 | 1 | 2 | 0 |
| text_units | unit_id | 1 | 1 | 2 | 7 | 0 |
| unit_targets | target_id | 3 | 1 | 3 | 7 | 0 |
| embedding_configs | embedding_config_id | 0 | 1 | 2 | 2 | 0 |
| embeddings | unit_id, embedding_config_id, chunk_index | 2 | 0 | 3 | 3 | 0 |

索引19本はPK 8本、一意制約4本、`races(domain_id,race_key)` の部分一意1本、および以下の検索用6本。記事の版キーと対象の関連キーはともに NULLS NOT DISTINCT。全文unit生成・unit範囲検査・chunk範囲と次元検査の3 trigger が有効だった。

| 表 | 検索用B-treeの列順 |
|---|---|
| horses | `(normalized_name)` |
| races | `(race_name,race_date)` |
| unit_targets | `(horse_id,phase,unit_id)`、`(race_id,phase,unit_id)`、`(race_id,horse_id,phase,unit_id)` |
| embeddings | `(embedding_config_id,unit_id)` |

`postgres` がDB・8表を所有する。`nlp_app` はLOGIN、superuser・createdb・createrole・replication・bypassrlsはいずれもfalse。CONNECTとスキーマUSAGE、8表のSELECT/INSERT、許可列のUPDATE、`unit_targets` のDELETEを持つ。DBのCREATE/TEMPとスキーマのCREATEはfalse。

初回LAN試験ではDNAT後の通信が VM15 の FORWARD 既定DROPに到達した。UFWは変更せず、Quadletに当該DB専用の転送許可を追加して再試験した。最終状態で `ss` と `podman port` の公開はIPv4 `192.168.0.14:5432` だけ。raw PREROUTING では同ポートのLAN外送信元をDROP、FORWARDではLAN送信元・入力 `enp0s17`・出力 `podman0`・元宛先 `.14:5432` のDNAT通信だけを許可した。UFWは稼働中で incoming/routed deny、LANからTCP 22/5432のみ許可。最終HBAは管理ソケットの `postgres/peer` と LAN の `keiba_nlp/nlp_app/scram-sha-256` の2行、解析エラー0件。LAN外の別ホストからの接続試験は行っていない。待受・転送・認証の実効設定で公開境界を照合した。

## 再起動とデータ照合

`tests/snapshot.sql` で日時をUTC、byteaをhexにそろえ、各表の全行全列を一定順序で SHA-256 化した。検証DBは30行、全体 `388030924cad0c651b6f821206baf311686ddd2d0eb072f3637651d1f3dbf9b5`。合成ベクトルを含む `embeddings` 単体は `7219ea2fad6348110664128d1240c598474ddd8af4d4b185dd0b305a079752a2`。通常DBは0行、全体 `9f8704b8d65fa84766d90672dfc8e106b167935f1d61dbda06384a4dcbf00c2b`。

| 観測点（JST） | 結果 |
|---|---|
| 11:58:25 基準、11:58:28 migration再適用後 | 両DBの各表件数・個別hash・全体hash・接続設定が一致 |
| 11:58:43 サービスrestart後 | 同じboot ID、全項目一致。restart要求からゲスト状態までの照合は2.7秒 |
| 11:59:03 VM15通常reboot要求 | 旧 `c10b57c4-11e9-4703-a55b-323e9631bdc2` → 新 `df52128e-f140-42f3-a716-d3b6f7918707`。新bootの鍵SSHを22.4秒、開発PCのDB認証を22.6秒で観測 |
| 11:59:34 ゲスト確認 | 選択NTPソース・Leap Normal を29.6秒、両DB全項目・サービス状態の照合を30.7秒で観測。postgres/demoは手動startなしでactive、failed unit 0件 |
| 12:03–12:05 最終確認 | 検証DB削除後に残ったDBは `keiba_nlp, postgres, template0, template1`。DBコンテナactive、再開始回数0、空き約83 GiB。既設の `articles`・`dumps` はroot:root 0750、`quadlet` はroot:root 0755 |

## 引き渡し範囲

構築・再開・接続方法とSQL例は [DBのREADME](../../../infra/nlp-vm/db/README.md)、機械試験は [tests](../../../infra/nlp-vm/db/tests) にある。構築・試験資材9ファイルと本レポートがGit対象。元の作業ツリーの未追跡5ファイルは段階2Aの保全コピーとバイト一致した。VM上のサービスjournalと現在のコンテナログを実値を表示せず検査し、2つの秘密の平文一致は0件だった。

既存PoC JSONLは読み込み・移行・編集していない。実記事の収集・実Embeddingの生成、v3・ESXiホスト・他VM・外部検索サービスの変更は実施していない。バックアップおよびdump/restoreの受入は指示書どおり段階4前に残る。
