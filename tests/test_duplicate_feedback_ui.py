import os
import tempfile
import unittest

from dash import html

from feedback_store import FeedbackStore
from duplicate_issue_finder import DuplicateCandidate
from agent.legacy.ai_chat_manager_legacy import (
    _build_duplicate_result_payload,
    _build_duplicate_summary_text,
    _build_latest_duplicate_result_store,
    _submit_duplicate_feedback,
    render_duplicate_result_message,
)


class TestDuplicateFeedbackPayload(unittest.TestCase):
    def test_build_duplicate_result_payload_includes_feedback_fields(self):
        candidates = [
            DuplicateCandidate(
                score_1_10=9,
                similarity=0.88,
                ticket_id="DEF-1001",
                name="Route planning failed",
                project="IDCEVO",
                pu="26-07",
                status_phase="03-In Analysis",
                snippet="Route planning failed after destination input.",
            )
        ]

        payload = _build_duplicate_result_payload(
            query_text="IDCEVO 26/07 route planning failed",
            dashboard_type="defect",
            candidates=candidates,
        )

        self.assertEqual(payload["query_text"], "IDCEVO 26/07 route planning failed")
        self.assertEqual(payload["dashboard_type"], "defect")
        self.assertEqual(payload["candidates"][0]["ticket_id"], "DEF-1001")
        self.assertEqual(payload["candidates"][0]["rank_pos"], 0)
        self.assertAlmostEqual(payload["candidates"][0]["similarity"], 0.88)

    def test_build_duplicate_summary_text_contains_conclusion_and_next_step(self):
        candidates = [
            DuplicateCandidate(
                score_1_10=9,
                similarity=0.88,
                ticket_id="DEF-1001",
                name="Route planning failed",
                project="IDCEVO",
                pu="26-07",
                status_phase="03-In Analysis",
                snippet="Route planning failed after destination input.",
            )
        ]

        summary = _build_duplicate_summary_text(candidates)

        self.assertIn("【结论】", summary)
        self.assertIn("【下一步】", summary)
        self.assertIn("DEF-1001", summary)

    def test_build_duplicate_summary_text_uses_highest_score_candidate_for_merge_target(self):
        candidates = [
            DuplicateCandidate(
                score_1_10=7,
                similarity=0.74,
                ticket_id="DEF-LOW",
                name="Less similar route planning issue",
                project="IDCEVO",
                pu="26-07",
                status_phase="03-In Analysis",
                snippet="Partial routing mismatch.",
            ),
            DuplicateCandidate(
                score_1_10=9,
                similarity=0.91,
                ticket_id="DEF-HIGH",
                name="Best matching route planning failure",
                project="IDCEVO",
                pu="26-07",
                status_phase="03-In Analysis",
                snippet="Best match for destination input failure.",
            ),
        ]

        summary = _build_duplicate_summary_text(candidates)

        self.assertIn("DEF-HIGH", summary)
        self.assertNotIn("DEF-LOW", summary)


class TestDuplicateFeedbackRenderer(unittest.TestCase):
    def test_renderer_outputs_summary_and_candidate_cards(self):
        message = {
            "role": "assistant",
            "type": "duplicate-search-result",
            "content": "【结论】\n- 建议：不建议提票",
            "duplicate_result": {
                "query_text": "IDCEVO 26/07 route planning failed",
                "dashboard_type": "defect",
                "candidates": [
                    {
                        "ticket_id": "DEF-1001",
                        "name": "Route planning failed",
                        "project": "IDCEVO",
                        "pu": "26-07",
                        "status_phase": "03-In Analysis",
                        "snippet": "Route planning failed after destination input.",
                        "score_1_10": 9,
                        "similarity": 0.88,
                        "rank_pos": 0,
                    }
                ],
            },
        }

        component = render_duplicate_result_message(message, chat_id_prefix="defect-chat")

        self.assertIsInstance(component, html.Div)
        component_str = repr(component)
        self.assertIn("DEF-1001", component_str)
        self.assertIn("duplicate-feedback-btn", component_str)
        self.assertIn("👍 匹配", component_str)
        self.assertIn("👎 不匹配", component_str)


class TestDuplicateFeedbackStoreShape(unittest.TestCase):
    def test_latest_duplicate_result_store_is_keyed_by_ticket_id(self):
        payload = {
            "query_text": "IDCEVO 26/07 route planning failed",
            "dashboard_type": "defect",
            "candidates": [
                {
                    "ticket_id": "DEF-1001",
                    "name": "Route planning failed",
                    "similarity": 0.88,
                    "rank_pos": 0,
                }
            ],
        }

        store = _build_latest_duplicate_result_store(payload)

        self.assertEqual(store["query_text"], "IDCEVO 26/07 route planning failed")
        self.assertIn("DEF-1001", store["candidates_by_ticket"])
        self.assertEqual(store["candidates_by_ticket"]["DEF-1001"]["rank_pos"], 0)


class TestDuplicateFeedbackSubmission(unittest.TestCase):
    def test_submit_duplicate_feedback_persists_positive_signal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "feedback.db")
            store_payload = {
                "query_text": "IDCEVO 26/07 route planning failed",
                "dashboard_type": "defect",
                "candidates_by_ticket": {
                    "DEF-1001": {
                        "ticket_id": "DEF-1001",
                        "similarity": 0.88,
                        "rank_pos": 0,
                    }
                },
            }

            result = _submit_duplicate_feedback(
                store_payload=store_payload,
                ticket_id="DEF-1001",
                signal="positive",
                feedback_db_path=db_path,
            )

            persisted = FeedbackStore(db_path=db_path).list_feedback(query_text="IDCEVO 26/07 route planning failed")

            self.assertTrue(result["success"])
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["signal"], "positive")


if __name__ == "__main__":
    unittest.main()