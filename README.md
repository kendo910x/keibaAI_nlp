# keibaAI_nlp

競馬の自然言語情報を自律探索・蓄積・分析する研究プロジェクト（共通作業規約は `AGENTS.md`）。

## 現在地と今後の計画

当面のゴールは、自然言語の曖昧さを許容しながら、競馬の情報を広く大量に継続蓄積することです。分類・収集は「9割がた当たれば十分」という実用性の目安で進めます。厳密な正解率90%の達成証明や全件検査を要求するものではありません。

**次の作業：[サーバ常用化と閲覧専用Dashboardの実装指示書](docs/instructions/2026-11/2026-11-26_nlp_server_runtime_dashboard_instruction.md)。** 研究で得た収集方法・Skill・コードを通常運転へ組み込み、サーバへの配備、毎朝の自動収集の有効化、初期構築のCLI起動、記事閲覧までを実装します。この指示書の追加は、サーバへの配備完了を意味しません。

| 用途 | 初版の運用 |
|---|---|
| 過去記事の初期構築 | 既存v3由来の馬名名簿を使い、CLIから有限の処理を開始・再開 |
| 日常収集 | Hermes Cronで毎朝1回、最新の対象を確認して同じ処理を実行 |
| 記事解釈 | 保存済みの未処理記事をサーバで順次解釈。収集と分けて継続 |
| Dashboard | 稼働状況・処理結果と、記事検索・一覧・詳細・件数の閲覧専用 |
| 設定変更・保守 | 必要時にCodexへ依頼し、CLI・設定ファイルで対応 |

通常運転は開発PCやCodexに依存させません。配備完了と、初期名簿の一巡・解釈待ちの消化は分けて報告します。

- **確認済みの研究成果**：馬トク報知、デイリーうま屋、競馬ブックSmart、ラジオNIKKEIから公開本文を148 URL追加しました。最新レポートの研究領域は累計599 URL・600版、独立解釈済み13版です。通常DBの件数ではありません。[主要媒体の実施レポート](docs/reports/2026-11/2026-11-26_nlp_major_media_discovery_report.md)
- **次工程で使う資産**：[媒体別の手引き](skills/keiba-search/references/media-discovery.md)、[導線・馬名研究](docs/reports/2026-11/2026-11-26_nlp_collection_routes_horse_seeds_report.md)、[検索研究・初期Skillの実施レポート](docs/reports/2026-11/2026-11-26_nlp_search_research_initial_skills_report.md)。本文・独立推論・Skill・名簿・再開情報を引き継ぎ、具体的な実装上の不足を補います。
- **維持する方針**：[AGENTS.md §3.1、§3.2、§5](AGENTS.md)。曖昧さを許容し、初期データのLocal LLM処理は数日〜1週間程度でも構いません。記事が見つからない馬には固執せず、独自のrobots事前拒否は撤廃済みです。[方針・コード修正の記録](docs/reports/2026-11/2026-11-26_nlp_media_discovery_policy_update_report.md)
- **従来環境の引き継ぎ**：[段階3C引き継ぎ書（2026-11-26）](docs/handoffs/2026-11/2026-11-26_stage3c_redesign_handover.md)。同書作成後の方針と作業順序は、上の新しい実装指示書を優先します。

## PoC: 日本語Embedding実行環境（CPU）

`Qwen/Qwen3-Embedding-0.6B` をCPUだけでベクトル化・類似検索する再現スクリプト。詳細は `docs/reports/2026-11/2026-11-22_embedding_cpu_environment_poc_report.md`。

```
py -3.14 -m venv .venv-emb-poc
.venv-emb-poc/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-emb-poc/Scripts/python.exe -m pip install -r poc/embedding_cpu/requirements.txt
.venv-emb-poc/Scripts/python.exe poc/embedding_cpu/emb_search.py
# 実記事を混ぜる場合: --passages data/poc/g1_passages.jsonl
```


