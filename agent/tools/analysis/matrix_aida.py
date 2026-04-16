"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
from datetime import datetime

logger = logging.getLogger(__name__)


class MatrixAidaHotspotsTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_matrix_aida_hotspots",
            description="分析每个 matrix 下 AIDA 的缺陷聚集度，并输出代表性 ticket 样本",
            parameters={
                "top_matrices": {
                    "type": "integer",
                    "description": "输出矩阵数量（按缺陷数排序）",
                    "default": 10
                },
                "top_aidas": {
                    "type": "integer",
                    "description": "每个矩阵输出 AIDA Top N",
                    "default": 5
                },
                "sample_tickets": {
                    "type": "integer",
                    "description": "每个 matrix×AIDA 输出 ticket 样本数",
                    "default": 3
                },
                "include_unknown": {
                    "type": "boolean",
                    "description": "是否包含未知矩阵/未知AIDA",
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
                    "result": {"total": 0, "matrices": []},
                    "insights": ["缺陷数据为空，无法分析 matrix×AIDA 热点"]
                }

            matrix_col = "matrix_display" if "matrix_display" in data.columns else "matrix" if "matrix" in data.columns else None
            if not matrix_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 matrix/matrix_display 列"}

            aida_col = "aida_english" if "aida_english" in data.columns else "aida" if "aida" in data.columns else None
            if not aida_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 aida/aida_english 列"}

            include_unknown = bool(kwargs.get("include_unknown", True))
            top_matrices = max(1, min(int(kwargs.get("top_matrices", 10)), 50))
            top_aidas = max(1, min(int(kwargs.get("top_aidas", 5)), 30))
            sample_tickets = max(0, min(int(kwargs.get("sample_tickets", 3)), 20))

            df = data.copy()

            m = df[matrix_col].astype(str).map(lambda v: v.strip())
            m = m.replace({"": np.nan, "nan": np.nan, "None": np.nan, "none": np.nan})
            m = (
                m.fillna("Unknown")
                .str.replace("MATRIX-", "", regex=False)
                .str.replace("Matrix-", "", regex=False)
                .str.replace("matrix-", "", regex=False)
                .str.upper()
            )

            a = df[aida_col].astype(str).map(lambda v: v.strip())
            a = a.replace({"": np.nan, "nan": np.nan, "None": np.nan, "none": np.nan}).fillna("Unknown")

            df["_matrix_norm"] = m
            df["_aida_norm"] = a

            if not include_unknown:
                df = df[(df["_matrix_norm"] != "UNKNOWN") & (df["_aida_norm"] != "Unknown")]

            total = int(len(df))
            if total == 0:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "matrices": []},
                    "insights": ["缺陷数据存在，但 matrix/AIDA 都为空或被过滤为 Unknown"]
                }

            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None

            if time_col and time_col in df.columns:
                df[time_col] = pd.to_datetime(df[time_col], errors="coerce")

            matrix_counts = df["_matrix_norm"].value_counts()
            selected_matrices = matrix_counts.head(top_matrices).index.tolist()

            matrices_out = []
            for matrix_value in selected_matrices:
                md = df[df["_matrix_norm"] == matrix_value]
                matrix_total = int(len(md))
                aida_counts = md["_aida_norm"].value_counts().head(top_aidas)
                aidas_out = []
                for aida_value, cnt in aida_counts.items():
                    sub = md[md["_aida_norm"] == aida_value]
                    samples = []
                    if sample_tickets > 0 and (id_col or title_col):
                        sub2 = sub
                        if time_col and time_col in sub2.columns:
                            sub2 = sub2.sort_values(time_col, ascending=False)
                        for _, r in sub2.head(sample_tickets).iterrows():
                            samples.append({
                                "id": r.get(id_col) if id_col else None,
                                "title": r.get(title_col) if title_col else None,
                                "project": r.get(project_col) if project_col else None,
                                "creation_time": str(r.get(time_col)) if time_col else None
                            })

                    aidas_out.append({
                        "aida": str(aida_value),
                        "count": int(cnt),
                        "ratio_in_matrix": round(int(cnt) / matrix_total * 100, 2) if matrix_total else 0.0,
                        "samples": samples
                    })

                matrices_out.append({
                    "matrix": str(matrix_value),
                    "matrix_total": matrix_total,
                    "matrix_share": round(matrix_total / total * 100, 2),
                    "top_aidas": aidas_out
                })

            insights = []
            if matrices_out:
                top_m = matrices_out[0]
                insights.append(f"缺陷最多的矩阵: {top_m['matrix']}（{top_m['matrix_total']} 条，占 {top_m['matrix_share']}%）")
                if top_m.get("top_aidas"):
                    top_a = top_m["top_aidas"][0]
                    insights.append(f"{top_m['matrix']} 内最聚集的 AIDA: {top_a['aida']}（{top_a['count']} 条，占该矩阵 {top_a['ratio_in_matrix']}%）")

            return {
                "success": True,
                "tool": self.name,
                "result": {"total": total, "matrices": matrices_out},
                "insights": insights
            }
        except Exception as e:
            logger.error(f"matrix×AIDA 热点分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
