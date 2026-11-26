# 主要な競馬媒体の発見と記事収集

2026年11月26日（JST）。指示書を収録した `origin/main` の `af488f9` を開始版とし、Windowsの研究環境とVM15の研究用Hermesで実施した。本文抽出と検索・統括Skillの更新は `ff150cc`。[研究指示書](../../instructions/2026-11/2026-11-26_nlp_major_media_discovery_instruction.md)・[実装とSkillのコミット](https://github.com/kendo910x/keibaAI_nlp/commit/ff150ccce16012b548fc3fa9a231aa88ff22847f)

**4掲載先から公開本文を148 URL・148版、新規保存した。累計は599 URL・600版。** 前回は新規426 URLのうち334 URLがnetkeiba掲載だった。今回は馬トク報知、デイリー、競馬ブックSmart、ラジオNIKKEIの各掲載先で本文を直接取得した。同じ発表や会見を伝える記事も含む。[前回の集計](2026-11-26_nlp_collection_routes_horse_seeds_report.md)

## 本文を保存した媒体

| 掲載先 | 新規URL | 入口と、実際に本文で読めた内容 |
|---|---:|---|
| ラジオNIKKEI | 62 | 月別一覧に出走登録、調教、一般競走からGIまでのレース後談話がある。11月22日で絞ると京都の花見小路特別や東京の新馬戦も見つかった。2021年12月を選ぶと最初の10件から「もっと見る」で311件が表示された。静的HTMLにも同じ311候補があり、VMで年月を替えられる。[月別一覧](https://www.radionikkei.jp/keiba_article/news/2026/11/)・[花見小路特別](https://www.radionikkei.jp/keiba_article/news/post_39112.html) |
| 競馬ブックSmart | 40 | 全ニュースの1・2ページ目と地方欄をたどった。ココナッツブラウンの引退のような短報、海外競走、地方の騎手・調教師の節目を取得。地方欄の先頭は10月の記事で、欄によって新着の間隔が違う。[全ニュース](https://s.keibabook.co.jp/news/all)・[地方欄](https://s.keibabook.co.jp/news/chihou)・[引退短報](https://s.keibabook.co.jp/news/detail/80612) |
| 馬トク報知 | 27 | 新着からジャパンC当週の外国馬取材、海外競馬タグからマイルCS後の香港遠征予定に到達。実出走馬ピコローズの検索では、シックスペンスが見出しになった11月22日の各陣営コメントに同馬の言及があった。[新着](https://umatoku.hochi.co.jp/articles)・[各陣営コメント](https://umatoku.hochi.co.jp/articles/20261122-OHT1T51265.html)・[香港招待の続報](https://umatoku.hochi.co.jp/articles/20261125-OHT1T51226.html) |
| デイリーうま屋 | 19 | ニュース欄10件と「かわら版」9件。追い切りの負荷や調整への評価に加え、ジョバンニの香港C招待受諾や、エリザベス女王杯後の引退・次走報を読めた。[ニュース](https://www.daily.co.jp/umaya/news/?pg=list)・[かわら版](https://www.daily.co.jp/umaya/kawaraban/?pg=list)・[調教取材](https://www.daily.co.jp/umaya/news/2026/11/26/0021073227.shtml) |

4媒体について、本文・見出し・日時のHTML要素を研究コードに追加した。馬トクとデイリーは本文段落だけをつなぎ、競馬ブックはニュース本文欄を取る。ラジオNIKKEIの日時欄が「更新」ならそのまま保存する。最終コードで各媒体から1件ずつ再取得し、4件とも保存済みの見出し・日時・本文版IDと一致した。私的使用に関する各社の案内を確認し、公開部分の原文は私有研究領域に置いた。[報知](https://www.hochi.co.jp/policy/)・[デイリー](https://www.daily.co.jp/company/privacy_protection.shtml)・[競馬ブック](https://s.keibabook.co.jp/entry/kiyaku)・[ラジオNIKKEI](https://www.radionikkei.jp/copyright/)

## 広く見つけた入口と本文を保存しなかった理由

「競馬 ニュースサイト」「競馬 ニュース スポーツ紙」等の一般検索から始め、ポータルの配信元と媒体自身の一覧を開いた。以下は今回の経路ごとの観測。

| 媒体 | 一覧・個別記事で確かめたこと | 今回の本文保存 |
|---|---|---|
| スポニチ競馬Web | 新着では兵庫ジュニアグランプリの勝者を扱った公開本文を実読。キーワード欄の「ピコローズ」からは前週の各馬コメントを含む16候補。[ニュース](https://keiba.sponichi.co.jp/news/)・[地方重賞の記事](https://keiba.sponichi.co.jp/news/20261126s00004049361000c) | 既存の `links_only` と私有方針により `metadata_only`。実読できた記事の取得記録にも本文は入っていない。[利用規約](https://keiba.sponichi.co.jp/terms_of_service) |
| 日刊スポーツ | 日別の新着・次走・引退の見出しを研究HTTPで確認。2024年記事の実読は指示書作成時の観測。[競馬ニュース](https://www.nikkansports.com/keiba/news/) | 情報解析・AI利用目的の収集や蓄積等に関する条件を確認し、今回の本文取得を見送った。[著作権方針](https://www.nikkansports.com/policy/copyright.html) |
| 東スポ競馬 | 静的HTTPは200でメニュー中心。PCのEdgeでニュース一覧を開くと403。スポーツナビには東スポ競馬名義の配信があった。[ニュース一覧](https://tospo-keiba.jp/news) | 直接の公開本文は未確認。403でその経路を終了した。[利用規約](https://tospo-keiba.jp/terms) |
| スポーツ報知本紙 | 競馬タグから馬トクと同じ記事番号・見出しの公開記事へ到達した。記事冒頭を確認。[本紙の競馬面](https://hochi.news/tag/%E7%AB%B6%E9%A6%AC) | 本紙の会員規約に情報解析条項があるため、掲載先URLを対応付けた。上表の27件は別サービスの馬トクで保存した。[本紙の規約](https://hochi.news/about/agreement/)・[馬トクの規約](https://umatoku.hochi.co.jp/info/kiyaku.html) |
| サンスポ・ZBAT! | 競馬面とジャパンC特集は研究HTTPで開き、枠順・馬体重の個別記事リンクを確認。[競馬面](https://www.sanspo.com/race/)・[特集](https://www.sanspo.com/race/racecard/japan-cup/) | 利用規約の情報解析・自動取得に関する条項を確認し、一覧までとした。[利用規約](https://www.sanspo.com/race/zbat_terms/) |
| スポーツナビ | 11月22日を選んで検索すると同じURLのまま20件が当日分に替わり、「もっと見る」で40件に増えた。配信元・時刻・記事URLを記録。[競馬ニュース](https://sports.yahoo.co.jp/list/news/keiba?genre=keiba) | 配信元を発見し、同一取材を対応付ける経路に使った。配信先での本文保存は0件。 |
| ウマニティ | 日付フォームと2021年ジャパンC特集を確認。Web閲覧では編集部名義の馬体重記事を実読。同じJRA発表には他社配信もある。[年別特集](https://umanity.jp/racedata/graderace/0015/2021/race_news.php)・[編集部の記事](https://umanity.jp/racedata/race_newsdet.php?nid=11881923) | 編集部記事の研究HTTPは202。媒体の複製条件も考慮して本文は保存していない。[利用規約](https://umanity.jp/agreement.php) |
| 競馬ラボ・競馬のおはなし | 両方の一覧で2ページ目に到達。競馬ラボは騎手とコースを扱う個別記事も読めた。[競馬ラボ](https://www.keibalab.jp/topics/backnumber.html)・[公開記事](https://www.keibalab.jp/topics/46763/)・[競馬のおはなしの2ページ目](https://keibana.com/news/page/2/) | 競馬ラボはコードで `metadata_only` を確認。競馬のおはなしは既存の私有方針でリンクを記録。[競馬ラボ利用規約](https://www.keibalab.jp/info/agreement.html) |
| 中日スポーツ | 一般検索と配信元表示から追加。正しい競馬面には月別と「次の11件」があり、ダブルハートボンドの調整を伝える公開本文を読めた。[競馬面](https://www.chunichi.co.jp/chuspo/race/horse)・[調整記事](https://www.chunichi.co.jp/article/1345016) | 中日新聞プラスの情報解析条項がこの競馬面にも適用されるかは未確認。今回は本文保存を見送った。[著作物利用](https://www.chunichi.co.jp/info/copyrights)・[会員規約](https://www.chunichi.co.jp/service/page/agreement/) |

地方競馬全国協会の公式入口も確認した。JRA-VANは一般検索で見つかったPC記事一覧でTLS接続が終了し、本文は未確認。京都2Rの実出走馬ポッドベローチェを日付・取材語と合わせて探した際は、検索した候補から同馬の個別取材を確認できず、そこで次へ進んだ。[地方競馬全国協会](https://www.keiba.go.jp/)・[JRA-VANの候補](https://app.jra-van.jp/PCWeb/Article0001.do?disp=all&service=web)

## 取材の重複と過去の馬名

カランダガンの11月26日19時の調教記事は馬トク、報知本紙、スポーツナビ経由のYahoo!ニュースで対応する。馬トクと本紙は記事番号、配信先は見出し・配信元・時刻で結び付け、3掲載先のURLを私有記録に残した。保存本文は馬トクの1件。同じ発表に基づく別記事もあり、掲載URL数を証言数には使えない。[馬トクの原掲載](https://umatoku.hochi.co.jp/articles/20261126-OHT1T51281.html)・[本紙掲載](https://hochi.news/articles/20261126-OHT1T51281.html)・[配信先](https://news.yahoo.co.jp/articles/a92643367f1919dd8d4f2eb7b57bd0731eaeb5c9)

過去のJRA出走履歴では「タンタラス」の部分一致に別馬も出た。馬名と活動年を見て2021年12月の一覧を絞ると、馬名・六甲アイランドSのどちらからも同じ1記事に到達し、2回目は既知URLを再利用した。大まかな分類で収集を進め、個々の発言が当時の予測に使えたかの検証は別工程に残した。[2021年のレース後記事](https://www.radionikkei.jp/keiba_article/news/post_25333.html)

## Hermesによる自力発見と引き継ぎ

| 渡したもの | Hermesの操作と、私有研究領域で照合した結果 |
|---|---|
| 活動馬トウカイオラージュと2020年2月15日・雲雀Sの手掛かり | 名簿とSkillを読み、自分で開いた月別一覧は267候補。馬名で絞ると0件、競走名で1件。勝者名が見出しの本文を保存し、同馬が3着だったことを確認した。[雲雀S](https://www.radionikkei.jp/keiba_article/news/post_20069.html) |
| 2022年4月10日の桜花賞と候補馬2頭 | 別セッションで名簿を照合しスターズオンアースを選択。PCで候補化していない4月の一覧で桜花賞に絞り、調整から当日までの16記事を新規保存。勝者と2着ウォーターナビレラの騎手談を本文で確認。別途試したJRA月別一覧はVMから403だった。[桜花賞](https://www.radionikkei.jp/keiba_article/news/i_8.html) |
| PCで固定した競馬ブックの一覧IDとoffset 12 | 3件を新規保存し、北海道競馬の発売金額の記事を読み、次のoffset 15を返した。この3件と自力発見17件を合わせてHermesの新規本文は20件。 |

PCの既存PlaywrightとEdgeで年月選択・日付検索・追加表示を実操作した。VMでは静的な受領HTMLに月別リンクがあるため、研究MCPの `listing` で新規探索できた。既存の `listing(render=true)` は表示後DOMを抽出する。クリックや選択を汎用化するならMicrosoftのPlaywright MCPも候補だが、今回繰り返せた操作には既存ライブラリで足りた。VMへのブラウザー導入や汎用ブラウザーMCPの導入は行っていない。[Playwright MCP](https://github.com/microsoft/playwright-mcp)

## 集計・再開

次の収集では、VMで当週の馬トク・うま屋の新着、競馬ブックの地方欄、過去のラジオNIKKEI月別を選べる。新しい配信元の発見にはPCのスポーツナビ日付検索を使い、選択日・媒体名・候補URLを引き渡す。通常DBへの接続と定期実行は別の作業として残る。

- 基準の451 URL・452版に対する差分を、本文のある正規化済み最終URLと版IDで数えた。新規はCodex 128 URL、Hermes 20 URL。候補台帳には一覧21観測と共用検索9観測があり、重複を除くと1,170候補URL。本文取得記録は148件が本文あり、2件が `metadata_only`。累計600版のうち独立解釈済み13版、未解釈587版。今回の本文取得と独立推論は別々に再開できる。
- PCの保管先は `%LOCALAPPDATA%\keiba-nlp-review\collection-routes-20261126`。同階層の `captures`、`listings`、`batches` を使う。今回の基準・集計・出典対応・ブラウザー観測・Hermesの実行記録はその下の `major-media-20261126`。再開案内は `handoff-major.md`、今回の復元用アーカイブは `resume-major-media.tar.gz`。
- VM15の研究プロファイル `/var/tmp/keiba-routes-20261126` と `/var/tmp/keiba-search-20261126` の両方で、作業規約、複製した `references/work-rules.md`、検索・統括Skill、収集コードを更新した。現行の導線研究データは前者の `data` にある。PCとVMで、競馬ブックの一覧 `b2a41ffed3c144aa8f74d45c4588dfc6` はoffset 15（残り5件）、ラジオNIKKEIの2021年12月 `c1757b60dfe249d69660c790dc07a3de` はoffset 13（残り298件）から再開できる。
- 復元用アーカイブのSHA-256は `9432ed40532e7281fd8a7c8200c331725b4a6cb00e2b3304ee98b34c35aece94`。導線研究プロファイルの925ファイルを照合し、VM上で保存済みの桜花賞記事を読み戻した。通常プロファイルの設定ファイルとSOULのハッシュは実行前後で一致した。
- 検索・統括Skillの形式、4媒体の実記事と本文版、従来のnetkeiba公開部分・JRA結果ページの抽出、メタデータ限定経路を検証した。通常DB、v3、定期運用への変更は行っていない。速度や全件の意味精度は評価していない。[検索Skillの媒体別手引き](../../../skills/keiba-search/references/media-discovery.md)
