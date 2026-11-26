# keibaAI_nlp

競馬の自然言語情報を自律探索・蓄積・分析する研究プロジェクト（共通作業規約は `AGENTS.md`）。

## 現在地と今後の計画

当面のゴールは、自然言語の曖昧さを許容しながら、競馬の情報を広く大量に継続蓄積することです。分類・収集は「9割がた当たれば十分」という実用性の目安で進めます。厳密な正解率90%の達成証明や全件検査を要求するものではありません。

- 馬トク報知、デイリーうま屋、競馬ブックSmart、ラジオNIKKEIから公開本文を148 URL追加しました。研究領域は累計599 URL・600版、独立解釈済み13版です。Hermesは2020年・2022年の対象から記事を発見し、PCから渡した一覧の続きも保存できました。[主要媒体の実施レポート](docs/reports/2026-11/2026-11-26_nlp_major_media_discovery_report.md)
- 新着・過去記事への導線、媒体別の保存範囲、再開方法を検索Skillにまとめました。継続蓄積の実行場所と通常DBへの接続は今後の研究対象です。[媒体別の手引き](skills/keiba-search/references/media-discovery.md)・[前回の導線・馬名研究](docs/reports/2026-11/2026-11-26_nlp_collection_routes_horse_seeds_report.md)
- **初回の成果**：[検索研究・初期Skillの実施レポート](docs/reports/2026-11/2026-11-26_nlp_search_research_initial_skills_report.md)。原文保存・独立推論・Skill更新の試用成果を再利用し、記事発見・収集経路の研究を続行します。
- **維持する研究方針**：[AGENTS.md §3.1、§5](AGENTS.md)。曖昧さを許容し、初期データのLocal LLM処理は数日〜1週間程度でも構いません。記事が見つからない馬には固執せず、独自のrobots事前拒否は撤廃します。[今回の方針・コード修正](docs/reports/2026-11/2026-11-26_nlp_media_discovery_policy_update_report.md)。
- **実装・実験の現在地**：[段階3C引き継ぎ書（2026-11-26）](docs/handoffs/2026-11/2026-11-26_stage3c_redesign_handover.md)。同書作成後の方針更新と作業順序は、上の研究指示書を優先します。

## PoC: 日本語Embedding実行環境（CPU）

`Qwen/Qwen3-Embedding-0.6B` をCPUだけでベクトル化・類似検索する再現スクリプト。詳細は `docs/reports/2026-11/2026-11-22_embedding_cpu_environment_poc_report.md`。

```
py -3.14 -m venv .venv-emb-poc
.venv-emb-poc/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-emb-poc/Scripts/python.exe -m pip install -r poc/embedding_cpu/requirements.txt
.venv-emb-poc/Scripts/python.exe poc/embedding_cpu/emb_search.py
# 実記事を混ぜる場合: --passages data/poc/g1_passages.jsonl
```

