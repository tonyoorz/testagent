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
from dataclasses import is_dataclass
from typing import Dict, List, Any, Optional, Callable, Generator
from datetime import datetime
import pandas as pd
import numpy as np
import io
import httpx

import dash
from dash import dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

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
from agent.core.conversation_orchestrator import ConversationOrchestrator
from agent.core.proactive_insight_engine import ProactiveInsightEngine
from agent.core.proactive_insight_reporter import ProactiveInsightReporter
from agent.core.proactive_insight_router import ProactiveInsightRouter
from agent.core.prompt_registry import PromptRegistry
from agent.core.session_manager import SessionManager
from agent.core.streaming_protocol import append_event as append_protocol_event, init_stream_state
from agent.evaluation.agent_critic import contains_strong_confident_language
from duplicate_issue_finder import extract_hints, get_or_build_index
from feedback_store import FeedbackStore
from agent.multimodal.dash_components import (
    create_multimodal_upload_component,
    register_multimodal_callbacks,
    extract_image_bytes_from_store,
    extract_audio_bytes_from_store,
)
from agent.multimodal.duplicate_search_multimodal import MultimodalDuplicateSearcher
from octane_db import default_db_path


def _get_current_user_id() -> str:
    """Read username from login_info.txt, fall back to 'anonymous'."""
    try:
        login_path = os.path.join(PROJECT_ROOT, 'login_info.txt')
        if os.path.isfile(login_path):
            with open(login_path, 'r', encoding='utf-8') as fh:
                info = json.loads(fh.read())
                return str(info.get('username') or 'anonymous').strip()
    except Exception:
        pass
    return 'anonymous'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging first before importing enhancement modules
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_POSITIVE_CONFIRMATION_REPLIES = {
    "继续", "继续执行", "确认", "确认执行", "是", "好的", "好", "ok", "yes", "y", "proceed", "continue",
}
_DUPLICATE_FOLLOWUP_MAX_LEN = 40
_DUPLICATE_FOLLOWUP_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"需要补充",
        r"补充信息",
        r"补充.*现象",
        r"补充.*复现",
        r"请补充",
        r"再判断",
        r"provide more information",
        r"need more information",
        r"need more details",
    ]
]


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


def _assistant_requests_duplicate_followup(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _DUPLICATE_FOLLOWUP_PATTERNS)


def _analyze_duplicate_followup_chain(
    question: str, conversation_history: Optional[List[Dict[str, Any]]]
) -> tuple:
    """Walk backward through conversation history to accumulate a multi-round
    duplicate-detection follow-up chain.

    Returns ``(effective_query, followup_round_count)``.
    *followup_round_count* is 0 when the current message is a standalone query.
    """
    current_question = str(question or "").strip()
    if not current_question:
        return ("", 0)
    if len(current_question) > _DUPLICATE_FOLLOWUP_MAX_LEN:
        return (current_question, 0)

    messages = [msg for msg in (conversation_history or []) if isinstance(msg, dict)]

    # Locate the current user message in history
    current_index = None
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if str(msg.get("role") or "").strip() != "user":
            continue
        if str(msg.get("content") or "").strip() == current_question:
            current_index = idx
            break

    if current_index is None:
        return (current_question, 0)

    # Walk backward collecting all user messages that belong to the chain.
    # Pattern: ...user → [reasoning*] → assistant("需要补充") → [reasoning*] → user → ...
    prior_user_messages: List[str] = []
    scan_idx = current_index - 1

    while scan_idx >= 0:
        # Step 1: find the nearest meaningful assistant message
        found_followup_assistant = False
        while scan_idx >= 0:
            msg = messages[scan_idx]
            role = str(msg.get("role") or "").strip()
            if role != "assistant":
                scan_idx -= 1
                continue
            content = str(msg.get("content") or "").strip()
            # Skip empty / placeholder assistant messages
            if not content or content == "AI正在思考...":
                scan_idx -= 1
                continue
            # First real assistant content — does it ask for follow-up?
            if _assistant_requests_duplicate_followup(content):
                found_followup_assistant = True
                scan_idx -= 1
                break
            else:
                # Assistant gave a definitive answer → chain ends
                break

        if not found_followup_assistant:
            break

        # Step 2: find the user message before this assistant
        found_user = False
        while scan_idx >= 0:
            msg = messages[scan_idx]
            role = str(msg.get("role") or "").strip()
            if role == "user":
                user_content = str(msg.get("content") or "").strip()
                if user_content:
                    prior_user_messages.append(user_content)
                    found_user = True
                    scan_idx -= 1
                    break
            scan_idx -= 1

        if not found_user:
            break

    if not prior_user_messages:
        return (current_question, 0)

    # prior_user_messages is in reverse chronological order → reverse to get [Q1, Q2, …]
    prior_user_messages.reverse()

    original = prior_user_messages[0]
    supplements = prior_user_messages[1:] + [current_question]

    # P0-3: Try LLM summarization for better followup query
    # Falls back to simple concatenation if LLM unavailable
    effective_query = _summarize_followup_with_llm(original, supplements)
    if not effective_query:
        effective_query = f"{original}\n补充信息：{'；'.join(supplements)}"
    return (effective_query, len(prior_user_messages))


def _summarize_followup_with_llm(original: str, supplements: List[str]) -> Optional[str]:
    """P0-3: Use LLM to condense multi-round followup into one precise query.

    Returns None if LLM is unavailable, so caller falls back to simple concatenation.
    """
    if not supplements:
        return original
    try:
        chatbot = DeepSeekStreamingChat()
        if not getattr(chatbot, 'client', None):
            return None
        context = f"原始描述：{original}"
        for i, s in enumerate(supplements, 1):
            context += f"\n补充{i}：{s}"
        prompt = (
            "请将以下多轮缺陷描述合并为一个简洁精准的查询语句（一句话，不超过100字）。"
            "只输出合并后的语句，不要解释。\n\n" + context
        )
        messages = [{"role": "user", "content": prompt}]
        result = str(chatbot.chat_completion(messages, temperature=0.1, max_tokens=200) or "").strip()
        if result and len(result) <= 200:
            return result
        return None
    except Exception as e:
        logger.debug(f"Followup LLM 摘要失败，使用拼接模式: {e}")
        return None


def build_duplicate_followup_query(
    question: str, conversation_history: Optional[List[Dict[str, Any]]]
) -> str:
    """Reconstruct the effective search query by merging prior follow-up turns."""
    return _analyze_duplicate_followup_chain(question, conversation_history)[0]


def count_duplicate_followup_rounds(
    question: str, conversation_history: Optional[List[Dict[str, Any]]]
) -> int:
    """Count how many supplementary rounds preceded *question* in a duplicate
    detection follow-up chain.  Returns 0 for standalone queries."""
    return _analyze_duplicate_followup_chain(question, conversation_history)[1]


def _build_enhanced_duplicate_result_payload(
    query_text: str,
    dashboard_type: str,
    candidates: List[Any],
) -> Dict[str, Any]:
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


def append_duplicate_result_message(
    chat_messages: List[Dict[str, Any]],
    stream_state: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    updated_messages = list(chat_messages or [])
    payload = dict((stream_state or {}).get("duplicate_payload") or {})
    if not (stream_state or {}).get("is_duplicate_search") or not payload:
        return updated_messages

    if updated_messages:
        last_message = updated_messages[-1]
        if (
            last_message.get("type") == "duplicate-search-result"
            and dict(last_message.get("duplicate_result") or {}).get("query_text") == payload.get("query_text")
        ):
            return updated_messages

    updated_messages.append(
        {
            "role": "assistant",
            "type": "duplicate-search-result",
            "content": "",
            "duplicate_result": payload,
        }
    )
    return updated_messages


def render_enhanced_duplicate_result_message(message: Dict[str, Any], chat_id_prefix: str) -> html.Div:
    payload = dict(message.get("duplicate_result") or {})
    query_text = str(payload.get("query_text") or "").strip()
    candidates = list(payload.get("candidates") or [])
    cards: List[Any] = []

    for candidate in candidates:
        ticket_id = str(candidate.get("ticket_id") or "")
        rank_pos = int(candidate.get("rank_pos", 0) or 0)
        meta = " / ".join(
            [value for value in [candidate.get("project"), candidate.get("pu"), candidate.get("status_phase")] if value]
        )
        cards.append(
            html.Div(
                [
                    html.Div(f"{candidate.get('score_1_10', 1)} 分", style={"fontWeight": "bold", "color": "#1f4b99"}),
                    html.Div(f"#{ticket_id or '(未知ID)'} - {candidate.get('name', '') or '(无标题)'}", style={"marginTop": "4px"}),
                    html.Div(meta or "-", style={"marginTop": "4px", "fontSize": "12px", "color": "#64748b"}),
                    html.Div(
                        candidate.get("snippet", ""),
                        style={"marginTop": "6px", "fontSize": "13px", "color": "#475569", "whiteSpace": "pre-line"},
                    ),
                    html.Div(
                        [
                            html.Button(
                                "✅ 是重复",
                                id={
                                    "type": f"{chat_id_prefix}-dup-feedback",
                                    "signal": "positive",
                                    "query": query_text[:200],
                                    "ticket": ticket_id,
                                    "idx": rank_pos,
                                },
                                n_clicks=0,
                                style={
                                    "padding": "6px 10px",
                                    "backgroundColor": "#e8f5e9",
                                    "border": "1px solid #81c784",
                                    "borderRadius": "6px",
                                    "cursor": "pointer",
                                },
                            ),
                            html.Button(
                                "❌ 不是",
                                id={
                                    "type": f"{chat_id_prefix}-dup-feedback",
                                    "signal": "negative",
                                    "query": query_text[:200],
                                    "ticket": ticket_id,
                                    "idx": rank_pos,
                                },
                                n_clicks=0,
                                style={
                                    "padding": "6px 10px",
                                    "backgroundColor": "#ffebee",
                                    "border": "1px solid #ef9a9a",
                                    "borderRadius": "6px",
                                    "cursor": "pointer",
                                    "marginLeft": "8px",
                                },
                            ),
                            html.Button(
                                "🤔 不确定",
                                id={
                                    "type": f"{chat_id_prefix}-dup-feedback",
                                    "signal": "uncertain",
                                    "query": query_text[:200],
                                    "ticket": ticket_id,
                                    "idx": rank_pos,
                                },
                                n_clicks=0,
                                style={
                                    "padding": "6px 10px",
                                    "backgroundColor": "#fff8e1",
                                    "border": "1px solid #ffe082",
                                    "borderRadius": "6px",
                                    "cursor": "pointer",
                                    "marginLeft": "8px",
                                },
                            ),
                        ],
                        style={"marginTop": "10px"},
                    ),
                ],
                style={
                    "padding": "10px",
                    "border": "1px solid #e2e8f0",
                    "borderRadius": "8px",
                    "marginTop": "10px",
                    "backgroundColor": "#ffffff",
                },
            )
        )

    return html.Div(
        [
            html.Div(
                [
                    html.I(className="fas fa-robot", style={"marginRight": "8px", "color": "#3498db"}),
                    html.Span("SiSi", style={"fontWeight": "bold", "color": "#3498db"}),
                ],
                style={"marginBottom": "5px"},
            ),
            html.Div(message.get("content", ""), style={"whiteSpace": "pre-line", "paddingLeft": "24px"}),
            html.Div(cards, style={"marginTop": "12px", "paddingLeft": "24px"}),
        ],
        style={
            "padding": "12px",
            "backgroundColor": "#f8f9fa",
            "borderRadius": "8px",
            "margin": "8px 0",
            "textAlign": "left",
            "border": "1px solid #e9ecef",
            "marginRight": "20px",
        },
    )

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
    return append_protocol_event(
        stream_entry,
        kind=str(kind or "info").strip() or "info",
        title=str(title or "事件").strip() or "事件",
        status=_normalize_event_status(status),
        summary=str(summary or "").strip(),
        details=_sanitize_event_details(details),
        limit=_timeline_event_limit(),
    )


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


def build_summary_schema_column_views(columns: Optional[List[str]], preview_limit: int = 30) -> Dict[str, List[str]]:
    normalized: List[str] = []
    seen = set()
    for raw in columns or []:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)

    safe_limit = max(0, int(preview_limit or 0))
    return {
        "full": normalized,
        "preview": normalized[:safe_limit] if safe_limit else [],
    }


