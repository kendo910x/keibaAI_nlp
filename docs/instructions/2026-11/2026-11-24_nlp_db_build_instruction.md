# 段階2B：NLP専用DB（PostgreSQL 16 + pgvector）構築 指示書

改訂日: 2026-11-24（JST）
対象: keibaAI_nlp / VM15 keiba-nlp（192.168.0.14）
位置付け: 段階2A受入後のDB構築。2026-11-22のDB構築・PoC移行指示書を全面的に置き換える。

## 1. 目的と今回の完了状態

自然言語の研究資料を大量に蓄積し、後からレース別・馬別・レース×馬別・レース前後別に取り出せる永続DBを構築する。本文のEmbedding実体を同じDBに保存でき、記事収集とEmbeddingの生成を独立して進められることを確認する。

完了状態は、NLP VM上のPostgreSQL 16 + pgvector、下記8テーブル、基本的なSQL抽出、再起動後の永続性、開発PCからの認証済みLAN接続が成立し、再現可能な構築資材と実施レポートがGitにあること。**実データ収集はまだ開始しない。既存PoC 24件は移行しない。** Local LLMやEmbeddingモデルの再評価も行わない。テストには架空の短文・架空のID・合成ベクトルのみを用いる。

### 1.1 今回の確定方針（旧仕様より優先）

- 研究データの中核は「記事本文・対象馬・対象レース・レース前/後」の4情報。出典・重複防止・Embedding・進捗管理に必要な管理項目だけ追加する。
- 収集エージェントは将来、LLMによる自律探索・記事取得・文脈理解・馬/レース同定・前後分類を**一体の活動**として行う。索引付け専用の別LLMバッチを通常フローにしない。
- LLMの最良判断をそのまま索引として保存する。不明・誤分類の可能性を許容し、情報量を優先する。日時、同定根拠、確信度、第三者による確認等を登録条件にしない。本文の保存は索引付け成功を条件にしない。
- 前後分類は、記事の文脈に基づくLLMの判断を保存する。公開時刻とレース日程の機械比較を主判定にしない。公開日時が不明でもpreは成立する。レース後の記事中にレース前の発言が引用されているだけなら当該レースの事前資料とはみなさない。
- 保存時に「好調/不調」、期待度、話者、発言種別、騎手・調教師・調教時計などの記事固有の属性を固定列化しない。記事内容の数値表現は原文のEmbeddingに任せる。
- Embeddingは収集と独立した後続バッチ。過去記事を先に蓄積し、後日まとめて生成できる。モデル未選定・未生成・生成失敗でも記事の収集・索引・原文の取得を妨げない。
- 通常の抽出と学習用一括出力は保存済みのデータとSQLで完結し、生成LLM・Embeddingモデルの呼出しを必要としない。要約や再解釈は別用途。
- データベースとしての整合性（PK/FK、範囲、本文とhash、重複、ベクトル次元）だけを強制する。自然言語の意味の正誤はDBの制約で保証しない。
- 旧21テーブル案、旧PoC移行指示書、古い配置・引き継ぎ文書にある馬名PK・証拠テーブル・移行必須・pgvector禁止などの記述は採用しない。本指示書がユーザー合意後の段階2B仕様である。共通規約の権利・アクセス制約・システム境界は維持する。

## 2. 開始前確認と作業境界

読むもの: AGENTS.md、docs/design/2026-11-22_nlp_infrastructure_placement.md、docs/handoffs/2026-11/2026-11-22_data_accumulation_handover.md、docs/reports/2026-11/2026-11-22_nlp_vm_recovery_report.md、infra/nlp-vm/README.md。古い文書は上記1.1と衝突しない範囲で参照する。

段階2Aの受入レポートは main の 814d5144e495c72e6e1cc5e01498861338a4b064 に含まれる。VM15はUbuntu Server 24.04.5 LTS、本体100 GiB、2 vCPU/8 GiB、固定IPv4 .14、rootful Podman + Quadlet、SSH鍵接続、ゲストchrony同期、UFW設定済み。レポートではpgdata空・5432待受なしであり、これが正常な構築前状態だった。今回も現物を確認し、既設DB・データを推測で削除しない。

