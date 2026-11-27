# keibaAI_nlp

競馬記事を本人が私的に複製・保存・閲覧・整理するためのプロジェクト。共通作業規約は[AGENTS.md](AGENTS.md)。収集データからのモデル作成・学習は未定です。

## 現在の作業

**2026-11-27の最新指示は、過去馬名検索と通常の日次検索をテスト用DBへ実行し、実データのDashboardで仕様を検討することです。本番清掃・検証領域分離を先に行い、カバー率調査は再開しません。**

[最新の実行指示書：2パターン試行とDashboard仕様検討](docs/instructions/2026-11/2026-11-27_nlp_two_pattern_dashboard_trial_instruction.md)  
[先行する指示書：本番清掃・検証領域分離・私的利用方針](docs/instructions/2026-11/2026-11-27_nlp_production_cleanup_test_isolation_instruction.md)

VM15では旧研究の1,303 URL・1,304版と旧56記事を私有バックアップへ復元検証済みです。本番DBを空にしてから、別DB・別資格情報・別Hermesで今回の2試行の収集を終えました。11月27日の収集終了時に全2,438版を有限解釈に登録し、現在の進捗を検証画面で確認できます。[検証用資料庫](http://192.168.0.14:8787/) ・ [本番の開始待ち画面](http://192.168.0.14:8786/) ・ [実機レポートと実画面](docs/reports/2026-11/2026-11-27_nlp_two_pattern_dashboard_trial_report.md)

| 項目 | 今回整える状態 |
|---|---|
| 本番DB・永続領域 | 研究・試験データを除去。本文・解釈・試験計画・再開情報を検証側へ分離 |
| 検証環境 | 空のテスト資料庫へ過去名簿の一部と通常日次1回分を実行。同じコード・Skill・モデル・MCPで原文・解釈・表示まで確認 |
| Dashboard | 本番は0件・開始待ち。検証では2試行の原文とLLM解釈を実際に閲覧し、画面仕様を検討 |
| 本番の収集・解釈 | 初期全名簿・毎朝Cron・常駐解釈は停止。検証後の切替・開始は別途指示 |
| カバー率 | 調査終了。再測定を受入条件にしない |
| 利用目的 | 現在の私的複製・閲覧・整理を基準に内部保存制限を修正 |

分類・収集は9割がた役立てば十分という方針を維持します。初期データのLocal LLM解釈に数日〜1週間程度かかっても構いません。収集・解釈・閲覧はサーバだけで完結させ、日常的でない保守はCodexへの依頼とCLIで行います。

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


