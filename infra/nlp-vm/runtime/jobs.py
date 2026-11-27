"""Finite plans and durable cursors. The caller chooses the plan; there is no automatic start."""

import argparse
from contextlib import contextmanager
import asyncio
import fcntl
import gzip
import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

import discovery
import raw_control
import raw_pages
from corpus import connect
from research import ROOT, digest, interpret, interpretation_config, read, require_interpretation
from routes import capture_url, collect, history_roster_file

JST = ZoneInfo("Asia/Tokyo")
TERMINAL = ("done", "partial", "failed")


def create(kind, label, scope, targets, definition, owner="cli", ident=None):
    if kind == "interpret":
        require_interpretation()
    ident = ident or str(uuid.uuid4())
    with connect() as c:
        if kind in ("history","daily"):
            c.execute("SELECT singleton FROM collection_control FOR SHARE")
            if not raw_control.allowed(c,kind):
                raise ValueError("Collection is stopped")
        inserted = c.execute(
            """INSERT INTO plans(id,kind,label,scope,state,input,owner)
          VALUES (%s,%s,%s,%s,'queued',%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
            (ident, kind, label, scope, Jsonb(definition), owner),
        ).fetchone()
        if inserted:
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO work_items(plan_id,position,target) VALUES (%s,%s,%s)",
                    ((ident, i, Jsonb(t)) for i, t in enumerate(targets)),
                )
    return str(ident)


def status(ident):
    with connect() as c:
        p = c.execute(
            "SELECT id,kind,label,scope,state,started_at,updated_at,ended_at,stop_requested,error FROM plans WHERE id=%s",
            (ident,),
        ).fetchone()
        if not p:
            raise ValueError("unknown plan")
        counts = c.execute(
            "SELECT state,count(*) n FROM work_items WHERE plan_id=%s GROUP BY state",
            (ident,),
        ).fetchall()
        nxt = c.execute(
            "SELECT position,target FROM work_items WHERE plan_id=%s AND state IN ('queued','working') ORDER BY position LIMIT 1",
            (ident,),
        ).fetchone()
    return {**p, "items": {r["state"]: r["n"] for r in counts}, "next": nxt}


def history(limit=None, year=None, source="net", media=(), media_only=False):
    content = history_roster_file().read_bytes()
    data = json.loads(gzip.decompress(content))
    horses = [h for h in data["horses"] if not year or year in h["years"]]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        horses = horses[:limit]
    work = (
        [] if media_only else [{"type": "horse", "source": source, **h} for h in horses]
    )
    if not limit and not media and not media_only:
        media = tuple(discovery.MEDIA)
    seeds = []
    years = sorted({y for h in horses for y in h["years"]}, reverse=True)
    for site in media:
        if site not in discovery.MEDIA:
            raise ValueError(site)
        if site != "radio":
            seeds.append(
                {
                    "type": "media",
                    "source": site,
                    "day": datetime.now(JST).date().isoformat(),
                    "limit": 20,
                }
            )
            continue
        for y in years:
            for month in range(12, 0, -1):
                day = date(int(y), month, 1)
                if day <= date.today():
                    seeds.append(
                        {
                            "type": "media",
                            "source": site,
                            "day": day.isoformat(),
                            "limit": 20,
                        }
                    )
    # Expose both horse names and all media at startup, including the current archive month.
    seeds.sort(key=lambda t: (t["day"][:7] != datetime.now(JST).strftime("%Y-%m"), t["source"]))
    work = [v for pair in zip(work[:len(seeds)],seeds) for v in pair] + seeds[len(work):] + work[len(seeds):]
    definition = {
        "roster": "history-jra",
        "roster_size": len(data["horses"]),
        "sha256": hashlib.sha256(content).hexdigest(),
        "horses": 0 if media_only else len(horses),
        "year": year,
        "start": data.get("start"),
        "end": data.get("end"),
        "media": list(media),
        "source": source,
    }
    ident = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "keiba-history/" + json.dumps(definition, sort_keys=True),
        )
    )
    return create(
        "history",
        "JRA出走履歴からの過去記事探索",
        "bounded" if limit else "operation",
        work,
        definition,
        ident=ident,
    )


def coverage(path):
    sample = json.loads(path.read_bytes())
    work = []
    for race in sample["races"]:
        for h in race["horses"]:
            work.append(
                {
                    "type": "horse",
                    "source": "net",
                    **h,
                    "day": race["day"],
                    "race": race["race"],
                    "group": race["key"],
                }
            )
    work.extend(
        {"type": "horse", "source": "net", "group": "aux", **h} for h in sample["aux"]
    )
    primary = list(work)
    for race in sample["races"]:
        work.append(
            {
                "type": "media",
                "source": "radio",
                "race_key": race["key"],
                "day": race["day"],
                "no": race["no"],
                "venue": race["venue"],
                "grade": race["grade"],
                "race": race["race"],
                "limit": 8,
            }
        )
    work.extend({**h, "source": "blog", "limit": 2} for h in primary)
    return create(
        "coverage",
        "開始前調査・13競走と名簿抽出馬",
        "review",
        work,
        {
            "selection": sample["selected"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "races": len(sample["races"]),
            "aux": len(sample["aux"]),
            "primary": len(primary),
        },
        owner="server-survey",
    )


def daily(
    day,
    scope="operation",
    sources=None,
    name_budget=None,
):
    on = date.fromisoformat(day)
    sources = sources or tuple(discovery.MEDIA)
    if not sources or any(s not in discovery.MEDIA for s in sources):
        raise ValueError("choose supported media")
    if scope == "review":
        offsets = [
            -((on.weekday() - 6) % 7),
            (5 - on.weekday()) % 7,
            (6 - on.weekday()) % 7,
        ]
    else:
        offsets = range(-7, 7)
    work = [
        {"type": "calendar", "day": (on + timedelta(days=i)).isoformat()}
        for i in sorted(set(offsets))
    ]
    calendars = work
    work = list(
        {
            "type": "media",
            "day": day,
            "source": s,
            "limit": 2 if scope == "review" else 16,
            "revisit": "updates",
        }
        for s in sources
    )
    work.extend(calendars)
    if scope == "operation" and "radio" in sources:
        with connect() as c:
            last = c.execute("""SELECT max(data->>'day') AS day FROM observations WHERE family='listings'
                 AND data->>'channel'='radio/' AND data->>'status'='ok' AND data->>'day'<%s""",(day,)).fetchone()["day"]
        start = min(date.fromisoformat(last), on-timedelta(days=8)) if last else on-timedelta(days=8)
        month = start.replace(day=1)
        while month < on.replace(day=1):
            work.append(dict(type="media", source="radio", day=month.isoformat(),limit=16))
            month = (month + timedelta(days=32)).replace(day=1)
    uid = (
        str(uuid.uuid5(uuid.NAMESPACE_URL, "keiba-nlp/daily/" + day))
        if scope == "operation"
        else None
    )
    return create(
        "daily",
        day + " の開催と新着",
        scope,
        work,
        {
            "day": day,
            "sources": list(sources),
            "name_budget": 2 if scope == "review" else name_budget,
        },
        "hermes",
        uid,
    )


def pending_captures(limit, cooldown=False):
    # Pick the first capture bearing the most recent nonempty publication label for each version.
    # A date correction can reopen the input; a Skill/settings change alone must not
    # schedule the entire successful corpus again. Explicit capture IDs still use
    # the current Skill/settings when an operator requests a bounded reinterpretation.
    skill, settings = interpretation_config()
    with connect() as c:
        rs = c.execute(
            """SELECT cap.id FROM versions v
            JOIN LATERAL (SELECT evidence->>'published_label' d FROM captures WHERE version_id=v.id
              ORDER BY nullif(evidence->>'published_label','') IS NOT NULL DESC,observed_at DESC,id LIMIT 1) latest ON true
            JOIN LATERAL (SELECT id FROM captures WHERE version_id=v.id
              AND (evidence->>'published_label') IS NOT DISTINCT FROM latest.d ORDER BY observed_at,id LIMIT 1) cap ON true
            WHERE NOT EXISTS(SELECT FROM interpretations i WHERE i.capture_id=cap.id AND i.input_key IS NOT NULL
              AND i.evidence->>'input_format'='article-date-v1'
              AND (i.status='ok' OR (%s AND i.skill_hash=%s AND i.evidence->'settings'=%s
                AND i.observed_at>now()-interval '1 day')))
            ORDER BY v.observed_at DESC,v.id LIMIT %s""",
            (cooldown, digest(skill), Jsonb(settings), limit),
        ).fetchall()
    return [r["id"] for r in rs]


def interpretation(captures=None, limit=None, scope="bounded"):
    require_interpretation()
    if captures is None:
        captures = pending_captures(limit)
    return create(
        "interpret",
        "保存本文の独立解釈",
        scope,
        [{"type": "interpret", "capture": k} for k in captures],
        {"count": len(captures)},
    )


def execute(target, p, *, recover_orphan=False):
    typ = target["type"]
    more = []
    production = p["scope"] == "operation" and p["kind"] in ("history","daily")
    if production and typ in ("horse","media","page"):
        return raw_pages.page_step(target,p)
    if typ == "horse":
        r = discovery.horse_route(
            target, target.get("source", "net"), target.get("limit", 4)
        )
    elif typ == "selected_article":
        hit = capture_url(target["name"], target["url"], target["title"])
        good = hit["status"] in ("ok", "partial")
        r = {
            "route_status": hit["status"],
            "retry_after": hit.get("retry_after"), "service_failure": hit.get("service_failure",False),
            "hits": [hit],
            "saved": int(good and not hit["known"]),
            "known": int(hit["known"]),
            "failed": int(not good and hit["status"] != "metadata_only"),
        }
    elif typ == "media":
        r = discovery.media_route(target)
        if (
            p["kind"] == "history"
            and r["candidate_count"] > len(r["hits"])
            and not r["failed"]
        ):
            more.append(
                {
                    "type": "listing",
                    "listing_id": r["observations"][0],
                    "offset": len(r["hits"]),
                    "source": target["source"],
                    "day": target["day"],
                }
            )
    elif typ == "listing":
        b = collect(target["listing_id"], target["offset"], target.get("limit",20),
                    revisit="updates" if production and p["kind"]=="daily" else False,
                    stop_check=(lambda: raw_control.stopped(p["id"])) if production else None)
        batch = read("batches", b["batch_id"])
        n = b["counts"]
        r = {
            "route_status": "ok",
            "saved": n.get("ok", 0) + n.get("partial", 0),
            "known": n.get("known", 0),
            "links_only": n.get("metadata_only", 0),
            "failed": sum(
                v
                for k, v in n.items()
                if k not in ("known", "ok", "partial", "metadata_only")
            ),
            "hits": batch["results"],
            "observations": [b["batch_id"]],
            "next_offset": b["next_offset"],
            "retry_after": b["retry_after"],
        }
        if production:
            r.update(deferred=b.get("deferred"), retry_after=b.get("retry_after"), service_failure=b.get("service_failure",False))
            r["stopped_before_batch"] = b.get("stopped") and b["next_offset"] == target["offset"]
            if r["deferred"]:
                r["failed"] -= 1
        if b["remaining"] and b["next_offset"] > target["offset"] and (production or not r["failed"]):
            more.append({**target, "offset": b["next_offset"], "queue_key": f"slice/{target['listing_id']}/{b['next_offset']}"})
    elif typ == "interpret":
        # Shared with the native Cron invocation. Separate processes cannot claim this GPU slot at once.
        options = {}
        if p["scope"] == "saved_versions":
            options = dict(expected_version=target["version"], required_result=target.get("reuse_id"),
                           configuration=p["input"]["configuration"], recover_orphan=recover_orphan)
        with (ROOT / "local-model.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            outcome = asyncio.run(interpret(target["capture"], **options))
        return {
            "route_status": outcome["status"],
            "failed": int(outcome["status"] != "ok"),
            "reused": int(bool(outcome.get("reused"))),
            "interpreted": int(outcome["status"] == "ok" and not outcome.get("reused")),
            "interpretation": outcome.get("interpretation_id"),
            "error": outcome.get("error"),
            "service_failure": outcome.get("service_failure", False),
        }, []
    elif typ == "calendar":
        listing = discovery.calendar(date.fromisoformat(target["day"]))
        keys = list(listing["races"])
        if p["scope"] == "review" and keys:
            feature = next(
                (k for k in keys if "ジャパン" in listing["races"][k]), keys[-1]
            )
            keys = [keys[1] if len(keys) > 1 else keys[0], feature]
        for k in dict.fromkeys(keys):
            past = target["day"] < p["input"]["day"]
            stages = ("result",) if past else ("registration", "entries")
            for stage in stages:
                more.append(
                    {
                        "type": "card",
                        "stage": stage,
                        "key": k,
                        "race": listing["races"][k],
                    }
                )
        r = {
            "route_status": "ok" if keys else "no_matching_links",
            "races": len(keys),
            "url": listing["url"],
        }
    elif typ == "card":
        r = discovery.card(target, p["scope"], p["created_at"])
        for name in r["names"] if production else r["added"]:
            more.append(
                {
                    "type": "horse",
                    "name": name,
                    "source": "net",
                    "race": target["race"],
                    "day": target["key"][:8],
                    "origin": target["key"], "stage": target["stage"],
                    "limit": 2,
                }
            )
    else:
        raise ValueError("unknown work type")
    return r, more


def add_targets(c, p, targets):
    if not targets:
        return
    if p["scope"] == "saved_versions":
        raise ValueError("Cannot append to a frozen version list")
    ident = p["id"]
    c.execute("SELECT id FROM plans WHERE id=%s FOR UPDATE", (ident,))
    pos = c.execute(
        "SELECT coalesce(max(position),-1)+1 n FROM work_items WHERE plan_id=%s",
        (ident,),
    ).fetchone()["n"]
    for target in targets:
        if target["type"] == "horse" and not target.get("decision"):
            budget = p["input"].get("name_budget")
            if c.execute("""SELECT 1 FROM work_items WHERE plan_id=%s AND target->>'type'='horse'
                    AND target->>'name'=%s AND NOT (target ? 'decision') LIMIT 1""",(ident,target["name"])).fetchone():
                continue
            if budget is not None and c.execute("SELECT count(*) n FROM work_items WHERE plan_id=%s AND target->>'type'='horse' AND NOT (target ? 'decision')",(ident,)).fetchone()["n"] >= budget:
                continue
        c.execute(
            "INSERT INTO work_items(plan_id,position,target) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (ident, pos, Jsonb(target)),
        )
        pos += 1


def request_stop(ident):
    with connect() as c:
        c.execute(
            """UPDATE plans SET stop_requested=true,state=CASE WHEN state='running' THEN state ELSE 'paused' END,
               updated_at=now() WHERE id=%s AND state IN ('running','queued','paused','waiting')""",
            (ident,),
        )
    return status(ident)


@contextmanager
def plan_actor(plan):
    before = os.environ.get("KEIBA_RESEARCH_ACTOR")
    if plan["kind"] == "coverage":
        os.environ["KEIBA_RESEARCH_ACTOR"] = "server-survey"
    elif plan["scope"] == "saved_versions":
        os.environ["KEIBA_RESEARCH_ACTOR"] = "saved-articles/" + str(plan["id"])
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("KEIBA_RESEARCH_ACTOR", None)
        else:
            os.environ["KEIBA_RESEARCH_ACTOR"] = before


def resume(ident):
    with connect() as c:
        c.execute(
            """UPDATE plans SET stop_requested=false,state='queued',updated_at=now()
                     WHERE id=%s AND state IN ('queued','paused')""",
            (ident,),
        )
    return status(ident)


def retry_failed(ident):
    with connect() as c:
        p = c.execute("SELECT * FROM plans WHERE id=%s", (ident,)).fetchone()
        if not p or p["state"] not in TERMINAL:
            raise ValueError("choose a finished plan")
        if p["scope"] == "saved_versions":
            raise ValueError("Keep the fixed version inventory and its outcomes in the original plan")
        targets = [
            r["target"]
            for r in c.execute(
                """SELECT target FROM work_items WHERE plan_id=%s
                AND state IN ('failed','partial') ORDER BY position""",
                (ident,),
            )
        ]
    if not targets:
        raise ValueError("no failed work to retry")
    return create(
        p["kind"],
        p["label"] + "・失敗分の再試行",
        p["scope"],
        targets,
        {**p["input"], "retry_of": str(ident)},
    )


def run(ident, steps=None, respect_stop=False):
    if steps is not None and steps < 1:
        raise ValueError("steps must be positive")
    with connect() as c:
        c.autocommit = True
        if not c.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) acquired",
            (str(ident),),
        ).fetchone()["acquired"]:
            return {"state": "already_running", "id": str(ident)}
        p = c.execute("SELECT * FROM plans WHERE id=%s", (ident,)).fetchone()
        if not p:
            raise ValueError("unknown plan")
        fixed = p["scope"] == "saved_versions"
        collecting = p["kind"] in ("history","daily")
        if p["kind"] == "interpret":
            require_interpretation()
        if collecting and not raw_control.allowed(c,p["kind"],p):
            return status(ident)
        if p["state"] in TERMINAL:
            return status(ident)
        started = c.execute(
            """UPDATE plans SET state='running',started_at=coalesce(started_at,now()),ended_at=NULL,
               updated_at=now() WHERE id=%s AND NOT stop_requested""",
            (ident,),
        )
        if not started.rowcount:
            return status(ident)
        n = 0
        while True:
            stop = c.execute(
                "SELECT stop_requested FROM plans WHERE id=%s", (ident,)
            ).fetchone()["stop_requested"]
            if stop or (collecting and not raw_control.allowed(c,p["kind"])):
                c.execute("UPDATE plans SET state='paused',updated_at=now() WHERE id=%s", (ident,))
                break
            priority = "position"
            if p["kind"] == "interpret" and p["scope"] == "finite":
                # Alternate source plans while both have pending versions, including late arrivals.
                priority = """(SELECT count(*) FROM work_items done WHERE done.plan_id=w.plan_id
                    AND done.state IN ('done','failed','partial') AND done.target->>'origin'=w.target->>'origin'), position"""
            if collecting:
                eligible = """SELECT * FROM work_items w WHERE plan_id=%s AND state IN ('queued','working')
                    AND (ready_at IS NULL OR ready_at<=now()) AND NOT EXISTS
                    (SELECT FROM route_waits h WHERE h.source IN ('*',w.target->>'source') AND h.retry_at>now())"""
                # Spend most turns consuming already discovered pages, while regularly starting roster seeds.
                lane = " AND (target ? 'queue_key')" if n % 5 else ""
                item = c.execute(eligible + lane + " ORDER BY position LIMIT 1",(ident,)).fetchone()
                if not item and lane:
                    item = c.execute(eligible+" ORDER BY position LIMIT 1",(ident,)).fetchone()
            else:
                item = c.execute("SELECT * FROM work_items w WHERE plan_id=%s AND state IN ('queued','working') ORDER BY "
                                 +priority+" LIMIT 1",(ident,)).fetchone()
            if not item:
                if collecting and c.execute("SELECT 1 FROM work_items WHERE plan_id=%s AND state IN ('queued','working') LIMIT 1",(ident,)).fetchone():
                    c.execute("UPDATE plans SET state='waiting' WHERE id=%s",(ident,))
                    if steps is not None:
                        break
                    time.sleep(15)
                    continue
                counts = c.execute(
                    """SELECT count(*) FILTER(WHERE state='done') ok,count(*) FILTER(WHERE state='failed') bad,
                  count(*) FILTER(WHERE state='partial') partial FROM work_items WHERE plan_id=%s""",
                    (ident,),
                ).fetchone()
                state = (
                    "failed"
                    if counts["bad"] and not counts["ok"] and not counts["partial"]
                    else ("partial" if counts["bad"] or counts["partial"] else "done")
                )
                finished = c.execute(
                    """UPDATE plans SET state=%s,ended_at=now(),updated_at=now() WHERE id=%s
                    AND NOT EXISTS(SELECT FROM work_items WHERE plan_id=plans.id AND state IN ('queued','working'))""",
                    (state, ident),
                )
                if not finished.rowcount:
                    continue
                break
            if steps is not None and n >= steps:
                c.execute(
                    "UPDATE plans SET state=%s,updated_at=now() WHERE id=%s",
                    ("queued" if collecting else "paused",ident),
                )
                break
            if (
                p["kind"] in ("history", "interpret")
                and p["scope"] != "finite"
                and c.execute(
                    """SELECT 1 FROM plans d WHERE kind='daily' AND state='running' AND NOT stop_requested AND EXISTS
                    (SELECT FROM pg_locks l WHERE l.locktype='advisory' AND l.objid=(hashtextextended(d.id::text,0)&4294967295)::oid) LIMIT 1"""
                ).fetchone()
            ):
                time.sleep(3)
                continue
            pos = item["position"]
            c.execute(
                "UPDATE work_items SET state='working',updated_at=now() WHERE plan_id=%s AND position=%s",
                (ident, pos),
            )
            c.execute("UPDATE plans SET state='running',updated_at=now() WHERE id=%s", (ident,))
            try:
                if collecting and shutil.disk_usage(ROOT).free < 512 * 1024**2:
                    raise OSError("Insufficient disk space to save a collection unit")
                with plan_actor(p):
                    interrupted = item["state"] == "working" or bool((item["result"] or {}).get("service_failure"))
                    result, more = execute(item["target"], p, recover_orphan=fixed and interrupted)
                bad = result.get("route_status") not in (
                    "ok",
                    "partial",
                    "no_matching_links",
                    "metadata_only",
                )
                if bad and not result.get("failed"):
                    result["failed"] = 1
                if (
                    result.get("failed")
                    and "hits" in result
                    and not any(result.get(k) for k in ("saved", "known", "links_only"))
                ):
                    bad = True
                state = (
                    "failed" if bad else ("partial" if result.get("failed") else "done")
                )
            except Exception as e:
                result, more, state = (
                    {"error": f"{type(e).__name__}: {e}"[:550], "route_status": str(e) or type(e).__name__,
                     "retry_after": getattr(e,"retry_after",None), "failed": 1,
                     "service_failure": fixed or (collecting and not isinstance(e, discovery.Unavailable))},
                    [],
                    "failed",
                )
            pause = fixed and result.get("service_failure", False)
            if fixed:
                attempts = list((item["result"] or {}).get("attempts", []))
                generated = result.get("interpretation")
                if generated and not result.get("reused") and generated not in attempts:
                    attempts.append(generated)
                result["attempts"] = attempts
                if pause:
                    state = "queued" if len(attempts) < 2 else "failed"
            with c.transaction():
                if collecting and result.get("stopped_before_batch"):
                    state = "queued"
                deferred = result.get("deferred") or result.get("route_status")
                if collecting and (result.get("service_failure") or deferred in ("http_429","http_503","cooldown")):
                    from routes import retry_seconds
                    seconds = retry_seconds(result.get("retry_after"),300 if result.get("service_failure") else 90)
                    source = "*" if result.get("service_failure") else item["target"].get("source","calendar")
                    c.execute("""INSERT INTO route_waits VALUES (%s,now()+%s*interval '1 second',%s)
                       ON CONFLICT(source) DO UPDATE SET retry_at=greatest(route_waits.retry_at,excluded.retry_at),reason=excluded.reason""",
                       (source,seconds,result.get("error") or deferred))
                    if not more:
                        state = "queued"
                        c.execute("UPDATE work_items SET ready_at=now()+%s*interval '1 second' WHERE plan_id=%s AND position=%s",(seconds,ident,pos))
                    elif not result.get("failed"):
                        state = "done"
                add_targets(c, p, more)
                c.execute(
                    "UPDATE work_items SET state=%s,result=%s,updated_at=now() WHERE plan_id=%s AND position=%s",
                    (state, Jsonb(result), ident, pos),
                )
                c.execute(
                    "UPDATE plans SET updated_at=now(),error=CASE WHEN %s='failed' THEN %s ELSE error END WHERE id=%s",
                    (state, result.get("error") or result.get("route_status"), ident),
                )
                if pause:
                    c.execute(
                        "UPDATE plans SET state='paused',stop_requested=true,error=%s WHERE id=%s",
                        (result["error"], ident),
                    )
            if pause:
                break
            n += 1
    return status(ident)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("history")
    h.add_argument("--limit", type=int)
    h.add_argument("--year")
    h.add_argument("--media", action="append", choices=discovery.MEDIA)
    h.add_argument("--source", choices=("net", "blog"), default="net")
    h.add_argument("--media-only", action="store_true")
    v = sub.add_parser("coverage")
    v.add_argument("sample", type=Path)
    d = sub.add_parser("daily")
    d.add_argument("--day", default=datetime.now(JST).date().isoformat())
    d.add_argument("--review", action="store_true")
    i = sub.add_parser("interpret")
    i.add_argument("--capture", action="append")
    i.add_argument("--limit", type=int)
    for name in ("run", "status", "stop", "resume", "retry-failed"):
        s = sub.add_parser(name)
        s.add_argument("id")
        if name == "run":
            s.add_argument("--steps", type=int)
            s.add_argument("--respect-stop", action="store_true")
    a = p.parse_args()
    if a.cmd == "history":
        value = history(
            a.limit,
            a.year,
            a.source,
            a.media or (("radio",) if a.media_only else ()),
            a.media_only,
        )
    elif a.cmd == "coverage":
        value = coverage(a.sample)
    elif a.cmd == "daily":
        value = daily(a.day, "review" if a.review else "operation")
    elif a.cmd == "interpret":
        if not a.limit and not a.capture:
            p.error("choose --capture or --limit for a finite plan")
        value = interpretation(a.capture, a.limit)
    elif a.cmd == "run":
        value = run(a.id, a.steps, a.respect_stop)
    elif a.cmd == "resume":
        value = resume(a.id)
    elif a.cmd == "retry-failed":
        value = retry_failed(a.id)
    elif a.cmd == "stop":
        value = request_stop(a.id)
    else:
        value = status(a.id)
    print(
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=str)
    )


if __name__ == "__main__":
    main()