1. git fetchし最新origin/main・AGENTS.md・本指示書を含む作業ツリーで着手。元の開発フォルダには以前の未追跡5ファイルが残っていたため、衝突する場合は保全したまま独立worktreeを作る。強制clean/reset、未追跡ファイルの上書き禁止。PoC JSONL等は読み込み・移行・編集しない。
2. 既知のホスト鍵で nlp@192.168.0.14 へSSHし、sudo、固定IP、rootful Podman/Quadlet、UFW、/srv/nlp の所有・空き容量・既設コンテナ、pgdata、5432を確認。時刻記録を始める前にゲストchronyの同期を確認。VM15以外には変更しない。
3. /srv/nlp/pgdata が空であることを確認して初回構築。既に本タスク自身の適用済みDBがある再開時は、構成・スキーマ・データの照合後に再利用する。不明な既設DB、ポート競合、データがある場合は停止報告。
4. ESXiホスト全体の約37時間の時計ずれは別件。VM15のゲスト時刻同期が正常なら本タスクの障害にしない。ホスト時刻やVMXを変更しない。

## 3. 配備仕様

| 項目 | 固定仕様 |
|---|---|
| DB | PostgreSQL 16（major固定）、pgvector 0.8.7 |
| イメージ | pgvectorプロジェクトの公開イメージ docker.io/pgvector/pgvector:0.8.7-pg16-bookworm。実際のlinux/amd64 manifestとdigestを確認してtag+digest固定。別版への無断fallback禁止 |
| コンテナ | rootful Podman、Quadlet nlp-postgres.container / nlp-postgres.service。WantedBy=multi-user.targetで自動起動 |
| 永続化 | ホスト /srv/nlp/pgdata → コンテナ /var/lib/postgresql/data。実イメージのUID/GIDを確認して所有・0700を設定。既存の他ディレクトリを変更しない |
| Quadlet | Git: infra/nlp-vm/quadlet/nlp-postgres.container、配置: /srv/nlp/quadlet/、/etc/containers/systemd/から参照 |
| 設定 | shared_buffers=512MB、max_connections=50、UTF8、DB時刻表示UTC |
| DB名 | keiba_nlp |
| ロール | bootstrap管理ロール postgres、アプリ用 nlp_app（LOGIN、NOSUPERUSER、NOCREATEDB、NOCREATEROLE、NOREPLICATION）。アプリをDB/DDL所有者にしない |
| 資格情報 | /srv/nlp/.env 等の秘密ファイルをroot:root 0600、Git管理外。管理用とアプリ用は別の強い生成パスワード。実値を端末出力、コマンドライン、ログ、レポート、Gitに残さない |
| 接続 | 既承認のLANのみ、192.168.0.14:5432/TCPに公開。TLSなし（このLAN利用に限る）。pg_hbaはLANの対象DB・アプリロールにSCRAM-SHA-256、管理用はコンテナ内管理経路に限定。その他の接続許可を広げない |
| FW | 現行UFWの22/5432 LAN許可・incoming denyを維持。Podmanのポート公開後に実効待受、アクセス制御、pg_hbaを確認。LAN外公開・他サービスのFW変更禁止 |

イメージの取得元・digest・PostgreSQLの実minor・拡張版を記録。拡張は管理ロールで CREATE EXTENSION vector; を適用する。nlp_appはアプリ8テーブルの必要なSELECT/INSERT/UPDATEとunit_targetsに限ったDELETE（誤った/不要になった関連付けの訂正用）を許可し、DDL・拡張作成・ロール管理は管理側だけにする。DROP等の破壊操作を通常の収集ツールに許可しない。秘密の安全な配布方法はREADMEに記載（実値を記載しない）。接続文字列のサンプルにはプレースホルダを使う。

参照: https://github.com/pgvector/pgvector/tree/v0.8.7 、https://www.postgresql.org/docs/16/ddl-constraints.html

## 4. 確定スキーマ v1（8テーブル）

