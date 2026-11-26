"""Read a fixed coverage plan. Counts refer to saved public text and deduplicated URL keys."""

import argparse
import collections
import json
import re
import statistics
import unicodedata
from datetime import date
from pathlib import Path

from corpus import connect
from discovery import VENUES, race_alias
from routes import url_key

KATA = r"ァ-ヺー"
PRE = re.compile(
    "追い切り|追切|出走予定|調教|前哨戦|枠順|展望|有力|狙い|最終調整|出走馬|出馬表|登録馬|が登録|参戦|予想|見どころ|出走へ"
)
POST = re.compile(
    "レース後|コメント|回顧|騎手談|敗因|制す|制覇|勝利|初勝利|差し切|逃げ切|着順|振り返|完勝|快勝|Ｖ|優勝|惜敗|連勝|勝因"
)
OPINION = re.compile(
    "追い切|追切|末脚|折り合|折り合い|状態|仕上が|手応え|気性|出遅れ|馬場|伸び|出脚|不利|位置取|直線|粘|差し切|余力|距離|調子|ペース|スタート|乗り|騎乗|進路|自分の競馬|調教師|厩舎|[「『]"
)
VENUE_NO = {k: v for k, v in VENUES.items()}


def textnorm(value):
    return unicodedata.normalize("NFKC", value or "").replace("\u3000", " ")


def mention(name, body):
    pattern = (
        r"(?<![" + KATA + r"])" + re.escape(textnorm(name)) + r"(?![" + KATA + r"])"
    )
    return list(re.finditer(pattern, body))


def substantive(name, body, ms):
    """Limit the context to this horse's sentence or a short comment headed by its name."""
    for m in ms:
        k = m.start()
        end = m.end()
        left = max(body.rfind("。", 0, k), body.rfind("\n", 0, k)) + 1
        cut = re.search(r"[。\n]", body[end : end + 165])
        right = end + (cut.start() if cut else 165)
        sentence = body[max(left, k - 35) : right]
        if len(sentence) >= len(name) + 9 and OPINION.search(sentence):
            return True
        following = body[end : end + 130]
        if re.match(r".{0,30}(?:騎手|調教師|助手|師)[)）]?\s*[「『]", following, re.S):
            return True
        if re.match(
            r"[\s（(]*\d+番人気.{0,30}(?:馬場|直線|伸び|出遅れ)", following, re.S
        ):
            return True
    return False


def phase(race, doc, body):
    if not race or not doc["article_day"]:
        return None
    day = date.fromisoformat(race["day"])
    gap = (doc["article_day"] - day).days
    if not -14 <= gap <= 15:
        return None
    title = race_alias(doc["title"])
    head = race_alias(body[:650])
    race_name = race_alias(race["race"])
    common = race["race"] in ("1勝", "2勝", "3勝", "未勝利", "新馬")
    loc = VENUE_NO[race["venue"]]
    shorthand = bool(
        re.search(
            loc + r"(?:競馬場)?第?0?" + str(int(race["no"])) + r"(?:R|レース)",
            title + " " + head[:220],
            re.I,
        )
    )
    focus = race_name in title or (not common and race_name in head[:180])
    if not (shorthand and (gap == 0 or loc in title) or not common and focus):
        return None
    if (
        common
        and shorthand
        and gap != 0
        and not (race_name in title or date_label(day) in head)
    ):
        return None
    if gap < 0:
        return "pre" if PRE.search(title + head[:180]) else None
    if gap > 0:
        return (
            "post"
            if POST.search(title + head[:240])
            and not ("登録" in title or "展望" in title)
            else None
        )
    if POST.search(title) or re.search(
        "レース後|勝った|着に入|優勝した|勝利した", head
    ):
        return "post"
    if PRE.search(title + head[:150]):
        return "pre"
    return None


def date_label(d):
    return f"{d.month}月{d.day}日"


MEASURES = (
    "direct",
    "primary",
    "count",
    "pre",
    "post",
    "substantive",
    "pre_thick",
    "post_thick",
    "primary_pre",
    "primary_post",
    "primary_pre_thick",
    "primary_post_thick",
    "primary_substantive",
)


