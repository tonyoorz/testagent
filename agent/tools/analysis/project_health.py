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


class ProjectRecentWeeksHealthTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_project_recent_weeks",
            description="针对指定项目，评估最近N周缺陷发现是否上升、测试执行是否变差（失败率）",
            parameters={
                "project": {"type": "string", "description": "项目名（如 IDCevo/IDC/MGU/App/RSU）", "default": ""},
                "weeks": {"type": "integer", "description": "最近N周", "default": 4},
            },
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        datasets = data if isinstance(data, dict) else {}
        defects = datasets.get("defects")
        tests = datasets.get("tests")
        project = str(kwargs.get("project") or "").strip()
        weeks = int(kwargs.get("weeks") or 4)
        weeks = max(1, min(26, weeks))

        if not project:
            return {"success": False, "tool": self.name, "error": "project 不能为空"}
        if defects is None or tests is None:
            return {"success": False, "tool": self.name, "error": "需要同时提供 defects 与 tests 数据集"}
        if not isinstance(defects, pd.DataFrame) or not isinstance(tests, pd.DataFrame):
            return {"success": False, "tool": self.name, "error": "defects/tests 必须为 DataFrame"}
        if defects.empty or tests.empty:
            return {
                "success": True,
                "tool": self.name,
                "result": {"project": project, "weeks": weeks, "note": "缺陷或测试数据为空，无法评估"},
                "insights": ["缺陷或测试数据为空，无法评估最近周趋势"],
            }

        def _norm_project(v: Any) -> str:
            s = str(v or "").strip()
            if not s:
                return ""
            u = s.upper()
            if u in {"IDCEVO", "IDCEVO25", "IDCEVO_25", "IDCEVO-25"}:
                return "IDCEVO"
            if u in {"IDC"}:
                return "IDC"
            if u in {"MGU", "MGU22", "MGU21", "MGU18"}:
                return "MGU"
            if u in {"APP"}:
                return "APP"
            if u in {"RSU"}:
                return "RSU"
            return u

        target = _norm_project(project)
        if not target:
            return {"success": False, "tool": self.name, "error": "project 无法解析"}

        ddf = defects.copy()
        tdf = tests.copy()

        d_proj_col = "tproject" if "tproject" in ddf.columns else "project" if "project" in ddf.columns else None
        d_time_col = "tcreationtime" if "tcreationtime" in ddf.columns else "creation_time" if "creation_time" in ddf.columns else None
        if not d_proj_col or not d_time_col:
            return {"success": False, "tool": self.name, "error": "缺陷数据缺少项目列或时间列"}
        ddf["_project_norm"] = ddf[d_proj_col].map(_norm_project)
        ddf["_t"] = pd.to_datetime(ddf[d_time_col], errors="coerce", utc=True)
        ddf = ddf[(ddf["_project_norm"] == target) & (ddf["_t"].notna())]

        t_proj_col = "project" if "project" in tdf.columns else "tproject" if "tproject" in tdf.columns else None
        t_status_col = "run_status" if "run_status" in tdf.columns else "status" if "status" in tdf.columns else "native_status" if "native_status" in tdf.columns else None
        t_time_col = None
        for c in ["finished_udf_dt", "finished_udf", "finished", "started", "creation_time", "tcreationtime"]:
            if c in tdf.columns:
                t_time_col = c
                break
        if not t_proj_col or not t_time_col:
            return {"success": False, "tool": self.name, "error": "测试数据缺少项目列或时间列"}
        tdf["_project_norm"] = tdf[t_proj_col].map(_norm_project)
        tdf["_t"] = pd.to_datetime(tdf[t_time_col], errors="coerce", utc=True)
        tdf = tdf[(tdf["_project_norm"] == target) & (tdf["_t"].notna())]

        if ddf.empty:
            return {
                "success": True,
                "tool": self.name,
                "result": {"project": project, "weeks": weeks, "note": "该项目在缺陷数据中无记录"},
                "insights": ["缺陷侧没有匹配记录（可能是项目命名不一致或当前过滤后为空）"],
            }
        if tdf.empty:
            return {
                "success": True,
                "tool": self.name,
                "result": {"project": project, "weeks": weeks, "note": "该项目在测试数据中无记录"},
                "insights": ["测试侧没有匹配记录（可能是项目命名不一致或当前过滤后为空）"],
            }

        end_time = min(ddf["_t"].max(), tdf["_t"].max())
        start_time = end_time - pd.Timedelta(days=weeks * 7)
        prev_start = start_time - pd.Timedelta(days=weeks * 7)

        def _weekly_counts(frame: pd.DataFrame, time_col: str) -> pd.DataFrame:
            out = frame.copy()
            out["_week"] = out[time_col].dt.to_period("W").astype(str)
            g = out.groupby("_week", dropna=False).size().reset_index(name="count").sort_values("_week")
            return g

        d_win = ddf[(ddf["_t"] > prev_start) & (ddf["_t"] <= end_time)].copy()
        d_win["_week"] = d_win["_t"].dt.to_period("W").astype(str)
        d_week = d_win.groupby("_week").size().reset_index(name="defects").sort_values("_week")
        d_recent = d_win[(d_win["_t"] > start_time) & (d_win["_t"] <= end_time)]
        d_prev = d_win[(d_win["_t"] > prev_start) & (d_win["_t"] <= start_time)]
        d_recent_n = int(len(d_recent))
        d_prev_n = int(len(d_prev))

        failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
        if t_status_col:
            tdf["_is_failure"] = tdf[t_status_col].astype(str).str.lower().apply(lambda s: any(k in s for k in failure_keywords))
        else:
            tdf["_is_failure"] = False
        t_win = tdf[(tdf["_t"] > prev_start) & (tdf["_t"] <= end_time)].copy()
        t_win["_week"] = t_win["_t"].dt.to_period("W").astype(str)
        t_week = t_win.groupby("_week").agg(total=("_week", "size"), failure=("_is_failure", "sum")).reset_index().sort_values("_week")
        t_week["failure_rate"] = np.where(t_week["total"] > 0, (t_week["failure"] / t_week["total"] * 100).round(2), 0.0)
        t_recent = t_win[(t_win["_t"] > start_time) & (t_win["_t"] <= end_time)]
        t_prev = t_win[(t_win["_t"] > prev_start) & (t_win["_t"] <= start_time)]
        t_recent_total = int(len(t_recent))
        t_prev_total = int(len(t_prev))
        t_recent_fail = int(t_recent["_is_failure"].sum()) if t_recent_total else 0
        t_prev_fail = int(t_prev["_is_failure"].sum()) if t_prev_total else 0
        t_recent_rate = round(t_recent_fail / t_recent_total * 100, 2) if t_recent_total else 0.0
        t_prev_rate = round(t_prev_fail / t_prev_total * 100, 2) if t_prev_total else 0.0

        def _trend_flag(curr: int, prev: int) -> str:
            if prev <= 0 and curr > 0:
                return "上升"
            if prev <= 0 and curr <= 0:
                return "持平"
            ratio = curr / prev if prev else 0.0
            if ratio >= 1.08:
                return "上升"
            if ratio <= 0.92:
                return "下降"
            return "持平"

        defect_trend = _trend_flag(d_recent_n, d_prev_n)
        test_trend = "变差" if (t_recent_rate - t_prev_rate) >= 0.5 else ("改善" if (t_prev_rate - t_recent_rate) >= 0.5 else "持平")

        insights = [
            f"缺陷：最近{weeks}周={d_recent_n}，前{weeks}周={d_prev_n}，趋势={defect_trend}",
            f"测试：最近{weeks}周失败率={t_recent_rate}%（{t_recent_fail}/{t_recent_total}），前{weeks}周={t_prev_rate}%（{t_prev_fail}/{t_prev_total}），趋势={test_trend}",
        ]

        return {
            "success": True,
            "tool": self.name,
            "result": {
                "project": project,
                "project_norm": target,
                "weeks": weeks,
                "window": {
                    "end_time": str(end_time),
                    "recent_start": str(start_time),
                    "previous_start": str(prev_start),
                },
                "defects": {
                    "recent_total": d_recent_n,
                    "previous_total": d_prev_n,
                    "trend": defect_trend,
                    "weekly": d_week.tail(12).to_dict(orient="records"),
                },
                "tests": {
                    "recent_total": t_recent_total,
                    "previous_total": t_prev_total,
                    "recent_failure_rate": t_recent_rate,
                    "previous_failure_rate": t_prev_rate,
                    "trend": test_trend,
                    "weekly": t_week.tail(12).to_dict(orient="records"),
                },
                "answer": {
                    "defects_increasing": defect_trend == "上升",
                    "tests_worsening": test_trend == "变差",
                },
            },
            "insights": insights,
        }
