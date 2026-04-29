# Duplicate Feedback UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured duplicate-search result cards with per-ticket `👍 匹配` and `👎 不匹配` feedback actions in Agent chat for the local duplicate-search path.

**Architecture:** Keep ordinary chat messages unchanged, but allow a new assistant message subtype for duplicate-search results that carries structured candidate payloads. Render that subtype as a summary block plus candidate cards, persist feedback through `FeedbackStore.submit_feedback()`, and keep the latest duplicate-result context in a dedicated Dash store so button clicks never need to parse natural-language text.

**Tech Stack:** Python, Dash, dcc.Store, pattern-matching callbacks, sqlite3, unittest, pandas

---

## File Structure

### Files to modify

- `agent/legacy/ai_chat_manager_legacy.py`
  Responsibility: build the structured duplicate-search assistant message, define duplicate result helpers, add the extra Dash store, render duplicate result cards, and register the button callback.

### Files to create

- `tests/test_duplicate_feedback_ui.py`
  Responsibility: verify structured payload generation, renderer output shape, and feedback submission wiring against `FeedbackStore`.

### Files to read while implementing

- `feedback_store.py`
  Responsibility: existing persistence contract for `submit_feedback()`.
- `duplicate_issue_finder.py`
  Responsibility: source of candidate fields used in payload generation.
- `docs/superpowers/specs/2026-04-29-duplicate-feedback-ui-design.md`
  Responsibility: approved scope and acceptance criteria.

---

### Task 1: Add Duplicate Result Payload Helpers

**Files:**
- Modify: `agent/legacy/ai_chat_manager_legacy.py`
- Test: `tests/test_duplicate_feedback_ui.py`

- [ ] **Step 1: Write the failing payload-generation tests**

