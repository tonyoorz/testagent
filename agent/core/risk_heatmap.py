"""
风险热力图模块

基于缺陷数据计算模块级风险分数，生成热力图数据和测试优先级推荐。

Features:
1. ModuleRiskScorer - 模块级风险评分
2. RiskHeatmapGenerator - 2D风险热力图数据生成
3. TestPriorityRecommender - 测试优先级推荐

Author: AI Assistant
Date: 2026-04-12
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class HeatmapData:
    """热力图数据"""
    matrix: List[List[float]]     # 2D 数值矩阵
    x_labels: List[str]           # X 轴标签
    y_labels: List[str]           # Y 轴标签
    risk_levels: List[List[str]]  # 对应的风险等级矩阵 (P0/P1/P2/P3)
    title: str = ""


@dataclass
class TestPriority:
    """测试优先级推荐"""
    module: str
    risk_score: float
    risk_level: str        # P0/P1/P2/P3
    reason: str            # 推荐理由
    focus_areas: List[str] # 重点测试领域


# ---------------------------------------------------------------------------
# ModuleRiskScorer
# ---------------------------------------------------------------------------

class ModuleRiskScorer:
    """
    模块级风险评分器

    评分维度（各 0-100）：
    1. 频次严重度：defect_count × avg_severity_weight
    2. 趋势方向：缺陷增长/下降趋势
    3. 处理效率：解决率
    4. TopIssue 占比：高风险缺陷占比
    """

    # 严重度权重映射
    SEVERITY_WEIGHTS = {
        "1A": 10, "1B": 9, "1C": 8, "1D": 7, "1E": 6,
        "2A": 9, "2B": 8, "2C": 7, "2D": 6, "2E": 5,
        "3A": 7, "3B": 6, "3C": 5, "3D": 4, "3E": 3,
        "4A": 5, "4B": 4, "4C": 3, "4D": 2, "4E": 1,
    }

    def __init__(
        self,
        module_field: str = "target_ecu",
        severity_field: str = "severity",
        status_field: str = "status",
        date_field: str = "created_date",
        risk_score_field: str = "risk_score",
    ):
        self.module_field = module_field
        self.severity_field = severity_field
        self.status_field = status_field
        self.date_field = date_field
        self.risk_score_field = risk_score_field

    def score(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        计算模块级风险分数

        Args:
            data: 缺陷数据 DataFrame

        Returns:
            DataFrame with columns: module, defect_count, avg_severity_score,
                                    trend_direction, resolve_rate, top_issue_ratio,
                                    risk_score, risk_level
        """
        if data is None or data.empty:
            return pd.DataFrame()

        df = data.copy()
        results = []

        modules = df[self.module_field].dropna().unique() if self.module_field in df.columns else []

        for module in modules:
            module_df = df[df[self.module_field] == module]
            if module_df.empty:
                continue

            row = {"module": module, "defect_count": len(module_df)}

            # 1. 频次严重度 (0-100)
            row["avg_severity_score"] = self._calc_severity_score(module_df)
            freq_severity = min(len(module_df) * row["avg_severity_score"] / 10, 100)

            # 2. 趋势方向 (0-100)
            row["trend_direction"] = self._calc_trend(module_df)
            trend_score = self._trend_to_score(row["trend_direction"])

            # 3. 处理效率 (0-100，解决率越高分数越低)
            row["resolve_rate"] = self._calc_resolve_rate(module_df)
            efficiency_score = (1 - row["resolve_rate"]) * 100

            # 4. TopIssue占比 (0-100)
            row["top_issue_ratio"] = self._calc_top_issue_ratio(module_df)
            top_issue_score = row["top_issue_ratio"] * 100

            # 综合评分（加权）
            risk_score = (
                freq_severity * 0.35 +
                trend_score * 0.25 +
                efficiency_score * 0.20 +
                top_issue_score * 0.20
            )

            row["risk_score"] = round(risk_score, 1)
            row["risk_level"] = self._score_to_level(risk_score)
            row["freq_severity"] = round(freq_severity, 1)
            row["trend_score"] = round(trend_score, 1)
            row["efficiency_score"] = round(efficiency_score, 1)
            row["top_issue_score"] = round(top_issue_score, 1)

            results.append(row)

        result_df = pd.DataFrame(results)
        if not result_df.empty:
            result_df = result_df.sort_values("risk_score", ascending=False).reset_index(drop=True)

        return result_df

    def _calc_severity_score(self, df: pd.DataFrame) -> float:
        """计算平均严重度分数"""
        if self.severity_field not in df.columns:
            return 5.0

        scores = []
        for sev in df[self.severity_field].dropna():
            sev_str = str(sev).strip().upper()
            score = self.SEVERITY_WEIGHTS.get(sev_str, 3)
            scores.append(score)

        return np.mean(scores) if scores else 3.0

    def _calc_trend(self, df: pd.DataFrame) -> str:
        """计算趋势方向"""
        if self.date_field not in df.columns:
            return "stable"

        df_copy = df.copy()
        try:
            df_copy["_date"] = pd.to_datetime(df_copy[self.date_field], errors="coerce")
            df_copy = df_copy.dropna(subset=["_date"])
            if len(df_copy) < 2:
                return "stable"

            monthly = df_copy.set_index("_date").resample("ME").size()
            if len(monthly) < 2:
                return "stable"

            # 简单线性回归斜率
            x = np.arange(len(monthly))
            y = monthly.values
            if np.std(y) == 0:
                return "stable"

            slope = np.polyfit(x, y, 1)[0]
            avg = np.mean(y)

            if avg == 0:
                return "stable"

            pct_change = slope / avg
            if pct_change > 0.1:
                return "increasing"
            elif pct_change < -0.1:
                return "decreasing"
            return "stable"
        except Exception:
            return "stable"

    @staticmethod
    def _trend_to_score(trend: str) -> float:
        """趋势方向转分数"""
        return {"increasing": 80, "decreasing": 20, "stable": 50}.get(trend, 50)

    def _calc_resolve_rate(self, df: pd.DataFrame) -> float:
        """计算解决率"""
        if self.status_field not in df.columns:
            return 0.0

        closed_statuses = {"06", "09", "10"}
        total = len(df)
        if total == 0:
            return 0.0

        closed = 0
        for status in df[self.status_field].dropna():
            status_prefix = str(status).split("_")[0].strip()
            if status_prefix in closed_statuses:
                closed += 1

        return closed / total

    def _calc_top_issue_ratio(self, df: pd.DataFrame) -> float:
        """计算TopIssue占比"""
        if self.risk_score_field not in df.columns:
            return 0.0

        total = len(df)
        if total == 0:
            return 0.0

        try:
            scores = pd.to_numeric(df[self.risk_score_field], errors="coerce")
            top_issue_count = (scores >= 60).sum()
            return top_issue_count / total
        except Exception:
            return 0.0

    @staticmethod
    def _score_to_level(score: float) -> str:
        """分数转风险等级"""
        if score >= 70:
            return "P0"
        elif score >= 50:
            return "P1"
        elif score >= 30:
            return "P2"
        else:
            return "P3"


