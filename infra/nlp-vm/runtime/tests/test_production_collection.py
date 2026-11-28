"""Regression tests for production stopping, page continuity and the interpretation guard."""

import asyncio
import os
import subprocess
import sys
import unittest
from uuid import uuid4
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

runtime = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(runtime))
repo = next((p for p in runtime.parents if (p / "poc/search_research").is_dir()), None)
if repo:
    sys.path.insert(0, str(repo / "poc/search_research"))
os.environ.setdefault("KEIBA_RESEARCH_DIR", "/tmp/keiba-raw-fixtures")

import jobs
import raw_pages
import research
import routes


class RawRouteTests(unittest.TestCase):
    def test_visible_navigation_and_complete_saved_candidates(self):
        root = "https://www.keibalab.jp/topics/backnumber.html"
        page = BeautifulSoup(
            '<ul class="indexContentsList"><li><a href="/topics/9/">共通欄</a></li></ul><ul class="tabList"><li><a href="/topics/1/">一</a></li><li><a href="/topics/2/">二</a></li></ul><ul class="pager"><li class="next"><a href="?page=2">NEXT »</a></li></ul>',
            "html.parser",
        )
        saved = {}

        def keep(_, data):
            saved.update(data)
            return dict(data, id="fixture-list")

        with (
            patch.object(raw_pages, "get_html", return_value=(root, page)),
            patch.object(raw_pages, "save", side_effect=keep),
        ):
            result, more = raw_pages.page_step(
                dict(type="media", source="lab", day="2026-11-28", limit=1),
                dict(id="fixture", kind="history", input={}),
            )
        self.assertEqual(len(saved["candidates"]), 2)
        self.assertEqual(
            (more[0]["count"], more[0]["offset"], more[1]["url"]),
            (2, 0, root + "?page=2"),
        )
        self.assertEqual(result["route_status"], "ok")

    @unittest.skipUnless(os.environ.get("KEIBA_RAW_TRIAL_TEST") == "1", "requires isolated PostgreSQL")
    def test_daily_pages_bridge_a_gap_since_the_previous_observation(self):
        from psycopg.types.json import Jsonb
        from corpus import connect
        from profile_db import trial

        self.assertTrue(trial())
        base = "https://www.keibalab.jp/topics/backnumber.html"
        page = BeautifulSoup(
            '<ul class="tabList"><li><a href="/topics/1/">一</a><time>2026-11-08</time></li></ul>'
            '<a rel="next" href="?page=2">次へ</a>', "html.parser"
        )
        with (
            connect() as connection,
            connection.transaction(force_rollback=True),
            patch.object(raw_pages, "get_html", return_value=(base, page)),
            patch.object(raw_pages, "save", return_value={"id": "saved-list"}),
            patch.object(raw_pages, "connect", return_value=nullcontext(connection)),
        ):
            target = dict(type="media", source="lab", day="2026-11-28", name="frontier-fixture")
            plan = dict(id="fixture", kind="daily", input={"day": target["day"]})
            _, tasks = raw_pages.page_step(target, plan)
            self.assertEqual([t["type"] for t in tasks], ["listing"])
            history = dict(channel="lab/frontier-fixture", head=True, day="2026-11-01",
                           status="ok", candidates=[{"url": base + "/older"}])
            connection.execute("INSERT INTO observations(family,id,data) VALUES ('listings',%s,%s)",
                               ("frontier-fixture", Jsonb(history)))
            _, tasks = raw_pages.page_step(target, plan)
            self.assertEqual([t["type"] for t in tasks], ["listing", "page"])

    def test_rate_limit_does_not_consume_blocked_article(self):
        items = [
            dict(url="https://example.com/" + str(n), title=str(n)) for n in range(3)
        ]
        batch = {}

        def keep(_, data):
            batch.update(data)
            return dict(data, id="batch")

        with (
            patch.object(
                routes, "read", return_value=dict(subject="馬", candidates=items)
            ),
            patch.object(routes, "known_articles", return_value={}),
            patch.object(routes, "save", side_effect=keep),
            patch.object(
                routes,
                "article",
                side_effect=[
                    dict(status="ok", id="a", final_url=items[0]["url"]),
                    dict(status="http_429", id="b", retry_after="90"),
                ],
            ),
        ):
            result = routes.collect("list", 0, 3)
        self.assertEqual(
            (
                result["next_offset"],
                result["remaining"],
                result["deferred"],
                result["retry_after"],
            ),
            (1, 2, "http_429", "90"),
        )
        self.assertEqual(len(batch["results"]), 2)

    def test_no_llm_or_interpretation_queue_in_raw_mode(self):
        with (
            patch.object(research, "SERVER", True),
            patch.object(
                research,
                "collection_policy",
                return_value={"article_interpretation": False},
            ),
            patch.object(research.httpx, "AsyncClient") as client,
        ):
            with self.assertRaisesRegex(ValueError, "保留"):
                asyncio.run(research.interpret("dummy"))
            with self.assertRaisesRegex(ValueError, "保留"):
                jobs.interpretation(["dummy"])
            client.assert_not_called()


