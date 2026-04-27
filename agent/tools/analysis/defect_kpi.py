"""Auto-extracted tool module."""
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

from agent.tools.base import DataAnalysisTool
from analysis_utils import compute_defect_explore_kpis

logger = logging.getLogger(__name__)


class DefectKPIParams(BaseModel):
    """KPI 工具参数模型"""
    start_date: Optional[str] = Field(default=None, description="起始日期 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束日期 YYYY-MM-DD")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError(f"日期格式必须是 YYYY-MM-DD，得到: {v}")


class DefectExploreKpiTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_kpis",
            description="生成 Defect Explore 看板常用 KPI（总缺陷、严重缺陷率、活跃 tester、日均缺陷等），支持按日期范围筛选",
            parameters={
                "start_date": {"type": "string", "description": "筛选起始日期 YYYY-MM-DD（可选）", "default": ""},
                "end_date": {"type": "string", "description": "筛选结束日期 YYYY-MM-DD（可选）", "default": ""},
            },
            param_model=DefectKPIParams,
        )

        self.usage_guide = (
            "使用场景: 获取缺陷数据的概览指标（总数、严重率、top tester、日均）。"
            "注意: 不指定日期范围则使用全部数据；日期格式必须为 YYYY-MM-DD。"
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            # 参数校验
            validated = self.validate_params(**kwargs)
            start_date = validated.get("start_date")
            end_date = validated.get("end_date")
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
