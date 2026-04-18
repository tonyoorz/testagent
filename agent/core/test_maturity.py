"""
测试成熟度评分模块

量化评估测试体系的成熟度，7个维度打分，加权平均出总分。

Features:
1. TestMaturityScorer - 7维度测试成熟度评估
2. MaturityReport / MaturityDimension - 结构化报告

Author: AI Assistant
Date: 2026-04-18
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class MaturityDimension:
    """成熟度单维度"""
    name: str           # 维度名
    score: float        # 0-100
    grade: str          # A/B/C/D/F
    benchmark: float    # 基准值
    actual: float       # 实际值
    note: str           # 说明


@dataclass
class MaturityReport:
    """成熟度评估报告"""
    total_score: float
    total_grade: str
    dimensions: List[MaturityDimension]
    summary: str
    actions: List[str]


# ---------------------------------------------------------------------------
# 等级映射
# ---------------------------------------------------------------------------

def _score_to_grade(score: float) -> str:
    """分数 → 等级"""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# TestMaturityScorer
# ---------------------------------------------------------------------------

class TestMaturityScorer:
    """
    测试成熟度评分器

    7个维度，每个维度 0-100 分：
    1. defect_detection_rate  — 缺陷发现率
    2. severity_balance       — 严重度分布合理性
    3. close_rate             — 关闭率
    4. fix_speed              — 修复速度
    5. pingpong_rate          — 乒乓率（越低越好）
    6. coverage_uniformity    — 模块覆盖均匀度
    7. trend_health           — 趋势健康度

    加权: severity_balance×1.5, close_rate×1.3, fix_speed×1.2, 其余×1.0
    等级: A(90+) B(75-89) C(60-74) D(45-59) F(<45)
    """

    # 维度权重
    WEIGHTS = {
        "defect_detection_rate": 1.0,
        "severity_balance": 1.5,
        "close_rate": 1.3,
        "fix_speed": 1.2,
        "pingpong_rate": 1.0,
        "coverage_uniformity": 1.0,
        "trend_health": 1.0,
    }

    # 行业基准值
    BENCHMARKS = {
        "defect_detection_rate": 0.6,    # 期望缺陷发现率 ≥60%
        "severity_balance": 0.2,         # Critical 占比 ≤20% 为佳
        "close_rate": 0.7,               # 关闭率 ≥70% 为佳
        "fix_speed": 5.0,                # 平均修复天数 ≤5天 为佳
        "pingpong_rate": 0.08,           # 乒乓率 ≤8% 为佳
        "coverage_uniformity": 0.5,      # 覆盖均匀度（基尼系数反转）
        "trend_health": 0.0,             # 缺陷趋势变化率，0=稳定
    }

    def __init__(
        self,
        status_field: str = "status",
        severity_field: str = "severity",
        date_field: str = "created_date",
        module_field: str = "target_ecu",
    ):
        self.status_field = status_field
        self.severity_field = severity_field
        self.date_field = date_field
        self.module_field = module_field

    def score(self, df: pd.DataFrame) -> MaturityReport:
        """
        计算测试成熟度评分

        Args:
            df: 缺陷数据 DataFrame

        Returns:
            MaturityReport
        """
        if df is None or df.empty:
            return MaturityReport(
                total_score=0, total_grade="F", dimensions=[],
                summary="数据为空，无法评估", actions=["请先导入缺陷数据"],
            )

        dimensions = [
            self._score_defect_detection_rate(df),
            self._score_severity_balance(df),
            self._score_close_rate(df),
            self._score_fix_speed(df),
            self._score_pingpong_rate(df),
            self._score_coverage_uniformity(df),
            self._score_trend_health(df),
        ]

        # 加权平均
        total_weight = sum(self.WEIGHTS.values())
        weighted_sum = sum(
            d.score * self.WEIGHTS.get(d.name, 1.0) for d in dimensions
        )
        total_score = round(weighted_sum / total_weight, 1)
        total_grade = _score_to_grade(total_score)

        summary = self._build_summary(total_score, total_grade, dimensions)
        actions = self._build_actions(dimensions)

        return MaturityReport(
            total_score=total_score,
            total_grade=total_grade,
            dimensions=dimensions,
            summary=summary,
            actions=actions,
        )

    # ----- 维度1：缺陷发现率 -----
    def _score_defect_detection_rate(self, df: pd.DataFrame) -> MaturityDimension:
        """
        缺陷发现率：缺陷总数相对于项目规模是否合理。
        太少可能漏测，太多可能过测。

        用缺陷模块数的平均每模块缺陷数来衡量。
        基准: 每模块平均 5-15 个缺陷视为合理发现率。
        """
        module_field = self._resolve_field(df, self.module_field, ["target_ecu", "ecu", "module"])

        if module_field not in df.columns:
            return self._na_dimension("defect_detection_rate", "缺少模块字段")

        modules = df[module_field].dropna()
        n_modules = modules.nunique()
        total = len(df)

        if n_modules == 0:
            return self._na_dimension("defect_detection_rate", "无有效模块数据")

        actual = total / n_modules  # 每模块平均缺陷数
        benchmark = 10.0  # 基准: 每模块10个

        # 评分：actual 在 5-15 区间得高分，偏离越多分越低
        if 5 <= actual <= 15:
            score = 90 - abs(actual - 10) * 2  # 中心10最佳
        elif actual < 5:
            score = max(30, 90 - (5 - actual) * 10)  # 太少
        else:
            score = max(30, 90 - (actual - 15) * 3)  # 太多

        score = min(100, max(0, score))
        return MaturityDimension(
            name="defect_detection_rate",
            score=round(score, 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(actual, 1),
            note=f"平均每模块 {actual:.1f} 个缺陷（基准: {benchmark:.0f}）",
        )

    # ----- 维度2：严重度分布合理性 -----
    def _score_severity_balance(self, df: pd.DataFrame) -> MaturityDimension:
        """
        Critical (1A/1B/2A) 占比 ≤20% 为佳（说明大部分问题不致命）。
        但也不应太少（<5%可能漏测严重问题）。
        """
        sev_field = self._resolve_field(df, self.severity_field, ["severity", "severity_group"])

        if sev_field not in df.columns:
            return self._na_dimension("severity_balance", "缺少严重度字段")

        total = len(df)
        if total == 0:
            return self._na_dimension("severity_balance", "无数据")

        # Critical: severity 以 1 或 2 开头
        critical_mask = df[sev_field].astype(str).str.match(r"^[12]", na=False)
        critical_ratio = critical_mask.sum() / total
        benchmark = 0.2  # ≤20%

        # 评分：10-20% 最佳(90+)，<5% 或 >40% 较差
        if 0.1 <= critical_ratio <= 0.2:
            score = 90
        elif 0.05 <= critical_ratio < 0.1:
            score = 75
        elif 0.2 < critical_ratio <= 0.3:
            score = 70
        elif critical_ratio < 0.05:
            score = 55
        elif 0.3 < critical_ratio <= 0.4:
            score = 50
        else:
            score = max(20, 50 - (critical_ratio - 0.4) * 200)

        score = min(100, max(0, score))
        return MaturityDimension(
            name="severity_balance",
            score=round(score, 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(critical_ratio, 3),
            note=f"Critical 占比 {critical_ratio:.1%}（基准 ≤{benchmark:.0%}）",
        )

    # ----- 维度3：关闭率 -----
    def _score_close_rate(self, df: pd.DataFrame) -> MaturityDimension:
        """关闭率 ≥70% 为佳"""
        status_field = self._resolve_field(df, self.status_field, ["status", "status_phase"])

        if status_field not in df.columns:
            return self._na_dimension("close_rate", "缺少状态字段")

        total = len(df)
        if total == 0:
            return self._na_dimension("close_rate", "无数据")

        closed_prefixes = {"06", "09", "10", "08"}
        closed = 0
        for s in df[status_field].dropna():
            prefix = str(s).split("_")[0].strip()
            if prefix in closed_prefixes:
                closed += 1

        close_rate = closed / total
        benchmark = 0.7

        # 评分：≥70% = 90+, ≥50% = 70+, 线性映射
        if close_rate >= benchmark:
            score = min(100, 70 + close_rate * 40)
        else:
            score = max(10, close_rate / benchmark * 70)

        return MaturityDimension(
            name="close_rate",
            score=round(score, 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(close_rate, 3),
            note=f"关闭率 {close_rate:.1%}（基准 ≥{benchmark:.0%}）",
        )

    # ----- 维度4：修复速度 -----
    def _score_fix_speed(self, df: pd.DataFrame) -> MaturityDimension:
        """平均修复天数，≤5天为佳"""
        date_field = self._resolve_field(df, self.date_field, ["created_date", "tcreationtime"])
        status_field = self._resolve_field(df, self.status_field, ["status", "status_phase"])

        if date_field not in df.columns:
            return self._na_dimension("fix_speed", "缺少日期字段")

        df_copy = df.copy()
        df_copy["_created"] = pd.to_datetime(df_copy[date_field], errors="coerce")

        # 查找关闭日期列
        close_date_col = None
        for c in ["resolved_date", "closed_date", "finished_udf_dt", "modified_date"]:
            if c in df_copy.columns:
                close_date_col = c
                break

        if close_date_col is None:
            # 用状态推断：已关闭的用 modified_date 或当前日期
            return self._estimate_fix_speed_fallback(df_copy, status_field)

        df_copy["_closed"] = pd.to_datetime(df_copy[close_date_col], errors="coerce")
        df_copy["_days"] = (df_copy["_closed"] - df_copy["_created"]).dt.days

        valid = df_copy["_days"].dropna()
        valid = valid[(valid >= 0) & (valid <= 365)]  # 过滤异常值

        if valid.empty:
            return self._na_dimension("fix_speed", "无有效修复周期数据")

        avg_days = valid.mean()
        benchmark = 5.0

        # 评分：≤3天=100, ≤5天=85, ≤10天=65, ≤20天=45, >20天递减
        if avg_days <= 3:
            score = 100
        elif avg_days <= 5:
            score = 85 + (5 - avg_days) / 2 * 15
        elif avg_days <= 10:
            score = 65 + (10 - avg_days) / 5 * 20
        elif avg_days <= 20:
            score = 45 + (20 - avg_days) / 10 * 20
        else:
            score = max(10, 45 - (avg_days - 20) * 2)

        return MaturityDimension(
            name="fix_speed",
            score=round(score, 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(avg_days, 1),
            note=f"平均修复 {avg_days:.1f} 天（基准 ≤{benchmark:.0f}天）",
        )

    def _estimate_fix_speed_fallback(self, df: pd.DataFrame, status_field: str) -> MaturityDimension:
        """修复速度降级估算：用已关闭缺陷的时间跨度粗估"""
        date_col = "_created" if "_created" in df.columns else self.date_field
        if date_col not in df.columns:
            return self._na_dimension("fix_speed", "无日期数据")

        # 粗估：用数据时间跨度 / 2 作为代理
        dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
        if len(dates) < 2:
            return self._na_dimension("fix_speed", "数据不足")

        span_days = (dates.max() - dates.min()).days
        total = len(df)
        if total == 0:
            return self._na_dimension("fix_speed", "无数据")

        # 估算平均修复时间 = 总跨度 / sqrt(总缺陷数)
        avg_days = span_days / max(np.sqrt(total), 1)
        benchmark = 5.0

        if avg_days <= 5:
            score = 80
        elif avg_days <= 10:
            score = 60
        else:
            score = max(20, 60 - (avg_days - 10) * 3)

        return MaturityDimension(
            name="fix_speed",
            score=round(score, 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(avg_days, 1),
            note=f"估算修复 {avg_days:.1f} 天（基准 ≤{benchmark:.0f}天，粗估值）",
        )

    # ----- 维度5：乒乓率 -----
    def _score_pingpong_rate(self, df: pd.DataFrame) -> MaturityDimension:
        """
        乒乓率：反复开关（状态在 开放↔关闭 间反复切换）的缺陷占比。
        ≤8%为佳。
        """
        status_field = self._resolve_field(df, self.status_field, ["status", "status_phase"])

        # 需要有 transfer_count 或 status_history 来判断乒乓
        # 降级方案：用转移次数判断
        transfer_col = None
        for c in ["transfer_count", "status_transitions", "age"]:
            if c in df.columns:
                transfer_col = c
                break

        if transfer_col:
            transfers = pd.to_numeric(df[transfer_col], errors="coerce").fillna(0)
            # 转移次数 > 3 视为乒乓
            pingpong_count = (transfers > 3).sum()
            total = len(df)
        else:
            # 无转移数据，用状态推断：
            # 如果有大量 waiting 状态的缺陷，可能是乒乓
            if status_field in df.columns:
                waiting_mask = df[status_field].astype(str).str.contains("Waiting|waiting|04", na=False)
                pingpong_count = int(waiting_mask.sum() * 0.3)  # 粗估30%是乒乓
                total = len(df)
            else:
                return self._na_dimension("pingpong_rate", "缺少状态/转移次数字段")

        if total == 0:
            return self._na_dimension("pingpong_rate", "无数据")

        pingpong_rate = pingpong_count / total
        benchmark = 0.08

        # 评分：≤5%=100, ≤8%=85, ≤15%=60, >15%递减
        if pingpong_rate <= 0.05:
            score = 100
        elif pingpong_rate <= benchmark:
            score = 85 + (benchmark - pingpong_rate) / (benchmark - 0.05) * 15
        elif pingpong_rate <= 0.15:
            score = 60 + (0.15 - pingpong_rate) / (0.15 - benchmark) * 25
        else:
            score = max(10, 60 - (pingpong_rate - 0.15) * 300)

        return MaturityDimension(
            name="pingpong_rate",
            score=round(score, 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(pingpong_rate, 3),
            note=f"乒乓率 {pingpong_rate:.1%}（基准 ≤{benchmark:.0%}）",
        )

    # ----- 维度6：覆盖均匀度 -----
    def _score_coverage_uniformity(self, df: pd.DataFrame) -> MaturityDimension:
        """
        各模块缺陷分布均匀度，不要集中在单一模块。
        用变异系数(CV)的倒数来衡量。
        """
        module_field = self._resolve_field(df, self.module_field, ["target_ecu", "ecu", "module"])

        if module_field not in df.columns:
            return self._na_dimension("coverage_uniformity", "缺少模块字段")

        counts = df[module_field].value_counts()
        if len(counts) < 2:
            return self._na_dimension("coverage_uniformity", "模块数不足")

        mean_val = counts.mean()
        std_val = counts.std()

        if mean_val == 0:
            return self._na_dimension("coverage_uniformity", "无缺陷数据")

        cv = std_val / mean_val  # 变异系数，越小越均匀
        # cv=0 → 完美均匀，cv=1 → 很不均匀
        # 评分：cv≤0.3=90+, cv≤0.6=70+, cv≤1.0=50+, cv>1.0递减
        if cv <= 0.3:
            score = 90 + (0.3 - cv) / 0.3 * 10
        elif cv <= 0.6:
            score = 70 + (0.6 - cv) / 0.3 * 20
        elif cv <= 1.0:
            score = 50 + (1.0 - cv) / 0.4 * 20
        else:
            score = max(10, 50 - (cv - 1.0) * 30)

        benchmark = 0.5  # CV≤0.5为基准
        return MaturityDimension(
            name="coverage_uniformity",
            score=round(min(100, score), 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(cv, 3),
            note=f"分布变异系数 {cv:.2f}（基准 CV≤{benchmark}）",
        )

    # ----- 维度7：趋势健康度 -----
    def _score_trend_health(self, df: pd.DataFrame) -> MaturityDimension:
        """
        趋势健康度：近期缺陷数量在降还是升。
        比较最近1/3周期 vs 前2/3周期的缺陷数。
        """
        date_field = self._resolve_field(df, self.date_field, ["created_date", "tcreationtime"])

        if date_field not in df.columns:
            return self._na_dimension("trend_health", "缺少日期字段")

        df_copy = df.copy()
        df_copy["_date"] = pd.to_datetime(df_copy[date_field], errors="coerce")
        df_copy = df_copy.dropna(subset=["_date"])

        if len(df_copy) < 4:
            return self._na_dimension("trend_health", "数据点不足")

        # 按周聚合
        weekly = df_copy.set_index("_date").resample("W").size()
        weekly = weekly[weekly > 0]  # 去除零周

        if len(weekly) < 3:
            return self._na_dimension("trend_health", "有效周数不足")

        # 线性回归斜率
        x = np.arange(len(weekly))
        y = weekly.values.astype(float)

        if np.std(y) == 0:
            score = 80  # 稳定
            actual = 0.0
        else:
            slope = np.polyfit(x, y, 1)[0]
            avg = np.mean(y)
            actual = (slope / avg) if avg > 0 else 0  # 变化率

            # 评分：变化率在 -10%~0%(轻微下降/稳定) 最佳
            if -0.1 <= actual <= 0.05:
                score = 90
            elif 0.05 < actual <= 0.15:
                score = 75
            elif 0.15 < actual <= 0.3:
                score = 55
            elif actual > 0.3:
                score = max(15, 55 - (actual - 0.3) * 200)
            elif -0.2 <= actual < -0.1:
                score = 80  # 下降是好趋势但不要太快
            else:
                score = 70  # 大幅下降

        benchmark = 0.0  # 稳定
        return MaturityDimension(
            name="trend_health",
            score=round(min(100, max(0, score)), 1),
            grade=_score_to_grade(score),
            benchmark=benchmark,
            actual=round(actual, 3),
            note=f"趋势变化率 {actual:+.1%}（基准: 稳定{benchmark:+.0%}）",
        )

    # ----- 辅助方法 -----
    def _resolve_field(self, df: pd.DataFrame, primary: str, candidates: List[str]) -> str:
        """查找可用字段"""
        if primary in df.columns:
            return primary
        for c in candidates:
            if c in df.columns:
                return c
        return primary  # 返回原值，后续会走 na 逻辑

    def _na_dimension(self, name: str, reason: str) -> MaturityDimension:
        """不可用维度"""
        return MaturityDimension(
            name=name,
            score=50.0,  # 缺数据时给中间分
            grade="C",
            benchmark=self.BENCHMARKS.get(name, 0),
            actual=0,
            note=f"无法评估: {reason}",
        )

    def _build_summary(self, total: float, grade: str, dims: List[MaturityDimension]) -> str:
        """构建摘要"""
        weak = [d for d in dims if d.grade in ("D", "F")]
        strong = [d for d in dims if d.grade in ("A", "B")]
        lines = [f"测试成熟度总分: {total} ({grade})", ""]

        if strong:
            names = ", ".join(f"{d.name}({d.grade})" for d in strong)
            lines.append(f"优势维度: {names}")

        if weak:
            names = ", ".join(f"{d.name}({d.grade})" for d in weak)
            lines.append(f"待改进维度: {names}")

        return "\n".join(lines)

    def _build_actions(self, dims: List[MaturityDimension]) -> List[str]:
        """构建建议行动"""
        actions = []
        for d in sorted(dims, key=lambda x: x.score):
            if d.score >= 75:
                continue
            if d.name == "close_rate" and d.actual < 0.5:
                actions.append(f"🔴 关闭率仅 {d.actual:.0%}，建议加快缺陷处理节奏")
            elif d.name == "fix_speed" and d.actual > 10:
                actions.append(f"🔴 平均修复 {d.actual:.0f} 天，建议优化修复流程")
            elif d.name == "severity_balance" and d.actual > 0.3:
                actions.append(f"🟡 Critical 占比 {d.actual:.0%}，建议加强代码审查")
            elif d.name == "pingpong_rate" and d.actual > 0.1:
                actions.append(f"🟡 乒乓率 {d.actual:.0%}，建议改善问题分配机制")
            elif d.name == "trend_health" and d.actual > 0.15:
                actions.append(f"🔴 缺陷增速 {d.actual:+.0%}，建议增加测试资源")
            elif d.name == "coverage_uniformity" and d.actual > 0.8:
                actions.append(f"🟡 缺陷分布不均(CV={d.actual:.2f})，关注薄弱模块")
            elif d.score < 60:
                actions.append(f"🟢 {d.name}: {d.note}，建议持续关注")

        if not actions:
            actions.append("✅ 各维度表现良好，保持当前测试策略")

        return actions


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_test_maturity_scorer(**kwargs) -> TestMaturityScorer:
    """创建测试成熟度评分器"""
    return TestMaturityScorer(**kwargs)
