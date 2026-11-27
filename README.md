# keibaAI_nlp

競馬記事を本人が私的に複製・保存・閲覧・整理するためのプロジェクト。共通作業規約は[AGENTS.md](AGENTS.md)。収集データからのモデル作成・学習は未定です。

## 現在の作業

2026-11-28、方針を**「テスト資料を撤去し、本番で記事原文の収集を先に始める」**へ切り替えました。Codexは必要な修正・配備と小さな確認の後、過去名簿の初期収集と毎朝の日次収集を開始します。記事単位の独立解釈・馬別要約生成は保留し、後日の指示で当週の情報と掲載日の新しい記事から進めます。

**この更新はCodexへの指示書の反映です。実機の停止・撤去・本番開始を完了したという報告ではありません。** 実行後はCodexの実施レポートと本番Dashboardで確認します。

- [最新のCodex指示書：本番の記事収集・テスト資料撤去・停止再開](docs/instructions/2026-11/2026-11-28_nlp_production_collection_instruction.md)
- [本番Dashboard](http://192.168.0.14:8786/)：開始後の原文・出典・件数・収集進捗を確認
- [VM15運用手順](infra/nlp-vm/runtime/README.md)：実行担当が配備に合わせて更新
- [前の指示書：保存済み検証記事の有限解釈（置換済み）](docs/instructions/2026-11/2026-11-27_nlp_saved_articles_interpretation_instruction.md)

| 今回の対象 | 指示内容 |
|---|---|
| 試験資料 | 既存の試験本文・解釈・計画・キュー・再開状態を撤去。2,438版の全件解釈を待たない |
| 本番データ | 試験データを移さず、空の保存先で新規取得を開始 |
| 過去記事 | v3由来の約54,591頭の名簿を使い、候補と次ページを保持して一巡 |
| 日次記事 | 初期収集中も新着を保存。初期時刻は毎朝06:40 JST |
| 停止・再開 | 過去だけ／日次を含む全収集をCLIで操作。手動停止は再起動後も維持 |
| LLM | 検索・統括の判断に利用。記事の独立解釈は起動しない |
| Dashboard | 本番の原文検索・詳細・媒体別件数・進捗。「解釈は保留」を明示 |
| カバー率 | 調査終了。開始条件として復活させない |

分類・収集は9割がた役立てば十分という方針を維持します。日時や対象の曖昧さを理由に保存を止めず、複数媒体の一覧・特集・サイト内検索と馬名を組み合わせます。1回の取得件数を、馬ごとの記事総数の上限にしません。解釈対象の精密な選別や全件検査を収集の前提にしません。

SkillなどのMarkdownはChatGPTが合意範囲で改訂し、実装・実機操作はCodexが指示書に基づいて行います。日常の収集はサーバで完結し、設定変更などはCodexへの依頼とCLIで行います。

## 直前までの成果と履歴

改訂Skillの6記事比較では、解釈時間の合計が旧版1,827.51秒から新版218.84秒に短縮しました。1記事・独立して説明されている馬ごとに1要約とする方針と、馬別画面の実装は引き継ぎます。試験の本文・解釈そのものは本番へ移しません。

- [6記事の比較検証レポート](docs/reports/2026-11/2026-11-27_nlp_summary_skills_validation_report.md)
- [馬別一覧の実装レポート](docs/reports/2026-11/2026-11-27_nlp_horse_summary_implementation_report.md)
- [2パターン収集試行のレポート](docs/reports/2026-11/2026-11-27_nlp_two_pattern_dashboard_trial_report.md)
- [検証用2,438版の有限解釈の開始報告](docs/reports/2026-11/2026-11-27_nlp_saved_articles_interpretation_report.md)：11月27日の記録。今回の停止・撤去前のもの
- [本番清掃・検証領域分離の指示書](docs/instructions/2026-11/2026-11-27_nlp_production_cleanup_test_isolation_instruction.md)：保存先分離と私的利用方針を継承
- Skill：[検索](skills/keiba-search/SKILL.md)・[記事解釈](skills/keiba-interpret/SKILL.md)・[統括](skills/keiba-coordinate/SKILL.md)。今回の収集専用状態への配備はCodexが行います。
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



