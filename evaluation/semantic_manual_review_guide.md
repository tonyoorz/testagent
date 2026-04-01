# Semantic Manual Review Guide

This guide is for manually auditing and tuning semantic/business understanding.

## 1) Source of truth files

- Rule definitions: semantic_catalog/business_rules.json
- Semantic matcher/runtime: semantic_catalog/runtime.py
- Deterministic SQL logic: agent/core/enhanced_ai_chat_manager.py
- Regression questions and outputs: evaluation/deterministic_sql_regression_report.json

## 2) Manual review workflow

1. Run semantic review report:
   - python evaluation/run_semantic_manual_review.py
2. Open report files:
   - evaluation/semantic_manual_review_report.md
   - evaluation/semantic_manual_review_report.json
3. Check Rule Health section:
   - duplicate IDs must be zero
   - invalid items must be zero
4. Check Never Hit Rules section:
   - if a rule never hits, verify its trigger_terms and aliases
5. Check Per Question Rule Hits:
   - ensure expected rules appear for each question
6. Update business rules in semantic_catalog/business_rules.json:
   - tune trigger_terms first
   - tune aliases second
   - tune sql_guardrails for query constraints
7. Re-run deterministic regression:
   - python evaluation/run_deterministic_sql_regression.py
8. Compare pass/nonempty and SQL text changes.

## 3) Rule tuning checklist

- Rule ID is stable and unique.
- Description is business-meaningful and testable.
- trigger_terms include both Chinese and English phrases used by users.
- aliases include dashboard language used in UI labels.
- rules contain concrete definitions, not generic advice.
- sql_guardrails explicitly prevent common SQL mistakes.

## 4) Practical tuning patterns

- If a rule never hits:
  - Add user-facing phrasing from real questions into trigger_terms.
- If wrong rules hit too often:
  - Remove overly broad generic terms.
  - Move generic words from trigger_terms to description.
- If SQL over-filters and returns empty:
  - Add guardrails to forbid intent/polite words as entity filters.
- If table routing is wrong:
  - Add routing keywords and guardrails aligned with source data model.

## 5) Recommended cadence

- Small iteration: edit 1-3 rules, rerun both reports.
- Commit only when:
  - semantic_manual_review_report has no validation issues
  - deterministic_sql_regression remains stable or better.
