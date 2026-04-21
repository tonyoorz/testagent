# Harness Runtime Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-stage harness runtime skeleton so the main chat path uses explicit guardrails, runtime stages, and centralized fallback while preserving Dash compatibility.

**Architecture:** Add three focused runtime modules: guardrails, runtime state machine, and recovery policy. Extend the orchestrator to coordinate them, then switch the enhanced chat manager to call the orchestrator-driven runtime path while keeping legacy execution as a fallback target.

**Tech Stack:** Python, unittest, existing Dash chat manager, current streaming protocol, existing legacy agent path.

---

## File Structure

- Create: `agent/core/guardrails.py` - structured guardrail decisions for allow, confirm, fallback, and block.
- Create: `agent/core/runtime_state_machine.py` - canonical runtime stages and transition validation.
- Create: `agent/core/recovery_policy.py` - structured recovery and fallback decisions.
- Modify: `agent/core/streaming_protocol.py` - additive runtime stage and fallback metadata helpers.
- Modify: `agent/core/conversation_orchestrator.py` - runtime coordinator entrypoints.
- Modify: `agent/core/enhanced_ai_chat_manager.py` - main path delegation into the orchestrator-driven runtime skeleton.
- Create: `agent/evaluation/test_guardrails.py` - guardrail decision tests.
- Create: `agent/evaluation/test_runtime_state_machine.py` - stage transition tests.
- Create: `agent/evaluation/test_recovery_policy.py` - fallback vs fail tests.
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py` - orchestration and fallback integration tests.

### Task 1: Add Runtime Guardrail Primitives

**Files:**
- Create: `agent/core/guardrails.py`
- Test: `agent/evaluation/test_guardrails.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent.core.guardrails import GuardrailEngine


class GuardrailTests(unittest.TestCase):
    def test_allows_normal_request(self):
        engine = GuardrailEngine()
        decision = engine.evaluate(
            question='show weekly defects',
            request={'question': 'show weekly defects'},
            page_context={'dashboard_type': 'defect'},
            agent_results={},
        )
        self.assertEqual(decision.action, 'allow')

    def test_requires_confirmation_when_pending_confirmation_exists(self):
        engine = GuardrailEngine()
        decision = engine.evaluate(
            question='继续',
            request={'question': '继续'},
            page_context={'dashboard_type': 'defect'},
            agent_results={'last_agent_context': {'confirmation_pending': True}},
        )
        self.assertEqual(decision.action, 'confirm')
        self.assertEqual(decision.reason_code, 'confirmation_required')

    def test_falls_back_when_request_has_no_page_context(self):
        engine = GuardrailEngine()
        decision = engine.evaluate(
            question='show weekly defects',
            request={'question': 'show weekly defects'},
            page_context={},
            agent_results={},
        )
        self.assertEqual(decision.action, 'fallback')
        self.assertEqual(decision.reason_code, 'missing_page_context')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_guardrails -v`
Expected: FAIL with import or missing symbol errors for `GuardrailEngine`.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class GuardrailDecision:
    action: str
    reason_code: str = 'allowed'
    message: str = ''
    details: Dict[str, Any] = field(default_factory=dict)


class GuardrailEngine:
    def evaluate(self, *, question: str, request: Dict[str, Any], page_context: Dict[str, Any], agent_results: Dict[str, Any]) -> GuardrailDecision:
        last_agent_context = (agent_results or {}).get('last_agent_context') or {}
        if last_agent_context.get('confirmation_pending'):
            return GuardrailDecision(action='confirm', reason_code='confirmation_required', message='confirmation pending')
        if not isinstance(page_context, dict) or not page_context.get('dashboard_type'):
            return GuardrailDecision(action='fallback', reason_code='missing_page_context', message='missing dashboard_type in page context')
        return GuardrailDecision(action='allow')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_guardrails -v`
Expected: PASS.

### Task 2: Add Runtime State Machine and Recovery Policy

