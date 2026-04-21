from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class SessionDataContext:
    dashboard_type: str = 'general'
    page_context: Dict[str, Any] = field(default_factory=dict)
    page_filters: Dict[str, Any] = field(default_factory=dict)
    data_summary: str = ''
    last_question: str = ''
    updated_at: str = ''

    def update_from_request(self, request: Dict[str, Any]) -> None:
        payload = dict(request or {})
        self.last_question = str(payload.get('question') or self.last_question or '').strip()
        page_context = payload.get('page_context') if isinstance(payload.get('page_context'), dict) else {}
        page_filters = payload.get('page_filters') if isinstance(payload.get('page_filters'), dict) else {}
        self.page_context = dict(page_context or self.page_context)
        self.page_filters = dict(page_filters or self.page_filters)
        self.data_summary = str(payload.get('data_summary') or self.data_summary or '')
        if page_context.get('dashboard_type'):
            self.dashboard_type = str(page_context.get('dashboard_type'))
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'dashboard_type': self.dashboard_type,
            'page_context': dict(self.page_context),
            'page_filters': dict(self.page_filters),
            'data_summary': self.data_summary,
            'last_question': self.last_question,
            'updated_at': self.updated_at,
        }


__all__ = ['SessionDataContext']