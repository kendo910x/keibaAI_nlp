"""Observe connections and raw collection progress without inference."""

import asyncio
import sys
from datetime import date, timedelta
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from corpus import connect
import raw_control
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


def record_hourly_progress(c):
    due = c.execute(
        """SELECT NOT EXISTS(SELECT FROM health WHERE name='collection_progress'
           AND checked_at>=date_trunc('hour',now())) AS due"""
    ).fetchone()["due"]
    if not due:
        return
    counts = c.execute(
        "SELECT now() AS checked,count(*) AS versions,max(observed_at) AS last_saved FROM versions"
    ).fetchone()
    state, flags, waits, plans = raw_control.operating_status(c)
    cutoff = counts["checked"] - timedelta(hours=1)
    saved = counts["last_saved"]
    details = [state, f"本文{counts['versions']:,}版（最終保存 {saved:%m/%d %H:%M} JST）" if saved else "本文0版"]
    issues = []
    daily_advancing = False
    evidence = []
    for plan in plans:
        if flags["all_paused"] or plan["stop_requested"] or (plan["kind"] == "history" and flags["history_paused"]):
            continue
        progress = raw_control.progress(c, plan["id"])
        last = progress["last_finished"]
        recent = (last or plan["since"]) >= cutoff
        if plan["kind"] == "daily" and recent and plan["state"] in ("queued", "running"):
            daily_advancing = True
        evidence.append((plan, progress, recent))
        name = "過去" if plan["kind"] == "history" else "日次"
        completion = last.strftime("%m/%d %H:%M") if last else "未完了"
        priority = "（日次優先）" if plan["state"] == "daily_priority" else ""
        details.append(f"{name}{priority} 完了{progress['finished']:,}・残り{progress['pending']:,}・"
                       f"既知{progress['reused']:,}（最終作業 {completion}）")
    for wait in waits:
        scope = "全経路" if wait["source"] == "*" else wait["source"]
        reason = wait["reason"].partition("\n")[0]
        message = f"{scope}は{wait['retry_at']:%H:%M} JSTまで待機（{reason}）"
        details.append(message)
        if wait["source"] == "*" and evidence:
            issues.append("共通障害")
    for plan, progress, recent in evidence:
        name = "過去" if plan["kind"] == "history" else "日次"
        if plan["state"] == "interrupted":
            issues.append(name + "のワーカー中断")
        elif (not recent and progress["pending"] > progress["held"]
              and not (plan["state"] == "daily_priority" and daily_advancing)):
            issues.append(name + "の作業が1時間以上未完了")
    detail = " ／ ".join((["要確認　" + "・".join(issues)] if issues else []) + details)
    written = c.execute(
        """INSERT INTO health(name,state,detail,checked_at) VALUES ('collection_progress',%s,%s,now())
           ON CONFLICT(name) DO UPDATE SET state=excluded.state,detail=excluded.detail,checked_at=excluded.checked_at
           WHERE health.checked_at<date_trunc('hour',now()) RETURNING checked_at""",
        ("failed" if issues else "ok", detail),
    ).fetchone()
    if written:
        print("collection_progress " + detail, flush=True)


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
    with connect() as c:
        record_hourly_progress(c)
