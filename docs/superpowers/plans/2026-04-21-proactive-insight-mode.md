# Proactive Insight Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit proactive insight mode that performs linked defect-and-test exploratory analysis, emits structured insight cards, and returns a complete natural-language report without changing ordinary Q&A behavior.

**Architecture:** Add a dedicated proactive insight path behind an explicit router. The route builds a structured `ProactiveInsightRequest`, runs a deterministic insight engine over the current defect/test datasets, converts structured cards into a narrative report, and returns both report text and cards in context. The existing runtime skeleton remains the default path when the router does not match.

**Tech Stack:** Python, dataclasses, pandas, unittest, existing enhanced chat manager and first-stage harness runtime skeleton.

---

## File Structure

- Create: `agent/core/proactive_insight_models.py` - stable request, evidence, card, and report dataclasses.
- Create: `agent/core/proactive_insight_router.py` - explicit entrypoint detection and request parsing.
- Create: `agent/core/proactive_insight_engine.py` - deterministic hotspot, anomaly, divergence, and turning-point discovery over defect/test data.
- Create: `agent/core/proactive_insight_reporter.py` - report synthesis from structured cards.
- Modify: `agent/core/enhanced_ai_chat_manager.py` - route explicit proactive-insight requests into the new path while leaving ordinary Q&A unchanged.
- Create: `agent/evaluation/test_proactive_insight_router.py` - router hit/miss and malformed request coverage.
- Create: `agent/evaluation/test_proactive_insight_engine.py` - deterministic insight card generation coverage.
- Create: `agent/evaluation/test_proactive_insight_reporter.py` - deterministic report generation coverage.
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py` - router integration and ordinary path non-regression coverage.

### Task 1: Add Proactive Insight Models and Router

**Files:**
- Create: `agent/core/proactive_insight_models.py`
- Create: `agent/core/proactive_insight_router.py`
- Test: `agent/evaluation/test_proactive_insight_router.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent.core.proactive_insight_router import ProactiveInsightRouter


