# Agent Trace Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full, title-free debug event timeline to the chat UI while preserving the existing lightweight streaming response.

**Architecture:** Extend `streaming_data` with an append-only `events` list, translate runtime progress into structured events, and render those events as timeline cards in the existing Dash polling callback. Keep the current reasoning summary as a compact no-title block.

**Tech Stack:** Python, Dash, existing streaming callback architecture, unittest

---

## File Map

- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`
- Reference: `docs/superpowers/specs/2026-04-02-agent-trace-timeline-design.md`

### Task 1: Add Timeline Event Helpers

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering:

```python
def test_append_stream_event_creates_append_only_timeline():
    stream_data = {"events": []}
    first = append_stream_event_to_store(stream_data, kind="route_decision", title="route")
    second = append_stream_event_to_store(stream_data, kind="tool_start", title="tool")
    assert len(stream_data["events"]) == 2
    assert stream_data["events"][0]["id"] == first["id"]
    assert stream_data["events"][1]["id"] == second["id"]


def test_build_timeline_view_models_marks_errors_as_expanded():
    stream_data = {
        "started_at": 100.0,
        "events": [
            {"id": "1", "ts": 101.0, "kind": "error", "title": "tool failed", "status": "error", "summary": "bad"}
        ],
    }
    rows = build_timeline_view_models(stream_data, now_ts=103.0)
    assert rows[0]["expanded"] is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: FAIL with missing helper functions.

- [ ] **Step 3: Write minimal helper implementation**

Add helper functions in `agent/core/enhanced_ai_chat_manager.py` for:

- appending timeline events
- trimming event count
- converting raw events into render-ready view models
- formatting details and elapsed labels

- [ ] **Step 4: Run the test to verify it passes**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

### Task 2: Record Runtime Events

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering:

```python
def test_build_summary_evidence_gaps_for_feature_question_without_feature_fields():
    gaps = infer_summary_evidence_gaps(
        question="3月份showstopper candidate发现了多少 都是哪些功能",
        sql_used="SELECT week, defect_count FROM octane_defects GROUP BY week",
        rows=[{"week": "2026-W10", "defect_count": 228}],
        table_name="octane_defects",
    )
    assert any("功能" in gap for gap in gaps)
    assert any("showstopper" in gap.lower() for gap in gaps)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: FAIL with missing evidence-gap helper.

- [ ] **Step 3: Implement runtime event recording**

Update `agent/core/enhanced_ai_chat_manager.py` so that:

- task initialization records `route_decision`
- agent progress callback records `context_ready`, `plan_created`, `tool_start`, `tool_result`, `replan`, and `llm_phase`
- database-summary flow records `sql_generated`, `sql_result`, `fallback`, and `evidence_gap`
- completed flows record `final_answer`
- error paths record `error`

- [ ] **Step 4: Run the test to verify it passes**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

### Task 3: Render Title-Free Timeline And Reasoning Blocks

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`

- [ ] **Step 1: Write the failing tests**

Add tests covering title-free labels:

```python
def test_build_timeline_view_models_keeps_titles_per_event_but_no_global_heading_text():
    rows = build_timeline_view_models(
        {"started_at": 100.0, "events": [{"id": "1", "ts": 101.0, "kind": "tool_start", "title": "调用工具: query_sqlite", "status": "running"}]},
        now_ts=102.0,
    )
    assert rows[0]["title"] == "调用工具: query_sqlite"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: FAIL until view-model helpers are wired into rendering.

- [ ] **Step 3: Implement rendering changes**

Update `agent/core/enhanced_ai_chat_manager.py` so that:

- the checklist label becomes `显示执行细节`
- reasoning messages render without the `AI思考` header
- a new `timeline` message type renders event cards without a global title
- polling callback updates both reasoning and timeline messages during streaming

- [ ] **Step 4: Run the test to verify it passes**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

### Task 4: Verify Regression Safety

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_enhanced_chat_reasoning.py`

- [ ] **Step 1: Run focused timeline tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_enhanced_chat_reasoning -v`

Expected: PASS.

- [ ] **Step 2: Run existing wrapper regression tests**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_root_wrappers -v`

Expected: PASS.

- [ ] **Step 3: Run a broader chat regression slice if needed**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_harness_router -v`

Expected: PASS.

## Self-Review

### Spec coverage

- append-only event model: covered in Task 1
- route, tool, fallback, evidence gap events: covered in Task 2
- no `AI思考` or `调试时间线` title in chat body: covered in Task 3
- regression verification: covered in Task 4

### Placeholder scan

- No `TODO` or `TBD` placeholders remain
- Commands are explicit
- File paths are explicit

### Type consistency

- Event list is always named `events`
- Render helpers use the same `kind`, `title`, `status`, `summary`, and `details` fields
- Reasoning remains summary-only while timeline is append-only

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-02-agent-trace-timeline.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

This session is proceeding with inline execution.