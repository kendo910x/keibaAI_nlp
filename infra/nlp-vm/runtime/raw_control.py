"""Persistent operator intent shared by collection workers and Hermes tools."""

from corpus import connect

# Calendar and race-card work belongs to the same publisher as its news route.
# Independently chosen web results may come from unrelated hosts.
WAIT_SOURCE_SQL = """CASE WHEN w.target->>'type'='selected_article'
    THEN lower(split_part(w.target->>'url','/',3)) ELSE coalesce(w.target->>'source','lab') END"""


def controls(c):
    return c.execute("SELECT * FROM collection_control WHERE singleton").fetchone()


def active_waits(c):
    return c.execute(
        "SELECT source,reason,retry_at FROM route_waits WHERE retry_at>now() ORDER BY retry_at"
    ).fetchall()


def has_worker(c, ident):
    """Only this database's live session lock identifies the worker for the plan."""
    return c.execute(
        """WITH k AS (SELECT hashtextextended(%s,0) h)
        SELECT EXISTS(SELECT FROM pg_locks,k WHERE locktype='advisory' AND granted AND objsubid=1
        AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
        AND classid=((h>>32)&4294967295)::oid AND objid=(h&4294967295)::oid) active""",
        (str(ident),),
    ).fetchone()["active"]


def worker_state(c, plan):
    state = plan["state"]
    if state not in ("running", "waiting"):
        return state
    if not has_worker(c, plan["id"]):
        return "interrupted" if state == "running" else state
    if plan["kind"] != "history" or plan["scope"] != "operation" or plan["stop_requested"]:
        return state
    daily = c.execute("SELECT id FROM plans WHERE kind='daily' AND state='running' AND NOT stop_requested").fetchall()
    if any(has_worker(c, d["id"]) for d in daily):
        yielding = c.execute(
            f"""SELECT NOT EXISTS(SELECT FROM work_items WHERE plan_id=%s AND state='working')
                AND EXISTS(SELECT FROM work_items w WHERE plan_id=%s AND state='queued'
                AND (ready_at IS NULL OR ready_at<=now()) AND NOT EXISTS
                (SELECT FROM route_waits WHERE source IN ('*',{WAIT_SOURCE_SQL}) AND retry_at>now())) AS yielding""",
            (plan["id"], plan["id"]),
        ).fetchone()["yielding"]
        if yielding:
            return "daily_priority"
    return state


def operating_status(c):
    flags = controls(c)
    waits = active_waits(c)
    plans = c.execute(
        """SELECT id,kind,scope,state,stop_requested,coalesce(started_at,created_at) AS since FROM plans
        WHERE scope='operation' AND kind IN ('daily','history')
        AND state IN ('queued','running','waiting','paused') ORDER BY created_at DESC"""
    ).fetchall()
    for plan in plans:
        plan["state"] = worker_state(c, plan)
    states = {p["state"] for p in plans if not p["stop_requested"]
              and not (flags["history_paused"] and p["kind"] == "history")}
    if flags["all_paused"]:
        status = "全収集を手動停止"
    elif plans and all(p["stop_requested"] for p in plans):
        status = "収集計画を手動停止"
    elif not states:
        status = "次の収集予定を待機"
    elif any(w["source"] == "*" for w in waits):
        status = "共通障害で再試行待ち"
    elif "running" in states:
        status = "原文を収集中"
    elif "interrupted" in states:
        status = "ワーカー中断・再開待ち"
    elif "queued" in states:
        status = "作業開始待ち"
    elif "waiting" in states:
        status = "再試行待ち"
    elif "daily_priority" in states:
        status = "日次収集を優先して待機"
    else:
        status = "収集計画を一時停止"
    return status, flags, waits, plans


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
        f"""SELECT count(*) FILTER(WHERE state IN ('done','partial','failed')) AS finished,
        count(*) FILTER(WHERE state IN ('working','queued')) AS pending,
        count(*) FILTER(WHERE target ? 'horse_id' AND target->>'type'='horse') horses,
        count(*) FILTER(WHERE target ? 'horse_id' AND target->>'type'='horse' AND state IN ('done','failed','partial')) searched,
        coalesce(sum((target->>'count')::int-(target->>'offset')::int) FILTER
          (WHERE target->>'type'='listing' AND state IN ('queued','working')),0) candidates,
        count(*) FILTER(WHERE state IN ('queued','working') AND (ready_at>now() OR EXISTS
          (SELECT FROM route_waits h WHERE h.source IN ('*',{WAIT_SOURCE_SQL}) AND h.retry_at>now()))) held,
        count(*) FILTER(WHERE state IN ('failed','partial')) failures,
        coalesce(sum((result->>'saved')::int),0) saved,coalesce(sum((result->>'known')::int),0) reused,
        max(updated_at) FILTER(WHERE state IN ('done','partial','failed')) last_finished
        FROM work_items w WHERE plan_id=%s""",
        (ident,),
    ).fetchone()
