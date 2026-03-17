"""
钩子系统与追踪系统 - Hooks & Tracing

实现类似 Claude Code 的钩子机制和结构化追踪：

钩子系统：
- pre_run: 执行前
- post_run: 执行后
- pre_tool_call: 工具调用前
- post_tool_call: 工具调用后
- on_error: 错误处理
- on_handoff: Agent 交接时

追踪系统：
- Span: 结构化追踪单元
- Trace: 完整追踪链
- 可视化: 生成追踪报告

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
import traceback

logger = logging.getLogger(__name__)


# ============================================================================
# 枚举和数据类
# ============================================================================

class HookType(Enum):
    """钩子类型"""
    PRE_RUN = "pre_run"
    POST_RUN = "post_run"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    ON_ERROR = "on_error"
    ON_HANDOFF = "on_handoff"
    ON_REFLECTION = "on_reflection"


class SpanStatus(Enum):
    """Span 状态"""
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class HookContext:
    """钩子上下文"""
    hook_type: HookType
    agent_name: str
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """钩子执行结果"""
    success: bool
    message: str = ""
    modified_data: Optional[Dict] = None
    should_continue: bool = True  # 是否继续执行


@dataclass
class Span:
    """
    追踪单元
    
    类似 OpenTelemetry Span，记录一个操作的完整信息
    """
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.STARTED
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    children: List["Span"] = field(default_factory=list)
    
    def end(self, status: SpanStatus = SpanStatus.COMPLETED):
        """结束 Span"""
        self.end_time = time.time()
        self.status = status
    
    def add_event(self, name: str, attributes: Dict = None):
        """添加事件"""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {}
        })
    
    def set_attribute(self, key: str, value: Any):
        """设置属性"""
        self.attributes[key] = value
    
    @property
    def duration(self) -> float:
        """计算耗时"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "children": [c.to_dict() for c in self.children]
        }


@dataclass
class Trace:
    """完整追踪链"""
    trace_id: str
    root_span: Optional[Span] = None
    spans: List[Span] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_span(self, span: Span):
        """添加 Span"""
        self.spans.append(span)
    
    def get_span(self, span_id: str) -> Optional[Span]:
        """获取 Span"""
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "metadata": self.metadata,
            "spans": [s.to_dict() for s in self.spans],
            "root_span": self.root_span.to_dict() if self.root_span else None
        }


# ============================================================================
# 钩子管理器
# ============================================================================

class HookManager:
    """钩子管理器"""
    
    def __init__(self):
        self.hooks: Dict[HookType, List[Callable]] = {
            hook_type: [] for hook_type in HookType
        }
    
    def register(self, hook_type: HookType, func: Callable) -> str:
        """
        注册钩子
        
        Args:
            hook_type: 钩子类型
            func: 钩子函数
            
        Returns:
            钩子ID
        """
        hook_id = str(uuid.uuid4())[:8]
        self.hooks[hook_type].append((hook_id, func))
        logger.info(f"注册钩子: {hook_type.value} -> {func.__name__} (id: {hook_id})")
        return hook_id
    
    def unregister(self, hook_type: HookType, hook_id: str):
        """注销钩子"""
        self.hooks[hook_type] = [
            (h_id, func) for h_id, func in self.hooks[hook_type]
            if h_id != hook_id
        ]
    
    def execute(self, hook_type: HookType, context: HookContext) -> HookResult:
        """
        执行钩子
        
        Args:
            hook_type: 钩子类型
            context: 钩子上下文
            
        Returns:
            钩子执行结果
        """
        results = []
        
        for hook_id, func in self.hooks[hook_type]:
            try:
                result = func(context)
                if isinstance(result, HookResult):
                    results.append(result)
                    if not result.should_continue:
                        break
            except Exception as e:
                logger.error(f"钩子执行失败: {hook_id} - {e}")
                results.append(HookResult(
                    success=False,
                    message=str(e),
                    should_continue=True
                ))
        
        # 合并结果
        if not results:
            return HookResult(success=True)
        
        final_result = HookResult(success=True)
        for r in results:
            if not r.success:
                final_result.success = False
            if r.modified_data:
                if final_result.modified_data is None:
                    final_result.modified_data = {}
                final_result.modified_data.update(r.modified_data)
            if not r.should_continue:
                final_result.should_continue = False
        
        return final_result


# ============================================================================
# 追踪管理器
# ============================================================================

