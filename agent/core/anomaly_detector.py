"""
时序异常检测模块

独立于 intelligent_agent.py 中的基础 wow_spike 规则，
提供更全面的异常检测能力：Z-score、移动平均偏离、连续趋势检测。

Features:
1. TimeSeriesAnomalyDetector - 多算法时序异常检测
2. AnomalyReportGenerator - 异常事件自然语言报告
3. ProactiveAnomalyScanner - 全模块定期扫描

Author: AI Assistant
Date: 2026-04-12
"""

import logging
import math
from typing import Any, Callable, Dict, List, Optional, Tuple
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
class AnomalyEvent:
    """单个异常事件"""
    type: str                # z_spike | ma_deviation | trend_streak
    severity: str            # high | medium | low
    period: str              # 发生的时间段/组
    value: float             # 实际值
    expected: float          # 期望值
    deviation: float         # 偏离程度（百分比或绝对值）
    description: str         # 自然语言描述
    module: Optional[str] = None  # 所属模块/ECU


@dataclass
class AnomalyAlert:
    """异常告警（用于主动推送）"""
    alert_id: str
    module: str
    anomaly_type: str
    severity: str
    summary: str
    detail: AnomalyEvent
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# TimeSeriesAnomalyDetector
# ---------------------------------------------------------------------------

