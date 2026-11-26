# 主要媒体を広く探す入口

2026-11-26の実地調査。入口の選び方、実際に読める部分、本文を保存した経路を示す。掲載先と署名・配信元はそれぞれ記録する。

## 探し方

「競馬 ニュースサイト」「競馬 ニュース スポーツ紙」等で候補を広く見つける。ポータルの配信元表示、公式サイトの競馬面、ニュース、特集、取材、次走報等から入口を増やす。既知のサイト名だけを検索し続けない。この表は着手候補であり、許可リストでも網羅一覧でもない。個人の回顧・分析も残せる。

媒体名が見つかったこと、一覧を開けたこと、本文を読めたこと、補助コードで保存できたことは別々に記す。取得ツールの制約で開けない場合は、その経路の結果を残す。「記事がない」「媒体全体が取得不能」とは断定しない。

## 研究用MCPでたどった経路

- **馬トク報知**の[記事一覧](https://umatoku.hochi.co.jp/articles)では `.news-top-grid__item a[href*="/articles/20"], .news-list__item a[href*="/articles/20"]` で新着を拾う。事前の調整・記者取材と、引退・次走のニュースが混じる。記事の `p.article__text` をまとめて読む。スポーツナビの「馬トク報知」と同じ見出し・掲載時刻なら、配信先URLと元記事URLを結び付ける。他紙も同じ会見やJRA発表を使う場合がある。
- **ラジオNIKKEI**の[月別ニュース](https://www.radionikkei.jp/keiba_article/news/2026/11/)は年月を選ぶと `/keiba_article/news/YYYY/MM/` に移る。画面の「もっと見る」で同じ月の残りを展開する。静的HTMLにリンクがあり、VMでも `a.category-list-item-link` が使える。日付なら `li.category-list-item:has(time:-soup-contains("2026/11/22")) a.category-list-item-link`、馬・競走なら `a.category-list-item-link:-soup-contains("六甲アイランド")` のように絞る。この文字列フィルタは静的HTML用。記事には出走登録、調教後の談話、一般競走のレース後コメントがある。時刻欄が「更新」ならその表示を残す。見出しに出ない敗戦馬は競走名から本文を読む。
- **競馬ブックSmart**の[ニュース](https://s.keibabook.co.jp/news/all)では `.news_section a[href*="/news/detail/"]` が個別記事。中央・地方・海外に移り、ページ下の `a[rel=next]` をたどる。「地方」の最新記事は中央と同じ日に出たとは限らない。登録抹消・転厩など一段落の公開記事も資料に含める。有料サービスへの入口と、今回読んだ公開ニュースを区別する。
- **デイリーうま屋**の[ニュース](https://www.daily.co.jp/umaya/news/?pg=list)は当日の調教診断、[かわら版](https://www.daily.co.jp/umaya/kawaraban/?pg=list)は前週以前も含む次走・引退を拾える。どちらも `a.news-primary-main-text, a.card-primary-main-text` から `/umaya/news/年/月/日/` の公開記事へ進む。本文は `.mainTxt p.news-detail-desc`、日付は `time.date`。公開記事の私的な研究保存と二次利用の条件を分けて扱う。[同社の著作権に関する案内](https://www.daily.co.jp/company/privacy_protection.shtml)
- **スポーツナビ**の[競馬ニュース](https://sports.yahoo.co.jp/list/news/keiba?genre=keiba)で配信元を見つける。PCで日付を選んで検索し「もっと見る」を押すと、同じURLのまま別の日・次の候補に移る。引き継ぎには選択日、表示時刻、媒体名と候補URLを残す。通常の `listing(render=true)` はこのクリックまで行わない。

## ほかの入口と保存条件

| 媒体 | 試せる入口と実際の制約 |
|---|---|
| スポニチ競馬Web | [一覧](https://keiba.sponichi.co.jp/news/)のGETフォームに馬名と日付欄がある。ピコローズで16候補、先頭は前週の各馬コメント。公開本文は読めた。旧研究のリンク限定は解除。第10条の私的使用と複写・転送・改変に関する記載を併せて扱う。[利用規約](https://keiba.sponichi.co.jp/terms_of_service) |
| 日刊スポーツ | [競馬ニュース](https://www.nikkansports.com/keiba/news/)に日別の次走報、引退、追い切りが並ぶ。私的複製を認める記載と、AI利用等を目的とする収集・解析・蓄積の許諾に関する記載がある。個人の保存、LLMに渡して整理する段階、将来の学習を区別する。[著作権方針](https://www.nikkansports.com/policy/copyright.html) |
| 東スポ競馬 | [一覧](https://tospo-keiba.jp/news)は研究HTTPでは200でメニュー中心、PCの表示後DOMは403。スポーツナビの配信元に東スポ競馬を確認した。直接の本文は未確認。[利用規約](https://tospo-keiba.jp/terms) |
| スポーツ報知本紙 | [競馬タグ](https://hochi.news/tag/%E7%AB%B6%E9%A6%AC)に、馬トクと記事番号・見出しが共通する掲載がある。本紙サイトの会員規約には情報解析の条項がある。今回、掲載先URLを対応付け、本紙本文の蓄積は見送った。[本紙の規約](https://hochi.news/about/agreement/)・[馬トクの規約](https://umatoku.hochi.co.jp/info/kiyaku.html) |
| サンスポ・ZBAT! | [競馬面](https://www.sanspo.com/race/)から[ジャパンC特集](https://www.sanspo.com/race/racecard/japan-cup/)へ進めた。私的複製に触れる規定に加え、第12条(11)(12)は無許可の自動クエリや自動手段による取得・蓄積を制限する。ここでのサーバによる反復アクセスにはこの条項が関係する。[運営会社のウェブサイト利用規約](https://www.sankei-digital.co.jp/terms/)[利用規約](https://www.sanspo.com/race/zbat_terms/) |
| ウマニティ | [日付別ニュース](https://umanity.jp/racedata/news_top.php)と[過去の年別特集](https://umanity.jp/racedata/graderace/0015/2021/race_news.php)。調教、枠順、前走談話、事後談話にたどれる。同じ公式発表にも編集部署名と他社配信があるので署名・発表元を読む。独自記事の一例はWeb閲覧で読めたが、研究HTTPでは202。本文保存は見送った。[利用規約](https://umanity.jp/agreement.php) |
| 競馬ラボ・競馬のおはなし | [競馬ラボ](https://www.keibalab.jp/topics/backnumber.html)で過去一覧の2ページ目と騎手・コース分析の公開記事を確認。[競馬のおはなし](https://keibana.com/news/)も2ページ目へ移れる。旧コード・私有設定による一律リンク限定は解除した。公開部分を本人用に整理する。[競馬ラボ利用規約](https://www.keibalab.jp/info/agreement.html) |
| 中日スポーツ | [競馬面](https://www.chunichi.co.jp/chuspo/race/horse)に月別と「次の11件」がある。調教・関係者談の公開部分を読めた。中日新聞プラスの情報解析条項と競馬面への適用範囲を区別し、今回は本文保存を見送った。[著作物利用](https://www.chunichi.co.jp/info/copyrights)・[会員規約](https://www.chunichi.co.jp/service/page/agreement/) |
| netkeiba・JRA | [netkeiba](https://news.netkeiba.com/?pid=news_backnumber)の馬名検索、[JRA](https://www.jra.go.jp/news/202611/index.html)の月別ニュースは従来の導線。地方を広げる場合は[地方競馬全国協会](https://www.keiba.go.jp/)の公式発表と取材記事を区別する。 |

保存方針・利用条件、ツール自身の拒否、実際のHTTP応答、公開本文の抽出漏れを区別する。独自のrobots事前拒否は撤廃済み。未発見や拒否を観測したら入口と日付を残し、ほかの取材を探せる。

本人による公開記事の保存・閲覧を扱う。旧私有設定のスポーツブル、千葉テレビを含め、一般的な転載禁止を理由に私的な保存を除外しない。公開範囲・取得応答は実際の操作で扱う。文化庁は私的使用でのRAG等の複製と第30条との関係を説明している。[文化庁FAQ 6－⑲](https://www.bunka.go.jp/seisaku/bunka_gyosei/kibankyoka/faq/index.html)
