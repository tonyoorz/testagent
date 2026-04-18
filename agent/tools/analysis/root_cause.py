"""根因分析工具 — 包装 root_cause_analyzer 模块"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class RootCauseTool(DataAnalysisTool):
    """根因分析工具：缺陷文本聚类 + 多维度根因分析"""

    def __init__(self):
        super().__init__(
            name="root_cause_analysis",
            description="对缺陷数据进行多维度根因分析，包括文本聚类、ECU关联、时间规律、版本关联等",
            parameters={
                "dimensions": {
                    "type": "array",
                    "description": "分析维度：frequency/ecu_correlation/time_pattern/version_correlation/status_distribution",
                    "items": {"type": "string"},
                    "default": [],
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行根因分析"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"hypothesis": "无缺陷数据可供分析", "confidence": 0.0},
                    "insights": ["数据为空，无法执行根因分析"],
                }

            # DataFrame → List[Dict] 供 RootCauseAnalyzer 使用
            defects = data.to_dict("records")

            # 分析维度
            dimensions = kwargs.get("dimensions") or None
            if dimensions and isinstance(dimensions, str):
                dimensions = [d.strip() for d in dimensions.split(",") if d.strip()]

            from agent.core.root_cause_analyzer import RootCauseAnalyzer

            analyzer = RootCauseAnalyzer()
            report = analyzer.analyze(defects, dimensions=dimensions)

            # 序列化结果
            dimension_results = [
                {
                    "name": a.dimension,
                    "significance": a.significance,
                    "findings": a.findings,
                }
                for a in report.dimension_analysis
            ]

            cluster_info = None
            if report.cluster_info:
                cluster_info = {
                    "id": report.cluster_info.cluster_id,
                    "label": report.cluster_info.label,
                    "size": report.cluster_info.size,
                    "keywords": report.cluster_info.keywords,
                }

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "cluster_info": cluster_info,
                    "dimensions": dimension_results,
                    "hypothesis": report.hypothesis,
                    "recommended_actions": report.recommended_actions,
                    "confidence": round(report.confidence, 2),
                },
                "insights": self._generate_insights(report),
            }

        except Exception as e:
            logger.error("根因分析失败: %s", e)
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_insights(self, report) -> List[str]:
        """生成洞察"""
        insights = []

        if report.cluster_info:
            insights.append(
                f"主要聚类: {report.cluster_info.label}（{report.cluster_info.size}个缺陷）"
            )

        high_dims = [a for a in report.dimension_analysis if a.significance == "high"]
        if high_dims:
            insights.append(
                f"高相关性维度: {', '.join(a.dimension for a in high_dims)}"
            )

        if report.confidence > 0.6:
            insights.append(f"分析置信度较高 ({report.confidence:.0%})，建议参考推荐行动")
        elif report.confidence > 0.3:
            insights.append(f"分析置信度中等 ({report.confidence:.0%})，建议结合业务上下文判断")

        if not insights:
            insights.append("根因分析完成，建议查看详细报告")

        return insights