class TracingManager:
    """追踪管理器"""
    
    def __init__(self, output_dir: str = ".traces"):
        self.output_dir = output_dir
        self.current_trace: Optional[Trace] = None
        self.current_span: Optional[Span] = None
        self.span_stack: List[Span] = []
        os.makedirs(output_dir, exist_ok=True)
    
    def start_trace(self, name: str, metadata: Dict = None) -> Trace:
        """开始新追踪"""
        trace_id = str(uuid.uuid4())
        
        trace = Trace(
            trace_id=trace_id,
            metadata=metadata or {}
        )
        
        # 创建根 Span
        root_span = Span(
            span_id=str(uuid.uuid4())[:16],
            trace_id=trace_id,
            parent_span_id=None,
            name=name,
            start_time=time.time()
        )
        
        trace.root_span = root_span
        trace.add_span(root_span)
        
        self.current_trace = trace
        self.current_span = root_span
        self.span_stack = [root_span]
        
        logger.info(f"开始追踪: {trace_id} - {name}")
        
        return trace
    
    def start_span(self, name: str, parent: Optional[Span] = None) -> Span:
        """开始新 Span"""
        if not self.current_trace:
            raise RuntimeError("没有活动的追踪")
        
        span = Span(
            span_id=str(uuid.uuid4())[:16],
            trace_id=self.current_trace.trace_id,
            parent_span_id=parent.span_id if parent else (self.current_span.span_id if self.current_span else None),
            name=name,
            start_time=time.time()
        )
        
        self.current_trace.add_span(span)
        
        # 添加到父 Span 的子列表
        if parent:
            parent.children.append(span)
        elif self.current_span:
            self.current_span.children.append(span)
        
        self.current_span = span
        self.span_stack.append(span)
        
        return span
    
    def end_span(self, span: Span, status: SpanStatus = SpanStatus.COMPLETED):
        """结束 Span"""
        span.end(status)
        
        if self.span_stack and self.span_stack[-1] == span:
            self.span_stack.pop()
            self.current_span = self.span_stack[-1] if self.span_stack else None
    
    def end_trace(self, status: SpanStatus = SpanStatus.COMPLETED) -> Trace:
        """结束追踪"""
        if not self.current_trace:
            raise RuntimeError("没有活动的追踪")
        
        # 结束所有未结束的 Span
        for span in self.current_trace.spans:
            if span.end_time is None:
                span.end(status)
        
        trace = self.current_trace
        self.current_trace = None
        self.current_span = None
        self.span_stack = []
        
        logger.info(f"结束追踪: {trace.trace_id}, 耗时: {trace.root_span.duration:.2f}s")
        
        return trace
    
    def save_trace(self, trace: Trace, filename: str = None):
        """保存追踪到文件"""
        if filename is None:
            filename = f"trace_{trace.trace_id}.json"
        
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(trace.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"追踪已保存: {filepath}")
    
    def load_trace(self, filename: str) -> Trace:
        """加载追踪"""
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        trace = Trace(trace_id=data['trace_id'], metadata=data.get('metadata', {}))
        # 重建 spans...
        
        return trace


# ============================================================================
# 带钩子和追踪的 Agent 基类
# ============================================================================

class TrackedAgent:
    """
    带追踪和钩子的 Agent 基类
    
    提供完整的生命周期钩子和追踪能力
    """
    
    def __init__(self, name: str = "tracked_agent"):
        self.name = name
        self.hook_manager = HookManager()
        self.tracing_manager = TracingManager()
    
    def register_hook(self, hook_type: HookType, func: Callable) -> str:
        """注册钩子"""
        return self.hook_manager.register(hook_type, func)
    
    def run(self, question: str, context: Optional[Dict] = None) -> Dict:
        """执行任务（带追踪和钩子）"""
        
        # 1. pre_run 钩子
        pre_context = HookContext(
            hook_type=HookType.PRE_RUN,
            agent_name=self.name,
            timestamp=datetime.now(),
            data={"question": question, "context": context}
        )
        pre_result = self.hook_manager.execute(HookType.PRE_RUN, pre_context)
        
        if not pre_result.should_continue:
            return {"error": "被钩子中断", "reason": pre_result.message}
        
        # 2. 开始追踪
        trace = self.tracing_manager.start_trace(
            name=f"{self.name}.run",
            metadata={"question": question}
        )
        
        try:
            # 3. 执行核心逻辑
            span = self.tracing_manager.start_span("execute")
            
            result = self._execute(question, context)
            
            self.tracing_manager.end_span(span)
            
            # 4. post_run 钩子
            post_context = HookContext(
                hook_type=HookType.POST_RUN,
                agent_name=self.name,
                timestamp=datetime.now(),
                data={"result": result}
            )
            self.hook_manager.execute(HookType.POST_RUN, post_context)
            
            # 5. 结束追踪
            trace = self.tracing_manager.end_trace()
            
            return result
            
        except Exception as e:
            # 错误钩子
            error_context = HookContext(
                hook_type=HookType.ON_ERROR,
                agent_name=self.name,
                timestamp=datetime.now(),
                data={"error": str(e), "traceback": traceback.format_exc()}
            )
            self.hook_manager.execute(HookType.ON_ERROR, error_context)
            
            # 结束追踪（失败状态）
            trace = self.tracing_manager.end_trace(SpanStatus.FAILED)
            
            return {"error": str(e)}
    
    def _execute(self, question: str, context: Optional[Dict]) -> Dict:
        """核心执行逻辑（子类实现）"""
        return {"answer": f"处理问题: {question}"}
    
    def call_tool(self, tool_name: str, **kwargs) -> Any:
        """调用工具（带钩子和追踪）"""
        
        # pre_tool_call 钩子
        pre_context = HookContext(
            hook_type=HookType.PRE_TOOL_CALL,
            agent_name=self.name,
            timestamp=datetime.now(),
            data={"tool_name": tool_name, "arguments": kwargs}
        )
        self.hook_manager.execute(HookType.PRE_TOOL_CALL, pre_context)
        
        # 追踪
        span = self.tracing_manager.start_span(f"tool.{tool_name}")
        
        try:
            result = self._do_call_tool(tool_name, **kwargs)
            
            # post_tool_call 钩子
            post_context = HookContext(
                hook_type=HookType.POST_TOOL_CALL,
                agent_name=self.name,
                timestamp=datetime.now(),
                data={"tool_name": tool_name, "result": result}
            )
            self.hook_manager.execute(HookType.POST_TOOL_CALL, post_context)
            
            self.tracing_manager.end_span(span)
            
            return result
            
        except Exception as e:
            self.tracing_manager.end_span(span, SpanStatus.FAILED)
            raise
    
    def _do_call_tool(self, tool_name: str, **kwargs) -> Any:
        """实际执行工具调用（子类实现）"""
        raise NotImplementedError


