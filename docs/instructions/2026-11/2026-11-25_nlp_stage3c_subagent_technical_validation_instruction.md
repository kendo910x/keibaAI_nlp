# 段階3C再設計 — Hermes標準サブエージェントの技術検証

作成日: 2026-11-25（JST）
対象: VM15 / 既存Hermes v0.22.2 / 既存LAN内Halogen Flash Next
基準: 0446235cda84e281594e15851199c840d4ca2244
担当: Codex（実機検証・独立照合・レポート作成）

## 1. 目的

[馬別文章再構成のPoC](../../reports/2026-11/2026-11-25_nlp_stage3c_semantic_reconstruction_poc_report.md)と[出力上限拡大の再検証](../../reports/2026-11/2026-11-25_nlp_stage3c_semantic_reconstruction_output_budget_retest_report.md)を踏まえ、次の構想を検討している。

- 親Hermes: 研究活動の統括、対象選択、追加探索の判断、Skill改善。
- 子Hermes: レース等を単位とする独立した探索・収集。子は順次起動できればよく、並列化は必須でない。
- 記事単位の分類: 取得原文と分類Skillを使う独立した直接API推論。Thinkingを含む大量の生成履歴を親子の探索セッションへ持ち込まない。
- 共通のDB・Skill: 成果と知識をセッションから独立させ、後の子や新しい親でも利用できる。処理済み・未処理の確実な管理は通常コードで行う。

今回は**Hermes標準のdelegate_taskが実環境で使えるかという技術検証**である。初期検索Skill・分類Skill・統括Skillの完成を待たず、短い合成課題でコンテキスト分離、MCP継承、Skillの更新・再利用、設定・終了・障害時の挙動を確認する。検索能力や競馬文章の分類精度、自律的な戦略改善の質を合否に用いない。DB/MCPの再設計、恒久運用方式の確定、初期競馬Skillの作成、外部検索・実記事収集は別工程。

## 2. 参照・現行仕様

最初にルートAGENTS.md、対象配下のAGENTS.md、git fetch/statusとorigin/mainを確認する。[Hermes環境README](../../../infra/nlp-vm/hermes/README.md)、[config.yaml](../../../infra/nlp-vm/hermes/config.yaml)、[環境構築レポート](../../reports/2026-11/2026-11-24_nlp_hermes_environment_report.md)、上記2件のPoCレポートを読む。READMEの初期公開範囲は旧時点のものなので、現行設定・実機の契約と区別する。

