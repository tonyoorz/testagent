"""
Training Data Generator for ML Intent Classifier

Generates augmented training data from existing INTENT_EXAMPLES in semantic_intent_detector.py.
No external API calls — all augmentation is rule-based and offline.

Usage:
    python -m agent.ml_intent.generate_training_data
    # Output: agent/ml_intent/data/train_data.json
"""

import json
import os
import random
import re
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# Augmentation helpers
# ============================================================

# Common Chinese synonyms for testing terms
SYNONYM_MAP = {
    "缺陷": ["bug", "问题", "故障", "defect", "issue", "毛病"],
    "风险": ["risk", "危险", "隐患", "threat", "高风险"],
    "严重": ["critical", "重大", "高优", "紧急", "severe", "high priority"],
    "趋势": ["trend", "走势", "变化", "趋势走向", "evolution"],
    "对比": ["compare", "比较", "versus", "vs", "横向"],
    "总结": ["summary", "概览", "总览", "overview", "整体情况"],
    "测试": ["test", "testing", "验证", "verification"],
    "覆盖": ["coverage", "覆盖度", "覆盖率"],
    "异常": ["anomaly", "abnormal", "不正常", "outlier"],
    "根因": ["root cause", "根本原因", "root cause analysis", "RCA"],
    "推荐": ["recommend", "建议", "suggestion", "recommendation"],
    "策略": ["strategy", "方法", "approach", "plan"],
    "预测": ["predict", "prediction", "forecast", "预估"],
    "分析": ["analysis", "analyze", "深入分析", "详细分析"],
    "分布": ["distribution", "矩阵", "matrix"],
    "ECU": ["ecu", "控制器", "controller"],
    "项目": ["project", "proj"],
    "模块": ["module", "component", "组件"],
    "状态": ["status", "state", "状态流转"],
    "流转": ["transition", "flow", "变更"],
    "矩阵": ["matrix", "分布矩阵", "热力图"],
    "关联": ["association", "correlation", "关联性"],
    "测试人员": ["tester", "工程师", "engineer", "QA"],
    "数据": ["data", "信息", "information"],
    "多少": ["how many", "count", "数量"],
    "如何": ["how", "怎么样", "how about"],
    "哪些": ["which", "what are"],
    "最近": ["recent", "lately", "近期", "最近"],
    "最高": ["highest", "top", "最大"],
    "有没有": ["any", "are there"],
    "看看": ["show", "check", "display", "查看"],
}

# English paraphrase patterns
EN_PATTERNS = {
    "show me": ["display", "give me", "tell me", "list", "show"],
    "how many": ["count of", "number of", "total", "how much"],
    "what is": ["whats", "what are", "which is"],
    "analysis": ["analysis", "analytics", "breakdown", "insights"],
    "compare": ["compare", "contrast", "versus", "vs", "diff"],
    "trend": ["trend", "trends", "trajectory", "pattern", "progression"],
}

# Noise injection for robustness
TYPO_MAP = {
    "的": ["de", "得", "地"],
    "了": ["le", "聊"],
    "分析": ["分柝", "分析"],
    "风险": ["分险", "风险"],
    "测试": ["测识", "测试"],
    "缺陷": ["确陷", "缺陷"],
    "对比": ["对笔", "对比"],
    "趋势": ["趋示", "趋势"],
    "总结": ["总结", "总结"],
}


def augment_with_synonyms(text: str) -> list[str]:
    """Replace words with synonyms to create variations."""
    results = []
    for cn_word, synonyms in SYNONYM_MAP.items():
        if cn_word in text:
            for syn in random.sample(synonyms, min(2, len(synonyms))):
                new_text = text.replace(cn_word, syn, 1)
                if new_text != text:
                    results.append(new_text)
    return results


def augment_with_prefix(text: str) -> list[str]:
    """Add natural prefixes users might use."""
    prefixes_cn = ["帮我", "请问", "我想知道", "看一下", "能不能看"]
    prefixes_en = ["can you", "please", "could you", "I want to", "show me"]
    results = []
    # Add a random prefix
    if any(ord(c) > 0x4e00 for c in text):
        # Has Chinese — add Chinese prefix
        prefix = random.choice(prefixes_cn)
        results.append(f"{prefix}{text}")
    if any(ord(c) < 0x80 for c in text):
        # Has English — add English prefix
        prefix = random.choice(prefixes_en)
        results.append(f"{prefix} {text}")
    return results


