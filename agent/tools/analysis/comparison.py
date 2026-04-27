"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

from agent.tools.base import DataAnalysisTool
from analysis_utils import pick_risk_score_column

logger = logging.getLogger(__name__)


class ComparisonParams(BaseModel):
    """对比分析工具参数模型"""
    items: List[str] = Field(default_factory=list, description="要对比的项目列表（为空则自动选择）")
    dimension: str = Field(default="project", description="对比维度")
    metrics: List[str] = Field(
        default=["count", "avg_risk_score", "topissue_ratio"],
        description="对比指标"
    )

    @field_validator("dimension")
    @classmethod
    def validate_dimension(cls, v: str) -> str:
        allowed = {"project", "severity", "category", "tester", "aida", "matrix"}
        if v.lower() in allowed:
            return v.lower()
        # 允许其他列名（自定义维度）
        return v

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, v: List[str]) -> List[str]:
        allowed = {"count", "avg_risk_score", "topissue_ratio", "high_risk_ratio", "close_rate"}
        invalid = [m for m in v if m not in allowed]
        if invalid:
            raise ValueError(f"metrics 包含无效值: {invalid}。可用值: {allowed}")
        return v


class ComparisonTool(DataAnalysisTool):
    """对比分析工具"""

    def __init__(self):
        super().__init__(
            name="compare_items",
            description="对比不同项目、严重性、类别等维度的多项指标（缺陷数、风险评分、TopIssue 比例等）",
            parameters={
                "items": {
                    "type": "array",
                    "description": "要对比的项目列表（为空则自动选择 top-3）",
                    "items": {"type": "string"}
                },
                "dimension": {
                    "type": "string",
                    "description": "对比维度: project/severity/category/tester/aida/matrix 或自定义列名",
                    "default": "project",
                    "enum": ["project", "severity", "category", "tester", "aida", "matrix"]
                },
                "metrics": {
                    "type": "array",
                    "description": "对比指标: count/avg_risk_score/topissue_ratio/high_risk_ratio/close_rate",
                    "items": {"type": "string"},
                    "default": ["count", "avg_risk_score", "topissue_ratio"]
                }
            },
            param_model=ComparisonParams,
        )

        self.usage_guide = (
            "使用场景: 对比不同项目/类别/测试人员的表现时。"
            "注意: items 为空时自动选择数据中最多的 top-3；"
            "支持跨项目对比缺陷数、风险评分、TopIssue 比例等多维度指标。"
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行对比分析"""
        try:
            # 参数校验
            validated = self.validate_params(**kwargs)
            items = validated.get('items', [])
            dimension = validated.get('dimension', 'project')
            metrics = validated.get('metrics', ['count', 'avg_risk_score', 'topissue_ratio'])

            # 映射维度列名
            col_mapping = {
                'project': 'tproject',
                'severity': 'severity_group',
                'category': 'category'
            }
            group_col = col_mapping.get(dimension, dimension)
            if dimension == 'project':
                if 'project' in data.columns and 'tproject' in data.columns:
                    expected = {"idc", "idcevo", "mgu", "rsu", "app"}
                    p = data['project'].astype(str).str.strip().str.lower()
                    tp = data['tproject'].astype(str).str.strip().str.lower()
                    p_hits = int(p.isin(expected).sum())
                    tp_hits = int(tp.isin(expected).sum())
                    group_col = 'project' if p_hits >= tp_hits else 'tproject'
                elif group_col == 'tproject' and group_col not in data.columns and 'project' in data.columns:
                    group_col = 'project'

            if group_col not in data.columns:
                return {"success": False, "tool": self.name, "error": f"列 {group_col} 不存在"}

            if not items:
                if dimension == 'project':
                    s = data[group_col].fillna("").astype(str).str.strip()
                    s = s[s != ""]
                    if s.empty:
                        return {"success": False, "tool": self.name, "error": "项目字段为空，无法自动选择对比项目"}
                    items = s.value_counts().head(3).index.tolist()
                else:
                    return {"success": False, "tool": self.name, "error": "请提供要对比的项目"}

            # 筛选数据
            comparison_data = data[data[group_col].isin(items)]

            if comparison_data.empty:
                return {"success": False, "tool": self.name, "error": f"未找到匹配的数据: {items}"}

            # 计算各项指标
            comparison_results = []

            for item in items:
                item_data = comparison_data[comparison_data[group_col] == item]

                result = {
                    'name': item,
                    'metrics': {}
                }

                for metric in metrics:
                    if metric == 'count':
                        result['metrics']['count'] = len(item_data)
                    elif metric == 'avg_risk_score':
                        score_col = pick_risk_score_column(item_data)
                        if score_col:
                            s = pd.to_numeric(item_data[score_col], errors="coerce")
                            score = float(s.mean()) if s.notna().any() else 0.0
                        else:
                            score = 0
                            score += min(len(item_data) / 100 * 30, 30)
                            if 'severity_group' in item_data.columns:
                                severity_weights = {'Critical': 40, 'Major': 25, 'Minor': 10}
                                avg_severity = item_data['severity_group'].map(severity_weights).mean()
                                score += avg_severity if pd.notna(avg_severity) else 15
                        result['metrics']['avg_risk_score'] = round(float(score), 2)
                    elif metric == 'topissue_ratio':
                        if 'topissue' in item_data.columns:
                            ratio = item_data['topissue'].eq('TopIssue').mean() * 100
                            result['metrics']['topissue_ratio'] = round(ratio, 2)
                        else:
                            result['metrics']['topissue_ratio'] = 0

                comparison_results.append(result)

            # 生成对比洞察
            insights = self._generate_comparison_insights(comparison_results, metrics)

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "dimension": dimension,
                    "comparisons": comparison_results
                },
                "insights": insights
            }

        except Exception as e:
            logger.error(f"对比分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_comparison_insights(self, results: List[Dict], metrics: List[str]) -> List[str]:
        """生成对比洞察"""
        insights = []

        if len(results) < 2:
            return ["需要至少 2 个项目进行对比"]

        # 找出每个指标的最好和最差
        for metric in metrics:
            values = [(r['name'], r['metrics'].get(metric, 0)) for r in results]

            if metric == 'count':
                best = max(values, key=lambda x: x[1])
                worst = min(values, key=lambda x: x[1])
                insights.append(
                    f"在缺陷数量方面，'{best[0]}' 最高 ({best[1]})，"
                    f"'{worst[0]}' 最低 ({worst[1]})"
                )
            elif metric == 'avg_risk_score':
                best = max(values, key=lambda x: x[1])
                worst = min(values, key=lambda x: x[1])
                insights.append(
                    f"在风险评分方面，'{best[0]}' 最高 ({best[1]})，"
                    f"'{worst[0]}' 最低 ({worst[1]})"
                )
            elif metric == 'topissue_ratio':
                best = max(values, key=lambda x: x[1])
                if best[1] > 0:
                    insights.append(
                        f"'{best[0]}' 的 TopIssue 比例最高 ({best[1]}%)，需要重点关注"
                    )

        return insights
