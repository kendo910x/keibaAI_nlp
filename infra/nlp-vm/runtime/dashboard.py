"""Read-only LAN archive. No model, admin endpoint or collector dependency."""

import html
import json
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from corpus import connect
from horse_view import horse_key, render_horse_card
from profile_db import PROFILES, database, trial

JST = ZoneInfo("Asia/Tokyo")
SITES = {
    "news.netkeiba.com": "netkeiba",
    "www.radionikkei.jp": "ラジオNIKKEI",
    "umatoku.hochi.co.jp": "馬トク報知",
    "s.keibabook.co.jp": "競馬ブック",
    "www.daily.co.jp": "デイリーうま屋",
    "www.yamaguchi-yoshino.com": "山口吉野",
    "www.jra.go.jp": "JRA",
    "www.keibalab.jp": "競馬ラボ",
}
ST = {
    "done": "完了",
    "partial": "一部失敗",
    "failed": "失敗",
    "queued": "待機",
    "working": "処理中",
    "running": "実行中",
    "paused": "中断・再開可",
    "ok": "接続確認",
    "off": "停止",
    "enabled": "有効",
    "disabled": "無効",
    "absent": "未登録",
    "coverage": "標本調査",
    "history": "初期構築",
    "daily": "日次収集",
    "interpret": "独立解釈",
    "review": "限定試験",
    "bounded": "有限の指定範囲",
    "operation": "通常範囲",
    "finite": "指定した収集分",
    "saved_versions": "固定した保存本文版",
    "server-survey": "サーバ標本調査",
    "net": "netkeiba",
    "blog": "山口吉野",
    "radio": "ラジオNIKKEI",
    "book": "競馬ブック",
    "hochi": "馬トク報知",
    "no_matching_links": "該当リンクなし",
    "metadata_only": "リンクのみ",
    "interpretation_failed": "解釈失敗",
    "article_element_missing": "本文欄未確認",
}
HEALTH = {
    "database": "通常DB",
    "model": "Local LLM",
    "search": "共用検索MCP",
    "fetch": "公開記事の取得経路",
    "ticker": "Hermes Cronの起動タイマー",
    "interpreter": "常駐解釈",
}
ESC = lambda x: html.escape(str(x if x is not None else ""), quote=True)
UUID = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"


def label(x):
    return ST.get(x, x or "不明")


def site(x):
    return SITES.get(x, x)


def stamp(x):
    if not x:
        return "—"
    if isinstance(x, str):
        try:
            x = datetime.fromisoformat(x)
        except ValueError:
            return x
    return x.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def badge(x, style=""):
    return f'<span class="tag {ESC(style)}">{ESC(x)}</span>'


def anchor(href, title):
    return f'<a href="{ESC(href)}">{ESC(title)}</a>'


def external(href):
    return (
        anchor(href, "掲載サイトの元記事を開く ↗")
        if urlsplit(href).scheme in ("http", "https")
        else ESC(href)
    )


def rows(items):
    return (
        "<dl>"
        + "".join(
            "<div><dt>" + ESC(k) + "</dt><dd>" + str(v) + "</dd></div>"
            for k, v in items
        )
        + "</dl>"
    )


def panel(title, body):
    return '<section class="panel"><h2>' + ESC(title) + "</h2>" + body + "</section>"


def table(headers, body):
    return (
        '<div class="tablewrap"><table><thead><tr>'
        + "".join("<th>" + ESC(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + str(x) + "</td>" for x in row) + "</tr>"
            for row in body
        )
        + "</tbody></table></div>"
    )


def opts(values, current):
    return "".join(
        f'<option value="{ESC(k)}" '
        + ("selected" if str(k) == current else "")
        + ">"
        + ESC(v)
        + "</option>"
        for k, v in values
    )


def linkto(path, query):
    return (
        path + "?" + urlencode({k: v for k, v in query.items() if v not in ("", None)})
    )


def layout(tab, title, body):
    env = "検証用" if trial() else "本番"
    nav = "".join(
        f'<a href="{href}" '
        + ('aria-current="page"' if tab == key else "")
        + ">"
        + name
        + "</a>"
        for key, href, name in (
            ("status", "/", "稼働状況"),
            ("horses", "/horses", "馬別の解釈"),
            ("articles", "/articles", "記事を探す"),
            ("runs", "/runs", "実行履歴"),
        )
    )
    return (
        '<!DOCTYPE html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>"
        + ESC(title)
        + ' | 競馬資料庫</title><link rel="stylesheet" href="/dashboard.css">'
        '<header><div><a class="brand" href="/"><span class="mark" aria-hidden="true">馬</span>競馬資料庫</a>'
        + '<strong class="environment">'
        + env
        + "</strong><nav>"
        + nav
        + "</nav></div></header><main><h1>"
        + ESC(title)
        + "</h1>"
        + body
        + "</main><footer>KeibaAI NLP　／　VM15　・　表示時刻 JST</footer></html>"
    )


def totals(c):
    return c.execute("""SELECT (SELECT count(DISTINCT url_key) FROM versions) urls,(SELECT count(*) FROM versions) versions,
        (SELECT count(DISTINCT version_id) FROM interpretations WHERE status='ok') interpreted,
        (SELECT count(DISTINCT version_id) FROM interpretations WHERE status='ok' AND input_key IS NOT NULL) dated,
        (SELECT count(DISTINCT url_key) FROM captures a WHERE NOT EXISTS(SELECT 1 FROM versions v WHERE v.url_key=a.url_key)) links""").fetchone()


def metrics(t):
    fields = [
        ("本文のあるURL", t["urls"]),
        ("保存本文の版", t["versions"]),
        ("解釈済みの版", t["interpreted"]),
        ("成功した解釈がまだない版", t["versions"] - t["interpreted"]),
    ]
    return (
        '<div class="metrics">'
        + "".join(
            f'<div class="metric"><strong>{n:,}</strong><span>{k}</span></div>'
            for k, n in fields
        )
        + '</div><p class="meta">日時付き入力で解釈済み　'
        + str(t["dated"])
        + " 版</p>"
    )


def schedules():
    f = Path("/run/hermes-cron/jobs.json")
    jobs = json.loads(f.read_bytes())["jobs"] if f.is_file() else []
    prod = next((j for j in jobs if j.get("name") == "keiba-morning"), None)
    return (
        ("absent", None)
        if prod is None
        else (
            ("enabled", prod.get("next_run_at"))
            if prod.get("enabled")
            else ("disabled", None)
        )
    )


