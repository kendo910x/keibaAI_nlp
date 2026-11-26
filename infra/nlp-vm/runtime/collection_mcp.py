"""Tools attached to both the usual Hermes CLI and the native Cron platform."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import fcntl
import inspect
import os
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from discovery import MEDIA, card, horse_route, media_route
from jobs import JST, daily, run, status
from research import ROOT, capture, interpret as independent, search
from routes import capture_url, collect, excerpt, listing, roster_page, seeds
from run import in_worker


def horse_news(name: str, year: str = "", source: str = "net", limit: int = 3) -> dict:
    """Search one horse on net (netkeiba) or blog (山口吉野). Save up to limit public articles and return IDs."""
    if source not in ("net", "blog") or not name.strip() or not 1 <= limit <= 8:
        raise ValueError("choose a horse, source and 1..8")
    target = {"name": name}
    if year:
        target.update(first=year + "0101", last=year + "1231")
    return horse_route(target, source, limit)


def media_news(source: str, day: str, limit: int) -> dict:
    """Read a public news list for radio, book, hochi or daily. Use an ISO day; radio supports past months."""
    if source not in MEDIA or not 1 <= limit <= 20:
        raise ValueError("choose a supported source and 1..20")
    return media_route({"source": source, "day": day, "limit": limit})


def daily_prepare(sources: list[str], review: bool = True) -> dict:
    """Create the morning plan. For finite trials use review=true. Production is enabled by the operator's Cron environment."""
    if not review:
        jobfile = Path("/opt/data/cron/jobs.json")
        jobs = json.loads(jobfile.read_text())["jobs"] if jobfile.exists() else []
        if not any(
            j.get("name") == "keiba-morning" and j.get("enabled", True) for j in jobs
        ):
            raise ValueError(
                "The production morning schedule is not registered or enabled"
            )
    return status(
        daily(
            datetime.now(JST).date().isoformat(),
            "review" if review else "operation",
            sources,
        )
    )


def plan_step(plan_id: str, count: int = 1) -> dict:
    """Process the next one to ten saved targets of an existing daily plan. Read its durable position afterwards."""
    p = status(plan_id)
    if p["kind"] != "daily" or not 1 <= count <= 10:
        raise ValueError("choose a daily plan and 1..10 targets")
    return run(plan_id, count)


def plan_status(plan_id: str) -> dict:
    """Read saved progress from a prior session."""
    return status(plan_id)


def race_roster(
    date_yyyymmdd: str, venue_code: str, race_no: int, stage: str = "result"
) -> dict:
    """Read a public registration, entries or result roster for a JRA date, two-digit venue and race number."""
    if not 1 <= race_no <= 12 or stage not in ("registration", "entries", "result"):
        raise ValueError("choose a JRA race number 1..12 and supported stage")
    found = card({"key": date_yyyymmdd + venue_code + f"{race_no:02d}", "stage": stage})
    return (
        {**found, "horses": seeds(found["roster"], limit=32)["horses"]}
        if found["count"]
        else found
    )


async def interpret(capture_id: str, fresh: bool = False) -> dict:
    """Read one previously saved body and its date label through the independent local model."""
    with (ROOT / "local-model.lock").open("a") as lock:
        if os.environ.get("KEIBA_MODEL_RESERVED") != "1":
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "model_busy", "capture_id": capture_id}
        return await independent(capture_id, fresh)


if __name__ == "__main__":
    server = FastMCP("keiba-collection")
    with ThreadPoolExecutor(max_workers=1) as pool:
        for fn in (
            horse_news,
            media_news,
            daily_prepare,
            plan_step,
            plan_status,
            race_roster,
            search,
            capture,
            listing,
            collect,
            capture_url,
            excerpt,
            seeds,
            roster_page,
            interpret,
        ):
            server.tool()(
                fn if inspect.iscoroutinefunction(fn) else in_worker(fn, pool)
            )
        server.run()
