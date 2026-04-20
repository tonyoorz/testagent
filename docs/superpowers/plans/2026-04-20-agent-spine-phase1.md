# Agent Spine Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-safe slice of the new Dash agent spine by extracting normalized page context, standardized streaming events, and a thin conversation orchestrator without regressing current Dash behavior.

**Architecture:** This phase keeps the existing Dash chat surface and current execution behavior, but introduces three new internal seams: a page context adapter, a streaming protocol module, and a conversation orchestrator. The existing enhanced chat manager becomes a consumer of these seams rather than the only place where context and stream event structure are defined.

**Tech Stack:** Python 3.11, unittest, Dash chat integration, existing agent/core modules

---

### Task 1: Extract Page Context Adapter

**Files:**
- Create: `agent/core/page_context_adapter.py`
- Create: `agent/evaluation/test_page_context_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent.core.page_context_adapter import normalize_page_context


class PageContextAdapterTests(unittest.TestCase):
    def test_normalize_page_context_keeps_dashboard_and_filter_state(self):
        payload = normalize_page_context(
            dashboard_type="defect",
            current_data={"defects": object()},
            conversation_state={"selected_team": "DTSV_China"},
            extra_context={"page_filters": {"project": ["IDCEVO"], "week": 12}},
        )

        self.assertEqual(payload["dashboard_type"], "defect")
        self.assertEqual(payload["selected_team"], "DTSV_China")
        self.assertEqual(payload["page_filters"], {"project": ["IDCEVO"], "week": 12})
        self.assertEqual(payload["available_datasets"], ["defects"])

    def test_normalize_page_context_handles_dataframe_like_absence(self):
        payload = normalize_page_context(
            dashboard_type="general",
            current_data=None,
            conversation_state=None,
            extra_context=None,
        )

        self.assertEqual(payload["dashboard_type"], "general")
        self.assertEqual(payload["available_datasets"], [])
        self.assertEqual(payload["page_filters"], {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_page_context_adapter -v`
Expected: FAIL with `ModuleNotFoundError` or missing `normalize_page_context`

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Any, Dict, Optional


