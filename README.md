# keibaAI_nlp

競馬記事を本人が私的に複製・保存・閲覧・整理するためのプロジェクト。共通作業規約は[AGENTS.md](AGENTS.md)。収集データからのモデル作成・学習は未定です。

## 現在の作業

2026年11月28日、VM15でJRA過去名簿54,591頭の初期収集と、本番の日次収集を開始しました。過去収集は07:27 JST、当日の日次は07:28 JSTに開始し、以後の日次予定は毎朝06:40 JSTです。記事単位の独立解釈・馬別要約は保留しています。[本番の実施レポート](docs/reports/2026-11/2026-11-28_nlp_production_collection_report.md)

| 確認したい内容 | 参照先 |
|---|---|
| 本番の保存件数・媒体・次回予定 | [Dashboard](http://192.168.0.14:8786/) |
| 原文・出典・掲載日の検索 | [記事一覧](http://192.168.0.14:8786/articles) |
| 過去名簿の進捗 | [初回探索済みの頭数・残り候補](http://192.168.0.14:8786/run/0c09da69-a0a8-5a9d-9b50-c50060cf82da) |
| 初回の日次収集 | [11月28日の開催・新着](http://192.168.0.14:8786/run/a054e74c-9b53-597f-8fc3-f73ad2a10f13) |
| 状態確認・過去のみ／全収集の停止再開 | [VM15運用手順](infra/nlp-vm/runtime/README.md) |
| 実施範囲と試験資料撤去の根拠 | [11月28日の指示書](docs/instructions/2026-11/2026-11-28_nlp_production_collection_instruction.md) |

分類・収集は9割がた役立てば十分という方針を維持します。日時や対象の曖昧さを理由に保存を止めず、複数媒体の一覧・特集・サイト内検索と馬名を組み合わせます。1回の取得件数を、馬ごとの記事総数の上限にしません。解釈対象の精密な選別や全件検査を収集の前提にしません。

SkillなどのMarkdownはChatGPTが合意範囲で改訂し、実装・実機操作はCodexが指示書に基づいて行います。日常の収集はサーバで完結し、設定変更などはCodexへの依頼とCLIで行います。

## 直前までの成果と履歴

改訂Skillの6記事比較では、解釈時間の合計が旧版1,827.51秒から新版218.84秒に短縮しました。1記事・独立して説明されている馬ごとに1要約とする方針と、馬別画面の実装は引き継ぎます。試験の本文・解釈そのものは本番へ移しません。

- [6記事の比較検証レポート](docs/reports/2026-11/2026-11-27_nlp_summary_skills_validation_report.md)
- [馬別一覧の実装レポート](docs/reports/2026-11/2026-11-27_nlp_horse_summary_implementation_report.md)
- [2パターン収集試行のレポート](docs/reports/2026-11/2026-11-27_nlp_two_pattern_dashboard_trial_report.md)
- [検証用2,438版の有限解釈の開始報告](docs/reports/2026-11/2026-11-27_nlp_saved_articles_interpretation_report.md)：11月27日の記録。今回の停止・撤去前のもの
- [本番清掃・検証領域分離の指示書](docs/instructions/2026-11/2026-11-27_nlp_production_cleanup_test_isolation_instruction.md)：保存先分離と私的利用方針を継承
- Skill：[検索](skills/keiba-search/SKILL.md)・[記事解釈](skills/keiba-interpret/SKILL.md)・[統括](skills/keiba-coordinate/SKILL.md)。VM15には収集専用の検索・統括Skillと、将来用の採用済み解釈Skillを配備しています。
- [過去のカバー率報告](docs/reports/2026-11/2026-11-27_nlp_coverage_report.md)・[段階3C引き継ぎ](docs/handoffs/2026-11/2026-11-26_stage3c_redesign_handover.md)

## PoC: 日本語Embedding実行環境（CPU）

`Qwen/Qwen3-Embedding-0.6B` をCPUだけでベクトル化・類似検索する再現スクリプト。詳細は `docs/reports/2026-11/2026-11-22_embedding_cpu_environment_poc_report.md`。

```
py -3.14 -m venv .venv-emb-poc
.venv-emb-poc/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-emb-poc/Scripts/python.exe -m pip install -r poc/embedding_cpu/requirements.txt
.venv-emb-poc/Scripts/python.exe poc/embedding_cpu/emb_search.py
# 実記事を混ぜる場合: --passages data/poc/g1_passages.jsonl
```



