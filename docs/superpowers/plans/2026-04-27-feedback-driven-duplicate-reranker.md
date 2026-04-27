# Feedback-Driven Duplicate Detection Re-Ranker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add feedback persistence and progressive duplicate-result re-ranking so duplicate search can learn from internal user feedback without changing the base embedding model.

**Architecture:** Keep the current duplicate search pipeline as the coarse retrieval layer. Add a SQLite-backed feedback store and a progressive re-ranker that starts with ticket-level statistical boosts and upgrades to a logistic-regression feature re-ranker when enough feedback exists. Expose a separate feedback-submission tool and extend duplicate search responses with lightweight feedback metadata.

**Tech Stack:** Python, sqlite3, numpy, pandas, sklearn, unittest

---

### Task 1: Feedback Store and Guard

**Files:**
- Create: `feedback_store.py`
- Create: `tests/test_feedback_store.py`

- [ ] Define failing tests for feedback insert, flip detection, rate limiting, and statistics aggregation.
- [ ] Run `python -m unittest tests.test_feedback_store -v` and verify the new tests fail for missing module/symbols.
- [ ] Implement `FeedbackStore`, `FeedbackGuard`, and `TrainingScheduler` with SQLite schema bootstrap in `feedback_store.py`.
- [ ] Run `python -m unittest tests.test_feedback_store -v` and verify pass.

### Task 2: Progressive Re-Ranker Core

**Files:**
- Create: `progressive_reranker.py`
- Create: `tests/test_progressive_reranker.py`

- [ ] Define failing tests for Phase 1 boost behavior, Phase 2 feature extraction/training activation, and safe fallback when sklearn training data is insufficient.
- [ ] Run `python -m unittest tests.test_progressive_reranker -v` and verify fail.
- [ ] Implement `ClickBoostReRanker`, `FeatureReRanker`, `ProgressiveReRanker`, and a minimal `ModelSafetyGuard`.
- [ ] Run `python -m unittest tests.test_progressive_reranker -v` and verify pass.

### Task 3: Duplicate Search Integration

**Files:**
- Modify: `duplicate_issue_finder.py`
- Modify: `tests/test_duplicate_issue_finder.py`

- [ ] Add failing integration tests proving `DuplicateIssueIndex.search()` uses the progressive re-ranker metadata path when enabled and still falls back cleanly when disabled.
- [ ] Run `python -m unittest tests.test_duplicate_issue_finder -v` and verify fail.
- [ ] Implement coarse-search extraction, progressive re-ranker hook-up, and metadata return helpers in `duplicate_issue_finder.py`.
- [ ] Run `python -m unittest tests.test_duplicate_issue_finder -v` and verify pass.

### Task 4: Agent Tool Surface

**Files:**
- Modify: `agent/core/intelligent_agent.py`
- Modify: `agent/tools/__init__.py`
- Create: `agent/tools/analysis/duplicate_feedback.py`
- Modify: `tests/test_enhanced_ai_chat_manager.py`

- [ ] Add failing tests or direct tool-level checks for duplicate search response metadata and feedback submission tool behavior.
- [ ] Run `python -m unittest tests.test_enhanced_ai_chat_manager -v` and verify the new checks fail.
- [ ] Implement `SubmitDuplicateSearchFeedbackTool`, extend duplicate search responses with `model_phase` and `feedback_count`, and register the new packaged tool.
- [ ] Run `python -m unittest tests.test_enhanced_ai_chat_manager -v` and verify pass.

### Task 5: Focused Verification

**Files:**
- Modify as needed from Tasks 1-4 only.

- [ ] Run `python -m unittest tests.test_feedback_store tests.test_progressive_reranker tests.test_duplicate_issue_finder tests.test_enhanced_ai_chat_manager -v`.
- [ ] Run `python -m unittest tests.test_duplicate_issue_finder tests.test_enhanced_ai_chat_manager -v` to re-check the touched integration slice.
- [ ] Review changed files for requirement coverage: feedback persistence, phase detection, reranking, feedback submission, metadata exposure.
