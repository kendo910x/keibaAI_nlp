# 段階3C再設計　Hermes標準サブエージェントの実機検証

2026-11-25（JST）、VM15のHermes v0.22.2からLAN内のHalogen Flash Nextを呼び、短い合成課題でT0〜T4を実施した。**親が子を順次起動し、記事をDB経由で、変換規則をSkill経由で次の子に渡せた。** 子が反復上限に達した場合も親は継続した。ただし今回の未完了の子にも `status=completed` が付いた。完了判定には `exit_reason`、`truncated` と保存済み成果の照合が必要になる。

実行版は指示書 `a4bf7f4298e51e8b3ded44c0581373e7f7de2447`、直前の基準版は `0446235cda84e281594e15851199c840d4ca2244`。[実験指示書](../../instructions/2026-11/2026-11-25_nlp_stage3c_subagent_technical_validation_instruction.md)・[段階3B環境](2026-11-24_nlp_hermes_environment_report.md)・[記事再構成PoC](2026-11-25_nlp_stage3c_semantic_reconstruction_poc_report.md)・[長文再検証](2026-11-25_nlp_stage3c_semantic_reconstruction_output_budget_retest_report.md)

| 項目 | 判定 | 観測した範囲 |
|---|---|---|
| T0　設定・経路・予算 | 実機で確認 | 親19、leaf子17の実送信ツール。親子が同じ試験home・設定・LANモデルを使用し、HTTP要求に `max_tokens=-1` が載った |
| T1　セッション分離 | 実機で確認 | 新しい子の初回はいずれもsystem＋user。親専用の文字列は子に入らず、Aの中間返却だけに置いた文字列は親・Bの全要求で0件 |
| T2　MCP継承・成果保存 | 実機で確認 | 同一UUID・本文をA、B、親、独立SQLで照合。sharedは接続・一覧・モデルへの公開までを測定 |
| T3　Skillの更新・再利用 | 実機で確認 | Aの `skill_manage` が新規作成し、Bの `skill_view` の本文指紋が実ファイルと一致。Bの変換結果は正答 |
| T4　未完了時の継続 | 実機で確認 | Cは1回の実書込み後に反復上限で終了。親はCを未完了と扱い、独立したDを起動して `42` を受領 |

## 実機・隔離・観測方法

