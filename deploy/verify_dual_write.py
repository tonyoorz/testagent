#!/usr/bin/env python3
"""Verify SQLite and PostgreSQL dual-write row counts."""

import argparse
import sqlite3
from typing import Any, Dict, List, Tuple


def _connect_pg(pg_url: str):
    try:
        import psycopg  # type: ignore

        return psycopg.connect(pg_url)
    except Exception:
        import psycopg2  # type: ignore

        return psycopg2.connect(pg_url)


def _fetch_sqlite(conn: sqlite3.Connection, sql: str) -> List[Tuple[Any, ...]]:
    return conn.execute(sql).fetchall()


def _fetch_pg(conn, sql: str, schema: str) -> List[Tuple[Any, ...]]:
    cur = conn.cursor()
    try:
        cur.execute(f'SET search_path TO "{schema}"')
        cur.execute(sql)
        return cur.fetchall()
    finally:
        cur.close()


def _to_map(rows: List[Tuple[Any, ...]], key_idx: int = 0, val_idx: int = 1) -> Dict[Any, Any]:
    out: Dict[Any, Any] = {}
    for row in rows:
        out[row[key_idx]] = row[val_idx]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="对比 SQLite 与 PostgreSQL 双写结果")
    parser.add_argument("--sqlite-path", default="database/local_data.db")
    parser.add_argument("--pg-url", required=True)
    parser.add_argument("--pg-schema", default="public")
    args = parser.parse_args()

    sqlite_conn = sqlite3.connect(args.sqlite_path)
    pg_conn = _connect_pg(args.pg_url)

    checks = {
        "defects_total": "SELECT COUNT(*) FROM octane_defects",
        "manual_runs_total": "SELECT COUNT(*) FROM octane_manual_runs",
        "histories_total": "SELECT COUNT(*) FROM octane_defect_histories",
    }

    print("=== Total Count Check ===")
    ok = True
    for label, sql in checks.items():
        s_val = _fetch_sqlite(sqlite_conn, sql)[0][0]
        p_val = _fetch_pg(pg_conn, sql, args.pg_schema)[0][0]
        same = s_val == p_val
        ok = ok and same
        print(f"{label:20s} sqlite={s_val:<10} postgres={p_val:<10} match={same}")

    print("\n=== Defects by Year ===")
    sql_year = "SELECT year, COUNT(*) FROM octane_defects GROUP BY year ORDER BY year"
    s_year = _to_map(_fetch_sqlite(sqlite_conn, sql_year))
    p_year = _to_map(_fetch_pg(pg_conn, sql_year, args.pg_schema))
    years = sorted(set(s_year.keys()) | set(p_year.keys()))
    for year in years:
        s_val = s_year.get(year, 0)
        p_val = p_year.get(year, 0)
        same = s_val == p_val
        ok = ok and same
        print(f"year={year} sqlite={s_val:<10} postgres={p_val:<10} match={same}")

    print("\n=== Manual Runs by Year ===")
    sql_mr_year = "SELECT year, COUNT(*) FROM octane_manual_runs GROUP BY year ORDER BY year"
    s_mr = _to_map(_fetch_sqlite(sqlite_conn, sql_mr_year))
    p_mr = _to_map(_fetch_pg(pg_conn, sql_mr_year, args.pg_schema))
    years = sorted(set(s_mr.keys()) | set(p_mr.keys()))
    for year in years:
        s_val = s_mr.get(year, 0)
        p_val = p_mr.get(year, 0)
        same = s_val == p_val
        ok = ok and same
        print(f"year={year} sqlite={s_val:<10} postgres={p_val:<10} match={same}")

    sqlite_conn.close()
    pg_conn.close()

    print("\n=== Result ===")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
