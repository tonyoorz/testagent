"""风险热力图工具 — 包装 risk_heatmap 模块"""

import logging
from typing import Any, Dict, List

import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class RiskHeatmapTool(DataAnalysisTool):
    """风险热力图工具：模块级风险评分 + 热力图 + 测试优先级推荐"""

    def __init__(self):
        super().__init__(
            name="risk_heatmap",
            description="生成模块风险热力图和测试优先级推荐，评估各模块风险等级",
            parameters={
                "module_field": {
                    "type": "string",
                    "description": "模块标识字段名",
                    "default": "target_ecu",
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回前 N 个高风险模块",
                    "default": 10,
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行风险热力图分析"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"modules": [], "heatmap_text": "", "priorities": []},
                    "insights": ["数据为空，无法生成风险热力图"],
                }

            module_field = kwargs.get("module_field", "target_ecu")
            top_n = kwargs.get("top_n", 10)

            # 自适应字段映射
            if module_field not in data.columns:
                for candidate in ["target_ecu", "ecu", "module"]:
                    if candidate in data.columns:
                        module_field = candidate
                        break

            from agent.core.risk_heatmap import (
                ModuleRiskScorer,
                RiskHeatmapGenerator,
                TestPriorityRecommender,
            )

            # 风险评分
            scorer = ModuleRiskScorer(
                module_field=module_field,
                severity_field=_find_column(data, ["severity", "severity_group"]),
                status_field=_find_column(data, ["status", "status_phase"]),
                date_field=_find_column(data, ["created_date", "tcreationtime"]),
            )
            risk_df = scorer.score(data)

            if risk_df.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"modules": [], "heatmap_text": "", "priorities": []},
                    "insights": ["无法计算模块风险评分"],
                }

            # 截取 top_n
            risk_df = risk_df.head(top_n)

            # 生成热力图
            heatmap_gen = RiskHeatmapGenerator()
            heatmap = heatmap_gen.generate(risk_df)
            heatmap_text = heatmap_gen.render_text(heatmap)

            # 测试优先级推荐
            recommender = TestPriorityRecommender()
            priorities = recommender.recommend(risk_df)

            # 序列化模块数据
            modules = risk_df[["module", "defect_count", "risk_score", "risk_level"]].to_dict("records")

            priority_list = [
                {
                    "module": p.module,
                    "risk_score": p.risk_score,
                    "risk_level": p.risk_level,
                    "reason": p.reason,
                    "focus_areas": p.focus_areas,
                }
                for p in priorities
            ]

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "modules": modules,
                    "heatmap_text": heatmap_text,
                    "priorities": priority_list,
                },
                "insights": self._generate_insights(risk_df, priorities),
            }

        except Exception as e:
            logger.error("风险热力图分析失败: %s", e)
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_insights(self, risk_df: pd.DataFrame, priorities) -> List[str]:
        """生成洞察"""
        insights = []

        if risk_df.empty:
            return ["无风险评分数据"]

        # P0/P1 模块
        p0 = risk_df[risk_df["risk_level"] == "P0"]
        p1 = risk_df[risk_df["risk_level"] == "P1"]

        if not p0.empty:
            names = ", ".join(p0["module"].tolist()[:3])
            insights.append(f"P0 极高风险模块: {names}")

        if not p1.empty:
            insights.append(f"共 {len(p1)} 个 P1 高风险模块需重点关注")

        avg_score = risk_df["risk_score"].mean()
        insights.append(f"模块平均风险评分: {avg_score:.1f}")

        return insights


def _find_column(data: pd.DataFrame, candidates: List[str]) -> str:
    """在 DataFrame 中查找第一个存在的列"""
    for c in candidates:
        if c in data.columns:
            return c
    return candidates[0]
