import unittest
from unittest.mock import patch

from semantic_catalog.term_adapter import (
    _clear_unified_intent_adapter_cache,
    adapt_question_with_semantic_terms,
    build_unified_query_intent,
    merge_semantic_hints,
)


class SemanticTermAdapterTests(unittest.TestCase):
    def test_adapter_maps_feature_question_to_aida_intent(self):
        out = adapt_question_with_semantic_terms(
            question="请按功能看问题分布",
            table_name="octane_defects",
            db_path=None,
            prefer_db=False,
        )

        hints = out.get("semantic_hints") or {}
        self.assertTrue(hints.get("wants_feature_breakdown"))
        self.assertTrue(hints.get("wants_aida_dist"))
        self.assertTrue(str(hints.get("preferred_dimension") or ""))

    def test_adapter_extracts_month_and_showstopper_candidate(self):
        out = adapt_question_with_semantic_terms(
            question="3月份showstopper candidate发现了多少",
            table_name="octane_defects",
            db_path=None,
            prefer_db=False,
        )

        hints = out.get("semantic_hints") or {}
        self.assertEqual(hints.get("month_number"), 3)
        self.assertTrue(hints.get("wants_showstopper"))
        self.assertTrue(hints.get("wants_showstopper_candidate"))

    def test_merge_semantic_hints_combines_flags_and_lists(self):
        merged = merge_semantic_hints(
            {
                "wants_aida_dist": True,
                "mapped_dimensions": ["top_aida"],
                "matched_rule_ids": ["br_defect_critical_classification_default"],
            },
            {
                "wants_showstopper": True,
                "wants_showstopper_candidate": True,
                "month_number": 3,
                "mapped_dimensions": ["aida_english"],
            },
        )

        self.assertTrue(merged.get("wants_aida_dist"))
        self.assertTrue(merged.get("wants_showstopper"))
        self.assertTrue(merged.get("wants_showstopper_candidate"))
        self.assertEqual(merged.get("month_number"), 3)
        dims = merged.get("mapped_dimensions") or []
        self.assertIn("top_aida", dims)
        self.assertIn("aida_english", dims)

    def test_unified_intent_builder_returns_expected_contract(self):
        intent = build_unified_query_intent(
            question="3月份showstopper candidate按功能分布",
            columns=["creation_time", "top_aida", "status_phase", "name"],
            table_name="octane_defects",
        )

        self.assertIsInstance(intent, dict)
        for key in [
            "query_family",
            "table_hint",
            "time_scope",
            "entity_filters",
            "semantic_constraints",
            "confidence",
            "provenance",
        ]:
            self.assertIn(key, intent)

        self.assertIsInstance(intent.get("time_scope"), dict)
        self.assertIsInstance(intent.get("entity_filters"), list)
        self.assertIsInstance(intent.get("semantic_constraints"), dict)
        self.assertIsInstance(intent.get("provenance"), list)

    def test_unified_intent_builder_cache_reuses_adapter_result_with_stable_contract(self):
        _clear_unified_intent_adapter_cache()
        try:
            with patch("semantic_catalog.term_adapter.adapt_question_with_semantic_terms") as mock_adapter:
                mock_adapter.return_value = {
                    "original_question": "cache-check-20260403",
                    "normalized_question": "cache-check-20260403",
                    "semantic_hints": {
                        "wants_aida_dist": True,
                        "wants_showstopper": True,
                        "month_number": 6,
                        "preferred_dimension": "top_aida",
                    },
                    "mapped_dimensions": ["top_aida"],
                    "matched_rule_ids": ["br_defect_critical_classification_default"],
                    "provenance": [{"type": "unit_test", "source": "cache"}],
                }

                kwargs = {
                    "question": "cache-check-20260403",
                    "columns": ["creation_time", "top_aida", "status_phase", "name"],
                    "table_name": "octane_defects",
                    "db_path": None,
                    "prefer_db": False,
                }

                first = build_unified_query_intent(**kwargs)
                second = build_unified_query_intent(**kwargs)

            mock_adapter.assert_called_once()
            self.assertEqual(first, second)
            self.assertIsInstance(second.get("time_scope"), dict)
            self.assertIsInstance(second.get("entity_filters"), list)
            self.assertIsInstance(second.get("semantic_constraints"), dict)
            self.assertIsInstance(second.get("provenance"), list)
        finally:
            _clear_unified_intent_adapter_cache()


if __name__ == "__main__":
    unittest.main()
