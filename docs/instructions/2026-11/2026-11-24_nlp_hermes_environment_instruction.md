# 段階3B：Hermes研究環境・基本ツール構築 指示書

作成日: 2026-11-24（JST）
対象: kendo910x/keibaAI_nlp、VM15 keiba-nlp（192.168.0.14）
validation baseline: 5566b0237235a1a32ff6a6d6f5d92a6fdc7a63f9
共用検索基準: kendo910x/OpenWebUI e33a4ae4451b6cb9aec502a8ce00d1ec84b93064

## 1. 目的・完了条件

Hermesが競馬の自然言語情報を自律的に探索・理解・蓄積し、経験から自分のSkillを改善していくための実行環境と基本的な道具を用意する。

**段階3Bは研究環境の構築であり、収集活動の設計・実施ではない。** Hermesの常用環境、既存Local LLM、共用検索MCP、合意済みDBへの基本操作、Skill/Memory/Sessionの永続化が成立することを受け入れる。実際の探索課題、探索範囲、検索戦略、初期収集指示、収集Skillの自己改善の研究は段階3C。継続収集、スケジュール、バックアップの運用整備は後続。Embedding生成・予測力評価も今回行わない。

人間が用意するのは機械的な保存・参照手段、固定の権限境界と利用契約だけ。何を検索するか、記事をどう理解するか、どの馬/レースと関係するか、どのように探索方法を改善するかは将来Hermes自身が判断する。収集専用ワークフロー、サイト一覧、巡回順、検索語テンプレート、収集件数目標、評価ラベル、分類器、LLMへの固定的な多段プロンプトを先に実装しない。

本指示書の作成・commitのみで実機構築を開始しない。実行依頼を受領してから以下の範囲で作業する。

## 2. 必読資料と開始前照合

