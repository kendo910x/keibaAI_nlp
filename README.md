# keibaAI_nlp

競馬記事を本人が私的に複製・保存・閲覧・整理するためのプロジェクト。共通作業規約は[AGENTS.md](AGENTS.md)。収集データからのモデル作成・学習は未定です。

## 現在の作業

次の作業は、保存済みの検証用2,438本文版へ採用済みSkillを適用し、馬別一覧で読める資料を増やす有限解釈です。既存6版を再利用し、残り2,432版を処理する想定です。今回の更新は指示書・関連Markdownの作成のみで、実機の処理は起動していません。Codexが新しい固定対象の計画を作って実行します。新規収集と本番開始は含みません。

VM15に改訂版の3つのSkillと馬別一覧を配備しました。保存記事6件を同じLocal LLMで実生成したところ、解釈時間の合計は旧版の1,827.51秒から新版の218.84秒になりました。検証Dashboardで6記事・24件の新しい馬別要約を読めます。[馬名から要約を読む](http://192.168.0.14:8787/horses)

- [最新のCodex指示書：保存済み検証記事の有限解釈・馬別閲覧](docs/instructions/2026-11/2026-11-27_nlp_saved_articles_interpretation_instruction.md)
- [前回のCodex指示書：改訂Skillの配備・馬別要約・解釈時間の比較検証](docs/instructions/2026-11/2026-11-27_nlp_summary_skills_validation_instruction.md)
- [完了した6記事の実機検証レポート](docs/reports/2026-11/2026-11-27_nlp_summary_skills_validation_report.md)
- [馬別一覧の実装レポート](docs/reports/2026-11/2026-11-27_nlp_horse_summary_implementation_report.md)
- [前回の指示書：馬別一覧と要約単位の修正（履歴）](docs/instructions/2026-11/2026-11-27_nlp_horse_summary_instruction.md)
- [先行する指示書：2パターン試行とDashboard仕様検討](docs/instructions/2026-11/2026-11-27_nlp_two_pattern_dashboard_trial_instruction.md)
- [先行する指示書：本番清掃・検証領域分離・私的利用方針](docs/instructions/2026-11/2026-11-27_nlp_production_cleanup_test_isolation_instruction.md)

先行する実機作業では、旧研究の1,303 URL・1,304版と旧56記事を私有バックアップへ退避して復元検証し、本番DBを空にしました。別DB・別資格情報・別Hermesで2試行の収集を終え、保存した2,438版を旧解釈計画へ登録しました。この計画は11月27日14:34 JSTに一時停止しました。[検証用資料庫](http://192.168.0.14:8787/) ・ [本番の開始待ち画面](http://192.168.0.14:8786/) ・ [先行する実機レポートと実画面](docs/reports/2026-11/2026-11-27_nlp_two_pattern_dashboard_trial_report.md)

| 項目 | 確認した状態 |
|---|---|
| 本番DB・永続領域 | 研究・試験データを除去。本文・解釈・試験計画・再開情報を検証側へ分離 |
| 検証環境 | 空のテスト資料庫へ過去名簿の一部と通常日次1回分を実行。同じコード・Skill・モデル・MCPで原文・解釈・表示まで確認 |
| Dashboard | 検証用の `/horses` で馬名を検索し、要約から保存原文と出典へ移動できる |
| 記事解釈 | 1記事・独立した説明対象の馬ごとに1要約。比較相手への言及は対象馬の文章に含め、コメント集の各馬は残す。競走は記事の主題一つ |
| 完了した比較 | 固定した6記事を旧新各1回実生成して終了。検証DBと解釈JSONには採用した6件を保存。原文2,438版と取得2,445件を保持。旧解釈計画は停止中 |
| 次の有限解釈 | 指示書を作成。旧計画の成功履歴ではなく保存2,438版を基準に、新しい計画で処理。既存6版の新結果を再利用。未起動 |
| 本番の収集・解釈 | 初期全名簿・毎朝Cron・常駐解釈は停止。検証後の切替・開始は別途指示 |
| カバー率 | 調査終了。再測定を受入条件にしない |
| 利用目的 | 現在の私的複製・閲覧・整理を基準に内部保存制限を修正 |

分類・収集は9割がた役立てば十分という方針を維持します。初期データのLocal LLM解釈に数日〜1週間程度かかっても構いません。SkillなどのMarkdownはChatGPTが合意範囲で改訂でき、実装・実機操作はCodexが指示書に基づいて行います。収集・解釈・閲覧はサーバだけで完結させ、日常的でない保守はCodexへの依頼とCLIで行います。

- Skill：[検索](skills/keiba-search/SKILL.md)・[記事解釈](skills/keiba-interpret/SKILL.md)・[統括](skills/keiba-coordinate/SKILL.md)。
- 現行配置の説明：[VM15運用手順](infra/nlp-vm/runtime/README.md)。本番と検証の保存先・閲覧先を記載しています。
- 過去の[カバー率報告](docs/reports/2026-11/2026-11-27_nlp_coverage_report.md)と[段階3C引き継ぎ](docs/handoffs/2026-11/2026-11-26_stage3c_redesign_handover.md)は履歴として残します。

## PoC: 日本語Embedding実行環境（CPU）

`Qwen/Qwen3-Embedding-0.6B` をCPUだけでベクトル化・類似検索する再現スクリプト。詳細は `docs/reports/2026-11/2026-11-22_embedding_cpu_environment_poc_report.md`。

```
py -3.14 -m venv .venv-emb-poc
.venv-emb-poc/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-emb-poc/Scripts/python.exe -m pip install -r poc/embedding_cpu/requirements.txt
.venv-emb-poc/Scripts/python.exe poc/embedding_cpu/emb_search.py
# 実記事を混ぜる場合: --passages data/poc/g1_passages.jsonl
```



