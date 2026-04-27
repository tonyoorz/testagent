# Feedback-Driven Duplicate Detection Re-Ranker Design

## Goal

Extend the existing duplicate issue detection system with a **progressive feedback learning pipeline** so that search results become more accurate over time as testers, test managers, and product managers provide feedback. The system must work from day one (zero feedback), improve incrementally, and never degrade below baseline quality.

## Scope

Included:

- feedback collection API (record thumbs-up, thumbs-down, click signals)
- three-phase progressive re-ranker (rule boost → LogReg → contrastive adapter)
- automatic training trigger on feedback accumulation
- lightweight anti-noise guard (flip detection, rate limiting, model rollback)
- integration into existing `DuplicateIssueIndex.search()` flow
- SQLite persistence in existing `database/ticket_embeddings.db`
- unit tests for each component

Excluded:

- changes to the base embedding model (bge-small-zh-v1.5 stays frozen)
- LLM (DeepSeek) fine-tuning
- front-end UI changes in Agent chat (feedback buttons are an API contract only)
- GPU-dependent training paths
- user trust scoring or consensus voting (unnecessary for internal BMW user base)

## Context

### Current System

[duplicate_issue_finder.py](../../../duplicate_issue_finder.py) implements a three-tier graceful-degradation search engine:

| Tier | Method | Library |
|------|--------|---------|
| 1 | Semantic embedding (BAAI/bge-small-zh-v1.5, 384-dim) | `sentence_transformers` |
| 2 | TF-IDF character n-grams (3-5, 200K features) | `sklearn` |
| 3 | Keyword token overlap (matches / 8.0) | built-in |

The existing `_apply_hint_boost()` adds static score bonuses for project (+0.08), PU (+0.12), ECU (+0.10), and lead_model (+0.05) metadata matches. There is no learning from user interaction.

### Problem

- Static hint boosts are hand-tuned, may not reflect actual user preferences
- No mechanism to learn from "this result was helpful" or "this is not a duplicate"
- High-quality BMW internal users provide feedback that currently goes unused
- Search accuracy plateaus regardless of usage volume

### Users

BMW internal testers, test managers, and product managers authenticated via BMW SSO. Trusted internal users — risk of malicious annotation is negligible. Primary noise source is accidental clicks (hand-slip).

## Architecture

### Data Flow

```
User Query                               User Feedback
    │                                         │
    ▼                                         ▼
┌──────────────────────┐         ┌──────────────────────────┐
│ DuplicateIssueIndex  │         │  FeedbackStore (SQLite)   │
│  .search() coarse    │         │  feedback_records table   │
│  frozen embedding    │         └────────────┬─────────────┘
└──────────┬───────────┘                      │
           │ top-50 candidates                │ auto-trigger every N records
           ▼                                  ▼
┌─────────────────────────────────────────────────────────────┐
│              ProgressiveReRanker                             │
├──────────────────────────────────────────────────────────────┤
│  Phase 1 (0-50 feedback):   ClickBoostReRanker              │
│     rule-based frequency boost, zero training cost           │
│                                                              │
│  Phase 2 (50-200 feedback): FeatureReRanker                  │
│     LogisticRegression on 9 features                         │
│                                                              │
│  Phase 3 (200+ feedback):   ContrastiveAdapter               │
│     Linear(384→384) projection + FeatureReRanker stacked     │
└──────────┬───────────────────────────────────────────────────┘
           │ re-ranked top-K
           ▼
     List[DuplicateCandidate]
```

### What Gets Trained

The base embedding model and LLM are **never modified**. Two lightweight layers are trained:

```
┌─────────────────────┐
│  bge-small-zh-v1.5  │  ← FROZEN (90MB, 384-dim, 33M params)
└──────────┬──────────┘
           │ raw embedding (384-dim)
           ▼
┌──────────────────────────────────┐
│  ContrastiveAdapter              │  ← Phase 3 trains this
│  Linear(384, 384) + LayerNorm   │     ~147K params
│  CPU training < 30 seconds       │     learns domain-specific similarity
└──────────┬───────────────────────┘
           │ adapted embedding (384-dim)
           ▼
┌──────────────────────────────────┐
│  FeatureReRanker                 │  ← Phase 2 trains this
│  LogisticRegression              │     ~10 weights
│  CPU training < 1 second         │     learns which feature combinations
│                                  │     predict true duplicates
└──────────┬───────────────────────┘
           ▼
     Final ranked results
```

Safety: adapter can be deleted at any time to revert to baseline behavior.

## Data Model

### New Tables (in `database/ticket_embeddings.db`)

