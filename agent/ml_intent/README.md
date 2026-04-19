# ML Intent Classifier

Bilingual (Chinese + English) intent classification using fine-tuned XLM-RoBERTa.

## Architecture

```
agent/ml_intent/
├── __init__.py
├── classifier.py              # Inference module (IntentClassifier)
├── generate_training_data.py  # Generate augmented training data
├── train.py                   # Fine-tune XLM-RoBERTa
├── requirements.txt           # Python dependencies
├── data/
│   └── train_data.json        # Generated training data (after running generator)
└── model/                     # Saved model (after training)
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    └── label_mapping.json
```

## Quick Start

### 1. Install dependencies

```bash
cd /path/to/testagent
pip install -r agent/ml_intent/requirements.txt
```

### 2. Generate training data

```bash
python -m agent.ml_intent.generate_training_data
# Output: agent/ml_intent/data/train_data.json
# Expected: 500-1000 augmented samples across 17 intents
```

### 3. Train the model

```bash
python -m agent.ml_intent.train
# ~5-10 min on Mac mini M1 (CPU/MPS)
# Output: agent/ml_intent/model/
```

### 4. Enable in Agent

```bash
export AGENT_ML_INTENT=1
```

Or add to `.env`:
```
AGENT_ML_INTENT=1
```

## How It Works

### Training Data Augmentation
The generator reads existing `INTENT_EXAMPLES` from `semantic_intent_detector.py` and creates variations using:
- **Synonym replacement** — CN/EN synonyms for domain terms
- **Prefix/suffix** — Natural conversational prefixes ("帮我...", "can you...")
- **Short forms** — Removing stop words
- **Typo injection** — Common character-level mistakes
- **Mixed language** — CN/EN mixing common in foreign companies

### Model
- **Base**: `xlm-roberta-base` (278M params, multilingual)
- **Task**: Sequence classification (17 intent classes)
- **Max length**: 64 tokens
- **Device**: MPS (M1/M2 Mac) or CPU

### Inference Pipeline
```
User Input
    ↓
ML Classifier (confidence ≥ 0.7?)
    ↓ Yes                    ↓ No
Return ML intent      →  Fall back to TF-IDF cosine similarity
```

### Threshold
- Default confidence threshold: **0.7**
- Below threshold → falls back to TF-IDF method
- Adjustable in `IntentClassifier(threshold=0.X)`

## Intents Covered

| Intent | Description |
|--------|-------------|
| risk | Risk analysis, critical defects |
| comparison | Project/module comparison |
| trend | Time-series trends |
| summary | Overview / summary |
| quality | Quality metrics |
| test | Test-related queries |
| dashboard | Dashboard navigation |
| matrix | Matrix distribution |
| cross | Cross-dimensional analysis |
| tester | Tester-specific queries |
| anomaly | Anomaly detection |
| root_cause | Root cause analysis |
| risk_eval | Risk evaluation |
| coverage | Test coverage |
| association | Association/correlation |
| strategy | Test strategy |
| predict | Prediction/forecast |

## Performance

Expected after training on ~800 augmented samples:
- Validation accuracy: **85-95%**
- Inference latency: **<50ms** per query (CPU)
- Both Chinese and English queries supported

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_ML_INTENT` | `0` | Enable ML classifier (1=on, 0=off) |

## Troubleshooting

**"ML model not found"**
→ Run training first: `python -m agent.ml_intent.train`

**"transformers/torch not installed"**
→ Install: `pip install -r agent/ml_intent/requirements.txt`

**Low accuracy**
→ Add more examples to `INTENT_EXAMPLES` in `semantic_intent_detector.py`, then regenerate and retrain
