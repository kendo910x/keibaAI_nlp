"""Run individual research operations or expose them to an isolated Hermes over stdio."""

import argparse
import asyncio
import json

from mcp.server.fastmcp import FastMCP

from research import capture, interpret, search


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
    args = vars(parser.parse_args())
    operation = args.pop("operation")
    actions = {fn.__name__: fn for fn in (search, capture, interpret)}
    if operation == "serve":
        server = FastMCP("keiba-search-research")
        for fn in actions.values():
            server.tool()(fn)
        server.run()
    else:
        print(json.dumps(asyncio.run(actions[operation](**args)), ensure_ascii=False))


if __name__ == "__main__":
    main()
