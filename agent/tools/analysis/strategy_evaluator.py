"""测试策略综合评估工具 — 编排层，串联风险→成熟度→异常→关联"""

import logging
from typing import Any, Dict, List

import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class StrategyEvaluatorTool(DataAnalysisTool):
    """测试策略综合评估：串联风险→覆盖→异常→关联，输出策略报告"""

    def __init__(self):
        super().__init__(
            name="strategy_evaluator",
            description="综合评估测试策略：风险热力图 + 成熟度评分 + 异常检测 + 关联发现",
            parameters={
                "top_n_modules": {
                    "type": "integer",
                    "description": "分析前 N 个高风险模块",
                    "default": 10,
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行测试策略综合评估"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"report": "数据为空，无法评估", "maturity": None, "risk_modules": [], "findings": [], "actions": []},
                    "insights": ["数据为空"],
                }

            top_n = kwargs.get("top_n_modules", 10)

            # 1. 风险热力图
            risk_result = self._run_risk_heatmap(data, top_n)

            # 2. 成熟度评分
            maturity_result = self._run_maturity(data)

            # 3. 异常检测
            anomaly_result = self._run_anomaly(data)

            # 4. 关联发现
            association_result = self._run_association(data)

            # 5. 综合报告
            report = self._build_report(maturity_result, risk_result, anomaly_result, association_result)

            # 汇总洞察
            insights = self._collect_insights(maturity_result, risk_result, anomaly_result)

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "report": report,
                    "maturity": maturity_result,
                    "risk_modules": risk_result,
                    "findings": self._extract_findings(anomaly_result, association_result),
                    "actions": maturity_result.get("actions", []) if maturity_result else [],
                },
                "insights": insights,
            }

        except Exception as e:
            logger.error("策略评估失败: %s", e, exc_info=True)
            return {"success": False, "tool": self.name, "error": str(e)}

    # ---- 子模块调用 ----

    def _run_risk_heatmap(self, data: pd.DataFrame, top_n: int) -> List[Dict]:
        """调用风险热力图模块"""
        try:
            from agent.core.risk_heatmap import ModuleRiskScorer

            module_field = _find_column(data, ["target_ecu", "ecu", "module"])
            scorer = ModuleRiskScorer(
                module_field=module_field,
                severity_field=_find_column(data, ["severity", "severity_group"]),
                status_field=_find_column(data, ["status", "status_phase"]),
                date_field=_find_column(data, ["created_date", "tcreationtime"]),
            )
            risk_df = scorer.score(data)
            if risk_df.empty:
                return []
            risk_df = risk_df.head(top_n)
            return risk_df[["module", "defect_count", "risk_score", "risk_level"]].to_dict("records")
        except Exception as e:
            logger.warning("风险热力图分析失败: %s", e)
            return []

    def _run_maturity(self, data: pd.DataFrame) -> Dict[str, Any]:
        """调用成熟度评分模块"""
        try:
            from agent.core.test_maturity import TestMaturityScorer

            scorer = TestMaturityScorer(
                status_field=_find_column(data, ["status", "status_phase"]),
                severity_field=_find_column(data, ["severity", "severity_group"]),
                date_field=_find_column(data, ["created_date", "tcreationtime"]),
                module_field=_find_column(data, ["target_ecu", "ecu", "module"]),
            )
            report = scorer.score(data)
            return {
                "total_score": report.total_score,
                "total_grade": report.total_grade,
                "dimensions": [
                    {
                        "name": d.name,
                        "score": d.score,
                        "grade": d.grade,
                        "actual": d.actual,
                        "note": d.note,
                    }
                    for d in report.dimensions
                ],
                "actions": report.actions,
            }
        except Exception as e:
            logger.warning("成熟度评估失败: %s", e)
            return {"total_score": 0, "total_grade": "?", "dimensions": [], "actions": []}

    def _run_anomaly(self, data: pd.DataFrame) -> Dict[str, Any]:
        """调用异常检测模块"""
        try:
            from agent.core.anomaly_detector import TimeSeriesAnomalyDetector

            time_series = self._build_time_series(data)
            if not time_series:
                return {"events": [], "report": ""}

            detector = TimeSeriesAnomalyDetector()
            events = detector.detect(time_series, key_field="group", value_field="value")

            return {
                "events": [
                    {"type": e.type, "severity": e.severity, "period": e.period, "description": e.description}
                    for e in events
                ],
                "high_count": sum(1 for e in events if e.severity == "high"),
            }
        except Exception as e:
            logger.warning("异常检测失败: %s", e)
            return {"events": [], "high_count": 0}

    def _run_association(self, data: pd.DataFrame) -> Dict[str, Any]:
        """调用关联发现模块"""
        try:
            from agent.core.association_anomaly_discoverer import AssociationMiner

            # 选择可用的维度列
            dim_candidates = ["target_ecu", "severity", "project", "reporter", "status", "fv"]
            available_dims = [c for c in dim_candidates if c in data.columns]
            if len(available_dims) < 2:
                return {"associations": []}

            miner = AssociationMiner(min_support=0.03, min_confidence=0.4, min_lift=1.1)
            rules = miner.mine(data, available_dims)

            return {
                "associations": [
                    {
                        "antecedent": r.antecedent,
                        "consequent": r.consequent,
                        "lift": r.lift,
                        "description": r.description,
                        "significance": r.significance,
                    }
                    for r in rules[:10]
                ],
            }
        except Exception as e:
            logger.warning("关联发现失败: %s", e)
            return {"associations": []}

    # ---- 报告生成 ----

    def _build_report(
        self,
        maturity: Dict,
        risk_modules: List[Dict],
        anomaly: Dict,
        association: Dict,
    ) -> str:
        """生成综合策略报告"""
        lines = ["## 测试策略评估报告", ""]

        # 成熟度
        grade = maturity.get("total_grade", "?")
        score = maturity.get("total_score", 0)
        lines.append(f"### 成熟度: {grade} ({score}/100)")

        dims = maturity.get("dimensions", [])
        for d in dims:
            emoji = "🟢" if d["grade"] in ("A", "B") else ("🟡" if d["grade"] == "C" else "🔴")
            lines.append(f"  {emoji} {d['name']}: {d['grade']} ({d['score']}) — {d['note']}")
        lines.append("")

        # 关键发现
        findings = self._extract_findings(anomaly, association)
        if findings:
            lines.append(f"### 关键发现（{len(findings)}条）")
            for i, f in enumerate(findings[:5], 1):
                lines.append(f"  {i}. {f}")
            lines.append("")

        # 风险模块
        if risk_modules:
            lines.append("### 高风险模块 TOP5")
            for m in risk_modules[:5]:
                level_emoji = {"P0": "🔴", "P1": "🟡", "P2": "🟢", "P3": "⚪"}.get(m.get("risk_level", ""), "⚪")
                lines.append(f"  {level_emoji} {m['module']}: 风险分 {m['risk_score']}, 缺陷 {m['defect_count']}个")
            lines.append("")

        # 建议行动
        actions = maturity.get("actions", [])
        if actions:
            lines.append("### 建议行动")
            for i, a in enumerate(actions, 1):
                lines.append(f"  {i}. {a}")

        return "\n".join(lines)

    def _extract_findings(self, anomaly: Dict, association: Dict) -> List[str]:
        """提取关键发现"""
        findings = []

        # 异常发现
        high_events = [e for e in anomaly.get("events", []) if e.get("severity") == "high"]
        if high_events:
            findings.append(f"🔴 检测到 {len(high_events)} 个高严重度异常事件")
            for e in high_events[:2]:
                findings.append(f"   → {e.get('description', '')}")

        # 关联发现
        high_assoc = [a for a in association.get("associations", []) if a.get("significance") == "high"]
        if high_assoc:
            findings.append(f"🔍 发现 {len(high_assoc)} 个高显著性跨维度关联")
            for a in high_assoc[:2]:
                findings.append(f"   → {a.get('description', '')}")

        if not findings:
            findings.append("✅ 未发现显著风险信号，整体状况良好")

        return findings

    def _collect_insights(self, maturity: Dict, risk_modules: List[Dict], anomaly: Dict) -> List[str]:
        """收集洞察"""
        insights = []

        grade = maturity.get("total_grade", "?")
        score = maturity.get("total_score", 0)
        insights.append(f"测试成熟度: {grade} ({score}/100)")

        p0_count = sum(1 for m in risk_modules if m.get("risk_level") == "P0")
        if p0_count:
            insights.append(f"有 {p0_count} 个P0级高风险模块需紧急关注")

        high_anomaly = anomaly.get("high_count", 0)
        if high_anomaly:
            insights.append(f"检测到 {high_anomaly} 个高严重度异常")

        return insights

    # ---- 辅助 ----

    def _build_time_series(self, data: pd.DataFrame) -> List[Dict]:
        """构建时序数据"""
        time_col = _find_column(data, ["tcreationtime", "creation_time", "created_at", "created_date", "finished_udf_dt"])
        if time_col not in data.columns:
            return []

        df = data.copy()
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])
        if df.empty:
            return []

        df["_group"] = df[time_col].dt.to_period("W").astype(str)
        grouped = df.groupby("_group").size().reset_index(name="value")
        return [{"group": str(r["_group"]), "value": int(r["value"])} for _, r in grouped.iterrows()]


def _find_column(data: pd.DataFrame, candidates: List[str]) -> str:
    """查找第一个存在的列"""
    for c in candidates:
        if c in data.columns:
            return c
    return candidates[0]
