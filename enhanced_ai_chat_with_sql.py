"""
增强版 AI Chat Manager with SQL Query Capability

在 enhanced_ai_chat_manager 基础上，集成 Text-to-SQL 功能，提供：
1. 智能工具调用 - AI 可执行数据分析操作
2. SQL 查询能力 - 自然语言查询数据库
3. 智能上下文管理 - 根据问题动态筛选数据
4. 对话记忆系统 - 记住关键洞察和用户偏好
5. 智能路由 - 自动判断使用 Agent 还是 SQL 查询

集成方式：
from enhanced_ai_chat_with_sql import create_enhanced_chat_manager_with_sql

chat_manager = create_enhanced_chat_manager_with_sql(
    dashboard_type='defect_explore',
    use_agent=True,
    enable_sql=True
)

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
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

import dash
from dash import dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

# 导入 SQL 查询引擎
from sql_query_engine import (
    SQLQueryEngine,
    SQLQueryConfig,
    create_sql_engine
)

# 导入配置和创建独立的 DeepSeekStreamingChat（避免依赖 ai_chat_manager）
try:
    from config_center import cfg
    DEEPSEEK_API_KEY = cfg.DEEPSEEK_API_KEY
    DEEPSEEK_API_BASE = cfg.DEEPSEEK_API_BASE
    DEEPSEEK_MODEL = cfg.DEEPSEEK_MODEL
except ImportError:
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2000
streaming_data = {}
streaming_lock = __import__('threading').Lock()

# 创建独立的 DeepSeekStreamingChat 类
class DeepSeekStreamingChat:
    """独立的 DeepSeek 聊天类（不依赖 ai_chat_manager）"""

    def __init__(self, *args, **kwargs):
        self._available = False
        self._client = None
        try:
            import openai
            self._client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_API_BASE
            )
            self._available = True
            logger.info("✅ OpenAI client 初始化成功")
        except ImportError as e:
            logger.warning(f"⚠️ openai 模块未安装: {e}")
        except Exception as e:
            logger.warning(f"⚠️ OpenAI client 初始化失败: {e}")

    def complete(self, prompt: str, **kwargs) -> str:
        """简单的 LLM 调用"""
        if not self._available or not self._client:
            return "抱歉，LLM 服务不可用，请检查配置或安装依赖。"

        try:
            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ LLM 调用失败: {e}")
            return f"LLM 调用失败: {str(e)}"

# 导入智能 Agent 系统
try:
    from intelligent_agent import (
        IntelligentAgent,
        create_agent,
        create_agent_for_defect,
        create_agent_for_test,
        create_agent_with_smart_loading,
        SmartAgent,
        ToolExecutor
    )
    AGENT_AVAILABLE = True
    print("✅ 智能Agent系统已加载")
except ImportError as e:
    AGENT_AVAILABLE = False
    print(f"⚠️ 智能Agent系统不可用: {e}")
    IntelligentAgent = None
    SmartAgent = None

# 导入智能数据加载器
try:
    from smart_data_loader import (
        SmartDataLoader,
        DataLoaderAdapter,
        LoaderConfig,
        create_smart_loader,
        create_data_loader_adapter
    )
    SMART_LOADER_AVAILABLE = True
    print("✅ 智能数据加载器已加载")
except ImportError as e:
    SMART_LOADER_AVAILABLE = False
    print(f"⚠️ 智能数据加载器不可用: {e}")

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 增强版 AI Chat Manager with SQL
# ============================================================================

class EnhancedAIChatManagerWithSQL:
    """带 SQL 查询能力的增强版 AI Chat Manager"""

    def __init__(
        self,
        dashboard_type: str = 'general',
        use_agent: bool = True,
        enable_sql: bool = True,
        assistant_name: str = 'SiSi',
        db_path: str = None,
        streaming: bool = True
    ):
        """
        初始化

        Args:
            dashboard_type: Dashboard 类型 ('defect', 'test', 'trend', 'general')
            use_agent: 是否使用智能 Agent
            enable_sql: 是否启用 SQL 查询
            assistant_name: AI 助手名称
            db_path: 数据库路径
            streaming: 是否使用流式响应
        """
        self.dashboard_type = dashboard_type
        self.use_agent = use_agent and AGENT_AVAILABLE
        self.enable_sql = enable_sql
        self.assistant_name = assistant_name
        self.streaming = streaming

        # 初始化 SQL 查询引擎
        if enable_sql:
            try:
                if db_path:
                    self.sql_engine = SQLQueryEngine(SQLQueryConfig(db_path=db_path))
                elif hasattr(self, 'get_db_path'):
                    self.sql_engine = SQLQueryEngine(SQLQueryConfig(db_path=self.get_db_path()))
                else:
                    # 默认路径
                    self.sql_engine = create_sql_engine()
                logger.info("✅ SQL 查询引擎已加载")
            except Exception as e:
                logger.warning(f"⚠️ SQL 查询引擎加载失败: {e}")
                self.enable_sql = False
                self.sql_engine = None
        else:
            self.sql_engine = None

        # 初始化 DeepSeek 聊天
        try:
            self.chatbot = DeepSeekStreamingChat()
            logger.info("✅ DeepSeek 聊天机器人初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek 聊天机器人初始化失败: {e}")
            self.chatbot = DeepSeekStreamingChat()  # 使用降级类

        # 初始化智能 Agent（如果启用）
        self.agent = None
        if self.use_agent:
            try:
                # 根据 dashboard 类型创建对应的 Agent
                if dashboard_type == 'defect':
                    self.agent = create_agent_for_defect()
                elif dashboard_type == 'test':
                    self.agent = create_agent_for_test()
                else:
                    self.agent = create_agent()
                logger.info(f"✅ 智能 Agent 已加载: {assistant_name}")
            except Exception as e:
                logger.warning(f"⚠️ 智能 Agent 加载失败: {e}")
                self.use_agent = False

        # 智能数据加载器
        self.smart_loader = None
        if SMART_LOADER_AVAILABLE:
            try:
                self.smart_loader = create_smart_loader()
                logger.info("✅ 智能数据加载器已加载")
            except Exception as e:
                logger.warning(f"⚠️ 智能数据加载器加载失败: {e}")

        # 对话记忆
        self.conversation_history = []
        self.user_preferences = {}

        logger.info(f"✅ 增强版 AI Chat Manager (with SQL) 初始化完成")

    def is_sql_question(self, question: str) -> bool:
        """判断问题是否需要 SQL 查询"""
        if not self.enable_sql:
            return False

        sql_keywords = [
            "多少", "数量", "统计", "排名", "最高", "最低", "平均",
            "查询", "列出", "展示", "显示", "查看",
            "通过率", "覆盖率", "缺陷", "测试", "失败", "成功",
            "趋势", "对比", "分布", "top", "前",
            "defects", "test", "count", "sql", "database"
        ]

        question_lower = question.lower()
        return any(keyword in question_lower for keyword in sql_keywords)

    def ask(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        智能问答 - 自动路由到 SQL 查询、Agent 或纯 LLM

        Args:
            question: 用户问题
            data_context: 当前数据上下文（可选）
            use_cache: 是否使用 SQL 查询缓存

        Returns:
            {
                "success": bool,
                "answer": str,
                "sql": Optional[str],
                "data": Optional[pd.DataFrame],
                "source": "sql" | "agent" | "llm",
                "error": Optional[str]
            }
        """
        # 1. 判断是否需要 SQL 查询
        if self.is_sql_question(question):
            logger.info(f"🔍 检测到 SQL 查询需求: {question[:50]}...")
            return self._ask_with_sql(question, data_context, use_cache)

        # 2. 判断是否使用智能 Agent
        if self.use_agent and self.agent:
            logger.info(f"🤖 使用智能 Agent: {question[:50]}...")
            return self._ask_with_agent(question, data_context)

        # 3. 降级到纯 LLM
        logger.info(f"💬 使用纯 LLM: {question[:50]}...")
        return self._ask_with_llm(question, data_context)

    def _ask_with_sql(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """使用 SQL 查询回答"""

        # 准备数据上下文
        data_context_str = None
        if data_context is not None and not data_context.empty:
            data_context_str = f"""
当前筛选的数据样本（前 3 行）：
{data_context.head(3).to_string()}
总行数: {len(data_context)}
"""

        # 调用 SQL 查询引擎
        result = self.sql_engine.query(
            question=question,
            llm_generate_func=self.chatbot.complete,
            data_context=data_context_str,
            use_cache=use_cache
        )

        if result["success"]:
            # 生成自然语言回答
            answer = self._generate_natural_answer(
                question=question,
                sql=result["sql"],
                data=result["result"]
            )

            return {
                "success": True,
                "answer": answer,
                "sql": result["sql"],
                "data": result["result"],
                "source": "sql",
                "retries": result["retries"],
                "execution_time_ms": result["execution_time_ms"],
                "from_cache": result.get("from_cache", False)
            }
        else:
            # SQL 查询失败，降级到 LLM
            logger.warning(f"SQL 查询失败: {result['error']}")
            return self._ask_with_llm(question, data_context, sql_error=result.get("error"))

    def _ask_with_agent(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """使用智能 Agent 回答"""

        try:
            # 准备上下文
            context = {}
            if data_context is not None and not data_context.empty:
                context['current_data'] = data_context.head(10).to_dict('records')

            # 调用 Agent
            response = self.agent.ask(question, context=context)

            return {
                "success": True,
                "answer": response.get("answer", ""),
                "source": "agent",
                "thought": response.get("thought", ""),
                "tools_used": response.get("tools_used", [])
            }
        except Exception as e:
            logger.error(f"Agent 调用失败: {e}")
            # 降级到 LLM
            return self._ask_with_llm(question, data_context, agent_error=str(e))

    def _ask_with_llm(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        sql_error: Optional[str] = None,
        agent_error: Optional[str] = None
    ) -> Dict[str, Any]:
        """直接用 LLM 回答"""

        prompt_parts = [f"用户问题：{question}"]

        # 添加数据上下文
        if data_context is not None and not data_context.empty:
            prompt_parts.append(f"\n当前数据：\n{data_context.head(5).to_string()}")

        # 添加错误信息
        if sql_error:
            prompt_parts.append(f"\n注意：SQL 查询失败，请直接分析数据。错误：{sql_error}")
        if agent_error:
            prompt_parts.append(f"\n注意：Agent 调用失败，请直接回答。错误：{agent_error}")

        # 添加 Dashboard 类型提示
        if self.dashboard_type == 'defect':
            prompt_parts.append("\n你是缺陷分析专家，关注缺陷严重度、分布、趋势等。")
        elif self.dashboard_type == 'test':
            prompt_parts.append("\n你是测试管理专家，关注测试覆盖率、通过率、失败原因等。")

        prompt = "\n".join(prompt_parts)

        try:
            answer = self.chatbot.complete(prompt)
            return {
                "success": True,
                "answer": answer,
                "source": "llm"
            }
        except Exception as e:
            return {
                "success": False,
                "answer": f"无法回答问题。错误：{str(e)}",
                "source": "llm_failed",
                "error": str(e)
            }

    def _generate_natural_answer(
        self,
        question: str,
        sql: str,
        data: pd.DataFrame
    ) -> str:
        """基于 SQL 查询结果生成自然语言回答"""

        prompt = f"""
用户问题：{question}

SQL 查询：
{sql}

查询结果：
{data.to_string(index=False)}

请用自然语言回答用户的问题，简洁明了。如果结果包含数字，请适当解释其含义。
"""

        try:
            answer = self.chatbot.complete(prompt)
            return answer
        except Exception as e:
            # 降级：直接返回数据
            return f"查询结果：\n{data.to_string(index=False)}"


# ============================================================================
# Dash 集成 - 兼容 enhanced_ai_chat_manager 接口
# ============================================================================

def create_enhanced_chat_manager_with_sql(
    dashboard_type: str = 'general',
    use_agent: bool = True,
    enable_sql: bool = True,
    assistant_name: str = 'SiSi',
    db_path: str = None,
    streaming: bool = True
) -> EnhancedAIChatManagerWithSQL:
    """
    创建增强版 AI Chat Manager (with SQL)

    Args:
        dashboard_type: Dashboard 类型 ('defect', 'test', 'trend', 'general')
        use_agent: 是否使用智能 Agent
        enable_sql: 是否启用 SQL 查询
        assistant_name: AI 助手名称
        db_path: 数据库路径
        streaming: 是否使用流式响应

    Returns:
        EnhancedAIChatManagerWithSQL 实例
    """
    return EnhancedAIChatManagerWithSQL(
        dashboard_type=dashboard_type,
        use_agent=use_agent,
        enable_sql=enable_sql,
        assistant_name=assistant_name,
        db_path=db_path,
        streaming=streaming
    )


# ============================================================================
# 扩展 EnhancedAIChatManagerWithSQL 的 Dash 集成方法
# ============================================================================

def create_enhanced_chat_interface(
    self,
    chat_id_prefix: str = "enhanced-sql-chat"
):
    """
    创建增强版聊天界面（兼容 enhanced_ai_chat_manager 接口）

    用法：
    chat_manager.create_enhanced_chat_interface('defect-explore-chat')
    """

    # 定义聊天数据存储（使用全局 streaming_data）
    if chat_id_prefix not in streaming_data:
        streaming_data[chat_id_prefix] = {
            "messages": [],
            "is_streaming": False
        }

    # 创建聊天界面组件
    chat_interface = html.Div([
        # 聊天头部
        html.Div([
            html.H4([
                html.Span("🤖 "),
                html.Span(f"{self.assistant_name} (SQL + Agent)"),
                # 显示能力标签
                html.Span([
                    html.Span(" SQL ", style={
                        "background": "#28a745" if self.enable_sql else "#6c757d",
                        "color": "white",
                        "padding": "2px 8px",
                        "borderRadius": "10px",
                        "fontSize": "12px",
                        "marginLeft": "10px"
                    }),
                    html.Span(" Agent ", style={
                        "background": "#007bff" if self.use_agent else "#6c757d",
                        "color": "white",
                        "padding": "2px 8px",
                        "borderRadius": "10px",
                        "fontSize": "12px",
                        "marginLeft": "5px"
                    })
                ])
            ], style={
                "margin": "0 0 15px 0",
                "color": "#333",
                "fontSize": "18px",
                "fontWeight": "500"
            }),

            # 聊天消息区域
            html.Div(
                id=f"{chat_id_prefix}-messages",
                children=[],
                style={
                    "height": "450px",
                    "overflowY": "auto",
                    "padding": "15px",
                    "border": "1px solid #e0e0e0",
                    "borderRadius": "8px",
                    "backgroundColor": "#fafafa",
                    "marginBottom": "15px"
                }
            ),

            # 输入区域
            html.Div([
                dcc.Textarea(
                    id=f"{chat_id_prefix}-input",
                    placeholder=f"输入问题（支持 SQL 查询和智能 Agent 分析）...",
                    style={
                        "width": "100%",
                        "height": "80px",
                        "padding": "12px",
                        "border": "1px solid #ccc",
                        "borderRadius": "8px",
                        "fontSize": "14px",
                        "resize": "none"
                    }
                ),
                html.Div([
                    html.Button(
                        "发送",
                        id=f"{chat_id_prefix}-submit",
                        n_clicks=0,
                        style={
                            "marginTop": "10px",
                            "padding": "10px 30px",
                            "backgroundColor": "#007bff",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "6px",
                            "cursor": "pointer",
                            "fontSize": "14px",
                            "fontWeight": "500"
                        }
                    ),
                    html.Button(
                        "清除",
                        id=f"{chat_id_prefix}-clear",
                        n_clicks=0,
                        style={
                            "marginTop": "10px",
                            "marginLeft": "10px",
                            "padding": "10px 20px",
                            "backgroundColor": "#6c757d",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "6px",
                            "cursor": "pointer",
                            "fontSize": "14px"
                        }
                    )
                ])
            ])
        ])
    ])

    return chat_interface


def create_enhanced_chat_stores(
    self,
    chat_id_prefix: str = "enhanced-sql-chat"
):
    """
    创建聊天存储组件（兼容 enhanced_ai_chat_manager 接口）

    用法：
    chat_manager.create_enhanced_chat_stores('defect-explore-chat')
    """
    return [
        dcc.Store(id=f"{chat_id_prefix}-history"),
        dcc.Store(id=f"{chat_id_prefix}-state", data={"initialized": False})
    ]


def register_enhanced_chat_callbacks(
    self,
    app,
    chat_id_prefix: str = "enhanced-sql-chat",
    data_store_id: str = None,
    data_processor_func: Callable = None,
    dashboard_type: str = None,
    chat_only_mode: bool = False
):
    """
    注册增强版聊天回调（兼容 enhanced_ai_chat_manager 接口）

    用法：
    chat_manager.register_enhanced_chat_callbacks(app, 'defect-explore-chat', 'filtered-data')
    """

    @app.callback(
        [
            Output(f"{chat_id_prefix}-messages", "children"),
            Output(f"{chat_id_prefix}-input", "value"),
            Output(f"{chat_id_prefix}-submit", "disabled")
        ],
        [
            Input(f"{chat_id_prefix}-submit", "n_clicks"),
            Input(f"{chat_id_prefix}-clear", "n_clicks")
        ],
        [
            State(f"{chat_id_prefix}-input", "value"),
            State(data_store_id, "data") if data_store_id else State("dummy", "value")
        ],
        prevent_initial_call=True
    )
    def update_chat(submit_clicks, clear_clicks, user_input, filtered_data):
        ctx = callback_context

        # 清除按钮被点击
        if ctx.triggered and ctx.triggered[0]['prop_id'].endswith('.n_clicks'):
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if 'clear' in trigger_id:
                streaming_data[chat_id_prefix]["messages"] = []
                return [], "", False

        # 发送按钮被点击
        if not user_input or not user_input.strip():
            raise PreventUpdate

        # 禁用发送按钮
        messages = streaming_data[chat_id_prefix]["messages"]

        # 添加用户消息
        messages.append(html.Div([
            html.Strong("你：", style={"color": "#007bff"}),
            html.Span(user_input, style={"color": "#333"})
        ], style={
            "marginBottom": "12px",
            "padding": "8px 12px",
            "backgroundColor": "#e3f2fd",
            "borderRadius": "8px",
            "borderLeft": "3px solid #007bff"
        }))

        # 处理过滤数据（如果有 data_processor_func）
        processed_data = filtered_data
        if data_processor_func and callable(data_processor_func) and filtered_data:
            try:
                processed_result = data_processor_func(filtered_data)
                if isinstance(processed_result, dict):
                    processed_data = processed_result.get("data", processed_result)
            except Exception as e:
                logger.warning(f"data_processor_func 执行失败: {e}")
                processed_data = filtered_data

        # 调用智能问答
        result = self.ask(user_input, data_context=pd.DataFrame(processed_data) if processed_data else None)

        # 构建 AI 消息
        ai_message_parts = []

        # 来源标签
        source_badges = {
            "sql": {"text": "SQL", "color": "#28a745"},
            "agent": {"text": "Agent", "color": "#007bff"},
            "llm": {"text": "LLM", "color": "#6c757d"},
            "sql_failed": {"text": "SQL→LLM", "color": "#dc3545"},
            "llm_failed": {"text": "Failed", "color": "#dc3545"}
        }

        source_info = source_badges.get(result.get("source", "llm"), {"text": "Unknown", "color": "#6c757d"})

        ai_message_parts.append(html.Div([
            html.Span(source_info["text"], style={
                "background": source_info["color"],
                "color": "white",
                "padding": "2px 8px",
                "borderRadius": "10px",
                "fontSize": "11px",
                "marginRight": "8px"
            }),
            html.Strong(f"{self.assistant_name}："),
        ]))

        # 主要回答
        ai_message_parts.append(html.P(result.get("answer", ""), style={
            "margin": "8px 0",
            "lineHeight": "1.6"
        }))

        # SQL 查询（如果有）
        if result.get("sql"):
            ai_message_parts.append(html.Div([
                html.Strong("📊 SQL：", style={"fontSize": "12px", "color": "#666"}),
                html.Code(result["sql"], style={
                    "display": "block",
                    "background": "#f5f5f5",
                    "padding": "8px",
                    "borderRadius": "4px",
                    "fontSize": "12px",
                    "marginTop": "5px",
                    "overflowX": "auto"
                })
            ]))

        # Agent 思考过程（如果有）
        if result.get("thought"):
            ai_message_parts.append(html.Details([
                html.Summary("🤔 思考过程", style={
                    "cursor": "pointer",
                    "color": "#007bff",
                    "fontSize": "13px",
                    "marginTop": "8px"
                }),
                html.P(result["thought"], style={
                    "padding": "8px",
                    "backgroundColor": "#f0f0f0",
                    "borderRadius": "4px",
                    "fontSize": "13px",
                    "margin": "5px 0"
                })
            ]))

        # 数据预览（如果有）
        if result.get("data") is not None and not result["data"].empty:
            ai_message_parts.append(html.Details([
                html.Summary("📋 数据预览", style={
                    "cursor": "pointer",
                    "color": "#007bff",
                    "fontSize": "13px",
                    "marginTop": "8px"
                }),
                html.Table([
                    html.Thead([html.Tr([html.Th(col, style={
                        "padding": "8px",
                        "background": "#007bff",
                        "color": "white",
                        "textAlign": "left"
                    }) for col in result["data"].columns])]),
                    html.Tbody([
                        html.Tr([html.Td(str(val), style={
                            "padding": "8px",
                            "borderBottom": "1px solid #ddd"
                        }) for val in row])
                        for row in result["data"].head(5).values.tolist()
                    ])
                ], style={
                    "width": "100%",
                    "borderCollapse": "collapse",
                    "marginTop": "5px",
                    "fontSize": "12px"
                })
            ]))

        # 执行信息（如果从缓存）
        if result.get("from_cache"):
            ai_message_parts.append(html.Div([
                html.Span("⚡ 缓存命中", style={
                    "color": "#28a745",
                    "fontSize": "11px"
                })
            ], style={
                "marginTop": "8px",
                "textAlign": "right"
            }))

        # 添加到消息列表
        messages.append(html.Div(ai_message_parts, style={
            "marginBottom": "12px",
            "padding": "12px",
            "backgroundColor": "white",
            "borderRadius": "8px",
            "borderLeft": "3px solid " + source_info["color"],
            "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"
        }))

        # 限制消息数量（最多保留 50 条）
        if len(messages) > 50:
            messages = messages[-50:]

        return messages, "", False


# ============================================================================
# 将方法绑定到类
# ============================================================================

EnhancedAIChatManagerWithSQL.create_enhanced_chat_interface = create_enhanced_chat_interface
EnhancedAIChatManagerWithSQL.create_enhanced_chat_stores = create_enhanced_chat_stores
EnhancedAIChatManagerWithSQL.register_enhanced_chat_callbacks = register_enhanced_chat_callbacks

# 添加 register_enhanced_callbacks 作为别名（兼容性）
EnhancedAIChatManagerWithSQL.register_enhanced_callbacks = register_enhanced_chat_callbacks


# ============================================================================
# 快捷函数
# ============================================================================

def create_enhanced_chat_manager_with_sql(
    dashboard_type: str = 'general',
    use_agent: bool = True,
    enable_sql: bool = True,
    assistant_name: str = 'SiSi',
    db_path: str = None,
    streaming: bool = True
):
    """
    快捷函数：创建增强版 AI Chat Manager (with SQL)

    Args:
        dashboard_type: Dashboard 类型
        use_agent: 是否使用智能 Agent
        enable_sql: 是否启用 SQL 查询
        assistant_name: AI 助手名称
        db_path: 数据库路径
        streaming: 是否使用流式响应

    Returns:
        EnhancedAIChatManagerWithSQL 实例
    """
    return EnhancedAIChatManagerWithSQL(
        dashboard_type=dashboard_type,
        use_agent=use_agent,
        enable_sql=enable_sql,
        assistant_name=assistant_name,
        db_path=db_path,
        streaming=streaming
    )


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="增强版 AI Chat Manager with SQL 测试")
    parser.add_argument("--question", "-q", type=str, help="测试问题")
    parser.add_argument("--db", "-d", type=str, default="database/local_data.db", help="数据库路径")
    parser.add_argument("--agent", "-a", action="store_true", help="启用 Agent")
    parser.add_argument("--sql", "-s", action="store_true", help="启用 SQL")

    args = parser.parse_args()

    # 创建聊天实例
    chat = create_enhanced_chat_manager_with_sql(
        dashboard_type='defect',
        use_agent=args.agent,
        enable_sql=args.sql,
        db_path=args.db
    )

    # 测试问题
    if args.question:
        print("=" * 60)
        print(f"问题: {args.question}")
        print("=" * 60)

        result = chat.ask(args.question)

        print(f"\n来源: {result['source']}")
        print(f"\n回答:\n{result['answer']}")

        if result.get("sql"):
            print(f"\nSQL:\n{result['sql']}")

        if result.get("data") is not None:
            print(f"\n数据:\n{result['data'].to_string(index=False)}")
    else:
        # 交互式测试
        print(f"增强版 AI Chat Manager (with SQL) - 交互式测试")
        print(f"Agent: {'✅' if args.agent else '❌'} | SQL: {'✅' if args.sql else '❌'}")
        print("输入问题，输入 'quit' 退出")
        print("=" * 60)

        while True:
            question = input(f"\n你 ({chat.assistant_name}): ").strip()

            if question.lower() in ['quit', 'exit', 'q']:
                print("再见！")
                break

            if not question:
                continue

            result = chat.ask(question)

            source_icon = {
                "sql": "📊",
                "agent": "🤖",
                "llm": "💬",
                "sql_failed": "❌",
                "llm_failed": "❌"
            }.get(result.get("source", "llm"), "❓")

            print(f"\n{source_icon} [{result['source'].upper()}] {chat.assistant_name}: {result['answer']}")

            if result.get("sql"):
                print(f"\n[SQL] {result['sql']}")

            if result.get("data") is not None and not result["data"].empty:
                print(f"\n[数据]")
                print(result["data"].to_string(index=False))