# ---------------------------------------------------------------------------
# RiskHeatmapGenerator
# ---------------------------------------------------------------------------

class RiskHeatmapGenerator:
    """
    风险热力图数据生成器

    生成模块 × 风险维度的 2D 矩阵数据
    """

    # 热力图颜色阈值
    COLOR_THRESHOLDS = [
        (70, "🔴"),
        (50, "🟡"),
        (30, "🟢"),
        (0, "⚪"),
    ]

    def generate(
        self,
        risk_scores: pd.DataFrame,
        x_dim: str = "risk_dimension",
        y_dim: str = "module",
    ) -> HeatmapData:
        """
        生成热力图数据

        Args:
            risk_scores: ModuleRiskScorer 的输出 DataFrame
            x_dim: X轴维度 (risk_dimension 或自定义)
            y_dim: Y轴维度

        Returns:
            HeatmapData
        """
        if risk_scores is None or risk_scores.empty:
            return HeatmapData([], [], [], [], title="风险热力图（无数据）")

        # 维度列
        dim_columns = ["freq_severity", "trend_score", "efficiency_score", "top_issue_score"]
        dim_labels = ["频次严重度", "趋势风险", "处理效率", "TopIssue占比"]

        modules = risk_scores["module"].tolist()
        matrix = []
        risk_levels = []

        for _, row in risk_scores.iterrows():
            row_values = []
            row_levels = []
            for col in dim_columns:
                val = float(row.get(col, 0))
                row_values.append(val)
                row_levels.append(self._val_to_level(val))
            matrix.append(row_values)
            risk_levels.append(row_levels)

        return HeatmapData(
            matrix=matrix,
            x_labels=dim_labels,
            y_labels=[str(m) for m in modules],
            risk_levels=risk_levels,
            title="模块风险热力图",
        )

    def generate_module_severity(
        self,
        data: pd.DataFrame,
        module_field: str = "target_ecu",
        severity_field: str = "severity",
    ) -> HeatmapData:
        """
        生成 模块 × 严重度等级 的热力图

        Args:
            data: 原始缺陷 DataFrame
            module_field: 模块字段
            severity_field: 严重度字段

        Returns:
            HeatmapData
        """
        if data is None or data.empty:
            return HeatmapData([], [], [], [], title="模块×严重度（无数据）")

        # 严重度等级
        severity_levels = ["1A", "1B", "1C", "1D", "1E",
                          "2A", "2B", "2C", "2D", "2E",
                          "3A", "3B", "3C", "3D", "3E"]

        modules = sorted(data[module_field].dropna().unique()) if module_field in data.columns else []

        matrix = []
        risk_levels = []
        max_val = 0

        # 先计算所有值
        counts: Dict[Tuple[str, str], int] = {}
        for _, row in data.iterrows():
            module = str(row.get(module_field, ""))
            severity = str(row.get(severity_field, "")).strip().upper()
            if module and severity:
                counts[(module, severity)] = counts.get((module, severity), 0) + 1

        if counts:
            max_val = max(counts.values())

        for module in modules:
            row_values = []
            row_levels = []
            for sev in severity_levels:
                val = counts.get((module, sev), 0)
                normalized = (val / max_val * 100) if max_val > 0 else 0
                row_values.append(normalized)
                row_levels.append(self._val_to_level(normalized))
            matrix.append(row_values)
            risk_levels.append(row_levels)

        return HeatmapData(
            matrix=matrix,
            x_labels=severity_levels,
            y_labels=[str(m) for m in modules],
            risk_levels=risk_levels,
            title="模块×严重度等级 热力图",
        )

    def render_text(self, heatmap: HeatmapData) -> str:
        """
        将热力图渲染为文本格式

        Args:
            heatmap: 热力图数据

        Returns:
            文本渲染结果
        """
        if not heatmap.matrix:
            return "（无数据）"

        lines = [heatmap.title, ""]

        # 表头
        header = f"{'模块':<20}"
        for label in heatmap.x_labels:
            header += f" {label:<10}"
        lines.append(header)
        lines.append("-" * len(header))

        # 数据行
        for i, y_label in enumerate(heatmap.y_labels):
            row = f"{y_label:<20}"
            for j in range(len(heatmap.x_labels)):
                val = heatmap.matrix[i][j] if i < len(heatmap.matrix) and j < len(heatmap.matrix[i]) else 0
                emoji = self._val_to_emoji(val)
                row += f" {emoji}{val:>4.0f}    "
            lines.append(row)

        lines.append("")
        lines.append("🔴 ≥70  🟡 ≥50  🟢 ≥30  ⚪ <30")

        return "\n".join(lines)

    def _val_to_level(self, val: float) -> str:
        """数值转风险等级"""
        if val >= 70:
            return "high"
        elif val >= 50:
            return "medium"
        elif val >= 30:
            return "low"
        return "minimal"

    def _val_to_emoji(self, val: float) -> str:
        """数值转emoji"""
        for threshold, emoji in self.COLOR_THRESHOLDS:
            if val >= threshold:
                return emoji
        return "⚪"