def has_worker(c, ident):
    """Session advisory locks disappear on process exit, including an interrupted plan."""
    return c.execute(
        """WITH k AS (SELECT hashtextextended(%s,0) h)
         SELECT EXISTS(SELECT FROM pg_locks,k WHERE locktype='advisory' AND granted AND objsubid=1
         AND classid=((h>>32)&4294967295)::oid AND objid=(h&4294967295)::oid) active""",
        (str(ident),),
    ).fetchone()["active"]


def run_rows(c, limit):
    ps = c.execute(
        """SELECT p.*,x.n,x.finished,x.saved,x.known,x.failed,x.interpreted,x.missing,x.reused FROM plans p
        CROSS JOIN LATERAL (SELECT count(*) n,count(*) FILTER(WHERE state IN ('done','partial','failed')) finished,
        coalesce(sum((result->>'saved')::int),0) saved,coalesce(sum((result->>'known')::int),0) known,
        coalesce(sum((result->>'failed')::int),0) failed,coalesce(sum((result->>'interpreted')::int),0) interpreted,
        coalesce(sum((result->>'reused')::int),0) reused,
        count(*) FILTER(WHERE target->>'type'='horse' AND result->>'route_status'='no_matching_links') missing
        FROM work_items WHERE plan_id=p.id) x ORDER BY p.updated_at DESC LIMIT %s""",
        (limit,),
    ).fetchall()
    for p in ps:
        if p["state"] == "running" and not has_worker(c, p["id"]):
            p["state"] = "中断・再開可"
    return ps


def runs_table(ps):
    return table(
        [
            "実行・対象範囲",
            "状態",
            "処理位置",
            "未発見の馬名検索",
            "新規 / 既知 / 失敗",
            "解釈 / 再利用",
            "更新 JST",
        ],
        [
            (
                anchor("/run/" + str(p["id"]), p["label"])
                + "<br><small>"
                + ESC(label(p["scope"]))
                + "</small>",
                badge(
                    label(p["state"]),
                    "warn" if p["state"] in ("failed", "partial") else "",
                ),
                f"{p['finished']} / {p['n']}",
                p["missing"],
                f"{p['saved']} / {p['known']} / {p['failed']}",
                f"{p['interpreted']} / {p['reused']}",
                stamp(p["updated_at"]),
            )
            for p in ps
        ],
    )


def home(c):
    t = totals(c)
    ss, nxt = schedules()
    ps = run_rows(c, 8)
    current = c.execute("""SELECT p.id,p.label,p.started_at,p.updated_at,w.target FROM plans p JOIN work_items w ON p.id=w.plan_id
            WHERE p.state='running' AND w.state='working' ORDER BY p.updated_at DESC""").fetchall()
    health = c.execute("SELECT * FROM health ORDER BY name").fetchall()
    byname = {h["name"]: h for h in health}
    operation = c.execute(
        "SELECT count(*) n FROM plans WHERE scope='operation' AND state IN ('queued','running')"
    ).fetchone()["n"]
    pending = (
        ss != "enabled"
        and not operation
        and byname.get("interpreter", {}).get("state") != "enabled"
    )
    clock = stamp(datetime.now(JST))
    h = (
        '<p class="statusline">'
        + badge(
            "検証用資料庫"
            if trial()
            else "実装済み・運用開始待ち"
            if pending
            else "本運用の設定あり"
        )
        + '<span class="muted">'
        + (
            "有限試行の進捗"
            if trial()
            else "本運用の次回予定　" + ESC(stamp(nxt) if nxt else "なし")
        )
        + "</span></p>"
        + (trial_links(c) if trial() else "")
        + horse_search_form()
        + "<h2>"
        + ("今回のテストDB全体" if trial() else "本番DB全体")
        + "</h2>"
        + metrics(t)
    )
    hh = [
        ("毎朝の本運用", badge(label(ss), "neutral")),
        ("本運用の次回", ESC(stamp(nxt) if nxt else "予定なし")),
        ("予定表の確認", ESC(clock + " JST")),
    ]
    for k in ("ticker", "interpreter"):
        r = byname.get(k)
        if r:
            hh.append(
                (
                    HEALTH[k],
                    ESC(r["detail"]) + " <small>" + stamp(r["checked_at"]) + "</small>",
                )
            )
    if trial():
        schedule_file = Path("/run/hermes-cron/jobs.json")
        native = (
            json.loads(schedule_file.read_bytes())["jobs"]
            if schedule_file.exists()
            else []
        )
        hh = [
            (
                j.get("name", "単発起動"),
                ESC(
                    "単発起動終了"
                    if j.get("repeat", {}).get("completed")
                    else "予定あり"
                    if j.get("enabled")
                    else "無効"
                ),
            )
            for j in native
        ]
    h += '<div class="blocks">' + panel(
        "検証用Hermesの予定" if trial() else "定期実行", rows(hh) if hh else "登録なし"
    )
    ch = [
        (
            "検証DB" if trial() else "本番DB",
            badge("接続確認") + " <small>" + clock + "</small>",
        )
    ]
    for r in health:
        if r["name"] in ("ticker", "interpreter", "database"):
            continue
        ch.append(
            (
                HEALTH.get(r["name"], r["name"]),
                badge(label(r["state"]), "warn" if r["state"] == "failed" else "")
                + " <small>"
                + stamp(r["checked_at"])
                + "</small><br>"
                + ESC(r["detail"]),
            )
        )
    h += panel("接続状態", rows(ch)) + "</div>"
    cp = []
    for p in current:
        if not has_worker(c, p["id"]):
            continue
        t0 = p["target"]
        target = (
            t0.get("name")
            or t0.get("race_key")
            or t0.get("capture")
            or t0.get("key")
            or t0.get("source")
            or t0.get("day")
        )
        cp.append(
            (
                p["label"],
                ESC(target)
                + "<br><small>開始 "
                + stamp(p["started_at"])
                + "　最終進捗 "
                + stamp(p["updated_at"])
                + "</small>",
            )
        )
    h += panel("現在の処理", rows(cp) if cp else "待機中")
    recent_problems = [r for r in health if r["state"] == "failed"]
    if recent_problems:
        h += panel(
            "確認が必要な接続",
            rows(
                [
                    (HEALTH.get(r["name"], r["name"]), ESC(r["detail"]))
                    for r in recent_problems
                ]
            ),
        )
    interrupted = [p for p in ps if p["state"] == "中断・再開可"]
    if interrupted:
        h += panel(
            "処理の中断",
            rows(
                [
                    (
                        p["label"],
                        anchor("/run/" + str(p["id"]), "保存された再開位置を確認"),
                    )
                    for p in interrupted
                ]
            ),
        )
    h += "<h2>最近の実行</h2>" + runs_table(ps)
    roster = c.execute(
        """SELECT input->>'horses' horses,id,label,state FROM plans WHERE kind='history' ORDER BY updated_at DESC LIMIT 4"""
    ).fetchall()
    roster_size = c.execute("""SELECT (input->>'roster_size')::int horses FROM plans
        WHERE kind='history' AND input ? 'roster_size' ORDER BY created_at DESC LIMIT 1""").fetchone()
    h += panel(
        "過去名簿の探索",
        (
            "<p>元のJRA履歴名簿　"
            + (f"{roster_size['horses']:,}頭" if roster_size else "対象計画の登録待ち")
            + "</p>"
            + rows(
                [
                    (
                        r["label"],
                        anchor(
                            "/run/" + str(r["id"]),
                            str(r["horses"]) + "頭の指定範囲・" + label(r["state"]),
                        ),
                    )
                    for r in roster
                ]
            )
        ),
    )
    return layout("status", "稼働状況", h)


