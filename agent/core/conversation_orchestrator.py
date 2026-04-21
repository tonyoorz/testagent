from typing import Any, Dict, Optional

from agent.core.guardrails import GuardrailEngine
from agent.core.page_context_adapter import normalize_page_context
from agent.core.recovery_policy import RecoveryPolicy
from agent.core.runtime_state_machine import RuntimeStateMachine
from agent.core.streaming_protocol import append_event, init_stream_state, set_runtime_flag, set_runtime_stage


class ConversationOrchestrator:
    def __init__(self):
        self.guardrails = GuardrailEngine()
        self.state_machine = RuntimeStateMachine()
        self.recovery_policy = RecoveryPolicy()

    def build_request(
        self,
        *,
        question: str,
        dashboard_type: str,
        current_data: Any,
        conversation_state: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = {
            "question": str(question or "").strip(),
            "page_context": normalize_page_context(
                dashboard_type=dashboard_type,
                current_data=current_data,
                conversation_state=conversation_state,
                extra_context=extra_context,
            ),
        }
        if isinstance(extra_context, dict) and extra_context:
            request.update(extra_context)
        return request

    def initialize_stream_state(self, progress: str) -> Dict[str, Any]:
        return init_stream_state(progress)

    def prepare_runtime(
        self,
        *,
        question: str,
        dashboard_type: str,
        current_data: Any,
        conversation_state: Optional[Dict[str, Any]] = None,
        extra_context: Optional[Dict[str, Any]] = None,
        agent_results: Optional[Dict[str, Any]] = None,
        progress: str = '',
    ) -> Dict[str, Any]:
        request = self.build_request(
            question=question,
            dashboard_type=dashboard_type,
            current_data=current_data,
            conversation_state=conversation_state,
            extra_context=extra_context,
        )
        stream_state = self.initialize_stream_state(progress)
        page_context = request.get('page_context') if isinstance(request.get('page_context'), dict) else {}
        decision = self.guardrails.evaluate(
            question=question,
            request=request,
            page_context=page_context,
            agent_results=agent_results or {},
        )

        next_stage = 'guarded' if decision.action == 'allow' else 'fallback'
        if decision.action == 'confirm':
            set_runtime_flag(stream_state, key='confirmation_pending', value=True)
        if decision.action == 'fallback':
            set_runtime_flag(stream_state, key='fallback_active', value=True)

        stream_state = self.state_machine.transition(stream_state, next_stage)
        set_runtime_stage(stream_state, stream_state.get('runtime_stage', next_stage))
        append_event(
            stream_state,
            kind='guardrail',
            title='Guardrail decision',
            status='info',
            summary=decision.action,
            details={'reason_code': decision.reason_code},
        )
        return {
            'request': request,
            'stream_state': stream_state,
            'guardrail_decision': decision,
        }