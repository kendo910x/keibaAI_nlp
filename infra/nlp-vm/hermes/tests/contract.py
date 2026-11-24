"""Exercise the installed stdio server on a newly migrated disposable database, then check every row."""
import asyncio
import hashlib
import json
import os
import sys
from uuid import UUID

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, "/opt/nlp-db")
from store import transaction

TEST = "keiba_nlp_stage2b_test"
TOOLS = set("find_articles get_article save_article find_horses save_horse find_races save_race save_targets get_runs save_run".split())
TABLES = ("articles", "collection_runs", "horses", "races", "text_units", "unit_targets", "embedding_configs", "embeddings")
RUN, H1, H2, R1, R2, ALT = (str(UUID(int=n)) for n in range(1, 7))
URL = "https://example.invalid/fixture-a"
BODY = "架空🌿甲と甲。余白"


def counts(conn):
    return {table: conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] for table in TABLES}


async def main():
    assert os.environ.get("NLP_DATABASE") == TEST
    with transaction() as conn:
        assert conn.execute("SELECT current_database() AS db").fetchone()["db"] == TEST
        assert not any(counts(conn).values()), "requires an empty, disposable DB"
    command = StdioServerParameters(command=sys.executable, args=["-B", "/opt/nlp-db/server.py"], env={"NLP_DATABASE": TEST})
    calls = 0
    async with stdio_client(command) as streams, ClientSession(*streams) as client:
        await client.initialize()
        assert {tool.name for tool in (await client.list_tools()).tools} == TOOLS

        async def call(tool_name, error=None, **args):
            nonlocal calls
            result = await client.call_tool(tool_name, args)
            calls += 1
            assert result.isError == (error is not None), (tool_name, [x.text for x in result.content])
            if error:
                assert error.lower() in result.content[0].text.lower(), (tool_name, error, result.content[0].text)
                return
            return result.structuredContent or json.loads(result.content[0].text)

        await call("save_run", run_id=RUN, task={"fixture": "A"}, status="running")
        await call("save_run", run_id=RUN, status="paused", progress={"offset": 2})
        assert (await call("get_runs", run_id=RUN, status="paused"))["items"][0]["progress"] == {"offset": 2}
        await call("save_run", run_id=RUN, status="completed")
        resumed = await call("save_run", run_id=RUN, status="running")
        assert resumed["finished_at"] is None and resumed["started_at"] and resumed["progress"] == {"offset": 2}

        args = dict(source_url=URL, body=BODY, body_kind="excerpt", run_id=RUN)
        a = await call("save_article", **args)
        aid, full = a["article_id"], a["full_unit_id"]
        assert (await call("find_articles", unclassified=True))["items"][0]["article_id"] == aid
        assert (await call("save_article", **args, media="fixture"))["full_unit_id"] == full
        revised = await call("save_article", **dict(args, body=BODY + "。"))
        missing = await call("save_article", source_url=URL+"/missing", body_kind="none")
        assert revised["article_id"] != aid and missing["full_unit_id"] is None
        assert (await call("save_article", source_url=URL+"/missing", body_kind="none")) == missing
        await call("save_article", "disagree", source_url=URL, body_kind="full")
        await call("save_horse", "Unknown horse", horse_id=H1)
        for h in (H1, H2):
            await call("save_horse", horse_id=h, create=True, horse_name="架　空Ａ")
        assert (await call("save_horse", horse_id=H1, create=True, horse_name="架　空Ａ", birth_year=2020))["horse_id"] == H1
        horse_page = await call("find_horses", name="架空A", limit=1)
        assert horse_page["next_offset"] == 1 and horse_page["items"][0]["horse_id"] == H1
        assert (await call("find_horses", name="架空A", offset=1, limit=1))["items"][0]["horse_id"] == H2
        assert len((await call("find_horses", horse_id=H1, birth_year=2020))["items"]) == 1
        await call("save_race", race_id=R1, create=True, race_name="合成一")
        await call("save_race", race_id=R1, domain_id="JRA", race_key="20200101/01/01")
        reused = await call("save_race", race_id=ALT, create=True, domain_id="JRA", race_key="20200101/01/01")
        assert reused["race_id"] == R1
        await call("save_race", race_id=R2, create=True, race_name="合成二", race_date="2020-01-02")
        assert len((await call("find_races", race_name="合成"))["items"]) == 2
        assert (await call("find_races", race_id=R2, race_date="2020-01-02"))["items"][0]["race_id"] == R2
        assert (await call("find_races", domain_id="JRA", race_key="20200101/01/01"))["items"][0]["race_date"] is None
        await call("save_race", "23514", race_id=ALT, create=True, race_key="invented")
        await call("save_targets", "Ambiguous quote", article_id=aid, targets=[{"quote": "甲", "phase": "mixed"}])
        await call("save_targets", "range", article_id=aid, targets=[{"start_char": 1, "end_char": 800}])
        await call("save_targets", "no text unit", article_id=missing["article_id"], targets=[{"phase": "unknown"}])
        await call("save_targets", "23503", article_id=aid, targets=[{"quote": "余白", "horse_label": "rollback"},
                                                                   {"quote": "🌿", "horse_id": ALT}])
        assert not (await call("get_article", article_id=aid))["targets"]["items"]
        await call("save_targets", "does not belong", article_id=aid, targets=[{"unit_id": revised["full_unit_id"]}])
        saved = (await call("save_targets", article_id=aid, targets=[
            {"unit_id": full, "horse_id": H1, "race_id": R1, "phase": "pre"},
            {"start_char": 2, "end_char": 3, "horse_id": H2, "race_id": R2, "phase": "post"},
            {"quote": "余白", "horse_label": "保留"}]))["targets"]
        assert saved[2]["phase"] == "unknown"
        corrected = (await call("save_targets", article_id=aid, targets=[
            {"target_id": saved[2]["target_id"], "horse_id": H1, "phase": "mixed"}]))["targets"][0]
        assert corrected["horse_label"] is None and corrected["horse_id"] == H1
        same = (await call("save_targets", article_id=aid, targets=[{"horse_id": H1, "race_id": R1}]))["targets"][0]
        assert same["target_id"] == saved[0]["target_id"] and same["phase"] == "pre"
        assert not (await call("find_articles", horse_id=H1, race_id=R2))["items"]
        found = await call("find_articles", source_url=URL, horse_id=H1, race_id=R1, phase="pre", run_id=RUN)
        assert [r["article_id"] for r in found["items"]] == [aid]
        assert len((await call("find_articles", horse_id=H1, unclassified=False))["items"]) == 1
        assert len((await call("find_articles", unclassified=True))["items"]) == 2
        assert (await call("find_articles", limit=1))["next_offset"] == 1
        await call("find_articles", "validation", limit=101)
        detail = await call("get_article", article_id=aid, body_start=2, body_chars=2, limit=1)
        assert detail["body"] == "🌿甲" and detail["next_char"] == 4 and detail["truncated"]
        assert all(detail[k]["next_offset"] == 1 for k in ("units","targets","versions"))
        tail = await call("get_article", article_id=aid, body_start=4, unit_offset=1, target_offset=1, version_offset=1)
        assert tail["body"] == BODY[4:] and tail["next_char"] is None
        assert [r["article_id"] for r in tail["versions"]["items"]] == [revised["article_id"]]
    with transaction() as conn:
        n = counts(conn)
        assert n == dict(zip(TABLES, (3,1,2,2,4,3,0,0))), n
        articles = {str(r["article_id"]): r for r in conn.execute("SELECT * FROM articles")}
        for ident, text in ((aid, BODY), (revised["article_id"], BODY+"。"), (missing["article_id"], None)):
            r = articles[ident]
            assert r["body"] == text and r["url_sha256"] == hashlib.sha256(r["source_url"].encode()).digest()
            assert r["body_sha256"] == (hashlib.sha256(text.encode()).digest() if text else None)
        assert articles[aid]["media"] == "fixture"
        units = {(str(r["article_id"]), r["start_char"], r["end_char"]) for r in conn.execute("SELECT * FROM text_units")}
        assert units == {(aid,0,len(BODY)),(aid,2,3),(aid,7,9),(revised["article_id"],0,len(BODY)+1)}
        indexed = {(str(r["horse_id"]),str(r["race_id"]),r["phase"],r["start_char"],r["end_char"]) for r in
                   conn.execute("SELECT t.*,u.start_char,u.end_char FROM unit_targets t JOIN text_units u USING(unit_id)")}
        assert indexed == {(H1,R1,"pre",0,len(BODY)),(H2,R2,"post",2,3),(H1,"None","mixed",7,9)}
        assert [(str(r["horse_id"]),r["normalized_name"],r["birth_year"]) for r in
                conn.execute("SELECT * FROM horses ORDER BY horse_id")] == [(H1,"架空A",2020),(H2,"架空A",None)]
        races = conn.execute("SELECT * FROM races ORDER BY race_id").fetchall()
        assert [str(r["race_id"]) for r in races] == [R1,R2] and races[0]["race_key"] == "20200101/01/01" and races[1]["domain_id"] is None
        run = conn.execute("SELECT * FROM collection_runs").fetchone()
        assert str(run["run_id"]) == RUN and run["status"] == "running" and run["task"] == {"fixture":"A"} and run["progress"] == {"offset":2}
    print(json.dumps({"tools":len(TOOLS),"calls":calls,"rows_verified":n},sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
