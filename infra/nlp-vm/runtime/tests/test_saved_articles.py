"""Exact accepted inputs and model outage handling for a bounded saved-article pass."""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

runtime = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(runtime))
repo = next((p for p in runtime.parents if (p / "poc/search_research").is_dir()), None)
if repo:
    sys.path.insert(0, str(repo / "poc/search_research"))
os.environ.setdefault("KEIBA_RESEARCH_DIR", "/tmp/keiba-saved-tests")
import research


class FrozenInputTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        skill = folder / "skill.md"
        skill.write_text("test skill", encoding="utf-8")
        self.enterContext(patch.dict(os.environ, KEIBA_INTERPRET_SKILL=str(skill)))
        self.enterContext(patch.object(research, "ROOT", folder))
        self.enterContext(patch.object(research, "SERVER", False))
        self.article = research.save(
            "captures",
            dict(
                subject="saved",
                status="ok",
                body="body",
                version_id="a" * 64,
                published_label=None,
                observed_at="2026-11-27T00:00Z",
            ),
        )
        txt, settings = research.interpretation_config()
        _, _, key = research.interpretation_input(self.article, txt, settings)
        self.options = dict(
            expected_version=self.article["version_id"],
            configuration=dict(
                skill_sha256=research.digest(txt),
                endpoint=research.LLM,
                settings=settings,
            ),
        )
        self.prior = research.save(
            "interpretations", dict(status="ok", input_key=key, content='{"items":[]}')
        )

    def test_exact_accepted_empty_result_and_mismatches_never_post(self):
        with patch.object(research.httpx, "AsyncClient") as client:
            result = asyncio.run(
                research.interpret(
                    self.article["id"], required_result=self.prior["id"], **self.options
                )
            )
            self.assertEqual(
                (result["reused"], result["count"], result["interpretation_id"]),
                (True, 0, self.prior["id"]),
            )
            for options in (
                dict(required_result="b" * 32),
                dict(expected_version="changed"),
                dict(configuration={}),
            ):
                with self.assertRaises(ValueError):
                    asyncio.run(
                        research.interpret(
                            self.article["id"], **{**self.options, **options}
                        )
                    )
            client.assert_not_called()

    def test_transport_failure_is_saved_as_shared_failure(self):
        client = AsyncMock()
        client.__aenter__.return_value.post.side_effect = research.httpx.ConnectError(
            "endpoint unavailable"
        )
        with patch.object(research.httpx, "AsyncClient", return_value=client):
            result = asyncio.run(
                research.interpret(self.article["id"], fresh=True, **self.options)
            )
        self.assertTrue(result["service_failure"])
        self.assertEqual(result["status"], "interpretation_failed")

    def test_resume_recovers_this_plans_success_after_json_write(self):
        actor = "saved-articles/test-plan"
        with patch.dict(os.environ, KEIBA_RESEARCH_ACTOR=actor):
            saved = research.save("interpretations", {
                "status": "ok", "input_key": self.prior["input_key"], "capture_id": self.article["id"],
                "version_id": self.article["version_id"], "content": '{"items":[]}',
            })
            with (
                patch.object(research, "SERVER", True),
                patch("corpus.input_success", return_value=None),
                patch("corpus.record") as restore,
                patch.object(research.httpx, "AsyncClient") as client,
            ):
                result = asyncio.run(research.interpret(self.article["id"], recover_orphan=True, **self.options))
            self.assertEqual(result["interpretation_id"], saved["id"])
            self.assertTrue(result["reused"])
            restore.assert_called_once_with("interpretations", saved)
            client.assert_not_called()
