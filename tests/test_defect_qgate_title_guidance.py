import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "report" / "generate_defect_qgate_title_guidance.py"
    spec = importlib.util.spec_from_file_location("defect_qgate_title_guidance_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DefectQGateTitleGuidanceTests(unittest.TestCase):
    def test_generate_guidance_writes_single_csv(self):
        module = _load_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            db_path = temp_root / "sample.db"
            output_root = temp_root / "out"

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE octane_defects (
                        defect_id TEXT PRIMARY KEY,
                        name TEXT,
                        top_aida TEXT,
                        first_use_sop_of_function TEXT,
                        project TEXT,
                        owner TEXT,
                        team TEXT,
                        creation_time TEXT
                    )
                    """
                )
                rows = [
                    ("1", "g70 hicar connection failed", "Provide Projected Modes China", "26-07", "IDCEVO", "Kay Tang", "DTSV_China", "2026-04-01T00:00:00Z"),
                    ("2", "g70 hicar audio issue", "Provide Projected Modes China", "26-07", "IDCEVO", "Kay Tang", "DTSV_China", "2026-04-02T00:00:00Z"),
                    ("3", "g70 hicar pairing error", "Provide Projected Modes China", "26-07", "IDCEVO", "Kay Tang", "DTSV_China", "2026-04-03T00:00:00Z"),
                    ("4", "g70 hicar disconnect", "Provide Projected Modes China", "26-07", "IDCEVO", "Cara Wang", "DTSV_China", "2026-04-04T00:00:00Z"),
                    ("5", "carplay apple map issue", "CarPlay", "25-07", "IDC", "Andreas Netzmann", "DTSV_China", "2026-04-05T00:00:00Z"),
                    ("6", "carplay apple map freeze", "CarPlay", "25-07", "IDC", "Andreas Netzmann", "DTSV_China", "2026-04-06T00:00:00Z"),
                    ("7", "carplay apple map crash", "CarPlay", "25-07", "IDC", "Andreas Netzmann", "DTSV_China", "2026-04-07T00:00:00Z"),
                    ("8", "carplay apple map lag", "CarPlay", "25-07", "IDC", "Ender Ersan", "DTSV_China", "2026-04-08T00:00:00Z"),
                ]
                conn.executemany(
                    "INSERT INTO octane_defects(defect_id, name, top_aida, first_use_sop_of_function, project, owner, team, creation_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                conn.commit()
            finally:
                conn.close()

            output_path, guidance_df = module.generate_guidance(
                db_path=db_path,
                output_root=output_root,
                min_feature_total=2,
                min_match_count=2,
                min_precision=0.45,
                min_lift=1.2,
                top_function_count=2,
                top_project_count=2,
                top_owner_count=2,
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.suffix, ".csv")
            self.assertGreater(len(guidance_df), 0)
            self.assertIn("candidate_project", guidance_df.columns)
            self.assertIn("candidate_owner", guidance_df.columns)

            created_files = list(output_root.iterdir())
            self.assertEqual(len(created_files), 1)
            self.assertEqual(created_files[0], output_path)


if __name__ == "__main__":
    unittest.main()