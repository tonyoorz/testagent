import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from duplicate_issue_finder import DuplicateCandidate, DuplicateSearchHints
from feedback_store import FeedbackStore
from progressive_reranker import ProgressiveReRanker


class FakeIndex:
    def __init__(self):
        self._meta = [
            {
                "ticket_id": "DEF-1",
                "name": "Route planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "ecu": "HU-H5",
                "lead_model": "G60",
                "description": "Route planning failed after destination input.",
                "status_phase": "03-In Analysis",
            },
            {
                "ticket_id": "DEF-2",
                "name": "App crash on startup",
                "project": "APP",
                "pu": "25-01",
                "ecu": "APP-ECU",
                "lead_model": "G20",
                "description": "App crashes during startup.",
                "status_phase": "03-In Analysis",
            },
        ]
        self._embedding_matrix = np.asarray(
            [
                [1.0, 0.0],
                [0.0, 1.0],
            ],
            dtype=np.float32,
        )


class TestProgressiveReRanker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = FeedbackStore(db_path=os.path.join(self.temp_dir.name, "feedback.db"))
        self.index = FakeIndex()
        self.candidates = [
            DuplicateCandidate(6, 0.60, "DEF-1", "Route planning failed", "IDCEVO", "26-07", "03-In Analysis", "Route planning failed after destination input."),
            DuplicateCandidate(6, 0.60, "DEF-2", "App crash on startup", "APP", "25-01", "03-In Analysis", "App crashes during startup."),
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_phase1_boosts_positive_ticket(self):
        self.store.submit_feedback("IDCEVO 26/07 routing failed", "DEF-1", "positive", user_id="alice")
        self.store.submit_feedback("IDCEVO 26/07 routing failed", "DEF-2", "negative", user_id="bob")
        reranker = ProgressiveReRanker(self.store)
        reranker.refresh(index=self.index)

        reranked = reranker.rerank(
            "IDCEVO 26/07 routing failed",
            self.candidates,
            hints=DuplicateSearchHints(project="idcevo", pu="26-07"),
            index=self.index,
            top_k=2,
        )

        self.assertEqual(reranker.model_phase, "click_boost")
        self.assertEqual(reranked[0].ticket_id, "DEF-1")
        self.assertGreater(reranked[0].similarity, reranked[1].similarity)

    def test_phase2_trains_feature_reranker_when_feedback_is_sufficient(self):
        for i in range(25):
            self.store.submit_feedback(
                f"IDCEVO 26/07 routing failed {i}", "DEF-1", "positive", user_id=f"user-p-{i}"
            )
            self.store.submit_feedback(
                f"APP 25/01 startup crash {i}", "DEF-2", "negative", user_id=f"user-n-{i}"
            )

        reranker = ProgressiveReRanker(self.store)
        reranker.refresh(index=self.index)
        reranked = reranker.rerank(
            "IDCEVO 26/07 routing failed",
            self.candidates,
            hints=DuplicateSearchHints(project="idcevo", pu="26-07"),
            index=self.index,
            top_k=2,
        )

        self.assertEqual(reranker.model_phase, "feature")
        self.assertEqual(reranked[0].ticket_id, "DEF-1")

    def test_insufficient_label_diversity_falls_back_to_click_boost(self):
        for i in range(60):
            self.store.submit_feedback(f"IDCEVO 26/07 routing failed {i}", "DEF-1", "positive", user_id=f"user-{i}")

        reranker = ProgressiveReRanker(self.store)
        reranker.refresh(index=self.index)

        self.assertEqual(reranker.model_phase, "click_boost")

    def test_phase3_activates_adapter_when_feedback_and_embeddings_are_available(self):
        for i in range(100):
            query = f"IDCEVO 26/07 routing failed {i}"
            self.store.submit_feedback(query, "DEF-1", "positive", user_id=f"user-p-{i}")
            self.store.submit_feedback(query, "DEF-2", "negative", user_id=f"user-n-{i}")

        reranker = ProgressiveReRanker(self.store)
        with patch(
            "progressive_reranker._encode_query_embeddings",
            return_value=np.asarray([[1.0, 0.0]] * 100, dtype=np.float32),
        ):
            reranker.refresh(index=self.index)
            reranked = reranker.rerank(
                "IDCEVO 26/07 routing failed",
                self.candidates,
                hints=DuplicateSearchHints(project="idcevo", pu="26-07"),
                index=self.index,
                top_k=2,
            )

        self.assertEqual(reranker.model_phase, "adapter")
        self.assertEqual(reranked[0].ticket_id, "DEF-1")


if __name__ == "__main__":
    unittest.main()
