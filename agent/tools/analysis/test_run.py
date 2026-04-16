"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
from agent.tools.helpers import resolve_dimension_to_column
from datetime import datetime

logger = logging.getLogger(__name__)


class AnalyzeTestRunTool(DataAnalysisTool):
    """测试运行分析工具"""

    def __init__(self):
        super().__init__(
            name="analyze_test_run",
            description="分析测试运行状态分布与失败率，支持按周/月或任意维度分组",
            parameters={
                "group_by": {
                    "type": "string",
                    "description": "分组维度",
                    "default": "week"
                },
                "status_column": {
                    "type": "string",
                    "description": "测试运行状态列",
                    "default": "run_status"
                },
                "time_column": {
                    "type": "string",
                    "description": "时间列名（用于生成周）",
                    "default": "finished_udf_dt"
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {
                        "group_by": kwargs.get("group_by", "week"),
                        "rows": [],
                        "summary": {"overall_total": 0, "overall_failure": 0, "overall_failure_rate": 0}
                    },
                    "insights": ["测试数据为空，无法计算失败率"]
                }
            dataset = str(kwargs.get("dataset") or "tests").strip().lower()
            group_by = str(kwargs.get("group_by", "week") or "week").strip()
            status_column = str(kwargs.get("status_column", "run_status") or "run_status").strip()
            time_column = str(kwargs.get("time_column", "finished_udf_dt") or "finished_udf_dt").strip()

            df = data.copy()
            if status_column not in df.columns:
                for c in ["run_status", "status", "native_status"]:
                    if c in df.columns:
                        status_column = c
                        break
            if status_column not in df.columns:
                return {"success": False, "tool": self.name, "error": f"列 {status_column} 不存在"}

            group_tokens = [t.strip() for t in group_by.split(",") if t.strip()]
            if not group_tokens:
                group_tokens = ["week"]

            # 常见中文/英文别名归一化
            alias_map = {
                "feature team": "fv",
                "feature_team": "fv",
                "feature-team": "fv",
                "call services": "fv",
                "功能": "aida",
                "模块": "aida",
                "service": "aida",
                "services": "aida",
                "测试人员": "tester",
                "测试员": "tester",
            }
            group_tokens = [alias_map.get(str(t).strip().lower(), t) for t in group_tokens]

            group_cols = []
            label_col = None
            time_modes = {"week": "W", "month": "M"}
            if group_tokens[0].lower() in time_modes:
                if time_column not in df.columns:
                    for c in ["finished_udf_dt", "tcreationtime", "creation_time", "finished_udf"]:
                        if c in df.columns:
                            time_column = c
                            break
                if time_column not in df.columns:
                    return {"success": False, "tool": self.name, "error": f"列 {time_column} 不存在"}
                df[time_column] = pd.to_datetime(df[time_column], errors="coerce")
                df["_time_group"] = df[time_column].dt.to_period(time_modes[group_tokens[0].lower()]).astype(str)
                group_cols.append("_time_group")
                label_col = "_time_group"
                for t in group_tokens[1:]:
                    c = resolve_dimension_to_column(dataset, t, list(df.columns))
                    if not c:
                        c = resolve_dimension_to_column(dataset, t.lower(), list(df.columns))
                    if c and c in df.columns:
                        group_cols.append(c)
            else:
                for t in group_tokens:
                    c = resolve_dimension_to_column(dataset, t, list(df.columns))
                    if not c:
                        fallback = {
                            "project": ["tproject", "project"],
                            "aida": ["aida_english", "top_aida", "aida"],
                            "fv": ["fv", "feature_team", "feature", "top_aida", "aida_english"],
                            "tester": ["tester", "owner", "found_by", "reporter", "author_name"],
                            "domain": ["domain", "solution_cluster", "pu"],
                            "severity": ["severity_group", "severity"],
                            "status": ["status_phase", "status", "run_status"],
                            "matrix": ["matrix_display", "matrix"],
                        }
                        for x in fallback.get(t.strip().lower(), []):
                            if x in df.columns:
                                c = x
                                break
                    if c and c in df.columns:
                        group_cols.append(c)
                if not group_cols:
                    return {"success": False, "tool": self.name, "error": f"列 {group_by} 不存在"}
                label_col = group_cols[0] if len(group_cols) == 1 else None

            status_counts = (
                df.groupby(group_cols)[status_column]
                .value_counts(dropna=False)
                .unstack(fill_value=0)
                .reset_index()
            )

            status_cols = [c for c in status_counts.columns if c not in group_cols]
            status_counts["total"] = status_counts[status_cols].sum(axis=1)

            failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
            failure_cols = [c for c in status_cols if any(k in str(c).lower() for k in failure_keywords)]
            if failure_cols:
                status_counts["failure"] = status_counts[failure_cols].sum(axis=1)
            else:
                status_counts["failure"] = 0
            status_counts["failure_rate"] = np.where(
                status_counts["total"] > 0,
                (status_counts["failure"] / status_counts["total"] * 100).round(2),
                0.0
            )

            rows = []
            for _, row in status_counts.iterrows():
                if label_col:
                    bucket = row[label_col]
                else:
                    bucket = " / ".join([str(row.get(c)) for c in group_cols])
                row_dict = {"group": bucket, "total": int(row["total"]), "failure_rate": float(row["failure_rate"])}
                for c in status_cols:
                    row_dict[str(c)] = int(row[c])
                rows.append(row_dict)

            top_failure = sorted(rows, key=lambda r: r.get("failure_rate", 0), reverse=True)[:5]
            insights = []
            if any(t.strip().lower() in {"fv", "feature team", "feature_team", "feature-team"} for t in group_tokens):
                insights.append("Feature Team 对应 FV 维度（可理解为责任团队/功能域归属）")
            if top_failure:
                insights.append(f"失败率最高的分组: {top_failure[0]['group']} ({top_failure[0]['failure_rate']}%)")
            overall_total = int(status_counts["total"].sum())
            overall_failure = int(status_counts["failure"].sum())
            overall_rate = round(overall_failure / overall_total * 100, 2) if overall_total else 0
            insights.append(f"总体失败率: {overall_rate}%（失败 {overall_failure} / 总计 {overall_total}）")

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "group_by": group_by,
                    "rows": rows,
                    "summary": {
                        "overall_total": overall_total,
                        "overall_failure": overall_failure,
                        "overall_failure_rate": overall_rate
                    }
                },
                "insights": insights
            }
        except Exception as e:
            logger.error(f"测试运行分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