**Files:**
- Create: `agent/core/runtime_state_machine.py`
- Create: `agent/core/recovery_policy.py`
- Test: `agent/evaluation/test_runtime_state_machine.py`
- Test: `agent/evaluation/test_recovery_policy.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from agent.core.recovery_policy import RecoveryPolicy
from agent.core.runtime_state_machine import RuntimeStateMachine


class RuntimeStateMachineTests(unittest.TestCase):
    def test_allows_forward_transition(self):
        machine = RuntimeStateMachine()
        state = machine.initialize()
        updated = machine.transition(state, 'guarded')
        self.assertEqual(updated['runtime_stage'], 'guarded')

    def test_rejects_invalid_transition(self):
        machine = RuntimeStateMachine()
        state = machine.initialize()
        with self.assertRaises(ValueError):
            machine.transition(state, 'completed')


class RecoveryPolicyTests(unittest.TestCase):
    def test_fallbacks_on_runtime_error(self):
        policy = RecoveryPolicy()
        decision = policy.resolve(reason_code='runtime_exception', error=RuntimeError('boom'))
        self.assertEqual(decision.action, 'fallback')

    def test_fails_when_blocked(self):
        policy = RecoveryPolicy()
        decision = policy.resolve(reason_code='blocked', error=None)
        self.assertEqual(decision.action, 'fail')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_runtime_state_machine agent.evaluation.test_recovery_policy -v`
Expected: FAIL with import or missing symbol errors.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from typing import Any, Dict


class RuntimeStateMachine:
    _allowed = {
        'received': {'guarded', 'fallback', 'failed'},
        'guarded': {'routed', 'fallback', 'failed'},
        'routed': {'executing', 'fallback', 'failed'},
        'executing': {'recovering', 'completed', 'fallback', 'failed'},
        'recovering': {'fallback', 'completed', 'failed'},
        'fallback': {'completed', 'failed'},
        'completed': set(),
        'failed': set(),
    }

    def initialize(self) -> Dict[str, Any]:
        return {'runtime_stage': 'received'}

    def transition(self, state: Dict[str, Any], next_stage: str) -> Dict[str, Any]:
        current = state.get('runtime_stage', 'received')
        if next_stage not in self._allowed.get(current, set()):
            raise ValueError(f'invalid transition: {current} -> {next_stage}')
        updated = dict(state)
        updated['runtime_stage'] = next_stage
        return updated


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason_code: str
    message: str = ''
    preserve_events: bool = True
    legacy_path: str = 'legacy_process_with_agent'


class RecoveryPolicy:
    def resolve(self, *, reason_code: str, error: Any = None) -> RecoveryDecision:
        if reason_code == 'blocked':
            return RecoveryDecision(action='fail', reason_code='blocked', legacy_path='')
        return RecoveryDecision(action='fallback', reason_code=reason_code, message=str(error or reason_code))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_runtime_state_machine agent.evaluation.test_recovery_policy -v`
Expected: PASS.

### Task 3: Extend Orchestrator and Streaming Protocol

**Files:**
- Modify: `agent/core/streaming_protocol.py`
- Modify: `agent/core/conversation_orchestrator.py`
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py`

- [ ] **Step 1: Write the failing integration tests**

```python
def test_initialize_stream_state_includes_runtime_metadata(self):
    orchestrator = ConversationOrchestrator()
    state = orchestrator.initialize_stream_state('starting')
    self.assertEqual(state['runtime_stage'], 'received')
    self.assertFalse(state['fallback_active'])
    self.assertFalse(state['confirmation_pending'])


def test_orchestrator_runs_guardrails(self):
    orchestrator = ConversationOrchestrator()
    runtime = orchestrator.prepare_runtime(
        question='show weekly defects',
        dashboard_type='defect',
        current_data=None,
        conversation_state=None,
        extra_context=None,
        agent_results={},
        progress='starting',
    )
    self.assertEqual(runtime['guardrail_decision'].action, 'allow')
    self.assertEqual(runtime['stream_state']['runtime_stage'], 'guarded')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: FAIL because runtime metadata or `prepare_runtime` do not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# agent/core/streaming_protocol.py
def init_stream_state(progress: str) -> Dict[str, Any]:
    now = time.time()
    return {
        'status': 'processing',
        'reasoning': '',
        'response': '',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'progress': str(progress or ''),
        'chunk_buffer': '',
        'last_update': now,
        'started_at': now,
        'events': [],
        'runtime_stage': 'received',
        'fallback_active': False,
        'confirmation_pending': False,
    }


def set_runtime_stage(stream_entry: Dict[str, Any], stage: str) -> Dict[str, Any]:
    stream_entry['runtime_stage'] = stage
    stream_entry['last_update'] = time.time()
    return append_event(stream_entry, kind='stage', title='Runtime stage updated', summary=stage, details={'runtime_stage': stage})


# agent/core/conversation_orchestrator.py
class ConversationOrchestrator:
    def __init__(self):
        self.guardrails = GuardrailEngine()
        self.state_machine = RuntimeStateMachine()
        self.recovery_policy = RecoveryPolicy()

    def prepare_runtime(...):
        request = self.build_request(...)
        stream_state = self.initialize_stream_state(progress)
        decision = self.guardrails.evaluate(...)
        if decision.action == 'confirm':
            stream_state['confirmation_pending'] = True
        next_stage = 'guarded' if decision.action == 'allow' else 'fallback'
        stream_state = self.state_machine.transition(stream_state, next_stage)
        set_runtime_stage(stream_state, stream_state['runtime_stage'])
        append_event(stream_state, kind='guardrail', title='Guardrail decision', summary=decision.action, details={'reason_code': decision.reason_code})
        return {'request': request, 'stream_state': stream_state, 'guardrail_decision': decision}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: PASS for the new runtime-preparation assertions.

### Task 4: Switch Enhanced Chat Manager Main Path to Runtime Skeleton With Fallback

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py`
- Test: `agent/evaluation/test_guardrails.py`
- Test: `agent/evaluation/test_runtime_state_machine.py`
- Test: `agent/evaluation/test_recovery_policy.py`

