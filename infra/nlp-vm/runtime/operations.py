"""Operator-started workers. Daily plans are created only by an authorized native Cron task."""

import argparse
import json
from datetime import datetime
from pathlib import Path
import time
import uuid
from corpus import connect
from jobs import JST, TERMINAL, add_targets, create, daily, interpretation, pending_captures, run
from research import ROOT, require_interpretation
import raw_control


def outstanding(kind):
    with connect() as c:
        return [
            r["id"]
            for r in c.execute(
                """SELECT id FROM plans WHERE kind=%s AND scope='operation'
         AND state IN ('queued','running','paused','waiting') AND NOT stop_requested ORDER BY created_at DESC""",
                (kind,),
            )
        ]


def interpreter():
    require_interpretation()
    stop = ROOT / "interpret.stop"
    stop.unlink(missing_ok=True)
    while not stop.exists():
        if outstanding("daily"):
            time.sleep(8)
            continue
        ids = outstanding("interpret")
        if not ids:
            pending = pending_captures(1, cooldown=True)
            if pending:
                ids = [interpretation(pending, scope="operation")]
        if ids:
            run(str(ids[0]))
        else:
            time.sleep(10)


def finite(sources):
    """Drain only versions reached by the named collection plans, including known URLs."""
    require_interpretation()
    sources = sorted({uuid.UUID(s) for s in sources})
    if not sources:
        raise ValueError("Supply the finite collection plan IDs")
    with connect() as c:
        selected = c.execute(
            "SELECT kind FROM plans WHERE id=ANY(%s)", (sources,)
        ).fetchall()
        if len(selected) != len(sources) or any(
            p["kind"] not in ("history", "daily") for p in selected
        ):
            raise ValueError("Unknown collection plan")
    ids = [str(s) for s in sources]
    ident = str(uuid.uuid5(uuid.NAMESPACE_URL, "keiba-interpret/" + "/".join(ids)))
    create(
        "interpret",
        "指定した収集本文の独立解釈",
        "finite",
        [],
        {"sources": ids},
        ident=ident,
    )
    while True:
        with connect() as c:
            p = c.execute(
                "SELECT * FROM plans WHERE id=%s FOR UPDATE", (ident,)
            ).fetchone()
            if p["stop_requested"]:
                return
            finished = all(
                r["state"] in TERMINAL
                for r in c.execute(
                    "SELECT state FROM plans WHERE id=ANY(%s)", (sources,)
                )
            )
            fresh = c.execute(
                """SELECT DISTINCT ON (cap.version_id) cap.id,cap.version_id,h.plan_id
                FROM plan_hits h JOIN captures cap ON cap.id=h.capture_id
                WHERE h.plan_id=ANY(%s) AND cap.version_id IS NOT NULL
                  AND NOT EXISTS(SELECT FROM work_items w WHERE w.plan_id=%s AND w.target->>'version'=cap.version_id)
                ORDER BY cap.version_id, nullif(cap.evidence->>'published_label','') IS NULL, cap.observed_at,cap.id,h.plan_id""",
                (sources, ident),
            ).fetchall()
            add_targets(
                c,
                p,
                [
                    {
                        "type": "interpret",
                        "capture": r["id"],
                        "version": r["version_id"],
                        "origin": str(r["plan_id"]),
                    }
                    for r in fresh
                ],
            )
            if fresh:
                c.execute(
                    "UPDATE plans SET state='queued',ended_at=NULL,updated_at=now() WHERE id=%s",
                    (ident,),
                )
            waiting = c.execute(
                "SELECT 1 FROM work_items WHERE plan_id=%s AND state IN ('queued','working') LIMIT 1",
                (ident,),
            ).fetchone()
        if waiting:
            run(ident, steps=1, respect_stop=True)
        elif finished:
            run(ident, respect_stop=True)
            return
        else:
            time.sleep(10)


def collection_status():
    with connect() as c:
        plans = c.execute(
            """SELECT id,kind,state,stop_requested,started_at,updated_at,ended_at,error,input FROM plans
            WHERE id=(SELECT id FROM plans WHERE scope='operation' AND kind='history' ORDER BY created_at DESC LIMIT 1)
               OR id IN (SELECT id FROM plans WHERE scope='operation' AND kind='daily' ORDER BY created_at DESC LIMIT 7)
            ORDER BY kind DESC,created_at DESC"""
        ).fetchall()
        for plan in plans:
            plan.update(raw_control.progress(c, plan["id"]))
            if plan["kind"] == "history":
                plan["remaining_horses"] = plan["horses"] - plan["searched"]
        holds=c.execute("SELECT * FROM route_waits WHERE retry_at>now() ORDER BY retry_at").fetchall()
        return dict(control=raw_control.controls(c),plans=plans,holds=holds)


def daily_workers():
    while True:
        with connect() as c:
            if not raw_control.allowed(c,"daily"):
                return
        ids = outstanding("daily")
        if not ids:
            return
        for ident in ids:
            result=run(str(ident),steps=8,respect_stop=True)
            if result["state"] in ("waiting","already_running"):
                time.sleep(5)


def due_daily():
    """On recovery open today's plan once the registered native schedule is due."""
    clock = datetime.now(JST)
    config = Path("/opt/data/cron/jobs.json")
    jobs = json.loads(config.read_bytes())["jobs"] if config.is_file() else []
    morning = next((j for j in jobs if j.get("name")=="keiba-morning" and j.get("enabled")),None)
    if not morning or (clock.hour,clock.minute) < (6,40):
        return
    day = clock.date().isoformat()
    with connect() as c:
        if not raw_control.allowed(c,"daily") or c.execute(
                "SELECT 1 FROM plans WHERE kind='daily' AND scope='operation' AND input->>'day'=%s",(day,)).fetchone():
            return
    daily(day)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("daily", "due-daily","interpret", "stop-interpret", "finite", "status",
                            "pause-all","pause-history","resume-history","resume-all")
    )
    parser.add_argument("plans", nargs="*")
    a = parser.parse_args()
    if a.action == "daily":
        daily_workers()
    elif a.action == "due-daily":
        due_daily()
    elif a.action == "status":
        print(json.dumps(collection_status(),ensure_ascii=False,default=str))
    elif a.action.startswith(("pause-","resume-")):
        print(json.dumps(raw_control.change(a.action),default=str))
    elif a.action == "finite":
        finite(a.plans)
    elif a.action == "interpret":
        interpreter()
    else:
        (ROOT / "interpret.stop").touch()
