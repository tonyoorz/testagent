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

import dash
from dash import dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

from duplicate_issue_finder import extract_hints, get_or_build_index
from octane_db import default_db_path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging first before importing enhancement modules
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    logger.info("✅ Smart Context Generator loaded")
except ImportError as e:
    SMART_CONTEXT_AVAILABLE = False
    SmartContextGenerator = None
    logger.warning(f"⚠️ Smart Context Generator not available: {e}")

try:
    from agent.memory.enhanced_memory_system import create_memory_system, EnhancedMemorySystem
    MEMORY_SYSTEM_AVAILABLE = True
    logger.info("✅ Enhanced Memory System loaded")
except ImportError as e:
    MEMORY_SYSTEM_AVAILABLE = False
    EnhancedMemorySystem = None
    logger.warning(f"⚠️ Enhanced Memory System not available: {e}")

try:
    from agent.tools.smart_tool_selector import create_smart_tool_selector, SmartToolSelector
    SMART_TOOL_SELECTOR_AVAILABLE = True
    logger.info("✅ Smart Tool Selector loaded")
except ImportError as e:
    SMART_TOOL_SELECTOR_AVAILABLE = False
    SmartToolSelector = None
    logger.warning(f"⚠️ Smart Tool Selector not available: {e}")

try:
    from agent.core.explainable_agent import create_explainable_agent, ExplainableAgent
    EXPLAINABLE_AGENT_AVAILABLE = True
    logger.info("✅ Explainable Agent loaded")
except ImportError as e:
    EXPLAINABLE_AGENT_AVAILABLE = False
    ExplainableAgent = None
    logger.warning(f"⚠️ Explainable Agent not available: {e}")

try:
    from agent.core.conversation_entity_tracker import (
        create_conversation_entity_tracker,
        create_initial_conversation_state,
        ConversationEntityTracker,
        ConversationState
    )
    ENTITY_TRACKER_AVAILABLE = True
    logger.info("✅ Conversation Entity Tracker loaded")
except ImportError as e:
    ENTITY_TRACKER_AVAILABLE = False
    ConversationEntityTracker = None
    ConversationState = None
    logger.warning(f"⚠️ Conversation Entity Tracker not available: {e}")

try:
    from agent.core.hybrid_retriever import HybridRetriever, create_hybrid_retriever
    HYBRID_RETRIEVER_AVAILABLE = True
    logger.info("✅ Hybrid Retriever loaded")
except ImportError as e:
    HYBRID_RETRIEVER_AVAILABLE = False
    HybridRetriever = None
    logger.warning(f"⚠️ Hybrid Retriever not available: {e}")

try:
    from agent.core.confluence_retriever import ConfluenceRetriever, create_confluence_retriever
    CONFLUENCE_RETRIEVER_AVAILABLE = True
    logger.info("✅ Confluence Retriever loaded")
except ImportError as e:
    CONFLUENCE_RETRIEVER_AVAILABLE = False
    ConfluenceRetriever = None
    logger.warning(f"⚠️ Confluence Retriever not available: {e}")

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
    print("✅ 智能Agent系统已加载")
except ImportError as e:
    AGENT_AVAILABLE = False
    print(f"⚠️ 智能Agent系统不可用: {e}")
    IntelligentAgent = None


# ============================================================================
# 增强版 AI Chat Manager
# ============================================================================