```python
import unittest

from agent.legacy.ai_chat_manager_legacy import (
    _build_duplicate_summary_text,
    _build_duplicate_result_payload,
)
from duplicate_issue_finder import DuplicateCandidate


class TestDuplicateFeedbackPayload(unittest.TestCase):
    def test_build_duplicate_result_payload_includes_feedback_fields(self):
        candidates = [
            DuplicateCandidate(
                score_1_10=9,
                similarity=0.88,
                ticket_id="DEF-1001",
                name="Route planning failed",
                project="IDCEVO",
                pu="26-07",
                status_phase="03-In Analysis",
                snippet="Route planning failed after destination input.",
            )
        ]

        payload = _build_duplicate_result_payload(
            query_text="IDCEVO 26/07 route planning failed",
            dashboard_type="defect",
            candidates=candidates,
        )

        self.assertEqual(payload["query_text"], "IDCEVO 26/07 route planning failed")
        self.assertEqual(payload["dashboard_type"], "defect")
        self.assertEqual(payload["candidates"][0]["ticket_id"], "DEF-1001")
        self.assertEqual(payload["candidates"][0]["rank_pos"], 0)
        self.assertAlmostEqual(payload["candidates"][0]["similarity"], 0.88)

    def test_build_duplicate_summary_text_contains_conclusion_and_next_step(self):
        candidates = [
            DuplicateCandidate(
                score_1_10=9,
                similarity=0.88,
                ticket_id="DEF-1001",
                name="Route planning failed",
                project="IDCEVO",
                pu="26-07",
                status_phase="03-In Analysis",
                snippet="Route planning failed after destination input.",
            )
        ]

        summary = _build_duplicate_summary_text(candidates)

        self.assertIn("【结论】", summary)
        self.assertIn("【下一步】", summary)
        self.assertIn("DEF-1001", summary)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: FAIL because helper functions do not exist yet.

- [ ] **Step 3: Implement minimal payload helpers in `agent/legacy/ai_chat_manager_legacy.py`**

```python
def _build_duplicate_result_payload(query_text: str, dashboard_type: str, candidates: List[Any]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for rank_pos, candidate in enumerate(candidates or []):
        items.append(
            {
                "ticket_id": getattr(candidate, "ticket_id", None),
                "name": getattr(candidate, "name", "") or "",
                "project": getattr(candidate, "project", None),
                "pu": getattr(candidate, "pu", None),
                "status_phase": getattr(candidate, "status_phase", None),
                "snippet": getattr(candidate, "snippet", "") or "",
                "score_1_10": int(getattr(candidate, "score_1_10", 1) or 1),
                "similarity": float(getattr(candidate, "similarity", 0.0) or 0.0),
                "rank_pos": rank_pos,
            }
        )
    return {
        "query_text": str(query_text or "").strip(),
        "dashboard_type": str(dashboard_type or "general"),
        "candidates": items,
    }
```

- [ ] **Step 4: Add the summary helper with the existing recommendation rules**

```python
def _build_duplicate_summary_text(candidates: List[Any]) -> str:
    best = max((int(getattr(c, "score_1_10", 0) or 0) for c in (candidates or [])), default=0)
    if best >= 8:
        suggestion = "不建议提票"
        reason = "与已有问题高度相似，建议优先合并/追加信息"
    elif best <= 6:
        suggestion = "可以提票"
        reason = "未发现高度相似的已知问题"
    else:
        suggestion = "需要补充信息后再判断"
        reason = "相似度中等，建议补充复现信息再决定是否新开票"

    lines = ["【结论】", f"- 建议：{suggestion}", f"- 依据：{reason}", "", "【下一步】"]
    if candidates and suggestion == "不建议提票":
        best_candidate = candidates[0]
        tid = f"#{getattr(best_candidate, 'ticket_id', None) or '该相似票'}"
        lines.append(f"- 建议合并到 {tid}：在原票补充你的复现步骤、期望/实际、环境、日志/截图。")
    else:
        lines.append("- 如果仍要提票：建议补充复现步骤、期望/实际、环境信息、日志/截图，并标注 project/PU。")
    return "\n".join(lines).strip()
```

- [ ] **Step 5: Run the focused test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: PASS for the payload-generation tests.

---

### Task 2: Render Structured Duplicate Result Cards

**Files:**
- Modify: `agent/legacy/ai_chat_manager_legacy.py`
- Test: `tests/test_duplicate_feedback_ui.py`

- [ ] **Step 1: Write the failing renderer test**

```python
import unittest
from dash import html

from agent.legacy.ai_chat_manager_legacy import render_duplicate_result_message


class TestDuplicateFeedbackRenderer(unittest.TestCase):
    def test_renderer_outputs_summary_and_candidate_cards(self):
        message = {
            "role": "assistant",
            "type": "duplicate-search-result",
            "content": "【结论】\n- 建议：不建议提票",
            "duplicate_result": {
                "query_text": "IDCEVO 26/07 route planning failed",
                "dashboard_type": "defect",
                "candidates": [
                    {
                        "ticket_id": "DEF-1001",
                        "name": "Route planning failed",
                        "project": "IDCEVO",
                        "pu": "26-07",
                        "status_phase": "03-In Analysis",
                        "snippet": "Route planning failed after destination input.",
                        "score_1_10": 9,
                        "similarity": 0.88,
                        "rank_pos": 0,
                    }
                ],
            },
        }

        component = render_duplicate_result_message(message, chat_id_prefix="defect-chat")

        self.assertIsInstance(component, html.Div)
        component_str = repr(component)
        self.assertIn("DEF-1001", component_str)
        self.assertIn("duplicate-feedback-btn", component_str)
        self.assertIn("👍 匹配", component_str)
        self.assertIn("👎 不匹配", component_str)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: FAIL because the renderer does not exist yet.

- [ ] **Step 3: Add a duplicate-result renderer and feedback button id helper**

```python
def _build_duplicate_feedback_button_id(chat_id_prefix: str, ticket_id: str, signal: str, rank_pos: int) -> Dict[str, Any]:
    return {
        "type": "duplicate-feedback-btn",
        "chat": chat_id_prefix,
        "ticket_id": ticket_id,
        "signal": signal,
        "rank_pos": int(rank_pos),
    }


def render_duplicate_result_message(message: Dict[str, Any], chat_id_prefix: str) -> html.Div:
    payload = dict(message.get("duplicate_result") or {})
    candidates = list(payload.get("candidates") or [])
    cards: List[Any] = []
    for candidate in candidates:
        ticket_id = str(candidate.get("ticket_id") or "")
        cards.append(
            html.Div(
                [
                    html.Div(f"{candidate.get('score_1_10', 1)} 分", style={"fontWeight": "bold"}),
                    html.Div(f"#{ticket_id} - {candidate.get('name', '')}"),
                    html.Div(" / ".join([v for v in [candidate.get('project'), candidate.get('pu'), candidate.get('status_phase')] if v])),
                    html.Div(candidate.get("snippet", ""), style={"color": "#666", "marginTop": "6px"}),
                    html.Div(
                        [
                            html.Button("👍 匹配", id=_build_duplicate_feedback_button_id(chat_id_prefix, ticket_id, "positive", candidate.get("rank_pos", 0)), n_clicks=0),
                            html.Button("👎 不匹配", id=_build_duplicate_feedback_button_id(chat_id_prefix, ticket_id, "negative", candidate.get("rank_pos", 0)), n_clicks=0, style={"marginLeft": "8px"}),
                        ],
                        style={"marginTop": "10px"},
                    ),
                    html.Div(id={"type": "duplicate-feedback-status", "chat": chat_id_prefix, "ticket_id": ticket_id}, style={"marginTop": "8px", "fontSize": "12px"}),
                ],
                style={"padding": "10px", "border": "1px solid #e2e8f0", "borderRadius": "8px", "marginTop": "10px", "backgroundColor": "#ffffff"},
            )
        )
    return html.Div([
        html.Div(message.get("content", ""), style={"whiteSpace": "pre-line"}),
        html.Div(cards, style={"marginTop": "12px"}),
    ])
```

- [ ] **Step 4: Route duplicate-result messages through the shared history renderer**

```python
if msg["role"] == "assistant" and msg.get("type") == "duplicate-search-result":
    chat_history_children.append(render_duplicate_result_message(msg, chat_id_prefix=chat_id_prefix))
elif msg["role"] == "assistant":
    chat_history_children.append(
        html.Div([
            html.I(className=icon_class, style={"marginRight": "8px", "color": icon_color}),
            html.Span(msg["content"], style={"whiteSpace": "pre-line"}),
        ], style=assistant_style)
    )
```

- [ ] **Step 5: Replace the local duplicate-search early-return payload with the new structured message**

```python
duplicate_summary = _build_duplicate_summary_text(candidates)
duplicate_payload = _build_duplicate_result_payload(
    query_text=user_message,
    dashboard_type=dashboard_type,
    candidates=candidates,
)
chat_messages.append(
    {
        "role": "assistant",
        "type": "duplicate-search-result",
        "content": duplicate_summary,
        "duplicate_result": duplicate_payload,
    }
)
```

- [ ] **Step 6: Run the focused test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: PASS for renderer and payload tests.

---

### Task 3: Store Latest Duplicate Context for Button Clicks

**Files:**
- Modify: `agent/legacy/ai_chat_manager_legacy.py`
- Test: `tests/test_duplicate_feedback_ui.py`

- [ ] **Step 1: Write the failing store-shape test**

```python
import unittest

from agent.legacy.ai_chat_manager_legacy import _build_latest_duplicate_result_store


class TestDuplicateFeedbackStoreShape(unittest.TestCase):
    def test_latest_duplicate_result_store_is_keyed_by_ticket_id(self):
        payload = {
            "query_text": "IDCEVO 26/07 route planning failed",
            "dashboard_type": "defect",
            "candidates": [
                {
                    "ticket_id": "DEF-1001",
                    "name": "Route planning failed",
                    "similarity": 0.88,
                    "rank_pos": 0,
                }
            ],
        }

        store = _build_latest_duplicate_result_store(payload)

        self.assertEqual(store["query_text"], "IDCEVO 26/07 route planning failed")
        self.assertIn("DEF-1001", store["candidates_by_ticket"])
        self.assertEqual(store["candidates_by_ticket"]["DEF-1001"]["rank_pos"], 0)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: FAIL because the store helper does not exist yet.

- [ ] **Step 3: Add a dedicated duplicate-result store to the chat stores list**

```python
return [
    dcc.Store(id=f'{chat_id_prefix}-messages', data=[], storage_type='session'),
    dcc.Store(id=f'{chat_id_prefix}-streaming-response', data='', storage_type='session'),
    dcc.Store(id=f'{chat_id_prefix}-streaming-state', data={'active': False, 'task_id': None}, storage_type='session'),
    dcc.Store(id=f'{chat_id_prefix}-latest-duplicate-result', data=None, storage_type='session'),
    dcc.Interval(
        id=f'{chat_id_prefix}-update-interval',
        interval=200,
        n_intervals=0,
        disabled=True,
    ),
]
```

- [ ] **Step 4: Implement the latest-result store helper and write it in the local duplicate branch**

```python
def _build_latest_duplicate_result_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidates = list(payload.get("candidates") or [])
    return {
        "query_text": payload.get("query_text", ""),
        "dashboard_type": payload.get("dashboard_type", "general"),
        "candidates_by_ticket": {
            str(candidate.get("ticket_id") or ""): candidate
            for candidate in candidates
            if candidate.get("ticket_id")
        },
    }
```

Then extend the local duplicate-search return outputs to include:

```python
latest_duplicate_store = _build_latest_duplicate_result_store(duplicate_payload)
return (
    chat_history_children,
    "",
    chat_messages,
    new_streaming_state,
    True,
    "",
    latest_duplicate_store,
)
```

- [ ] **Step 5: Expand the callback signature to output and preserve the new store**

```python
[Output(f'{chat_id_prefix}-history', 'children'),
 Output(f'{chat_id_prefix}-input', 'value'),
 Output(f'{chat_id_prefix}-messages', 'data'),
 Output(f'{chat_id_prefix}-streaming-state', 'data'),
 Output(f'{chat_id_prefix}-update-interval', 'disabled'),
 Output(f'{chat_id_prefix}-status', 'children'),
 Output(f'{chat_id_prefix}-latest-duplicate-result', 'data')]
```

Also read the current store in `State(...)` and preserve it for non-duplicate flows.

- [ ] **Step 6: Run the focused test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: PASS for payload, renderer, and store-shape tests.

---

### Task 4: Wire Feedback Button Callback to `FeedbackStore`

**Files:**
- Modify: `agent/legacy/ai_chat_manager_legacy.py`
- Test: `tests/test_duplicate_feedback_ui.py`

- [ ] **Step 1: Write the failing feedback-submission test**

```python
import os
import tempfile
import unittest

from feedback_store import FeedbackStore
from agent.legacy.ai_chat_manager_legacy import _submit_duplicate_feedback


class TestDuplicateFeedbackSubmission(unittest.TestCase):
    def test_submit_duplicate_feedback_persists_positive_signal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "feedback.db")
            store_payload = {
                "query_text": "IDCEVO 26/07 route planning failed",
                "dashboard_type": "defect",
                "candidates_by_ticket": {
                    "DEF-1001": {
                        "ticket_id": "DEF-1001",
                        "similarity": 0.88,
                        "rank_pos": 0,
                    }
                },
            }

            result = _submit_duplicate_feedback(
                store_payload=store_payload,
                ticket_id="DEF-1001",
                signal="positive",
                feedback_db_path=db_path,
            )

            persisted = FeedbackStore(db_path=db_path).list_feedback(query_text="IDCEVO 26/07 route planning failed")

            self.assertTrue(result["success"])
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["signal"], "positive")
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: FAIL because the submission helper and callback do not exist yet.

