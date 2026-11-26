"""Bounded public routes used by the server CLI and the Hermes collection MCP."""

import re
import unicodedata
from datetime import date
from urllib.parse import quote, urljoin

from corpus import article_day, connect
from research import now, read, save
from routes import capture_url, get_html, rendered_html, roster_page, url_key

VENUES = dict(
    zip(
        ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10"),
        (
            "札幌",
            "函館",
            "福島",
            "新潟",
            "東京",
            "中山",
            "中京",
            "京都",
            "阪神",
            "小倉",
        ),
    )
)
MEDIA = {
    "radio": (
        "https://www.radionikkei.jp/keiba_article/news/{year}/{month:02}/",
        "a.category-list-item-link",
    ),
    "book": (
        "https://s.keibabook.co.jp/news/all",
        '.news_section a[href*="/news/detail/"]',
    ),
    "hochi": (
        "https://umatoku.hochi.co.jp/articles",
        '.news-list__item a[href*="/articles/20"], .news-top-grid__item a[href*="/articles/20"]',
    ),
    "daily": (
        "https://www.daily.co.jp/umaya/news/?pg=list",
        "a.news-primary-main-text, a.card-primary-main-text",
    ),
}
NET = '#NewsBacknumberList a[href*="news_view"]'
BLOG = "a.entry-title-link"
NORMAL = str.maketrans({"ヶ": "ケ", "ヵ": "カ", "ケ": "ケ", "（": "(", "）": ")"})


def norm(s):
    return re.sub(
        r"[\s・()（）]", "", unicodedata.normalize("NFKC", s or "").translate(NORMAL)
    )


def race_alias(s):
    return norm(s).replace("ステークス", "S").replace("カップ", "C")


def compact_day(value):
    return date.fromisoformat(value) if value else None


def summarize_hits(candidates, chosen, subject, observation, revisit=False):
    results = []
    for item in chosen:
        check_update = revisit is True or (
            revisit == "updates" and bool(re.search("更新|訂正|追記", item["title"]))
        )
        result = capture_url(subject, item["url"], item["title"], revisit=check_update)
        results.append(result)
        if result["status"] in (
            "http_429",
            "http_503",
            "http_401",
            "http_403",
            "cooldown",
        ):
            break
    return {
        "observations": [observation],
        "candidate_count": len(candidates),
        "candidates_selected": len(chosen),
        "saved": sum(
            r["status"] in ("ok", "partial") and not r["known"] for r in results
        ),
        "known": sum(r["known"] for r in results),
        "failed": sum(
            r["status"] not in ("ok", "partial", "metadata_only") for r in results
        ),
        "links_only": sum(r["status"] == "metadata_only" for r in results),
        "hits": results,
    }


def horse_route(target, source="net", limit=4):
    """Inspect one visible result page. Prefer the target race and active years, then retain other leads."""
    name = target["name"]
    url = (
        "https://news.netkeiba.com/?pid=news_search&keyword="
        if source == "net"
        else "https://www.yamaguchi-yoshino.com/search?q="
    ) + quote(name)
    selector = NET if source == "net" else BLOG
    observation = {
        "subject": name,
        "url": url,
        "selector": selector,
        "route": "browser_dom" if source == "net" else "public_html",
        "observed_at": now(),
        "candidates": [],
    }
    try:
        final, soup = rendered_html(url, selector) if source == "net" else get_html(url)
        observation["final_url"] = final
        for a in soup.select(selector):
            title = (a.select_one(".NewsTitle") or a).get_text(" ", strip=True)
            stamp = (
                a.select_one(".Time")
                if source == "net"
                else (a.find_parent("article") or a.parent.parent).select_one("time")
            )
            label = (
                (stamp.get("datetime") or stamp.get_text(" ", strip=True))
                if stamp
                else ""
            )
            observation["candidates"].append(
                {"url": urljoin(final, a["href"]), "title": title, "date": label}
            )
        observation["status"] = (
            "ok" if observation["candidates"] else "no_matching_links"
        )
    except Exception as e:
        observation["status"] = str(e)[:250] or type(e).__name__
        observation["retry_after"] = getattr(e, "retry_after", None)
    save("listings", observation)
    candidates = observation["candidates"]
    first, last = compact_day(target.get("first")), compact_day(target.get("last"))
    race_day = compact_day(target.get("day"))

    def rank(hit):
        d = article_day(hit["date"])
        near = bool(race_day and d and abs((d - race_day).days) <= 7)
        active = bool(d and first and last and first <= d <= last)
        race = norm(target.get("race"))
        return (
            near,
            bool(race and race in norm(hit["title"])),
            active,
            norm(name) in norm(hit["title"]),
        )

    chosen = sorted(candidates, key=rank, reverse=True)[:limit]
    return dict(
        route_status=observation["status"],
        retry_after=observation.get("retry_after"),
        **summarize_hits(candidates, chosen, name, observation["id"]),
    )


