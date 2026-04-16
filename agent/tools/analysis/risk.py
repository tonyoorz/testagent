"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
from agent.tools.helpers import resolve_dimension_to_column
from analysis_utils import pick_risk_score_column

logger = logging.getLogger(__name__)


class RiskAnalysisTool(DataAnalysisTool):
    """风险分析工具"""

    def __init__(self):
        super().__init__(
            name="analyze_risk",
            description="分析风险分布，识别高风险项目和缺陷",
            parameters={
                "dimension": {
                    "type": "string",
                    "description": "分析维度",
                    "default": "project"
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回前 N 个高风险项",
                    "default": 10
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行风险分析"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"dimension": kwargs.get('dimension', 'project'), "risk_items": []},
                    "insights": ["数据为空，无法计算风险分布"]
                }
            dimension = kwargs.get('dimension', 'project')
            top_n = kwargs.get('top_n', 10)

            dataset = str(kwargs.get("dataset") or "defects").strip().lower()
            group_col = resolve_dimension_to_column(dataset, str(dimension), list(data.columns))
            if not group_col:
                fallback = {
                    "project": ["tproject", "project"],
                    "matrix": ["matrix_display", "matrix"],
                    "severity": ["severity_group", "severity"],
                    "category": ["category"],
                }
                for c in fallback.get(str(dimension).strip().lower(), []):
                    if c in data.columns:
                        group_col = c
                        break

            if group_col not in data.columns:
                return {"success": False, "tool": self.name, "error": f"列 {group_col} 不存在"}

            # 计算风险评分
            def calculate_risk_score(group):
                """计算风险评分"""
                score_col = pick_risk_score_column(group)
                if score_col:
                    s = pd.to_numeric(group[score_col], errors="coerce")
                    if s.notna().any():
                        return float(round(s.mean(), 2))

                score = 0

                # 1. 缺陷数量权重 (30%)
                count = len(group)
                score += min(count / 100 * 30, 30)

                # 2. 严重性权重 (40%)
                if 'severity_group' in group.columns:
                    severity_weights = {'Critical': 40, 'Major': 25, 'Minor': 10}
                    avg_severity = group['severity_group'].map(severity_weights).mean()
                    score += avg_severity if pd.notna(avg_severity) else 15

                # 3. TopIssue 权重 (20%)
                if 'topissue' in group.columns:
                    topissue_ratio = group['topissue'].eq('TopIssue').mean()
                    score += topissue_ratio * 20

                # 4. 矩阵位置权重 (10%)
                if 'matrix_display' in group.columns:
                    high_risk_matrices = ['1A', '1B', '1C', '1D', '1E']
                    matrix_code = group['matrix_display'].astype(str).str.replace('MATRIX-', '', regex=False).str.replace('Matrix-', '', regex=False).str.upper()
                    high_risk_ratio = matrix_code.isin(high_risk_matrices).mean()
                    score += high_risk_ratio * 10

                return round(score, 2)

            # 按维度分组并计算风险评分
            risk_analysis = data.groupby(group_col).apply(calculate_risk_score).reset_index()
            risk_analysis.columns = [group_col, 'risk_score']
            risk_analysis = risk_analysis.sort_values('risk_score', ascending=False).head(top_n)

            # 生成结果
            risk_items = []
            for _, row in risk_analysis.iterrows():
                group_key = row[group_col]
                group_data = data[data[group_col] == group_key]

                risk_items.append({
                    'name': group_key,
                    'risk_score': float(row['risk_score']),
                    'defect_count': len(group_data),
                    'topissue_count': group_data['topissue'].eq('TopIssue').sum() if 'topissue' in group_data.columns else 0,
                    'high_risk_ratio': self._calculate_high_risk_ratio(group_data)
                })

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "dimension": dimension,
                    "risk_items": risk_items
                },
                "insights": self._generate_risk_insights(risk_items)
            }

        except Exception as e:
            logger.error(f"风险分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _calculate_high_risk_ratio(self, group_data: pd.DataFrame) -> float:
        """计算高风险比例"""
        if 'matrix_display' not in group_data.columns:
            return 0.0

        high_risk_matrices = ['1A', '1B', '1C', '1D', '1E']
        return round(
            group_data['matrix_display'].astype(str).str.replace('MATRIX-', '', regex=False).str.replace('Matrix-', '', regex=False).str.upper().isin(high_risk_matrices).sum() / len(group_data) * 100,
            2
        )

    def _generate_risk_insights(self, risk_items: List[Dict]) -> List[str]:
        """生成风险洞察"""
        insights = []

        if not risk_items:
            return ["没有足够的数据进行风险分析"]

        # 顶层风险
        top_risk = risk_items[0]
        insights.append(f"最高风险项是 '{top_risk['name']}'，风险评分 {top_risk['risk_score']}")

        # 风险分布
        avg_score = np.mean([item['risk_score'] for item in risk_items])
        high_risk_count = len([item for item in risk_items if item['risk_score'] > avg_score * 1.2])
        insights.append(f"有 {high_risk_count} 个项目的风险评分显著高于平均水平")

        # TopIssue 分析
        total_topissue = sum(item['topissue_count'] for item in risk_items)
        if total_topissue > 0:
            insights.append(f"高风险项目中包含 {total_topissue} 个 TopIssue，需要优先处理")

        return insights
