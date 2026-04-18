"""关联异常发现工具 — 包装 association_anomaly_discoverer 模块"""

import logging
from typing import Any, Dict, List

import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class AssociationDiscoveryTool(DataAnalysisTool):
    """关联发现工具：跨维度关联规则挖掘 + OTA影响 + 测试效率 + ECU乒乓"""

    def __init__(self):
        super().__init__(
            name="association_discovery",
            description="发现跨维度隐藏关联模式，包括OTA升级影响、测试人员效率、时间模式、ECU间传递",
            parameters={
                "scenario": {
                    "type": "string",
                    "description": "分析场景: all / ota_impact / tester_efficiency / time_pattern / ecu_pingpong",
                    "default": "all",
                },
                "dimensions": {
                    "type": "array",
                    "description": "关联挖掘的维度列名列表",
                    "items": {"type": "string"},
                    "default": [],
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行关联发现分析"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"associations": [], "scenarios": {}, "report": ""},
                    "insights": ["数据为空，无法执行关联分析"],
                }

            scenario = kwargs.get("scenario", "all")
            dimensions = kwargs.get("dimensions") or []

            from agent.core.association_anomaly_discoverer import (
                AssociationMiner,
                CrossDimensionAnalyzer,
                AnomalyDigestGenerator,
            )

            result_data: Dict[str, Any] = {}

            # 1. 关联规则挖掘
            associations_result = []
            if dimensions:
                if isinstance(dimensions, str):
                    dimensions = [d.strip() for d in dimensions.split(",") if d.strip()]

                # 过滤到实际存在的列
                valid_dims = [d for d in dimensions if d in data.columns]

                if len(valid_dims) >= 2:
                    miner = AssociationMiner()
                    rules = miner.mine(data, valid_dims)

                    associations_result = [
                        {
                            "antecedent": r.antecedent,
                            "consequent": r.consequent,
                            "support": r.support,
                            "confidence": r.confidence,
                            "lift": r.lift,
                            "description": r.description,
                            "significance": r.significance,
                        }
                        for r in rules
                    ]
            elif len(data.columns) >= 2:
                # 自动选取常见维度
                auto_dims = [
                    c for c in ["target_ecu", "severity", "project", "fv", "reporter"]
                    if c in data.columns
                ]
                if len(auto_dims) >= 2:
                    miner = AssociationMiner()
                    rules = miner.mine(data, auto_dims)
                    associations_result = [
                        {
                            "antecedent": r.antecedent,
                            "consequent": r.consequent,
                            "support": r.support,
                            "confidence": r.confidence,
                            "lift": r.lift,
                            "description": r.description,
                            "significance": r.significance,
                        }
                        for r in rules
                    ]

            result_data["associations"] = associations_result

            # 2. 场景分析
            analyzer = CrossDimensionAnalyzer()
            digest_gen = AnomalyDigestGenerator()

            if scenario == "all":
                scenario_results = analyzer.analyze_all(data)
                result_data["scenarios"] = scenario_results
                result_data["report"] = digest_gen.generate_scenario_digest(scenario_results)
            else:
                scenario_result = analyzer.analyze(data, scenario)
                result_data["scenarios"] = {scenario: scenario_result}
                findings = scenario_result.get("findings", [])
                result_data["report"] = "\n".join(findings) if findings else "未发现显著模式"

            # 关联摘要
            if associations_result:
                rules_for_digest = []
                for r_dict in associations_result[:10]:
                    from agent.core.association_anomaly_discoverer import Association
                    rules_for_digest.append(Association(
                        antecedent=r_dict["antecedent"],
                        consequent=r_dict["consequent"],
                        support=r_dict["support"],
                        confidence=r_dict["confidence"],
                        lift=r_dict["lift"],
                        description=r_dict["description"],
                        dimensions=[],
                        significance=r_dict["significance"],
                    ))
                result_data["association_report"] = digest_gen.generate(rules_for_digest)

            return {
                "success": True,
                "tool": self.name,
                "result": result_data,
                "insights": self._generate_insights(associations_result, result_data.get("scenarios", {})),
            }

        except Exception as e:
            logger.error("关联发现分析失败: %s", e)
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_insights(self, associations: List[Dict], scenarios: Dict) -> List[str]:
        """生成洞察"""
        insights = []

        if associations:
            high = [a for a in associations if a.get("significance") == "high"]
            insights.append(f"发现 {len(associations)} 条关联规则，其中 {len(high)} 条高显著性")

        for scenario_name, result in scenarios.items():
            if isinstance(result, dict) and result.get("success"):
                findings = result.get("findings", [])
                if findings:
                    insights.append(f"[{scenario_name}] {findings[0]}")

        if not insights:
            insights.append("未发现显著的跨维度关联模式")

        return insights
