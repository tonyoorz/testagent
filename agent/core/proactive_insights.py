"""
Proactive Insights — 主动洞察推送

数据加载后主动分析并生成"值得关注的事"，
不是等用户问，而是告诉用户数据里有什么故事。

洞察类型：
1. 异常突增/突降（数值突变量检测）
2. 分布失衡（某个维度占比过高）
3. 趋势预警（恶化/改善趋势）
4. 关联发现（两个维度强相关）
5. 风险聚焦（高风险项集中）
6. 行动建议（基于数据特征推荐分析方向）

用法：
    from agent.core.proactive_insights import ProactiveInsightEngine

    engine = ProactiveInsightEngine()
    insights = engine.analyze(df, data_profile=profile)
    summary = engine.format_insights(insights)  # 用户友好的文本
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class InsightSeverity(Enum):
    CRITICAL = "🔴"
    WARNING = "🟡"
    INFO = "🟢"
    TIP = "💡"


class InsightType(Enum):
    ANOMALY_SPIKE = "anomaly_spike"           # 突增/突降
    DISTRIBUTION_IMBALANCE = "imbalance"      # 分布失衡
    TREND_WARNING = "trend_warning"            # 趋势预警
    CORRELATION = "correlation"                # 关联发现
    RISK_FOCUS = "risk_focus"                  # 风险聚焦
    DATA_QUALITY = "data_quality"              # 数据质量
    ACTION_SUGGESTION = "action"               # 行动建议


@dataclass
class Insight:
    """一条洞察。"""
    type: InsightType
    severity: InsightSeverity
    title: str
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    action: str = ""  # 建议的下一步

    def to_text(self) -> str:
        parts = [f"{self.severity.value} {self.title}"]
        if self.detail:
            parts.append(f"   {self.detail}")
        if self.action:
            parts.append(f"   → {self.action}")
        return "\n".join(parts)


class ProactiveInsightEngine:
    """主动洞察引擎。"""

    def __init__(self, spike_threshold: float = 2.0, imbalance_threshold: float = 0.6):
        self._spike_threshold = spike_threshold
        self._imbalance_threshold = imbalance_threshold

    def analyze(
        self,
        df: pd.DataFrame,
        data_profile: Optional[Any] = None,
        dataset_name: str = "defects",
    ) -> List[Insight]:
        """对数据执行全面洞察分析。"""
        insights: List[Insight] = []

        if df is None or len(df) == 0:
            return insights

        # 1. 异常突增检测
        insights.extend(self._detect_spikes(df))

        # 2. 分布失衡检测
        insights.extend(self._detect_imbalance(df))

        # 3. 趋势预警
        insights.extend(self._detect_trends(df))

        # 4. 风险聚焦
        insights.extend(self._detect_risks(df))

        # 5. 数据质量洞察
        if data_profile:
            insights.extend(self._detect_quality_issues(df, data_profile))

        # 6. 行动建议
        insights.extend(self._generate_actions(df, insights))

        # 按严重度排序
        severity_order = {
            InsightSeverity.CRITICAL: 0,
            InsightSeverity.WARNING: 1,
            InsightSeverity.INFO: 2,
            InsightSeverity.TIP: 3,
        }
        insights.sort(key=lambda i: severity_order.get(i.severity, 99))

        return insights

    def format_insights(self, insights: List[Insight], max_items: int = 8) -> str:
        """格式化为用户友好的文本。"""
        if not insights:
            return "数据加载完成，未发现需要特别关注的问题。"

        top = insights[:max_items]
        parts = [f"📋 发现 {len(insights)} 个值得关注的信息（显示前 {len(top)} 个）：\n"]
        for i, insight in enumerate(top, 1):
            parts.append(f"{i}. {insight.to_text()}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 异常突增
    # ------------------------------------------------------------------

    def _detect_spikes(self, df: pd.DataFrame) -> List[Insight]:
        """检测时间维度上的数值突增。"""
        insights = []

        # 找时间列
        time_col = self._find_time_column(df)
        if not time_col:
            return insights

        try:
            dates = pd.to_datetime(df[time_col], errors="coerce")
            if dates.isnull().all():
                return insights

            # 按周聚合
            df_copy = df.copy()
            df_copy["_week"] = dates.dt.isocalendar().week.astype(int)
            df_copy["_year"] = dates.dt.year

            weekly = df_copy.groupby(["_year", "_week"]).size().reset_index(name="count")
            if len(weekly) < 3:
                return insights

            mean_count = weekly["count"].mean()
            std_count = weekly["count"].std()

            if std_count > 0:
                latest = weekly.iloc[-1]
                z_score = (latest["count"] - mean_count) / std_count

                if z_score >= self._spike_threshold:
                    insights.append(Insight(
                        type=InsightType.ANOMALY_SPIKE,
                        severity=InsightSeverity.CRITICAL,
                        title=f"最近一周数据量突增",
                        detail=f"第{int(latest['_week'])}周有 {int(latest['count'])} 条记录，"
                               f"是周均值({mean_count:.0f})的 {latest['count']/mean_count:.1f} 倍",
                        evidence={"week": int(latest["_week"]), "count": int(latest["count"]),
                                  "mean": round(mean_count, 1), "z_score": round(z_score, 2)},
                        action="建议查看突增原因——是数据导入延迟积压，还是真实业务变化？",
                    ))
                elif z_score <= -self._spike_threshold:
                    insights.append(Insight(
                        type=InsightType.ANOMALY_SPIKE,
                        severity=InsightSeverity.WARNING,
                        title=f"最近一周数据量骤降",
                        detail=f"第{int(latest['_week'])}周仅 {int(latest['count'])} 条记录，"
                               f"远低于周均值({mean_count:.0f})",
                        action="可能是数据延迟未同步，或实际产出减少",
                    ))

        except Exception as e:
            logger.debug(f"Spike detection failed: {e}")

        return insights

    # ------------------------------------------------------------------
    # 分布失衡
    # ------------------------------------------------------------------

    def _detect_imbalance(self, df: pd.DataFrame) -> List[Insight]:
        """检测分类维度分布失衡。"""
        insights = []

        # 检测 project, severity, status 等维度
        check_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(k in col_lower for k in ["project", "severity", "status", "ecu", "domain", "aida"]):
                if df[col].nunique() <= 20:
                    check_cols.append(col)

        total = len(df)
        for col in check_cols:
            try:
                vc = df[col].value_counts()
                if len(vc) < 2:
                    continue

                top_val, top_count = vc.index[0], vc.iloc[0]
                top_pct = top_count / total

                if top_pct >= self._imbalance_threshold and len(vc) >= 2:
                    col_label = col.replace("_", " ").title()
                    insights.append(Insight(
                        type=InsightType.DISTRIBUTION_IMBALANCE,
                        severity=InsightSeverity.WARNING if top_pct < 0.8 else InsightSeverity.INFO,
                        title=f"{col_label} 分布集中",
                        detail=f"'{top_val}' 占比 {top_pct:.0%}（{top_count}/{total}），"
                               f"其余 {len(vc)-1} 个值共占 {(1-top_pct):.0%}",
                        evidence={"column": col, "top_value": str(top_val),
                                  "top_pct": round(top_pct, 3), "unique_count": len(vc)},
                        action=f"跨{col_label}对比时注意样本量差异，'{top_val}'的统计更可靠",
                    ))
            except Exception:
                pass

        return insights

    # ------------------------------------------------------------------
    # 趋势预警
    # ------------------------------------------------------------------

    def _detect_trends(self, df: pd.DataFrame) -> List[Insight]:
        """检测趋势变化。"""
        insights = []

        time_col = self._find_time_column(df)
        if not time_col:
            return insights

        severity_col = self._find_column(df, ["severity_group", "severity", "problem_severity"])
        if not severity_col:
            return insights

        try:
            df_copy = df.copy()
            df_copy["_month"] = pd.to_datetime(df_copy[time_col], errors="coerce").dt.to_period("M")

            # 严重率月度趋势
            critical_kw = ["critical", "严重"]
            df_copy["_is_severe"] = df_copy[severity_col].apply(
                lambda x: any(k in str(x).lower() for k in critical_kw)
            )

            monthly = df_copy.groupby("_month").agg(
                total=("_is_severe", "size"),
                severe=("_is_severe", "sum"),
            )
            monthly["rate"] = monthly["severe"] / monthly["total"]

            if len(monthly) >= 3:
                # 最近3个月的严重率趋势
                recent_rates = monthly["rate"].iloc[-3:].values
                if recent_rates[-1] > recent_rates[0] * 1.3:
                    insights.append(Insight(
                        type=InsightType.TREND_WARNING,
                        severity=InsightSeverity.WARNING,
                        title="严重缺陷率持续上升",
                        detail=f"近3个月严重率: {', '.join(f'{r:.1%}' for r in recent_rates)}，"
                               f"增长了 {(recent_rates[-1]/recent_rates[0]-1):.0%}",
                        action="建议检查最近引入的变更或新模块是否带来了更多严重问题",
                    ))
                elif recent_rates[-1] < recent_rates[0] * 0.7:
                    insights.append(Insight(
                        type=InsightType.TREND_WARNING,
                        severity=InsightSeverity.INFO,
                        title="严重缺陷率持续改善",
                        detail=f"近3个月严重率: {', '.join(f'{r:.1%}' for r in recent_rates)}，"
                               f"下降了 {(1-recent_rates[-1]/recent_rates[0]):.0%}",
                        action="改善趋势良好，可总结经验推广",
                    ))
        except Exception as e:
            logger.debug(f"Trend detection failed: {e}")

        return insights

    # ------------------------------------------------------------------
    # 风险聚焦
    # ------------------------------------------------------------------

    def _detect_risks(self, df: pd.DataFrame) -> List[Insight]:
        """检测高风险聚集。"""
        insights = []

        risk_col = self._find_column(df, ["topissue_risk_score", "risk_score"])
        project_col = self._find_column(df, ["project", "tproject"])

        if risk_col and project_col:
            try:
                df_valid = df[df[risk_col].notna()].copy()
                if len(df_valid) > 0:
                    df_valid["_risk"] = pd.to_numeric(df_valid[risk_col], errors="coerce")
                    high_risk = df_valid[df_valid["_risk"] >= 60]

                    if len(high_risk) > 0:
                        by_project = high_risk.groupby(project_col).size().sort_values(ascending=False)
                        if len(by_project) > 0:
                            top_proj, top_count = by_project.index[0], by_project.iloc[0]
                            insights.append(Insight(
                                type=InsightType.RISK_FOCUS,
                                severity=InsightSeverity.CRITICAL if top_count >= 5 else InsightSeverity.WARNING,
                                title=f"高风险缺陷集中在 {top_proj}",
                                detail=f"{top_proj} 有 {top_count} 个 TopIssue（风险分≥60），"
                                       f"共 {len(high_risk)} 个 TopIssue 分布在 {len(by_project)} 个项目",
                                evidence={"project": str(top_proj), "count": int(top_count),
                                          "total_topissue": len(high_risk)},
                                action=f"建议优先处理 {top_proj} 的 TopIssue，聚焦根因分析",
                            ))
            except Exception as e:
                logger.debug(f"Risk detection failed: {e}")

        # ECU乒乓风险
        ecu_pp_col = self._find_column(df, ["ecu_pingpong_count"])
        if ecu_pp_col and project_col:
            try:
                df_valid = df.copy()
                df_valid["_pp"] = pd.to_numeric(df_valid[ecu_pp_col], errors="coerce").fillna(0)
                high_pp = df_valid[df_valid["_pp"] >= 3]
                if len(high_pp) >= 3:
                    insights.append(Insight(
                        type=InsightType.RISK_FOCUS,
                        severity=InsightSeverity.WARNING,
                        title=f"发现 {len(high_pp)} 个高复杂度ECU乒乓缺陷",
                        detail=f"ECU乒乓≥3次的缺陷有 {len(high_pp)} 个，"
                               f"最高乒乓 {int(df_valid['_pp'].max())} 次",
                        action="建议分析这些缺陷涉及的ECU链路，是否需要升级协调",
                    ))
            except Exception:
                pass

        return insights

    # ------------------------------------------------------------------
    # 数据质量
    # ------------------------------------------------------------------

    def _detect_quality_issues(self, df: pd.DataFrame, profile: Any) -> List[Insight]:
        """基于 DataProfile 检测数据质量问题。"""
        insights = []

        # profile 可以是 DataProfile 对象或 dict
        if hasattr(profile, "anomalies"):
            anomalies = profile.anomalies
        elif isinstance(profile, dict):
            anomalies = profile.get("anomalies", [])
        else:
            return insights

        for anomaly in anomalies:
            if "空值率" in str(anomaly) and "受限" in str(anomaly):
                insights.append(Insight(
                    type=InsightType.DATA_QUALITY,
                    severity=InsightSeverity.WARNING,
                    title="数据完整性问题",
                    detail=anomaly,
                    action="分析时注意标注该字段的覆盖率，避免过度推断",
                ))

        return insights

    # ------------------------------------------------------------------
    # 行动建议
    # ------------------------------------------------------------------

    def _generate_actions(self, df: pd.DataFrame, existing_insights: List[Insight]) -> List[Insight]:
        """基于已有洞察和数据特征，推荐分析方向。"""
        actions = []

        insight_types = {i.type for i in existing_insights}

        # 如果有风险聚集，建议根因分析
        if InsightType.RISK_FOCUS in insight_types:
            actions.append(Insight(
                type=InsightType.ACTION_SUGGESTION,
                severity=InsightSeverity.TIP,
                title="建议分析方向",
                detail="试试问：「这些 TopIssue 的根因是什么？」或「哪个 ECU 的缺陷需要优先关注？」",
            ))

        # 如果有突增，建议细看
        if InsightType.ANOMALY_SPIKE in insight_types:
            actions.append(Insight(
                type=InsightType.ACTION_SUGGESTION,
                severity=InsightSeverity.TIP,
                title="建议分析方向",
                detail="试试问：「最近一周新增了哪些类型的缺陷？」或「突增的缺陷集中在哪个模块？」",
            ))

        # 如果数据量大，建议缩小范围
        if len(df) > 50000:
            actions.append(Insight(
                type=InsightType.ACTION_SUGGESTION,
                severity=InsightSeverity.TIP,
                title="数据量较大",
                detail=f"当前 {len(df)} 行数据。建议指定时间范围或项目缩小分析范围，如「分析IDCevo最近一个月的缺陷」",
            ))

        # 通用建议（如果没有其他洞察）
        if not existing_insights and not actions:
            actions.append(Insight(
                type=InsightType.ACTION_SUGGESTION,
                severity=InsightSeverity.TIP,
                title="可以问我",
                detail="「哪个项目风险最高？」「最近缺陷趋势如何？」「严重缺陷集中在哪些模块？」",
            ))

        return actions

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _find_time_column(df: pd.DataFrame) -> Optional[str]:
        """找时间列。"""
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                return col
            col_lower = col.lower()
            if any(k in col_lower for k in ["time", "date", "creation"]):
                return col
        return None

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        """从候选列表中找到存在的列。"""
        for c in candidates:
            if c in df.columns:
                return c
            # 模糊匹配
            for col in df.columns:
                if c in col.lower() or col.lower() in c:
                    return col
        return None
