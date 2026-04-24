import unittest

import numpy as np

from duplicate_issue_finder import DuplicateIssueIndex, DuplicateSearchHints, extract_hints


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


if __name__ == "__main__":
    unittest.main()