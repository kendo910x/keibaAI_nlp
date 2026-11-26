# 主要媒体を広く探す入口

2026-11-26に、広いWeb検索と公開ページの閲覧で確認した初歩の地図。研究用コードで全媒体の本文を保存した実績ではない。netkeibaでの件数増加と、主要媒体の基礎調査の完了を混同しない。

## 探し方

「競馬 ニュースサイト」「競馬 ニュース スポーツ紙」等で候補を広く見つける。ポータルの配信元表示、公式サイトの競馬面、ニュース、特集、取材、次走報等から入口を増やす。既知のサイト名だけを検索し続けない。この表は着手候補であり、許可リストでも網羅一覧でもない。個人の回顧・分析も残せる。

媒体名が見つかったこと、一覧を開けたこと、本文を読めたこと、補助コードで保存できたことは別々に記す。取得ツールの制約で開けない場合は、その経路の結果を残す。「記事がない」「媒体全体が取得不能」とは断定しない。

## 入口と今回確認した範囲

| 媒体 | 入口・用途 | 今回の閲覧で確認したこと／残ること |
|---|---|---|
| スポーツナビ | [競馬ニュース一覧](https://sports.yahoo.co.jp/list/news/keiba?genre=keiba) | 複数媒体の配信元・日時付き見出し、全1,000件という表示、追加表示の入口。1,000件を取得した意味ではない。記事の遷移先や配信元を個別に確かめる |
| スポニチ競馬Web | [ニュース一覧](https://keiba.sponichi.co.jp/news/) | 日付・キーワード検索欄、新着、特集の入口。[当週の調教記事](https://keiba.sponichi.co.jp/news/20261126s00004048027000c)は公開本文を読めた。研究コードにはrobotsと別のmetadata-only設定が残っており、本文保存済みとは扱わない |
| 日刊スポーツ | [競馬ニュース一覧](https://www.nikkansports.com/keiba/news/) | 日別見出しと、GI以外を含む次走・有力馬情報。[2024年記事](https://www.nikkansports.com/keiba/news/202404270000975.html)の公開本文も読めた。内部検索・過去一覧の実操作は追加調査 |
| デイリー・うま屋 | [ニュース](https://www.daily.co.jp/umaya/news/) | ニュース・コラムの一覧と記事へのリンク。[当週の調教記事](https://www.daily.co.jp/umaya/news/2026/11/26/0021073227.shtml)で本文と調教診断を確認。次走報・馬体診断等の別入口も調べる |
| 東スポ競馬 | [ニュース一覧](https://tospo-keiba.jp/news) | 検索インデックスでは記事候補が見えるが、今回のWeb抽出はメニュー中心。一覧の表示後DOM、検索、ページ送りは未確認であり、既存ブラウザー手段が使える場面で調べる |
| スポーツ報知・馬トク | [馬トク](https://umatoku.hochi.co.jp/) | 公式入口とスポーツナビの配信元表示を確認。今回のWeb取得ツールは直接閲覧を拒否した。内部導線と本文は未確認 |
| サンスポ・ZBAT! | [競馬入口](https://www.sanspo.com/race/) | 本体は今回のWeb取得ツールが拒否。ウマニティ等でサンケイスポーツの配信表示を確認。本体の導線と配信先を区別して調べる |
| ウマニティ | [中央競馬ニュース](https://umanity.jp/racedata/news_top.php)・[ニュース一覧](https://umanity.jp/racedata/race_newslist.php) | サンスポ配信と独自記事。[2021年ジャパンC特集](https://umanity.jp/racedata/graderace/0015/2021/race_news.php)に事前調教・枠順・前走談話・事後談話が日付付きでまとまる。[当時の陣営談話](https://umanity.jp/racedata/race_newsdet.php?nid=11678673)の本文も確認 |
| 競馬ラボ | [ニュース一覧](https://www.keibalab.jp/topics/backnumber.html) | 先行研究に一覧・名簿の到達記録がある。今回のWeb直接取得は403。既存のmetadata-only方針と今回のHTTP結果は別。取得経路を添えて扱う |
| 競馬ブック | [Web](https://p.keibabook.co.jp/)・[Smart](https://s.keibabook.co.jp/) | 専門紙サービスの候補。今回のWeb取得は403で公開記事の範囲は未確認。存在確認だけで本文収集可能とはしない |
| ラジオNIKKEI | [競馬実況web](https://www.radionikkei.jp/keiba/)・[2026年11月ニュース](https://www.radionikkei.jp/keiba_article/news/2026/11/) | 月別一覧から[ダノンデサイルの調教師談話](https://www.radionikkei.jp/keiba_article/news/c_271.html)の本文へ到達。前走・調整・追い切り等の取材が詳しい。別の年月の選択も調べる |
| netkeiba・JRA | [netkeibaニュース](https://news.netkeiba.com/?pid=news_backnumber)・[JRA月別ニュース](https://www.jra.go.jp/news/202611/index.html) | 先行研究の名簿・一覧・特集・馬名検索を再利用し、他媒体との配信関係や記事内容の違いも見る |

同じ取材の配信先が複数あっても、独立した証言の数にはしない。保存URLは各出典として残せる。新着巡回には日別・カテゴリ別の一覧、過去発掘には年・レース別特集、馬名検索、過去記事の関連リンク等を使い分ける。

NLP補助コードによる独自robots事前拒否は撤廃された。上表の外部Web取得ツール自身の拒否は別の観測であり、補助コードの変更で解除したものではない。過去のrobots判定を恒久的な媒体除外へ転記しない。
