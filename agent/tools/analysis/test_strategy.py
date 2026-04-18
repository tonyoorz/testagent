"""测试策略推荐工具 — 包装 test_case_recommender 模块"""

import logging
from typing import Any, Dict, List

import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class TestStrategyTool(DataAnalysisTool):
    """测试策略工具：覆盖差距分析 + 测试用例建议 + 回归测试选择"""

    def __init__(self):
        super().__init__(
            name="test_strategy",
            description="分析测试覆盖差距，生成测试用例建议和回归测试策略",
            parameters={
                "analysis_type": {
                    "type": "string",
                    "description": "分析类型: coverage_gap / regression",
                    "default": "coverage_gap",
                },
                "changed_modules": {
                    "type": "array",
                    "description": "回归测试时变更的模块列表",
                    "items": {"type": "string"},
                    "default": [],
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行测试策略分析"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"gaps": [], "suggestions": [], "regression_plan": None},
                    "insights": ["数据为空，无法分析测试覆盖"],
                }

            analysis_type = kwargs.get("analysis_type", "coverage_gap")

            from agent.core.test_case_recommender import (
                TestCoverageAnalyzer,
                TestCaseGenerator,
                RegressionTestSelector,
            )

            # 覆盖差距分析
            gaps_result = []
            suggestions_result = []

            analyzer = TestCoverageAnalyzer(
                defect_module_field=_find_module_field(data),
            )

            # 尝试查找测试用例数据（可能通过 kwargs 传入或不存在）
            test_cases = kwargs.get("test_cases")
            if isinstance(test_cases, pd.DataFrame):
                gaps = analyzer.find_gaps(data, test_cases)
            else:
                # 没有测试用例数据时，只统计模块缺陷分布
                gaps = analyzer.find_gaps(data, pd.DataFrame())

            gaps_result = [
                {
                    "module": g.module,
                    "defect_count": g.defect_count,
                    "test_case_count": g.test_case_count,
                    "gap_score": g.gap_score,
                    "severity": g.severity,
                    "uncovered_areas": g.uncovered_areas,
                }
                for g in gaps
            ]

            # 回归测试选择（如果提供了 changed_modules）
            regression_result = None
            changed_modules = kwargs.get("changed_modules", [])
            if changed_modules and isinstance(test_cases, pd.DataFrame):
                selector = RegressionTestSelector()
                plan = selector.select(changed_modules, test_cases)
                regression_result = {
                    "selected_tests": plan.selected_tests,
                    "total_tests": plan.total_tests,
                    "selected_ratio": plan.selected_ratio,
                    "reason": plan.reason,
                    "estimated_effort": plan.estimated_effort,
                }

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "gaps": gaps_result,
                    "regression_plan": regression_result,
                },
                "insights": self._generate_insights(gaps),
            }

        except Exception as e:
            logger.error("测试策略分析失败: %s", e)
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_insights(self, gaps) -> List[str]:
        """生成洞察"""
        if not gaps:
            return ["未发现测试覆盖缺口"]

        insights = [f"发现 {len(gaps)} 个覆盖缺口"]

        high_gaps = [g for g in gaps if g.severity == "high"]
        if high_gaps:
            modules = ", ".join(g.module for g in high_gaps[:3])
            insights.append(f"高缺口模块: {modules}（缺陷多、测试用例少）")

        no_coverage = [g for g in gaps if g.test_case_count == 0 and g.defect_count > 0]
        if no_coverage:
            insights.append(f"{len(no_coverage)} 个模块完全无测试覆盖")

        return insights


def _find_module_field(data: pd.DataFrame) -> str:
    """查找模块字段"""
    for c in ["target_ecu", "ecu", "module"]:
        if c in data.columns:
            return c
    return "target_ecu"
