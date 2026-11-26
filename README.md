# keibaAI_nlp

競馬記事を本人が私的に複製・保存・閲覧・整理するためのプロジェクト。共通作業規約は[AGENTS.md](AGENTS.md)。収集データからのモデル作成・学習は未定です。

## 現在の作業

**2026-11-27の最新指示は、本番の研究・試験データの清掃と、検証領域の分離です。カバー率調査は終了しました。**

[実行指示書：本番データ清掃・検証領域分離・私的利用方針](docs/instructions/2026-11/2026-11-27_nlp_production_cleanup_test_isolation_instruction.md)

直前の[配備報告](docs/reports/2026-11/2026-11-27_nlp_server_runtime_dashboard_report.md)では、通常DBに研究・試験由来の1,303 URL・1,304版と旧56記事が入っています。この文書更新は実機での退避・削除を完了した報告ではありません。現物を保全して検証側へ移し、本番の利用データを空にするのが次の作業です。

| 項目 | 今回整える状態 |
|---|---|
| 本番DB・永続領域 | 研究・試験データを除去。本文・解釈・試験計画・再開情報を検証側へ分離 |
| 検証環境 | 本番と同じコード・Skill・モデル・MCPで収集・解釈・表示を有限試験 |
| Dashboard | 本番は0件・開始待ち。検証は検証用であることを明示して実データを表示 |
| 本番の収集・解釈 | 初期全名簿・毎朝Cron・常駐解釈は停止。検証後の切替・開始は別途指示 |
| カバー率 | 調査終了。再測定を受入条件にしない |
| 利用目的 | 現在の私的複製・閲覧・整理を基準に内部保存制限を修正 |

分類・収集は9割がた役立てば十分という方針を維持します。初期データのLocal LLM解釈に数日〜1週間程度かかっても構いません。収集・解釈・閲覧はサーバだけで完結させ、日常的でない保守はCodexへの依頼とCLIで行います。

- Skill：[検索](skills/keiba-search/SKILL.md)・[記事解釈](skills/keiba-interpret/SKILL.md)・[統括](skills/keiba-coordinate/SKILL.md)。
- 現行配置の説明：[VM15運用手順](infra/nlp-vm/runtime/README.md)。最新の分離指示に沿って修正する対象です。
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


