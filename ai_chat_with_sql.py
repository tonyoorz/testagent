#!/usr/bin/env python3
"""
AI Chat Manager with SQL Query Capability

在原有 ai_chat_manager 基础上，集成 Text-to-SQL 功能

使用方法：
from ai_chat_with_sql import AIChatWithSQL
chat = AIChatWithSQL()
result = chat.ask("最近一周的测试通过率是多少？")

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime

# 导入 SQL 查询引擎
from sql_query_engine import (
    SQLQueryEngine,
    SQLQueryConfig,
    create_sql_engine
)

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
    # 降级：从 config_center 读取配置
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
    
    # 创建简单的占位类
    class DeepSeekStreamingChat:
        def __init__(self, *args, **kwargs):
            pass
        
        def complete(self, prompt: str, **kwargs) -> str:
            """简单的 LLM 调用（需要实现）"""
            import openai
            client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_API_BASE
            )
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS
            )
            return response.choices[0].message.content
    
    streaming_data = {}
    streaming_lock = __import__('threading').Lock()

import pandas as pd

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# AI Chat with SQL
# ============================================================================

class AIChatWithSQL:
    """带 SQL 查询能力的 AI Chat Manager"""
    
    def __init__(self, db_path: str = None, config: SQLQueryConfig = None):
        """
        初始化
        
        Args:
            db_path: 数据库路径
            config: SQL 查询配置
        """
        # 初始化 SQL 查询引擎
        if db_path:
            self.sql_engine = SQLQueryEngine(config or SQLQueryConfig(db_path=db_path))
        elif config and config.db_path:
            self.sql_engine = SQLQueryEngine(config)
        else:
            # 默认路径
            try:
                from config_center import cfg
                db_path = cfg.get_db_path()
            except ImportError:
                db_path = "database/local_data.db"
            self.sql_engine = SQLQueryEngine(SQLQueryConfig(db_path=db_path))
        
        # 初始化 DeepSeek 聊天
        try:
            self.chatbot = DeepSeekStreamingChat()
            logger.info("DeepSeek 聊天机器人初始化成功")
        except Exception as e:
            logger.warning(f"DeepSeek 聊天机器人初始化失败: {e}，使用降级方案")
            self.chatbot = DeepSeekStreamingChat()  # 使用降级类
        
        logger.info("AI Chat with SQL 初始化完成")
    
    def ask(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        enable_sql: bool = True,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        提问并回答
        
        Args:
            question: 用户问题
            data_context: 当前数据上下文（可选）
            enable_sql: 是否启用 SQL 查询
            use_cache: 是否使用 SQL 查询缓存
        
        Returns:
            {
                "success": bool,
                "answer": str,
                "sql": Optional[str],
                "data": Optional[pd.DataFrame],
                "source": "sql" | "llm",
                "error": Optional[str]
            }
        """
        # 判断是否需要 SQL 查询
        if enable_sql and self._is_sql_question(question):
            # 尝试 SQL 查询
            return self._ask_with_sql(question, data_context, use_cache)
        else:
            # 直接用 LLM 回答
            return self._ask_with_llm(question, data_context)
    
    def _is_sql_question(self, question: str) -> bool:
        """判断问题是否需要 SQL 查询"""
        sql_keywords = [
            "多少", "数量", "统计", "排名", "最高", "最低", "平均",
            "查询", "列出", "展示", "显示", "查看",
            "通过率", "覆盖率", "缺陷", "测试", "失败", "成功",
            "趋势", "对比", "分布", "top", "前"
        ]
        
        question_lower = question.lower()
        return any(keyword in question for keyword in sql_keywords)
    
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
            return {
                "success": False,
                "answer": f"无法执行数据库查询。错误：{result['error']}",
                "sql": result.get("sql"),
                "source": "sql_failed",
                "error": result["error"]
            }
    
    def _ask_with_llm(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """直接用 LLM 回答"""
        
        prompt_parts = [f"用户问题：{question}"]
        
        if data_context is not None and not data_context.empty:
            prompt_parts.append(f"\n当前数据：\n{data_context.head(5).to_string()}")
        
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

请用自然语言回答用户的问题，简洁明了。
"""
        
        try:
            answer = self.chatbot.complete(prompt)
            return answer
        except Exception as e:
            # 降级：直接返回数据
            return f"查询结果：\n{data.to_string(index=False)}"
    
    def chat_stream(self, question: str, **kwargs) -> None:
        """流式聊天（兼容原有接口）"""
        # 这里可以实现流式响应
        # 暂时使用普通问答
        result = self.ask(question, **kwargs)
        print(result["answer"])


# ============================================================================
# Dash 集成示例
# ============================================================================

def create_chat_interface_with_sql(
    app,
    chat_id_prefix: str = "sql-chat",
    db_path: str = None
):
    """
    创建带 SQL 查询能力的 Dash 聊天界面
    
    用法：
    from dash import Dash, html, dcc, Input, Output
    from ai_chat_with_sql import create_chat_interface_with_sql
    
    app = Dash(__name__)
    
    # 创建聊天界面
    create_chat_interface_with_sql(app, "my-chat")
    """
    
    chat_manager = AIChatWithSQL(db_path=db_path)
    
    # 定义聊天数据存储
    chat_data = {
        "messages": [],
        "last_question": "",
        "last_answer": ""
    }
    
    # 创建聊天界面组件
    chat_container = html.Div([
        html.Div([
            html.H5("🤖 AI 助手（支持 SQL 查询）"),
            html.Div(id=f"{chat_id_prefix}-messages", style={
                "height": "400px",
                "overflow-y": "auto",
                "padding": "10px",
                "border": "1px solid #ddd",
                "border-radius": "5px",
                "margin-bottom": "10px"
            }),
            html.Div([
                dcc.Textarea(
                    id=f"{chat_id_prefix}-input",
                    placeholder="输入问题，例如：最近一周的测试通过率是多少？",
                    style={
                        "width": "100%",
                        "height": "80px",
                        "padding": "10px",
                        "border": "1px solid #ddd",
                        "border-radius": "5px"
                    }
                ),
                html.Button(
                    "发送",
                    id=f"{chat_id_prefix}-submit",
                    n_clicks=0,
                    style={
                        "margin-top": "10px",
                        "padding": "8px 20px",
                        "background-color": "#007bff",
                        "color": "white",
                        "border": "none",
                        "border-radius": "5px",
                        "cursor": "pointer"
                    }
                )
            ])
        ], style={"max-width": "800px", "margin": "20px auto"})
    ])
    
    # 注册回调
    @app.callback(
        [
            Output(f"{chat_id_prefix}-messages", "children"),
            Output(f"{chat_id_prefix}-input", "value")
        ],
        [
            Input(f"{chat_id_prefix}-submit", "n_clicks")
        ],
        [
            State(f"{chat_id_prefix}-input", "value")
        ]
    )
    def update_chat(n_clicks, user_input):
        if not user_input or not user_input.strip():
            return chat_data["messages"], ""
        
        # 添加用户消息
        chat_data["messages"].append(html.Div([
            html.Strong("你："),
            html.Span(user_input)
        ], style={"margin-bottom": "10px", "color": "#333"}))
        
        # 调用 AI 回答
        result = chat_manager.ask(user_input)
        
        # 添加 AI 消息
        ai_message_parts = [
            html.Strong("AI："),
            html.Span(result["answer"])
        ]
        
        # 如果有 SQL 查询，显示 SQL
        if result.get("sql"):
            ai_message_parts.append(html.Div([
                html.Strong("SQL："),
                html.Code(result["sql"], style={
                    "background": "#f5f5f5",
                    "padding": "5px",
                    "border-radius": "3px",
                    "display": "block",
                    "margin-top": "5px"
                })
            ]))
        
        # 如果有数据，显示数据预览
        if result.get("data") is not None and not result["data"].empty:
            ai_message_parts.append(html.Div([
                html.Strong("数据预览："),
                html.Table([
                    html.Thead([html.Tr([html.Th(col) for col in result["data"].columns])]),
                    html.Tbody([
                        html.Tr([html.Td(str(val)) for val in row])
                        for row in result["data"].head(5).values.tolist()
                    ])
                ])
            ]))
        
        chat_data["messages"].append(html.Div(ai_message_parts, style={
            "margin-bottom": "10px",
            "padding": "10px",
            "background": "#f0f0f0",
            "border-radius": "5px"
        }))
        
        return chat_data["messages"], ""
    
    return chat_container


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AI Chat with SQL 测试")
    parser.add_argument("--question", "-q", type=str, help="测试问题")
    parser.add_argument("--db", "-d", type=str, default="database/local_data.db", help="数据库路径")
    
    args = parser.parse_args()
    
    # 创建聊天实例
    chat = AIChatWithSQL(db_path=args.db)
    
    # 测试问题
    if args.question:
        print("=" * 60)
        print(f"问题: {args.question}")
        print("=" * 60)
        
        result = chat.ask(args.question)
        
        print("\n回答:")
        print(result["answer"])
        
        if result.get("sql"):
            print(f"\nSQL:\n{result['sql']}")
        
        if result.get("data") is not None:
            print(f"\n数据:\n{result['data'].to_string(index=False)}")
    else:
        # 交互式测试
        print("AI Chat with SQL - 交互式测试")
        print("输入问题，输入 'quit' 退出")
        print("=" * 60)
        
        while True:
            question = input("\n你: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("再见！")
                break
            
            if not question:
                continue
            
            result = chat.ask(question)
            
            print(f"\nAI: {result['answer']}")
            
            if result.get("sql"):
                print(f"\n[SQL] {result['sql']}")
            
            if result.get("data") is not None and not result["data"].empty:
                print(f"\n[数据]")
                print(result["data"].to_string(index=False))