- 本repo AGENTS.md、docs/design/2026-11-22_nlp_infrastructure_placement.md、docs/handoffs/2026-11/2026-11-22_data_accumulation_handover.md。
- 段階2Aの docs/reports/2026-11/2026-11-22_nlp_vm_recovery_report.md。
- 確定8テーブルの段階2B指示書 docs/instructions/2026-11/2026-11-24_nlp_db_build_instruction.md、実測レポート docs/reports/2026-11/2026-11-24_nlp_db_build_report.md、infra/nlp-vm/db/README.md、migrations/001_initial.sql、catalog_fingerprint.sql、pg_hba.conf、quadlet/nlp-postgres.container。
- 共用検索の[段階3A受入レポート](https://github.com/kendo910x/OpenWebUI/blob/e33a4ae4451b6cb9aec502a8ce00d1ec84b93064/docs/reports/2026-11/2026-11-24_shared_search_redeploy_report.md)、同版 infra/google-search-mcp/README.md と yahoo_search_server.py。
- Hermes公式: [コンテナ](https://hermes-agent.nousresearch.com/docs/user-guide/docker)、[カスタム推論先](https://hermes-agent.nousresearch.com/docs/integrations/providers)、[MCP設定](https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference)、[Skill管理](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/)、[設定](https://hermes-agent.nousresearch.com/docs/user-guide/configuration)、[コンテキスト圧縮](https://hermes-agent.nousresearch.com/docs/developer-guide/context-compression-and-caching)。導入する固定版の実装・help・設定schemaを確認し、Web上の最新版だけを根拠に未対応設定を入れない。

開始時にgit fetch、最新origin/mainと対象差分を確認。開発PCの旧作業ツリーに残る未追跡5ファイルとPoCを上書きしない。必要なら既存の独立worktreeを利用。VM15のSSHホスト鍵、固定IP、chrony、Podman/Quadlet、メモリ/ディスク空き、既存DB/既存demoの稼働、UFW、秘密ファイルのアクセス権を確認。通常DBは段階2B終了時8表とも0件。今回の開始時件数と既存行の有無を実測する。既存データは消去しない。

DBの最新DDL（8表、PostgreSQL 16.16＋pgvector 0.8.7）を正本とし、古い21表案・馬名PK・PoC移行・厳密な日時/同定の必須化を採用しない。AGENTS.md・旧資料中の記述は、段階2Bで確定した「不明を許容し、LLMの文脈判断を用いる」方針を優先して解釈する。実記事の保存・アクセス条件は維持する。

共用検索は新版 shared.2（digest sha256:088f5c16810f21931dcdfc7756e9d0e95716609e7b03276ccc71c27ad2cfaddf）で技術受入済み。実Yahoo検索の利用条件は未解決であり、本taskでは呼び出さない。

## 3. 配備・実行方式

| 項目 | 指定 |
|---|---|
| VM | 既存VM15 Ubuntu Server 24.04.5、2 vCPU/8 GiB/100 GiB thin |
| 実行基盤 | 既存rootful Podman + Quadlet。新規VM・k8s・Docker daemon不要 |
| Hermes | 公式 nousresearch/hermes-agent の公開安定版（実行時にリリースとlinux/amd64イメージを照合し、版/tag＋digest固定）。main開発版・可変latestへの常時追従は禁止 |
| 基本ツール | 同一コンテナ内の小さなstdio MCP（Python＋psycopg）。必要な依存だけを固定した派生イメージとして再現可能にする |
| 管理 | nlp-hermes.container / nlp-hermes.service、既存SSH経由のCLI |
| 永続領域 | /srv/nlp/hermes → /opt/data。Skill、Memory、Session、設定、ログ等は公式の永続領域を利用 |
| 常設動作 | idle状態でCLIが実行可能。公式イメージの対応する sleep infinity 起動方式を利用し、gateway、外部チャット連携、dashboard、API公開、cron/定期収集はまだ開始しない |
| 接続 | 既存LANのLocal LLM・共用MCP・DBのみを初期設定 |
| リソース | 初期上限 memory 3 GiB / CPU 1.5相当（実効Podman設定を照合）。実行前後に既存DBとVMの余力を確認 |

公式イメージのENTRYPOINT・初期化・権限分離を維持する。安定版で提供される非root runtimeを使用し、実UID/GIDを確認する。コンテナ内のツール実行をrootにしない。派生イメージは固定baseとDB用依存・機械的なstdioツールだけを追加し、Hermes本体やそのvenvを書き換えない。DB MCP用は別venv等の独立した固定依存環境とし、psycopg 3.3.9（既存検証版）とMCP SDKの互換版を実物確認して固定する。専用のHTTP DBサービス、追加プロセス監視framework、新しいGHCR発行基盤は不要。小規模なローカルbuildで足りる。依存追加を隠さず、base digest・依存lock・build手順・実イメージIDを記録する。

Quadletは既存同様 infra/nlp-vm/quadlet/ にGit管理し、/srv/nlp/quadlet/ と /etc/containers/systemd/ から参照。network-online後に起動し、自動起動を有効にするが、起動だけで推論・探索・定期タスクを走らせない。停止・再開・同一イメージでの再作成が可能なこと。gatewayが自動起動しないことを実測する。利用者はSSHで入り、非rootのHermes CLIをpodman execで実行できる。実コマンドは採用版のhelpに沿いREADMEへ記載する。

PodmanのネットワークはVM専用環境での既存LAN利用を簡単にするため、今回のCLI用コンテナはNetwork=host（公開ポートなし）とする。host networkはネットワーク隔離を提供するものではないことを明記。ホストのPodman/Dockerソケット、SSH鍵、管理者credentials、他プロジェクトのファイル・DB、ホストルートをマウントしない。privilegedは禁止。新しいlisten portを生じさせず、UFWの外部公開範囲を広げない。

## 4. 接続設定・権限

### 4.1 Local LLM（EVO-X2）

既存Halogen Flash-Next API http://192.168.0.13:8731 の現行OpenAI互換接続先を既存の実測/設定、/modelsの応答等から確認。モデルID、API base URL（通常 /v1）、必要な認証方式、実際の有効context lengthを照合してHermesのcustom providerを設定する。存在しないモデル名・context長・キーを推測しない。認証が必要なら既承認のLocal LLM接続用資格情報のみ安全に供給する。

圧縮を有効にし、要約・補助モデル等のLLM呼出も同じ既存Local LLMへ向ける。外部推論・Portal・有料サービスへの自動fallbackは禁止。モデル最大長ではなく実際のサーバーの有効上限を採用し、必要時にmodel.context_lengthを明示する。圧縮は標準機能を使い、選定版で有効な閾値と補助providerを確認。十分な余裕（目安としてcontext上限の50%付近からの圧縮、実効閾値が版によって異なる場合は記録）を確保する。実効設定を確認せず「自動圧縮が有効」とだけ報告しない。

過去のHermes Desktopではcontext枯渇で停止した事例があるため、単なる設定値の確認だけでなく、短い合成履歴で標準の圧縮動作とLocal LLMへの補助要求を可能な範囲で確認する。テストprofileだけで必要に応じ短い履歴でも動作する閾値/保護tail設定を使用し、本番contextを埋める長時間・巨大入力試験は不要。圧縮が実行できない場合は理由と確認できた範囲を明示し、自動圧縮が実証済みとはしない。独自圧縮・再開frameworkは作らない。EVO-X2のサービス・モデル・設定変更は範囲外。

### 4.2 共用検索MCP

既存URL http://192.168.0.11:30081/mcp のStreamable HTTPをHermesに登録する。既存サービスへ新規ツール・検索backend・proxyを追加しない。

現行のYahoo robots.txtと前回のユーザー指定により、実Yahoo検索は引き続き0件。通常profileのMCP設定ではサーバーを登録するが、実際にモデルへ公開するtoolはfetch_pageだけ（公式MCP tool include/exclude等）。yahoo_searchは将来の利用条件整理後に人間が有効化する候補としてREADMEに残す。Hermesの既存web/browser/terminal等を使った代替検索・制限回避も今回行わない。段階3Aで模擬検索のMCP呼出は受入済みなので再試験・一時Kubernetes Podの作成は不要。今回はVM内のHermes自身から、既に許可確認した公開試験ページ（候補 https://httpbingo.org/html）を1回取得して実接続を確認。現在の利用条件とrobotsを再確認し、許可範囲内で行う。競馬記事を実収集しない。

### 4.3 DB

通常DB keiba_nlp、アプリ用 nlp_app、192.168.0.14:5432、SCRAM、既存LAN内TLSなし。DB owner/postgresの認証をHermesへ渡さない。

まず採用するコンテナの実行ユーザー・接続経路から既存LAN用設定のまま認証できるか確認する。DB実行側でinet_client_addr()等を観測し、VM内NATのため既存HBAに該当しないことが確認された場合に限り、実測したVM内ゲートウェイの単一/32に対する keiba_nlp/nlp_app/SCRAM の限定HBA追加を許可する（既存LAN行を保持、広いbridge subnet/0.0.0.0/0は不可）。既存HBAの変更前後・reload・認証・LAN経路・拒否動作を照合して正本に反映する。経路がこの限定対応で成立しない場合は無断でFW/ネットワーク全体を緩和せず報告する。

既存 /srv/nlp/db-secrets/nlp_app の資格情報のみ、必要なruntime UIDで読める専用のroot管理ディレクトリ配下のファイルまたは対応するPodman secretとして供給し、読み取り専用でmountする。アプリpasswordをコマンドライン・Hermesのtool引数/応答・prompt・Skill・Memory・Session・ログ・Gitへ出さない。管理者秘密は渡さない。DB接続先/DB名/資格情報パスは管理側設定から供給し、モデルに任意DB接続を許可しない。SQLはパラメータ化、短いトランザクション、例外時rollback、適切な接続/statement timeout。任意SQL実行ツールは作らない。

## 5. DBの基本ツール（探索アルゴリズムを入れない）

infra/nlp-vm/hermes/ 以下に小さなstdio MCPサーバー・固定依存・ツール契約・試験を実装する。HermesからはネイティブMCP toolとして利用する。サーバー内部は通常のPython/SQLのみで、別LLMを呼び出さない。専用のagent frameworkや記事収集ループは作らない。下記の機能名は公開APIの基準（Hermesが付与するprefixは実行時に確認）。

| tool | 入力と動作 |
|---|---|
| find_articles | URL、馬ID、レースID、phase、run_id等の任意条件で記事/関連の一覧を取得。指定なしでもページ付き一覧可。複数馬・レースは同じtarget行に条件を掛け、親記事重複を除く。未分類の確認も可能 |
| get_article | article_idで原文・出典・版・unit/targetを参照。大きな本文/明細は明示的な範囲・ページ付きで取得し、切り捨てを通知。原文の文字位置を保持 |
| save_article | source_url、body、body_kind、media/title/published_text/run_id（任意）を既存articlesへ保存。SHA-256・重複判定はコード側。既存同一版を再利用、更新版は別行。全文unitは既存triggerで生成、article_id/full unit IDを返す |
| find_horses | 名前・既知ID・生年等で候補を検索。既存normalized_nameを使用。候補が複数あっても返す。人間/LLMの判断に任せる |
| save_horse | 既存horse_idの補完または明示的な新規作成。名前を一意キーにしない。同名候補はfind結果で選べる。同名別馬も作れる |
| find_races | race_id、domain_id/race_key、名称・開催日などの判明情報で候補を検索。日付等が不明でも候補検索可能 |
| save_race | 既存race_idの補完または明示的な新規作成。確定domain_id/race_keyが同じなら既存IDを再利用。分からない日付/開催コード等を生成しない |
| save_targets | article_idと対象の配列（文章範囲、horse_idまたはhorse_label、race_idまたはrace_label、phase）を保存。必要なunitを作り、既存同一対応をupsert。明示的なtarget_idを指定した訂正も可能 |
| get_runs | run_id/status等でcollection_runsのタスク・進捗・状態を参照 |
| save_run | run_idによるcollection_runsの作成/状態・progress更新。再開時は同じrun_idを使う。進捗JSONの意味・探索の進め方はHermes/将来タスクに委ねる |

実装上の最低契約:
- 一覧は小さな既定件数と上限、続きを取れる明示的なpaginationを持つ（例 20件/最大100件）。全部のDB本文を1応答に入れない。件数上限はtool応答の制約であり、収集件数の上限ではない。
- source_url・原文・取得種別の同一版は冪等。段階2BのREADMEのSQLと制約を再利用する。metadata不明はNULL可。取得不可はnone（本文なし）、スニペットや抜粋を全文にしない。LLMの要約を原文として登録しない。
- 原文保存を先行commitし、同じエージェント活動中に索引付けする。分類失敗で原文を失わない。索引専用の別LLMバッチを通常経路にしない。
- 馬・レースの候補を示し、既存IDの選択/新規作成はLLMの判断とする。候補が曖昧ならラベルとNULLのまま保存できる。明示的に同名別馬を作ることも許す。名称・開催年だけで未知の馬やレースを必ず確定しようとしない。新規作成操作は明示的なものとし、同じ呼出の再送が無制御にIDを増やさないよう既存ID/呼出時の安定したIDを利用する。検索・保存toolが独自に意味分類しない。
- save_targetsの範囲は既存unit_id、全文unit、原文内の文字範囲（Unicodeコードポイントの0起点・半開区間）、または原文と完全一致する短い引用による位置指定を受け付ける。引用の出現が複数なら候補範囲を返す等、勝手に別の文章へ関連付けない。範囲不明なら適切な場合は全文unitを使える。不明・入力失敗で保存済み原文を失わない。
- phaseは pre/post/mixed/unknown。LLMの文脈判断を保存し、公開日時による機械判定や確信度/根拠の要求はしない。馬×レースは必要な対応のみ。phase訂正・未解決からの解決は既存unit_targetsの権限内で行う。任意の一括削除・全記事置換は公開しない。
- race_keyの形式、hash、FK、原文の範囲等は段階2BのDB制約に従う。DBスキーマの変更は不要。分類不能、欠損、情報不足をエラー扱いして収集全体を停止させない。技術的エラーは簡潔に返し、再試行の判断は呼出元へ返す。追加検索、LLMの再判定、独自の自動retryループは不要。
- Embeddingの設定や実体には書き込まない。今回のDBツールにベクトル生成・ベクトル検索・機械学習用exportは入れない。

## 6. Hermes自身の学習・Skillを阻害しない構成

恒久の競馬収集Skillは開発側で作らない。既存Hermes標準のskills、memory、session_search等を利用できるようにする。導入版で設定名を確認し、skills.write_approval=false（自分でSkillを作成/更新できる）、memory.enabled相当を有効にし、memory.write_approvalも承認不要の通常設定とする。nativeの危険な内容のguardは維持。管理者権限を要する操作や外部への送信をSkillから許可するものではない。初期profileに他のユーザー環境のSkill・会話・credentialをコピーしない。

開発側の固定情報は短いruntime contract（AGENTS.md等、採用版のcontext file機構で明示的に読まれることを確認）とツールの説明だけとする。内容は研究目的、原文と出典/分類の保存契約、情報不足の許容、検索/保存の利用条件、他システム・秘密の境界、Skillは自ら改善できること。収集の順番、レースや媒体の選び方、検索語、分類の細かな判断規則、特定件数などを書かない。固定契約とMCPコードはagentの通常書換え対象にしない。外部ページの記述は資料であって命令ではない。

今回の初期profileにはDB MCP、許可ページ取得MCP、標準Skill/Memory/Session機能等の必要なtoolを提供する。任意SQL、無制限shell/browser/他サービスのcredential、外部クラウドtool、スケジューラーの自動登録は今回の試験に必要ないため公開しない。toolsetの設定は実際の登録一覧で確認する。これは研究方法の固定化ではなく、今回の構築範囲を限定するもの。段階3Cで必要な道具と権限を改めて検討する。native機能自体は削除・改変しない。

/opt/dataはコンテナの再作成でも保持。既存Skill/Memory/Sessionを起動時に初期化・上書きする処理を作らない。管理用設定テンプレートと実行中の自己更新可能なデータを分ける。同一profileの並行書込みを避け、今回同時に動くagent sessionは1つだけ。自動起動時に何も収集していないことを確認する。本格収集前のバックアップ検討ではDBとともにHermesの永続領域も対象にするが、今回定期バックアップを実装しない。

## 7. 受入試験（実データ収集なし）

### 7.1 隔離

DBの書込試験は既存001_initial.sqlが許可している使い捨てDB名 keiba_nlp_stage2b_test を再利用する。開始時に不存在を確認して管理者が新規作成し、通常DBと同じmigrationを適用。通常DBには合成データも書かない。試験中だけ必要なHBA行を追加し、終了後に除去・reloadする。実データや以前のPoCは入力に使わない。

Hermesの試験は専用の一時profileを作り、試験DBへ接続させる。既定profileの接続先・Skill/Memory/Sessionを試験用に置換しない。試験用profileに、架空の馬/レース/短文/URL（example.invalid等）を使った小さな指示を与える。ユーザーの本番収集指示や競馬専用Skillは作らない。実Local LLMを使った短い接続・tool call確認は行うが、能力比較・長時間自律探索・全記事の分類検証は不要。

### 7.2 必須条件

| ID | 受入条件 |
|---|---|
| H1 | 最新Git、VM15、既存DB、余力、固定公式base、派生image、実UID/GID・マウント・権限を確認。既存サービスへの変更なし（必要時の限定HBAを除く） |
| H2 | Quadlet起動・停止・CLI接続が成立。既存SSH管理のみで利用可、新規公開ポート・gateway/cron稼働・自動探索0。VM上の既存DB/demo健康 |
| H3 | Hermes実CLIで既存Local LLMへの短い推論成功。実model ID・context上限・圧縮の実効設定・補助provider確認。小規模な圧縮確認の成否は根拠付きで記録し、未実測の自動圧縮性能をPASSにしない。外部推論fallbackなし |
| H4 | Hermes自身から本番の共用MCPに接続し、許可ページ取得1件成功（final_url/status/truncated/footer確認）。通常profileの実Yahoo検索tool非公開。実Yahoo検索0件 |
| H5 | DB MCPの10機能の基本契約を使い捨てDBでコード試験。本文のみ保存、同一版再登録、新版、欠損、複数馬/レース、phase、部分範囲、再開情報の保存・取得、訂正・失敗時原文保持。全件SQL照合。Embeddingなし |
| H6 | 実HermesのLocal LLMセッションから少なくとも記事保存・関連付け・参照・run進捗取得/更新を実tool callし、DB実レコードと照合。試験入力には対応先を明示し、文脈分類の能力試験にしない。MCP tool結果と実SQLを区別して確認 |
| H7 | 試験profileでHermes自身が標準skill_manageを用いて無害な試験Skillを作成・更新（個別人間承認なし）、memory書込・session保存が成立。ファイルを人間が手動生成しただけでは合格としない |
| H8 | Hermesの通常停止と同一imageでのコンテナ再作成（1回）後、試験profileのSkill/Memory/Sessionが保持され、新セッションから該当Skillを標準機能で参照できる。設定・DB MCP再接続も確認。VM再起動は不要 |
| H9 | 試験profile/使い捨てDB/臨時HBA/臨時資材を対象確認後に回収。通常DBの全8表とschema fingerprintが開始時と一致し、Embedding行の追加0。通常profileの接続設定・Skill/Memory書込可・収集スケジュール0・試験Skillなしを確認。既存PoC未変更 |
| H10 | README・固定依存・Quadlet・tool契約・試験・実測レポートをGitで引渡し、実配置とorigin/mainを照合。段階3Cの課題を残件として明示 |

H3の圧縮検証は基本動作の観測であり、巨大な履歴でcontext枯渇しないことの保証や新たなモデル評価を要求しない。圧縮そのものが成立せず今後の継続活動に影響すると判明した場合は、既存実装の問題として報告し、無断で別のLLMを採用しない。

試験Skillは収集方法ではない短い機械的な試験手順とし、自己更新の機能だけを確認する。Skillの質・自律的改善能力は段階3Cで観察する。試験用Memory/Session/Skillを通常profileに残さない。標準機能の入出力と保存の照合に必要な最小回数で終了し、延々と再試行しない。

## 8. 変更範囲・禁止・停止

tracked write scope:
- infra/nlp-vm/hermes/（派生Dockerfile、固定依存、stdio MCP、最小設定テンプレート、runtime contract、README、試験）
- infra/nlp-vm/quadlet/nlp-hermes.container
- DB認証経路のため限定HBA変更が実際に必要な場合だけ infra/nlp-vm/db/pg_hba.conf と関連README。migration/既存schema/DBロールの変更は不可。
- docs/reports/2026-11/2026-11-24_nlp_hermes_environment_report.md（実施日が異なる場合は当日名）。

許可範囲はVM15のHermes構築・上記試験用DB・必要な限定接続設定・既存LLM/MCPの通常API呼出・Git引渡し。公式image/固定依存の取得は許可。新規アカウントや課金、外部サービスへの認証は行わない。

禁止: 実記事探索/蓄積、実Yahoo検索、サイトのアクセス制限回避、収集戦略/専用Skillの事前実装、Embedding/予測研究、v3本番やDuckDB参照/変更、EVO-X2/OpenWebUI/Talos/ESXi/他VMの変更・再起動、追加の公開サービス・自動収集スケジュール、無断fallback・恒久framework、既存PoC移行。秘密値・Session生ログ・実本文・DB実体・モデルをGitへ入れない。認証情報を含むURL・無関係なブラウザタブを出力しない。今回はブラウザGUI操作を必要としない。

停止条件: VM/既存DBの重大な差異、必要な公式版/固定依存が成立しない、Local LLM/MCP接続不可、許可境界を守れない、既存データや秘密の破壊/露出、他サービスへの影響、根拠のない新機能や権限が必要、必須試験の不成立。DBの実記事に関する不明項目は停止条件にしない。問題発生時は事実・影響・復旧状態・必要な判断を報告し、検証していないことをPASSにしない。

## 9. 成果物・引渡し

実施レポートに基準commit、固定Hermes版/tag/digest、派生imageの依存・実image ID、実行方式・権限・永続領域・実効リソース、DB接続元とHBA差分の有無、Local LLMの実model/context/圧縮の確認範囲、実MCP tool一覧、合成DB試験・Hermes実tool call・Skill更新/再作成後の保持、試験の回収、H1〜H10の判定・実測根拠、通常DB開始終了状態、既存サービス・PoC保全、実Yahoo検索0、実収集0、残件を記載する。READMEには実機で確認したSSH/CLI起動、接続先の設定、保存/参照toolの使用契約、停止・再作成・永続領域、Skill管理、利用制限、再現手順を示す。実値credentialは含めない。

対象fileのみcommit/push、origin/mainとVM15配置を照合する。通常profileは研究活動開始可能な待機状態で引き渡す。

次の段階3Cで検討するのは、Hermesにどのような目的・個別タスクを与えるか、検索手段の利用条件と利用可能な探索経路、実際の探索からHermesが自分のSkillをどう作成・改善するかである。今回の完了は競馬記事の自律収集や意味検索品質を実証したことを意味しない。
