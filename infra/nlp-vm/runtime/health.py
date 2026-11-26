"""Observe connections without inference or storing external content."""

import asyncio
import sys
from datetime import date
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from corpus import connect
from research import LLM, MODEL, SHARED


async def shared_names():
    async with streamablehttp_client(SHARED) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return {t.name for t in (await s.list_tools()).tools}


def check(name, fn):
    try:
        return name, "ok", fn()
    except Exception as e:
        return name, "failed", type(e).__name__ + ": " + str(e)[:170]


def models():
    r = httpx.get(LLM.replace("chat/completions", "models"), timeout=8)
    r.raise_for_status()
    if MODEL not in [x["id"] for x in r.json()["data"]]:
        raise RuntimeError("設定モデルが一覧にありません")
    return "設定モデルの応答を確認"


def tools_check():
    if not {"yahoo_search", "fetch_page"} <= asyncio.run(
        asyncio.wait_for(shared_names(), 12)
    ):
        raise RuntimeError("検索・取得ツールが一覧にありません")
    return "Yahoo検索・ページ取得ツールを確認"


def site_check():
    url = "https://www.radionikkei.jp/keiba_article/news/" + date.today().strftime(
        "%Y/%m/"
    )
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": "KeibaNLPResearch/1.0"},
        follow_redirects=True,
        timeout=8,
    ) as r:
        r.raise_for_status()
        return "ラジオNIKKEI月別一覧・HTTP " + str(r.status_code)


if __name__ == "__main__":
    rows = [
        check("model", models),
        check("search", tools_check),
        check("fetch", site_check),
    ]
    for name, v in zip(("ticker", "interpreter"), sys.argv[1:3]):
        rows.append(
            (
                name,
                "enabled" if v == "active" else ("failed" if v == "failed" else "off"),
                "稼働中"
                if v == "active"
                else ("サービス失敗" if v == "failed" else "停止中"),
            )
        )
    with connect() as c:
        with c.cursor() as cur:
            cur.executemany(
                """INSERT INTO health VALUES (%s,%s,%s,now()) ON CONFLICT(name)
            DO UPDATE SET state=excluded.state,detail=excluded.detail,checked_at=excluded.checked_at""",
                rows,
            )
