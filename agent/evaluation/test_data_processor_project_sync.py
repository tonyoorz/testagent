import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import pandas as pd

import data_processor


class DataProcessorProjectSyncTests(unittest.TestCase):
    def test_sync_processed_project_to_db_updates_project_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sync_test.db"

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE octane_defects (
                        defect_id TEXT PRIMARY KEY
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE octane_manual_runs (
                        mr_id TEXT PRIMARY KEY
                    )
                    """
                )
                conn.execute("INSERT INTO octane_defects(defect_id) VALUES ('1001')")
                conn.execute("INSERT INTO octane_manual_runs(mr_id) VALUES ('9001')")
                conn.commit()
            finally:
                conn.close()

            defect_df = pd.DataFrame(
                [
                    {"id": "1001", "project": "IDC"},
                ]
            )
            manual_df = pd.DataFrame(
                [
                    {"id": "9001", "project": "IDCevo"},
                ]
            )

            stats = data_processor.sync_processed_project_to_db(
                defect_df=defect_df,
                manual_df=manual_df,
                db_path=str(db_path),
            )

            self.assertEqual(stats.get("defect_updates"), 1)
            self.assertEqual(stats.get("manual_run_updates"), 1)

            conn = sqlite3.connect(str(db_path))
            try:
                defect_row = conn.execute(
                    "SELECT project, tproject FROM octane_defects WHERE defect_id='1001'"
                ).fetchone()
                manual_row = conn.execute(
                    "SELECT project, tproject FROM octane_manual_runs WHERE mr_id='9001'"
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(defect_row, ("IDC", "IDC"))
            self.assertEqual(manual_row, ("IDCEVO", "IDCEVO"))

    def test_sync_processed_fields_to_db_updates_fv_team_fvp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sync_fields_test.db"

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE octane_defects (
                        defect_id TEXT PRIMARY KEY
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE octane_manual_runs (
                        mr_id TEXT PRIMARY KEY
                    )
                    """
                )
                conn.execute("INSERT INTO octane_defects(defect_id) VALUES ('d-1')")
                conn.execute("INSERT INTO octane_manual_runs(mr_id) VALUES ('m-1')")
                conn.commit()
            finally:
                conn.close()

            defect_df = pd.DataFrame(
                [
                    {
                        "id": "d-1",
                        "project": "IDCevo",
                        "fv": "DIPS_TSP_Enabler",
                        "team": "TSP",
                        "fvp": "Tianhua",
                    }
                ]
            )
            manual_df = pd.DataFrame(
                [
                    {
                        "id": "m-1",
                        "project": "MGU",
                        "fv": "IuK_TSP_HMI",
                        "team": "HMI",
                        "fvp": "Jerry",
                    }
                ]
            )

            stats = data_processor.sync_processed_fields_to_db(
                defect_df=defect_df,
                manual_df=manual_df,
                db_path=str(db_path),
            )

            self.assertEqual(stats.get("defect_updates"), 1)
            self.assertEqual(stats.get("manual_run_updates"), 1)

            conn = sqlite3.connect(str(db_path))
            try:
                defect_row = conn.execute(
                    "SELECT project, tproject, fv, team, fvp FROM octane_defects WHERE defect_id='d-1'"
                ).fetchone()
                manual_row = conn.execute(
                    "SELECT project, tproject, fv, team, fvp FROM octane_manual_runs WHERE mr_id='m-1'"
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(defect_row, ("IDCEVO", "IDCEVO", "DIPS_TSP_Enabler", "TSP", "Tianhua"))
            self.assertEqual(manual_row, ("MGU", "MGU", "IuK_TSP_HMI", "HMI", "Jerry"))

    @mock.patch("data_processor.load_test_data")
    @mock.patch("data_processor.load_defect_data")
    def test_sync_processed_fields_to_db_discovers_years_and_loads_all_defect_years(
        self,
        load_defect_data_mock,
        load_test_data_mock,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "sync_all_years_test.db"

            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE octane_defects (
                        defect_id TEXT PRIMARY KEY,
                        year INTEGER
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE octane_manual_runs (
                        mr_id TEXT PRIMARY KEY,
                        year INTEGER
                    )
                    """
                )
                conn.execute("INSERT INTO octane_defects(defect_id, year) VALUES ('d-2024', 2024)")
                conn.execute("INSERT INTO octane_defects(defect_id, year) VALUES ('d-2025', 2025)")
                conn.execute("INSERT INTO octane_manual_runs(mr_id, year) VALUES ('m-2024', 2024)")
                conn.execute("INSERT INTO octane_manual_runs(mr_id, year) VALUES ('m-2026', 2026)")
                conn.commit()
            finally:
                conn.close()

            def _fake_load_defect_data(file_pattern="defect/2025_defect.json"):
                if "2024" in str(file_pattern):
                    return pd.DataFrame([{"id": "d-2024", "project": "IDC"}])
                if "2025" in str(file_pattern):
                    return pd.DataFrame([{"id": "d-2025", "project": "MGU"}])
                return pd.DataFrame(columns=["id", "project"])

            load_defect_data_mock.side_effect = _fake_load_defect_data
            load_test_data_mock.return_value = pd.DataFrame(
                [
                    {"id": "m-2024", "project": "App"},
                    {"id": "m-2026", "project": "IDCevo"},
                ]
            )

            stats = data_processor.sync_processed_fields_to_db(db_path=str(db_path))

            self.assertEqual(stats.get("defect_updates"), 2)
            self.assertEqual(stats.get("manual_run_updates"), 2)

            call_patterns = [
                str(call.kwargs.get("file_pattern", ""))
                for call in load_defect_data_mock.call_args_list
            ]
            self.assertIn("defect/2024_defect.json", call_patterns)
            self.assertIn("defect/2025_defect.json", call_patterns)

            conn = sqlite3.connect(str(db_path))
            try:
                defect_rows = conn.execute(
                    "SELECT defect_id, project, tproject FROM octane_defects ORDER BY defect_id"
                ).fetchall()
                manual_rows = conn.execute(
                    "SELECT mr_id, project, tproject FROM octane_manual_runs ORDER BY mr_id"
                ).fetchall()
            finally:
                conn.close()

            self.assertEqual(defect_rows, [("d-2024", "IDC", "IDC"), ("d-2025", "MGU", "MGU")])
            self.assertEqual(manual_rows, [("m-2024", "App", "App"), ("m-2026", "IDCEVO", "IDCEVO")])


if __name__ == "__main__":
    unittest.main()
