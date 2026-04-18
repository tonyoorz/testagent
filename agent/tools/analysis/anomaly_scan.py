"""时序异常检测工具 — 包装 anomaly_detector 模块"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
from agent.core.anomaly_detector import (
    TimeSeriesAnomalyDetector,
    AnomalyReportGenerator,
)

logger = logging.getLogger(__name__)


class AnomalyScanTool(DataAnalysisTool):
    """时序异常检测工具：Z-score / 移动平均 / 连续趋势"""

    def __init__(self):
        super().__init__(
            name="anomaly_scan",
            description="时序异常检测：识别数据中的突增突降、移动平均偏离和连续趋势",
            parameters={
                "group_by": {
                    "type": "string",
                    "description": "时间分组维度（week/month 或自定义列名）",
                    "default": "week",
                },
                "metric": {
                    "type": "string",
                    "description": "统计指标",
                    "default": "count",
                },
                "z_threshold": {
                    "type": "number",
                    "description": "Z-score 阈值",
                    "default": 3.0,
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行异常检测"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"events": [], "report": "数据为空，无法执行异常检测"},
                    "insights": ["数据为空"],
                }

            group_by = kwargs.get("group_by", "week")
            metric = kwargs.get("metric", "count")
            z_threshold = kwargs.get("z_threshold", 3.0)

            # 构建时序数据
            time_series = self._build_time_series(data, group_by, metric)
            if not time_series:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"events": [], "report": "无法构建时序数据"},
                    "insights": ["时序数据构建失败，可能缺少时间列"],
                }

            # 执行检测
            detector = TimeSeriesAnomalyDetector(z_threshold=z_threshold)
            events = detector.detect(time_series, key_field="group", value_field="value")

            # 生成报告
            report_gen = AnomalyReportGenerator()
            report_text = report_gen.generate(events)

            # 序列化事件
            event_list = [
                {
                    "type": e.type,
                    "severity": e.severity,
                    "period": e.period,
                    "value": e.value,
                    "expected": e.expected,
                    "deviation": e.deviation,
                    "description": e.description,
                }
                for e in events
            ]

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "events": event_list,
                    "report": report_text,
                    "total_anomalies": len(events),
                    "high_count": sum(1 for e in events if e.severity == "high"),
                    "medium_count": sum(1 for e in events if e.severity == "medium"),
                },
                "insights": self._generate_insights(events),
            }

        except Exception as e:
            logger.error("异常检测失败: %s", e)
            return {"success": False, "tool": self.name, "error": str(e)}

    def _build_time_series(
        self, data: pd.DataFrame, group_by: str, metric: str
    ) -> List[Dict]:
        """从 DataFrame 构建时序数据"""
        # 查找时间列
        time_col = None
        for candidate in ["tcreationtime", "creation_time", "created_at", "created_date", "finished_udf_dt"]:
            if candidate in data.columns:
                time_col = candidate
                break

        if time_col is None:
            return []

        df = data.copy()
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])

        if df.empty:
            return []

        # 时间分组
        if group_by == "week":
            df["_group"] = df[time_col].dt.to_period("W").astype(str)
        elif group_by == "month":
            df["_group"] = df[time_col].dt.to_period("M").astype(str)
        else:
            return []

        # 聚合
        grouped = df.groupby("_group").size().reset_index(name="value")

        return [
            {"group": str(row["_group"]), "value": int(row["value"])}
            for _, row in grouped.iterrows()
        ]

    def _generate_insights(self, events) -> List[str]:
        """生成洞察"""
        if not events:
            return ["未发现显著异常"]

        insights = [f"检测到 {len(events)} 个异常事件"]
        high = [e for e in events if e.severity == "high"]
        if high:
            insights.append(f"其中 {len(high)} 个为高严重度，建议立即排查")
        return insights