def resolve_summary_scope_team(semantic_hints: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    disabled_tokens = {"*", "all", "any", "none", "off", "false", "0"}
    hints = semantic_hints if isinstance(semantic_hints, dict) else {}

    existing_scope_team = str(hints.get("scope_team") or "").strip()
    if existing_scope_team and existing_scope_team.lower() not in disabled_tokens:
        return {
            "scope_team": existing_scope_team,
            "source": "semantic_hints",
        }

    configured_scope_team = str(
        os.getenv("CHAT_SUMMARY_SCOPE_TEAM")
        or os.getenv("OCTANE_TEAM")
        or ""
    ).strip()
    if configured_scope_team and configured_scope_team.lower() not in disabled_tokens:
        return {
            "scope_team": configured_scope_team,
            "source": "CHAT_SUMMARY_SCOPE_TEAM/OCTANE_TEAM",
        }

    return {
        "scope_team": "",
        "source": "",
    }


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
        self._conversation_orchestrator = ConversationOrchestrator()
        self.prompt_registry = PromptRegistry.get_instance()
        self.session_manager = SessionManager()
        self.proactive_insight_router = None
        self.proactive_insight_engine = None
        self.proactive_insight_reporter = None
        
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
        self.preset_questions = self._build_default_presets()

    def _build_default_presets(self) -> Dict[str, Dict[str, str]]:
        return {
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
                'team': "请分析测试团队效率和缺陷发现能力",
                'proactive_insight': "请做主动洞察"
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
                'agent_explore': "请使用智能工具探索数据",
                'proactive_insight': "请做主动洞察"
            }
        }

    def _get_chat_model_options(self) -> List[str]:
        env_raw = str(os.getenv("CHAT_MODEL_OPTIONS") or "").strip()
        env_models = [m.strip() for m in env_raw.split(",") if str(m).strip()] if env_raw else []
        defaults = [
            str(DEEPSEEK_MODEL or "").strip(),
            "glm-5",
            "qwen3.5-397b-a17b",
            "deepseek-v3.2",
        ]
        merged = env_models + defaults
        seen = set()
        ordered: List[str] = []
        for model_name in merged:
            name = str(model_name or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(name)
        return ordered or ["glm-5"]

    def _get_default_chat_model(self) -> str:
        options = self._get_chat_model_options()
        current = str(getattr(self.chatbot, "model", "") or "").strip() if getattr(self, "chatbot", None) else ""
        if current:
            for opt in options:
                if str(opt).strip().lower() == current.lower():
                    return opt
        return options[0]

    def _get_internal_endpoint_for_model(self, model_name: str) -> str:
        raw_map = str(os.getenv("CHAT_MODEL_ENDPOINTS") or "").strip()
        endpoint_map: Dict[str, str] = {}
        if raw_map:
            try:
                parsed = json.loads(raw_map)
                if isinstance(parsed, dict):
                    endpoint_map = {str(k).strip().lower(): str(v).strip() for k, v in parsed.items() if str(k).strip() and str(v).strip()}
            except Exception:
                logger.warning("CHAT_MODEL_ENDPOINTS 解析失败，忽略该配置")

        if not endpoint_map:
            endpoint_map = {
                "deepseek-v3.2": "https://aistudio.bmwbrill.cn/api/service/160/{access_code}/llama4/v2/chat/completions",
                "qwen3.5-397b-a17b": "https://aistudio.bmwbrill.cn/api/service/164/ernie/v2/chat/completions",
            }

        key = str(model_name or "").strip().lower()
        return str(endpoint_map.get(key) or "").strip()

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
        normalized_lower = normalized_question.lower()

        if trigger == 'proactive_insight':
            updated_context['mode'] = 'proactive_insight'
            updated_context['entry_point'] = 'proactive_insight_button'
            return {
                'question': normalized_question or '请做主动洞察',
                'extra_context': updated_context,
            }

        if normalized_lower == '/proactive-insight' or normalized_lower.startswith('/proactive-insight '):
            updated_context['mode'] = 'proactive_insight'
            updated_context['entry_point'] = 'proactive_insight_slash'
            return {
                'question': '请做主动洞察',
                'extra_context': updated_context,
            }

        return {
            'question': normalized_question,
            'extra_context': updated_context,
        }

    def _build_agent_request(
        self,
        question: str,
        current_data: Any,
        conversation_state: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = self._conversation_orchestrator.build_request(
            question=question,
            dashboard_type=self.dashboard_type,
            current_data=current_data,
            conversation_state=conversation_state,
            extra_context=extra_context,
        )
        session_id = self._resolve_session_id(
            extra_context=extra_context,
            conversation_state=conversation_state,
        )
        request['session_id'] = session_id
        if getattr(self, 'session_manager', None):
            session = self.session_manager.get_or_create(session_id, dashboard_type=self.dashboard_type)
            page_context = request.get('page_context') if isinstance(request.get('page_context'), dict) else {}
            page_filters = {}
            if isinstance(extra_context, dict) and isinstance(extra_context.get('page_filters'), dict):
                page_filters = dict(extra_context.get('page_filters') or {})
            session.data_context.update_from_request(
                {
                    'question': request.get('question'),
                    'page_context': page_context,
                    'page_filters': page_filters,
                    'data_summary': page_context.get('data_summary') if isinstance(page_context, dict) else '',
                }
            )
        return request

        logger.info(f"增强版AI Chat Manager初始化完成 (Agent: {'启用' if self.use_agent else '禁用'})")

    def _resolve_session_id(
        self,
        *,
        extra_context: Optional[Dict[str, Any]] = None,
        conversation_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        candidates = []
        if isinstance(extra_context, dict):
            candidates.extend(
                [
                    extra_context.get('session_id'),
                    extra_context.get('chat_session_id'),
                    extra_context.get('chat_id_prefix'),
                ]
            )
        if isinstance(conversation_state, dict):
            candidates.extend(
                [
                    conversation_state.get('session_id'),
                    conversation_state.get('chat_id_prefix'),
                ]
            )
        for candidate in candidates:
            value = str(candidate or '').strip()
            if value:
                return f'{value}:{self.dashboard_type}'
        return f'{self.dashboard_type}:default'

    def _ensure_proactive_insight_components(self) -> None:
        if not getattr(self, 'proactive_insight_router', None):
            self.proactive_insight_router = ProactiveInsightRouter()
        if not getattr(self, 'proactive_insight_engine', None):
            self.proactive_insight_engine = ProactiveInsightEngine()
        if not getattr(self, 'proactive_insight_reporter', None):
            self.proactive_insight_reporter = ProactiveInsightReporter()

    def _serialize_proactive_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._serialize_proactive_value(item) for item in value]
        if isinstance(value, dict):
            return {
                key: self._serialize_proactive_value(item)
                for key, item in value.items()
            }
        if is_dataclass(value) and hasattr(value, 'to_dict'):
            return self._serialize_proactive_value(value.to_dict())
        return value

    def process_with_agent(self, question: str, data: pd.DataFrame,
                          conversation_history: List = None,
                          conversation_state: Optional[Dict] = None,
                          progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
                          extra_context: Optional[Dict[str, Any]] = None,
                          agent_request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        self._ensure_proactive_insight_components()
        try:
            proactive_matched, proactive_request = self.proactive_insight_router.match(
                question=question,
                extra_context=extra_context,
            )
            if proactive_matched:
                effective_request = agent_request if isinstance(agent_request, dict) else self._build_agent_request(
                    question,
                    data,
                    conversation_state=conversation_state,
                    extra_context=extra_context,
                )
                page_context = effective_request.get('page_context') if isinstance(effective_request.get('page_context'), dict) else {}
                datasets = data if isinstance(data, dict) else {'defects': data}
                proactive_cards = self.proactive_insight_engine.generate(
                    request=proactive_request,
                    datasets=datasets,
                )
                proactive_report_text = self.proactive_insight_reporter.render(proactive_cards)
                result_context = {
                    'proactive_insight_mode': True,
                    'proactive_insight_request': self._serialize_proactive_value(proactive_request),
                    'proactive_insight_cards': self._serialize_proactive_value(proactive_cards),
                }
                if page_context:
                    result_context.setdefault('page_context', page_context)
                if isinstance(extra_context, dict) and extra_context:
                    result_context.update(extra_context)
                return {
                    'success': True,
                    'text': proactive_report_text,
                    'insights': [],
                    'visualizations': [],
                    'tools_used': [],
                    'context': result_context,
                    'agent_used': True,
                    'conversation_state': conversation_state,
                    'resolved_question': None,
                }
        except Exception as proactive_err:
            fallback_request = agent_request if isinstance(agent_request, dict) else self._build_agent_request(
                question,
                data,
                conversation_state=conversation_state,
                extra_context=extra_context,
            )
            page_context = fallback_request.get('page_context') if isinstance(fallback_request.get('page_context'), dict) else {}
            result_context = {
                'proactive_insight_mode': True,
                'proactive_insight_error': str(proactive_err),
            }
            if page_context:
                result_context.setdefault('page_context', page_context)
            if isinstance(extra_context, dict) and extra_context:
                result_context.update(extra_context)
            return {
                'success': True,
                'error': str(proactive_err),
                'text': '已进入主动洞察模式，但当前无法完成分析。请检查数据范围或稍后重试。',
                'insights': [],
                'visualizations': [],
                'tools_used': [],
                'context': result_context,
                'agent_used': True,
                'conversation_state': conversation_state,
                'resolved_question': None,
            }

        if not self.use_agent or not self.intelligent_agent:
            return {
                'success': False,
                'error': '智能Agent系统不可用',
                'text': '抱歉，智能分析功能当前不可用。请使用普通对话功能。'
            }

        runtime = self._conversation_orchestrator.prepare_runtime(
            question=question,
            dashboard_type=self.dashboard_type,
            current_data=data,
            conversation_state=conversation_state,
            extra_context=extra_context,
            agent_results={},
            progress='AI正在分析问题...',
        )
        guardrail_decision = runtime['guardrail_decision']

        if guardrail_decision.action == 'confirm':
            return {
                'success': True,
                'text': '需要确认后才能继续执行当前分析请求。',
                'agent_used': True,
                'needs_confirmation': True,
                'context': {
                    'guardrail_reason': guardrail_decision.reason_code,
                    'stream_state': runtime['stream_state'],
                },
                'conversation_state': conversation_state,
            }

        if guardrail_decision.action == 'fallback':
            return self._legacy_process_with_agent(
                question,
                data,
                conversation_history=conversation_history,
                conversation_state=conversation_state,
                progress_cb=progress_cb,
                extra_context=extra_context,
                agent_request=agent_request,
            )

        effective_agent_request = agent_request if isinstance(agent_request, dict) else runtime.get('request')
        result = self._process_with_agent_core(
            question,
            data,
            conversation_history=conversation_history,
            conversation_state=conversation_state,
            progress_cb=progress_cb,
            extra_context=extra_context,
            agent_request=effective_agent_request,
        )
        if result.get('success'):
            return result

        recovery = self._conversation_orchestrator.recovery_policy.resolve(
            reason_code='runtime_exception',
            error=result.get('error'),
        )
        if recovery.action == 'fallback':
            return self._legacy_process_with_agent(
                question,
                data,
                conversation_history=conversation_history,
                conversation_state=conversation_state,
                progress_cb=progress_cb,
                extra_context=extra_context,
                agent_request=agent_request,
            )
        return result

    def _legacy_process_with_agent(self, question: str, data: pd.DataFrame,
                                   conversation_history: List = None,
                                   conversation_state: Optional[Dict] = None,
                                   progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
                                   extra_context: Optional[Dict[str, Any]] = None,
                                   agent_request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._process_with_agent_core(
            question,
            data,
            conversation_history=conversation_history,
            conversation_state=conversation_state,
            progress_cb=progress_cb,
            extra_context=extra_context,
            agent_request=agent_request,
        )

    def _process_with_agent_core(self, question: str, data: pd.DataFrame,
                                 conversation_history: List = None,
                                 conversation_state: Optional[Dict] = None,
                                 progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
                                 extra_context: Optional[Dict[str, Any]] = None,
                                 agent_request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.use_agent or not self.intelligent_agent:
            return {
                'success': False,
                'error': '智能Agent系统不可用',
                'text': '抱歉，智能分析功能当前不可用。请使用普通对话功能。'
            }

        try:
            # 实体追踪：指代消解
            initial_request_question = ''
            if isinstance(agent_request, dict):
                initial_request_question = str(agent_request.get('question') or '').strip()
            resolved_question = initial_request_question or question
            updated_state = conversation_state
            agent_request = agent_request if isinstance(agent_request, dict) else self._build_agent_request(
                question=question,
                current_data=data,
                conversation_state=conversation_state,
                extra_context=extra_context,
            )
            page_context = agent_request.get('page_context', {}) if isinstance(agent_request, dict) else {}

            if self.entity_tracker and conversation_state is not None:
                try:
                    # 恢复对话状态
                    state = ConversationState.from_dict(conversation_state) if ConversationState else None
                    if state:
                        # 指代消解
                        resolved_question = self.entity_tracker.resolve_references(resolved_question, state)
                        if resolved_question != question:
                            logger.info(f"Entity resolution: '{question}' -> '{resolved_question}'")
                except Exception as e:
                    logger.warning(f"Entity resolution failed: {e}")

            if isinstance(agent_request, dict):
                agent_request['question'] = resolved_question

            # 使用智能 Agent 处理
            result = self.intelligent_agent.process(
                resolved_question,
                data,
                conversation_history,
                progress_cb=progress_cb,
                page_context=page_context,
                request=agent_request,
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
            result_context = result.get('context', {}) if isinstance(result.get('context', {}), dict) else {}
            result_context = dict(result_context)
            if page_context:
                result_context.setdefault('page_context', page_context)
            if isinstance(extra_context, dict) and extra_context:
                result_context.update(extra_context)
            if getattr(self, 'session_manager', None) and isinstance(agent_request, dict):
                session_id = str(agent_request.get('session_id') or '').strip() or self._resolve_session_id(
                    extra_context=extra_context,
                    conversation_state=conversation_state,
                )
                session = self.session_manager.get_or_create(session_id, dashboard_type=self.dashboard_type)
                trace = result_context.get('analysis_trace') if isinstance(result_context.get('analysis_trace'), dict) else {}
                intents = result_context.get('intents') if isinstance(result_context.get('intents'), list) else []
                session.query_memory.add_query(
                    resolved_question,
                    answer=result.get('text', ''),
                    intents=intents,
                    trace=trace,
                    metadata={'tools_used': result.get('tools_used', [])},
                )

            return {
                'success': True,
                'text': result['text'],
                'insights': result.get('insights', []),
                'visualizations': result.get('visualizations', []),
                'tools_used': result.get('tools_used', []),
                'context': result_context,
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
        registry = getattr(self, 'prompt_registry', None)
        if registry:
            try:
                prompt = registry.render_dashboard_prompt(self.dashboard_type, data_context=data_context)
                if isinstance(prompt, str) and prompt.strip():
                    if data_context and "**当前数据上下文：**" not in prompt and 'Current Data Context:' not in prompt:
                        prompt += f"\n\n**当前数据上下文：**\n{data_context}\n"
                    prompt += (
                        "\n\n**引用规则（防止数字幻觉）：**\n"
                        "1) 任何具体数字/占比/TopN，必须来自“当前数据上下文”或工具输出。\n"
                        "2) 上下文未提供的数字，不要猜；改用定性描述或明确说明需要补充字段/口径。\n"
                        "3) 给测试策略时，优先输出：优先级→动作→验收指标（指标必须可从数据计算）。\n"
                    )
                    return prompt
            except Exception as registry_err:
                logger.warning(f"PromptRegistry 不可用，回退到现有提示词逻辑: {registry_err}")

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

    def create_enhanced_chat_interface(self, chat_id_prefix: str = 'chat') -> html.Div:
        """
        创建增强版聊天界面组件

        新增功能：
        - Agent 模式切换开关
        - 工具调用结果显示
        - 数据可视化嵌入
        """
        # 获取预设问题
        preset_questions = self.preset_questions.get(
            self.dashboard_type,
            self.preset_questions['general']
        )

        # 创建预设按钮
        preset_buttons = []
        button_colors = [
            {'bg': '#e3f2fd', 'color': '#1976d2', 'border': '#1976d2'},
            {'bg': '#fce4ec', 'color': '#c2185b', 'border': '#c2185b'},
            {'bg': '#fff3e0', 'color': '#f57c00', 'border': '#f57c00'},
            {'bg': '#e8f5e8', 'color': '#388e3c', 'border': '#388e3c'},
            {'bg': '#f3e5f5', 'color': '#7b1fa2', 'border': '#7b1fa2'},
            {'bg': '#e0f2f1', 'color': '#00796b', 'border': '#00796b'},
            {'bg': '#fff8e1', 'color': '#f57f17', 'border': '#f57f17'}  # Agent 专用
        ]

        for i, (key, question) in enumerate(preset_questions.items()):
            color_scheme = button_colors[i % len(button_colors)]
            is_agent_button = 'agent' in key

            button_id = f'{chat_id_prefix}-{key}-btn'
            preset_buttons.append(
                html.Button(
                    question,
                    id=button_id,
                    n_clicks=0,
                    className='chat-quick-btn',
                    style={
                        'margin': '3px',
                        'padding': '5px 10px',
                        'fontSize': '11px',
                        'backgroundColor': color_scheme['bg'],
                        'color': color_scheme['color'],
                        'border': f"1px solid {color_scheme['border']}",
                        'borderRadius': '13px',
                        'cursor': 'pointer',
                        'transition': 'all 0.3s ease',
                        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)' if is_agent_button else 'none'
                    }
                )
            )

        # UI 默认选中 Agent（数据库直读）模式，避免首次进入直接落到 Skill 工具链。
        default_mode = "summary"
        chat_model_options = self._get_chat_model_options()
        default_chat_model = self._get_default_chat_model()

        # 构建界面 — ChatGPT/Claude 风格
        interface = html.Div([
            # ── 消息滚动区 ──
            html.Div([
                # 对话历史（callback 动态填充，也承载欢迎屏逻辑）
                html.Div(
                    id=f'{chat_id_prefix}-history',
                    children=[
                        # 默认欢迎屏（callback 会替换整个 children）
                        html.Div([
                            html.Div('🤖', style={'fontSize': '48px', 'textAlign': 'center', 'marginBottom': '12px'}),
                            html.H2(
                                f'你好，我是{self.assistant_name}',
                                style={'textAlign': 'center', 'color': '#1a1a2e', 'fontWeight': '700', 'marginBottom': '8px', 'fontSize': '24px', 'border': 'none', 'padding': '0'}
                            ),
                            html.P(
                                '我可以帮你分析缺陷数据、查询测试状态、生成报告等',
                                style={'textAlign': 'center', 'color': '#6b7280', 'fontSize': '14px', 'marginBottom': '24px'}
                            ),
                            # 预设问题 2 列网格
                            html.Div(
                                preset_buttons,
                                className='chat-preset-grid'
                            )
                        ], className='chat-welcome')
                    ],
                    className='chat-messages'
                ),
            ], style={'flex': '1 1 auto', 'minHeight': '0', 'overflowY': 'auto', 'display': 'flex', 'flexDirection': 'column'}),

            # ── 底部固定输入区 ──
            html.Div([
                # 状态显示（保留 ID）
                html.Div(
                    id=f'{chat_id_prefix}-status',
                    children=[],
                    style={'textAlign': 'center', 'fontSize': '12px', 'color': '#999', 'minHeight': '0', 'padding': '2px 0'}
                ),

                # 控制：模式 + 已知问题 + 模型
                html.Div([
                    html.Div([
                        dcc.RadioItems(
                            id=f'{chat_id_prefix}-chat-mode',
                            options=[
                                {'label': ' 纯聊天', 'value': 'pure'},
                                {'label': ' RAG', 'value': 'rag'},
                                {'label': ' Confluence', 'value': 'confluence'},
                                {'label': ' Agent', 'value': 'summary'},
                                {'label': ' Skill', 'value': 'agent'},
                            ],
                            value=default_mode,
                            labelStyle={'display': 'inline-block', 'marginRight': '8px', 'fontSize': '12px'}
                        ),
                        html.Span(
                            "纯=不读本地 | RAG=Dify Chatflow | Confluence=知识空间检索 | Agent=数据库直读 | Skill=工具链",
                            style={'fontSize': '10px', 'color': '#9ca3af', 'marginLeft': '4px'}
                        )
                    ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '4px'}),
                    html.Div([
                        dcc.Checklist(
                            id=f'{chat_id_prefix}-known-issues',
                            options=[{'label': ' 已知问题', 'value': 'known'}],
                            value=[],
                            style={'display': 'inline-block', 'fontSize': '12px'}
                        ),
                        html.Span(
                            "检测重复提票",
                            style={'fontSize': '10px', 'color': '#9ca3af', 'marginLeft': '4px'}
                        )
                    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '4px'}),
                    html.Div([
                        html.Span("Model", style={'fontSize': '11px', 'color': '#6b7280', 'fontWeight': '600'}),
                        dcc.Dropdown(
                            id=f'{chat_id_prefix}-model-select',
                            options=[{'label': m, 'value': m} for m in chat_model_options],
                            value=default_chat_model,
                            clearable=False,
                            searchable=False,
                            style={'width': '180px', 'fontSize': '12px'}
                        )
                    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'marginLeft': 'auto'})
                ], className='chat-controls'),

                # 多模态上传区域（图片/语音）
                create_multimodal_upload_component(chat_id_prefix=chat_id_prefix),

                # 输入行
                html.Div([
                    dcc.Input(
                        id=f'{chat_id_prefix}-input',
                        type='text',
                        placeholder='请输入您的问题...',
                        className='chat-input-field',
                        value='',
                        persistence=False
                    ),
                    html.Button(
                        html.I(className="fas fa-paper-plane"),
                        id=f'{chat_id_prefix}-send-button',
                        n_clicks=0,
                        className='chat-send-btn'
                    ),
                    html.Button(
                        html.I(className="fas fa-stop"),
                        id=f'{chat_id_prefix}-stop-button',
                        n_clicks=0,
                        disabled=True,
                        className='chat-stop-btn'
                    )
                ], className='chat-input-row'),
            ], className='chat-input-area'),

            # 隐藏的控制面板（保留所有 ID，callback 依赖它们）
            html.Div([
                # 预设问题按钮（隐藏但保留 ID）
                html.Div(preset_buttons, style={'display': 'none'}),

                # 控制面板
                html.Div([
                    html.Div([
                        html.Label([
                            dcc.Checklist(
                                id=f'{chat_id_prefix}-show-reasoning',
                                options=[{'label': ' 显示执行细节', 'value': 'show'}],
                                value=['show'],
                                style={'fontSize': '12px'}
                            )
                        ])
                    ], style={'flex': '1'}),

                    html.Div([
                        html.Button(
                            [html.I(className="fas fa-trash", style={'marginRight': '5px'}), '清空'],
                            id=f'{chat_id_prefix}-clear-button',
                            n_clicks=0,
                            style={
                                'padding': '4px 10px',
                            'backgroundColor': '#dc3545',
                            'color': 'white',
                            'border': 'none',
                            'borderRadius': '4px',
                            'cursor': 'pointer',
                            'fontSize': '11px'
                        }
                    )
                ], style={'textAlign': 'right'})
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'marginTop': '6px',
                    'padding': '6px 8px',
                    'backgroundColor': '#f8f9fa',
                    'borderRadius': '4px'
                })
            ], style={'display': 'none'})  # 隐藏控制面板区
        ], className='chat-root')

        return interface

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

    def create_enhanced_chat_stores(self, chat_id_prefix: str = 'chat') -> List[dcc.Store]:
        """创建增强版聊天存储组件"""
        initial_conversation_state = self._create_initial_conversation_state()

        stores = [
            dcc.Store(id=f'{chat_id_prefix}-messages', data=[], storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-use-agent-state', data={'use_agent': self.use_agent}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-agent-results', data={}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-known-issue-state', data={'enabled': False}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-streaming-state', data={'active': False, 'task_id': None}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-conversation-state', data=initial_conversation_state, storage_type='session'),
            dcc.Interval(
                id=f'{chat_id_prefix}-update-interval',
                interval=max(100, int(os.getenv("CHAT_UI_POLL_INTERVAL_MS", "250") or 250)),
                n_intervals=0,
                disabled=True
            )
        ]

        return stores

    def register_enhanced_callbacks(self, app: dash.Dash, chat_id_prefix: str = 'chat',
                                   data_store_id: str = 'filtered-data',
                                   data_processor_func: Optional[Callable] = None):
        """
        注册增强版聊天回调函数

        新增功能：
        - Agent 模式切换
        - 工具调用结果展示
        - 数据可视化嵌入
        """
        try:
            max_store_messages = int(os.getenv("CHAT_UI_MAX_MESSAGES", "200"))
        except Exception:
            max_store_messages = 200
        try:
            max_render_messages = int(os.getenv("CHAT_UI_RENDER_MESSAGES", "60"))
        except Exception:
            max_render_messages = 60

        def _trim_chat_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            if not messages:
                return []
            if max_store_messages <= 0:
                return []
            if len(messages) <= max_store_messages:
                return messages
            return messages[-max_store_messages:]

        def _timeline_status_meta(status: str) -> Dict[str, str]:
            mapping = {
                'running': {'label': '进行中', 'bg': '#eef4ff', 'fg': '#1d4ed8', 'border': '#bfdbfe'},
                'ok': {'label': '完成', 'bg': '#e8f7ee', 'fg': '#0f7a42', 'border': '#b7e1c2'},
                'warn': {'label': '注意', 'bg': '#fff7e6', 'fg': '#b7791f', 'border': '#f6d58a'},
                'error': {'label': '失败', 'bg': '#fdeaea', 'fg': '#c0392b', 'border': '#f5b7b1'},
                'fallback': {'label': '回退', 'bg': '#eef2ff', 'fg': '#4338ca', 'border': '#c7d2fe'},
                'info': {'label': '事件', 'bg': '#f3f4f6', 'fg': '#4b5563', 'border': '#d1d5db'},
            }
            return mapping.get(str(status or 'info').strip().lower(), mapping['info'])

        def _render_timeline_content(event_rows: Any):
            if not isinstance(event_rows, list):
                return html.Div()

            blocks = []
            for event in event_rows:
                if not isinstance(event, dict):
                    continue
                meta = _timeline_status_meta(event.get('status'))
                title = str(event.get('title') or '事件').strip() or '事件'
                elapsed = str(event.get('elapsed_label') or '').strip()
                summary = str(event.get('summary') or '').strip()
                details_text = str(event.get('details_text') or '').strip()
                expanded = bool(event.get('expanded'))

                card_children: List[Any] = [
                    html.Div([
                        html.Div([
                            html.Span(elapsed, style={
                                'fontSize': '11px',
                                'color': '#6b7280',
                                'minWidth': '52px'
                            }),
                            html.Span(title, style={
                                'fontSize': '13px',
                                'fontWeight': '600',
                                'color': '#1f2937'
                            }),
                        ], style={
                            'display': 'flex',
                            'alignItems': 'center',
                            'gap': '8px',
                            'flex': '1'
                        }),
                        html.Span(meta['label'], style={
                            'fontSize': '11px',
                            'fontWeight': '600',
                            'padding': '2px 8px',
                            'borderRadius': '999px',
                            'backgroundColor': meta['bg'],
                            'color': meta['fg'],
                            'border': f"1px solid {meta['border']}"
                        })
                    ], style={
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'space-between',
                        'gap': '10px'
                    })
                ]

                if summary:
                    card_children.append(html.Div(summary, style={
                        'fontSize': '12px',
                        'lineHeight': '1.5',
                        'color': '#4b5563',
                        'marginTop': '6px',
                        'whiteSpace': 'pre-line'
                    }))

                if details_text:
                    card_children.append(
                        html.Details([
                            html.Summary('详情', style={
                                'fontSize': '12px',
                                'color': '#4b5563',
                                'cursor': 'pointer',
                                'marginTop': '8px'
                            }),
                            html.Pre(details_text, style={
                                'whiteSpace': 'pre-wrap',
                                'fontSize': '11px',
                                'lineHeight': '1.45',
                                'color': '#374151',
                                'backgroundColor': '#f9fafb',
                                'border': '1px solid #e5e7eb',
                                'borderRadius': '8px',
                                'padding': '8px',
                                'marginTop': '6px',
                                'marginBottom': '0'
                            })
                        ], open=expanded)
                    )

                blocks.append(
                    html.Div(card_children, style={
                        'padding': '10px 12px',
                        'backgroundColor': 'white',
                        'borderRadius': '10px',
                        'border': f"1px solid {meta['border']}",
                        'boxShadow': '0 1px 2px rgba(15, 23, 42, 0.04)'
                    })
                )

            return html.Div(blocks, style={
                'display': 'flex',
                'flexDirection': 'column',
                'gap': '8px'
            })

        def render_chat_history(chat_messages: List[Dict[str, Any]]):
            chat_history_children = []
            messages = _trim_chat_messages(chat_messages or [])
            visible = messages
            if max_render_messages > 0 and len(visible) > max_render_messages:
                folded = len(visible) - max_render_messages
                chat_history_children.append(
                    html.Div(
                        f"已折叠更早的 {folded} 条对话（为保证性能与上下文预算）。如需完整记录可点击“导出对话”。",
                        style={
                            'padding': '8px 12px',
                            'backgroundColor': '#fff3cd',
                            'borderRadius': '8px',
                            'margin': '8px 0',
                            'border': '1px solid #ffeeba',
                            'color': '#856404',
                            'fontSize': '12px'
                        }
                    )
                )
                visible = visible[-max_render_messages:]
            for msg in visible:
                if msg.get("role") == "user":
                    chat_history_children.append(
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-user", style={'marginRight': '8px', 'color': '#2c3e50'}),
                                html.Span("您", style={'fontWeight': 'bold', 'color': '#2c3e50'})
                            ], style={'marginBottom': '5px'}),
                            html.Div(msg.get("content", ""), style={'paddingLeft': '24px'})
                        ], style={
                            'padding': '12px',
                            'backgroundColor': '#e3f2fd',
                            'borderRadius': '8px',
                            'margin': '8px 0',
                            'border': '1px solid #bbdefb',
                            'marginLeft': '20px'
                        })
                    )
                elif msg.get("role") == "assistant":
                    msg_type = msg.get("type")
                    if msg_type == "duplicate-search-result":
                        chat_history_children.append(
                            render_enhanced_duplicate_result_message(msg, chat_id_prefix=chat_id_prefix)
                        )
                        continue
                    if msg_type == "reasoning":
                        bg_color = "#fef9e7"
                        border_color = "#f4d03f"
                    elif msg_type == "timeline":
                        bg_color = "#f8fafc"
                        border_color = "#dbe7f3"
                    elif msg_type == "error":
                        icon_class = "fas fa-exclamation-triangle"
                        icon_color = "#e74c3c"
                        bg_color = "#fdeaea"
                        border_color = "#f1948a"
                        title = "错误"
                    elif msg.get("agent_used"):
                        icon_class = "fas fa-brain"
                        icon_color = "#00796b"
                        bg_color = "#e0f2f1"
                        border_color = "#00796b"
                        title = self.assistant_name
                    else:
                        icon_class = "fas fa-robot"
                        icon_color = "#3498db"
                        bg_color = "#f8f9fa"
                        border_color = "#e9ecef"
                        title = self.assistant_name

                    content_style = {
                        'paddingLeft': '24px',
                        'whiteSpace': 'pre-line'
                    }
                    if msg_type == "reasoning":
                        content_style.update({
                            'maxHeight': '8.5em',
                            'overflowY': 'auto',
                            'fontSize': '12px',
                            'lineHeight': '1.35em',
                            'paddingLeft': '0'
                        })

                    if msg_type == "reasoning":
                        chat_history_children.append(
                            html.Div([
                                html.Div(msg.get("content", ""), style=content_style)
                            ], style={
                                'padding': '12px',
                                'backgroundColor': bg_color,
                                'borderRadius': '8px',
                                'margin': '8px 0',
                                'border': f'1px solid {border_color}',
                                'marginRight': '20px'
                            })
                        )
                    elif msg_type == "timeline":
                        chat_history_children.append(
                            html.Div([
                                _render_timeline_content(msg.get("content"))
                            ], style={
                                'padding': '0',
                                'backgroundColor': bg_color,
                                'borderRadius': '8px',
                                'margin': '8px 0',
                                'marginRight': '20px'
                            })
                        )
                    else:
                        msg_content = msg.get("content", "")
                        display_content = msg_content
                        feedback_buttons = None
                        # Parse feedback metadata from duplicate search results
                        if "<!--FEEDBACK_META:" in str(msg_content):
                            parts = str(msg_content).split("<!--FEEDBACK_META:")
                            display_content = parts[0].rstrip()
                            try:
                                meta_json = parts[1].split("-->")[0]
                                fb_meta = json.loads(meta_json)
                                fb_query = fb_meta.get("query", "")
                                fb_tickets = fb_meta.get("tickets", [])
                                if fb_tickets:
                                    top_ticket = fb_tickets[0]
                                    msg_idx = len(chat_history_children)
                                    feedback_buttons = html.Div([
                                        html.Span("这个结果有帮助吗？", style={
                                            'fontSize': '12px', 'color': '#6b7280', 'marginRight': '8px'
                                        }),
                                        html.Button("👍 有帮助", id={
                                            'type': f'{chat_id_prefix}-dup-feedback',
                                            'signal': 'positive',
                                            'query': fb_query[:200],
                                            'ticket': top_ticket,
                                            'idx': msg_idx,
                                        }, n_clicks=0, style={
                                            'padding': '3px 10px', 'fontSize': '12px',
                                            'borderRadius': '12px', 'border': '1px solid #d1d5db',
                                            'backgroundColor': '#f0fdf4', 'cursor': 'pointer',
                                            'marginRight': '6px',
                                        }),
                                        html.Button("👎 不相关", id={
                                            'type': f'{chat_id_prefix}-dup-feedback',
                                            'signal': 'negative',
                                            'query': fb_query[:200],
                                            'ticket': top_ticket,
                                            'idx': msg_idx,
                                        }, n_clicks=0, style={
                                            'padding': '3px 10px', 'fontSize': '12px',
                                            'borderRadius': '12px', 'border': '1px solid #d1d5db',
                                            'backgroundColor': '#fef2f2', 'cursor': 'pointer',
                                        }),
                                    ], style={
                                        'marginTop': '8px', 'paddingTop': '8px',
                                        'borderTop': '1px solid #e5e7eb',
                                        'display': 'flex', 'alignItems': 'center',
                                    })
                            except Exception:
                                pass

                        inner_children = [
                            html.Div([
                                html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                html.Span(title, style={'fontWeight': 'bold', 'color': icon_color})
                            ], style={'marginBottom': '5px'}),
                            html.Div(display_content, style=content_style),
                        ]
                        if feedback_buttons is not None:
                            inner_children.append(feedback_buttons)
                        chat_history_children.append(
                            html.Div(inner_children, style={
                                'padding': '12px',
                                'backgroundColor': bg_color,
                                'borderRadius': '8px',
                                'margin': '8px 0',
                                'border': f'1px solid {border_color}',
                                'marginRight': '20px'
                            })
                        )
            return chat_history_children

        def start_agent_streaming(task_id: str, question: str, current_data: Any,
                      conversation_history: List[Dict[str, Any]],
                      conversation_state: Optional[Dict[str, Any]],
                      extra_context: Optional[Dict[str, Any]] = None):
            def worker():
                heartbeat_running = {"on": True}
                reasoning_lines: List[str] = []
                agent_request = self._build_agent_request(
                    question=question,
                    current_data=current_data,
                    conversation_state=conversation_state,
                    extra_context=extra_context,
                )
                page_context = agent_request.get("page_context", {}) if isinstance(agent_request, dict) else {}
                runtime_extra_context = dict(extra_context or {})
                if page_context:
                    runtime_extra_context['page_context'] = page_context

                def _append_timeline_event(kind: str, title: str, status: str = "info",
                                           summary: str = "", details: Optional[Any] = None) -> None:
                    append_stream_event(
                        task_id,
                        kind=kind,
                        title=title,
                        status=status,
                        summary=summary,
                        details=details,
                    )

                def _append_reasoning(line: str) -> None:
                    text = str(line or "").strip()
                    if not text:
                        return
                    reasoning_lines.append(text)
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['reasoning'] = "\n".join(reasoning_lines[-10:])
                        streaming_data[task_id]['last_update'] = time.time()

                def _on_agent_progress(event: Dict[str, Any]) -> None:
                    if not isinstance(event, dict):
                        return
                    event_name = str(event.get("event") or "").strip().lower()
                    if event_name == "context_ready":
                        dataset = event.get("primary_dataset") or "-"
                        intents = event.get("intents") or []
                        intents_text = ", ".join([str(x) for x in intents if x]) if isinstance(intents, list) else ""
                        _append_reasoning(f"上下文: dataset={dataset}; intents={intents_text or '-'}")
                        _append_timeline_event(
                            kind="context_ready",
                            title="上下文准备完成",
                            status="ok",
                            summary=f"dataset={dataset}; intents={intents_text or '-'}",
                            details={
                                "dataset": dataset,
                                "intents": intents if isinstance(intents, list) else intents_text,
                            },
                        )
                    elif event_name == "planned":
                        tools = event.get("tools") or []
                        tools_text = " -> ".join([str(t) for t in tools if t]) if isinstance(tools, list) else ""
                        total = int(event.get("total_steps") or 0)
                        _append_reasoning(f"计划: {tools_text}" if tools_text else f"计划: {total} 步")
                        _append_timeline_event(
                            kind="plan_created",
                            title="执行计划已生成",
                            status="ok",
                            summary=tools_text if tools_text else f"共 {total} 步",
                            details={
                                "tools": tools if isinstance(tools, list) else tools_text,
                                "total_steps": total,
                            },
                        )
                    elif event_name == "tool_start":
                        tool = event.get("tool") or "unknown_tool"
                        step_idx = int(event.get("step_index") or 0)
                        total = int(event.get("total_steps") or 0)
                        _append_reasoning(f"调用工具: {tool} ({step_idx}/{total})")
                        _append_timeline_event(
                            kind="tool_start",
                            title=f"开始工具调用: {tool}",
                            status="running",
                            summary=f"步骤 {step_idx}/{total}" if total else "开始执行",
                            details={
                                "tool": tool,
                                "step_index": step_idx,
                                "total_steps": total,
                            },
                        )
                    elif event_name == "tool_end":
                        tool = event.get("tool") or "unknown_tool"
                        ok = bool(event.get("success"))
                        duration_ms = int(event.get("duration_ms") or 0)
                        err = str(event.get("error") or "").strip()
                        suffix = "ok" if ok else (f"err: {err}" if err else "err")
                        _append_reasoning(f"工具结果: {tool} [{suffix}] {duration_ms}ms")
                        _append_timeline_event(
                            kind="tool_result",
                            title=f"工具返回: {tool}",
                            status="ok" if ok else "error",
                            summary=(f"成功，耗时 {duration_ms}ms" if ok else (err or f"失败，耗时 {duration_ms}ms")),
                            details={
                                "tool": tool,
                                "success": ok,
                                "duration_ms": duration_ms,
                                "error": err,
                            },
                        )
                    elif event_name == "replan":
                        failed_tool = event.get("failed_tool") or "-"
                        tools = event.get("replan_tools") or []
                        tools_text = " -> ".join([str(t) for t in tools if t]) if isinstance(tools, list) else "-"
                        _append_reasoning(f"重规划: {failed_tool} -> {tools_text}")
                        _append_timeline_event(
                            kind="replan",
                            title="执行计划已调整",
                            status="warn",
                            summary=f"{failed_tool} -> {tools_text}",
                            details={
                                "failed_tool": failed_tool,
                                "replan_tools": tools if isinstance(tools, list) else tools_text,
                            },
                        )
                    elif event_name == "synthesize":
                        _append_reasoning("正在汇总结论...")
                        _append_timeline_event(
                            kind="llm_phase",
                            title="正在汇总结论",
                            status="running",
                            summary="模型正在整理最终回答",
                        )

                def heartbeat():
                    while heartbeat_running["on"]:
                        with streaming_lock:
                            if task_id in streaming_data and streaming_data[task_id].get('status') == 'processing':
                                streaming_data[task_id]['last_update'] = time.time()
                        time.sleep(5)

                hb_thread = threading.Thread(target=heartbeat, daemon=True)
                hb_thread.start()
                try:
                    with streaming_lock:
                        streaming_data.setdefault(
                            task_id,
                            self._conversation_orchestrator.initialize_stream_state('智能Agent正在分析数据...'),
                        )
                        streaming_data[task_id]['page_context'] = page_context
                    _append_timeline_event(
                        kind="llm_phase",
                        title="Agent 执行已启动",
                        status="running",
                        summary="准备数据、上下文与工具计划",
                    )
                    _append_reasoning("初始化: 准备数据与上下文")

                    _append_reasoning("处理中: 规划任务与执行工具")

                    result = self.process_with_agent(
                        question,
                        current_data,
                        conversation_history,
                        conversation_state=conversation_state,
                        progress_cb=_on_agent_progress,
                        extra_context=runtime_extra_context,
                        agent_request=agent_request,
                    )
                    if not result.get('success'):
                        raise RuntimeError(result.get('text') or result.get('error') or "智能Agent执行失败")

                    with streaming_lock:
                        if task_id in streaming_data:
                            streaming_data[task_id]['conversation_state'] = result.get('conversation_state')
                            streaming_data[task_id]['result_meta'] = {
                                'agent_used': True,
                                'resolved_question': result.get('resolved_question'),
                                'tools_used': result.get('tools_used', []),
                                'last_agent_context': result.get('context', {}),
                            }

                    ctx = result.get("context") or {}
                    trace = (ctx.get("analysis_trace") or {}) if isinstance(ctx, dict) else {}
                    plan = trace.get("plan") or []
                    execution = trace.get("execution") or []
                    lines: List[str] = []
                    primary = ctx.get("primary_dataset") if isinstance(ctx, dict) else None
                    intents = ctx.get("intents") if isinstance(ctx, dict) else None
                    if primary:
                        lines.append(f"数据集: {primary}")
                    if intents:
                        try:
                            lines.append("意图: " + ", ".join([str(x) for x in intents if x]))
                        except Exception:
                            pass
                    if plan:
                        try:
                            lines.append("计划: " + " → ".join([str(s.get("tool")) for s in plan if s.get("tool")]))
                        except Exception:
                            pass
                    if execution:
                        try:
                            items = []
                            for e in execution:
                                t = e.get("tool")
                                if not t:
                                    continue
                                ok = "ok" if e.get("success") else "err"
                                items.append(f"{t}({ok})")
                            if items:
                                lines.append("执行: " + " → ".join(items[:8]))
                        except Exception:
                            pass
                    if os.getenv("AGENT_MEMORY_DEBUG", "0") == "1":
                        mem = ctx.get("memory_debug") if isinstance(ctx, dict) else None
                        if isinstance(mem, dict):
                            st = mem.get("short_term_size")
                            lt = mem.get("long_term_size")
                            used = mem.get("used") or []
                            lines.append(f"记忆: short={st}, long={lt}, used={len(used)}")
                    reasoning_text = "\n".join([x for x in lines if x]).strip()
                    if reasoning_text:
                        for line in reasoning_text.splitlines():
                            _append_reasoning(line)

                    _append_timeline_event(
                        kind="llm_phase",
                        title="正在组织最终回答",
                        status="running",
                        summary=f"工具数 {len(result.get('tools_used', []) or [])}",
                        details={
                            "tools_used": result.get('tools_used', []),
                            "resolved_question": result.get('resolved_question'),
                        },
                    )

                    formatted = self._format_agent_message(
                        result.get('text', ''),
                        result.get('tools_used', []),
                        result.get('insights', [])
                    )
                    with streaming_lock:
                        streaming_data[task_id]['response'] = formatted
                        streaming_data[task_id]['status'] = 'completed'
                        streaming_data[task_id]['progress'] = '完成'
                        streaming_data[task_id]['last_update'] = time.time()

                except Exception as e:
                    _append_timeline_event(
                        kind="error",
                        title="Agent 执行失败",
                        status="error",
                        summary=str(e),
                        details={
                            "error": str(e),
                            "reasoning_tail": reasoning_lines[-5:],
                        },
                    )
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'error'
                        streaming_data[task_id]['error'] = str(e)
                        streaming_data[task_id]['last_update'] = time.time()
                finally:
                    heartbeat_running["on"] = False

            threading.Thread(target=worker, daemon=True).start()

        def start_llm_streaming(task_id: str, question: str, current_data: Any,
                                conversation_history: List[Dict[str, Any]],
                                chat_mode: str = "summary",
                                selected_model: Optional[str] = None):
            # pure 模式用于直连LLM验证，不做数据库摘要兜底。
            if chat_mode != "pure" and not self._has_data(current_data):
                db_summary = _build_db_profile_summary(question)
                if db_summary:
                    append_stream_event(
                        task_id,
                        kind="fallback",
                        title="切换为数据库概览",
                        status="fallback",
                        summary="当前无已加载数据，返回数据库结构摘要",
                    )
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'completed'
                        streaming_data[task_id]['response'] = db_summary
                        streaming_data[task_id]['progress'] = '完成（数据库摘要）'
                        streaming_data[task_id]['last_update'] = time.time()
                    return

            data_context = "" if chat_mode == "pure" else self._generate_data_context(current_data, question=question)
            if chat_mode == "pure":
                system_prompt = (
                    "你是一个简洁友好的通用助手。"
                    "优先直接回答用户问题；不主动要求提供缺陷/测试数据；"
                    "除非用户明确要求数据分析。"
                )
            else:
                system_prompt = self._get_enhanced_system_prompt(data_context)
            messages = [{"role": "system", "content": system_prompt}]
            for msg in (conversation_history or [])[-10:]:
                if msg.get('role') in ['user', 'assistant']:
                    content = str(msg.get('content', '')).strip()
                    if not content:
                        continue
                    if msg.get('type') in {'stream_response', 'reasoning', 'timeline'}:
                        continue
                    messages.append({"role": msg['role'], "content": content})
            messages.append({"role": "user", "content": question})

            append_stream_event(
                task_id,
                kind="llm_phase",
                title="直接模型回答已启动",
                status="running",
                summary=f"模式 {chat_mode}",
            )

            model_chatbot = _chatbot_for_model(selected_model)
            model_chatbot.start_optimized_streaming_thread(
                messages,
                task_id=task_id,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS
            )

        def start_dify_streaming(task_id: str, question: str, current_data: Any):
            def worker():
                try:
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'processing'
                        streaming_data[task_id]['progress'] = '正在调用 Dify Workflow...'
                        streaming_data[task_id]['last_update'] = time.time()

                    data_context = ""
                    if self._has_data(current_data):
                        data_context = self._generate_data_context(current_data, question=question)

                    use_streaming = (os.environ.get("DIFY_RESPONSE_MODE", "streaming") or "streaming").strip().lower() == "streaming"
                    full_text = ""

                    if use_streaming and self.dify_client and self.dify_client.enabled:
                        for event in self.dify_client.stream_workflow(
                            question=question,
                            context=data_context,
                            user=self.dify_client.build_user(self.dashboard_type)
                        ):
                            if event.get("type") == "chunk":
                                full_text += str(event.get("text") or "")
                                with streaming_lock:
                                    streaming_data.setdefault(task_id, {})
                                    streaming_data[task_id]['status'] = 'processing'
                                    streaming_data[task_id]['response'] = full_text
                                    streaming_data[task_id]['progress'] = 'RAG 正在输出...'
                                    streaming_data[task_id]['last_update'] = time.time()

                    if not full_text.strip():
                        result = self.process_with_dify_workflow(question, data_context)
                        if not result.get('success'):
                            raise RuntimeError(result.get('text') or result.get('error') or 'Dify Workflow 执行失败')
                        full_text = str(result.get('text') or '').strip()
                        _stream_text_response(task_id, full_text, progress_text='RAG 正在输出...')
                        return

                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'completed'
                        streaming_data[task_id]['progress'] = '完成'
                        streaming_data[task_id]['last_update'] = time.time()
                except Exception as e:
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'error'
                        streaming_data[task_id]['error'] = str(e)
                        streaming_data[task_id]['last_update'] = time.time()

            threading.Thread(target=worker, daemon=True).start()

        def start_confluence_streaming(task_id: str, question: str, current_data: Any):
            def worker():
                try:
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'processing'
                        streaming_data[task_id]['progress'] = '正在检索 Confluence 空间...'
                        streaming_data[task_id]['last_update'] = time.time()

                    data_context = ""
                    if self._has_data(current_data):
                        data_context = self._generate_data_context(current_data, question=question)

                    result = self.process_with_confluence(question, data_context=data_context)
                    if not result.get('success'):
                        raise RuntimeError(result.get('text') or result.get('error') or 'Confluence 模式执行失败')

                    full_text = str(result.get('text') or '').strip()
                    if not full_text:
                        full_text = 'Confluence 已返回结果，但没有可展示的文本输出。'

                    _stream_text_response(task_id, full_text, progress_text='Confluence 正在输出...')
                except Exception as e:
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'error'
                        streaming_data[task_id]['error'] = str(e)
                        streaming_data[task_id]['last_update'] = time.time()

            threading.Thread(target=worker, daemon=True).start()

        def _stream_text_response(task_id: str, text: str, progress_text: str = '正在输出结果...'):
            content = str(text or "").strip()
            with streaming_lock:
                streaming_data[task_id]['response'] = content
                streaming_data[task_id]['status'] = 'completed'
                streaming_data[task_id]['progress'] = '完成'
                streaming_data[task_id]['last_update'] = time.time()

        def _safe_chat_completion(task_id: str, messages: List[Dict[str, str]], temperature: float,
                                  max_tokens: int, stage_text: str,
                                  selected_model: Optional[str] = None) -> str:
            """调用LLM时做容错，避免摘要模式因单次请求异常而整体失败。"""
            model_chatbot = _chatbot_for_model(selected_model)
            if not model_chatbot or not hasattr(model_chatbot, 'chat_completion'):
                return ""

            try:
                return str(model_chatbot.chat_completion(messages, temperature=temperature, max_tokens=max_tokens) or "").strip()
            except Exception as e:
                logger.warning(f"摘要模式LLM调用失败({stage_text}): {e}")
                append_stream_event(
                    task_id,
                    kind="fallback",
                    title=f"{stage_text}失败",
                    status="fallback",
                    summary=str(e),
                    details={
                        "stage": stage_text,
                        "error": str(e),
                    },
                )
                with streaming_lock:
                    streaming_data.setdefault(task_id, {})
                    streaming_data[task_id]['status'] = 'processing'
                    streaming_data[task_id]['progress'] = f'{stage_text}失败，正在降级...'
                    streaming_data[task_id]['llm_error'] = f"{stage_text}: {e}"
                    streaming_data[task_id]['last_update'] = time.time()
                return ""

        def _build_local_db_answer(question: str, table_name: str, sql_used: str,
                                   rows: List[Dict[str, Any]], note: str = "") -> str:
            """大模型不可用时的本地回答兜底。"""
            safe_rows = [r for r in (rows or []) if isinstance(r, dict)]
            lines: List[str] = [
                "[结论]",
                "当前为本地降级摘要结果。",
                "",
                "[关键数字]",
                f"- 数据表: {table_name or '-'}",
                f"- SQL: {sql_used or '-'}",
            ]
            if note:
                lines.append(f"说明: {note}")

            if not safe_rows:
                lines.append("结果: 查询无数据。请调整问题或切换 Skill（工具链）模式。")
                return "\n".join(lines)

            lines.append("")
            lines.append(f"命中记录: {len(safe_rows)}")

            aida_col = None
            for c in ['aida_english', 'top_aida', 'aida', 'product_area', 'service', 'module']:
                if any(c in row for row in safe_rows):
                    aida_col = c
                    break

            if aida_col:
                counts: Dict[str, int] = {}
                for row in safe_rows:
                    v = str(row.get(aida_col) or '未标注').strip()
                    if not v:
                        v = '未标注'
                    counts[v] = counts.get(v, 0) + 1
                top_aidas = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
                lines.append("AIDA分布(Top10):")
                for name, cnt in top_aidas:
                    lines.append(f"- {name}: {cnt}")

            key_cols = []
            for c in ['defect_id', 'id', 'name', 'status_phase', 'project', 'tproject', 'ecu', 'severity_group', 'topissue_display']:
                if any(c in row for row in safe_rows):
                    key_cols.append(c)

            lines.append("")
            lines.append("Ticket详情(前20条):")
            for i, row in enumerate(safe_rows[:20], 1):
                parts = []
                for c in key_cols[:8]:
                    v = row.get(c)
                    if v not in (None, ""):
                        parts.append(f"{c}={v}")
                if not parts:
                    parts.append(str(row)[:220])
                lines.append(f"{i}. " + " | ".join(parts))

            lines.append("\n提示: 当前返回为本地降级结果，如需更深分析请切换 Skill（工具链）模式。")
            return "\n".join(lines)

        def _summary_debug_enabled() -> bool:
            return (os.getenv("CHAT_SUMMARY_DEBUG", "1") or "1").strip().lower() not in {"0", "false", "no"}

        def _append_summary_debug_block(text: str, mode: str, stage: str, elapsed_ms: int,
                                        table_name: str, sql_used: str, row_count: int,
                                        failure_category: str = "", execution_path: str = "",
                                        stage_timeline: str = "") -> str:
            if not _summary_debug_enabled():
                return text
            debug_lines = [
                "",
                "[调试]",
                f"- mode: {mode}",
                f"- stage: {stage}",
                f"- elapsed_ms: {elapsed_ms}",
                f"- table: {table_name or '-'}",
                f"- row_count: {int(row_count or 0)}",
                f"- sql: {sql_used or '-'}",
            ]
            if execution_path:
                debug_lines.append(f"- execution_path: {execution_path}")
            if failure_category:
                debug_lines.append(f"- failure_category: {failure_category}")
            if stage_timeline:
                debug_lines.append(f"- stage_timeline: {stage_timeline}")
            return f"{text.rstrip()}\n" + "\n".join(debug_lines)

        def _classify_summary_failure(stage: str, reason: str) -> str:
            rs = str(reason or "").lower()
            st = str(stage or "").lower()
            if "tool_executor" in rs or "tool" in rs:
                return "tool_unavailable"
            if "llm" in rs or "模型" in rs or "chat" in rs:
                return "llm_failure"
            if "schema" in rs or st == "load_schema":
                return "schema_failure"
            if st in {"generate_sql"}:
                return "sql_generation_failure"
            if st in {"run_sql_tool", "run_sql_local_fallback"} or "sql" in rs:
                return "sql_execution_failure"
            if st in {"generate_answer"}:
                return "answer_generation_failure"
            return "unknown"

        def _log_summary_trace(task_id: str, trace: Dict[str, Any], success: bool, error: str = "") -> None:
            try:
                payload = {
                    "event": "summary_trace",
                    "task_id": str(task_id or ""),
                    "success": bool(success),
                    "error": str(error or ""),
                    "trace": trace or {},
                }
                logger.info(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass

        def _format_business_explanation_block(explanation: Dict[str, Any]) -> str:
            if not isinstance(explanation, dict) or not explanation:
                return ""
            lines: List[str] = ["[业务解释]"]
            highlights = explanation.get("highlights") or []
            cautions = explanation.get("cautions") or []
            if isinstance(highlights, list) and highlights:
                lines.append("要点:")
                for h in highlights[:6]:
                    lines.append(f"- {str(h)}")
            if isinstance(cautions, list) and cautions:
                lines.append("提醒:")
                for c in cautions[:4]:
                    lines.append(f"- {str(c)}")
            return "\n".join(lines)

        def _build_structured_summary_text(
            llm_answer: str,
            table_name: str,
            sql_used: str,
            rows: List[Dict[str, Any]],
            explanation: Dict[str, Any],
            mode: str,
            total_count: Optional[int] = None,
            sample_limit: int = 120,
            fallback_reason: str = "",
            evidence_bundle: Optional[Dict[str, Any]] = None,
        ) -> str:
            row_count = len(rows or [])
            conclusion = str(llm_answer or "").strip() or "暂无可用结论。"
            safe_total = int(total_count) if isinstance(total_count, (int, np.integer)) and int(total_count) >= 0 else None
            total_count_display = format_total_count_display(safe_total)
            bundle = evidence_bundle if isinstance(evidence_bundle, dict) else {}
            if not bundle:
                bundle = build_evidence_bundle(
                    sql_used=sql_used,
                    rows=rows,
                    total_count=safe_total,
                    evidence_gap=[],
                )

            conclusion = downgrade_unsupported_claims(conclusion, bundle)

            evidence_gaps = bundle.get("evidence_gap") if isinstance(bundle.get("evidence_gap"), list) else []
            uncertainty_line = build_summary_uncertainty_line(evidence_gaps)

            observed_lines: List[str] = [
                "[Observed Facts]",
                f"- total_count: {total_count_display}",
                f"- sample_count: {row_count}",
                f"- table: {table_name or '-'}",
                f"- sql_used: {sql_used or '-'}",
                f"- sql_mode: {mode or '-'}",
            ]
            key_fields = bundle.get("key_fields") if isinstance(bundle.get("key_fields"), list) else []
            if key_fields:
                observed_lines.append(f"- key_fields: {', '.join([str(f) for f in key_fields[:12]])}")
            rule_ids = bundle.get("rule_ids") if isinstance(bundle.get("rule_ids"), list) else []
            if rule_ids:
                observed_lines.append(f"- rule_ids: {', '.join([str(r) for r in rule_ids[:12]])}")

            interpretation_lines: List[str] = [
                "[Rule-Based Interpretation]",
                f"- {conclusion}",
            ]
            highlights = explanation.get("highlights") if isinstance(explanation, dict) else []
            if isinstance(highlights, list):
                for h in highlights[:6]:
                    interpretation_lines.append(f"- {str(h)}")
            if uncertainty_line:
                interpretation_lines.append(f"- {uncertainty_line}")

            suggestion_lines: List[str] = ["[Suggestions / Inference]"]
            if row_count == 0:
                suggestion_lines.append("- 当前查询命中为0，可尝试放宽时间范围、状态或模块筛选")
            if (safe_total is not None) and (safe_total > row_count) and int(sample_limit) > 0:
                suggestion_lines.append(
                    f"- 为保证响应速度，回答详情按样本返回（上限 {int(sample_limit)} 条），已提供全量命中总数"
                )
            if uncertainty_line:
                suggestion_lines.append("- 证据链不完整，建议补充明细字段或调整筛选口径后再下最终结论")
            if fallback_reason:
                suggestion_lines.append(f"- 本地兜底原因: {fallback_reason}")
            cautions = explanation.get("cautions") if isinstance(explanation, dict) else []
            if isinstance(cautions, list):
                for c in cautions[:4]:
                    suggestion_lines.append(f"- {str(c)}")
            if len(suggestion_lines) == 1:
                suggestion_lines.append("- 当前证据支持基础结论，建议结合业务上下文复核")

            return "\n".join(observed_lines + [""] + interpretation_lines + [""] + suggestion_lines)

        def start_db_summary_streaming(task_id: str, question: str, conversation_history: List[Dict[str, Any]],
                           selected_model: Optional[str] = None):
            """摘要模式：优先走 Agent 统一 SQL 工具链，再按需降级。"""
            def worker():
                target_table = ""
                sql_clean = ""
                out_rows: List[Dict[str, Any]] = []
                total_count: Optional[int] = None
                business_explanation: Dict[str, Any] = {}
                evidence_bundle: Dict[str, Any] = {}
                semantic_adapter: Dict[str, Any] = {}
                semantic_hints: Dict[str, Any] = {}
                query_strategy: Dict[str, Any] = {}
                normalized_question = str(question or "").strip()
                stage = "init"
                summary_sql_mode = "agent"
                summary_row_limit_raw = (os.getenv("CHAT_SUMMARY_ROW_LIMIT", "120") or "120").strip() or "120"
                try:
                    summary_row_limit = int(summary_row_limit_raw)
                except Exception:
                    summary_row_limit = 120
                summary_unlimited = summary_row_limit <= 0
                started_at = time.time()
                tool_executor = getattr(self.intelligent_agent, 'tool_executor', None) if self.intelligent_agent else None
                tool_sql_succeeded = False
                local_fallback_reason = ""
                failure_category = ""
                execution_path: List[str] = []
                stage_events: List[str] = []

                def _append_db_event(kind: str, title: str, status: str = "info",
                                     summary: str = "", details: Optional[Any] = None) -> None:
                    append_stream_event(
                        task_id,
                        kind=kind,
                        title=title,
                        status=status,
                        summary=summary,
                        details=details,
                    )

                def _mark_stage(new_stage: str) -> None:
                    nonlocal stage
                    stage = str(new_stage or "")
                    stage_events.append(f"{stage}@{int((time.time() - started_at) * 1000)}ms")

                try:
                    _append_db_event(
                        kind="llm_phase",
                        title="数据库摘要执行已启动",
                        status="running",
                        summary="准备数据库结构与查询计划",
                    )
                    _mark_stage("open_db")
                    db_path = os.getenv("AGENT_SQLITE_DB_PATH") or default_db_path()
                    if not db_path or not os.path.exists(db_path):
                        raise RuntimeError(f"数据库文件不存在: {db_path}")

                    try:
                        from semantic_catalog.term_adapter import adapt_question_with_semantic_terms, is_semantic_catalog_enabled

                        if is_semantic_catalog_enabled():
                            semantic_adapter = adapt_question_with_semantic_terms(
                                question=question,
                                db_path=db_path,
                                table_name="",
                                prefer_db=True,
                            )
                            semantic_hints = dict(semantic_adapter.get("semantic_hints") or {})
                            normalized_question = str(semantic_adapter.get("normalized_question") or question).strip() or str(question or "")

                            mapped_dims = semantic_adapter.get("mapped_dimensions") or []
                            matched_rules = semantic_adapter.get("matched_rule_ids") or []
                            if semantic_hints or mapped_dims or matched_rules:
                                _append_db_event(
                                    kind="context_ready",
                                    title="语义术语映射已应用",
                                    status="ok",
                                    summary=(
                                        f"dimensions={len(mapped_dims)}; rules={len(matched_rules)}"
                                    ),
                                    details={
                                        "normalized_question": normalized_question,
                                        "semantic_hints": semantic_hints,
                                        "mapped_dimensions": mapped_dims[:10],
                                        "matched_rule_ids": matched_rules[:12],
                                    },
                                )
                    except Exception as sem_err:
                        logger.debug(f"语义术语映射失败，继续使用原始问题: {sem_err}")

                    scope_team_info = resolve_summary_scope_team(semantic_hints)
                    scope_team = str(scope_team_info.get("scope_team") or "").strip()
                    if scope_team:
                        semantic_hints["scope_team"] = scope_team
                        _append_db_event(
                            kind="context_ready",
                            title="团队作用域已应用",
                            status="ok",
                            summary=f"scope_team={scope_team}",
                            details={
                                "scope_team": scope_team,
                                "source": str(scope_team_info.get("source") or ""),
                            },
                        )

                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'processing'
                        streaming_data[task_id]['progress'] = '正在读取数据库结构...'
                        streaming_data[task_id]['last_update'] = time.time()

                    _mark_stage("load_schema")
                    raw_target_table = guess_target_table(question)
                    normalized_target_table = guess_target_table(normalized_question)
                    target_table = normalized_target_table or raw_target_table or "octane_defects"
                    if raw_target_table == "octane_manual_runs":
                        target_table = "octane_manual_runs"
                    all_tables: List[str] = []
                    schema_columns: List[str] = []
                    col_preview: List[str] = []

                    if tool_executor:
                        execution_path.append("schema:tool")
                        try:
                            schema_out = tool_executor.execute_tool("get_sqlite_schema", None, table=target_table)
                            schema_result = schema_out.get("result") if isinstance(schema_out, dict) and schema_out.get("success") is True else {}
                            table_map = (schema_result or {}).get("tables") or {}
                            all_tables = [str(t) for t in table_map.keys()]
                            if target_table in table_map and isinstance(table_map.get(target_table), list):
                                schema_views = build_summary_schema_column_views(
                                    [str((c or {}).get("name") or "") for c in table_map.get(target_table) if isinstance(c, dict)],
                                    preview_limit=30,
                                )
                                schema_columns = list(schema_views.get("full") or [])
                                col_preview = list(schema_views.get("preview") or [])
                        except Exception:
                            all_tables = []
                            schema_columns = []
                            col_preview = []
                            local_fallback_reason = "schema工具失败"

                    if not all_tables or not schema_columns:
                        execution_path.append("schema:local")
                        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        try:
                            cur.execute("PRAGMA query_only = ON")
                        except Exception:
                            pass

                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                        all_tables = []
                        for r in (cur.fetchall() or []):
                            if r is None:
                                continue
                            try:
                                all_tables.append(str(r[0]))
                            except Exception:
                                continue
                        if not all_tables:
                            conn.close()
                            raise RuntimeError("数据库无可用业务表")
                        if target_table not in all_tables:
                            if raw_target_table == "octane_manual_runs" or normalized_target_table == "octane_manual_runs":
                                conn.close()
                                raise RuntimeError("数据库缺少 octane_manual_runs 表，无法回答测试用例执行问题")
                            target_table = all_tables[0]

                        cur.execute(f'PRAGMA table_info("{target_table}")')
                        schema_rows = cur.fetchall() or []
                        columns = []
                        for r in schema_rows:
                            if r is None:
                                continue
                            try:
                                columns.append(str(r[1]))
                            except Exception:
                                continue
                        schema_views = build_summary_schema_column_views(columns, preview_limit=30)
                        schema_columns = list(schema_views.get("full") or [])
                        col_preview = list(schema_views.get("preview") or [])
                        conn.close()

                    _append_db_event(
                        kind="context_ready",
                        title="数据库上下文已加载",
                        status="ok",
                        summary=f"目标表 {target_table}; 预览列 {len(col_preview)} 个",
                        details={
                            "table": target_table,
                            "columns": col_preview,
                            "tables": all_tables[:10],
                        },
                    )

                    query_strategy = decide_summary_query_execution_strategy(
                        question=normalized_question,
                        columns=schema_columns,
                        semantic_hints=semantic_hints,
                    )
                    configured_mode = str(os.getenv("CHAT_SUMMARY_SQL_MODE") or "").strip().lower()
                    query_strategy = apply_summary_query_strategy_override(
                        query_strategy=query_strategy,
                        configured_mode=configured_mode,
                    )
                    strategy_name = str(query_strategy.get("strategy") or "constrained_fallback").strip().lower()
                    strategy_confidence = float(query_strategy.get("confidence") or 0.0)
                    forced_by_env = str(query_strategy.get("forced_by_env") or "").strip()

                    execution_path.append(f"strategy:{strategy_name}")
                    _append_db_event(
                        kind="route_decision",
                        title="摘要查询策略已确定",
                        status="ok",
                        summary=(
                            f"strategy={strategy_name}; confidence={strategy_confidence:.2f}"
                            + (f"; forced_by_env={forced_by_env}" if forced_by_env else "")
                        ),
                        details=query_strategy,
                    )

                    with streaming_lock:
                        if strategy_name == "deterministic_first":
                            streaming_data[task_id]['progress'] = '正在生成数据库查询(Deterministic优先)...'
                        else:
                            streaming_data[task_id]['progress'] = '正在生成数据库查询(受限回退策略)...'
                        streaming_data[task_id]['last_update'] = time.time()

                    _mark_stage("generate_sql")
                    sql = ""
                    rows: List[Any] = []

                    use_agent_sql = (os.getenv("CHAT_SUMMARY_SQL_USE_AGENT", "1") or "1").strip().lower() not in {"0", "false", "no"}
                    if strategy_name == "deterministic_first":
                        execution_path.append("sql_generate:deterministic")
                        summary_sql_mode = "deterministic"
                        sql = build_deterministic_sql(
                            question=normalized_question,
                            table_name=target_table,
                            columns=schema_columns,
                            semantic_hints=semantic_hints,
                            row_limit=summary_row_limit,
                        )
                    elif use_agent_sql:
                        execution_path.append("sql_generate:tool")
                        with streaming_lock:
                            streaming_data[task_id]['progress'] = '正在通过Agent工具链生成SQL...'
                            streaming_data[task_id]['last_update'] = time.time()

                        agent_query_out = execute_query_with_fix(
                            question=normalized_question,
                            table_name=target_table,
                            row_limit=summary_row_limit,
                            tool_executor=tool_executor,
                            semantic_hints=semantic_hints,
                        )
                        if bool(agent_query_out.get("success")):
                            sql = str(agent_query_out.get("sql") or "").strip()
                            if not summary_unlimited:
                                out_rows = list(agent_query_out.get("rows") or [])
                            exp = agent_query_out.get("business_explanation")
                            if isinstance(exp, dict):
                                business_explanation = exp
                            tool_sql_succeeded = True
                            summary_sql_mode = "agent"
                        else:
                            local_fallback_reason = str(agent_query_out.get("error") or "query_sqlite_with_fix失败")
                            failure_category = _classify_summary_failure(stage, local_fallback_reason)
                            _append_db_event(
                                kind="fallback",
                                title="Agent SQL 生成失败",
                                status="fallback",
                                summary=local_fallback_reason,
                                details={
                                    "table": target_table,
                                    "mode": "agent",
                                    "strategy": strategy_name,
                                },
                            )

                    if not out_rows and not sql:
                        execution_path.append("sql_generate:deterministic")
                        summary_sql_mode = "deterministic"
                        sql = build_deterministic_sql(
                            question=normalized_question,
                            table_name=target_table,
                            columns=schema_columns,
                            semantic_hints=semantic_hints,
                            row_limit=summary_row_limit,
                        )

                    sql_clean = sanitize_select_sql(sql_text=sql, table_name=target_table, default_limit=50)

                    with streaming_lock:
                        streaming_data[task_id]['progress'] = '正在执行数据库查询...'
                        streaming_data[task_id]['last_update'] = time.time()

                    if not out_rows:
                        _mark_stage("run_sql_tool")
                        if summary_unlimited:
                            local_fallback_reason = "CHAT_SUMMARY_ROW_LIMIT<=0，启用无上限本地查询"
                        elif tool_executor:
                            execution_path.append("sql_run:tool")
                            try:
                                tool_run = tool_executor.execute_tool("run_sqlite_query", None, sql=sql_clean, limit=summary_row_limit)
                                if isinstance(tool_run, dict) and tool_run.get("success") is True:
                                    rs = tool_run.get("result") or {}
                                    sql_clean = str(rs.get("sql") or sql_clean)
                                    items = rs.get("rows") or []
                                    if isinstance(items, list):
                                        out_rows = [r for r in items[:summary_row_limit] if isinstance(r, dict)]
                                    tool_sql_succeeded = True
                                else:
                                    local_fallback_reason = str((tool_run or {}).get("error") or "run_sqlite_query失败")
                                    failure_category = _classify_summary_failure(stage, local_fallback_reason)
                            except Exception:
                                local_fallback_reason = "run_sqlite_query异常"
                                failure_category = _classify_summary_failure(stage, local_fallback_reason)
                                pass
                        else:
                            local_fallback_reason = "tool_executor不可用"
                            failure_category = _classify_summary_failure(stage, local_fallback_reason)

                    if (not out_rows) and (not tool_sql_succeeded):
                        _mark_stage("run_sql_local_fallback")
                        execution_path.append("sql_run:local_fallback")
                        _append_db_event(
                            kind="fallback",
                            title="切换本地 SQL 执行",
                            status="fallback",
                            summary=local_fallback_reason or "工具执行不可用，改走本地只读查询",
                            details={
                                "table": target_table,
                                "sql": sql_clean,
                            },
                        )
                        local_out = execute_sql_rows(
                            sql_text=sql_clean,
                            db_path=db_path,
                            table_name=target_table,
                            row_limit=summary_row_limit,
                            tool_executor=None,
                        )
                        if bool(local_out.get("success")):
                            out_rows = list(local_out.get("rows") or [])
                            sql_clean = str(local_out.get("sql") or sql_clean)
                        else:
                            local_fallback_reason = str(
                                local_out.get("error")
                                or local_fallback_reason
                                or "本地SQL兜底失败"
                            )
                            if not failure_category:
                                failure_category = _classify_summary_failure(stage, local_fallback_reason)

                    # 分析类问题若因噪声实体词导致零结果，先放宽实体词重试；仍为空则切换聚合模板再试一次。
                    if (not out_rows) and summary_sql_mode == "deterministic":
                        retry_hints = extract_query_hints(normalized_question, schema_columns, semantic_hints=semantic_hints)
                        analysis_like_intent = bool(
                            retry_hints.get("wants_analysis")
                            or retry_hints.get("wants_aida_dist")
                            or retry_hints.get("wants_matrix_severity")
                        )
                        if analysis_like_intent and (retry_hints.get("entity_tokens") or []):
                            _mark_stage("retry_broad_query")
                            execution_path.append("sql_retry:deterministic_broad")
                            _append_db_event(
                                kind="fallback",
                                title="零结果后放宽过滤重试",
                                status="fallback",
                                summary="已移除实体词过滤，重新执行查询",
                                details={
                                    "entity_tokens": retry_hints.get("entity_tokens") or [],
                                    "table": target_table,
                                },
                            )
                            with streaming_lock:
                                streaming_data[task_id]['progress'] = '结果为空，正在放宽筛选重试...'
                                streaming_data[task_id]['last_update'] = time.time()

                            broad_sql = build_deterministic_sql(
                                question=normalized_question,
                                table_name=target_table,
                                columns=schema_columns,
                                entity_tokens_override=[],
                                semantic_hints=semantic_hints,
                                row_limit=summary_row_limit,
                            )
                            broad_sql_clean = broad_sql.strip().rstrip(';')
                            if not broad_sql_clean or not re.match(r"^\s*(select|with)\b", broad_sql_clean, flags=re.IGNORECASE):
                                broad_sql_clean = f'SELECT * FROM "{target_table}" LIMIT 50'
                            if re.search(r"\b(insert|update|delete|drop|alter|truncate|attach|detach|pragma\s+write)\b", broad_sql_clean, flags=re.IGNORECASE):
                                broad_sql_clean = f'SELECT * FROM "{target_table}" LIMIT 50'

                            retry_outcome = execute_sql_rows(
                                sql_text=broad_sql_clean,
                                db_path=db_path,
                                table_name=target_table,
                                row_limit=summary_row_limit,
                                tool_executor=tool_executor,
                            )
                            retry_rows: List[Dict[str, Any]] = list(retry_outcome.get("rows") or [])
                            broad_sql_clean = str(retry_outcome.get("sql") or broad_sql_clean)

                            # 放宽实体词后仍为空：再尝试一次通用聚合模板，避免分析问题直接返回无数据。
                            if (not retry_rows) and analysis_like_intent:
                                overview_sql = ""
                                if target_table == "octane_defects":
                                    if "severity_group" in schema_columns:
                                        overview_sql = (
                                            f'SELECT COALESCE(NULLIF(TRIM(CAST(severity_group AS TEXT)), ""), "未标注") AS severity, '
                                            "COUNT(*) AS defect_count "
                                            f'FROM "{target_table}" '
                                            "GROUP BY 1 ORDER BY defect_count DESC LIMIT 20"
                                        )
                                    elif "severity" in schema_columns:
                                        overview_sql = (
                                            f'SELECT COALESCE(NULLIF(TRIM(CAST(severity AS TEXT)), ""), "未标注") AS severity, '
                                            "COUNT(*) AS defect_count "
                                            f'FROM "{target_table}" '
                                            "GROUP BY 1 ORDER BY defect_count DESC LIMIT 20"
                                        )
                                    elif "status_phase" in schema_columns:
                                        overview_sql = (
                                            f'SELECT COALESCE(NULLIF(TRIM(CAST(status_phase AS TEXT)), ""), "未标注") AS status, '
                                            "COUNT(*) AS defect_count "
                                            f'FROM "{target_table}" '
                                            "GROUP BY 1 ORDER BY defect_count DESC LIMIT 20"
                                        )
                                elif target_table == "octane_manual_runs":
                                    status_col = "run_status" if "run_status" in schema_columns else ("status" if "status" in schema_columns else "")
                                    if status_col:
                                        overview_sql = (
                                            f'SELECT COALESCE(NULLIF(TRIM(CAST({status_col} AS TEXT)), ""), "未标注") AS run_status, '
                                            "COUNT(*) AS run_count "
                                            f'FROM "{target_table}" '
                                            "GROUP BY 1 ORDER BY run_count DESC LIMIT 20"
                                        )

                                if overview_sql:
                                    execution_path.append("sql_retry:deterministic_overview")
                                    _append_db_event(
                                        kind="fallback",
                                        title="切换聚合模板重试",
                                        status="fallback",
                                        summary="零结果后改用聚合 SQL 模板",
                                        details={
                                            "table": target_table,
                                            "sql": overview_sql,
                                        },
                                    )
                                    with streaming_lock:
                                        streaming_data[task_id]['progress'] = '结果仍为空，正在切换聚合模板重试...'
                                        streaming_data[task_id]['last_update'] = time.time()

                                    overview_outcome = execute_sql_rows(
                                        sql_text=overview_sql,
                                        db_path=db_path,
                                        table_name=target_table,
                                        row_limit=summary_row_limit,
                                        tool_executor=tool_executor,
                                    )
                                    retry_rows = list(overview_outcome.get("rows") or [])
                                    overview_sql = str(overview_outcome.get("sql") or overview_sql)

                                    if retry_rows:
                                        broad_sql_clean = overview_sql

                            if retry_rows:
                                out_rows = retry_rows
                                sql_clean = broad_sql_clean
                                local_fallback_reason = (
                                    f"{local_fallback_reason}; 零结果后自动放宽实体词过滤重试成功"
                                    if local_fallback_reason else "零结果后自动放宽实体词过滤重试成功"
                                )

                    if (not out_rows) and strategy_name == "deterministic_first" and use_agent_sql:
                        _mark_stage("fallback_agent_sql")
                        execution_path.append("sql_fallback:agent_tool")
                        _append_db_event(
                            kind="fallback",
                            title="Deterministic 结果不足，切换 Agent SQL",
                            status="fallback",
                            summary="结构化查询未命中有效样本，尝试受限回退",
                            details={
                                "table": target_table,
                                "strategy": strategy_name,
                                "mode": summary_sql_mode,
                            },
                        )

                        agent_fallback_out = execute_query_with_fix(
                            question=normalized_question,
                            table_name=target_table,
                            row_limit=summary_row_limit,
                            tool_executor=tool_executor,
                            semantic_hints=semantic_hints,
                        )
                        if bool(agent_fallback_out.get("success")):
                            if not summary_unlimited:
                                out_rows = list(agent_fallback_out.get("rows") or [])
                            sql_clean = str(agent_fallback_out.get("sql") or sql_clean)
                            exp = agent_fallback_out.get("business_explanation")
                            if isinstance(exp, dict):
                                business_explanation = exp
                            summary_sql_mode = "agent"
                            tool_sql_succeeded = True
                        else:
                            fallback_error = str(agent_fallback_out.get("error") or "query_sqlite_with_fix失败")
                            local_fallback_reason = (
                                f"{local_fallback_reason}; {fallback_error}" if local_fallback_reason else fallback_error
                            )
                            if not failure_category:
                                failure_category = _classify_summary_failure(stage, local_fallback_reason)

                    _append_db_event(
                        kind="sql_generated",
                        title="SQL 已生成",
                        status="ok" if sql_clean else "warn",
                        summary=f"模式 {summary_sql_mode}; 表 {target_table}",
                        details={
                            "sql": sql_clean,
                            "mode": summary_sql_mode,
                            "table": target_table,
                        },
                    )

                    total_count = compute_total_count(
                        db_path=db_path,
                        table_name=target_table,
                        sql_text=sql_clean,
                        tool_executor=tool_executor,
                    )

                    _append_db_event(
                        kind="sql_result",
                        title="SQL 查询完成",
                        status="ok" if out_rows else "warn",
                        summary=(
                            f"返回 {len(out_rows)} 行样本，总量 {total_count}"
                            if total_count is not None else f"返回 {len(out_rows)} 行样本"
                        ),
                        details={
                            "row_count": len(out_rows),
                            "total_count": total_count,
                            "table": target_table,
                            "failure_category": failure_category,
                            "execution_path": execution_path,
                            "query_strategy": query_strategy,
                        },
                    )

                    evidence_gaps = infer_summary_evidence_gaps(question, sql_clean, out_rows, target_table)
                    matched_rule_ids = semantic_adapter.get("matched_rule_ids") if isinstance(semantic_adapter, dict) else []
                    evidence_bundle = build_evidence_bundle(
                        sql_used=sql_clean,
                        rows=out_rows,
                        total_count=total_count,
                        rule_ids=matched_rule_ids if isinstance(matched_rule_ids, list) else [],
                        evidence_gap=evidence_gaps,
                    )
                    if not isinstance(business_explanation, dict):
                        business_explanation = {}
                    business_explanation["evidence_bundle"] = evidence_bundle
                    if evidence_gaps:
                        _append_db_event(
                            kind="evidence_gap",
                            title="证据存在缺口",
                            status="warn",
                            summary=evidence_gaps[0],
                            details=evidence_gaps,
                        )

                    with streaming_lock:
                        streaming_data[task_id]['progress'] = '正在生成回答...'
                        streaming_data[task_id]['last_update'] = time.time()

                    _mark_stage("generate_answer")
                    _append_db_event(
                        kind="llm_phase",
                        title="正在生成回答",
                        status="running",
                        summary=f"基于 {len(out_rows)} 行样本整理回答",
                    )
                    ans_messages = [
                        {"role": "system", "content": "你是数据分析助手。基于SQL结果回答用户，先给结论，再给关键数据点；若样本不足要明确说明。"},
                        {"role": "user", "content": json.dumps({
                            "question": question,
                            "table": target_table,
                            "sql": sql_clean,
                            "total_count": total_count,
                            "sample_count": len(out_rows),
                            "sample_limit": summary_row_limit,
                            "row_count": len(out_rows),
                            "rows": out_rows,
                            "evidence_bundle": evidence_bundle,
                        }, ensure_ascii=False)}
                    ]
                    stage = "generate_answer"
                    answer = _safe_chat_completion(
                        task_id=task_id,
                        messages=ans_messages,
                        temperature=0.2,
                        max_tokens=1200,
                        stage_text='答案生成',
                        selected_model=selected_model,
                    )

                    # 第一次失败时，自动降采样重试，减少上下文负载造成的失败概率。
                    if not answer:
                        _append_db_event(
                            kind="fallback",
                            title="答案生成失败，准备重试",
                            status="fallback",
                            summary="首轮回答失败，缩小样本后重试",
                            details={
                                "sample_count": len(out_rows),
                                "retry_sample_count": min(len(out_rows), 30),
                            },
                        )
                        compact_rows = out_rows[:30]
                        retry_messages = [
                            {"role": "system", "content": "你是数据分析助手。请基于给定样本简洁回答，先结论后要点。"},
                            {"role": "user", "content": json.dumps({
                                "question": question,
                                "table": target_table,
                                "sql": sql_clean,
                                "total_count": total_count,
                                "sample_count": len(compact_rows),
                                "sample_limit": summary_row_limit,
                                "row_count": len(compact_rows),
                                "rows": compact_rows,
                                "evidence_bundle": evidence_bundle,
                                "note": "compact_retry"
                            }, ensure_ascii=False)}
                        ]
                        answer = _safe_chat_completion(
                            task_id=task_id,
                            messages=retry_messages,
                            temperature=0.2,
                            max_tokens=800,
                            stage_text='答案生成重试',
                            selected_model=selected_model,
                        )

                    if not answer:
                        llm_err = ""
                        with streaming_lock:
                            llm_err = str((streaming_data.get(task_id) or {}).get('llm_error') or "").strip()
                        _append_db_event(
                            kind="fallback",
                            title="大模型不可用，切换本地摘要",
                            status="fallback",
                            summary=llm_err or local_fallback_reason or "改用本地降级回答",
                            details={
                                "llm_error": llm_err,
                                "fallback_reason": local_fallback_reason,
                            },
                        )
                        answer = _build_local_db_answer(
                            question=question,
                            table_name=target_table,
                            sql_used=sql_clean,
                            rows=out_rows,
                            note=(
                                f"大模型不可用，已返回本地汇总; {llm_err}" if llm_err
                                else (f"本地兜底原因: {local_fallback_reason}" if local_fallback_reason else '大模型不可用，已返回本地汇总')
                            )
                        )
                        if not failure_category:
                            failure_category = _classify_summary_failure(stage, llm_err or local_fallback_reason)
                    final = _build_structured_summary_text(
                        llm_answer=answer,
                        table_name=target_table,
                        sql_used=sql_clean,
                        rows=out_rows,
                        explanation=business_explanation,
                        mode=summary_sql_mode,
                        total_count=total_count,
                        sample_limit=summary_row_limit,
                        fallback_reason=local_fallback_reason,
                        evidence_bundle=evidence_bundle,
                    )
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    stage_timeline = " > ".join(stage_events)
                    execution_path_text = " > ".join(execution_path)
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        summary_trace = {
                            'mode': summary_sql_mode,
                            'query_strategy': query_strategy,
                            'stage': stage,
                            'execution_path': execution_path,
                            'failure_category': failure_category,
                            'fallback_reason': local_fallback_reason,
                            'stage_timeline': stage_events,
                            'elapsed_ms': elapsed_ms,
                            'row_count': len(out_rows),
                            'table': target_table,
                            'sql': sql_clean,
                            'evidence_bundle': evidence_bundle,
                        }
                        streaming_data[task_id]['summary_trace'] = summary_trace
                    _log_summary_trace(task_id=task_id, trace=summary_trace, success=True)
                    final = _append_summary_debug_block(
                        text=final,
                        mode=summary_sql_mode,
                        stage=stage,
                        elapsed_ms=elapsed_ms,
                        table_name=target_table,
                        sql_used=sql_clean,
                        row_count=len(out_rows),
                        failure_category=failure_category,
                        execution_path=execution_path_text,
                        stage_timeline=stage_timeline,
                    )
                    _stream_text_response(task_id, final)

                except Exception as e:
                    failure_category = _classify_summary_failure(stage, str(e))
                    _append_db_event(
                        kind="error",
                        title="数据库摘要执行失败",
                        status="error",
                        summary=f"stage={stage}",
                        details={
                            "stage": stage,
                            "error": str(e),
                            "table": target_table,
                            "sql": sql_clean,
                        },
                    )
                    fallback_text = _build_local_db_answer(
                        question=question,
                        table_name=target_table,
                        sql_used=sql_clean,
                        rows=out_rows,
                        note=f"阶段={stage}; 异常={e}"
                    )
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    stage_timeline = " > ".join(stage_events)
                    execution_path_text = " > ".join(execution_path)
                    summary_trace = {
                        'mode': summary_sql_mode,
                        'query_strategy': query_strategy,
                        'stage': stage,
                        'execution_path': execution_path,
                        'failure_category': failure_category,
                        'fallback_reason': local_fallback_reason,
                        'stage_timeline': stage_events,
                        'elapsed_ms': elapsed_ms,
                        'row_count': len(out_rows),
                        'table': target_table,
                        'sql': sql_clean,
                    }
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['summary_trace'] = summary_trace
                    _log_summary_trace(task_id=task_id, trace=summary_trace, success=False, error=str(e))
                    fallback_text = _append_summary_debug_block(
                        text=fallback_text,
                        mode=summary_sql_mode,
                        stage=stage,
                        elapsed_ms=elapsed_ms,
                        table_name=target_table,
                        sql_used=sql_clean,
                        row_count=len(out_rows),
                        failure_category=failure_category,
                        execution_path=execution_path_text,
                        stage_timeline=stage_timeline,
                    )
                    if fallback_text.strip():
                        _stream_text_response(task_id, fallback_text, progress_text='摘要模式降级输出中...')
                    else:
                        with streaming_lock:
                            streaming_data.setdefault(task_id, {})
                            streaming_data[task_id]['status'] = 'error'
                            streaming_data[task_id]['error'] = f"数据库直读模式失败(stage={stage}): {e}"
                            streaming_data[task_id]['last_update'] = time.time()

            threading.Thread(target=worker, daemon=True).start()

        def _format_db_profile_lines(result: Dict[str, Any]) -> str:
            tables = (result or {}).get("tables") or {}
            if not tables:
                return "当前数据库可访问，但未读取到可用表结构。"
            lines: List[str] = ["已切换为 Agent 模式（数据库直读 / SQLite）。"]
            for tname, tinfo in list(tables.items())[:3]:
                row_count = int((tinfo or {}).get("row_count") or 0)
                lines.append(f"- 表 {tname}: {row_count} 行")
                cols = (tinfo or {}).get("columns") or []
                for c in cols[:8]:
                    cname = c.get("name")
                    if not cname:
                        continue
                    top_vals = c.get("top_values") or []
                    if top_vals:
                        preview = ", ".join([f"{str(v.get('value'))}:{int(v.get('count') or 0)}" for v in top_vals[:3]])
                        lines.append(f"  - {cname}: {preview}")
            lines.append("提示：如需更深入分析，请切换到 Skill（工具链）模式。")
            return "\n".join(lines)

        def _build_db_profile_summary(question_text: str) -> str:
            try:
                if not self.intelligent_agent or not getattr(self.intelligent_agent, "tool_executor", None):
                    return ""
                tool_executor = self.intelligent_agent.tool_executor
                tool_names = set((tool_executor.tools or {}).keys()) if hasattr(tool_executor, "tools") else set()
                if "get_db_profile" not in tool_names:
                    return ""

                table_name = guess_target_table(question_text)
                out = tool_executor.execute_tool("get_db_profile", None, table=table_name, top_n=5, sample_columns=12)
                if not isinstance(out, dict) or out.get("success") is not True:
                    # 指定表失败时回退全库概览
                    out = tool_executor.execute_tool("get_db_profile", None, top_n=5, sample_columns=8)
                if not isinstance(out, dict) or out.get("success") is not True:
                    return ""
                return _format_db_profile_lines(out.get("result") or {})
            except Exception as e:
                logger.warning(f"数据库摘要生成失败: {e}")
                return ""

        def _chatbot_for_model(selected_model: Optional[str]):
            model_name = str(selected_model or "").strip()
            if not model_name:
                return self.chatbot
            try:
                internal_endpoint = self._get_internal_endpoint_for_model(model_name)
                if internal_endpoint:
                    return DeepSeekStreamingChat(model=model_name, internal_template_url=internal_endpoint)
                return DeepSeekStreamingChat(model=model_name)
            except Exception as e:
                logger.warning(f"按模型创建聊天实例失败({model_name})，回退默认实例: {e}")
                return self.chatbot

        def start_duplicate_check_streaming(task_id: str, question: str, current_data: Any,
                            conversation_history: List[Dict[str, Any]],
                            selected_model: Optional[str] = None,
                            multimodal_images: Optional[List[bytes]] = None,
                            multimodal_audio: Optional[bytes] = None):
            df: pd.DataFrame = pd.DataFrame()
            if isinstance(current_data, pd.DataFrame) and not current_data.empty:
                df = current_data
            elif isinstance(current_data, dict):
                defects_df = current_data.get("defects")
                if isinstance(defects_df, pd.DataFrame) and not defects_df.empty:
                    df = defects_df
            else:
                try:
                    from data_processor import load_defect_data
                    loaded = load_defect_data()
                    df = loaded if isinstance(loaded, pd.DataFrame) else pd.DataFrame()
                except Exception as e:
                    logger.warning(f"加载缺陷数据失败: {e}")
                    df = pd.DataFrame()

            # 多模态处理：如果有图片/语音，先用多模态搜索器
            _mm_searcher = None
            _mm_result = None
            has_multimodal = bool(multimodal_images) or bool(multimodal_audio)
            if has_multimodal:
                try:
                    _mm_searcher = MultimodalDuplicateSearcher()
                    _mm_result = _mm_searcher.search(
                        text=question if question.strip() else None,
                        images=multimodal_images,
                        audio=multimodal_audio,
                        df=df if not df.empty else None,
                        cache_key=f"duplicate:{self.dashboard_type}",
                    )
                    logger.info(f"多模态搜索结果: {_mm_result.get('summary', {})}")
                except Exception as _mm_err:
                    logger.warning(f"多模态搜索失败，降级到纯文字: {_mm_err}")
                    has_multimodal = False

            effective_query = build_duplicate_followup_query(question, conversation_history)
            followup_rounds = count_duplicate_followup_rounds(question, conversation_history)

            # ── 多模态批量结果直接返回 ──
            if has_multimodal and _mm_result and _mm_result.get('success'):
                _mm_summary = _mm_result.get('summary', {})
                _mm_results = _mm_result.get('results', [])
                lines: List[str] = []
                lines.append("📷 多模态分析结果")
                lines.append("")
                lines.append(f"从输入中提取了 {_mm_summary.get('total', 0)} 个 ticket：")
                lines.append(f"- 疑似重复：{_mm_summary.get('duplicates', 0)} 个")
                lines.append(f"- 可能是新问题：{_mm_summary.get('new_issues', 0)} 个")
                lines.append("")
                if _mm_summary.get('transcribed_text'):
                    lines.append("🎤 语音转写：" + str(_mm_summary.get("transcribed_text", "")))
                    lines.append("")
                for _ri, _r in enumerate(_mm_results, 1):
                    _is_dup = _r.get('is_likely_duplicate', False)
                    _tag = '🔄 疑似重复' if _is_dup else '✅ 可能是新问题'
                    _q = str(_r.get("query", "?"))[:80]
                    lines.append(f"--- Ticket {_ri}：{_q} ---")
                    _ts = _r.get("top_score", 0)
                    lines.append(f"状态：{_tag}（最高相似度 {_ts:.1f}/10）")
                    _cands = _r.get('candidates', [])[:3]
                    if _cands:
                        lines.append("最相似的已知问题：")
                        for _c in _cands:
                            _tid = f'#{_c.get("ticket_id")}' if _c.get("ticket_id") else '#(未知)'
                            _sc = _c.get("score_1_10", 0)
                            _nm = _c.get("name", "")
                            lines.append(f'  {_sc}分：{_tid} - {_nm}')
                    lines.append("")
                _formatted = "\n".join(lines)
                chunk_size = 80
                for end in range(0, len(_formatted), chunk_size):
                    partial = _formatted[: end + chunk_size]
                    with streaming_lock:
                        if task_id in streaming_data:
                            streaming_data[task_id]['status'] = 'processing'
                            streaming_data[task_id]['response'] = partial
                            streaming_data[task_id]['progress'] = 'SiSi正在生成多模态分析报告...'
                            streaming_data[task_id]['last_update'] = time.time()
                    time.sleep(0.02)
                with streaming_lock:
                    if task_id in streaming_data:
                        streaming_data[task_id]['status'] = 'completed'
                        streaming_data[task_id]['progress'] = '完成'
                        streaming_data[task_id]['last_update'] = time.time()
                return

            hints = extract_hints(effective_query)
            index = get_or_build_index(cache_key=f"duplicate:{self.dashboard_type}", df=df)
            try:
                from progressive_reranker import get_progressive_reranker
                _reranker = get_progressive_reranker()
            except Exception:
                _reranker = None
            candidates, _dup_metadata = index.search_with_metadata(
                effective_query, hints=hints, top_k=10, reranker=_reranker,
            )
            _dup_feedback_store = FeedbackStore()
            _dup_model_phase = _dup_metadata.get('model_phase', 'baseline')
            _dup_feedback_count = _dup_metadata.get('feedback_count', 0)
            duplicate_payload = _build_enhanced_duplicate_result_payload(
                query_text=effective_query,
                dashboard_type=self.dashboard_type,
                candidates=candidates,
            )
            # Track search session for training-data mining
            _search_session_id = None
            try:
                from search_session_tracker import get_session_tracker
                _session_tracker = get_session_tracker()
                _search_session_id = _session_tracker.begin_session(
                    query_text=effective_query,
                    candidates=candidates,
                    user_id=_get_current_user_id(),
                    model_phase=_dup_model_phase,
                )
            except Exception as _e:
                logger.debug(f"Session tracking skipped: {_e}")
            with streaming_lock:
                if task_id in streaming_data:
                    streaming_data[task_id]['is_duplicate_search'] = True
                    streaming_data[task_id]['duplicate_payload'] = duplicate_payload
                    if _search_session_id:
                        streaming_data[task_id]['search_session_id'] = _search_session_id

            model_chatbot = _chatbot_for_model(selected_model)
            local_only = not getattr(model_chatbot, "client", None) and not getattr(model_chatbot, "backup_api_key", "")
            force_conclusion = followup_rounds >= 2
            if local_only:
                best = max((c.score_1_10 for c in candidates), default=0)
                if best >= 8:
                    suggestion = "不建议提票"
                    reason = "与已有问题高度相似，建议优先合并/追加信息"
                elif best <= 6:
                    suggestion = "可以提票"
                    reason = "未发现高度相似的已知问题"
                elif force_conclusion:
                    if best >= 7:
                        suggestion = "不建议提票"
                        reason = "经过多轮补充，与已有问题较为相似，建议优先合并/追加信息"
                    else:
                        suggestion = "可以提票"
                        reason = "经过多轮补充，仍未找到高度匹配的已知问题"
                else:
                    suggestion = "需要补充信息后再判断"
                    reason = "相似度中等，建议补充复现信息再决定是否新开票"

                lines: List[str] = []
                lines.append("【结论】")
                lines.append(f"- 建议：{suggestion}")
                lines.append(f"- 依据：{reason}")
                lines.append("")
                lines.append("【相似已知问题（按相似度降序）】")
                if not candidates:
                    lines.append("- (未检索到候选；可能当前筛选数据为空或已排除关闭态)")
                else:
                    for c in candidates[:10]:
                        tid = f"#{c.ticket_id}" if c.ticket_id else "#(未知ID)"
                        meta = " / ".join([x for x in [c.project, c.pu] if x])
                        phase = c.status_phase or "-"
                        title = c.name or "(无标题)"
                        lines.append(f"- {c.score_1_10}分：{tid} - {title}（{meta or '-'}，{phase}）")
                        if c.snippet:
                            lines.append(f"  匹配点：{c.snippet}")
                lines.append("")
                lines.append("【下一步】")
                if suggestion == "不建议提票" and candidates:
                    best_c = candidates[0]
                    tid = f"#{best_c.ticket_id}" if best_c.ticket_id else "该相似票"
                    lines.append(f"- 建议合并到 {tid}：在原票补充你的复现步骤、期望/实际、环境、日志/截图。")
                else:
                    lines.append("- 如果仍要提票：建议补充复现步骤、期望/实际、环境信息、日志/截图，并标注 project/PU。")
                lines.append("")
                lines.append("（提示：当前未配置可用的 LLM 密钥，因此以上为本地检索结果生成的建议。）")
                if _dup_feedback_count > 0:
                    phase_label = {'click_boost': '统计增强', 'feature': '特征学习'}.get(_dup_model_phase, '基线')
                    lines.append(f"\n🧠 模型阶段：{phase_label}（基于 {_dup_feedback_count} 条团队反馈）")

                formatted = "\n".join(lines).strip()
                chunk_size = 80
                for end in range(0, len(formatted), chunk_size):
                    partial = formatted[: end + chunk_size]
                    with streaming_lock:
                        streaming_data[task_id]['status'] = 'processing'
                        streaming_data[task_id]['response'] = partial
                        streaming_data[task_id]['progress'] = 'SiSi正在回答...'
                        streaming_data[task_id]['last_update'] = time.time()
                    time.sleep(0.02)
                with streaming_lock:
                    streaming_data[task_id]['status'] = 'completed'
                    streaming_data[task_id]['progress'] = '完成'
                    streaming_data[task_id]['last_update'] = time.time()
                return

            candidate_lines: List[str] = []
            for c in candidates:
                candidate_lines.append(
                    json.dumps(
                        {
                            "score_1_10": c.score_1_10,
                            "ticket_id": c.ticket_id,
                            "name": c.name,
                            "project": c.project,
                            "pu": c.pu,
                            "status_phase": c.status_phase,
                            "snippet": c.snippet,
                        },
                        ensure_ascii=False,
                    )
                )

            candidate_block = "\n".join(candidate_lines) if candidate_lines else "(无候选)"

            system_prompt = f"""你是缺陷提票前置审查助手。你的任务是：根据用户的自然语言问题描述，在“候选缺陷列表”中找出最相似的已知问题，并给出是否建议提票的结论。\n\n规则：\n1) 只能基于提供的候选列表，不要编造不存在的ticket。\n2) 相似度评分使用 1-10（10=几乎同一个问题）。你可以参考候选里给定的 score_1_10，但如果你认为不合理可以小幅调整；最终输出仍需按 10→1 排序。\n3) 如果最高相似度 >= 8：结论默认“不建议提票”，建议合并到最相似票或补充复现信息后追踪。\n4) 如果最高相似度 <= 6：结论默认“可以提票”，并给出建议标题与必填信息清单。\n\n输出格式（必须使用以下结构）：\n【结论】\n- 建议：不建议提票 / 可以提票 / 需要补充信息后再判断\n- 依据：一句话说明\n\n【相似已知问题（按相似度降序）】\n- 10分：#id - 标题（project/pu，phase）\\n  匹配点：...\\n  差异点：...（P1-4：说明与用户问题的不同之处）\n- 9分：...\n\n【下一步】\n- 如果不建议提票：建议合并到哪一票，以及需要补充哪些信息。\n- 如果可以提票：建议标题、复现步骤、期望/实际、环境、日志/截图等。\n\n候选缺陷列表（JSON Lines）：\n{candidate_block}\n"""

            messages = [{"role": "system", "content": system_prompt}]

            if force_conclusion:
                system_prompt += (
                    "\n\n【重要】用户已经补充了多轮信息，请基于当前已有的全部信息给出确定性结论"
                    "（「可以提票」或「不建议提票」），不要再输出「需要补充信息后再判断」。"
                    "如果相似度处于 7 分左右的中间地带，倾向于给出明确建议而非继续追问。"
                )
                messages = [{"role": "system", "content": system_prompt}]

            for msg in (conversation_history or [])[-6:]:
                if msg.get('role') in ['user', 'assistant']:
                    content = str(msg.get('content', '')).strip()
                    if not content:
                        continue
                    if msg.get('type') in {'stream_response', 'reasoning', 'timeline'}:
                        continue
                    messages.append({"role": msg['role'], "content": content})
            messages.append({"role": "user", "content": question})

            model_chatbot.start_optimized_streaming_thread(
                messages,
                task_id=task_id,
                temperature=0.2,
                max_tokens=DEFAULT_MAX_TOKENS
            )

        # 注册多模态回调（图片上传 + 录音）
        try:
            register_multimodal_callbacks(app, chat_id_prefix=chat_id_prefix)
        except Exception as _mm_cb_err:
            logger.debug(f"多模态回调注册跳过: {_mm_cb_err}")

        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children'),
             Output(f'{chat_id_prefix}-input', 'value'),
             Output(f'{chat_id_prefix}-messages', 'data'),
             Output(f'{chat_id_prefix}-streaming-state', 'data'),
             Output(f'{chat_id_prefix}-update-interval', 'disabled'),
             Output(f'{chat_id_prefix}-status', 'children'),
             Output(f'{chat_id_prefix}-agent-results', 'data'),
             Output(f'{chat_id_prefix}-conversation-state', 'data'),
             Output(f'{chat_id_prefix}-stop-button', 'disabled')],
            [Input(f'{chat_id_prefix}-send-button', 'n_clicks'),
             Input(f'{chat_id_prefix}-input', 'n_submit'),
             Input(f'{chat_id_prefix}-clear-button', 'n_clicks')] +
            [Input(f'{chat_id_prefix}-{key}-btn', 'n_clicks')
             for key in self.preset_questions.get(self.dashboard_type, self.preset_questions['general']).keys()],
            [State(f'{chat_id_prefix}-input', 'value'),
             State(f'{chat_id_prefix}-messages', 'data'),
             State(f'{chat_id_prefix}-streaming-state', 'data'),
             State(data_store_id, 'data'),
             State(f'{chat_id_prefix}-chat-mode', 'value'),
             State(f'{chat_id_prefix}-known-issues', 'value'),
             State(f'{chat_id_prefix}-agent-results', 'data'),
             State(f'{chat_id_prefix}-conversation-state', 'data'),
             State(f'{chat_id_prefix}-model-select', 'value'),
             State(f'{chat_id_prefix}-image-store', 'data'),
             State(f'{chat_id_prefix}-audio-store', 'data')]
        )
        def handle_enhanced_chat(*args):
            send_clicks = args[0]
            input_submit = args[1]
            clear_clicks = args[2]
            preset_clicks = args[3:-9]
            input_value = args[-11]
            chat_messages = _trim_chat_messages(args[-10] or [])
            streaming_state = args[-9] or {'active': False, 'task_id': None}
            filtered_data = args[-8]
            chat_mode = (args[-7] or "summary")
            known_issues_checked = args[-6] or []
            prior_agent_results = dict(args[-5] or {})
            conversation_state = args[-4] or self._create_initial_conversation_state()
            selected_model = str(args[-3] or "").strip() or self._get_default_chat_model()
            multimodal_images_store = args[-2] or []
            multimodal_audio_store = args[-1]

            ctx = callback_context
            if not ctx.triggered:
                raise PreventUpdate

            trigger = ctx.triggered[0]
            prop_id = trigger['prop_id']

            # 处理清空
            if prop_id == f'{chat_id_prefix}-clear-button.n_clicks' and clear_clicks:
                initial_message = html.Div([
                    html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span("对话已清空。您可以重新开始提问。")
                ], style={
                    'padding': '12px',
                    'backgroundColor': '#f8f9fa',
                    'borderRadius': '8px',
                    'margin': '8px 0',
                    'border': '1px solid #e9ecef'
                })
                return [initial_message], "", [], {'active': False, 'task_id': None}, True, "", {}, self._create_initial_conversation_state(), True

            if streaming_state.get('active'):
                status_display = html.Div([
                    html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span("上一条消息正在生成中，请稍候…（可点击“清空”重置）", style={'color': '#666'})
                ])
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, status_display, dash.no_update, dash.no_update, dash.no_update

            use_known_issues = 'known' in (known_issues_checked or [])

            # 确定用户消息
            user_message = ""
            normalized_message = ""
            normalized_extra_context = {}
            preset_questions = self.preset_questions.get(self.dashboard_type, self.preset_questions['general'])
            trigger_key = ''

            if prop_id.startswith(f'{chat_id_prefix}-') and prop_id.endswith('-btn.n_clicks'):
                trigger_key = prop_id[len(f'{chat_id_prefix}-'):-len('-btn.n_clicks')]

            if prop_id in [f'{chat_id_prefix}-send-button.n_clicks', f'{chat_id_prefix}-input.n_submit']:
                if input_value and input_value.strip():
                    user_message = input_value.strip()
            else:
                for key, question in preset_questions.items():
                    if prop_id == f'{chat_id_prefix}-{key}-btn.n_clicks':
                        user_message = question
                        if 'agent' in key:
                            chat_mode = "agent"
                        break

            if user_message:
                normalized_entry = self._normalize_proactive_insight_entry(
                    question=user_message,
                    trigger_key=trigger_key,
                    extra_context={},
                )
                normalized_message = normalized_entry['question']
                normalized_extra_context = normalized_entry['extra_context']
                if normalized_extra_context.get('mode') == 'proactive_insight':
                    chat_mode = 'agent'

            # 处理用户消息
            agent_results = {}
            status_display = ""
            route_decision = None
            route_trace = {}

            if user_message:
                # 问候语快速路径：避免被分析型提示词放大为长篇数据说明。
                msg_norm = str(normalized_message or user_message or "").strip().lower()
                greeting_set = {"hi", "hello", "hey", "你好", "嗨", "哈喽", "在吗", "在么", "hi!", "hello!"}
                if msg_norm in greeting_set and len(msg_norm) <= 12:
                    chat_messages.append({"role": "user", "content": user_message})
                    chat_messages.append({
                        "role": "assistant",
                        "content": "你好，我在。你可以直接问我问题，或告诉我你想分析的范围。"
                    })
                    chat_messages = _trim_chat_messages(chat_messages)
                    chat_history_children = render_chat_history(chat_messages)
                    return chat_history_children, "", chat_messages, {'active': False, 'task_id': None}, True, "", {}, conversation_state, True

                # 添加用户消息
                chat_messages.append({"role": "user", "content": user_message})
                chat_messages = _trim_chat_messages(chat_messages)

                force_skill_agent = should_resume_pending_agent_confirmation(user_message, prior_agent_results)

                route_request = HarnessRouteRequest(
                    question=normalized_message,
                    selected_mode=chat_mode,
                    known_issues_enabled=use_known_issues,
                    use_agent=self.use_agent,
                    dashboard_type=self.dashboard_type,
                    force_skill_agent=force_skill_agent,
                )

                current_data: Any = pd.DataFrame()
                if filtered_data and should_load_local_data(route_request):
                    try:
                        if data_processor_func:
                            try:
                                current_data = data_processor_func(filtered_data, user_message)
                            except TypeError:
                                current_data = data_processor_func(filtered_data)
                        else:
                            json_data = filtered_data.get('data', filtered_data) if isinstance(filtered_data, dict) else filtered_data
                            current_data = pd.read_json(io.StringIO(json_data), orient='split')
                    except Exception as e:
                        logger.error(f"数据解析失败: {e}")

                route_decision = resolve_harness_route(route_request, has_data=self._has_data(current_data))
                route_trace = route_decision.to_trace()
                agent_results = {'route': route_trace}
            else:
                raise PreventUpdate

                
            try:
                cleanup_stale_streaming_data(max_age_seconds=int(os.getenv("CHAT_STREAMING_STALE_SECONDS", "300")))
            except Exception:
                pass

            # Limit streaming_data size to prevent memory issues
            with streaming_lock:
                if len(streaming_data) > 50:
                    # Remove oldest entries
                    sorted_tasks = sorted(
                        streaming_data.items(),
                        key=lambda x: x[1].get('last_update', 0)
                    )
                    for task_id, _ in sorted_tasks[:len(streaming_data) - 50]:
                        del streaming_data[task_id]
                    logger.warning(f"Streaming data size exceeded limit, cleaned up old entries")

            task_id = f"{chat_id_prefix}_{int(time.time() * 1000)}"
            route_reasoning = self._build_route_reasoning(route_trace)
            with streaming_lock:
                streaming_data[task_id] = {
                    'status': 'processing',
                    'reasoning': '',
                    'route_reasoning': route_reasoning,
                    'route_trace': route_trace,
                    'response': '',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'started_at': time.time(),
                    'selected_model': selected_model,
                    'progress': f"{route_trace.get('handler_label', 'AI')} 正在初始化...",
                    'chunk_buffer': '',
                    'events': [],
                    'last_update': time.time()
                }
                append_stream_event_to_store(
                    streaming_data[task_id],
                    kind='route_decision',
                    title='路由决策完成',
                    status='ok',
                    summary=(
                        f"{route_trace.get('requested_mode_label', route_trace.get('requested_mode', '-'))} -> "
                        f"{route_trace.get('handler_label', route_trace.get('handler', '-'))}"
                    ),
                    details=route_trace,
                )

            chat_messages.append({
                "role": "assistant",
                "content": "AI正在思考...",
                "type": "reasoning",
                "task_id": task_id,
                "agent_used": False
            })
            chat_messages.append({
                "role": "assistant",
                "content": "",
                "type": "stream_response",
                "task_id": task_id,
                "agent_used": bool(route_decision and route_decision.agent_used)
            })
            chat_messages = _trim_chat_messages(chat_messages)

            status_display = html.Div([
                html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                html.Span("AI正在思考...", style={'color': '#666'})
            ])

            if route_decision.handler == HarnessRouteHandler.KNOWN_ISSUE:
                with streaming_lock:
                    if task_id in streaming_data:
                        streaming_data[task_id]['progress'] = 'SiSi正在检索已知问题...'
                start_duplicate_check_streaming(task_id, user_message, current_data, chat_messages,
                                                 selected_model=selected_model,
                                                 multimodal_images=extract_image_bytes_from_store(multimodal_images_store),
                                                 multimodal_audio=extract_audio_bytes_from_store(multimodal_audio_store))
            elif route_decision.handler == HarnessRouteHandler.DIFY_WORKFLOW:
                start_dify_streaming(task_id, user_message, current_data)
            elif route_decision.handler == HarnessRouteHandler.CONFLUENCE:
                start_confluence_streaming(task_id, user_message, current_data)
            elif route_decision.handler == HarnessRouteHandler.DATABASE_SUMMARY:
                start_db_summary_streaming(task_id, user_message, chat_messages, selected_model=selected_model)
            elif route_decision.handler == HarnessRouteHandler.SKILL_AGENT:
                start_agent_streaming(
                    task_id,
                    normalized_message,
                    current_data,
                    chat_messages,
                    conversation_state,
                    normalized_extra_context,
                )
            else:
                start_llm_streaming(
                    task_id,
                    user_message,
                    current_data,
                    chat_messages,
                    chat_mode=route_decision.llm_mode,
                    selected_model=selected_model,
                )

            streaming_state = {'active': True, 'task_id': task_id}

            chat_history_children = render_chat_history(chat_messages)
            interval_disabled = not streaming_state.get('active')
            return chat_history_children, "", chat_messages, streaming_state, interval_disabled, status_display, agent_results, conversation_state, False

        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-messages', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-streaming-state', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-update-interval', 'disabled', allow_duplicate=True),
             Output(f'{chat_id_prefix}-status', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-agent-results', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-conversation-state', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-stop-button', 'disabled', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-update-interval', 'n_intervals')],
            [State(f'{chat_id_prefix}-messages', 'data'),
             State(f'{chat_id_prefix}-streaming-state', 'data'),
             State(f'{chat_id_prefix}-show-reasoning', 'value'),
             State(f'{chat_id_prefix}-agent-results', 'data'),
             State(f'{chat_id_prefix}-conversation-state', 'data')],
            prevent_initial_call=True
        )
        def update_streaming_response(n_intervals, chat_messages, streaming_state, show_reasoning, agent_results, conversation_state):
            if not streaming_state or not streaming_state.get('active'):
                raise PreventUpdate

            task_id = streaming_state.get('task_id')
            if not task_id:
                raise PreventUpdate

            with streaming_lock:
                stream_data = dict(streaming_data.get(task_id) or {})

            if not stream_data:
                chat_messages = _trim_chat_messages(chat_messages or [])
                response_index = -1
                for i in range(len(chat_messages) - 1, -1, -1):
                    if chat_messages[i].get('type') == 'stream_response' and chat_messages[i].get('task_id') == task_id:
                        response_index = i
                        break
                if response_index != -1:
                    chat_messages[response_index]["type"] = "error"
                    chat_messages[response_index]["content"] = "❌ 流式任务已失效（可能刷新页面/后端重启/网络中断）。请重新发送。"
                streaming_state = {'active': False, 'task_id': None}
                chat_history_children = render_chat_history(chat_messages)
                interval_disabled = True
                status_display = ""
                return chat_history_children, chat_messages, streaming_state, interval_disabled, status_display, agent_results, conversation_state, True

            max_stale_seconds = 300
            try:
                max_stale_seconds = int(os.getenv("CHAT_STREAMING_STALE_SECONDS", "300"))
            except Exception:
                max_stale_seconds = 300

            chat_messages = _trim_chat_messages(chat_messages or [])
            current_task_id = task_id
            current_ts = time.time()

            reasoning_content = build_stream_reasoning_content(stream_data, now_ts=current_ts)
            status = stream_data.get('status')

            show_details = bool(show_reasoning and 'show' in (show_reasoning or []))
            chat_messages = [
                msg for msg in chat_messages
                if not (
                    msg.get('task_id') == current_task_id
                    and msg.get('type') in {'reasoning', 'timeline'}
                )
            ]

            response_index = -1
            for i in range(len(chat_messages) - 1, -1, -1):
                if chat_messages[i].get('type') == 'stream_response' and chat_messages[i].get('task_id') == current_task_id:
                    response_index = i
                    break

            if show_details:
                if reasoning_content:
                    reasoning_message = {
                        "role": "assistant",
                        "type": "reasoning",
                        "task_id": current_task_id,
                        "agent_used": False,
                        "content": reasoning_content
                    }
                    if response_index != -1:
                        chat_messages.insert(response_index, reasoning_message)
                        response_index += 1
                    else:
                        chat_messages.append(reasoning_message)
                chat_messages = _trim_chat_messages(chat_messages)
                if response_index == -1:
                    for i in range(len(chat_messages) - 1, -1, -1):
                        if chat_messages[i].get('type') == 'stream_response' and chat_messages[i].get('task_id') == current_task_id:
                            response_index = i
                            break

            response_content = stream_data.get('response') or ''
            if response_index != -1 and (response_content or status == 'completed'):
                chat_messages[response_index]["content"] = response_content
            chat_messages = _trim_chat_messages(chat_messages)

            updated_agent_results = dict(agent_results or {})
            route_trace = stream_data.get('route_trace')
            if isinstance(route_trace, dict) and route_trace:
                updated_agent_results['route'] = route_trace

            result_meta = stream_data.get('result_meta')
            if isinstance(result_meta, dict) and result_meta:
                updated_agent_results.update(result_meta)

            updated_conversation_state = conversation_state or self._create_initial_conversation_state()
            streamed_conversation_state = stream_data.get('conversation_state')
            if isinstance(streamed_conversation_state, dict) and streamed_conversation_state:
                updated_conversation_state = streamed_conversation_state

            last_update = float(stream_data.get('last_update') or 0)
            if status == 'processing' and last_update > 0 and max_stale_seconds > 0:
                if (time.time() - last_update) > max_stale_seconds:
                    status = 'error'
                    stream_data['error'] = f"流式任务超过 {max_stale_seconds}s 未更新，已自动终止（可能网络/接口超时）"
            progress_msg = stream_data.get('progress') or 'AI正在处理...'
            status_display = ""
            if status == 'processing':
                status_display = html.Div([
                    html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span(progress_msg, style={'color': '#666'})
                ])

            if status == 'error':
                error_msg = stream_data.get('error') or '未知错误'
                if response_index != -1:
                    chat_messages[response_index]["type"] = "error"
                    chat_messages[response_index]["content"] = f"❌ {error_msg}"
                streaming_state = {'active': False, 'task_id': None}
                # Clean up streaming data on error
                with streaming_lock:
                    if task_id in streaming_data:
                        del streaming_data[task_id]
                        logger.info(f"Cleaned up streaming data for failed task {task_id}")
                status_display = ""

            if status == 'stopped':
                if response_index != -1:
                    partial = str(stream_data.get('response') or '').strip()
                    chat_messages[response_index]["content"] = (partial + "\n\n⏹ 已手动停止。") if partial else "⏹ 已手动停止。"
                streaming_state = {'active': False, 'task_id': None}
                with streaming_lock:
                    if task_id in streaming_data:
                        del streaming_data[task_id]
                status_display = ""

            if status == 'completed':
                chat_messages = append_duplicate_result_message(chat_messages, stream_data)
                chat_messages = _trim_chat_messages(chat_messages)
                streaming_state = {'active': False, 'task_id': None}
                # Clean up streaming data to prevent memory leak
                with streaming_lock:
                    if task_id in streaming_data:
                        del streaming_data[task_id]
                        logger.info(f"Cleaned up streaming data for task {task_id}")
                status_display = ""

            chat_history_children = render_chat_history(chat_messages)
            interval_disabled = not streaming_state.get('active')
            return chat_history_children, chat_messages, streaming_state, interval_disabled, status_display, updated_agent_results, updated_conversation_state, not streaming_state.get('active')

        @app.callback(
            [Output(f'{chat_id_prefix}-streaming-state', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-update-interval', 'disabled', allow_duplicate=True),
             Output(f'{chat_id_prefix}-status', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-stop-button', 'disabled', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-stop-button', 'n_clicks')],
            [State(f'{chat_id_prefix}-streaming-state', 'data')],
            prevent_initial_call=True
        )
        def handle_stop_button(n_clicks, streaming_state):
            if not n_clicks:
                raise PreventUpdate
            task_id = (streaming_state or {}).get('task_id')
            if task_id:
                with streaming_lock:
                    if task_id in streaming_data:
                        streaming_data[task_id]['status'] = 'stopped'
                        streaming_data[task_id]['last_update'] = time.time()
            return {'active': False, 'task_id': None}, True, "", True

        # --- Duplicate search feedback callback (pattern-matching on button IDs) ---
        from dash import ALL, MATCH
        @app.callback(
            Output(f'{chat_id_prefix}-status', 'children', allow_duplicate=True),
            Input({'type': f'{chat_id_prefix}-dup-feedback', 'signal': ALL, 'query': ALL, 'ticket': ALL, 'idx': ALL}, 'n_clicks'),
            prevent_initial_call=True
        )
        def handle_duplicate_feedback(n_clicks_list):
            if not n_clicks_list or not any(n_clicks_list):
                raise PreventUpdate
            triggered = callback_context.triggered_id
            if not isinstance(triggered, dict):
                raise PreventUpdate
            signal = triggered.get('signal', '')
            query_text = triggered.get('query', '')
            ticket_id = triggered.get('ticket', '')
            if not signal or not query_text or not ticket_id:
                raise PreventUpdate
            try:
                store = FeedbackStore()
                user_id = _get_current_user_id()

                # Map uncertain to 'click' signal — recorded but not used for training
                effective_signal = signal
                source = 'explicit'
                if signal == 'uncertain':
                    effective_signal = 'click'
                    source = 'explicit_uncertain'

                result = store.submit_feedback(
                    query_text=query_text,
                    ticket_id=ticket_id,
                    signal=effective_signal,
                    user_id=user_id,
                    source=source,
                )

                # Also record in search session tracker for mining
                try:
                    from search_session_tracker import get_session_tracker
                    _session_tracker = get_session_tracker()
                    # Find the latest session for this query
                    _latest_sid = _session_tracker._conn().execute(
                        "SELECT session_id FROM search_sessions "
                        "WHERE query_hash=? ORDER BY created_at DESC LIMIT 1",
                        (_session_tracker.query_hash(query_text),)
                    ).fetchone()
                    if _latest_sid:
                        _session_tracker.record_explicit(_latest_sid[0], ticket_id, signal)
                except Exception as _se:
                    logger.debug(f"Session tracking for feedback skipped: {_se}")
                if result.get('accepted'):
                    count = result.get('feedback_count', 0)
                    phase = result.get('model_phase', 'baseline')
                    phase_label = {'click_boost': '统计增强', 'feature': '特征学习'}.get(phase, '基线')
                    if signal == 'uncertain':
                        msg = f"已记录，系统会学习这种边界情况。已收集 {count} 条反馈。"
                    else:
                        msg = f"感谢反馈！已有 {count} 条学习记录（{phase_label}），下次搜索将更精准。"
                    return html.Div([
                        html.I(className="fas fa-check-circle", style={'marginRight': '6px', 'color': '#22c55e'}),
                        html.Span(msg, style={'color': '#22c55e', 'fontSize': '12px'})
                    ])
                return html.Div([
                    html.Span(f"反馈未接受：{result.get('reason', '未知')}", style={'color': '#ef4444', 'fontSize': '12px'})
                ])
            except Exception as exc:
                logger.warning(f"Feedback submission error: {exc}")
                raise PreventUpdate

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
# 工厂函数
# ============================================================================

def create_enhanced_chat_manager(dashboard_type: str = 'defect',
                                use_agent: bool = True,
                                assistant_name: Optional[str] = None) -> EnhancedAIChatManager:
    """创建增强版 AI Chat Manager"""
    return EnhancedAIChatManager(dashboard_type, use_agent, assistant_name=assistant_name)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'EnhancedAIChatManager',
    'create_enhanced_chat_manager'
]


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("增强版 AI Chat Manager 测试")
    print("=" * 50)

    # 测试创建
    manager = create_enhanced_chat_manager('defect', use_agent=True)
    print("Enhanced AI Chat Manager created successfully")
    print(f"   - 看板类型: {manager.dashboard_type}")
    print(f"   - Agent启用: {manager.use_agent}")
    print(f"   - 预设问题数: {len(manager.preset_questions[manager.dashboard_type])}")

    # 测试界面创建
    interface = manager.create_enhanced_chat_interface('test-chat')
    print("Chat interface created successfully")
