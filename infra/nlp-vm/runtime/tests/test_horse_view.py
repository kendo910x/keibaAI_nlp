"""Horse-card regressions that need neither a database nor a running model."""

import copy
import sys
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from horse_view import (
    group_horse_items,
    horse_key,
    render_horse_card,
    safe_horse_back,
)


class ParsedHTML(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    @property
    def links(self):
        return [attrs["href"] for tag, attrs in self.tags if tag == "a"]


def item(horse, text, race="ジャパンカップ", phase="pre", **fields):
    return {"horse": horse, "text": text, "race": race, "phase": phase, **fields}


def card(items=None, **fields):
    row = {
        "horse": "カランダガン",
        "items": items if items is not None else [item("カランダガン", "落ち着いて調整している。")],
        "capture_id": "capture-1",
        "version_id": "version-1",
        "title": "ジャパンカップに向けて",
        "source_url": "https://example.test/news/1?a=2&b=3",
        "host": "example.test",
        "date_label": "2026年11月26日 10:20",
        "observed_at": datetime(2026, 11, 26, 2, 0, tzinfo=timezone.utc),
        "interpretation_at": datetime(2026, 11, 27, 3, 0, tzinfo=timezone.utc),
        "partial": False,
    }
    return {**row, **fields}


class HorseGroupingTests(unittest.TestCase):
    def test_seven_fragments_across_races_and_phases_are_one_horse_group(self):
        fragments = [
            item("カランダガン", f"保存済み記述{i}。", race=race, phase=phase)
            for i, (race, phase) in enumerate(
                [
                    ("ジャパンカップ", "pre"),
                    ("ジャパンカップ", "pre"),
                    ("英チャンピオンＳ", "post"),
                    ("ジャパンカップ", "pre"),
                    (None, "unknown"),
                    ("英チャンピオンＳ", "post"),
                    ("ジャパンカップ", "mixed"),
                ],
                1,
            )
        ]
        original = copy.deepcopy(fragments)
        groups = group_horse_items(fragments, "カランダガン", exact=True)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["items"], original)
        self.assertEqual(fragments, original)

    def test_width_case_and_whitespace_variants_form_one_group(self):
        values = [item("  ＡＢ　 ", "一つ目"), item("ab", "二つ目"), item("A B", "三つ目")]
        self.assertEqual(horse_key(" Ａ　Ｂ\n"), "ab")
        groups = group_horse_items(values, "a b", exact=True)
        self.assertEqual(len(groups), 1)
        self.assertEqual([x["text"] for x in groups[0]["items"]], ["一つ目", "二つ目", "三つ目"])

    def test_exact_choice_does_not_include_a_longer_horse_name(self):
        values = [item("ノヴァ", "対象馬"), item("スーパーノヴァ", "別の馬")]
        self.assertEqual([g["horse"] for g in group_horse_items(values, "ノヴァ")], ["ノヴァ", "スーパーノヴァ"])
        self.assertEqual([g["horse"] for g in group_horse_items(values, "ノヴァ", exact=True)], ["ノヴァ"])

    def test_unknown_horse_and_empty_or_malformed_items_are_not_assigned(self):
        values = [
            None,
            "破損した項目",
            item(None, "馬の指定がない解釈"),
            item("", "空の馬名"),
            item("カランダガン", " \n "),
            item("カランダガン", None),
            item("ダノンデサイル", "他馬の解釈"),
            item("カランダガン", "対象馬の解釈"),
        ]
        groups = group_horse_items(values, "カランダガン", exact=True)
        self.assertEqual(len(groups), 1)
        self.assertEqual([x["text"] for x in groups[0]["items"]], ["対象馬の解釈"])
        self.assertEqual(group_horse_items(None), [])
        self.assertEqual(group_horse_items({"horse": "カランダガン"}), [])


