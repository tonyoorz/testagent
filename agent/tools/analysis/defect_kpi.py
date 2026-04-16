"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
from analysis_utils import compute_defect_explore_kpis

logger = logging.getLogger(__name__)


class DefectExploreKpiTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_kpis",
            description="生成 Defect Explore 看板常用 KPI（总缺陷、严重缺陷率、活跃 tester、日均缺陷等）",
            parameters={
                "start_date": {"type": "string", "description": "筛选起始日期(YYYY-MM-DD)，可为空", "default": ""},
                "end_date": {"type": "string", "description": "筛选结束日期(YYYY-MM-DD)，可为空", "default": ""},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            start_date = (kwargs.get("start_date") or "").strip() or None
            end_date = (kwargs.get("end_date") or "").strip() or None
            kpis = compute_defect_explore_kpis(data, start_date=start_date, end_date=end_date)
            insights = []
            insights.append(f"总缺陷数: {kpis.get('total_defects', 0)}")
            insights.append(f"严重缺陷率: {kpis.get('severe_rate', 0)}%")
            if kpis.get("top_tester"):
                insights.append(f"最活跃 tester: {kpis.get('top_tester')}")
            if kpis.get("daily_avg", 0) > 0:
                insights.append(f"日均缺陷: {kpis.get('daily_avg')}")
            return {"success": True, "tool": self.name, "result": kpis, "insights": insights}
        except Exception as e:
            logger.error(f"Defect Explore KPI 计算失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
