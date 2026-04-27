import unittest
import os
import tempfile

import numpy as np

from duplicate_issue_finder import DuplicateIssueIndex, DuplicateSearchHints, extract_hints
from feedback_store import FeedbackStore
from progressive_reranker import ProgressiveReRanker


class TestExtractHints(unittest.TestCase):
    """Verify extract_hints parses project & PU from messy free-form text."""

    # --- Project detection ---
    def test_project_idcevo_case_insensitive(self):
        self.assertEqual(extract_hints("IDCEVO 26/07 route fail").project, "idcevo")

    def test_project_idc_without_evo(self):
        self.assertEqual(extract_hints("IDC 25-07 screen blank").project, "idc")

    def test_project_idcevo_with_space(self):
        self.assertEqual(extract_hints("idc evo 26-07 navi crash").project, "idcevo")

    def test_project_app(self):
        self.assertEqual(extract_hints("App crash on startup").project, "app")

    def test_project_none_when_absent(self):
        self.assertIsNone(extract_hints("routing planning failed").project)

    # --- PU detection ---
    def test_pu_bare_slash(self):
        self.assertEqual(extract_hints("IDCEVO 26/07 routing failed").pu, "26-07")

    def test_pu_bare_dash(self):
        self.assertEqual(extract_hints("26-07 some issue").pu, "26-07")

    def test_pu_bare_dot(self):
        self.assertEqual(extract_hints("problem with 26.07").pu, "26-07")

    def test_pu_explicit_prefix(self):
        self.assertEqual(extract_hints("PU: 26-07 navi issue").pu, "26-07")

    def test_pu_explicit_prefix_chinese_colon(self):
        self.assertEqual(extract_hints("pu：26/07 crash").pu, "26-07")

    def test_pu_with_surrounding_punctuation(self):
        # Commas, semicolons, exclamation marks around the PU token
        self.assertEqual(extract_hints("IDCEVO, 26/07, routing failed!").pu, "26-07")

    def test_pu_with_brackets(self):
        self.assertEqual(extract_hints("[IDCEVO] (26/07) route planning failed").pu, "26-07")

    def test_pu_none_when_absent(self):
        self.assertIsNone(extract_hints("routing planning failed").pu)

    def test_pu_alpha_identifier(self):
        # "PU EE" style
        self.assertEqual(extract_hints("PU: EE CAN timeout").pu, "ee")

    # --- Combined noisy inputs ---
    def test_noisy_chinese_mixed(self):
        hints = extract_hints("IDCEVO，PU 26/07，导航路线规划失败！！")
        self.assertEqual(hints.project, "idcevo")
        self.assertEqual(hints.pu, "26-07")

    def test_noisy_parentheses_and_commas(self):
        hints = extract_hints("(IDC) [26-07] screen goes blank, then reboots")
        self.assertEqual(hints.project, "idc")
        self.assertEqual(hints.pu, "26-07")

    def test_extract_ecu_and_lead_model(self):
        hints = extract_hints("IDCEVO ECU: HU-H5 lead model: G60 route planning failed")
        self.assertEqual(hints.ecu, "hu-h5")
        self.assertEqual(hints.lead_model, "g60")