# ---------------------------------------------------------------------------
# TestPriorityRecommender
# ---------------------------------------------------------------------------

class TestPriorityRecommender:
    """
    基于风险分数的测试优先级推荐器
    """

    PRIORITY_DESCRIPTIONS = {
        "P0": "极高优先级 - 必须测试",
        "P1": "高优先级 - 重点测试",
        "P2": "中优先级 - 回归测试",
        "P3": "低优先级 - 可选测试",
    }

    def recommend(self, risk_scores: pd.DataFrame) -> List[TestPriority]:
        """
        生成测试优先级推荐

        Args:
            risk_scores: ModuleRiskScorer 的输出

        Returns:
            测试优先级列表
        """
        if risk_scores is None or risk_scores.empty:
            return []

        recommendations = []

        for _, row in risk_scores.iterrows():
            module = str(row.get("module", ""))
            score = float(row.get("risk_score", 0))
            level = str(row.get("risk_level", "P3"))

            # 构建推荐理由
            reasons = []
            focus_areas = []

            freq = float(row.get("freq_severity", 0))
            if freq >= 60:
                reasons.append(f"频次严重度高({freq:.0f})")
                focus_areas.append("高频严重缺陷回归")

            trend = str(row.get("trend_direction", ""))
            if trend == "increasing":
                reasons.append("缺陷趋势上升")
                focus_areas.append("新增缺陷场景覆盖")

            resolve = float(row.get("resolve_rate", 0))
            if resolve < 0.3:
                reasons.append(f"解决率低({resolve:.0%})")
                focus_areas.append("历史遗留缺陷验证")

            top_ratio = float(row.get("top_issue_ratio", 0))
            if top_ratio > 0.2:
                reasons.append(f"TopIssue占比高({top_ratio:.0%})")
                focus_areas.append("高风险缺陷专项测试")

            reason = "；".join(reasons) if reasons else "常规风险水平"
            if not focus_areas:
                focus_areas = ["基本功能回归"]

            recommendations.append(TestPriority(
                module=module,
                risk_score=score,
                risk_level=level,
                reason=reason,
                focus_areas=focus_areas,
            ))

        return recommendations

    def format_report(self, recommendations: List[TestPriority]) -> str:
        """
        格式化推荐报告

        Args:
            recommendations: 推荐列表

        Returns:
            文本报告
        """
        if not recommendations:
            return "无测试优先级推荐数据。"

        lines = ["🎯 测试优先级推荐", ""]

        by_level: Dict[str, List[TestPriority]] = defaultdict(list)
        for r in recommendations:
            by_level[r.risk_level].append(r)

        for level in ["P0", "P1", "P2", "P3"]:
            items = by_level.get(level, [])
            if not items:
                continue

            desc = self.PRIORITY_DESCRIPTIONS.get(level, level)
            lines.append(f"**{level} - {desc}**")

            for item in items:
                lines.append(f"  ▸ {item.module} (风险分: {item.risk_score:.1f})")
                lines.append(f"    理由: {item.reason}")
                lines.append(f"    重点: {', '.join(item.focus_areas)}")

            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_module_risk_scorer(**kwargs) -> ModuleRiskScorer:
    """创建模块风险评分器"""
    return ModuleRiskScorer(**kwargs)


