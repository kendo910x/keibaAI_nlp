"""Pure presentation helpers for saved horse interpretations; no model or DB access."""

import html
import unicodedata
from datetime import datetime
from urllib.parse import quote, urlencode, urlsplit
from zoneinfo import ZoneInfo


def horse_key(value):
    """Ignore width and whitespace differences without requiring an external ID."""
    if not isinstance(value, str):
        return ""
    return "".join(unicodedata.normalize("NFKC", value).split()).lower()


def group_horse_items(items, query="", exact=False):
    """Group stored items per horse, retaining every text and race/phase context."""
    wanted = horse_key(query)
    groups = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = horse_key(item.get("horse"))
        if not key or not isinstance(item.get("text"), str) or not item["text"].strip():
            continue
        if wanted and (key != wanted if exact else wanted not in key):
            continue
        if key not in groups:
            groups[key] = {"key": key, "horse": item["horse"].strip(), "items": []}
        groups[key]["items"].append(item)
    return list(groups.values())


def safe_horse_back(back):
    try:
        parsed = urlsplit(back)
        if not parsed.scheme and not parsed.netloc and parsed.path == "/horses":
            return back
    except (TypeError, ValueError):
        pass
    return "/horses"


def _escape(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _stamp(value):
    if not value:
        return "不明"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M")


def render_horse_card(row, back="/horses", horse_href=None):
    """Render one article-version/horse card. Legacy fragments stay unaltered."""
    groups = group_horse_items(row.get("items"), row.get("horse", ""), exact=True)
    if not groups:
        return ""
    group = groups[0]
    name = _escape(group["horse"])
    if horse_href and safe_horse_back(horse_href) == horse_href:
        name = '<a href="' + _escape(horse_href) + '">' + name + "</a>"
    article_href = (
        "/article/"
        + quote(str(row["capture_id"]), safe="")
        + "?"
        + urlencode({"back": safe_horse_back(back)})
    )
    title = row.get("title") or "見出し不明"
    h = (
        '<article class="article horse-card"><h3>'
        + name
        + '</h3><p class="horse-source-title"><a href="'
        + _escape(article_href)
        + '">'
        + _escape(title)
        + '</a></p><p class="meta">'
        + _escape(row.get("publisher") or row.get("host") or "媒体不明")
        + "　掲載・更新 "
        + _escape(row.get("date_label") or row.get("article_day") or "不明")
        + "　取得 "
        + _escape(_stamp(row.get("observed_at")))
        + "</p>"
    )
    if row.get("partial"):
        h += '<p class="meta">公開部分からの解釈</p>'
    if len(group["items"]) > 1:
        h += (
            '<p class="meta legacy-fragments">既存の分割解釈（'
            + str(len(group["items"]))
            + "項目）を同じ記事・馬にまとめて表示。文章は保存時のままです。</p>"
        )
    phases = {"pre": "事前", "post": "事後", "mixed": "事前・事後", "unknown": "前後不明"}
    for item in group["items"]:
        context = [item[k] for k in ("race", "race_date", "venue") if item.get(k)]
        if item.get("race_no"):
            context.append(str(item["race_no"]) + "R")
        if item.get("phase"):
            context.append(phases.get(item["phase"], item["phase"]))
        h += '<div class="horse-part">'
        if context:
            h += '<p class="meta">' + _escape(" ／ ".join(map(str, context))) + "</p>"
        h += '<p class="horse-summary">' + _escape(item["text"]) + "</p></div>"
    h += '<p class="horse-links"><a href="' + _escape(article_href) + '">保存原文と解釈を比較する</a>'
    source = row.get("source_url") or ""
    try:
        parsed = urlsplit(source)
        valid_source = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except (TypeError, ValueError):
        valid_source = False
    if valid_source:
        h += '　<a href="' + _escape(source) + '">掲載サイトの元記事 ↗</a>'
    h += '</p><p class="meta">解釈保存 ' + _escape(_stamp(row.get("interpretation_at"))) + "</p></article>"
    return h