```sql
-- Feedback records from user interactions
CREATE TABLE IF NOT EXISTS feedback_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text  TEXT NOT NULL,
    query_hash  TEXT NOT NULL,              -- MD5(query_text)
    ticket_id   TEXT NOT NULL,
    signal      TEXT NOT NULL CHECK(signal IN ('positive','negative','click')),
    base_score  REAL,                       -- original embedding similarity
    rank_pos    INTEGER,                    -- position in result list (0-indexed)
    user_id     TEXT,                       -- BMW SSO identifier
    is_valid    INTEGER DEFAULT 1,          -- 0 = flagged by anti-noise guard
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fb_query ON feedback_records(query_hash);
CREATE INDEX IF NOT EXISTS idx_fb_ticket ON feedback_records(ticket_id);
CREATE INDEX IF NOT EXISTS idx_fb_user_time ON feedback_records(user_id, created_at);

-- Trained re-ranker model snapshots
CREATE TABLE IF NOT EXISTS reranker_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phase       TEXT NOT NULL,              -- 'click_boost' | 'feature' | 'adapter'
    model_blob  BLOB,                       -- pickled sklearn model or numpy weights
    metrics     TEXT,                       -- JSON: {ndcg, precision_at_3, mrr, train_size}
    feedback_count INTEGER,                 -- number of feedback records used
    created_at  REAL NOT NULL
);

-- Contrastive adapter projection weights
CREATE TABLE IF NOT EXISTS adapter_weights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    weight_matrix   BLOB NOT NULL,          -- float32[384×384] as bytes
    bias_vector     BLOB,                   -- float32[384] as bytes (nullable)
    loss_history    TEXT,                    -- JSON array of per-epoch losses
    train_pairs     INTEGER,                -- number of training triplets
    ndcg_score      REAL,                   -- validation NDCG@10
    created_at      REAL NOT NULL
);
```

### Signal Weights

| Signal | Semantic | Weight in Training |
|--------|----------|-------------------|
| `positive` (👍) | "This result is relevant/duplicate" | label = 1, weight = 1.0 |
| `negative` (👎) | "This result is not relevant" | label = 0, weight = 1.0 |
| `click` | "User clicked to inspect this result" | label = 1, weight = 0.3 |

## Phase 1: ClickBoostReRanker (0-50 Feedback)

### Behavior

For each candidate in the coarse top-50, look up its ticket_id in feedback history and compute a frequency-based boost:

```python
positive_count = count(signal in ('positive', 'click') for this ticket_id)
negative_count = count(signal == 'negative' for this ticket_id)
denominator = positive_count + negative_count + 1  # +1 smoothing

positive_rate = positive_count / denominator
boost = (positive_rate - 0.5) * 0.15  # range: [-0.075, +0.075]

final_score = clamp(base_score + boost, 0.0, 1.0)
```

### Properties

- **Zero training cost**: pure lookup + arithmetic
- **Immediate effect**: a single feedback changes the next search
- **Bounded impact**: maximum ±0.075 score change — cannot dominate over embedding similarity
- **Per-ticket**: each ticket has independent statistics, no cross-contamination

## Phase 2: FeatureReRanker (50-200 Feedback)

### Feature Vector (per query-candidate pair)

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 1 | `base_similarity` | float | Frozen embedding cosine similarity |
| 2 | `project_match` | binary | Hint project matches candidate project |
| 3 | `pu_match` | binary | Hint PU matches candidate PU |
| 4 | `ecu_match` | binary | Hint ECU matches candidate ECU |
| 5 | `lead_model_match` | binary | Hint lead_model matches candidate lead_model |
| 6 | `token_overlap` | float | Jaccard-like overlap of query tokens in candidate text |
| 7 | `rank_position` | float | Normalized position in coarse results (0.0 = top) |
| 8 | `candidate_popularity` | float | Historical positive rate for this ticket (Phase 1 stat) |
| 9 | `query_length_norm` | float | Normalized query text length |

### Training

- **Model**: `sklearn.linear_model.LogisticRegression(class_weight='balanced', max_iter=200)`
- **Labels**: positive/click → 1, negative → 0
- **Sample weights**: click signals weighted 0.3, explicit signals weighted 1.0
- **Validation**: 80/20 stratified split, compute NDCG@10 on held-out set
- **Output**: `model.predict_proba(X)[:, 1]` as re-rank score

### Application

```python
coarse_candidates = index.search(query, top_k=50)  # frozen embedding search
features = extract_features(query, hints, coarse_candidates)
rerank_scores = reranker_model.predict_proba(features)[:, 1]
# Blend: 60% rerank + 40% base_similarity for stability
final_scores = 0.6 * rerank_scores + 0.4 * base_similarities
# Sort descending, return top_k
```

## Phase 3: ContrastiveAdapter (200+ Feedback)

### Architecture

```
frozen_embedding (384) → Linear(384, 384) → LayerNorm → adapted_embedding (384)
```

