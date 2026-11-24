"""Synthetic acceptance tests for the empty, disposable Stage 2B database."""
from getpass import getpass
from hashlib import sha256
import json
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

HERE = Path(__file__).resolve().parent
TEST_DB = "keiba_nlp_stage2b_test"
TABLES = ("collection_runs", "articles", "horses", "races", "text_units",
          "unit_targets", "embedding_configs", "embeddings")
URL = "https://fixture.invalid/item?edition=1"
BODY = "甲🐎e\u0301乙。丙丁"

ARTICLE_SQL = """
WITH incoming(url,body,kind,title,run_id) AS (VALUES (%s::text,%s::text,%s::text,%s::text,%s::uuid))
INSERT INTO articles AS a (source_url,url_sha256,body,body_sha256,body_kind,title,run_id)
SELECT url,sha256(convert_to(url,'UTF8')),body,sha256(convert_to(body,'UTF8')),kind,title,run_id FROM incoming
ON CONFLICT (url_sha256,body_kind,body_sha256) DO UPDATE SET title=coalesce(a.title,EXCLUDED.title)
WHERE a.source_url=EXCLUDED.source_url AND a.body IS NOT DISTINCT FROM EXCLUDED.body
RETURNING article_id,collected_at
"""


def article(c, url, body, kind, title=None, run_id=None):
    row = c.execute(ARTICLE_SQL, (url, body, kind, title, run_id)).fetchone()
    if row is None:
        raise ValueError("matching hash with different original text")
    return row


def rejected(c, sql, expected, params=None):
    try:
        with c.transaction():
            c.execute(sql, params)
    except psycopg.Error as err:
        if err.sqlstate != expected:
            raise
    else:
        raise AssertionError(f"command unexpectedly succeeded; expected {expected}")


