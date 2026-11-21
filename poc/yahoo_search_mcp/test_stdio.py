# -*- coding: utf-8 -*-
"""stdio MCP 実機試験: initialize → tools/list → yahoo_search 実呼出。

実行: .venv-yahoo-mcp/Scripts/python.exe test_stdio.py "<query>"
（第1引数なしの場合は tools/list まで。実検索は明示的にクエリを渡したときのみ。）
"""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve().parent / "yahoo_search_server.py")],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"[init] server={info.serverInfo.name} protocol={info.protocolVersion}")
            tools = await session.list_tools()
            print(f"[tools] {[t.name for t in tools.tools]}")
            if len(sys.argv) > 1:
                res = await session.call_tool("yahoo_search",
                                              {"query": sys.argv[1], "num_results": 5})
                print("[call] yahoo_search ->")
                print(res.content[0].text)
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
