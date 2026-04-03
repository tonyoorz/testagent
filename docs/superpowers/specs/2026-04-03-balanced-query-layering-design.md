# Balanced Query Layering Design

## Goal

Design a balanced deterministic-first query architecture for TPMDashbaord that improves answer reliability and auditability without sacrificing long-tail coverage.

## Context

The current system already has strong deterministic SQL generation, semantic catalog assets, SQL safety guards, and timeline diagnostics. However, business rules and intent logic are still partially duplicated across modules, and final answer provenance is not consistently exposed.

## Problem Statement

Current behavior risks include:

1. Rule drift from duplicated hint logic in multiple modules.
2. Over-filtering in some semantic/entity slicing scenarios.
3. Inconsistent visibility of data quality and provenance in final answers.
4. Limited anomaly coverage and no strict post-generation evidence verifier.

## Decision

Adopt a balanced strategy:

1. Deterministic-first for structured analysis queries.
2. Constrained LLM fallback for long-tail/unmapped queries.
3. Mandatory evidence scope and uncertainty signaling when confidence is insufficient.

## Non-Goals

1. Replacing all query generation with LLM.
2. Removing deterministic SQL path.
3. Building a separate admin system for query execution.
4. Forcing template-only final responses.

## Architecture

### Layer 1: Query Registry

Purpose: a declarative registry of stable high-frequency query families, not an independent SQL engine.

Registry entry includes:

1. query_family
2. target_table candidates
3. required dimensions/measures
4. parameter slots (time/project/aida/risk/tester)
5. output shape contract
6. business constraints and exclusions

Initial families:

1. trend_by_week
2. risk_ranking
3. aida_distribution
4. tester_performance
5. test_execution

### Layer 2: Unified Intent Builder

Purpose: one canonical intent/hint pipeline that consolidates semantic term mapping and deterministic query hints.

Inputs:

1. user question
2. optional table context
3. optional schema/profile context

Outputs:

1. query_family candidate
2. table_hint
3. time_scope
4. entity filters
5. semantic constraints
6. confidence
7. provenance of matched terms/rules

### Layer 3: Deterministic SQL Main Path

Purpose: generate and execute SQL for structured analysis queries.

Rules:

1. SELECT/WITH only.
2. Registered tables and approved fields only.
3. Read-only execution and SQL sanitation mandatory.
4. Retry strategy keeps current broadening logic for zero-result conditions.

### Layer 4: Constrained LLM Fallback

Purpose: cover long-tail queries when Layer 1-3 confidence is insufficient.

Rules:

1. Strict schema and safety constraints.
2. SQL must be validated before execution.
3. Final answer must include evidence scope and uncertainty markers.
4. If evidence remains insufficient, downgrade to explicit evidence-gap response.

## Routing Policy

### Deterministic-First Query Classes

Always prioritize Layer 1-3 for:

1. trend and period comparisons
2. distribution and breakdown
3. ranking and top-N
4. pass rate, execution status, manual run summaries
5. matrix/severity/aida/risk structured aggregation

### LLM-Eligible Query Classes

Allow Layer 4 for:

1. root-cause style explanations
2. recommendation synthesis
3. metric definition clarification
4. cross-topic, long-tail, weakly structured asks

## Fallback Policy (Balanced)

When deterministic confidence is low or mapping fails:

1. invoke constrained LLM fallback
2. keep answer generation allowed
3. require explicit evidence scope
4. require uncertainty statements for unsupported claims
5. block confident unsupported statements

## Output Governance

Final response should separate:

1. observed facts (rows/aggregates)
2. rule-based interpretation (semantic/business rules)
3. suggestions/inference (explicitly marked)

Minimum provenance payload per answer:

1. sql_used
2. sample_count and total_count
3. key fields used
4. rule_ids or formula references when derived metrics are discussed
5. evidence_gap flags when applicable

## Data Quality Exposure

The runtime should expose at least:

1. null ratio / field usability warnings
2. cardinality hints for grouping dimensions
3. sample-vs-total caveats

This does not require new profiling engines first; it should reuse current profile outputs and make them visible.

## Anomaly Detection Expansion

Extend from fixed heuristics to configurable business anomaly rules:

1. week-over-week surge thresholds (including >=300 percent spikes)
2. sparse-signal suppression
3. seasonality-aware checks (where available)
4. high-risk concentration shifts

## Rollout Plan

Phase 1:

1. add query registry schema and deterministic-first routing switch
2. keep existing deterministic and fallback behavior intact

Phase 2:

1. unify intent/hint extraction into one path
2. remove duplicate hint logic from multiple modules

Phase 3:

1. add provenance/evidence response contract
2. add strict unsupported-claim downgrade behavior

Phase 4:

1. extend anomaly rule coverage
2. run regression and acceptance checks

## Success Metrics

1. deterministic hit-rate for structured queries increases
2. zero-result false negatives decrease
3. unsupported confident statements decrease
4. long-tail coverage remains acceptable (no severe answer-rate drop)

## Acceptance Criteria

1. Structured queries route to deterministic path by default.
2. Long-tail queries still receive answers via constrained fallback when possible.
3. Final responses include evidence scope and uncertainty when needed.
4. No write SQL can execute in any path.
5. Existing deterministic regression suites stay green.

## Risks and Mitigations

1. Risk: routing too strict lowers answer coverage.
Mitigation: balanced fallback policy and phased rollout with metrics.

2. Risk: duplicated logic persists during migration.
Mitigation: enforce single-source intent builder and parity tests.

3. Risk: provenance verbosity harms readability.
Mitigation: concise user-facing summary plus expandable detail view.

## File Touch Scope (Planned)

1. agent/core/deterministic_sql_service.py
2. semantic_catalog/deterministic_query_hints.py
3. semantic_catalog/term_adapter.py
4. agent/core/enhanced_ai_chat_manager.py
5. agent/core/intelligent_agent.py
6. agent/core/sql_runtime_service.py
7. semantic_catalog/datasets.json
8. semantic_catalog/business_rules.json
9. semantic_catalog/metrics.json
10. agent/evaluation/* relevant regression suites
