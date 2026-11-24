# VM15 の NLP 専用データベース

通常DBは `keiba_nlp`。開発PCから `192.168.0.14:5432` に `nlp_app` と SCRAM-SHA-256 で接続する。DBの表示時刻は UTC。TLSなしの接続先は承認済み LAN `192.168.0.0/24` に限定する。

## 配置と接続

| VM15 上の配置 | 用途 |
|---|---|
| `/srv/nlp/pgdata` | UID/GID 999:999・0700 の永続データ。コンテナ内は `/var/lib/postgresql/data` |
| `/srv/nlp/db/` | root 所有の HBA と migration。コンテナには `/etc/nlp-db` として読み取り専用マウント |
| `/srv/nlp/db-secrets/{postgres,nlp_app}` | 別々に生成した秘密。親は root:root 0700、各ファイルは root:root 0600 |
| `/srv/nlp/quadlet/nlp-postgres.container` | `/etc/containers/systemd/` の同名リンクを経由して rootful Quadlet が生成 |
| `/run/systemd/generator/nlp-postgres.service` | `multi-user.target` が起動する生成サービス |

開発PCの例は `psql -X -W 'postgresql://nlp_app@192.168.0.14:5432/keiba_nlp?sslmode=disable'`。アプリ用の秘密だけを、VM15の既知ホスト鍵を照合した SSH 管理経路で、受領者限定の資格情報ストアまたはクライアントのメモリに直接渡す。パスワードは対話プロンプトまたはライブラリの接続引数で供給する。シェルの引数・履歴・標準出力・チャットに展開しない。管理接続は VM15 上で `sudo podman exec -it -u postgres nlp-postgres psql -X -d keiba_nlp`。Unix ソケットの peer 認証を使う。

## 初回構築

以下のシェル例は VM15 の root。`src` は配置用に渡した `infra/nlp-vm` ディレクトリを指す。最初に SSH 鍵・ゲスト時刻同期・`enp0s17` の固定IP・空き容量・既設 Podman/UFW・5432の空き・`pgdata` が空であることを照合する。既存DBの再開は次節を使う。

1. 公開レジストリの `docker.io/pgvector/pgvector:0.8.7-pg16-bookworm` の index は `sha256:484e838076e04939d27d3e176e91c86eea96236126023be8d3059761122e579f`。linux/amd64 子 manifest と Quadlet の固定参照を一致させる。VM15 で実行イメージの PostgreSQL、vector 制御ファイル、postgres UID/GID を確認する。

```sh
set -eu
ref=$(sed -n 's/^Image=//p' "$src/quadlet/nlp-postgres.container")
podman pull "$ref"
podman image inspect --format '{{.Architecture}} {{.Digest}} {{.Id}}' "$ref"
podman run --rm --pull=never --network=none --entrypoint sh "$ref" \
  -ec 'id postgres; postgres -V; grep default_version /usr/share/postgresql/16/extension/vector.control'
```

2. 空の初回環境でのみ秘密と配置先を準備する。確認済みの postgres UID/GID を `pgdata` に設定する。既存ファイルに対する追記や再生成は行わない。

```sh
set -eu
test -d /srv/nlp/pgdata && test -z "$(ls -A /srv/nlp/pgdata)"
test -z "$(ss -Hln sport = :5432)"
for f in /srv/nlp/db /srv/nlp/db-secrets /srv/nlp/quadlet/nlp-postgres.container \
         /etc/containers/systemd/nlp-postgres.container; do test ! -e "$f" && test ! -L "$f"; done
mkdir -m 0700 /srv/nlp/db-secrets
(umask 077; set -C
 for account in postgres nlp_app; do openssl rand -hex 48 > "/srv/nlp/db-secrets/$account"; done)
chown 999:999 /srv/nlp/pgdata
chmod 0700 /srv/nlp/pgdata
install -d -m 0755 /srv/nlp/db/migrations
install -m 0644 "$src"/db/migrations/*.sql /srv/nlp/db/migrations/
install -m 0644 "$src/db/pg_hba.conf" /srv/nlp/db/
install -m 0644 "$src/quadlet/nlp-postgres.container" /srv/nlp/quadlet/
ln -s /srv/nlp/quadlet/nlp-postgres.container /etc/containers/systemd/nlp-postgres.container
systemctl daemon-reload
systemctl start nlp-postgres.service
podman exec -u postgres nlp-postgres pg_isready -d postgres
```

3. 初期化終了後、Unix ソケットで管理ロール・DB名を照合してから、アプリロール・通常DBを一度だけ作成する。`\password` の2入力は標準入力へ直接渡す。`dbsql` は以下の例で共通の管理用シェル関数。

