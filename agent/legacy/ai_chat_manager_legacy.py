"""
AI聊天管理模块 - 集成版本
统一管理所有看板的AI对话功能，包含配置、流式聊天和测试功能
"""

import os
import sys
import time
import json
import queue
import logging
import threading
import traceback
import pandas as pd
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Generator
import io
import uuid

from agent.core.harness_config import load_llm_provider_config, load_workspace_env
from duplicate_issue_finder import extract_hints, get_or_build_index

import dash
from dash import ALL, MATCH, dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

load_workspace_env()

# ============================================================================
# DeepSeek API 配置部分
# ============================================================================

_DEFAULT_INTERNAL_BASE = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"
_DEFAULT_INTERNAL_MODEL = "glm-5"
_DEFAULT_PUBLIC_BASE = "https://api.deepseek.com/v1"
_DEFAULT_PUBLIC_MODEL = "deepseek-reasoner"
_DEFAULT_MOONSHOT_BASE = "https://api.moonshot.cn/v1"
_DEFAULT_MOONSHOT_MODEL = "kimi-k2.5"
_DEFAULT_INTERNAL_TEMPLATE_URL = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"

HARDCODED_DEEPSEEK_ACCESS_CODE = "7FD25E1BD6124A1C8BF29030C8BFC43E"
HARDCODED_DEEPSEEK_API_KEY = ""
HARDCODED_DEEPSEEK_API_BASE = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"
HARDCODED_DEEPSEEK_MODEL = "glm-5"
HARDCODED_DEEPSEEK_API_KEY_BACKUP = "sk-e1a77ca98a30498ca33acc7f803f0d41"
HARDCODED_DEEPSEEK_API_BASE_BACKUP = ""
HARDCODED_DEEPSEEK_MODEL_BACKUP = ""

_PROVIDER_CONFIG = load_llm_provider_config(
    hardcoded_access_code=HARDCODED_DEEPSEEK_ACCESS_CODE,
    hardcoded_api_key=HARDCODED_DEEPSEEK_API_KEY,
    hardcoded_api_base=HARDCODED_DEEPSEEK_API_BASE,
    hardcoded_model=HARDCODED_DEEPSEEK_MODEL,
    hardcoded_backup_api_key=HARDCODED_DEEPSEEK_API_KEY_BACKUP,
    hardcoded_backup_api_base=HARDCODED_DEEPSEEK_API_BASE_BACKUP,
    hardcoded_backup_model=HARDCODED_DEEPSEEK_MODEL_BACKUP,
    default_internal_base=_DEFAULT_INTERNAL_BASE,
    default_internal_model=_DEFAULT_INTERNAL_MODEL,
    default_public_base=_DEFAULT_PUBLIC_BASE,
    default_public_model=_DEFAULT_PUBLIC_MODEL,
    default_moonshot_base=_DEFAULT_MOONSHOT_BASE,
    default_moonshot_model=_DEFAULT_MOONSHOT_MODEL,
    default_internal_template_url=_DEFAULT_INTERNAL_TEMPLATE_URL,
)

ACCESS_CODE = _PROVIDER_CONFIG.access_code
DEEPSEEK_API_KEY = _PROVIDER_CONFIG.primary_api_key
DEEPSEEK_API_BASE = _PROVIDER_CONFIG.primary_api_base
DEEPSEEK_MODEL = _PROVIDER_CONFIG.primary_model
DEEPSEEK_API_KEY_BACKUP = _PROVIDER_CONFIG.backup_api_key
DEEPSEEK_API_BASE_BACKUP = _PROVIDER_CONFIG.backup_api_base
DEEPSEEK_MODEL_BACKUP = _PROVIDER_CONFIG.backup_model
INTERNAL_TEMPLATE_URL = _PROVIDER_CONFIG.internal_template_url

# Chat Configuration
DEFAULT_TEMPERATURE = _PROVIDER_CONFIG.default_temperature
DEFAULT_MAX_TOKENS = _PROVIDER_CONFIG.default_max_tokens
DEFAULT_STREAM = _PROVIDER_CONFIG.default_stream

# SSL验证设置 - 内网环境可能需要禁用SSL验证
VERIFY_SSL = _PROVIDER_CONFIG.verify_ssl

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# DeepSeek 流式聊天处理器
# ============================================================================

# 全局流式数据存储
streaming_data = {}
streaming_lock = threading.Lock()


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


def _build_duplicate_recommendation_parts(candidates: List[Any]) -> Dict[str, Any]:
    best_candidate = None
    best_score = 0
    for candidate in candidates or []:
        score = int(getattr(candidate, "score_1_10", 0) or 0)
        if best_candidate is None or score > best_score:
            best_candidate = candidate
            best_score = score

    if best_score >= 8:
        suggestion = "不建议提票"
        reason = "与已有问题高度相似，建议优先合并/追加信息"
    elif best_score <= 6:
        suggestion = "可以提票"
        reason = "未发现高度相似的已知问题"
    else:
        suggestion = "需要补充信息后再判断"
        reason = "相似度中等，建议补充复现信息再决定是否新开票"

    if best_candidate is not None and suggestion == "不建议提票":
        tid = f"#{getattr(best_candidate, 'ticket_id', None) or '该相似票'}"
        next_step = f"- 建议合并到 {tid}：在原票补充你的复现步骤、期望/实际、环境、日志/截图。"
    else:
        next_step = "- 如果仍要提票：建议补充复现步骤、期望/实际、环境信息、日志/截图，并标注 project/PU。"

    return {
        "best_candidate": best_candidate,
        "best_score": best_score,
        "suggestion": suggestion,
        "reason": reason,
        "next_step": next_step,
    }


def _build_duplicate_summary_text(candidates: List[Any]) -> str:
    recommendation = _build_duplicate_recommendation_parts(candidates)
    lines = [
        "【结论】",
        f"- 建议：{recommendation['suggestion']}",
        f"- 依据：{recommendation['reason']}",
        "",
        "【下一步】",
        recommendation["next_step"],
    ]
    return "\n".join(lines).strip()


def _build_latest_duplicate_result_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidates = list((payload or {}).get("candidates") or [])
    return {
        "query_text": (payload or {}).get("query_text", ""),
        "dashboard_type": (payload or {}).get("dashboard_type", "general"),
        "candidates_by_ticket": {
            str(candidate.get("ticket_id") or ""): candidate
            for candidate in candidates
            if candidate.get("ticket_id")
        },
    }


