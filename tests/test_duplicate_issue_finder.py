import unittest
import os
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from duplicate_issue_finder import DuplicateIssueIndex, DuplicateSearchHints, extract_hints, get_or_build_index
from feedback_store import FeedbackStore
from progressive_reranker import ProgressiveReRanker


class _FakeEmbeddingCache:
    def __init__(self):
        self.items = []

    def get_many(self, ticket_ids, model_name):
        return {}

    def put_many(self, items, model_name):
        self.items.extend(items)


class _FakeEmbeddingModel:
    def encode(self, texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True):
        vectors = []
        for idx, _ in enumerate(texts):
            vectors.append(np.array([1.0 + idx, 0.5 + idx], dtype=np.float32))
        return np.vstack(vectors)


class _FakeChromaCollection:
    def __init__(self):
        self.upsert_calls = []
        self.query_calls = []

    def upsert(self, ids, embeddings, documents, metadatas):
        self.upsert_calls.append(
            {
                "ids": list(ids),
                "embeddings": list(embeddings),
                "documents": list(documents),
                "metadatas": list(metadatas),
            }
        )

    def query(self, query_embeddings, n_results, include=None, where=None):
        self.query_calls.append(
            {
                "query_embeddings": query_embeddings,
                "n_results": n_results,
                "include": include,
                "where": where,
            }
        )
        return {
            "ids": [["1", "2"]],
            "distances": [[0.02, 0.45]],
        }


