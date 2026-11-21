# -*- coding: utf-8 -*-
"""yahoo_search_server の単体試験（実ネットワーク不使用）。

実行: .venv-yahoo-mcp/Scripts/python.exe -m unittest test_yahoo_search -v
  - 成功/失敗/0件/ブロックの判別（HTMLフィクスチャ）
  - 429処理: Retry-After尊重・未指定時既定待機・再試行1回上限・長時間待機指示で停止
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yahoo_search_server as ys  # noqa: E402

SERP_OK = """<html><body>
<a href="https://example.jp/a#:~:text=abc"><h3 class="sw-Card__titleMain">記事タイトルA</h3></a>
<div class="sw-Card__summary">抜粋Aです。</div>
<a href="https://example.jp/b"><h3 class="sw-Card__titleMain">記事タイトルB</h3></a>
<div class="sw-Card__summary">抜粋Bです。</div>
</body></html>"""
SERP_EMPTY = "<html><body>結果なし</body></html>"
SERP_BLOCK = "<html><body>ロボット確認です。captcha を入力してください</body></html>"


class FakeResp:
    def __init__(self, status=200, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}


def make_get(seq):
    """seq の順に FakeResp / Exception を返す requests.get モック。"""
    it = iter(seq)

    def _get(*a, **k):
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item
    return _get


class ParseTests(unittest.TestCase):
    def call(self, seq, query="test"):
        with mock.patch.object(ys.requests, "get", side_effect=make_get(seq)):
            return ys.yahoo_search(query)

    def test_success(self):
        out = self.call([FakeResp(200, SERP_OK)])
        self.assertIn("記事タイトルA", out)
        self.assertIn("URL: https://example.jp/a", out)
        self.assertNotIn("#:~:", out)
        self.assertIn("抜粋Aです。", out)
        self.assertIn("HTTP=200", out)

    def test_http_error(self):
        out = self.call([FakeResp(503, "")])
        self.assertIn("検索取得失敗: HTTP 503", out)

    def test_network_error(self):
        out = self.call([ys.requests.RequestException("boom")])
        self.assertIn("検索取得失敗", out)
        self.assertIn("RequestException", out)

    def test_zero_results(self):
        out = self.call([FakeResp(200, SERP_EMPTY)])
        self.assertIn("検索結果 0 件", out)

    def test_block(self):
        out = self.call([FakeResp(200, SERP_BLOCK)])
        self.assertIn("検索ブロック", out)


class RateLimitTests(unittest.TestCase):
    def call(self, seq):
        sleeps = []
        with mock.patch.object(ys.requests, "get", side_effect=make_get(seq)), \
             mock.patch.object(ys.time, "sleep", side_effect=sleeps.append):
            return ys.yahoo_search("test"), sleeps

    def test_429_retry_after_respected_then_success(self):
        out, sleeps = self.call([FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, SERP_OK)])
        self.assertIn("記事タイトルA", out)
        self.assertEqual(sleeps, [7.0])
        self.assertIn("retry=1", out)

    def test_429_no_retry_after_default_wait(self):
        out, sleeps = self.call([FakeResp(429), FakeResp(200, SERP_OK)])
        self.assertIn("記事タイトルA", out)
        self.assertEqual(sleeps, [ys.DEFAULT_WAIT_AFTER_429])

    def test_429_twice_stops(self):
        out, sleeps = self.call([FakeResp(429, headers={"Retry-After": "1"}), FakeResp(429)])
        self.assertIn("検索停止: 再試行後も429", out)
        self.assertEqual(sleeps, [1.0])  # 再試行は1回のみ

    def test_429_long_wait_stops_without_sleep(self):
        out, sleeps = self.call([FakeResp(429, headers={"Retry-After": "600"})])
        self.assertIn("検索停止", out)
        self.assertIn("上限", out)
        self.assertEqual(sleeps, [])  # 長時間待機は待たず停止

    def test_429_invalid_retry_after_falls_back_default(self):
        out, sleeps = self.call([FakeResp(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
                                 FakeResp(200, SERP_OK)])
        self.assertEqual(sleeps, [ys.DEFAULT_WAIT_AFTER_429])
        self.assertIn("記事タイトルA", out)


if __name__ == "__main__":
    unittest.main()
