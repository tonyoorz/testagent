import unittest

from agent.core.page_context_adapter import normalize_page_context


class PageContextAdapterTests(unittest.TestCase):
    def test_normalize_page_context_keeps_dashboard_and_filter_state(self):
        payload = normalize_page_context(
            dashboard_type="defect",
            current_data={"defects": object()},
            conversation_state={"selected_team": "DTSV_China"},
            extra_context={"page_filters": {"project": ["IDCEVO"], "week": 12}},
        )

        self.assertEqual(payload["dashboard_type"], "defect")
        self.assertEqual(payload["selected_team"], "DTSV_China")
        self.assertEqual(payload["page_filters"], {"project": ["IDCEVO"], "week": 12})
        self.assertEqual(payload["available_datasets"], ["defects"])

    def test_normalize_page_context_handles_dataframe_like_absence(self):
        payload = normalize_page_context(
            dashboard_type="general",
            current_data=None,
            conversation_state=None,
            extra_context=None,
        )

        self.assertEqual(payload["dashboard_type"], "general")
        self.assertEqual(payload["available_datasets"], [])
        self.assertEqual(payload["page_filters"], {})


if __name__ == "__main__":
    unittest.main()