class HorseCardTests(unittest.TestCase):
    def test_legacy_fragments_render_once_with_every_saved_text_and_context(self):
        values = [
            item("カランダガン", "同馬の一つ目。", "ジャパンカップ", "pre"),
            item("ダノンデサイル", "他馬の文章。"),
            item("カランダガン", "同馬の二つ目。", "英チャンピオンＳ", "post"),
        ]
        markup = render_horse_card(card(values))
        parsed = ParsedHTML(markup)
        self.assertEqual(sum(tag == "article" for tag, attrs in parsed.tags), 1)
        self.assertEqual(sum(attrs.get("class") == "horse-summary" for tag, attrs in parsed.tags), 2)
        self.assertIn("既存の分割解釈（2項目）", markup)
        self.assertIn("文章は保存時のまま", markup)
        self.assertIn("同馬の一つ目。", parsed.text)
        self.assertIn("同馬の二つ目。", parsed.text)
        self.assertNotIn("他馬の文章。", markup)
        self.assertIn("ジャパンカップ ／ 事前", parsed.text)
        self.assertIn("英チャンピオンＳ ／ 事後", parsed.text)

    def test_one_summary_is_not_labelled_as_legacy_fragments(self):
        markup = render_horse_card(card())
        self.assertNotIn("legacy-fragments", markup)
        self.assertNotIn("分割解釈", markup)
        self.assertIn("落ち着いて調整している。", markup)

    def test_missing_matching_interpretation_renders_no_fabricated_card(self):
        self.assertEqual(render_horse_card(card(items=[])), "")
        self.assertEqual(render_horse_card(card([item("別の馬", "別の解釈")])), "")

    def test_title_horse_summary_and_context_are_plain_text(self):
        horse = '<img src=x onerror="alert(1)">'
        text = '<script>alert("x")</script> & 記述'
        race = '<iframe src="javascript:alert(2)">'
        title = '<svg onload="alert(3)">見出し</svg>'
        markup = render_horse_card(card([item(horse, text, race, "post")], horse=horse, title=title))
        parsed = ParsedHTML(markup)
        self.assertFalse({"script", "img", "iframe", "svg"}.intersection(tag for tag, attrs in parsed.tags))
        self.assertTrue(all(not any(k.startswith("on") for k in attrs) for tag, attrs in parsed.tags))
        self.assertIn(horse, parsed.text)
        self.assertIn(text, parsed.text)
        self.assertIn(title, parsed.text)
        self.assertTrue(any(race in t for t in parsed.text))

    def test_source_and_dates_remain_visible(self):
        row = card(publisher="掲載媒体", partial=True)
        parsed = ParsedHTML(render_horse_card(row))
        text = "".join(parsed.text)
        self.assertIn(row["source_url"], parsed.links)
        self.assertIn("掲載媒体", text)
        self.assertIn("2026年11月26日 10:20", text)
        self.assertIn("取得 2026-11-26 11:00", text)
        self.assertIn("解釈保存 2026-11-27 12:00", text)
        self.assertIn("公開部分からの解釈", text)

    def test_unknown_dates_remain_unknown(self):
        text = "".join(ParsedHTML(render_horse_card(card(date_label=None, article_day=None, observed_at=None, interpretation_at=None))).text)
        self.assertIn("掲載・更新 不明", text)
        self.assertIn("取得 不明", text)
        self.assertIn("解釈保存 不明", text)

    def test_non_web_source_is_not_an_external_link(self):
        for source in ("javascript:alert(1)", "data:text/html,unsafe", "file:///tmp/article", "//other.example/article", "https:///article"):
            with self.subTest(source=source):
                parsed = ParsedHTML(render_horse_card(card(source_url=source)))
                self.assertNotIn(source, parsed.links)
                self.assertFalse(any(urlsplit(link).netloc for link in parsed.links))

    def test_detail_link_preserves_search_context_and_encodes_capture_identifier(self):
        back = "/horses?q=%E3%83%8E%E3%83%B4%E3%82%A1&exact=1&plan=trial-a&page=2"
        parsed = ParsedHTML(render_horse_card(card(capture_id="id/with?query"), back=back))
        detail = next(link for link in parsed.links if link.startswith("/article/"))
        self.assertEqual(urlsplit(detail).path, "/article/id%2Fwith%3Fquery")
        self.assertEqual(parse_qs(urlsplit(detail).query)["back"], [back])

    def test_return_and_horse_links_only_use_the_local_horse_view(self):
        for back in ("https://outside.example/horses", "//outside.example/horses", "javascript:alert(1)", "/runs", None):
            with self.subTest(back=back):
                self.assertEqual(safe_horse_back(back), "/horses")
                parsed = ParsedHTML(render_horse_card(card(), back=back, horse_href=back))
                detail = next(link for link in parsed.links if link.startswith("/article/"))
                self.assertEqual(parse_qs(urlsplit(detail).query)["back"], ["/horses"])
                self.assertNotIn(back, parsed.links)
        local = "/horses?q=AB&exact=1"
        self.assertEqual(safe_horse_back(local), local)
        self.assertIn(local, ParsedHTML(render_horse_card(card(), horse_href=local)).links)


