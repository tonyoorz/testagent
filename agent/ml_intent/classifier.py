"""
ML Intent Classifier — Inference Module

Loads fine-tuned XLM-RoBERTa for bilingual intent classification.
Falls back gracefully if model not found.

Usage:
    from agent.ml_intent.classifier import IntentClassifier
    clf = IntentClassifier()
    intent, conf = clf.predict("帮我看看ECU乒乓的情况")
"""

import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "model"


class IntentClassifier:
    """Bilingual intent classifier using fine-tuned XLM-RoBERTa."""

    def __init__(self, model_path: str = None, threshold: float = 0.7):
        self.threshold = threshold
        self.model = None
        self.tokenizer = None
        self.id2label = {}
        self.label2id = {}
        self.device = None
        self._loaded = False

        path = Path(model_path) if model_path else MODEL_DIR
        self._load(path)

    def _load(self, model_path: Path):
        """Load model, tokenizer, and label mapping."""
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
        except ImportError:
            logger.warning("transformers/torch not installed. ML classifier unavailable.")
            return

        if not model_path.exists():
            logger.info(f"ML model not found at {model_path}. Run training first.")
            return

        try:
            self.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

            self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path))
            self.model.to(self.device)
            self.model.eval()

            # Load label mapping
            mapping_file = model_path / "label_mapping.json"
            if mapping_file.exists():
                with open(mapping_file, "r") as f:
                    mapping = json.load(f)
                self.label2id = mapping["label2id"]
                self.id2label = {int(k): v for k, v in mapping["id2label"].items()}

            self._loaded = True
            logger.info(f"ML intent classifier loaded from {model_path} (device={self.device})")

        except Exception as e:
            logger.warning(f"Failed to load ML classifier: {e}")
            self._loaded = False

    @property
    def is_ready(self) -> bool:
        return self._loaded

    def predict(self, text: str, threshold: float = None) -> Tuple[Optional[str], float]:
        """
        Predict intent for a single text.

        Returns:
            (intent, confidence) — intent is None if below threshold
        """
        if not self._loaded:
            return None, 0.0

        import torch

        thresh = threshold or self.threshold

        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=64, padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = self.model(**inputs).logits

        probs = torch.softmax(logits, dim=-1)
        max_prob, max_idx = probs.max(dim=-1)

        confidence = max_prob.item()
        intent_idx = max_idx.item()

        if confidence < thresh:
            return None, confidence

        intent = self.id2label.get(intent_idx, f"unknown_{intent_idx}")
        return intent, confidence

    def predict_batch(self, texts: List[str], threshold: float = None) -> List[Tuple[Optional[str], float]]:
        """Predict intents for multiple texts."""
        if not self._loaded:
            return [(None, 0.0)] * len(texts)

        import torch

        thresh = threshold or self.threshold

        inputs = self.tokenizer(
            texts, return_tensors="pt", truncation=True, max_length=64, padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = self.model(**inputs).logits

        probs = torch.softmax(logits, dim=-1)
        max_probs, max_indices = probs.max(dim=-1)

        results = []
        for prob, idx in zip(max_probs.tolist(), max_indices.tolist()):
            if prob < thresh:
                results.append((None, prob))
            else:
                results.append((self.id2label.get(idx, f"unknown_{idx}"), prob))

        return results

    def predict_top_k(self, text: str, k: int = 3) -> List[Tuple[str, float]]:
        """Get top-k intent predictions with probabilities."""
        if not self._loaded:
            return []

        import torch

        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=64, padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = self.model(**inputs).logits

        probs = torch.softmax(logits, dim=-1).squeeze()
        top_k = torch.topk(probs, min(k, len(probs)))

        return [
            (self.id2label.get(idx.item(), f"unknown_{idx.item()}"), prob.item())
            for prob, idx in zip(top_k.values, top_k.indices)
        ]


# Singleton for reuse
_classifier_instance = None


def get_classifier() -> IntentClassifier:
    """Get or create singleton classifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
