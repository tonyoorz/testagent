"""
ML-based Intent Classification Module

Bilingual (CN+EN) intent classifier using XLM-RoBERTa fine-tuning.
Replaces TF-IDF cosine similarity with a trained model for better accuracy.

Usage:
    AGENT_ML_INTENT=1 python -m agent.ml_intent.train
"""

from .classifier import IntentClassifier

__all__ = ["IntentClassifier"]