def normalize_page_context(
    dashboard_type: str,
    current_data: Any,
    conversation_state: Optional[Dict[str, Any]] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = dict(conversation_state or {})
    extras = dict(extra_context or {})

    if isinstance(current_data, dict):
        available_datasets = [str(key) for key in current_data.keys()]
    else:
        available_datasets = [] if current_data is None else ["primary"]

    page_filters = extras.get("page_filters") if isinstance(extras.get("page_filters"), dict) else {}

    return {
        "dashboard_type": str(dashboard_type or "general"),
        "selected_team": str(state.get("selected_team") or ""),
        "page_filters": page_filters,
        "available_datasets": available_datasets,
        "conversation_state": state,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_page_context_adapter -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/core/page_context_adapter.py agent/evaluation/test_page_context_adapter.py
git commit -m "feat: add page context adapter"
```

### Task 2: Extract Streaming Protocol Helpers

**Files:**
- Create: `agent/core/streaming_protocol.py`
- Create: `agent/evaluation/test_streaming_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent.core.streaming_protocol import append_event, init_stream_state


class StreamingProtocolTests(unittest.TestCase):
    def test_init_stream_state_sets_expected_defaults(self):
        state = init_stream_state("Agent working...")
        self.assertEqual(state["status"], "processing")
        self.assertEqual(state["progress"], "Agent working...")
        self.assertEqual(state["events"], [])

    def test_append_event_caps_event_count_and_normalizes_status(self):
        state = init_stream_state("x")
        for idx in range(3):
            append_event(state, kind="tool", title=f"step-{idx}", status="unknown")
        self.assertEqual(state["events"][-1]["status"], "info")
        self.assertEqual(state["events"][-1]["title"], "step-2")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_streaming_protocol -v`
Expected: FAIL with missing module or symbol

- [ ] **Step 3: Write minimal implementation**

```python
from datetime import datetime
import time
from typing import Any, Dict, Optional


def init_stream_state(progress: str) -> Dict[str, Any]:
    return {
        "status": "processing",
        "reasoning": "",
        "response": "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "progress": str(progress or ""),
        "chunk_buffer": "",
        "last_update": time.time(),
        "started_at": time.time(),
        "events": [],
    }


def append_event(
    stream_entry: Dict[str, Any],
    *,
    kind: str,
    title: str,
    status: str = "info",
    summary: str = "",
    details: Optional[Any] = None,
    limit: int = 80,
) -> Dict[str, Any]:
    normalized = status if status in {"running", "ok", "warn", "error", "fallback", "info"} else "info"
    events = stream_entry.setdefault("events", [])
    event = {
        "id": f"evt_{int(time.time() * 1000)}_{len(events) + 1}",
        "ts": time.time(),
        "kind": str(kind or "info"),
        "title": str(title or "事件"),
        "status": normalized,
        "summary": str(summary or ""),
        "details": details or {},
    }
    events.append(event)
    if len(events) > limit:
        del events[:-limit]
    stream_entry["last_update"] = time.time()
    return event
```

- [ ] **Step 4: Run test to verify it passes**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_streaming_protocol -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/core/streaming_protocol.py agent/evaluation/test_streaming_protocol.py
git commit -m "feat: add streaming protocol helpers"
```

### Task 3: Add Thin Conversation Orchestrator

**Files:**
- Create: `agent/core/conversation_orchestrator.py`
- Create: `agent/evaluation/test_conversation_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent.core.conversation_orchestrator import ConversationOrchestrator


class ConversationOrchestratorTests(unittest.TestCase):
    def test_build_request_merges_page_context_and_question(self):
        orchestrator = ConversationOrchestrator()
        request = orchestrator.build_request(
            question="按项目看风险",
            dashboard_type="defect",
            current_data={"defects": object()},
            conversation_state={"selected_team": "DTSV_China"},
            extra_context={"page_filters": {"project": ["MGU"]}},
        )
        self.assertEqual(request["question"], "按项目看风险")
        self.assertEqual(request["page_context"]["dashboard_type"], "defect")
        self.assertEqual(request["page_context"]["page_filters"], {"project": ["MGU"]})

    def test_initialize_stream_state_uses_protocol_module(self):
        orchestrator = ConversationOrchestrator()
        stream_state = orchestrator.initialize_stream_state("处理中")
        self.assertEqual(stream_state["status"], "processing")
        self.assertIn("events", stream_state)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_conversation_orchestrator -v`
Expected: FAIL with missing module or symbol

- [ ] **Step 3: Write minimal implementation**

```python
from typing import Any, Dict, Optional

from agent.core.page_context_adapter import normalize_page_context
from agent.core.streaming_protocol import init_stream_state


class ConversationOrchestrator:
    def build_request(
        self,
        *,
        question: str,
        dashboard_type: str,
        current_data: Any,
        conversation_state: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "question": str(question or "").strip(),
            "page_context": normalize_page_context(
                dashboard_type=dashboard_type,
                current_data=current_data,
                conversation_state=conversation_state,
                extra_context=extra_context,
            ),
        }

    def initialize_stream_state(self, progress: str) -> Dict[str, Any]:
        return init_stream_state(progress)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_conversation_orchestrator -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/core/conversation_orchestrator.py agent/evaluation/test_conversation_orchestrator.py
git commit -m "feat: add conversation orchestrator skeleton"
```

### Task 4: Wire Enhanced Chat Manager to New Seams

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_root_wrappers.py`
- Test: `agent/evaluation/test_page_context_adapter.py`
- Test: `agent/evaluation/test_streaming_protocol.py`
- Test: `agent/evaluation/test_conversation_orchestrator.py`

- [ ] **Step 1: Write the failing integration test**

```python
import unittest

from agent.core.conversation_orchestrator import ConversationOrchestrator


class OrchestratorIntegrationContractTests(unittest.TestCase):
    def test_orchestrator_can_seed_streaming_state_and_request_payload(self):
        orchestrator = ConversationOrchestrator()
        request = orchestrator.build_request(
            question="趋势分析",
            dashboard_type="defect",
            current_data={"defects": []},
            conversation_state={"selected_team": "DTSV_China"},
            extra_context={"page_filters": {"week": 16}},
        )
        stream_state = orchestrator.initialize_stream_state("智能Agent正在分析数据...")
        self.assertEqual(request["page_context"]["selected_team"], "DTSV_China")
        self.assertEqual(stream_state["progress"], "智能Agent正在分析数据...")
```

- [ ] **Step 2: Run test to verify it fails for missing integration behavior if not already covered**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_conversation_orchestrator -v`
Expected: FAIL before manager wiring or request structure stabilization

- [ ] **Step 3: Write minimal integration implementation**

```python
from agent.core.conversation_orchestrator import ConversationOrchestrator
from agent.core.streaming_protocol import append_event, init_stream_state

# in EnhancedAIChatManager.__init__
self._conversation_orchestrator = ConversationOrchestrator()

# in start_agent_streaming worker initialization
streaming_data.setdefault(task_id, self._conversation_orchestrator.initialize_stream_state("智能Agent正在分析数据..."))

# when building request context before process_with_agent
request = self._conversation_orchestrator.build_request(
    question=question,
    dashboard_type=self.dashboard_type,
    current_data=current_data,
    conversation_state=conversation_state,
    extra_context={},
)

# preserve current behavior by storing the normalized page context for downstream use
normalized_page_context = request.get("page_context", {})
```

- [ ] **Step 4: Run focused verification**

Run: `c:/Users/q446328/Desktop/TPMDashbaord/.venv/Scripts/python.exe -m unittest agent.evaluation.test_page_context_adapter agent.evaluation.test_streaming_protocol agent.evaluation.test_conversation_orchestrator agent.evaluation.test_root_wrappers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/core/enhanced_ai_chat_manager.py agent/core/conversation_orchestrator.py agent/core/page_context_adapter.py agent/core/streaming_protocol.py agent/evaluation/test_page_context_adapter.py agent/evaluation/test_streaming_protocol.py agent/evaluation/test_conversation_orchestrator.py
git commit -m "feat: wire phase-one agent spine seams"
```