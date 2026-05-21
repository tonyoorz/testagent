import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from octane_db import OctaneSQLiteStore
import backfill_qgate_defects as backfill


class TestBackfillQgateDefects(unittest.TestCase):
    def test_backfill_writes_optimized_defects_from_payload_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(pathlib.Path(temp_dir) / "qgate_data.db")
            store = OctaneSQLiteStore(db_path)
            try:
                store.create_tables()
                store.upsert_payload(
                    kind="defects",
                    team="DTSV_China",
                    year=2026,
                    spec="DTSV_China",
                    payload={
                        "data": [
                            {
                                "id": "D-1",
                                "name": "Voice wakeup fails",
                                "creation_time": "2026-05-01T00:00:00Z",
                                "team": {"full_name": "DTSV_China"},
                                "problem_finder_team_udf": {"full_name": "DTSV_China"},
                            }
                        ]
                    },
                    fetched_at="2026-05-19T10:00:00Z",
                )
            finally:
                store.close()

            summary = backfill.backfill_qgate_defects(db_path)

            self.assertEqual(summary["payload_rows_seen"], 1)
            self.assertEqual(summary["payload_rows_loaded"], 1)
            self.assertEqual(summary["defects_upserted"], 1)

            conn = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                self.assertIn("octane_defects", tables)
                row = conn.execute(
                    "SELECT defect_id, name, year, fetched_at FROM octane_defects WHERE defect_id = ?",
                    ("D-1",),
                ).fetchone()
                self.assertEqual(row, ("D-1", "Voice wakeup fails", 2026, "2026-05-19T10:00:00Z"))
            finally:
                conn.close()

    @mock.patch("backfill_qgate_defects.data_processor.sync_processed_fields_to_db")
    def test_backfill_triggers_processed_field_sync(self, sync_mock):
        sync_mock.return_value = {"defect_updates": 3}

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(pathlib.Path(temp_dir) / "qgate_data.db")
            store = OctaneSQLiteStore(db_path)
            try:
                store.create_tables()
                store.upsert_payload(
                    kind="defects",
                    team="DTSV_China",
                    year=2026,
                    spec="DTSV_China",
                    payload={"data": [{"id": "D-2", "creation_time": "2026-05-01T00:00:00Z"}]},
                    fetched_at="2026-05-19T10:00:00Z",
                )
            finally:
                store.close()

            summary = backfill.backfill_qgate_defects(db_path)

        sync_mock.assert_called_once_with(db_path=db_path, sync_manual_runs=False)
        self.assertEqual(summary["processed_field_sync_ran"], 1)
        self.assertEqual(summary["processed_defect_updates"], 3)


if __name__ == "__main__":
    unittest.main()