- `nlp@192.168.0.14` で `keiba-nlp` にSSH接続した。既存 `nlp-hermes` の実image IDは `sha256:93fc35d4f46eefbfb9ad7942010f4f80a5022c182a983422a0103cbfd499da94`。コンテナのCIスタンプは `0.22.2`、commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8`。委譲、設定解決、子toolset、子の結果生成、Skill管理の5実装を固定Git blobとSHA-256で照合した。[標準委譲仕様](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/website/docs/user-guide/features/delegation.md)・[固定版の子toolset解決](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool_toolsets.py)・[Skill仕様](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/website/docs/user-guide/features/skills.md)
- 開始時に通常エージェント・MCP子プロセスがなく、Halogenの実行0・待機0を確認した。通常homeは `/opt/data`。試験用名は `stage3c-delegation-b6194f9b`。既存コンテナ内でUID/GID 10000を使った。通常設定の必要部分と架空の資料Skillを専用領域へ置き、実CLIには `HERMES_HOME=/dev/shm/stage3c-delegation-b6194f9b/profiles/stage3c-delegation-b6194f9b` を明示した。Hermesが生成する未加工セッション・思考・コンソールを一時RAM領域に収めるための選択である。試験用のOS home・キャッシュも同じRAM領域に置いた。
- 親子の要求時に読み込まれたhome、configの実パス・ハッシュ、エージェントのsession ID、state.dbパスを記録した。通常系の実設定SHA-256は `91a97e45d6ac1ef81351e276dcff62e413168b64dee76e87054ca44f0644014f`、上限試験用は `2f280df051f33c0717621a2bda7dd201acb9c7fa279bb7a1d37ace6b42729638`。Skill作成先は試験home直下の `skills/`、外部・project Skillディレクトリは空、合成Skillの実体パスにsymlinkはなかった。
- `keiba_nlp_stage2b_test` の不存在を確認して作成し、既設の `001_initial.sql` を適用した。試験DBのOIDは `20646`、所有者は `postgres`。臨時HBAはこのDB・`nlp_app`・`192.168.0.14/32`・SCRAMだけの1行。設定から取り出した接続変数とMCP実装の接続処理を使った独立照会で、実DB名、ユーザー、接続元、read-only、記事0件を確認してからCLIを起動した。[実機手順](../../../infra/nlp-vm/hermes/README.md)・[DB接続実装](../../../infra/nlp-vm/hermes/store.py)
- 初回は配布の `hermes chat -Q --max-turns 14 -q` をそのまま実行した。包装スクリプトが `PYTHONPATH` を上書きしたため、この回の根拠は実セッション、ツール応答、独立SQL、Skillファイル。補足は1回だけとし、別名の新規Skillと同じ記事版を使った。補足と上限試験では、配布スクリプトの最終起動先と同じ公式Python・`hermes_cli.main.main()`・CLI引数で実行し、専用プロファイルからHTTP観測器を読み込んだ。`chat --help` で観測器の起動も確認した。観測器は送信JSON・HTTP応答とSSEを読み、指紋・役割・ツール定義名・識別文字列の有無・終了理由・トークン数を出力した。要求・応答の差替え、偽のツール結果、Hermesソース変更は0件。

## T0　実効設定と推論経路

| 項目 | 読み戻し・実要求 |
|---|---|
| モデル | `halogen-qwen3.8-flash-next`。親子とも実provider `custom`、`http://192.168.0.13:8731/v1/chat/completions`。試験用に同じLAN宛先のprovider名 `custom:stage3c-local` を設定した。fallbackは空、設定済み補助モデルの宛先も同LAN |
| 生成枠 | 試験providerの `extra_body.max_tokens=-1` が親子に継承された。エージェント単体の `max_tokens` 属性は空でも、補足11要求・上限試験6要求の全17件の送信値は `-1`。全件HTTP 200。各回の終了理由は下表に記録 |
| Thinking | 実送信は `reasoning_effort=medium`、`chat_template_kwargs.enable_thinking=true`。短い合成課題用の設定。記事分類の配備既定は `xhigh` |
| Contextと圧縮 | 親子ともcontext 262,144、圧縮有効、実効閾値131,072、保護tail 20、縮約目標0.2。割合の設定0.50に対し、このcontextで圧縮器内部の割合は0.75、明示した絶対閾値が有効。圧縮の発火は観測していない |
| 反復・子数 | 親は実効14回、子は通常12回・上限試験1回。読込値は同時子数1、深さ1、単発CLIの子総数4、MCP継承有効、`subagent_auto_approve=false`。実測は各親が2回に分けてleafを1件ずつ起動。総数4までの境界試験は行っていない |
| タイムアウト | 親子のHTTP要求のconnect/pool各30秒、read/write各1,800秒。子の無活動タイムアウトは未設定。外側の作業枠は概ね90分。これらの時間切れは注入していない |

Halogenの `/health` と `/v1/models` はAPI・engine 0.20.1、通常出力8,192、指定上限65,536、context 262,144と整合した。独立した短文1要求でも `max_tokens=-1` を送り、0.43秒で `READY.`、`stop`、入力15・生成21（思考17）を受領した。仕様上の `-1` はサーバー上限と残りcontextで許される最大枠を要求する。個別要求で確保された枠の数値は応答にない。記事分類における65,536の品質・所要時間は前回の長文実測を参照する。[Halogen固定版の出力予算](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/docs/token-budgets.md)・[Hermes固定版の委譲設定](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool_config.py)

## T1　親子セッションと引渡し

