# keibaAI_nlp

競馬の自然言語情報を自律探索・蓄積・分析する研究プロジェクト（共通作業規約は `AGENTS.md`）。

## 現在地と今後の計画

当面のゴールは、自然言語の曖昧さを許容しながら、競馬の情報を広く大量に継続蓄積することです。分類・収集は「9割がた当たれば十分」という実用性の目安で進めます。厳密な正解率90%の達成証明や全件検査を要求するものではありません。

- **現在地**：[導線・馬名研究の実施レポート](docs/reports/2026-11/2026-11-26_nlp_collection_routes_horse_seeds_report.md)。研究領域に累計451 URL・452版、うち独立解釈済み13版。一部媒体で一覧からの取得・再利用・再開を実証しました。主要媒体の基礎調査、通常DBへの接続、継続運用は未完了です。
- **次の作業**：[主要媒体の発見と収集経路の基礎調査](docs/instructions/2026-11/2026-11-26_nlp_major_media_discovery_instruction.md)。Codex自身が広い検索で競馬ポータル・大手スポーツ紙を探し、複数媒体の公開記事と新着・過去の導線を実際に確認します。既存の名簿・収集コードを使い、得た方法をSkillへ反映してからHermesで再現します。
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