def aggregate(rows):
    n = len(rows)
    amounts = [r["count"] for r in rows]
    return {
        "n": n,
        "unique": len({r["horse_id"] for r in rows}),
        **{
            key: sum(bool(r[key]) for r in rows) for key in (*MEASURES, "any_candidate")
        },
        "zero": amounts.count(0),
        "one": amounts.count(1),
        "multi": sum(x > 1 for x in amounts),
        "median": statistics.median(amounts) if n else 0,
        "min": min(amounts, default=0),
        "max": max(amounts, default=0),
    }


def parallel_texts(docs):
    """Find conspicuous overlap between the archive and portal within one day."""
    grams = {}
    for url, doc in docs.items():
        s = re.sub(
            r"[^一-龯ぁ-んァ-ヶa-zA-Z0-9]",
            "",
            textnorm(doc["body"].removeprefix(doc["title"])),
        )
        grams[url] = {s[i : i + 8] for i in range(len(s) - 7)}
    pairs = []
    for url, doc in docs.items():
        if doc["host"] != "www.radionikkei.jp" or not doc["article_day"]:
            continue
        for other, portal in docs.items():
            if portal["host"] != "news.netkeiba.com" or not portal["article_day"]:
                continue
            if abs((doc["article_day"] - portal["article_day"]).days) > 1:
                continue
            same = len(grams[url] & grams[other])
            if same >= 140 and same / min(len(grams[url]), len(grams[other])) >= 0.7:
                pairs.append(
                    {
                        "source": url,
                        "mirrors": [other],
                        "captures": [doc["cid"], portal["cid"]],
                        "basis": "同じ競走の談話本文が広範囲に一致。表示したURLごとに保存。",
                    }
                )
    return pairs