- [ ] **Step 3: Add a pure helper for feedback submission so it can be unit-tested without Dash**

```python
def _submit_duplicate_feedback(store_payload: Dict[str, Any], ticket_id: str, signal: str, feedback_db_path: Optional[str] = None) -> Dict[str, Any]:
    from feedback_store import FeedbackStore

    payload = dict(store_payload or {})
    candidates_by_ticket = dict(payload.get("candidates_by_ticket") or {})
    candidate = dict(candidates_by_ticket.get(ticket_id) or {})
    if not payload.get("query_text") or not candidate:
        return {"success": False, "message": "缺少反馈上下文"}

    store = FeedbackStore(db_path=feedback_db_path) if feedback_db_path else FeedbackStore()
    result = store.submit_feedback(
        query_text=str(payload.get("query_text") or ""),
        ticket_id=ticket_id,
        signal=signal,
        base_score=candidate.get("similarity"),
        rank_pos=candidate.get("rank_pos"),
        user_id=None,
    )
    if result.get("accepted"):
        message = "已记录为正向反馈" if signal == "positive" else "已记录为负向反馈"
        return {"success": True, "message": message, "result": result}
    return {"success": False, "message": f"反馈提交失败：{result.get('reason') or 'unknown'}", "result": result}
```

- [ ] **Step 4: Register the pattern-matching callback that updates card status text**

