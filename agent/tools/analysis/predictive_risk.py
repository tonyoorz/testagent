"""风险预判工具 — 基于趋势外推预测未来风险"""

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class PredictiveRiskTool(DataAnalysisTool):
    """风险预判：基于趋势外推，预测未来30天的风险分布"""

    def __init__(self):
        super().__init__(
            name="predictive_risk",
            description="基于历史趋势预测未来缺陷分布，识别加速恶化模块并给出预警",
            parameters={
                "horizon_days": {
                    "type": "integer",
                    "description": "预测天数",
                    "default": 30,
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回前 N 个高风险预测模块",
                    "default": 10,
                },
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行风险预判"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"report": "数据为空，无法预测", "predictions": [], "warnings": [], "actions": []},
                    "insights": ["数据为空"],
                }

            horizon_days = kwargs.get("horizon_days", 30)
            top_n = kwargs.get("top_n", 10)

            # 查找字段
            time_col = _find_column(data, ["created_date", "tcreationtime", "creation_time", "created_at"])
            module_col = _find_column(data, ["target_ecu", "ecu", "module"])

            if time_col not in data.columns:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"report": "缺少时间列，无法预测", "predictions": [], "warnings": [], "actions": []},
                    "insights": ["缺少时间列"],
                }

            df = data.copy()
            df["_date"] = pd.to_datetime(df[time_col], errors="coerce")
            df = df.dropna(subset=["_date"])

            if len(df) < 3:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"report": "数据点不足（<3），无法预测", "predictions": [], "warnings": [], "actions": []},
                    "insights": ["数据点不足"],
                }

            # 按模块预测
            predictions = self._predict_by_module(df, module_col, horizon_days)

            # 总体预测
            total_prediction = self._predict_total(df, horizon_days)

            # 生成预警
            warnings = self._generate_warnings(predictions)

            # 建议干预
            actions = self._generate_actions(predictions, warnings)

            # 生成报告
            report = self._build_report(total_prediction, predictions, warnings, actions, horizon_days)

            # 按预测缺陷数排序
            predictions.sort(key=lambda p: p["predicted_count"], reverse=True)
            predictions = predictions[:top_n]

            insights = self._collect_insights(total_prediction, warnings)

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "report": report,
                    "total_predicted": total_prediction,
                    "predictions": predictions,
                    "warnings": warnings,
                    "actions": actions,
                    "horizon_days": horizon_days,
                },
                "insights": insights,
            }

        except Exception as e:
            logger.error("风险预判失败: %s", e, exc_info=True)
            return {"success": False, "tool": self.name, "error": str(e)}

    # ---- 预测逻辑 ----

    def _predict_by_module(
        self, df: pd.DataFrame, module_col: str, horizon_days: int
    ) -> List[Dict]:
        """按模块分别预测"""
        predictions = []

        if module_col not in df.columns:
            # 无模块维度，整体预测
            pred = self._fit_and_predict(df, horizon_days)
            if pred:
                pred["module"] = "全部"
                predictions.append(pred)
            return predictions

        for module, group in df.groupby(module_col):
            if len(group) < 2:
                continue
            pred = self._fit_and_predict(group, horizon_days)
            if pred:
                pred["module"] = str(module)
                predictions.append(pred)

        return predictions

    def _predict_total(self, df: pd.DataFrame, horizon_days: int) -> Dict:
        """总体预测"""
        pred = self._fit_and_predict(df, horizon_days)
        if pred:
            return pred
        return {"predicted_count": 0, "slope": 0, "acceleration": 0, "confidence": "low"}

    def _fit_and_predict(self, df: pd.DataFrame, horizon_days: int) -> Dict:
        """
        对单个模块的周缺陷数拟合线性回归，外推预测。

        Returns:
            {predicted_count, slope, weekly_avg, acceleration, confidence}
        """
        # 按周聚合
        weekly = df.set_index("_date").resample("W").size().reset_index(name="count")
        n_weeks = len(weekly)

        if n_weeks < 2:
            return None

        x = np.arange(n_weeks, dtype=float)
        y = weekly["count"].values.astype(float)

        # 线性回归 (numpy polyfit)
        try:
            coeffs = np.polyfit(x, y, 1)
            slope = coeffs[0]
            intercept = coeffs[1]
        except Exception:
            return None

        # 预测未来 horizon_days 对应的周数
        future_weeks = horizon_days / 7.0
        last_x = n_weeks - 1
        future_x = np.arange(last_x + 1, last_x + 1 + future_weeks)

        predicted_values = slope * future_x + intercept
        # 不预测负数
        predicted_values = np.maximum(predicted_values, 0)
        predicted_total = predicted_values.sum()

        # 加速度：用二次拟合检测趋势是否在加速
        acceleration = 0.0
        if n_weeks >= 4:
            try:
                coeffs2 = np.polyfit(x, y, 2)
                acceleration = coeffs2[0]  # 二次项系数，正=加速上升
            except Exception:
                pass

        # 置信度
        confidence = self._estimate_confidence(y, n_weeks)

        # 近期平均
        recent_window = min(4, n_weeks)
        recent_avg = float(y[-recent_window:].mean())

        return {
            "predicted_count": round(float(predicted_total), 0),
            "slope": round(float(slope), 2),
            "weekly_avg": round(float(y.mean()), 1),
            "recent_weekly_avg": round(recent_avg, 1),
            "acceleration": round(float(acceleration), 3),
            "confidence": confidence,
            "n_weeks": n_weeks,
        }

    def _estimate_confidence(self, y: np.ndarray, n_weeks: int) -> str:
        """估算预测置信度"""
        if n_weeks < 4:
            return "low"
        if n_weeks < 8:
            return "medium"

        # 检查数据波动性
        cv = np.std(y) / max(np.mean(y), 1)
        if cv < 0.3:
            return "high"
        elif cv < 0.6:
            return "medium"
        return "low"

    # ---- 预警与建议 ----

    def _generate_warnings(self, predictions: List[Dict]) -> List[Dict]:
        """生成预警"""
        warnings = []

        for p in predictions:
            module = p.get("module", "未知")

            # 加速恶化
            if p["acceleration"] > 0.5 and p["slope"] > 0:
                warnings.append({
                    "level": "high",
                    "module": module,
                    "message": f"🔴 {module} 缺陷增速加快（加速度={p['acceleration']:.2f}），如不干预可能触发 showstopper",
                })
            # 持续上升
            elif p["slope"] > 1.0 and p["predicted_count"] > 10:
                warnings.append({
                    "level": "medium",
                    "module": module,
                    "message": f"🟡 {module} 缺陷持续上升（斜率={p['slope']:.1f}/周），预计新增 ~{p['predicted_count']:.0f} 个",
                })
            # 近期恶化（近4周平均高于整体平均）
            elif p.get("recent_weekly_avg", 0) > p.get("weekly_avg", 0) * 1.5 and p["slope"] > 0:
                warnings.append({
                    "level": "medium",
                    "module": module,
                    "message": f"🟡 {module} 近期缺陷频率上升（近{4}周均{p['recent_weekly_avg']:.1f} vs 整体均{p['weekly_avg']:.1f}）",
                })

        # 按严重度排序
        level_rank = {"high": 2, "medium": 1}
        warnings.sort(key=lambda w: level_rank.get(w["level"], 0), reverse=True)
        return warnings

    def _generate_actions(self, predictions: List[Dict], warnings: List[Dict]) -> List[str]:
        """生成建议干预"""
        actions = []

        # 从预警提取行动
        high_warnings = [w for w in warnings if w["level"] == "high"]
        for w in high_warnings:
            actions.append(f"🔴 {w['module']}: 安排专项测试，覆盖近期新增功能")

        # 按预测缺陷数排序的前几个模块
        top_pred = sorted(predictions, key=lambda p: p["predicted_count"], reverse=True)[:3]
        for p in top_pred:
            if p["predicted_count"] > 5 and p["slope"] > 0:
                actions.append(f"🟡 {p['module']}: 预计新增 ~{p['predicted_count']:.0f} 个缺陷，建议增加测试资源")

        if not actions:
            actions.append("✅ 整体趋势平稳，保持当前测试策略即可")

        return actions

    # ---- 报告 ----

    def _build_report(
        self,
        total: Dict,
        predictions: List[Dict],
        warnings: List[Dict],
        actions: List[str],
        horizon_days: int,
    ) -> str:
        """生成预判报告"""
        lines = [f"## 风险预判（未来{horizon_days}天）", ""]

        # 总量预测
        confidence_label = {"high": "高", "medium": "中", "low": "低"}.get(total.get("confidence", "low"), "低")
        lines.append(f"### 预计新增缺陷: ~{total.get('predicted_count', 0):.0f}个（置信度{confidence_label}）")

        # 模块明细
        sorted_pred = sorted(predictions, key=lambda p: p["predicted_count"], reverse=True)
        if sorted_pred:
            lines.append("")
            lines.append("### 模块预测明细")
            for p in sorted_pred[:8]:
                module = p.get("module", "未知")
                cnt = p["predicted_count"]
                trend_icon = "📈" if p["slope"] > 0.5 else ("📉" if p["slope"] < -0.5 else "➡️")
                accel_flag = " ⚠️加速" if p["acceleration"] > 0.3 else ""
                lines.append(f"  {trend_icon} {module}: +{cnt:.0f}个 (斜率={p['slope']:.1f}/周{accel_flag})")

        # 预警
        if warnings:
            lines.append("")
            lines.append("### 预警")
            for w in warnings:
                lines.append(f"  {w['message']}")

        # 建议干预
        if actions:
            lines.append("")
            lines.append("### 建议干预")
            for i, a in enumerate(actions, 1):
                lines.append(f"  {i}. {a}")

        return "\n".join(lines)

    def _collect_insights(self, total: Dict, warnings: List[Dict]) -> List[str]:
        """收集洞察"""
        insights = [f"预计未来新增 ~{total.get('predicted_count', 0):.0f} 个缺陷"]

        high_warnings = [w for w in warnings if w["level"] == "high"]
        if high_warnings:
            modules = ", ".join(w["module"] for w in high_warnings)
            insights.append(f"🔴 {len(high_warnings)} 个模块加速恶化: {modules}")

        return insights


def _find_column(data: pd.DataFrame, candidates: List[str]) -> str:
    """查找第一个存在的列"""
    for c in candidates:
        if c in data.columns:
            return c
    return candidates[0]
