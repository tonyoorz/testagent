"""
Export training data from feedback_records → sentence-transformers format.

Usage:
    python scripts/embedding_finetune/export_training_data.py
    python scripts/embedding_finetune/export_training_data.py --feedback-db database/ticket_embeddings.db --defect-db database/local_data_rebuilt.db --out training_data
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_FEEDBACK_DB = str(PROJECT_ROOT / "database" / "ticket_embeddings.db")
DEFAULT_DEFECT_DB = str(PROJECT_ROOT / "database" / "local_data_rebuilt.db")
DEFAULT_OUTPUT_DIR = str(PROJECT_ROOT / "scripts" / "embedding_finetune" / "training_data")

# Fields used in duplicate_issue_finder.py _build_document()
TEXT_FIELDS = ("name", "description", "project", "pu", "ecu", "top_aida", "fv", "team", "fvp", "lead_model")


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _build_ticket_text(row: dict) -> str:
    """Build the same document text as DuplicateIssueIndex._build_document()."""
    parts = []
    for f in TEXT_FIELDS:
        v = _normalize(row.get(f, ""))
        if v:
            parts.append(v)
    return "\n".join(parts)


def load_ticket_texts(defect_db: str) -> Dict[str, str]:
    """Load ticket id → document text from defect database."""
    if not os.path.exists(defect_db):
        print(f"[WARN] Defect DB not found: {defect_db}")
        return {}

    conn = sqlite3.connect(defect_db)
    conn.row_factory = sqlite3.Row

    # Try octane_defects table first (main table in octane_db.py)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]

    ticket_texts: Dict[str, str] = {}
    target_table = None
    for t in ["octane_defects", "defects", "octane_defect"]:
        if t in tables:
            target_table = t
            break

    if not target_table:
        print(f"[WARN] No defect table found in {defect_db}. Available: {tables[:10]}")
        conn.close()
        return {}

    # Get column names
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({target_table})").fetchall()]
    print(f"[INFO] Loading tickets from {target_table} ({len(cols)} columns)")

    rows = conn.execute(f"SELECT * FROM {target_table}").fetchall()
    for r in rows:
        row_dict = dict(r)
        # Support both "id" and "defect_id" column names
        tid = str(row_dict.get("id") or row_dict.get("defect_id") or "").strip()
        if not tid:
            continue
        text = _build_ticket_text(row_dict)
        if text:
            ticket_texts[tid] = text

    conn.close()
    print(f"[INFO] Loaded {len(ticket_texts)} ticket documents")
    return ticket_texts


def load_feedback(feedback_db: str) -> List[Dict[str, Any]]:
    """Load all valid feedback records."""
    if not os.path.exists(feedback_db):
        print(f"[ERROR] Feedback DB not found: {feedback_db}")
        return []

    conn = sqlite3.connect(feedback_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT query_text, query_hash, ticket_id, signal, base_score, rank_pos
        FROM feedback_records
        WHERE is_valid = 1
        ORDER BY created_at ASC
    """).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    print(f"[INFO] Loaded {len(result)} feedback records")
    return result


