from typing import Any, Dict, Optional

from agent.tools.base import DataAnalysisTool
from agent.tools.helpers import build_legacy_tool


class SQLiteQueryTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        self._delegate = build_legacy_tool('SQLiteQueryTool', db_path)
        super().__init__(
            name=self._delegate.name,
            description=self._delegate.description,
            parameters=self._delegate.parameters,
        )

    def execute(self, data: Any, **kwargs: Any) -> Dict[str, Any]:
        return self._delegate.execute(data, **kwargs)