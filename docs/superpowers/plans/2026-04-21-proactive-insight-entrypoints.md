# Proactive Insight Entry Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dual-entry proactive insight trigger to the existing Dash chat shell so users can enter proactive insight mode through either a preset button or a slash command without changing ordinary chat behavior.

**Architecture:** Reuse the existing enhanced chat UI and callback tree in `agent/core/enhanced_ai_chat_manager.py`. Normalize both the preset button and the `/proactive-insight` command into the same explicit `extra_context["mode"] = "proactive_insight"` signal before the current `process_with_agent(...)` path executes.

**Tech Stack:** Python, Dash callbacks, unittest, existing enhanced chat manager, current proactive insight runtime modules.

---

## File Structure

- Modify: `agent/core/enhanced_ai_chat_manager.py` - add proactive insight preset entries, entry normalization helpers, and callback wiring.
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py` - add focused normalization and mode-consistent behavior tests.
- Create: `agent/evaluation/test_proactive_insight_entrypoints.py` - narrow tests for preset/slash normalization and insufficient-data behavior.

### Task 1: Add a Normalized Proactive Insight Entry Helper

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_proactive_insight_entrypoints.py`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from agent.core.enhanced_ai_chat_manager import EnhancedAIChatManager


class ProactiveInsightEntrypointTests(unittest.TestCase):
    def test_detects_slash_command_and_sets_mode(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='/proactive-insight',
            trigger_key=None,
            extra_context={'chat_id_prefix': 'defect-chat'},
        )

        self.assertEqual(normalized['question'], '请做主动洞察')
        self.assertEqual(normalized['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(normalized['extra_context']['entry_point'], 'proactive_insight_slash')

    def test_detects_preset_button_and_sets_mode(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='请做主动洞察',
            trigger_key='proactive_insight',
            extra_context={},
        )

        self.assertEqual(normalized['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(normalized['extra_context']['entry_point'], 'proactive_insight_button')

    def test_leaves_normal_question_unchanged(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='show weekly defects',
            trigger_key=None,
            extra_context={'page_filters': {'project': ['MGU']}},
        )

        self.assertEqual(normalized['question'], 'show weekly defects')
        self.assertNotIn('mode', normalized['extra_context'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints -v`
Expected: FAIL with missing `EnhancedAIChatManager._normalize_proactive_insight_entry`.

- [ ] **Step 3: Write minimal implementation**

```python
def _normalize_proactive_insight_entry(
    self,
    *,
    question: str,
    trigger_key: Optional[str],
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_question = str(question or '').strip()
    updated_context = dict(extra_context or {})
    trigger = str(trigger_key or '').strip()

    if trigger == 'proactive_insight':
        updated_context['mode'] = 'proactive_insight'
        updated_context['entry_point'] = 'proactive_insight_button'
        return {'question': normalized_question or '请做主动洞察', 'extra_context': updated_context}

    if normalized_question.lower().startswith('/proactive-insight'):
        updated_context['mode'] = 'proactive_insight'
        updated_context['entry_point'] = 'proactive_insight_slash'
        return {'question': '请做主动洞察', 'extra_context': updated_context}

    return {'question': normalized_question, 'extra_context': updated_context}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints -v`
Expected: PASS.

### Task 2: Add the Proactive Insight Preset Button to the Existing Chat Shell

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Test: `agent/evaluation/test_proactive_insight_entrypoints.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_general_presets_include_proactive_insight(self):
    manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
    manager.dashboard_type = 'general'
    manager.preset_questions = EnhancedAIChatManager.__dict__['_build_default_presets'](manager)

    self.assertIn('proactive_insight', manager.preset_questions['general'])


def test_defect_explore_presets_include_proactive_insight(self):
    manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
    manager.dashboard_type = 'defect_explore'
    manager.preset_questions = EnhancedAIChatManager.__dict__['_build_default_presets'](manager)

    self.assertIn('proactive_insight', manager.preset_questions['defect_explore'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints -v`
Expected: FAIL because the preset set does not include the proactive insight key yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _build_default_presets(self) -> Dict[str, Dict[str, str]]:
    return {
        'defect_explore': {
            'summary': '请总结当前的缺陷和测试数据综合情况',
            'risk': '请分析高复杂度缺陷和测试覆盖的风险点',
            'project': '请对比分析各项目的缺陷与测试情况',
            'trend': '请基于缺陷趋势和测试效率给出改进建议',
            'matrix': '请分析缺陷矩阵分布和严重性问题',
            'team': '请分析测试团队效率和缺陷发现能力',
            'proactive_insight': '请做主动洞察',
        },
        'general': {
            'summary': '请总结当前数据情况',
            'analysis': '请分析当前数据',
            'insight': '请提供数据洞察',
            'recommendation': '请给出改进建议',
            'agent_explore': '请使用智能工具探索数据',
            'proactive_insight': '请做主动洞察',
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints -v`
Expected: PASS.

### Task 3: Wire Dual Entry Normalization Into the Existing Callback Path

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py`
- Test: `agent/evaluation/test_proactive_insight_entrypoints.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_process_with_agent_receives_mode_from_slash_normalization(self):
    manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
    manager.dashboard_type = 'defect'
    manager.use_agent = True
    manager.entity_tracker = None
    manager._conversation_orchestrator = ConversationOrchestrator()
    manager.proactive_insight_router = Mock()
    manager.proactive_insight_engine = Mock()
    manager.proactive_insight_reporter = Mock()
    manager.intelligent_agent = Mock()

    proactive_request = ProactiveInsightRequest(mode='proactive_insight', dataset_scope='defect_test')
    manager.proactive_insight_router.match.return_value = (True, proactive_request)
    manager.proactive_insight_engine.generate.return_value = []
    manager.proactive_insight_reporter.render.return_value = '总览\n当前范围内未发现需要重点关注的主动洞察。'

    result = manager.process_with_agent(
        '请做主动洞察',
        data={'defects': None, 'tests': None},
        conversation_history=[],
        extra_context={'mode': 'proactive_insight', 'entry_point': 'proactive_insight_slash'},
    )

    self.assertTrue(result['success'])
    self.assertTrue(result['context']['proactive_insight_mode'])


def test_proactive_insight_with_insufficient_data_stays_mode_consistent(self):
    manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
    manager.dashboard_type = 'defect_explore'
    manager.use_agent = True
    manager.entity_tracker = None
    manager._conversation_orchestrator = ConversationOrchestrator()
    manager.proactive_insight_router = Mock()
    manager.proactive_insight_engine = Mock(return_value=[])
    manager.proactive_insight_reporter = Mock()
    manager.intelligent_agent = Mock()

    proactive_request = ProactiveInsightRequest(mode='proactive_insight', dataset_scope='defect_test')
    manager.proactive_insight_router.match.return_value = (True, proactive_request)
    manager.proactive_insight_engine.generate.return_value = []
    manager.proactive_insight_reporter.render.return_value = '总览\n当前范围内未发现需要重点关注的主动洞察。'

    result = manager.process_with_agent(
        '请做主动洞察',
        data={'defects': None, 'tests': None},
        conversation_history=[],
        extra_context={'mode': 'proactive_insight'},
    )

    self.assertIn('总览', result['text'])
    self.assertTrue(result['context']['proactive_insight_mode'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: FAIL because the callback/request normalization path does not yet feed the explicit mode signal into the runtime consistently.

- [ ] **Step 3: Write minimal implementation**

```python
# inside the enhanced chat callback path
trigger_key = ''
if prop_id.startswith(f'{chat_id_prefix}-') and prop_id.endswith('-btn.n_clicks'):
    trigger_key = prop_id[len(f'{chat_id_prefix}-'):-len('-btn.n_clicks')]

normalized = self._normalize_proactive_insight_entry(
    question=user_question,
    trigger_key=trigger_key,
    extra_context=extra_context,
)
user_question = normalized['question']
extra_context = normalized['extra_context']
```

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: PASS.

### Task 4: Run Full Regression Checks for Stage Three

**Files:**
- Test only.

- [ ] **Step 1: Run stage-three focused suite**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_entrypoints agent.evaluation.test_proactive_insight_router agent.evaluation.test_proactive_insight_engine agent.evaluation.test_proactive_insight_reporter agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: PASS.

- [ ] **Step 2: Run package regression suite**

Run: `c:\Users\q446328\Desktop\TPMDashbaord\.venv\Scripts\python.exe -m unittest agent.evaluation.test_tool_package agent.evaluation.test_tool_package_loader agent.evaluation.test_tool_registry -v`
Expected: PASS.

## Self-Review

- Spec coverage: Task 1 covers dual-entry normalization. Task 2 covers explicit preset exposure in the current chat shell. Task 3 covers wiring the normalized mode into the existing callback/request flow and preserving proactive-insight semantics when data is insufficient. Task 4 covers final regression verification.
- Placeholder scan: no `TODO`, `TBD`, or deferred implementation placeholders remain.
- Type consistency: the plan consistently uses `mode`, `entry_point`, `_normalize_proactive_insight_entry(...)`, and `proactive_insight` as the preset key.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-proactive-insight-entrypoints.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?