- Parameters: 384 × 384 + 384 (bias) = **147,840 params**
- Initialized as identity matrix + zero bias (initial pass-through)

### Training Data Construction

From feedback records, construct triplets:

- **Anchor**: query text embedding (frozen)
- **Positive**: embedding of a ticket marked 👍 or clicked for that query
- **Negative**: embedding of a ticket marked 👎 for that query, OR the lowest-ranked un-clicked candidate from the same query (hard negative mining)

Minimum requirement: 200 triplets (may come from fewer feedback records through combinatorial expansion).

### Loss Function

Triplet margin loss:

$$\mathcal{L} = \max(0, \|f(a) - f(p)\|_2 - \|f(a) - f(n)\|_2 + \alpha)$$

where $f(x) = \text{LayerNorm}(W \cdot x + b)$, $\alpha = 0.2$

### Training Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Optimizer | Adam (lr=1e-3) | Standard for small models |
| Batch size | 32 | Fits CPU memory easily |
| Epochs | 20 | Sufficient for 147K params |
| Early stopping | patience=3 on validation loss | Prevent overfitting |
| Weight init | W=identity, b=zeros | Start as pass-through |
| Device | CPU | ~30 seconds for 1000 triplets |

### Inference

```python
# Pre-compute once after adapter training:
adapted_matrix = embedding_matrix @ W.T + b                    # (N, 384)
adapted_matrix /= np.linalg.norm(adapted_matrix, axis=1, keepdims=True)

# Per query:
adapted_query = (query_vec @ W.T + b)
adapted_query /= np.linalg.norm(adapted_query)
sims = adapted_matrix @ adapted_query.T  # cosine similarity
```

Cost: one extra matrix multiply during index build, zero extra cost per query (pre-computed).

### Stacking with Phase 2

When Phase 3 is active, both layers are applied:

```
Frozen embedding → Adapter projection → Cosine search (top-50)
                                              │
                                              ▼
                                   FeatureReRanker (top-K)
```

The adapter improves the recall quality of the coarse search, while the re-ranker fine-tunes the final ranking.

### PyTorch-Free Fallback

If `torch` is not available, the adapter trains via pure numpy gradient descent:

```python
# Forward pass
projected = X @ W.T + b
norm = np.linalg.norm(projected, axis=1, keepdims=True) + 1e-8
out = projected / norm

# Triplet loss + manual backward pass
# Adam optimizer implemented in ~40 lines of numpy
```

This ensures the feature works without adding PyTorch as a dependency.

## Automatic Training Trigger

```python
class TrainingScheduler:
    PHASE_THRESHOLDS = {
        'click_boost': 0,      # always active
        'feature': 50,         # activate LogReg at 50 feedback records
        'adapter': 200,        # activate adapter at 200 feedback records
    }
    RETRAIN_INTERVAL = 20      # retrain every 20 new feedback records

    def current_phase(self, total_feedback: int) -> str:
        if total_feedback >= 200:
            return 'adapter'
        if total_feedback >= 50:
            return 'feature'
        return 'click_boost'

    def should_retrain(self, total_feedback: int, last_train_count: int) -> bool:
        return total_feedback - last_train_count >= self.RETRAIN_INTERVAL
```

- Training executes in a **background thread**, does not block search requests
- New model is validated before deployment (see Safety Guard below)
- Active model swaps atomically via reference replacement

## Anti-Noise Guard

Designed for the **internal BMW user base** — trusted users, low malice risk. Guard focuses on accidental errors and model safety, not adversarial defense.

### Flip Detection

If a user submits opposite signals for the same `(query_hash, ticket_id)` within 5 minutes, discard the earlier record and keep only the correction:

```python
FLIP_WINDOW_SECONDS = 300

# On new feedback:
recent = SELECT * FROM feedback_records
         WHERE query_hash=? AND ticket_id=? AND user_id=?
         AND created_at > (now - FLIP_WINDOW)
         ORDER BY created_at DESC LIMIT 1

if recent and recent.signal != new_signal:
    UPDATE feedback_records SET is_valid=0 WHERE id=recent.id
    # new feedback is inserted as usual
```

### Rate Limiting

```python
MAX_FEEDBACK_PER_HOUR = 50  # per user

count = SELECT COUNT(*) FROM feedback_records
        WHERE user_id=? AND created_at > (now - 3600)

if count >= MAX_FEEDBACK_PER_HOUR:
    return {"accepted": False, "reason": "rate_limit"}
```

### Model Rollback Safety Net

```python
class ModelSafetyGuard:
    MAX_NDCG_REGRESSION = 0.05  # allow at most 5% NDCG drop
    MAX_MODEL_VERSIONS = 3       # keep 3 most recent valid models

    def should_deploy(self, old_metrics: dict, new_metrics: dict) -> bool:
        if old_metrics is None:
            return True  # first model, always deploy
        if new_metrics['ndcg'] < old_metrics['ndcg'] - self.MAX_NDCG_REGRESSION:
            logger.warning(
                "New model rejected: NDCG %.3f < baseline %.3f - %.3f",
                new_metrics['ndcg'], old_metrics['ndcg'], self.MAX_NDCG_REGRESSION
            )
            return False
        return True
```