def media_route(target):
    day = compact_day(target["day"])
    key = target["source"]
    u, selector = MEDIA[key]
    u = u.format(year=day.year, month=day.month)
    url, soup = get_html(u)
    candidates = []
    seen = set()
    for a in soup.select(selector):
        href = urljoin(url, a["href"])
        if url_key(href) in seen:
            continue
        seen.add(url_key(href))
        title = (
            a.select_one(".category-list-title, .news-list__item__title") or a
        ).get_text(" ", strip=True)
        t = a.select_one("time")
        stamp = article_day(t.get_text(" ", strip=True)) if t else None
        if target.get("race_key"):
            named = race_alias(target["race"])
            token = race_alias(title)
            venue = VENUES[target["venue"]]
            venue_r = bool(
                re.search(
                    venue
                    + r"(?:競馬)?(?:場)?第?0?"
                    + str(int(target["no"]))
                    + r"(?:R|レース)",
                    token,
                    re.I,
                )
            )
            common = named in ("1勝", "2勝", "3勝", "未勝利", "新馬") or bool(
                re.fullmatch(r".*(?:クラス|未勝利|新馬)", named)
            )
            # General class names recur on every card. Require the venue and race number.
            if (
                not stamp
                or abs((stamp - day).days) > 8
                or not (venue_r or (not common and named and named in token))
            ):
                continue
        candidates.append({"url": href, "title": title})
    o = save(
        "listings",
        {
            "subject": target.get("race_key", key),
            "url": url,
            "selector": selector,
            "route": "public_html",
            "observed_at": now(),
            "candidates": candidates,
            "status": "ok" if candidates else "no_matching_links",
        },
    )
    return dict(
        route_status=o["status"],
        list_scope=(
            "race"
            if target.get("race_key")
            else "month"
            if key == "radio"
            else "latest"
        ),
        **summarize_hits(
            candidates,
            candidates[: target.get("limit", 8)],
            o["subject"],
            o["id"],
            target.get("revisit", False),
        ),
    )


def calendar(day):
    """Discover the available race links for a date from the site's own calendar."""
    key = day.strftime("%Y%m%d")
    url, soup = get_html("https://www.keibalab.jp/db/race/" + key + "/")
    races = {}
    for a in soup.select('a[href*="/db/race/"]'):
        m = re.fullmatch(r"/db/race/(" + key + r"\d{4})/", a["href"])
        if m:
            ident = m[1]
            races[ident] = a.get_text(" ", strip=True) or races.get(ident, "")
    # Cross-date links include alternative holiday meetings.
    dates = sorted(
        {
            m[1]
            for a in soup.select("a[href]")
            if (m := re.fullmatch(r"/db/race/(\d{8})/", a["href"]))
        }
    )
    return {"url": url, "races": races, "dates": dates}


def card(target, scope="lookup", previous_before=None):
    key, stage = target["key"], target["stage"]
    if not re.fullmatch(r"\d{12}", key):
        raise ValueError("invalid race key")
    base = "https://www.keibalab.jp/db/race/" + key + "/"
    suffix, selector = {
        "registration": (
            "tokubetsu.html?kind=simple",
            ".tkbttable tbody tr td:first-child",
        ),
        "entries": ("syutsuba.html", "td[data-hsnm]"),
        "result": ("raceresult.html", 'td[itemprop=name]:has(a[href*="/db/horse/"])'),
    }[stage]
    roster = "jra-" + key + "-" + stage
    with connect() as c:
        prev = c.execute(
            """SELECT data FROM observations WHERE family='roster_pages' AND data->>'roster'=%s
                       AND data->>'selector'=%s AND data->>'scope'=%s AND jsonb_array_length(data->'horses')>0
                       AND (%s::timestamptz IS NULL OR (data->>'observed_at')::timestamptz < %s)
                       ORDER BY data->>'observed_at' DESC LIMIT 1""",
            (roster, selector, scope, previous_before, previous_before),
        ).fetchone()
    o = roster_page(
        roster,
        stage,
        key[:8] + "/" + key[8:10] + "/" + key[10:],
        base + suffix,
        selector,
        scope,
    )
    rows = read("roster_pages", o["observation_id"])["horses"]
    old = {r["name"] for r in prev["data"]["horses"]} if prev else set()
    added = [r["name"] for r in rows if r["name"] not in old]
    return {
        "observations": [o["observation_id"]],
        "count": len(rows),
        "added": added,
        "roster": roster,
        "route_status": "ok" if rows else "no_matching_links",
    }
