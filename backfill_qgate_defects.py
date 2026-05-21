import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import data_processor
from octane_db import OctaneSQLiteStore


def _extract_defects(payload_json: str) -> Optional[List[Dict[str, Any]]]:
    try:
        payload = json.loads(payload_json)
    except Exception:
        return None

    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return None

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    return None


def _infer_year(year_value: Optional[int], defects: List[Dict[str, Any]]) -> Optional[int]:
    if year_value is not None:
        try:
            return int(year_value)
        except Exception:
            return None

    for defect in defects:
        creation_time = defect.get("creation_time")
        if not creation_time:
            continue
        try:
            return int(str(creation_time)[:4])
        except Exception:
            continue
    return None


def _load_payload_rows(db_path: str) -> List[Tuple[Optional[int], str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            """
            SELECT year, spec, payload_json, fetched_at
            FROM octane_payloads
            WHERE kind = 'defects'
            ORDER BY year, team, spec
            """
        ).fetchall()
    finally:
        conn.close()


def backfill_qgate_defects(db_path: str, sync_processed_fields: bool = True) -> Dict[str, int]:
    summary = {
        "payload_rows_seen": 0,
        "payload_rows_loaded": 0,
        "payload_rows_skipped": 0,
        "defects_upserted": 0,
        "processed_field_sync_ran": 0,
        "processed_defect_updates": 0,
    }

    payload_rows = _load_payload_rows(db_path)
    store = OctaneSQLiteStore(db_path)
    try:
        store.create_tables()
        store.create_optimized_tables()

        for year_value, _spec, payload_json, fetched_at in payload_rows:
            summary["payload_rows_seen"] += 1
            defects = _extract_defects(payload_json)
            if defects is None:
                summary["payload_rows_skipped"] += 1
                continue

            resolved_year = _infer_year(year_value, defects)
            if resolved_year is None:
                summary["payload_rows_skipped"] += 1
                continue

            summary["payload_rows_loaded"] += 1
            summary["defects_upserted"] += store.upsert_defects_batch(
                defects,
                year=resolved_year,
                fetched_at=fetched_at,
            )
    finally:
        store.close()

    if sync_processed_fields:
        sync_stats = data_processor.sync_processed_fields_to_db(
            db_path=db_path,
            sync_manual_runs=False,
        )
        summary["processed_field_sync_ran"] = 1
        summary["processed_defect_updates"] = int(sync_stats.get("defect_updates") or 0)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill qgate defect payloads into the octane_defects optimized table."
    )
    parser.add_argument(
        "--db-path",
        default="qgate/qgate_data.db",
        help="Path to the qgate SQLite database.",
    )
    parser.add_argument(
        "--skip-processed-field-sync",
        action="store_true",
        help="Only replay payloads into octane_defects and skip data_processor field sync.",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    summary = backfill_qgate_defects(
        str(db_path),
        sync_processed_fields=not args.skip_processed_field_sync,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()