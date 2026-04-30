"""
Reusable training utilities extracted from train_embedding.py.

Provides ``train_embedding_model`` — a single function that can be imported
by ``auto_train_pipeline.py`` (no subprocess fork needed).
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BASE_MODEL = "BAAI/bge-small-zh-v1.5"


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def train_embedding_model(
    base_model: str = DEFAULT_BASE_MODEL,
    train_data_dir: str = "",
    output_dir: str = "",
    strategy: str = "mnrl",
    epochs: int = 5,
    batch_size: int = 16,
    lr: float = 2e-5,
    warmup_ratio: float = 0.1,
    margin: float = 0.3,
    device: str = "cpu",
    eval_data_path: Optional[str] = None,
    extra_triplet_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Train an embedding model and return a metrics dict.

    Parameters
    ----------
    base_model : str
        HuggingFace model id or local path.
    train_data_dir : str
        Directory containing ``train_pairs.jsonl`` (and optionally
        ``train_triplets.jsonl``).
    output_dir : str
        Where to save the fine-tuned model.
    strategy : str
        ``"mnrl"`` (default) or ``"triplet"`` or ``"hybrid"``.
    epochs, batch_size, lr, warmup_ratio, margin, device :
        Standard training hyper-params.
    eval_data_path : str or None
        Optional path to ``eval_set.json`` for InformationRetrievalEvaluator.
    extra_triplet_path : str or None
        If provided *and* strategy is ``"hybrid"``, also train with
        TripletLoss on this file after the MNRL phase.

    Returns
    -------
    dict
        ``{"strategy", "train_pairs", "train_triplets", "epochs",
          "batch_size", "lr", "final_loss", "ndcg": ..., "model_path"}``
    """
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader

    metrics: Dict[str, Any] = {
        "strategy": strategy,
        "train_pairs": 0,
        "train_triplets": 0,
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "final_loss": None,
        "ndcg": None,
        "model_path": output_dir,
    }

    print(f"[train_utils] Loading base model: {base_model}")
    model = SentenceTransformer(base_model, device=device)

    # ── Load data ──────────────────────────────────────────────────
    pairs_path = os.path.join(train_data_dir, "train_pairs.jsonl")
    triplets_path = os.path.join(train_data_dir, "train_triplets.jsonl")

    raw_pairs = load_jsonl(pairs_path) if os.path.exists(pairs_path) else []
    raw_triplets = load_jsonl(triplets_path) if os.path.exists(triplets_path) else []
    if extra_triplet_path and os.path.exists(extra_triplet_path):
        raw_triplets.extend(load_jsonl(extra_triplet_path))

    metrics["train_pairs"] = len(raw_pairs)
    metrics["train_triplets"] = len(raw_triplets)

    # ── Decide loss(es) ────────────────────────────────────────────
    train_objectives: List[tuple] = []

    if strategy in ("mnrl", "hybrid") and raw_pairs:
        examples = [InputExample(texts=[p["anchor"], p["positive"]]) for p in raw_pairs]
        dl = DataLoader(examples, shuffle=True, batch_size=batch_size)
        loss = losses.MultipleNegativesRankingLoss(model=model)
        train_objectives.append((dl, loss))
        print(f"[train_utils] MNRL: {len(examples)} pairs")

    if strategy in ("triplet", "hybrid") and raw_triplets:
        examples = [
            InputExample(texts=[t["anchor"], t["positive"], t["negative"]])
            for t in raw_triplets
        ]
        dl = DataLoader(examples, shuffle=True, batch_size=batch_size)
        loss = losses.TripletLoss(
            model=model,
            distance_metric=losses.TripletDistanceMetric.COSINE,
            triplet_margin=margin,
        )
        train_objectives.append((dl, loss))
        print(f"[train_utils] Triplet: {len(examples)} triplets")

    if not train_objectives:
        print("[train_utils] No training data available, skipping.")
        return metrics

    # ── Eval ───────────────────────────────────────────────────────
    evaluator = None
    if eval_data_path and os.path.exists(eval_data_path):
        evaluator = _build_ir_evaluator(eval_data_path, model)

    # ── Train ──────────────────────────────────────────────────────
    total_steps = sum(len(dl) for dl, _ in train_objectives) * epochs
    warmup_steps = int(total_steps * warmup_ratio)

    model.fit(
        train_objectives=train_objectives,
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": lr},
        output_path=output_dir,
        show_progress_bar=False,
        evaluator=evaluator,
        evaluation_steps=max(1, total_steps // 2) if evaluator else 0,
        save_best_model=bool(evaluator),
    )

    # ── Eval metrics ───────────────────────────────────────────────
    if evaluator is not None:
        try:
            score = model.evaluate(evaluator)
            metrics["ndcg"] = score
        except Exception:
            pass

    _save_training_meta(output_dir, metrics)
    print(f"[train_utils] Model saved to: {output_dir}")
    return metrics


# ---------------------------------------------------------------------------
# Helpers (same as train_embedding.py)
# ---------------------------------------------------------------------------

def _build_ir_evaluator(eval_data_path: str, model):
    from sentence_transformers.evaluation import InformationRetrievalEvaluator

    with open(eval_data_path, "r", encoding="utf-8") as f:
        eval_data = json.load(f)

    queries = eval_data.get("queries", {})
    corpus = eval_data.get("corpus", {})
    relevant_docs = eval_data.get("relevant_docs", {})

    if not queries or not relevant_docs:
        return None

    for qid in relevant_docs:
        relevant_docs[qid] = {did: int(v) for did, v in relevant_docs[qid].items()}

    return InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="duplicate-search-eval",
        show_progress_bar=False,
        ndcg_at_k=[5, 10],
    )


def _save_training_meta(output_dir: str, meta: dict):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "finetune_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, ensure_ascii=False, fp=f, indent=2)
