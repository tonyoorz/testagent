import sqlite3
import tempfile
import unittest
import pathlib
import sys
import json

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from octane_db import OctaneSQLiteStore


class TestOctaneSQLiteStoreSmoke(unittest.TestCase):
    def test_create_optimized_tables_adds_description_and_comments_support(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = temp_dir + "\\octane_smoke.db"
            store = OctaneSQLiteStore(db_path)
            try:
                store.create_tables()
                store.create_optimized_tables()

                defect_count = store.upsert_defects_batch(
                    defects=[
                        {
                            "id": "D-1",
                            "name": "Speech cannot wake up",
                            "description": "Wake word not responding after cold boot",
                            "comments": [
                                {
                                    "id": "C-1",
                                    "author": "Tony Xie",
                                    "creation_time": "2026-05-02T08:00:00Z",
                                    "last_modified": "2026-05-02T09:00:00Z",
                                    "text": "Need more logs from cold start run.",
                                }
                            ],
                            "creation_time": "2026-05-01T00:00:00Z",
                            "team": {"full_name": "DTSV_China"},
                        }
                    ],
                    year=2026,
                )

                self.assertEqual(defect_count, 1)

                conn = sqlite3.connect(db_path)
                try:
                    defect_columns = [
                        row[1]
                        for row in conn.execute("PRAGMA table_info(octane_defects)").fetchall()
                    ]
                    self.assertIn("description", defect_columns)
                    self.assertIn("comments", defect_columns)

                    defect_row = conn.execute(
                        "SELECT description, comments FROM octane_defects WHERE defect_id = ?",
                        ("D-1",),
                    ).fetchone()
                    self.assertEqual(defect_row[0], "Wake word not responding after cold boot")
                    comments_payload = json.loads(defect_row[1])
                    self.assertEqual(len(comments_payload), 1)
                    self.assertEqual(comments_payload[0]["id"], "C-1")
                    self.assertEqual(comments_payload[0]["author"], "Tony Xie")
                    self.assertEqual(comments_payload[0]["text"], "Need more logs from cold start run.")
                finally:
                    conn.close()
            finally:
                store.close()

    def test_upsert_defect_history_populates_flattened_history_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = temp_dir + "\\octane_history_smoke.db"
            store = OctaneSQLiteStore(db_path)
            try:
                store.create_tables()
                store.create_optimized_tables()

                store.upsert_defect_history(
                    defect_id="D-1",
                    team="DTSV_China",
                    payload={
                        "total_count": 2,
                        "data": [
                            {
                                "timestamp": "2026-05-02T08:00:00Z",
                                "user_name": "Tony Xie",
                                "action": "update",
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "01-New",
                                        "value_text": "02-In Pre-Analysis",
                                    },
                                    {
                                        "field_name": "severity",
                                        "old_value_text": "Medium",
                                        "value_text": "High",
                                    },
                                ],
                            }
                        ],
                    },
                    fetched_at="2026-05-19T10:00:00Z",
                )

                conn = sqlite3.connect(db_path)
                try:
                    event_columns = [
                        row[1]
                        for row in conn.execute("PRAGMA table_info(octane_defect_history_events)").fetchall()
                    ]
                    self.assertIn("field_name", event_columns)
                    self.assertIn("event_timestamp", event_columns)

                    rows = conn.execute(
                        """
                        SELECT defect_id, team, event_timestamp, field_name, old_value_text, new_value_text, fetched_at
                        FROM octane_defect_history_events
                        WHERE defect_id = ?
                        ORDER BY entry_index, change_index
                        """,
                        ("D-1",),
                    ).fetchall()
                    self.assertEqual(
                        rows,
                        [
                            (
                                "D-1",
                                "DTSV_China",
                                "2026-05-02T08:00:00Z",
                                "phase",
                                "01-New",
                                "02-In Pre-Analysis",
                                "2026-05-19T10:00:00Z",
                            ),
                            (
                                "D-1",
                                "DTSV_China",
                                "2026-05-02T08:00:00Z",
                                "severity",
                                "Medium",
                                "High",
                                "2026-05-19T10:00:00Z",
                            ),
                        ],
                    )
                finally:
                    conn.close()
            finally:
                store.close()

    def test_upsert_defect_history_can_skip_flattened_history_events_when_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = temp_dir + "\\octane_history_deferred.db"
            store = OctaneSQLiteStore(db_path, sync_history_events=False)
            try:
                store.create_tables()
                store.create_optimized_tables()

                store.upsert_defect_history(
                    defect_id="D-2",
                    team="DTSV_China",
                    payload={
                        "total_count": 1,
                        "data": [
                            {
                                "timestamp": "2026-05-02T08:00:00Z",
                                "user_name": "Tony Xie",
                                "action": "update",
                                "change_set": [
                                    {
                                        "field_name": "phase",
                                        "old_value_text": "01-New",
                                        "value_text": "02-In Pre-Analysis",
                                    }
                                ],
                            }
                        ],
                    },
                    fetched_at="2026-05-19T10:00:00Z",
                )

                conn = sqlite3.connect(db_path)
                try:
                    history_count = conn.execute(
                        "SELECT COUNT(*) FROM octane_defect_histories WHERE defect_id = ?",
                        ("D-2",),
                    ).fetchone()[0]
                    event_count = conn.execute(
                        "SELECT COUNT(*) FROM octane_defect_history_events WHERE defect_id = ?",
                        ("D-2",),
                    ).fetchone()[0]
                    self.assertEqual(history_count, 1)
                    self.assertEqual(event_count, 0)
                finally:
                    conn.close()
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()