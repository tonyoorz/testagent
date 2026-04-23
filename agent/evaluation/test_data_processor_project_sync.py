import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import data_processor


class DataProcessorProjectSyncTests(unittest.TestCase):
    @mock.patch("data_processor.load_app_rsu_mapping")
    @mock.patch("data_processor._load_defects_from_optimized_table")
    @mock.patch("data_processor._load_octane_payload_data")
    def test_load_defect_data_classifies_projects_from_ecu_and_top_aida_without_vin(
        self,
        load_octane_payload_data_mock,
        load_defects_from_optimized_table_mock,
        load_app_rsu_mapping_mock,
    ):
        load_octane_payload_data_mock.return_value = [
            {
                "id": "1",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "IDCEVO-25"},
                "product_areas": {"data": [{"name": "Use Speech operation [01.04.02.01.01.05]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "2",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "HU-MGU_02_A"},
                "product_areas": {"data": [{"name": "Voice Interface [01.04.02.01.01.02]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "3",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "HU-MGU_02_L"},
                "product_areas": {"data": [{"name": "Voice Interface [01.04.02.01.01.02]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "4",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "RSE_EXBX-02"},
                "product_areas": {"data": [{"name": "Use Rear Seat Entertainment [01.04.01.09.02]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "5",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "APP_Mobile_2_0_Android_CN"},
                "product_areas": {"data": [{"name": "Tencent MiniProgramPlatform (Tencent MPP) [01.04.01.06.01]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "6",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "CDE-01"},
                "product_areas": {"data": [{"name": "Use Co-Driver Entertainment [01.04.01.09.03]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "7",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "ICON-25"},
                "product_areas": {"data": [{"name": "Basic Vehicle Connectivity [01.04.04.02.02.02]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "8",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "SP_NavInfo"},
                "product_areas": {"data": [{"name": "Guiding ASIA [01.04.03.01.02.08]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "9",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "IPN-10"},
                "product_areas": {"data": [{"name": "Provide Navigation 2.0 [01.04.03.01.03.06]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "10",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "BMTH-01"},
                "product_areas": {"data": [{"name": "Telephony via customer device [01.04.01.04.01.01]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "11",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "IPN-10_DE"},
                "product_areas": {"data": [{"name": "Provide Navigation 2.0 [01.04.03.01.03.06]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "12",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "SD-Amap"},
                "product_areas": {"data": [{"name": "Positioning ASIA [01.04.03.01.02.01.02]"}]},
                "user_tags": {"data": []},
            },
            {
                "id": "13",
                "creation_time": "2025-04-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": {"name": "BMT"},
                "product_areas": {"data": [{"name": "Stability"}]},
                "user_tags": {"data": []},
            },
        ]
        load_defects_from_optimized_table_mock.return_value = []
        load_app_rsu_mapping_mock.return_value = {
            "app": ["Tencent MiniProgramPlatform (Tencent MPP) [01.04.01.06.01]"],
            "rsu": ["Use Rear Seat Entertainment [01.04.01.09.02]"],
        }

        original_source = data_processor._DEFAULT_OCTANE_SOURCE
        original_reloader = data_processor.IS_RELOADER
        data_processor._DEFAULT_OCTANE_SOURCE = "db_only"
        data_processor.IS_RELOADER = False
        try:
            defect_df = data_processor.load_defect_data("defect/2025_defect.json")
        finally:
            data_processor._DEFAULT_OCTANE_SOURCE = original_source
            data_processor.IS_RELOADER = original_reloader

        project_by_id = defect_df.set_index("id")["project"].to_dict()
        self.assertEqual(project_by_id.get("1"), "IDCEVO")
        self.assertEqual(project_by_id.get("2"), "IDC")
        self.assertEqual(project_by_id.get("3"), "MGU")
        self.assertEqual(project_by_id.get("4"), "RSU")
        self.assertEqual(project_by_id.get("5"), "App")
        self.assertEqual(project_by_id.get("6"), "IDCEVO")
        self.assertEqual(project_by_id.get("7"), "IDCEVO")
        self.assertEqual(project_by_id.get("8"), "MGU")
        self.assertEqual(project_by_id.get("9"), "IDCEVO")
        self.assertEqual(project_by_id.get("10"), "IDCEVO")
        self.assertEqual(project_by_id.get("11"), "IDCEVO")
        self.assertEqual(project_by_id.get("12"), "IDCEVO")
        self.assertEqual(project_by_id.get("13"), "MGU")

    @mock.patch("data_processor.load_app_rsu_mapping")
    @mock.patch("data_processor._load_defects_from_optimized_table")
    @mock.patch("data_processor._load_octane_payload_data")
    def test_classifies_projects_from_software_version_and_lead_model(
        self,
        load_octane_payload_data_mock,
        load_defects_from_optimized_table_mock,
        load_app_rsu_mapping_mock,
    ):
        """software_version and lead_model should be used as fallback signals."""
        load_octane_payload_data_mock.return_value = [
            {
                "id": "sv1",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "BMWIDC23;mainline-24w49.5-1;idc23",
                "lead_model_udf": None,
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "sv2",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "BMWIDCEVO;2607_i460-25w50.2-1;idcevo",
                "lead_model_udf": None,
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "sv3",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "BMWMGU22;MGU22_25w36.3-1-2;mgu22",
                "lead_model_udf": None,
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "sv4",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "nightly/idcevo/rse26-mainline/25w50.7-1",
                "lead_model_udf": None,
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "lm1",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "",
                "lead_model_udf": {"name": "U12"},
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "lm2",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "",
                "lead_model_udf": {"name": "NA6"},
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "lm3",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "",
                "lead_model_udf": {"name": "G28"},
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
            {
                "id": "lm4",
                "creation_time": "2025-06-01T00:00:00Z",
                "vin_udf": "",
                "assigned_ecu_udf": None,
                "software_version_udf": "",
                "lead_model_udf": {"name": "G70"},
                "product_areas": {"data": []},
                "user_tags": {"data": []},
            },
        ]
        load_defects_from_optimized_table_mock.return_value = []
        load_app_rsu_mapping_mock.return_value = {"app": [], "rsu": []}

        original_source = data_processor._DEFAULT_OCTANE_SOURCE
        original_reloader = data_processor.IS_RELOADER
        data_processor._DEFAULT_OCTANE_SOURCE = "db_only"
        data_processor.IS_RELOADER = False
        try:
            defect_df = data_processor.load_defect_data("defect/2025_defect.json")
        finally:
            data_processor._DEFAULT_OCTANE_SOURCE = original_source
            data_processor.IS_RELOADER = original_reloader

        project_by_id = defect_df.set_index("id")["project"].to_dict()
        # software_version signals
        self.assertEqual(project_by_id.get("sv1"), "IDC")
        self.assertEqual(project_by_id.get("sv2"), "IDCEVO")
        self.assertEqual(project_by_id.get("sv3"), "MGU")
        self.assertEqual(project_by_id.get("sv4"), "IDCEVO")  # contains both idcevo and rse, idcevo takes priority
        # lead_model strong mappings
        self.assertEqual(project_by_id.get("lm1"), "IDC")      # U12 → IDC
        self.assertEqual(project_by_id.get("lm2"), "IDCEVO")   # NA6 → IDCEVO
        self.assertEqual(project_by_id.get("lm3"), "MGU")      # G28 → MGU
        # G70 is ambiguous → should remain Unknown
        self.assertEqual(project_by_id.get("lm4"), "Unknown")

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
