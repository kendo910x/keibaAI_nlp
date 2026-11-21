# -*- coding: utf-8 -*-
"""Yahoo MCP 検索の実行ユーティリティ（比較・自律探索用）。

実行: .venv-yahoo-mcp/Scripts/python.exe run_search.py <out.json> "<query1>" ["<query2>" ...]
1セッション内で順に実行し、結果とHTTP記録をJSONに保存。呼び出し間隔は5秒。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(queries):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve().parent / "yahoo_search_server.py")],
    )
    out = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for i, q in enumerate(queries):
                if i:
                    time.sleep(5)
                t0 = time.time()
                res = await session.call_tool("yahoo_search",
                                              {"query": q, "num_results": 5})
                out.append({"query": q, "seconds": round(time.time() - t0, 1),
                            "result": res.content[0].text})
    return out


if __name__ == "__main__":
    out_path, queries = sys.argv[1], sys.argv[2:]
    data = asyncio.run(run(queries))
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for d in data:
        print(f"===== {d['query']} ({d['seconds']}s) =====")
        print(d["result"])