class DifyWorkflowClient:
    """最小化 Dify Workflow 客户端（用于 RAG 模式）。"""

    def __init__(self, api_base: Optional[str] = None, api_key: Optional[str] = None):
        self.api_base = (api_base or os.environ.get("DIFY_API_BASE") or HARDCODED_DIFY_API_BASE).rstrip("/")
        self.api_key = api_key or os.environ.get("DIFY_API_KEY") or HARDCODED_DIFY_API_KEY
        self.query_key = os.environ.get("DIFY_WORKFLOW_QUERY_KEY") or DEFAULT_DIFY_WORKFLOW_QUERY_KEY
        self.context_key = os.environ.get("DIFY_WORKFLOW_CONTEXT_KEY") or DEFAULT_DIFY_WORKFLOW_CONTEXT_KEY
        self.user_prefix = os.environ.get("DIFY_USER_PREFIX") or DEFAULT_DIFY_WORKFLOW_USER_PREFIX
        self.timeout = float(os.environ.get("DIFY_TIMEOUT", "120"))
        self.enabled = bool(self.api_base and self.api_key)
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
            "response_mode": os.environ.get("DIFY_RESPONSE_MODE", "blocking"),
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
                          conversation_state: Optional[Dict] = None) -> Dict[str, Any]:
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
            result = self.intelligent_agent.process(resolved_question, data, conversation_history)

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

        # 构建界面
        interface = html.Div([
            # 会话与视图控制栏
            html.Div([
                html.Div([
                    dcc.Dropdown(
                        id=f'{chat_id_prefix}-session-selector',
                        options=[{'label': '当前会话', 'value': 'session-default'}],
                        value='session-default',
                        placeholder='选择历史会话',
                        clearable=False,
                        style={'minWidth': '260px', 'fontSize': '12px'}
                    ),
                    html.Button(
                        [html.I(className="fas fa-plus", style={'marginRight': '5px'}), '新会话'],
                        id=f'{chat_id_prefix}-new-session-btn',
                        n_clicks=0,
                        style={
                            'padding': '6px 10px',
                            'backgroundColor': '#2563eb',
                            'color': 'white',
                            'border': 'none',
                            'borderRadius': '6px',
                            'cursor': 'pointer',
                            'fontSize': '12px'
                        }
                    ),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'flexWrap': 'wrap'}),
                html.Div([
                    html.Button(
                        [html.I(className="fas fa-compress-alt", style={'marginRight': '5px'}), '紧凑排版'],
                        id=f'{chat_id_prefix}-compact-toggle-btn',
                        n_clicks=0,
                        style={
                            'padding': '6px 10px',
                            'backgroundColor': '#f3f4f6',
                            'color': '#374151',
                            'border': '1px solid #d1d5db',
                            'borderRadius': '6px',
                            'cursor': 'pointer',
                            'fontSize': '12px'
                        }
                    ),
                    html.Button(
                        [html.I(className="fas fa-expand", style={'marginRight': '5px'}), '放大全屏'],
                        id=f'{chat_id_prefix}-fullscreen-btn',
                        n_clicks=0,
                        style={
                            'padding': '6px 10px',
                            'backgroundColor': '#f3f4f6',
                            'color': '#374151',
                            'border': '1px solid #d1d5db',
                            'borderRadius': '6px',
                            'cursor': 'pointer',
                            'fontSize': '12px'
                        }
                    ),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'flexWrap': 'wrap'})
            ], style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'gap': '8px',
                'flexWrap': 'wrap',
                'padding': '6px 8px',
                'backgroundColor': '#f9fafb',
                'border': '1px solid #e5e7eb',
                'borderRadius': '8px'
            }),

            # 对话历史区域
            html.Div(
                id=f'{chat_id_prefix}-history',
                children=[
                    html.Div([
                        html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3498db'}),
                        html.Span(
                            f"您好！我是{self.assistant_name}。"
                            f"{'当前为 Skill（工具链）模式。' if default_mode == 'agent' else '当前为 Agent（数据库直读）模式。'}"
                        )
                    ], style={
                        'padding': '6px 9px',
                        'backgroundColor': '#f8f9fa',
                        'borderRadius': '8px',
                        'margin': '2px 0',
                        'border': '1px solid #e9ecef',
                        'fontSize': '12px',
                        'lineHeight': '1.35'
                    })
                ],
                style={
                    'flex': '1 1 auto',
                    'minHeight': '240px',
                    'height': 'calc(100vh - 360px)',
                    'overflowY': 'auto',
                    'border': '1px solid #ddd',
                    'padding': '8px',
                    'borderRadius': '8px',
                    'backgroundColor': '#fafafa'
                }
            ),

            # 对话模式和重复提票控制（放在对话框和发送区之间）
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
                        labelStyle={'display': 'inline-block', 'marginRight': '10px', 'fontSize': '12px'}
                    ),
                    html.Span(
                        "纯=不读本地 | RAG=Dify Chatflow | Confluence=知识空间检索 | Agent=数据库直读 | Skill=工具链",
                        style={'fontSize': '11px', 'color': '#6b7280', 'marginLeft': '6px'}
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
                        style={'fontSize': '11px', 'color': '#6b7280', 'marginLeft': '5px'}
                    )
                ], style={'display': 'flex', 'alignItems': 'center'})
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
                'padding': '6px 8px',
                'backgroundColor': '#f8f9fa',
                'border': '1px solid #e5e7eb',
                'borderRadius': '8px',
                'gap': '8px',
                'flexWrap': 'wrap'
            }),

            # 状态显示
            html.Div(
                id=f'{chat_id_prefix}-status',
                children=[],
                style={
                    'textAlign': 'center',
                    'marginTop': '6px',
                    'marginBottom': '6px',
                    'fontSize': '12px',
                    'color': '#666',
                    'minHeight': '16px'
                }
            ),

            # 输入区域
            html.Div([
                dcc.Input(
                    id=f'{chat_id_prefix}-input',
                    type='text',
                    placeholder='请输入您的问题...',
                    style={
                        'width': '84%',
                        'padding': '8px 10px',
                        'marginRight': '8px',
                        'borderRadius': '8px',
                        'border': '1px solid #d1d5db',
                        'fontSize': '12px'
                    },
                    value='',
                    persistence=False
                ),
                html.Button(
                    [html.I(className="fas fa-paper-plane", style={'marginRight': '5px'}), '发送'],
                    id=f'{chat_id_prefix}-send-button',
                    n_clicks=0,
                    style={
                        'width': '14%',
                        'padding': '8px 10px',
                        'backgroundColor': '#3498db',
                        'color': 'white',
                        'border': 'none',
                        'borderRadius': '8px',
                        'cursor': 'pointer',
                        'fontSize': '12px',
                        'fontWeight': 'bold'
                    }
                )
            ], style={'display': 'flex', 'alignItems': 'center', 'marginTop': '6px'}),

            # 预设问题
            html.Div([
                html.P("快速提问：", style={'fontSize': '12px', 'margin': '6px 0 3px 0', 'color': '#666'}),
                html.Div(
                    preset_buttons,
                    style={
                        'display': 'flex',
                        'gap': '6px',
                        'flexWrap': 'wrap',
                        'justifyContent': 'center'
                    }
                )
            ], style={'marginTop': '8px'}),

            # 控制面板
            html.Div([
                html.Div([
                    html.Label([
                        dcc.Checklist(
                            id=f'{chat_id_prefix}-show-reasoning',
                            options=[{'label': ' 显示AI思考过程', 'value': 'show'}],
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
        ], id=f'{chat_id_prefix}-container', style={
            'width': '100%',
            'height': 'calc(100vh - 120px)',
            'minHeight': '520px',
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '6px',
            'padding': '10px',
            'boxSizing': 'border-box'
        })

        return interface

    def create_enhanced_chat_stores(self, chat_id_prefix: str = 'chat') -> List[dcc.Store]:
        """创建增强版聊天存储组件"""
        # Initialize conversation state if entity tracker is available
        initial_conversation_state = {}
        if ENTITY_TRACKER_AVAILABLE and create_initial_conversation_state:
            try:
                initial_state = create_initial_conversation_state()
                initial_conversation_state = initial_state.to_dict()
            except Exception as e:
                logger.warning(f"Failed to create initial conversation state: {e}")

        now_ts = int(time.time())
        default_session_id = 'session-default'
        default_sessions = {
            'sessions': [
                {
                    'id': default_session_id,
                    'title': '当前会话',
                    'messages': [],
                    'updated_at': now_ts,
                }
            ]
        }

        stores = [
            dcc.Store(id=f'{chat_id_prefix}-messages', data=[], storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-use-agent-state', data={'use_agent': self.use_agent}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-agent-results', data={}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-known-issue-state', data={'enabled': False}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-streaming-state', data={'active': False, 'task_id': None}, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-conversation-state', data=initial_conversation_state, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-chat-sessions', data=default_sessions, storage_type='local'),
            dcc.Store(id=f'{chat_id_prefix}-active-session-id', data=default_session_id, storage_type='session'),
            dcc.Store(id=f'{chat_id_prefix}-ui-state', data={'fullscreen': False, 'compact': True}, storage_type='session'),
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

        def _is_compact(ui_state: Optional[Dict[str, Any]]) -> bool:
            if not isinstance(ui_state, dict):
                return True
            return bool(ui_state.get('compact', True))

        def render_chat_history(chat_messages: List[Dict[str, Any]], compact: bool = True):
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
                    bubble_padding = '8px 10px' if compact else '12px'
                    bubble_margin = '4px 0' if compact else '8px 0'
                    msg_font = '12px' if compact else '13px'
                    chat_history_children.append(
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-user", style={'marginRight': '8px', 'color': '#2c3e50'}),
                                html.Span("您", style={'fontWeight': 'bold', 'color': '#2c3e50'})
                            ], style={'marginBottom': '5px'}),
                            html.Div(msg.get("content", ""), style={'paddingLeft': '20px', 'fontSize': msg_font, 'lineHeight': '1.4'})
                        ], style={
                            'padding': bubble_padding,
                            'backgroundColor': '#e3f2fd',
                            'borderRadius': '8px',
                            'margin': bubble_margin,
                            'border': '1px solid #bbdefb',
                            'marginLeft': '8px'
                        })
                    )
                elif msg.get("role") == "assistant":
                    msg_type = msg.get("type")
                    if msg_type == "reasoning":
                        icon_class = "fas fa-brain"
                        icon_color = "#f39c12"
                        bg_color = "#fef9e7"
                        border_color = "#f4d03f"
                        title = "AI思考"
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
                        'paddingLeft': '20px',
                        'whiteSpace': 'pre-line',
                        'fontSize': '12px' if compact else '13px',
                        'lineHeight': '1.4'
                    }
                    if msg_type == "reasoning":
                        content_style.update({
                            'maxHeight': '7em',
                            'overflowY': 'auto',
                            'fontSize': '12px',
                            'lineHeight': '1.2em'
                        })

                    chat_history_children.append(
                        html.Div([
                            html.Div([
                                html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                html.Span(title, style={'fontWeight': 'bold', 'color': icon_color})
                            ], style={'marginBottom': '5px'}),
                            html.Div(msg.get("content", ""), style=content_style)
                        ], style={
                            'padding': '8px 10px' if compact else '12px',
                            'backgroundColor': bg_color,
                            'borderRadius': '8px',
                            'margin': '4px 0' if compact else '8px 0',
                            'border': f'1px solid {border_color}',
                            'marginRight': '8px'
                        })
                    )
            return chat_history_children

        def _session_title_from_messages(messages: List[Dict[str, Any]]) -> str:
            for msg in messages or []:
                if msg.get('role') == 'user':
                    t = str(msg.get('content') or '').strip()
                    if t:
                        return t[:24]
            return '新会话'

        def _session_options(sessions_data: Dict[str, Any]) -> List[Dict[str, str]]:
            sessions = list((sessions_data or {}).get('sessions') or [])
            # new -> old ordering
            sessions = sorted(sessions, key=lambda s: int(s.get('updated_at') or 0), reverse=True)
            return [
                {
                    'label': str(s.get('title') or '会话'),
                    'value': str(s.get('id') or ''),
                }
                for s in sessions if s.get('id')
            ]

        def _build_container_style(ui_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            fullscreen = bool((ui_state or {}).get('fullscreen', False))
            if fullscreen:
                try:
                    left_px = int(os.getenv('CHAT_FULLSCREEN_LEFT_PX', '300'))
                except Exception:
                    left_px = 300
                return {
                    'position': 'fixed',
                    'top': '8px',
                    'right': '8px',
                    'bottom': '8px',
                    'left': f'{left_px}px',
                    'zIndex': 2000,
                    'backgroundColor': '#ffffff',
                    'border': '1px solid #d1d5db',
                    'borderRadius': '10px',
                    'boxShadow': '0 8px 24px rgba(0,0,0,0.16)',
                    'display': 'flex',
                    'flexDirection': 'column',
                    'gap': '6px',
                    'padding': '10px',
                    'boxSizing': 'border-box'
                }

            return {
                'width': '100%',
                'height': 'calc(100vh - 120px)',
                'minHeight': '520px',
                'display': 'flex',
                'flexDirection': 'column',
                'gap': '6px',
                'padding': '10px',
                'boxSizing': 'border-box'
            }

        def _build_history_style(ui_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            fullscreen = bool((ui_state or {}).get('fullscreen', False))
            compact = _is_compact(ui_state)
            return {
                'flex': '1 1 auto',
                'minHeight': '240px' if compact else '220px',
                'height': 'calc(100vh - 200px)' if fullscreen else 'calc(100vh - 360px)',
                'overflowY': 'auto',
                'border': '1px solid #ddd',
                'padding': '8px' if compact else '10px',
                'borderRadius': '8px',
                'backgroundColor': '#fafafa'
            }

        @app.callback(
            [Output(f'{chat_id_prefix}-chat-sessions', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-session-selector', 'options', allow_duplicate=True),
             Output(f'{chat_id_prefix}-session-selector', 'value', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-messages', 'data')],
            [State(f'{chat_id_prefix}-chat-sessions', 'data'),
             State(f'{chat_id_prefix}-active-session-id', 'data')],
            prevent_initial_call=True
        )
        def sync_active_session(messages, sessions_data, active_session_id):
            sessions_data = sessions_data or {'sessions': []}
            sessions = list(sessions_data.get('sessions') or [])
            sid = str(active_session_id or '').strip()
            if not sid:
                return dash.no_update, dash.no_update, dash.no_update

            updated = False
            now_ts = int(time.time())
            for s in sessions:
                if str(s.get('id') or '') == sid:
                    s['messages'] = _trim_chat_messages(messages or [])
                    s['updated_at'] = now_ts
                    s['title'] = _session_title_from_messages(s.get('messages') or [])
                    updated = True
                    break

            if not updated:
                sessions.append({
                    'id': sid,
                    'title': _session_title_from_messages(messages or []),
                    'messages': _trim_chat_messages(messages or []),
                    'updated_at': now_ts,
                })

            data = {'sessions': sessions}
            options = _session_options(data)
            return data, options, sid

        @app.callback(
            [Output(f'{chat_id_prefix}-messages', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-active-session-id', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-chat-sessions', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-session-selector', 'options', allow_duplicate=True),
             Output(f'{chat_id_prefix}-session-selector', 'value', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-new-session-btn', 'n_clicks'),
             Input(f'{chat_id_prefix}-session-selector', 'value')],
            [State(f'{chat_id_prefix}-chat-sessions', 'data'),
             State(f'{chat_id_prefix}-active-session-id', 'data')],
            prevent_initial_call=True
        )
        def handle_session_switch(new_session_clicks, selected_session_id, sessions_data, active_session_id):
            sessions_data = sessions_data or {'sessions': []}
            sessions = list(sessions_data.get('sessions') or [])
            ctx = callback_context
            if not ctx.triggered:
                raise PreventUpdate

            prop_id = ctx.triggered[0]['prop_id']
            now_ts = int(time.time())

            if prop_id == f'{chat_id_prefix}-new-session-btn.n_clicks':
                sid = f'session-{int(time.time() * 1000)}'
                sessions.append({'id': sid, 'title': '新会话', 'messages': [], 'updated_at': now_ts})
                data = {'sessions': sessions}
                options = _session_options(data)
                return [], sid, data, options, sid

            sid = str(selected_session_id or '').strip()
            if not sid:
                raise PreventUpdate

            for s in sessions:
                if str(s.get('id') or '') == sid:
                    data = {'sessions': sessions}
                    options = _session_options(data)
                    return _trim_chat_messages(s.get('messages') or []), sid, data, options, sid

            raise PreventUpdate

        @app.callback(
            [Output(f'{chat_id_prefix}-container', 'style', allow_duplicate=True),
             Output(f'{chat_id_prefix}-history', 'style', allow_duplicate=True),
             Output(f'{chat_id_prefix}-fullscreen-btn', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-compact-toggle-btn', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-ui-state', 'data', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-fullscreen-btn', 'n_clicks'),
             Input(f'{chat_id_prefix}-compact-toggle-btn', 'n_clicks')],
            [State(f'{chat_id_prefix}-ui-state', 'data')],
            prevent_initial_call=True
        )
        def toggle_ui_modes(fullscreen_clicks, compact_clicks, ui_state):
            ui_state = dict(ui_state or {'fullscreen': False, 'compact': True})
            ctx = callback_context
            if not ctx.triggered:
                raise PreventUpdate
            prop_id = ctx.triggered[0]['prop_id']

            if prop_id == f'{chat_id_prefix}-fullscreen-btn.n_clicks':
                ui_state['fullscreen'] = not bool(ui_state.get('fullscreen', False))
            elif prop_id == f'{chat_id_prefix}-compact-toggle-btn.n_clicks':
                ui_state['compact'] = not bool(ui_state.get('compact', True))

            fullscreen_btn_text = (
                [html.I(className="fas fa-compress", style={'marginRight': '5px'}), '退出全屏']
                if ui_state.get('fullscreen') else
                [html.I(className="fas fa-expand", style={'marginRight': '5px'}), '放大全屏']
            )
            compact_btn_text = (
                [html.I(className="fas fa-compress-alt", style={'marginRight': '5px'}), '紧凑排版']
                if ui_state.get('compact', True) else
                [html.I(className="fas fa-text-height", style={'marginRight': '5px'}), '舒适排版']
            )
            return _build_container_style(ui_state), _build_history_style(ui_state), fullscreen_btn_text, compact_btn_text, ui_state

        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-messages', 'data'),
             Input(f'{chat_id_prefix}-ui-state', 'data')],
            prevent_initial_call=True
        )
        def rerender_history_on_session_switch(messages, ui_state):
            compact = _is_compact(ui_state)
            if not messages:
                return [[
                    html.Div([
                        html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3498db'}),
                        html.Span(f"您好！我是{self.assistant_name}。可以从历史会话继续，或新建会话。")
                    ], style={
                        'padding': '6px 9px',
                        'backgroundColor': '#f8f9fa',
                        'borderRadius': '8px',
                        'margin': '2px 0',
                        'border': '1px solid #e9ecef',
                        'fontSize': '12px',
                        'lineHeight': '1.35'
                    })
                ]]
            return [render_chat_history(messages, compact=compact)]

        def start_agent_streaming(task_id: str, question: str, current_data: Any, conversation_history: List[Dict[str, Any]]):
            def worker():
                heartbeat_running = {"on": True}

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
                        streaming_data.setdefault(task_id, {
                            'status': 'processing',
                            'reasoning': '',
                            'response': '',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'progress': '智能Agent正在分析数据...',
                            'chunk_buffer': '',
                            'last_update': time.time()
                        })
                        streaming_data[task_id]['reasoning'] = "初始化: 准备数据与上下文"

                    with streaming_lock:
                        streaming_data[task_id]['reasoning'] = "处理中: 规划任务与执行工具"
                        streaming_data[task_id]['last_update'] = time.time()

                    result = self.process_with_agent(question, current_data, conversation_history)
                    if not result.get('success'):
                        raise RuntimeError(result.get('text') or result.get('error') or "智能Agent执行失败")

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
                        with streaming_lock:
                            streaming_data[task_id]['reasoning'] = reasoning_text
                            streaming_data[task_id]['last_update'] = time.time()

                    formatted = self._format_agent_message(
                        result.get('text', ''),
                        result.get('tools_used', []),
                        result.get('insights', [])
                    )

                    chunk_size = 60
                    for end in range(0, len(formatted), chunk_size):
                        partial = formatted[:end + chunk_size]
                        with streaming_lock:
                            streaming_data[task_id]['status'] = 'processing'
                            streaming_data[task_id]['response'] = partial
                            streaming_data[task_id]['progress'] = '智能Agent正在输出...'
                            streaming_data[task_id]['last_update'] = time.time()
                        time.sleep(0.05)

                    with streaming_lock:
                        streaming_data[task_id]['status'] = 'completed'
                        streaming_data[task_id]['progress'] = '完成'
                        streaming_data[task_id]['last_update'] = time.time()

                except Exception as e:
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
                                chat_mode: str = "summary"):
            # pure 模式用于直连LLM验证，不做数据库摘要兜底。
            if chat_mode != "pure" and not self._has_data(current_data):
                db_summary = _build_db_profile_summary(question)
                if db_summary:
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
                    if msg.get('type') in {'stream_response', 'reasoning'}:
                        continue
                    messages.append({"role": msg['role'], "content": content})
            messages.append({"role": "user", "content": question})

            self.chatbot.start_optimized_streaming_thread(
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

        def _guess_target_table(question_text: str) -> str:
            q = (question_text or "").lower()
            if any(k in q for k in ["manual run", "testrun", "测试执行", "测试运行"]):
                return "octane_manual_runs"
            if any(k in q for k in ["history", "历史", "阶段变化", "phase"]):
                return "octane_defect_histories"
            return "octane_defects"

        def _stream_text_response(task_id: str, text: str, progress_text: str = '正在输出结果...'):
            chunk_size = 90
            content = str(text or "").strip()
            for end in range(0, len(content), chunk_size):
                partial = content[:end + chunk_size]
                with streaming_lock:
                    streaming_data[task_id]['status'] = 'processing'
                    streaming_data[task_id]['response'] = partial
                    streaming_data[task_id]['progress'] = progress_text
                    streaming_data[task_id]['last_update'] = time.time()
                time.sleep(0.02)
            with streaming_lock:
                streaming_data[task_id]['status'] = 'completed'
                streaming_data[task_id]['progress'] = '完成'
                streaming_data[task_id]['last_update'] = time.time()

        def _safe_chat_completion(task_id: str, messages: List[Dict[str, str]], temperature: float,
                                  max_tokens: int, stage_text: str) -> str:
            """调用LLM时做容错，避免摘要模式因单次请求异常而整体失败。"""
            if not self.chatbot or not hasattr(self.chatbot, 'chat_completion'):
                return ""

            try:
                return str(self.chatbot.chat_completion(messages, temperature=temperature, max_tokens=max_tokens) or "").strip()
            except Exception as e:
                logger.warning(f"摘要模式LLM调用失败({stage_text}): {e}")
                with streaming_lock:
                    streaming_data.setdefault(task_id, {})
                    streaming_data[task_id]['status'] = 'processing'
                    streaming_data[task_id]['progress'] = f'{stage_text}失败，正在降级...'
                    streaming_data[task_id]['llm_error'] = f"{stage_text}: {e}"
                    streaming_data[task_id]['last_update'] = time.time()
                return ""

        def _extract_query_hints(question: str, columns: List[str]) -> Dict[str, Any]:
            q = str(question or "")
            ql = q.lower()

            # 识别可能的项目/团队关键字（例如 IDCEVO）
            en_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", q)
            zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,8}", q)
            entity_tokens = []
            stop_words = {
                "aida", "ticket", "topissue", "issue", "defect", "summary", "agent", "sqlite",
                "tester", "reporter", "owner", "team", "project", "status", "phase", "query"
            }
            for t in en_tokens:
                tl = t.lower()
                if tl in stop_words:
                    continue
                if len(tl) <= 1:
                    continue
                entity_tokens.append(t)
            for t in zh_tokens:
                if any(k in t for k in ["提票", "情况", "如何", "分析", "查询", "统计", "数据", "测试", "缺陷", "团队", "项目"]):
                    continue
                entity_tokens.append(t)

            # 去重并限制长度，避免生成过长 where 子句
            dedup_tokens = []
            seen = set()
            for t in entity_tokens:
                tl = str(t).strip().lower()
                if not tl or tl in seen:
                    continue
                seen.add(tl)
                dedup_tokens.append(str(t).strip())

            wants_aida_dist = any(k in ql for k in ["aida", "分布", "distribution", "领域", "模块"])
            wants_topissue = any(k in ql for k in ["topissue", "top issue", "高风险", "风险", "严重"])
            wants_detail = any(k in ql for k in ["详情", "详细", "detail", "ticket", "列表", "哪些"])
            wants_tester = any(k in ql for k in ["提票", "提单", "报缺陷", "提交人", "报告人", "发现人", "测试员", "测试人员", "tester", "reporter", "found by", "found_by", "detected by", "detected_by"])

            return {
                "entity_tokens": dedup_tokens[:6],
                "wants_aida_dist": wants_aida_dist,
                "wants_topissue": wants_topissue,
                "wants_detail": wants_detail,
                "wants_tester": wants_tester,
                "columns": set(columns or []),
            }

        def _build_deterministic_sql(question: str, table_name: str, columns: List[str]) -> str:
            """规则化SQL生成：摘要模式默认走这里，避免LLM生成SQL卡住。"""
            hints = _extract_query_hints(question, columns)
            cols = hints["columns"]

            def _esc_like(token: str) -> str:
                return str(token or "").replace("'", "''")

            select_cols = []
            for c in [
                "defect_id", "id", "name", "project", "tproject", "team", "ecu",
                "aida_english", "top_aida", "status_phase", "severity_group",
                "tester", "detected_by", "reporter", "found_by", "author_name", "owner",
                "topissue_display", "creation_time", "last_modified"
            ]:
                if c in cols:
                    select_cols.append(c)

            if not select_cols:
                select_cols = list(columns[:10]) if columns else ["*"]

            where_parts = []

            if hints["wants_topissue"]:
                if "topissue_display" in cols:
                    where_parts.append("topissue_display IS NOT NULL AND CAST(topissue_display AS TEXT) <> ''")
                elif "severity_group" in cols:
                    where_parts.append("LOWER(CAST(severity_group AS TEXT)) IN ('critical','high','s1','s2')")

            if hints["entity_tokens"]:
                person_fields = [c for c in ["tester", "detected_by", "reporter", "found_by", "author_name", "owner"] if c in cols]
                generic_fields = [c for c in ["project", "tproject", "team", "ecu", "name"] if c in cols]
                searchable = person_fields if (hints.get("wants_tester") and person_fields) else (person_fields + generic_fields if person_fields else generic_fields)
                for tok in hints["entity_tokens"]:
                    if searchable:
                        safe_tok = _esc_like(tok)
                        like_group = " OR ".join([f"LOWER(CAST({c} AS TEXT)) LIKE LOWER('%{safe_tok}%')" for c in searchable])
                        where_parts.append(f"({like_group})")

            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            order_col = "creation_time" if "creation_time" in cols else "last_modified" if "last_modified" in cols else None
            order_sql = f" ORDER BY {order_col} DESC" if order_col else ""

            return f'SELECT {", ".join(select_cols)} FROM "{table_name}"{where_sql}{order_sql} LIMIT 120'

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
        ) -> str:
            row_count = len(rows or [])
            conclusion = str(llm_answer or "").strip() or "暂无可用结论。"
            safe_total = int(total_count) if isinstance(total_count, int) and total_count >= 0 else None
            lines: List[str] = [
                "[结论]",
                conclusion,
                "",
                "[关键数字]",
                f"- 总命中记录: {safe_total if safe_total is not None else row_count}",
                f"- 返回样本: {row_count}",
                f"- 数据表: {table_name or '-'}",
                f"- SQL: {sql_used or '-'}",
                f"- SQL模式: {mode or '-'}",
            ]

            explain_block = _format_business_explanation_block(explanation)
            if explain_block:
                lines.extend(["", explain_block])

            cautions: List[str] = []
            if row_count == 0:
                cautions.append("当前查询命中为0，可尝试放宽时间范围、状态或模块筛选")
            if (safe_total is not None) and (safe_total > row_count):
                cautions.append(f"为保证响应速度，回答详情按样本返回（上限 {int(sample_limit)} 条），已提供全量命中总数")
            if fallback_reason:
                cautions.append(f"本地兜底原因: {fallback_reason}")
            if cautions:
                lines.append("")
                lines.append("[口径提醒]")
                for c in cautions:
                    lines.append(f"- {c}")

            return "\n".join(lines)

        def start_db_summary_streaming(task_id: str, question: str, conversation_history: List[Dict[str, Any]]):
            """摘要模式：优先走 Agent 统一 SQL 工具链，再按需降级。"""
            def worker():
                target_table = ""
                sql_clean = ""
                out_rows: List[Dict[str, Any]] = []
                total_count: Optional[int] = None
                business_explanation: Dict[str, Any] = {}
                stage = "init"
                summary_sql_mode = "agent"
                summary_row_limit = max(1, int((os.getenv("CHAT_SUMMARY_ROW_LIMIT", "120") or "120").strip() or "120"))
                started_at = time.time()
                tool_executor = getattr(self.intelligent_agent, 'tool_executor', None) if self.intelligent_agent else None
                tool_sql_succeeded = False
                local_fallback_reason = ""
                failure_category = ""
                execution_path: List[str] = []
                stage_events: List[str] = []

                def _unwrap_sql_for_count(sql_text: str, table_name: str) -> str:
                    s = str(sql_text or "").strip().rstrip(";")
                    if not s:
                        return f'SELECT * FROM "{table_name}"'
                    # run_sqlite_query 会把 SQL 包成: SELECT * FROM (<inner>) AS _q LIMIT N
                    m = re.match(r"^\s*SELECT\s+\*\s+FROM\s+\((.*)\)\s+AS\s+_q\s+LIMIT\s+\d+\s*$", s, flags=re.IGNORECASE | re.DOTALL)
                    if m:
                        s = str(m.group(1) or "").strip()
                    s = re.sub(r"\s+LIMIT\s+\d+\s*$", "", s, flags=re.IGNORECASE)
                    if not re.match(r"^\s*(select|with)\b", s, flags=re.IGNORECASE):
                        return f'SELECT * FROM "{table_name}"'
                    return s

                def _compute_total_count(db_path: str, table_name: str, sql_text: str) -> Optional[int]:
                    base_sql = _unwrap_sql_for_count(sql_text, table_name)
                    count_sql = f"SELECT COUNT(*) AS total_count FROM ({base_sql}) AS _cnt"

                    if tool_executor:
                        try:
                            c_out = tool_executor.execute_tool("run_sqlite_query", None, sql=count_sql, limit=1)
                            if isinstance(c_out, dict) and c_out.get("success") is True:
                                rs = c_out.get("result") or {}
                                items = rs.get("rows") or []
                                if isinstance(items, list) and items and isinstance(items[0], dict):
                                    v = items[0].get("total_count")
                                    if v is not None:
                                        return int(v)
                        except Exception:
                            pass

                    try:
                        conn3 = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                        cur3 = conn3.cursor()
                        try:
                            cur3.execute("PRAGMA query_only = ON")
                        except Exception:
                            pass
                        cur3.execute(count_sql)
                        one = cur3.fetchone()
                        conn3.close()
                        if one is not None:
                            return int(one[0])
                    except Exception:
                        return None
                    return None

                def _mark_stage(new_stage: str) -> None:
                    nonlocal stage
                    stage = str(new_stage or "")
                    stage_events.append(f"{stage}@{int((time.time() - started_at) * 1000)}ms")

                try:
                    _mark_stage("open_db")
                    db_path = os.getenv("AGENT_SQLITE_DB_PATH") or default_db_path()
                    if not db_path or not os.path.exists(db_path):
                        raise RuntimeError(f"数据库文件不存在: {db_path}")

                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        streaming_data[task_id]['status'] = 'processing'
                        streaming_data[task_id]['progress'] = '正在读取数据库结构...'
                        streaming_data[task_id]['last_update'] = time.time()

                    _mark_stage("load_schema")
                    target_table = _guess_target_table(question)
                    all_tables: List[str] = []
                    col_preview: List[str] = []

                    if tool_executor:
                        execution_path.append("schema:tool")
                        try:
                            schema_out = tool_executor.execute_tool("get_sqlite_schema", None, table="")
                            schema_result = schema_out.get("result") if isinstance(schema_out, dict) and schema_out.get("success") is True else {}
                            table_map = (schema_result or {}).get("tables") or {}
                            all_tables = [str(t) for t in table_map.keys()]
                            if all_tables and target_table not in all_tables:
                                target_table = all_tables[0]
                            if target_table in table_map and isinstance(table_map.get(target_table), list):
                                col_preview = [str((c or {}).get("name") or "") for c in table_map.get(target_table) if isinstance(c, dict)]
                                col_preview = [c for c in col_preview if c][:30]
                        except Exception:
                            all_tables = []
                            col_preview = []
                            local_fallback_reason = "schema工具失败"

                    if not all_tables or not col_preview:
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
                        col_preview = columns[:30]
                        conn.close()

                    # 摘要模式优先走统一工具链，避免与Agent模式SQL行为漂移。
                    with streaming_lock:
                        streaming_data[task_id]['progress'] = '正在生成数据库查询(工具链优先)...'
                        streaming_data[task_id]['last_update'] = time.time()

                    _mark_stage("generate_sql")
                    summary_sql_mode = (os.getenv("CHAT_SUMMARY_SQL_MODE") or "agent").strip().lower()
                    sql = ""
                    rows: List[Any] = []

                    # 优先复用统一工具链，避免摘要模式与 Agent 模式出现两套SQL行为漂移。
                    use_agent_sql = (os.getenv("CHAT_SUMMARY_SQL_USE_AGENT", "1") or "1").strip().lower() not in {"0", "false", "no"}
                    if use_agent_sql and tool_executor:
                        execution_path.append("sql_generate:tool")
                        try:
                            with streaming_lock:
                                streaming_data[task_id]['progress'] = '正在通过Agent工具链生成SQL...'
                                streaming_data[task_id]['last_update'] = time.time()
                            agent_sql_out = tool_executor.execute_tool(
                                "query_sqlite_with_fix",
                                None,
                                question=question,
                                limit=summary_row_limit,
                                table=target_table,
                            )
                            if isinstance(agent_sql_out, dict) and agent_sql_out.get("success") is True:
                                rs = agent_sql_out.get("result") or {}
                                sql = str(rs.get("generated_sql") or rs.get("sql") or "").strip()
                                items = rs.get("rows") or []
                                if isinstance(items, list):
                                    out_rows = [r for r in items[:summary_row_limit] if isinstance(r, dict)]
                                exp = rs.get("business_explanation")
                                if isinstance(exp, dict):
                                    business_explanation = exp
                                tool_sql_succeeded = True
                                summary_sql_mode = "agent"
                        except Exception:
                            local_fallback_reason = "query_sqlite_with_fix异常"
                            failure_category = _classify_summary_failure(stage, local_fallback_reason)
                            pass

                    if not out_rows and not sql:
                        execution_path.append("sql_generate:deterministic")
                        summary_sql_mode = "deterministic"
                        sql = _build_deterministic_sql(question=question, table_name=target_table, columns=col_preview)

                    sql_clean = sql.strip().rstrip(';')
                    if not sql_clean:
                        sql_clean = f'SELECT * FROM "{target_table}" LIMIT 50'
                    if not re.match(r"^\s*(select|with)\b", sql_clean, flags=re.IGNORECASE):
                        sql_clean = f'SELECT * FROM "{target_table}" LIMIT 50'
                    if re.search(r"\b(insert|update|delete|drop|alter|truncate|attach|detach|pragma\s+write)\b", sql_clean, flags=re.IGNORECASE):
                        sql_clean = f'SELECT * FROM "{target_table}" LIMIT 50'

                    with streaming_lock:
                        streaming_data[task_id]['progress'] = '正在执行数据库查询...'
                        streaming_data[task_id]['last_update'] = time.time()

                    if not out_rows:
                        _mark_stage("run_sql_tool")
                        if tool_executor:
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
                        # 本地最终兜底仍保留，但也走只读连接，不复用上游游标。
                        try:
                            conn2 = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                            conn2.row_factory = sqlite3.Row
                            cur2 = conn2.cursor()
                            try:
                                cur2.execute("PRAGMA query_only = ON")
                            except Exception:
                                pass
                            try:
                                cur2.execute(sql_clean)
                                rows = cur2.fetchmany(200)
                            except Exception:
                                sql_clean = f'SELECT * FROM "{target_table}" LIMIT 50'
                                cur2.execute(sql_clean)
                                rows = cur2.fetchmany(200)
                            conn2.close()
                        except Exception:
                            rows = []

                        out_rows = []
                        for r in rows[:summary_row_limit]:
                            try:
                                d = dict(r) if r is not None else {}
                            except Exception:
                                d = {}
                            out_rows.append({k: d.get(k) for k in list(d.keys())[:18]})

                    total_count = _compute_total_count(db_path=db_path, table_name=target_table, sql_text=sql_clean)

                    with streaming_lock:
                        streaming_data[task_id]['progress'] = '正在生成回答...'
                        streaming_data[task_id]['last_update'] = time.time()

                    _mark_stage("generate_answer")
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
                            "rows": out_rows
                        }, ensure_ascii=False)}
                    ]
                    stage = "generate_answer"
                    answer = _safe_chat_completion(
                        task_id=task_id,
                        messages=ans_messages,
                        temperature=0.2,
                        max_tokens=1200,
                        stage_text='答案生成'
                    )

                    # 第一次失败时，自动降采样重试，减少上下文负载造成的失败概率。
                    if not answer:
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
                                "note": "compact_retry"
                            }, ensure_ascii=False)}
                        ]
                        answer = _safe_chat_completion(
                            task_id=task_id,
                            messages=retry_messages,
                            temperature=0.2,
                            max_tokens=800,
                            stage_text='答案生成重试'
                        )

                    if not answer:
                        llm_err = ""
                        with streaming_lock:
                            llm_err = str((streaming_data.get(task_id) or {}).get('llm_error') or "").strip()
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
                    )
                    elapsed_ms = int((time.time() - started_at) * 1000)
                    stage_timeline = " > ".join(stage_events)
                    execution_path_text = " > ".join(execution_path)
                    with streaming_lock:
                        streaming_data.setdefault(task_id, {})
                        summary_trace = {
                            'mode': summary_sql_mode,
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

                table_name = _guess_target_table(question_text)
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

        def start_duplicate_check_streaming(task_id: str, question: str, current_data: Any, conversation_history: List[Dict[str, Any]]):
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

            hints = extract_hints(question)
            index = get_or_build_index(cache_key=f"duplicate:{self.dashboard_type}", df=df)
            candidates = index.search(question, hints=hints, top_k=10)

            local_only = not getattr(self.chatbot, "client", None) and not getattr(self.chatbot, "backup_api_key", "")
            if local_only:
                best = max((c.score_1_10 for c in candidates), default=0)
                if best >= 8:
                    suggestion = "不建议提票"
                    reason = "与已有问题高度相似，建议优先合并/追加信息"
                elif best <= 6:
                    suggestion = "可以提票"
                    reason = "未发现高度相似的已知问题"
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

                formatted = "\n".join(lines).strip()
                chunk_size = 80
                for end in range(0, len(formatted), chunk_size):
                    partial = formatted[: end + chunk_size]
                    with streaming_lock:
                        streaming_data[task_id]['status'] = 'processing'
                        streaming_data[task_id]['response'] = partial
                        streaming_data[task_id]['progress'] = '正在输出结果...'
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

            system_prompt = f"""你是缺陷提票前置审查助手。你的任务是：根据用户的自然语言问题描述，在“候选缺陷列表”中找出最相似的已知问题，并给出是否建议提票的结论。\n\n规则：\n1) 只能基于提供的候选列表，不要编造不存在的ticket。\n2) 相似度评分使用 1-10（10=几乎同一个问题）。你可以参考候选里给定的 score_1_10，但如果你认为不合理可以小幅调整；最终输出仍需按 10→1 排序。\n3) 如果最高相似度 >= 8：结论默认“不建议提票”，建议合并到最相似票或补充复现信息后追踪。\n4) 如果最高相似度 <= 6：结论默认“可以提票”，并给出建议标题与必填信息清单。\n\n输出格式（必须使用以下结构）：\n【结论】\n- 建议：不建议提票 / 可以提票 / 需要补充信息后再判断\n- 依据：一句话说明\n\n【相似已知问题（按相似度降序）】\n- 10分：#id - 标题（project/pu，phase）\\n  匹配点：...\n- 9分：...\n\n【下一步】\n- 如果不建议提票：建议合并到哪一票，以及需要补充哪些信息。\n- 如果可以提票：建议标题、复现步骤、期望/实际、环境、日志/截图等。\n\n候选缺陷列表（JSON Lines）：\n{candidate_block}\n"""

            messages = [{"role": "system", "content": system_prompt}]
            for msg in (conversation_history or [])[-6:]:
                if msg.get('role') in ['user', 'assistant']:
                    content = str(msg.get('content', '')).strip()
                    if not content:
                        continue
                    if msg.get('type') in {'stream_response', 'reasoning'}:
                        continue
                    messages.append({"role": msg['role'], "content": content})
            messages.append({"role": "user", "content": question})

            self.chatbot.start_optimized_streaming_thread(
                messages,
                task_id=task_id,
                temperature=0.2,
                max_tokens=DEFAULT_MAX_TOKENS
            )

        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children'),
             Output(f'{chat_id_prefix}-input', 'value'),
             Output(f'{chat_id_prefix}-messages', 'data'),
             Output(f'{chat_id_prefix}-streaming-state', 'data'),
             Output(f'{chat_id_prefix}-update-interval', 'disabled'),
             Output(f'{chat_id_prefix}-status', 'children'),
             Output(f'{chat_id_prefix}-agent-results', 'data')],
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
               State(f'{chat_id_prefix}-ui-state', 'data')]
        )
        def handle_enhanced_chat(*args):
            send_clicks = args[0]
            input_submit = args[1]
            clear_clicks = args[2]
            preset_clicks = args[3:-7]
            input_value = args[-7]
            chat_messages = _trim_chat_messages(args[-6] or [])
            streaming_state = args[-5] or {'active': False, 'task_id': None}
            filtered_data = args[-4]
            chat_mode = (args[-3] or "summary")
            known_issues_checked = args[-2] or []
            ui_state = args[-1] if isinstance(args[-1], dict) else {}

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
                return [initial_message], "", [], {'active': False, 'task_id': None}, True, "", {}

            if streaming_state.get('active'):
                status_display = html.Div([
                    html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span("上一条消息正在生成中，请稍候…（可点击“清空”重置）", style={'color': '#666'})
                ])
                return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, status_display, dash.no_update

            use_known_issues = 'known' in (known_issues_checked or [])

            def _is_advanced_decision_query(text: str) -> bool:
                q = str(text or "").strip().lower()
                if not q:
                    return False
                keywords = [
                    "趋势", "trend", "风险", "risk", "预测", "predict", "策略", "strategy",
                    "建议", "recommend", "复盘", "retrospective", "恶化", "improve",
                    "下个版本", "next release", "测试重点", "质量趋势", "根因", "priority"
                ]
                return any(k in q for k in keywords)

            # 确定用户消息
            user_message = ""
            preset_questions = self.preset_questions.get(self.dashboard_type, self.preset_questions['general'])

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

            # 处理用户消息
            agent_results = {}
            status_display = ""
            prefer_agent_for_query = False

            if user_message:
                # 问候语快速路径：避免被分析型提示词放大为长篇数据说明。
                msg_norm = str(user_message or "").strip().lower()
                greeting_set = {"hi", "hello", "hey", "你好", "嗨", "哈喽", "在吗", "在么", "hi!", "hello!"}
                if msg_norm in greeting_set and len(msg_norm) <= 12:
                    chat_messages.append({"role": "user", "content": user_message})
                    chat_messages.append({
                        "role": "assistant",
                        "content": "你好，我在。你可以直接问我问题，或告诉我你想分析的范围。"
                    })
                    chat_messages = _trim_chat_messages(chat_messages)
                    chat_history_children = render_chat_history(chat_messages, compact=_is_compact(ui_state))
                    return chat_history_children, "", chat_messages, {'active': False, 'task_id': None}, True, "", {}

                # 添加用户消息
                chat_messages.append({"role": "user", "content": user_message})
                chat_messages = _trim_chat_messages(chat_messages)

                # 获取数据
                current_data: Any = pd.DataFrame()
                allow_local_data = (chat_mode in {"agent", "rag", "confluence"}) or use_known_issues
                if filtered_data and allow_local_data:
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
                prefer_agent_for_query = (
                    (not use_known_issues)
                    and (chat_mode == "agent")
                    and self.use_agent
                    and _is_advanced_decision_query(user_message)
                )
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
            with streaming_lock:
                streaming_data[task_id] = {
                    'status': 'processing',
                    'reasoning': '',
                    'response': '',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'progress': 'AI正在初始化...',
                    'chunk_buffer': '',
                    'last_update': time.time()
                }

            chat_messages.append({
                "role": "assistant",
                "content": "",
                "type": "stream_response",
                "task_id": task_id,
                "agent_used": bool((not use_known_issues) and ((chat_mode == "agent") or prefer_agent_for_query) and self.use_agent and self._has_data(current_data))
            })
            chat_messages = _trim_chat_messages(chat_messages)

            status_display = html.Div([
                html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                html.Span("AI正在思考...", style={'color': '#666'})
            ])

            if use_known_issues:
                with streaming_lock:
                    if task_id in streaming_data:
                        streaming_data[task_id]['progress'] = '正在检索已知问题...'
                start_duplicate_check_streaming(task_id, user_message, current_data, chat_messages)
            elif chat_mode == "rag":
                start_dify_streaming(task_id, user_message, current_data)
            elif chat_mode == "confluence":
                start_confluence_streaming(task_id, user_message, current_data)
            elif chat_mode == "summary":
                start_db_summary_streaming(task_id, user_message, chat_messages)
            elif ((chat_mode == "agent") or prefer_agent_for_query) and self.use_agent and self._has_data(current_data):
                start_agent_streaming(task_id, user_message, current_data, chat_messages)
            else:
                start_llm_streaming(task_id, user_message, current_data, chat_messages, chat_mode=chat_mode)

            streaming_state = {'active': True, 'task_id': task_id}

            chat_history_children = render_chat_history(chat_messages, compact=_is_compact(ui_state))
            interval_disabled = not streaming_state.get('active')
            return chat_history_children, "", chat_messages, streaming_state, interval_disabled, status_display, agent_results

        @app.callback(
            [Output(f'{chat_id_prefix}-history', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-messages', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-streaming-state', 'data', allow_duplicate=True),
             Output(f'{chat_id_prefix}-update-interval', 'disabled', allow_duplicate=True),
             Output(f'{chat_id_prefix}-status', 'children', allow_duplicate=True),
             Output(f'{chat_id_prefix}-agent-results', 'data', allow_duplicate=True)],
            [Input(f'{chat_id_prefix}-update-interval', 'n_intervals')],
            [State(f'{chat_id_prefix}-messages', 'data'),
             State(f'{chat_id_prefix}-streaming-state', 'data'),
             State(f'{chat_id_prefix}-show-reasoning', 'value'),
             State(f'{chat_id_prefix}-agent-results', 'data'),
             State(f'{chat_id_prefix}-ui-state', 'data')],
            prevent_initial_call=True
        )
        def update_streaming_response(n_intervals, chat_messages, streaming_state, show_reasoning, agent_results, ui_state):
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
                chat_history_children = render_chat_history(chat_messages, compact=_is_compact(ui_state))
                interval_disabled = True
                status_display = ""
                return chat_history_children, chat_messages, streaming_state, interval_disabled, status_display, agent_results

            max_stale_seconds = 300
            try:
                max_stale_seconds = int(os.getenv("CHAT_STREAMING_STALE_SECONDS", "300"))
            except Exception:
                max_stale_seconds = 300

            chat_messages = _trim_chat_messages(chat_messages or [])
            current_task_id = task_id

            def _tail_lines(text: str, max_lines: int = 5) -> str:
                raw_lines = (text or "").splitlines()
                tail = raw_lines[-max_lines:] if raw_lines else []
                return "\n".join(tail).strip()

            reasoning_content = stream_data.get('reasoning') or ''
            if reasoning_content and show_reasoning and 'show' in (show_reasoning or []):
                trimmed = _tail_lines(reasoning_content, 5)
                if trimmed:
                    reasoning_content = trimmed
                reasoning_index = -1
                for i in range(len(chat_messages) - 1, -1, -1):
                    if chat_messages[i].get('type') == 'reasoning' and chat_messages[i].get('task_id') == current_task_id:
                        reasoning_index = i
                        break
                if reasoning_index == -1:
                    chat_messages.append({
                        "role": "assistant",
                        "type": "reasoning",
                        "task_id": current_task_id,
                        "agent_used": False,
                        "content": f"💭 AI思考(最近5行)：\n{reasoning_content}"
                    })
                else:
                    chat_messages[reasoning_index]["content"] = f"💭 AI思考(最近5行)：\n{reasoning_content}"
                chat_messages = _trim_chat_messages(chat_messages)

            response_content = stream_data.get('response') or ''
            response_index = -1
            for i in range(len(chat_messages) - 1, -1, -1):
                if chat_messages[i].get('type') == 'stream_response' and chat_messages[i].get('task_id') == current_task_id:
                    response_index = i
                    break
            if response_index != -1:
                chat_messages[response_index]["content"] = response_content
            chat_messages = _trim_chat_messages(chat_messages)

            status = stream_data.get('status')
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

            if status == 'completed':
                streaming_state = {'active': False, 'task_id': None}
                # Clean up streaming data to prevent memory leak
                with streaming_lock:
                    if task_id in streaming_data:
                        del streaming_data[task_id]
                        logger.info(f"Cleaned up streaming data for task {task_id}")
                status_display = ""

            chat_history_children = render_chat_history(chat_messages, compact=_is_compact(ui_state))
            interval_disabled = not streaming_state.get('active')
            return chat_history_children, chat_messages, streaming_state, interval_disabled, status_display, agent_results

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
    print(f"✅ 增强版AI Chat Manager创建成功")
    print(f"   - 看板类型: {manager.dashboard_type}")
    print(f"   - Agent启用: {manager.use_agent}")
    print(f"   - 预设问题数: {len(manager.preset_questions[manager.dashboard_type])}")

    # 测试界面创建
    interface = manager.create_enhanced_chat_interface('test-chat')
    print(f"✅ 聊天界面创建成功")
