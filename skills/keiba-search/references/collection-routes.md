# 媒体の一覧と馬名を組み合わせる

2026年11月26日に日本語の公開画面で辿った経路。表示と利用条件は再訪時のものを使う。競馬の言葉を広く集め、九割がた役立つことを目安に、名簿にない馬、開催前の予定、矛盾や未確定の日付も残す。

## 名簿を選ぶ

- 特別登録は [競馬ラボのジャパンC登録馬](https://www.keibalab.jp/db/race/202611290512/tokubetsu.html?kind=simple) の「簡易版」などで馬名欄を読む。`.tkbttable tbody tr td:first-child` は外国馬の名前だけのセルも含む。馬DBへのリンクに限定すると18頭から12頭に減った。登録後に回避が分かっても、それまでの記事は保持する。
- 11/28東京2Rは木曜14時台の取材想定が3頭、16時03分のJRA公表出馬表は馬番が空欄で15頭。JRAの「競馬メニュー → 出馬表 → 当該開催 → 当該Rの出馬表」とたどる。開催の一覧にある実際のリンクを開き、`td.horse .name` の名前を使う。同じ18頭がそろったジャパンC、登録21頭のうち18頭が公表されたキャピタルSのように、競走によって差分は異なる。媒体の `(外)` は表示用に残して比べる。出馬表が結果に変わったあとも、競馬ラボの「簡易出馬表」では11/21京都2Rの13頭を確認できた。[東京2Rの公式出馬表](https://www.jra.go.jp/JRADB/accessD.html?CNAME=pw01dde0105202605070220261128/BB)・[同じ競走のnetkeiba出馬表](https://race.netkeiba.com/race/shutuba.html?race_id=202605050702)・[京都2Rの簡易出馬表](https://www.keibalab.jp/db/race/202611210802/syutsuba.html)
- 事後は実際の着順表を使える。JRAのマイルCSでは馬名は `table.striped tbody tr td:nth-of-type(4)`。過去は `seeds("history-jra", name="タンタラス", year="2021")` のように既存のJRA出走履歴から活動年も引ける。名簿内の同名は元の馬IDと期間を残す。[マイルCSの公式結果](https://www.jra.go.jp/datafile/seiseki/g1/mile/result/mile2026.html)
- 出走回数の少ない馬では馬名でニュースが出ないこともある。フロールネイジは媒体内の馬名検索で0件。出走歴から同走馬ビップキャッツアイを取り、2017年1月21日・京都新馬を合わせると、当日の騎手談に届いた。起点にした馬自身の発言としては扱わず、同じ競走の資料として保存できる。[当日の談話](https://news.netkeiba.com/?pid=news_view&no=118342)

## 記事を増やせた入口

| 媒体・入口 | 操作と使い分け |
|---|---|
| [netkeibaのニュース一覧](https://news.netkeiba.com/?pid=news_backnumber) | 「中央競馬」または「記事から検索」を使う。馬名検索は公開フォームの `pid=news_search`、`keyword=馬名`。通常のブラウザーで表示後、`#NewsBacknumberList a[href*="news_view"]` と `#NewsBacknumberList a[title="次へ"]` を読む。静的HTMLでは枠だけが返った。タンタラスは20、20、18件の3ページ。「馬名＋年」の結果には別年・別馬の記事も出た。活動年と掲載日を見て、競走の正式名と開催日が分かれば外部検索でも絞れる。 |
| [タンタラスの馬ページ](https://db.netkeiba.com/horse/2016104835/) | 記事本文の馬名から馬ページへ。「netkeibaニュース」の短い一覧の「もっと見る」は馬名検索につながる。馬ページの直近分が繁殖・産駒の話でも、先のページには現役時の取材がある。本文内の比較相手や `.RelatedContentsList a[href*="news_view"]` は別の起点になる。 |
| [JRA月別ニュース](https://www.jra.go.jp/news/202611/index.html)・[ジャパンC特集](https://www.jra.go.jp/keiba/g1/jc.html) | 静的HTMLから日ごとの `#date_25 li.race .news_line a` 等を辿る。日別には故障、引退、次走、外国馬の調教が混在する。特集では `#contents a[href^="/news/2026"]` が日別取材への別の入口。月・年は実際のリンクから選び直す。結果へのリンクにはレース叙述と成績表が同居する。 |
| [山口吉野の回顧一覧](https://www.yamaguchi-yoshino.com/archive/category/%E5%9B%9E%E9%A1%A7) | `a.entry-title-link` と `.pager-next a` で各30件のページを辿れた。公開の検索欄は `/search?q=馬名`。シックスペンスではマイルCSと安田記念を含む11件。記事内の関連リンクや前後の記事も辿れる。筆者の解釈と騎手・調教師の談話を区別する。 |
| [スポニチ競馬Web](https://keiba.sponichi.co.jp/news/)・[ジャパンC特集](https://keiba.sponichi.co.jp/feature/horseracing/G1/japanc/2026) | キーワードと日付は別の入口。日付選択で22日→OK→検索を操作すると `/news/2026/11/22?search=&date=2026%2F11%2F22` が開いた。トップに `?date=...` だけを足すと新着が残った。研究保存先では同サイトを見出し・リンクのみとし、本文の複写・転送に関する規約を引き継いだ。[利用規約第10条](https://keiba.sponichi.co.jp/terms_of_service) |
| [競馬ラボのニュース](https://www.keibalab.jp/topics/backnumber.html) | 一覧の `#topicsTab .tabList li > a[href^="/topics/"]` から50リンク。条件戦馬を含む2歳馬情報やコラムも見つかる。ニュース本文は記録対象をリンク・見出しに留め、出馬表からは馬名等の事実を読む。[利用規約・著作権表示](https://www.keibalab.jp/info/agreement.html) |
| [競馬のおはなし](https://keibana.com/) | 外部検索で同じ見出しの配信が複数見つかったら、署名・配信元を確認して元の媒体の検索欄を使う。ここでは `/?s=馬名` を開き、静的HTMLの `main .head a[href*="/news/"]` に記事リンクがある。京都2Rの1着馬・2着馬は各1件で同じ記事に届いた。検証した範囲はリンク・配信関係。[元の競走記事](https://keibana.com/news/143805/) |

## 続きから収集する

1. `listing(subject, url, selector, next_selector)` で取得経路と実際の候補を保存する。`render=true` はPlaywrightとEdgeのあるPC用。静的HTMLでゼロ件なら、表示待ちの枠、該当なし、取得拒否を区別する。日刊スポーツのニュースは今回robotsで対象外だった。[日刊スポーツのアクセス方針](https://www.nikkansports.com/robots.txt)
2. `collect(listing_id, offset, limit)` は0始まりの範囲を保存し、次のoffsetと残件を返す。既知のURLはその取得IDを返す。ある一覧を深掘りする途中でも、別の馬や期間へ移れる。新着順のページは並びが変わるため、再訪時は入口を新たに観測し、前回中断した固定の候補群には保存済み一覧IDを使う。
3. 公開範囲に本文があればモデルを経由せず保存する。見出しだけ、表だけ、本文欄が「…」のみの場合は取得できた記事数から分ける。重い意味解釈は後回しにできる。次の担当へ名簿名、一覧ID、続きのoffset、手掛かりとなった馬・記事、未探索の方向を渡す。
4. netkeibaで公開部分の直後に会員向けの「続きを読む」が付く場合は、読めた文章を `partial` として扱う。429・503で中断した場合は返された `retry_after` と保存済みoffsetを引き継ぐ。PCで候補を表示して保存すれば、ブラウザーのないHermes環境でも同じ一覧IDの続きから本文を取得できる。
