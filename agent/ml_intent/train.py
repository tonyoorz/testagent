"""
Train ML Intent Classifier

Fine-tunes XLM-RoBERTa-base for bilingual (CN+EN) intent classification.
Runs on CPU — ~5-10 min on Mac mini M1 with 500-1000 samples.

Usage:
    cd /path/to/testagent
    python -m agent.ml_intent.generate_training_data  # Generate data first
    python -m agent.ml_intent.train                    # Then train
"""

import json
import os
import sys
from pathlib import Path

import numpy as np

# ============================================================
# Config
# ============================================================
DATA_PATH = Path(__file__).parent / "data" / "train_data.json"
MODEL_DIR = Path(__file__).parent / "model"
BASE_MODEL = "distilbert-base-multilingual-cased"
MAX_LENGTH = 64
NUM_EPOCHS = 5
BATCH_SIZE = 16
LEARNING_RATE = 3e-5
VAL_SPLIT = 0.2
SEED = 42

# ============================================================
# Main
# ============================================================

def train():
    # Lazy imports — don't fail if transformers not installed
    import torch
    from torch.utils.data import Dataset, DataLoader
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        get_linear_schedule_with_warmup,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, accuracy_score

    # 1. Load data
    if not DATA_PATH.exists():
        print(f"❌ Training data not found at {DATA_PATH}")
        print("Run: python -m agent.ml_intent.generate_training_data")
        sys.exit(1)

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} training samples")

    texts = [d["text"] for d in data]
    labels = [d["label"] for d in data]

    # 2. Label encoding
    unique_labels = sorted(set(labels))
    label2id = {l: i for i, l in enumerate(unique_labels)}
    id2label = {i: l for l, i in label2id.items()}
    num_labels = len(unique_labels)
    print(f"Labels: {num_labels} → {unique_labels}")

    # Save label mapping
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(MODEL_DIR / "label_mapping.json", "w") as f:
        json.dump({"label2id": label2id, "id2label": {str(k): v for k, v in id2label.items()}}, f, indent=2)

    # 3. Train/val split
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts, labels, test_size=VAL_SPLIT, stratify=labels, random_state=SEED
    )
    print(f"Train: {len(train_texts)}, Val: {len(val_texts)}")

    # 4. Tokenizer
    print(f"Loading tokenizer: {BASE_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

    # 5. Dataset
    class IntentDataset(Dataset):
        def __init__(self, texts, labels, tokenizer, max_length, label2id):
            self.texts = texts
            self.labels = [label2id[l] for l in labels]
            self.tokenizer = tokenizer
            self.max_length = max_length

        def __len__(self):
            return len(self.texts)

        def __getitem__(self, idx):
            encoding = self.tokenizer(
                self.texts[idx],
                truncation=True,
                padding="max_length",
                max_length=self.max_length,
                return_tensors="pt",
            )
            return {
                "input_ids": encoding["input_ids"].squeeze(),
                "attention_mask": encoding["attention_mask"].squeeze(),
                "labels": torch.tensor(self.labels[idx]),
            }

    train_ds = IntentDataset(train_texts, train_labels, tokenizer, MAX_LENGTH, label2id)
    val_ds = IntentDataset(val_texts, val_labels, tokenizer, MAX_LENGTH, label2id)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)

    # 6. Model
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Using device: {device}")

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    )
    model.to(device)

    # 7. Optimizer & scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    total_steps = len(train_loader) * NUM_EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=int(0.1 * total_steps), num_training_steps=total_steps
    )

    # 8. Training loop
    best_val_acc = 0.0
    print(f"\nTraining for {NUM_EPOCHS} epochs...")

    for epoch in range(NUM_EPOCHS):
        # Train
        model.train()
        total_loss = 0
        for batch in train_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels_batch = batch["labels"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels_batch)
            loss = outputs.loss

            loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)

        # Validate
        model.eval()
        val_preds = []
        val_true = []
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels_batch = batch["labels"].to(device)

                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                preds = outputs.logits.argmax(dim=-1).cpu().tolist()
                val_preds.extend(preds)
                val_true.extend(labels_batch.cpu().tolist())

        val_acc = accuracy_score(val_true, val_preds)
        print(f"  Epoch {epoch+1:2d}/{NUM_EPOCHS}: loss={avg_loss:.4f}, val_acc={val_acc:.4f}")

        # Save best
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            model.save_pretrained(MODEL_DIR)
            tokenizer.save_pretrained(MODEL_DIR)
            print(f"    ✓ Saved best model (acc={val_acc:.4f})")

    # 9. Final evaluation
    print(f"\n{'='*60}")
    print(f"Best validation accuracy: {best_val_acc:.4f}")
    print(f"Model saved to: {MODEL_DIR}")

    # Load best model for final report
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
    model.to(device)
    model.eval()

    val_preds = []
    val_true = []
    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels_batch = batch["labels"].to(device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            val_preds.extend(outputs.logits.argmax(dim=-1).cpu().tolist())
            val_true.extend(labels_batch.cpu().tolist())

    pred_labels = [id2label[i] for i in val_preds]
    true_labels = [id2label[i] for i in val_true]
    print(f"\nClassification Report:")
    print(classification_report(true_labels, pred_labels, zero_division=0))

    print(f"\n✅ Training complete! Model saved to: {MODEL_DIR}")
    print(f"Enable in agent: AGENT_ML_INTENT=1")


if __name__ == "__main__":
    train()
