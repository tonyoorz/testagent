# Balanced Query Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement balanced deterministic-first query layering so structured asks reliably use deterministic SQL while long-tail asks remain covered by constrained fallback with explicit evidence and uncertainty controls.

**Architecture:** Add a declarative query registry and a unified intent builder as shared upstream contracts, then route summary and agent SQL paths through deterministic-first strategy. Standardize evidence payloads and unsupported-claim downgrade behavior across both summary and agent flows, and extend anomaly checks through catalog-driven rules.

**Tech Stack:** Python, SQLite, Dash chat orchestration, semantic catalog JSON, unittest

---

## File Map

- Create: `semantic_catalog/query_registry.json`
- Modify: `semantic_catalog/deterministic_query_hints.py`
- Modify: `semantic_catalog/term_adapter.py`
- Modify: `agent/core/deterministic_sql_service.py`
- Modify: `agent/core/sql_runtime_service.py`
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Modify: `agent/core/intelligent_agent.py`
- Modify: `semantic_catalog/business_rules.json`
- Modify: `semantic_catalog/metrics.json`
- Modify: `semantic_catalog/datasets.json` (if new family dimension aliases are required)
- Modify: `agent/evaluation/test_deterministic_sql_service.py`
- Modify: `agent/evaluation/test_semantic_hint_parity.py`
- Modify: `agent/evaluation/test_semantic_term_adapter.py`
- Modify: `agent/evaluation/test_sql_runtime_service.py`
- Modify: `agent/evaluation/test_enhanced_chat_reasoning.py`
- Modify: `agent/evaluation/test_harness_router.py` (only if outer routing changes)
- Modify: `agent/evaluation/run_agent_eval_cases.py`

### Task 1: Add Declarative Query Registry (Layer 1)

**Files:**
- Create: `semantic_catalog/query_registry.json`
- Modify: `semantic_catalog/deterministic_query_hints.py`
- Test: `agent/evaluation/test_semantic_hint_parity.py`

- [ ] **Step 1: Write failing registry-loading tests**

Add tests covering:

```python
def test_query_registry_contains_required_families():
    registry = load_query_registry()
    assert "trend_by_week" in registry
    assert "risk_ranking" in registry
    assert "aida_distribution" in registry
    assert "tester_performance" in registry
    assert "test_execution" in registry


def test_query_registry_entry_has_contract_keys():
    entry = load_query_registry()["trend_by_week"]
    assert "target_tables" in entry
    assert "required_dimensions" in entry
    assert "parameter_slots" in entry
    assert "output_contract" in entry
    assert "constraints" in entry
```

- [ ] **Step 2: Run tests to verify failure**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_semantic_hint_parity -v`

Expected: FAIL with missing `load_query_registry` and/or missing registry file.

- [ ] **Step 3: Implement registry file and loader**

Implement:
- `semantic_catalog/query_registry.json` with all five initial query families
- `load_query_registry()` in `semantic_catalog/deterministic_query_hints.py`
- minimal validation of required keys and fallback to empty dict on malformed entries

- [ ] **Step 4: Re-run tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_semantic_hint_parity -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add semantic_catalog/query_registry.json semantic_catalog/deterministic_query_hints.py agent/evaluation/test_semantic_hint_parity.py
git commit -m "feat: add declarative query registry for deterministic families"
```

### Task 2: Build Unified Intent Builder (Layer 2)

**Files:**
- Modify: `semantic_catalog/term_adapter.py`
- Modify: `semantic_catalog/deterministic_query_hints.py`
- Modify: `agent/core/deterministic_sql_service.py`
- Test: `agent/evaluation/test_semantic_term_adapter.py`
- Test: `agent/evaluation/test_deterministic_sql_service.py`

- [ ] **Step 1: Write failing intent-contract tests**

Add tests covering:

