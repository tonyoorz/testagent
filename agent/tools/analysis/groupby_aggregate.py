"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class GroupbyAggregateTool(DataAnalysisTool):
    """通用 groupby 聚合工具（可支持 failure_rate 等复合指标）"""

    def __init__(self):
        super().__init__(
            name="groupby_aggregate",
            description="通用分组聚合工具：支持任意列分组与多指标聚合（含失败率）",
            parameters={
                "group_by": {"type": "string", "description": "分组列名，多个用逗号分隔", "default": ""},
                "aggregations": {
                    "type": "array",
                    "description": "聚合定义列表，每项包含 op/column/name。op 支持 count/nunique/sum/mean/max/min/failure_rate",
                    "default": [{"op": "count", "column": "", "name": "count"}],
                },
                "pre_top_n": {"type": "integer", "description": "高基数字段预裁剪：仅保留分组键 TopN（按出现次数）", "default": 0},
                "top_n": {"type": "integer", "description": "返回 TopN 行", "default": 20},
                "sort_by": {"type": "string", "description": "排序字段（默认为第一个聚合字段）", "default": ""},
                "descending": {"type": "boolean", "description": "是否降序", "default": True},
                "status_column": {"type": "string", "description": "failure_rate 用到的状态列名", "default": "run_status"},
                "filters": {"type": "object", "description": "可选过滤条件：{col: [v1,v2]}", "default": {}},
                "max_groups": {"type": "integer", "description": "最大分组数限制，防止爆炸", "default": 5000},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "summary": {"total_rows": 0}}}

            df = data.copy()
            raw_group_by = (kwargs.get("group_by") or "").strip()
            if not raw_group_by:
                return {"success": False, "tool": self.name, "error": "缺少 group_by"}
            group_cols = [c.strip() for c in raw_group_by.split(",") if c.strip()]
            missing = [c for c in group_cols if c not in df.columns]
            if missing:
                return {"success": False, "tool": self.name, "error": f"group_by 列不存在: {missing}"}

            filters = kwargs.get("filters") or {}
            if isinstance(filters, dict) and filters:
                for col, values in filters.items():
                    if col not in df.columns:
                        continue
                    if values is None:
                        continue
                    if not isinstance(values, (list, tuple, set)):
                        values = [values]
                    df = df[df[col].isin(list(values))]

            if df.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "summary": {"total_rows": 0}}}

            pre_top_n = int(kwargs.get("pre_top_n", 0) or 0)
            if pre_top_n > 0 and len(group_cols) == 1:
                g = group_cols[0]
                s = df[g].fillna("").astype(str).str.strip()
                s = s[s != ""]
                if not s.empty:
                    keep = s.value_counts().head(pre_top_n).index.tolist()
                    df = df[df[g].astype(str).str.strip().isin(keep)]

            aggregations = kwargs.get("aggregations") or []
            if not isinstance(aggregations, list) or not aggregations:
                aggregations = [{"op": "count", "column": "", "name": "count"}]

            named_aggs: Dict[str, Any] = {}
            needs_failure_rate = any((a or {}).get("op") == "failure_rate" for a in aggregations)
            status_column = kwargs.get("status_column", "run_status")
            if needs_failure_rate:
                if status_column not in df.columns:
                    return {"success": False, "tool": self.name, "error": f"failure_rate 需要列 {status_column}"}
                failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
                df["_is_failure"] = df[status_column].astype(str).str.lower().apply(lambda s: any(k in s for k in failure_keywords))

            for agg in aggregations:
                if not isinstance(agg, dict):
                    continue
                op = (agg.get("op") or "count").strip()
                col = (agg.get("column") or "").strip()
                name = (agg.get("name") or "").strip() or f"{op}_{col or 'rows'}"

                if op == "count":
                    named_aggs[name] = (group_cols[0], "size")
                elif op == "nunique":
                    if not col or col not in df.columns:
                        return {"success": False, "tool": self.name, "error": f"nunique 需要有效 column: {col}"}
                    named_aggs[name] = (col, "nunique")
                elif op in {"sum", "mean", "max", "min"}:
                    if not col or col not in df.columns:
                        return {"success": False, "tool": self.name, "error": f"{op} 需要有效 column: {col}"}
                    named_aggs[name] = (col, op)
                elif op == "failure_rate":
                    named_aggs["total"] = (group_cols[0], "size")
                    named_aggs["failure"] = ("_is_failure", "sum")
                    if not name:
                        name = "failure_rate"
                else:
                    return {"success": False, "tool": self.name, "error": f"不支持的 op: {op}"}

            grouped = df.groupby(group_cols, dropna=False).agg(**named_aggs).reset_index()
            if "total" in grouped.columns and "failure" in grouped.columns:
                grouped["failure_rate"] = np.where(
                    grouped["total"] > 0, (grouped["failure"] / grouped["total"] * 100).round(2), 0.0
                )

            max_groups = int(kwargs.get("max_groups", 5000))
            if len(grouped) > max_groups:
                hint = "可尝试设置 pre_top_n（例如 200/500）先聚焦高频分组。"
                return {"success": False, "tool": self.name, "error": f"分组数过多（{len(grouped)}），请增加过滤条件或调整 group_by；{hint}"}

            sort_by = (kwargs.get("sort_by") or "").strip()
            if not sort_by:
                sort_by = "failure_rate" if "failure_rate" in grouped.columns else (list(named_aggs.keys())[0] if named_aggs else group_cols[0])
            if sort_by in grouped.columns:
                grouped = grouped.sort_values(sort_by, ascending=not bool(kwargs.get("descending", True)))

            top_n = int(kwargs.get("top_n", 20))
            out = grouped.head(top_n).copy()
            rows = out.to_dict(orient="records")
            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "group_by": group_cols,
                    "rows": rows,
                    "summary": {
                        "total_rows": int(len(grouped)),
                        "returned_rows": int(len(out)),
                        "sort_by": sort_by,
                    },
                },
                "insights": [f"分组总数: {len(grouped)}，返回Top {len(out)}"],
            }
        except Exception as e:
            logger.error(f"groupby 聚合失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
