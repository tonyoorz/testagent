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
"""

import os
import sys
import json
import time
import logging
import threading
from typing import Dict, List, Any, Optional, Callable, Generator
from datetime import datetime
import pandas as pd
import io
import httpx

import dash
from dash import dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

from duplicate_issue_finder import extract_hints, get_or_build_index

# 导入原有的 AI Chat Manager 组件
try:
    from ai_chat_manager import (
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
    from intelligent_agent import (
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

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Dify Workflow 配置
# ============================================================================

HARDCODED_DIFY_API_BASE = "http://10.86.150.232/v1"
HARDCODED_DIFY_API_KEY = "app-YweK9LdWefjG11niKLtqTBV8"
DEFAULT_DIFY_WORKFLOW_QUERY_KEY = "query"
DEFAULT_DIFY_WORKFLOW_CONTEXT_KEY = "context"
DEFAULT_DIFY_WORKFLOW_USER_PREFIX = "preanalysis"


class DifyWorkflowClient:
    """最小化 Dify Workflow 客户端。"""

    def __init__(self, api_base: Optional[str] = None, api_key: Optional[str] = None):
        self.api_base = (api_base or os.environ.get("DIFY_API_BASE") or HARDCODED_DIFY_API_BASE).rstrip("/")
        self.api_key = api_key or os.environ.get("DIFY_API_KEY") or HARDCODED_DIFY_API_KEY
        self.query_key = os.environ.get("DIFY_WORKFLOW_QUERY_KEY") or DEFAULT_DIFY_WORKFLOW_QUERY_KEY
        self.context_key = os.environ.get("DIFY_WORKFLOW_CONTEXT_KEY") or DEFAULT_DIFY_WORKFLOW_CONTEXT_KEY
        self.user_prefix = os.environ.get("DIFY_USER_PREFIX") or DEFAULT_DIFY_WORKFLOW_USER_PREFIX
        self.timeout = float(os.environ.get("DIFY_TIMEOUT", "120"))
        self.poll_timeout = float(os.environ.get("DIFY_POLL_TIMEOUT", "90"))
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
        workflow_run_id = body.get("workflow_run_id") or data.get("id")
        status = data.get("status")

        if status in {"running", None} and workflow_run_id:
            data = self._poll_run_detail(workflow_run_id)

        outputs = data.get("outputs") or {}
        error = data.get("error")
        if data.get("status") in {"failed", "stopped"}:
            raise RuntimeError(error or "Dify Workflow 执行失败")

        return {
            "workflow_run_id": workflow_run_id,
            "task_id": body.get("task_id"),
            "status": data.get("status") or status or "succeeded",
            "outputs": outputs,
            "text": self._extract_text(outputs),
            "raw": body,
        }

    def _poll_run_detail(self, workflow_run_id: str) -> Dict[str, Any]:
        started = time.time()
        last_payload: Dict[str, Any] = {}

        while time.time() - started < self.poll_timeout:
            response = self.http_client.get(
                f"{self.api_base}/workflows/run/{workflow_run_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text.strip()
                raise RuntimeError(f"查询 Dify Workflow 状态失败: HTTP {response.status_code} - {detail}") from exc

            payload = response.json()
            last_payload = payload
            status = payload.get("status")
            if status not in {None, "running"}:
                return payload
            time.sleep(1)

        raise RuntimeError(f"Dify Workflow 执行超时，最后状态: {last_payload.get('status', 'unknown')}")

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
# 增强版 AI Chat Manager
# ============================================================================

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
                self.intelligent_agent = create_agent(dashboard_type)
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
                'team': "请分析测试团队效率和缺陷发现能力",
                'one_click': "请一键综合分析当前缺陷与测试数据（全量）",
                'agent_analysis': "请使用智能工具进行深度分析"
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
                          conversation_history: List = None) -> Dict[str, Any]:
        """
        使用智能 Agent 处理问题

        Args:
            question: 用户问题
            data: 数据 DataFrame
            conversation_history: 对话历史（可选）

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
            # 使用智能 Agent 处理
            result = self.intelligent_agent.process(question, data, conversation_history)

            # 格式化返回结果
            return {
                'success': True,
                'text': result['text'],
                'insights': result.get('insights', []),
                'visualizations': result.get('visualizations', []),
                'tools_used': result.get('tools_used', []),
                'context': result.get('context', {}),
                'agent_used': True
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
        """使用 Dify Workflow 处理问题。"""
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
                user=self.dify_client.build_user(self.dashboard_type),
            )
            text = result.get('text') or 'Dify Workflow 已执行，但没有返回可展示的文本。'
            return {
                'success': True,
                'text': text,
                'workflow_run_id': result.get('workflow_run_id'),
                'task_id': result.get('task_id'),
                'outputs': result.get('outputs', {}),
            }
        except Exception as e:
            logger.error(f"Dify Workflow 处理失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'text': f'Dify Workflow 调用失败：{str(e)}'
            }

    def _get_enhanced_system_prompt(self, data_context: str = "") -> str:
        """获取增强的系统提示词"""
        if self.use_agent and self.intelligent_agent:
            # 使用智能 Agent 的系统提示词
            return self.intelligent_agent.get_enhanced_system_prompt(data_context)

        # 使用默认增强提示词
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

        if data_context:
            prompt += f"\n\n**当前数据上下文：**\n{data_context}\n"

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
                        'margin': '5px',
                        'padding': '8px 12px',
                        'fontSize': '12px',
                        'backgroundColor': color_scheme['bg'],
                        'color': color_scheme['color'],
                        'border': f"1px solid {color_scheme['border']}",
                        'borderRadius': '15px',
                        'cursor': 'pointer',
                        'transition': 'all 0.3s ease',
                        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)' if is_agent_button else 'none'
                    }
                )
            )

        # 构建界面
        interface = html.Div([
            # Agent 模式控制
            html.Div([
                html.Div([
                    html.Label([
                        html.I(className="fas fa-robot", style={'marginRight': '5px'}),
                        '启用智能分析'
                    ], style={'fontSize': '14px', 'marginRight': '10px'}),
                    dcc.Checklist(
                        id=f'{chat_id_prefix}-use-agent',
                        options=[{'label': ' 使用 Agent', 'value': 'agent'}],
                        value=['agent'] if self.use_agent else [],
                        style={'display': 'inline-block'}
                    )
                ], style={'display': 'inline-block', 'marginRight': '18px'}),
                html.Div([
                    html.Label([
                        html.I(className="fas fa-diagram-project", style={'marginRight': '5px'}),
                        'Dify Workflow'
                    ], style={'fontSize': '14px', 'marginRight': '10px'}),
                    dcc.Checklist(
                        id=f'{chat_id_prefix}-use-dify',
                        options=[{'label': ' 调用 Dify', 'value': 'dify'}],
                        value=[],
                        style={'display': 'inline-block'}
                    )
                ], style={'display': 'inline-block', 'marginRight': '18px'}),
                html.Div([
                    html.Label([
                        html.I(className="fas fa-search", style={'marginRight': '5px'}),
                        '重复提票检测'
                    ], style={'fontSize': '14px', 'marginRight': '10px'}),
                    dcc.Checklist(
                        id=f'{chat_id_prefix}-known-issues',
                        options=[{'label': ' 识别已知问题', 'value': 'known'}],
                        value=[],
                        style={'display': 'inline-block'}
                    )
                ], style={'display': 'inline-block'})
            ], style={
                'textAlign': 'right',
                'padding': '10px',
                'backgroundColor': '#f8f9fa',
                'borderRadius': '8px',
                'marginBottom': '10px'
            }),

            # 对话历史区域
            html.Div(
                id=f'{chat_id_prefix}-history',
                children=[
                    html.Div([
                        html.I(className="fas fa-robot", style={'marginRight': '8px', 'color': '#3498db'}),
                        html.Span(
                            f"您好！我是{self.assistant_name}。"
                            f"{'智能Agent模式已启用，可以执行数据分析操作。' if self.use_agent else '您可以问我关于数据的问题。'}"
                        )
                    ], style={
                        'padding': '12px',
                        'backgroundColor': '#f8f9fa',
                        'borderRadius': '8px',
                        'margin': '8px 0',
                        'border': '1px solid #e9ecef'
                    })
                ],
                style={
                    'flex': '1 1 auto',
                    'minHeight': '220px',
                    'overflowY': 'auto',
                    'border': '1px solid #ddd',
                    'padding': '15px',
                    'borderRadius': '8px',
                    'backgroundColor': '#fafafa'
                }
            ),

            # 状态显示
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

            # 输入区域
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
                        'fontSize': '14px'
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
                        'fontWeight': 'bold'
                    }
                )
            ], style={'display': 'flex', 'alignItems': 'center', 'marginTop': '10px'}),

            # 预设问题
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

            # 控制面板
            html.Div([
                html.Div([
                    html.Label([
                        dcc.Checklist(
                            id=f'{chat_id_prefix}-show-reasoning',
                            options=[{'label': ' 显示AI思考过程', 'value': 'show'}],
                            value=['show'],
                            style={'fontSize': '14px'}
                        )
                    ])
                ], style={'flex': '1'}),

                html.Div([
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
                'borderRadius': '4px'
            })
        ], style={'width': '100%', 'height': '100%', 'display': 'flex', 'flexDirection': 'column', 'gap': '10px', 'padding': '20px'})

        return interface

    def create_enhanced_chat_stores(self, chat_id_prefix: str = 'chat') -> List[dcc.Store]:
        """创建增强版聊天存储组件"""
        stores = [
            dcc.Store(id=f'{chat_id_prefix}-messages', data=[]),
            dcc.Store(id=f'{chat_id_prefix}-use-agent-state', data={'use_agent': self.use_agent}),
            dcc.Store(id=f'{chat_id_prefix}-agent-results', data={}),
            dcc.Store(id=f'{chat_id_prefix}-known-issue-state', data={'enabled': False}),
            dcc.Store(id=f'{chat_id_prefix}-streaming-state', data={'active': False, 'task_id': None}),
            dcc.Interval(
                id=f'{chat_id_prefix}-update-interval',
                interval=200,
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
        def render_chat_history(chat_messages: List[Dict[str, Any]]):
            chat_history_children = []
            for msg in chat_messages:
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

                    chat_history_children.append(
                        html.Div([
                            html.Div([
                                html.I(className=icon_class, style={'marginRight': '8px', 'color': icon_color}),
                                html.Span(title, style={'fontWeight': 'bold', 'color': icon_color})
                            ], style={'marginBottom': '5px'}),
                            html.Div(msg.get("content", ""), style={
                                'paddingLeft': '24px',
                                'whiteSpace': 'pre-line'
                            })
                        ], style={
                            'padding': '12px',
                            'backgroundColor': bg_color,
                            'borderRadius': '8px',
                            'margin': '8px 0',
                            'border': f'1px solid {border_color}',
                            'marginRight': '20px'
                        })
                    )
            return chat_history_children

        def start_agent_streaming(task_id: str, question: str, current_data: Any, conversation_history: List[Dict[str, Any]]):
            def worker():
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

                    result = self.process_with_agent(question, current_data, conversation_history)
                    if not result.get('success'):
                        raise RuntimeError(result.get('text') or result.get('error') or "智能Agent执行失败")

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

            threading.Thread(target=worker, daemon=True).start()

        def start_llm_streaming(task_id: str, question: str, current_data: Any, conversation_history: List[Dict[str, Any]]):
            data_context = self._generate_data_context(current_data)
            system_prompt = self._get_enhanced_system_prompt(data_context)
            messages = [{"role": "system", "content": system_prompt}]
            for msg in (conversation_history or [])[-10:]:
                if msg.get('role') in ['user', 'assistant']:
                    messages.append({"role": msg['role'], "content": msg.get('content', '')})
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
                        streaming_data.setdefault(task_id, {
                            'status': 'processing',
                            'reasoning': '',
                            'response': '',
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'progress': 'Dify Workflow 正在执行...',
                            'chunk_buffer': '',
                            'last_update': time.time()
                        })

                    data_context = self._generate_data_context(current_data)
                    result = self.process_with_dify_workflow(question, data_context)
                    if not result.get('success'):
                        raise RuntimeError(result.get('error') or result.get('text') or 'Dify Workflow 执行失败')

                    formatted = result.get('text', '')
                    outputs = result.get('outputs') or {}
                    workflow_run_id = result.get('workflow_run_id')
                    if workflow_run_id:
                        formatted = f"{formatted}\n\n[Dify Workflow Run ID] {workflow_run_id}"
                    if outputs and formatted.strip() == json.dumps(outputs, ensure_ascii=False, indent=2).strip():
                        formatted = f"Dify Workflow 输出：\n{formatted}"

                    chunk_size = 80
                    for end in range(0, len(formatted), chunk_size):
                        partial = formatted[:end + chunk_size]
                        with streaming_lock:
                            streaming_data[task_id]['status'] = 'processing'
                            streaming_data[task_id]['response'] = partial
                            streaming_data[task_id]['progress'] = 'Dify Workflow 正在输出...'
                            streaming_data[task_id]['last_update'] = time.time()
                        time.sleep(0.03)

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

            threading.Thread(target=worker, daemon=True).start()

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
                    messages.append({"role": msg['role'], "content": msg.get('content', '')})
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
             State(f'{chat_id_prefix}-use-agent', 'value'),
             State(f'{chat_id_prefix}-use-dify', 'value'),
             State(f'{chat_id_prefix}-known-issues', 'value')]
        )
        def handle_enhanced_chat(*args):
            send_clicks = args[0]
            input_submit = args[1]
            clear_clicks = args[2]
            preset_clicks = args[3:-7]
            input_value = args[-7]
            chat_messages = args[-6] or []
            streaming_state = args[-5] or {'active': False, 'task_id': None}
            filtered_data = args[-4]
            use_agent_checked = args[-3] or []
            use_dify_checked = args[-2] or []
            known_issues_checked = args[-1] or []

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
                raise PreventUpdate

            use_agent = ('agent' in use_agent_checked) and self.use_agent
            use_dify = 'dify' in (use_dify_checked or [])
            use_known_issues = 'known' in (known_issues_checked or [])

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
                        # Agent 按钮强制启用 Agent 模式
                        if 'agent' in key:
                            use_agent = True and self.use_agent
                        break

            # 处理用户消息
            agent_results = {}
            status_display = ""

            if user_message:
                # 添加用户消息
                chat_messages.append({"role": "user", "content": user_message})

                # 获取数据
                current_data: Any = pd.DataFrame()
                if filtered_data:
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
                    "agent_used": bool((not use_known_issues) and use_agent and self._has_data(current_data))
                })

                status_display = html.Div([
                    html.I(className="fas fa-spinner fa-spin", style={'marginRight': '8px', 'color': '#3498db'}),
                    html.Span("AI正在思考...", style={'color': '#666'})
                ])

                if use_known_issues:
                    with streaming_lock:
                        if task_id in streaming_data:
                            streaming_data[task_id]['progress'] = '正在检索已知问题...'
                    start_duplicate_check_streaming(task_id, user_message, current_data, chat_messages)
                elif use_dify:
                    with streaming_lock:
                        if task_id in streaming_data:
                            streaming_data[task_id]['progress'] = '正在调用 Dify Workflow...'
                    start_dify_streaming(task_id, user_message, current_data)
                elif use_agent and self._has_data(current_data):
                    start_agent_streaming(task_id, user_message, current_data, chat_messages)
                else:
                    start_llm_streaming(task_id, user_message, current_data, chat_messages)

                streaming_state = {'active': True, 'task_id': task_id}

            chat_history_children = render_chat_history(chat_messages)
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
             State(f'{chat_id_prefix}-agent-results', 'data')],
            prevent_initial_call=True
        )
        def update_streaming_response(n_intervals, chat_messages, streaming_state, show_reasoning, agent_results):
            if not streaming_state or not streaming_state.get('active'):
                raise PreventUpdate

            task_id = streaming_state.get('task_id')
            if not task_id:
                raise PreventUpdate

            with streaming_lock:
                stream_data = dict(streaming_data.get(task_id) or {})

            if not stream_data:
                raise PreventUpdate

            chat_messages = chat_messages or []
            current_task_id = task_id

            reasoning_content = stream_data.get('reasoning') or ''
            if reasoning_content and show_reasoning and 'show' in (show_reasoning or []):
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
                        "content": f"💭 AI思考过程：\n{reasoning_content}"
                    })
                else:
                    chat_messages[reasoning_index]["content"] = f"💭 AI思考过程：\n{reasoning_content}"

            response_content = stream_data.get('response') or ''
            response_index = -1
            for i in range(len(chat_messages) - 1, -1, -1):
                if chat_messages[i].get('type') == 'stream_response' and chat_messages[i].get('task_id') == current_task_id:
                    response_index = i
                    break
            if response_index != -1:
                chat_messages[response_index]["content"] = response_content

            status = stream_data.get('status')
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
                status_display = ""

            if status == 'completed':
                streaming_state = {'active': False, 'task_id': None}
                status_display = ""

            chat_history_children = render_chat_history(chat_messages)
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

    def _generate_data_context(self, data: Any) -> str:
        """生成数据上下文"""
        if not self._has_data(data):
            return "当前没有可用的数据。"

        def summarize_df(df: pd.DataFrame, title: str) -> List[str]:
            parts = [f"{title}："]
            parts.append(f"- 总记录数: {len(df)}")
            parts.append(f"- 列数: {len(df.columns)}")
            key_columns = {
                'tproject': '项目',
                'project': '项目',
                'severity_group': '严重性',
                'category': '类别',
                'topissue': 'TopIssue',
                'run_status': '测试状态'
            }
            for col, display_name in key_columns.items():
                if col in df.columns:
                    try:
                        unique_count = df[col].nunique()
                    except Exception:
                        unique_count = 0
                    parts.append(f"- {display_name}种类: {unique_count}")
            return parts

        context_parts = ["数据集概览："]
        if isinstance(data, pd.DataFrame):
            context_parts.extend(summarize_df(data, "当前数据"))
        elif isinstance(data, dict):
            for name, df in data.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    context_parts.extend(summarize_df(df, f"数据集[{name}]"))

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
