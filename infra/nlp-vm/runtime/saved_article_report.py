"""Check a fixed trial pass against its files, database and live reading pages."""

import argparse
import json
import os
import statistics
import sys
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

from bs4 import BeautifulSoup

import research
from corpus import connect
from dashboard import has_worker, label, saved_progress, stamp
from profile_db import trial
from saved_articles import target_digest


DASHBOARD = "http://192.168.0.14:8787"
OLD_PLAN = "a2f95417-8ea6-5df2-8225-1a46461f2bc7"
# Two new results observed during this pass and one retained result from trial B.
EXAMPLES = (
    ("bb9e1cc7fae244d7b0521ce84f5686b4", "history", ["トーアアイギス"]),
    ("19d975758a7e4ecda4b790020dc6f8f1", "daily", ["ワンスフォーユー", "エランヴィータ"]),
    ("88c700e4725845afbfd7ed56ad4bd820", "daily", ["カランダガン"]),
)


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def page(path):
    require(path.startswith("/") and not urlsplit(path).netloc, "Expected a local Dashboard path")
    with urlopen(DASHBOARD + path, timeout=30) as response:
        return BeautifulSoup(response.read(), "html.parser", from_encoding="utf-8")


def find_card(search, title):
    visited = set()
    while search and search not in visited:
        visited.add(search)
        results = page(search)
        for card in results.select(".horse-card"):
            if card.select_one(".horse-source-title").get_text() == title:
                return search, card
        more = results.find("a", string="次の20件 →")
        search = more["href"] if more else None
    raise ValueError("Horse search did not show the saved article: " + title)


def check_examples(c, plan):
    links = []
    for capture, kind, horses in EXAMPLES:
        row = c.execute(
            """SELECT v.body,v.source_url,v.title,v.host,v.article_day,i.items,p.id::text source
               FROM work_items w JOIN versions v ON v.id=w.target->>'version'
               JOIN interpretations i ON i.id=w.result->>'interpretation'
               JOIN plans p ON w.target->'origins' ? p.id::text
               WHERE w.plan_id=%s AND w.target->>'capture'=%s AND p.kind=%s""",
            (plan, capture, kind),
        ).fetchone()
        require(row, "Missing displayed result: " + capture)
        for horse in horses:
            terms = {"q": horse, "match": "exact", "plan": row["source"], "site": row["host"]}
            if row["article_day"]:
                terms.update(dict.fromkeys(("from", "to"), row["article_day"].isoformat()))
            search, card = find_card("/horses?" + urlencode(terms), row["title"])
            expected = [item["text"] for item in row["items"] if item.get("horse") == horse]
            require(expected and [p.get_text() for p in card.select(".horse-summary")] == expected, horse)
            targets = [a["href"] for a in card.select(".horse-links a")]
            detail = page(targets[0])
            require(row["source_url"] in targets and detail.find("a", href=row["source_url"]), capture)
            require(detail.select_one("#source .sourcebody").get_text() == row["body"], capture)
            texts = [p.get_text() for p in detail.select("#interpretation .meaning p")]
            require(all(i["text"] in texts for i in row["items"]), capture)
            back = urlsplit(detail.find("a", string="← 馬別の解釈")["href"])
            selected = parse_qs(urlsplit(search).query)
            selected.setdefault("p", ["1"])
            require(back.path == "/horses" and parse_qs(back.query) == selected, "Missing return to the selected horse")
            links.append(dict(horse=horse, capture=capture, items=len(row["items"]), search=search, detail=targets[0]))
    return links


def check_sources(c, folder, targets, sources):
    original = json.loads((folder / "source-ids.json").read_bytes())
    for table in ("versions", "captures"):
        ids = [r["id"] for r in c.execute("SELECT id FROM " + table + " ORDER BY id")]
        require(ids == original[table], "Source IDs changed: " + table)
    require({p.stem for p in (research.ROOT / "captures").glob("*.json")} == set(original["captures"]), "Capture files changed")
    require({t["version"] for t in targets} == set(original["versions"]), "Version scope changed")
    origins = c.execute(
        """SELECT cap.version_id,array_agg(DISTINCT h.plan_id::text ORDER BY h.plan_id::text) sources
           FROM plan_hits h JOIN captures cap ON cap.id=h.capture_id
           WHERE h.plan_id=ANY(%s) AND cap.version_id IS NOT NULL GROUP BY cap.version_id""", (sources,)
    )
    require({r["version_id"]: r["sources"] for r in origins} == {t["version"]: t["origins"] for t in targets}, "Source membership changed")
    counts = c.execute("SELECT state,count(*) n FROM work_items WHERE plan_id=%s GROUP BY state", (OLD_PLAN,))
    require({r["state"]: r["n"] for r in counts} == {"done": 101, "failed": 1, "queued": 2336}, "Old queue changed")
    require(c.execute("SELECT state='paused' AND stop_requested AS stopped FROM plans WHERE id=%s", (OLD_PLAN,)).fetchone()["stopped"], "Old plan resumed")
    return {table: len(ids) for table, ids in original.items()}


