"""Find public article links and collect their text before doing model inference."""

import gzip
import json
import os
import re
import socket
import time
import uuid
from email.utils import parsedate_to_datetime
from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from research import ROOT, SERVER, digest, links_only, now, read, save


HEADERS = {"User-Agent": "KeibaNLPResearch/1.0"}
REQUEST_INTERVAL_SECONDS = 1.0
LAST_REQUEST = {}
PUBLIC_ARTICLE_LAYOUTS = {
    ("umatoku.hochi.co.jp", "/articles/"): (
        "article.news-article p.article__text", "article.news-article h1", "time.note__pubdate"),
    ("www.radionikkei.jp", "/keiba_article/news/"): (
        "article.article-box", "h2.proglam-article-title", "time.articles-time"),
    ("s.keibabook.co.jp", "/news/detail/"): (
        ".newsbox .newshonbun .honbun", ".newsbox .news h2", ".newsbox .news .date"),
    ("www.daily.co.jp", "/umaya/news/"): (
        ".mainTxt p.news-detail-desc", "h1.ttl-main", "time.date"),
}


class Unavailable(Exception):
    """A reason to keep the candidate without an article body."""

    def __init__(self, reason, retry_after=None):
        super().__init__(reason)
        self.retry_after = retry_after


def url_key(url):
    p = urlsplit(url)
    pairs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if k != "rf" and not k.startswith("utm_")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(pairs), ""))


@lru_cache(maxsize=256)
def public_host(host):
    return all(ip_address(r[4][0]).is_global for r in socket.getaddrinfo(host, None))


def public_url(url):
    p = urlsplit(url)
    if (p.scheme not in ("https", "http") or not p.hostname or p.username is not None
            or p.password is not None or p.port not in (None, 80, 443) or not public_host(p.hostname)):
        raise Unavailable("unsupported_url")
    return p


def pace(url):
    public_url(url)
    host = urlsplit(url).netloc
    if SERVER:
        # Each collector and browser on VM15 shares the same per-host wait.
        server_pace(host)
        return
    time.sleep(max(0, LAST_REQUEST.get(host, 0) + REQUEST_INTERVAL_SECONDS - time.monotonic()))
    LAST_REQUEST[host] = time.monotonic()


def server_pace(host, retry_seconds=None):
    import fcntl
    folder = ROOT / "pacing"
    folder.mkdir(exist_ok=True)
    with (folder / digest(host)).open("a+") as state:
        fcntl.flock(state, fcntl.LOCK_EX)
        state.seek(0)
        values = state.read().split()
        last, cooldown = map(float, values) if len(values)==2 else (0,0)
        current = time.time()
        if retry_seconds is None:
            if cooldown > current:
                raise Unavailable("cooldown", str(max(1,round(cooldown-current))))
            time.sleep(max(0, last + REQUEST_INTERVAL_SECONDS-current))
            last = time.time()
        else:
            cooldown = max(cooldown,current+retry_seconds)
        state.seek(0)
        state.truncate()
        state.write(f"{last} {cooldown}")


def record_limit(url, status, header):
    if SERVER and status in (429,503):
        try:
            seconds = int(header)
        except (TypeError,ValueError):
            try: seconds = parsedate_to_datetime(header).timestamp()-time.time()
            except (TypeError,ValueError,OverflowError): seconds=60
        server_pace(urlsplit(url).netloc,max(1,seconds))


def get_html(url):
    with httpx.Client(headers=HEADERS, timeout=20) as client:
        for _ in range(6):
            pace(url)
            r = client.get(url)
            if r.is_redirect:
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code != 200:
                record_limit(url,r.status_code,r.headers.get("retry-after"))
                raise Unavailable(f"http_{r.status_code}", r.headers.get("retry-after"))
            if "html" not in r.headers.get("content-type", "").lower():
                raise Unavailable("not_html")
            return str(r.url), BeautifulSoup(r.content, "html.parser")
    raise Unavailable("redirect_limit")


