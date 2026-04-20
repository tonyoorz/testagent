import os
from typing import Any, Callable, Dict, Optional

from agent.core.agentic_runtime import build_tool_specs, run_agentic_loop
from agent.core.conversation_runtime import serialize_plan_trace


class UnifiedExecutionEngine:
    def __init__(self, *, tool_executor: Any, task_planner: Any):
        self.tool_executor = tool_executor
        self.task_planner = task_planner

    def execute_agentic(
        self,
        *,
        question: str,
        prepared_data: Any,
        context: Dict[str, Any],
        analysis_trace: Dict[str, Any],
        tool_call_max: Optional[int] = None,
        max_iters: Optional[int] = None,
        llm_client: Any = None,
        llm_model: Any = None,
        run_agentic_loop_fn: Callable[..., Dict[str, Any]] = run_agentic_loop,
    ) -> Dict[str, Any]:
        tool_call_max = int(tool_call_max if tool_call_max is not None else (os.getenv('AGENT_TOOL_CALL_MAX', '8') or 8))
        tool_call_max = max(0, min(tool_call_max, 100))
        max_iters = int(max_iters if max_iters is not None else (os.getenv('AGENT_AGENTIC_MAX_ITERS', '6') or 6))
        max_iters = max(1, min(max_iters, 20))

        llm = self.tool_executor._llm
        llm_client = llm_client or getattr(llm, 'client', None)
        llm_model = llm_model or getattr(llm, 'model', None)
        if not llm_client:
            raise RuntimeError('agentic 模式缺少可用 LLM client')

        tools_schema = self.tool_executor.get_tool_schema() or {}
        tool_specs = build_tool_specs(tools_schema)
        agentic_result = run_agentic_loop_fn(
            llm_client=llm_client,
            llm_model=llm_model,
            tool_specs=tool_specs,
            question=question,
            data_summary=str(context.get('data_summary') or ''),
            execute_tool=lambda tool_name, args: self.tool_executor.execute_tool(
                tool_name,
                prepared_data,
                **(args if isinstance(args, dict) else {}),
            ),
            tool_call_max=tool_call_max,
            max_iters=max_iters,
        )
        exec_rows = list(agentic_result.get('execution_rows') or [])
        stop_reason = str(agentic_result.get('stop_reason') or '')
        final_text = str(agentic_result.get('final_text') or '')
        trace = dict(analysis_trace or {})
        trace['execution'] = exec_rows
        trace['agentic_stop_reason'] = stop_reason
        return {
            'text': final_text,
            'tools_used': [r.get('tool') for r in exec_rows],
            'execution_results': [{'tool': r.get('tool'), 'result': {'success': bool(r.get('success'))}} for r in exec_rows],
            'analysis_trace': trace,
        }

    def execute_plan_flow(
        self,
        *,
        question: str,
        prepared_data: Any,
        context: Dict[str, Any],
        analysis_trace: Dict[str, Any],
        pending_confirmation: Optional[Dict[str, Any]],
        confirmed_now: bool,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]],
        should_require_confirmation: Callable[[Any, Dict[str, Any]], bool],
        build_confirmation_payload: Callable[[str, Any, Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        plan = None
        if isinstance(pending_confirmation, dict) and confirmed_now:
            reused_plan = pending_confirmation.get('plan')
            if isinstance(reused_plan, list) and reused_plan:
                plan = reused_plan
        if plan is None:
            plan = self.task_planner.plan(question, context)

        trace = dict(analysis_trace or {})
        trace['plan'] = serialize_plan_trace(plan)

        if (not confirmed_now) and should_require_confirmation(plan, context):
            return {
                'needs_confirmation': True,
                'pending_confirmation': {
                    'question': question,
                    'plan': plan,
                },
                'confirmation_payload': build_confirmation_payload(question, plan, context, trace),
                'analysis_trace': trace,
            }

        if progress_cb:
            try:
                progress_cb(
                    {
                        'event': 'planned',
                        'total_steps': len(plan or []),
                        'tools': [s.get('tool') for s in (plan or []) if isinstance(s, dict)],
                    }
                )
            except Exception:
                pass

        execution_results = self.task_planner.execute_plan(plan, prepared_data, context=context, progress_cb=progress_cb)
        trace['execution'] = [r.get('trace') for r in (execution_results or []) if isinstance(r, dict) and r.get('trace')]
        return {
            'execution_results': execution_results,
            'analysis_trace': trace,
            'plan': plan,
        }