@unittest.skipUnless(os.environ.get("KEIBA_RAW_TRIAL_TEST") == "1", "requires isolated PostgreSQL")
class CollectionMonitoringTests(unittest.TestCase):
    def test_dashboard_and_hourly_check_use_real_waits_and_completed_work(self):
        import dashboard
        import health
        import raw_control
        from corpus import connect
        from profile_db import trial

        self.assertTrue(trial())
        ident = uuid4()
        with connect() as c, c.transaction(force_rollback=True):
            c.execute("UPDATE collection_control SET all_paused=false,history_paused=false WHERE singleton")
            c.execute("""INSERT INTO plans(id,kind,label,scope,state,started_at,input,owner)
                VALUES (%s,'daily','monitor fixture','operation','running',now()-interval '2 hours','{}','test')""",
                (ident,))
            c.execute("INSERT INTO work_items(plan_id,position,target) VALUES (%s,0,'{}')", (ident,))
            self.assertEqual(raw_control.operating_status(c)[0], "ワーカー中断・再開待ち")
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(ident),))
            self.assertEqual(raw_control.operating_status(c)[0], "原文を収集中")
            c.execute("INSERT INTO route_waits VALUES ('*',now()+interval '5 minutes','fixture failure')")
            with patch.object(dashboard, "trial", return_value=False):
                html = BeautifulSoup(dashboard.home(c), "html.parser")
            field = html.find("dt", string="運転状態")
            self.assertEqual(field.find_next_sibling("dd").get_text(strip=True), "共通障害で再試行待ち")
            self.assertIn("fixture failure", html.get_text())
            health.record_hourly_progress(c)
            def observation():
                return c.execute("SELECT state,detail FROM health WHERE name='collection_progress'").fetchone()
            first = observation()
            self.assertEqual(first["state"], "failed")
            self.assertIn("共通障害", first["detail"])
            c.execute("UPDATE route_waits SET retry_at=now()-interval '1 minute' WHERE source='*'")
            health.record_hourly_progress(c)
            self.assertEqual(observation(), first)
            history = uuid4()
            c.execute("""INSERT INTO plans(id,kind,label,scope,state,input,owner)
                VALUES (%s,'history','monitor fixture','operation','waiting','{}','test')""", (history,))
            c.execute("INSERT INTO work_items(plan_id,position,target) VALUES (%s,0,'{}')", (history,))
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(history),))
            historical = next(p for p in raw_control.operating_status(c)[3] if p["id"] == history)
            self.assertEqual(historical["state"], "daily_priority")
            c.execute("UPDATE health SET checked_at=now()-interval '2 hours' WHERE name='collection_progress'")
            health.record_hourly_progress(c)
            self.assertIn("1時間以上未完了", observation()["detail"])
            c.execute("UPDATE work_items SET state='done',updated_at=now() WHERE plan_id=%s", (ident,))
            c.execute("UPDATE health SET checked_at=now()-interval '2 hours' WHERE name='collection_progress'")
            health.record_hourly_progress(c)
            self.assertEqual(observation()["state"], "ok")
            c.execute("UPDATE collection_control SET all_paused=true WHERE singleton")
            self.assertEqual(raw_control.operating_status(c)[0], "全収集を手動停止")


@unittest.skipUnless(
    os.environ.get("KEIBA_RAW_TRIAL_TEST") == "1",
    "requires the operator's empty trial database",
)
class PersistedControlTests(unittest.TestCase):
    def test_sticky_stop_same_plan_and_waiting_source(self):
        from collection_mcp import plan_step
        from corpus import connect
        from profile_db import trial
        import raw_control

        self.assertTrue(trial())
        with connect() as c:
            self.assertEqual(
                c.execute("select count(*) n from plans").fetchone()["n"], 0
            )
        ident = jobs.create(
            "history",
            "isolated control check",
            "operation",
            [dict(type="calendar"), dict(type="media", source="lab"), dict(type="media", source="book")],
            {},
        )
        jobs.request_stop(ident)
        self.assertEqual(plan_step(ident)["state"], "paused")
        cli = Path(jobs.__file__).with_name("jobs.py")
        out = subprocess.check_output(
            [sys.executable, "-B", str(cli), "run", ident], text=True
        )
        self.assertIn('"stop_requested": true', out)
        jobs.resume(ident)

        def execute(target, *_args, **_kwargs):
            return (
                dict(route_status="http_429", retry_after="90")
                if target["type"] == "calendar"
                else dict(route_status="no_matching_links")
            ), []

        with patch.object(jobs, "execute", side_effect=execute):
            self.assertEqual(plan_step(ident, 2)["state"], "waiting")
        with connect() as c:
            states = c.execute(
                "SELECT state FROM work_items WHERE plan_id=%s ORDER BY position",
                (ident,),
            ).fetchall()
            self.assertEqual([r["state"] for r in states], ["queued", "queued", "done"])
            self.assertTrue(
                c.execute(
                    "SELECT retry_at>now() AS held FROM route_waits WHERE source='lab'"
                ).fetchone()["held"]
            )
        raw_control.change("pause-all")
        self.assertEqual(plan_step(ident, 1)["state"], "paused")
        with self.assertRaisesRegex(ValueError, "stopped"):
            jobs.create("daily", "blocked", "operation", [], {})
        raw_control.change("resume-all")
        self.assertEqual(jobs.status(ident)["items"], {"done": 1, "queued": 2})
