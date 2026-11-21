# Hermes × Yahoo! JAPAN検索 ローカル比較PoC レポート

実施日: 2026-11-22 / 対象: `kendo910x/keibaAI_nlp` / 指示書: [hermes_yahoo_search_local_poc_instruction](../../instructions/2026-11/2026-11-22_hermes_yahoo_search_local_poc_instruction.md)（Commit `4da1c179`）

## 0. 判定サマリ

| 段階 | 判定 |
|---|---|
| 1. ローカル接続 | **成功**（独立venvでstdio MCP起動、Hermes設定登録済み。ただし現セッションでのツール読込は再起動が必要） |
| 2. 単体試験 | **成功**（unittest 10/10、stdio実機で実検索5件、429処理は架空応答で5パターン検証） |
| 3. 固定クエリ比較 | **実施**（4クエリ×両エンジン。Yahoo 4/4 HTTP=200・retry 0。Hermes 4/4成功だが4件中2件でddgs失敗→fallback） |
| 4. Hermes自律探索 | **実施**（追加6回、全HTTP=200。新規URL25件発見、既存24件とのURL一致は1件） |

429は本番実検索中に一度も発生せず（全11回 HTTP=200）。再試行・待機ロジックは架空応答テストのみで検証。

## 1. 参照正本・取得版

- 元実装: `kendo910x/OpenWebUI` `infra/google-search-mcp/yahoo_search_server.py`
- 取得版: commit **`5f7f3ddebe1b22798e9d6ac443b6103e4d72fdef`**（2026-10-18 09:27 +0900「feat: add self-authored Yahoo! JAPAN search MCP…」）
- 取得元: ローカル clone `C:\Users\kendo\OpenWebUI`（HEAD `0288932b816a213db3901f20b274c6ae488507db`）
- GitHub の API / raw からの取得は 404（`kendo910x/OpenWebUI` がAPIから見えない: private化または改名と推定）。ローカル clone を正本として使用
- 導入レポート（`docs/reports/2026-10/2026-10-18_yahoo_search_mcp_report.md`）も GitHub raw では 404 のため未読。セレクタ・判別マーカーはコード内の Stage 0 実測コメント（2026-10-18）から引き継ぎ

## 2. 実施範囲1: ローカル接続

### 構成
- `poc/yahoo_search_mcp/yahoo_search_server.py` — 元実装コピー＋必要最小限の変更:
  - HTTP 429 処理追加（`Retry-After` 尊重／未指定なら既定待機／再試行最大1回／`MAX_WAIT_AFTER_429` 超の待機指定は停止・報告）
  - 結果末尾に `[HTTP] HTTP=… retry=…` の記録行を付与
  - セレクタ・判別マーカー・num_results clamp・UA は元実装のまま。IP/UA変更・プロキシ切替・CAPTCHA回避なし
- 独立venv `.venv-yahoo-mcp`（Python 3.14.0）: `requests==2.34.2` / `beautifulsoup4==4.15.0` / **`mcp==1.30.0`**
  - mcp 2.x は `mcp.server.fastmcp` が `MCPServer` へ改名され元実装が起動不能（`ModuleNotFoundError` を実測）。本番K8sと同じ 1.30.0 に固定して変更を最小化
- Hermes登録: `hermes config set mcp_servers.yahoo_search.command/args` で `hermes/config.yaml` に stdio 登録済み（venv python + サーバーパス）。**MCPツールは起動時読込のため、現セッションでは `mcp_yahoo_search_*` ツール未読込**。読込にはHermes再起動が必要（hot-reloadなし）。本PoCの検索実行は stdio クライアント（`test_stdio.py` / `run_search.py`）から同一サーバーを起動して行い、サーバー側の挙動（429処理・出力形式）は MCP 経由と同一