def rendered_html(url, selector):
    """Use the public page's visible DOM on a machine with Playwright and Edge."""
    from playwright.sync_api import Error as BrowserError, TimeoutError as BrowserTimeout, sync_playwright

    public_url(url)
    with sync_playwright() as p:
        try:
            executable = os.environ.get("KEIBA_BROWSER_EXECUTABLE")
            browser = p.chromium.launch(headless=True, **({"executable_path": executable}
                                        if executable else {"channel": "msedge"}))
        except BrowserError as exc:
            raise Unavailable("browser_unavailable") from exc
        page = browser.new_page(locale="ja-JP")

        blocked=[]
        def guard(route):
            request = route.request
            if request.resource_type in ("image", "font", "media"):
                return route.abort()
            if request.is_navigation_request() and request.frame == page.main_frame:
                try:
                    pace(request.url)
                except (Unavailable, OSError, ValueError, httpx.HTTPError) as exc:
                    blocked.append(exc)
                    return route.abort()
            return route.continue_()

        page.route("**/*", guard)
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except BrowserError as exc:
            if blocked:raise blocked[-1] from exc
            raise Unavailable("browser_navigation_failed") from exc
        if not response:
            raise Unavailable("browser_no_response")
        if response.status != 200:
            record_limit(page.url,response.status,response.headers.get("retry-after"))
            raise Unavailable(f"http_{response.status}", response.headers.get("retry-after"))
        try:
            page.locator(selector).first.wait_for(state="attached", timeout=8000)
        except BrowserTimeout:
            pass
        final_url, html = page.url, page.content()
        browser.close()
    return final_url, BeautifulSoup(html, "html.parser")


def anchor_rows(soup, selector, base):
    found = {}
    if selector:
        for link in soup.select(selector):
            href = link.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            url = urljoin(base, href)
            if urlsplit(url).scheme in ("http", "https"):
                label = link.select_one(".txt, .News_Title, .news-list__item__title, .category-list-title, dt.title") or link
                lines = label.get_text("\n", strip=True).splitlines()
                if len(lines) > 1 and lines[0] in ("ニュース", "レース関連"):
                    lines = lines[1:]
                title = lines[0][:240] if lines else ""
                key = url_key(url)
                if key not in found or not found[key]["title"]:
                    found[key] = dict(url=url, title=title)
    return list(found.values())


def listing(subject: str, url: str, selector: str, next_selector: str = "",
            render: bool = False) -> dict:
    """Save the discovered article links and actual navigation links from a public listing."""
    start = time.monotonic()
    record = dict(subject=subject, url=url, selector=selector, next_selector=next_selector,
                  route="browser_dom" if render else "public_html", candidates=[], navigation=[])
    try:
        final, soup = rendered_html(url, selector) if render else get_html(url)
        candidates = anchor_rows(soup, selector, final)
        record.update(final_url=final, title=soup.title.get_text(strip=True) if soup.title else "",
                      candidates=candidates, navigation=anchor_rows(soup, next_selector, final),
                      status="ok" if candidates else "no_matching_links")
    except (Unavailable, httpx.HTTPError, OSError, ValueError, ImportError) as exc:
        record["status"] = str(exc)
        if getattr(exc, "retry_after", None):
            record["retry_after"] = exc.retry_after
    record.update(observed_at=now(), seconds=round(time.monotonic()-start, 2))
    save("listings", record)
    return dict(listing_id=record["id"], status=record["status"], count=len(record["candidates"]),
                examples=record["candidates"][:4], navigation=record["navigation"][:15],
                retry_after=record.get("retry_after"))


def known_articles(keys=()):
    if SERVER:
        from corpus import lookup
        return lookup(list(keys))
    latest = {}
    for p in (ROOT / "captures").glob("*.json"):
        item = json.loads(p.read_text(encoding="utf-8"))
        if item.get("status") in ("ok", "partial") and item.get("body"):
            for url in (item["url"], item["final_url"]):
                key = url_key(url)
                version = (item["observed_at"], item["id"])
                if key not in latest or latest[key] < version:
                    latest[key] = version
    return {key: version[1] for key, version in latest.items()}