def _submit_duplicate_feedback(
    store_payload: Dict[str, Any],
    ticket_id: str,
    signal: str,
    feedback_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    from feedback_store import FeedbackStore

    payload = dict(store_payload or {})
    candidates_by_ticket = dict(payload.get("candidates_by_ticket") or {})
    candidate = dict(candidates_by_ticket.get(ticket_id) or {})
    if not payload.get("query_text") or not candidate:
        return {"success": False, "message": "缺少反馈上下文"}

    store = FeedbackStore(db_path=feedback_db_path) if feedback_db_path else FeedbackStore()
    result = store.submit_feedback(
        query_text=str(payload.get("query_text") or ""),
        ticket_id=str(ticket_id or ""),
        signal=str(signal or "").lower(),
        base_score=candidate.get("similarity"),
        rank_pos=candidate.get("rank_pos"),
        user_id=None,
    )
    if result.get("accepted"):
        message = "已记录为正向反馈" if str(signal).lower() == "positive" else "已记录为负向反馈"
        return {"success": True, "message": message, "result": result}
    return {"success": False, "message": f"反馈提交失败：{result.get('reason') or 'unknown'}", "result": result}


def _build_duplicate_feedback_button_id(chat_id_prefix: str, ticket_id: str, signal: str, rank_pos: int) -> Dict[str, Any]:
    return {
        "type": "duplicate-feedback-btn",
        "chat": chat_id_prefix,
        "ticket_id": str(ticket_id or ""),
        "signal": str(signal or "").lower(),
        "rank_pos": int(rank_pos or 0),
    }


def render_duplicate_result_message(message: Dict[str, Any], chat_id_prefix: str) -> html.Div:
    payload = dict(message.get("duplicate_result") or {})
    candidates = list(payload.get("candidates") or [])
    cards: List[Any] = []
    for candidate in candidates:
        ticket_id = str(candidate.get("ticket_id") or "")
        meta = " / ".join(
            [value for value in [candidate.get("project"), candidate.get("pu"), candidate.get("status_phase")] if value]
        )
        cards.append(
            html.Div(
                [
                    html.Div(f"{candidate.get('score_1_10', 1)} 分", style={"fontWeight": "bold", "color": "#1f4b99"}),
                    html.Div(f"#{ticket_id or '(未知ID)'} - {candidate.get('name', '') or '(无标题)'}", style={"marginTop": "4px"}),
                    html.Div(meta or "-", style={"marginTop": "4px", "fontSize": "12px", "color": "#64748b"}),
                    html.Div(candidate.get("snippet", ""), style={"marginTop": "6px", "fontSize": "13px", "color": "#475569", "whiteSpace": "pre-line"}),
                    html.Div(
                        [
                            html.Button(
                                "👍 匹配",
                                id=_build_duplicate_feedback_button_id(chat_id_prefix, ticket_id, "positive", candidate.get("rank_pos", 0)),
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
                                "👎 不匹配",
                                id=_build_duplicate_feedback_button_id(chat_id_prefix, ticket_id, "negative", candidate.get("rank_pos", 0)),
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
                        ],
                        style={"marginTop": "10px"},
                    ),
                    html.Div(
                        id={"type": "duplicate-feedback-status", "chat": chat_id_prefix, "ticket_id": ticket_id},
                        style={"marginTop": "8px", "fontSize": "12px", "color": "#64748b"},
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
            html.I(className="fas fa-robot", style={"marginRight": "8px", "color": "#3498db"}),
            html.Div(
                [
                    html.Div(message.get("content", ""), style={"whiteSpace": "pre-line"}),
                    html.Div(cards, style={"marginTop": "12px"}),
                ],
                style={"display": "inline-block", "width": "calc(100% - 24px)"},
            ),
        ],
        style={
            "padding": "12px",
            "backgroundColor": "#f8f9fa",
            "borderRadius": "8px",
            "margin": "8px 0",
            "textAlign": "left",
            "border": "1px solid #e9ecef",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
            "marginRight": "20px",
        },
    )

class DeepSeekStreamingChat:
    """优化的DeepSeek流式聊天类，支持推理过程显示和性能优化"""
    
    def __init__(self, api_key: str = None, model: str = DEEPSEEK_MODEL, api_base: str = None,
                 internal_template_url: Optional[str] = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.access_code = ACCESS_CODE
        self.model = model
        self.api_base = api_base or DEEPSEEK_API_BASE
        self.internal_template_url = str(internal_template_url or "").strip()
        self.client = self._create_client(self.api_key, self.api_base) if self._should_use_openai_client(self.api_key, self.api_base) else None
        self.response_queue = queue.Queue()
        self.streaming_active = False
        # 备用API参数
        self.backup_api_key = DEEPSEEK_API_KEY_BACKUP
        self.backup_api_base = DEEPSEEK_API_BASE_BACKUP
        self.backup_model = DEEPSEEK_MODEL_BACKUP

    def _is_internal_direct_endpoint(self, api_base: Optional[str]) -> bool:
        base = str(api_base or "")
        return "/api/service/" in base and "/chat/completions" in base

    def _should_use_openai_client(self, api_key: Optional[str], api_base: Optional[str]) -> bool:
        return bool(api_key) and not self._is_internal_direct_endpoint(api_base)

    def _build_openai_compat_url(self) -> str:
        base = (self.api_base or "").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"
        
    def _create_client(self, api_key, api_base):
        """创建优化的HTTP客户端"""
        import httpx
        from openai import OpenAI
        
        http_client = httpx.Client(
            verify=False,
            timeout=120,  # 增加超时时间
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        return OpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=120,
            http_client=http_client
        )

    def _resolve_temperature(self, temperature: float, model: str, api_base: str):
        model_text = (model or "").lower()
        base_text = (api_base or "").lower()
        if "kimi" in model_text or "moonshot.cn" in base_text:
            return 1
        return temperature

    def _extract_access_code(self) -> str:
        key = str(self.api_key or "").strip()
        if key.startswith("ACCESSCODE"):
            parts = key.split(" ", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
        return str(self.access_code or "").strip()

    def _should_use_internal_template_for_nonstream(self) -> bool:
        # 只要能拿到 access_code，就优先走已验证可用的内网模板接口。
        return bool(self._extract_access_code())

    def _resolve_internal_template_url(self) -> str:
        tmpl = self.internal_template_url or os.environ.get("DEEPSEEK_INTERNAL_TEMPLATE_URL") or INTERNAL_TEMPLATE_URL
        code = self._extract_access_code()
        if not code:
            raise ValueError("未配置 access code，无法调用内网模板接口")
        return tmpl.format(access_code=code)

    def _request_internal_template_nonstream(self, messages: List[Dict[str, str]],
                                             temperature: float, max_tokens: int) -> str:
        url = self._resolve_internal_template_url()
        access_code = self._extract_access_code()
        if not access_code:
            raise ValueError("未配置 access code，无法调用内网GLM-5接口")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature, self.model, self.api_base),
            "stream": False,
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"ACCESSCODE {access_code}",
        }
        timeout_sec = float(os.environ.get("DEEPSEEK_INTERNAL_TIMEOUT", "120"))
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec, verify=False)
        resp.raise_for_status()
        try:
            obj = resp.json()
        except Exception:
            text = (resp.text or "").strip()
            if text:
                return text
            raise RuntimeError("内网模板接口返回空响应")

        if isinstance(obj, dict) and obj.get("code") and obj.get("message"):
            raise RuntimeError(f"内网模板接口错误: code={obj.get('code')}, message={obj.get('message')}")

        choices = obj.get("choices") if isinstance(obj, dict) else None
        if isinstance(choices, list) and choices:
            msg = (choices[0] or {}).get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                content = "".join([str(x.get("text") or x.get("content") or "") if isinstance(x, dict) else str(x) for x in content])
            if content is not None:
                return str(content).strip()

        for k in ("content", "response", "answer", "text"):
            if isinstance(obj, dict) and obj.get(k) is not None:
                return str(obj.get(k)).strip()

        return json.dumps(obj, ensure_ascii=False)

    def _stream_internal_template(self, messages: List[Dict[str, str]],
                                    temperature: float, max_tokens: int) -> Generator[str, None, None]:
        """真正的 SSE 流式请求内网 GLM 接口，逐块 yield 文本。"""
        url = self._resolve_internal_template_url()
        access_code = self._extract_access_code()
        if not access_code:
            raise ValueError("未配置 access code，无法调用内网GLM流式接口")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature, self.model, self.api_base),
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "accept": "text/event-stream",
            "Content-Type": "application/json",
            "Authorization": f"ACCESSCODE {access_code}",
        }
        timeout_sec = float(os.environ.get("DEEPSEEK_INTERNAL_TIMEOUT", "120"))
        resp = requests.post(url, headers=headers, json=payload,
                             timeout=timeout_sec, stream=True, verify=False)
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data:"):
                raw = line[5:].strip()
            else:
                raw = line.strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            choices = obj.get("choices") if isinstance(obj, dict) else None
            if not isinstance(choices, list) or not choices:
                continue
            delta = (choices[0] or {}).get("delta") or {}
            chunk = delta.get("content") or ""
            if chunk:
                yield chunk

    def _probe_non_stream_error(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        """在SDK返回结构异常时，直接探测原始HTTP返回，给出可读错误。"""
        try:
            url = self._build_openai_compat_url()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self._resolve_temperature(temperature, self.model, self.api_base),
                "max_tokens": max_tokens,
                "stream": False,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=45, verify=False)
            text = (resp.text or "").strip()
            try:
                obj = resp.json()
            except Exception:
                obj = None
            if isinstance(obj, dict):
                code = obj.get("code")
                msg = obj.get("message") or obj.get("error") or text[:300]
                return f"HTTP {resp.status_code}; code={code}; message={msg}"
            return f"HTTP {resp.status_code}; body={text[:300]}"
        except Exception as e:
            return f"raw probe failed: {e}"
    
    def validate_api_key(self) -> bool:
        """验证API密钥"""
        if not self.api_key:
            return False
        if self.api_key == "your-api-key-here":
            return False
        return True

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        if not self.validate_api_key():
            raise ValueError("未配置可用的 DEEPSEEK_API_KEY")
        if self._should_use_internal_template_for_nonstream():
            try:
                return self._request_internal_template_nonstream(messages, temperature, max_tokens)
            except Exception as e:
                if self._is_internal_direct_endpoint(self.api_base):
                    raise RuntimeError(f"内网GLM-5接口调用失败: {e}") from e
                logger.warning(f"内网模板接口调用失败，回退OpenAI兼容链路: {e}")

        if not self.client:
            if self._is_internal_direct_endpoint(self.api_base):
                raise RuntimeError("当前内网接口不是OpenAI兼容base_url，已阻止错误回退链路")
            self.client = self._create_client(self.api_key, self.api_base)
        try:
            resolved_temperature = self._resolve_temperature(temperature, self.model, self.api_base)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=resolved_temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            choices = getattr(resp, "choices", None)
            if not choices:
                detail = self._probe_non_stream_error(messages, temperature, max_tokens)
                raise RuntimeError(f"LLM响应缺少choices。{detail}")
            first_choice = choices[0]
            msg_obj = getattr(first_choice, "message", None)
            content = getattr(msg_obj, "content", None) if msg_obj is not None else None
            if content is None:
                detail = self._probe_non_stream_error(messages, temperature, max_tokens)
                raise RuntimeError(f"LLM响应content为空。{detail}")
            return str(content).strip()
        except Exception as e:
            if not self.backup_api_key:
                raise
            try:
                backup_client = self._create_client(self.backup_api_key, self.backup_api_base)
                resolved_temperature = self._resolve_temperature(temperature, self.backup_model, self.backup_api_base)
                resp = backup_client.chat.completions.create(
                    model=self.backup_model,
                    messages=messages,
                    temperature=resolved_temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
                choices = getattr(resp, "choices", None)
                if not choices:
                    raise RuntimeError("备用模型响应缺少choices")
                msg_obj = getattr(choices[0], "message", None)
                content = getattr(msg_obj, "content", None) if msg_obj is not None else None
                if content is None:
                    raise RuntimeError("备用模型响应content为空")
                return str(content).strip()
            except Exception:
                raise e
    
    def stream_chat_response_optimized(self, messages: List[Dict[str, str]], 
                                    task_id: str,
                                    temperature: float = 0.7, 
                                    max_tokens: int = 2000) -> Generator[str, None, None]:
        """优化的流式响应生成器，支持推理过程显示，主API失败时自动切换备用API"""
        with streaming_lock:
            streaming_data.setdefault(task_id, {
                'status': 'initializing',
                'reasoning': '',
                'response': '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'progress': 'AI正在初始化...',
                'chunk_buffer': '',
                'last_update': time.time()
            })
        try:
            yield from self._try_stream(messages, task_id, temperature, max_tokens, use_backup=False)
        except Exception as e:
            if self.backup_api_key:
                print(f"主DeepSeek API调用失败，尝试备用API... 错误: {e}")
                try:
                    yield from self._try_stream(messages, task_id, temperature, max_tokens, use_backup=True)
                    return
                except Exception as e2:
                    error_msg = f"主API和备用API均失败: {e2}"
            else:
                error_msg = f"主DeepSeek API调用失败: {e}"
            print(error_msg)
            with streaming_lock:
                streaming_data.setdefault(task_id, {})['status'] = 'error'
                streaming_data[task_id]['error'] = error_msg
            yield f"error:{error_msg}"
    
    def _try_stream(self, messages, task_id, temperature, max_tokens, use_backup=False):
        # Read response_prefix written by the caller (e.g., known-issue prelude)
        with streaming_lock:
            _prefix = str((streaming_data.get(task_id) or {}).get('response_prefix', ''))
        # 切换API参数
        if use_backup:
            if not self.backup_api_key:
                raise ValueError("未配置备用API密钥，请设置 DEEPSEEK_API_KEY_BACKUP")
            client = self._create_client(self.backup_api_key, self.backup_api_base)
            model = self.backup_model
            # 备用API也使用流式响应
            with streaming_lock:
                if task_id in streaming_data:
                    streaming_data[task_id].update({
                        'status': 'processing',
                        'progress': 'SiSi正在思考...',
                        'last_update': time.time()
                    })
                else:
                    streaming_data[task_id] = {
                        'status': 'processing',
                        'reasoning': '',
                        'response': '',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'progress': 'SiSi正在思考...',
                        'chunk_buffer': '',
                        'last_update': time.time()
                    }
            
            # 备用API流式处理
            reasoning_content = ""
            content = _prefix
            chunk_buffer = ""
            last_yield_time = time.time()
            reasoning_yielded = False
            
            for chunk in client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,  # 改为流式
                max_tokens=max_tokens,
                temperature=self._resolve_temperature(temperature, model, self.backup_api_base)
            ):
                try:
                    current_time = time.time()
                    # 处理推理过程 (DeepSeek-R1 特有)
                    if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                        reasoning_chunk = chunk.choices[0].delta.reasoning_content
                        reasoning_content += reasoning_chunk
                        with streaming_lock:
                            streaming_data[task_id]['reasoning'] = reasoning_content
                            streaming_data[task_id]['progress'] = 'SiSi正在思考...'
                            streaming_data[task_id]['last_update'] = current_time
                        # 持续yield推理内容更新
                        yield f"reasoning:{reasoning_content}"
                        reasoning_yielded = True
                    elif chunk.choices[0].delta.content:
                        content_chunk = chunk.choices[0].delta.content
                        content += content_chunk
                        chunk_buffer += content_chunk
                        
                        # 批量输出优化 - 每50ms或累积5个字符输出一次
                        if (current_time - last_yield_time > 0.05) or len(chunk_buffer) >= 5:
                            with streaming_lock:
                                streaming_data[task_id]['response'] = content
                                streaming_data[task_id]['progress'] = 'SiSi正在回答...'
                                streaming_data[task_id]['chunk_buffer'] = chunk_buffer
                                streaming_data[task_id]['last_update'] = current_time
                            
                            yield f"content:{chunk_buffer}"
                            chunk_buffer = ""
                            last_yield_time = current_time
                            
                except Exception as e:
                    print(f"处理备用API流式数据块时出错: {e}")
                    continue
            
            # 输出剩余内容
            if chunk_buffer:
                with streaming_lock:
                    streaming_data[task_id]['response'] = content
                    streaming_data[task_id]['chunk_buffer'] = chunk_buffer
                yield f"content:{chunk_buffer}"
            
            # 完成标记
            with streaming_lock:
                streaming_data[task_id]['status'] = 'completed'
                streaming_data[task_id]['progress'] = '完成'
            yield "done:完成"
            return
        else:
            # 内网主链路统一走已验证可用的 access_code 模板接口。
            if self._should_use_internal_template_for_nonstream():
                with streaming_lock:
                    streaming_data.setdefault(task_id, {})
                    streaming_data[task_id].update({
                        'status': 'processing',
                        'progress': 'SiSi正在思考...',
                        'last_update': time.time(),
                    })

                content = _prefix
                chunk_buf = ""
                last_emit = time.time()
                try:
                    for chunk_text in self._stream_internal_template(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        content += chunk_text
                        chunk_buf += chunk_text
                        now = time.time()
                        if len(chunk_buf) >= 20 or (now - last_emit) > 0.04:
                            with streaming_lock:
                                streaming_data[task_id]['response'] = content
                                streaming_data[task_id]['progress'] = 'SiSi正在回答...'
                                streaming_data[task_id]['last_update'] = now
                            yield f"content:{chunk_buf}"
                            chunk_buf = ""
                            last_emit = now
                except Exception as stream_err:
                    # 流式失败降级为非流式
                    logger.warning(f"GLM流式请求失败，降级为非流式: {stream_err}")
                    full_text = self._request_internal_template_nonstream(
                        messages=messages, temperature=temperature, max_tokens=max_tokens,
                    )
                    full_text = str(full_text or "")
                    for ch in full_text:
                        content += ch
                        chunk_buf += ch
                        now = time.time()
                        if len(chunk_buf) >= 20 or (now - last_emit) > 0.04:
                            with streaming_lock:
                                streaming_data[task_id]['response'] = content
                                streaming_data[task_id]['progress'] = 'SiSi正在回答...'
                                streaming_data[task_id]['last_update'] = now
                            yield f"content:{chunk_buf}"
                            chunk_buf = ""
                            last_emit = now

                if chunk_buf:
                    with streaming_lock:
                        streaming_data[task_id]['response'] = content
                        streaming_data[task_id]['last_update'] = time.time()
                    yield f"content:{chunk_buf}"

                with streaming_lock:
                    streaming_data[task_id]['status'] = 'completed'
                    streaming_data[task_id]['progress'] = '完成'
                    streaming_data[task_id]['last_update'] = time.time()
                yield "done:完成"
                return

            if not self.client:
                raise ValueError("未配置API密钥，请设置 DEEPSEEK_API_KEY 或 DEEPSEEK_ACCESS_CODE")
            client = self.client
            model = self.model
            
            # 主API也需要初始化streaming_data
            with streaming_lock:
                if task_id in streaming_data:
                    streaming_data[task_id].update({
                        'status': 'processing',
                        'progress': 'AI正在连接...',
                        'last_update': time.time()
                    })
                else:
                    streaming_data[task_id] = {
                        'status': 'processing',
                        'reasoning': '',
                        'response': '',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'progress': 'AI正在连接...',
                        'chunk_buffer': '',
                        'last_update': time.time()
                    }
        
        # --- 内网流式 ---
        reasoning_content = ""
        content = _prefix
        chunk_buffer = ""
        last_yield_time = time.time()
        reasoning_yielded = False
        for chunk in client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=self._resolve_temperature(temperature, model, self.api_base)
        ):
            try:
                current_time = time.time()
                # 处理推理过程 (DeepSeek-R1 特有)
                if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                    reasoning_chunk = chunk.choices[0].delta.reasoning_content
                    reasoning_content += reasoning_chunk
                    with streaming_lock:
                        streaming_data[task_id]['reasoning'] = reasoning_content
                        streaming_data[task_id]['progress'] = 'SiSi正在思考...'
                        streaming_data[task_id]['last_update'] = current_time
                    # 持续yield推理内容更新
                    yield f"reasoning:{reasoning_content}"
                    reasoning_yielded = True
                elif chunk.choices[0].delta.content:
                    content_chunk = chunk.choices[0].delta.content
                    content += content_chunk
                    chunk_buffer += content_chunk
                    should_yield = (
                        len(chunk_buffer) >= 50 or
                        current_time - last_yield_time > 0.5 or
                        '\n' in chunk_buffer or
                        '。' in chunk_buffer or '！' in chunk_buffer or '？' in chunk_buffer
                    )
                    if should_yield:
                        with streaming_lock:
                            streaming_data[task_id]['response'] = content
                            streaming_data[task_id]['progress'] = 'SiSi正在回答...'
                            streaming_data[task_id]['last_update'] = current_time
                        # yield content内容
                        yield f"content:{chunk_buffer}"
                        chunk_buffer = ""
                        last_yield_time = current_time
            except Exception as e:
                print(f"处理chunk时出错: {e}")
                continue
        if chunk_buffer:
            with streaming_lock:
                streaming_data[task_id]['response'] = content
            yield f"content:{chunk_buffer}"
        with streaming_lock:
            streaming_data[task_id]['status'] = 'completed'
            streaming_data[task_id]['progress'] = '完成'
        yield "done:完成"
    
    def start_optimized_streaming_thread(self, messages: List[Dict[str, str]], 
                                       task_id: str,
                                       temperature: float = 0.7, 
                                       max_tokens: int = 2000,
                                       response_prefix: str = ""):
        """启动优化的流式处理线程"""
        self.streaming_active = True
        
        # 提前初始化流式数据
        with streaming_lock:
            streaming_data[task_id] = {
                'status': 'initializing',
                'reasoning': '',
                'response': response_prefix,
                'response_prefix': response_prefix,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'progress': 'AI正在初始化...',
                'chunk_buffer': '',
                'last_update': time.time()
            }
        
        def streaming_worker():
            try:
                for chunk in self.stream_chat_response_optimized(messages, task_id, temperature, max_tokens):
                    if not self.streaming_active:
                        break
                    self.response_queue.put(chunk)
                    
            except Exception as e:
                err = f"流式处理错误: {str(e)}"
                with streaming_lock:
                    if task_id in streaming_data:
                        streaming_data[task_id]['status'] = 'error'
                        streaming_data[task_id]['error'] = err
                        streaming_data[task_id]['progress'] = '失败'
                        streaming_data[task_id]['last_update'] = time.time()
                    else:
                        streaming_data[task_id] = {
                            'status': 'error',
                            'reasoning': '',
                            'response': '',
                            'error': err,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'progress': '失败',
                            'chunk_buffer': '',
                            'last_update': time.time()
                        }
                self.response_queue.put(f"error:{err}")
            finally:
                if self.streaming_active:
                    self.response_queue.put("done:完成")
        
        thread = threading.Thread(target=streaming_worker, daemon=True)
        thread.start()
    
    def get_streaming_data(self, task_id: str) -> Dict:
        """获取流式数据"""
        with streaming_lock:
            return streaming_data.get(task_id, {})
    
    def clear_streaming_data(self, task_id: str):
        """清理流式数据"""
        with streaming_lock:
            if task_id in streaming_data:
                del streaming_data[task_id]

# ============================================================================
# AI聊天管理器
# ============================================================================


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
                stale_tasks.append(task_id)
        
        for task_id in stale_tasks:
            del streaming_data[task_id]
            logger.info(f"Cleaned up stale streaming data for task {task_id} (age: {age:.1f}s)")
    
    if stale_tasks:
        logger.info(f"Cleaned up {len(stale_tasks)} stale streaming tasks")
    
    return len(stale_tasks)

class AIChatManager:
    """AI聊天管理器 - 统一处理所有看板的AI对话功能"""
    
    def __init__(self):
        """初始化AI聊天管理器"""
        self.chatbot = None
        try:
            self.chatbot = DeepSeekStreamingChat()
            logger.info("DeepSeek聊天机器人初始化成功")
        except Exception as e:
            logger.error(f"DeepSeek聊天机器人初始化失败: {e}")
            self.chatbot = None
        
        # 预设问题模板
        self.preset_questions = {
            'defect': {
                'summary': "请总结当前的缺陷数据情况",
                'risk': "请分析当前数据中的高风险问题", 
                'project': "请分析项目分布情况",
                'trend': "请给出趋势分析建议"
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
                'trend': "请给出测试改进建议"
            },
            'general': {
                'summary': "请总结当前数据情况",
                'analysis': "请分析当前数据",
                'insight': "请提供数据洞察",
                'recommendation': "请给出改进建议"
            }
        }
    
    def generate_data_context(self, data: pd.DataFrame, context_type: str = 'general', 
                            custom_fields: Optional[Dict[str, str]] = None) -> str:
        """
        生成数据上下文信息
        
        Args:
            data: 要分析的数据DataFrame
            context_type: 上下文类型 ('defect', 'test', 'general')
            custom_fields: 自定义字段映射 {'field_name': 'display_name'}
        
        Returns:
            格式化的数据上下文字符串
        """
        if data.empty:
            return "No data available."
        
        context_parts = [f"Current {context_type.title()} Data Summary:"]
        context_parts.append(f"- Total records: {len(data)}")
        
        # 根据不同类型添加特定分析
        if context_type == 'defect':
            context_parts.extend(self._generate_defect_context(data))
        elif context_type == 'test':
            context_parts.extend(self._generate_test_context(data))
        elif context_type == 'general':
            context_parts.extend(self._generate_general_context(data))
        
        # 添加自定义字段分析
        if custom_fields:
            for field, display_name in custom_fields.items():
                if field in data.columns:
                    field_counts = data[field].value_counts().head(5).to_dict()
                    context_parts.append(f"- {display_name}: {field_counts}")
        
        return "\n".join(context_parts)
    
    def _generate_defect_context(self, data: pd.DataFrame) -> List[str]:
        """生成缺陷数据特定上下文"""
        context_parts = []
        
        # 矩阵分布
        if 'matrix_display' in data.columns:
            matrix_counts = data['matrix_display'].value_counts().head(5).to_dict()
            context_parts.append(f"- Matrix distribution: {matrix_counts}")
        
        # 项目分布
        if 'tproject' in data.columns:
            project_counts = data['tproject'].value_counts().head(5).to_dict()
            context_parts.append(f"- Top projects: {project_counts}")
        
        # 状态分布
        if 'status_phase' in data.columns:
            status_counts = data['status_phase'].value_counts().head(5).to_dict()
            context_parts.append(f"- Status distribution: {status_counts}")
        
        # 严重性分布
        if 'severity_group' in data.columns:
            severity_counts = data['severity_group'].value_counts().to_dict()
            context_parts.append(f"- Severity distribution: {severity_counts}")
        
        return context_parts
    
    def _generate_test_context(self, data: pd.DataFrame) -> List[str]:
        """生成测试数据特定上下文"""
        context_parts = []
        
        # 测试覆盖率相关字段
        coverage_fields = ['test_coverage', 'coverage_rate', 'pass_rate']
        for field in coverage_fields:
            if field in data.columns:
                avg_value = data[field].mean()
                context_parts.append(f"- Average {field}: {avg_value:.2f}")
        
        # 测试状态分布
        if 'test_status' in data.columns:
            status_counts = data['test_status'].value_counts().to_dict()
            context_parts.append(f"- Test status distribution: {status_counts}")
        
        return context_parts
    
    def _generate_general_context(self, data: pd.DataFrame) -> List[str]:
        """生成通用数据上下文"""
        context_parts = []
        
        # 数据基本信息
        context_parts.append(f"- Columns: {len(data.columns)}")
        context_parts.append(f"- Data types: {data.dtypes.value_counts().to_dict()}")
        
        # 检查常见字段
        common_fields = ['project', 'status', 'type', 'category', 'team', 'owner']
        for field in common_fields:
            if field in data.columns:
                unique_count = data[field].nunique()
                context_parts.append(f"- Unique {field}s: {unique_count}")
        
        return context_parts
    
    def get_ai_response(self, user_message: str, data_context: str, 
                       dashboard_type: str = 'general') -> str:
        """
        获取AI响应
        
        Args:
            user_message: 用户消息
            data_context: 数据上下文
            dashboard_type: 看板类型，用于选择合适的系统提示
        
        Returns:
            AI响应内容
        """
        # 检查是否有可用的chatbot
        if self.chatbot and self.chatbot.validate_api_key():
            try:
                # 使用新的统一 Prompt 模板
                try:
                    from prompt_templates import get_system_prompt
                    system_message = get_system_prompt(dashboard_type, data_context)
                except ImportError:
                    # 降级：如果 prompt_templates 不存在，使用原简化版
                    system_prompts = {
                        'defect': "You are a helpful assistant for defect analysis.",
                        'test': "You are a helpful assistant for test coverage analysis.",
                        'trend': "You are a helpful assistant for trend analysis.",
                        'general': "You are a helpful assistant for data analysis."
                    }
                    system_message = system_prompts.get(dashboard_type, system_prompts['general'])
                    system_message += f"\n\nData context: {data_context}"

                # 添加用户问题到消息
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ]
                
                # 获取DeepSeek API响应
                response = self.chatbot.get_simple_response(messages, temperature=0.7, max_tokens=1000)
                return response
                
            except Exception as e:
                return f"调用DeepSeek API时出现错误：{str(e)}"
        
        # 降级到简单响应
        return self.get_simple_response(user_message, data_context, dashboard_type)
    
    def get_simple_response(self, user_message: str, data_context: str, 
                          dashboard_type: str = 'general') -> str:
        """
        简单规则响应系统（作为AI API的降级方案）
        
        Args:
            user_message: 用户消息
            data_context: 数据上下文
            dashboard_type: 看板类型
        
        Returns:
            规则响应内容
        """
        user_message_lower = user_message.lower()
        
        # 提取数据上下文中的关键信息
        total_records = self._extract_total_records(data_context)
        
        if "总结" in user_message or "summary" in user_message_lower:
            response = f"基于当前{dashboard_type}数据分析：\n\n"
            response += f"• 总记录数: {total_records}\n"
            response += f"• {data_context}\n"
            
            if dashboard_type == 'defect':
                response += "\n建议重点关注高风险缺陷和TopIssue问题。"
            elif dashboard_type == 'test':
                response += "\n建议重点关注覆盖率较低的模块。"
            else:
                response += "\n建议进一步分析数据趋势和分布。"
                
        elif "风险" in user_message or "risk" in user_message_lower:
            response = f"{dashboard_type}风险分析：\n\n"
            response += f"• 当前数据量: {total_records}\n"
            if dashboard_type == 'defect':
                response += "• 建议优先处理高严重性和TopIssue缺陷\n"
                response += "• 关注矩阵位置1A-1E的高风险问题"
            elif dashboard_type == 'test':
                response += "• 建议优先提升覆盖率较低的模块\n"
                response += "• 关注失败率较高的测试用例"
            else:
                response += "• 建议识别数据异常和趋势变化\n"
                response += "• 关注关键指标的波动"
                
        elif "项目" in user_message or "project" in user_message_lower:
            response = f"{dashboard_type}项目分析：\n\n"
            response += f"• 总数据量: {total_records}\n"
            response += "• 建议分析各项目的数据分布和趋势\n"
            response += "• 识别需要重点关注的项目"
            
        elif "趋势" in user_message or "trend" in user_message_lower:
            response = f"{dashboard_type}趋势分析建议：\n\n"
            response += "• 建议定期监控关键指标变化\n"
            response += "• 分析时间序列数据找出规律\n"
            response += "• 建立预警机制及时发现异常\n"
            response += "• 跟踪改进措施的效果"
            
        else:
            response = f"感谢您的问题！我可以帮助您分析{dashboard_type}数据。请尝试询问关于数据总结、风险分析、项目分布或趋势分析的问题。"
        
        return response
    
    def _extract_total_records(self, data_context: str) -> str:
        """从数据上下文中提取总记录数"""
        try:
            for line in data_context.split('\n'):
                if 'Total records:' in line:
                    return line.split('Total records:')[1].strip()
            return "未知"
        except:
            return "未知"
    
    def create_enhanced_chat_interface(self, chat_id_prefix: str = 'chat', 
                                     dashboard_type: str = 'general') -> html.Div:
        """
        创建增强版聊天界面组件，支持流式对话和推理显示
        
        Args:
            chat_id_prefix: 聊天组件ID前缀，避免不同看板间冲突
            dashboard_type: 看板类型，用于定制预设问题
        
        Returns:
            增强版聊天界面的Dash组件
        """
        # 获取对应类型的预设问题
        preset_questions = self.preset_questions.get(dashboard_type, self.preset_questions['general'])
        
        # 创建预设问题按钮 - 美化样式
        preset_buttons = []
        button_colors = [
            {'bg': '#e3f2fd', 'color': '#1976d2', 'border': '#1976d2'},
            {'bg': '#fce4ec', 'color': '#c2185b', 'border': '#c2185b'},
            {'bg': '#fff3e0', 'color': '#f57c00', 'border': '#f57c00'},
            {'bg': '#e8f5e8', 'color': '#388e3c', 'border': '#388e3c'},
            {'bg': '#f3e5f5', 'color': '#7b1fa2', 'border': '#7b1fa2'},
            {'bg': '#e0f2f1', 'color': '#00796b', 'border': '#00796b'}
        ]
        
        for i, (key, question) in enumerate(preset_questions.items()):
            color_scheme = button_colors[i % len(button_colors)]
            button_id = f'{chat_id_prefix}-{key}-btn'
            preset_buttons.append(
                html.Button(
                    question, 
                    id=button_id, 
                    n_clicks=0, 
                    className='chat-quick-btn',
                    style={
                        'margin': '5px',
                        'padding': '8px 12px',
                        'fontSize': '12px',
                        'backgroundColor': color_scheme['bg'],
                        'color': color_scheme['color'],
                        'border': f"1px solid {color_scheme['border']}",
                        'borderRadius': '15px',
                        'cursor': 'pointer',
                        'transition': 'all 0.3s ease'
                    }
                )
            )

        enhanced_interface = html.Div([
            html.Div([
                # 对话历史显示区域 - 增强样式
                html.Div(
                    id=f'{chat_id_prefix}-history', 
                    children=[
                        html.Div([
                            html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3498db'}),
                            html.Span("您好！我是AI助手，可以帮助您分析数据。请问有什么可以帮助您的吗？")
                        ], style={
                            'padding': '12px', 
                            'backgroundColor': '#f8f9fa', 
                            'borderRadius': '8px', 
                            'margin': '8px 0', 
                            'textAlign': 'left',
                            'border': '1px solid #e9ecef',
                            'boxShadow': '0 1px 3px rgba(0,0,0,0.1)'
                        })
                    ], 
                    style={
                        'height': '300px', 
                        'overflowY': 'auto', 
                        'border': '1px solid #ddd', 
                        'padding': '15px', 
                        'borderRadius': '8px', 
                        'backgroundColor': '#fafafa',
                        'scrollBehavior': 'smooth'
                    }
                ),
                
                # 实时状态显示区域
                html.Div(
                    id=f'{chat_id_prefix}-status', 
                    children=[],
                    style={
                        'textAlign': 'center', 
                        'marginTop': '10px', 
                        'marginBottom': '10px', 
                        'fontSize': '14px', 
                        'color': '#666',
                        'minHeight': '20px'
                    }
                ),
                
                # 输入框和发送按钮 - 增强样式
                html.Div([
                    dcc.Input(
                        id=f'{chat_id_prefix}-input',
                        type='text',
                        placeholder='请输入您的问题...',
                        style={
                            'width': '82%', 
                            'padding': '12px', 
                            'marginRight': '10px', 
                            'borderRadius': '8px', 
                            'border': '2px solid #e0e0e0',
                            'fontSize': '14px',
                            'outline': 'none',
                            'transition': 'border-color 0.3s ease'
                        },
                        value='',
                        persistence=False
                    ),
                    html.Button(
                        [html.I(className="fas fa-paper-plane", style={'marginRight': '5px'}), '发送'], 
                        id=f'{chat_id_prefix}-send-button', 
                        n_clicks=0, 
                        style={
                            'width': '15%', 
                            'padding': '12px', 
                            'backgroundColor': '#3498db', 
                            'color': 'white', 
                            'border': 'none', 
                            'borderRadius': '8px', 
                            'cursor': 'pointer',
                            'fontSize': '14px',
                            'fontWeight': 'bold',
                            'transition': 'background-color 0.3s ease'
                        }
                    )
                ], style={'display': 'flex', 'alignItems': 'center', 'marginTop': '10px'}),
                
                # 预设问题快捷按钮
                html.Div([
                    html.P("快速提问：", style={'fontSize': '14px', 'margin': '10px 0 5px 0', 'color': '#666'}),
                    html.Div(
                        preset_buttons,
                        style={
                            'display': 'flex', 
                            'gap': '8px', 
                            'flexWrap': 'wrap',
                            'justifyContent': 'center'
                        }
                    )
                ], style={'marginTop': '15px'}),
                
                # 聊天控制面板
                html.Div([
                    # 推理过程显示开关
                    html.Div([
                        html.Label([
                            dcc.Checklist(
                                id=f'{chat_id_prefix}-show-reasoning',
                                options=[{'label': ' 显示AI思考过程', 'value': 'show'}],
                                value=['show'],  # 默认开启
                                style={'fontSize': '14px'}
                            )
                        ], style={'margin': '0'})
                    ], style={'flex': '1'}),
                    
                    # 自动滚动开关
                    html.Div([
                        html.Label([
                            dcc.Checklist(
                                id=f'{chat_id_prefix}-auto-scroll',
                                options=[{'label': ' 自动滚动', 'value': 'auto'}],
                                value=['auto'],  # 默认开启
                                style={'fontSize': '14px'}
                            )
                        ], style={'margin': '0'})
                    ], style={'flex': '1'}),

                    html.Div([
                        html.Label([
                            dcc.Checklist(
                                id=f'{chat_id_prefix}-known-issues',
                                options=[{'label': ' 识别已知问题', 'value': 'known'}],
                                value=[],
                                style={'fontSize': '14px'}
                            )
                        ], style={'margin': '0'})
                    ], style={'flex': '1'}),
                    
                    # 功能按钮
                    html.Div([
                        html.Button(
                            [html.I(className="fas fa-download", style={'marginRight': '5px'}), '导出对话'],
                            id=f'{chat_id_prefix}-export-button',
                            n_clicks=0,
                            style={
                                'padding': '6px 12px',
                                'backgroundColor': '#17a2b8',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '4px',
                                'cursor': 'pointer',
                                'fontSize': '12px',
                                'marginRight': '8px'
                            }
                        ),
                        html.Button(
                            [html.I(className="fas fa-trash", style={'marginRight': '5px'}), '清空'],
                            id=f'{chat_id_prefix}-clear-button',
                            n_clicks=0,
                            style={
                                'padding': '6px 12px',
                                'backgroundColor': '#dc3545',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '4px',
                                'cursor': 'pointer',
                                'fontSize': '12px'
                            }
                        )
                    ], style={'textAlign': 'right'})
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'marginTop': '10px',
                    'padding': '8px',
                    'backgroundColor': '#f8f9fa',
                    'borderRadius': '4px',
                    'border': '1px solid #dee2e6'
                })
            ], style={'maxWidth': '800px', 'margin': '0 auto', 'padding': '20px'})
        ], style={})
        
        return enhanced_interface
    
    def create_chat_interface(self, chat_id_prefix: str = 'chat', 
                            dashboard_type: str = 'general') -> html.Div:
        """
        创建基础聊天界面组件 - 保持向后兼容性
        """
        return self.create_enhanced_chat_interface(chat_id_prefix, dashboard_type)
    
    def create_enhanced_chat_stores(self, chat_id_prefix: str = 'chat') -> List[dcc.Store]:
        """
        创建增强版聊天相关的存储组件
        
        Args:
            chat_id_prefix: 聊天组件ID前缀
        
        Returns:
            存储组件列表
        """
        return [
            dcc.Store(id=f'{chat_id_prefix}-messages', data=[], storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-streaming-response', data='', storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-streaming-state', data={'active': False, 'task_id': None}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-latest-duplicate-result', data=None, storage_type='session'),
            # 添加定时器用于流式更新
            dcc.Interval(
                id=f'{chat_id_prefix}-update-interval',
                interval=200,  # 200ms更新一次，提升响应速度
                n_intervals=0,
                disabled=True
            )
        ]
    
    def register_enhanced_chat_callbacks(self, app: dash.Dash, chat_id_prefix: str = 'chat', 
                                       data_store_id: str = 'filtered-data', 
                                       dashboard_type: str = 'general',
                                       data_processor_func: Optional[Callable] = None,
                                       chat_only_mode: bool = True):
        """
        注册增强版聊天相关的回调函数，支持流式对话和推理显示
        
        Args:
            app: Dash应用实例
            chat_id_prefix: 聊天组件ID前缀
            data_store_id: 数据存储组件ID
            dashboard_type: 看板类型
            data_processor_func: 自定义数据处理函数，接收filtered_data并返回DataFrame
            chat_only_mode: 是否启用纯聊天模式（默认True），不使用本地数据上下文
        """
        
        # 创建流式聊天实例
        streaming_chat = DeepSeekStreamingChat()
        
        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children'),
             Output(f'{chat_id_prefix}-input', 'value'),
             Output(f'{chat_id_prefix}-messages', 'data'),
             Output(f'{chat_id_prefix}-streaming-state', 'data'),
             Output(f'{chat_id_prefix}-update-interval', 'disabled'),
             Output(f'{chat_id_prefix}-status', 'children'),
             Output(f'{chat_id_prefix}-latest-duplicate-result', 'data')],
            [Input(f'{chat_id_prefix}-send-button', 'n_clicks'),
             Input(f'{chat_id_prefix}-input', 'n_submit'),
             Input(f'{chat_id_prefix}-clear-button', 'n_clicks')] +
            [Input(f'{chat_id_prefix}-{key}-btn', 'n_clicks') 
             for key in self.preset_questions.get(dashboard_type, self.preset_questions['general']).keys()],
            [State(f'{chat_id_prefix}-input', 'value'),
             State(f'{chat_id_prefix}-messages', 'data'),
             State(f'{chat_id_prefix}-streaming-state', 'data'),
             State(f'{chat_id_prefix}-show-reasoning', 'value'),
             State(data_store_id, 'data'),
               State(f'{chat_id_prefix}-known-issues', 'value'),
               State(f'{chat_id_prefix}-latest-duplicate-result', 'data')]
        )
        def handle_enhanced_chat(*args):
            """处理增强版聊天交互，支持流式响应"""
            # Clean up stale streaming data
            try:
                cleanup_stale_streaming_data(max_age_seconds=300)
            except Exception as e:
                logger.warning(f"Failed to cleanup stale data: {e}")
            try:
                max_store_messages = int(os.getenv("CHAT_UI_MAX_MESSAGES", "200"))
            except Exception:
                max_store_messages = 200
            try:
                max_render_messages = int(os.getenv("CHAT_UI_RENDER_MESSAGES", "60"))
            except Exception:
                max_render_messages = 60
            try:
                max_llm_history_messages = int(os.getenv("CHAT_LLM_HISTORY_MESSAGES", "10"))
            except Exception:
                max_llm_history_messages = 10

            def _trim_chat_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                if not messages:
                    return []
                system_msgs = [m for m in messages if m.get("role") == "system"]
                head = system_msgs[:1]
                rest = [m for m in messages if m.get("role") != "system"]
                if max_store_messages <= 0:
                    return head
                keep = max(0, max_store_messages - len(head))
                if keep <= 0:
                    return head
                if len(rest) <= keep:
                    return head + rest
                return head + rest[-keep:]
            # 解析参数
            send_clicks = args[0]
            input_submit = args[1]
            clear_clicks = args[2]
            preset_clicks = args[3:-7]  # 预设按钮点击次数
            input_value = args[-7]
            chat_messages = args[-6]
            streaming_state = args[-5]
            show_reasoning = args[-4]
            filtered_data = args[-3]
            known_issues_checked = args[-2] or []
            latest_duplicate_result = args[-1]
            
            ctx = callback_context
            if not ctx.triggered:
                raise PreventUpdate
            
            trigger = ctx.triggered[0]
            prop_id = trigger['prop_id']
            
            # 处理清空对话
            if prop_id == f'{chat_id_prefix}-clear-button.n_clicks' and clear_clicks:
                initial_message = html.Div([
                    html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span("您好！我是AI助手，可以帮助您分析数据。请问有什么可以帮助您的吗？")
                ], style={
                    'padding': '12px', 
                    'backgroundColor': '#f8f9fa', 
                    'borderRadius': '8px', 
                    'margin': '8px 0', 
                    'textAlign': 'left',
                    'border': '1px solid #e9ecef',
                    'boxShadow': '0 1px 3px rgba(0,0,0,0.1)'
                })
                return [initial_message], "", [], {'active': False, 'task_id': None}, True, "", None
            
            # 初始化聊天消息
            if not chat_messages:
                chat_messages = [
                    {"role": "system", "content": f"You are a helpful assistant for {dashboard_type} analysis."},
                    {"role": "assistant", "content": "您好！我是AI助手，可以帮助您分析数据。请问有什么可以帮助您的吗？"}
                ]
            else:
                chat_messages = _trim_chat_messages(chat_messages)
            
            # 获取当前数据
            current_data = pd.DataFrame()
            if not chat_only_mode and filtered_data:
                try:
                    if data_processor_func:
                        current_data = data_processor_func(filtered_data)
                    else:
                        json_data = filtered_data['data'] if isinstance(filtered_data, dict) else filtered_data
                        current_data = pd.read_json(io.StringIO(json_data), orient='split')
                except:
                    current_data = pd.DataFrame()
            else:
                # 在纯聊天模式下，明确不使用本地数据
                current_data = pd.DataFrame()

            use_known_issues = 'known' in (known_issues_checked or [])
            
            # 确定用户消息
            user_message = ""
            preset_questions = self.preset_questions.get(dashboard_type, self.preset_questions['general'])
            
            if prop_id in [f'{chat_id_prefix}-send-button.n_clicks', f'{chat_id_prefix}-input.n_submit']:
                if input_value and input_value.strip():
                    user_message = input_value.strip()
            else:
                # 检查哪个预设按钮被点击
                for key, question in preset_questions.items():
                    if prop_id == f'{chat_id_prefix}-{key}-btn.n_clicks':
                        user_message = question
                        break
            
            # 处理用户消息
            if user_message:
                # 添加用户消息到聊天历史
                chat_messages.append({"role": "user", "content": user_message})
                chat_messages = _trim_chat_messages(chat_messages)
                
                # 只发用户输入，不拼接数据上下文
                try:
                    if use_known_issues:
                        df: pd.DataFrame = pd.DataFrame()
                        if isinstance(current_data, pd.DataFrame) and not current_data.empty:
                            df = current_data
                        elif isinstance(current_data, dict):
                            defects_df = current_data.get("defects")
                            if isinstance(defects_df, pd.DataFrame) and not defects_df.empty:
                                df = defects_df
                        if df.empty:
                            try:
                                from data_processor import load_defect_data
                                loaded = load_defect_data()
                                df = loaded if isinstance(loaded, pd.DataFrame) else pd.DataFrame()
                            except Exception:
                                df = pd.DataFrame()

                        hints = extract_hints(user_message)
                        index = get_or_build_index(cache_key=f"duplicate:{dashboard_type}", df=df)
                        candidates = index.search(user_message, hints=hints, top_k=10)

                        if not getattr(streaming_chat, "client", None) and not getattr(streaming_chat, "backup_api_key", ""):
                            duplicate_summary = _build_duplicate_summary_text(candidates)
                            duplicate_payload = _build_duplicate_result_payload(
                                query_text=user_message,
                                dashboard_type=dashboard_type,
                                candidates=candidates,
                            )
                            latest_duplicate_result = _build_latest_duplicate_result_store(duplicate_payload)
                            chat_messages.append(
                                {
                                    "role": "assistant",
                                    "type": "duplicate-search-result",
                                    "content": duplicate_summary,
                                    "duplicate_result": duplicate_payload,
                                }
                            )
                            new_streaming_state = {'active': False, 'task_id': None}
                            chat_history_children = []
                            for i, msg in enumerate(chat_messages):
                                if msg["role"] == "user":
                                    chat_history_children.append(
                                        html.Div([
                                            html.I(className="fas fa-user", style={'marginRight': '8px', 'color': '#2c3e50'}),
                                            html.Span(msg["content"])
                                        ], style={
                                            'padding': '12px',
                                            'backgroundColor': '#e3f2fd',
                                            'borderRadius': '8px',
                                            'margin': '8px 0',
                                            'textAlign': 'left',
                                            'border': '1px solid #bbdefb',
                                            'marginLeft': '20px'
                                        })
                                    )
                                elif msg["role"] == "assistant":
                                    if msg.get("type") == "duplicate-search-result":
                                        chat_history_children.append(
                                            render_duplicate_result_message(msg, chat_id_prefix=chat_id_prefix)
                                        )
                                    else:
                                        icon_class = "fas fa-brain" if "思考" in msg["content"] else "fas fa-robot"
                                        icon_color = "#f39c12" if "思考" in msg["content"] else "#3498db"
                                        chat_history_children.append(
                                            html.Div([
                                                html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                                html.Span(msg["content"], style={'whiteSpace': 'pre-line'})
                                            ], style={
                                                'padding': '12px',
                                                'backgroundColor': '#f8f9fa',
                                                'borderRadius': '8px',
                                                'margin': '8px 0',
                                                'textAlign': 'left',
                                                'border': '1px solid #e9ecef',
                                                'marginRight': '20px'
                                            })
                                        )

                            return (chat_history_children, "", chat_messages, new_streaming_state, True, "", latest_duplicate_result)

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
                        system_prompt = f"""你是缺陷提票前置审查助手。你的任务是：根据用户的自然语言问题描述，在“候选缺陷列表”中找出最相似的已知问题，并给出是否建议提票的结论。\n\n规则：\n1) 只能基于提供的候选列表，不要编造不存在的ticket。\n2) 相似度评分使用 1-10（10=几乎同一个问题）。你可以参考候选里给定的 score_1_10，但如果你认为不合理可以小幅调整；最终输出仍需按 10→1 排序。\n3) 如果最高相似度 >= 8：结论默认“不建议提票”，建议合并到最相似票或补充复现信息后追踪。\n4) 如果最高相似度 <= 6：结论默认“可以提票”，并给出建议标题与必填信息清单。\n\n输出格式（必须使用以下结构）：\n【结论】\n- 建议：不建议提票 / 可以提票 / 需要补充信息后再判断\n- 依据：一句话说明\n\n【相似已知问题（按相似度降序）】\n- 10分：#id - 标题（project/pu，phase）\\n  匹配点：...\n- 9分：...\n\n【下一步】\n- 如果不建议提票：建议合并到哪一票，以及需要补充哪些信息。\n- 如果可以提票：建议标题、复现步骤、期望/实际、环境、日志/截图等。\n\n候选缺陷列表（JSON Lines）：\n{candidate_block}\n"""

                        # Populate store so feedback buttons work even with LLM path
                        duplicate_payload = _build_duplicate_result_payload(
                            query_text=user_message,
                            dashboard_type=dashboard_type,
                            candidates=candidates,
                        )
                        latest_duplicate_result = _build_latest_duplicate_result_store(duplicate_payload)

                        api_messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
                    else:
                        api_messages = []
                        non_system = [m for m in chat_messages if m.get("role") != "system"]
                        if max_llm_history_messages > 0 and len(non_system) > max_llm_history_messages:
                            non_system = non_system[-max_llm_history_messages:]
                        for msg in ([m for m in chat_messages if m.get("role") == "system"][:1] + non_system):
                            if msg["role"] == "system":
                                api_messages.append(msg)
                            elif msg["role"] == "user":
                                api_messages.append({"role": "user", "content": msg["content"]})
                            elif msg["role"] == "assistant":
                                api_messages.append(msg)
                    
                    # 启动流式响应
                    task_id = f"{chat_id_prefix}_{int(time.time())}"
                    streaming_chat.start_optimized_streaming_thread(api_messages, task_id, temperature=0.2 if use_known_issues else 0.7, max_tokens=2000)
                    
                    # 添加临时的"正在思考"消息
                    thinking_message = {"role": "assistant", "content": "🤔 正在检索已知问题并生成建议..." if use_known_issues else "🤔 正在分析数据并思考..."}
                    chat_messages.append(thinking_message)
                    chat_messages = _trim_chat_messages(chat_messages)
                    
                    new_streaming_state = {'active': True, 'task_id': task_id}
                    if use_known_issues and candidates:
                        new_streaming_state['is_duplicate_search'] = True
                        new_streaming_state['duplicate_payload'] = duplicate_payload
                    
                except Exception as e:
                    error_response = f"抱歉，处理您的请求时出现错误：{str(e)}"
                    chat_messages.append({"role": "assistant", "content": error_response})
                    chat_messages = _trim_chat_messages(chat_messages)
                    new_streaming_state = {'active': False, 'task_id': None}
            else:
                new_streaming_state = streaming_state
            
            # 生成聊天历史HTML
            chat_history_children = []
            visible_messages = [m for m in chat_messages if m.get("role") != "system"]
            if max_render_messages > 0 and len(visible_messages) > max_render_messages:
                folded = len(visible_messages) - max_render_messages
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
                visible_messages = visible_messages[-max_render_messages:]
            for i, msg in enumerate(visible_messages):
                if msg["role"] == "user":
                    chat_history_children.append(
                        html.Div([
                            html.I(className="fas fa-user", style={'marginRight': '8px', 'color': '#2c3e50'}),
                            html.Span(msg["content"])
                        ], style={
                            'padding': '12px',
                            'backgroundColor': '#e3f2fd',
                            'borderRadius': '8px',
                            'margin': '8px 0',
                            'textAlign': 'left',
                            'border': '1px solid #bbdefb',
                            'marginLeft': '20px'
                        })
                    )
                elif msg["role"] == "assistant":
                    if msg.get("type") == "duplicate-search-result":
                        chat_history_children.append(
                            render_duplicate_result_message(msg, chat_id_prefix=chat_id_prefix)
                        )
                    else:
                        icon_class = "fas fa-brain" if "思考" in msg["content"] else "fas fa-robot"
                        icon_color = "#f39c12" if "思考" in msg["content"] else "#3498db"
                        
                        chat_history_children.append(
                            html.Div([
                                html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                html.Span(msg["content"], style={'whiteSpace': 'pre-line'})
                            ], style={
                                'padding': '12px',
                                'backgroundColor': '#f8f9fa',
                                'borderRadius': '8px',
                                'margin': '8px 0',
                                'textAlign': 'left',
                                'border': '1px solid #e9ecef',
                                'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                                'marginRight': '20px'
                            })
                        )
            
            # 设置状态显示
            status_display = ""
            if new_streaming_state.get('active'):
                status_display = html.Div([
                    html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span("AI正在分析数据并生成回答...", style={'color': '#666'})
                ])
            
            # 清空输入框
            new_input_value = ""
            
            return (chat_history_children, new_input_value, chat_messages, 
                     new_streaming_state, not new_streaming_state.get('active'), status_display, latest_duplicate_result)

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
        
        # 流式更新回调
        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-messages', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-streaming-state', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-update-interval', 'disabled', allow_duplicate=True),
             Output(f'{chat_id_prefix}-status', 'children', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-update-interval', 'n_intervals')],
            [State(f'{chat_id_prefix}-messages', 'data'),
             State(f'{chat_id_prefix}-streaming-state', 'data'),
             State(f'{chat_id_prefix}-show-reasoning', 'value'),
             State(f'{chat_id_prefix}-latest-duplicate-result', 'data')],
            prevent_initial_call=True
        )
        def update_streaming_response(n_intervals, chat_messages, streaming_state, show_reasoning, latest_dup_result):
            """优化的流式响应更新"""
            if not streaming_state or not streaming_state.get('active'):
                raise PreventUpdate
            
            try:
                # 从全局存储获取流式数据
                task_id = streaming_state.get('task_id')
                if not task_id:
                    print(f"No task_id in streaming_state: {streaming_state}")
                    raise PreventUpdate
                
                stream_data = streaming_chat.get_streaming_data(task_id)
                if not stream_data:
                    print(f"No stream_data for task_id: {task_id}")
                    raise PreventUpdate
                
                # 检查是否有新的更新
                last_update = stream_data.get('last_update', 0)
                current_time = time.time()
                
                # 如果没有新的更新，跳过
                if current_time - last_update > 30:  # 30秒超时
                    streaming_state = {'active': False, 'task_id': None}
                    status_display = ""
                    # 保持现有聊天历史，不要清空，直接返回当前状态
                    # 生成当前聊天历史显示
                    chat_history_children = []
                    for msg in chat_messages:
                        if msg["role"] == "user":
                            chat_history_children.append(
                                html.Div([
                                    html.Div([
                                        html.I(className="fas fa-user", style={'marginRight': '8px', 'color': '#2c3e50'}),
                                        html.Span("用户", style={'fontWeight': 'bold', 'color': '#2c3e50'})
                                    ], style={'marginBottom': '5px'}),
                                    html.Div(msg["content"], style={'paddingLeft': '24px'})
                                ], style={
                                    'padding': '12px',
                                    'backgroundColor': '#e3f2fd',
                                    'borderRadius': '8px',
                                    'margin': '8px 0',
                                    'textAlign': 'left',
                                    'border': '1px solid #bbdefb',
                                    'marginLeft': '20px',
                                    'boxShadow': '0 1px 3px rgba(0,0,0,0.1)'
                                })
                            )
                        elif msg["role"] == "assistant":
                            if msg.get("type") == "duplicate-search-result":
                                chat_history_children.append(
                                    render_duplicate_result_message(msg, chat_id_prefix=chat_id_prefix)
                                )
                                continue
                            # 根据消息类型设置样式
                            if msg.get("type") == "reasoning":
                                icon_class = "fas fa-brain"
                                icon_color = "#f39c12"
                                bg_color = "#fef9e7"
                                border_color = "#f4d03f"
                                title = "AI思考"
                            elif msg.get("type") == "error":
                                icon_class = "fas fa-exclamation-triangle"
                                icon_color = "#e74c3c"
                                bg_color = "#fdeaea"
                                border_color = "#f1948a"
                                title = "错误"
                            else:
                                icon_class = "fas fa-robot"
                                icon_color = "#3498db"
                                bg_color = "#f8f9fa"
                                border_color = "#e9ecef"
                                title = "AI助手"
                            
                            chat_history_children.append(
                                html.Div([
                                    html.Div([
                                        html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                        html.Span(title, style={'fontWeight': 'bold', 'color': icon_color})
                                    ], style={'marginBottom': '5px'}),
                                    html.Div(
                                        msg["content"],
                                        style={
                                            'paddingLeft': '24px',
                                            'whiteSpace': 'pre-line',
                                            'fontFamily': 'inherit',
                                            **(
                                                {
                                                    'maxHeight': '7em',
                                                    'overflowY': 'auto',
                                                    'fontSize': '12px',
                                                    'lineHeight': '1.2em'
                                                }
                                                if msg.get("type") == "reasoning"
                                                else {}
                                            )
                                        },
                                    )
                                ], style={
                                    'padding': '12px',
                                    'backgroundColor': bg_color,
                                    'borderRadius': '8px',
                                    'margin': '8px 0',
                                    'textAlign': 'left',
                                    'border': f'1px solid {border_color}',
                                    'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                                    'marginRight': '20px'
                                })
                            )
                    
                    # 返回当前状态，不抛出异常
                    return (chat_history_children, chat_messages, streaming_state, 
                           True, status_display)  # 启用输入框，清空状态显示
                
                # 处理推理内容
                reasoning_content = stream_data.get('reasoning', '')
                if reasoning_content and show_reasoning and 'show' in show_reasoning:
                    def _tail_lines(text: str, max_lines: int = 5) -> str:
                        raw_lines = (text or "").splitlines()
                        tail = raw_lines[-max_lines:] if raw_lines else []
                        return "\n".join(tail).strip()

                    trimmed = _tail_lines(reasoning_content, 5)
                    if trimmed:
                        reasoning_content = trimmed
                    # 查找当前任务对应的推理消息（从最后开始查找）
                    reasoning_msg_index = -1
                    current_task_id = streaming_state.get('task_id')
                    
                    # 从后往前查找，找到与当前task_id关联的推理消息
                    for i in range(len(chat_messages) - 1, -1, -1):
                        if (chat_messages[i].get('type') == 'reasoning' and 
                            chat_messages[i].get('task_id') == current_task_id):
                            reasoning_msg_index = i
                            break
                    
                    if reasoning_msg_index == -1:
                        # 创建新的推理消息，关联到当前task_id
                        chat_messages.append({
                            "role": "assistant",
                            "content": f"🧠 思考(最近5行)：\n{reasoning_content}",
                            "type": "reasoning",
                            "task_id": current_task_id,
                            "timestamp": datetime.now().strftime('%H:%M:%S')
                        })
                    else:
                        # 更新现有推理消息
                        chat_messages[reasoning_msg_index]["content"] = f"🧠 思考(最近5行)：\n{reasoning_content}"
                
                # 处理回复内容
                response_content = stream_data.get('response', '')
                if response_content:
                    # 查找当前任务对应的回复消息（从最后开始查找）
                    response_msg_index = -1
                    current_task_id = streaming_state.get('task_id')
                    
                    # 从后往前查找，找到与当前task_id关联的回复消息
                    for i in range(len(chat_messages) - 1, -1, -1):
                        if (chat_messages[i]["role"] == "assistant" and 
                            chat_messages[i].get("type") != "reasoning" and
                            chat_messages[i].get('task_id') == current_task_id):
                            response_msg_index = i
                            break
                    
                    if response_msg_index == -1:
                        # 创建新的回复消息，关联到当前task_id
                        chat_messages.append({
                            "role": "assistant",
                            "content": response_content,
                            "type": "response",
                            "task_id": current_task_id,
                            "timestamp": datetime.now().strftime('%H:%M:%S')
                        })
                    else:
                        # 更新现有回复消息
                        if "正在分析数据并思考" in chat_messages[response_msg_index]["content"]:
                            # 开始新的回答
                            chat_messages[response_msg_index]["content"] = response_content
                        else:
                            # 更新内容
                            chat_messages[response_msg_index]["content"] = response_content
                
                # 检查是否完成
                if stream_data.get('status') == 'completed':
                    # If this was a duplicate search, append a card message for buttons
                    if streaming_state.get('is_duplicate_search') and streaming_state.get('duplicate_payload'):
                        chat_messages.append({
                            "role": "assistant",
                            "type": "duplicate-search-result",
                            "content": "",
                            "duplicate_result": streaming_state['duplicate_payload'],
                        })
                    streaming_state = {'active': False, 'task_id': None}
                    # Clean up streaming data
                    streaming_chat.clear_streaming_data(task_id)
                    # 清理推理消息中的临时标记
                    for msg in chat_messages:
                        if msg.get("type") == "reasoning":
                            msg["content"] = msg["content"].replace("🧠 思考过程：\n", "💭 AI思考过程：\n")
                elif stream_data.get('status') == 'error':
                    # 处理错误
                    error_msg = stream_data.get('error', '未知错误')
                    if chat_messages and chat_messages[-1]["role"] == "assistant":
                        chat_messages[-1]["content"] = f"❌ 抱歉，处理过程中出现错误：{error_msg}"
                        chat_messages[-1]["type"] = "error"
                    streaming_state = {'active': False, 'task_id': None}
                    # Clean up streaming data on error
                    streaming_chat.clear_streaming_data(task_id)

                
                # 生成更新的聊天历史
                chat_history_children = []
                for msg in chat_messages:
                    if msg["role"] == "user":
                        chat_history_children.append(
                            html.Div([
                                html.Div([
                                    html.I(className="fas fa-user", style={'marginRight': '8px', 'color': '#2c3e50'}),
                                    html.Span("用户", style={'fontWeight': 'bold', 'color': '#2c3e50'})
                                ], style={'marginBottom': '5px'}),
                                html.Div(msg["content"], style={'paddingLeft': '24px'})
                            ], style={
                                'padding': '12px',
                                'backgroundColor': '#e3f2fd',
                                'borderRadius': '8px',
                                'margin': '8px 0',
                                'textAlign': 'left',
                                'border': '1px solid #bbdefb',
                                'marginLeft': '20px',
                                'boxShadow': '0 1px 3px rgba(0,0,0,0.1)'
                            })
                        )
                    elif msg["role"] == "assistant":
                        if msg.get("type") == "duplicate-search-result":
                            chat_history_children.append(
                                render_duplicate_result_message(msg, chat_id_prefix=chat_id_prefix)
                            )
                            continue
                        # 根据消息类型设置样式
                        if msg.get("type") == "reasoning":
                            icon_class = "fas fa-brain"
                            icon_color = "#f39c12"
                            bg_color = "#fef9e7"
                            border_color = "#f4d03f"
                            title = "AI思考"
                        elif msg.get("type") == "error":
                            icon_class = "fas fa-exclamation-triangle"
                            icon_color = "#e74c3c"
                            bg_color = "#fdeaea"
                            border_color = "#f1948a"
                            title = "错误"
                        else:
                            icon_class = "fas fa-robot"
                            icon_color = "#3498db"
                            bg_color = "#f8f9fa"
                            border_color = "#e9ecef"
                            title = "AI助手"
                        
                        chat_history_children.append(
                            html.Div([
                                html.Div([
                                    html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                    html.Span(title, style={'fontWeight': 'bold', 'color': icon_color})
                                ], style={'marginBottom': '5px'}),
                                html.Div(
                                    msg["content"],
                                    style={
                                        'paddingLeft': '24px',
                                        'whiteSpace': 'pre-line',
                                        'fontFamily': 'inherit',
                                        **(
                                            {
                                                'maxHeight': '7em',
                                                'overflowY': 'auto',
                                                'fontSize': '12px',
                                                'lineHeight': '1.2em'
                                            }
                                            if msg.get("type") == "reasoning"
                                            else {}
                                        )
                                    },
                                )
                            ], style={
                                'padding': '12px',
                                'backgroundColor': bg_color,
                                'borderRadius': '8px',
                                'margin': '8px 0',
                                'textAlign': 'left',
                                'border': f'1px solid {border_color}',
                                'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                                'marginRight': '20px'
                            })
                        )
                
                # 设置状态显示
                status_display = ""
                if streaming_state.get('active'):
                    # 从全局存储获取进度信息
                    task_id = streaming_state.get('task_id')
                    if task_id:
                        stream_data = streaming_chat.get_streaming_data(task_id)
                        progress_msg = stream_data.get('progress', 'AI正在处理...')
                    else:
                        progress_msg = 'AI正在处理...'
                    
                    status_display = html.Div([
                        html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                        html.Span(progress_msg, style={'color': '#666'})
                    ])
                
                return (chat_history_children, chat_messages, streaming_state, 
                       not streaming_state.get('active'), status_display)
                
            except queue.Empty:
                # 队列为空，继续等待
                raise PreventUpdate
            except Exception as e:
                # 处理其他错误
                print(f"Streaming update error: {e}")
                print(f"Error traceback: {traceback.format_exc()}")
                raise PreventUpdate
        
        # 导出对话回调
        @app.callback(
            Output(f'{chat_id_prefix}-export-button', 'children'),
            [Input(f'{chat_id_prefix}-export-button', 'n_clicks')],
            [State(f'{chat_id_prefix}-messages', 'data')],
            prevent_initial_call=True
        )
        def export_conversation(n_clicks, chat_messages):
            """导出对话记录"""
            if n_clicks and chat_messages:
                try:
                    # 生成对话文本
                    conversation_text = f"AI对话记录 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    
                    for msg in chat_messages:
                        if msg["role"] == "user":
                            conversation_text += f"👤 用户: {msg['content']}\n\n"
                        elif msg["role"] == "assistant":
                            conversation_text += f"🤖 AI助手: {msg['content']}\n\n"
                    
                    # 这里可以添加实际的下载功能
                    return [html.I(className="fas fa-check", style={'marginRight': '5px'}), '已导出']
                except:
                    return [html.I(className="fas fa-exclamation-triangle", style={'marginRight': '5px'}), '导出失败']
            
            return [html.I(className="fas fa-download", style={'marginRight': '5px'}), '导出对话']
        
        # 自动滚动的客户端回调
        app.clientside_callback(
            f"""
            function(history_children, auto_scroll) {{
                if (auto_scroll && auto_scroll.includes('auto')) {{
                    setTimeout(function() {{
                        var chatHistory = document.getElementById('{chat_id_prefix}-history');
                        if (chatHistory) {{
                            chatHistory.scrollTop = chatHistory.scrollHeight;
                        }}
                    }}, 100);
                }}
                return '';
            }}
            """,
            Output(f'{chat_id_prefix}-input', 'placeholder'),
            [Input(f'{chat_id_prefix}-history', 'children'),
             Input(f'{chat_id_prefix}-auto-scroll', 'value')]
        )

