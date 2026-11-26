"""Persistent observations for the NLP server. The legacy public schema stays separate."""

import gzip
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from profile_db import credentials


def connect(reader=False):
    return psycopg.connect(
        **credentials(reader),
        connect_timeout=6,
        row_factory=dict_row,
        application_name="keiba-reading" if reader else "keiba-collection",
        options="-c search_path=collection,pg_catalog -c timezone=Asia/Tokyo",
    )


def article_day(label):
    text = unicodedata.normalize("NFKC", label or "")
    m = re.search(r"(20\d\d|19\d\d)\s*[-年/.]\s*(\d{1,2})\s*[-月/.]\s*(\d{1,2})", text)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            pass
    return None


def persist(c, family, rec, origin):
    from routes import url_key

    if family == "captures":
        requested = rec["url"]
        url = rec.get("final_url") or requested
        key, host = url_key(url), urlsplit(url).hostname or "不明"
        when = rec["observed_at"]
        version = None
        if rec.get("body") and rec["status"] in ("ok", "partial"):
            version = rec["version_id"]
            label = rec.get("published_label")
            c.execute(
                """INSERT INTO versions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET date_label=coalesce(versions.date_label,excluded.date_label),
                article_day=coalesce(versions.article_day,excluded.article_day)""",
                (
                    version,
                    key,
                    url,
                    host,
                    rec.get("title", ""),
                    rec["body"],
                    label,
                    article_day(label),
                    when,
                    rec.get("truncated", False) or rec["status"] == "partial",
                    origin,
                ),
            )
        evidence = {k: v for k, v in rec.items() if k not in ("body", "response")}
        c.execute(
            """INSERT INTO captures VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                     ON CONFLICT (id) DO NOTHING""",
            (
                rec["id"],
                key,
                url_key(requested),
                version,
                url,
                host,
                rec.get("title", ""),
                rec["status"],
                when,
                origin,
                Jsonb(evidence),
            ),
        )
    elif family == "interpretations":
        items = json.loads(rec["content"])["items"] if rec.get("status") == "ok" else []
        extra = {k: v for k, v in rec.items() if k != "content"}
        c.execute(
            """INSERT INTO interpretations VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                     ON CONFLICT (id) DO NOTHING""",
            (
                rec["id"],
                rec["version_id"],
                rec["capture_id"],
                rec["status"],
                rec["observed_at"],
                rec.get("input_key"),
                rec.get("skill_sha256"),
                Jsonb(items),
                Jsonb(extra),
            ),
        )
    else:
        c.execute(
            """INSERT INTO observations VALUES (%s,%s,%s)
                     ON CONFLICT (family,id) DO UPDATE SET data=excluded.data WHERE observations.data<>excluded.data""",
            (family, rec["id"], Jsonb(rec)),
        )


def record(family, rec):
    with connect() as c:
        persist(c, family, rec, "server")


def import_directory(root, origin):
    if root.resolve() != Path("/var/lib/keiba"):
        raise ValueError("Recovery reads only the mounted data directory of this profile")
    counts = {}
    with connect() as c:
        for family in (
            "captures",
            "interpretations",
            "searches",
            "listings",
            "batches",
            "roster_pages",
            "rosters",
            "corrections",
        ):
            total = 0
            for p in sorted((root / family).glob("*")):
                if family == "rosters" and p.name == "history-jra.json.gz":
                    continue
                if p.suffix not in (".json", ".gz"):
                    continue
                raw = (
                    gzip.decompress(p.read_bytes())
                    if p.suffix == ".gz"
                    else p.read_bytes()
                )
                rec = json.loads(raw)
                if family == "rosters":
                    rec = {**rec, "id": p.name.split(".")[0]}
                elif family == "corrections":
                    rec = {"id": p.stem, "record": rec}
                persist(c, family, rec, origin)
                total += 1
            counts[family] = total
        for name in (
            "source-relations.json",
            "major-media-20261126/major-source-relations.json",
            "coverage-source-relations.json",
            "collection-policy.json",
        ):
            if (root / name).is_file():
                persist(
                    c,
                    "reference",
                    {"id": name, "record": json.loads((root / name).read_bytes())},
                    origin,
                )
    return counts


def lookup(keys):
    if not keys:
        return {}
    with connect() as c:
        rows = c.execute(
            """SELECT id,url_key,requested_key FROM captures WHERE version_id IS NOT NULL
              AND (url_key=ANY(%s) OR requested_key=ANY(%s)) ORDER BY observed_at,id""",
            (keys, keys),
        ).fetchall()
    return {key: r["id"] for r in rows for key in (r["url_key"], r["requested_key"])}


def input_success(key):
    with connect() as c:
        row = c.execute(
            "SELECT id FROM interpretations WHERE input_key=%s AND status='ok' ORDER BY observed_at DESC LIMIT 1",
            (key,),
        ).fetchone()
    return row["id"] if row else None
