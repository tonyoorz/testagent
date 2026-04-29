# Embedding Fine-tune Pipeline

This directory contains the complete pipeline for fine-tuning the duplicate search embedding model.

## Quick Start

```bash
# Step 1: Export training data from feedback database
python scripts/embedding_finetune/export_training_data.py

# Step 2: Train (on GPU machine)
python scripts/embedding_finetune/train_embedding.py --strategy mnrl

# Step 3: Evaluate
python scripts/embedding_finetune/evaluate_model.py

# Step 4: Deploy
python scripts/embedding_finetune/deploy_model.py
```

## Pipeline

```
feedback_records (SQLite)
        │
        ▼
[export_training_data.py]  →  training_data/*.jsonl
        │
        ▼
[train_embedding.py]       →  models/bge-small-zh-finetuned/
        │
        ▼
[evaluate_model.py]        →  compare base vs fine-tuned
        │
        ▼
[deploy_model.py]          →  cache/embedding_models/ + clear cache
```

## GPU Requirements

Training requires a GPU. Options:
- AutoDL (A100/4090, ¥2-5/hr)
- Colab Pro (T4/A100)
- Local RTX 4090

To transfer training data to GPU machine:
```bash
# Pack training data
tar czf training_data.tar.gz scripts/embedding_finetune/training_data/

# On GPU machine
tar xzf training_data.tar.gz
pip install sentence-transformers>=3.0.0 torch>=2.0
python scripts/embedding_finetune/train_embedding.py --strategy mnrl
```