# ============================================================================
# 预定义钩子
# ============================================================================

def logging_hook(context: HookContext) -> HookResult:
    """日志记录钩子"""
    logger.info(f"[{context.hook_type.value}] {context.agent_name}: {context.data}")
    return HookResult(success=True)


def timing_hook(context: HookContext) -> HookResult:
    """计时钩子"""
    if context.hook_type == HookType.PRE_RUN:
        context.metadata["start_time"] = time.time()
    elif context.hook_type == HookType.POST_RUN:
        start = context.metadata.get("start_time", time.time())
        duration = time.time() - start
        logger.info(f"执行耗时: {duration:.2f}s")
    return HookResult(success=True)


def validation_hook(context: HookContext) -> HookResult:
    """验证钩子"""
    if context.hook_type == HookType.POST_RUN:
        result = context.data.get("result", {})
        if result.get("error"):
            return HookResult(
                success=False,
                message="输出包含错误",
                should_continue=True
            )
    return HookResult(success=True)


# ============================================================================
# 追踪可视化
# ============================================================================

def generate_trace_report(trace: Trace) -> str:
    """
    生成追踪报告（Markdown 格式）
    
    Args:
        trace: 追踪对象
        
    Returns:
        Markdown 格式的报告
    """
    lines = [
        f"# 追踪报告: {trace.trace_id}",
        "",
        f"## 概览",
        "",
        f"- **追踪ID**: {trace.trace_id}",
        f"- **总耗时**: {trace.root_span.duration:.2f}s" if trace.root_span else "",
        f"- **Span数量**: {len(trace.spans)}",
        "",
        "## 时间线",
        "",
    ]
    
    def render_span(span: Span, level: int = 0) -> List[str]:
        indent = "  " * level
        span_lines = [
            f"{indent}- **{span.name}** ({span.status.value})",
            f"{indent}  - 耗时: {span.duration:.3f}s",
        ]
        
        if span.attributes:
            span_lines.append(f"{indent}  - 属性:")
            for k, v in span.attributes.items():
                span_lines.append(f"{indent}    - {k}: {v}")
        
        for event in span.events:
            span_lines.append(f"{indent}  - 事件: {event['name']}")
        
        for child in span.children:
            span_lines.extend(render_span(child, level + 1))
        
        return span_lines
    
    if trace.root_span:
        lines.extend(render_span(trace.root_span))
    
    lines.extend([
        "",
        "## 详细信息",
        "",
        "```json",
        json.dumps(trace.to_dict(), indent=2, ensure_ascii=False, default=str),
        "```"
    ])
    
    return "\n".join(lines)


# ============================================================================
# 工厂函数
# ============================================================================

def create_hook_manager() -> HookManager:
    """创建钩子管理器"""
    manager = HookManager()
    
    # 注册默认钩子
    manager.register(HookType.PRE_RUN, logging_hook)
    manager.register(HookType.POST_RUN, logging_hook)
    manager.register(HookType.POST_RUN, timing_hook)
    
    return manager


def create_tracing_manager(output_dir: str = ".traces") -> TracingManager:
    """创建追踪管理器"""
    return TracingManager(output_dir=output_dir)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("钩子与追踪系统测试")
    print("=" * 70)
    
    # 创建 Agent
    agent = TrackedAgent("demo_agent")
    
    # 注册自定义钩子
    def custom_hook(context: HookContext) -> HookResult:
        print(f"🔔 钩子触发: {context.hook_type.value}")
        return HookResult(success=True)
    
    agent.register_hook(HookType.PRE_RUN, custom_hook)
    agent.register_hook(HookType.POST_RUN, custom_hook)
    
    # 执行任务
    print("\n执行任务...")
    result = agent.run("分析最近两周的缺陷趋势")
    
    print(f"\n结果: {result}")
    
    # 保存追踪
    if agent.tracing_manager.current_trace:
        trace = agent.tracing_manager.end_trace()
        agent.tracing_manager.save_trace(trace)
        
        # 生成报告
        report = generate_trace_report(trace)
        print("\n" + "=" * 70)
        print(report[:500] + "...")
