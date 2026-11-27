"""Persistent operator intent shared by collection workers and Hermes tools."""

from corpus import connect


def controls(c):
    return c.execute("SELECT * FROM collection_control WHERE singleton").fetchone()


def allowed(c, kind, plan=None):
    flags = controls(c)
    return not (
        flags["all_paused"]
        or (kind == "history" and flags["history_paused"])
        or (plan and plan["stop_requested"])
    )


def check_plan(ident):
    with connect() as c:
        plan = c.execute(
            "SELECT kind,stop_requested FROM plans WHERE id=%s", (ident,)
        ).fetchone()
        if (
            not plan
            or plan["kind"] not in ("history", "daily")
            or not allowed(c, plan["kind"], plan)
        ):
            raise ValueError("Collection is stopped or the plan is unknown")
        return plan["kind"]


def stopped(ident):
    try:
        check_plan(ident)
    except ValueError:
        return True
    return False


def change(action):
    column = "all_paused" if action.endswith("all") else "history_paused"
    pause = action.startswith("pause")
    with connect() as c:
        c.execute(
            f"UPDATE collection_control SET {column}=%s,changed_at=now() WHERE singleton",
            (pause,),
        )
        if pause:
            c.execute(
                """UPDATE plans SET state=CASE WHEN state='running' THEN state ELSE 'paused' END,
                      updated_at=now() WHERE kind=ANY(%s) AND state IN ('queued','running','waiting','paused')""",
                (["history", "daily"] if column == "all_paused" else ["history"],),
            )
        else:
            flags = controls(c)
            kinds = (
                []
                if flags["all_paused"]
                else (["daily"] if flags["history_paused"] else ["history", "daily"])
            )
            c.execute(
                """UPDATE plans SET state='queued',updated_at=now()
                      WHERE state='paused' AND NOT stop_requested AND kind=ANY(%s)""",
                (kinds,),
            )
        return controls(c)


def progress(c, ident):
    return c.execute(
        """SELECT count(*) FILTER(WHERE target ? 'horse_id' AND target->>'type'='horse') horses,
        count(*) FILTER(WHERE target ? 'horse_id' AND target->>'type'='horse' AND state IN ('done','failed','partial')) searched,
        coalesce(sum((target->>'count')::int-(target->>'offset')::int) FILTER
          (WHERE target->>'type'='listing' AND state IN ('queued','working')),0) candidates,
        count(*) FILTER(WHERE state IN ('queued','working') AND (ready_at>now() OR EXISTS
          (SELECT FROM route_waits h WHERE h.source IN ('*',w.target->>'source') AND h.retry_at>now()))) held,
        count(*) FILTER(WHERE state IN ('failed','partial')) failures,
        coalesce(sum((result->>'saved')::int),0) saved,coalesce(sum((result->>'known')::int),0) reused,
        max(updated_at) FILTER(WHERE state IN ('done','partial','failed')) last_finished
        FROM work_items w WHERE plan_id=%s""",
        (ident,),
    ).fetchone()