```python
@app.callback(
    Output({"type": "duplicate-feedback-status", "chat": chat_id_prefix, "ticket_id": MATCH}, "children"),
    [Input({"type": "duplicate-feedback-btn", "chat": chat_id_prefix, "ticket_id": MATCH, "signal": ALL, "rank_pos": ALL}, "n_clicks")],
    [State({"type": "duplicate-feedback-btn", "chat": chat_id_prefix, "ticket_id": MATCH, "signal": ALL, "rank_pos": ALL}, "id"),
     State(f'{chat_id_prefix}-latest-duplicate-result', 'data')],
    prevent_initial_call=True,
)
def submit_duplicate_feedback_callback(clicks, button_ids, latest_duplicate_result):
    if not clicks or not any(clicks):
        raise PreventUpdate
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate
    result = _submit_duplicate_feedback(
        store_payload=latest_duplicate_result,
        ticket_id=str(triggered.get("ticket_id") or ""),
        signal=str(triggered.get("signal") or "").lower(),
    )
    return result["message"]
```

- [ ] **Step 5: Run the focused test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py -q`
Expected: PASS for the feedback submission helper and the rest of the focused UI tests.

---

### Task 5: Run Regression and Manual Verification

**Files:**
- Modify as needed: `agent/legacy/ai_chat_manager_legacy.py`
- Test: `tests/test_duplicate_feedback_ui.py`
- Regression: `tests/test_duplicate_issue_tools.py`, `tests/test_enhanced_ai_chat_manager.py`

- [ ] **Step 1: Run the focused and adjacent regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_feedback_ui.py tests/test_duplicate_issue_tools.py tests/test_enhanced_ai_chat_manager.py -q`
Expected: PASS.

