import unittest

from semantic_catalog.term_adapter import adapt_question_with_semantic_terms, merge_semantic_hints


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


if __name__ == "__main__":
    unittest.main()
