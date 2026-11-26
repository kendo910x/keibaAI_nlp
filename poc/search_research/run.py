"""Run individual research operations or expose them to an isolated Hermes over stdio."""

import argparse
import asyncio
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from functools import partial, wraps

from mcp.server.fastmcp import FastMCP

from research import capture, interpret, search
from routes import capture_url, collect, excerpt, listing, roster_page, seeds


def in_worker(fn, worker):
    @wraps(fn)
    async def call(**arguments):
        return await asyncio.get_running_loop().run_in_executor(worker, partial(fn, **arguments))

    return call


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("serve")
    query = commands.add_parser("search")
    query.add_argument("subject")
    query.add_argument("query")
    query.add_argument("--limit", type=int, default=6)
    page = commands.add_parser("capture")
    page.add_argument("search_id")
    page.add_argument("rank", type=int)
    interpretation = commands.add_parser("interpret")
    interpretation.add_argument("capture_id")
    interpretation.add_argument("--fresh", action="store_true")
    links = commands.add_parser("listing")
    links.add_argument("subject")
    links.add_argument("url")
    links.add_argument("selector", help="CSS selector for article links")
    links.add_argument("--next-selector", default="")
    links.add_argument("--render", action="store_true", help="Use the local Playwright/Edge DOM")
    batch = commands.add_parser("collect")
    batch.add_argument("listing_id")
    batch.add_argument("--offset", type=int, default=0)
    batch.add_argument("--limit", type=int, default=20)
    batch.add_argument("--revisit", action="store_true")
    direct = commands.add_parser("capture_url")
    direct.add_argument("subject")
    direct.add_argument("url")
    direct.add_argument("--title", default="")
    direct.add_argument("--revisit", action="store_true")
    sample = commands.add_parser("excerpt")
    sample.add_argument("capture_id")
    sample.add_argument("--offset", type=int, default=0)
    sample.add_argument("--length", type=int, default=700)
    names = commands.add_parser("seeds")
    names.add_argument("roster")
    names.add_argument("--offset", type=int, default=0)
    names.add_argument("--limit", type=int, default=12)
    names.add_argument("--name", default="")
    names.add_argument("--year", default="")
    roster = commands.add_parser("roster_page")
    for key in ("roster", "stage", "race_key", "url", "selector"):
        roster.add_argument(key)
    args = vars(parser.parse_args())
    operation = args.pop("operation")
    actions = {fn.__name__: fn for fn in (search, capture, interpret, listing, collect, capture_url,
                                         excerpt, seeds, roster_page)}
    if operation == "serve":
        server = FastMCP("keiba-search-research")
        # Keep synchronous browser/collection calls off the inference event loop and in order.
        with ThreadPoolExecutor(max_workers=1) as worker:
            for fn in actions.values():
                server.tool()(fn if inspect.iscoroutinefunction(fn) else in_worker(fn, worker))
            server.run()
    else:
        result = actions[operation](**args)
        print(json.dumps(asyncio.run(result) if inspect.isawaitable(result) else result, ensure_ascii=False))


if __name__ == "__main__":
    main()
