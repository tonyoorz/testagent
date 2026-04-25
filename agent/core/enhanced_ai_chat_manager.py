"""
增强版 AI Chat Manager - 集成智能 Agent 系统

在原有 AI Chat Manager 的基础上，添加以下增强功能：
1. 智能工具调用 - AI 可执行数据分析操作
2. 智能上下文管理 - 根据问题动态筛选数据
3. 对话记忆系统 - 记住关键洞察和用户偏好
4. 知识库集成 - RAG 能力提供领域知识
5. 任务规划能力 - 分解复杂任务
6. 增强系统提示词 - 专业领域知识

作者: AI Assistant
日期: 2025-01-19
更新: 2025-02-04 - 集成智能上下文生成、记忆系统、工具选择器和可解释性模块
"""

import os
import sys
import json
import time
import logging
import threading
import sqlite3
import re
from typing import Dict, List, Any, Optional, Callable, Generator
from datetime import datetime
import pandas as pd
import numpy as np
import io
import httpx

from agent.core.harness_config import load_dify_workflow_config
from agent.core.harness_router import (
    HarnessRouteHandler,
    HarnessRouteRequest,
    resolve_harness_route,
    should_load_local_data,
)
from agent.core.deterministic_sql_service import (
    build_deterministic_sql,
    decide_query_execution_strategy,
    extract_query_hints,
    guess_target_table,
)
from agent.core.sql_runtime_service import (
    build_evidence_bundle,
    compute_total_count,
    execute_query_with_fix,
    execute_sql_rows,
    sanitize_select_sql,
)
from agent.evaluation.agent_critic import contains_strong_confident_language
from duplicate_issue_finder import extract_hints, get_or_build_index
from octane_db import default_db_path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging first before importing enhancement modules
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_POSITIVE_CONFIRMATION_REPLIES = {
    "继续", "继续执行", "确认", "确认执行", "是", "好的", "好", "ok", "yes", "y", "proceed", "continue",
}


def _normalize_confirmation_reply(text: str) -> str:
    return str(text or "").strip().lower().strip(" \t\r\n,，。.!！？、；;:：")


def is_positive_confirmation_reply(text: str) -> bool:
    normalized = _normalize_confirmation_reply(text)
    return bool(normalized) and normalized in _POSITIVE_CONFIRMATION_REPLIES


def should_resume_pending_agent_confirmation(user_message: str, agent_results: Optional[Dict[str, Any]]) -> bool:
    if not is_positive_confirmation_reply(user_message):
        return False
    if not isinstance(agent_results, dict):
        return False

    context = agent_results.get("last_agent_context")
    if not isinstance(context, dict):
        return False

    return bool(context.get("needs_confirmation") or context.get("confirmation_pending"))

# Dify Workflow (RAG) config
HARDCODED_DIFY_API_BASE = "http://10.86.150.232/v1"
HARDCODED_DIFY_API_KEY = "app-YweK9LdWefjG11niKLtqTBV8"
DEFAULT_DIFY_WORKFLOW_QUERY_KEY = "query"
DEFAULT_DIFY_WORKFLOW_CONTEXT_KEY = "context"
DEFAULT_DIFY_WORKFLOW_USER_PREFIX = "preanalysis"

# Import new enhancement modules
try:
    from agent.core.smart_context_generator import create_smart_context_generator, SmartContextGenerator
    SMART_CONTEXT_AVAILABLE = True
    logger.info("Smart Context Generator loaded")
except ImportError as e:
    SMART_CONTEXT_AVAILABLE = False
    SmartContextGenerator = None
    logger.warning(f"Smart Context Generator not available: {e}")

try:
    from agent.memory.enhanced_memory_system import create_memory_system, EnhancedMemorySystem
    MEMORY_SYSTEM_AVAILABLE = True
    logger.info("Enhanced Memory System loaded")
except ImportError as e:
    MEMORY_SYSTEM_AVAILABLE = False
    EnhancedMemorySystem = None
    logger.warning(f"Enhanced Memory System not available: {e}")

try:
    from agent.tools.smart_tool_selector import create_smart_tool_selector, SmartToolSelector
    SMART_TOOL_SELECTOR_AVAILABLE = True
    logger.info("Smart Tool Selector loaded")
except ImportError as e:
    SMART_TOOL_SELECTOR_AVAILABLE = False
    SmartToolSelector = None
    logger.warning(f"Smart Tool Selector not available: {e}")

try:
    from agent.core.explainable_agent import create_explainable_agent, ExplainableAgent
    EXPLAINABLE_AGENT_AVAILABLE = True
    logger.info("Explainable Agent loaded")
except ImportError as e:
    EXPLAINABLE_AGENT_AVAILABLE = False
    ExplainableAgent = None
    logger.warning(f"Explainable Agent not available: {e}")

try:
    from agent.core.conversation_entity_tracker import (
        create_conversation_entity_tracker,
        create_initial_conversation_state,
        ConversationEntityTracker,
        ConversationState
    )
    ENTITY_TRACKER_AVAILABLE = True
    logger.info("Conversation Entity Tracker loaded")
except ImportError as e:
    ENTITY_TRACKER_AVAILABLE = False
    ConversationEntityTracker = None
    ConversationState = None
    logger.warning(f"Conversation Entity Tracker not available: {e}")

try:
    from agent.core.hybrid_retriever import HybridRetriever, create_hybrid_retriever
    HYBRID_RETRIEVER_AVAILABLE = True
    logger.info("Hybrid Retriever loaded")
except ImportError as e:
    HYBRID_RETRIEVER_AVAILABLE = False
    HybridRetriever = None
    logger.warning(f"Hybrid Retriever not available: {e}")

try:
    from agent.core.confluence_retriever import ConfluenceRetriever, create_confluence_retriever
    CONFLUENCE_RETRIEVER_AVAILABLE = True
    logger.info("Confluence Retriever loaded")
except ImportError as e:
    CONFLUENCE_RETRIEVER_AVAILABLE = False
    ConfluenceRetriever = None
    logger.warning(f"Confluence Retriever not available: {e}")

# 导入原有的 AI Chat Manager 组件
try:
    from agent.core.ai_chat_manager import (
        DeepSeekStreamingChat,
        streaming_data,
        streaming_lock,
        DEEPSEEK_API_KEY,
        DEEPSEEK_API_BASE,
        DEEPSEEK_MODEL,
        DEFAULT_TEMPERATURE,
        DEFAULT_MAX_TOKENS
    )
except ImportError:
    # 如果导入失败，使用默认配置
    DEEPSEEK_API_KEY = "your-api-key-here"
    DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL = "deepseek-chat"
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 2000

    # 创建简单的占位类
    class DeepSeekStreamingChat:
        def __init__(self, *args, **kwargs):
            pass

    streaming_data = {}
    streaming_lock = __import__('threading').Lock()

# 导入智能 Agent 系统
try:
    from agent.core.intelligent_agent import (
        IntelligentAgent,
        create_agent,
        create_agent_for_defect,
        create_agent_for_test,
        ToolExecutor
    )
    AGENT_AVAILABLE = True
    logger.info("Intelligent agent system loaded")
