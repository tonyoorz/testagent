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


class CorrelateDefectsTestsTool(DataAnalysisTool):
    """缺陷-测试关联洞察工具"""

    def __init__(self):
        super().__init__(
            name="correlate_defects_tests",
            description="按项目/周关联缺陷数量与测试失败率，发现高风险项目",
            parameters={
                "defect_time_col": {"type": "string", "default": "tcreationtime"},
                "defect_project_col": {"type": "string", "default": "tproject"},
                "test_time_col": {"type": "string", "default": "finished_udf_dt"},
                "test_project_col": {"type": "string", "default": "project"},
                "test_status_col": {"type": "string", "default": "run_status"},
                "top_n": {"type": "integer", "default": 10}
            }
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        try:
            datasets = data if isinstance(data, dict) else {}
            defects = datasets.get("defects")
            tests = datasets.get("tests")
            if defects is None or tests is None or defects.empty or tests.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"top": []},
                    "insights": ["缺陷或测试数据为空，无法进行联动关联分析"]
                }

            defect_time_col = kwargs.get("defect_time_col", "tcreationtime")
            defect_project_col = kwargs.get("defect_project_col", "tproject")
            test_time_col = kwargs.get("test_time_col", "finished_udf_dt")
            test_project_col = kwargs.get("test_project_col", "project")
            test_status_col = kwargs.get("test_status_col", "run_status")
            top_n = int(kwargs.get("top_n", 10))

            if defect_time_col not in defects.columns:
                for c in ["tcreationtime", "creation_time", "created_at"]:
                    if c in defects.columns:
                        defect_time_col = c
                        break
            if defect_project_col not in defects.columns:
                for c in ["tproject", "project"]:
                    if c in defects.columns:
                        defect_project_col = c
                        break
            ddf = defects[[c for c in [defect_time_col, defect_project_col, "_id", "severity_group", "severity"] if c in defects.columns]].copy()
            if defect_time_col not in ddf.columns or defect_project_col not in ddf.columns:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少时间列或项目列"}
            ddf[defect_time_col] = pd.to_datetime(ddf[defect_time_col], errors="coerce")
            ddf["week"] = ddf[defect_time_col].dt.to_period("W").astype(str)
            d_group = ddf.groupby([defect_project_col, "week"]).size().reset_index(name="defect_count")

            tcols = [c for c in [test_time_col, test_project_col, test_status_col] if c in tests.columns]
            tdf = tests[tcols].copy()
            if test_time_col not in tests.columns:
                for c in ["finished_udf_dt", "tcreationtime", "finished_udf"]:
                    if c in tests.columns:
                        test_time_col = c
                        break
            if test_project_col not in tests.columns:
                for c in ["project", "tproject"]:
                    if c in tests.columns:
                        test_project_col = c
                        break
            if test_status_col not in tests.columns:
                for c in ["run_status", "status"]:
                    if c in tests.columns:
                        test_status_col = c
                        break
            tcols = [c for c in [test_time_col, test_project_col, test_status_col] if c in tests.columns]
            tdf = tests[tcols].copy()
            if test_time_col not in tdf.columns or test_project_col not in tdf.columns or test_status_col not in tdf.columns:
                return {"success": False, "tool": self.name, "error": "测试数据缺少时间列/项目列/状态列"}
            tdf[test_time_col] = pd.to_datetime(tdf[test_time_col], errors="coerce")
            tdf["week"] = tdf[test_time_col].dt.to_period("W").astype(str)

            failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
            tdf["_is_failure"] = tdf[test_status_col].astype(str).str.lower().apply(lambda s: any(k in s for k in failure_keywords))
            t_group = tdf.groupby([test_project_col, "week"]).agg(
                test_total=("week", "size"),
                test_failure=("_is_failure", "sum")
            ).reset_index()
            t_group["failure_rate"] = np.where(
                t_group["test_total"] > 0,
                (t_group["test_failure"] / t_group["test_total"] * 100).round(2),
                0.0
            )

            merged = d_group.merge(
                t_group,
                left_on=[defect_project_col, "week"],
                right_on=[test_project_col, "week"],
                how="inner"
            )
            if merged.empty:
                return {"success": False, "tool": self.name, "error": "缺陷与测试在项目/周维度没有可关联的数据"}

            merged["risk_index"] = (merged["defect_count"] * (1 + merged["failure_rate"] / 100)).round(2)
            merged = merged.sort_values("risk_index", ascending=False)

            top_rows = []
            for _, r in merged.head(top_n).iterrows():
                top_rows.append({
                    "project": r[defect_project_col],
                    "week": r["week"],
                    "defect_count": int(r["defect_count"]),
                    "test_total": int(r["test_total"]),
                    "failure_rate": float(r["failure_rate"]),
                    "risk_index": float(r["risk_index"])
                })

            insights = [
                "风险指数 = 缺陷数 × (1 + 失败率)",
                f"最高风险组合: {top_rows[0]['project']} / {top_rows[0]['week']} (risk_index={top_rows[0]['risk_index']})"
            ]

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "top": top_rows
                },
                "insights": insights
            }
        except Exception as e:
            logger.error(f"缺陷-测试关联分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