def check_results(c, plan, targets, config):
    rows = c.execute(
        """SELECT w.target,w.state,w.result,i.id,i.input_key,i.capture_id,i.version_id,i.skill_hash,
                  i.status,i.items,i.evidence->'settings' settings,i.evidence->>'actor' actor
           FROM work_items w LEFT JOIN interpretations i ON i.id=w.result->>'interpretation'
           WHERE w.plan_id=%s ORDER BY w.position""", (plan,)
    ).fetchall()
    require([r["target"] for r in rows] == targets, "Work list differs from the manifest")
    counts = Counter()
    failures = []
    for r in rows:
        t = r["target"]
        if r["state"] == "failed":
            failures.append(dict(version=t["version"], capture=t["capture"], error=r["result"].get("error") or r["result"].get("route_status")))
        elif r["state"] == "done":
            stored = research.read("interpretations", r["id"])
            require(r["status"] == stored["status"] == "ok" and stored["id"] == r["id"], t["version"])
            require(r["capture_id"] == stored["capture_id"] == t["capture"] and r["version_id"] == stored["version_id"] == t["version"], t["version"])
            require(r["input_key"] == stored["input_key"] and r["skill_hash"] == stored["skill_sha256"] == config["skill_sha256"], t["version"])
            require(r["settings"] == stored["settings"] == config["settings"] and json.loads(stored["content"])["items"] == r["items"], t["version"])
            if t["reuse_id"]:
                require(r["id"] == t["reuse_id"] and r["result"].get("reused"), t["version"])
                counts["reused"] += 1
            else:
                require(r["actor"] == "saved-articles/" + plan, t["version"])
                counts["generated"] += 1
            counts["summaries"] += len(r["items"])
            counts["empty"] += int(not r["items"])
        else:
            require(r["state"] in ("queued", "working"), t["version"])
    return counts, failures