- [ ] **Step 1: Write the failing integration test**

```python
def test_process_with_agent_falls_back_on_runtime_failure(self):
    manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
    manager.dashboard_type = 'defect'
    manager.use_agent = True
    manager.entity_tracker = None
    manager._conversation_orchestrator = ConversationOrchestrator()
    manager._legacy_process_with_agent = Mock(return_value={'success': True, 'mode': 'legacy-fallback'})

    intelligent_agent = Mock()
    intelligent_agent.process.side_effect = RuntimeError('boom')
    manager.intelligent_agent = intelligent_agent

    result = manager.process_with_agent('show weekly defects', data=None, conversation_history=[])

    self.assertTrue(result['success'])
    self.assertEqual(result['mode'], 'legacy-fallback')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_guardrails agent.evaluation.test_runtime_state_machine agent.evaluation.test_recovery_policy agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: FAIL because the chat manager does not yet use the runtime skeleton and recovery policy.

- [ ] **Step 3: Write minimal implementation**

```python
# enhanced_ai_chat_manager.py
def _legacy_process_with_agent(self, *args, **kwargs):
    return self._process_with_agent_legacy(*args, **kwargs)


def process_with_agent(...):
    runtime = self._conversation_orchestrator.prepare_runtime(
        question=question,
        dashboard_type=self.dashboard_type,
        current_data=data,
        conversation_state=conversation_state,
        extra_context=extra_context,
        agent_results=agent_results or {},
        progress='AI正在分析问题...',
    )
    decision = runtime['guardrail_decision']
    if decision.action == 'confirm':
        return {'success': True, 'needs_confirmation': True, 'stream_state': runtime['stream_state'], 'context': {'guardrail_reason': decision.reason_code}}
    if decision.action == 'fallback':
        return self._legacy_process_with_agent(...)
    try:
        # existing agent execution path
        ...
    except Exception as exc:
        recovery = self._conversation_orchestrator.recovery_policy.resolve(reason_code='runtime_exception', error=exc)
        if recovery.action == 'fallback':
            return self._legacy_process_with_agent(...)
        raise
```

- [ ] **Step 4: Run focused runtime tests**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_guardrails agent.evaluation.test_runtime_state_machine agent.evaluation.test_recovery_policy agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: PASS.

- [ ] **Step 5: Run package regression tests**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_tool_package agent.evaluation.test_tool_package_loader agent.evaluation.test_tool_registry -v`
Expected: PASS.

## Self-Review

- Spec coverage: Task 1 covers explicit guardrails. Task 2 covers state machine and recovery policy. Task 3 wires orchestrator and streaming protocol. Task 4 switches the main path and verifies fallback behavior.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: `GuardrailDecision`, `RecoveryDecision`, and `runtime_stage` naming are consistent across tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-harness-runtime-skeleton.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

The user already selected inline execution for this session, so proceed with implementing this plan directly.