def item_name(item):
    return (
        " ／ ".join(str(item[k]) for k in ("horse", "race") if item.get(k))
        or "対象未確定"
    )


def pattern(kind):
    return "A　過去馬名検索" if kind == "history" else "B　日次検索"


def progress_label(state):
    return {
        "ok": "解釈済み",
        "queued": "解釈待ち",
        "working": "処理中",
        "failed": "解釈失敗",
    }[state]


def trial_links(c):
    plans = c.execute("""SELECT DISTINCT ON (kind) id,kind FROM plans WHERE kind IN ('history','daily')
                         ORDER BY kind,created_at DESC""").fetchall()
    bykind = {p["kind"]: str(p["id"]) for p in plans}
    cards = ""
    for kind in ("history", "daily"):
        ident = bykind.get(kind)
        body = (
            (
                anchor(linkto("/articles", {"plan": ident}), "取得した記事")
                + "　"
                + anchor("/run/" + ident, "対象と進捗")
            )
            if ident
            else "開始待ち"
        )
        cards += panel(pattern(kind), body)
    saved = c.execute("SELECT id,label FROM plans WHERE scope='saved_versions' ORDER BY created_at DESC LIMIT 1").fetchone()
    if saved:
        cards += panel("保存済み記事の解釈", anchor("/run/" + str(saved["id"]), saved["label"] + "の進捗"))
    return '<div class="blocks">' + cards + "</div>"


def source_summary(c, ident, kind):
    stats = c.execute(
        """WITH seen AS (SELECT DISTINCT c.url_key,c.version_id FROM plan_hits h
                        JOIN captures c ON c.id=h.capture_id WHERE h.plan_id=%s AND c.version_id IS NOT NULL)
        SELECT count(DISTINCT url_key) urls,count(DISTINCT version_id) versions,
        count(DISTINCT version_id) FILTER(WHERE p.state='ok') ok,
        count(DISTINCT version_id) FILTER(WHERE p.state='queued') queued,
        count(DISTINCT version_id) FILTER(WHERE p.state='working') working,
        count(DISTINCT version_id) FILTER(WHERE p.state='failed') failed
        FROM seen LEFT JOIN version_progress p ON p.id=seen.version_id""",
        (ident,),
    ).fetchone()
    left = c.execute(
        "SELECT count(*) n FROM work_items WHERE plan_id=%s AND state IN ('queued','working')",
        (ident,),
    ).fetchone()["n"]
    marks = "　".join(
        f"{progress_label(k)} {stats[k]} 版"
        for k in ("ok", "queued", "working", "failed")
    )
    picks = c.execute(
        """SELECT DISTINCT ON (term) term FROM (
        SELECT coalesce(nullif(target->>'name',''),nullif(target->>'race','')) AS term FROM work_items
        WHERE plan_id=%s) x WHERE term IS NOT NULL ORDER BY term LIMIT 12""",
        (ident,),
    ).fetchall()
    links = "　".join(
        anchor(linkto("/articles", {"plan": ident, "q": r["term"]}), r["term"])
        for r in picks
    )
    examples = c.execute(
        """SELECT DISTINCT ON (c.version_id) c.version_id,c.id,c.title,i.items
        FROM plan_hits h JOIN captures c ON c.id=h.capture_id JOIN interpretations i ON i.version_id=c.version_id
        WHERE h.plan_id=%s AND i.status='ok' AND jsonb_array_length(i.items)>0 ORDER BY c.version_id,c.observed_at LIMIT 3""",
        (ident,),
    ).fetchall()
    examples_html = "".join(
        "<li>"
        + anchor("/article/" + e["id"] + "#interpretation", e["title"] or "見出し不明")
        + "　"
        + ESC(item_name(e["items"][0]))
        + "</li>"
        for e in examples
    )
    return panel(
        pattern(kind),
        anchor(linkto("/articles", {"plan": ident}), "この実行の記事を読む")
        + f"<p>本文 {stats['urls']} URL ／ {stats['versions']} 版　収集の残り {left} 対象</p><p>{marks}</p>"
        + ("<p>対象から検索　" + links + "</p>" if links else "")
        + (
            "<h3>原文と解釈を読める記事</h3><ul>" + examples_html + "</ul>"
            if examples
            else ""
        ),
    )