```sh
dbsql() { podman exec -i -u postgres nlp-postgres psql -X --no-password -v ON_ERROR_STOP=1 "$@"; }
dbsql -d postgres -c "SELECT rolname FROM pg_roles WHERE rolname='nlp_app'" \
                  -c "SELECT datname FROM pg_database WHERE datname='keiba_nlp'"
dbsql -d postgres -c 'CREATE ROLE nlp_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
{ cat /srv/nlp/db-secrets/nlp_app; cat /srv/nlp/db-secrets/nlp_app; } |
  dbsql -d postgres -c '\password nlp_app'
dbsql -d postgres -c "CREATE DATABASE keiba_nlp OWNER postgres TEMPLATE template0 ENCODING 'UTF8'"
dbsql -d keiba_nlp -f /etc/nlp-db/migrations/001_initial.sql
```

## 起動・停止・再開

`systemctl stop nlp-postgres.service` で通常停止、`systemctl start nlp-postgres.service` で再開する。`systemctl restart nlp-postgres.service` は同じ永続領域を使う。再開時は固定イメージ、`pgdata/PG_VERSION`、マウント、所有者、DB名、ロールを照合する。スキーマの確認には同じ `001_initial.sql` を再適用する。新規時は1トランザクションで構築し、適用済みなら定義・拡張・権限の SHA-256 を固定値と照合する。差異はエラーで停止する。`pgdata` の初期化、秘密の生成、既存DBの削除は再開手順に含めない。

`systemctl list-dependencies multi-user.target`、`podman port nlp-postgres`、`ss -lntp 'sport = :5432'` で自動起動・公開先を確認する。UFW は incoming/routed を deny、LAN から TCP 22/5432 を許可する。VM15 の Netavark は宛先 NAT を使うため、Quadlet は起動前に LAN 外からの当該ポートを raw PREROUTING で破棄し、LAN→`enp0s17`→`podman0` で元宛先が `.14:5432` の DNAT 通信だけ FORWARD を許可する。重複追加を避け、停止中もこのポートの規則を保持する。`iptables -t raw -S PREROUTING`、`iptables -S FORWARD`、`ufw status verbose` および管理接続の `SELECT * FROM pg_hba_file_rules` で確認できる。

## 原文の保存と索引の訂正

取得版と全文unitを先にコミットし、分類は別トランザクションで追加する。以下の `$1` 等はドライバのバインド引数。`none` は `$2=NULL` とする。結果が0行ならハッシュ一致・原値不一致として停止する。初回取得時刻は再登録でも保存する。

```sql
WITH v(url,body,kind,media,title,published) AS (
    VALUES ($1::text,$2::text,$3::text,$4::text,$5::text,$6::text)
)
INSERT INTO articles AS a (source_url,url_sha256,body,body_sha256,body_kind,media,title,published_text)
SELECT url,sha256(convert_to(url,'UTF8')),body,sha256(convert_to(body,'UTF8')),kind,media,title,published FROM v
ON CONFLICT (url_sha256,body_kind,body_sha256) DO UPDATE
SET media=coalesce(a.media,EXCLUDED.media), title=coalesce(a.title,EXCLUDED.title),
    published_text=coalesce(a.published_text,EXCLUDED.published_text)
WHERE a.source_url=EXCLUDED.source_url AND a.body IS NOT DISTINCT FROM EXCLUDED.body
RETURNING article_id,collected_at;
```

`text_units` は Unicode コードポイントの0起点半開区間。部分範囲は `INSERT ... ON CONFLICT (article_id,start_char,end_char) DO NOTHING` の次の文で同じ3列から unit_id を引く。対象ごとに同じ関連行に馬・レース・phase を格納する。元の表記を解決した例は以下。旧行と解決先の対象を確認して同じトランザクションで処理する。

```sql
BEGIN;
INSERT INTO unit_targets(unit_id,horse_id,race_id,phase) VALUES (:'unit_id',:'horse_id',:'race_id',:'phase')
ON CONFLICT (unit_id,horse_id,race_id,horse_label,race_label) DO UPDATE SET phase=EXCLUDED.phase;
DELETE FROM unit_targets WHERE target_id=:'old_target_id' AND unit_id=:'unit_id'
  AND horse_id IS NULL AND horse_label=:'old_label' AND race_id=:'race_id';
COMMIT;
```

## SQL での抽出

以下は psql の変数を使う。`race_id`・`horse_id` は UUID、片方だけで抽出するときは他方を空文字にする。`phase` は任意で、指定しないときは空文字。例として `\set horse_id ''` と `\set phase pre` を使うと、指定レースの事前資料を取れる。既知キーからレースを引くには `SELECT race_id FROM races WHERE domain_id=:'domain' AND race_key=:'key'`。単独の資料・未分類の全文も `articles` と `text_units` から直接参照できる。

```sql
-- 馬、レース、またはその組。対応する1行に条件を掛け、文章単位で重複を除く。
SELECT t.unit_id,a.article_id,a.source_url,a.published_text,
       substring(a.body FROM t.start_char+1 FOR t.end_char-t.start_char) AS passage
FROM text_units t JOIN articles a USING(article_id)
WHERE EXISTS (
    SELECT FROM unit_targets x WHERE x.unit_id=t.unit_id
      AND (nullif(:'horse_id','') IS NULL OR x.horse_id=nullif(:'horse_id','')::uuid)
      AND (nullif(:'race_id','') IS NULL OR x.race_id=nullif(:'race_id','')::uuid)
      AND (nullif(:'phase','') IS NULL OR x.phase=:'phase')
);
```