def augment_with_suffix(text: str) -> list[str]:
    """Add natural suffixes."""
    suffixes = ["怎么样", "如何", "有多少", "的情况", "是什么情况", "是怎样的"]
    results = []
    if any(ord(c) > 0x4e00 for c in text):
        suffix = random.choice(suffixes)
        if not text.endswith(suffix):
            results.append(f"{text}{suffix}")
    return results


def augment_short_form(text: str) -> list[str]:
    """Create shortened/abbreviated versions."""
    results = []
    # Remove some stop words
    stop_words = ["的", "了", "吗", "呢", "吧", "情况", "问题"]
    shortened = text
    for w in random.sample(stop_words, min(2, len(stop_words))):
        shortened = shortened.replace(w, "", 1)
    if shortened != text and len(shortened) > 1:
        results.append(shortened)
    return results


def augment_with_typos(text: str) -> list[str]:
    """Inject minor typos for robustness."""
    results = []
    for correct, typos in TYPO_MAP.items():
        if correct in text:
            typo = random.choice(typos)
            if typo != correct:
                results.append(text.replace(correct, typo, 1))
    return results


def augment_mixed_lang(text: str) -> list[str]:
    """Create mixed CN/EN versions common in foreign companies."""
    mixed_pairs = {
        "缺陷": "defect",
        "风险": "risk",
        "测试": "test",
        "分析": "analysis",
        "覆盖": "coverage",
        "异常": "anomaly",
        "对比": "comparison",
        "趋势": "trend",
        "严重": "critical",
        "推荐": "recommend",
    }
    results = []
    for cn, en in random.sample(list(mixed_pairs.items()), min(1, len(mixed_pairs))):
        if cn in text:
            results.append(text.replace(cn, en, 1))
    return results


def augment_text(text: str, label: str, target_per_sample: int = 8) -> list[dict]:
    """Apply all augmentation strategies to generate variations."""
    all_texts = set()
    all_texts.add(text)

    augmenters = [
        augment_with_synonyms,
        augment_with_prefix,
        augment_with_suffix,
        augment_short_form,
        augment_with_typos,
        augment_mixed_lang,
    ]

    for aug_fn in augmenters:
        try:
            variations = aug_fn(text)
            all_texts.update(variations)
        except Exception:
            pass

    # If we need more, apply augmentation recursively on generated ones
    attempts = 0
    while len(all_texts) < target_per_sample and attempts < 20:
        base = random.choice(list(all_texts))
        aug_fn = random.choice(augmenters)
        try:
            variations = aug_fn(base)
            all_texts.update(variations)
        except Exception:
            pass
        attempts += 1

    return [{"text": t, "label": label} for t in all_texts]


def generate_training_data(output_path: str = None):
    """Generate the full training dataset."""
    # Import intent examples from existing detector
    from agent.core.semantic_intent_detector import SemanticIntentDetector

    detector = SemanticIntentDetector()
    intent_examples = detector.INTENT_EXAMPLES

    print(f"Found {len(intent_examples)} intents with examples")

    all_data = []
    stats = {}

    for intent, examples in intent_examples.items():
        intent_data = []
        for example in examples:
            augmented = augment_text(example, intent, target_per_sample=6)
            intent_data.extend(augmented)

        # Deduplicate
        seen = set()
        unique_data = []
        for item in intent_data:
            if item["text"] not in seen:
                seen.add(item["text"])
                unique_data.append(item)

        all_data.extend(unique_data)
        stats[intent] = len(unique_data)
        print(f"  {intent}: {len(examples)} original → {len(unique_data)} augmented")

    # Shuffle
    random.shuffle(all_data)

    # Save
    if output_path is None:
        output_path = str(Path(__file__).parent / "data" / "train_data.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    total = len(all_data)
    print(f"\nTotal training samples: {total}")
    print(f"Saved to: {output_path}")
    print(f"\nDistribution:")
    for intent, count in sorted(stats.items()):
        pct = count / total * 100
        print(f"  {intent:15s}: {count:4d} ({pct:.1f}%)")

    return all_data


if __name__ == "__main__":
    random.seed(42)  # Reproducible
    generate_training_data()