class HorsePageTests(unittest.TestCase):
    """Check page presentation from result rows, not database query correctness."""

    @classmethod
    def setUpClass(cls):
        import dashboard

        cls.dashboard = dashboard

    def connection(self, *results):
        connection = MagicMock()
        cursors = []
        for rows in results:
            cursor = MagicMock()
            cursor.fetchone.return_value = rows[0] if rows else None
            cursor.fetchall.return_value = rows
            cursors.append(cursor)
        connection.execute.side_effect = cursors
        return connection

    def render(self, connection, query):
        with patch.object(self.dashboard, "trial", return_value=True):
            return ParsedHTML(self.dashboard.horses(connection, query))

    def test_empty_interpretation_search_keeps_article_and_unprocessed_routes_distinct(self):
        connection = self.connection([{"n": 0}], [], [])
        parsed = self.render(connection, {"q": "カランダガン", "match": "exact"})
        text = "".join(parsed.text)
        self.assertIn("該当する保存済みの馬別解釈はまだありません", text)
        self.assertIn("記事がないとは限りません", text)
        self.assertNotIn("この馬の記事はありません", text)
        self.assertFalse(any(tag == "article" for tag, attrs in parsed.tags))
        article_queries = [parse_qs(urlsplit(link).query) for link in parsed.links if urlsplit(link).path == "/articles"]
        self.assertIn({"q": ["カランダガン"]}, article_queries)
        self.assertIn({"stage": ["no"]}, article_queries)
        self.assertFalse(any(q.get("stage") == ["no"] and "q" in q for q in article_queries))

    def test_pagination_preserves_filters_and_clamps_to_last_page(self):
        plan = "a16db065-2244-5243-a6e3-87e3a04a9b6f"
        query = {
            "q": "カランダガン",
            "match": "exact",
            "plan": plan,
            "site": "example.test",
            "from": "2026-11-01",
            "to": "2026-11-27",
        }
        for requested, current, previous, following in ((2, 2, 1, 3), (99999, 3, 2, None)):
            with self.subTest(requested=requested):
                connection = self.connection(
                    [{"kind": "daily", "label": "日次試行"}],
                    [{"n": 41}],
                    [card()],
                    [{"host": "example.test"}],
                )
                parsed = self.render(connection, {**query, "p": str(requested)})
                self.assertIn(f"{current} / 3 ページ", "".join(parsed.text))
                page_links = [parse_qs(urlsplit(link).query) for link in parsed.links if urlsplit(link).path == "/horses" and "p" in parse_qs(urlsplit(link).query)]
                self.assertEqual({int(q["p"][0]) for q in page_links}, {previous} | ({following} if following else set()))
                for page_query in page_links:
                    for key, value in query.items():
                        self.assertEqual(page_query[key], [value])
                detail = next(link for link in parsed.links if urlsplit(link).path.startswith("/article/"))
                back = parse_qs(urlsplit(detail).query)["back"][0]
                self.assertEqual(parse_qs(urlsplit(back).query)["p"], [str(current)])
                self.assertEqual(connection.execute.call_args_list[2].args[1][-1], (current - 1) * 20)

    def test_invalid_scope_or_date_is_rejected_before_database_access(self):
        for query in ({"plan": "unrecognized-plan"}, {"from": "2026-02-31"}, {"to": "not-a-date"}):
            with self.subTest(query=query):
                connection = MagicMock()
                with self.assertRaises(ValueError):
                    self.dashboard.horses(connection, query)
                connection.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