- [ ] **Step 2: Run the existing duplicate-search slice to ensure no regression**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_duplicate_issue_finder.py tests/test_progressive_reranker.py tests/test_duplicate_issue_tools.py -q`
Expected: PASS.

- [ ] **Step 3: Start the app and verify the local duplicate path manually**

Run: `python serve_waitress.py --host 0.0.0.0 --port 8051 --threads 8`
Expected: app starts successfully and serves on `http://127.0.0.1:8051/`.

Manual checklist:

```text
1. Open Agent chat and enable “识别已知问题”.
2. Enter a query that returns duplicate candidates.
3. Confirm the assistant summary appears above candidate cards.
4. Confirm each card shows ticket id, title, metadata, snippet, and two buttons.
5. Click “👍 匹配” on one card and confirm “已记录为正向反馈”.
6. Click “👎 不匹配” on another card and confirm “已记录为负向反馈”.
7. Confirm the feedback appears in feedback_records via FeedbackStore or monitor UI.
```

- [ ] **Step 4: Review changed code against the approved spec**

Check these items explicitly:

```text
- Only the local duplicate-search path changed.
- Ordinary assistant text messages still render normally.
- The feedback payload includes query_text, ticket_id, signal, base_score, and rank_pos.
- No database schema change was introduced.
- The latest duplicate-result context is stored structurally, not parsed from visible text.
```