### 実行手順（再現）
```
py -3.14 -m venv .venv-yahoo-mcp
.venv-yahoo-mcp/Scripts/pip install -r poc/yahoo_search_mcp/requirements.txt
.venv-yahoo-mcp/Scripts/python poc/yahoo_search_mcp/test_stdio.py "皐月賞 2026 結果"
.venv-yahoo-mcp/Scripts/python poc/yahoo_search_mcp/run_search.py <出力.json> <クエリ...>   # 5秒間隔・逐次
```

## 3. 実施範囲2: 単体試験

- `test_yahoo_search.py`: **10/10 OK**
  - パース5: 正常（タイトル/URL/抜粋）、`#:~:text=`除去、0件、ブロック（captcha/ロボット確認マーカー）、不正HTML
  - 429処理5: `Retry-After` 尊重、未指定時既定待機、再試行1回上限、再429で停止、長時間待機指定で停止（不正値は既定フォールバック）
- `test_stdio.py`（実機stdio MCP）: initialize 成功（server=yahoo-search, protocol=2025-11-25）、`tools=['yahoo_search']`、実検索「皐月賞 2026 結果」で5件取得成功（netkeiba / JRA / スポーツナビ / sp.jra / netkeibaTV）、`HTTP=200 retry=0`
- 失敗・0件・ブロックの区別: 架空HTMLフィクスチャで判別確認済み

## 4. 実施範囲3: 固定クエリ比較（4クエリ）

共通検索語: ①皐月賞 2024 騎手 レース後コメント ②皐月賞 2024 ダノンデサイル 除外 ③皐月賞 2025 クロワデュノール 無敗 陣営コメント ④皐月賞 2026 ロブチェン 落鉄

### 実行記録（HTTP・バックエンド・fallback）

| クエリ | Yahoo MCP | Hermes web_search（served_by / fallback） |
|---|---|---|
| ① 2024 騎手コメント | HTTP=200 retry=0 (0.8s) | 成功 / **exa**（ddgs失敗: DDGSException No results → fallback） |
| ② 2024 ダノンデサイル除外 | HTTP=200 retry=0 (0.7s) | 成功 / ddgs 直接（fallbackなし） |
| ③ 2025 クロワデュノール | HTTP=200 retry=0 (0.7s) | 成功 / **parallel**（ddgs失敗 → fallback） |
| ④ 2026 ロブチェン落鉄 | HTTP=200 retry=0 (0.7s) | 成功 / ddgs 直接（fallbackなし） |

- 設定済みバックエンド `ddgs` は日本語競馬クエリで4件中2件「No results found」→ 無鍵free tier（exa / parallel）へ fallback。Hermes側はfallbackが常時起き得る
- 両エンジンとも4/4成功・ブロックなし・空振りなし。片系のみ失敗という差は出なかった

### 関連性・一次資料・重複

- 一次資料（JRA公式回顧）: ①はHermesのみTop5内（5位）、④は両者（Yahoo 4位 / Hermes 2位）、②はHermesが集約ページ経由、③は両者ともTop5になし
- ③はTop5の重複ゼロ: Yahooは予想系・知恵袋・YouTube中心、Hermesは長文回顧（テレ東・日刊ゲンダイ・ラジオNIKKEI・Number・SPAIA）。**同一クエリでもエンジン間で提示される記事群がかなり違う**
- 抜粋の質: Hermes（exa/parallel）はdescriptionに騎手コメント全文級の高情報量を含むことがあった（さんけい・オリコン）。Yahooの抜粋は短め
- Yahoo固有のノイズ: Top5に知恵袋・Instagram・Yahoo動画検索ページ等のUGCが混入（①③④で計5枠）。競馬一次情報の網羅自体は netkeiba / tospo / 優馬 等が上位に安定
- 新規URL: 固定4クエリで Yahoo 上位20URL中17が既存24件にないURL（内1はYahoo内部リンク）

## 5. 実施範囲4: Hermes自律探索（Yahoo MCP・追加6回）

検索語はHermesが選択（レース単位→人物・ライター単位へ展開）。全6回 HTTP=200 retry=0、5秒間隔・逐次。

