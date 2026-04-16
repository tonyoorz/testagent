"""
Agent Tracer — 全链路可观测性

每次 process() 调用生成一个 trace，贯穿意图检测→上下文准备→规划→执行→生成。
支持嵌套 span，自动计时，可选写入 JSON 文件。

Usage:
    tracer = AgentTracer.enabled(question="ECU乒乓TOP10")
    with tracer.span("intent_detection"):
        ...
    with tracer.span("tool_execution"):
        with tracer.span("analyze_trend", params={"group_by": "week"}):
            result = ...
            tracer.annotate(rows=1200, success=True)
    tracer.finish()
"""

import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


class Span:
    """A single timed span within a trace."""

    __slots__ = ("name", "params", "start", "end", "events", "children", "span_id", "parent_id", "status")

    def __init__(self, name: str, span_id: Optional[str] = None, parent_id: Optional[str] = None):
        self.name = name
        self.span_id = span_id or _short_id()
        self.parent_id = parent_id
        self.params: Dict[str, Any] = {}
        self.start: float = 0.0
        self.end: float = 0.0
        self.events: List[Dict[str, Any]] = []
        self.children: List["Span"] = []
        self.status: str = "ok"

    def annotate(self, **kv):
        """Attach key-value metadata to this span."""
        self.events.append(kv)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.end = time.perf_counter()
        if args[0] is not None:
            self.status = "error"

    @property
    def duration_ms(self) -> int:
        if self.end and self.start:
            return int((self.end - self.start) * 1000)
        return 0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "span_id": self.span_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
        }
        if self.parent_id:
            d["parent_id"] = self.parent_id
        if self.params:
            d["params"] = self.params
        if self.events:
            d["events"] = self.events
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


class AgentTracer:
    """Top-level trace for one agent.process() invocation."""

    def __init__(self, question: str, trace_id: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        if not enabled:
            return
        self.trace_id = trace_id or f"t_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_short_id()}"
        self.question = question
        self.root: Span = Span("agent.process", span_id="root")
        self.root.start = time.perf_counter()
        self._stack: List[Span] = [self.root]
        self._meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Context-manager based span creation
    # ------------------------------------------------------------------

    @contextmanager
    def span(self, name: str, **params):
        """Create a child span. Usage::

            with tracer.span("analyze_trend", group_by="week") as sp:
                ...
                sp.annotate(rows=100)
        """
        if not self.enabled:
            yield _NullSpan()
            return
        parent = self._stack[-1] if self._stack else self.root
        child = Span(name, parent_id=parent.span_id)
        child.params = params
        child.start = time.perf_counter()
        parent.children.append(child)
        self._stack.append(child)
        try:
            yield child
        except Exception:
            child.status = "error"
            raise
        finally:
            child.end = time.perf_counter()
            self._stack.pop()

    # ------------------------------------------------------------------
    # Lightweight event annotation (no nesting)
    # ------------------------------------------------------------------

    def annotate(self, **kv):
        """Attach key-value metadata to the current span."""
        if not self.enabled or not self._stack:
            return
        self._stack[-1].events.append(kv)

    def set_meta(self, **kv):
        """Set trace-level metadata (e.g. mode, model, intents)."""
        if not self.enabled:
            return
        self._meta.update(kv)

    # ------------------------------------------------------------------
    # Finalisation
    # ------------------------------------------------------------------

    def finish(self, answer_summary: str = "") -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        self.root.end = time.perf_counter()
        payload = self.to_dict()
        if answer_summary:
            payload["answer_summary"] = answer_summary[:500]
        self._persist(payload)
        return payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "question": self.question,
            "total_ms": self.root.duration_ms,
            "meta": self._meta,
            "root": self.root.to_dict(),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, payload: Dict[str, Any]):
        trace_dir = os.getenv("AGENT_TRACE_DIR", ".traces")
        try:
            os.makedirs(trace_dir, exist_ok=True)
            path = os.path.join(trace_dir, f"{self.trace_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.debug(f"Trace persist failed: {e}")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def enabled(cls, question: str) -> "AgentTracer":
        """Create a tracer respecting the AGENT_TRACE_ENABLED env-var."""
        is_on = os.getenv("AGENT_TRACE_ENABLED", "0") == "1"
        return cls(question=question, enabled=is_on)

    @classmethod
    def noop(cls, question: str = "") -> "AgentTracer":
        return cls(question=question, enabled=False)


class _NullSpan:
    """No-op stand-in when tracing is disabled."""

    def annotate(self, **kv):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
