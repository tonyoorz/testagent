"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

from agent.tools.base import DataAnalysisTool, ToolValidationError
from agent.tools.helpers import resolve_dimension_to_column, evaluate_anomaly_rules
from datetime import datetime

logger = logging.getLogger(__name__)


class TrendAnalysisParams(BaseModel):
    """趋势分析工具参数模型"""
    group_by: str = Field(default="week", description="分组维度: week/month/day 或 列名")
    metric: str = Field(default="count", description="统计指标")
    time_column: str = Field(default="tcreationtime", description="时间列名")

    @field_validator("group_by")
    @classmethod
    def validate_group_by(cls, v: str) -> str:
        allowed = {"day", "week", "month"}
        if v.lower() in allowed:
            return v.lower()
        # 允许其他列名（用于分组）
        return v

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        allowed = {"count", "unique", "sum", "mean", "max", "min"}
        if v not in allowed:
            raise ValueError(f"metric 必须是 {allowed} 之一，得到: {v}")
        return v


class TrendAnalysisTool(DataAnalysisTool):
    """趋势分析工具"""

    def __init__(self):
        super().__init__(
            name="analyze_trend",
            description="分析数据趋势，支持按时间（day/week/month）或自定义维度分组",
            parameters={
                "group_by": {
                    "type": "string",
                    "description": "分组维度: day/week/month 或项目/类别/状态等列名",
                    "default": "week",
                    "enum": ["day", "week", "month", "project", "aida", "severity", "status", "matrix"]
                },
                "metric": {
                    "type": "string",
                    "description": "统计指标",
                    "enum": ["count", "unique", "sum", "mean", "max", "min"],
                    "default": "count"
                },
                "time_column": {
                    "type": "string",
                    "description": "时间列名",
                    "default": "tcreationtime"
                }
            },
            param_model=TrendAnalysisParams,
        )

        self.usage_guide = (
            "使用场景: 需要看缺陷数量/风险分数随时间变化时用 week/month，"
            "需要看不同项目/类别的分布时用对应的列名。"
            "注意: day 分组适合短期数据（1-14天），week/month 适合长期趋势。"
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行趋势分析"""
        try:
            # 参数校验
            validated = self.validate_params(**kwargs)
            group_by = validated.get('group_by', 'week')
            metric = validated.get('metric', 'count')
            time_column = validated.get('time_column', 'tcreationtime')

            # 确保时间列是 datetime 类型
            if time_column not in data.columns:
                for candidate in ['tcreationtime', 'creation_time', 'created_at', 'finished_udf_dt', 'finished_udf']:
                    if candidate in data.columns:
                        time_column = candidate
                        break
            if time_column in data.columns:
                data = data.copy()
                data[time_column] = pd.to_datetime(data[time_column], errors='coerce')

            # 根据分组维度创建时间分组
            if group_by in ['week', 'month'] and time_column in data.columns:
                if group_by == 'week':
                    data['_time_group'] = data[time_column].dt.to_period('W').astype(str)
                else:
                    data['_time_group'] = data[time_column].dt.to_period('M').astype(str)
                group_cols = ['_time_group']
                label_col = '_time_group'
            else:
                dataset = str(kwargs.get("dataset") or "defects").strip().lower()
                actual_col = resolve_dimension_to_column(dataset, group_by, list(data.columns))
                if not actual_col:
                    fallback = {
                        "project": ["tproject", "project"],
                        "aida": ["aida_english", "top_aida", "aida"],
                        "severity": ["severity_group", "severity"],
                        "status": ["status_phase", "status"],
                        "matrix": ["matrix_display", "matrix"],
                    }
                    for c in fallback.get(str(group_by).strip().lower(), []):
                        if c in data.columns:
                            actual_col = c
                            break
                if not actual_col or actual_col not in data.columns:
                    return {"success": False, "tool": self.name, "error": f"列 {group_by} 不存在"}
                group_cols = [actual_col]
                label_col = actual_col

            # 执行分组统计
            if metric == 'count':
                result = data.groupby(group_cols).size().reset_index(name='value')
            elif metric == 'unique':
                unique_col = None
                for c in ['_id', 'id', 'ticket_id']:
                    if c in data.columns:
                        unique_col = c
                        break
                if not unique_col:
                    result = data.groupby(group_cols).size().reset_index(name='value')
                else:
                    result = data.groupby(group_cols).agg({unique_col: 'nunique'}).reset_index(name='value')
            else:
                numeric_cols = data.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) == 0:
                    return {"success": False, "tool": self.name, "error": "没有数值列可用于聚合"}
                result = data.groupby(group_cols)[numeric_cols[0]].agg(metric).reset_index(name='value')

            if group_by not in ['week', 'month']:
                result = result.sort_values('value', ascending=False).head(20)

            # 转换为返回格式
            trend_data = []
            for _, row in result.iterrows():
                trend_data.append({
                    'group': row[label_col],
                    'value': int(row['value']) if metric in ['count', 'unique', 'sum'] else float(row['value'])
                })

            # 计算趋势指标
            values = [item['value'] for item in trend_data]
            trend_direction = "上升" if len(values) > 1 and values[-1] > values[0] else "下降"
            change_rate = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "trend_data": trend_data,
                    "summary": {
                        "direction": trend_direction,
                        "change_rate": round(change_rate, 2),
                        "total": sum(values),
                        "average": round(np.mean(values), 2),
                        "max": max(values),
                        "min": min(values)
                    }
                },
                "insights": self._generate_insights(trend_data, trend_direction, change_rate)
            }

        except Exception as e:
            logger.error(f"趋势分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_insights(self, trend_data: List[Dict], direction: str, change_rate: float) -> List[str]:
        """生成趋势洞察"""
        insights = []

        if len(trend_data) < 2:
            insights.append("数据点较少，建议收集更多数据以准确分析趋势")
        else:
            insights.append(f"整体呈{direction}趋势，变化率为 {change_rate:.1f}%")

            anomaly_findings = evaluate_anomaly_rules(trend_data)
            if anomaly_findings:
                insights.append(f"检测到 {len(anomaly_findings)} 个异常数据点，需要关注")

        return insights
