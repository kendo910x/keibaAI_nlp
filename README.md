# keibaAI_nlp

競馬の自然言語情報を自律探索・蓄積・分析する研究プロジェクト（共通作業規約は `AGENTS.md`）。

## 現在地と今後の計画

当面のゴールは、自然言語の曖昧さを許容しながら、競馬の情報を広く大量に継続蓄積することです。分類・収集は「9割がた当たれば十分」という実用性の目安で進めます。厳密な正解率90%の達成証明や全件検査を要求するものではありません。

**VM15の[閲覧専用Dashboard](http://192.168.0.14:8786/)はLAN内で利用できます。** 通常DBへ研究コーパス599 URL・600版・既存解釈13版を引き継ぎ、有限試験・標本調査で得た記事も同じ資料庫から読めます。移行前の通常DB資料は由来別に閲覧できます。全名簿の初期構築・毎朝のCron・常駐解釈は運用開始待ちです。[開始前レビュー](docs/reports/2026-11/2026-11-27_nlp_server_runtime_dashboard_report.md)・[標本の集計](docs/reports/2026-11/2026-11-27_nlp_coverage_report.md)・[VM15の運用手順](infra/nlp-vm/runtime/README.md)

| 用途 | 開始指示後の運用 | 今回の引き渡し |
|---|---|---|
| 過去記事の初期構築 | 既存v3由来の馬名名簿を使うCLI処理 | 実装・有限試験済み、全名簿は未起動 |
| 日常収集 | Hermes Cronで毎朝1回、同じ処理を実行 | 起動経路を有限試験し、本運用Cronは未登録または無効 |
| 記事解釈 | 保存済みの未処理記事を収集と分けて順次処理 | 有限試験のみ。常駐解釈は停止 |
| Dashboard | 稼働状況・記事検索・一覧・詳細・件数の閲覧専用 | 既存データ・試験結果を閲覧でき、「運用開始待ち」を表示 |
| 設定変更・保守 | 必要時にCodexへ依頼し、CLI・設定ファイルで対応 | 開始・停止・設定等の手順を用意 |

通常運転は開発PCやCodexに依存させません。今回は「実装完了・運用開始待ち」で引き渡します。最終的な3つのSkillと、重賞・条件戦、年代、有力馬とその他でどれだけ記事が揃うかを事前に確認します。選んだレースの全出走馬と名簿からの補助標本を調べ、未発見も報告します。カバー率90%などの合格値は設けません。前版の毎朝の有効化・初期構築開始の指示は取り消しています。

- **確認済みの研究成果**：馬トク報知、デイリーうま屋、競馬ブックSmart、ラジオNIKKEIから公開本文を148 URL追加しました。最新レポートの研究領域は累計599 URL・600版、独立解釈済み13版です。通常DBの件数ではありません。[主要媒体の実施レポート](docs/reports/2026-11/2026-11-26_nlp_major_media_discovery_report.md)
- **配置したSkill**：[検索](skills/keiba-search/SKILL.md)・[記事解釈](skills/keiba-interpret/SKILL.md)・[親の統括](skills/keiba-coordinate/SKILL.md)。検索Skillから[媒体別の手引き](skills/keiba-search/references/media-discovery.md)を参照できます。
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


