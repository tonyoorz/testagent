"""
Unified Execution Engine — 统一 ReAct 执行引擎

把 rule 模式和 agentic 模式统一成一个 ReAct 循环：
- rule 模式：planner 预先决定步骤 → 顺序执行 → 不动态调整
- agentic 模式：LLM 动态决策下一步 → 支持条件分支和重试

核心抽象：
1. Decision：决定下一步做什么（用哪个工具 + 参数）
2. Action：执行工具
3. Observation：观察结果，决定是否继续

所有模式共享：
- Tracer 可观测性
- Self-Correction 错误修正
- Query Memory 记忆
- Guardrails 安全检查
- Streaming 事件流

用法：
    engine = UnifiedExecutionEngine(agent)
    result = engine.run(question, data, mode="auto")
"""

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

# 导入四层架构模块
try:
    from agent.core.tool_retriever import ToolRetriever, DEFAULT_TOP_K
    from agent.core.few_shot_templates import get_relevant_templates, format_templates_for_prompt
    from agent.core.tool_call_guardrails import ToolCallGuardrail, GuardrailResult
    from agent.core.retry_strategy import RetryStrategy, ErrorCategory
    LAYER_MODULES_AVAILABLE = True
except ImportError:
    LAYER_MODULES_AVAILABLE = False
    logger.warning("四层架构模块未完全可用，部分功能降级")

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """决策类型。"""
    USE_TOOL = "use_tool"       # 调用工具
    RESPOND = "respond"         # 直接回答
    REPLAN = "replan"           # 重新规划
    GIVE_UP = "give_up"         # 放弃


@dataclass
class Decision:
    """一次决策。"""
    type: DecisionType
    tool: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    reasoning: str = ""


@dataclass
class StepResult:
    """一步执行的结果。"""
    tool: str
    params: Dict[str, Any]
    success: bool
    result: Any = None
    error: str = ""
    duration_ms: int = 0
    corrected: bool = False  # 是否经过了self-correction
    error_category: str = ""  # 错误分类（Layer 4）
    retry_count: int = 0  # 重试次数（Layer 4）
    warnings: List[str] = field(default_factory=list)  # 警告信息（Layer 3 后置校验）