以下が全アプリテーブル。表記: PK=主キー、FK=外部キー、NN=NOT NULL。UUIDのPKには gen_random_uuid() を既定値とする。明示しない列はNULL可。全ての取得・生成・実行日時は timestamptz、システムが記録。記事の公称公開日時だけは元の表記をtextで保持し、時刻不明・日付不明を補完しない。付加情報を得るためのWeb追加調査は要求しない。

連番SQLを infra/nlp-vm/db/migrations/ に保存。初期SQLを一つのトランザクションで適用し、適用済みの場合はDDL・拡張版を照合する。再実行でテーブル・既存行を消さない。拡張の内部オブジェクト、機械的検査用関数・trigger、読み取りviewはアプリテーブル数に数えないが、不要な専用表・フレームワーク・監査基盤を追加しない。

### 4.1 collection_runs — 収集タスク

| 列 | 型・制約 | 意味 |
|---|---|---|
| run_id | uuid PK | 一回の収集ジョブ |
| task | jsonb NN | 対象・実行条件等。LLMモデル・指示版が分かる場合もここに記録 |
| status | text NN default 'queued' | queued / running / paused / completed / failed |
| progress | jsonb NN default '{}' | 後続エージェントの再開情報 |
| started_at | timestamptz | 開始時刻 |
| updated_at | timestamptz NN default now() | 更新時刻 |
| finished_at | timestamptz | 終了時刻 |
| last_error | text | 失敗内容、秘密を含めない |

実際の収集スケジューリング、タスク契約、検索ログ、checkpoint更新の実装は段階3。検索ログ専用テーブルは作らない。

### 4.2 articles — 原資料（取得内容の版を含む）

| 列 | 型・制約 | 意味 |
|---|---|---|
| article_id | uuid PK | 一つの取得内容の版 |
| source_url | text NN | 実際に取得/発見したURL（最終URLが確認できればそれを採用） |
| url_sha256 | bytea NN | source_urlのUTF-8 SHA-256（32バイト） |
| media | text | 媒体名 |
| title | text | 記事タイトル |
| published_text | text | サイト上の公開日時の元表記。日付・時刻・精度を強制しない |
| body | text | 保存可能な原文。LLM要約・推測は入れない |
| body_kind | text NN | full / excerpt / snippet / none |
| body_sha256 | bytea | bodyのUTF-8 SHA-256（32バイト） |
| collected_at | timestamptz NN default now() | この内容を初めて記録した時刻 |
| run_id | uuid FK → collection_runs.run_id | 取得元ジョブ。手動登録時等はNULL可 |

制約: source_urlは空にしない。url_sha256は実値と一致。body_kind=noneならbody・body_sha256はNULL。それ以外はbody非空・hash実値一致を要求する（空文字や取得失敗を原文にしない）。CHECKはNULLの三値論理で不正な組合せを通さないこと。ハッシュにはPostgreSQL 16のsha256(convert_to(...,'UTF8'))を用いるか、同値の実装をDB側で検査する。

UNIQUE NULLS NOT DISTINCT (url_sha256, body_kind, body_sha256)。同じURL・同じ取得種別・同じ本文を再登録しても同一article_idを再利用し、collected_atは変えない。媒体・タイトル・公開表記の欠損補完は可。body、body_kind、URL、hashは既存版を書き換えず、本文更新やsnippet→fullは新規article_idとする。異なるURLは同一本文でも出典を失わないよう別行。URLは過剰な正規化・クエリ削除をしない。ハッシュ一致時に原値も照合する。毎回の取得イベント専用表は不要。

公開日不明・馬不明・レース不明・Embedding未生成でも登録可。閲覧・保存できない場合は許される範囲のsnippetまたはnone。アクセス制限の回避・許諾を無視した本文取得/保存/加工は行わない。記事一覧・広告・関連記事の混入を避けた本文を保存するが、この抽出ツールは段階3。

### 4.3 horses — NLP内の馬識別

| 列 | 型・制約 | 意味 |
|---|---|---|
| horse_id | uuid PK | NLP内部ID |
| horse_name | text NN | 表示用馬名 |
| normalized_name | text NN | 同一馬の検索用 |
| birth_year | smallint | 生年が分かる場合のみ |

