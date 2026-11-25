"""Stage 3B stdio MCP. No database identifiers, SQL or credentials in the tool interface."""
from datetime import date
from hashlib import sha256
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from store import Limit, Offset, Phase, Status, compatible, filtered, page, required, transaction
from targets import save_targets

mcp = FastMCP("nlp-db", log_level="WARNING")
mcp.tool()(save_targets)
ARTICLE = """SELECT a.article_id,a.source_url,a.media,a.title,a.published_text,a.body_kind,
             a.collected_at,a.run_id,char_length(a.body) AS body_length,
             encode(a.body_sha256,'hex') AS body_sha256 FROM articles a"""
RELATION = "SELECT FROM text_units u JOIN unit_targets t USING (unit_id) WHERE u.article_id=a.article_id"


@mcp.tool()
def find_articles(source_url: str | None = None, horse_id: UUID | None = None,
                  race_id: UUID | None = None, phase: Phase | None = None,
                  run_id: UUID | None = None, unclassified: bool | None = None,
                  limit: Limit = 20, offset: Offset = 0) -> dict:
    """List distinct articles. Horse, race and phase match the same target. Unclassified means no targets."""
    terms, args = filtered([("a.source_url=%s", source_url), ("a.run_id=%s", run_id)])
    related, params = filtered([("t.horse_id=%s", horse_id), ("t.race_id=%s", race_id), ("t.phase=%s", phase)])
    if related:
        terms.append("EXISTS (" + RELATION + " AND " + " AND ".join(related) + ")")
        args.extend(params)
    if unclassified is not None:
        terms.append(("NOT EXISTS (" if unclassified else "EXISTS (") + RELATION + ")")
    with transaction() as conn:
        return page(conn, ARTICLE, terms, args, "a.collected_at,a.article_id", limit, offset)


@mcp.tool()
def get_article(article_id: UUID, body_start: Offset = 0,
                body_chars: Annotated[int, Field(ge=0, le=8192)] = 2048,
                unit_offset: Offset = 0, target_offset: Offset = 0, version_offset: Offset = 0,
                limit: Limit = 20) -> dict:
    """Read one source version, a bounded code-point slice and separately paginated units, targets and versions."""
    with transaction() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        meta = required(conn.execute(ARTICLE + " WHERE a.article_id=%s", (article_id,)).fetchone(), "Unknown article")
        length = meta["body_length"] or 0
        if body_start > length:
            raise ValueError("body_start exceeds source length")
        body = conn.execute("SELECT substring(body FROM %s FOR %s) AS text FROM articles WHERE article_id=%s",
                            (body_start + 1, body_chars, article_id)).fetchone()["text"]
        end = body_start + len(body or "")
        units = page(conn, "SELECT unit_id,start_char,end_char FROM text_units", ["article_id=%s"], [article_id],
                     "start_char,end_char,unit_id", limit, unit_offset)
        targets = page(conn, "SELECT t.*,u.start_char,u.end_char FROM unit_targets t JOIN text_units u USING(unit_id)",
                       ["u.article_id=%s"], [article_id], "u.start_char,u.end_char,t.target_id", limit, target_offset)
        versions = page(conn, ARTICLE, ["a.source_url=%s", "a.url_sha256=%s"],
                        [meta["source_url"], sha256(meta["source_url"].encode()).digest()],
                        "a.collected_at,a.article_id", limit, version_offset)
        return {"article": meta, "body": body, "start_char": body_start, "end_char": end,
                "next_char": end if end < length else None, "truncated": body_start > 0 or end < length,
                "units": units, "targets": targets, "versions": versions}


