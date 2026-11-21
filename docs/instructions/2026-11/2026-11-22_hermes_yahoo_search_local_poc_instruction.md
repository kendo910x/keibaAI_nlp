# Hermes × Yahoo! JAPAN検索 ローカル比較PoC 指示書

作成日: 2026-11-22 / 対象: `kendo910x/keibaAI_nlp`

## 目的・判断
**Hermesの探索判断と検索バックエンドの能力を切り分ける。** 既存のYahoo! JAPAN検索MCPを開発PC上で再利用し、検索結果の関連性・新規記事発見とHermesからのツール呼出しを、前回のG1探索結果と比較する。均等な記事件数や全記事網羅は要件にしない。

開始前に本repoの `AGENTS.md` と [前回G1探索レポート](../../reports/2026-11/2026-11-22_g1_article_autonomous_search_poc_report.md) を読む。参照正本は `kendo910x/OpenWebUI` の [`infra/google-search-mcp/yahoo_search_server.py`](https://github.com/kendo910x/OpenWebUI/blob/main/infra/google-search-mcp/yahoo_search_server.py) と [導入レポート](https://github.com/kendo910x/OpenWebUI/blob/main/docs/reports/2026-10/2026-10-18_yahoo_search_mcp_report.md)。取得したコードの版／SHAを記録する。

## 実施範囲
1. **ローカル接続**：OpenWebUIのYahoo MCPロジック（HTTP GET＋HTML解析、stdioの`yahoo_search`）を `poc/yahoo_search_mcp/` に再利用し、開発PCの独立venvで起動。既存のHermes環境・設定を調べ、実機に適合するstdio MCP登録を行う。モデルは既存Halogen / Flash-Next。既存OpenWebUI、Kubernetes、EVO-X2の設定には触れない。元実装との変更点は依存・パス・下記429処理など必要最小限にして明記する。
2. **単体試験**：日本語の既知クエリでタイトル・URL・抜粋が取得できるか、失敗・0件・ブロックを区別できるか確認。架空HTTP応答で429処理をテストする。最初の実検索は少数に限定。
3. **検索エンジン比較**：2024/2025/2026年皐月賞を題材に、陣営コメント・騎手談話・特記事象など**共通の検索語4件程度**を固定し、Hermes既存検索系（利用できるバックエンド名・実際のfallbackも記録）とYahoo MCPで検索。上位URLの関連性、一次資料、新規URL、ブロック・空振りを比較。片方が失敗しても別の成功を同等の結果とみなさない。
4. **Hermes自律探索**：Yahoo MCPを明示的に使わせ、同じ3競走の未知記事を追加探索する。検索語はHermesが選択。まずYahoo実検索は**追加6回以内**、追加URL／独立した情報の発見、検索戦略の展開、ツール呼び出しの成否を観測する。得られた情報は既存の `data/poc/g1_passages.jsonl`（24件）とURL照合し、見つからなくても不成功扱いしない。前回データが利用できなければその旨を記録する。

## アクセス制御・境界
- **429は制限信号**。原則として`Retry-After`を尊重して待機し、指定がない場合も即時再試行せず十分な間隔を空ける。再試行は最大1回、再び429または長時間の待機指定なら停止・報告する。検索間隔は控えめにし、並列実行・高頻度連打はしない。429を回避するためのIP・UA変更、プロキシ切替、CAPTCHA回避はしない。HTTPステータス、待機指示、再試行有無を記録する。
- 技術的にHTTP 200が得られることと、利用条件上の許諾は別。アクセス方針・利用条件を確認し、許可されない自動取得を要する場合は実アクセスを進めず報告する。
- ページ本文取得や大量収集、Embedding・DB改修、恒久サービス化、K8sの共通公開、OpenWebUI元repo変更は本タスク対象外。既存の収集データを無断で置換しない。ローカル結果・検索抜粋・実行ログ・認証情報はGit管理しない。

## 完了・報告
実機MCP接続、単体検索、固定クエリ比較、Hermes自律探索を**実測できた範囲で**判定し、各段階の失敗も隠さない。検索バックエンドによる差、Hermesの判断による差、本文取得の可否を分けて報告する。実際に比較していない能力は優劣を断定しない。

コード・最小限の実行手順（必要な場合）と `docs/reports/2026-11/2026-11-22_hermes_yahoo_search_local_poc_report.md` を対象限定でcommit／push。次にローカル方式を続けるか、既存Kubernetesの検索サービスを共通利用するかを提案し、**Kubernetesへの変更は別タスク**とする。
