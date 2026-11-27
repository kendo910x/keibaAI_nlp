"""Regression tests for production stopping, page continuity and the interpretation guard."""

import asyncio
import os
import subprocess
import sys
import unittest
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
            '<ul class="indexContentsList"><li><a href="/topics/1/">一</a></li><li><a href="/topics/2/">二</a></li></ul><ul class="pager"><li class="next"><a href="?page=2">NEXT »</a></li></ul>',
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
            [dict(type="media", source="book"), dict(type="media", source="lab")],
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
                if target["source"] == "book"
                else dict(route_status="no_matching_links")
            ), []

        with patch.object(jobs, "execute", side_effect=execute):
            self.assertEqual(plan_step(ident, 2)["state"], "waiting")
        with connect() as c:
            states = c.execute(
                "SELECT state FROM work_items WHERE plan_id=%s ORDER BY position",
                (ident,),
            ).fetchall()
            self.assertEqual([r["state"] for r in states], ["queued", "done"])
            self.assertTrue(
                c.execute(
                    "SELECT retry_at>now() AS held FROM route_waits WHERE source='book'"
                ).fetchone()["held"]
            )
        raw_control.change("pause-all")
        self.assertEqual(plan_step(ident, 1)["state"], "paused")
        with self.assertRaisesRegex(ValueError, "stopped"):
            jobs.create("daily", "blocked", "operation", [], {})
        raw_control.change("resume-all")
        self.assertEqual(jobs.status(ident)["items"], {"done": 1, "queued": 1})
