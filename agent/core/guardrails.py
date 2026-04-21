from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class GuardrailDecision:
    action: str
    reason_code: str = 'allowed'
    message: str = ''
    details: Dict[str, Any] = field(default_factory=dict)


class GuardrailEngine:
    def evaluate(
        self,
        *,
        question: str,
        request: Dict[str, Any],
        page_context: Dict[str, Any],
        agent_results: Dict[str, Any],
    ) -> GuardrailDecision:
        last_agent_context = (agent_results or {}).get('last_agent_context') or {}
        if last_agent_context.get('confirmation_pending'):
            return GuardrailDecision(
                action='confirm',
                reason_code='confirmation_required',
                message='confirmation pending',
                details={'question': str(question or '').strip()},
            )

        if not isinstance(page_context, dict) or not str(page_context.get('dashboard_type') or '').strip():
            return GuardrailDecision(
                action='fallback',
                reason_code='missing_page_context',
                message='missing dashboard_type in page context',
                details={'request_keys': sorted(list((request or {}).keys()))},
            )

        return GuardrailDecision(action='allow')