@mcp.tool()
def save_article(source_url: str, body_kind: Literal["full", "excerpt", "snippet", "none"],
                 body: str | None = None, media: str | None = None, title: str | None = None,
                 published_text: str | None = None, run_id: UUID | None = None) -> dict:
    """Commit the actual permitted source text first. Identical URL, kind and text reuse a version.
    Use none without body for unavailable text. Do not substitute a summary for source text.
    """
    url = urlsplit(source_url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or url.password is not None:
        raise ValueError("Supply an HTTP(S) source URL without credentials")
    if (body_kind == "none" and body is not None) or (body_kind != "none" and not body):
        raise ValueError("body_kind and source text disagree")
    with transaction() as conn:
        row = required(conn.execute("""
            INSERT INTO articles AS a(source_url,url_sha256,body_kind,body,body_sha256,media,title,published_text,run_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (url_sha256,body_kind,body_sha256) DO UPDATE SET
              media=coalesce(a.media,excluded.media),title=coalesce(a.title,excluded.title),
              published_text=coalesce(a.published_text,excluded.published_text)
            WHERE a.source_url=excluded.source_url AND a.body IS NOT DISTINCT FROM excluded.body
            RETURNING article_id,collected_at""",
            (source_url, sha256(source_url.encode()).digest(), body_kind, body,
             sha256(body.encode()).digest() if body is not None else None, media, title, published_text, run_id)
        ).fetchone(), "Version identity collision")
        row["full_unit_id"] = None
        if body is not None:
            row["full_unit_id"] = conn.execute("""SELECT unit_id FROM text_units
                WHERE article_id=%s AND start_char=0 AND end_char=%s""", (row["article_id"], len(body))).fetchone()["unit_id"]
        return row


class Slice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horse_id: UUID
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    quote: str = Field(min_length=1)
    phase: Literal["pre", "post", "mixed"]


@mcp.tool()
def save_slices(article_id: UUID, slices: list[Slice]) -> dict:
    """Save verbatim per-horse slices of one article in a single atomic call (one call per article).
    Each quote must equal body[start_char:end_char] exactly; any mismatch rejects the whole call.
    Horse must already exist (resolve with find_horses first); labels are not accepted.
    Idempotent: reruns reuse existing units and targets. The full-text unit is left untouched.
    """
    if not 1 <= len(slices) <= 100:
        raise ValueError("Supply 1 to 100 slices per call")
    with transaction() as conn:
        article = required(conn.execute("SELECT body FROM articles WHERE article_id=%s FOR UPDATE",
                                        (article_id,)).fetchone(), "Unknown article")
        body = article["body"]
        if body is None:
            raise ValueError("An article without source text has no slices")
        created_units = reused_units = created_targets = reused_targets = 0
        for s in slices:
            if s.end_char > len(body):
                raise ValueError("Slice range exceeds article body")
            if body[s.start_char:s.end_char] != s.quote:
                raise ValueError("quote does not match body[start_char:end_char] verbatim")
            required(conn.execute("SELECT 1 FROM horses WHERE horse_id=%s", (s.horse_id,)).fetchone(),
                     "Unknown horse_id. Resolve candidates with find_horses first")
            row = conn.execute("SELECT unit_id FROM text_units WHERE article_id=%s AND start_char=%s AND end_char=%s",
                               (article_id, s.start_char, s.end_char)).fetchone()
            if row:
                unit, reused_units = row["unit_id"], reused_units + 1
            else:
                unit = conn.execute("""INSERT INTO text_units(article_id,start_char,end_char)
                                       VALUES (%s,%s,%s) RETURNING unit_id""",
                                    (article_id, s.start_char, s.end_char)).fetchone()["unit_id"]
                created_units += 1
            existing = conn.execute("""SELECT target_id FROM unit_targets WHERE unit_id=%s AND horse_id=%s
                                       AND race_id IS NULL AND horse_label IS NULL AND race_label IS NULL""",
                                    (unit, s.horse_id)).fetchone()
            if existing:
                reused_targets += 1
            else:
                conn.execute("INSERT INTO unit_targets(unit_id,horse_id,phase) VALUES (%s,%s,%s)",
                             (unit, s.horse_id, s.phase))
                created_targets += 1
        return {"units_created": created_units, "units_reused": reused_units,
                "targets_created": created_targets, "targets_reused": reused_targets}


# Match the generated normalized_name expression from migration 001 using PostgreSQL's Unicode version.
NORMAL_NAME = r"""translate(normalize(%s,NFKC),U&'\0009\000A\000B\000C\000D\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000','')"""


@mcp.tool()
def find_horses(name: str | None = None, horse_id: UUID | None = None, birth_year: int | None = None,
                limit: Limit = 20, offset: Offset = 0) -> dict:
    """Find all candidates by normalized exact name, known ID or year; same names remain distinct."""
    terms, args = filtered([("normalized_name=" + NORMAL_NAME, name), ("horse_id=%s", horse_id), ("birth_year=%s", birth_year)])
    with transaction() as conn:
        return page(conn, "SELECT * FROM horses", terms, args, "horse_id", limit, offset)


@mcp.tool()
def save_horse(horse_id: UUID, horse_name: str | None = None, birth_year: int | None = None,
               create: bool = False) -> dict:
    """Complete a known horse. For a new horse supply create=true, a stable UUID and a name."""
    with transaction() as conn:
        if create and horse_name:
            conn.execute("""INSERT INTO horses(horse_id,horse_name,birth_year) VALUES (%s,%s,%s)
                         ON CONFLICT (horse_id) DO NOTHING""", (horse_id, horse_name, birth_year))
        row = required(conn.execute("SELECT * FROM horses WHERE horse_id=%s FOR UPDATE", (horse_id,)).fetchone(),
                       "Unknown horse. Creation requires create=true, stable UUID and name")
        compatible(row, {"horse_name": horse_name, "birth_year": birth_year})
        return conn.execute("UPDATE horses SET birth_year=coalesce(birth_year,%s) WHERE horse_id=%s RETURNING *",
                            (birth_year, horse_id)).fetchone()


@mcp.tool()
def find_races(race_id: UUID | None = None, domain_id: str | None = None, race_key: str | None = None,
               race_name: str | None = None, race_date: date | None = None,
               limit: Limit = 20, offset: Offset = 0) -> dict:
    """Find race candidates using the known fields. Name is a literal substring; dates are optional.
    race_key format: YYYYMMDD/<venue code>/<race number>, e.g. 20250420/06/11. domain_id is "JRA" or "NAR"."""
    terms, args = filtered([("race_id=%s", race_id), ("domain_id=%s", domain_id), ("race_key=%s", race_key),
                            ("strpos(race_name,%s)>0", race_name), ("race_date=%s", race_date)])
    with transaction() as conn:
        return page(conn, "SELECT * FROM races", terms, args, "race_id", limit, offset)


@mcp.tool()
def save_race(race_id: UUID, race_name: str | None = None, race_date: date | None = None,
              domain_id: str | None = None, race_key: str | None = None, create: bool = False) -> dict:
    """Complete a known race or explicitly create using a stable UUID. Reuse a confirmed domain/key pair.
    race_key format: YYYYMMDD/<venue code>/<race number> (schema CHECK ^[0-9]{8}/[0-9]{2}/[0-9]{2}$).
    domain_id convention: "JRA" or "NAR". UNIQUE(domain_id, race_key).
    Example: 皐月賞 on 2025-04-20, Nakayama race 11 -> domain_id="JRA", race_key="20250420/06/11".
    JRA venue codes: 01 札幌 / 02 函館 / 03 福島 / 04 新潟 / 05 東京 / 06 中山 / 07 中京 / 08 京都 / 09 阪神 / 10 小倉.
    NAR venue codes: 30 門別 / 31 北見 / 32 岩見沢 / 33 帯広 / 34 旭川 / 35 盛岡 / 36 水沢 / 37 上山 / 38 三条 / 39 足利 / 40 宇都宮 / 41 高崎 / 42 浦和 / 43 船橋 / 44 大井 / 45 川崎 / 46 金沢 / 47 笠松 / 48 名古屋 / 49 紀三井寺 / 50 園田 / 51 姫路 / 52 益田 / 53 福山 / 54 高知 / 55 佐賀 / 56 荒尾 / 57 中津 / 58 札幌(NAR) / 59 函館(NAR) / 60 新潟(NAR) / 61 中京(NAR).
    """
    fields = dict(race_name=race_name, race_date=race_date, domain_id=domain_id, race_key=race_key)
    with transaction() as conn:
        if create:
            conn.execute("""INSERT INTO races(race_id,race_name,race_date,domain_id,race_key) VALUES (%s,%s,%s,%s,%s)
                            ON CONFLICT DO NOTHING""", (race_id, race_name, race_date, domain_id, race_key))
        row = conn.execute("SELECT * FROM races WHERE race_id=%s FOR UPDATE", (race_id,)).fetchone()
        if domain_id is not None and race_key is not None:
            canonical = conn.execute("SELECT * FROM races WHERE domain_id=%s AND race_key=%s FOR UPDATE",
                                     (domain_id, race_key)).fetchone()
            if row and canonical and row["race_id"] != canonical["race_id"]:
                raise ValueError("Known race IDs conflict with the confirmed domain/key")
            row = row or canonical
        required(row, "Unknown race. Creation requires create=true and a stable UUID")
        compatible(row, fields)
        return conn.execute("""UPDATE races SET race_name=coalesce(race_name,%s),race_date=coalesce(race_date,%s),
                               domain_id=coalesce(domain_id,%s),race_key=coalesce(race_key,%s)
                               WHERE race_id=%s RETURNING *""",
                            (race_name, race_date, domain_id, race_key, row["race_id"])).fetchone()


@mcp.tool()
def get_runs(run_id: UUID | None = None, status: Status | None = None, limit: Limit = 20, offset: Offset = 0) -> dict:
    """Read the saved task, progress and status. Use the same run ID to resume."""
    terms, args = filtered([("run_id=%s", run_id), ("status=%s", status)])
    with transaction() as conn:
        return page(conn, "SELECT * FROM collection_runs", terms, args, "updated_at,run_id", limit, offset)


@mcp.tool()
def save_run(run_id: UUID, task: dict | None = None, status: Status | None = None,
             progress: dict | None = None, last_error: str | None = None) -> dict:
    """Create with a stable UUID and task object. Update the same ID's status/progress; supplied JSON replaces that field."""
    with transaction() as conn:
        if task is not None:
            conn.execute("""INSERT INTO collection_runs(run_id,task) VALUES (%s,%s)
                            ON CONFLICT (run_id) DO NOTHING""", (run_id, Jsonb(task)))
        row = required(conn.execute("SELECT * FROM collection_runs WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone(),
                       "Unknown run. Supply a task to create it")
        state = status or row["status"]
        return conn.execute("""UPDATE collection_runs SET task=%s,status=%s,progress=%s,updated_at=now(),
            started_at=CASE WHEN %s='running' THEN coalesce(started_at,now()) ELSE started_at END,
            finished_at=CASE WHEN %s IN ('completed','failed') THEN coalesce(finished_at,now()) ELSE NULL END,
            last_error=%s WHERE run_id=%s RETURNING *""",
            (Jsonb(task if task is not None else row["task"]), state,
             Jsonb(progress if progress is not None else row["progress"]), state, state,
             last_error if last_error is not None else (None if status in ("running","completed") else row["last_error"]),
             run_id)).fetchone()


if __name__ == "__main__":
    mcp.run(transport="stdio")
