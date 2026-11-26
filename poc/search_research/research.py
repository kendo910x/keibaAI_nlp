"""Private, per-observation files for the three search settings. No database writes."""

import asyncio
import hashlib
import json
import os
import re
import time
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


SHARED = "http://192.168.0.11:30081/mcp"
LLM = "http://192.168.0.13:8731/v1/chat/completions"
MODEL = "halogen-qwen3.8-flash-next"
ROOT = Path(os.environ["KEIBA_RESEARCH_DIR"]).resolve()


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def save(group, record):
    record["id"] = uuid.uuid4().hex
    record["actor"] = os.environ.get("KEIBA_RESEARCH_ACTOR", "codex")
    directory = ROOT / group
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (record["id"] + ".json")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return record


def read(group, ident):
    if not re.fullmatch(r"[0-9a-f]{32}", ident):
        raise ValueError("Use the saved observation ID")
    return json.loads((ROOT / group / (ident + ".json")).read_text(encoding="utf-8"))


def links_only(url):
    hosts = {"keiba.sponichi.co.jp", "www.keibalab.jp"}
    policy = ROOT / "collection-policy.json"
    if policy.is_file():
        hosts.update(json.loads(policy.read_text(encoding="utf-8"))["links_only_hosts"])
    return urlsplit(url).hostname in hosts


async def shared(tool, arguments):
    async with streamablehttp_client(SHARED) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
            return result.content[0].text


def status(raw):
    footer = re.search(r"(?:^|\n)\[STATUS\] status=(\S+)[^\n]*\Z", raw)
    return footer.group(1) if footer else "unknown_response"


async def search(subject: str, query: str, limit: int = 6) -> dict:
    """Search shared Yahoo. Pass a short race/setting label. Keep the ID for capture."""
    started = time.monotonic()
    limit = max(1, min(10, limit))
    try:
        raw = await shared("yahoo_search", {"query": query, "num_results": limit})
        state = status(raw)
    except Exception as exc:
        raw, state = str(exc), "transport_error"
    results = [dict(title=t, url=u) for t, u in re.findall(r"^\d+\. (.+)\n   URL: (\S+)", raw, re.M)]
    record = save("searches", dict(subject=subject, query=query, requested=limit,
                  route="shared.yahoo_search", observed_at=now(), response=raw,
                  seconds=round(time.monotonic() - started, 2), results=results, status=state))
    return dict(search_id=record["id"], status=state, results=results,
                detail=raw.splitlines()[-1] if raw else "")


async def check_access(url):
    """Validate a candidate without imposing a local robots.txt preflight gate."""
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        return "unsupported_url"
    if links_only(url):
        return "metadata_only"
    return "allowed"


async def capture(search_id: str, rank: int) -> dict:
    """Capture one 1-based Yahoo result through shared fetch. A fresh call records a revisit."""
    query = read("searches", search_id)
    if not 1 <= rank <= len(query["results"]):
        raise ValueError("Rank outside the recorded result list")
    hit = query["results"][rank - 1]
    record = dict(search_id=search_id, rank=rank, subject=query["subject"], **hit,
                  route="shared.fetch_page", started_at=now())
    try:
        state = await check_access(hit["url"])
        if state == "allowed":
            raw = await shared("fetch_page", {"url": hit["url"]})
            state = status(raw)
            if state in ("ok", "partial"):
                header, content = raw.split("\n---\n", 1)
                body, _ = content.rsplit("\n[STATUS] ", 1)
                fields = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
                final_url = fields["final_url"]
                record.update(final_url=final_url, fetched_at=fields["取得日時"])
                access = "allowed" if final_url == hit["url"] else await check_access(final_url)
                if access == "allowed":
                    record.update(response=raw, body=body, truncated=fields["truncated"] == "true",
                                  version_id=digest(final_url + "\n" + body))
                else:
                    state = access
            else:
                record["response"] = raw
    except Exception as exc:
        state = "capture_error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    record.update(status=state, observed_at=now())
    save("captures", record)
    summary = dict(capture_id=record["id"], title=hit["title"], status=state,
                   version_id=record.get("version_id"), chars=len(record.get("body", "")),
                   truncated=record.get("truncated"), url=record.get("final_url", hit["url"]))
    if "body" not in record:
        detail = record.get("error") or record.get("response") or state
        summary["detail"] = detail.splitlines()[-1]
    return summary


def interpretation_summary(result, capture_id, items, reused):
    return dict(interpretation_id=result["id"], capture_id=capture_id, status=result["status"],
                count=len(items), horses=list(dict.fromkeys(i["horse"] for i in items if i["horse"])),
                examples=items[:3], reused=reused, error=result.get("error"))


async def interpret(capture_id: str, fresh: bool = False) -> dict:
    """Interpret a saved body independently. Reuse a successful same-version/Skill/settings result unless fresh."""
    article = read("captures", capture_id)
    if "body" not in article or article["status"] not in ("ok", "partial"):
        return dict(status="no_captured_body", capture_id=capture_id)
    skill = Path(os.environ["KEIBA_INTERPRET_SKILL"]).read_text(encoding="utf-8")
    settings = dict(model=MODEL, max_tokens=65536, temperature=0, reasoning_effort="xhigh",
                    chat_template_kwargs={"enable_thinking": True}, stream=False)
    result = dict(capture_id=capture_id, version_id=article["version_id"], subject=article["subject"],
                  skill="keiba-interpret", skill_sha256=digest(skill), settings=settings, started_at=now())
    if not fresh:
        for path in (ROOT / "interpretations").glob("*.json"):
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior["status"] == "ok" and all(
                prior.get(key) == result[key] for key in ("version_id", "skill_sha256", "settings")
            ):
                return interpretation_summary(prior, capture_id, json.loads(prior["content"])["items"], True)
    items = []
    started = time.monotonic()
    try:
        messages = [dict(role="system", content=skill), dict(role="user", content=article["body"])]
        async with httpx.AsyncClient(timeout=1800) as client:
            reply = await client.post(LLM, json=dict(**settings, messages=messages))
            reply.raise_for_status()
        response = reply.json()
        choice = response["choices"][0]
        result.update(finish_reason=choice["finish_reason"], usage=response.get("usage"),
                      content=choice["message"].get("content"))
        if choice["finish_reason"] != "stop":
            raise ValueError("Incomplete model response")
        parsed = json.loads(result["content"])["items"]
        if not isinstance(parsed, list) or not all(valid_item(item) for item in parsed):
            raise ValueError("Unexpected items format")
        items = parsed
        result["status"] = "ok"
        result["normalized_horses"] = {
            item["horse"]: "".join(unicodedata.normalize("NFKC", item["horse"]).split())
            for item in items if item["horse"]
        }
    except asyncio.CancelledError:
        result.update(status="interrupted", error="The caller cancelled the interpretation")
        raise
    except Exception as exc:
        result.update(status="interpretation_failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        result.update(observed_at=now(), seconds=round(time.monotonic() - started, 2))
        save("interpretations", result)
    return interpretation_summary(result, capture_id, items, False)


def valid_item(item):
    if not isinstance(item, dict) or not {"horse", "race", "phase", "text"} <= item.keys():
        return False
    return (
        all(item[key] is None or isinstance(item[key], str) for key in ("horse", "race"))
        and item["phase"] in ("pre", "post", "mixed", "unknown")
        and isinstance(item["text"], str) and bool(item["text"].strip())
    )