class ProactiveInsightRouterTests(unittest.TestCase):
    def test_matches_explicit_entrypoint_flag(self):
        router = ProactiveInsightRouter()
        matched, request = router.match(
            question='请做主动洞察',
            extra_context={'mode': 'proactive_insight'},
        )
        self.assertTrue(matched)
        self.assertEqual(request.mode, 'proactive_insight')
        self.assertEqual(request.dataset_scope, 'defect_test')

    def test_ignores_standard_questions(self):
        router = ProactiveInsightRouter()
        matched, request = router.match(
            question='show weekly defects',
            extra_context={},
        )
        self.assertFalse(matched)
        self.assertIsNone(request)

    def test_rejects_missing_scope_with_explicit_command(self):
        router = ProactiveInsightRouter()
        with self.assertRaises(ValueError):
            router.parse(
                question='/proactive-insight',
                extra_context={'mode': 'proactive_insight', 'dataset_scope': ''},
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_router -v`
Expected: FAIL with import or missing symbol errors for the router and request model.

- [ ] **Step 3: Write minimal implementation**

```python
# agent/core/proactive_insight_models.py
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProactiveInsightRequest:
    mode: str
    dataset_scope: str
    dimensions: List[str] = field(default_factory=lambda: ['project', 'aida', 'severity', 'week'])
    time_window: str = 'recent'
    options: Dict[str, Any] = field(default_factory=dict)


# agent/core/proactive_insight_router.py
from typing import Dict, Optional, Tuple
from agent.core.proactive_insight_models import ProactiveInsightRequest


class ProactiveInsightRouter:
    def match(self, *, question: str, extra_context: Optional[Dict] = None) -> Tuple[bool, Optional[ProactiveInsightRequest]]:
        context = extra_context or {}
        explicit_mode = str(context.get('mode') or '').strip().lower()
        if explicit_mode == 'proactive_insight':
            return True, self.parse(question=question, extra_context=context)
        if str(question or '').strip().lower().startswith('/proactive-insight'):
            return True, self.parse(question=question, extra_context=context)
        return False, None

    def parse(self, *, question: str, extra_context: Optional[Dict] = None) -> ProactiveInsightRequest:
        context = dict(extra_context or {})
        dataset_scope = str(context.get('dataset_scope') or 'defect_test').strip()
        if not dataset_scope:
            raise ValueError('dataset_scope is required')
        return ProactiveInsightRequest(
            mode='proactive_insight',
            dataset_scope=dataset_scope,
            dimensions=list(context.get('dimensions') or ['project', 'aida', 'severity', 'week']),
            time_window=str(context.get('time_window') or 'recent'),
            options={k: v for k, v in context.items() if k not in {'mode', 'dataset_scope', 'dimensions', 'time_window'}},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_router -v`
Expected: PASS.

### Task 2: Add Deterministic Proactive Insight Engine

**Files:**
- Create: `agent/core/proactive_insight_engine.py`
- Modify: `agent/core/proactive_insight_models.py`
- Test: `agent/evaluation/test_proactive_insight_engine.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

import pandas as pd

from agent.core.proactive_insight_engine import ProactiveInsightEngine
from agent.core.proactive_insight_models import ProactiveInsightRequest


class ProactiveInsightEngineTests(unittest.TestCase):
    def test_generates_divergence_card_for_defect_test_mismatch(self):
        engine = ProactiveInsightEngine()
        request = ProactiveInsightRequest(mode='proactive_insight', dataset_scope='defect_test')
        defects = pd.DataFrame([
            {'project': 'MGU', 'week': '2026-W10', 'id': 1},
            {'project': 'MGU', 'week': '2026-W10', 'id': 2},
            {'project': 'MGU', 'week': '2026-W10', 'id': 3},
        ])
        tests = pd.DataFrame([
            {'project': 'MGU', 'week': '2026-W10', 'test_id': 1},
        ])
        cards = engine.generate(request=request, datasets={'defects': defects, 'tests': tests})
        self.assertTrue(any(card.type == 'divergence' for card in cards))

    def test_generates_hotspot_card_for_dominant_project(self):
        engine = ProactiveInsightEngine()
        request = ProactiveInsightRequest(mode='proactive_insight', dataset_scope='defect_test')
        defects = pd.DataFrame([
            {'project': 'MGU', 'week': '2026-W10', 'id': 1},
            {'project': 'MGU', 'week': '2026-W10', 'id': 2},
            {'project': 'BMS', 'week': '2026-W10', 'id': 3},
        ])
        cards = engine.generate(request=request, datasets={'defects': defects, 'tests': pd.DataFrame()})
        self.assertTrue(any(card.type == 'hotspot' for card in cards))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_engine -v`
Expected: FAIL with import or missing symbol errors for the engine or models.

- [ ] **Step 3: Write minimal implementation**

```python
# agent/core/proactive_insight_models.py
@dataclass(frozen=True)
class InsightEvidence:
    label: str
    value: Any


@dataclass(frozen=True)
class InsightCard:
    type: str
    title: str
    summary: str
    scope: Dict[str, Any]
    confidence: float
    severity: str
    evidence: List[InsightEvidence]
    metrics: Dict[str, Any]


# agent/core/proactive_insight_engine.py
import pandas as pd
from agent.core.proactive_insight_models import InsightCard, InsightEvidence, ProactiveInsightRequest


class ProactiveInsightEngine:
    def generate(self, *, request: ProactiveInsightRequest, datasets: dict) -> list[InsightCard]:
        cards = []
        defects = datasets.get('defects')
        tests = datasets.get('tests')
        if isinstance(defects, pd.DataFrame) and not defects.empty and 'project' in defects.columns:
            counts = defects['project'].astype(str).value_counts()
            if not counts.empty and counts.iloc[0] >= max(2, counts.sum() / 2):
                project = str(counts.index[0])
                cards.append(InsightCard(
                    type='hotspot',
                    title=f'{project} defect hotspot',
                    summary=f'{project} defects dominate the current slice.',
                    scope={'project': project},
                    confidence=0.7,
                    severity='medium',
                    evidence=[InsightEvidence(label='defect_count', value=int(counts.iloc[0]))],
                    metrics={'defect_count': int(counts.iloc[0])},
                ))
        if isinstance(defects, pd.DataFrame) and not defects.empty and isinstance(tests, pd.DataFrame) and not tests.empty:
            defect_count = len(defects)
            test_count = len(tests)
            if defect_count >= max(3, test_count * 2):
                cards.append(InsightCard(
                    type='divergence',
                    title='Defect/Test imbalance detected',
                    summary='Defect volume is materially higher than test activity in the current slice.',
                    scope={'dataset_scope': request.dataset_scope},
                    confidence=0.75,
                    severity='high',
                    evidence=[
                        InsightEvidence(label='defect_count', value=int(defect_count)),
                        InsightEvidence(label='test_count', value=int(test_count)),
                    ],
                    metrics={'defect_count': int(defect_count), 'test_count': int(test_count)},
                ))
        return cards
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_engine -v`
Expected: PASS.

### Task 3: Add Proactive Insight Reporter

**Files:**
- Create: `agent/core/proactive_insight_reporter.py`
- Modify: `agent/core/proactive_insight_models.py`
- Test: `agent/evaluation/test_proactive_insight_reporter.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent.core.proactive_insight_models import InsightCard, InsightEvidence
from agent.core.proactive_insight_reporter import ProactiveInsightReporter


class ProactiveInsightReporterTests(unittest.TestCase):
    def test_builds_complete_report_from_cards(self):
        reporter = ProactiveInsightReporter()
        cards = [
            InsightCard(
                type='divergence',
                title='Defect/Test imbalance detected',
                summary='Defect volume is materially higher than test activity in the current slice.',
                scope={'project': 'MGU'},
                confidence=0.75,
                severity='high',
                evidence=[InsightEvidence(label='defect_count', value=3), InsightEvidence(label='test_count', value=1)],
                metrics={'defect_count': 3, 'test_count': 1},
            )
        ]
        report = reporter.render(cards)
        self.assertIn('总览', report)
        self.assertIn('Defect/Test imbalance detected', report)
        self.assertIn('MGU', report)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_reporter -v`
Expected: FAIL with import or missing symbol errors.

- [ ] **Step 3: Write minimal implementation**

```python
# agent/core/proactive_insight_reporter.py
from typing import Iterable

from agent.core.proactive_insight_models import InsightCard


class ProactiveInsightReporter:
    def render(self, cards: Iterable[InsightCard]) -> str:
        items = list(cards)
        lines = ['总览']
        if not items:
            lines.append('当前范围内未发现需要重点关注的主动洞察。')
            return '\n'.join(lines)
        lines.append(f'本次共生成 {len(items)} 条主动洞察。')
        lines.append('关键发现')
        for card in items:
            scope_text = ', '.join(f'{k}={v}' for k, v in (card.scope or {}).items()) or 'scope=global'
            lines.append(f'- {card.title}: {card.summary} ({scope_text})')
        lines.append('数据边界说明')
        lines.append('该报告基于当前上下文中的 defect/test 数据切片，不代表完整历史全量结论。')
        return '\n'.join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_reporter -v`
Expected: PASS.

### Task 4: Integrate Proactive Insight Mode into the Chat Manager

**Files:**
- Modify: `agent/core/enhanced_ai_chat_manager.py`
- Modify: `agent/evaluation/test_enhanced_chat_manager_spine.py`

- [ ] **Step 1: Write the failing integration test**

```python
def test_process_with_agent_uses_proactive_insight_path_when_router_matches(self):
    manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
    manager.dashboard_type = 'defect'
    manager.use_agent = True
    manager.entity_tracker = None
    manager._conversation_orchestrator = ConversationOrchestrator()
    manager.proactive_insight_router = Mock()
    manager.proactive_insight_engine = Mock()
    manager.proactive_insight_reporter = Mock()
    manager.intelligent_agent = Mock()

    request = Mock(mode='proactive_insight', dataset_scope='defect_test')
    cards = [Mock(type='divergence')]
    manager.proactive_insight_router.match.return_value = (True, request)
    manager.proactive_insight_engine.generate.return_value = cards
    manager.proactive_insight_reporter.render.return_value = '主动洞察报告'

    result = manager.process_with_agent(
        '请做主动洞察',
        data={'defects': pd.DataFrame(), 'tests': pd.DataFrame()},
        conversation_history=[],
        extra_context={'mode': 'proactive_insight'},
    )

    self.assertTrue(result['success'])
    self.assertEqual(result['text'], '主动洞察报告')
    self.assertEqual(result['context']['proactive_insight_cards'], cards)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: FAIL because the chat manager does not yet recognize or execute the proactive insight path.

- [ ] **Step 3: Write minimal implementation**

```python
# enhanced_ai_chat_manager.py additions
from agent.core.proactive_insight_engine import ProactiveInsightEngine
from agent.core.proactive_insight_reporter import ProactiveInsightReporter
from agent.core.proactive_insight_router import ProactiveInsightRouter


def _ensure_proactive_insight_components(self):
    if not getattr(self, 'proactive_insight_router', None):
        self.proactive_insight_router = ProactiveInsightRouter()
    if not getattr(self, 'proactive_insight_engine', None):
        self.proactive_insight_engine = ProactiveInsightEngine()
    if not getattr(self, 'proactive_insight_reporter', None):
        self.proactive_insight_reporter = ProactiveInsightReporter()


def process_with_agent(...):
    self._ensure_proactive_insight_components()
    matched, proactive_request = self.proactive_insight_router.match(question=question, extra_context=extra_context)
    if matched:
        cards = self.proactive_insight_engine.generate(request=proactive_request, datasets=data if isinstance(data, dict) else {'defects': data})
        report_text = self.proactive_insight_reporter.render(cards)
        return {
            'success': True,
            'text': report_text,
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {
                'proactive_insight_mode': True,
                'proactive_insight_request': proactive_request,
                'proactive_insight_cards': cards,
            },
            'agent_used': True,
            'conversation_state': conversation_state,
            'resolved_question': None,
        }
    # else continue existing runtime skeleton path unchanged
```

- [ ] **Step 4: Run focused proactive insight and spine tests**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_router agent.evaluation.test_proactive_insight_engine agent.evaluation.test_proactive_insight_reporter agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: PASS.

### Task 5: Run Final Regression Checks

**Files:**
- Test only.

- [ ] **Step 1: Run proactive insight suite**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_proactive_insight_router agent.evaluation.test_proactive_insight_engine agent.evaluation.test_proactive_insight_reporter agent.evaluation.test_enhanced_chat_manager_spine -v`
Expected: PASS.

- [ ] **Step 2: Run existing package regression suite**

Run: `.\.venv\Scripts\python.exe -m unittest agent.evaluation.test_tool_package agent.evaluation.test_tool_package_loader agent.evaluation.test_tool_registry -v`
Expected: PASS.

## Self-Review

- Spec coverage: Task 1 covers the explicit entrypoint and parsing contract. Task 2 covers linked defect/test insight generation. Task 3 covers narrative reporting from structured cards. Task 4 covers chat-manager integration and preservation of the ordinary path. Task 5 covers regression verification.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: `ProactiveInsightRequest`, `InsightCard`, `InsightEvidence`, and `proactive_insight_cards` naming are consistent across tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-proactive-insight-mode.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?