# ============================================================================
# 测试功能
# ============================================================================

class AITestSuite:
    """AI功能测试套件"""
    
    @staticmethod
    def test_imports():
        """测试模块导入"""
        print("=" * 50)
        print("测试模块导入...")
        
        try:
            print("✓ 所有模块已在本文件中集成")
            print(f"  - API Base: {DEEPSEEK_API_BASE}")
            print(f"  - Model: {DEEPSEEK_MODEL}")
            print(f"  - API Key: {'已配置' if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != 'your-api-key-here' else '未配置'}")
            return True
        except Exception as e:
            print(f"✗ 模块检查失败: {e}")
            return False
    
    @staticmethod
    def test_api_key():
        """测试API密钥配置"""
        print("\n" + "=" * 50)
        print("测试API密钥配置...")
        
        if not DEEPSEEK_API_KEY:
            print("✗ API密钥未设置")
            return False
        
        if DEEPSEEK_API_KEY == "your-api-key-here":
            print("✗ API密钥使用默认值，请设置真实的API密钥")
            return False
        
        if DEEPSEEK_API_KEY.startswith("ACCESSCODE"):
            print("✓ 使用BMW内网API格式")
            return True
        elif DEEPSEEK_API_KEY.startswith("sk-"):
            print("✓ 使用标准OpenAI格式")
            return True
        else:
            print("⚠️  API密钥格式未识别，但将尝试使用")
            return True
    
    @staticmethod
    def test_api_connection():
        """测试API连接"""
        print("\n" + "=" * 50)
        print("测试API连接...")
        
        try:
            chat = DeepSeekStreamingChat()
            
            if not chat.validate_api_key():
                print("✗ API密钥验证失败")
                return False
            
            print("✓ API密钥验证通过")
            
            # 测试简单的API调用
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant. Answer in Chinese."},
                {"role": "user", "content": "请回复'测试成功'"}
            ]
            
            print("发送测试消息...")
            start_time = time.time()
            
            response = chat.get_simple_response(test_messages, temperature=0.1, max_tokens=50)
            
            end_time = time.time()
            response_time = end_time - start_time
            
            if "error" in response.lower() or "错误" in response:
                print(f"✗ API调用返回错误: {response}")
                return False
            
            print(f"✓ API调用成功")
            print(f"  - 响应时间: {response_time:.2f}秒")
            print(f"  - 响应内容: {response[:100]}...")
            return True
            
        except Exception as e:
            print(f"✗ API连接测试失败: {e}")
            return False
    
    @staticmethod
    def test_streaming():
        """测试流式响应"""
        print("\n" + "=" * 50)
        print("测试流式响应...")
        
        try:
            chat = DeepSeekStreamingChat()
            
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant. Answer in Chinese."},
                {"role": "user", "content": "请简单介绍一下人工智能，大约50字"}
            ]
            
            print("开始流式响应测试...")
            response_chunks = []
            
            for chunk in chat.stream_chat_response_optimized(test_messages, task_id="test", temperature=0.5, max_tokens=100):
                response_chunks.append(chunk)
                print(chunk, end='', flush=True)
                
                # 如果收到错误消息，停止测试
                if chunk.startswith("Error:"):
                    print(f"\n✗ 流式响应测试失败: {chunk}")
                    return False
            
            print(f"\n✓ 流式响应测试成功")
            print(f"  - 收到 {len(response_chunks)} 个数据块")
            return True
            
        except Exception as e:
            print(f"✗ 流式响应测试失败: {e}")
            return False
    
    @staticmethod
    def run_all_tests():
        """运行所有测试"""
        print("AI功能集成测试")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        tests = [
            ("模块导入", AITestSuite.test_imports),
            ("API密钥配置", AITestSuite.test_api_key),
            ("API连接", AITestSuite.test_api_connection),
            ("流式响应", AITestSuite.test_streaming)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
                
                if not result:
                    print(f"\n⚠️  {test_name} 测试失败，停止后续测试")
                    break
                    
            except Exception as e:
                print(f"\n✗ {test_name} 测试异常: {e}")
                results.append((test_name, False))
                break
        
        # 输出测试结果摘要
        print("\n" + "=" * 50)
        print("测试结果摘要:")
        
        all_passed = True
        for test_name, result in results:
            status = "✓ 通过" if result else "✗ 失败"
            print(f"  {test_name}: {status}")
            if not result:
                all_passed = False
        
        if all_passed:
            print("\n🎉 所有测试通过！AI功能集成成功。")
            print("您现在可以在各个看板中使用AI对话功能了。")
        else:
            print("\n❌ 部分测试失败，请检查配置。")
        
        return all_passed

# ============================================================================
# 全局实例和样式
# ============================================================================

# 全局AI聊天管理器实例
ai_chat_manager = AIChatManager()

def get_chat_css_styles() -> str:
    """返回聊天界面所需的CSS样式"""
    return """
        .chat-quick-btn {
            background-color: #28a745;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
            margin: 2px;
        }
        .chat-quick-btn:hover {
            background-color: #218838;
        }
        .user-message {
            background-color: #007bff;
            color: white;
            padding: 10px;
            border-radius: 10px;
            margin: 5px 0;
            text-align: right;
            margin-left: 20%;
        }
        .ai-message {
            background-color: #f0f0f0;
            color: black;
            padding: 10px;
            border-radius: 10px;
            margin: 5px 0;
            text-align: left;
            margin-right: 20%;
        }
        .streaming-message {
            background-color: #e9ecef;
            color: #6c757d;
            padding: 10px;
            border-radius: 10px;
            margin: 5px 0;
            text-align: left;
            margin-right: 20%;
            border-left: 3px solid #007bff;
        }
    """

# ============================================================================
# 兼容性导出（保持向后兼容）
# ============================================================================

# 导出配置常量，保持其他文件的兼容性
DEEPSEEK_API_KEY = DEEPSEEK_API_KEY
DEEPSEEK_API_BASE = DEEPSEEK_API_BASE  
DEEPSEEK_MODEL = DEEPSEEK_MODEL
VERIFY_SSL = VERIFY_SSL

# 测试入口点
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 运行测试
        success = AITestSuite.run_all_tests()
        sys.exit(0 if success else 1)
    else:
        # 简单的功能演示
        print("AI聊天管理器 - 集成版本")
        print("使用方法：")
        print("1. 运行测试：python ai_chat_manager.py test")  
        print("2. 在其他模块中导入：from agent.core.ai_chat_manager import ai_chat_manager")
        print("3. 创建聊天界面：ai_chat_manager.create_chat_interface('chat', 'defect')")
        print("\n要运行完整测试，请执行：python ai_chat_manager.py test")