```python
def test_unified_intent_builder_returns_expected_contract():
    result = build_unified_query_intent(
        question="compare weekly defect trend for march",
        table_hint="octane_defects",
        schema_context={"columns": ["year", "week", "severity"]},
    )
    assert "query_family" in result
    assert "table_hint" in result
    assert "time_scope" in result
    assert "entity_filters" in result
    assert "semantic_constraints" in result
    assert "confidence" in result
    assert "provenance" in result


def test_extract_query_hints_uses_unified_intent_builder_when_available():
    hints = extract_query_hints("show risk ranking by tester", table_name="octane_defects")
    assert hints.get("query_family") in {"risk_ranking", "tester_performance"}
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_semantic_term_adapter agent.evaluation.test_deterministic_sql_service -v`

Expected: FAIL with missing builder and/or missing `query_family` in hints.

- [ ] **Step 3: Implement unified intent builder and integration**

Implement:
- `build_unified_query_intent(...)` in `semantic_catalog/term_adapter.py`
- contract includes `query_family`, `table_hint`, `time_scope`, `entity_filters`, `semantic_constraints`, `confidence`, `provenance`
- `extract_query_hints(...)` in `agent/core/deterministic_sql_service.py` consumes unified intent first, then preserves existing behavior for backward compatibility

- [ ] **Step 4: Re-run focused tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_semantic_term_adapter agent.evaluation.test_deterministic_sql_service -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add semantic_catalog/term_adapter.py semantic_catalog/deterministic_query_hints.py agent/core/deterministic_sql_service.py agent/evaluation/test_semantic_term_adapter.py agent/evaluation/test_deterministic_sql_service.py
git commit -m "feat: unify intent and hint extraction contract"
```

### Task 3: Enforce Deterministic-First Routing (Layer 3)

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Modify: `agent/core/deterministic_sql_service.py`
- Modify: `agent/core/intelligent_agent.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`
- Test: `agent/evaluation/test_deterministic_sql_service.py`

- [ ] **Step 1: Write failing deterministic-first routing tests**

Add tests covering:

```python
def test_summary_path_prefers_deterministic_sql_for_structured_query():
    decision = decide_query_execution_strategy(
        question="weekly trend by severity in 2026",
        unified_intent={"query_family": "trend_by_week", "confidence": 0.92},
    )
    assert decision["strategy"] == "deterministic_first"


def test_summary_path_allows_llm_fallback_when_deterministic_confidence_low():
    decision = decide_query_execution_strategy(
        question="what root cause explains this volatility",
        unified_intent={"query_family": None, "confidence": 0.42},
    )
    assert decision["strategy"] == "constrained_fallback"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning agent.evaluation.test_deterministic_sql_service -v`

Expected: FAIL with missing strategy helper and current order mismatch.

- [ ] **Step 3: Implement deterministic-first strategy and keep balanced fallback**

Implement:
- `decide_query_execution_strategy(...)` in deterministic SQL service or chat manager helper block
- in `start_db_summary_streaming`, switch order to deterministic SQL first for structured classes
- preserve constrained fallback to `query_sqlite_with_fix` when deterministic confidence is low or zero rows after broadening
- in `SQLiteNLQueryWithFixTool.execute`, consume same strategy metadata for parity with summary path

- [ ] **Step 4: Re-run tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning agent.evaluation.test_deterministic_sql_service -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/core/enhanced_ai_chat_manager.py agent/core/deterministic_sql_service.py agent/core/intelligent_agent.py agent/evaluation/test_enhanced_chat_reasoning.py agent/evaluation/test_deterministic_sql_service.py
git commit -m "feat: enforce deterministic-first routing with balanced fallback"
```

### Task 4: Add Evidence Contract and Output Governance (Layer 4 support)

**Files:**
- Modify: `agent/core/sql_runtime_service.py`
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Modify: `agent/core/intelligent_agent.py`
- Test: `agent/evaluation/test_sql_runtime_service.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`

- [ ] **Step 1: Write failing evidence-contract tests**

Add tests covering:

