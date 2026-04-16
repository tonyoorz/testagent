"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class MatrixDistributionTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_matrix_distribution",
            description="分析缺陷矩阵（matrix）分布与占比",
            parameters={
                "include_unknown": {
                    "type": "boolean",
                    "description": "是否包含空值/未知矩阵",
                    "default": True
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "distribution": []},
                    "insights": ["缺陷数据为空，无法统计 matrix 分布"]
                }

            col = "matrix_display" if "matrix_display" in data.columns else "matrix" if "matrix" in data.columns else None
            if not col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 matrix/matrix_display 列"}

            include_unknown = bool(kwargs.get("include_unknown", True))
            s = data[col].astype(str).map(lambda v: v.strip())
            s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan, "none": np.nan})

            normalized = (
                s.fillna("Unknown")
                .str.replace("MATRIX-", "", regex=False)
                .str.replace("Matrix-", "", regex=False)
                .str.replace("matrix-", "", regex=False)
                .str.upper()
            )

            if not include_unknown:
                normalized = normalized[normalized != "UNKNOWN"]

            total = int(len(normalized))
            if total == 0:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "distribution": []},
                    "insights": ["缺陷数据存在，但 matrix 全为空/未知"]
                }

            counts = normalized.value_counts()

            def _sort_key(v: str):
                if v == "UNKNOWN":
                    return (999, "Z", v)
                m = re.match(r"^(\d+)([A-Z])$", v)
                if m:
                    return (int(m.group(1)), m.group(2), v)
                return (998, "Z", v)

            items = []
            for k, c in counts.items():
                items.append({
                    "matrix": str(k),
                    "count": int(c),
                    "ratio": round(int(c) / total * 100, 2)
                })
            items = sorted(items, key=lambda r: _sort_key(r["matrix"]))

            insights = []
            top = counts.index[0]
            insights.append(f"占比最高的矩阵: {top}（{int(counts.iloc[0])} 条，{round(int(counts.iloc[0]) / total * 100, 2)}%）")

            high_risk = {"1A", "1B", "1C", "1D", "1E"}
            high_cnt = int(sum(counts.get(k, 0) for k in high_risk))
            if high_cnt > 0:
                insights.append(f"高风险矩阵(1A-1E)合计: {high_cnt} 条（{round(high_cnt / total * 100, 2)}%）")

            return {
                "success": True,
                "tool": self.name,
                "result": {"total": total, "distribution": items},
                "insights": insights
            }
        except Exception as e:
            logger.error(f"matrix 分布分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
