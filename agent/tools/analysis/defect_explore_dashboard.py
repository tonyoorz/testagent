from typing import Any, Dict

from agent.tools.base import DataAnalysisTool
from agent.tools.helpers import build_legacy_tool


class DefectExploreDashboardTool(DataAnalysisTool):
    def __init__(self):
        self._delegate = build_legacy_tool('DefectExploreDashboardTool')
        super().__init__(
            name=self._delegate.name,
            description=self._delegate.description,
            parameters=self._delegate.parameters,
        )

    def execute(self, data: Any, **kwargs: Any) -> Dict[str, Any]:
        return self._delegate.execute(data, **kwargs)