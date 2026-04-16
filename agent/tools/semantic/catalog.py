"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class SemanticCatalogTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str] = None):
        super().__init__(
            name="consult_semantic_catalog",
            description="查询语义目录（数据集/指标/图表口径与误用风险），用于约束分析结论",
            parameters={
                "question": {"type": "string", "description": "用户问题"},
                "dashboard": {"type": "string", "description": "可选：看板名，用于过滤图表语义", "default": ""},
                "max_each": {"type": "integer", "description": "每类最多返回条数", "default": 6},
            },
        )
        self._db_path = db_path

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        question = str(kwargs.get("question") or "").strip()
        if not question:
            return {"success": False, "tool": self.name, "error": "question 不能为空"}
        dashboard = str(kwargs.get("dashboard") or "").strip() or None
        max_each = int(kwargs.get("max_each") or 6)
        if max_each <= 0:
            max_each = 6
        try:
            from semantic_catalog.runtime import build_semantic_context

            cols = []
            if isinstance(data, pd.DataFrame):
                cols = [str(c) for c in data.columns.tolist()]
            semantic_context = build_semantic_context(
                question=question, dashboard=dashboard, dataframe_columns=cols, max_each=max_each, db_path=self._db_path
            )
            return {"success": True, "tool": self.name, "result": {"semantic_context": semantic_context}}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}