| 検索語 | 主な収穫 |
|---|---|
| 皐月賞 2024 戸崎圭太 藤岡康太 悼む | netkeiba 261765（戸崎「康太の思いも乗せて」＋友道師） |
| 皐月賞 2024 コスモキュランダ モレイラ 2着 | netkeiba 261670、umanity、日刊スポーツ |
| 皐月賞 2025 ミュージアムマイル 回顧 福嶌弘 | **既存passage一致1件**（テレ東 037730）＋note回顧2件 |
| 皐月賞 2025 クロワデュノール 北村友一 レース後コメント 2着 | netkeiba 294871、オリコン（北村友「申し訳ないです」） |
| 皐月賞 2026 回顧 フォルテアンジェロ | note回顧、JRA-VAN G1特集、競馬研究ニュース |
| 皐月賞 2026 ロブチェン 杉山晴紀 調教師 コメント | ラジオNIKKEI栗東レポート post_37459、tospo 70724 |

- URL照合（`data/poc/g1_passages.jsonl` 24件と正規化比較）: 30 URL / 重複除去27 / **既存一致1 / 新規25**（Yahoo内部リンク1を除く）
- 独立した情報の発見: あり（騎手・調教師・ライター名を軸にすると既存収集にない回顧・会見コメント記事が出る）
- 検索戦略の展開: 「レース＋事象」→「人物名＋コメント」への切替で別記事群に到達。Yahooは人物名クエリでも安定200
- 見つからなかった場合の不成功扱いなしの規定は発火せず（全回5件返却）

## 6. アクセス制御の記録

- 実Yahoo検索は合計11回（stdio試験1＋固定4＋自律6）、全件 HTTP=200・retry=0・待機なし。429・ブロックは観測されず
- 再試行・待機挙動は指示書どおり架空応答でのみ検証（実429未発生）
- 間隔: run_search.py で5秒間隔・逐次実行。並列・連打なし
- **HTTP 200 ≠ 利用条件上の許諾**。Yahoo! JAPANの自動取得に対する利用条件の精査は未実施（次段階の宿題）。収集はPoC範囲（検索結果スナップショットのみ、ページ本文の大量取得なし）に留めた
- 検索結果JSON（`data/poc/yahoo_*.json`）はGit管理外（`.gitignore`済み）

## 7. バックエンド差とHermes判断差の切り分け

- **バックエンド能力差**: ①日本語競馬特化クエリで ddgs は高率に無結果→fallback（exa/parallelが実働）。Yahoo! JAPAN直接は11/11成功で安定。②エンジン間でTop5の重複が低い（③でゼロ）ため、単一エンジンでは記事集合の偏りが出る。③YahooはUGC混入、Hermes fallback側は抜粋情報量が大きい
- **Hermes判断差**: 現セッションはMCPツール未読込のため、ツール呼出し判断は未検証（stdioクライアント起動で代替）。人物名への検索語展開など探索戦略自体はHermes側で機能
- **本文取得の可否**: 本タスク対象外（未実施・優劣断定しない）
- 実際に比較していない能力（Yahoo MCP読込後のHermes自律ツール呼出し、本文取得、長時間のレート制限挙動）は未検証として記録

## 8. 既知の未処理・注意

- Hermes再起動後に `mcp_yahoo_search_*` ツールが読込されるかの実機確認（未実施）
- Yahoo利用条件の精査（§6）
- `jra.jp` と `jra.go.jp` は別ホストとして扱われる（正規化の限界。照合時は手動マージ推奨）

## 9. 提案

- **ローカル方式の継続（推奨）**: 開発PCのPoC・探索実験は本構成（stdio MCP＋独立venv）で十分。追加6回/日の規模ならレートも無問題。次は Hermes 再起動後のツール呼出し検証と、Yahoo利用条件の確認
- **K8s既存検索サービスの共通利用**: 複数人・常時運用が必要になる段階まで持ち越し。**Kubernetesへの変更は別タスク**（本PoCでは既存OpenWebUI/K8s/EVO-X2に一切触れていない）