normalized_nameは馬名のUnicode NFKC後、Unicode空白を除去。長音・記号・「号」等を勝手に削除しない。名前索引は非一意。同名別馬を許容し、名前はPKにしない。通常はLLMの最良判断で既存IDを再利用し、特定できない場合はunit_targetsのhorse_id=NULLと生表記を残す。確認を繰り返す処理は要求しない。初期v3連携なし。将来のblood_reg_no等との対応表追加を妨げない内部IDとする。

### 4.4 races — NLP内の個別レース識別

| 列 | 型・制約 | 意味 |
|---|---|---|
| race_id | uuid PK | NLP内部ID |
| race_name | text | 名称（開催年などを含む識別可能な表現でも可） |
| race_date | date | 開催日が分かる場合 |
| domain_id | text | 確認できたドメイン。jra / nar_thoroughbred等、未判明はNULL |
| race_key | text | v3互換の YYYYMMDD/JJ/RR が分かる場合 |

(domain_id, race_key) は両方非NULLの場合のみ一意（部分一意索引）。race_keyは判明している場合だけ形式を検査し、コードの推測・架空の開催日/レース番号補完は禁止。レース名を一意にしない。名称・開催年しか分からない場合は識別可能な個別競走なら内部IDで保持可、個別競走を特定できないならunit_targetsのrace_id=NULLとrace_labelで保持する。初期から実v3や公式データ全体を取り込まない。海外等のdomainをDB制約で排除しない。

### 4.5 text_units — 原文範囲

| 列 | 型・制約 | 意味 |
|---|---|---|
| unit_id | uuid PK | 一つの文章単位 |
| article_id | uuid NN FK → articles.article_id | 元の取得版 |
| start_char | integer NN | 原文内開始位置 |
| end_char | integer NN | 原文内終了位置（排他的） |

UNIQUE (article_id, start_char, end_char)。位置はUnicodeコードポイントの0起点・半開区間 [start_char,end_char)。0 <= start_char < end_char <= char_length(body) をDB側で検査する（親行参照は小さなtrigger等で検査）。原文の一部を本文と別にコピーしたりLLMに書き直させたりしない。SQLで substring(body from start_char+1 for end_char-start_char) を取得できること。noneにはunitを作らない。

本文がある場合は、原資料の登録と同じトランザクションで全文範囲のunitを用意する（既存の同一版では再利用）。LLMが対象ごとの文章範囲を特定できれば別unitを作って索引を付ける。単一馬記事等は全文unitで構わない。分類に失敗しても原資料と全文unitは維持し、無関係な馬へ全文unitを自動割当しない。重複範囲は再利用。後日のEmbedding tokenizerによる長文分割はembeddings側の範囲で表現し、この表の関連付けや本文を改変しない。

### 4.6 unit_targets — LLMが付ける対象と前後分類

| 列 | 型・制約 | 意味 |
|---|---|---|
| target_id | uuid PK | 一つの関連付け |
| unit_id | uuid NN FK → text_units.unit_id | 対象文章 |
| horse_id | uuid FK → horses.horse_id | 対象馬。NULL可 |
| race_id | uuid FK → races.race_id | 対象レース。NULL可 |
| horse_label | text | IDを割り当てられない場合の馬名・表記 |
| race_label | text | IDを割り当てられない場合のレース表現 |
| phase | text NN default 'unknown' | pre / post / mixed / unknown |

UNIQUE NULLS NOT DISTINCT (unit_id, horse_id, race_id, horse_label, race_label)。対応の訂正はphase更新または関連行を訂正する通常処理でよく、LLMの解釈版・確信度・証拠履歴の恒久管理はしない。IDが付与済みなら対応するlabelはNULLとし、同じ関係を別表記で増殖させない。解決した関連行は不要な未解決重複行を残さない。ラベル/IDを全て特定できない場合は関連行なしでも本文は保存される。馬だけ、レースだけの関連も許容し、レースを必須にしない。

