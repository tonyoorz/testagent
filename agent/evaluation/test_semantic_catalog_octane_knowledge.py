import json
import unittest
from pathlib import Path


class SemanticCatalogOctaneKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo_root = Path(__file__).resolve().parents[2]
        datasets_path = repo_root / "semantic_catalog" / "datasets.json"
        business_rules_path = repo_root / "semantic_catalog" / "business_rules.json"

        cls.datasets = json.loads(datasets_path.read_text(encoding="utf-8"))
        cls.business_rules = json.loads(business_rules_path.read_text(encoding="utf-8"))

    def _dataset_by_id(self, dataset_id):
        for dataset in self.datasets.get("datasets", []):
            if dataset.get("id") == dataset_id:
                return dataset
        return {}

    def test_octane_defects_declares_optimized_table_schema(self):
        dataset = self._dataset_by_id("octane_defects")
        optimized = dataset.get("optimized_table") or {}

        self.assertEqual(optimized.get("table_name"), "octane_defects")
        columns = optimized.get("columns") or []
        self.assertGreaterEqual(len(columns), 44)

        names = {str(item.get("name") or "") for item in columns}
        required_columns = {
            "problem_finder_team",
            "function_responsible",
            "tolerated_count",
            "reprel_changes",
            "reporting_class",
            "raw_json",
            "fvp",
        }
        self.assertTrue(required_columns.issubset(names))

    def test_octane_tests_declares_optimized_table_schema(self):
        dataset = self._dataset_by_id("octane_tests")
        optimized = dataset.get("optimized_table") or {}

        self.assertEqual(optimized.get("table_name"), "octane_manual_runs")
        columns = optimized.get("columns") or []
        self.assertGreaterEqual(len(columns), 30)

        names = {str(item.get("name") or "") for item in columns}
        required_columns = {
            "testing_tool_type",
            "native_status",
            "target_ecu_conf",
            "testplatformid",
            "run_team",
            "defect_id",
            "raw_json",
        }
        self.assertTrue(required_columns.issubset(names))

    def test_business_rules_include_octane_db_and_history_knowledge(self):
        rules = self.business_rules.get("business_rules") or []
        rule_ids = {str(item.get("id") or "") for item in rules}

        required_rule_ids = {
            "br_problem_finder_team_vs_team",
            "br_history_json_structure",
            "br_reprel_changes_meaning",
            "br_testing_tool_type_classification",
            "br_native_status_vs_status",
            "br_raw_json_access_pattern",
            "br_octane_db_flattening_logic",
        }
        self.assertTrue(required_rule_ids.issubset(rule_ids))


if __name__ == "__main__":
    unittest.main()
