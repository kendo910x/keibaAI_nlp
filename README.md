# keibaAI_nlp

競馬の自然言語情報を自律探索・蓄積・分析する研究プロジェクト（共通作業規約は `AGENTS.md`）。

## 現在地と今後の計画

当面のゴールは、今後の研究に使える競馬の自然言語データを継続して蓄積することです。
合意した方針、PoCの到達点、検索基盤・専用DB・v3参照情報・エージェント実行基盤の計画は、[2026-11-22 引き継ぎ書](docs/handoffs/2026-11/2026-11-22_data_accumulation_handover.md)を参照してください。

## PoC: 日本語Embedding実行環境（CPU）

`Qwen/Qwen3-Embedding-0.6B` をCPUだけでベクトル化・類似検索する再現スクリプト。詳細は `docs/reports/2026-11/2026-11-22_embedding_cpu_environment_poc_report.md`。

```
py -3.14 -m venv .venv-emb-poc
.venv-emb-poc/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-emb-poc/Scripts/python.exe -m pip install -r poc/embedding_cpu/requirements.txt
.venv-emb-poc/Scripts/python.exe poc/embedding_cpu/emb_search.py
# 実記事を混ぜる場合: --passages data/poc/g1_passages.jsonl
```
