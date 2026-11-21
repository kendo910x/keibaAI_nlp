# -*- coding: utf-8 -*-
"""Qwen3-Embedding-0.6B CPU PoC: 日本語競馬コメントのベクトル化と類似検索.

使い方:
  python emb_search.py [--passages data/poc/g1_passages.jsonl] [--max-passages 200]

- CPUのみで実行する。GPUは使用しない。
- モデルは HuggingFace Hub から初回のみダウンロードされ、~/.cache/huggingface に保存される（Git管理しない）。
- 検索文はモデル推奨の query 用入力形式（Instruct フォーマット）を使う。
"""

import argparse
import ctypes
import json
import os
import sys
import time
from pathlib import Path

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"

# 競馬コメントを模したサンプル（肯定・否定・距離延長／短縮・馬場適性の対照を含む）
SAMPLE_COMMENTS = [
    "距離延長がこの馬にはプラスに働き、持ち前のスタミナを発揮できる見込みだ。",
    "距離短縮はこの馬には向かず、短い直線での不安が残る。",
    "重馬場の好走実績があり、馬場悪化はむしろ追い風になりそうだ。",
    "重馬場では実績がなく、馬場が重くなると苦にしている。",
    "芝での好走がある一方、ダートでは実績が乏しい。",
    "芝では精彩を欠いたが、ダート転向で真価を発揮できる。",
    "調教師は「前走の疲れはなく、状態は万全です」と語った。",
    "調教師は「まだ脚元が不安定で、状態は上向途中です」と語った。",
    "1800メートルへの距離延長が合い、長距離戦でのメドが立ちつつある。",
    "1400メートルへの距離短縮に苦しみ、慣れたマイルでこそ結果を出したい。",
    "内回りコースでは実績がなく、コース適正は未知数だ。",
    "外回りコースの適正があり、末脚を存分に発揮できる。",
    "大舞台に強い馬で、緊張感のある大勢の馬場でも動じない。",
    "大舞台の経験がなく、緊張感のある場では伸びきれない可能性がある。",
]

# 検索文（延長／短縮・否定・馬場適性の混同を見るための対照クエリ）
SAMPLE_QUERIES = [
    "距離が伸びてプラスになりそうな馬",
    "距離短縮がマイナスに働きそうな馬",
    "重い馬場が味方しそうな馬",
    "重い馬場では実績がなく不安な馬",
    "ダート向きの馬",
    "まだ状態が万全でない馬",
]


def peak_working_set_mb() -> float:
    """Windows API でこのプロセスのピークRSS(MB)を取る（失敗時は nan）。"""
    try:
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return float("nan")
        return pmc.PeakWorkingSetSize / (1024 * 1024)
    except Exception:
        return float("nan")


