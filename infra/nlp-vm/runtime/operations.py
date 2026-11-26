"""Operator-started workers. Daily plans are created only by an authorized native Cron task."""

import argparse
import time
import uuid
from corpus import connect
from jobs import TERMINAL, add_targets, create, interpretation, pending_captures, run
from research import ROOT


def outstanding(kind):
    with connect() as c:
        return [
            r["id"]
            for r in c.execute(
                """SELECT id FROM plans WHERE kind=%s AND scope='operation'
         AND state IN ('queued','running','paused') AND NOT stop_requested ORDER BY created_at""",
                (kind,),
            )
        ]


def interpreter():
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("daily", "interpret", "stop-interpret", "finite")
    )
    parser.add_argument("plans", nargs="*")
    a = parser.parse_args()
    if a.action == "daily":
        for ident in outstanding("daily"):
            run(str(ident))
    elif a.action == "finite":
        finite(a.plans)
    elif a.action == "interpret":
        interpreter()
    else:
        (ROOT / "interpret.stop").touch()
