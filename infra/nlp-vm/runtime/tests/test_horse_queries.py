"""Execute horse-search and interpretation-queue SQL on disposable PostgreSQL.

Optional local test dependency: pgserver (bundled PostgreSQL 16). No production
credentials, VM connection, article retrieval or model request is used. Run with:
    KEIBA_SQL_TEST=1 python -m unittest discover -s infra/nlp-vm/runtime/tests -p test_horse_queries.py -v

For a socket-restricted environment, set KEIBA_SQL_SINGLE_USER=1 instead. That
mode runs the same SQL through the PostgreSQL engine without a network/Unix
socket; it verifies SQL results, not psycopg connection behavior.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

try:
    import pgserver
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:
    pgserver = None

RUNTIME = Path(__file__).resolve().parents[1]
REPO = RUNTIME.parents[2]


class SingleUserConnection:
    """Small test-only executor for PostgreSQL's documented standalone mode."""

    def __init__(self, pgdata):
        self.pgdata = pgdata
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def close(self):
        pass

    def execute(self, sql, params=()):
        from pgserver._commands import POSTGRES_BIN_PATH
        from psycopg.adapt import Transformer

        parts = sql.split("%s")
        if len(parts) != len(params) + 1:
            raise ValueError("fixture SQL parameter count")
        transformer = Transformer()
        sql = parts[0] + "".join(
            transformer.as_literal(value).decode("utf-8") + tail
            for value, tail in zip(params, parts[1:])
        )
        returns_rows = sql.lstrip().upper().startswith(("SELECT", "WITH"))
        if returns_rows:
            sql = "SELECT coalesce(json_agg(row_to_json(q)), '[]')::text AS result FROM (" + sql + ") q;"
        result = subprocess.run(
            [str(POSTGRES_BIN_PATH / "postgres"), "--single", "-j", "-D", str(self.pgdata),
             "-c", "search_path=collection,pg_catalog", "-c", "timezone=UTC", "postgres"],
            input=sql + "\n\n", capture_output=True, text=True, timeout=15,
        )
        if result.returncode or re.search(r"\b(?:ERROR|FATAL|PANIC):", result.stderr):
            raise RuntimeError(result.stdout + result.stderr)
        self.rows = []
        if returns_rows:
            match = re.search(r'1: result = "(.*)"\t\(typeid', result.stdout, re.S)
            if not match:
                raise RuntimeError("No standalone SQL result: " + result.stdout)
            self.rows = json.loads(match.group(1))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


