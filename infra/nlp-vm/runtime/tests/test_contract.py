"""Small regressions for the dated input, archived race attribution and public access policy."""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
repo = next((p for p in HERE.parents if (p / "poc/search_research").is_dir()), None)
if repo:
    sys.path.insert(0, str(repo / "poc/search_research"))
os.environ.setdefault("KEIBA_RESEARCH_DIR", "/tmp/keiba-unit-tests")
from corpus import article_day
from coverage_report import mention, phase, substantive
import research


class CoverageTests(unittest.TestCase):
    def test_dates_and_names(self):
        self.assertEqual(article_day("2026/11/26 17:10 更新"), date(2026, 11, 26))
        self.assertIsNone(article_day("10分前"))
        self.assertFalse(mention("ノヴァ", "スーパーノヴァが出走"))
        self.assertTrue(mention("ノヴァ", "ノヴァが出走"))
        body = "東京の馬場について説明。登録馬一覧\nノヴァ\nイクス"
        self.assertFalse(substantive("ノヴァ", body, mention("ノヴァ", body)))

    def test_later_article_is_not_prerace(self):
        race = {"race": "皐月賞", "day": "20210418", "venue": "06", "no": "11"}
        article = {"article_day": date(2026, 4, 15), "title": "皐月賞の追い切り"}
        self.assertIsNone(phase(race, article, article["title"]))
        article["article_day"] = date(2021, 4, 15)
        self.assertEqual(phase(race, article, article["title"]), "pre")

    def test_resolved_race_requires_all_three_fields(self):
        item = {
            "horse": " ＡＢ ",
            "race": "東京２Ｒ",
            "venue": "東京競馬場",
            "race_no": 2,
        }
        self.assertIsNone(research.normalized_target(item)["race_key"])
        item["race_date"] = "2026-11-28"
        self.assertEqual(
            research.normalized_target(item),
            {"horse": "AB", "race": "東京２Ｒ", "race_key": "20261128/05/02"},
        )


class DateInputTests(unittest.TestCase):
    def test_legacy_and_updated_context_do_not_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            skill = root / "skill"
            skill.write_text("独立解釈", encoding="utf8")
            with (
                patch.object(research, "ROOT", root),
                patch.object(research, "SERVER", False),
                patch.dict(os.environ, {"KEIBA_INTERPRET_SKILL": str(skill)}),
            ):
                src = research.save(
                    "captures",
                    dict(
                        subject="検索語",
                        status="ok",
                        body="資料本文",
                        version_id="a" * 64,
                        observed_at="2026-11-27T00:00Z",
                        published_label="2026年11月1日 更新",
                    ),
                )
                skill_text, settings = research.interpretation_config()
                research.save(
                    "interpretations",
                    dict(
                        version_id=src["version_id"],
                        capture_id=src["id"],
                        status="ok",
                        content='{"items":[]}',
                        settings=settings,
                        skill_sha256=research.digest(skill_text),
                    ),
                )
                reply = MagicMock()
                reply.json.return_value = {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": '{"items":[]}'},
                        }
                    ]
                }
                client = AsyncMock()
                client.__aenter__.return_value.post.return_value = reply
                with patch.object(research.httpx, "AsyncClient", return_value=client):
                    first = asyncio.run(research.interpret(src["id"]))
                    self.assertFalse(first["reused"])
                    actual = client.__aenter__.return_value.post.call_args.kwargs[
                        "json"
                    ]["messages"][-1]["content"]
                    self.assertEqual(
                        json.loads(actual)["掲載・更新欄の表示"], src["published_label"]
                    )
                    self.assertNotIn("検索語", actual)
                    second = asyncio.run(research.interpret(src["id"]))
                    self.assertEqual(
                        first["interpretation_id"], second["interpretation_id"]
                    )
                    self.assertTrue(second["reused"])
                    changed = research.save(
                        "captures", {**src, "published_label": "2026年11月2日 更新"}
                    )
                    self.assertFalse(
                        asyncio.run(research.interpret(changed["id"]))["reused"]
                    )
                    self.assertEqual(client.__aenter__.return_value.post.await_count, 2)


if __name__ == "__main__":
    unittest.main()
