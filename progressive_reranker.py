"""
Progressive ReRanker for duplicate-issue search.

Two-phase design:
  Phase 1 — ClickBoost: statistical boost from historical click/feedback rates (always active)
  Phase 2 — FeatureReRanker: LogisticRegression with cross-validation guard (triggers at 50+ explicit labels)

The old ContrastiveAdapter has been removed — its value is covered by the LR
feature model, and true embedding fine-tuning (via train_embedding.py) is the
right upgrade path at scale.
"""

import logging
import math
import pickle
import re
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from feedback_store import FeedbackStore

try:
    from sklearn.linear_model import LogisticRegression
except Exception:  # pragma: no cover
    LogisticRegression = None

try:
    from sklearn.model_selection import cross_val_score
except Exception:  # pragma: no cover
    cross_val_score = None

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Model Safety Guard
# ---------------------------------------------------------------------------

class ModelSafetyGuard:
    """Prevent deploying a model that is worse than the current one."""

    def __init__(self, max_ndcg_regression: float = 0.05):
        self.max_ndcg_regression = max_ndcg_regression

    def should_deploy(
        self, old_metrics: Optional[Dict[str, Any]], new_metrics: Optional[Dict[str, Any]]
    ) -> bool:
        if not new_metrics:
            return False
        if not old_metrics:
            return True
        return float(new_metrics.get("ndcg", 0.0)) >= (
            float(old_metrics.get("ndcg", 0.0)) - self.max_ndcg_regression
        )


# ---------------------------------------------------------------------------
# Phase 1: Click Boost (always active)
# ---------------------------------------------------------------------------

class ClickBoostReRanker:
    MAX_ABS_BOOST = 0.075

    def __init__(self, feedback_store: FeedbackStore):
        self.feedback_store = feedback_store

    def score_candidates(self, candidates: Sequence[Any]) -> Dict[str, float]:
        ticket_ids = [getattr(candidate, "ticket_id", None) for candidate in candidates]
        stats = self.feedback_store.get_ticket_feedback_stats(ticket_ids)
        boosts: Dict[str, float] = {}
        for ticket_id, item in stats.items():
            positive_rate = _safe_float(item.get("weighted_positive_rate"), 0.0)
            raw_boost = (positive_rate - 0.5) * 0.15
            boosts[ticket_id] = max(-self.MAX_ABS_BOOST, min(self.MAX_ABS_BOOST, raw_boost))
        return boosts


# ---------------------------------------------------------------------------
# Phase 2: Feature ReRanker (LR with cross-validation)
# ---------------------------------------------------------------------------

