"""Database connection and bounded, parameterized reads shared by the ten MCP tools."""
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

import psycopg
from psycopg.rows import dict_row
from pydantic import Field

Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0, le=2147483646)]
Phase = Literal["pre", "post", "mixed", "unknown"]
Status = Literal["queued", "running", "paused", "completed", "failed"]


@contextmanager
def transaction():
    name = os.environ.get("NLP_DATABASE", "keiba_nlp")
    if name not in {"keiba_nlp", "keiba_nlp_stage2b_test"}:
        raise ValueError("Invalid administrator database setting")
    try:
        with psycopg.connect(
            host="192.168.0.14", port=5432, dbname=name, user="nlp_app",
            password=Path("/run/secrets/nlp_app").read_text().rstrip("\r\n"),
            sslmode="disable", connect_timeout=4, row_factory=dict_row,
            application_name="nlp-hermes-mcp",
            options="-c statement_timeout=5000 -c lock_timeout=3000 -c search_path=public,pg_catalog",
        ) as conn:
            yield conn
    except psycopg.Error as exc:
        # PostgreSQL DETAIL/CONTEXT can contain input rows. Keep them out of sessions.
        raise ValueError(f"Database operation failed ({exc.sqlstate or 'connection'}).") from None


def filtered(fields):
    """Column expressions come from the caller's fixed SQL, never tool input."""
    terms, args = [], []
    for expr, value in fields:
        if value is not None:
            terms.append(expr)
            args.append(value)
    return terms, args


def page(conn, select, terms, args, order, limit, offset):
    where = " WHERE " + " AND ".join(terms) if terms else ""
    rows = conn.execute(
        f"{select}{where} ORDER BY {order} LIMIT %s OFFSET %s",
        [*args, limit + 1, offset],
    ).fetchall()
    return {"items": rows[:limit], "offset": offset,
            "next_offset": offset + limit if len(rows) > limit else None}


def required(row, message):
    if row is None:
        raise ValueError(message)
    return row


def compatible(row, supplied):
    for field, value in supplied.items():
        if value is not None and row[field] is not None and value != row[field]:
            raise ValueError(f"Existing {field} conflicts with supplied value")