phaseの意味:
- pre: 対象レースの事前情報として書かれた資料とLLMが判断。
- post: 対象レースの事後情報とLLMが判断。
- mixed: 事前・事後の内容が分けられない。
- unknown: 判断不能または対象レースとの前後関係が不明。

記事収集時のLLMが対象との関係を文脈から付ける。馬とレースの別々の集合を直積して結合しない。複数馬・複数レースは関連する文章範囲ごとに必要な組だけを保存。事前予測向け抽出は対象race_idを指定しphase=preを使う。公開日時の有無は登録/抽出の必須条件にしない。phaseは当時の公開を証明する値ではなく、ノイズを含むLLM分類である。後日の研究では明らかな事後記事の混入等を確認し、歴史的資料の分類ベースの検証と厳密な時点再現を混同しない。全件の証拠収集や日程履歴の再構築は本タスク対象外。

### 4.7 embedding_configs — モデルと生成設定

| 列 | 型・制約 | 意味 |
|---|---|---|
| embedding_config_id | uuid PK | ベクトル化条件の識別 |
| model_name | text NN | モデル識別名 |
| model_revision | text NN | 固定可能な重み/モデルの版 |
| dimensions | integer NN | 1〜16000（採用vector型の上限） |
| settings | jsonb NN | tokenizer/版、入力・分割・前処理・正規化等、再現に必要な設定 |
| config_sha256 | bytea NN UNIQUE | 条件全体の正規化JSONのSHA-256（32バイト） |

config_sha256は model_name, model_revision, dimensions, settings を一つのJSONオブジェクトとし、キーをソート、UTF-8、ensure_ascii=False、separators=(',',':')、allow_nan=FalseのPython json.dumps規則で算出。登録側で実値と照合する。同じ設定は同じIDを再利用し、変更は新configとする。特定モデル、固定次元、L2正規化を全設定に強制しない。初期実装で実モデルの設定を登録/ダウンロードする必要はない。合成テスト用設定だけ使用。

### 4.8 embeddings — 数値ベクトル実体

| 列 | 型・制約 | 意味 |
|---|---|---|
| unit_id | uuid NN FK → text_units.unit_id | 元の文章 |
| embedding_config_id | uuid NN FK → embedding_configs.embedding_config_id | 生成条件 |
| chunk_index | integer NN | 同じ文章・設定内の0起点の分割順 |
| start_char | integer NN | unit内の開始位置 |
| end_char | integer NN | unit内の終了位置（排他的） |
| embedding | vector NN | pgvector可変次元、float32実体 |
| generated_at | timestamptz NN default now() | 生成日時 |

PK (unit_id, embedding_config_id, chunk_index)。chunk_index >= 0、0 <= start_char < end_char <= unitの長さ、vector_dims(embedding)=embedding_configs.dimensions をDB側で検査する。親参照は最小限のtrigger等。NaN/Infはvector型で拒絶。ノルムや内容の意味の正誤はDBで強制しない。start/endはunit内のUnicodeコードポイントの半開区間で、モデル固有の分割を保存できる。元の入力はその範囲の原文とconfigの前処理で再現する。原文ではないLLM要約や好不調ラベルのベクトルを原文ベクトルとして混在させない。

同じunit・configの全chunkは将来の生成処理が一トランザクションで登録し、失敗時は部分行を残さない。完了済みunit/configは再実行時にスキップ。モデル・前処理・分割設定を変える場合は新configを使用し、旧ベクトルを保持する。生成処理は段階5A、今回作らない。Embedding未生成はこの表に行がないだけであり、他表の状態や収集進行を拘束しない。ANN索引（HNSW/IVFFlat）を今は作らない。

### 4.9 索引と更新制約

PK・FK、一意制約以外に次のB-tree索引を作成:
- horses(normalized_name)
- races(race_name, race_date)
- unit_targets(horse_id, phase, unit_id)
- unit_targets(race_id, phase, unit_id)
- unit_targets(race_id, horse_id, phase, unit_id)
- embeddings(embedding_config_id, unit_id)