def create_risk_heatmap_generator() -> RiskHeatmapGenerator:
    """创建热力图生成器"""
    return RiskHeatmapGenerator()


def create_test_priority_recommender() -> TestPriorityRecommender:
    """创建测试优先级推荐器"""
    return TestPriorityRecommender()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("风险热力图模块测试")
    print("=" * 60)

    # 模拟缺陷数据
    test_data = pd.DataFrame([
        {"target_ecu": "ECU_Display", "severity": "1A", "status": "03_In Progress", "created_date": "2026-01-15", "risk_score": 85},
        {"target_ecu": "ECU_Display", "severity": "2B", "status": "01_New", "created_date": "2026-02-10", "risk_score": 72},
        {"target_ecu": "ECU_Display", "severity": "3C", "status": "03_In Progress", "created_date": "2026-03-05", "risk_score": 45},
        {"target_ecu": "ECU_Power", "severity": "2A", "status": "04_Waiting", "created_date": "2026-01-20", "risk_score": 65},
        {"target_ecu": "ECU_Power", "severity": "3B", "status": "06_Concluded", "created_date": "2026-02-15", "risk_score": 30},
        {"target_ecu": "ECU_NAV", "severity": "4C", "status": "06_Concluded", "created_date": "2026-01-25", "risk_score": 20},
        {"target_ecu": "ECU_NAV", "severity": "3D", "status": "09_Concluded", "created_date": "2026-02-20", "risk_score": 15},
        {"target_ecu": "ECU_IC", "severity": "1B", "status": "02_Investigation", "created_date": "2026-03-01", "risk_score": 90},
        {"target_ecu": "ECU_IC", "severity": "2A", "status": "02_Investigation", "created_date": "2026-03-10", "risk_score": 78},
        {"target_ecu": "ECU_IC", "severity": "1C", "status": "03_In Progress", "created_date": "2026-03-15", "risk_score": 82},
    ])

    # 风险评分
    scorer = create_module_risk_scorer()
    risk_df = scorer.score(test_data)
    print("\n--- 模块风险评分 ---")
    print(risk_df[["module", "defect_count", "risk_score", "risk_level"]].to_string(index=False))

    # 热力图
    gen = create_risk_heatmap_generator()
    heatmap = gen.generate(risk_df)
    print("\n" + gen.render_text(heatmap))

    # 测试优先级推荐
    recommender = create_test_priority_recommender()
    priorities = recommender.recommend(risk_df)
    print("\n" + recommender.format_report(priorities))

    print("✅ 测试完成")