```python
def test_build_evidence_bundle_includes_minimum_fields():
    payload = build_evidence_bundle(
        sql_used="SELECT severity, COUNT(*) AS c FROM octane_defects GROUP BY severity",
        rows=[{"severity": "high", "c": 12}],
        total_count=200,
        key_fields=["severity", "c"],
        rule_refs=["severity_distribution_rule"],
    )
    assert payload["sql_used"].startswith("SELECT")
    assert payload["sample_count"] == 1
    assert payload["total_count"] == 200
    assert payload["key_fields"] == ["severity", "c"]
    assert payload["rule_ids"] == ["severity_distribution_rule"]
    assert "evidence_gap" in payload


def test_structured_summary_text_contains_uncertainty_when_evidence_gap_present():
    text = _build_structured_summary_text(
        question="why did this happen",
        rows=[{"week": "2026-W10", "defect_count": 1}],
        sql_used="SELECT week, defect_count FROM octane_defects",
        evidence_gaps=["insufficient root-cause fields"],
    )
    assert "uncertainty" in text.lower() or "insufficient" in text.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_sql_runtime_service agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: FAIL with missing `build_evidence_bundle` and/or missing uncertainty behavior.

- [ ] **Step 3: Implement shared evidence payload and rendering contract**

Implement:
- `build_evidence_bundle(...)` in `agent/core/sql_runtime_service.py`
- summary and agent outputs both include: `sql_used`, `sample_count`, `total_count`, `key_fields`, `rule_ids`, `evidence_gap`
- `_build_structured_summary_text` enforces separation: observed facts, rule-based interpretation, suggestions/inference

- [ ] **Step 4: Re-run tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_sql_runtime_service agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/core/sql_runtime_service.py agent/core/enhanced_ai_chat_manager.py agent/core/intelligent_agent.py agent/evaluation/test_sql_runtime_service.py agent/evaluation/test_enhanced_chat_reasoning.py
git commit -m "feat: add shared evidence contract and governed output structure"
```

### Task 5: Add Unsupported-Claim Downgrade Enforcement

**Files:**
- Modify: `agent/evaluation/agent_critic.py`
- Modify: `agent/core/intelligent_agent.py`
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`
- Test: `agent/evaluation/run_agent_eval_cases.py`

- [ ] **Step 1: Write failing unsupported-claim tests**

Add tests covering:

```python
def test_rule_based_critic_flags_confident_claim_without_evidence():
    verdict = RuleBasedCritic().critique(
        answer_text="This definitively proves root cause X",
        evidence_bundle={"evidence_gap": True, "sample_count": 1, "total_count": 500},
    )
    assert verdict.should_refuse is True


def test_summary_path_downgrades_confident_language_on_evidence_gap():
    text = downgrade_unsupported_claims(
        answer_text="This is definitely caused by team A",
        evidence_bundle={"evidence_gap": True},
    )
    assert "cannot be confirmed" in text.lower() or "insufficient" in text.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: FAIL with missing downgrade behavior.

- [ ] **Step 3: Implement downgrade in both agent and summary modes**

Implement:
- extend `RuleBasedCritic.critique` to read evidence bundle and strong-claim patterns
- enforce downgrade/refusal path in `IntelligentAgent.process`
- apply summary-mode equivalent in `enhanced_ai_chat_manager` before final emission

- [ ] **Step 4: Re-run tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

- [ ] **Step 5: Run eval gate and commit**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m agent.evaluation.run_agent_eval_cases`

Expected: improved unsupported-claim compliance metrics.

```bash
git add agent/evaluation/agent_critic.py agent/core/intelligent_agent.py agent/core/enhanced_ai_chat_manager.py agent/evaluation/test_enhanced_chat_reasoning.py agent/evaluation/run_agent_eval_cases.py
git commit -m "feat: enforce unsupported-claim downgrade from evidence gaps"
```

### Task 6: Expand Anomaly Rules via Catalog

**Files:**
- Modify: `semantic_catalog/business_rules.json`
- Modify: `semantic_catalog/metrics.json`
- Modify: `agent/core/intelligent_agent.py`
- Test: `agent/evaluation/test_agentic_runtime.py` (or create `agent/evaluation/test_anomaly_rules.py`)

- [ ] **Step 1: Write failing anomaly-rule tests**

Add tests covering:

```python
def test_anomaly_detector_flags_week_over_week_spike_over_300_percent():
    insights = evaluate_anomaly_rules([
        {"week": "2026-W10", "value": 10},
        {"week": "2026-W11", "value": 45},
    ])
    assert any(i.get("rule_id") == "wow_spike_300pct" for i in insights)


