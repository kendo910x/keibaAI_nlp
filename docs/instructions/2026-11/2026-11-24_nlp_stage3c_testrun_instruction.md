# 段階3C-1: Yahoo検索の有効化とHermes自律収集テストラン 指示書

作成日: 2026-11-24（JST） / 対象: VM15 `192.168.0.14`（nlp-hermes・設定・固定契約）+ 本repo
設計出典: 引き継ぎ書 `docs/handoffs/2026-11/2026-11-24_stage3b_completed_handover.md` §7・§8.1

## 1. 目的

(1) Hermes通常profileで **yahoo_searchを有効化**し、(2) 対象を1レースに絞った**テストラン**でHermesの自律収集能力と探索方向性を確認する。テストラン合格後、別指示書で無制限マラソン収集（段階3C-2）へ進む。本指示書はマラソン開始の承認ではない。

## 2. ユーザー承認の記録（2026-11-24 明示決定）

- **Yahoo検索を自己規制なしで有効化する**。OpenWebUI・Hermesを問わず既存の共用yahoo_searchの利用を承認する
- 遵守条件は次の2点のみ:
  1. **429を尊重し、受信時は待機する**（共用ゲート・Retry-After・cooldown・`retryable_at` の既存実装がこれに対応。追加の自己制限は設けない）
  2. **CAPTCHA・認証・アクセス制御の突破を試みない**（Yahooに限らない。回避用のIP/UA切替・プロキシ等も禁止）
- 実記事の収集・DB保存も本指示書で承認する（固定契約の "future authorization" に該当）
- 将来の目標状態: 期限・量・格の制限なく競馬関連記事を可能な限り収集（G1/重賞限定なし）。本テストランはその前段の能力確認であり、この目標自体はマラソン指示書でタスク化する

## 3. 管理側変更（VM15）

1. `/srv/nlp/hermes-runtime/config.yaml`: `mcp_servers.shared.tools.include` を `[fetch_page, yahoo_search]` に変更
2. 固定契約 `/opt/nlp-research/AGENTS.md` を更新（repo `infra/nlp-vm/hermes/AGENTS.md` と同期）。変更方針:
   - 「Live Yahoo search and collection of real articles require a future authorization」→「Yahoo検索は承認済み（2026-11-24）。429/Retry-After/cooldownを尊重し、CAPTCHA・認証・アクセス制御の突破と回避手段を用いない」に置換
   - 「Respect site access rules, robots, copyright and permitted storage」の包括表現は、上記2条件と矛盾する自己規制として削除し、上記2条件のみを残す
   - 他文（原文先行保存・索引付け・Skill自己改善許可等）は不変
3. `systemctl stop/start nlp-hermes`（単一ファイルbindの反映規則どおり）→ CLI起動してツール一覧に `yahoo_search` が出ることを確認
4. 共用検索側（Talos）の変更は**行わない**（30081公開・ゲートは現行のままで成立）

## 4. テストラン実行

- 対象: **2025年皐月賞（2025-04-20 中山）**（PoC 24件との比較材料がある。変更可）
- 実行: README準拠の単発CLI（`hermes chat -Q --max-turns <十分大きな値> -q "<タスク文>"`）。SSHセッションは切断に備え `tmux`/`screen` 推奨（VM15に既存ツールがあれば。無ければ新規導入せず素のSSHで実行し、切断時は再開手順どおり save_run から再開してよい）
- タスク文（この文面をそのまま与える。これ以上の指示を足さない）:

> 研究タスク: 2025年皐月賞（2025年4月20日 中山）に関連する競馬記事を集めてください。yahoo_searchで検索し、fetch_pageで本文を取得し、save_articleで原文を保存し、save_targetsで馬・レース・前後（phase）を索引付けしてください。検索語・情報源・展開の方法はあなたの判断で自由に決めてください。予算: 経過60分・yahoo_search 30回・fetch_page 60回まで。予算を使い切るか、新しいURLが出なくなったら終了してください。進捗と終了理由はsave_runに記録してください。

- 実行中の人間介入はしない（Skill作成・検索語の組み替え・方向転換を含む判断はすべてHermesの裁量）

## 5. 観察チェックリスト（レポートに実測を転記。測定していない項目にPASSと書かない）

DB（SQLで実測）:
- [ ] articles保存件数と `body_kind` 内訳（full/excerpt/snippet/none）
- [ ] source_urlのドメイン分布（**3ドメイン以上**が方向性OKの目安）
- [ ] unit_targets の phase 分布と、馬・レース索引のサンプル10件の妥当性（人間が目視。誤分類は許容範囲か）
- [ ] 重複・ゴミレコードなし（一意制約で増殖していない）
- [ ] collection_runs に進捗・終了理由が記録されている

セッションログ（人間が読める形に保存。記事本文の大量転記はしない）:
- [ ] 検索語の組替えが確認できる（同一検索語の繰り返しだけでない）
- [ ] 検索結果からの追加展開（記事内の手掛かり・別媒体への移動等）
- [ ] 429・blocked・fetch_failed の扱い（あれば。連打・回避試行がないこと）
- [ ] Skill作成/更新イベントの有無（有無どちらもあり。ノルマにしない）
- [ ] 圧縮発動の有無・context推移
- [ ] 所要時間・tool call数・失敗した呼出の内訳

禁止行為の不在:
- [ ] CAPTCHA・認証突破や回避手段の試行が0件

## 6. 合格基準（方向性OKの判断）

次を**目安**として判定し、数値不足でも判断根拠をレポートに書く（機械的合否で打ち切らない）:
- full取得が複数件、複数ドメインから存在する
- 索引付けされた馬・レース・phaseのサンプルが概ね妥当（完全である必要はない）
- 検索語の組替えと情報源の展開が観察される
- 禁止行為なし・DB状態がクリーン

## 7. 実行後

1. `pg_dump` を `/srv/nlp/dumps/` へ（マラソン前の保険。バックアップ設計自体は段階4）
2. 実施レポート: `docs/reports/2026-11/2026-11-24_nlp_stage3c_testrun_report.md`
   - 記録必須: 変更した設定・契約diff、ツール一覧確認、観察チェックリスト実測、保存件数内訳、Skill差分、所要時間・tool call統計、方向性の判定と根拠、残件
3. 対象ファイルのみ commit/push（`infra/nlp-vm/hermes/` の契約・config更新、レポート）。**記事本文・セッションログ全文はcommitしない**

## 8. 禁止・境界

- 共用検索（Talos）・OpenWebUI・v3・他VMへの変更
- shell・browser・一般web等、段階3Bで除外したtoolsetの解放（テストランで不足が実測されてから別指示で判断）
- cron・gateway・自動起動の追加（マラソン起動方式は3C-2で設計）
- CAPTCHA/認証/アクセス制御の突破・回避手段（IP/UA切替・プロキシ等）
- 秘密値・記事本文のGit commit

## 9. 停止条件

- yahoo_search有効化後にツール一覧へ出ない、または実呼出が技術的に失敗する（設定・ログを報告）
- 共用検索から連続した429・ブロックが解消しない（ゲート動作を確認し、連打がないことを確認して停止・報告）
- Hermesの起動・圧縮・永続化に段階3Bの想定外の不具合（ログを保存して停止）
- 禁止行為の試行が観察された（即時Ctrl-Cで中断し、ログを保全して報告）