def measures(c, plan):
    records = c.execute(
        """SELECT (evidence->>'seconds')::float8 seconds,evidence->'usage' usage,status,
                  evidence->>'finish_reason' finish,version_id FROM interpretations
           WHERE evidence->>'actor'=%s ORDER BY observed_at""", ("saved-articles/" + plan,)
    ).fetchall()
    times = [r["seconds"] for r in records if r["seconds"] is not None]
    slowest = max(records, key=lambda r: r["seconds"] or 0, default={})
    tokens = Counter()
    for r in records:
        usage = r["usage"] or {}
        for k in ("prompt_tokens", "completion_tokens"):
            tokens[k] += usage.get(k) or 0
        tokens["reasoning_tokens"] += (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    return dict(attempts=len(records), versions=len({r["version_id"] for r in records}), timed=len(times),
                sum_seconds=round(sum(times), 2), median=statistics.median(times) if times else None,
                maximum=slowest.get("seconds"), longest=slowest.get("version_id"), tokens=dict(tokens),
                at_least_120s=sum(t >= 120 for t in times), at_least_600s=sum(t >= 600 for t in times),
                finish=dict(Counter(r["finish"] or "応答理由なし" for r in records)))


def final_section(report):
    s, m, t = report["progress"], report["measurements"], report["runtime"]
    heading = "一巡終了・失敗あり" if s["failed"] else "一巡終了・全版成功"
    lines = [f"## {heading}", "", f"終了 {report['ended']} JST。VM15での照合は {stamp(t['observed'])} JST。",
             "", "| 固定対象 | 既存再利用 | 新規成功 | 失敗 | 待機 | 処理中 | 要約 | 要約0件の成功 |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|",
             "| " + " | ".join(f"{s[k]:,}" for k in ("total", "reused", "generated", "failed", "queued", "working", "summaries", "empty")) + " |",
             "", f"通常のモデル要求 {m['attempts']:,} 回・{m['versions']:,} 版。計時した {m['timed']:,} 回の中央値 {m['median']:,.2f} 秒、最長 {m['maximum']:,.2f} 秒、合計 {m['sum_seconds']:,.2f} 秒。最長の版IDは `{m['longest']}`。"]
    tokens = m["tokens"]
    lines.extend(["", f"2分以上を要したのは {m['at_least_120s']:,} 回で、このうち10分以上は {m['at_least_600s']:,} 回。APIが返したトークンの合計は入力 {tokens.get('prompt_tokens',0):,}、生成 {tokens.get('completion_tokens',0):,}、うち思考 {tokens.get('reasoning_tokens',0):,}。応答の終了理由は " + "、".join(f"{k} {v:,}回" for k,v in m["finish"].items()) + "。",
                  "", f"成功 {s['successful']:,} 版について通常保存先のJSONと検証DBの要約・取得ID・入力キー・設定が一致した。保存2,438版と取得2,445件のID、原文の取得ファイル、旧計画の停止、採用済み6版の解釈IDを照合した。下記の馬別検索・記事詳細・出典リンクは終了後にも再確認した。",
                  "", "有限ワーカーと旧ワーカーは停止し、モデル利用の計画ロックは解放された。本番の利用データは0件、本番・検証で有効な収集予定は0件。検証Dashboardの応答を確認した。"])
    if report["failures"]:
        lines.extend(["", "### 失敗版", "", "理由の詳細と作業位置は進捗画面、全版IDと生の理由は検証用私有領域の `outcome.json` に保存した。", ""])
        for f in report["failures"][:20]:
            kind = (f["error"] or "unknown").split(":", 1)[0][:70].splitlines()[0]
            lines.append(f"- [{f['version']}]({DASHBOARD}/article/{f['capture']})　{kind}")
    return "\n".join(lines)


def write_file(path, content):
    staging = path.with_suffix(".tmp")
    staging.write_text(content, encoding="utf-8")
    staging.replace(path)


def verify(path, interim):
    require(trial(), "Use the trial profile")
    manifest = json.loads(path.read_bytes())
    targets = manifest["targets"]
    checksum = target_digest(targets)
    require(manifest["sha256"] == checksum, "Manifest checksum mismatch")
    plan = str(uuid.uuid5(uuid.NAMESPACE_URL, "keiba/saved-versions/" + checksum))
    with connect() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        p = c.execute("SELECT * FROM plans WHERE id=%s AND scope='saved_versions'", (plan,)).fetchone()
        require(p and p["input"]["sha256"] == checksum, plan)
        s = saved_progress(c, plan)
        counts, failed = check_results(c, plan, targets, manifest["configuration"])
        inventory = check_sources(c, path.parent, targets, manifest["sources"])
        samples = check_examples(c, plan)
        metrics = measures(c, plan)
        report = dict(plan=plan, observed=research.now(), ended=stamp(p["ended_at"]), state=p["state"],
                      progress=s, files=dict(counts), failures=failed, sources=inventory, samples=samples, measurements=metrics)
        if not interim:
            require(p["ended_at"] and p["state"] in ("done", "failed", "partial") and not has_worker(c, plan), "Worker is not finished")
            require(s["total"] == s["successful"] + len(failed) == len(targets) and s["working"] == s["queued"] == 0, "Nonterminal versions")
            require(all(s[k] == counts[k] for k in ("reused", "generated", "summaries", "empty")) and s["failed"] == len(failed), "File and progress counts differ")
            require(s["reused"] == p["input"]["accepted"] and s["attempts"] == metrics["attempts"], "Reuse or attempt count differs")
            all_records = c.execute("SELECT id,version_id,status FROM interpretations").fetchall()
            successful = [record for record in all_records if record["status"] == "ok"]
            require(len(successful) == len({r["version_id"] for r in successful}) == s["successful"], "Duplicate or unrelated successful result")
            require({r["id"] for r in all_records} == {f.stem for f in (research.ROOT / "interpretations").glob("*.json")}, "DB and JSON record sets differ")
            live = page("/run/" + plan)
            values = {dt.get_text(): dt.find_next_sibling("dd").get_text(strip=True) for dt in live.select("dt")}
            require(values.get("状態") == label(p["state"]) and values.get("対象版数") == f"{s['total']:,}", "Dashboard terminal state")
            require(values.get("保存済み成功版") == f"{s['successful']:,}（既存再利用 {s['reused']:,} ／ 新規成功 {s['generated']:,}）" and values.get("作業状態") == f"待機 0 ／ 処理中 0 ／ 失敗 {s['failed']:,}", "Dashboard terminal counts")
            runtime = json.load(sys.stdin)
            require(runtime["plan"] == plan and all(x == "inactive" for x in runtime["units"].values()), "Worker units still active")
            require(not any(runtime["production"].values()) and not any(runtime["active_cron"].values()), "Production data or collection schedules changed")
            report["runtime"] = runtime
    folder = path.parent
    if not interim:
        base = (folder / "report-base.md").read_text(encoding="utf-8")
        require(base.count("<!-- pass-result -->") == 1, "Missing report insertion point")
        rendered = base.replace("<!-- pass-result -->", final_section(report))
        write_file(folder / "report.md", rendered)
    name = "progress.json" if interim else "outcome.json"
    write_file(folder / name, json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(dict(state=report["state"], progress=s, measurements=metrics, checked_cards=len(samples)), ensure_ascii=False, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--in-progress", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    verify(args.manifest, args.in_progress)
