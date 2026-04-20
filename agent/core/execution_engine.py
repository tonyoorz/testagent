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

    def resolve_analysis_inputs(
        self,
        *,
        question: str,
        conversation_history: Any,
        context_manager: Any,
        db_path: Optional[str],
        semantic_adapter_enabled: bool,
        semantic_adapter_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        analysis_question = str(question or '').strip()
        semantic_term_adapter: Dict[str, Any] = {}
        semantic_term_hints: Dict[str, Any] = {}

        if semantic_adapter_enabled and callable(semantic_adapter_fn):
            semantic_term_adapter = semantic_adapter_fn(
                question=analysis_question,
                db_path=db_path,
                table_name='',
                prefer_db=bool(db_path),
            ) or {}
            semantic_term_hints = dict(semantic_term_adapter.get('semantic_hints') or {})
            normalized_question = str(semantic_term_adapter.get('normalized_question') or '').strip()
            if normalized_question:
                analysis_question = normalized_question

        early_intents, early_confidence, clarification = context_manager.analyze_intent_with_confidence(analysis_question)

        if early_intents == ['general']:
            q = str(question or '').strip()
            ql = q.lower()
            has_time_slot = any(k in ql for k in [
                '本周', '这周', '上周', '本月', '上月', '本季度', '季度', '本年', '今年',
                'today', 'yesterday', 'this week', 'last week', 'this month', 'quarter'
            ])
            has_project_slot = False
            try:
                import re

                has_project_slot = bool(re.search(r"\b(IDCEVO|IDC|MGU|APP|RSU|ENTRYEVO|G\d{2,})\b", q, flags=re.IGNORECASE))
            except Exception:
                has_project_slot = False
            if has_time_slot or has_project_slot:
                inherited_intents = []
                for msg in reversed(conversation_history or []):
                    if str((msg or {}).get('role') or '') != 'user':
                        continue
                    content = str((msg or {}).get('content') or '').strip()
                    if not content or content == q:
                        continue
                    cand = context_manager.analyze_intent(content)
                    if cand and cand != ['general']:
                        inherited_intents = cand
                        break
                if inherited_intents:
                    early_intents = inherited_intents
                    early_confidence = 0.78
                    clarification = None

        return {
            'analysis_question': analysis_question,
            'semantic_term_adapter': semantic_term_adapter,
            'semantic_term_hints': semantic_term_hints,
            'early_intents': early_intents,
            'early_confidence': early_confidence,
            'clarification': clarification,
        }

    def gather_supporting_context(
        self,
        *,
        question: str,
        analysis_question: str,
        context: Dict[str, Any],
        memory: Any,
        knowledge_base: Any,
        memory_debug_enabled: bool,
    ) -> Dict[str, Any]:
        relevant_history = memory.get_relevant_history(question)
        if memory_debug_enabled:
            used = []
            for h in (relevant_history or [])[:5]:
                used.append(
                    {
                        'role': h.get('role'),
                        'from_memory': bool(h.get('from_memory')),
                        'kind': h.get('kind'),
                        'tags': h.get('tags') or [],
                        'content': (h.get('content') or '')[:160],
                    }
                )
            context['memory_debug'] = {
                'short_term_size': len(memory.short_term or []),
                'long_term_size': len(memory.long_term or []),
                'used': used,
            }
        knowledge_context = knowledge_base.get_knowledge_context(analysis_question)
        return {
            'relevant_history': relevant_history,
            'knowledge_context': knowledge_context,
            'context': context,
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

    def finalize_answer(
        self,
        *,
        question: str,
        context: Dict[str, Any],
        execution_results: Any,
        knowledge_context: Any,
        relevant_history: Any,
        start_time_seconds: float,
        current_time_seconds: float,
        generate_answer_fn: Callable[..., Dict[str, Any]],
        memory_add_message_fn: Callable[[str, str, Dict[str, Any]], None],
        normalize_response_fn: Callable[[Dict[str, Any], Any], Dict[str, Any]],
    ) -> Dict[str, Any]:
        answer = generate_answer_fn(
            question=question,
            context=context,
            execution_results=execution_results,
            knowledge_context=knowledge_context,
            relevant_history=relevant_history,
        )
        try:
            ctx_obj = answer.get('context') if isinstance(answer, dict) else None
            if isinstance(ctx_obj, dict):
                ctx_obj['analysis_trace'] = context.get('analysis_trace')
        except Exception:
            pass

        memory_add_message_fn(
            'assistant',
            answer['text'],
            {
                'tools_used': [r['tool'] for r in (execution_results or []) if isinstance(r, dict) and r.get('tool')],
                'execution_time': max(0.0, float(current_time_seconds) - float(start_time_seconds)),
            },
        )
        return normalize_response_fn(answer, execution_results=execution_results)