導入版の固定ソース（NousResearch/hermes-agent、d923a5eb487a17c0a68801bba9ef0f56c81040a8）を使用し、最新版の説明をそのまま適用しない。
- [サブエージェント仕様](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/website/docs/user-guide/features/delegation.md)
- [delegate_task実装](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool.py)
- [delegation設定](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool_config.py)・[子のtoolset解決](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/tools/delegate_tool_toolsets.py)
- [Skill仕様](https://github.com/NousResearch/hermes-agent/blob/d923a5eb487a17c0a68801bba9ef0f56c81040a8/website/docs/user-guide/features/skills.md)
- Halogen 0.20.1の[出力予算仕様](https://github.com/peonist-ai/halogen-flash-server/blob/d2f4286fc97fd1f75cd765714dbc50524004356f/docs/token-budgets.md)

ソース上では新規の子セッション、親toolsetの継承と一部ツールの除外、単発CLIでの同期結果返却がある。単発CLIの子総数の既定値は2、同時子数10、深さ1、子の反復上限は250。child_timeout_secondsは無活動時間の上限（既定なし）であって単純な総実行時間の上限ではない。バックグラウンド完了の記録は中断された子の実行再開を保証しない。これらは事前のソース知見であり、実機の有効設定と実挙動を別途確認する。

## 3. 隔離・許可範囲

既存nlp-hermesコンテナの実image ID、Hermes固定版、稼働状態、実モデル/API、通常profile、通常DBの8表の件数・全行指紋・DDL指紋、既存Skill・Memory・設定・収集履歴とPoC証拠の保全状態を記録する。通常profileでのエージェント稼働がないこと、Halogenの混雑状況を確認する。既存サービスの停止・再起動、アップグレード、モデル切替はしない。

READMEの合成試験と同じ方式で、既存コンテナに**試験専用の空profile（例: profiles/stage3c-delegation-test、HERMES_HOMEを明示）**を作る。既存パスと衝突しないことを確認し、通常profileのstate.db、Skill、Memory、設定へ書かせない。通常profileの複製は設定の必要部分だけとし、実記事・履歴・秘密を試験課題に含めない。実際に読み込まれたconfigとhomeを親子それぞれ確認。起動時のprofile解決が保証できなければ停止する。

DB操作はREADMEにある試験専用DB keiba_nlp_stage2b_test を新規の空DBとして使用し、既存のmigration、nlp_app、必要最小の臨時HBA行を用いる。既存の同名DBがあれば勝手に削除・初期化せず報告。試験profile内のMCP接続先が試験DBであることを先に通常コードで確認する。合成記事はexample.invalidの固定URL・短文1件程度で十分。通常DBの書込禁止。DBの新仕様やMCPの実装変更は行わない。既存のshared MCPは接続・tools/list・親子の実送信ツール定義の確認までとし、yahoo_search/fetch_pageによる外部検索・取得はしない。今回測るのはMCP継承であり、検索サービスの実検索品質ではない。

試験profileのみ、現行cli toolsetsにdelegationを追加する。既存の公開権限を不必要に広げず、terminal、file、任意SQL、外部推論、cron、gateway等を追加しない。子は親の許可範囲を越えないこと。subagent_auto_approveは有効にしない。fallbackや補助モデルも既存LANのFlash Nextに限定。試験用のSkill書込を許可する場合は試験profile内部だけ。既存ファイルの更新先・symlink・外部Skillディレクトリへの解決に注意する。

原則、実CLIの単発実行（hermes chat -Q -q 等、実装に合う引数）を使う。1profileにつき同時親1、子は順次・max_concurrent_children=1、max_spawn_depth=1。oneshot_max_childrenは試験に必要な数（例えば4）を明示し、既定2による誤停止を避ける。正常系には必要な反復回数を確保し、失敗試験だけは後述の制限を使う。実際に有効になった値を記録。試験全体は小規模（正常系の親＋子2件、失敗系の親＋子2件を基本、必要なら新親の再開確認1件）に留める。外側の安全枠は概ね90分、進行中の正常な推論を速さだけで中断しない。混雑、異常な反復、継続障害、通常環境への影響があれば停止して部分結果を報告する。

## 4. 試験項目

実際のモデル要求（message/tool schema/route/予算・終了理由）、session ID・parent_session_id、ツール呼出/返却、DB実測、Skillファイルのhashを照合する。子や親の自己申告だけを根拠にPASSとしない。前回の圧縮試験と同様、必要なら一時的なクライアント側観測を用いるが、Hermesの実行ロジックを書き換えたり架空の応答を差し込んだりしない。CLIの実経路が観測不能なら限定的なハーネス検証と区別する。秘密やthinking全文は保存しない。

### T0: 基本構成・出力予算・推論経路

- 親の実送信ツール一覧にdelegate_taskがあり、現行のMCP/skillsツールが維持されることを確認。親子のmodel/provider/base_url/context_length、thinking、実際のmax_tokensまたは同義パラメータ、タイムアウト、圧縮設定、反復上限、delegation設定を記録する。設定キーの存在だけで実効としない。
- Halogen 0.20.1ではmax_tokens=-1がサーバー上限とcontext残量の範囲で最大の生成枠を要求する仕様。短い合成入力1要求で直接APIの受付と正常終了を確認してよい。実際に返る上限等を確認できる範囲で記録。無限生成や上限撤廃とは扱わない。Hermesが-1を通せるかは導入版の設定解決・実送信で確認し、未対応なら65,536等の許容値を使える既存設定経路を確認する。サーバーのcap超過の送信を意図的に繰り返さない。
- 記事分類の既定xhighを低減して速度を稼ぐ試験ではない。今回の親子課題は短く、試験profileだけの適切な予算を使ってよい。現行条件との差は明示し、長い本番推論の品質・完結率に外挿しない。圧縮を誘発する負荷は不要。圧縮無効化が必要な場合も試験profile内だけで、実行予算を別途確認し、理由を記録する。

### T1: 親から子を起動し、コンテキストが独立するか

合成課題を2件、親がdelegate_taskで順に依頼する。親の会話にはテスト専用の識別文字列Pを置くが、子のgoal/contextには渡さない。子Aの作業途中のツール返却に別の識別文字列Aを置き、最終報告はID・処理成否・短い知見だけとする。子Bには必要なID等だけを渡し、Aの中間履歴を転記しない。

- 実際の親・A・Bのsession IDと親子関係、各子の初回要求、親のdelegate_task返却後の要求を確認。親の会話全文、兄弟の履歴・中間tool result・reasoningが自動的に混入していないこと。意図的に渡したgoal/context、共通project context・Skillの索引、短い要約は区別。
- Aの中間内容が親/子Bへ伝わっていないことは、専用canaryと実際のmessagesで確認する。session_searchによる能動的な履歴参照は自動引継ぎと異なるので、試験では使用させない。
- 親が結果を受け取って子Bを起動したこと、単発CLIでの同期/非同期の実挙動、返却されるstatus・summary等、親に返る情報量を測定。親の最終文だけではなく実際のdelegate_task呼出を確認する。

### T2: 子へのMCP継承と保存

T1の子Aに試験DBだけで合成記事1件を登録・参照させ、記事IDを短く返させる。子Bに同じ記事IDを参照させ、親もその成果を確認する。通常コードによる独立SQL照合で、同じ記事・本文hash・件数を確認する。子が使用した実ツール名・戻り値・DB接続先とMCPエラーを記録する。子が親にない権限を得ていないことも親子の実送信ツール一覧で確認する。

shared MCPの検索・取得ツールが子の定義に現れるかはtools/listと要求の定義で確認する。実際の外部検索は実施しないので、shared MCPの実呼出成功まで証明したとはしない。leaf子にdelegate_taskやmemory等の禁止ツールが出ないかも確認する（標準の制限に従う。SkillとMemoryは別機能）。失敗時に広いtoolsetへ無断変更しない。

### T3: Skillの更新と後続子による再利用

T1と同じ子A/Bを使い、試験専用の小さな架空Skill（名前衝突のないもの）を用意する。Aは合成課題で得た架空の規則をskill_manageで作成または既存試験Skillへ追記する。例えば架空の資料の識別子から特定の出力ラベルへ変換する規則でよい。Aの親への要約にその規則の答えそのものは含めず、Skill名・更新成否だけを返す。Bは新規子としてskill_viewで読み直し、同じ規則を別の合成入力へ適用する。

Skillの実体パス、更新前後hash、書込・読取ツールの実成功、Bの実入力にSkill内容が現れた経路、答えの一致を確認する。親による手動転記、Codexによる試験途中のSkill修復で成功扱いにしない。新規Skillの索引更新が同じ親の途中で反映されるかと、既知名での直接読取は区別。既存親の再読が必要なら報告する。必要に応じて新しい親セッションでも同じ試験Skillを参照し、セッションを超えた永続性を確認する。競馬Skillそのものの研究・最終品質評価はしない。並行更新の衝突試験は今回は不要。

### T4: 子の未完了・失敗時の親の継続

別の短い単発CLI試験で、通常系とは区別して子を意図的に未完了にする。例えば試験profileのdelegation.max_iterationsを1等に設定し、複数回の実ツール呼出と追加判断が必要な合成課題を割り当て、実際の反復上限終了を観測する。試験側が事前に作ったfake statusを返す方式は禁止。失敗誘発の詳細は実装に合わせてよいが、通常DB・サービス・実プロセスを強制停止しない。通常のMCPエラーを子が処理できたケースだけで、子の異常終了試験に合格したとはしない。

親に返るstatus/exit_reason/truncated/summary、失敗前に保存された試験DB成果が残るか、親が失敗を完了と誤認せず次の短い独立子を実際に起動し結果を受け取れるかを確認する。後続子は制限下でも終えられる簡単な課題とする。子自身の上限による終了と親全体の上限による終了を分ける。意図した未完了が発生しなければ評価不能とし、別の安全な制御方法の候補を報告する。何度もエラーを起こさない。

標準サブエージェントが親のプロセス消失時に実行再開を保証するとは仮定しない。新しい親セッションから保存済み合成記事やSkillを再読できることは試してよいが、それは永続成果の再利用であって途中推論の復元ではない。親クラッシュ・OS再起動・ネットワーク障害・並列競合の実障害注入は行わない。今回測らなかった障害経路を明記する。

## 5. 結論・成果物

T0〜T4を「実機で確認」「一部確認」「不適合」「未確認」に分け、設定と根拠（ログ/session ID/実要求/DB照合/Skill hash）を示す。エージェントが命令どおり作業しなかった場合も機能の欠如・設定不備・モデルの判断・試験設計上の不備を切り分ける。必要なら短い合成指示の修正を一度行ってよいが、全試行を記録する。

次の設計への結論は、(1) 親子セッションによるコンテキスト分離が現構成で成立するか、(2) DBとSkillを通じて次の子へ成果・知識を渡せるか、(3) 子の未完了が親の継続を阻害するか、(4) 単発CLIの反復/子数・provider予算・タイムアウト等の制限をどう設定すべきか、(5) 通常コードによる永続進捗管理が必要な範囲、の5点。現在の技術構成を基礎に次のDB/MCPと3種の初期Skill（統括・検索・分類）へ進めるか提案する。親子階層や並列数、恒久設定の変更はこの段階では決定しない。圧縮問題の解消、無停止運転、実記事収集能力を証明済みとしない。

レポート: docs/reports/2026-11/2026-11-25_nlp_stage3c_subagent_technical_validation_report.md（実施日が変われば当日名）。

試験終了後は子・親・MCPプロセスが残存しないこと、Halogenの待機/実行状態を確認。試験profile・試験DBをREADMEに従って識別子・所有者・接続数確認の上で回収し、臨時HBA行を復元・reload・照合する。他の変更や他taskのデータを削除しない。試験profileの登録に伴う監視枠が発生していれば専用分だけを既存手順で回収。通常8表・DDL、通常profile/Skill/Memory/設定・既存サービス・前回PoC証拠の保全を実測確認する。試験の再現に必要な合成課題・設定差・検証記録はレポートに簡潔に記載し、必要な詳細証拠はアクセス制限されたGit外の領域へ保全する。

tracked変更はレポート1本のみ。通常DBのDML/DDL、通常profile・既存Skill変更、恒久config/MCP変更、サービスの再起動・再配備・更新、外部検索・記事取得、v3操作は禁止。試験専用の一時資材以外を変更しない。対象レポートのみcommit/pushし、origin/mainへの包含と本文一致を確認する。既存3C-2s不合格判定は維持する。結果が出たら設計相談へ戻る。
