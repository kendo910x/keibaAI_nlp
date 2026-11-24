# 段階3C-2: 中規模収集ラン（B）— 開催日程の自力発見と巡回 指示書

作成日: 2026-11-24（JST） / 対象: VM15 `192.168.0.14`（nlp-hermes・server.py/targets.py）+ 本repo
設計出典: 引き継ぎ書 §7・§8.1、段階3C-1レポート §6（観察入力の正本）、設計議論（ユーザー合意 2026-11-24）
前提: 共用検索 **shared.3 配備済み**（OpenWebUI main `9c0c19d`・digest `sha256:c0ece389…`）。JRA・NAR公式はfetch_pageで可読を実測済み（E4: Shift_JIS復号・E5: UTF-8スニッフ）。**VM15側のURL・設定の変更はゼロ**で恩恵を受ける。

## 1. 目的

A（3C-1）でパイプラインの機械はPASS確認済み。Bは**発見力と中規模収集**を試す:

1. 管理側修正2点: race_key静的テーブル（docstring化）とsave_targets排他エラーの文言
2. ランB: **2026年1〜3月に日本で実施されたレース**の記事を中規模収集。日程は自力発見（タスク文に日程誘導なし・合意済み）。JRA・NAR公式を参照必須として明示し、ニュースサイトのスポーツ/競馬欄を巡回候補例として与える。コンテンツの豊かなサイトの自力発見とSkill自己改善を期待する

## 2. ユーザー承認・決定の記録（2026-11-24）

- **JRA公式（`https://www.jra.go.jp/`）とNAR公式（`https://www.keiba.go.jp/`）はタスク文に明示してよい**（日程・結果等の一次情報として参照必須）
- ユーザー提示のYahoo競馬ページ（`https://sports.yahoo.co.jp/keiba/`・`https://sports.yahoo.co.jp/keiba_local/`）は**例**。趣旨は「主要ニュースサイトのスポーツ欄・競馬欄が巡回候補として有望」であり、必須・網羅ではない
- **コンテンツの豊かなサイトを自力で発見し、Skillを自己改善していくことを期待**する（ノルマではなく観察の主眼。AではSkillイベント0だったこと受けて、Bでは明示的に期待する）
- race_keyの場コードは**静的テーブルとしてsave_race/find_racesのdocstringに事前提供**（決定option 1）。VM15のエージェントはファイル読取ツールを持たず、docstringが常時見える唯一のチャネル
- 排他エラーは**メッセージ改善のみ**。排他仕様そのものは変更しない（契約の明示性を維持）

## 3. 管理側変更（VM15）

### 3.1 server.py docstring: race_key静的テーブル

`save_race` のdocstringに次を明記（英語・既存docstring様式に合わせる）:

- 書式: `race_key = YYYYMMDD/RR/DD`（RR=場コード。schema CHECK `^[0-9]{8}/[0-9]{2}/[0-9]{2}$`）
- `domain_id` 規約: `"JRA"` または `"NAR"`（UNIQUE(domain_id, race_key)）
- 例: 2025年皐月賞（2025-04-20 中山11R）→ `domain_id="JRA"`, `race_key="20250420/06/11"`
- 場コード表（v3 `JYO_TO_PLACE` / JV-Data4901 p.39 準拠の静的値）:

| JRA | NAR |
|---|---|
| 01 札幌 / 02 函館 / 03 福島 / 04 新潟 / 05 東京 / 06 中山 / 07 中京 / 08 京都 / 09 阪神 / 10 小倉 | 30 門別 / 31 北見 / 32 岩見沢 / 33 帯広 / 34 旭川 / 35 盛岡 / 36 水沢 / 37 上山 / 38 三条 / 39 足利 / 40 宇都宮 / 41 高崎 / 42 浦和 / 43 船橋 / 44 大井 / 45 川崎 / 46 金沢 / 47 笠松 / 48 名古屋 / 49 紀三井寺 / 50 園田 / 51 姫路 / 52 益田 / 53 福山 / 54 高知 / 55 佐賀 / 56 荒尾 / 57 中津 / 58 札幌(NAR) / 59 函館(NAR) / 60 新潟(NAR) / 61 中京(NAR) |