class TimeSeriesAnomalyDetector:
    """
    多算法时序异常检测器

    检测算法：
    1. Z-score 突增突降检测（阈值 > 3σ）
    2. 移动平均偏离检测（窗口=3，阈值 > 2σ）
    3. 连续N期单向变化趋势检测（N>=3）
    """

    def __init__(
        self,
        z_threshold: float = 3.0,
        ma_window: int = 3,
        ma_threshold: float = 2.0,
        streak_min: int = 3,
        min_data_points: int = 3,
    ):
        """
        Args:
            z_threshold: Z-score 阈值，默认 3.0
            ma_window: 移动平均窗口，默认 3
            ma_threshold: 移动平均偏离阈值（σ倍数），默认 2.0
            streak_min: 连续趋势最少期数，默认 3
            min_data_points: 最少数据点数，低于此数不检测
        """
        self.z_threshold = z_threshold
        self.ma_window = ma_window
        self.ma_threshold = ma_threshold
        self.streak_min = streak_min
        self.min_data_points = min_data_points

    def detect(
        self,
        time_series: List[Dict],
        key_field: str = "group",
        value_field: str = "value",
    ) -> List[AnomalyEvent]:
        """
        对时序数据执行多算法异常检测

        Args:
            time_series: 时序数据列表，每个元素为 {key_field: str, value_field: float}
            key_field: 时间/分组字段名
            value_field: 数值字段名

        Returns:
            异常事件列表
        """
        if len(time_series) < self.min_data_points:
            logger.debug("数据点不足 %d，跳过检测", self.min_data_points)
            return []

        # 提取数值序列
        values = []
        keys = []
        for row in time_series:
            try:
                v = float(row.get(value_field, 0))
                k = str(row.get(key_field, ""))
                values.append(v)
                keys.append(k)
            except (TypeError, ValueError):
                continue

        if len(values) < self.min_data_points:
            return []

        events: List[AnomalyEvent] = []

        # 1. Z-score 检测
        z_events = self._detect_z_spike(values, keys)
        events.extend(z_events)

        # 2. 移动平均偏离检测
        ma_events = self._detect_ma_deviation(values, keys)
        events.extend(ma_events)

        # 3. 连续趋势检测
        streak_events = self._detect_streak(values, keys)
        events.extend(streak_events)

        # 去重：同一 period 可能被多个算法命中，保留最严重的
        deduped = self._deduplicate(events)
        return deduped

    def _detect_z_spike(self, values: List[float], keys: List[str]) -> List[AnomalyEvent]:
        """Z-score 突增突降检测"""
        events = []
        arr = np.array(values, dtype=float)
        mean = np.mean(arr)
        std = np.std(arr)

        if std == 0 or not np.isfinite(std):
            return events

        for i, (v, k) in enumerate(zip(values, keys)):
            z = (v - mean) / std
            if abs(z) > self.z_threshold:
                direction = "突增" if z > 0 else "突降"
                severity = "high" if abs(z) > 4 else "medium"
                events.append(AnomalyEvent(
                    type="z_spike",
                    severity=severity,
                    period=k,
                    value=v,
                    expected=round(mean, 2),
                    deviation=round(abs(z), 2),
                    description=f"{k} 数值 {v:.1f} {direction}，Z-score={z:.2f}，"
                                f"期望均值={mean:.1f}，偏离 {abs(z):.1f} 个标准差",
                ))

        return events

    def _detect_ma_deviation(self, values: List[float], keys: List[str]) -> List[AnomalyEvent]:
        """移动平均偏离检测"""
        events = []
        arr = np.array(values, dtype=float)

        for i in range(self.ma_window, len(arr)):
            window = arr[i - self.ma_window:i]
            ma = np.mean(window)
            window_std = np.std(window)

            if window_std == 0 or not np.isfinite(window_std):
                continue

            deviation = (arr[i] - ma) / window_std
            if abs(deviation) > self.ma_threshold:
                direction = "高于" if deviation > 0 else "低于"
                severity = "medium" if abs(deviation) > 3 else "low"
                events.append(AnomalyEvent(
                    type="ma_deviation",
                    severity=severity,
                    period=keys[i],
                    value=float(arr[i]),
                    expected=round(float(ma), 2),
                    deviation=round(float(deviation), 2),
                    description=f"{keys[i]} 数值 {arr[i]:.1f} {direction}移动平均 {ma:.1f}，"
                                f"偏离 {abs(deviation):.1f}σ（窗口={self.ma_window}）",
                ))

        return events

    def _detect_streak(self, values: List[float], keys: List[str]) -> List[AnomalyEvent]:
        """连续单向变化趋势检测"""
        events = []
        arr = np.array(values, dtype=float)

        streak_start = 0
        streak_direction = 0  # 1=上升, -1=下降

        for i in range(1, len(arr)):
            diff = arr[i] - arr[i - 1]
            current_dir = 1 if diff > 0 else (-1 if diff < 0 else 0)

            if current_dir == streak_direction and current_dir != 0:
                continue  # 继续streak
            else:
                # 检查上一个streak是否够长
                streak_len = i - streak_start
                if streak_len >= self.streak_min and streak_direction != 0:
                    self._record_streak(
                        events, arr, keys, streak_start, i, streak_direction
                    )
                streak_start = i - 1 if current_dir != 0 else i
                streak_direction = current_dir

        # 检查末尾的streak
        streak_len = len(arr) - streak_start
        if streak_len >= self.streak_min and streak_direction != 0:
            self._record_streak(
                events, arr, keys, streak_start, len(arr), streak_direction
            )

        return events

    def _record_streak(
        self,
        events: List[AnomalyEvent],
        arr: np.ndarray,
        keys: List[str],
        start: int,
        end: int,
        direction: int,
    ):
        """记录一个连续趋势事件"""
        direction_text = "连续上升" if direction > 0 else "连续下降"
        start_val = float(arr[start])
        end_val = float(arr[end - 1])
        change_pct = ((end_val - start_val) / start_val * 100) if start_val != 0 else 0

        events.append(AnomalyEvent(
            type="trend_streak",
            severity="medium",
            period=f"{keys[start]}~{keys[end - 1]}",
            value=end_val,
            expected=start_val,
            deviation=round(change_pct, 2),
            description=f"{direction_text} {end - start} 期："
                        f"从 {start_val:.1f}({keys[start]}) 到 {end_val:.1f}({keys[end - 1]})，"
                        f"变化 {change_pct:+.1f}%",
        ))

    def _deduplicate(self, events: List[AnomalyEvent]) -> List[AnomalyEvent]:
        """同一 period 保留最严重的事件"""
        by_period: Dict[str, AnomalyEvent] = {}
        severity_rank = {"high": 3, "medium": 2, "low": 1}

        for e in events:
            key = e.period
            existing = by_period.get(key)
            if existing is None or severity_rank.get(e.severity, 0) > severity_rank.get(existing.severity, 0):
                by_period[key] = e

        return sorted(by_period.values(), key=lambda x: severity_rank.get(x.severity, 0), reverse=True)