@unittest.skipUnless(
    pgserver is not None and (os.environ.get("KEIBA_SQL_TEST") == "1" or os.environ.get("KEIBA_SQL_SINGLE_USER") == "1"),
    "opt in with KEIBA_SQL_TEST=1 (optional pgserver/psycopg); standalone: KEIBA_SQL_SINGLE_USER=1",
)
class HorseQueryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="keiba-horse-sql-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.pgdata = Path(cls.directory.name) / "pgdata"
        cls.single_user = os.environ.get("KEIBA_SQL_SINGLE_USER") == "1"
        if cls.single_user:
            from pgserver._commands import initdb
            cls.pgdata.mkdir()
            initdb(["--auth=trust", "--encoding=utf8", "-U", "postgres"], pgdata=cls.pgdata, user=None)
        else:
            cls.server = pgserver.get_server(cls.pgdata, cleanup_mode="delete")
            cls.addClassCleanup(cls.server.cleanup)
            cls.uri = cls.server.get_uri()
        sys.path.insert(0, str(REPO / "poc/search_research"))
        sys.path.insert(0, str(RUNTIME))
        # Importing the runtime must not select the mounted production profile.
        with patch.dict(os.environ, {"KEIBA_RESEARCH_DIR": cls.directory.name, "KEIBA_RUNTIME_DB": "0"}):
            import dashboard
            import jobs
        cls.dashboard, cls.jobs = dashboard, jobs
        migrations = RUNTIME.parent / "db/migrations"
        # Use the application DDL, omitting deployment-only roles, grants and the
        # legacy public-schema view. The trial migration also has psql commands.
        schema = (migrations / "002_collection_runtime.sql").read_text().split(
            "GRANT USAGE ON SCHEMA collection", 1
        )[0] + "COMMIT;"
        trial = (migrations / "003_trial_paths.sql").read_text()
        trial = trial[trial.index("CREATE TABLE IF NOT EXISTS agent_searches"):].split(
            "GRANT SELECT,INSERT ON agent_searches", 1
        )[0]
        with cls.connection() as connection:
            connection.execute(schema)
            connection.execute(trial)

    @classmethod
    def connection(cls):
        if cls.single_user:
            return SingleUserConnection(cls.pgdata)
        return psycopg.connect(
            cls.uri, autocommit=True, row_factory=dict_row,
            options="-c search_path=collection,pg_catalog -c timezone=UTC",
        )

    def setUp(self):
        self.db = self.connection()
        self.addCleanup(self.db.close)
        self.db.execute("TRUNCATE versions,plans,observations,health CASCADE")
        self.now = datetime.now(timezone.utc)
        self.settings = {"model": "local-test", "reasoning_effort": "xhigh"}
        self.skill = "updated one-horse summary skill"
        self.connect_patch = patch.object(self.jobs, "connect", self.connection)
        self.config_patch = patch.object(
            self.jobs, "interpretation_config", return_value=(self.skill, self.settings)
        )
        self.connect_patch.start()
        self.config_patch.start()
        self.addCleanup(self.connect_patch.stop)
        self.addCleanup(self.config_patch.stop)

    def version(self, ident, *, url=None, minute=0, day="2026-11-27", label="2026-11-27"):
        url = url or "https://example.invalid/" + ident
        self.db.execute(
            """INSERT INTO versions(id,url_key,source_url,host,title,body,date_label,
               article_day,observed_at,partial,origin) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s)""",
            (ident, url, url, "example.invalid", "fixture " + ident, "local fixture",
             label, day, self.now + timedelta(minutes=minute), "sql-unittest"),
        )
        cap = "cap-" + ident
        self.capture(cap, ident, minute=minute, label=label)
        return cap

    def capture(self, ident, version, *, minute=0, label="2026-11-27"):
        self.db.execute(
            """INSERT INTO captures(id,url_key,requested_key,version_id,source_url,host,
               title,status,observed_at,origin,evidence)
               SELECT %s,url_key,url_key,id,source_url,host,title,'ok',%s,'sql-unittest',%s
               FROM versions WHERE id=%s""",
            (ident, self.now + timedelta(minutes=minute), Jsonb({"published_label": label}), version),
        )

    def interpretation(self, ident, version, items, *, capture=None, minute=0,
                       status="ok", skill=None, settings=None, input_key="input",
                       input_format="article-date-v1"):
        self.db.execute(
            """INSERT INTO interpretations(id,version_id,capture_id,status,observed_at,
               input_key,skill_hash,items,evidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (ident, version, capture or "cap-" + version, status,
             self.now + timedelta(minutes=minute), input_key,
             self.jobs.digest(self.skill) if skill is None else skill, Jsonb(items),
             Jsonb({"input_format": input_format, "settings": self.settings if settings is None else settings})),
        )

    def cards(self, query=None):
        base, args = self.dashboard.horse_query(query or {})
        return self.db.execute(
            base + "SELECT version_id,horse_key,horse,items FROM horse_cards ORDER BY version_id,horse_key", args
        ).fetchall()

    def plan(self, ident, captures):
        self.db.execute(
            "INSERT INTO plans(id,kind,label,scope,state,input,owner) VALUES (%s,'daily','fixture','review','done','{}','unittest')",
            (ident,),
        )
        self.db.execute(
            "INSERT INTO work_items(plan_id,position,target,state,result) VALUES (%s,0,'{}','done',%s)",
            (ident, Jsonb({"hits": [{"capture_id": cap} for cap in captures]})),
        )

    def test_latest_url_version_is_chosen_before_horse_and_date_filters(self):
        url = "https://example.invalid/updated"
        self.version("old", url=url, minute=-10, day="2026-11-20")
        self.interpretation("old-result", "old", [{"horse": "カランダガン", "text": "old"}])
        self.version("new", url=url, minute=-5, day="2026-11-27")
        self.interpretation("new-result", "new", [{"horse": "別の馬", "text": "new"}])
        self.assertEqual(self.cards({"q": "カランダガン"}), [])
        self.assertEqual(self.cards({"to": "2026-11-21"}), [])
        self.assertEqual([row["version_id"] for row in self.cards()], ["new"])

    def test_uninterpreted_latest_version_does_not_fall_back_to_old_version(self):
        url = "https://example.invalid/updated"
        self.version("old", url=url, minute=-10)
        self.interpretation("old-result", "old", [{"horse": "カランダガン", "text": "old"}])
        self.version("new", url=url, minute=-5)
        self.assertEqual(self.cards({"q": "カランダガン"}), [])

    def test_latest_success_is_chosen_before_matching_and_failure_is_ignored(self):
        self.version("article")
        self.interpretation("old", "article", [{"horse": "カランダガン", "text": "old"}], minute=-20)
        self.interpretation("latest-ok", "article", [{"horse": "別の馬", "text": "current"}], minute=-10)
        self.interpretation("failure", "article", [{"horse": "カランダガン", "text": "failed"}], status="failed")
        self.assertEqual(self.cards({"q": "カランダガン"}), [])
        self.assertEqual(self.cards()[0]["horse"], "別の馬")

    def test_same_horse_across_race_phase_is_one_count_and_pagination_unit(self):
        self.version("article-00")
        parts = [{"horse": "カランダガン", "race": "競走" + str(i),
                  "phase": "pre" if i % 2 else "post", "text": "言及" + str(i)} for i in range(7)]
        parts.append({"horse": "別の馬", "text": "別の解釈"})
        self.interpretation("parts", "article-00", parts)
        for number in range(1, 20):
            version = "article-" + str(number).zfill(2)
            self.version(version)
            self.interpretation("result-" + version, version, [{"horse": "カランダガン", "text": "要約"}])
        base, args = self.dashboard.horse_query({})
        self.assertEqual(self.db.execute(base + "SELECT count(*) n FROM horse_cards", args).fetchone()["n"], 21)
        pages = [self.db.execute(
            base + "SELECT version_id,horse_key FROM horse_cards ORDER BY version_id,horse_key LIMIT 20 OFFSET %s",
            [*args, offset],
        ).fetchall() for offset in (0, 20)]
        self.assertEqual([len(page) for page in pages], [20, 1])
        keys = {(r["version_id"], r["horse_key"]) for page in pages for r in page}
        self.assertEqual(len(keys), 21)
        target = self.cards({"q": "カランダガン", "match": "exact"})
        self.assertEqual(len(target), 20)
        self.assertEqual(len(target[0]["items"]), 7)

    def test_empty_unrecognized_and_malformed_items_are_ignored(self):
        for index, items in enumerate((None, {}, [], "unrecognized")):
            version = "empty-" + str(index)
            self.version(version)
            self.interpretation("result-" + version, version, items)
        self.version("mixed")
        self.interpretation("mixed-result", "mixed", [None, "string", {},
            {"horse": None, "text": "全体"}, {"horse": 123, "text": "number"},
            {"horse": "", "text": "empty horse"}, {"horse": "空", "text": " \n\t"},
            {"horse": "欠落"}, {"horse": "異型", "text": []},
            {"horse": "カランダガン", "text": "有効な要約"}])
        result = self.cards()
        self.assertEqual([(row["version_id"], row["horse"]) for row in result], [("mixed", "カランダガン")])

    def test_plan_scope_selects_its_own_latest_capture_before_horse_matching(self):
        url = "https://example.invalid/updated"
        old = self.version("old", url=url, minute=-10)
        self.interpretation("old-result", "old", [{"horse": "カランダガン", "text": "old"}])
        new = self.version("new", url=url, minute=-5)
        self.interpretation("new-result", "new", [{"horse": "別の馬", "text": "new"}])
        old_plan = "00000000-0000-0000-0000-000000000001"
        new_plan = "00000000-0000-0000-0000-000000000002"
        self.plan(old_plan, [old])
        self.plan(new_plan, [old, new])
        self.assertEqual([r["version_id"] for r in self.cards({"plan": old_plan, "q": "カランダガン"})], ["old"])
        self.assertEqual(self.cards({"plan": new_plan, "q": "カランダガン"}), [])
        self.assertEqual(self.cards({"q": "カランダガン"}), [])

    def test_completed_dated_input_stays_done_after_skill_or_settings_change(self):
        self.version("done")
        self.interpretation("done-result", "done", [], skill="old-skill-hash", settings={"model": "old-settings"})
        self.assertEqual(self.jobs.pending_captures(20), [])
        self.assertEqual(self.jobs.pending_captures(20, cooldown=True), [])

    def test_missing_success_and_legacy_undated_input_remain_pending(self):
        self.version("never")
        self.version("legacy")
        self.interpretation("legacy-result", "legacy", [], input_format="old-format")
        self.version("no-key")
        self.interpretation("no-key-result", "no-key", [], input_key=None)
        self.assertEqual(set(self.jobs.pending_captures(20)), {"cap-never", "cap-legacy", "cap-no-key"})
        self.assertEqual(len(self.jobs.pending_captures(2)), 2)

    def test_new_dated_input_reopens_but_recapture_with_same_date_does_not(self):
        old = self.version("article", minute=-20, label=None)
        self.interpretation("undated-result", "article", [], capture=old)
        self.capture("dated", "article", minute=-10, label="2026-11-27")
        self.assertEqual(self.jobs.pending_captures(20), ["dated"])
        self.interpretation("dated-result", "article", [], capture="dated", skill="older-skill")
        self.capture("same-date", "article", minute=-5, label="2026-11-27")
        self.assertEqual(self.jobs.pending_captures(20), [])
        self.capture("corrected-date", "article", label="2026-11-26")
        self.assertEqual(self.jobs.pending_captures(20), ["corrected-date"])

    def test_failure_cooldown_still_matches_current_skill_settings_and_age(self):
        for version in ("recent", "expired", "other-skill", "other-settings"):
            self.version(version)
        self.interpretation("recent-result", "recent", [], status="failed", minute=-5)
        self.interpretation("expired-result", "expired", [], status="failed", minute=-1500)
        self.interpretation("other-skill-result", "other-skill", [], status="failed", skill="old")
        self.interpretation("other-settings-result", "other-settings", [], status="failed", settings={"model": "other"})
        self.assertEqual(set(self.jobs.pending_captures(20)),
                         {"cap-recent", "cap-expired", "cap-other-skill", "cap-other-settings"})
        self.assertEqual(set(self.jobs.pending_captures(20, cooldown=True)),
                         {"cap-expired", "cap-other-skill", "cap-other-settings"})


if __name__ == "__main__":
    unittest.main()