| CLI試行（JST） | 親のsession ID | 子のsession ID（起動順） | モデル要求の根拠 |
|---|---|---|---|
| 初回 19:37:17〜19:38:16 | `20261125_103725_e469d7` | A `20261125_103745_7792d2`、B `20261125_103802_9cf5ce` | nativeのAPI計数が親4・A5・B2。HTTP観測なし |
| 補足 19:39:32〜19:40:38 | `20261125_103938_dd444e` | A `20261125_103957_2198ff`、B `20261125_104024_c4455c` | 実HTTPは親4・A5・B2。各セッション最終は `stop`、それ以前は `tool_calls` |
| 上限試験 19:41:04〜19:41:50 | `20261125_104110_b04b05` | C `20261125_104128_a93ab9`、D `20261125_104142_0ee48f` | 実HTTPは親3・C2・D1。親は `tool_calls` 2回の後 `stop`、Cは `tool_calls → stop`、Dは `stop` |

SQLiteの `parent_session_id` は各行の子2件から同じ行の親を指した。初回を含む3 CLIはすべて終了コード0。親3件は `cli_close`、子6件は `agent_close`。補足では親の最初の委譲、Aの全要求、親がAの結果を受け取った要求、Bの全要求、親のB結果受領・記事確認の順に時刻とcall IDが連なった。標準の単発CLIで同期返却を確認した。

| 補足の実要求 | 要求数 | 親だけの文字列Pあり | Aの中間返却だけの文字列Aあり | 生成tokensのうち思考 |
|---|---:|---:|---:|---:|
| 親 | 4 | 4 | 0 | 97 / 848 |
| 子A | 5 | 0 | 4 | 727 / 1,130 |
| 子B | 2 | 0 | 0 | 63 / 218 |

Pは親の依頼文だけに置き、Aは資料Skill本文だけに置いた。両方の子の初回要求はsystemと新しいuserの2通。補足Aの1回目の `skill_view` 後に初めてA文字列が出現した。親・BにAの中間tool結果の全文はなく、Aの保存済み思考5件も親・Bのメッセージ、ツール引数、思考に全文一致0件だった。各自の会話内で過去の思考が再送された場面はある。親から渡したgoal/context、共通の `AGENTS.md` の作業契約、Skill索引は初回に現れた。全セッションで能動的な `session_search` は0回。

補足の親が受け取ったAの `delegate_task` 返却は1,990文字（最終要約245文字）、Bは1,360文字（要約113文字）。次の実要求に載った返却のハッシュとSQLite上の返却が一致した。要約に加え、状態、終了理由、トークン、所要時間、`tool_trace`、一時transcriptへの参照が入った。traceにはツール名、引数キー、入出力長、成否がある。Aの資料本文や規則の答えはAの引渡しに含まれず、Bが返した答えはその後の親の入力に入った。[固定版の結果生成](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool_child_run.py)

## T2・T3　同じ記事と新しいSkillを別の子が読む

DB MCPは実stdio、shared MCPは `http://192.168.0.11:30081/mcp` のStreamable HTTPで初期化し、両方の `tools/list` を取得した。現行DBは11ツール、sharedは `fetch_page` と `yahoo_search`。親のモデルに実送信されたDB名は `mcp__nlpdb__` に続く `find_articles, get_article, save_article, find_horses, save_horse, find_races, save_race, save_targets, save_slices, get_runs, save_run`。これにshared 2、`skills_list, skill_view, skill_manage, memory, session_search, delegate_task` を加えた19件だった。子の17件はこの集合から `delegate_task` と `memory` を除いたものと厳密に一致。terminal、file、任意SQL、cron、gatewayの公開は0件。起動時には一度MCP名を未知とする警告も表示されたが、discovery後の実定義とDB操作は成立した。全9セッションでsharedの検索・取得は0呼出。shared実検索の成否は評価対象外。

初回Aは `save_article → get_article`、Bと親は同じUUIDで `get_article` を実行した。補足Aは `find_articles` で既存版を確認した上で `save_article` を実行し、同じUUIDを受領した。両試行でA・B・親の返却6件と通常コードによる独立SQLが次の内容で一致。全9セッションでDB MCPのエラー返却は0件だった。