def vector_report(vecs, label: str) -> dict:
    """ベクトル群の次元・型・NaN・空ベクトル（ノルム0）を点検して報告する。"""
    import numpy as np

    arr = np.asarray(vecs)
    norms = np.linalg.norm(arr, axis=1)
    report = {
        "label": label,
        "count": int(arr.shape[0]),
        "dim": int(arr.shape[1]),
        "dtype": str(arr.dtype),
        "nan_count": int(np.isnan(arr).sum()),
        "inf_count": int(np.isinf(arr).sum()),
        "zero_norm_rows": [int(i) for i in np.where(norms == 0)[0]],
        "norm_min": float(norms.min()),
        "norm_max": float(norms.max()),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--passages", default=None,
                    help="G1記事探索結果の JSONL（text フィールドを使う）。無くてもサンプルのみで完了する")
    ap.add_argument("--max-passages", type=int, default=200)
    ap.add_argument("--output", default=None,
                    help="結果JSONの保存先（既定: data/poc/embedding_search_results.json）")
    ap.add_argument("--query", action="append", default=None,
                    help="検索文を追加（複数指定可）。既定のサンプルクエリに追加される")
    ap.add_argument("--dtype", default="fp32", choices=["bf16", "fp32"],
                    help="モデル読込 dtype（既定 fp32: 本CPU実測で bf16 より約6倍速。bf16 は --dtype bf16 で比較可）")
    args = ap.parse_args()

    t0 = time.perf_counter()
    from sentence_transformers import SentenceTransformer
    import torch

    torch.set_num_threads(max(1, (os.cpu_count() or 4)))

    t_import = time.perf_counter() - t0

    t0 = time.perf_counter()
    dtype = torch.bfloat16 if args.dtype == "bf16" else torch.float32
    model = SentenceTransformer(MODEL_ID, device="cpu",
                                model_kwargs={"revision": MODEL_REVISION, "dtype": dtype})
    load_time = time.perf_counter() - t0

    prompts = getattr(model, "prompts", {}) or {}
    query_prompt = prompts.get("query")
    print(f"[model] {MODEL_ID} rev={MODEL_REVISION[:12]}")
    print(f"[model] import {t_import:.1f}s / load {load_time:.1f}s / device=cpu / threads={torch.get_num_threads()}")
    print(f"[model] query prompt: {query_prompt!r}")

    results = {"model": MODEL_ID, "revision": MODEL_REVISION,
               "dtype": args.dtype,
               "load_seconds": round(load_time, 2),
               "query_prompt": query_prompt, "vectors": [], "searches": []}

    # --- ドキュメント側 Embedding ---
    docs = list(SAMPLE_COMMENTS)
    doc_ids = [f"sample_{i:02d}" for i in range(len(docs))]

    passages_file = Path(args.passages) if args.passages else None
    if passages_file and passages_file.exists():
        n = 0
        with passages_file.open(encoding="utf-8") as f:
            for line in f:
                if n >= args.max_passages:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = (obj.get("text") or "").strip()
                if text:
                    docs.append(text)
                    doc_ids.append(f"passage_{n:04d}")
                    n += 1
        print(f"[passages] {passages_file}: {n} 件を追加")
    else:
        print("[passages] 未指定または存在しないためサンプルのみで実行")

    t0 = time.perf_counter()
    doc_vecs = model.encode(docs, batch_size=8, normalize_embeddings=True,
                            convert_to_numpy=True, show_progress_bar=False)
    doc_time = time.perf_counter() - t0
    print(f"[encode] docs {len(docs)}件 {doc_time:.2f}s ({len(docs)/doc_time:.1f}件/秒)")
    results["vectors"].append(vector_report(doc_vecs, "documents"))
    results["encode_docs_seconds"] = round(doc_time, 2)

    # --- クエリ側 Embedding（モデル推奨の query 形式）と検索 ---
    queries = SAMPLE_QUERIES + (args.query or [])
    t0 = time.perf_counter()
    query_vecs = model.encode(
        queries, batch_size=8, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
        prompt_name="query" if "query" in prompts else None)
    query_time = time.perf_counter() - t0
    results["vectors"].append(vector_report(query_vecs, "queries"))
    results["encode_queries_seconds"] = round(query_time, 2)

    sims = query_vecs @ doc_vecs.T  # 正規化済みなので内積 = cosine
    for qi, q in enumerate(queries):
        order = sims[qi].argsort()[::-1][:5]
        hits = [{"rank": r + 1, "id": doc_ids[i], "score": round(float(sims[qi][i]), 4),
                 "text": docs[i]} for r, i in enumerate(order)]
        results["searches"].append({"query": q, "top5": hits})
        print(f"\n[query] {q}")
        for h in hits:
            print(f"  {h['rank']}. ({h['score']:+.4f}) [{h['id']}] {h['text']}")

    results["peak_rss_mb"] = round(peak_working_set_mb(), 1)
    print(f"\n[mem] プロセス ピークRSS: {results['peak_rss_mb']} MB")
    for v in results["vectors"]:
        print(f"[vec] {v['label']}: {v['count']}本 x {v['dim']}次元 dtype={v['dtype']} "
              f"NaN={v['nan_count']} Inf={v['inf_count']} ノルム0={v['zero_norm_rows']} "
              f"norm[{v['norm_min']:.4f},{v['norm_max']:.4f}]")

    out = Path(args.output) if args.output else Path(__file__).resolve().parents[2] / "data" / "poc" / "embedding_search_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[out] 結果を保存: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
