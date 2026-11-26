"""Operator-started workers. Daily plans are created only by an authorized native Cron task."""

import argparse
import time
from corpus import connect
from jobs import interpretation, pending_captures, run
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("daily", "interpret", "stop-interpret"))
    a = parser.parse_args()
    if a.action == "daily":
        for ident in outstanding("daily"):
            run(str(ident))
    elif a.action == "interpret":
        interpreter()
    else:
        (ROOT / "interpret.stop").touch()
