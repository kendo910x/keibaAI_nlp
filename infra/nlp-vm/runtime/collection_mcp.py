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
from corpus import connect
from jobs import JST, add_targets, daily, history, run, status
from profile_db import trial
from plan_sources import PlanSession
from raw_control import check_plan
from research import ROOT, capture, collection_policy, interpret as independent, read, require_interpretation, search
from routes import capture_url, collect, excerpt, listing, roster_page, seeds
from run import in_worker

session = PlanSession()


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


def trial_request():
    return json.loads(Path("/run/keiba/trial.json").read_text())


def history_prepare(
    limit: int | None = None, source: str = "net", full_roster: bool = False
) -> dict:
    """Open the authorized historical roster prefix. Return the real names and active years."""
    if trial():
        designated = trial_request()["history_limit"]
        if full_roster or limit not in (None, designated):
            raise ValueError("Use the designated trial roster size")
        limit = designated
    elif not collection_policy().get("article_interpretation",False) and (not full_roster or source!="net"):
        raise ValueError("Open the fixed production roster with full_roster=true; add other routes to that plan")
    if (
        (limit is None) != full_roster
        or (limit is not None and limit < 1)
        or source not in ("net", "blog")
    ):
        raise ValueError("Choose a positive roster size and a supported source")
    ident = history(limit, source=source)
    check_plan(ident)
    session.plan_id = ident
    with connect() as c:
        rows = c.execute(
            "SELECT target FROM work_items WHERE plan_id=%s AND target ? 'horse_id' ORDER BY position LIMIT 40",
            (ident,),
        )
        return {
            "plan_id": ident,
            "horses": [
                {k: r["target"][k] for k in ("name", "first", "last")} for r in rows
            ],
        }


def daily_prepare(sources: list[str], review: bool = False) -> dict:
    """Open the normal daily plan in this profile. The isolated one-off uses its fixed JST date."""
    day = datetime.now(JST).date().isoformat()
    if trial():
        day = trial_request()["day"]
        if review or set(sources) != set(MEDIA):
            raise ValueError(
                "The daily trial uses normal expansion and all four news lists"
            )
    elif not review:
        jobfile = Path("/opt/data/cron/jobs.json")
        jobs = json.loads(jobfile.read_text())["jobs"] if jobfile.exists() else []
        if not any(
            j.get("name") == "keiba-morning" and j.get("enabled", True) for j in jobs
        ):
            raise ValueError(
                "The production morning schedule is not registered or enabled"
            )
    session.plan_id = daily(
        day,
        "review" if review else "operation",
        sources if trial() or review else tuple(MEDIA),
    )
    return status(session.plan_id)


def plan_step(plan_id: str, count: int = 1) -> dict:
    """Process one to ten saved targets of this historical or daily plan."""
    p = status(plan_id)
    if p["kind"] not in ("history", "daily") or not 1 <= count <= 10:
        raise ValueError("choose a collection plan and 1..10 targets")
    return run(plan_id, count)


async def plan_search(plan_id: str, subject: str, query: str) -> dict:
    """Search the public web for an agent-selected horse/race and record the actual query under its plan."""
    check_plan(plan_id)
    result = await search(subject, query, 6)
    with connect() as c:
        c.execute(
            "INSERT INTO agent_searches VALUES (%s,%s,%s,%s)",
            (plan_id, result["search_id"], subject, query),
        )
    return result


def plan_follow(
    plan_id: str,
    subject: str,
    reason: str,
    source: str,
    search_id: str = "",
    number: int = 1,
    year: str = "",
) -> dict:
    """Queue the chosen web result (source=search, 1-based number), or another site search (net/blog) for this subject."""
    check_plan(plan_id)
    if not subject.strip() or not reason.strip():
        raise ValueError("Include the real horse/race and the reason for the route")
    with connect() as c:
        p = c.execute(
            "SELECT * FROM plans WHERE id=%s FOR UPDATE", (plan_id,)
        ).fetchone()
        if not p or p["kind"] not in ("history", "daily") or p["stop_requested"]:
            raise ValueError("Choose an active collection plan")
        if source == "search":
            if not c.execute(
                "SELECT 1 FROM agent_searches WHERE plan_id=%s AND search_id=%s",
                (plan_id, search_id),
            ).fetchone():
                raise ValueError("Choose this plan's search observation")
            hits = read("searches", search_id)["results"]
            if not 1 <= number <= len(hits):
                raise ValueError("Choose a returned result number")
            target = {
                "type": "selected_article",
                "name": subject,
                "source": source,
                "search_id": search_id,
                **hits[number - 1],
            }
        elif source in ("net", "blog"):
            target = {"type": "horse", "name": subject, "source": source, "limit": 3}
            if year:
                if len(year) != 4 or not year.isdecimal():
                    raise ValueError("Use a four-digit activity year")
                target.update(first=year + "0101", last=year + "1231")
        else:
            raise ValueError("Choose search, net or blog")
        target["decision"] = reason
        from psycopg.types.json import Jsonb

        if not c.execute(
            "SELECT 1 FROM work_items WHERE plan_id=%s AND target=%s",
            (plan_id, Jsonb(target)),
        ).fetchone():
            add_targets(c, p, [target])
            c.execute(
                "UPDATE plans SET state=CASE WHEN state='running' THEN state ELSE 'queued' END,ended_at=NULL,updated_at=now() WHERE id=%s",
                (plan_id,),
            )
    return {"plan_id": plan_id, "subject": subject, "route": source, "queued": True}


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
    require_interpretation()
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
        tools = (
            horse_news,
            media_news,
            history_prepare,
            daily_prepare,
            plan_search,
            plan_follow,
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
        )
        if not collection_policy().get("article_interpretation", False):
            # Unbound direct tools cannot carry a parent's stop state or save discovery lineage.
            tools = (history_prepare,daily_prepare,plan_search,plan_follow,plan_step,plan_status,excerpt,seeds)
        for fn in tools:
            if fn in (horse_news, media_news, capture, collect, capture_url):
                fn = session.track(fn)
            server.tool()(
                fn if inspect.iscoroutinefunction(fn) else in_worker(fn, pool)
            )
        server.run()
