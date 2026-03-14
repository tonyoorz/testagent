"""
Code Interpreter Agent - 核心智能体类
实现 ReAct 框架 + Tool Calling 的混合架构
"""

import os
import json
import time
import logging
import re
from typing import Dict, List, Any, Optional, Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime
import traceback

# 导入工具模块
from .tools import (
    query_database,
    execute_python_code,
    calculate_risk_score,
    analyze_trend,
    generate_chart,
    get_database_schema
)
from .prompts import SYSTEM_PROMPT, TOOL_DESCRIPTIONS
from .db_connector import DatabaseConnector

# 尝试导入 DeepSeek API 配置
try:
    from ai_chat_manager import (
        DEEPSEEK_API_KEY,
        DEEPSEEK_API_BASE,
        DEEPSEEK_MODEL,
        DeepSeekStreamingChat
    )
    HAS_DEEPSEEK = True
except ImportError:
    HAS_DEEPSEEK = False
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Agent 状态管理"""
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    current_step: int = 0
    max_steps: int = 10
    reasoning_trace: List[str] = field(default_factory=list)
    final_answer: str = ""
    is_complete: bool = False
    error: Optional[str] = None


@dataclass
class ToolCall:
    """工具调用结构"""
    tool_name: str
    arguments: Dict[str, Any]
    reasoning: str = ""


class CodeInterpreterAgent:
    """
    Code Interpreter Agent - 数据分析智能体
    
    核心能力：
    1. 理解用户意图并规划分析步骤
    2. 动态生成 SQL 查询数据库
    3. 生成并执行 Python 代码进行复杂分析
    4. 多步推理，支持 ReAct 循环
    5. 流式返回结果和推理过程
    
    使用示例：
    ```python
    agent = CodeInterpreterAgent(db_path="path/to/database.db")
    
    # 同步调用
    result = agent.run("最近两周哪个模块风险最高？")
    
    # 流式调用
    for chunk in agent.stream("分析 ABS 模块的缺陷趋势"):
        print(chunk)
    ```
    """
    
    def __init__(
        self,
        db_path: str = None,
        api_key: str = None,
        api_base: str = None,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4000,
        max_steps: int = 10,
        enable_code_execution: bool = True,
        enable_sql_query: bool = True
    ):
        """
        初始化 Agent
        
        Args:
            db_path: SQLite 数据库路径
            api_key: DeepSeek API Key (可选，默认从环境变量读取)
            api_base: API Base URL
            model: 模型名称
            temperature: 生成温度
            max_tokens: 最大 token 数
            max_steps: 最大推理步数
            enable_code_execution: 是否启用代码执行
            enable_sql_query: 是否启用 SQL 查询
        """
        # API 配置
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.api_base = api_base or DEEPSEEK_API_BASE
        self.model = model or DEEPSEEK_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Agent 配置
        self.max_steps = max_steps
        self.enable_code_execution = enable_code_execution
        self.enable_sql_query = enable_sql_query
        
        # 数据库连接
        self.db_path = db_path or os.environ.get(
            "DATABASE_PATH",
            os.path.join(os.path.dirname(__file__), "..", "database", "local_data.db")
        )
        self.db_connector = DatabaseConnector(self.db_path)
        
        # LLM 客户端
        if HAS_DEEPSEEK:
            self.llm_client = DeepSeekStreamingChat(
                api_key=self.api_key,
                api_base=self.api_base,
                model=self.model
            )
        else:
            self.llm_client = None
            logger.warning("DeepSeekStreamingChat not available, will use fallback mode")
        
        # 工具注册
        self.tools = self._register_tools()
        
        # 状态管理
        self.state = AgentState(max_steps=max_steps)
        
        logger.info(f"CodeInterpreterAgent initialized with db: {self.db_path}")
    
    def _register_tools(self) -> Dict[str, Callable]:
        """注册可用工具"""
        tools = {}
        
        # 数据库查询工具
        if self.enable_sql_query:
            tools["query_database"] = lambda sql: query_database(
                sql, 
                db_connector=self.db_connector
            )
            tools["get_schema"] = lambda: get_database_schema(self.db_connector)
        
        # Python 代码执行工具
        if self.enable_code_execution:
            tools["execute_python"] = lambda code, data=None: execute_python_code(
                code,
                data=data,
                db_connector=self.db_connector
            )
        
        # 分析工具
        tools["calculate_risk_score"] = lambda **kwargs: calculate_risk_score(
            db_connector=self.db_connector,
            **kwargs
        )
        tools["analyze_trend"] = lambda **kwargs: analyze_trend(
            db_connector=self.db_connector,
            **kwargs
        )
        tools["generate_chart"] = lambda **kwargs: generate_chart(**kwargs)
        
        return tools
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词，包含数据库 Schema"""
        schema_info = get_database_schema(self.db_connector)
        
        prompt = SYSTEM_PROMPT.format(
            db_schema=schema_info,
            tool_descriptions=TOOL_DESCRIPTIONS,
            current_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        return prompt
    
    def _parse_tool_call(self, response: str) -> Optional[ToolCall]:
        """
        从 LLM 响应中解析工具调用
        
        支持格式：
        1. JSON 格式: {"tool": "tool_name", "arguments": {...}}
        2. XML 格式: <tool>name</tool><args>{...}</args>
        3. 自然语言格式（需要智能解析）
        """
        # 尝试解析 JSON 格式
        json_pattern = r'```json\s*(.*?)\s*```'
        json_matches = re.findall(json_pattern, response, re.DOTALL)
        
        for match in json_matches:
            try:
                data = json.loads(match)
                if "tool" in data or "function" in data:
                    return ToolCall(
                        tool_name=data.get("tool") or data.get("function"),
                        arguments=data.get("arguments") or data.get("parameters") or {},
                        reasoning=data.get("reasoning", "")
                    )
            except json.JSONDecodeError:
                continue
        
        # 尝试解析内嵌 JSON
        try:
            # 查找可能的 JSON 对象
            json_obj_pattern = r'\{[^{}]*"tool"[^{}]*\}|\{[^{}]*"function"[^{}]*\}'
            matches = re.findall(json_obj_pattern, response)
            for match in matches:
                data = json.loads(match)
                if "tool" in data or "function" in data:
                    return ToolCall(
                        tool_name=data.get("tool") or data.get("function"),
                        arguments=data.get("arguments") or data.get("parameters") or {}
                    )
        except (json.JSONDecodeError, KeyError):
            pass
        
        # 尝试解析 XML 格式
        tool_match = re.search(r'<tool>(.*?)</tool>', response)
        args_match = re.search(r'<args>(.*?)</args>', response, re.DOTALL)
        
        if tool_match:
            tool_name = tool_match.group(1).strip()
            arguments = {}
            if args_match:
                try:
                    arguments = json.loads(args_match.group(1))
                except json.JSONDecodeError:
                    pass
            return ToolCall(tool_name=tool_name, arguments=arguments)
        
        return None
    
    def _execute_tool(self, tool_call: ToolCall) -> Dict[str, Any]:
        """执行工具调用"""
        tool_name = tool_call.tool_name
        arguments = tool_call.arguments
        
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")
        
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}. Available tools: {list(self.tools.keys())}"
            }
        
        try:
            result = self.tools[tool_name](**arguments)
            return {
                "success": True,
                "result": result,
                "tool": tool_name
            }
        except Exception as e:
            logger.error(f"Tool execution error: {e}\n{traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "tool": tool_name
            }
    
    def _build_messages(self, user_input: str) -> List[Dict[str, str]]:
        """构建消息列表"""
        messages = [
            {"role": "system", "content": self._build_system_prompt()}
        ]
        
        # 添加对话历史
        messages.extend(self.state.conversation_history)
        
        # 添加当前用户输入
        messages.append({"role": "user", "content": user_input})
        
        return messages
    
    def _should_continue(self, response: str) -> bool:
        """判断是否需要继续推理"""
        # 检查是否包含最终答案标记
        if "<final_answer>" in response.lower() or "最终答案:" in response:
            return False
        
        # 检查是否达到最大步数
        if self.state.current_step >= self.max_steps:
            return False
        
        # 检查是否包含工具调用
        tool_call = self._parse_tool_call(response)
        if tool_call:
            return True
        
        # 如果响应以问号结尾或包含"需要更多信息"，可能需要继续
        if response.strip().endswith("?") or "需要更多信息" in response:
            return True
        
        return False
    
    def _extract_final_answer(self, response: str) -> str:
        """提取最终答案"""
        # 尝试提取 <final_answer> 标签内容
        match = re.search(r'<final_answer>(.*?)</final_answer>', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 尝试提取 "最终答案:" 后的内容
        match = re.search(r'最终答案[：:]\s*(.*?)(?=\n\n|$)', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 否则返回整个响应
        return response.strip()
    
    def run(self, user_input: str) -> str:
        """
        同步执行 Agent
        
        Args:
            user_input: 用户输入
            
        Returns:
            最终答案
        """
        # 重置状态
        self.state = AgentState(max_steps=self.max_steps)
        self.state.conversation_history.append({"role": "user", "content": user_input})
        
        current_input = user_input
        
        while not self.state.is_complete and self.state.current_step < self.max_steps:
            self.state.current_step += 1
            logger.info(f"Step {self.state.current_step}")
            
            # 获取 LLM 响应
            messages = self._build_messages(current_input)
            
            try:
                if self.llm_client:
                    response = self.llm_client.get_simple_response(
                        messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    )
                else:
                    response = self._fallback_response(current_input)
                
                # 记录推理过程
                self.state.reasoning_trace.append(f"Step {self.state.current_step}: {response[:200]}...")
                
                # 解析工具调用
                tool_call = self._parse_tool_call(response)
                
                if tool_call:
                    # 执行工具
                    tool_result = self._execute_tool(tool_call)
                    self.state.tool_results.append(tool_result)
                    
                    # 将工具结果添加到对话历史
                    self.state.conversation_history.append({
                        "role": "assistant",
                        "content": response
                    })
                    self.state.conversation_history.append({
                        "role": "user",
                        "content": f"工具执行结果: {json.dumps(tool_result, ensure_ascii=False, indent=2)}"
                    })
                    
                    current_input = f"基于工具执行结果继续分析: {json.dumps(tool_result, ensure_ascii=False)}"
                else:
                    # 没有工具调用，检查是否完成
                    if not self._should_continue(response):
                        self.state.final_answer = self._extract_final_answer(response)
                        self.state.is_complete = True
                    else:
                        self.state.conversation_history.append({
                            "role": "assistant",
                            "content": response
                        })
                        current_input = "请继续分析并给出最终结论"
                        
            except Exception as e:
                logger.error(f"Agent execution error: {e}\n{traceback.format_exc()}")
                self.state.error = str(e)
                self.state.is_complete = True
                self.state.final_answer = f"分析过程中出现错误: {str(e)}"
        
        return self.state.final_answer
    
    def stream(self, user_input: str) -> Generator[str, None, None]:
        """
        流式执行 Agent
        
        Args:
            user_input: 用户输入
            
        Yields:
            流式响应块
        """
        # 重置状态
        self.state = AgentState(max_steps=self.max_steps)
        self.state.conversation_history.append({"role": "user", "content": user_input})
        
        current_input = user_input
        task_id = f"agent_{int(time.time())}"
        
        yield f"data: {json.dumps({'type': 'start', 'message': '开始分析...', 'task_id': task_id})}\n\n"
        
        while not self.state.is_complete and self.state.current_step < self.max_steps:
            self.state.current_step += 1
            
            yield f"data: {json.dumps({'type': 'step', 'step': self.state.current_step, 'max_steps': self.max_steps})}\n\n"
            
            messages = self._build_messages(current_input)
            
            try:
                if self.llm_client:
                    # 流式获取响应
                    full_response = ""
                    for chunk in self.llm_client.stream_chat_response_optimized(
                        messages,
                        task_id=task_id,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    ):
                        if chunk.startswith("content:"):
                            content = chunk[8:]
                            full_response += content
                            yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                        elif chunk.startswith("reasoning:"):
                            reasoning = chunk[10:]
                            yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning})}\n\n"
                        elif chunk.startswith("error:"):
                            error = chunk[6:]
                            yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"
                    
                    response = full_response
                else:
                    response = self._fallback_response(current_input)
                    yield f"data: {json.dumps({'type': 'content', 'content': response})}\n\n"
                
                # 解析并执行工具
                tool_call = self._parse_tool_call(response)
                
                if tool_call:
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_call.tool_name, 'arguments': tool_call.arguments})}\n\n"
                    
                    tool_result = self._execute_tool(tool_call)
                    self.state.tool_results.append(tool_result)
                    
                    yield f"data: {json.dumps({'type': 'tool_result', 'result': tool_result})}\n\n"
                    
                    self.state.conversation_history.append({"role": "assistant", "content": response})
                    self.state.conversation_history.append({
                        "role": "user",
                        "content": f"工具执行结果: {json.dumps(tool_result, ensure_ascii=False, indent=2)}"
                    })
                    
                    current_input = f"基于工具执行结果继续分析"
                else:
                    if not self._should_continue(response):
                        final_answer = self._extract_final_answer(response)
                        self.state.final_answer = final_answer
                        self.state.is_complete = True
                        
                        yield f"data: {json.dumps({'type': 'final_answer', 'content': final_answer})}\n\n"
                    else:
                        self.state.conversation_history.append({"role": "assistant", "content": response})
                        current_input = "请继续分析并给出最终结论"
                        
            except Exception as e:
                logger.error(f"Stream execution error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break
        
        yield f"data: {json.dumps({'type': 'done', 'message': '分析完成'})}\n\n"
    
    def _fallback_response(self, user_input: str) -> str:
        """
        降级响应（当 LLM 不可用时）
        """
        # 简单的关键词匹配
        if "风险" in user_input or "risk" in user_input.lower():
            return json.dumps({
                "tool": "calculate_risk_score",
                "arguments": {},
                "reasoning": "用户询问风险相关内容，调用风险计算工具"
            })
        
        if "趋势" in user_input or "trend" in user_input.lower():
            return json.dumps({
                "tool": "analyze_trend",
                "arguments": {},
                "reasoning": "用户询问趋势相关内容，调用趋势分析工具"
            })
        
        if "图表" in user_input or "chart" in user_input.lower():
            return json.dumps({
                "tool": "generate_chart",
                "arguments": {},
                "reasoning": "用户请求生成图表"
            })
        
        # 默认查询数据库
        return json.dumps({
            "tool": "query_database",
            "arguments": {"sql": "SELECT * FROM defects LIMIT 10"},
            "reasoning": "查询最近的缺陷数据"
        })
    
    def get_state(self) -> Dict[str, Any]:
        """获取当前 Agent 状态"""
        return {
            "current_step": self.state.current_step,
            "max_steps": self.state.max_steps,
            "is_complete": self.state.is_complete,
            "error": self.state.error,
            "tool_results_count": len(self.state.tool_results),
            "conversation_length": len(self.state.conversation_history)
        }
    
    def reset(self):
        """重置 Agent 状态"""
        self.state = AgentState(max_steps=self.max_steps)
        logger.info("Agent state reset")