# ---------------------------------------------------------------------------
# AnomalyReportGenerator
# ---------------------------------------------------------------------------

class AnomalyReportGenerator:
    """
    异常事件自然语言报告生成器

    将检测到的异常事件翻译成人类可读的报告，
    可作为 agentic_runtime 的上下文注入。
    """

    SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    TYPE_LABEL = {
        "z_spike": "数值突增/突降",
        "ma_deviation": "移动平均偏离",
        "trend_streak": "连续趋势",
    }

    def generate(self, events: List[AnomalyEvent], module: str = "") -> str:
        """
        生成异常报告

        Args:
            events: 异常事件列表
            module: 模块名称（可选）

        Returns:
            自然语言报告文本
        """
        if not events:
            return "未发现显著异常。"

        lines = []
        header = "📊 异常检测报告"
        if module:
            header += f" - {module}"
        lines.append(header)
        lines.append(f"发现 {len(events)} 个异常事件：")
        lines.append("")

        # 按严重度分组
        high = [e for e in events if e.severity == "high"]
        medium = [e for e in events if e.severity == "medium"]
        low = [e for e in events if e.severity == "low"]

        if high:
            lines.append(f"🔴 高严重度（{len(high)}个）：")
            for e in high:
                lines.append(f"  • [{self.TYPE_LABEL.get(e.type, e.type)}] {e.description}")
            lines.append("")

        if medium:
            lines.append(f"🟡 中严重度（{len(medium)}个）：")
            for e in medium:
                lines.append(f"  • [{self.TYPE_LABEL.get(e.type, e.type)}] {e.description}")
            lines.append("")

        if low:
            lines.append(f"🟢 低严重度（{len(low)}个）：")
            for e in low:
                lines.append(f"  • [{self.TYPE_LABEL.get(e.type, e.type)}] {e.description}")
            lines.append("")

        # 建议
        lines.append("💡 建议操作：")
        if high:
            lines.append("  1. 立即排查高严重度异常，确认是否为真实问题")
            lines.append("  2. 对比前后周期数据，定位变化原因")
        if medium:
            lines.append("  3. 关注中严重度趋势，设置监控阈值")
        lines.append("  4. 可追问\"为什么{period}出现异常\"进行根因分析")

        return "\n".join(lines)

    def generate_prompt_context(self, events: List[AnomalyEvent]) -> str:
        """
        生成可注入 agentic_runtime system prompt 的上下文

        Returns:
            简洁的异常摘要，供 LLM 参考使用
        """
        if not events:
            return ""

        summaries = []
        for e in events[:5]:  # 最多5个
            summaries.append(
                f"- {e.period}: {e.description}"
            )

        return "检测到的异常事件：\n" + "\n".join(summaries)


# ---------------------------------------------------------------------------
# ProactiveAnomalyScanner
# ---------------------------------------------------------------------------