text_unitsのarticle_idは一意索引先頭列、unit_targetsのunit_idは一意索引先頭列、embeddingsのunit_idはPK先頭列を利用できる。重複索引を作らない。削除はFKで参照整合性を維持（原則RESTRICT/NO ACTION、無条件CASCADE削除をしない）。原文版の識別列、本文、unit範囲、embedding_configsの設定はアプリの通常UPDATE対象にしない（列権限または小さな検査で実現）。同定結果・馬/レースの名称や判明したキー・進捗・欠損メタの更新は可。不要な履歴表、追加のセマンティック分類、過度な入力制約を作らない。

## 5. 保存・抽出の実装契約

今回実装するのはDDLと機械的なSQL受入試験。次段階の収集・分類やEmbeddingの処理コードを先取りしない。ただしREADMEに以下のSQL取得方法と保存手順を再現可能に記載し、テストで成立させる。

1. 収集時は、原資料の保存を確定した上で、同じ自律探索の活動中にLLMがunitとtargetを追加する。後段で失敗しても既に保存した原文をrollbackしない。原文だけの登録・参照を保証する。
2. 後日のEmbedding処理は、指定configに対応するembeddings行のないunitを抽出する。未分類・馬/レース不明のunitも生成可能。原文・索引・他モデルの生成済みベクトルには影響を与えない。
3. レース別はrace_id（判明済みならdomain_id+race_keyから引ける）、馬別はhorse_id、レース×馬別は同じunit_targets行のrace_idとhorse_idを指定。phase指定は任意。親記事単位の出力ではarticle_id、文章単位ではunit_idを重複排除して取得する。複数targetによる水増しを避ける。
4. ベクトルの一括抽出はunit_targets→text_units→articles→embeddings→embedding_configsをJOINし、embedding_config_idを明示して取得する。ベクトル明細の粒度は対象レース・馬・unit・config・chunk_index。未生成を捏造/ゼロ埋めしない。必要に応じ原文明細をLEFT JOINして未生成を識別できること。馬だけに関係する過去記事の採用条件、v3への学習データ出力/集約方法は後続の研究設計で決める。
5. 「preだけ抽出」は対象レースを指定した上でphase='pre'で行う。日付不明のpreも抽出される。mixed/unknown/postはデフォルトで対象レースの事前予測明細に入れない。過去走のpostが将来の別レースの予測材料になり得るので原文を捨てない。公開日不明を理由にデータを消さない。
6. いずれのSQLもLLM API、検索MCP、Embeddingモデルを呼ばずに実行する。v3側の参照データ同期・馬IDマッピング・出走馬番対応は将来の別作業。段階2Bではv3実データへの接続を行わない。

## 6. 実装・受入手順

実行環境はVM15と開発PCの対象リポジトリに限定。独立した検証DB keiba_nlp_stage2b_test に同一migrationを適用し、合成データで試験する。通常DB keiba_nlp は8テーブル構築後も実データ0件のままにする。検証DBへの合成データのみをサービス/ゲスト再起動の永続性検査に用い、全検証終了後に名前を照合して検証DBだけ削除する。通常DBは削除しない。