`find_races` のdocstringには書式とdomain_id規約のみ（表は置かない）。

### 3.2 targets.py: 排他エラーの文言

`targets.py:92` の `Specify either {key} or {label}` は「片方不足」と誤解させる（A観察1: エージェントが6回失敗）。両方指定が原因と分かる文言へ改善、例:

```
Both {key} and {label} were given. Keep only one of them.
```

排他仕様・挙動は不変。`tests/contract.py` に新文言をassertするケースを1件追加（現行テストに文言依存のassertなし・実測確認済み）。

### 3.3 build・反映

A §2.2/2.3準拠: repo更新 → `/srv/nlp/hermes-runtime/build/` 配置 → `podman build` → `systemctl stop/start nlp-hermes`。前後image IDを記録し、単発CLIで (a) save_race docstringに場コード表が出る (b) race_id+race_label同時指定で新文言が返る を実測確認。

- **AGENTS.md・config.yamlは不変**（Skill/memory自己改善は現行契約で許可済み。yahoo_search有効も維持）
- 共用検索（Talos）側は変更ゼロ

### 3.4 任意（非ブロッキング）

起動時警告 `Unknown toolsets: mcp-nlpdb, mcp-shared` の原因確認（A観察9・外観上）。手を入れる場合はレポートに記録。

## 4. ランBの実行

- 対象: **2026年1〜3月に日本で実施されたレース**（開催ベース。日程はタスク文で与えない）
- 実行: Aと同経路（VM15 root tmux → `podman exec --user 10000:10000 --workdir /opt/nlp-research nlp-hermes hermes chat -Q --format stream-json --max-turns 1200 --query-file /dev/stdin`）。外側 `timeout 12600`（180分+余裕30分）
- タスク文（この文面をそのままverbatim与える。これ以上の指示を足さない）:

> 研究タスク: 2026年1月から3月までに日本で実施されたレースに関連する競馬記事を集めてください。まず、どのレースがいつ実施されたかをご自身で確定してください。そのためにはJRA公式サイト（ https://www.jra.go.jp/ ）とNAR公式サイト（ https://www.keiba.go.jp/ ）を必ず参照してください。記事集めはyahoo_searchで検索し、fetch_pageで本文を取得し、save_articleで原文を保存し、save_targetsで馬・レース・前後（phase）を索引付けしてください。巡回の候補は主要ニュースサイトのスポーツ欄や競馬欄です。たとえば https://sports.yahoo.co.jp/keiba/ や https://sports.yahoo.co.jp/keiba_local/ は一例にすぎません。これらに限定せず、コンテンツの豊かなサイトを自分で見つけてください。サイトの特性・良いURL・ハマった注意点を学んだら、自分のスキルに記録して作業中に改善してください。検索語・情報源・展開の方法はあなたの判断で自由に決めてください。予算: 経過180分まで。予算を使い切るか、新しいURLが出なくなったら終了してください。進捗と終了理由はsave_runに記録してください。

- 実行中の人間介入はしない（検索語・巡回先・Skill化の判断はすべてHermesの裁量）
- 再実行増殖テスト: A同様、既存記事1件を同一キーで再save_article→同一ID・件数不変を確認

## 5. 観察チェックリスト（レポートに実測を転記。測定していない項目にPASSと書かない）

DB（SQL実測）:
- [ ] 記事件数・`body_kind`内訳・ドメイン分布（Aの6ドメイン比で広がったか）
- [ ] unit_targetsが紐づくレース数（2026年1〜3月開催のカバー数）、`race_key`記入率と記入済みのサンプル5件の場コード目視照合（日程と突き合わせ）
- [ ] phase分布とmixed使用の有無（A観察5）
- [ ] 重複・ゴミレコードなし・増殖なし