If a new model fails validation, the previous model remains active. The last 3 valid model snapshots are kept in the `reranker_models` table for manual rollback.

## Evaluation Metrics

Computed on the 20% held-out validation set during each training cycle:

| Metric | Formula | Target |
|--------|---------|--------|
| NDCG@10 | Normalized Discounted Cumulative Gain at rank 10 | > 0.7 |
| Precision@3 | Fraction of top-3 results with positive feedback | > 0.6 |
| MRR | Mean Reciprocal Rank of first positive result | > 0.5 |
| vs Baseline | NDCG improvement over no-reranker baseline | > 0% (monotonic) |

Metrics are stored as JSON in `reranker_models.metrics` for trend tracking.

## Integration Points

### 1. DuplicateIssueIndex.search() Modification

```python
def search(self, query, hints=None, top_k=10):
    # Step 1: Coarse search (unchanged, frozen embedding)
    coarse_top = 50
    coarse_results = self._coarse_search(query, hints, top_k=coarse_top)

    # Step 2: Progressive re-rank (new)
    reranker = get_progressive_reranker()
    if reranker and reranker.ready:
        return reranker.rerank(query, coarse_results, hints, top_k=top_k)

    return coarse_results[:top_k]
```

### 2. Feedback API (Agent Tool)

New tool `submit_search_feedback` exposed via the agent tool system:

```python
{
    "name": "submit_search_feedback",
    "parameters": {
        "query_text": str,       # original search query
        "ticket_id": str,        # candidate ticket ID
        "signal": str,           # 'positive' | 'negative' | 'click'
        "base_score": float,     # optional: original similarity score
        "rank_pos": int,         # optional: position in result list
    }
}
```

### 3. Agent Tool Response Extension

`search_similar_issues` tool response adds a `search_id` field:

```python
{
    "success": True,
    "result": {
        "search_id": "abc123",   # NEW: for linking feedback to this search
        "candidates": [...],
        "model_phase": "feature", # NEW: current reranker phase
        "feedback_count": 87      # NEW: total feedback collected
    }
}
```

## File Structure

```
TPMDashbaord/
├── feedback_store.py              # NEW: FeedbackStore, FeedbackGuard, TrainingScheduler
├── progressive_reranker.py        # NEW: ProgressiveReRanker, ClickBoostReRanker,
│                                  #       FeatureReRanker, ContrastiveAdapter,
│                                  #       ModelSafetyGuard
├── duplicate_issue_finder.py      # MODIFIED: integrate reranker into search()
├── tests/
│   ├── test_feedback_store.py     # NEW: feedback CRUD, flip detection, rate limiting
│   └── test_progressive_reranker.py  # NEW: all 3 phases, safety guard, metric calc
└── database/
    └── ticket_embeddings.db       # EXTENDED: 3 new tables
```

## User Experience Signals

To make users perceive the model "getting smarter":

1. **Immediate confirmation**: After 👍/👎, respond with feedback count:
   > "感谢反馈！已有 47 条学习记录，下次搜索将更精准。"

2. **Phase milestone notification**: When crossing thresholds:
   > "🎯 模型已完成第 2 阶段升级（基于 52 条团队反馈），搜索精度提升约 15%"

3. **Result provenance tag**: On re-ranked results:
   > ⚡ 此结果基于团队历史反馈优先推荐

These are returned as metadata in the tool response, rendered by the Agent UI.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Insufficient feedback volume | Stuck in Phase 1 | Phase 1 still provides value; click signals are collected passively |
| Adapter overfits to small dataset | Worse than baseline | Identity init + safety guard prevents deployment of degraded models |
| sklearn not installed | Phase 2 unavailable | Graceful degradation to Phase 1 only (consistent with existing tier system) |
| torch not installed | Phase 3 unavailable | Numpy fallback for adapter training; or stay at Phase 2 |
| Training blocks search | Latency spike | Background thread + atomic swap; search uses old model during training |
| Database grows large | Disk usage | Feedback records are tiny (~200 bytes each); 10K records < 2MB |

## Dependencies

### Required (already in project)

- `numpy` — matrix operations, adapter inference
- `pandas` — data manipulation
- `sqlite3` — persistence (stdlib)
- `sklearn` — LogisticRegression, cosine_similarity (already optional dependency)

### Optional (new, for Phase 3 adapter)

- `torch` — preferred for contrastive adapter training (not required; numpy fallback exists)

No new required dependencies are introduced.
