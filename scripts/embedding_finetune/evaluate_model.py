"""
Evaluate fine-tuned model vs base model on the same eval set.

Usage:
    python scripts/embedding_finetune/evaluate_model.py
    python scripts/embedding_finetune/evaluate_model.py \
        --base-model BAAI/bge-small-zh-v1.5 \
        --finetuned-model models/bge-small-zh-finetuned \
        --eval-data scripts/embedding_finetune/training_data/eval_set.json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BASE_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_FINETUNED = str(PROJECT_ROOT / "models" / "bge-small-zh-finetuned")
DEFAULT_EVAL_DATA = str(PROJECT_ROOT / "scripts" / "embedding_finetune" / "training_data" / "eval_set.json")


def evaluate_model(model_name_or_path: str, eval_data: dict, label: str) -> dict:
    """Run IR evaluation on a single model, return metrics dict."""
    from sentence_transformers import SentenceTransformer
    import numpy as np

    print(f"\n{'=' * 60}")
    print(f"Evaluating: {label}")
    print(f"Model: {model_name_or_path}")
    print(f"{'=' * 60}")

    model = SentenceTransformer(model_name_or_path)

    queries = eval_data["queries"]      # {qid: text}
    corpus = eval_data["corpus"]        # {doc_id: text}
    relevant_docs = eval_data["relevant_docs"]  # {qid: {doc_id: relevance}}

    if not queries or not relevant_docs:
        print("[WARN] Empty eval set")
        return {}

    # Encode all queries and documents
    qids = list(queries.keys())
    q_texts = [queries[qid] for qid in qids]
    doc_ids = list(corpus.keys())
    doc_texts = [corpus[did] for did in doc_ids]

    print(f"Encoding {len(q_texts)} queries + {len(doc_texts)} documents...")
    q_embeddings = model.encode(q_texts, normalize_embeddings=True, show_progress_bar=False)
    d_embeddings = model.encode(doc_texts, normalize_embeddings=True, show_progress_bar=False)

    # Compute similarity matrix
    sim_matrix = np.dot(q_embeddings, d_embeddings.T)  # (num_queries, num_docs)

    # Compute metrics
    metrics = {}
    mrr_scores = []
    ndcg_scores = {5: [], 10: [], 20: []}
    hit_scores = {1: [], 3: [], 5: [], 10: []}

    for i, qid in enumerate(qids):
        if qid not in relevant_docs:
            continue

        rel = relevant_docs[qid]  # {doc_id: relevance}
        sims = sim_matrix[i]

        # Rank documents by similarity
        ranked_indices = np.argsort(-sims)
        ranked_doc_ids = [doc_ids[idx] for idx in ranked_indices]

        # MRR
        for rank, did in enumerate(ranked_doc_ids, 1):
            if did in rel and int(rel[did]) > 0:
                mrr_scores.append(1.0 / rank)
                break
        else:
            mrr_scores.append(0.0)

        # Hit@K
        for k in hit_scores:
            top_k_docs = set(ranked_doc_ids[:k])
            hit = any(did in rel and int(rel[did]) > 0 for did in top_k_docs)
            hit_scores[k].append(1.0 if hit else 0.0)

        # NDCG@K
        for k in ndcg_scores:
            dcg = 0.0
            for rank_idx in range(min(k, len(ranked_doc_ids))):
                did = ranked_doc_ids[rank_idx]
                if did in rel:
                    dcg += int(rel[did]) / np.log2(rank_idx + 2)

            # Ideal DCG
            ideal_rels = sorted([int(v) for v in rel.values()], reverse=True)
            idcg = 0.0
            for rank_idx in range(min(k, len(ideal_rels))):
                idcg += ideal_rels[rank_idx] / np.log2(rank_idx + 2)

            ndcg_scores[k].append(dcg / idcg if idcg > 0 else 0.0)

    metrics["MRR"] = float(np.mean(mrr_scores)) if mrr_scores else 0.0
    for k, scores in hit_scores.items():
        metrics[f"Hit@{k}"] = float(np.mean(scores)) if scores else 0.0
    for k, scores in ndcg_scores.items():
        metrics[f"NDCG@{k}"] = float(np.mean(scores)) if scores else 0.0

    # Print results
    print(f"\nResults ({len(qids)} queries):")
    for name, value in sorted(metrics.items()):
        print(f"  {name:12s}: {value:.4f}")

    return metrics


def compare_models(base_metrics: dict, ft_metrics: dict):
    """Print side-by-side comparison."""
    print(f"\n{'=' * 60}")
    print("COMPARISON: Base vs Fine-tuned")
    print(f"{'=' * 60}")
    print(f"{'Metric':<12s} {'Base':>10s} {'Fine-tuned':>10s} {'Delta':>10s} {'Change':>10s}")
    print("-" * 54)

    all_improved = True
    for name in sorted(set(list(base_metrics.keys()) + list(ft_metrics.keys()))):
        base_val = base_metrics.get(name, 0.0)
        ft_val = ft_metrics.get(name, 0.0)
        delta = ft_val - base_val
        pct = (delta / base_val * 100) if base_val > 0 else 0.0

        indicator = "✅" if delta > 0 else ("⚠️" if delta < 0 else "  ")
        if delta < 0:
            all_improved = False
        print(f"  {name:<12s} {base_val:>8.4f}   {ft_val:>8.4f}   {delta:>+8.4f}  {pct:>+7.1f}% {indicator}")

    print()
    if all_improved:
        print("✅ Fine-tuned model improves on ALL metrics. Safe to deploy.")
    else:
        print("⚠️  Some metrics regressed. Review before deploying.")


def main():
    parser = argparse.ArgumentParser(description="Evaluate fine-tuned vs base embedding model")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--finetuned-model", default=DEFAULT_FINETUNED)
    parser.add_argument("--eval-data", default=DEFAULT_EVAL_DATA)
    args = parser.parse_args()

    if not os.path.exists(args.eval_data):
        print(f"[ERROR] Eval data not found: {args.eval_data}")
        print("Run export_training_data.py first to generate eval set.")
        return

    with open(args.eval_data, "r", encoding="utf-8") as f:
        eval_data = json.load(f)

    if not eval_data.get("queries") or not eval_data.get("relevant_docs"):
        print("[ERROR] Eval set is empty. Need more feedback data.")
        return

    base_metrics = evaluate_model(args.base_model, eval_data, "BASE MODEL")

    if os.path.exists(args.finetuned_model):
        ft_metrics = evaluate_model(args.finetuned_model, eval_data, "FINE-TUNED MODEL")
        compare_models(base_metrics, ft_metrics)
    else:
        print(f"\n[INFO] Fine-tuned model not found at {args.finetuned_model}")
        print("Run train_embedding.py first, then re-run this evaluation.")


if __name__ == "__main__":
    main()