| SQLの照合点 | 値 |
|---|---|
| 取得版 | `f1a72b95-5608-4024-b8d7-1445dd68fc5e`、`https://example.invalid/stage3c/delegation-tile`、`full` |
| 本文 | 合成文 `The sample tile is round.`、25文字、3者が読んだ版はいずれも打切りなし |
| SHA-256 | `591ade74a7419aa69b0f8de41a26719fda6347dcc5192f01a45e153b7e394c9f`。保存値とSQLによるUTF-8再計算が一致 |
| 行数 | 記事1、全文unit 1（`ba065b47-346f-466d-8f3d-f34fc99bd40f`、区間 `[0,25)`）。補足後も同数 |

資料Skillを実験者が開始前に用意し、派生Skillの本文は各回のAが作った。変換は `TILE-` に続く数字列を保ち、先頭を `MICA/` にする架空の規則。親はBに記事UUID・Skill名・別の入力 `TILE-27` を渡し、BはDBとSkillを自分で読み `MICA/27` を返した。

| 試験home内の実体 | 作成前 | 作成後のSHA-256・実読取 |
|---|---|---|
| `skills/lab-source-card/SKILL.md` | 設置済み | `8c6a3ee4eeb175287e829e356a0ad6f92782f2c4e42047a6cc7f9ad33c6d38b3`。両Aの読取本文と一致 |
| `skills/lab-tile-map/SKILL.md` | 不存在 | `a6800b02fef4023377de0fed266d83bd08b48f5f3ff6ee5669943599bea4c1cc`。初回Aが作成、初回Bの読取本文と一致 |
| `skills/lab-tile-proof/SKILL.md` | 不存在 | `21495c37bf6c5b00444dea836ba1fa76fdee5519af791159615e7708091f8a4b`。補足Aが作成、補足Bの読取本文と一致 |

両回とも `skill_manage` の個別create結果と `skill_view` は成功。簡易Skillに付いたlintは `missing-metadata` と `missing-section` で、読取と適用には成功した。途中の手修復は0件。補足の親のsystemは4要求で同じハッシュで、新規Skill名は索引に現れなかった。新しく起動したBのsystemには名前が現れ、初回messagesには変換規則がなく、2回目に `skill_view` の返却から規則が入った。Bへ渡したcontextにはSkill名や答えを書かず、既知名はgoalにあった。その後、別の親を起動したT4の初回systemにも新規Skill名が現れた。稼働中の親の索引更新に依存せず、委譲時に既知の名前を渡せる。

## T4　未完了を検出した後の継続

子の `delegation.max_iterations` だけを12から1に変えた。Cには、①runを `running`・step 1で作成、②戻りを得てからDBを再読、③再読した更新時刻付きで完了を書き込む、の順を指定した。Dには独立した加算だけを依頼するよう親に指示した。

| 子 | 親に返ったnative値 | 独立した確認 |
|---|---|---|
| C | `status=completed`、`exit_reason=max_iterations`、`truncated=true`。返却2,030文字、要約881文字 | 実ツールは `save_run` 1回。SQLで `6cfb12dd-9ad7-4c72-a3db-482ad37f8c15`、`running`、`{"step":1}`。再読・完了更新は0回 |
| D | `status=completed`、`exit_reason=completed`、`truncated=false`。返却949文字、要約2文字 | 親はCの結果を受け取った次の要求で新しいDを起動。Dはツール0回、応答 `42`。親の最終応答はCを未完了、Dを完了とした |

Cには通常反復1回に加えて、標準の終了要約用のモデル要求が1回あった。nativeのAPI計数は1、HTTP実測は2で、2回目の `stop` は要約生成の終了。親の反復枠には余裕があった。今回の親には終了理由を読む指示を与えた。親プロセス消失、VM再起動、ネットワーク断、並列競合、途中推論の自動復元は未検証。

## 次の設計への判断

