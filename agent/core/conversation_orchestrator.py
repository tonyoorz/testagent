from typing import Any, Dict, Optional

from agent.core.page_context_adapter import normalize_page_context
from agent.core.streaming_protocol import init_stream_state


class ConversationOrchestrator:
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