class TestDuplicateScoring(unittest.TestCase):
    """Verify project/PU hints influence score and ranking."""

    def test_search_boosts_project_and_pu_match_in_score(self):
        index = DuplicateIssueIndex()
        index._use_embeddings = True
        index._embedding_matrix = np.ones((2, 1), dtype=np.float32)
        index._meta = [
            {
                "ticket_id": "1",
                "name": "Routing planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            },
            {
                "ticket_id": "2",
                "name": "Routing planning failed",
                "project": None,
                "pu": None,
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            },
        ]
        index._embedding_search = lambda query_text: np.array([0.55, 0.55], dtype=np.float32)

        candidates = index.search(
            "IDCEVO 26/07 routing planning failed",
            hints=DuplicateSearchHints(project="idcevo", pu="26-07"),
            top_k=2,
        )

        self.assertEqual(candidates[0].ticket_id, "1")
        self.assertGreater(candidates[0].similarity, candidates[1].similarity)
        self.assertGreater(candidates[0].score_1_10, candidates[1].score_1_10)

    def test_search_boosts_ecu_and_lead_model_match_in_score(self):
        index = DuplicateIssueIndex()
        index._use_embeddings = True
        index._embedding_matrix = np.ones((3, 1), dtype=np.float32)
        index._meta = [
            {
                "ticket_id": "1",
                "name": "Route planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "ecu": "HU-H5",
                "lead_model": "G60",
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            },
            {
                "ticket_id": "2",
                "name": "Route planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "ecu": "HU-H5",
                "lead_model": None,
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            },
            {
                "ticket_id": "3",
                "name": "Route planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "ecu": None,
                "lead_model": None,
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            },
        ]
        index._embedding_search = lambda query_text: np.array([0.50, 0.50, 0.50], dtype=np.float32)

        candidates = index.search(
            "IDCEVO 26/07 ECU: HU-H5 lead model: G60 route planning failed",
            hints=DuplicateSearchHints(
                project="idcevo",
                pu="26-07",
                ecu="hu-h5",
                lead_model="g60",
            ),
            top_k=3,
        )

        self.assertEqual([candidate.ticket_id for candidate in candidates], ["1", "2", "3"])
        self.assertGreater(candidates[0].similarity, candidates[1].similarity)
        self.assertGreater(candidates[1].similarity, candidates[2].similarity)


class TestDuplicateIssueIndexRerankerIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = FeedbackStore(db_path=os.path.join(self.temp_dir.name, "feedback.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_search_with_metadata_uses_reranker_when_provided(self):
        index = DuplicateIssueIndex()
        index._use_embeddings = True
        index._embedding_matrix = np.ones((2, 1), dtype=np.float32)
        index._meta = [
            {
                "ticket_id": "1",
                "name": "Route planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "ecu": "HU-H5",
                "lead_model": "G60",
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            },
            {
                "ticket_id": "2",
                "name": "App crash",
                "project": "APP",
                "pu": "25-01",
                "ecu": "APP-ECU",
                "lead_model": "G20",
                "status_phase": "03-In Analysis",
                "description": "App crashes during startup.",
            },
        ]
        index._embedding_search = lambda query_text: np.array([0.50, 0.50], dtype=np.float32)
        self.store.submit_feedback("IDCEVO 26/07 routing failed", "1", "positive", user_id="alice")
        self.store.submit_feedback("IDCEVO 26/07 routing failed", "2", "negative", user_id="bob")
        reranker = ProgressiveReRanker(self.store)

        candidates, metadata = index.search_with_metadata(
            "IDCEVO 26/07 routing failed",
            hints=DuplicateSearchHints(project="idcevo", pu="26-07"),
            top_k=2,
            reranker=reranker,
        )

        self.assertEqual(candidates[0].ticket_id, "1")
        self.assertEqual(metadata["model_phase"], "click_boost")
        self.assertEqual(metadata["feedback_count"], 2)

    def test_search_with_metadata_returns_baseline_when_no_reranker(self):
        index = DuplicateIssueIndex()
        index._use_embeddings = True
        index._embedding_matrix = np.ones((1, 1), dtype=np.float32)
        index._meta = [
            {
                "ticket_id": "1",
                "name": "Route planning failed",
                "project": "IDCEVO",
                "pu": "26-07",
                "status_phase": "03-In Analysis",
                "description": "Route planning failed after destination input.",
            }
        ]
        index._embedding_search = lambda query_text: np.array([0.42], dtype=np.float32)

        candidates, metadata = index.search_with_metadata("IDCEVO 26/07 routing failed", top_k=1)

        self.assertEqual(candidates[0].ticket_id, "1")
        self.assertEqual(metadata["model_phase"], "baseline")
        self.assertEqual(metadata["feedback_count"], 0)


if __name__ == "__main__":
    unittest.main()