1. **親子で探索を分ける。** 現構成の単発CLIで、親は明示した課題と短い結果を使って次の子を順次起動できる。親に返る要約・traceの量は計画に含める。
2. **DBとSkillを引渡しに使う。** 成果はDBの版ID、手順・規則はSkill名で次の子へ渡せる。統括・検索の初期Skillと、保存原文を読む記事単位の独立分類Skillの設計へ進めてよい。
3. **未完了でも次に進める。** この合成課題では途中までの書込みを残しながら独立した子を実行できた。上限到達時の `status` 単独で業務を完了にすると、未処理の工程を落とす。
4. **処理枠を個別に指定する。** 固定版の既定は単発CLIの子総数2、同時10、深さ1、子250反復、子の無活動期限なし。次の小規模試験では予定子数、順次実行、親に残す反復数、子1件の反復数、HTTP期限、出力枠を別々に決める。分類の長文予算と今回の短課題のthinking条件は別に扱う。[固定版の委譲実装](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool.py)
5. **通常コードが進捗の正本を持つ。** 記事版、処理段階、利用したSkill版、書込み済み成果、検証済み完了を照合し、再開時は未処理の工程を選べるようにする。既存DB/MCPを基礎にこの契約を設計する。実記事収集、分類精度、圧縮問題の解消、無停止運転、恒久の階層・並列数の判断は後続工程。既存3C-2sの不合格判定を維持する。

## 回収・保全・証拠

開始19:30:09、終了19:46:33（JST）に同じ読取り専用トランザクションで通常DBを照合した。8表の件数と各表全行の指紋が一致。件数は `articles` 56、`collection_runs` 3、`horses` 68、`races` 16、`text_units` 207、`unit_targets` 750、Embedding 2表は各0。計1,100行の集約は `948e9ffdb3b6bcd5a06964f7843fbb273a887f37da42655c38f9b5b7baf4d828`、DDL指紋は `2a303dd483dd85e517a71b60870e7d06b1151da55f39b44b629aafb38a863b3e`。

- 試験DBはOID `20646`、所有者 `postgres`、接続0を再確認して削除し、不存在を確認した。HBAのSHA-256は開始・復元後 `1bdb2a03ea220d99967c9ca4094a6653684332094506ee7a3d6cec1810964755`、一時適用時 `9e27c3fb044ff6a5b4d41982f46d617c79ea01eda4445b68272ced4dcfaf6071`。復元・reload後のparse errorと試験DB行はともに0件。
- RAMプロファイルと設定転送用の専用ディレクトリは、パス・所有者・デバイス・inodeを照合して回収した。転送用では事前確認時にHermesが作った雛形・設定バックアップ・空ログなど5ファイルも識別してから回収した。s6の監視枠は前後同じ6件で、試験専用の枠は0。既存Hermes・PostgreSQL・demoのコンテナID、image ID、PID、起動時刻が一致。Hermesコンテナの全プロセス一覧は開始時と一致し、残存する親・子・MCPは0、Halogen終了時の実行・待機はともに0。
- 通常state.dbとWALのハッシュ、11セッション・1,061メッセージ、通常設定、既存収集Skill、Memory、収集ログを含む照合対象351ファイルの指紋・集合が前後一致した。通常設定は `ef4b3242a2e99cb6afabcd0b2c24ccfadef64d24197daf87fb986301d3a98178`、既存収集Skillは `0ce3913aaa01b8eeafe807ec9c546de51c58eee3b18ee35b520581eae9f70b82`。別置きの過去run資料40件・dump 4件は回収前後に全件のハッシュを照合し、更新時刻・変更時刻はいずれも今回の実験開始前だった。開発PCのPoC 6ファイル、前回までのGit外証拠41＋8ファイルも実験の前後で同一だった。
- 詳細証拠は開発PCの `%LOCALAPPDATA%\keiba-nlp-review\subagent-20261125-192728-b6194f9b` に保全した。NTFSのアクセスは実行ユーザーとSYSTEMに限定した。索引 `evidence-index.json` は26ファイルを結び、SHA-256は `4f0d120f118f1cdaf20b89ddcf85d0386fb19edceb5f0756ffd3c019b8d532d1`。合成指示、試験設定、HTTPメタデータ、メッセージとSkillの指紋、SQL照合、回収記録を含む。思考全文・生のセッションDBは保全対象外。Git変更は本レポート1本。
