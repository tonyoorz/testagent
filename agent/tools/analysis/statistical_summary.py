"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class StatisticalSummaryTool(DataAnalysisTool):
    """统计摘要工具"""

    def __init__(self):
        super().__init__(
            name="statistical_summary",
            description="生成数据的统计摘要，包括分布、异常值等",
            parameters={
                "columns": {
                    "type": "array",
                    "description": "要统计的列名，留空则自动选择关键列",
                    "items": {"type": "string"},
                    "default": []
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """生成统计摘要"""
        try:
            columns = kwargs.get('columns', [])

            # 自动选择关键列
            if not columns:
                key_columns = ['tproject', 'project', 'severity_group', 'severity', 'category', 'topissue', 'matrix_display', 'run_status']
                columns = [col for col in key_columns if col in data.columns]

            summary = {
                'total_records': len(data),
                'columns_analysis': {}
            }

            for col in columns:
                if col not in data.columns:
                    continue

                col_summary = {
                    'unique_count': data[col].nunique(),
                    'most_common': data[col].value_counts().head(5).to_dict(),
                    'null_count': data[col].isna().sum(),
                    'null_percentage': round(data[col].isna().mean() * 100, 2)
                }

                # 数值型列的额外统计
                if pd.api.types.is_numeric_dtype(data[col]):
                    col_summary.update({
                        'mean': round(data[col].mean(), 2),
                        'median': round(data[col].median(), 2),
                        'std': round(data[col].std(), 2),
                        'min': float(data[col].min()),
                        'max': float(data[col].max())
                    })

                summary['columns_analysis'][col] = col_summary

            # 生成洞察
            insights = self._generate_summary_insights(summary)

            return {
                "success": True,
                "tool": self.name,
                "result": summary,
                "insights": insights
            }

        except Exception as e:
            logger.error(f"统计摘要失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_summary_insights(self, summary: Dict) -> List[str]:
        """生成摘要洞察"""
        insights = []

        insights.append(f"数据集包含 {summary['total_records']} 条记录")

        for col, col_summary in summary['columns_analysis'].items():
            if col_summary['null_percentage'] > 10:
                insights.append(
                    f"警告: 列 '{col}' 有 {col_summary['null_percentage']}% 的缺失值"
                )

            if col_summary['unique_count'] == 1:
                insights.append(f"列 '{col}' 只有一个唯一值，可能无法提供有用的区分信息")

        return insights