class _FakeChromaClient:
    def __init__(self, collection, max_batch_size=None):
        self.collection = collection
        self.collection_name = None
        self._max_batch_size = max_batch_size

    def get_or_create_collection(self, name, metadata=None):
        self.collection_name = name
        return self.collection

    def get_max_batch_size(self):
        if self._max_batch_size is None:
            raise AttributeError("max batch size unavailable")
        return self._max_batch_size


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

    def test_build_from_df_uses_comments_in_default_text_fields(self):
        df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "Intermittent wake issue",
                    "description": "Wake pipeline unstable after cold boot.",
                    "comments": '[{"text":"Gateway wake CANoe trace timeout after KL15 on."}]',
                    "status_phase": "03-In Analysis",
                },
                {
                    "id": "2",
                    "name": "Trace collection issue",
                    "description": "CANoe trace timeout",
                    "comments": None,
                    "status_phase": "03-In Analysis",
                },
            ]
        )

        with patch("duplicate_issue_finder._get_st_model", return_value=None):
            index = DuplicateIssueIndex()
            index.build_from_df(df)

        candidates = index.search("Gateway wake CANoe trace timeout after KL15 on", top_k=2)

        self.assertEqual(candidates[0].ticket_id, "1")

    def test_build_from_df_prioritizes_signal_comments_and_truncates_comment_text(self):
        high_signal_comment = (
            "Root cause isolated in HU-H5 wake path after KL15 on. "
            "CANoe trace shows gateway timeout and routing handshake retry. "
        ) * 8
        low_signal_comment = "Thanks. Will check again tomorrow. " * 40

        df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "Wake issue",
                    "description": "General wake instability.",
                    "comments": [
                        {"text": low_signal_comment},
                        {"text": high_signal_comment},
                        {"text": "Need more logs."},
                    ],
                    "status_phase": "03-In Analysis",
                }
            ]
        )

        with patch("duplicate_issue_finder._get_st_model", return_value=None):
            index = DuplicateIssueIndex()
            index.build_from_df(df)

        document = index._documents[0]

        self.assertIn("Root cause isolated in HU-H5 wake path", document)
        self.assertNotIn(low_signal_comment[:120], document)
        self.assertLessEqual(len(document), 900)

    def test_build_from_df_uses_chroma_when_requested(self):
        df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "Route issue",
                    "description": "Gateway wake timeout during routing.",
                    "project": "IDCEVO",
                    "status_phase": "03-In Analysis",
                },
                {
                    "id": "2",
                    "name": "App issue",
                    "description": "UI crash on startup.",
                    "project": "APP",
                    "status_phase": "03-In Analysis",
                },
            ]
        )
        fake_collection = _FakeChromaCollection()
        fake_client = _FakeChromaClient(fake_collection)

        with patch("duplicate_issue_finder._get_st_model", return_value=_FakeEmbeddingModel()), \
             patch("duplicate_issue_finder._get_embedding_cache", return_value=_FakeEmbeddingCache()), \
             patch("duplicate_issue_finder._get_chroma_client", return_value=fake_client):
            index = DuplicateIssueIndex(vector_backend="chroma")
            index.build_from_df(df)
            candidates = index.search("gateway wake timeout", top_k=2)

        self.assertTrue(index._use_chroma)
        self.assertEqual(fake_collection.upsert_calls[0]["ids"], ["1", "2"])
        self.assertEqual(fake_collection.upsert_calls[0]["metadatas"][0]["project"], "IDCEVO")
        self.assertTrue(fake_collection.query_calls)
        self.assertEqual(candidates[0].ticket_id, "1")

    def test_build_from_df_falls_back_when_chroma_unavailable(self):
        df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "Route issue",
                    "description": "Gateway wake timeout during routing.",
                    "status_phase": "03-In Analysis",
                }
            ]
        )

        with patch("duplicate_issue_finder._get_st_model", return_value=_FakeEmbeddingModel()), \
             patch("duplicate_issue_finder._get_embedding_cache", return_value=_FakeEmbeddingCache()), \
             patch("duplicate_issue_finder._get_chroma_client", return_value=None):
            index = DuplicateIssueIndex(vector_backend="chroma")
            index.build_from_df(df)

        self.assertFalse(index._use_chroma)
        self.assertIsNotNone(index._embedding_matrix)

    def test_chroma_search_pushes_metadata_filters(self):
        df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "Route issue",
                    "description": "Gateway wake timeout during routing.",
                    "project": "IDCEVO",
                    "pu": "26-07",
                    "ecu": "HU-H5",
                    "lead_model": "G60",
                    "status_phase": "03-In Analysis",
                },
                {
                    "id": "2",
                    "name": "App issue",
                    "description": "UI crash on startup.",
                    "project": "APP",
                    "pu": "25-01",
                    "ecu": "APP-ECU",
                    "lead_model": "G20",
                    "status_phase": "03-In Analysis",
                },
            ]
        )
        fake_collection = _FakeChromaCollection()
        fake_client = _FakeChromaClient(fake_collection)

        with patch("duplicate_issue_finder._get_st_model", return_value=_FakeEmbeddingModel()), \
             patch("duplicate_issue_finder._get_embedding_cache", return_value=_FakeEmbeddingCache()), \
             patch("duplicate_issue_finder._get_chroma_client", return_value=fake_client):
            index = DuplicateIssueIndex(vector_backend="chroma")
            index.build_from_df(df)
            index.search(
                "IDCEVO 26/07 ECU: HU-H5 lead model: G60 gateway wake timeout",
                hints=DuplicateSearchHints(project="idcevo", pu="26-07", ecu="hu-h5", lead_model="g60"),
                top_k=2,
            )

        self.assertEqual(
            fake_collection.query_calls[0]["where"],
            {
                "$and": [
                    {"project_norm": "idcevo"},
                    {"pu_norm": "26-07"},
                    {"ecu_norm": "hu-h5"},
                    {"lead_model_norm": "g60"},
                ]
            },
        )

    def test_build_from_df_batches_chroma_upserts_to_client_limit(self):
        df = pd.DataFrame(
            [
                {
                    "id": str(i),
                    "name": f"Issue {i}",
                    "description": f"Description {i}",
                    "status_phase": "03-In Analysis",
                }
                for i in range(5)
            ]
        )
        fake_collection = _FakeChromaCollection()
        fake_client = _FakeChromaClient(fake_collection, max_batch_size=2)

        with patch("duplicate_issue_finder._get_st_model", return_value=_FakeEmbeddingModel()), \
             patch("duplicate_issue_finder._get_embedding_cache", return_value=_FakeEmbeddingCache()), \
             patch("duplicate_issue_finder._get_chroma_client", return_value=fake_client):
            index = DuplicateIssueIndex(vector_backend="chroma")
            index.build_from_df(df)

        self.assertTrue(index._use_chroma)
        self.assertEqual([len(call["ids"]) for call in fake_collection.upsert_calls], [2, 2, 1])

    def test_get_or_build_index_rebuilds_when_excluded_phase_prefixes_change(self):
        df = pd.DataFrame(
            [
                {
                    "id": "1",
                    "name": "Open issue",
                    "description": "Still active in analysis.",
                    "status_phase": "03-In Analysis",
                },
                {
                    "id": "2",
                    "name": "Closed issue",
                    "description": "Already closed.",
                    "status_phase": "09-Closed",
                },
            ]
        )
        cache_key = "phase-filter-rebuild"

        with patch("duplicate_issue_finder._get_st_model", return_value=None):
            first = get_or_build_index(cache_key, df, excluded_phase_prefixes=("09-",))
            second = get_or_build_index(cache_key, df, excluded_phase_prefixes=())

        self.assertEqual(first._row_count, 1)
        self.assertEqual(second._row_count, 2)


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