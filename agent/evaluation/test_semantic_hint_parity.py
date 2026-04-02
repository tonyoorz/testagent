import unittest

from agent.core.deterministic_sql_service import extract_query_hints
from semantic_catalog.deterministic_query_hints import build_deterministic_query_hints


class SemanticHintParityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