親記事単位の例は次の通り。事前予測用の明細は対象レースと `pre` を指定する。公開表記の有無を条件にしない。`phase` は文脈から得た分類であり、当時の公開時点の確認は別の研究課題になる。

```sql
SELECT a.article_id,a.source_url,a.title,a.published_text,a.body
FROM articles a WHERE EXISTS (
    SELECT FROM text_units t JOIN unit_targets x USING(unit_id)
    WHERE t.article_id=a.article_id AND x.race_id=:'race_id'::uuid AND x.phase='pre'
);
```

生成設定の登録側は `model_name, model_revision, dimensions, settings` 全体を `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(',',':'), allow_nan=False).encode('utf-8')` として SHA-256 を照合する。`config_sha256` の競合時は元の全条件も照合して既存IDを使う。変更した生成条件には新しいIDを割り当てる。登録・再利用の実行例は `tests/verify.py` の `register_config` にある。

```sql
-- 指定configで未生成のunit。targetの有無を問わない。
SELECT t.unit_id,substring(a.body FROM t.start_char+1 FOR t.end_char-t.start_char) AS passage
FROM text_units t JOIN articles a USING(article_id)
JOIN embedding_configs c ON c.embedding_config_id=:'config_id'::uuid
WHERE NOT EXISTS (SELECT FROM embeddings e WHERE e.unit_id=t.unit_id AND e.embedding_config_id=c.embedding_config_id);
```

生成時は同一unit・configの全chunkを1トランザクションで保存する。並行実行時はその組を直列化して既存行を再確認し、完了済みならスキップする。抽出例は1行がレース・馬・unit・config・chunk。`e.chunk_index IS NULL` の行が未生成で、生成済みだけを要求する場合は `LEFT JOIN embeddings` を `JOIN embeddings` にする。

```sql
WITH targets AS (
    SELECT DISTINCT race_id,horse_id,unit_id FROM unit_targets
    WHERE race_id=:'race_id'::uuid AND phase='pre'
)
SELECT x.race_id,x.horse_id,t.unit_id,a.article_id,c.embedding_config_id,c.model_name,c.model_revision,
       e.chunk_index,e.embedding,
       substring(a.body FROM t.start_char+1 FOR t.end_char-t.start_char) AS passage,
       substring(a.body FROM t.start_char+e.start_char+1 FOR e.end_char-e.start_char) AS chunk_text
FROM targets x JOIN text_units t USING(unit_id) JOIN articles a USING(article_id)
JOIN embedding_configs c ON c.embedding_config_id=:'config_id'::uuid
LEFT JOIN embeddings e ON e.unit_id=t.unit_id AND e.embedding_config_id=c.embedding_config_id
ORDER BY x.race_id,x.horse_id,t.unit_id,e.chunk_index;
```

## 合成データによる受入の再現

1. 管理ソケットで既存DB名を照合し、未使用の `keiba_nlp_stage2b_test` を `postgres` 所有・UTF8・template0 で作る。通常DBと同じ `001_initial.sql` をこのDBにも適用する。検証中だけ、HBA に `hostnossl keiba_nlp_stage2b_test nlp_app 192.168.0.0/24 scram-sha-256` を追記し、管理接続で `SELECT pg_reload_conf()`。有効なルールと `error IS NULL` を照合する。
2. 開発PC上の Python 3 と psycopg 3 (`python -m pip install 'psycopg[binary]>=3.2,<4'`) で `python tests/verify.py`。テストは検証DB名・ロール・8表が空であることを確認する。架空資料の保存・分類失敗のロールバック・抽出・合成設定の再利用・数値ベクトルの制約・権限を LAN 接続で試す。
3. 両DBで `SET TIME ZONE 'UTC'` と `SET bytea_output='hex'` の上で `tests/snapshot.sql` を実行し、各表の件数・全列の SHA-256 と全体値を記録する。両DBの migration 再適用後、サービス通常再起動後、承認済みの VM15 通常再起動後に同じ値を照合する。後者は boot ID、自動起動、LAN 認証、`chronyc tracking` と選択ソース、failed unit、pgvector とDB設定も確認する。
4. 全検証後、Git版の `pg_hba.conf` を配置し直し reload する。検証用LAN接続を閉じ、`postgres` DBに管理接続して `SELECT datname FROM pg_database WHERE datname='keiba_nlp_stage2b_test'` と接続数を照合し、`DROP DATABASE keiba_nlp_stage2b_test` を単独で実行する。通常DBへの LAN 接続・8表各0件・サービス稼働を再確認する。

PoCの移行、実記事の収集、モデルを使うEmbedding生成は後続工程。バックアップの運用と dump/restore 試験は段階4前の別作業とする。
