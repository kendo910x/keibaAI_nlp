"""Export JRA search seeds to stdout from an existing read-only v3 Hist database."""

import argparse
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb


def export(database, start, end):
    for date in (start, end):
        datetime.strptime(date, "%Y%m%d")
    if start > end:
        raise ValueError("Start must precede end")
    starts = """
        SELECT trim(SE12_blood_reg_no) AS horse_id, trim(SE13_uma_name) AS name,
               SE_kaisai_ymd AS race_day
        FROM se_core
        WHERE SE_kaisai_ymd BETWEEN ? AND ?
          AND SE6_jyo_cd BETWEEN '01' AND '10'
          AND trim(SE13_uma_name) <> ''
          AND coalesce(try_cast(SE39_ijou_kbn_cd AS INTEGER), 0) NOT IN (1, 2, 3)
          AND (try_cast(SE41_kakutei_chakujun AS INTEGER) > 0
               OR try_cast(SE39_ijou_kbn_cd AS INTEGER) IN (4, 5, 6, 7))
    """
    with duckdb.connect(str(database), read_only=True, config={"threads": "2"}) as connection:
        rows = connection.execute(f"""
            SELECT horse_id, name, min(race_day), max(race_day), count(*),
                   list(DISTINCT left(race_day, 4) ORDER BY left(race_day, 4))
            FROM ({starts}) GROUP BY horse_id, name ORDER BY name, horse_id
        """, [start, end]).fetchall()
    keys = ("horse_id", "name", "first", "last", "starts", "years")
    return dict(domain="jra", source="se_core", start=start, end=end,
                horses=[dict(zip(keys, row)) for row in rows])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("start", help="YYYYMMDD, inclusive")
    parser.add_argument("end", help="YYYYMMDD, inclusive")
    parser.add_argument("--gzip", action="store_true", help="Write gzip-compressed JSON")
    args = parser.parse_args()
    data = json.dumps(export(args.database, args.start, args.end), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(gzip.compress(data) if args.gzip else data)