def analyze(ident, sample):
    with connect() as c:
        plan = c.execute("SELECT * FROM plans WHERE id=%s", (ident,)).fetchone()
        work = c.execute(
            "SELECT * FROM work_items WHERE plan_id=%s ORDER BY position", (ident,)
        ).fetchall()
        captures = {
            r["cid"]: r
            for r in c.execute(
                """SELECT cap.id cid,cap.status,cap.url_key,v.title,v.host,v.article_day,v.body,v.id vid,v.partial
            FROM work_items w CROSS JOIN LATERAL jsonb_array_elements(w.result->'hits') hit
            JOIN captures cap ON cap.id=hit->>'capture_id' LEFT JOIN versions v ON v.id=cap.version_id
            WHERE w.plan_id=%s""",
                (ident,),
            )
        }
        discovered = {
            r["url"]
            for r in c.execute(
                """SELECT distinct candidate->>'url' url FROM work_items w
            CROSS JOIN LATERAL jsonb_array_elements_text(w.result->'observations') ref
            JOIN observations o ON o.id=ref AND o.family='listings'
            CROSS JOIN LATERAL jsonb_array_elements(o.data->'candidates') candidate WHERE w.plan_id=%s""",
                (ident,),
            )
        }
    pools = collections.defaultdict(lambda: collections.defaultdict(dict))
    direct = collections.defaultdict(set)
    candidate_names = set()
    routes = collections.defaultdict(collections.Counter)
    examples = {}
    all_docs = {}
    all_versions = set()
    preview = set()
    links = set()
    failed = set()
    for w in work:
        t = w["target"]
        r = w["result"] or {}
        group = t.get("group", t.get("race_key"))
        src = t["source"]
        if group == "aux":
            group = "aux/" + t["horse_id"]
        b = routes[src]
        b["targets"] += 1
        b["work_" + w["state"]] += 1
        for key in ("candidate_count", "saved", "known", "failed", "links_only"):
            b[key] += r.get(key, 0)
        b[r.get("route_status", "error")] += 1
        hid = t.get("horse_id")
        if hid and r.get("candidate_count"):
            candidate_names.add((group, hid))
        for hit in r.get("hits", []):
            doc = captures[hit["capture_id"]]
            u = doc["url_key"]
            if not doc["vid"]:
                (links if doc["status"] == "metadata_only" else failed).add(u)
                continue
            all_versions.add(doc["vid"])
            all_docs[u] = doc
            if doc["partial"]:
                preview.add(u)
            pools[group][src][u] = doc
            if src == "net":
                direct[(group, hid)].add(u)
    output = []
    for race in [*sample["races"], {"key": "aux", "horses": sample["aux"]}]:
        for horse in race["horses"]:
            g = race["key"] if race["key"] != "aux" else "aux/" + horse["horse_id"]
            stages = pools[g]
            base = stages["net"]
            docs = {**base, **stages["radio"], **stages["blog"]}
            record = dict(
                horse_id=horse["horse_id"],
                name=horse["name"],
                group=race["key"],
                pop=horse.get("popularity"),
                grade=race.get("grade"),
                era=race.get("era"),
                any_candidate=(g, horse["horse_id"]) in candidate_names,
            )
            sets = {k: set() for k in MEASURES}
            record["examples"] = {}
            for u, doc in docs.items():
                body = textnorm(doc["body"])
                hits = mention(horse["name"], body)
                if not hits:
                    continue
                d = doc["article_day"]
                active = bool(
                    d
                    and date.fromisoformat(horse["first"])
                    <= d
                    <= date.fromisoformat(horse["last"])
                )
                timing = phase(race if race["key"] != "aux" else None, doc, body)
                thick = substantive(horse["name"], body, hits)
                if active:
                    sets["count"].add(u)
                    if u in base:
                        sets["primary"].add(u)
                    if u in direct[(g, horse["horse_id"])]:
                        sets["direct"].add(u)
                    if thick:
                        sets["substantive"].add(u)
                        if u in base:
                            sets["primary_substantive"].add(u)
                    record["examples"].setdefault(
                        "comment" if thick else "mention", doc["cid"]
                    )
                if timing:
                    sets[timing].add(u)
                    if u in base:
                        sets["primary_" + timing].add(u)
                    if thick:
                        sets[timing + "_thick"].add(u)
                        if u in base:
                            sets["primary_" + timing + "_thick"].add(u)
                    record["examples"].setdefault(
                        timing + ("_thick" if thick else "_mention"), doc["cid"]
                    )
                category = (
                    timing or ("comment" if thick else "mention")
                    if active or timing
                    else None
                )
                if category and len(examples.setdefault(category, [])) < 30:
                    examples[category].append(
                        dict(
                            name=horse["name"],
                            race=race["key"],
                            title=doc["title"],
                            id=doc["cid"],
                            url=u,
                        )
                    )
            record.update({k: len(v) for k, v in sets.items()})
            output.append(record)
    main = [r for r in output if r["group"] != "aux"]
    aux = [r for r in output if r["group"] == "aux"]
    groups = {"競走標本": aggregate(main), "名簿補助": aggregate(aux)}
    for race in sample["races"]:
        groups[race["key"]] = aggregate([r for r in main if r["group"] == race["key"]])
    for key in ("grade", "era"):
        for v in dict.fromkeys(r[key] for r in main):
            groups[v] = aggregate([r for r in main if r[key] == v])
    for tag, fn in (
        ("1〜3番人気", lambda x: x and x <= 3),
        ("4番人気以下", lambda x: x and x > 3),
        ("人気不明", lambda x: not x),
    ):
        groups[tag] = aggregate([r for r in main if fn(r["pop"])])
    # Exact same bodies at different URLs are evidence of a possible copy, not a universal syndication detector.
    import hashlib

    texts = collections.defaultdict(set)
    for u, d in all_docs.items():
        texts[hashlib.sha256(d["body"].encode()).hexdigest()].add(u)
    return {
        "id": str(plan["id"]),
        "state": plan["state"],
        "groups": groups,
        "rows": output,
        "routes": routes,
        "candidate_urls": len({url_key(u) for u in discovered}),
        "saved_urls": len(all_docs),
        "versions": len(all_versions),
        "partial_urls": len(preview),
        "metadata_urls": len(links),
        "failed_urls": len(failed),
        "hosts": dict(collections.Counter(d["host"] for d in all_docs.values())),
        "identical_bodies_multiple_urls": sum(len(us) > 1 for us in texts.values()),
        "examples": examples,
        "parallel_texts": parallel_texts(all_docs),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("id")
    p.add_argument("sample", type=Path)
    a = p.parse_args()
    print(
        json.dumps(
            analyze(a.id, json.loads(a.sample.read_bytes())),
            ensure_ascii=False,
            default=str,
        )
    )
