from typing import Any, Dict, Optional

from agent.tools.base import DataAnalysisTool
from agent.tools.helpers import build_legacy_tool


class SQLiteNLQueryWithFixTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str], llm: Any = None):
        self._delegate = build_legacy_tool('SQLiteNLQueryWithFixTool', db_path, llm=llm)
        super().__init__(
            name=self._delegate.name,
            description=self._delegate.description,
            parameters=self._delegate.parameters,
        )

    def execute(self, data: Any, **kwargs: Any) -> Dict[str, Any]:
        return self._delegate.execute(data, **kwargs)