def article(subject, url, title, listing_id=None):
    start = time.monotonic()
    rec = dict(subject=subject, url=url, title=title, listing_id=listing_id,
               route="public_html", started_at=now())
    try:
        if links_only(url):
            raise Unavailable("metadata_only")
        final, soup = get_html(url)
        if links_only(final):
            raise Unavailable("metadata_only")
        location = urlsplit(final)
        layout = next((selectors for (host, prefix), selectors in PUBLIC_ARTICLE_LAYOUTS.items()
                       if location.hostname == host and location.path.startswith(prefix)), None)
        if layout:
            # Select the public story, including all its paragraphs on 馬トク.
            for node in soup.select('[hidden], [aria-hidden=true], [style]'):
                if node.attrs is not None and (node.has_attr("hidden") or node.get("aria-hidden") == "true"
                        or re.search(r"display\s*:\s*none\b", node.get("style", ""), re.I)):
                    node.decompose()
            parts = soup.select(layout[0])
        else:
            main = next((node for selector in (".NewsArticle_Body", ".news_contents_area", ".entry-content",
                                               "[itemprop=articleBody]", "article")
                         if (node := soup.select_one(selector)) is not None), None)
            parts = [main] if main is not None else []
        jra_result = (urlsplit(final).hostname in ("www.jra.go.jp", "jra.jp")
                      and "/datafile/seiseki/g1/" in urlsplit(final).path and "/result/" in urlsplit(final).path)
        if not parts and jra_result:
            parts = soup.select("#contentsBody > h2 + div.grid")[:1]
        if not parts:
            raise Unavailable("article_element_missing")
        main = parts[0]
        for part in parts:
            for node in part.select("script, style, template, [hidden], [aria-hidden=true], .mov_btn"):
                node.decompose()
        text = "\n".join(part.get_text("\n", strip=True) for part in parts).strip()
        if not re.search(r"\w", text) or re.search(r"続きを読むには.{0,15}(?:登録|ログイン)|ここから先は有料", text):
            raise Unavailable("no_public_article_body")
        notice = main.find_next_sibling(class_="NewsReadMore")
        preview = bool(notice and re.search(r"登録|ログイン|有料", notice.get_text(strip=True)))
        heading = soup.select_one(layout[1] if layout else
                                  ".NewsArticle_Header h1, .news_title h1, h1.entry-title, article h1")
        if jra_result:
            heading = soup.select_one("#contentsBody > h2")
        headline = heading.get_text(" ", strip=True) if heading else title
        has_headline = text.partition("\n")[0] == headline if layout else text.startswith(headline)
        body = headline + "\n" + text if headline and not has_headline else text
        date = soup.select_one(layout[2]) if layout else None
        if date is None:
            date = soup.select_one('meta[property="article:published_time"], time[datetime], '
                                   '.ArticleNewsData, .news_title .date')
        published = (date.get("content") or date.get("datetime") or date.get_text(" ", strip=True)) if date else None
        rec.update(status="partial" if preview else "ok", title=headline, final_url=final, fetched_at=now(), body=body,
                   version_id=digest(final + "\n" + body), published_label=published, truncated=preview,
                   source_access="public_preview" if preview else "public_view",
                   extraction="public_article_element", source_element=main.name,
                   source_classes=main.get("class", []))
        if layout:
            rec["source_selector"] = layout[0]
    except (Unavailable, httpx.HTTPError, OSError, ValueError) as exc:
        rec["status"] = str(exc)
        if getattr(exc, "retry_after", None):
            rec["retry_after"] = exc.retry_after
    rec.update(observed_at=now(), seconds=round(time.monotonic()-start, 2))
    save("captures", rec)
    return rec


def collect(listing_id: str, offset: int = 0, limit: int = 20, revisit: bool = False) -> dict:
    """Save a slice of a listing, skip known URLs and return the next zero-based offset."""
    source = read("listings", listing_id)
    if offset < 0 or not 1 <= limit <= 100 or offset > len(source["candidates"]):
        raise ValueError("Use a valid listing offset and 1..100 articles per call")
    start = time.monotonic()
    known = known_articles(url_key(hit["url"]) for hit in source["candidates"][offset:offset+limit])
    results = []
    retry_current = False
    retry_after = None
    for hit in source["candidates"][offset:offset + limit]:
        key = url_key(hit["url"])
        if not revisit and key in known:
            results.append(dict(url=hit["url"], status="known", capture_id=known[key]))
            continue
        rec = article(source["subject"], hit["url"], hit["title"], listing_id)
        unchanged = rec.get("version_id") and key in known and read("captures",known[key]).get("version_id")==rec["version_id"]
        results.append(dict(url=hit["url"], status="known" if unchanged else rec["status"], capture_id=rec["id"]))
        if rec["status"] in ("ok", "partial"):
            known[key] = known[url_key(rec["final_url"])] = rec["id"]
        retry_current = rec["status"] in ("http_429", "http_503","cooldown")
        if retry_current or rec["status"] in ("http_403", "http_401"):
            retry_after = rec.get("retry_after")
            break
    cursor = offset + len(results) - int(retry_current)
    record = save("batches", dict(listing_id=listing_id, subject=source["subject"], offset=offset,
                  next_offset=cursor, retry_after=retry_after, observed_at=now(), results=results,
                  seconds=round(time.monotonic()-start, 2)))
    counts = {s: sum(row["status"] == s for row in results) for s in {row["status"] for row in results}}
    return dict(batch_id=record["id"], counts=counts, next_offset=cursor,
                remaining=len(source["candidates"])-cursor, retry_after=retry_after, examples=results[:4])


