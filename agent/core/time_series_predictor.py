"""
Time Series Predictor — 时序预测模块

基于历史数据做简单预测：
- 周度缺陷数预测（线性回归 + 季节性）
- 项目风险趋势预测
- Sprint 级别的风险预警

不依赖重型库（不用 Prophet/ARIMA），用简单统计方法，
在有数据后可以升级为 ML 模型。

环境变量：AGENT_PREDICTOR=1 启用
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ENABLED = os.getenv("AGENT_PREDICTOR", "0").strip() in {"1", "true", "yes"}


class TimeSeriesPredictor:
    """时序预测器 — 基于历史趋势的轻量级预测。"""

    def __init__(self, duckdb_layer=None):
        self.analytics = duckdb_layer

    # ========== 主接口 ==========

    def predict_weekly_defects(self, project: Optional[str] = None,
                               weeks_ahead: int = 4) -> Dict[str, Any]:
        """预测未来N周的缺陷数。"""
        df = self._get_weekly_history(project)
        if df.empty or len(df) < 4:
            return {"status": "insufficient_data", "message": "至少需要4周历史数据"}

        # 按周聚合
        weekly = df.groupby("week_start")["defect_count"].sum().reset_index()
        weekly = weekly.sort_values("week_start").tail(12)  # 取最近12周

        values = weekly["defect_count"].values
        dates = weekly["week_start"].values

        # 线性回归预测
        trend_slope, trend_intercept = self._linear_fit(values)
        last_date = pd.to_datetime(dates[-1])

        predictions = []
        for i in range(1, weeks_ahead + 1):
            pred_date = last_date + timedelta(weeks=i)
            pred_value = max(0, trend_slope * (len(values) + i - 1) + trend_intercept)

            # 加入简单季节性（最近3周同期的平均偏差）
            seasonal_factor = self._seasonal_factor(values, i)
            pred_value = max(0, pred_value * seasonal_factor)

            # 置信区间（基于残差标准差）
            residuals = values - (trend_slope * np.arange(len(values)) + trend_intercept)
            std_err = np.std(residuals) if len(residuals) > 2 else max(pred_value * 0.3, 5)

            predictions.append({
                "week": str(pred_date.date()),
                "predicted": round(pred_value, 1),
                "lower": round(max(0, pred_value - 1.96 * std_err), 1),
                "upper": round(pred_value + 1.96 * std_err, 1),
            })

        current_avg = np.mean(values[-4:])
        trend_direction = "上升" if trend_slope > 0.5 else ("下降" if trend_slope < -0.5 else "平稳")

        return {
            "status": "ok",
            "project": project or "all",
            "current_avg_weekly": round(current_avg, 1),
            "trend_direction": trend_direction,
            "trend_slope": round(trend_slope, 2),
            "predictions": predictions,
        }

    def predict_risk_trajectory(self, project: str,
                                weeks_ahead: int = 4) -> Dict[str, Any]:
        """预测项目风险走势。"""
        df = self._get_weekly_history(project)
        if df.empty or len(df) < 4:
            return {"status": "insufficient_data"}

        # 按周 + severity 聚合
        weekly = df.groupby(["week_start", "severity"])["defect_count"].sum().reset_index()
        weekly = weekly.sort_values("week_start")

        # 高严重度权重
        high_sev = ["1A", "1B", "1C", "1D", "1E", "2A", "2B"]
        weekly["risk_weight"] = weekly["severity"].apply(
            lambda s: 3.0 if s in high_sev[:4] else (2.0 if s in high_sev else 1.0)
        )
        weekly["risk_score"] = weekly["defect_count"] * weekly["risk_weight"]

        risk_by_week = weekly.groupby("week_start")["risk_score"].sum().reset_index()
        risk_by_week = risk_by_week.sort_values("week_start").tail(8)

        values = risk_by_week["risk_score"].values
        slope, intercept = self._linear_fit(values)
        last_date = pd.to_datetime(risk_by_week["week_start"].values[-1])

        trajectory = []
        current_risk = values[-1]
        for i in range(1, weeks_ahead + 1):
            pred_date = last_date + timedelta(weeks=i)
            pred_risk = max(0, slope * (len(values) + i - 1) + intercept)
            trajectory.append({
                "week": str(pred_date.date()),
                "risk_score": round(pred_risk, 1),
            })

        peak_week = max(trajectory, key=lambda x: x["risk_score"])
        risk_level = "高" if peak_week["risk_score"] > current_risk * 1.2 else (
            "中" if peak_week["risk_score"] > current_risk * 0.8 else "低"
        )

        return {
            "status": "ok",
            "project": project,
            "current_risk": round(current_risk, 1),
            "predicted_peak_week": peak_week["week"],
            "predicted_peak_risk": peak_week["risk_score"],
            "risk_level": risk_level,
            "trajectory": trajectory,
        }

    def generate_prediction_text(self, project: Optional[str] = None) -> str:
        """生成可注入 prompt 的预测文本。"""
        results = []

        # 周度预测
        pred = self.predict_weekly_defects(project)
        if pred.get("status") == "ok":
            trend = pred["trend_direction"]
            avg = pred["current_avg_weekly"]
            next_w = pred["predictions"][0] if pred["predictions"] else None
            if next_w:
                results.append(
                    f"缺陷趋势{trend}（当前周均{avg}个，下周预计{next_w['predicted']}个，"
                    f"范围[{next_w['lower']}-{next_w['upper']}]）"
                )

        # 风险预测
        if project:
            risk = self.predict_risk_trajectory(project)
            if risk.get("status") == "ok" and risk["risk_level"] != "低":
                results.append(
                    f"项目{project}风险级别{risk['risk_level']}，"
                    f"峰值预计在{risk['predicted_peak_week']}（风险分{risk['predicted_peak_risk']}）"
                )

        return "\n".join(results) if results else ""

    # ========== 内部方法 ==========

    def _get_weekly_history(self, project: Optional[str] = None) -> pd.DataFrame:
        """获取周度历史数据。"""
        if not self.analytics:
            return pd.DataFrame()

        if project:
            return self.analytics.get_weekly_trends(project=project, weeks=24)
        return self.analytics.query(
            "SELECT * FROM defect_daily_agg WHERE agg_date >= CURRENT_DATE - 168"
        )

    @staticmethod
    def _linear_fit(values: np.ndarray) -> Tuple[float, float]:
        """简单线性回归。"""
        x = np.arange(len(values))
        if len(x) < 2:
            return 0.0, float(values[0]) if len(values) > 0 else 0.0
        slope = np.polyfit(x, values, 1)[0]
        intercept = np.polyfit(x, values, 1)[1]
        return float(slope), float(intercept)

    @staticmethod
    def _seasonal_factor(values: np.ndarray, ahead: int) -> float:
        """简单季节性因子（最近同周期的平均偏差）。"""
        if len(values) < 4:
            return 1.0
        mean = np.mean(values)
        if mean == 0:
            return 1.0
        # 取同期位置的历史值
        idx = len(values) - 4 + (ahead % 4)
        if idx < len(values):
            return values[idx] / mean
        return 1.0


def create_predictor(duckdb_layer=None) -> Optional[TimeSeriesPredictor]:
    """创建预测器（如果启用）。"""
    if not ENABLED:
        return None
    return TimeSeriesPredictor(duckdb_layer)
