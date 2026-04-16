"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class DescribeDatasetTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="describe_dataset",
            description="描述数据集的列结构、样例值与基础统计，用于agentic模式的上下文自检",
            parameters={
                "dataset": {"type": "string", "description": "数据集名", "default": "defects"},
                "max_columns": {"type": "integer", "description": "最多返回列数", "default": 20},
                "sample_values": {"type": "integer", "description": "每列最多返回样例值数", "default": 3},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
        max_columns = int(kwargs.get("max_columns") or 20)
        max_columns = max(1, min(200, max_columns))
        sample_values = int(kwargs.get("sample_values") or 3)
        sample_values = max(0, min(20, sample_values))
        cols = [str(c) for c in df.columns.tolist()][:max_columns]
        samples: Dict[str, List[Any]] = {}
        if sample_values > 0 and not df.empty:
            for c in cols:
                try:
                    s = df[c].dropna()
                    vals = s.astype(str).head(sample_values).tolist()
                    samples[c] = vals
                except Exception:
                    samples[c] = []
        return {
            "success": True,
            "tool": self.name,
            "result": {
                "columns": cols,
                "row_count": int(len(df)),
                "sample_values": samples,
            },
        }