def capture_url(subject: str, url: str, title: str = "", revisit: bool = False) -> dict:
    """Capture an article URL found on a public page. Reuse a stored URL by default."""
    key = url_key(url)
    prior_id = known_articles([key]).get(key)
    prior = read("captures", prior_id) if prior_id else None
    rec = prior if prior and not revisit else article(subject, url, title)
    return dict(capture_id=rec["id"], status=rec["status"], known=bool(prior and rec.get("version_id")==prior["version_id"]),
                revisited=bool(prior and revisit),retry_after=rec.get("retry_after"),
                url=rec.get("final_url", url), title=rec["title"], chars=len(rec.get("body", "")))


def excerpt(capture_id: str, offset: int = 0, length: int = 700) -> dict:
    """Read a small slice of an already captured article without model inference."""
    rec = read("captures", capture_id)
    body = rec.get("body", "")
    if offset < 0 or not 1 <= length <= 3000:
        raise ValueError("Use a nonnegative offset and length of 1..3000")
    return dict(title=rec["title"], url=rec.get("final_url", rec["url"]), status=rec["status"],
                chars=len(body), text=body[offset:offset+length], published=rec.get("published_label"))


def daily_horse(horse):
    display = horse["name"]
    name = re.sub(r"^[(（](?:外|地|市|父|抽)[)）]\s*", "", display)
    if name == display:
        return horse
    return {**horse, "name": name, "display_name": horse.get("display_name", display)}


def seeds(roster: str, offset: int = 0, limit: int = 12, name: str = "", year: str = "") -> dict:
    """Read a published or historical roster. Filter by a name fragment or activity year."""
    if not re.fullmatch(r"[a-z0-9-]+", roster) or offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Use a roster name, nonnegative offset and limit of 1..100")
    p = ROOT / "rosters" / (roster + ".json")
    if re.fullmatch(r"[a-f0-9]{32}", roster) and (ROOT / "roster_pages" / p.name).is_file():
        data = read("roster_pages", roster)
    else:
        raw = p.read_bytes() if p.is_file() else gzip.decompress(p.with_suffix(".json.gz").read_bytes())
        data = json.loads(raw)
    horses = data["horses"]
    if "stage" in data:
        horses = (daily_horse(horse) for horse in horses)
    rows = [h for h in horses if name in h["name"] and (not year or year in h.get("years", []))]
    source_details = {k: data[k] for k in ("race_key", "observed_at", "start", "end", "domain") if k in data}
    if "id" in data:
        source_details["observation_id"] = data["id"]
    return dict(roster=roster, source=data["source"], stage=data.get("stage", "history"),
                count=len(rows), horses=rows[offset:offset+limit],
                next_offset=min(offset+limit, len(rows)), **source_details)


def roster_page(roster: str, stage: str, race_key: str, url: str, selector: str, scope: str = "research") -> dict:
    """Read horse-name cells on a public roster. Keep this dated observation and update the named copy."""
    if not re.fullmatch(r"[a-z0-9-]+", roster) or roster == "history-jra":
        raise ValueError("Choose a daily roster name")
    final, soup = get_html(url)
    horses = []
    for cell in soup.select(selector):
        name = cell.get_text(" ", strip=True)
        if name:
            horse = daily_horse({"name": name})
            link = cell if cell.name == "a" else cell.select_one("a[href]")
            if link and link.get("href"):
                horse["source_link"] = urljoin(final, link["href"])
            horses.append(horse)
    rec = save("roster_pages", dict(roster=roster, stage=stage, race_key=race_key, source=final, scope=scope,
               selector=selector, observed_at=now(), horses=horses))
    if horses:
        dest = ROOT / "rosters" / (roster + ".json")
        dest.parent.mkdir(exist_ok=True)
        temp = dest.with_suffix("." + uuid.uuid4().hex + ".tmp")
        temp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        temp.replace(dest)
        if SERVER:
            from corpus import record
            record("rosters",{**rec,"id":roster,"observation_id":rec["id"]})
    return dict(roster=roster, observation_id=rec["id"], count=len(horses), examples=horses[:5])

