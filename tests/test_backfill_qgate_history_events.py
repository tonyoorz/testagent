import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import backfill_qgate_history_events as backfill


class TestBackfillQgateHistoryEvents(unittest.TestCase):
    def test_backfill_writes_lightweight_history_events_from_payload_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(pathlib.Path(temp_dir) / "qgate_history.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE octane_defect_histories (
                        defect_id TEXT NOT NULL PRIMARY KEY,
                        team TEXT NOT NULL,
                        total_count INTEGER,
                        payload_json TEXT NOT NULL,
                        fetched_at TEXT NOT NULL
                    )
                    """
                )
                payload = {
                    "total_count": 1,
                    "data": [
                        {
                            "timestamp": "2026-05-03T09:30:00Z",
                            "user_name": "tester-a",
                            "action": "update",
                            "change_set": [
                                {
                                    "field_name": "phase",
                                    "old_value_text": "02-In Pre-Analysis",
                                    "value_text": "03-In Analysis",
                                },
                                {
                                    "field_name": "comments",
                                    "old_value_text": None,
                                    "value_text": "<html><body><p>Huge note</p></body></html>",
                                }
                            ],
                        }
                    ],
                }
                conn.execute(
                    "INSERT INTO octane_defect_histories(defect_id, team, total_count, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
                    ("D-200", "DTSV_China", 1, json.dumps(payload, ensure_ascii=False), "2026-05-19T10:00:00Z"),
                )
                conn.commit()
            finally:
                conn.close()

            summary = backfill.backfill_qgate_history_events(db_path)

            self.assertEqual(summary["history_rows_seen"], 1)
            self.assertEqual(summary["history_rows_loaded"], 1)
            self.assertEqual(summary["events_upserted"], 1)

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    SELECT defect_id, team, field_name, old_value_text, new_value_text, raw_event_json, raw_change_json
                    FROM octane_defect_history_events
                    WHERE defect_id = ?
                    """,
                    ("D-200",),
                ).fetchone()
                self.assertEqual(
                    row,
                    (
                        "D-200",
                        "DTSV_China",
                        "phase",
                        "02-In Pre-Analysis",
                        "03-In Analysis",
                        "",
                        "",
                    ),
                )
                count = conn.execute(
                    "SELECT COUNT(*) FROM octane_defect_history_events WHERE defect_id = ?",
                    ("D-200",),
                ).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()