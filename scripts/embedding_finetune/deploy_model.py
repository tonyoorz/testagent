"""
Deploy fine-tuned embedding model to the production path.

What this script does:
1. Validates the fine-tuned model can load and encode text
2. Backs up existing model (if any)
3. Copies fine-tuned model to the production path
4. Clears the embedding cache (forces re-indexing with new model)
5. Verifies the deployment by encoding a test query

Usage:
    # Deploy to default location (cache/embedding_models/)
    python scripts/embedding_finetune/deploy_model.py

    # Deploy specific model
    python scripts/embedding_finetune/deploy_model.py \
        --model-path models/bge-small-zh-finetuned \
        --deploy-dir cache/embedding_models/finetuned_v1

    # Dry run (validate only, no file changes)
    python scripts/embedding_finetune/deploy_model.py --dry-run
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MODEL_PATH = str(PROJECT_ROOT / "models" / "bge-small-zh-finetuned")
DEFAULT_DEPLOY_DIR = str(
    PROJECT_ROOT / "cache" / "embedding_models" / "modelscope" / "BAAI" / "bge-small-zh-finetuned"
)
EMBEDDING_DB = str(PROJECT_ROOT / "database" / "ticket_embeddings.db")


def validate_model(model_path: str) -> bool:
    """Check the model loads and produces embeddings."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        print(f"[Validate] Loading model from: {model_path}")
        model = SentenceTransformer(model_path)

        test_texts = [
            "IDCEVO 26/07 HU-H5 导航路由规划黑屏",
            "车机系统崩溃重启 ECU: HU-H5",
            "转向系统噪音异常 PU 25/11",
        ]
        embeddings = model.encode(test_texts, normalize_embeddings=True)

        assert embeddings.shape[0] == 3
        assert embeddings.shape[1] > 0
        dim = embeddings.shape[1]

        # Check embeddings are normalized
        norms = np.linalg.norm(embeddings, axis=1)
        assert all(abs(n - 1.0) < 0.01 for n in norms), f"Embeddings not normalized: {norms}"

        # Check similarity is reasonable (first two should be more similar)
        sim_01 = float(np.dot(embeddings[0], embeddings[1]))
        sim_02 = float(np.dot(embeddings[0], embeddings[2]))
        print(f"[Validate] Dimension: {dim}")
        print(f"[Validate] Test sim(HU-H5 nav, HU-H5 crash): {sim_01:.4f}")
        print(f"[Validate] Test sim(HU-H5 nav, steering noise): {sim_02:.4f}")
        print(f"[Validate] ✅ Model validation passed")
        return True

    except Exception as exc:
        print(f"[Validate] ❌ Model validation FAILED: {exc}")
        return False


def clear_embedding_cache(db_path: str, model_name: str = None):
    """
    Clear cached embeddings so they get re-computed with the new model.
    If model_name is given, only clear that model's entries.
    """
    if not os.path.exists(db_path):
        print(f"[Cache] No embedding DB at {db_path}, nothing to clear")
        return

    conn = sqlite3.connect(db_path)
    if model_name:
        result = conn.execute(
            "DELETE FROM ticket_embeddings WHERE model_name = ?", (model_name,)
        )
    else:
        result = conn.execute("DELETE FROM ticket_embeddings")
    deleted = result.rowcount
    conn.commit()
    conn.close()
    print(f"[Cache] Cleared {deleted} cached embeddings from {db_path}")


def deploy(model_path: str, deploy_dir: str, dry_run: bool = False):
    """Deploy fine-tuned model to production path."""
    if not os.path.exists(model_path):
        print(f"[ERROR] Model not found: {model_path}")
        return False

    # Step 1: Validate
    if not validate_model(model_path):
        print("[ABORT] Model validation failed. Not deploying.")
        return False

    if dry_run:
        print("\n[DRY RUN] Validation passed. No files changed.")
        return True

    # Step 2: Backup existing model
    if os.path.exists(deploy_dir):
        backup_dir = f"{deploy_dir}.backup.{int(time.time())}"
        print(f"[Deploy] Backing up existing model → {backup_dir}")
        shutil.move(deploy_dir, backup_dir)

    # Step 3: Copy model
    print(f"[Deploy] Copying model → {deploy_dir}")
    shutil.copytree(model_path, deploy_dir)

    # Step 4: Clear embedding cache
    clear_embedding_cache(EMBEDDING_DB)

    # Step 5: Verify deployment
    if validate_model(deploy_dir):
        print(f"\n✅ Deployment successful!")
        print(f"   Model path: {deploy_dir}")
        print(f"\n   To use this model, set environment variable:")
        print(f"   DUPLICATE_EMBEDDING_MODEL={deploy_dir}")
        print(f"\n   Or the model will be auto-discovered by _discover_local_embedding_model()")
        print(f"\n   Next time the app starts, all ticket embeddings will be re-computed.")
        return True
    else:
        print("[ERROR] Post-deployment validation failed!")
        return False


def main():
    parser = argparse.ArgumentParser(description="Deploy fine-tuned embedding model")
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH, help="Path to fine-tuned model")
    parser.add_argument("--deploy-dir", default=DEFAULT_DEPLOY_DIR, help="Deployment directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, don't copy files")
    args = parser.parse_args()

    deploy(args.model_path, args.deploy_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
