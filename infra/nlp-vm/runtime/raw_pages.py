"""Save an observed production listing before consuming its article candidates."""

import re
from datetime import date, timedelta
from urllib.parse import parse_qs, quote, urljoin, urlsplit

import httpx
from corpus import article_day, connect
from discovery import BLOG, MEDIA, NET
from research import digest, now, save
from routes import Unavailable, get_html, rendered_html, url_key


def entry(target):
    source = target["source"]
    if source == "net":
        return "https://news.netkeiba.com/?pid=news_search&keyword=" + quote(
            target["name"]
        ), NET
    if source == "blog":
        return "https://www.yamaguchi-yoshino.com/search?q=" + quote(
            target["name"]
        ), BLOG
    day = date.fromisoformat(target["day"])
    url, selector = MEDIA[source]
    return url.format(year=day.year, month=day.month), selector


def next_page(soup, url, base):
    """Follow the displayed forward control within this list/search only."""
    start = urlsplit(base)
    for a in soup.select(
        'a[rel~=next], li.next a[href], a.-next[href], a[title="次へ"], .pagination a[href], .pager a[href], .pager-area a[href], a.pagenation-next'
    ):
        text = a.get_text(" ", strip=True)
        if not (
            "next" in a.get("rel", [])
            or "next" in str(a.get("class", []))
            or a.find_parent(class_="next")
            or re.search(r"次|NEXT|^[›»＞→]+$", text, re.I)
        ):
            continue
        dest = urljoin(url, a.get("href", ""))
        part = urlsplit(dest)
        if (
            part.hostname != start.hostname
            or part.scheme not in ("http", "https")
            or url_key(dest) == url_key(url)
        ):
            continue
        if part.path != start.path and not part.path.startswith(
            start.path.rstrip("/") + "/page/"
        ):
            continue
        query = parse_qs(part.query)
        if any(
            query.get(k) != v
            for k, v in parse_qs(start.query).items()
            if k in ("pid", "keyword", "q", "pg")
        ):
            continue
        return dest
    return None


def candidates(soup, selector, base):
    found = {}
    for a in soup.select(selector):
        href = a.get("href")
        if not href:
            continue
        link = urljoin(base, href)
        if urlsplit(link).hostname != urlsplit(base).hostname:
            continue
        key = url_key(link)
        label = (
            a.select_one(
                ".NewsTitle,.category-list-title,.news-list__item__title,.c-news__title"
            )
            or a
        )
        title = label.get_text(" ", strip=True)
        parent = a.find_parent(["li", "article"]) or a.parent
        when = a.select_one("time,.Time") or parent.select_one("time,.Time")
        raw = (when.get("datetime") or when.get_text(" ", strip=True)) if when else ""
        found.setdefault(key, dict(url=link, title=title[:240], date_label=raw))
    return list(found.values())


def page_step(target, plan):
    start, selector = entry(target)
    url = target.get("url", start)
    source = target["source"]
    channel = source + "/" + target.get("name", "")
    data = dict(
        subject=target.get("name", source),
        url=url,
        selector=selector,
        observed_at=now(),
        channel=channel,
        plan=str(plan["id"]),
        head=url_key(url) == url_key(start),
        day=plan["input"].get("day") if plan["kind"] == "daily" else None,
        candidates=[],
        navigation=[],
    )
    try:
        final, soup = rendered_html(url, selector) if source == "net" else get_html(url)
        rows = candidates(soup, selector, final)
        nav = next_page(soup, final, start)
        data.update(
            final_url=final,
            candidates=rows,
            navigation=[nav] if nav else [],
            status="ok" if rows or nav else "no_matching_links",
        )
    except (Unavailable, httpx.HTTPError, OSError) as exc:
        data.update(
            status=str(exc) or type(exc).__name__,
            retry_after=getattr(exc, "retry_after", None),
            common=isinstance(exc, (httpx.TransportError, OSError))
            or str(exc)
            in (
                "browser_unavailable",
                "browser_navigation_failed",
                "browser_no_response",
            ),
        )
    saved = save("listings", data)
    result = dict(
        route_status=data["status"],
        observations=[saved["id"]],
        candidate_count=len(data["candidates"]),
        retry_after=data.get("retry_after"),
        service_failure=data.get("common", False),
    )
    context = {
        k: target[k]
        for k in (
            "source",
            "name",
            "horse_id",
            "day",
            "race",
            "stage",
            "origin",
            "first",
            "last",
            "limit",
        )
        if k in target
    }
    group = (
        channel
        + "/"
        + str(context.get("horse_id", ""))
        + "/"
        + (start if source == "radio" else "")
    )
    follow = []
    if data["candidates"]:
        follow.append(
            dict(
                context,
                type="listing",
                listing_id=saved["id"],
                offset=0,
                count=len(data["candidates"]),
                limit=min(target.get("limit", 8), 16),
                queue_key="slice/" + saved["id"] + "/0",
            )
        )
    if not data["navigation"]:
        return result, follow
    nav = data["navigation"][0]
    if url_key(nav) == url_key(start) or target.get("overlap"):
        return result, follow
    overlap = False
    if data["day"] and data["candidates"]:
        dates = [
            article_day(hit["date_label"] or hit["url"]) for hit in data["candidates"]
        ]
        if all(dates) and max(dates) < date.fromisoformat(data["day"]) - timedelta(
            days=8
        ):
            return result, follow
        with connect() as c:
            prior = c.execute(
                """SELECT data->'candidates' items FROM observations WHERE family='listings'
              AND data->>'channel'=%s AND data->>'head'='true' AND data->>'day'<%s AND data->>'status'='ok'
              ORDER BY data->>'day' DESC LIMIT 1""",
                (channel, data["day"]),
            ).fetchone()
        if prior:
            old = {url_key(hit["url"]) for hit in prior["items"]}
            overlap = any(url_key(hit["url"]) in old for hit in data["candidates"])
    follow.append(
        dict(
            context,
            type="page",
            url=nav,
            overlap=overlap,
            queue_key="page/" + digest(group + "/" + url_key(nav)),
        )
    )
    return result, follow
