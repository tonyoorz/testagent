import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

from octane_db import DEFAULT_LIGHT_HISTORY_FIELDS, OctaneSQLiteStore


def _load_history_rows(db_path: str) -> List[Tuple[str, str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT defect_id, team, payload_json, fetched_at
            FROM octane_defect_histories
            ORDER BY team, defect_id
            """
        ).fetchall()
    finally:
        conn.close()


def backfill_qgate_history_events(db_path: str, *, vacuum: bool = False) -> Dict[str, int]:
    summary = {
        "history_rows_seen": 0,
        "history_rows_loaded": 0,
        "history_rows_skipped": 0,
        "events_upserted": 0,
    }

    history_rows = _load_history_rows(db_path)
    store = OctaneSQLiteStore(db_path)
    try:
        store.create_tables()
        store.create_optimized_tables()

        for defect_id, team, payload_json, fetched_at in history_rows:
            summary["history_rows_seen"] += 1
            try:
                payload = json.loads(payload_json)
            except Exception:
                summary["history_rows_skipped"] += 1
                continue

            summary["history_rows_loaded"] += 1
            summary["events_upserted"] += store.replace_defect_history_events(
                defect_id=str(defect_id),
                team=str(team or ""),
                payload=payload,
                fetched_at=fetched_at,
                tracked_fields=set(DEFAULT_LIGHT_HISTORY_FIELDS),
                include_raw_json=False,
            )

        if vacuum:
            store.close()
            vacuum_conn = sqlite3.connect(db_path)
            try:
                vacuum_conn.execute("VACUUM")
            finally:
                vacuum_conn.close()
            return summary
    finally:
        try:
            store.close()
        except Exception:
            pass

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill qgate defect history payloads into the octane_defect_history_events table."
    )
    parser.add_argument(
        "--db-path",
        default="qgate/qgate_data.db",
        help="Path to the qgate SQLite database.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM after rebuilding lightweight history events to reclaim file size.",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    summary = backfill_qgate_history_events(str(db_path), vacuum=args.vacuum)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()