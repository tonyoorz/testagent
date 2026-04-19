"""
Proactive Insight Engine — 主动洞察引擎

定期扫描数据，自动发现5种洞察类型：
1. 趋势预警：缺陷数连续变化，预测未来走势
2. 状态停滞：缺陷卡在某个状态超过阈值
3. 关联发现：维度间的异常关联（如ECU更新后缺陷激增）
4. 测试盲区：低测试覆盖但应该关注的风险区域
5. 预测：基于历史模式的风险预警

产出的洞察：
- 注入 Agent 的每次对话上下文
- 可推送给用户（由 ProactiveInsights 模块调度）

环境变量：AGENT_INSIGHT_ENGINE=1 启用
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ENABLED = os.getenv("AGENT_INSIGHT_ENGINE", "0").strip() in {"1", "true", "yes"}


class Insight:
    """单条洞察。"""
    def __init__(self, insight_type: str, dimension: str, summary: str,
                 score: float = 0.0, detail: Optional[Dict] = None):
        self.insight_type = insight_type
        self.dimension = dimension
        self.summary = summary
        self.score = score  # 0-1，越高越重要
        self.detail = detail or {}
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_type": self.insight_type,
            "dimension": self.dimension,
            "summary": self.summary,
            "score": self.score,
            "detail": self.detail,
            "created_at": self.created_at,
        }


class ProactiveInsightEngine:
    """主动洞察引擎 — 自动扫描数据，发现洞察。"""

    def __init__(self, duckdb_layer=None, sqlite_db_path: Optional[str] = None):
        self.analytics = duckdb_layer
        self.sqlite_db_path = sqlite_db_path
        self._insights: List[Insight] = []

    # ========== 主入口 ==========

    def scan_all(self) -> List[Insight]:
        """运行所有扫描器，返回发现的洞察。"""
        self._insights = []

        self._scan_trend_warning()
        self._scan_stagnant_defects()
        self._scan_test_blindspots()
        self._scan_correlation_anomalies()
        self._scan_predictions()

        # 按分数排序
        self._insights.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"🔍 Insight Engine: 发现 {len(self._insights)} 条洞察")
        return self._insights

    def get_top_insights(self, n: int = 5, min_score: float = 0.3) -> List[Insight]:
        """获取 top N 洞察。"""
        return [i for i in self._insights if i.score >= min_score][:n]

    def get_context_text(self, max_insights: int = 3, max_length: int = 500) -> str:
        """生成注入 prompt 的洞察文本。"""
        top = self.get_top_insights(n=max_insights, min_score=0.3)
        if not top:
            return ""

        lines = []
        for ins in top:
            icon = {
                "trend_warning": "📈",
                "stagnant": "🚫",
                "correlation": "🔗",
                "blindspot": "👁️",
                "prediction": "🔮",
            }.get(ins.insight_type, "💡")
            lines.append(f"{icon} [{ins.dimension}] {ins.summary}")

        text = "🔍 主动洞察:\n" + "\n".join(f"  - {l}" for l in lines)
        if len(text) > max_length:
            text = text[:max_length] + "..."
        return text

    def record_to_duckdb(self) -> None:
        """将洞察记录到 DuckDB insight_history 表。"""
        if not self.analytics:
            return
        for ins in self._insights:
            try:
                self.analytics.record_insight(
                    insight_type=ins.insight_type,
                    dimension=ins.dimension,
                    summary=ins.summary,
                    score=ins.score,
                )
            except Exception:
                pass

    # ========== 扫描器 ==========

    def _scan_trend_warning(self) -> None:
        """扫描1: 趋势预警 — 连续N周上升/下降的维度。"""
        if not self.analytics:
            return

        df = self.analytics.query("""
            SELECT dimension_key, metric, mean, std, last_value, zscore
            FROM anomaly_baselines
            WHERE ABS(zscore) > 1.5
            ORDER BY ABS(zscore) DESC
        """)
        if df.empty:
            return

        for _, row in df.head(5).iterrows():
            dim = row["dimension_key"]
            zscore = row["zscore"]
            last = row["last_value"]
            mean = row["mean"]
            direction = "上升" if zscore > 0 else "下降"
            pct = abs(zscore) * 100

            score = min(abs(zscore) / 5.0, 1.0)  # zscore=5 → 满分
            summary = f"{dim} 缺陷数{direction}异常（当前{last:.0f}，均值{mean:.0f}，偏离{pct:.0f}%）"

            self._insights.append(Insight(
                insight_type="trend_warning",
                dimension=dim,
                summary=summary,
                score=score,
                detail={"zscore": zscore, "last_value": last, "mean": mean},
            ))

    def _scan_stagnant_defects(self) -> None:
        """扫描2: 状态停滞 — Open/Closed 之外停留过久的缺陷。"""
        if not self.sqlite_db_path and not self.analytics:
            return

        import sqlite3
        db_path = self.sqlite_db_path
        if not db_path:
            return

        try:
            con = sqlite3.connect(db_path)
            df = pd.read_sql("""
                SELECT
                    status_phase,
                    severity,
                    COUNT(*) as cnt,
                    AVG(julianday('now') - julianday(last_modified)) as avg_days_stagnant
                FROM octane_defects
                WHERE status_phase NOT IN ('Closed', 'Rejected')
                    AND last_modified IS NOT NULL
                GROUP BY status_phase, severity
                HAVING avg_days_stagnant > 14
                ORDER BY avg_days_stagnant DESC
            """, con)
            con.close()
        except Exception as e:
            logger.debug(f"停滞扫描跳过: {e}")
            return

        for _, row in df.head(5).iterrows():
            status = row["status_phase"]
            sev = row["severity"]
            cnt = row["cnt"]
            days = row["avg_days_stagnant"]

            # 高严重度 + 长时间 = 高分
            severity_boost = 0.3 if sev in ("1A", "1B", "1C", "2A") else 0.0
            time_boost = min(days / 60.0, 0.4)
            score = 0.3 + severity_boost + time_boost

            summary = f"{cnt}个{sev}缺陷在'{status}'状态已停滞{days:.0f}天"

            self._insights.append(Insight(
                insight_type="stagnant",
                dimension=f"{status}/{sev}",
                summary=summary,
                score=score,
                detail={"status": status, "severity": sev, "count": cnt, "avg_days": days},
            ))

    def _scan_test_blindspots(self) -> None:
        """扫描3: 测试盲区 — 低执行率但应有覆盖的区域。"""
        if not self.sqlite_db_path:
            return

        import sqlite3
        try:
            con = sqlite3.connect(self.sqlite_db_path)
            # 检查表是否存在
            tables = pd.read_sql(
                "SELECT name FROM sqlite_master WHERE type='table'", con
            )["name"].tolist()
            if "octane_testcases" not in tables or "octane_manual_runs" not in tables:
                con.close()
                return

            # 找执行率低的测试区域
            df = pd.read_sql("""
                SELECT
                    run_team as team,
                    COUNT(DISTINCT test_id) as total_tests,
                    SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) as completed,
                    ROUND(100.0 * SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) as completion_rate
                FROM octane_manual_runs
                WHERE year >= CAST(strftime('%Y', 'now') AS INTEGER) - 1
                GROUP BY run_team
                HAVING COUNT(*) >= 10
                ORDER BY completion_rate ASC
            """, con)
            con.close()
        except Exception as e:
            logger.debug(f"盲区扫描跳过: {e}")
            return

        for _, row in df.head(3).iterrows():
            team = row["team"]
            rate = row["completion_rate"]
            total = row["total_tests"]

            if rate < 50:
                score = 0.4 + (50 - rate) / 100.0
                summary = f"{team} 测试完成率仅{rate}%（共{total}个用例），可能存在覆盖不足"

                self._insights.append(Insight(
                    insight_type="blindspot",
                    dimension=team,
                    summary=summary,
                    score=score,
                    detail={"team": team, "completion_rate": rate, "total_tests": total},
                ))

    def _scan_correlation_anomalies(self) -> None:
        """扫描4: 关联发现 — 维度间的异常关联。"""
        if not self.analytics:
            return

        # 从日度聚合中找 project × severity 的异常关联
        df = self.analytics.query("""
            SELECT project, severity, SUM(defect_count) as total
            FROM defect_daily_agg
            WHERE agg_date >= CURRENT_DATE - INTERVAL '30' DAY
            GROUP BY project, severity
            ORDER BY total DESC
        """)
        if df.empty or len(df) < 5:
            return

        # 简单关联检测：某个 project 的某个 severity 占比异常高
        project_totals = df.groupby("project")["total"].sum().to_dict()
        for _, row in df.head(5).iterrows():
            proj = row["project"]
            sev = row["severity"]
            total = row["total"]
            proj_total = project_totals.get(proj, 1)
            ratio = total / proj_total if proj_total > 0 else 0

            # 某个 severity 占比超过 40% 且总数 > 10
            if ratio > 0.4 and total > 10:
                score = 0.3 + ratio * 0.4
                summary = f"{proj} 的 {sev} 缺陷占比{ratio*100:.0f}%（{total}个），远高于正常分布"

                self._insights.append(Insight(
                    insight_type="correlation",
                    dimension=f"{proj}/{sev}",
                    summary=summary,
                    score=min(score, 0.9),
                    detail={"project": proj, "severity": sev, "ratio": ratio, "total": total},
                ))

    def _scan_predictions(self) -> None:
        """扫描5: 简单预测 — 基于近期趋势外推。"""
        if not self.analytics:
            return

        df = self.analytics.query("""
            SELECT
                dimension_key,
                metric,
                mean,
                std,
                last_value,
                zscore,
                CASE
                    WHEN last_value > mean AND zscore > 1 THEN 'accelerating_up'
                    WHEN last_value > mean AND zscore > 0 THEN 'rising'
                    WHEN last_value < mean AND zscore < -1 THEN 'accelerating_down'
                    ELSE 'stable'
                END as trend_direction
            FROM anomaly_baselines
            WHERE ABS(zscore) > 1
        """)
        if df.empty:
            return

        for _, row in df.head(3).iterrows():
            dim = row["dimension_key"]
            trend = row["trend_direction"]
            last = row["last_value"]
            mean = row["mean"]

            if trend == "accelerating_up":
                # 简单外推：如果趋势持续，2周后预测值
                predicted = last + (last - mean) * 0.5
                score = 0.5 + min(abs(row["zscore"]) / 10.0, 0.4)
                summary = (
                    f"{dim} 缺陷呈加速上升趋势，"
                    f"按当前速率2周后预计达到{predicted:.0f}个/周"
                )
                self._insights.append(Insight(
                    insight_type="prediction",
                    dimension=dim,
                    summary=summary,
                    score=score,
                    detail={"predicted_value": predicted, "trend": trend},
                ))


def create_insight_engine(duckdb_layer=None,
                          sqlite_db_path: Optional[str] = None) -> Optional[ProactiveInsightEngine]:
    """创建洞察引擎（如果启用）。"""
    if not ENABLED:
        return None
    engine = ProactiveInsightEngine(duckdb_layer, sqlite_db_path)
    return engine
