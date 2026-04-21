import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    name: str
    template: str
    version: str = '1.0'
    description: str = ''
    tags: List[str] = field(default_factory=list)


class PromptRegistry:
    _instance: Optional['PromptRegistry'] = None

    def __init__(self, include_defaults: bool = True):
        self._prompts: Dict[str, PromptTemplate] = {}
        if include_defaults:
            self._load_builtin_prompts()

    @classmethod
    def get_instance(cls) -> 'PromptRegistry':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        name: str,
        template: str,
        version: str = '1.0',
        description: str = '',
        tags: Optional[List[str]] = None,
    ) -> None:
        self._prompts[name] = PromptTemplate(
            name=name,
            template=template,
            version=version,
            description=description,
            tags=list(tags or []),
        )

    def get(self, prompt_name: str) -> Optional[PromptTemplate]:
        return self._prompts.get(prompt_name)

    def render(self, prompt_name: str, **kwargs: Any) -> str:
        prompt = self._prompts.get(prompt_name)
        if prompt is None:
            logger.warning('Prompt not found: %s', prompt_name)
            return ''
        rendered = prompt.template
        for key, value in kwargs.items():
            rendered = rendered.replace('{{' + str(key) + '}}', str(value))
        return rendered

    def render_dashboard_prompt(self, dashboard_type: str, data_context: str = '') -> str:
        prompt_name = str(dashboard_type or '').strip().lower() or 'general'
        if prompt_name not in self._prompts:
            prompt_name = 'general'
        return self.render(prompt_name, data_context=data_context)

    def _load_builtin_prompts(self) -> None:
        self.register(
            'defect',
            (
                'You are an automotive defect analysis assistant for BMW DTSV.\n'
                'Focus on severity, trends, module distribution, and risk prioritization.\n\n'
                'Current Data Context:\n{{data_context}}'
            ),
            description='Default defect analysis prompt',
            tags=['core', 'defect'],
        )
        self.register(
            'test',
            (
                'You are a test coverage analysis assistant for BMW DTSV.\n'
                'Explain coverage gaps, pass rates, and improvement actions.\n\n'
                'Current Data Context:\n{{data_context}}'
            ),
            description='Default test prompt',
            tags=['core', 'test'],
        )
        self.register(
            'general',
            (
                'You are a data analysis assistant for automotive testing and defect data.\n'
                'Use only the provided tool outputs and data context.\n\n'
                'Current Data Context:\n{{data_context}}'
            ),
            description='Default general prompt',
            tags=['core'],
        )


__all__ = ['PromptRegistry', 'PromptTemplate']