# 開発PCでの日本語Embedding実行環境 PoC 実施レポート

実施日: 2026-11-22 / 対象指示書: `docs/instructions/2026-11/2026-11-22_embedding_cpu_environment_poc_instruction.md`（commit `d684715`）

## 1. 目的・対象

開発PC（CPUのみ）で `Qwen/Qwen3-Embedding-0.6B` を使い、日本語競馬コメントのベクトル化と自然言語類似検索が実運用可能かを実測する。G1記事探索の結果には依存しない。

## 2. 実行環境（実測）

| 項目 | 値 |
|---|---|
| OS | Windows 11 (10.0.26300.10075) |
| CPU | AMD Ryzen 7 5800X (8コア16スレッド) |
| RAM | 64 GB（空き十分） |
| Python | 3.14.0（既存システムPython。独立 venv `.venv-emb-poc` を作成し、既存環境・v3環境への変更なし） |
| torch | 2.15.0+cpu（PyTorch公式CPU index、cp314 wheel あり） |
| sentence-transformers | 6.3.0 / transformers 5.24.0 / huggingface-hub 2.4.0 / numpy 2.5.5 |
| モデル | `Qwen/Qwen3-Embedding-0.6B` revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`（HuggingFace Hub、重みは `~/.cache/huggingface` に保存・Git管理外） |

備考:

- 開発PCの `miniconda3` は python.exe が無く不完全なインストールだった（観測事実のみ。今回は未使用・未修正）。
- HFキャッシュは Developer Mode 無効のため symlink 不可 → 重複保存の警告あり（動作には影響なし）。
- 管理者権限を要する変更は行っていない。

## 3. 実施内容

1. Python 3.14 で独立 venv を作成し、torch CPU 版と sentence-transformers を導入（`poc/embedding_cpu/requirements.txt`）。
2. `poc/embedding_cpu/emb_search.py` を作成。競馬コメント模しの日本語サンプル14件（肯定／否定・距離延長／短縮・馬場適性・状態・コース適性の対照ペア）をベクトル化し、検索文6件で cosine 上位5件を原文付きで出力。
3. 検索文はモデル推奨の query 形式（sentence-transformers の `prompt_name="query"` → `Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery: `）を自動適用。ドキュメント側は無地の原文。
4. dtype 比較（fp32 / bf16）、ロード時間・処理時間・ピークメモリを計測。
5. `data/poc/g1_passages.jsonl` は本実施時点では未存在のため、`--passages` オプションのみ実装（サンプルのみで完走）。

再実行手順:

```
py -3.14 -m venv .venv-emb-poc
.venv-emb-poc/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv-emb-poc/Scripts/python.exe -m pip install -r poc/embedding_cpu/requirements.txt
.venv-emb-poc/Scripts/python.exe poc/embedding_cpu/emb_search.py
```

## 4. 実測結果

### 4.1 ベクトルの健全性

- 次元数 **1024**、出力 dtype **float32**、NaN 0件・Inf 0件・ノルム0（空ベクトル）なし。正規化後ノルム 1.0000。

### 4.2 所要時間・メモリ（Ryzen 7 5800X / 16スレッド / CPUのみ）

| 測定 | fp32 | bf16 |
|---|---|---|
| モデルロード | 3.5 s | 3.3 s |
| 短文14件のEmbedding | **0.77 s（18.2件/秒）** | 4.85 s（2.9件/秒） |
| プロセス ピークRSS | **2,841 MB** | （計測前に修正前のため未取得） |

- **CPU では bf16 より fp32 の方が約6倍速い**（sentence-transformers 自体が警告している挙動と一致）。スクリプトの既定は fp32 とした。
- 初回モデルダウンロード（約1.2 GB）は数分。2回目以降はキャッシュから。
- ピークRSS 約2.8 GB は64 GB搭載機では問題なし。

### 4.3 検索品質（上位5件の原文とスコアは `data/poc/embedding_search_results.json` に保存、Git管理外）

正しく引当できた例（Top1 = 期待通り）:

- 「距離が伸びてプラスになりそうな馬」→ Top1 「距離延長がこの馬にはプラスに働き…」(+0.718)
- 「距離短縮がマイナスに働きそうな馬」→ Top1 「距離短縮はこの馬には向かず…」(+0.635)
- 「重い馬場では実績がなく不安な馬」→ Top1 「重馬場では実績がなく…」(+0.743)

**取り違え（混同）の実測:**

1. **否定・極性の混同（最重要）**: 「重い馬場が味方しそうな馬」の Top1 が「重馬場では**実績がなく**、苦にしている」(+0.610) で、正解の「重馬場の**好走実績があり**」は3位(+0.502)。「芝での好走がある一方、ダートでは実績が乏しい」も「ダート向きの馬」で3位に入った。適性の良／否という**極性（肯定／否定）がベクトル距離に十分効いていない**。
2. **表面単語の一致が意味に優先**: 「重い馬場」クエリで無関係な「緊張感のある大勢の**馬場**でも動じない」が2位に入ることがある（馬場・実績などの語彙重複が効く）。
3. **名詞句のみの短いクエリの判別が弱い**: 「ダート向きの馬」「まだ状態が万全でない馬」は Top5 スコアが 0.37〜0.49 と低く、期待するコメントが Top5 外（「ダート転向で真価」は6位以下、「状態は上向途中」も Top5 外）。逆に反対極性の「状態は万全です」が4位に入った。
4. 延長／短縮は Top1 は正しいが、互いが2位に浮く（延長クエリ→短縮コメントが2位 +0.534 など）。同一トピックの対義表現は近接する傾向。

## 5. 未確認事項・未実施事項

- 実記事（`data/poc/g1_passages.jsonl`）での検索品質は未検証（ファイル未存在。`--passages data/poc/g1_passages.jsonl` で合流可能な状態にしてある）。
- 数百〜数千件規模のスループット、batch size・スレッド数のチューニングは未実施（短文14件のみ）。
- 検索プロンプトを日本語にした場合の差、fp16、rerank（cross-encoder）併用は未検証。
- bf16 時のピークRSSは未取得。

## 6. 変更・副作用

- 新規 tracked file: `poc/embedding_cpu/emb_search.py`、`poc/embedding_cpu/requirements.txt`、`.gitignore`、本レポート、README.md の手順追記のみ。
- Git管理外: `.venv-emb-poc/`（仮想環境）、HFキャッシュ（`~/.cache/huggingface`）、`data/poc/embedding_search_results*.json`（結果）。`.gitignore` に追加。
- 既存環境（v3含む）への変更なし。常駐プロセス・サービス追加なし。

## 7. 結論と次の一手

**結論**: CPUのみでも Qwen3-Embedding-0.6B での日本語ベクトル化・類似検索は実用速度（fp32 で約18件/秒、ピーク約2.8GB）で動作。ただし**否定・極性の混同と短文クエリの判別弱さ**が実測され、コメント検索をそのまま「除外条件付き検索」に使うのは危険（例: 「重馬場実績なし」を「重馬場向き」で引くと最上位に来る）。

**次の一手（提案）**:

1. G1記事探索タスクの成果を `data/poc/g1_passages.jsonl` に投入し、`--passages` で実文による検索品質を確認する（本PoCの合流点）。
2. 実文で同様の混同が出る場合の対策候補（未実施・要承認）: クエリ側を完全な肯定文にリライトする／主張単位でチャンクする／小型 cross-encoder リランクの CPU 実測。
3. 大量 Embedding 時は fp32 固定・正規化保存・モデル revision のメタデータ記録（AGENTS.md 第7節）をバッチスクリプトに反映する。