def test_anomaly_detector_suppresses_sparse_signal():
    insights = evaluate_anomaly_rules([
        {"week": "2026-W10", "value": 1},
        {"week": "2026-W11", "value": 2},
    ])
    assert not any(i.get("severity") == "high" for i in insights)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_agentic_runtime -v`

Expected: FAIL with missing `evaluate_anomaly_rules`/config-driven logic.

- [ ] **Step 3: Implement catalog-driven anomaly evaluation**

Implement:
- anomaly rule definitions in `business_rules.json` (wow spike, sparse suppression, risk concentration shift)
- metric references in `metrics.json`
- anomaly evaluator consumed by `TrendAnalysisTool._generate_insights`

- [ ] **Step 4: Re-run tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_agentic_runtime -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add semantic_catalog/business_rules.json semantic_catalog/metrics.json agent/core/intelligent_agent.py agent/evaluation/test_agentic_runtime.py
git commit -m "feat: add configurable anomaly rule evaluation"
```

### Task 7: Acceptance Verification and Rollout Guardrails

**Files:**
- Modify: `agent/evaluation/test_harness_router.py` (if mode routing changed)
- Modify: `agent/evaluation/run_agent_eval_cases.py`

- [ ] **Step 1: Run core deterministic and semantic suites**

Run:
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_deterministic_sql_service -v`
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_semantic_hint_parity -v`
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_semantic_term_adapter -v`

Expected: PASS.

- [ ] **Step 2: Run summary and SQL runtime suites**

Run:
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_sql_runtime_service -v`
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

- [ ] **Step 3: Run routing and agent eval checks**

Run:
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_harness_router -v`
- `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m agent.evaluation.run_agent_eval_cases`

Expected:
- no write SQL in any path
- structured asks choose deterministic-first
- long-tail asks still receive constrained fallback answers
- unsupported confident statements decrease in eval output

- [ ] **Step 4: Final commit**

```bash
git add agent/evaluation/run_agent_eval_cases.py agent/evaluation/test_harness_router.py
git commit -m "test: add acceptance gates for balanced query layering"
```

## Rollout Notes

- Phase 1 toggle: keep behavior-compatible fallback path enabled while introducing registry and strategy helper.
- Phase 2 migration: remove duplicate hint logic only after parity tests are green in two consecutive runs.
- Phase 3 governance: turn on strict unsupported-claim downgrade once evidence contract is present in both summary and agent paths.
- Phase 4 anomaly expansion: monitor false positive rate before raising rule sensitivity.

## Self-Review

### Spec coverage

- Layer 1 query registry: Task 1
- Layer 2 unified intent builder: Task 2
- Layer 3 deterministic-first routing: Task 3
- Layer 4 constrained fallback with evidence signaling: Tasks 3 and 4
- output governance and provenance payload: Task 4
- unsupported-claim downgrade: Task 5
- anomaly rule expansion: Task 6
- acceptance criteria and regression safety: Task 7

### Placeholder scan

- No `TODO`, `TBD`, or deferred placeholders remain.
- All tasks include explicit file targets and runnable commands.
- Test-first ordering is preserved for each implementation task.

### Type consistency

- Unified intent contract keys are consistent across tasks: `query_family`, `table_hint`, `time_scope`, `entity_filters`, `semantic_constraints`, `confidence`, `provenance`.
- Evidence contract keys are consistent across tasks: `sql_used`, `sample_count`, `total_count`, `key_fields`, `rule_ids`, `evidence_gap`.
- Deterministic routing strategy labels are consistent: `deterministic_first`, `constrained_fallback`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-03-balanced-query-layering-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?