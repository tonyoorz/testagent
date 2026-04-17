import unittest
import json
from unittest.mock import patch

from agent.core.deterministic_sql_service import extract_query_hints
from semantic_catalog.deterministic_query_hints import (
    build_deterministic_query_hints,
    load_query_registry,
)


class SemanticHintParityTests(unittest.TestCase):
    def test_query_registry_load_failure_warns_and_falls_back(self):
        with patch("semantic_catalog.deterministic_query_hints.Path.read_text", return_value="{bad-json"):
            with self.assertLogs("semantic_catalog.deterministic_query_hints", level="WARNING") as captured:
                registry = load_query_registry()

        self.assertEqual(registry, {})
        self.assertTrue(any("Failed to load query registry" in line for line in captured.output))

    def test_query_registry_skips_malformed_and_type_mismatched_entries(self):
        payload = {
            "valid_family": {
                "target_tables": ["octane_defects"],
                "required_dimensions": ["team"],
                "parameter_slots": {"year": "int"},
                "output_contract": {"kind": "table"},
                "constraints": {"limit": 100},
            },
            "missing_required_key": {
                "target_tables": ["octane_defects"],
                "required_dimensions": ["team"],
                "parameter_slots": {"year": "int"},
                "output_contract": {"kind": "table"},
            },
            "bad_target_tables": {
                "target_tables": "octane_defects",
                "required_dimensions": ["team"],
                "parameter_slots": {"year": "int"},
                "output_contract": {"kind": "table"},
                "constraints": {"limit": 100},
            },
            "bad_required_dimensions": {
                "target_tables": ["octane_defects"],
                "required_dimensions": {"team": True},
                "parameter_slots": {"year": "int"},
                "output_contract": {"kind": "table"},
                "constraints": {"limit": 100},
            },
            "bad_parameter_slots": {
                "target_tables": ["octane_defects"],
                "required_dimensions": ["team"],
                "parameter_slots": ["year"],
                "output_contract": {"kind": "table"},
                "constraints": {"limit": 100},
            },
            "bad_output_contract": {
                "target_tables": ["octane_defects"],
                "required_dimensions": ["team"],
                "parameter_slots": {"year": "int"},
                "output_contract": ["table"],
                "constraints": {"limit": 100},
            },
            "bad_constraints": {
                "target_tables": ["octane_defects"],
                "required_dimensions": ["team"],
                "parameter_slots": {"year": "int"},
                "output_contract": {"kind": "table"},
                "constraints": ["limit"],
            },
        }

        with patch(
            "semantic_catalog.deterministic_query_hints.Path.read_text",
            return_value=json.dumps(payload),
        ):
            registry = load_query_registry()

        self.assertEqual(set(registry.keys()), {"valid_family"})

    def test_query_registry_contains_required_families(self):
        registry = load_query_registry()
        required_families = {
            "trend_by_week",
            "risk_ranking",
            "aida_distribution",
            "tester_performance",
            "test_execution",
        }

        self.assertTrue(required_families.issubset(set(registry.keys())))

    def test_query_registry_entry_has_contract_keys(self):
        registry = load_query_registry()
        required_keys = {
            "target_tables",
            "required_dimensions",
            "parameter_slots",
            "output_contract",
            "constraints",
        }

        for family_name, definition in registry.items():
            with self.subTest(family=family_name):
                self.assertTrue(required_keys.issubset(set(definition.keys())))

    def test_extract_query_hints_keeps_shared_core_flags_in_sync(self):
        cases = [
            ("请看执行状态中Blocked和Failed周趋势", ["test_week", "run_status", "owner"]),
            ("请分析缺陷矩阵分布和严重性问题", ["defect_id", "severity", "creation_time"]),
            ("状态变更记录", ["modified_time", "defect_id", "field_name", "old_value", "new_value"]),
            ("请看AIDA维度缺陷状态分布", ["top_aida", "status_phase", "creation_time"]),
        ]
        shared_keys = [
            "wants_distribution",
            "wants_matrix",
            "wants_severity",
            "wants_matrix_severity",
            "wants_aida_dist",
            "wants_topissue",
            "wants_detail",
            "wants_tester",
            "wants_trend",
            "wants_efficiency",
            "wants_test_coverage",
            "wants_recommendation",
            "wants_analysis",
        ]

        for question, columns in cases:
            with self.subTest(question=question):
                shared = build_deterministic_query_hints(question, columns)
                runtime = extract_query_hints(question, columns)
                for key in shared_keys:
                    self.assertEqual(bool(runtime.get(key)), bool(shared.get(key)), f"mismatch at {key}")

    def test_extract_query_hints_allows_semantic_overrides(self):
        runtime = extract_query_hints(
            "请看本月关键问题",
            ["creation_time", "status_phase", "top_aida", "name"],
            semantic_hints={
                "wants_aida_dist": True,
                "wants_showstopper": True,
                "wants_showstopper_candidate": True,
                "month_number": 3,
                "preferred_dimension": "top_aida",
            },
        )

        self.assertTrue(runtime.get("wants_aida_dist"))
        self.assertTrue(runtime.get("wants_showstopper"))
        self.assertTrue(runtime.get("wants_showstopper_candidate"))
        self.assertEqual(runtime.get("month_number"), 3)
        self.assertEqual(runtime.get("preferred_dimension"), "top_aida")

    def test_testcase_summary_phrase_is_recognized_as_manual_run_coverage(self):
        question = "上周团队测试用例情况"
        columns = ["creation_time", "status", "run_by", "test_id", "run_team"]

        shared = build_deterministic_query_hints(question, columns)
        runtime = extract_query_hints(question, columns)

        self.assertTrue(bool(shared.get("wants_test_coverage")))
        self.assertTrue(bool(runtime.get("wants_test_coverage")))


if __name__ == "__main__":
    unittest.main()