def register_config(c, conditions, claimed_digest):
    canonical = json.dumps(conditions, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    if sha256(canonical).digest() != claimed_digest:
        raise ValueError("config digest disagrees with its input")
    original = (conditions["model_name"], conditions["model_revision"],
                conditions["dimensions"], conditions["settings"])
    with c.transaction():
        c.execute("""INSERT INTO embedding_configs(model_name,model_revision,dimensions,settings,config_sha256)
                     VALUES (%s,%s,%s,%s,%s) ON CONFLICT(config_sha256) DO NOTHING""",
                  (*original[:3], Jsonb(original[3]), claimed_digest))
        row = c.execute("""SELECT embedding_config_id,model_name,model_revision,dimensions,settings=%s
                          FROM embedding_configs WHERE config_sha256=%s""",
                        (Jsonb(original[3]), claimed_digest)).fetchone()
        if row is None or row[1:4] != original[:3] or not row[4]:
            raise ValueError("stored config disagrees with its input")
    return row[0]


def source_checks(c):
    run_id = c.execute("INSERT INTO collection_runs(task) VALUES ('{}') RETURNING run_id").fetchone()[0]
    c.execute("UPDATE collection_runs SET status='running',started_at=now(),updated_at=now() WHERE run_id=%s",
              (run_id,))
    saved = article(c, URL, BODY, "full", run_id=run_id)
    full_unit = c.execute("SELECT unit_id FROM text_units WHERE article_id=%s AND start_char=0 AND end_char=8",
                          (saved[0],)).fetchone()[0]
    assert c.execute("""SELECT title IS NULL AND published_text IS NULL AND media IS NULL AND body=%s
                       FROM articles WHERE article_id=%s""", (BODY, saved[0])).fetchone() == (True,)
    # The article and full unit committed first. Roll back the entire classification attempt.
    try:
        with c.transaction():
            c.execute("INSERT INTO unit_targets(unit_id,horse_label) VALUES (%s,'仮分類')", (full_unit,))
            c.execute("INSERT INTO unit_targets(unit_id,phase) VALUES (%s,'invalid')", (full_unit,))
    except psycopg.errors.CheckViolation:
        pass
    else:
        raise AssertionError("expected classification failure")
    assert c.execute("SELECT count(*) FROM unit_targets").fetchone() == (0,)
    assert c.execute("SELECT body,unit_id FROM articles JOIN text_units USING(article_id) WHERE article_id=%s",
                     (saved[0],)).fetchone() == (BODY, full_unit)
    assert article(c, URL, BODY, "full", "合成・主資料") == saved
    assert c.execute("SELECT count(*) FROM articles").fetchone() == (1,)
    none = article(c, URL, None, "none")
    assert article(c, URL, None, "none") == none
    rejected(c, "INSERT INTO text_units(article_id,start_char,end_char) VALUES (%s,0,1)", "23514", (none[0],))
    assert c.execute("SELECT count(*) FROM text_units WHERE article_id=%s", (none[0],)).fetchone() == (0,)
    versions = [article(c, URL, BODY + "改", "full"), article(c, URL, BODY, "snippet"),
                article(c, URL + "&source=2", BODY, "full"), article(c, URL, "架空の抜粋", "excerpt")]
    assert len({row[0] for row in [saved, none, *versions]}) == 6
    for sql in (
        "INSERT INTO articles(source_url,url_sha256,body_kind) VALUES ('x',sha256('bad'::bytea),'none')",
        "INSERT INTO articles(source_url,url_sha256,body,body_kind) VALUES ('x',sha256('x'::bytea),'x','full')",
        "INSERT INTO articles(source_url,url_sha256,body_kind) VALUES ('x',sha256('x'::bytea),'snippet')",
        "INSERT INTO articles(source_url,url_sha256,body,body_kind) VALUES ('x',sha256('x'::bytea),'x','none')",
        "INSERT INTO articles(source_url,url_sha256,body,body_sha256,body_kind) "
        "VALUES ('x',sha256('x'::bytea),'x',sha256('bad'::bytea),'excerpt')",
    ):
        rejected(c, sql, "23514")
    rejected(c, "INSERT INTO text_units(article_id,start_char,end_char) VALUES (%s,0,9)", "23514", (saved[0],))
    assert c.execute("SELECT count(*) FROM embeddings").fetchone() == (0,)
    return run_id


def config_checks(c):
    for dim in (3, 4):
        condition = dict(settings={"分割": "合成", "norm": False}, dimensions=dim,
                         model_revision="fixture-v1", model_name=f"synthetic-{dim}")
        # Independent literal canonical form also checks non-ASCII key encoding and recursive key sorting.
        wire = ('{"dimensions":%d,"model_name":"synthetic-%d","model_revision":"fixture-v1",'
                '"settings":{"norm":false,"分割":"合成"}}' % (dim, dim)).encode("utf-8")
        digest = sha256(wire).digest()
        first = register_config(c, condition, digest)
        assert register_config(c, dict(reversed(list(condition.items()))), digest) == first
        try:
            register_config(c, condition, bytes(32))
        except ValueError:
            pass
        else:
            raise AssertionError("incorrect config digest accepted")


def permissions(c):
    for sql in (
        "CREATE TABLE public.fixture_forbidden(i int)", "CREATE TEMP TABLE fixture_t(i int)",
        "CREATE EXTENSION hstore", "CREATE ROLE fixture_forbidden",
        "UPDATE articles SET body=body WHERE false", "UPDATE articles SET collected_at=now() WHERE false",
        "UPDATE text_units SET start_char=0 WHERE false", "UPDATE embedding_configs SET settings='{}' WHERE false",
        "DELETE FROM articles WHERE false", "TRUNCATE embeddings",
    ):
        rejected(c, sql, "42501")
    for table in TABLES:
        rights = c.execute("""SELECT has_table_privilege(current_user,%s,'SELECT'),
                             has_table_privilege(current_user,%s,'INSERT'),
                             has_table_privilege(current_user,%s,'DELETE')""", (table, table, table)).fetchone()
        assert rights == (True, True, table == "unit_targets")


def run(c):
    if not __debug__:
        raise RuntimeError("run without Python -O")
    if not c.autocommit or c.execute("SELECT current_database(),current_user").fetchone() != (TEST_DB, "nlp_app"):
        raise RuntimeError("requires autocommit and the dedicated test DB as nlp_app")
    if any(c.execute(f"SELECT EXISTS(SELECT FROM {table})").fetchone()[0] for table in TABLES):
        raise RuntimeError("requires an empty test database")
    c.execute("SET plpgsql.check_asserts=on")
    run_id = source_checks(c)
    print("B4/B5 original survives classification rollback; 6 distinct versions")
    with c.transaction():
        c.execute((HERE / "targets.sql").read_text(encoding="utf-8"))
    print("B6 7 targets, 4 phases, 2 related pairs; race query 4 rows / 2 units / 1 article")
    config_checks(c)
    with c.transaction():
        c.execute((HERE / "embeddings.sql").read_text(encoding="utf-8"))
        c.execute("""UPDATE collection_runs SET progress='{"fixture":"done"}',status='completed',
                     finished_at=now(),updated_at=now() WHERE run_id=%s""", (run_id,))
    print("B7 2 configs, 2+1 chunks; failed group rolled back, generated pair skipped")
    permissions(c)
    print("B8 8 table grants, 10 forbidden operations checked")


if __name__ == "__main__":
    with psycopg.connect(host="192.168.0.14", port=5432, dbname=TEST_DB, user="nlp_app",
                         sslmode="disable", password=getpass("Test DB password: "), autocommit=True) as connection:
        run(connection)