@dataclass
class ExecutionResult:
    """整个执行过程的结果。"""
    success: bool
    steps: List[StepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    mode_used: str = "rule"  # rule / agentic / hybrid
    stop_reason: str = ""
    answer_text: str = ""


class RuleDecider:
    """Rule模式的决策器：按预设计划顺序执行。"""

    def __init__(self, plan: List[Dict[str, Any]]):
        self._plan = plan or []
        self._index = 0

    def next_decision(self, observations: List[StepResult]) -> Decision:
        """返回下一步决策。"""
        if self._index >= len(self._plan):
            return Decision(type=DecisionType.RESPOND)

        step = self._plan[self._index]
        self._index += 1

        # 如果上一步失败且是关键工具，考虑跳过
        if observations:
            last = observations[-1]
            if not last.success:
                # 非关键工具继续，关键工具停止
                optional_tools = {"describe_dataset", "statistical_summary", "consult_semantic_catalog"}
                if last.tool not in optional_tools:
                    # 尝试继续执行剩余步骤
                    pass

        return Decision(
            type=DecisionType.USE_TOOL,
            tool=step.get("tool"),
            params=step.get("params", {}),
            description=step.get("description", ""),
        )

    @property
    def remaining(self) -> int:
        return len(self._plan) - self._index


class AgenticDecider:
    """Agentic模式的决策器：LLM动态决定下一步。"""

    def __init__(self, llm_client, llm_model, tool_specs, question, data_summary, max_iters=6, tool_call_max=8):
        self._client = llm_client
        self._model = llm_model
        self._all_tool_specs = tool_specs  # 保存全量 specs
        self._tool_specs = tool_specs  # 当前使用的 specs（会被过滤）
        self._question = question
        self._data_summary = data_summary
        self._max_iters = max_iters
        self._tool_call_max = tool_call_max
        self._iteration = 0
        self._tool_calls_used = 0
        self._messages = []
        self._final_text = ""

        # Layer 2: 工具检索器和 Few-shot 模板
        self._tool_retriever = None
        self._few_shot_templates = []
        if LAYER_MODULES_AVAILABLE:
            self._tool_retriever = ToolRetriever(self._all_tool_specs)
            self._few_shot_templates = get_relevant_templates(question, top_k=3)
            # 过滤工具 specs
            selected_tools = self._tool_retriever.retrieve(question, top_k=DEFAULT_TOP_K)
            selected_set = set(selected_tools)
            filtered_specs = []
            for spec in self._all_tool_specs:
                func = (spec.get("function") or spec) if isinstance(spec, dict) else {}
                if func.get("name") in selected_set:
                    filtered_specs.append(spec)
            self._tool_specs = filtered_specs if filtered_specs else self._all_tool_specs

    def next_decision(self, observations: List[StepResult]) -> Decision:
        """让LLM决定下一步。"""
        self._iteration += 1

        if self._iteration > self._max_iters:
            return Decision(type=DecisionType.RESPOND, reasoning="max_iterations_reached")

        # 构建上下文
        if self._iteration == 1:
            sys_prompt = self._build_system_prompt()
            self._messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": self._question},
            ]
        else:
            # 附加观察结果
            obs_text = self._format_observations(observations)
            self._messages.append({"role": "user", "content": obs_text})

        # 调用LLM
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                tools=self._tool_specs,
                temperature=0.1,
            )

            choices = getattr(response, "choices", None)
            if not choices:
                return Decision(type=DecisionType.GIVE_UP, reasoning="no choices")

            message = choices[0].message
            content = str(getattr(message, "content", "") or "").strip()
            if content:
                self._final_text = content

            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                return Decision(
                    type=DecisionType.RESPOND,
                    reasoning="model_final_answer",
                )

            # 只处理第一个tool call（逐步执行，而不是一次全部）
            import json
            tc = tool_calls[0]
            tool_name = str(getattr(getattr(tc, "function", None), "name", "") or "").strip()
            args_text = str(getattr(getattr(tc, "function", None), "arguments", "") or "").strip()

            if not tool_name:
                return Decision(type=DecisionType.RESPOND)

            self._tool_calls_used += 1
            if self._tool_calls_used > self._tool_call_max:
                return Decision(type=DecisionType.GIVE_UP, reasoning="tool_budget_exhausted")

            try:
                args = json.loads(args_text) if args_text else {}
            except Exception:
                args = {}

            # 附加assistant message到历史
            self._messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [{"id": getattr(tc, "id", ""), "type": "function",
                                "function": {"name": tool_name, "arguments": args_text}}],
            })

            return Decision(
                type=DecisionType.USE_TOOL,
                tool=tool_name,
                params=args if isinstance(args, dict) else {},
                reasoning=f"agentic iter {self._iteration}",
            )

        except Exception as e:
            return Decision(type=DecisionType.GIVE_UP, reasoning=str(e))

    @property
    def final_text(self) -> str:
        return self._final_text

    def _build_system_prompt(self) -> str:
        prompt = """你是汽车测试/缺陷数据分析助手。基于工具返回的真实结果逐步决策。

核心规则：
1. 只使用提供的工具，不要编造数据
2. 先理解问题，再选择工具
3. 如果工具失败，尝试其他工具或参数
4. 给出结论时说明数据依据
5. 提供可操作的建议

分析要求：
- 不要只报告数据，要解释"为什么"和"怎么办"
- 发现异常时，主动对比前后周期找原因
- 对高风险问题，给出具体改进建议
"""
        if self._data_summary:
            prompt += f"\n\n数据摘要:\n{self._data_summary}"

        # Layer 2: 注入 Few-shot 模板
        if LAYER_MODULES_AVAILABLE and self._few_shot_templates:
            prompt += format_templates_for_prompt(self._few_shot_templates)

        return prompt

    def _format_observations(self, observations: List[StepResult]) -> str:
        parts = [f"第{self._iteration - 1}轮工具执行结果："]
        for obs in observations[-3:]:  # 只保留最近3个
            status = "成功" if obs.success else "失败"
            preview = str(obs.result)[:200] if obs.success else obs.error[:200]
            parts.append(f"- {obs.tool}: {status}; 摘要={preview}")
        parts.append("请基于以上真实结果继续：若信息足够请直接给结论，否则继续调用工具。")
        return "\n".join(parts)


