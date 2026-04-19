"""DuckDB Analytics Layer — 从 SQLite 抽取数据并预计算聚合指标。

依赖: pip install duckdb
启用: AGENT_DUCKDB_ENABLED=1

预计算表:
  defect_daily_agg / defect_weekly_trends / ecu_severity_matrix_snapshot
  status_transition_graph / anomaly_baselines / insight_history
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# 模块级开关（供 intelligent_agent.py 导入）
ENABLED = os.getenv("AGENT_DUCKDB_ENABLED", "0").strip() in {"1", "true", "yes"}


def _is_enabled() -> bool:
    return ENABLED


class DuckDBAnalyticsLayer:
    """DuckDB 分析层 — 预计算聚合，加速 Agent 查询。"""

    def __init__(self, sqlite_db_path: Optional[str] = None, duckdb_path: Optional[str] = None):
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        if sqlite_db_path is None:
            # 自动检测 SQLite 路径
            rebuilt = os.path.join(base, "database", "local_data_rebuilt.db")
            sqlite_db_path = rebuilt if os.path.exists(rebuilt) else os.path.join(base, "database", "local_data.db")
        self.sqlite_db_path = sqlite_db_path

        if duckdb_path is None:
            os.makedirs(os.path.join(base, "database"), exist_ok=True)
            duckdb_path = os.path.join(base, "database", "analytics.duckdb")
        self.duckdb_path = duckdb_path

        self._con: Optional[duckdb.DuckDBPyConnection] = None
        self._built = False

    @property
    def is_connected(self) -> bool:
        return self._con is not None

    # ── 兼容 intelligent_agent.py 的接口 ────────────────────────────────

    def connect(self) -> None:
        """连接 DuckDB（兼容集成代码）。"""
        os.makedirs(os.path.dirname(self.duckdb_path), exist_ok=True)
        self._con = duckdb.connect(self.duckdb_path)

    def refresh(self) -> None:
        """刷新预计算数据（兼容集成代码）。"""
        self.build_all()

    def table_stats(self) -> str:
        """返回各表行数摘要（兼容集成代码）。"""
        stats = []
        for table in ["defect_daily_agg", "defect_weekly_trends",
                       "ecu_severity_matrix_snapshot", "status_transition_graph",
                       "anomaly_baselines", "insight_history"]:
            try:
                df = self.query(f"SELECT COUNT(*) as c FROM {table}")
                c = df.iloc[0]["c"] if not df.empty else 0
                stats.append(f"{table}={c}")
            except Exception:
                stats.append(f"{table}=?")
        return ", ".join(stats)

    def build_all(self) -> None:
        """从 SQLite 抽取数据，预计算所有表。"""
        if self._con is None:
            self.connect()
        logger.info("DuckDB Analytics: 开始构建预计算层...")
        t0 = datetime.now()
        self._build_defect_daily_agg()
        self._build_defect_weekly_trends()
        self._build_ecu_severity_matrix()
        self._build_status_transition_graph()
        self._build_anomaly_baselines()
        self._built = True
        logger.info(f"DuckDB Analytics: 构建完成 ({(datetime.now()-t0).total_seconds():.1f}s)")

    def update_incremental(self) -> None:
        """增量更新。"""
        self.build_all()

    # ========== 查询 ==========

    def query(self, sql: str, params: Optional[list] = None) -> pd.DataFrame:
        """执行 SQL 查询，返回 DataFrame。"""
        try:
            if params:
                return self._con.execute(sql, params).df()
            return self._con.execute(sql).df()
        except Exception as e:
            logger.warning(f"DuckDB query failed: {e}")
            return pd.DataFrame()

    def get_anomaly_baselines(self, dimension: Optional[str] = None) -> pd.DataFrame:
        """获取异常基线。dimension 可选，如 'project', 'ecu', 'severity'。"""
        if dimension:
            return self.query(
                "SELECT * FROM anomaly_baselines WHERE dimension_key LIKE ?",
                [f"{dimension}%"]
            )
        return self.query("SELECT * FROM anomaly_baselines")

    def get_daily_agg(self, project: Optional[str] = None,
                      days: int = 90) -> pd.DataFrame:
        """获取日度聚合数据。"""
        sql = f"SELECT * FROM defect_daily_agg WHERE agg_date >= CURRENT_DATE - {days}"
        if project:
            sql += f" AND project = '{project}'"
        return self.query(sql)

    def get_weekly_trends(self, project: Optional[str] = None,
                          weeks: int = 12) -> pd.DataFrame:
        """获取周趋势数据。"""
        sql = f"SELECT * FROM defect_weekly_trends WHERE week_start >= CURRENT_DATE - {weeks * 7}"
        if project:
            sql += f" AND project = '{project}'"
        return self.query(sql)

    def record_insight(self, insight_type: str, dimension: str,
                       summary: str, score: float = 0.0) -> None:
        """记录洞察，避免重复推送。"""
        self._con.execute(
            """INSERT INTO insight_history (insight_type, dimension, summary, score, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [insight_type, dimension, summary, score, datetime.now(timezone.utc).isoformat()]
        )

    def get_recent_insights(self, hours: int = 24, min_score: float = 0.0) -> pd.DataFrame:
        """获取最近 N 小时的洞察。"""
        return self.query(
            """SELECT * FROM insight_history
               WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '?' HOUR
               AND score >= ? ORDER BY score DESC""",
            [hours, min_score]
        )

    def get_active_hotspots(self, zscore_threshold: float = 2.0) -> List[Dict[str, Any]]:
        """获取当前活跃的异常热点（供 SessionDataContext 使用）。"""
        df = self.query(
            """SELECT dimension_key, metric, mean, std, last_value, zscore
               FROM anomaly_baselines
               WHERE ABS(zscore) > ?
               ORDER BY ABS(zscore) DESC LIMIT 20""",
            [zscore_threshold]
        )
        if df.empty:
            return []
        return df.to_dict("records")

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:
            pass

    # ========== 内部构建方法 ==========

    def _read_sqlite(self, sql: str) -> pd.DataFrame:
        """从 SQLite 读取数据到 DataFrame。"""
        import sqlite3
        try:
            con = sqlite3.connect(self.sqlite_db_path)
            df = pd.read_sql(sql, con)
            con.close()
            return df
        except Exception as e:
            logger.warning(f"SQLite read failed: {e}")
            return pd.DataFrame()

    def _build_defect_daily_agg(self) -> None:
        """日度聚合表。"""
        df = self._read_sqlite("""
            SELECT DATE(creation_time) as agg_date,
                   COALESCE(team,'unknown') as project,
                   COALESCE(severity,'unknown') as severity,
                   COALESCE(assigned_ecu,'unknown') as ecu,
                   COALESCE(status_phase,'unknown') as status,
                   COALESCE(program,'unknown') as program,
                   COUNT(*) as defect_count,
                   SUM(CASE WHEN severity IN ('1A','1B','1C','1D','1E','2A','2B')
                       THEN 1 ELSE 0 END) as high_severity_count
            FROM octane_defects WHERE creation_time IS NOT NULL
            GROUP BY 1,2,3,4,5,6
        """)
        if df.empty:
            return
        self._con.execute("DROP TABLE IF EXISTS defect_daily_agg")
        self._con.execute("CREATE TABLE defect_daily_agg AS SELECT * FROM df")
        try:
            self._con.execute("CREATE INDEX idx_daily_date ON defect_daily_agg(agg_date)")
        except Exception:
            pass
        logger.info(f"  defect_daily_agg: {len(df)} 行")

    def _build_defect_weekly_trends(self) -> None:
        """周趋势表 + 环比变化。"""
        self._con.execute("DROP TABLE IF EXISTS defect_weekly_trends")
        self._con.execute("""
            CREATE TABLE defect_weekly_trends AS
            SELECT DATE_TRUNC('week', CAST(agg_date AS DATE)) as week_start,
                   project, severity, ecu,
                   SUM(defect_count) as defect_count,
                   SUM(high_severity_count) as high_severity_count,
                   SUM(defect_count) - LAG(SUM(defect_count)) OVER (
                       PARTITION BY project, severity, ecu
                       ORDER BY DATE_TRUNC('week', CAST(agg_date AS DATE))
                   ) as wow_change
            FROM defect_daily_agg GROUP BY 1,2,3,4
        """)
        count_df = self.query("SELECT COUNT(*) as c FROM defect_weekly_trends")
        count = count_df.iloc[0]["c"] if not count_df.empty else 0
        logger.info(f"  defect_weekly_trends: {count} 行")

    def _build_ecu_severity_matrix(self) -> None:
        """ECU × 严重度矩阵快照。"""
        self._con.execute("DROP TABLE IF EXISTS ecu_severity_matrix_snapshot")
        self._con.execute("""
            CREATE TABLE ecu_severity_matrix_snapshot AS
            SELECT ecu, severity, SUM(defect_count) as defect_count,
                   CURRENT_TIMESTAMP as snapshot_at
            FROM defect_daily_agg WHERE ecu != 'unknown'
            GROUP BY 1, 2
        """)
        count_df = self.query("SELECT COUNT(*) as c FROM ecu_severity_matrix_snapshot")
        count = count_df.iloc[0]["c"] if not count_df.empty else 0
        logger.info(f"  ecu_severity_matrix_snapshot: {count} 行")

    def _build_status_transition_graph(self) -> None:
        """状态转换统计: from_status, to_status, cnt, avg_days。"""
        df = self._read_sqlite("""
            SELECT COALESCE(phase,'unknown') as from_status,
                   COALESCE(status_phase,'unknown') as to_status,
                   COUNT(*) as cnt,
                   ROUND(AVG(JULIANDAY(last_modified)-JULIANDAY(creation_time)),2) as avg_days
            FROM octane_defects
            WHERE creation_time IS NOT NULL AND last_modified IS NOT NULL
            GROUP BY 1,2
        """)
        if df.empty:
            return
        self._con.register("_tmp", df)
        self._con.execute("CREATE OR REPLACE TABLE status_transition_graph AS SELECT * FROM _tmp")
        self._con.unregister("_tmp")
        logger.info(f"  status_transition_graph: {len(df)} 行")

    def _build_anomaly_baselines(self) -> None:
        """异常基线：每个维度的 mean/std/zscore。"""
        self._con.execute("DROP TABLE IF EXISTS anomaly_baselines")
        self._con.execute("""
            CREATE TABLE anomaly_baselines AS
            WITH daily_totals AS (
                SELECT project as dimension_key,'defect_count' as metric,agg_date,defect_count as value
                FROM defect_daily_agg WHERE project!='unknown'
                UNION ALL
                SELECT ecu,'defect_count',agg_date,defect_count
                FROM defect_daily_agg WHERE ecu!='unknown'
                UNION ALL
                SELECT severity,'defect_count',agg_date,defect_count
                FROM defect_daily_agg WHERE severity!='unknown'
            ),
            stats AS (
                SELECT dimension_key, metric,
                       AVG(value) as mean, STDDEV(value) as std,
                       AVG(value) FILTER (WHERE agg_date >= CURRENT_DATE - INTERVAL '7' DAY) as last_value
                FROM daily_totals GROUP BY dimension_key, metric
                HAVING COUNT(*) >= 7
            )
            SELECT dimension_key, metric, mean, std, last_value,
                   CASE WHEN std>0 THEN (last_value-mean)/std ELSE 0 END as zscore,
                   CURRENT_TIMESTAMP as updated_at
            FROM stats
        """)
        # 洞察历史表
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS insight_history (
                id INTEGER PRIMARY KEY DEFAULT nextval('insight_seq'),
                insight_type VARCHAR, dimension VARCHAR,
                summary TEXT, score DOUBLE, created_at VARCHAR
            )
        """)
        try:
            self._con.execute("DROP SEQUENCE IF EXISTS insight_seq")
            self._con.execute("CREATE SEQUENCE insight_seq START 1")
        except Exception:
            pass
        count_df = self.query("SELECT COUNT(*) as c FROM anomaly_baselines")
        count = count_df.iloc[0]["c"] if not count_df.empty else 0
        logger.info(f"  anomaly_baselines: {count} 条基线")


# ========== 便捷入口 ==========

def create_analytics_layer(repo_root: Optional[str] = None) -> Optional[DuckDBAnalyticsLayer]:
    """创建分析层实例（如果启用）。"""
    if not _is_enabled():
        logger.debug("DuckDB Analytics 未启用 (AGENT_DUCKDB_ENABLED=1)")
        return None

    base = repo_root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    layer = DuckDBAnalyticsLayer()

    if not os.path.exists(layer.sqlite_db_path):
        logger.warning(f"SQLite 不存在: {layer.sqlite_db_path}")
        return None

    try:
        layer.connect()
        layer.build_all()
    except Exception as e:
        logger.warning(f"DuckDB 构建失败: {e}")
        return None

    return layer


def create_duckdb_context_provider(layer: DuckDBAnalyticsLayer):
    """创建 DuckDB 上下文 Provider（注入到 ContextChain）。"""
    from agent.core.context_provider import ContextProvider

    class DuckDBContextProvider(ContextProvider):
        @property
        def name(self) -> str:
            return "duckdb_analytics"

        def __init__(self, duckdb_layer):
            self.layer = duckdb_layer

        def priority(self) -> int:
            return 50

        def provide(self, data, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
            result: Dict[str, Any] = {}
            # 注入异常热点
            try:
                hotspots = self.layer.get_active_hotspots(zscore_threshold=2.0)
                if hotspots:
                    lines = []
                    for h in hotspots[:5]:
                        dim = h.get("dimension_key", "?")
                        zscore = h.get("zscore", 0)
                        direction = "↑" if zscore > 0 else "↓"
                        lines.append(f"{dim}: {direction} 偏离{abs(zscore)*100:.0f}%")
                    result["duckdb_hotspots"] = "数据异常点: " + ", ".join(lines)
            except Exception:
                pass
            return result

    return DuckDBContextProvider(layer)
