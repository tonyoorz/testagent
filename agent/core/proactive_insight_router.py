from typing import Any, Dict, Optional, Tuple

from agent.core.proactive_insight_models import ProactiveInsightRequest


class ProactiveInsightRouter:
    _allowed_scopes = {'defect_test'}
    _default_dimensions = ['project', 'aida', 'severity', 'week']

    def match(
        self,
        *,
        question: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[ProactiveInsightRequest]]:
        context = dict(extra_context or {})
        explicit_mode = str(context.get('mode') or '').strip().lower()

        if explicit_mode == 'proactive_insight':
            return True, self.parse(question=question, extra_context=context)
        return False, None

    def parse(
        self,
        *,
        question: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> ProactiveInsightRequest:
        del question

        context = dict(extra_context or {})
        if 'dataset_scope' in context and not str(context.get('dataset_scope') or '').strip():
            raise ValueError('dataset_scope is required')

        dataset_scope = str(context.get('dataset_scope') or 'defect_test').strip()
        if dataset_scope not in self._allowed_scopes:
            raise ValueError(f'unsupported dataset_scope: {dataset_scope}')

        raw_dimensions = context.get('dimensions') or list(self._default_dimensions)
        if not isinstance(raw_dimensions, list) or not all(
            isinstance(item, str) and item.strip() for item in raw_dimensions
        ):
            raise ValueError('dimensions must be a non-empty list of strings')
        dimensions = [item.strip() for item in raw_dimensions]

        time_window = str(context.get('time_window') or 'recent').strip()
        if not time_window:
            raise ValueError('time_window is required')
        options = {
            key: value
            for key, value in context.items()
            if key not in {'mode', 'dataset_scope', 'dimensions', 'time_window'}
        }

        return ProactiveInsightRequest(
            mode='proactive_insight',
            dataset_scope=dataset_scope,
            dimensions=dimensions,
            time_window=time_window,
            options=options,
        )