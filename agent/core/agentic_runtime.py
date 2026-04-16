import json
import logging
import time
from typing import Any, Callable, Dict, List


logger = logging.getLogger(__name__)


def _to_json_schema(params: Any) -> Dict[str, Any]:
    """Deprecated: use ToolExecutor.normalize_params_to_json_schema instead."""
    from agent.core.tool_executor import ToolExecutor
    return ToolExecutor.normalize_params_to_json_schema(params if isinstance(params, dict) else {})


def build_tool_specs(tools_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for tool_name, tool_schema in (tools_schema or {}).items():
        tool_schema = tool_schema if isinstance(tool_schema, dict) else {}
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": str(tool_name),
                    "description": str(tool_schema.get("description") or ""),
                    "parameters": _to_json_schema(tool_schema.get("parameters") or {}),
                },
            }
        )
    return specs


def run_agentic_loop(
    *,
    llm_client: Any,
    llm_model: Any,
    tool_specs: List[Dict[str, Any]],
    question: str,
    data_summary: str,
    execute_tool: Callable[[str, Dict[str, Any]], Any],
    tool_call_max: int,
    max_iters: int,
) -> Dict[str, Any]:
    sys_prompt = """你是汽车测试/缺陷数据分析助手。你必须基于工具返回的真实结果逐步决策。

核心业务知识：
1. TopIssue风险评分：8维非线性算法（Matrix指数衰减30分 + Classification 30分 + ECU转移 30分 + Domain转移 20分 + 父复杂度对数增长30分 + 子复杂度对数增长30分 + 处理周期双峰分布20分 + ShiftPU 10分）。智能组合: 高分项算术平均×1.2 + 低分项几何平均×0.8 + 非线性交互调整。>=60分为TopIssue。
2. 严重矩阵：指数衰减 score=30*exp(-0.25*order)。1A(30分)最严重，4E(≈1分)最轻。1A~3A为严重问题区域。
3. ECU乒乓效应：缺陷在不同ECU间来回转派，>=3次说明协调复杂度高。
4. 状态流转：01-New → 02-Investigation → 03-In Progress → 04-Waiting → 05-Deferred → 06-Concluded → 09-Concluded without action → 10-Closed
5. 风险等级：>=140极高 | >=100高 | >=60中(TopIssue) | >=30低 | <30无风险
6. 状态字段可能带_严重度后缀（如06-Concluded_Medium），查询时需前缀匹配
7. project/fv/pu关键字段有映射/填充逻辑：project由target_ecu三步分类，FV由Excel按top_aida映射，PU有5级填充策略

分析要求：
- 不要只报告数据，要解释"为什么"和"怎么办"
- 发现异常时，主动对比前后周期找原因
- 对高风险问题，给出具体的改进建议
- 提到TopIssue时，说明是哪个维度（严重度/高频流转/结构复杂/长期未决）拉高了分数
- 注意状态查询用前缀匹配(LIKE '06%')，不要用等值比较
"""
    if data_summary:
        sys_prompt += "\n\n数据摘要:\n" + str(data_summary)

    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": question}]
    used = 0
    final_text = ""
    stop_reason = ""
    execution_rows: List[Dict[str, Any]] = []

    for iteration in range(1, max_iters + 1):
        response = llm_client.chat.completions.create(
            model=llm_model,
            messages=messages,
            tools=tool_specs,
            temperature=0.1,
        )
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("LLM响应缺少choices（可能是网关异常、鉴权失败或上下文被服务端拒绝）")

        first_choice = choices[0] if isinstance(choices, list) else None
        if first_choice is None:
            raise RuntimeError("LLM响应choices[0]为空")

        message = getattr(first_choice, "message", None)
        if message is None:
            raise RuntimeError("LLM响应缺少message")

        content = str(getattr(message, "content", "") or "").strip()
        if content:
            final_text = content

        tool_calls = list(getattr(message, "tool_calls", None) or [])
        if not tool_calls:
            stop_reason = "model_final_answer"
            break

        tool_feedback_lines = [f"第{iteration}轮工具执行结果："]
        for tool_call in tool_calls:
            tool_name = str(getattr(getattr(tool_call, "function", None), "name", "") or "").strip()
            arguments_text = str(getattr(getattr(tool_call, "function", None), "arguments", "") or "").strip()
            if not tool_name:
                continue

            if used >= tool_call_max:
                execution_rows.append(
                    {
                        "iter": iteration,
                        "tool": tool_name,
                        "success": False,
                        "error": "工具调用预算已用尽",
                    }
                )
                tool_feedback_lines.append(f"- {tool_name}: 失败，原因=工具调用预算已用尽")
                stop_reason = "tool_budget_exhausted"
                continue

            used += 1
            try:
                args = json.loads(arguments_text) if arguments_text else {}
            except Exception:
                args = {}

            start_ts = time.perf_counter()
            output = execute_tool(tool_name, args if isinstance(args, dict) else {})
            duration_ms = int((time.perf_counter() - start_ts) * 1000)
            ok = bool(isinstance(output, dict) and output.get("success") is True)
            error = output.get("error") if isinstance(output, dict) else None

            execution_rows.append(
                {
                    "iter": iteration,
                    "tool": tool_name,
                    "dataset": (args or {}).get("dataset") if isinstance(args, dict) else None,
                    "params": args if isinstance(args, dict) else {},
                    "duration_ms": duration_ms,
                    "success": ok,
                    "error": error,
                }
            )

            preview = ""
            if isinstance(output, dict):
                if ok:
                    result = output.get("result")
                    if isinstance(result, dict):
                        preview = ", ".join([str(k) for k in list(result.keys())[:6]])
                    elif isinstance(result, list):
                        preview = f"rows={len(result)}"
                    else:
                        preview = str(result)[:180]
                else:
                    preview = str(error or "工具失败")[:180]
            else:
                preview = str(output)[:180]

            status_text = "成功" if ok else "失败"
            tool_feedback_lines.append(f"- {tool_name}: {status_text}; 摘要={preview}")

        messages.append(
            {
                "role": "user",
                "content": "\n".join(tool_feedback_lines)
                + "\n请基于以上真实结果继续：若信息足够请直接给结论，否则继续调用工具。",
            }
        )

        if stop_reason == "tool_budget_exhausted":
            break

    if not stop_reason:
        stop_reason = "max_iterations_reached"

    if not final_text:
        success_count = sum(1 for row in execution_rows if row.get("success"))
        final_text = f"已完成工具执行（成功 {success_count}/{len(execution_rows)}），但未产出最终自然语言结论。"

    return {
        "final_text": final_text,
        "execution_rows": execution_rows,
        "stop_reason": stop_reason,
    }