except ImportError as e:
    AGENT_AVAILABLE = False
    logger.warning(f"Intelligent agent system unavailable: {e}")
    IntelligentAgent = None


# ============================================================================
# 增强版 AI Chat Manager
# ============================================================================


class DifyWorkflowClient:
    """最小化 Dify Workflow 客户端（用于 RAG 模式）。"""

    def __init__(self, api_base: Optional[str] = None, api_key: Optional[str] = None):
        config = load_dify_workflow_config(
            default_api_base=HARDCODED_DIFY_API_BASE,
            default_api_key=HARDCODED_DIFY_API_KEY,
            default_query_key=DEFAULT_DIFY_WORKFLOW_QUERY_KEY,
            default_context_key=DEFAULT_DIFY_WORKFLOW_CONTEXT_KEY,
            default_user_prefix=DEFAULT_DIFY_WORKFLOW_USER_PREFIX,
            override_api_base=api_base,
            override_api_key=api_key,
        )
        self.api_base = config.api_base
        self.api_key = config.api_key
        self.query_key = config.query_key
        self.context_key = config.context_key
        self.user_prefix = config.user_prefix
        self.timeout = config.timeout
        self.response_mode = config.response_mode
        self.enabled = config.enabled
        self.http_client = httpx.Client(timeout=self.timeout, verify=False)

    def build_user(self, dashboard_type: str) -> str:
        return f"{self.user_prefix}-{dashboard_type}"

    def run_workflow(self, question: str, context: str = "", user: Optional[str] = None) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Dify Workflow 未配置，请设置 DIFY_API_BASE 和 DIFY_API_KEY")

        inputs: Dict[str, Any] = {
            self.query_key: question,
        }
        if context:
            inputs[self.context_key] = context

        extra_inputs_raw = os.environ.get("DIFY_WORKFLOW_EXTRA_INPUTS", "").strip()
        if extra_inputs_raw:
            try:
                extra_inputs = json.loads(extra_inputs_raw)
                if isinstance(extra_inputs, dict):
                    inputs.update(extra_inputs)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"DIFY_WORKFLOW_EXTRA_INPUTS 不是合法 JSON: {exc}") from exc

        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user or self.build_user("general"),
        }

        response = self.http_client.post(
            f"{self.api_base}/workflows/run",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip()
            raise RuntimeError(f"Dify Workflow 请求失败: HTTP {response.status_code} - {detail}") from exc

        body = response.json()
        data = body.get("data") or {}
        status = data.get("status") or "succeeded"
        if status in {"failed", "stopped"}:
            raise RuntimeError(data.get("error") or "Dify Workflow 执行失败")

        outputs = data.get("outputs") or {}
        text = self._extract_text(outputs)

        return {
            "status": status,
            "outputs": outputs,
            "text": text,
            "raw": body,
        }

    def stream_workflow(self, question: str, context: str = "", user: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """以 SSE 方式流式调用 Dify Workflow，逐步产出文本片段。"""
        if not self.enabled:
            raise RuntimeError("Dify Workflow 未配置，请设置 DIFY_API_BASE 和 DIFY_API_KEY")

        inputs: Dict[str, Any] = {
            self.query_key: question,
        }
        if context:
            inputs[self.context_key] = context

        extra_inputs_raw = os.environ.get("DIFY_WORKFLOW_EXTRA_INPUTS", "").strip()
        if extra_inputs_raw:
            try:
                extra_inputs = json.loads(extra_inputs_raw)
                if isinstance(extra_inputs, dict):
                    inputs.update(extra_inputs)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"DIFY_WORKFLOW_EXTRA_INPUTS 不是合法 JSON: {exc}") from exc

        payload = {
            "inputs": inputs,
            "response_mode": "streaming",
            "user": user or self.build_user("general"),
        }

        with self.http_client.stream(
            "POST",
            f"{self.api_base}/workflows/run",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=payload,
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                raise RuntimeError(f"Dify Workflow 流式请求失败: HTTP {response.status_code} - {detail}") from exc

            for line in response.iter_lines():
                if not line:
                    continue
                text_line = str(line).strip()
                if not text_line.startswith("data:"):
                    continue
                raw_data = text_line[5:].strip()
                if not raw_data or raw_data == "[DONE]":
                    continue

                try:
                    event_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                event_name = str(event_data.get("event") or "").strip()

                if event_name in {"workflow_finished", "message_end", "done"}:
                    yield {"type": "done", "event": event_name, "data": event_data}
                    continue

                if event_name in {"error", "workflow_failed"}:
                    message = (
                        event_data.get("message")
                        or event_data.get("error")
                        or event_data.get("detail")
                        or "Dify Workflow 流式执行失败"
                    )
                    raise RuntimeError(str(message))

                chunk = ""
                if isinstance(event_data.get("answer"), str):
                    chunk = event_data.get("answer") or ""
                elif isinstance(event_data.get("text"), str):
                    chunk = event_data.get("text") or ""
                else:
                    data_obj = event_data.get("data")
                    if isinstance(data_obj, dict):
                        if isinstance(data_obj.get("answer"), str):
                            chunk = data_obj.get("answer") or ""
                        elif isinstance(data_obj.get("text"), str):
                            chunk = data_obj.get("text") or ""

                if chunk:
                    yield {"type": "chunk", "event": event_name, "text": chunk, "data": event_data}

    def _extract_text(self, outputs: Dict[str, Any]) -> str:
        if not outputs:
            return ""

        preferred_keys = ["answer", "text", "result", "output", "content"]
        for key in preferred_keys:
            value = outputs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for value in outputs.values():
            if isinstance(value, str) and value.strip():
                return value.strip()

        return json.dumps(outputs, ensure_ascii=False, indent=2)


# ============================================================================
# Streaming Data Cleanup
# ============================================================================

def cleanup_stale_streaming_data(max_age_seconds: int = 300):
    """
    Clean up stale streaming data that hasn't been updated recently
    
    Args:
        max_age_seconds: Maximum age in seconds before data is considered stale
    """
    current_time = time.time()
    stale_tasks = []
    
    with streaming_lock:
        for task_id, data in list(streaming_data.items()):
            last_update = data.get('last_update', 0)
            age = current_time - last_update
            
            if age > max_age_seconds:
                stale_tasks.append((task_id, age))
        
        for task_id, age in stale_tasks:
            del streaming_data[task_id]
            logger.info(f"Cleaned up stale streaming data for task {task_id} (age: {age:.1f}s)")
    
    if stale_tasks:
        logger.info(f"Cleaned up {len(stale_tasks)} stale streaming tasks")
    
    return len(stale_tasks)


def _timeline_event_limit() -> int:
    try:
        return max(20, int(os.getenv("CHAT_UI_MAX_TRACE_EVENTS", "80") or 80))
    except Exception:
        return 80


def _normalize_event_status(status: Any) -> str:
    text = str(status or "info").strip().lower()
    if text in {"running", "ok", "warn", "error", "fallback", "info"}:
        return text
    return "info"


def _sanitize_event_details(details: Any) -> Any:
    if details in (None, "", [], {}):
        return {}
    if isinstance(details, (str, int, float, bool)):
        return details
    if isinstance(details, list):
        cleaned: List[Any] = []
        for item in details[:20]:
            cleaned.append(_sanitize_event_details(item))
        return [item for item in cleaned if item not in (None, "", [], {})]
    if isinstance(details, dict):
        cleaned_dict: Dict[str, Any] = {}
        for key, value in list(details.items())[:20]:
            normalized = _sanitize_event_details(value)
            if normalized in (None, "", [], {}):
                continue
            cleaned_dict[str(key)] = normalized
        return cleaned_dict
    return str(details)


def _format_event_details_text(details: Any) -> str:
    normalized = _sanitize_event_details(details)
    if normalized in (None, "", [], {}):
        return ""
    if isinstance(normalized, str):
        return normalized.strip()
    if isinstance(normalized, dict):
        lines: List[str] = []
        for key, value in normalized.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{key}:")
                lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            else:
                lines.append(f"{key}: {value}")
        return "\n".join([line for line in lines if line]).strip()
    return json.dumps(normalized, ensure_ascii=False, indent=2)


def append_stream_event_to_store(
    stream_entry: Dict[str, Any],
    *,
    kind: str,
    title: str,
    status: str = "info",
    summary: str = "",
    details: Optional[Any] = None,
    event_ts: Optional[float] = None,
) -> Dict[str, Any]:
    if not isinstance(stream_entry, dict):
        return {}

    events = stream_entry.get("events")
    if not isinstance(events, list):
        events = []
        stream_entry["events"] = events

    ts = float(event_ts if event_ts is not None else time.time())
    event = {
        "id": f"evt_{int(ts * 1000)}_{len(events) + 1}",
        "ts": ts,
        "kind": str(kind or "info").strip() or "info",
        "title": str(title or "事件").strip() or "事件",
        "status": _normalize_event_status(status),
        "summary": str(summary or "").strip(),
        "details": _sanitize_event_details(details),
    }
    events.append(event)
    limit = _timeline_event_limit()
    if len(events) > limit:
        del events[:-limit]
    return event


def append_stream_event(task_id: str, **event_kwargs: Any) -> Dict[str, Any]:
    with streaming_lock:
        stream_entry = streaming_data.setdefault(str(task_id or ""), {})
        event = append_stream_event_to_store(stream_entry, **event_kwargs)
        stream_entry["last_update"] = time.time()
        return event


def _format_elapsed_label(event_ts: Any, started_at: Any) -> str:
    try:
        event_value = float(event_ts or 0)
        started_value = float(started_at or 0)
    except Exception:
        return ""
    if event_value <= 0 or started_value <= 0:
        return ""
    elapsed = max(0.0, event_value - started_value)
    return f"+{elapsed:.1f}s"


def build_timeline_view_models(stream_data: Dict[str, Any], now_ts: Optional[float] = None) -> List[Dict[str, Any]]:
    if not isinstance(stream_data, dict):
        return []

    started_at = stream_data.get("started_at") or 0
    events = stream_data.get("events")
    if not isinstance(events, list):
        return []

    rows: List[Dict[str, Any]] = []
    for raw_event in events:
        if not isinstance(raw_event, dict):
            continue
        kind = str(raw_event.get("kind") or "info").strip().lower() or "info"
        status = _normalize_event_status(raw_event.get("status"))
        details_text = _format_event_details_text(raw_event.get("details"))
        rows.append(
            {
                "id": str(raw_event.get("id") or ""),
                "kind": kind,
                "status": status,
                "title": str(raw_event.get("title") or "事件").strip() or "事件",
                "summary": str(raw_event.get("summary") or "").strip(),
                "details_text": details_text,
                "elapsed_label": _format_elapsed_label(raw_event.get("ts"), started_at),
                "expanded": bool(status in {"error", "warn", "fallback"} or kind in {"error", "fallback", "evidence_gap"}),
            }
        )
    return rows


def build_terminal_timeline_event(stream_data: Dict[str, Any], now_ts: Optional[float] = None) -> Dict[str, Any]:
    if not isinstance(stream_data, dict):
        return {}

    status = str(stream_data.get("status") or "").strip().lower()
    event_ts = float(now_ts if now_ts is not None else time.time())
    response = str(stream_data.get("response") or "").strip()
    error_text = str(stream_data.get("error") or "").strip()

    if status == "completed" and response:
        return {
            "id": f"evt_terminal_{int(event_ts * 1000)}",
            "kind": "final_answer",
            "status": "ok",
            "title": "最终回答已生成",
            "summary": f"输出 {len(response)} 字",
            "details_text": response[:400],
            "elapsed_label": _format_elapsed_label(event_ts, stream_data.get("started_at") or 0),
            "expanded": False,
        }

    if status == "error" and error_text:
        return {
            "id": f"evt_terminal_{int(event_ts * 1000)}",
            "kind": "error",
            "status": "error",
            "title": "执行失败",
            "summary": error_text,
            "details_text": error_text,
            "elapsed_label": _format_elapsed_label(event_ts, stream_data.get("started_at") or 0),
            "expanded": True,
        }

    return {}


def infer_summary_evidence_gaps(question: str, sql_used: str, rows: List[Dict[str, Any]], table_name: str) -> List[str]:
    question_text = str(question or "").strip()
    question_lower = question_text.lower()
    sql_text = str(sql_used or "").strip().lower()

    sample_columns = set()
    for row in (rows or [])[:3]:
        if isinstance(row, dict):
            sample_columns.update([str(key) for key in row.keys()])

    gaps: List[str] = []

    if not rows:
        gaps.append("当前查询没有返回结果，无法据此回答问题。")

    feature_like_columns = {
        "feature",
        "features",
        "function",
        "function_name",
        "module",
        "service",
        "component",
        "aida",
        "aida_english",
        "top_aida",
        "domain",
    }
    detail_like_columns = feature_like_columns | {"defect_id", "id", "name", "title", "ticket_id", "test_name"}
    asks_feature_breakdown = any(token in question_lower for token in ["功能", "feature", "features", "模块", "module", "service", "aida"])
    asks_detail_list = any(token in question_lower for token in ["哪些", "明细", "列表", "detail", "details", "which"])
    asks_showstopper = any(token in question_lower for token in ["showstopper candidate", "showstopper"])
    aggregate_sql = ("group by" in sql_text) or any(token in sql_text for token in ["count(", "sum(", "avg(", "round("])

    if asks_feature_breakdown and not (sample_columns & feature_like_columns):
        gaps.append("结果中不包含功能维度字段，无法回答“都是哪些功能”。")

    if asks_detail_list and aggregate_sql and not (sample_columns & detail_like_columns):
        gaps.append("当前 SQL 返回的是聚合结果而非明细记录，无法回答对象列表类问题。")

    if asks_showstopper and "showstopper" not in sql_text:
        gaps.append("当前查询未显式筛选 showstopper candidate，统计口径可能不匹配。")

    deduped: List[str] = []
    seen = set()
    for gap in gaps:
        key = gap.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(gap)
    return deduped


def build_summary_uncertainty_line(evidence_gaps: Optional[List[str]]) -> str:
    normalized: List[str] = []
    for gap in (evidence_gaps or []):
        text = str(gap or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    if not normalized:
        return ""
    return f"insufficient evidence: {normalized[0]}"


def downgrade_unsupported_claims(answer_text: str, evidence_bundle: Optional[Dict[str, Any]]) -> str:
    text = str(answer_text or "").strip()
    if not text:
        return text

    bundle = evidence_bundle if isinstance(evidence_bundle, dict) else {}
    evidence_gaps = bundle.get("evidence_gap") if isinstance(bundle.get("evidence_gap"), list) else []
    normalized_gaps = [str(g).strip() for g in evidence_gaps if str(g or "").strip()]
    if not normalized_gaps:
        return text

    has_strong_claim = contains_strong_confident_language(text)
    if not has_strong_claim:
        return text

    downgraded = text
    replacements = [
        (r"完全证明", "初步显示"),
        (r"已被证明", "初步显示"),
        (r"证明", "显示"),
        (r"必然", "较可能"),
        (r"一定", "较可能"),
        (r"毫无疑问", "从当前样本看"),
        (r"可以确定", "目前倾向认为"),
        (r"\bdefinitely\b", "likely"),
        (r"\bcertainly\b", "likely"),
        (r"\bguaranteed\b", "likely"),
        (r"\bprove(?:s|d|n)?\b", "suggests"),
    ]
    for pattern, repl in replacements:
        downgraded = re.sub(pattern, repl, downgraded, flags=re.IGNORECASE)

    if ("无法确认" not in downgraded) and ("cannot be confirmed" not in downgraded.lower()):
        notice = f"证据说明：{normalized_gaps[0]}，当前结论仍有不确定性，暂无法确认。"
        downgraded = f"{downgraded}\n{notice}" if downgraded else notice

    return downgraded


def format_total_count_display(total_count: Optional[int], unknown_marker: str = "unknown") -> str:
    marker = str(unknown_marker or "").strip() or "unknown"
    if isinstance(total_count, (int, np.integer)):
        try:
            normalized = int(total_count)
        except Exception:
            normalized = -1
        if normalized >= 0:
            return str(normalized)
    return marker


def decide_summary_query_execution_strategy(
    question: str,
    columns: Optional[List[str]] = None,
    semantic_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return decide_query_execution_strategy(
        question=question,
        columns=columns,
        semantic_hints=semantic_hints,
    )


def apply_summary_query_strategy_override(
    query_strategy: Optional[Dict[str, Any]],
    configured_mode: str = "",
) -> Dict[str, Any]:
    effective_strategy = dict(query_strategy) if isinstance(query_strategy, dict) else {}
    strategy_name = str(effective_strategy.get("strategy") or "constrained_fallback").strip().lower()

    try:
        strategy_confidence = float(effective_strategy.get("confidence") or 0.0)
    except Exception:
        strategy_confidence = 0.0

    mode = str(configured_mode or "").strip().lower()
    forced_by_env = ""
    if mode == "deterministic":
        strategy_name = "deterministic_first"
        strategy_confidence = max(strategy_confidence, 0.65)
        forced_by_env = "deterministic"
    elif mode == "agent":
        strategy_name = "constrained_fallback"
        strategy_confidence = min(strategy_confidence, 0.55)
        forced_by_env = "agent"

    strategy_confidence = max(0.05, min(0.95, strategy_confidence))
    effective_strategy["strategy"] = strategy_name
    effective_strategy["confidence"] = round(strategy_confidence, 3)
    effective_strategy["prefer_deterministic"] = bool(
        strategy_name == "deterministic_first" and strategy_confidence >= 0.55
    )
    if forced_by_env:
        effective_strategy["forced_by_env"] = forced_by_env
    else:
        effective_strategy.pop("forced_by_env", None)
    return effective_strategy


def build_stream_reasoning_content(stream_data: Dict[str, Any], now_ts: Optional[float] = None) -> str:
    """Build a compact, de-duplicated reasoning block for streaming UI updates."""
    if not isinstance(stream_data, dict):
        return ""

    def _non_empty_lines(text: Any) -> List[str]:
        out: List[str] = []
        for raw in str(text or "").splitlines():
            line = str(raw or "").strip()
            if line:
                out.append(line)
        return out

    route_reasoning = str(stream_data.get("route_reasoning") or "").strip()
    live_reasoning_lines = _non_empty_lines(stream_data.get("reasoning") or "")
    if len(live_reasoning_lines) > 8:
        live_reasoning_lines = live_reasoning_lines[-8:]
    progress_hint = str(stream_data.get("progress") or "").strip()

    summary_trace = stream_data.get("summary_trace") if isinstance(stream_data.get("summary_trace"), dict) else {}
    trace_stage = str(summary_trace.get("stage") or "").strip()
    execution_path = summary_trace.get("execution_path") if isinstance(summary_trace.get("execution_path"), list) else []
    execution_path_text = " > ".join([str(x) for x in execution_path if x]) if execution_path else ""

    blocks: List[str] = []
    if route_reasoning:
        blocks.append(route_reasoning)
    if live_reasoning_lines:
        blocks.append("\n".join(live_reasoning_lines))
    if progress_hint:
        blocks.append(f"进度: {progress_hint}")
    if trace_stage:
        blocks.append(f"阶段: {trace_stage}")
    if execution_path_text:
        blocks.append(f"路径: {execution_path_text}")

    try:
        started_at = float(stream_data.get("started_at") or 0)
    except Exception:
        started_at = 0
    status = str(stream_data.get("status") or "").strip().lower()
    if started_at > 0 and status == "processing":
        ts = float(now_ts if now_ts is not None else time.time())
        elapsed_seconds = int(max(0, ts - started_at))
        blocks.append(f"耗时: {elapsed_seconds}s")

    seen = set()
    merged_lines: List[str] = []
    for block in blocks:
        for line in _non_empty_lines(block):
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            merged_lines.append(line)

    if not merged_lines:
        return ""
    if len(merged_lines) > 14:
        merged_lines = merged_lines[-14:]

    return "\n".join([f"- {line}" for line in merged_lines]).strip()

class EnhancedAIChatManager:
    """增强版 AI Chat Manager - 集成智能 Agent 能力"""

    def __init__(self, dashboard_type: str = 'general', use_agent: bool = True, assistant_name: Optional[str] = None):
        """
        初始化增强版 AI Chat Manager

        Args:
            dashboard_type: 看板类型 ('defect', 'test', 'general')
            use_agent: 是否使用智能 Agent 系统
            assistant_name: 助手展示名（例如：SiSi）
        """
        self.dashboard_type = dashboard_type
        
        # Initialize enhancement modules
        self.smart_context_generator = None
        self.memory_system = None
        self.tool_selector = None
        self.explainable_agent = None
        self.entity_tracker = None
        self.hybrid_retriever = None
        self.confluence_retriever = None
        
        # Initialize smart context generator
        if SMART_CONTEXT_AVAILABLE:
            try:
                self.smart_context_generator = create_smart_context_generator()
                logger.info("Smart context generator initialized")
            except Exception as e:
                logger.error(f"Failed to initialize smart context generator: {e}")
        
        # Initialize memory system
        if MEMORY_SYSTEM_AVAILABLE:
            try:
                db_path = os.path.join(PROJECT_ROOT, 'database', 'agent_memory.db')
                self.memory_system = create_memory_system(db_path=db_path, user_id=dashboard_type)
                logger.info("Memory system initialized")
            except Exception as e:
                logger.error(f"Failed to initialize memory system: {e}")
        
        # Initialize tool selector
        if SMART_TOOL_SELECTOR_AVAILABLE:
            try:
                db_path = os.path.join(PROJECT_ROOT, 'database', 'tool_performance.db')
                self.tool_selector = create_smart_tool_selector(db_path=db_path)
                logger.info("Tool selector initialized")
            except Exception as e:
                logger.error(f"Failed to initialize tool selector: {e}")
        
        # Initialize explainable agent
        if EXPLAINABLE_AGENT_AVAILABLE:
            try:
                self.explainable_agent = create_explainable_agent()
                logger.info("Explainable agent initialized")
            except Exception as e:
                logger.error(f"Failed to initialize explainable agent: {e}")

        # Initialize entity tracker
        if ENTITY_TRACKER_AVAILABLE:
            try:
                self.entity_tracker = create_conversation_entity_tracker()
                logger.info("Entity tracker initialized")
            except Exception as e:
                logger.error(f"Failed to initialize entity tracker: {e}")

        # Initialize hybrid retriever
        if HYBRID_RETRIEVER_AVAILABLE:
            try:
                self.hybrid_retriever = create_hybrid_retriever()
                logger.info("Hybrid retriever initialized")
            except Exception as e:
                logger.error(f"Failed to initialize hybrid retriever: {e}")

        # Initialize Confluence retriever
        if CONFLUENCE_RETRIEVER_AVAILABLE:
            try:
                self.confluence_retriever = create_confluence_retriever()
                logger.info(
                    "Confluence retriever initialized (%s)",
                    "enabled" if getattr(self.confluence_retriever, "enabled", False) else "disabled"
                )
            except Exception as e:
                logger.error(f"Failed to initialize confluence retriever: {e}")

        self.use_agent = use_agent and AGENT_AVAILABLE
        if assistant_name:
            self.assistant_name = assistant_name
        else:
            self.assistant_name = "SiSi" if dashboard_type in {"defect", "defect_explore"} else "AI助手"

        # 初始化原有组件
        try:
            self.chatbot = DeepSeekStreamingChat()
            logger.info("DeepSeek聊天机器人初始化成功")
        except Exception as e:
            logger.error(f"DeepSeek聊天机器人初始化失败: {e}")
            self.chatbot = None

        try:
            self.dify_client = DifyWorkflowClient()
            logger.info(f"Dify Workflow 客户端初始化{'成功' if self.dify_client.enabled else '未启用'}")
        except Exception as e:
            logger.error(f"Dify Workflow 客户端初始化失败: {e}")
            self.dify_client = None

        # 初始化智能 Agent
        if self.use_agent:
            try:
                db_path = os.getenv("AGENT_SQLITE_DB_PATH") or default_db_path()
                self.intelligent_agent = create_agent(dashboard_type, llm=self.chatbot, db_path=db_path)
                logger.info(f"智能Agent初始化成功 (类型: {dashboard_type})")
            except Exception as e:
                logger.error(f"智能Agent初始化失败: {e}")
                self.use_agent = False
                self.intelligent_agent = None
        else:
            self.intelligent_agent = None

        # 预设问题模板（增强版）
        self.preset_questions = {
            'defect': {
                'summary': "请总结当前的缺陷数据情况",
                'risk': "请分析当前数据中的高风险问题",
                'project': "请分析项目分布情况",
                'trend': "请分析缺陷趋势变化",
                'comparison': "请对比各项目的表现",
                'agent_summary': "请使用智能分析工具全面分析缺陷数据"
            },
            'defect_explore': {
                'summary': "请总结当前的缺陷和测试数据综合情况",
                'risk': "请分析高复杂度缺陷和测试覆盖的风险点",
                'project': "请对比分析各项目的缺陷与测试情况",
                'trend': "请基于缺陷趋势和测试效率给出改进建议",
                'matrix': "请分析缺陷矩阵分布和严重性问题",
                'team': "请分析测试团队效率和缺陷发现能力"
            },
            'test': {
                'summary': "请总结当前的测试覆盖率情况",
                'risk': "请分析测试覆盖率中的风险点",
                'project': "请分析各项目的测试情况",
                'trend': "请给出测试改进建议",
                'agent_test': "请智能分析测试覆盖率并给出优化建议"
            },
            'general': {
                'summary': "请总结当前数据情况",
                'analysis': "请分析当前数据",
                'insight': "请提供数据洞察",
                'recommendation': "请给出改进建议",
                'agent_explore': "请使用智能工具探索数据"
            }
        }

        logger.info(f"增强版AI Chat Manager初始化完成 (Agent: {'启用' if self.use_agent else '禁用'})")

    def process_with_agent(self, question: str, data: pd.DataFrame,
                          conversation_history: List = None,
                          conversation_state: Optional[Dict] = None,
                          progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        使用智能 Agent 处理问题

        Args:
            question: 用户问题
            data: 数据 DataFrame
            conversation_history: 对话历史（可选）
            conversation_state: 对话状态（用于实体追踪）

        Returns:
            包含答案、工具调用结果、洞察等的字典
        """
        if not self.use_agent or not self.intelligent_agent:
            return {
                'success': False,
                'error': '智能Agent系统不可用',
                'text': '抱歉，智能分析功能当前不可用。请使用普通对话功能。'
            }

        try:
            # 实体追踪：指代消解
            resolved_question = question
            updated_state = conversation_state

            if self.entity_tracker and conversation_state is not None:
                try:
                    # 恢复对话状态
                    state = ConversationState.from_dict(conversation_state) if ConversationState else None
                    if state:
                        # 指代消解
                        resolved_question = self.entity_tracker.resolve_references(question, state)
                        if resolved_question != question:
                            logger.info(f"Entity resolution: '{question}' -> '{resolved_question}'")
                except Exception as e:
                    logger.warning(f"Entity resolution failed: {e}")

            # 使用智能 Agent 处理
            result = self.intelligent_agent.process(
                resolved_question,
                data,
                conversation_history,
                progress_cb=progress_cb,
            )

            # 更新对话状态
            if self.entity_tracker and conversation_state is not None:
                try:
                    state = ConversationState.from_dict(conversation_state) if ConversationState else None
                    if state:
                        tools_used = result.get('tools_used', [])
                        intent = result.get('context', {}).get('intents', [])
                        state = self.entity_tracker.update_state(
                            state, resolved_question,
                            intent=intent[0] if intent else None,
                            tools_used=tools_used
                        )
                        updated_state = state.to_dict()
                except Exception as e:
                    logger.warning(f"State update failed: {e}")

            # 格式化返回结果
            return {
                'success': True,
                'text': result['text'],
                'insights': result.get('insights', []),
                'visualizations': result.get('visualizations', []),
                'tools_used': result.get('tools_used', []),
                'context': result.get('context', {}),
                'agent_used': True,
                'conversation_state': updated_state,
                'resolved_question': resolved_question if resolved_question != question else None
            }

        except Exception as e:
            logger.error(f"智能Agent处理失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'text': f'智能分析过程中出现错误：{str(e)}',
                'agent_used': True
            }

    def process_with_llm(self, question: str, data_context: str,
                        conversation_history: List = None) -> str:
        """
        使用 LLM 处理问题（原有方式）

        Args:
            question: 用户问题
            data_context: 数据上下文字符串
            conversation_history: 对话历史（可选）

        Returns:
            AI 回答文本
        """
        if not self.chatbot:
            return self._get_fallback_response(question, data_context)

        try:
            # 构建消息
            messages = []

            # 系统消息（增强版）
            system_prompt = self._get_enhanced_system_prompt(data_context)
            messages.append({"role": "system", "content": system_prompt})

            # 对话历史
            if conversation_history:
                for msg in conversation_history[-10:]:  # 限制历史长度
                    if msg.get('role') in ['user', 'assistant']:
                        messages.append({
                            "role": msg['role'],
                            "content": msg['content']
                        })

            # 用户问题
            messages.append({"role": "user", "content": question})

            # 调用 LLM（使用原有的流式聊天）
            # 这里简化处理，直接调用
            response_text = ""
            for chunk in self.chatbot.stream_chat_response_optimized(
                messages,
                task_id=f"chat_{int(time.time())}",
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS
            ):
                if chunk.startswith("error:"):
                    raise RuntimeError(chunk.replace("error:", "", 1))
                if chunk.startswith("content:"):
                    response_text += chunk.replace("content:", "")

            return response_text

        except Exception as e:
            logger.error(f"LLM处理失败: {e}")
            return self._get_fallback_response(question, data_context)

    def process_with_dify_workflow(self, question: str, data_context: str) -> Dict[str, Any]:
        """使用 Dify Workflow 处理问题（RAG 模式）。"""
        if not self.dify_client or not self.dify_client.enabled:
            return {
                'success': False,
                'error': 'Dify Workflow 未配置',
                'text': 'Dify Workflow 当前不可用，请检查 DIFY_API_BASE、DIFY_API_KEY 和工作流输入变量。'
            }

        try:
            result = self.dify_client.run_workflow(
                question=question,
                context=data_context,
                user=self.dify_client.build_user(self.dashboard_type)
            )
            text = (result.get('text') or '').strip()
            if not text:
                text = 'Dify Workflow 已返回结果，但没有可展示的文本输出。'
            return {
                'success': True,
                'text': text,
                'dify_status': result.get('status'),
                'dify_outputs': result.get('outputs', {}),
            }
        except Exception as e:
            logger.error(f"Dify Workflow 处理失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'text': f'Dify Workflow 调用失败：{str(e)}'
            }

    def process_with_confluence(self, question: str, data_context: str = "") -> Dict[str, Any]:
        """使用 Confluence 作为知识源进行检索增强对话。"""
        if not self.confluence_retriever or not getattr(self.confluence_retriever, "enabled", False):
            return {
                'success': False,
                'error': 'Confluence 未配置',
                'text': (
                    'Confluence 模式当前不可用。请配置环境变量：'
                    'CONFLUENCE_BASE_URL、CONFLUENCE_TOKEN，以及 CONFLUENCE_SPACE_KEY 或 CONFLUENCE_ROOT_PAGE_ID。'
                ),
            }

        try:
            top_k = max(1, int((os.getenv("CONFLUENCE_TOP_K") or "5").strip() or "5"))
        except Exception:
            top_k = 5

        try:
            retrieved = self.confluence_retriever.retrieve(question, top_k=top_k)
            results = list((retrieved or {}).get("results") or [])
            meta = dict((retrieved or {}).get("meta") or {})

            if not results:
                return {
                    'success': True,
                    'text': 'Confluence 已连接，但未检索到与当前问题相关的页面内容。',
                    'meta': meta,
                    'sources': [],
                }

            context_parts: List[str] = []
            source_list: List[Dict[str, Any]] = []
            for idx, item in enumerate(results, 1):
                title = str(item.get("title") or "").strip() or f"Page {idx}"
                url = str(item.get("url") or "").strip()
                snippet = str(item.get("content") or "").strip()
                score = float(item.get("score") or 0.0)
                source_list.append(
                    {
                        "title": title,
                        "url": url,
                        "score": score,
                    }
                )
                context_parts.append(f"[{idx}] 标题: {title}")
                if url:
                    context_parts.append(f"[{idx}] 链接: {url}")
                if snippet:
                    context_parts.append(f"[{idx}] 内容: {snippet}")

            context_block = "\n".join(context_parts).strip()
            merged_context = "\n\n".join([x for x in [data_context, context_block] if x]).strip()

            system_prompt = (
                "你是企业知识库助手。请基于给定的 Confluence 证据回答问题。"
                "输出要求：先给结论，再给依据；若证据不足请明确说明。"
                "引用证据时使用 [1] [2] 这样的编号。"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"问题：{question}\n\n"
                        f"Confluence证据：\n{merged_context}\n\n"
                        "请严格基于证据回答。"
                    ),
                },
            ]

            if not self.chatbot:
                lines = ["[结论]", "已完成 Confluence 检索，但当前 LLM 不可用。", "", "[候选来源]"]
                for i, src in enumerate(source_list, 1):
                    lines.append(f"{i}. {src.get('title')} ({src.get('url')})")
                return {
                    'success': True,
                    'text': "\n".join(lines),
                    'meta': meta,
                    'sources': source_list,
                }

            answer = ""
            if hasattr(self.chatbot, "chat_completion"):
                answer = str(
                    self.chatbot.chat_completion(
                        messages,
                        temperature=0.2,
                        max_tokens=1200,
                    ) or ""
                ).strip()

            if not answer:
                answer = "基于当前 Confluence 检索结果，暂时无法生成有效总结。"

            source_lines = ["", "[来源]"]
            for i, src in enumerate(source_list, 1):
                source_lines.append(f"{i}. {src.get('title')} - {src.get('url')}")

            return {
                'success': True,
                'text': answer + "\n" + "\n".join(source_lines),
                'meta': meta,
                'sources': source_list,
            }
        except Exception as e:
            logger.error(f"Confluence 模式处理失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'text': f'Confluence 调用失败：{str(e)}',
            }

    def _get_enhanced_system_prompt(self, data_context: str = "") -> str:
        """获取增强的系统提示词 - 使用新的统一模板"""
        # 默认增强提示词（确保任何路径都有可用 prompt）
        base_prompts = {
            'defect': """你是 BMW 汽车测试数据分析专家。

**核心能力：**
1. 缺陷数据分析 - 识别趋势、模式和异常
2. 风险评估 - 评估风险分布和优先级
3. 对比分析 - 对比不同项目的表现
4. 改进建议 - 提供数据驱动的建议

**领域知识：**
- 矩阵分析：1A-1E 为高风险区域
- TopIssue 标记的缺陷需要特别关注
- 严重性：Critical > Major > Minor

**回答风格：**
- 使用专业但易懂的中文
- 每个结论都要有数据支撑
- 提供可执行的改进建议
""",
                'test': """你是测试覆盖率分析专家。

**核心能力：**
1. 测试覆盖率分析
2. 测试效率评估
3. 风险区域识别
4. 测试策略优化

**回答风格：**
- 数据驱动的分析
- 可执行的优化建议
- 关注测试质量而不仅仅是覆盖率
""",
                'general': """你是数据分析助手。

**核心能力：**
1. 数据探索
2. 趋势分析
3. 异常检测
4. 洞察提取

**回答风格：**
- 清晰简洁
- 数据支撑
- 可执行建议
"""
        }

        prompt = base_prompts.get(self.dashboard_type, base_prompts['general'])

        # 优先使用新的 prompt_templates
        try:
            from prompt_templates import get_system_prompt

            template_prompt = get_system_prompt(self.dashboard_type, data_context)
            if isinstance(template_prompt, str) and template_prompt.strip():
                prompt = template_prompt
        except Exception as e:
            # 降级：如果 prompt_templates 不存在或模板执行异常，继续使用回退方案
            logger.warning(f"prompt_templates 不可用，使用降级方案: {e}")
            if self.use_agent and self.intelligent_agent:
                try:
                    agent_prompt = self.intelligent_agent.get_enhanced_system_prompt(data_context)
                    if isinstance(agent_prompt, str) and agent_prompt.strip():
                        prompt = agent_prompt
                except Exception as agent_err:
                    logger.warning(f"智能Agent系统提示词不可用，继续使用默认提示词: {agent_err}")

        if data_context and "**当前数据上下文：**" not in prompt:
            prompt += f"\n\n**当前数据上下文：**\n{data_context}\n"

        prompt += (
            "\n\n**引用规则（防止数字幻觉）：**\n"
            "1) 任何具体数字/占比/TopN，必须来自“当前数据上下文”或工具输出。\n"
            "2) 上下文未提供的数字，不要猜；改用定性描述或明确说明需要补充字段/口径。\n"
            "3) 给测试策略时，优先输出：优先级→动作→验收指标（指标必须可从数据计算）。\n"
        )
        return prompt

    def _get_fallback_response(self, question: str, data_context: str) -> str:
        """降级响应（当 AI 不可用时）"""
        question_lower = question.lower()

        if "总结" in question or "summary" in question_lower:
            return f"基于当前数据分析：\n\n{data_context}\n\n建议关注关键指标和异常点。"

        elif "风险" in question or "risk" in question_lower:
            return """风险分析建议：

1. 优先处理高严重性缺陷（Critical > Major > Minor）
2. 关注矩阵位置 1A-1E 的高风险问题
3. TopIssue 标记的缺陷需要优先处理
4. 分析项目风险分布，识别风险聚集点

建议使用风险评分工具进行量化评估。"""

        elif "趋势" in question or "trend" in question_lower:
            return """趋势分析建议：

1. 分析缺陷数量随时间的变化
2. 识别周期性模式
3. 检测异常波动
4. 预测未来趋势

建议关注周度/月度趋势变化。"""

        elif "对比" in question or "compare" in question_lower:
            return """对比分析建议：

1. 对比不同项目的缺陷数量
2. 对比严重性分布
3. 对比 TopIssue 比例
4. 识别表现最好和最差的项目

建议使用多维度指标进行综合对比。"""

        else:
            return f"感谢您的问题！关于「{question}」，我建议您使用智能分析工具进行深入探索。"

    def _create_initial_conversation_state(self) -> Dict[str, Any]:
        if ENTITY_TRACKER_AVAILABLE and create_initial_conversation_state:
            try:
                initial_state = create_initial_conversation_state()
                return initial_state.to_dict()
            except Exception as e:
                logger.warning(f"Failed to create initial conversation state: {e}")
        return {}

    def _build_route_reasoning(self, route_trace: Optional[Dict[str, Any]]) -> str:
        if not isinstance(route_trace, dict) or not route_trace:
            return ""

        lines = []
        requested_label = route_trace.get("requested_mode_label") or route_trace.get("requested_mode")
        handler_label = route_trace.get("handler_label") or route_trace.get("handler")

        if requested_label:
            lines.append(f"请求模式: {requested_label}")
        if handler_label:
            lines.append(f"执行路由: {handler_label}")

        reason = str(route_trace.get("reason") or "").strip()
        if reason:
            lines.append(f"原因: {reason}")

        if route_trace.get("used_fallback") and route_trace.get("fallback_reason"):
            lines.append(f"回退: {route_trace.get('fallback_reason')}")

        if route_trace.get("should_try_local_data"):
            lines.append(f"本地数据: {'已命中' if route_trace.get('has_data') else '未命中'}")

        return "\n".join(lines).strip()

    def _format_agent_message(self, text: str, tools_used: List[str], insights: List[str]) -> str:
        parts = []
        if text:
            parts.append(text.strip())
        if tools_used:
            parts.append("")
            parts.append("使用工具: " + "、".join(tools_used))
        if insights:
            parts.append("")
            parts.append("关键洞察:")
            for i, ins in enumerate(insights[:5], 1):
                parts.append(f"{i}. {ins}")
        return "\n".join(parts).strip()

    def _has_data(self, data: Any) -> bool:
        if data is None:
            return False
        if isinstance(data, pd.DataFrame):
            return not data.empty
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, pd.DataFrame) and not v.empty:
                    return True
        return False

    def _generate_data_context(self, data: Any, question: str = "", intents: Optional[List[str]] = None) -> str:
        """生成数据上下文 - 使用智能上下文生成器（如果可用）"""
        if not self._has_data(data):
            return "当前没有可用的数据。"
        
        # Try to use smart context generator
        if self.smart_context_generator:
            try:
                # Extract DataFrame from data
                df = None
                dataset_key = None
                if isinstance(data, pd.DataFrame):
                    df = data
                    dataset_key = self.dashboard_type or "dataframe"
                elif isinstance(data, dict):
                    # Try to get defects or tests dataframe
                    df = data.get("defects")
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        dataset_key = "defects"
                    else:
                        df = data.get("tests")
                        if isinstance(df, pd.DataFrame) and not df.empty:
                            dataset_key = "tests"
                    if not isinstance(df, pd.DataFrame):
                        # Get first available dataframe
                        for value in data.values():
                            if isinstance(value, pd.DataFrame) and not value.empty:
                                df = value
                                dataset_key = "dataframe"
                                break
                
                if df is not None and not df.empty:
                    context = self.smart_context_generator.generate_context(
                        question=question,
                        full_data=df,
                        intents=intents,
                        dataset_key=dataset_key
                    )
                    logger.info("Using smart context generator")
                    return context
            except Exception as e:
                logger.warning(f"Smart context generator failed, falling back to default: {e}")
        
        # Fallback to original context generation
        return self._generate_data_context_fallback(data)
    
    def _generate_data_context_fallback(self, data: Any) -> str:
        """原始的数据上下文生成方法（作为降级方案）"""
        if not self._has_data(data):
            return "当前没有可用的数据。"

        def top_counts_safe(df: pd.DataFrame, col: str, top_n: int = 5) -> Dict[str, int]:
            if df is None or df.empty or col not in df.columns:
                return {}
            s = df[col].fillna("").astype(str).map(lambda x: x.strip())
            s = s[s != ""]
            if s.empty:
                return {}
            return s.value_counts().head(top_n).to_dict()

        def critical_mask(df: pd.DataFrame) -> pd.Series:
            if df is None or df.empty:
                return pd.Series([], dtype=bool)
            col = "severity_group" if "severity_group" in df.columns else "severity" if "severity" in df.columns else None
            if not col:
                return pd.Series([False] * len(df), index=df.index, dtype=bool)
            s = df[col].fillna("").astype(str).str.lower()
            return s.str.contains("critical")

        def summarize_defects(df: pd.DataFrame) -> List[str]:
            parts: List[str] = ["缺陷（defects）摘要："]
            parts.append(f"- 总缺陷数: {len(df)}")
            severe = int(critical_mask(df).sum())
            severe_rate = round(severe / len(df) * 100, 2) if len(df) else 0.0
            parts.append(f"- 严重缺陷数: {severe}，严重缺陷率: {severe_rate}%")
            if "is_topissue" in df.columns:
                topissue_cnt = int(pd.to_numeric(df["is_topissue"], errors="coerce").fillna(0).astype(int).sum())
                parts.append(f"- TopIssue 数: {topissue_cnt}（占 {round(topissue_cnt/len(df)*100,2) if len(df) else 0.0}%）")
            if "is_long_runner" in df.columns:
                lr_cnt = int(pd.to_numeric(df["is_long_runner"], errors="coerce").fillna(0).astype(int).sum())
                parts.append(f"- LongRunner 数: {lr_cnt}（占 {round(lr_cnt/len(df)*100,2) if len(df) else 0.0}%）")
            for col, title in [
                ("matrix_display", "矩阵Top"),
                ("aida_english", "AIDA Top"),
                ("fv", "FV Top"),
                ("domain_display", "Solution Cluster Top"),
                ("domain", "Solution Cluster Top"),
                ("project", "项目(project) Top"),
                ("tproject", "项目(tproject) Top"),
                ("ecu", "项目(ECU) Top"),
                ("status_phase", "状态Top"),
            ]:
                counts = top_counts_safe(df, col, top_n=5)
                if counts:
                    parts.append(f"- {title}: {counts}")
                    if col in {"domain_display", "domain"}:
                        break
                    if col in {"project", "tproject", "ecu"}:
                        break
            return parts

        def summarize_tests(df: pd.DataFrame) -> List[str]:
            parts: List[str] = ["测试（tests）摘要："]
            parts.append(f"- 总测试执行数: {len(df)}")
            status_col = "run_status" if "run_status" in df.columns else "status" if "status" in df.columns else None
            if not status_col:
                return parts
            s = df[status_col].fillna("").astype(str).str.lower()
            failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
            is_fail = s.apply(lambda x: any(k in x for k in failure_keywords))
            overall_total = int(len(df))
            overall_failure = int(is_fail.sum())
            overall_rate = round(overall_failure / overall_total * 100, 2) if overall_total else 0.0
            parts.append(f"- 失败数: {overall_failure}，总体失败率: {overall_rate}%")

            time_col = "finished_udf_dt" if "finished_udf_dt" in df.columns else "tcreationtime" if "tcreationtime" in df.columns else "finished_udf" if "finished_udf" in df.columns else None
            if time_col and time_col in df.columns:
                ts = pd.to_datetime(df[time_col], errors="coerce")
                tmp = df.copy()
                tmp["_t"] = ts
                tmp = tmp[tmp["_t"].notna()]
                if not tmp.empty:
                    tmp["_w"] = tmp["_t"].dt.to_period("W").astype(str)
                    tmp["_fail"] = is_fail.reindex(tmp.index).fillna(False).astype(int)
                    agg = tmp.groupby("_w").agg(total=("_w", "size"), failure=("_fail", "sum")).reset_index()
                    agg["failure_rate"] = np.where(agg["total"] > 0, (agg["failure"] / agg["total"] * 100).round(2), 0.0)
                    top = agg.sort_values("failure_rate", ascending=False).head(5)
                    rows = [f"{r['_w']}: {r['failure_rate']}% (总{int(r['total'])})" for _, r in top.iterrows()]
                    if rows:
                        parts.append("- 失败率Top5(按周): " + "; ".join(rows))
            return parts

        context_parts = ["数据集概览："]
        if isinstance(data, pd.DataFrame):
            if "run_status" in data.columns or "finished_udf_dt" in data.columns:
                context_parts.extend(summarize_tests(data))
            else:
                context_parts.extend(summarize_defects(data))
        elif isinstance(data, dict):
            defects_df = data.get("defects")
            tests_df = data.get("tests")
            if isinstance(defects_df, pd.DataFrame) and not defects_df.empty:
                context_parts.extend(summarize_defects(defects_df))
            if isinstance(tests_df, pd.DataFrame) and not tests_df.empty:
                context_parts.extend(summarize_tests(tests_df))
            if not isinstance(defects_df, pd.DataFrame) and not isinstance(tests_df, pd.DataFrame):
                for name, df in data.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        context_parts.append(f"数据集[{name}]：")
                        context_parts.append(f"- 总记录数: {len(df)}")
                        context_parts.append(f"- 列数: {len(df.columns)}")

        return "\n".join(context_parts)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'EnhancedAIChatManager',
]


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("增强版 AI Chat Manager 测试")
    print("=" * 50)

    # 测试创建
    manager = EnhancedAIChatManager('defect', use_agent=True)
    print("Enhanced AI Chat Manager created successfully")
    print(f"   - 看板类型: {manager.dashboard_type}")
    print(f"   - Agent启用: {manager.use_agent}")
    print(f"   - 预设问题数: {len(manager.preset_questions[manager.dashboard_type])}")