def horse_search_form(q=None, hosts=None):
    q = q or {}
    form = (
        '<form class="filters horse-search" method="get" action="/horses">'
        '<label class="grow">馬別の解釈を探す<input type="search" name="q" value="'
        + ESC(q.get("q", ""))
        + '" placeholder="馬名を入力"></label>'
    )
    if q.get("plan"):
        form += '<input type="hidden" name="plan" value="' + ESC(q["plan"]) + '">'
    if hosts is not None:
        form += (
            '<label>馬名の一致<select name="match">'
            + opts([("", "一部が一致"), ("exact", "この馬だけ")], q.get("match", ""))
            + '</select></label><label>掲載ホスト<select name="site">'
            + opts([("", "すべて")] + [(r["host"], site(r["host"])) for r in hosts], q.get("site", ""))
            + "</select></label>"
        )
        for key, title in (("from", "掲載日から"), ("to", "掲載日まで")):
            form += (
                "<label>"
                + title
                + '<input type="date" name="'
                + key
                + '" value="'
                + ESC(q.get(key, ""))
                + '"></label>'
            )
    return form + "<button>解釈を検索</button></form>"


def horse_query(q):
    """Select the displayed version and successful result before matching horses.

    Plan scope is applied to captures first: its latest capture per URL chooses
    the version. Publication filters and horse matching never select an older
    version or an older successful interpretation in place of that result.
    """
    params = []
    scope = ""
    if q.get("plan"):
        if not re.fullmatch(UUID, q["plan"]):
            raise ValueError("実行IDを確認してください")
        scope = " AND EXISTS(SELECT FROM plan_hits h WHERE h.plan_id=%s AND h.capture_id=cap.id)"
        params.append(q["plan"])
    conditions = []
    if q.get("site"):
        conditions.append("a.host=%s")
        params.append(q["site"])
    for key, op in (("from", ">="), ("to", "<=")):
        if q.get(key):
            try:
                day = datetime.strptime(q[key], "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("期間には有効な日付を指定してください。")
            conditions.append("a.article_day" + op + "%s")
            params.append(day)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    term = horse_key(q.get("q", "")[:250])
    match = "horse_key<>''"
    if term:
        match += " AND " + ("horse_key=%s" if q.get("match") == "exact" else "strpos(horse_key,%s)>0")
        params.append(term)
    sql = """WITH selected_versions AS (
        SELECT DISTINCT ON (v.url_key)
            v.id version_id,v.url_key,v.host,coalesce(nullif(v.title,''),cap.title) title,
            v.source_url,v.article_day,v.date_label,v.partial,cap.observed_at,cap.id capture_id
        FROM versions v JOIN LATERAL (
            SELECT cap.id,cap.title,cap.observed_at FROM captures cap
            WHERE cap.version_id=v.id""" + scope + """
            ORDER BY cap.observed_at DESC,cap.id DESC LIMIT 1
        ) cap ON true
        ORDER BY v.url_key,cap.observed_at DESC,cap.id DESC,v.id DESC
    ), selected_interpretations AS (
        SELECT a.*,i.id interpretation_id,i.items,i.observed_at interpretation_at
        FROM selected_versions a LEFT JOIN LATERAL (
            SELECT id,items,observed_at FROM interpretations
            WHERE version_id=a.version_id AND status='ok'
            ORDER BY observed_at DESC,id DESC LIMIT 1
        ) i ON true""" + where + """
    ), horse_parts AS (
        SELECT a.version_id,p.item,p.ordinality,btrim(p.item->>'horse') horse,
            regexp_replace(lower(normalize(p.item->>'horse',NFKC)), '[[:space:]]+', '', 'g') horse_key
        FROM selected_interpretations a CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(a.items)='array' THEN a.items ELSE '[]'::jsonb END
        ) WITH ORDINALITY AS p(item,ordinality)
        WHERE jsonb_typeof(p.item->'horse')='string'
          AND jsonb_typeof(p.item->'text')='string' AND p.item->>'text' ~ '[^[:space:]]'
    ), horse_cards AS (
        SELECT version_id,horse_key,min(horse) horse,jsonb_agg(item ORDER BY ordinality) items
        FROM horse_parts WHERE """ + match + """
        GROUP BY version_id,horse_key
    ) """
    return sql, params


def horses(c, q):
    q = {k: q[k] for k in ("q", "plan", "site", "from", "to", "match", "p") if q.get(k)}
    q["q"] = q.get("q", "").strip()[:250]
    plan = q.get("plan", "")
    base, params = horse_query(q)
    selected = None
    if plan:
        selected = c.execute(
            "SELECT kind,label FROM plans WHERE id=%s AND kind IN ('history','daily')", (plan,)
        ).fetchone()
        if not selected:
            raise LookupError
    total = c.execute(base + "SELECT count(*) n FROM horse_cards", params).fetchone()["n"]
    page = max(1, min(100000, int(q.get("p") or 1)))
    page = min(page, max(1, (total + 19) // 20))
    result = c.execute(
        base + """SELECT a.version_id,a.capture_id,a.host,a.title,a.source_url,a.article_day,
            a.date_label,a.partial,a.observed_at,a.interpretation_at,g.horse,g.horse_key,g.items
            FROM horse_cards g JOIN selected_interpretations a USING(version_id)
            ORDER BY a.article_day DESC NULLS LAST,a.observed_at DESC,a.version_id,g.horse_key
            LIMIT 20 OFFSET %s""", [*params, (page - 1) * 20]
    ).fetchall()
    candidates = (
        c.execute(
            base + """SELECT horse_key,min(horse) horse,count(*) n FROM horse_cards
                GROUP BY horse_key ORDER BY n DESC,horse_key LIMIT 20""", params
        ).fetchall()
        if q["q"] and q.get("match") != "exact" else []
    )
    hosts = c.execute("SELECT DISTINCT host FROM versions ORDER BY host").fetchall()
    article_filters = {k: q[k] for k in ("plan", "site", "from", "to") if q.get(k)}
    h = (
        ("<p>" + anchor("/run/" + plan, "← " + selected["label"] + " の実行記録") + "</p>" if selected else "")
        + '<p class="lead">馬名から、保存済みのLLM解釈を読めます。同じ記事の同じ馬は1件にまとめ、原文も開けます。</p>'
        + horse_search_form(q, hosts)
    )
    if candidates:
        h += '<div class="horse-candidates"><span>この馬に絞る</span> '
        h += " ".join(
            anchor(linkto("/horses", {**article_filters, "q": r["horse"], "match": "exact"}), r["horse"] + "（" + str(r["n"]) + "件）")
            for r in candidates
        )
        h += "</div>"
    h += '<h2>馬別の解釈　' + f"{total:,}" + ' 件</h2><p class="meta">1件＝1記事・1頭。掲載日が新しい順に表示します。</p>'
    if not total:
        h += '<section class="notice"><p>該当する保存済みの馬別解釈はまだありません。</p><p>記事がないとは限りません。解釈前の記事や、本文には馬名があっても解釈では取り上げられていない記事も、元記事の検索から確認できます。</p></section>'
    back = linkto("/horses", {**q, "p": page})
    for r in result:
        h += render_horse_card(
            {**r, "publisher": site(r["host"])},
            back,
            linkto("/horses", {**article_filters, "q": r["horse"], "match": "exact"}),
        )
    h += '<div class="pager">'
    if page > 1:
        h += anchor(linkto("/horses", {**q, "p": page - 1}), "← 前の20件")
    h += f"<small>{page} / {max(1, (total + 19) // 20)} ページ</small>"
    if page * 20 < total:
        h += anchor(linkto("/horses", {**q, "p": page + 1}), "次の20件 →")
    h += '</div><section class="panel"><h2>元記事も確認する</h2><p>'
    h += anchor(linkto("/articles", {**article_filters, "q": q["q"]}), "この馬名で元記事を検索" if q["q"] else "元記事の一覧を開く")
    h += "　" + anchor(linkto("/articles", {**article_filters, "stage": "no"}), "この範囲の未解釈記事を見る")
    h += '</p><p class="meta">ここでは解釈に記録された馬名を検索しています。未解釈記事は馬名で絞らず一覧できます。</p></section>'
    return layout("horses", "馬別の解釈", h)


def archive(c, q):
    conditions = []
    params = []

    def cond(sql, v):
        conditions.append(sql)
        params.append(v)

    plan = q.get("plan", "")
    selected = None
    if plan:
        if not re.fullmatch(UUID, plan):
            raise ValueError("実行IDを確認してください")
        selected = c.execute(
            "SELECT kind,label FROM plans WHERE id=%s AND kind IN ('history','daily')",
            (plan,),
        ).fetchone()
        if not selected:
            raise LookupError
        cond(
            "EXISTS(SELECT FROM plan_hits h WHERE h.plan_id=%s AND h.capture_id=cap.id)",
            plan,
        )

    for key, col in (("site", "cap.host"), ("body", ""), ("stage", "")):
        v = q.get(key, "")
        if key == "site" and v:
            cond(col + "=%s", v)
        if key == "body" and v in ("yes", "no"):
            conditions.append(
                "v.id IS "
                + (
                    "NOT NULL"
                    if v == "yes"
                    else "NULL AND NOT EXISTS(SELECT FROM versions vx WHERE vx.url_key=cap.url_key)"
                )
            )
        if key == "stage" and v in ("yes", "no"):
            conditions.append(
                ("EXISTS" if v == "yes" else "v.id IS NOT NULL AND NOT EXISTS")
                + "(SELECT FROM interpretations i WHERE i.version_id=v.id AND i.status='ok')"
            )
        if key == "stage" and v in ("queued", "working", "failed"):
            cond("(SELECT state FROM version_progress WHERE id=v.id)=%s", v)
    for k, op in (("from", ">="), ("to", "<=")):
        if q.get(k):
            try:
                v = datetime.strptime(q[k], "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("期間には有効な日付を指定してください。")
            cond("v.article_day" + op + "%s", v)
    term = q.get("q", "").strip()[:250]
    field = q.get("field", "")
    if term and field == "target":
        cond(
            """EXISTS(SELECT FROM interpretations i CROSS JOIN LATERAL jsonb_array_elements(i.items) item
             WHERE i.version_id=v.id AND i.status='ok' AND
             strpos(lower(normalize(concat_ws(' ',item->>'horse',item->>'race'),NFKC)), lower(normalize(%s,NFKC)))>0)""",
            term,
        )
    elif term:
        cond(
            """strpos(lower(normalize(concat_ws(' ',cap.title,v.title,v.body,cap.host,
                 (SELECT string_agg(concat_ws(' ',i.items::text,(i.evidence->'normalized_targets')::text),' ') FROM interpretations i WHERE i.version_id=v.id AND i.status='ok')),NFKC)),
                 lower(normalize(%s,NFKC)))>0""",
            term,
        )
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    base = (
        """SELECT DISTINCT ON (cap.url_key) cap.id,cap.url_key,cap.host,coalesce(v.title,cap.title) title,cap.observed_at,
      v.id version_id,v.article_day,v.date_label,v.partial FROM captures cap LEFT JOIN versions v ON v.id=cap.version_id"""
        + where
        + """ ORDER BY cap.url_key,(v.id IS NOT NULL) DESC,cap.observed_at DESC,cap.id"""
    )
    sort = (
        "article_day DESC NULLS LAST,observed_at DESC,id"
        if q.get("sort") == "date"
        else "observed_at DESC,id"
    )
    page = max(1, min(100000, int(q.get("p") or 1)))
    total = c.execute("SELECT count(*) n FROM (" + base + ") x", params).fetchone()["n"]
    page = min(page, max(1, (total + 19) // 20))
    result = c.execute(
        "SELECT * FROM (" + base + ") x ORDER BY " + sort + " LIMIT 20 OFFSET %s",
        [*params, (page - 1) * 20],
    ).fetchall()
    sites = c.execute(
        "SELECT host,count(DISTINCT url_key) n FROM versions GROUP BY host ORDER BY n DESC,host"
    ).fetchall()
    all_hosts = c.execute("SELECT DISTINCT host FROM captures ORDER BY host").fetchall()
    years = c.execute(
        """SELECT extract(year FROM article_day)::int y,count(DISTINCT url_key) n,count(*) v FROM versions GROUP BY 1 ORDER BY 1 DESC NULLS LAST"""
    ).fetchall()
    t = totals(c)
    form = (
        '<form class="filters" method="get" action="/articles"><label class="grow">馬名・競走・キーワード<input type="search" name="q" value="'
        + ESC(term)
        + '" placeholder="馬名、レース名、本文の言葉"></label>'
    )
    if plan:
        form += '<input type="hidden" name="plan" value="' + ESC(plan) + '">'
    fields = (
        (
            "field",
            "検索範囲",
            [("", "本文・見出し・解釈"), ("target", "LLMが特定した馬・競走")],
        ),
        (
            "site",
            "掲載ホスト",
            [("", "すべて")] + [(r["host"], site(r["host"])) for r in all_hosts],
        ),
        ("body", "本文", [("", "すべて"), ("yes", "保存あり"), ("no", "URLのみ")]),
        (
            "stage",
            "解釈",
            [
                ("", "すべて"),
                ("yes", "解釈済み"),
                ("no", "成功した解釈なし"),
                ("queued", "解釈待ち"),
                ("working", "処理中"),
                ("failed", "失敗"),
            ],
        ),
        ("sort", "並び順", [("", "取得が新しい順"), ("date", "記事日時が新しい順")]),
    )
    for k, title, choices in fields:
        form += (
            "<label>"
            + title
            + '<select name="'
            + k
            + '">'
            + opts(choices, q.get(k, ""))
            + "</select></label>"
        )
    for k, txt in (("from", "掲載日から"), ("to", "掲載日まで")):
        form += (
            "<label>"
            + txt
            + '<input type="date" name="'
            + k
            + '" value="'
            + ESC(q.get(k, ""))
            + '"></label>'
        )
    form += "<button>検索</button></form>"
    h = (
        (
            (
                "<p>"
                + anchor("/run/" + plan, "← " + selected["label"] + " の実行記録")
                + "</p>"
            )
            if selected
            else trial_links(c)
            if trial()
            else ""
        )
        + form
        + (
            '<p class="notice">馬についての解釈を読むなら　'
            + anchor(
                linkto("/horses", {k: q[k] for k in ("q", "plan", "site", "from", "to") if q.get(k)}),
                "「" + term + "」を馬別の解釈で検索 →",
            )
            + "</p>"
            if term else ""
        )
        + f'<h2>検索結果　{total:,} URL</h2><ul class="articles">'
    )
    for r in result:
        ii = (
            c.execute(
                "SELECT items FROM interpretations WHERE version_id=%s AND status='ok' ORDER BY observed_at DESC LIMIT 1",
                (r["version_id"],),
            ).fetchone()
            if r["version_id"]
            else None
        )
        targets = list(dict.fromkeys(item_name(x) for x in ii["items"])) if ii else []
        h += (
            "<li><div><h3>"
            + anchor(
                linkto("/article/" + r["id"], {"back": linkto("/articles", q)}),
                r["title"] or r["url_key"],
            )
            + '</h3><div class="meta">'
            + ESC(site(r["host"]))
            + "　掲載・更新 "
            + ESC(r["date_label"] or "不明")
            + "　取得 "
            + stamp(r["observed_at"])
            + "</div><small>"
            + ESC("、".join(targets[:3]) or "対象未確定")
            + "</small></div><div>"
            + badge(
                ("公開部分" if r["partial"] else "本文あり")
                if r["version_id"]
                else "URLのみ",
                "neutral",
            )
        )
        if r["version_id"]:
            progress = c.execute(
                "SELECT state FROM version_progress WHERE id=%s", (r["version_id"],)
            ).fetchone()
            h += " " + badge(progress_label(progress["state"]), "" if ii else "neutral")
            if ii:
                h += "<small> 解釈 " + str(len(ii["items"])) + " 項目</small>"
        h += "</div></li>"
    h += '</ul><div class="pager">'
    if page > 1:
        h += anchor(linkto("/articles", {**q, "p": page - 1}), "← 前の20件")
    h += f"<small>{page} / {max(1, (total + 19) // 20)} ページ</small>"
    if page * 20 < total:
        h += anchor(linkto("/articles", {**q, "p": page + 1}), "次の20件 →")
    h += (
        "</div><h2>"
        + ("今回のテストDB全体" if trial() else "本番DB全体")
        + "</h2>"
        + metrics(t)
        + '<div class="blocks">'
        + panel(
            "掲載ホスト別の本文URL",
            table(
                ["媒体", "URL"],
                [
                    (
                        anchor(
                            linkto("/articles", {"site": s["host"]}), site(s["host"])
                        ),
                        s["n"],
                    )
                    for s in sites
                ],
            ),
        )
        + panel(
            "記事の表示年別",
            table(
                ["年", "本文URL", "保存版"],
                [(r["y"] or "日時不明", r["n"], r["v"]) for r in years],
            )
            + f"<small>DB全体で本文のないURLは {t['links']:,} 件。</small>",
        )
        + "</div>"
    )
    return layout(
        "articles", pattern(selected["kind"]) if selected else "記事を探す", h
    )


def detail(c, ident, back="/articles"):
    parsed = urlsplit(back)
    if parsed.scheme or parsed.netloc or parsed.path not in ("/articles", "/horses"):
        back = "/articles"
    cap = c.execute("SELECT * FROM captures WHERE id=%s", (ident,)).fetchone()
    if not cap:
        raise LookupError
    v = (
        c.execute("SELECT * FROM versions WHERE id=%s", (cap["version_id"],)).fetchone()
        if cap["version_id"]
        else None
    )
    heading = (v or cap)["title"] or "見出し不明"
    membership = c.execute(
        """SELECT DISTINCT p.id,p.kind FROM plan_hits h JOIN plans p ON p.id=h.plan_id
        JOIN captures a ON a.id=h.capture_id WHERE a.version_id=%s OR a.id=%s ORDER BY p.kind""",
        (cap["version_id"], ident),
    ).fetchall()
    h = (
        "<p>"
        + anchor(back, "← 馬別の解釈" if urlsplit(back).path == "/horses" else "← 記事一覧")
        + "".join(
            "　"
            + anchor(linkto("/articles", {"plan": str(m["id"])}), pattern(m["kind"]))
            for m in membership
        )
        + "</p>"
        + panel(
            "出典と保存情報",
            rows(
                [
                    ("掲載ホスト", ESC(site(cap["host"]) + "　" + cap["host"])),
                    (
                        "掲載・更新の表示",
                        ESC(v["date_label"] if v and v["date_label"] else "不明"),
                    ),
                    ("取得時刻（JST）", stamp(cap["observed_at"])),
                    ("元記事", external(cap["source_url"])),
                    (
                        "受領状態",
                        ESC(
                            {"ok": "本文保存", "partial": "公開部分を保存"}.get(
                                cap["status"], label(cap["status"])
                            )
                        ),
                    ),
                    ("取得ID", ESC(cap["id"])),
                    ("版ID", ESC(cap["version_id"] or "—")),
                ]
            ),
        )
    )
    if v:
        h += (
            '<p class="jump">'
            + anchor("#source", "保存した原文")
            + "　"
            + anchor("#interpretation", "馬・競走別のLLM解釈")
            + "</p>"
            '<div class="comparison"><section class="article" id="source"><h2>保存した原文</h2>'
            + badge("公開部分のみ" if v["partial"] else "本文保存", "neutral")
            + '<p class="sourcebody">'
            + ESC(v["body"])
            + "</p></section>"
        )
        it = c.execute(
            "SELECT * FROM interpretations WHERE version_id=%s ORDER BY observed_at DESC",
            (v["id"],),
        ).fetchall()
        h += '<section class="article" id="interpretation"><h2>馬・競走別のLLM解釈</h2>'
        if not it:
            progress = c.execute(
                "SELECT state FROM version_progress WHERE id=%s", (v["id"],)
            ).fetchone()
            h += "<p>" + progress_label(progress["state"]) + "・対象未確定</p>"
        for i in it:
            h += (
                "<p>"
                + badge("解釈済み" if i["status"] == "ok" else label(i["status"]))
                + " <small>"
                + stamp(i["observed_at"])
                + "　"
                + ("日時付き入力" if i["input_key"] else "旧入力・本文のみ")
                + "</small></p>"
            )
            if i["status"] == "ok" and not i["items"]:
                h += "<p>独立した見解の項目は0件。</p>"
            for index, item in enumerate(i["items"]):
                phase = {
                    "pre": "事前",
                    "post": "事後",
                    "mixed": "混在",
                    "unknown": "時点不明",
                }.get(item["phase"], "不明")
                targets = i["evidence"].get("normalized_targets", [])
                key = targets[index].get("race_key") if index < len(targets) else None
                h += (
                    '<div class="meaning"><b>'
                    + ESC(item_name(item))
                    + "</b>　"
                    + badge(phase, "neutral")
                    + " "
                    + ESC(key or "")
                    + "<p>"
                    + ESC(item["text"])
                    + "</p></div>"
                )
        h += anchor("#source", "保存した原文へ戻る") + "</section></div>"
    else:
        h += panel("本文の保存状態", "URLと取得時の状態を保存。本文は未取得。")
    versions = c.execute(
        """SELECT DISTINCT ON (v.id) v.id,cap.id capture,v.observed_at FROM versions v JOIN captures cap ON cap.version_id=v.id WHERE v.url_key=%s ORDER BY v.id,cap.observed_at""",
        (cap["url_key"],),
    ).fetchall()
    if versions:
        h += panel(
            "このURLの保存版",
            table(
                ["取得 JST", "版"],
                [
                    (
                        stamp(x["observed_at"]),
                        anchor("/article/" + x["capture"], x["id"][:16]),
                    )
                    for x in sorted(
                        versions, key=lambda a: a["observed_at"], reverse=True
                    )
                ],
            ),
        )
    linked = []
    for entry in c.execute(
        "SELECT relation FROM source_relations WHERE strpos(relation::text,%s)>0",
        (cap["source_url"],),
    ):
        container = entry["relation"]
        for rel in container.get("relations", [container]):
            urls = [
                rel.get(k)
                for k in ("source", "original", "distributor", "publisher_other_url")
            ] + rel.get("mirrors", [])
            if cap["source_url"] in urls:
                linked.extend(
                    (rel.get("basis") or "同一取材の掲載先", external(u))
                    for u in urls
                    if isinstance(u, str) and u != cap["source_url"]
                )
    if linked:
        h += panel("確認済みの配信関係", rows(linked))
    return layout("articles", heading, h)


def legacy(c, ident=None):
    if ident:
        a = c.execute(
            "SELECT * FROM legacy_articles WHERE article_id=%s", (ident,)
        ).fetchone()
        if not a:
            raise LookupError
        h = (
            "<p>"
            + anchor("/legacy", "← 移行前の資料一覧")
            + "</p>"
            + panel(
                "移行前の記録",
                rows(
                    [
                        ("保存種別", ESC(a["body_kind"])),
                        ("媒体", ESC(a["media"] or "不明")),
                        ("掲載表示", ESC(a["published_text"] or "不明")),
                        ("取得 JST", stamp(a["collected_at"])),
                        ("出典", external(a["source_url"])),
                    ]
                ),
            )
        )
        return layout(
            "articles",
            a["title"] or "旧資料",
            h
            + '<section class="article"><h2>旧DBの保存内容</h2><p class="sourcebody">'
            + ESC(a["body"] or "本文なし")
            + "</p></section>",
        )
    data = c.execute(
        "SELECT article_id,title,body_kind,media,collected_at FROM legacy_articles ORDER BY collected_at DESC"
    ).fetchall()
    return layout(
        "articles",
        "移行前の通常DB資料",
        '<p class="sub">研究コーパスの移行前に保存した '
        + str(len(data))
        + " 件。保存種別は当時の記録に従います。</p>"
        + table(
            ["見出し", "媒体", "旧保存種別", "取得 JST"],
            [
                (
                    anchor("/legacy/" + str(a["article_id"]), a["title"] or "旧資料"),
                    ESC(a["media"]),
                    ESC(a["body_kind"]),
                    stamp(a["collected_at"]),
                )
                for a in data
            ],
        ),
    )


def saved_progress(c, ident):
    actor = "saved-articles/" + str(ident)
    return c.execute(
        """WITH work AS (
               SELECT state,updated_at,target->>'version' version,target->>'capture' capture,
                      target->>'reuse_id' accepted FROM work_items WHERE plan_id=%s
           ), successful AS (
               SELECT DISTINCT ON (w.version) w.version,i.id,jsonb_array_length(i.items) n
               FROM work w JOIN interpretations i ON i.version_id=w.version AND i.capture_id=w.capture
               WHERE i.status='ok' AND (i.id=w.accepted OR i.evidence->>'actor'=%s)
               ORDER BY w.version,i.observed_at DESC,i.id
           )
           SELECT count(*) total,count(s.id) successful,count(*) FILTER(WHERE s.id=w.accepted) reused,
             count(*) FILTER(WHERE s.id IS NOT NULL AND w.accepted IS NULL) generated,
             coalesce(sum(s.n),0) summaries,count(*) FILTER(WHERE s.n=0) empty,
             count(*) FILTER(WHERE w.state='queued') queued,count(*) FILTER(WHERE w.state='working') working,
             count(*) FILTER(WHERE w.state='failed') failed,
             max(w.updated_at) FILTER(WHERE w.state IN ('done','partial','failed')) last_finished,
             (SELECT count(*) FROM interpretations i WHERE i.evidence->>'actor'=%s) attempts
           FROM work w LEFT JOIN successful s ON s.version=w.version""", (ident, actor, actor),
    ).fetchone()


def run_detail(c, ident, q):
    p = c.execute("SELECT * FROM plans WHERE id=%s", (ident,)).fetchone()
    if not p:
        raise LookupError
    if p["state"] == "running" and not has_worker(c, p["id"]):
        p["state"] = "中断・再開可"
    page = max(1, int(q.get("p") or 1))
    count = c.execute(
        "SELECT count(*) n FROM work_items WHERE plan_id=%s", (ident,)
    ).fetchone()["n"]
    items = c.execute(
        "SELECT * FROM work_items WHERE plan_id=%s ORDER BY position LIMIT 50 OFFSET %s",
        (ident, (page - 1) * 50),
    ).fetchall()
    h = panel(
        "実行記録",
        rows(
            [
                ("状態", badge(label(p["state"]))),
                ("区分", ESC(label(p["kind"]) + " ／ " + label(p["scope"]))),
                ("開始 JST", stamp(p["started_at"])),
                ("終了 JST", stamp(p["ended_at"])),
                ("最終進捗 JST", stamp(p["updated_at"])),
                ("実行ID", ESC(ident)),
            ]
        ),
    )
    if p["kind"] in ("history", "daily"):
        h = source_summary(c, ident, p["kind"]) + h
    fixed = p["scope"] == "saved_versions"
    if fixed:
        s = saved_progress(c, ident)
        h += panel("今回の固定対象", rows([
            ("対象版数", f"{s['total']:,}"),
            ("保存済み成功版", f"{s['successful']:,}（既存再利用 {s['reused']:,} ／ 新規成功 {s['generated']:,}）"),
            ("要約", f"{s['summaries']:,}件 ／ 要約0件の成功 {s['empty']:,}版"),
            ("作業状態", f"待機 {s['queued']:,} ／ 処理中 {s['working']:,} ／ 失敗 {s['failed']:,}"),
            ("今回のモデル要求記録", f"{s['attempts']:,}回"),
            ("直近の作業完了 JST", stamp(s["last_finished"])),
        ]))
        if p["state"] == "paused" and p.get("error"):
            h += panel("停止時の記録", ESC(p["error"]))
    result = []
    for it in items:
        t = it["target"]
        r = it["result"] or {}
        hits = r.get("hits", [])
        if fixed:
            result.append((it["position"] + 1, anchor("/article/" + t["capture"], t["capture"]),
                           ESC(label(it["state"])), ESC(r.get("error") or
                           ("既存結果を再利用" if t.get("reuse_id") and it["state"] == "done" else
                            "解釈を保存" if it["state"] == "done" else "—"))))
            continue
        result.append(
            (
                it["position"] + 1,
                ESC(
                    t.get("name")
                    or t.get("race_key")
                    or t.get("key")
                    or t.get("capture")
                    or t.get("day")
                ),
                ESC(label(t.get("source") or t["type"])),
                ESC(label(it["state"])),
                ESC(label(r.get("route_status") or r.get("error") or "—")),
                f"{r.get('saved', 0)} / {r.get('known', 0)} / {r.get('failed', 0)}",
                "<br>".join(
                    anchor("/article/" + a["capture_id"], a.get("title") or "取得記録")
                    for a in hits
                ),
            )
        )
    h += table(
        ["位置", "保存記事", "状態", "結果"] if fixed else
        ["位置", "対象", "経路", "状態", "結果", "新規 / 既知 / 失敗", "取得記録"],
        result,
    )
    if page > 1:
        h += anchor(linkto("/run/" + ident, {"p": page - 1}), "← 前の50件") + "　"
    if page * 50 < count:
        h += anchor(linkto("/run/" + ident, {"p": page + 1}), "次の50件 →")
    return layout("runs", p["label"], h)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_error(405)

    do_PUT = do_PATCH = do_DELETE = do_POST

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlsplit(self.path)
        status = 200
        mime = "text/html; charset=utf-8"
        try:
            q = {k: v[0] for k, v in parse_qs(u.query, max_num_fields=20).items()}
            if u.path == "/dashboard.css":
                mime = "text/css; charset=utf-8"
                out = Path(__file__).with_suffix(".css").read_text()
            else:
                with connect(reader=True) as c:
                    if u.path == "/":
                        out = home(c)
                    elif u.path == "/horses":
                        out = horses(c, q)
                    elif u.path == "/articles":
                        out = archive(c, q)
                    elif u.path == "/runs":
                        out = layout("runs", "実行履歴", runs_table(run_rows(c, 200)))
                    elif u.path == "/legacy":
                        out = legacy(c)
                    elif re.fullmatch("/legacy/" + UUID, u.path):
                        out = legacy(c, u.path.rsplit("/", 1)[1])
                    elif re.fullmatch(r"/article/[a-f0-9]{32}", u.path):
                        out = detail(
                            c, u.path.rsplit("/", 1)[1], q.get("back", "/articles")
                        )
                    elif re.fullmatch("/run/" + UUID, u.path):
                        out = run_detail(c, u.path.rsplit("/", 1)[1], q)
                    else:
                        raise LookupError
        except LookupError:
            status = 404
            out = layout("", "見つかりません", anchor("/articles", "記事一覧へ"))
        except ValueError as e:
            status = 400
            out = layout("", "検索条件を確認してください", ESC(e))
        except Exception as e:
            self.log_error("read failed: %s", type(e).__name__)
            status = 503
            out = layout(
                "",
                "資料庫に接続できません",
                "VM15のDB・閲覧サービスの状態を確認してください。",
            )
        b = out.encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)


if __name__ == "__main__":
    ThreadingHTTPServer(
        ("192.168.0.14", PROFILES[database()][2]), Handler
    ).serve_forever()

