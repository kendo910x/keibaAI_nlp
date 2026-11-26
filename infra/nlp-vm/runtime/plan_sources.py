"""Associate direct Hermes article tools with the active collection plan."""

import hashlib
import inspect
import json
from functools import wraps

from psycopg.types.json import Jsonb
from corpus import connect
from research import read


class PlanSession:
    """Each native stdio MCP process belongs to one Hermes session."""

    def __init__(self):
        self.plan_id = None

    def track(self, fn):
        def save_result(result, args, kwargs):
            if self.plan_id:
                params = inspect.signature(fn).bind(*args, **kwargs).arguments
                record_route(self.plan_id, fn.__name__, params, result)
            return result

        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_call(*args, **kwargs):
                return save_result(await fn(*args, **kwargs), args, kwargs)

            return async_call

        @wraps(fn)
        def sync_call(*args, **kwargs):
            return save_result(fn(*args, **kwargs), args, kwargs)

        return sync_call


def record_route(plan_id, tool, params, result):
    if tool == "collect":
        batch = read("batches", result["batch_id"])
        hits = batch["results"]
        observations = [result["batch_id"]]
    else:
        hits = result.get("hits", [result] if result.get("capture_id") else [])
        observations = result.get("observations", [])
    event = hashlib.sha256(
        json.dumps(
            [tool, params, observations, [h["capture_id"] for h in hits]],
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    target = {
        "type": "agent_route",
        "source": tool,
        "name": params.get("name")
        or params.get("subject")
        or params.get("source")
        or tool,
        "arguments": dict(params),
        "event": event,
    }
    payload = {
        "hits": hits,
        "observations": observations,
        "route_status": result.get("route_status", result.get("status", "ok")),
        "saved": sum(
            h["status"] in ("ok", "partial") and not h.get("known") for h in hits
        ),
        "known": sum(bool(h.get("known") or h["status"] == "known") for h in hits),
        "links_only": sum(h["status"] == "metadata_only" for h in hits),
        "failed": sum(
            h["status"] not in ("ok", "partial", "known", "metadata_only") for h in hits
        ),
    }
    state = "partial" if payload["failed"] else "done"
    with connect() as c:
        p = c.execute(
            "SELECT kind FROM plans WHERE id=%s FOR UPDATE", (plan_id,)
        ).fetchone()
        if not p or p["kind"] not in ("daily", "history"):
            raise ValueError("Choose a collection plan")
        c.execute(
            """INSERT INTO work_items(plan_id,position,target,state,result)
            SELECT %s,coalesce(max(position),-1)+1,%s,%s,%s FROM work_items WHERE plan_id=%s
            HAVING count(*) FILTER(WHERE target->>'event'=%s)=0""",
            (plan_id, Jsonb(target), state, Jsonb(payload), plan_id, event),
        )