def build_query_groups(feedback: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Group feedback by query_hash.
    Returns {query_hash: {"query": str, "positives": set, "negatives": set, "clicks": set}}
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for fb in feedback:
        qhash = fb["query_hash"]
        if qhash not in groups:
            groups[qhash] = {
                "query": fb["query_text"],
                "positives": set(),
                "negatives": set(),
                "clicks": set(),
            }
        tid = str(fb["ticket_id"]).strip()
        signal = fb["signal"]
        if signal == "positive":
            groups[qhash]["positives"].add(tid)
            # If previously in negatives, remove (user corrected)
            groups[qhash]["negatives"].discard(tid)
        elif signal == "negative":
            groups[qhash]["negatives"].add(tid)
            groups[qhash]["positives"].discard(tid)
        elif signal == "click":
            groups[qhash]["clicks"].add(tid)
    return groups


def export_triplets(
    groups: Dict[str, Dict[str, Any]],
    ticket_texts: Dict[str, str],
) -> List[Dict[str, str]]:
    """
    Generate (anchor, positive, negative) triplets for TripletLoss / MultipleNegativesRankingLoss.

    Priority for negatives:
    1. Explicit negatives (user marked 👎)
    2. Click-only (user clicked but didn't mark positive → weak negative)
    """
    triplets = []

    for qhash, group in groups.items():
        query = group["query"]
        positives = group["positives"]
        negatives = group["negatives"]
        clicks = group["clicks"]

        # Resolve ticket texts
        pos_texts = {tid: ticket_texts[tid] for tid in positives if tid in ticket_texts}
        neg_texts = {tid: ticket_texts[tid] for tid in negatives if tid in ticket_texts}

        if not pos_texts:
            continue

        # Build triplets: each (query, positive, negative)
        for pos_id, pos_text in pos_texts.items():
            # Hard negatives (explicit 👎)
            for neg_id, neg_text in neg_texts.items():
                triplets.append({
                    "anchor": query,
                    "positive": pos_text,
                    "negative": neg_text,
                    "pos_ticket_id": pos_id,
                    "neg_ticket_id": neg_id,
                    "negative_type": "explicit",
                })

    return triplets


def export_pairs(
    groups: Dict[str, Dict[str, Any]],
    ticket_texts: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Generate (anchor, positive) pairs for MultipleNegativesRankingLoss.
    In-batch negatives make this very data-efficient — often better than explicit triplets.
    """
    pairs = []

    for qhash, group in groups.items():
        query = group["query"]
        positives = group["positives"]

        for pos_id in positives:
            if pos_id in ticket_texts:
                pairs.append({
                    "anchor": query,
                    "positive": ticket_texts[pos_id],
                    "pos_ticket_id": pos_id,
                })

    return pairs


def export_eval_set(
    groups: Dict[str, Dict[str, Any]],
    ticket_texts: Dict[str, str],
    eval_ratio: float = 0.15,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Split query groups into train/eval.
    Eval set uses InformationRetrievalEvaluator format:
    - queries: {qid: query_text}
    - corpus: {doc_id: doc_text}
    - relevant_docs: {qid: {doc_id: relevance}}
    """
    import random
    random.seed(42)

    all_hashes = list(groups.keys())
    random.shuffle(all_hashes)

    split_idx = max(1, int(len(all_hashes) * (1 - eval_ratio)))
    train_hashes = set(all_hashes[:split_idx])
    eval_hashes = set(all_hashes[split_idx:])

    # Build eval set in IR evaluator format
    queries = {}
    corpus = {}
    relevant_docs = {}

    for qhash in eval_hashes:
        g = groups[qhash]
        qid = qhash
        queries[qid] = g["query"]

        relevant = {}
        for tid in g["positives"]:
            if tid in ticket_texts:
                corpus[tid] = ticket_texts[tid]
                relevant[tid] = 1  # relevant
        for tid in g["negatives"]:
            if tid in ticket_texts:
                corpus[tid] = ticket_texts[tid]
                # negatives not added to relevant_docs (implicit 0)

        if relevant:
            relevant_docs[qid] = relevant

    eval_data = {
        "queries": queries,
        "corpus": corpus,
        "relevant_docs": relevant_docs,
    }

    return train_hashes, eval_data


def print_stats(groups, triplets, pairs, ticket_texts):
    """Print summary statistics."""
    total_pos = sum(len(g["positives"]) for g in groups.values())
    total_neg = sum(len(g["negatives"]) for g in groups.values())
    total_click = sum(len(g["clicks"]) for g in groups.values())
    covered_pos = sum(
        1 for g in groups.values()
        for tid in g["positives"] if tid in ticket_texts
    )
    covered_neg = sum(
        1 for g in groups.values()
        for tid in g["negatives"] if tid in ticket_texts
    )

    print("\n" + "=" * 60)
    print("TRAINING DATA SUMMARY")
    print("=" * 60)
    print(f"Unique queries:          {len(groups)}")
    print(f"Positive signals:        {total_pos} ({covered_pos} with ticket text)")
    print(f"Negative signals:        {total_neg} ({covered_neg} with ticket text)")
    print(f"Click signals:           {total_click}")
    print(f"Triplets generated:      {len(triplets)}")
    print(f"Pairs generated:         {len(pairs)}")
    print(f"Ticket corpus size:      {len(ticket_texts)}")
    print("=" * 60)

    # Readiness check
    if len(pairs) < 50:
        print("\n⚠️  WARNING: < 50 pairs. Fine-tuning may not be effective yet.")
        print("   Recommendation: Continue collecting feedback until 200+ pairs.")
    elif len(pairs) < 200:
        print(f"\n⚡ READY for initial fine-tuning ({len(pairs)} pairs)")
        print("   Expected: modest improvement. Keep collecting for better results.")
    else:
        print(f"\n✅ GOOD dataset size ({len(pairs)} pairs)")
        print("   Expected: meaningful improvement over base model.")


def main():
    parser = argparse.ArgumentParser(description="Export training data for embedding fine-tuning")
    parser.add_argument("--feedback-db", default=DEFAULT_FEEDBACK_DB, help="Path to feedback SQLite DB")
    parser.add_argument("--defect-db", default=DEFAULT_DEFECT_DB, help="Path to defect data DB")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # 1. Load data
    print("[Step 1/4] Loading feedback records...")
    feedback = load_feedback(args.feedback_db)
    if not feedback:
        print("[ERROR] No feedback data found. Exiting.")
        return

    print("[Step 2/4] Loading ticket documents...")
    ticket_texts = load_ticket_texts(args.defect_db)

    # 2. Group by query
    groups = build_query_groups(feedback)

    # 3. Generate training data
    print("[Step 3/4] Generating training data...")
    triplets = export_triplets(groups, ticket_texts)
    pairs = export_pairs(groups, ticket_texts)

    # 4. Train/eval split
    print("[Step 4/4] Splitting train/eval...")
    train_hashes, eval_data = export_eval_set(groups, ticket_texts)

    # Filter triplets/pairs to train set only
    train_groups = {h: groups[h] for h in train_hashes if h in groups}
    train_triplets = export_triplets(train_groups, ticket_texts)
    train_pairs = export_pairs(train_groups, ticket_texts)

    # Save files
    def save_jsonl(data, filename):
        path = os.path.join(args.out, filename)
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"  -> {path} ({len(data)} rows)")

    save_jsonl(triplets, "all_triplets.jsonl")
    save_jsonl(pairs, "all_pairs.jsonl")
    save_jsonl(train_triplets, "train_triplets.jsonl")
    save_jsonl(train_pairs, "train_pairs.jsonl")

    eval_path = os.path.join(args.out, "eval_set.json")
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_data, ensure_ascii=False, fp=f, indent=2)
    print(f"  -> {eval_path} ({len(eval_data.get('queries', {}))} eval queries)")

    # Stats
    print_stats(groups, triplets, pairs, ticket_texts)

    # Save metadata
    meta = {
        "feedback_db": args.feedback_db,
        "defect_db": args.defect_db,
        "total_feedback": len(feedback),
        "unique_queries": len(groups),
        "total_triplets": len(triplets),
        "total_pairs": len(pairs),
        "train_triplets": len(train_triplets),
        "train_pairs": len(train_pairs),
        "eval_queries": len(eval_data.get("queries", {})),
        "base_model": "BAAI/bge-small-zh-v1.5",
    }
    meta_path = os.path.join(args.out, "export_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, ensure_ascii=False, fp=f, indent=2)
    print(f"  -> {meta_path}")


if __name__ == "__main__":
    main()
