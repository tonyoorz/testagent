import os
import tempfile
import unittest

import pandas as pd

from agent.core.intelligent_agent import DuplicateIssueSearchTool, SubmitDuplicateSearchFeedbackTool
from feedback_store import FeedbackStore


class TestDuplicateIssueTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "feedback.db")
        self.store = FeedbackStore(db_path=self.db_path)
        self.data = pd.DataFrame(
            [
                {
                    "id": "DEF-1",
                    "name": "Route planning failed",
                    "description": "Route planning failed after destination input.",
                    "project": "IDCEVO",
                    "pu": "26-07",
                    "status_phase": "03-In Analysis",
                },
                {
                    "id": "DEF-2",
                    "name": "App crash on startup",
                    "description": "App crashes during startup.",
                    "project": "APP",
                    "pu": "25-01",
                    "status_phase": "03-In Analysis",
                },
            ]
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_duplicate_search_tool_returns_feedback_metadata(self):
        tool = DuplicateIssueSearchTool()

        result = tool.execute(
            self.data,
            query="IDCEVO 26/07 routing failed",
            top_k=2,
            cache_key="tool-test",
            feedback_db_path=self.db_path,
        )

        self.assertTrue(result["success"])
        self.assertIn("model_phase", result["result"])
        self.assertIn("feedback_count", result["result"])
        self.assertIn("search_id", result["result"])

    def test_feedback_tool_persists_feedback(self):
        tool = SubmitDuplicateSearchFeedbackTool()

        result = tool.execute(
            self.data,
            query_text="IDCEVO 26/07 routing failed",
            ticket_id="DEF-1",
            signal="positive",
            user_id="alice",
            feedback_db_path=self.db_path,
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.store.count_feedback(), 1)


if __name__ == "__main__":
    unittest.main()