class UnifiedExecutionEngine:
    """统一执行引擎 — 所有模式共享同一个执行循环。"""

    def __init__(self, agent):
        self._agent = agent
        # Layer 3/4: 初始化护栏和重试策略
        self._tool_guardrail = ToolCallGuardrail() if LAYER_MODULES_AVAILABLE else None
        self._retry_strategy = RetryStrategy() if LAYER_MODULES_AVAILABLE else None

    def run(
        self,
        question: str,
        data: Any,
        context: Dict[str, Any],
        mode: str = "rule",
        plan: Optional[List[Dict[str, Any]]] = None,
        progress_cb: Optional[Callable] = None,
        tracer: Any = None,
    ) -> ExecutionResult:
        """执行分析任务。

        Args:
            question: 用户问题
            data: 数据（DataFrame 或 dict）
            context: 上下文
            mode: 执行模式 (rule/agentic/hybrid)
            plan: 预设计划（rule模式必需）
            progress_cb: 进度回调
            tracer: Tracer 实例
        """
        start_time = time.perf_counter()
        steps: List[StepResult] = []

        # 创建决策器
        decider = self._create_decider(mode, plan, question, context)

        # 执行循环
        max_steps = int(os.getenv("AGENT_MAX_EXECUTION_STEPS", "20") or 20)

        for step_idx in range(max_steps):
            # 1. 决策
            decision = decider.next_decision(steps)

            if decision.type == DecisionType.RESPOND:
                break
            elif decision.type == DecisionType.GIVE_UP:
                break
            elif decision.type == DecisionType.REPLAN:
                # TODO: 支持重新规划
                break
            elif decision.type != DecisionType.USE_TOOL:
                break

            # 2. 执行
            if progress_cb:
                try:
                    progress_cb({"event": "tool_start", "step_index": step_idx + 1, "tool": decision.tool})
                except Exception:
                    pass

            step_result = self._execute_tool(
                tool_name=decision.tool,
                params=decision.params,
                data=data,
                context=context,
                question=question,
                tracer=tracer,
            )
            steps.append(step_result)

            if progress_cb:
                try:
                    progress_cb({
                        "event": "tool_end",
                        "step_index": step_idx + 1,
                        "tool": decision.tool,
                        "success": step_result.success,
                        "duration_ms": step_result.duration_ms,
                    })
                except Exception:
                    pass

        # 获取最终文本（agentic模式）
        answer_text = ""
        if isinstance(decider, AgenticDecider):
            answer_text = decider.final_text

        total_ms = int((time.perf_counter() - start_time) * 1000)

        return ExecutionResult(
            success=any(s.success for s in steps),
            steps=steps,
            total_duration_ms=total_ms,
            mode_used=mode,
            stop_reason=decision.reasoning if decision else "completed",
            answer_text=answer_text,
        )

    def _create_decider(self, mode: str, plan, question, context) -> Any:
        """创建对应模式的决策器。"""
        if mode == "agentic":
            llm = self._agent.tool_executor._llm
            if not llm or not getattr(llm, "client", None):
                logger.warning("Agentic模式无LLM，降级为rule模式")
                return RuleDecider(plan or [])

            from agent.core.agentic_runtime import build_tool_specs
            tools_schema = self._agent.tool_executor.get_tool_schema() or {}
            tool_specs = build_tool_specs(tools_schema)

            return AgenticDecider(
                llm_client=llm.client,
                llm_model=getattr(llm, "model", None),
                tool_specs=tool_specs,
                question=question,
                data_summary=str(context.get("data_summary") or ""),
            )
        else:
            # rule / hybrid 都用预设计划
            return RuleDecider(plan or [])

    def _execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        data: Any,
        context: Dict[str, Any],
        question: str,
        tracer: Any = None,
    ) -> StepResult:
        """执行单个工具，集成四层架构：
        - Layer 3: 执行前参数校验 + 后置结果校验
        - Layer 4: 智能重试 + 错误分类
        """
        t0 = time.perf_counter()
        retry_count = 0
        error_category = ""
        warnings = []

        # Layer 3: 执行前校验
        if self._tool_guardrail:
            tool_descriptor = self._get_tool_descriptor(tool_name)
            guard_result = self._tool_guardrail.check_tool_call(tool_name, params, tool_descriptor)
            if not guard_result.passed:
                return StepResult(
                    tool=tool_name,
                    params=params,
                    success=False,
                    error=f"护栏拦截: {guard_result.message}",
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    corrected=False,
                    error_category=ErrorCategory.FATAL.value,
                    warnings=guard_result.error_details,
                )

        # Tracer span
        _span = None
        if tracer and hasattr(tracer, "span"):
            _span = tracer.span(tool_name).__enter__()

        # 执行 + Layer 4: 智能重试
        result = None
        error_msg = ""
        success = False
        corrected = False

        while retry_count <= 1:  # 最多重试1次（可配置）
            try:
                result = self._agent.tool_executor.execute_tool(tool_name, data, **params)
            except Exception as e:
                result = {"success": False, "tool": tool_name, "error": str(e)}

            success = isinstance(result, dict) and result.get("success") is True
            error_msg = "" if success else (str(result.get("error", "")) if isinstance(result, dict) else str(result))

            if success:
                break

            # Layer 4: 错误分类 + 决定是否重试
            if self._retry_strategy:
                error_info = self._retry_strategy.should_retry(tool_name, error_msg, retry_count)
                error_category = error_info.category.value

                if not error_info.retryable:
                    break

                # RETRYABLE/REPHRASE → 重试
                if retry_count == 0:
                    logger.info(f"工具 {tool_name} 失败，准备重试: {error_msg}")
                    if self._retry_strategy.need_cooldown():
                        self._retry_strategy.cooldown()
                    retry_count += 1
                    continue

            # 不重试，跳出循环
            break

        if _span:
            _span.__exit__(None, None, None)

        # Self-Correction (原有逻辑，保留)
        if not success and not corrected:
            corrector = getattr(self._agent, "_self_corrector", None)
            if corrector is not None:
                try:
                    corrected_result = corrector.try_correct(
                        tool_name=tool_name,
                        original_params=params,
                        error_message=error_msg,
                        context=context,
                        data=data,
                        available_tools=getattr(self._agent.tool_executor, "tools", {}),
                    )
                    if isinstance(corrected_result, dict) and corrected_result.get("success") is True:
                        result = corrected_result
                        success = True
                        corrected = True
                        logger.info(f"Self-correction succeeded for {tool_name}")
                except Exception as e:
                    logger.debug(f"Self-correction skipped: {e}")

        # Layer 3: 后置结果校验
        if success and self._tool_guardrail:
            sanity_result = self._tool_guardrail.check_result_sanity(tool_name, result, params)
            if sanity_result.risk_level.value != "safe":
                warnings.append(sanity_result.message)

        duration_ms = int((time.perf_counter() - t0) * 1000)

        # 记录重试
        if retry_count > 0 and self._retry_strategy:
            self._retry_strategy.record_retry(tool_name)

        return StepResult(
            tool=tool_name,
            params=params,
            success=success,
            result=result,
            error="" if success else error_msg,
            duration_ms=duration_ms,
            corrected=corrected,
            error_category=error_category,
            retry_count=retry_count,
            warnings=warnings,
        )

    def _get_tool_descriptor(self, tool_name: str) -> Any:
        """获取工具描述符。"""
        if hasattr(self._agent.tool_executor, "_tool_registry"):
            from agent.tools.registry import get_registry
            return get_registry().get(tool_name)
        return None
