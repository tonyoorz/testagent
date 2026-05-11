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


if __name__ == "__main__":
    unittest.main()