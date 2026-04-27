import os
import tempfile
import unittest

from feedback_store import FeedbackStore, TrainingScheduler


class TestTrainingScheduler(unittest.TestCase):
    def test_phase_thresholds(self):
        scheduler = TrainingScheduler()
        self.assertEqual(scheduler.current_phase(0), "click_boost")
        self.assertEqual(scheduler.current_phase(50), "feature")
        self.assertEqual(scheduler.current_phase(200), "adapter")


class TestFeedbackStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "feedback.db")
        self.store = FeedbackStore(db_path=self.db_path, max_feedback_per_hour=2)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_submit_feedback_persists_and_counts(self):
        result = self.store.submit_feedback(
            query_text="IDCEVO 26/07 routing failed",
            ticket_id="DEF-1",
            signal="positive",
            user_id="alice",
            base_score=0.62,
            rank_pos=0,
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(self.store.count_feedback(), 1)
        stats = self.store.get_ticket_feedback_stats(["DEF-1"])
        self.assertEqual(stats["DEF-1"]["positive"], 1)
        self.assertAlmostEqual(stats["DEF-1"]["positive_rate"], 0.5)

    def test_flip_detection_invalidates_previous_signal(self):
        self.store.submit_feedback("q1", "DEF-1", "positive", user_id="alice")
        result = self.store.submit_feedback("q1", "DEF-1", "negative", user_id="alice")

        self.assertTrue(result["accepted"])
        rows = self.store.list_feedback(query_text="q1", ticket_id="DEF-1", valid_only=False)
        valid_rows = [row for row in rows if row["is_valid"]]
        self.assertEqual(len(valid_rows), 1)
        self.assertEqual(valid_rows[0]["signal"], "negative")

    def test_rate_limit_rejects_excess_feedback(self):
        self.store.submit_feedback("q1", "DEF-1", "positive", user_id="alice")
        self.store.submit_feedback("q2", "DEF-2", "positive", user_id="alice")
        result = self.store.submit_feedback("q3", "DEF-3", "negative", user_id="alice")

        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "rate_limit")

    def test_training_examples_return_only_valid_rows(self):
        self.store.submit_feedback("q1", "DEF-1", "positive", user_id="alice")
        self.store.submit_feedback("q1", "DEF-1", "negative", user_id="alice")
        self.store.submit_feedback("q2", "DEF-2", "click", user_id="bob")

        rows = self.store.get_training_examples()

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["signal"] for row in rows}, {"negative", "click"})


if __name__ == "__main__":
    unittest.main()
