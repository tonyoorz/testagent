import unittest
from unittest.mock import patch

from agent.core.deterministic_sql_service import (
    build_deterministic_sql,
    decide_query_execution_strategy,
    extract_query_hints,
    guess_target_table,
)


class DeterministicSQLServiceTests(unittest.TestCase):
    def test_summary_path_prefers_deterministic_sql_for_structured_query(self):
        decision = decide_query_execution_strategy(
            question="请看测试通过率周趋势，并给出Top 5 tester",
            columns=["test_week", "run_status", "run_by", "test_id"],
        )

        self.assertEqual(decision.get("strategy"), "deterministic_first")
        self.assertGreaterEqual(float(decision.get("confidence") or 0.0), 0.6)

    def test_summary_path_allows_llm_fallback_when_deterministic_confidence_low(self):
        decision = decide_query_execution_strategy(
            question="请做根因分析并给出改进建议，定义一下关键质量问题",
            columns=["creation_time", "status_phase", "name"],
        )

        self.assertEqual(decision.get("strategy"), "constrained_fallback")
        self.assertLess(float(decision.get("confidence") or 1.0), 0.6)

    def test_guess_target_table_routes_execution_status_to_manual_runs(self):
        table = guess_target_table("请看执行状态中Blocked和Failed周趋势")
        self.assertEqual(table, "octane_manual_runs")

    def test_guess_target_table_routes_test_case_execution_phrase_to_manual_runs(self):
        table = guess_target_table("所有测试人员测试用例执行情况")
        self.assertEqual(table, "octane_manual_runs")

    def test_guess_target_table_routes_testcase_synonyms_to_manual_runs(self):
        phrases = [
            "all testers testcase execution status",
            "please summarize test cases execution",
            "所有测试人员 cases 执行情况",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(guess_target_table(phrase), "octane_manual_runs")

    def test_guess_target_table_routes_history_synonyms_to_defect_histories(self):
        phrases = [
            "缺陷流转历史",
            "状态变更记录",
            "defect status history",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(guess_target_table(phrase), "octane_defect_histories")

    def test_extract_query_hints_keeps_entity_and_marks_test_coverage(self):
        hints = extract_query_hints(
            "请看IDCEVO测试通过率趋势",
            ["creation_time", "status", "name"],
        )
        self.assertTrue(hints.get("wants_test_coverage"))
        self.assertIn("IDCEVO", hints.get("entity_tokens") or [])

    def test_extract_query_hints_marks_test_case_execution_phrase_as_test_coverage(self):
        hints = extract_query_hints(
            "所有测试人员测试用例执行情况",
            ["test_week", "run_status", "owner"],
        )
        self.assertTrue(hints.get("wants_test_coverage"))

    def test_extract_query_hints_marks_testcase_synonyms_as_test_coverage(self):
        phrases = [
            "all testers testcase execution status",
            "test cases execution summary",
            "所有测试人员 cases 执行情况",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                hints = extract_query_hints(phrase, ["creation_time", "status", "run_by", "test_id"])
                self.assertTrue(hints.get("wants_test_coverage"))

    def test_extract_query_hints_filters_confirmation_reply_tokens(self):
        hints = extract_query_hints(
            "继续",
            ["creation_time", "status_phase", "name", "author"],
        )

        self.assertEqual(hints.get("entity_tokens"), [])

    def test_build_deterministic_sql_does_not_search_confirmation_reply_literal(self):
        sql = build_deterministic_sql(
            question="继续",
            table_name="octane_defects",
            columns=["defect_id", "name", "author", "creation_time"],
        )

        self.assertNotIn("%继续%", sql)
        self.assertIn('FROM "octane_defects"', sql)

    def test_build_deterministic_sql_for_manual_runs_uses_pass_rate_aggregation(self):
        sql = build_deterministic_sql(
            question="请看测试执行通过率趋势",
            table_name="octane_manual_runs",
            columns=["creation_time", "status", "name"],
        )
        self.assertIn("pass_rate", sql)
        self.assertIn("run_count", sql)
        self.assertIn('FROM "octane_manual_runs"', sql)

    def test_build_deterministic_sql_for_test_case_execution_phrase_uses_manual_run_aggregation(self):
        sql = build_deterministic_sql(
            question="所有测试人员测试用例执行情况",
            table_name="octane_manual_runs",
            columns=["test_week", "run_status", "owner"],
        )
        self.assertIn("pass_rate", sql)
        self.assertIn("run_count", sql)
        self.assertIn('FROM "octane_manual_runs"', sql)

    def test_build_deterministic_sql_groups_manual_runs_by_tester_for_tester_execution_queries(self):
        sql = build_deterministic_sql(
            question="所有测试人员测试用例执行情况",
            table_name="octane_manual_runs",
            columns=["run_by", "status", "test_id", "test_name"],
        )
        self.assertIn("AS tester", sql)
        self.assertIn("testcase_count", sql)
        self.assertIn("run_count", sql)
        self.assertIn("pass_rate", sql)
        self.assertIn("GROUP BY 1", sql)

    def test_build_deterministic_sql_groups_manual_runs_by_tester_for_testcase_synonyms(self):
        sql = build_deterministic_sql(
            question="all testers test cases execution status",
            table_name="octane_manual_runs",
            columns=["run_by", "status", "test_id"],
        )
        self.assertIn("AS tester", sql)
        self.assertIn("testcase_count", sql)
        self.assertIn('FROM "octane_manual_runs"', sql)

    def test_build_deterministic_sql_for_english_testcase_summary_does_not_filter_on_intent_words(self):
        sql = build_deterministic_sql(
            question="please summarize test cases execution",
            table_name="octane_manual_runs",
            columns=["creation_time", "status", "run_by", "test_id", "test_name"],
        )
        self.assertIn("pass_rate", sql)
        self.assertNotIn("summarize", sql.lower())
        self.assertNotIn("%cases%", sql.lower())
        self.assertNotIn("%execution%", sql.lower())

    def test_build_deterministic_sql_for_history_synonym_avoids_literal_phrase_filter(self):
        sql = build_deterministic_sql(
            question="状态变更记录",
            table_name="octane_defect_histories",
            columns=["modified_time", "defect_id", "field_name", "old_value", "new_value"],
        )
        self.assertIn('FROM "octane_defect_histories"', sql)
        self.assertNotIn("状态变更记录", sql)

    def test_build_deterministic_sql_for_matrix_severity_joins_defect_features(self):
        sql = build_deterministic_sql(
            question="请分析缺陷矩阵分布和严重性问题",
            table_name="octane_defects",
            columns=["defect_id", "severity", "creation_time"],
        )
        self.assertIn('LEFT JOIN "defect_features"', sql)
        self.assertIn("matrix_zone", sql)
        self.assertIn("severity", sql)

    def test_extract_query_hints_maps_feature_question_to_aida_distribution(self):
        hints = extract_query_hints(
            "3月份showstopper candidate发现了多少 都是哪些功能",
            ["creation_time", "status_phase", "top_aida", "name"],
        )
        self.assertTrue(hints.get("wants_aida_dist"))
        self.assertTrue(hints.get("wants_showstopper"))
        self.assertNotIn("showstopper", [str(t).lower() for t in (hints.get("entity_tokens") or [])])
        self.assertNotIn("candidate", [str(t).lower() for t in (hints.get("entity_tokens") or [])])

    def test_extract_query_hints_uses_unified_intent_builder_when_available(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            mock_builder.return_value = {
                "query_family": "defect_distribution",
                "table_hint": "octane_defects",
                "time_scope": {"month_number": 4},
                "entity_filters": ["IDCEVO"],
                "semantic_constraints": {
                    "wants_aida_dist": True,
                    "preferred_dimension": "top_aida",
                    "wants_showstopper": True,
                },
                "confidence": 0.9,
                "provenance": [{"source": "unit_test"}],
            }

            hints = extract_query_hints(
                "请查看分布",
                ["creation_time", "top_aida", "status_phase", "name"],
            )

        mock_builder.assert_called_once()
        self.assertEqual(hints.get("month_number"), 4)
        self.assertIn("IDCEVO", hints.get("entity_tokens") or [])
        self.assertTrue(hints.get("wants_aida_dist"))
        self.assertTrue(hints.get("wants_showstopper"))
        self.assertEqual(hints.get("preferred_dimension"), "top_aida")

    def test_extract_query_hints_preserves_unified_positives_when_base_hints_are_weak(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            mock_builder.return_value = {
                "query_family": "defect_distribution",
                "table_hint": "octane_defects",
                "time_scope": {"month_number": 4},
                "entity_filters": ["IDCEVO"],
                "semantic_constraints": {
                    "wants_aida_dist": True,
                    "preferred_dimension": "top_aida",
                    "wants_showstopper": True,
                },
                "confidence": 0.9,
                "provenance": [{"source": "unit_test"}],
            }

            hints = extract_query_hints(
                "请查看分布",
                ["creation_time", "top_aida", "status_phase", "name"],
                semantic_hints={
                    "wants_aida_dist": False,
                    "wants_showstopper": False,
                    "preferred_dimension": None,
                    "month_number": None,
                    "entity_tokens": ["TEAM_X"],
                },
            )

        self.assertEqual(hints.get("month_number"), 4)
        self.assertIn("IDCEVO", hints.get("entity_tokens") or [])
        self.assertIn("TEAM_X", hints.get("entity_tokens") or [])
        self.assertTrue(hints.get("wants_aida_dist"))
        self.assertTrue(hints.get("wants_showstopper"))
        self.assertEqual(hints.get("preferred_dimension"), "top_aida")

    def test_extract_query_hints_allows_meaningful_base_hints_to_override_unified_values(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            mock_builder.return_value = {
                "query_family": "defect_distribution",
                "table_hint": "octane_defects",
                "time_scope": {"month_number": 4},
                "entity_filters": ["IDCEVO"],
                "semantic_constraints": {
                    "wants_aida_dist": True,
                    "preferred_dimension": "top_aida",
                    "wants_showstopper": True,
                },
                "confidence": 0.9,
                "provenance": [{"source": "unit_test"}],
            }

            hints = extract_query_hints(
                "请查看分布",
                ["creation_time", "top_aida", "aida_english", "status_phase", "name"],
                semantic_hints={
                    "preferred_dimension": "aida_english",
                    "month_number": 5,
                },
            )

        self.assertEqual(hints.get("month_number"), 5)
        self.assertEqual(hints.get("preferred_dimension"), "aida_english")

    def test_decide_query_execution_strategy_skips_unified_intent_when_semantic_hints_provided(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            decision = decide_query_execution_strategy(
                question="show pass rate trend by week",
                columns=["test_week", "run_status", "run_by"],
                semantic_hints={"entity_tokens": ["IDCEVO"]},
            )

        mock_builder.assert_not_called()
        self.assertEqual(decision.get("strategy"), "deterministic_first")

    def test_decide_query_execution_strategy_keeps_unified_intent_for_callers_without_semantic_hints(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            mock_builder.return_value = {}
            decide_query_execution_strategy(
                question="show pass rate trend by week",
                columns=["test_week", "run_status", "run_by"],
            )

        mock_builder.assert_called_once()

    def test_build_deterministic_sql_skips_unified_intent_when_semantic_hints_provided(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            sql = build_deterministic_sql(
                question="show pass rate trend by week",
                table_name="octane_manual_runs",
                columns=["test_week", "run_status", "run_by"],
                semantic_hints={"entity_tokens": ["IDCEVO"]},
            )

        mock_builder.assert_not_called()
        self.assertIn('FROM "octane_manual_runs"', sql)

    def test_build_deterministic_sql_keeps_unified_intent_for_callers_without_semantic_hints(self):
        with patch("agent.core.deterministic_sql_service.build_unified_query_intent") as mock_builder:
            mock_builder.return_value = {}
            build_deterministic_sql(
                question="show pass rate trend by week",
                table_name="octane_manual_runs",
                columns=["test_week", "run_status", "run_by"],
            )

        mock_builder.assert_called_once()

    def test_build_deterministic_sql_feature_question_uses_aida_and_showstopper_filter(self):
        sql = build_deterministic_sql(
            question="3月份showstopper candidate发现了多少 都是哪些功能",
            table_name="octane_defects",
            columns=["creation_time", "status_phase", "top_aida", "name"],
        )
        sql_lower = sql.lower()
        self.assertIn(" as aida", sql_lower)
        self.assertIn("group by 1", sql_lower)
        self.assertIn("showstopper", sql_lower)
        self.assertIn("candidate", sql_lower)
        self.assertIn("strftime('%m', creation_time) = '03'", sql_lower)
        self.assertIn('from "octane_defects"', sql_lower)

    def test_build_deterministic_sql_accepts_semantic_term_hints(self):
        sql = build_deterministic_sql(
            question="请看这个月关键问题分布",
            table_name="octane_defects",
            columns=["creation_time", "status_phase", "top_aida", "name"],
            semantic_hints={
                "wants_aida_dist": True,
                "wants_showstopper": True,
                "wants_showstopper_candidate": True,
                "month_number": 3,
                "preferred_dimension": "top_aida",
            },
        )
        sql_lower = sql.lower()
        self.assertIn(" as aida", sql_lower)
        self.assertIn("group by 1", sql_lower)
        self.assertIn("showstopper", sql_lower)
        self.assertIn("candidate", sql_lower)
        self.assertIn("strftime('%m', creation_time) = '03'", sql_lower)


if __name__ == "__main__":
    unittest.main()