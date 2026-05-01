"""
Unified Auto-Train Pipeline for Duplicate Search.

Usage:
    # 自动模式：检查数据量，够就训练
    python auto_train_pipeline.py

    # 强制训练（不管数据量）
    python auto_train_pipeline.py --force

    # 只导出数据不训练
    python auto_train_pipeline.py --export-only --output-dir ./training_export

    # 指定 GPU
    python auto_train_pipeline.py --device cuda:0
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
LATEST_MODEL_FILE = os.path.join(MODELS_DIR, "latest_model.txt")
LATEST_REPORT_FILE = os.path.join(MODELS_DIR, "latest_report.json")


class AutoTrainPipeline:
    """Unified auto-train pipeline: data prep → quality check → train → deploy."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        min_pairs: int = 50,
        min_positive_ratio: float = 0.3,
        max_positive_ratio: float = 0.7,
        base_model: str = "BAAI/bge-small-zh-v1.5",
        epochs: int = 5,
        batch_size: int = 16,
        lr: float = 2e-5,
        device: str = "cpu",
    ):
        self.db_path = db_path or os.path.join(
            PROJECT_ROOT, "database", "ticket_embeddings.db"
        )
        self.min_pairs = min_pairs
        self.min_positive_ratio = min_positive_ratio
        self.max_positive_ratio = max_positive_ratio
        self.base_model = base_model
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.device = device

    # ── Data preparation ───────────────────────────────────────────

    def prepare_data(self, output_dir: str) -> Dict[str, Any]:
        """Mine training data from feedback & search sessions, export JSONL."""
        # TODO: search_session_tracker module not yet implemented
        # Currently training data comes from FeedbackStore directly
        from feedback_store import FeedbackStore

        os.makedirs(output_dir, exist_ok=True)
        store = FeedbackStore()
        examples = store.get_training_examples()

        if not examples:
            return {"pairs": 0, "triplets": 0, "ready": False}

        pair_records = []
        for e in examples:
            if e.get("signal") == "positive" and e.get("query_text") and e.get("ticket_id"):
                pair_records.append({
                    "anchor": e["query_text"],
                    "positive": e["ticket_id"],
                    "weight": 1.0,
                })

        pair_path = os.path.join(output_dir, "train_pairs.jsonl")
        with open(pair_path, "w", encoding="utf-8") as f:
            for rec in pair_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        stats = {"pairs": len(pair_records), "triplets": 0, "ready": len(pair_records) >= 50}
        return stats


    # ── Quality check ──────────────────────────────────────────────

    def check_quality(self, data_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data quality before training."""
        total = data_stats.get("exported_pairs", 0)
        triplets = data_stats.get("exported_triplets", 0)
        pos = data_stats.get("positive_pairs", 0)
        neg = data_stats.get("negative_pairs", 0)
        total_raw = pos + neg

        checks: List[Dict[str, Any]] = []

        # Minimum pairs
        enough = total >= self.min_pairs
        checks.append({
            "name": "min_pairs",
            "passed": enough,
            "detail": f"{total}/{self.min_pairs} exported pairs",
        })

        # Positive ratio
        if total_raw > 0:
            pos_ratio = pos / total_raw
            balanced = self.min_positive_ratio <= pos_ratio <= self.max_positive_ratio
            checks.append({
                "name": "balance",
                "passed": balanced,
                "detail": f"positive ratio {pos_ratio:.2f} (target {self.min_positive_ratio:.1f}~{self.max_positive_ratio:.1f})",
            })
        else:
            checks.append({"name": "balance", "passed": False, "detail": "no raw pairs"})

        all_passed = all(c["passed"] for c in checks)

        print("\n=== Quality Check ===")
        for c in checks:
            icon = "✅" if c["passed"] else "❌"
            print(f"  {icon} {c['name']}: {c['detail']}")
        print(f"  Overall: {'PASS' if all_passed else 'FAIL'}")

        return {"passed": all_passed, "checks": checks}

    # ── Training ───────────────────────────────────────────────────

    def train(self, data_dir: str, output_dir: str) -> Dict[str, Any]:
        """Run embedding fine-tuning."""
        from scripts.embedding_finetune.train_utils import train_embedding_model

        # Decide strategy
        triplet_path = os.path.join(data_dir, "train_triplets.jsonl")
        pair_path = os.path.join(data_dir, "train_pairs.jsonl")

        n_pairs = 0
        n_triplets = 0
        if os.path.exists(pair_path):
            with open(pair_path) as f:
                n_pairs = sum(1 for _ in f)
        if os.path.exists(triplet_path):
            with open(triplet_path) as f:
                n_triplets = sum(1 for _ in f)

        # Hybrid if enough triplets
        strategy = "mnrl"
        if n_triplets > n_pairs * 0.5 and n_triplets >= 10:
            strategy = "hybrid"

        print(f"\n=== Training ===")
        print(f"  Strategy: {strategy}")
        print(f"  Pairs: {n_pairs}, Triplets: {n_triplets}")
        print(f"  Device: {self.device}")

        eval_path = os.path.join(data_dir, "eval_set.json")
        if not os.path.exists(eval_path):
            eval_path = None

        metrics = train_embedding_model(
            base_model=self.base_model,
            train_data_dir=data_dir,
            output_dir=output_dir,
            strategy=strategy,
            epochs=self.epochs,
            batch_size=self.batch_size,
            lr=self.lr,
            device=self.device,
            eval_data_path=eval_path,
        )
        return metrics

    # ── Model deployment ───────────────────────────────────────────

    def deploy(self, model_dir: str, metrics: Dict[str, Any]) -> bool:
        """Deploy model if it passes safety check."""
        old_ndcg = self._load_old_ndcg()
        new_ndcg = metrics.get("ndcg")

        # Safety: don't deploy if significantly worse
        if new_ndcg is not None and old_ndcg is not None:
            if new_ndcg < old_ndcg - 0.05:
                print(f"\n⚠️  Safety check FAILED: new NDCG={new_ndcg:.4f} < old NDCG={old_ndcg:.4f} - 0.05")
                print("  Keeping previous model. New model saved but not activated.")
                return False

        # Update latest_model.txt
        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(LATEST_MODEL_FILE, "w") as f:
            f.write(model_dir)

        print(f"\n✅ Deployed: {model_dir}")
        if new_ndcg is not None:
            print(f"  NDCG: {new_ndcg:.4f} (previous: {old_ndcg})")
        return True

    def _load_old_ndcg(self) -> Optional[float]:
        if not os.path.exists(LATEST_REPORT_FILE):
            return None
        try:
            with open(LATEST_REPORT_FILE) as f:
                report = json.load(f)
            return report.get("metrics", {}).get("ndcg")
        except Exception:
            return None

    # ── Report ─────────────────────────────────────────────────────

    def save_report(
        self,
        data_stats: Dict[str, Any],
        quality: Dict[str, Any],
        metrics: Dict[str, Any],
        model_dir: str,
        deployed: bool,
    ) -> str:
        report = {
            "timestamp": datetime.now().isoformat(),
            "data": data_stats,
            "quality": quality,
            "metrics": metrics,
            "model_dir": model_dir,
            "deployed": deployed,
        }
        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(LATEST_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print("\n=== Training Report ===")
        print(f"  Time:       {report['timestamp']}")
        print(f"  Data pairs: {data_stats.get('exported_pairs', 0)}")
        print(f"  Triplets:   {data_stats.get('exported_triplets', 0)}")
        print(f"  Epochs:     {metrics.get('epochs', 'N/A')}")
        print(f"  Strategy:   {metrics.get('strategy', 'N/A')}")
        ndcg = metrics.get("ndcg")
        print(f"  NDCG:       {ndcg:.4f}" if ndcg is not None else "  NDCG:       N/A")
        print(f"  Model:      {model_dir}")
        print(f"  Deployed:   {'Yes' if deployed else 'No'}")
        print(f"  Report:     {LATEST_REPORT_FILE}")

        return LATEST_REPORT_FILE

    # ── Main pipeline ──────────────────────────────────────────────

    def run(
        self,
        force: bool = False,
        export_only: bool = False,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the full pipeline."""
        # Step 1: Prepare data
        data_dir = output_dir or os.path.join(PROJECT_ROOT, "training_export")
        data_stats = self.prepare_data(data_dir)

        if export_only:
            print("\n[export-only] Data exported, skipping training.")
            return {"status": "exported", "data_stats": data_stats}

        # Step 2: Quality check
        quality = self.check_quality(data_stats)
        if not quality["passed"] and not force:
            print("\n⚠️  Quality check failed. Use --force to train anyway.")
            return {"status": "quality_failed", "data_stats": data_stats, "quality": quality}

        if quality["passed"] is False and force:
            print("\n[force] Quality check overridden.")

        # Step 3: Train
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_dir = os.path.join(
            MODELS_DIR, f"bge-small-zh-finetuned-v{timestamp}"
        )

        try:
            metrics = self.train(data_dir, model_dir)
        except Exception as exc:
            logger.exception("Training failed")
            print(f"\n❌ Training failed: {exc}")
            return {"status": "training_failed", "error": str(exc)}

        # Step 4: Deploy
        deployed = self.deploy(model_dir, metrics)

        # Step 5: Report
        report_path = self.save_report(data_stats, quality, metrics, model_dir, deployed)

        return {
            "status": "success" if deployed else "trained_not_deployed",
            "data_stats": data_stats,
            "quality": quality,
            "metrics": metrics,
            "model_dir": model_dir,
            "deployed": deployed,
            "report_path": report_path,
        }


def main():
    parser = argparse.ArgumentParser(description="Unified Auto-Train Pipeline")
    parser.add_argument("--force", action="store_true", help="Train even if quality check fails")
    parser.add_argument("--export-only", action="store_true", help="Only export data, don't train")
    parser.add_argument("--output-dir", default=None, help="Output directory for exported data")
    parser.add_argument("--device", default="cpu", help="Device for training (cpu, cuda:0, etc.)")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--min-pairs", type=int, default=50, help="Minimum pairs to train")
    parser.add_argument("--base-model", default="BAAI/bge-small-zh-v1.5")
    args = parser.parse_args()

    pipeline = AutoTrainPipeline(
        min_pairs=args.min_pairs,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        device=args.device,
    )
    result = pipeline.run(
        force=args.force,
        export_only=args.export_only,
        output_dir=args.output_dir,
    )
    print(f"\nPipeline result: {result['status']}")
    return result


if __name__ == "__main__":
    main()
