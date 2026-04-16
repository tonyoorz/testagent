"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class TopIssueHotlistTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_topissue_hotlist",
            description="输出 TopIssue/高风险票据清单（按风险分排序）",
            parameters={
                "top_n": {"type": "integer", "description": "输出前 N 条", "default": 20}
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "total": 0}, "insights": ["缺陷数据为空，无法生成清单"]}

            df = data.copy()

            score_col = None
            for c in ["topissue_risk_score", "risk_score", "topissue_score"]:
                if c in df.columns:
                    score_col = c
                    break
            if not score_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少风险分字段（topissue_risk_score/risk_score）"}

            topissue_col = None
            for c in ["is_topissue", "topissue"]:
                if c in df.columns:
                    topissue_col = c
                    break

            if topissue_col == "is_topissue":
                df = df[df[topissue_col].astype(bool)]
            elif topissue_col == "topissue":
                df = df[df[topissue_col].astype(str).str.lower().str.contains("topissue")]

            if df.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "total": 0}, "insights": ["未找到 TopIssue 票据（或 TopIssue 字段为空）"]}

            df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0.0)
            df = df.sort_values(score_col, ascending=False)

            top_n = max(1, min(int(kwargs.get("top_n", 20)), 200))
            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            pu_col = "pu" if "pu" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "status" if "status" in df.columns else None
            aida_col = "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None

            rows = []
            for _, r in df.head(top_n).iterrows():
                rows.append({
                    "id": r.get(id_col) if id_col else None,
                    "title": r.get(title_col) if title_col else None,
                    "score": float(r.get(score_col) or 0),
                    "project": r.get(project_col) if project_col else None,
                    "matrix": r.get(matrix_col) if matrix_col else None,
                    "pu": r.get(pu_col) if pu_col else None,
                    "status": r.get(status_col) if status_col else None,
                    "aida": r.get(aida_col) if aida_col else None,
                    "creation_time": str(r.get(time_col)) if time_col else None
                })

            insights = [f"TopIssue 高风险票据 Top1: {rows[0].get('id')}（score={rows[0].get('score')}）"] if rows else []
            return {"success": True, "tool": self.name, "result": {"total": int(len(df)), "rows": rows}, "insights": insights}
        except Exception as e:
            logger.error(f"TopIssue 清单生成失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