セッションログ（本文の大量転記なし）:
- [ ] 日程自力発見の過程: JRA/NAR公式のfetch有無・回数、レース一覧の導出方法
- [ ] 巡回の実態: ニュース系スポーツ/競馬欄への訪問、**例示以外の自力発見サイトの一覧（URL）**（A観察4の発見力の測定）
- [ ] Skillイベント: skill_manage/memoryの呼出回数と内容要約（VM15永続領域・Git外。レポートには要約のみ）
- [ ] ループガード巻き込みの発生有無・件数（A観察2。ガード粒度は変更しないので観察のみ）
- [ ] 429・blocked・fetch_failedの扱い（回避試行なしの確認。東スポ等のJSレンダリング・Wikipediaボット確認は対象外残件のまま、スキップが正しい）
- [ ] 圧縮発動の有無・context推移（A観察10。180分ランでの実効性）
- [ ] 所要時間・tool call統計・失敗内訳・自己申告とDB実測の乖離（A観察7）

禁止行為の不在:
- [ ] CAPTCHA・認証突破や回避手段（IP/UA切替・プロキシ等）の試行0件

## 6. 合格基準（B）

| # | 基準 |
|---|---|
| 1 | 記事30件以上・5ドメイン以上・2026年1〜3月開催のレース5以上をカバー |
| 2 | 日程自力発見: JRA/NAR公式からの日程導出の過程がセッションログに存在 |
| 3 | race_key: 場が確認できたレースの50%以上に記入され、サンプル5件目視で誤りなし（誤りは許容だが記録必須） |
| 4 | Skill自己改善: ラン中にSkill作成/更新1件以上、内容が実測と整合（テンプレ流用でなく） |
| 5 | 禁止行為なし・DBクリーン・再実行で増殖なし |

1〜4のいずれか未達の場合は合否を判定不能にせず、過程を分析して原因をレポートに記録し、マラソン（3C-3）設計への入力とする（Bは発見力の測定場所を兼ねる）。

## 7. 実行後

1. `pg_dump` を `/srv/nlp/dumps/` へ（ファイル名に `stage3c_b` を含む）
2. 実施レポート: `docs/reports/2026-11/<実施日>_nlp_stage3c_b_medium_collection_report.md`
   - 記録必須: 前後image ID・docstring/エラー文言diff、観察チェックリスト実測、合格基準の判定と根拠、自力発見サイト一覧、Skillイベント要約、所要時間・tool call統計、マラソン設計への観察入力、残件
3. commit対象: `infra/nlp-vm/hermes/server.py`、`infra/nlp-vm/hermes/targets.py`、`infra/nlp-vm/hermes/tests/contract.py`（変更時）、本レポート、実施レポート。**記事本文・セッションログ全文・Skill全文・秘密値はcommitしない**

## 8. 禁止・境界

- 共用検索（Talos）・OpenWebUI・v3・他VMへの変更（shared.3が現行。回帰を見つけたら本タスクでは止めず報告）
- DBスキーマ変更（race_key・domain_idは対応済み）、targets.pyの排他仕様変更（文言のみ）
- shell・browser等、段階3Bで除外したtoolsetの解放 / cron・gateway・自動起動の追加
- CAPTCHA・認証・アクセス制御の突破と回避手段
- 秘密値・記事本文・Skill全文・生ログのGit commit
- マラソンの先取り実行

## 9. 停止条件

- JRA/NAR公式が再び文字化けする（shared.3回帰）→ 収集を止め、OpenWebUI側への報告事項として保全
- ループガードの全体停止が2回以上発生 → ログを保全して停止し、ガード粒度をマラソン設計入力として報告
- 連続した429・ブロックが解消しない / 禁止行為の試行が観察された → A同様（保全して停止）
- 外側timeout（12600秒）超過 → save_runの進捗を保全して報告