class ProactiveAnomalyScanner:
    """
    主动异常扫描器

    定期扫描所有模块/ECU 的时序数据，
    汇总异常并生成告警。
    """

    def __init__(
        self,
        detector: Optional[TimeSeriesAnomalyDetector] = None,
        report_generator: Optional[AnomalyReportGenerator] = None,
        severity_filter: str = "medium",  # 最低报告严重度
    ):
        """
        Args:
            detector: 异常检测器实例
            report_generator: 报告生成器实例
            severity_filter: 最低报告严重度 (high/medium/low)
        """
        self.detector = detector or TimeSeriesAnomalyDetector()
        self.report_generator = report_generator or AnomalyReportGenerator()
        self.severity_filter = severity_filter

        # 用于去重的已报告缓存 {(module, period, type): timestamp}
        self._reported_cache: Dict[Tuple[str, str, str], str] = {}

    def scan_all(
        self,
        data_loader: Callable[[str], pd.DataFrame],
        group_field: str = "group",
        value_field: str = "value",
        module_field: str = "target_ecu",
    ) -> List[AnomalyAlert]:
        """
        扫描所有模块的时序数据

        Args:
            data_loader: 数据加载函数，接受 SQL 或模块名，返回 DataFrame
            group_field: 时间分组字段
            value_field: 数值字段
            module_field: 模块标识字段

        Returns:
            异常告警列表
        """
        alerts: List[AnomalyAlert] = []
        severity_rank = {"high": 3, "medium": 2, "low": 1}
        min_rank = severity_rank.get(self.severity_filter, 2)

        try:
            # 加载所有模块的聚合数据
            df = data_loader("__all_modules__")

            if df is None or df.empty:
                logger.info("扫描数据为空，跳过")
                return alerts

            # 按模块分组检测
            modules = df[module_field].unique() if module_field in df.columns else ["__all__"]

            for module in modules:
                if module_field in df.columns:
                    module_df = df[df[module_field] == module]
                else:
                    module_df = df

                if module_df.empty:
                    continue

                # 转为 time_series 格式
                time_series = []
                for _, row in module_df.iterrows():
                    time_series.append({
                        group_field: str(row.get(group_field, "")),
                        value_field: row.get(value_field, 0),
                    })

                # 检测异常
                events = self.detector.detect(time_series, group_field, value_field)

                # 过滤严重度
                for event in events:
                    if severity_rank.get(event.severity, 0) < min_rank:
                        continue

                    # 去重
                    cache_key = (str(module), event.period, event.type)
                    now = datetime.now().isoformat()
                    if cache_key in self._reported_cache:
                        continue
                    self._reported_cache[cache_key] = now

                    alert = AnomalyAlert(
                        alert_id=f"alert_{len(alerts):04d}",
                        module=str(module),
                        anomaly_type=event.type,
                        severity=event.severity,
                        summary=event.description,
                        detail=event,
                    )
                    alerts.append(alert)

        except Exception as e:
            logger.error("扫描异常: %s", e, exc_info=True)

        # 按严重度排序
        alerts.sort(
            key=lambda a: severity_rank.get(a.severity, 0),
            reverse=True,
        )

        return alerts

    def generate_digest(self, alerts: List[AnomalyAlert]) -> str:
        """
        生成告警摘要

        Args:
            alerts: 告警列表

        Returns:
            自然语言摘要
        """
        if not alerts:
            return "✅ 所有模块正常，未发现异常。"

        events = [a.detail for a in alerts]
        modules = set(a.module for a in alerts)

        report = self.report_generator.generate(events, module=",".join(str(m) for m in modules))
        return report

    def clear_cache(self):
        """清除去重缓存"""
        self._reported_cache.clear()


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_anomaly_detector(**kwargs) -> TimeSeriesAnomalyDetector:
    """创建异常检测器实例"""
    return TimeSeriesAnomalyDetector(**kwargs)


def create_anomaly_report_generator() -> AnomalyReportGenerator:
    """创建异常报告生成器实例"""
    return AnomalyReportGenerator()


def create_proactive_scanner(**kwargs) -> ProactiveAnomalyScanner:
    """创建主动扫描器实例"""
    return ProactiveAnomalyScanner(**kwargs)


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("时序异常检测模块测试")
    print("=" * 60)

    # 模拟时序数据（含异常）
    test_data = [
        {"group": "2026-W01", "value": 10},
        {"group": "2026-W02", "value": 12},
        {"group": "2026-W03", "value": 11},
        {"group": "2026-W04", "value": 13},
        {"group": "2026-W05", "value": 10},
        {"group": "2026-W06", "value": 55},  # 突增！
        {"group": "2026-W07", "value": 12},
        {"group": "2026-W08", "value": 14},
        {"group": "2026-W09", "value": 16},
        {"group": "2026-W10", "value": 18},
        {"group": "2026-W11", "value": 20},
        {"group": "2026-W12", "value": 22},  # 连续上升趋势
    ]

    # 检测异常
    detector = create_anomaly_detector()
    events = detector.detect(test_data, key_field="group", value_field="value")

    print(f"\n检测到 {len(events)} 个异常事件：")
    for e in events:
        print(f"  [{e.severity}] {e.type}: {e.description}")

    # 生成报告
    generator = create_anomaly_report_generator()
    report = generator.generate(events, module="Display_Controller")
    print("\n" + report)

    # Prompt 上下文
    ctx = generator.generate_prompt_context(events)
    print("\n--- Prompt Context ---")
    print(ctx)

    print("\n✅ 测试完成")