class FeatureReRanker:
    MIN_TRAIN_SAMPLES = 30
    MIN_CV_FOLDS = 3
    CV_AUC_FLOOR = 0.6

    def __init__(self, feedback_store: FeedbackStore):
        self.feedback_store = feedback_store
        self.model = None
        self.metrics: Dict[str, Any] = {}

    @property
    def ready(self) -> bool:
        return self.model is not None

    def train(self, rows: Sequence[Dict[str, Any]], index: Any) -> bool:
        if LogisticRegression is None or not rows or index is None:
            return False
        meta_by_ticket = {
            str(meta.get("ticket_id")): meta
            for meta in getattr(index, "_meta", [])
            if meta.get("ticket_id")
        }
        xs: List[List[float]] = []
        ys: List[int] = []
        weights: List[float] = []
        for row in rows:
            meta = meta_by_ticket.get(str(row.get("ticket_id")))
            if not meta:
                continue
            feature_row = self.build_feature_row(
                str(row.get("query_text") or ""),
                meta,
                _safe_float(row.get("base_score"), 0.0),
                self.feedback_store.get_ticket_feedback_stats(
                    [meta.get("ticket_id")]
                ).get(meta.get("ticket_id"), {}),
                rank_pos=row.get("rank_pos"),
            )
            signal = str(row.get("signal") or "").lower()
            xs.append(feature_row)
            ys.append(0 if signal == "negative" else 1)
            # Implicit clicks get lower weight than explicit labels
            source = row.get("source", "explicit")
            if signal == "click":
                weights.append(0.3)
            elif source == "explicit":
                weights.append(1.0)
            else:
                weights.append(0.4)

        if len(xs) < self.MIN_TRAIN_SAMPLES or len(set(ys)) < 2:
            return False

        X = np.asarray(xs, dtype=np.float32)
        y = np.asarray(ys, dtype=np.int32)
        w = np.asarray(weights, dtype=np.float32)
        model = LogisticRegression(
            C=0.5,                    # stronger L2 regularisation
            class_weight="balanced",
            max_iter=200,
        )

        # Cross-validation gate: don't deploy if AUC < threshold
        if cross_val_score is not None and len(xs) >= 50:
            n_folds = min(5, max(self.MIN_CV_FOLDS, len(xs) // 20))
            try:
                cv_scores = cross_val_score(model, X, y, cv=n_folds, scoring="roc_auc")
                cv_auc = float(cv_scores.mean())
                if cv_auc < self.CV_AUC_FLOOR:
                    logger.warning(
                        "FeatureReRanker CV AUC=%.3f < %.3f, skipping deployment",
                        cv_auc, self.CV_AUC_FLOOR,
                    )
                    return False
                self.metrics["cv_auc"] = cv_auc
                self.metrics["cv_auc_std"] = float(cv_scores.std())
            except Exception as exc:
                logger.warning("Cross-validation failed: %s", exc)

        model.fit(X, y, sample_weight=w)
        self.model = model
        predictions = model.predict_proba(X)[:, 1]
        self.metrics.update({
            "ndcg": self._pseudo_ndcg(predictions, ys),
            "train_size": len(xs),
        })
        return True

    def build_feature_row(
        self,
        query_text: str,
        meta: Dict[str, Any],
        base_similarity: float,
        popularity_stats: Optional[Dict[str, Any]],
        rank_pos: Optional[int] = None,
    ) -> List[float]:
        from duplicate_issue_finder import extract_hints

        hints = extract_hints(query_text)
        project = str(meta.get("project") or "").lower()
        pu = str(meta.get("pu") or "").lower()
        ecu = str(meta.get("ecu") or "").lower()
        lead_model = str(meta.get("lead_model") or "").lower()
        overlap = _token_overlap(
            query_text,
            "\n".join(
                str(meta.get(key) or "")
                for key in ("name", "description", "project", "pu", "ecu", "lead_model")
            ),
        )
        popularity = popularity_stats or {}
        normalized_rank = 0.0 if rank_pos is None else min(1.0, max(0.0, float(rank_pos) / 50.0))
        return [
            float(base_similarity),                                           # 0
            1.0 if hints.project and hints.project in project else 0.0,       # 1
            1.0 if hints.pu and hints.pu in pu else 0.0,                     # 2
            1.0 if hints.ecu and hints.ecu in ecu else 0.0,                  # 3
            1.0 if hints.lead_model and hints.lead_model in lead_model else 0.0,  # 4
            overlap,                                                          # 5
            normalized_rank,                                                  # 6
            _safe_float(popularity.get("weighted_positive_rate"), 0.0),       # 7
            min(1.0, len(str(query_text or "")) / 120.0),                    # 8
        ]

    def score_candidates(
        self, query_text: str, candidates: Sequence[Any], index: Any
    ) -> Dict[str, float]:
        if not self.ready:
            return {}
        meta_by_ticket = {
            str(meta.get("ticket_id")): meta
            for meta in getattr(index, "_meta", [])
            if meta.get("ticket_id")
        }
        stats = self.feedback_store.get_ticket_feedback_stats(
            [getattr(candidate, "ticket_id", None) for candidate in candidates]
        )
        xs: List[List[float]] = []
        ticket_order: List[str] = []
        for rank_pos, candidate in enumerate(candidates):
            ticket_id = getattr(candidate, "ticket_id", None)
            meta = meta_by_ticket.get(str(ticket_id))
            if not ticket_id or not meta:
                continue
            xs.append(
                self.build_feature_row(
                    query_text,
                    meta,
                    _safe_float(getattr(candidate, "similarity", 0.0)),
                    stats.get(ticket_id),
                    rank_pos=rank_pos,
                )
            )
            ticket_order.append(ticket_id)
        if not xs:
            return {}
        probabilities = self.model.predict_proba(np.asarray(xs, dtype=np.float32))[:, 1]
        return {ticket_order[idx]: float(probabilities[idx]) for idx in range(len(ticket_order))}

    @staticmethod
    def _pseudo_ndcg(predictions: Sequence[float], labels: Sequence[int]) -> float:
        pairs = sorted(zip(predictions, labels), key=lambda item: item[0], reverse=True)
        ideal = sorted(labels, reverse=True)
        dcg = 0.0
        for rank, (_, label) in enumerate(pairs, start=1):
            dcg += float(label) / math.log2(rank + 1)
        idcg = 0.0
        for rank, label in enumerate(ideal, start=1):
            idcg += float(label) / math.log2(rank + 1)
        if idcg <= 0:
            return 0.0
        return dcg / idcg


# ---------------------------------------------------------------------------
# Progressive ReRanker (unified two-phase)
# ---------------------------------------------------------------------------

class ProgressiveReRanker:
    def __init__(self, feedback_store: Optional[FeedbackStore] = None):
        self.feedback_store = feedback_store or FeedbackStore()
        self.click_boost = ClickBoostReRanker(self.feedback_store)
        self.feature_reranker = FeatureReRanker(self.feedback_store)
        self.safety_guard = ModelSafetyGuard()
        self.model_phase = "click_boost"
        self.feedback_count = 0
        self._last_trained_feedback_count = 0

    @property
    def ready(self) -> bool:
        return True

    def refresh(self, index: Any = None) -> None:
        self.feedback_count = self.feedback_store.count_feedback()

        # Check LR readiness via the scheduler's quality checks
        readiness = self.feedback_store.scheduler.check_lr_readiness()
        target_phase = "feature" if readiness["ready"] else "click_boost"
        self.model_phase = "click_boost"

        if target_phase == "feature" and self.feedback_store.scheduler.should_retrain(
            self.feedback_count, self._last_trained_feedback_count
        ):
            examples = self.feedback_store.get_training_examples()
            trained = self.feature_reranker.train(examples, index=index)
            if trained:
                latest = self.feedback_store.load_latest_model_snapshot()
                metrics = dict(self.feature_reranker.metrics)
                if self.safety_guard.should_deploy(
                    latest["metrics"] if latest else None, metrics
                ):
                    self.feedback_store.save_model_snapshot(
                        phase="feature",
                        model_blob=pickle.dumps(self.feature_reranker.model),
                        metrics=metrics,
                        feedback_count=self.feedback_count,
                    )
                    self.model_phase = "feature"
                    self._last_trained_feedback_count = self.feedback_count
                else:
                    logger.warning("New feature model failed safety check, keeping previous")
            elif self.feature_reranker.ready:
                self.model_phase = "feature"
        elif self.feature_reranker.ready:
            self.model_phase = "feature"

    def rerank(
        self,
        query_text: str,
        candidates: Sequence[Any],
        hints: Optional[Any] = None,
        index: Any = None,
        top_k: Optional[int] = None,
    ) -> List[Any]:
        self.refresh(index=index)
        click_boost_scores = self.click_boost.score_candidates(candidates)
        feature_scores: Dict[str, float] = {}
        if self.model_phase == "feature" and index is not None:
            feature_scores = self.feature_reranker.score_candidates(
                query_text, candidates, index=index
            )

        reranked: List[Tuple[float, Any]] = []
        for candidate in candidates:
            ticket_id = getattr(candidate, "ticket_id", None)
            base_score = _safe_float(getattr(candidate, "similarity", 0.0), 0.0)
            boosted_score = max(0.0, min(1.0, base_score + click_boost_scores.get(ticket_id, 0.0)))
            final_score = boosted_score
            if ticket_id in feature_scores:
                final_score = (0.6 * feature_scores[ticket_id]) + (0.4 * boosted_score)
            reranked.append((final_score, _clone_candidate(candidate, final_score)))

        reranked.sort(key=lambda item: item[0], reverse=True)
        limit = len(reranked) if top_k is None else max(1, int(top_k))
        return [item[1] for item in reranked[:limit]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RERANKER_CACHE: Dict[str, ProgressiveReRanker] = {}


def get_progressive_reranker(db_path: Optional[str] = None) -> ProgressiveReRanker:
    store = FeedbackStore(db_path=db_path) if db_path else FeedbackStore()
    cache_key = store.db_path
    reranker = _RERANKER_CACHE.get(cache_key)
    if reranker is None:
        reranker = ProgressiveReRanker(store)
        _RERANKER_CACHE[cache_key] = reranker
    return reranker


def _clone_candidate(candidate: Any, score: float) -> Any:
    if hasattr(candidate, "__dataclass_fields__"):
        from duplicate_issue_finder import _to_score_1_10
        return replace(candidate, similarity=float(score), score_1_10=_to_score_1_10(score))
    if isinstance(candidate, dict):
        updated = dict(candidate)
        updated["similarity"] = float(score)
        return updated
    setattr(candidate, "similarity", float(score))
    return candidate


def _token_overlap(query_text: str, candidate_text: str) -> float:
    query_tokens = set(re.findall(r"[a-z0-9_./-]{2,}", str(query_text or "").lower()))
    candidate_tokens = set(re.findall(r"[a-z0-9_./-]{2,}", str(candidate_text or "").lower()))
    if not query_tokens or not candidate_tokens:
        return 0.0
    intersection = len(query_tokens & candidate_tokens)
    union = len(query_tokens | candidate_tokens)
    return float(intersection) / float(max(1, union))


__all__ = [
    "ClickBoostReRanker",
    "FeatureReRanker",
    "ModelSafetyGuard",
    "ProgressiveReRanker",
    "get_progressive_reranker",
]