| ID | 必須の受入条件 |
|---|---|
| B1 | 最新Git基準・VM15・ゲスト時刻同期・既設サービス・pgdata空/再開状態を確認。対象外サービスに変更なし |
| B2 | 固定digestでPostgreSQL 16 + pgvector 0.8.7が稼働。UTF8、512MB、50接続、自動起動設定、vector拡張を実測 |
| B3 | 通常DBに定義した8アプリテーブルだけが存在。PK/FK/CHECK/UNIQUE/索引・権限を確認。適用済み構築手順の再実行でデータ消去・重複作成なし |
| B4 | 公開日時・タイトル・馬・レース・分類が不明でも本文版を保存できる。noneやsnippetも正しく保持し、noneへのunit作成を拒否。LLM処理失敗を模した場合でも先行保存済みの本文を保持 |
| B5 | 同一URL・同一本文の再登録で新規版0件、本文更新で別版、snippet/full区別、異なるURLは出典を保持。原文Unicode範囲の抽出一致、破損hash・範囲外unitを拒否 |
| B6 | 複数馬・複数レースを含む架空記事で、指定した対応のみを抽出。馬だけ・レースだけ・未同定labelも保存。同名別馬を登録可能。phaseの4値を保持し、日時不明preが取得される。post/mixed/unknownは事前抽出に混入しない |
| B7 | Embeddingゼロ件でも原文/索引の追加・SQL抽出が成立。索引がないunitも指定configの未処理候補になる。3次元/4次元等の合成ベクトルを同一unitの別configに保存し、別モデルの混入なし・次元不一致拒否・複数chunk・原文範囲・二重登録拒否を実測 |
| B8 | 開発PCからnlp_app認証でLAN接続・必要なSQLを実行でき、誤パスワード・DDL/拡張/ロール操作が拒否される。実効待受・pg_hba・UFW・Podman公開設定を確認しLAN以外へ公開していない。秘密の露出なし |
| B9 | PostgreSQLサービスの通常restart後に合成データ・設定・vectorを照合。VM15の通常rebootを最大1回実行し、自動起動・NTP再同期・LAN接続・データ保持・failed unitを確認 |
| B10 | 検証DBだけを削除し通常DB8テーブルが空で正常稼働。DBの配置・起動/停止/再開・接続・migration・抽出SQLをREADMEに記録。対象外変更なし、Git差分を確認 |

合成テストはLLM/検索/Embedding実モデル不要。データ量・推論品質・速度ベンチマークは合格条件にしない。旧PoC24件はテストの入力にもしない。自動バックアップやdump/restoreの運用・受入試験は段階4前の別工程に延期（配置設計の既合意を維持）。今はサービス/VM再起動後の永続性を確認する。

## 7. 禁止事項・停止条件

禁止: v3本番・histdb/DuckDB・mini-v3への接続/変更・参照データ実取込、ESXiホスト全体の設定/時計修正、他VM・Talos/k8s・OpenWebUI・EVO-X2への変更、Yahoo等の実検索、Hermes構築/実行、LLM能力再検証、実記事の収集・移行、Embeddingモデルの取得/実行/比較、定期バックアップ/スケジュール構築、人物/事象/評価の専用表・証拠管理等の無断追加。Gitに秘密・実記事・DB実体・ベクトル実体・生ログを含めない。

停止: 2Aの状態と対象を照合できない、既設データの破壊や範囲外変更が必要、ゲスト時刻同期ができない、指定イメージの版・digest・拡張を確認できない、認証/公開境界が維持できない、確定8テーブルと必要な保存/抽出の両立ができない、その他の追加判断が必要。**単に記事の公開日時や分類が不明という理由は停止条件にしない。** B1〜B10の未達を隠して完了としない。

## 8. 成果物・報告・引渡し

- infra/nlp-vm/db/migrations/ のDDL（必要な検査関数・索引・ロール権限設定を含む）、infra/nlp-vm/db/README.md（接続・適用/再開・SQL例・試験手順）、infra/nlp-vm/db/tests/ の小規模な再現可能SQL試験、infra/nlp-vm/quadlet/nlp-postgres.container、必要な秘密を含まない設定テンプレート。
- docs/reports/2026-11/2026-11-24_nlp_db_build_report.md（実施日が異なる場合は実施日をファイル名に使用）。
- レポート: 基準commit、実機の開始/終了状態、配置ファイルとイメージdigest・minor・拡張版、実DDLと索引一覧、B1〜B10のPASS/FAIL/未実施と観測根拠、再起動とデータ照合、通常DB件数、権限/FW、秘密を伏せた実行経路、変更範囲・残件を記録。PoC移行なし・実収集なし・実Embedding生成なしを明示。
- 変更対象だけcommit/pushしorigin/mainへの反映を確認。既存作業やPoCを上書きしない。

次は共用検索基盤の修正（別リポジトリ）とHermes収集・分類・保存の一体実装。過去記事の継続収集を優先し、Embeddingの全件生成を収集開始の条件にしない。本指示書の完了だけでその後の実収集や外部サービス変更を包括承認したことにはならない。
