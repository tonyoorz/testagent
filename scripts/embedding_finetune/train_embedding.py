"""
Fine-tune bge-small-zh-v1.5 embedding model on duplicate-search feedback data.

This script supports two training strategies:
  1. MultipleNegativesRankingLoss (MNRL) — uses (anchor, positive) pairs;
     in-batch negatives provide implicit negatives. Best for small datasets.
  2. TripletLoss — uses (anchor, positive, negative) triplets;
     requires explicit negatives. Better when you have many 👎 signals.

Usage:
    # Strategy 1: MNRL (recommended, works with fewer data)
    python scripts/embedding_finetune/train_embedding.py --strategy mnrl

    # Strategy 2: TripletLoss
    python scripts/embedding_finetune/train_embedding.py --strategy triplet

    # Custom base model
    python scripts/embedding_finetune/train_embedding.py --base-model BAAI/bge-base-zh-v1.5

    # Full options
    python scripts/embedding_finetune/train_embedding.py \
        --data-dir scripts/embedding_finetune/training_data \
        --output-dir models/bge-small-zh-finetuned \
        --strategy mnrl \
        --epochs 5 \
        --batch-size 16 \
        --lr 2e-5 \
        --warmup-ratio 0.1

Requirements (install on GPU machine):
    pip install sentence-transformers>=3.0.0 torch>=2.0
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DATA_DIR = str(PROJECT_ROOT / "scripts" / "embedding_finetune" / "training_data")
DEFAULT_OUTPUT_DIR = str(PROJECT_ROOT / "models" / "bge-small-zh-finetuned")
DEFAULT_BASE_MODEL = "BAAI/bge-small-zh-v1.5"


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def train_mnrl(
    base_model: str,
    data_dir: str,
    output_dir: str,
    epochs: int = 5,
    batch_size: int = 16,
    lr: float = 2e-5,
    warmup_ratio: float = 0.1,
    eval_data_path: Optional[str] = None,
):
    """
    Train with MultipleNegativesRankingLoss.
    Uses (anchor, positive) pairs — other positives in the same batch
    serve as in-batch negatives. Very data-efficient.
    """
    from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
    from torch.utils.data import DataLoader

    print(f"[MNRL] Loading base model: {base_model}")
    model = SentenceTransformer(base_model)

    # Load pairs
    pairs_path = os.path.join(data_dir, "train_pairs.jsonl")
    raw_pairs = load_jsonl(pairs_path)
    print(f"[MNRL] Loaded {len(raw_pairs)} training pairs")

    if len(raw_pairs) < 10:
        print("[ERROR] Too few training pairs (< 10). Collect more feedback first.")
        return

    # Build InputExamples
    # For bge models: prepend "查询: " to queries for better performance
    train_examples = []
    for p in raw_pairs:
        train_examples.append(InputExample(
            texts=[p["anchor"], p["positive"]]
        ))

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)

    # Loss: MNRL with cosine similarity
    train_loss = losses.MultipleNegativesRankingLoss(model=model)

    # Evaluator (optional)
    evaluator = None
    if eval_data_path and os.path.exists(eval_data_path):
        evaluator = _build_ir_evaluator(eval_data_path, model)

    # Calculate warmup steps
    total_steps = len(train_dataloader) * epochs
    warmup_steps = int(total_steps * warmup_ratio)
    print(f"[MNRL] Training: {epochs} epochs, {len(train_dataloader)} steps/epoch, "
          f"warmup={warmup_steps}, lr={lr}")

    # Train
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": lr},
        output_path=output_dir,
        show_progress_bar=True,
        evaluator=evaluator,
        evaluation_steps=max(1, len(train_dataloader) // 2),  # eval 2x per epoch
        save_best_model=True if evaluator else False,
    )

    print(f"\n[MNRL] Model saved to: {output_dir}")
    _save_training_meta(output_dir, {
        "strategy": "mnrl",
        "base_model": base_model,
        "train_pairs": len(raw_pairs),
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
    })


def train_triplet(
    base_model: str,
    data_dir: str,
    output_dir: str,
    epochs: int = 5,
    batch_size: int = 16,
    lr: float = 2e-5,
    warmup_ratio: float = 0.1,
    margin: float = 0.3,
    eval_data_path: Optional[str] = None,
):
    """
    Train with TripletLoss.
    Uses (anchor, positive, negative) triplets — requires explicit negative examples.
    """
    from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
    from torch.utils.data import DataLoader

    print(f"[Triplet] Loading base model: {base_model}")
    model = SentenceTransformer(base_model)

    # Load triplets
    triplets_path = os.path.join(data_dir, "train_triplets.jsonl")
    raw_triplets = load_jsonl(triplets_path)
    print(f"[Triplet] Loaded {len(raw_triplets)} training triplets")

    if len(raw_triplets) < 10:
        print("[ERROR] Too few triplets (< 10). Need more positive+negative feedback.")
        return

    train_examples = []
    for t in raw_triplets:
        train_examples.append(InputExample(
            texts=[t["anchor"], t["positive"], t["negative"]]
        ))

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)

    # Loss: TripletLoss with cosine distance
    train_loss = losses.TripletLoss(
        model=model,
        distance_metric=losses.TripletDistanceMetric.COSINE,
        triplet_margin=margin,
    )

    evaluator = None
    if eval_data_path and os.path.exists(eval_data_path):
        evaluator = _build_ir_evaluator(eval_data_path, model)

    total_steps = len(train_dataloader) * epochs
    warmup_steps = int(total_steps * warmup_ratio)
    print(f"[Triplet] Training: {epochs} epochs, {len(train_dataloader)} steps/epoch, "
          f"warmup={warmup_steps}, lr={lr}, margin={margin}")

    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": lr},
        output_path=output_dir,
        show_progress_bar=True,
        evaluator=evaluator,
        evaluation_steps=max(1, len(train_dataloader) // 2),
        save_best_model=True if evaluator else False,
    )

    print(f"\n[Triplet] Model saved to: {output_dir}")
    _save_training_meta(output_dir, {
        "strategy": "triplet",
        "base_model": base_model,
        "train_triplets": len(raw_triplets),
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "margin": margin,
    })


def _build_ir_evaluator(eval_data_path: str, model):
    """Build InformationRetrievalEvaluator from eval_set.json."""
    from sentence_transformers.evaluation import InformationRetrievalEvaluator

    with open(eval_data_path, "r", encoding="utf-8") as f:
        eval_data = json.load(f)

    queries = eval_data.get("queries", {})
    corpus = eval_data.get("corpus", {})
    relevant_docs = eval_data.get("relevant_docs", {})

    if not queries or not relevant_docs:
        print("[WARN] Eval set empty, skipping evaluator")
        return None

    # Convert relevance values to int
    for qid in relevant_docs:
        relevant_docs[qid] = {did: int(v) for did, v in relevant_docs[qid].items()}

    evaluator = InformationRetrievalEvaluator(
        queries=queries,
        corpus=corpus,
        relevant_docs=relevant_docs,
        name="duplicate-search-eval",
        show_progress_bar=False,
        mrr_at_k=[5, 10, 20],
        ndcg_at_k=[5, 10, 20],
        accuracy_at_k=[1, 3, 5, 10],
        precision_recall_at_k=[5, 10],
        map_at_k=[10],
    )
    print(f"[Eval] Built evaluator: {len(queries)} queries, {len(corpus)} docs")
    return evaluator


def _save_training_meta(output_dir: str, meta: dict):
    meta_path = os.path.join(output_dir, "finetune_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, ensure_ascii=False, fp=f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Fine-tune embedding model for duplicate search")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL, help="Base model name or path")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Training data directory")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output model directory")
    parser.add_argument("--strategy", choices=["mnrl", "triplet"], default="mnrl",
                        help="Training strategy: mnrl (pairs, recommended) or triplet")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--margin", type=float, default=0.3, help="Triplet loss margin (only for triplet strategy)")
    args = parser.parse_args()

    eval_path = os.path.join(args.data_dir, "eval_set.json")

    if args.strategy == "mnrl":
        train_mnrl(
            base_model=args.base_model,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            warmup_ratio=args.warmup_ratio,
            eval_data_path=eval_path,
        )
    elif args.strategy == "triplet":
        train_triplet(
            base_model=args.base_model,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            warmup_ratio=args.warmup_ratio,
            margin=args.margin,
            eval_data_path=eval_path,
        )


if __name__ == "__main__":
    main()
