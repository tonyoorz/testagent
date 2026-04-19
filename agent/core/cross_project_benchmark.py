"""
Cross Project Benchmark — 跨项目对标分析

对比不同项目在同一维度的表现：
- 缺陷密度对比（defects/测试用例数）
- 严重度分布对比
- 解决效率对比（平均关闭天数）
- 风险评分对标

用于回答"别的项目做得怎么样"这类问题。

环境变量：AGENT_CROSS_PROJECT=1 启用
"""

import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ENABLED = os.getenv("AGENT_CROSS_PROJECT", "0").strip() in {"1", "true", "yes"}


class CrossProjectBenchmark:
    """跨项目对标分析。"""

    def __init__(self, duckdb_layer=None, sqlite_db_path: Optional[str] = None):
        self.analytics = duckdb_layer
        self.sqlite_db_path = sqlite_db_path

    # ========== 主接口 ==========

    def benchmark_all(self) -> Dict[str, Any]:
        """全量对标：所有项目的综合对比。"""
        result = {
            "defect_density": self._benchmark_defect_density(),
            "severity_distribution": self._benchmark_severity(),
            "resolution_efficiency": self._benchmark_resolution(),
        }
        return result

    def benchmark_project(self, project: str) -> Dict[str, Any]:
        """单个项目的对标报告。"""
        all_data = self.benchmark_all()
        project_report = {"project": project, "benchmarks": {}}

        for metric_name, data in all_data.items():
            if isinstance(data, list):
                proj_entry = next((d for d in data if d.get("project") == project), None)
                if proj_entry:
                    # 排名
                    if metric_name == "defect_density":
                        sorted_projects = sorted(data, key=lambda x: x.get("density", 0))
                    elif metric_name == "resolution_efficiency":
                        sorted_projects = sorted(data, key=lambda x: x.get("avg_days", 999))
                    else:
                        sorted_projects = data

                    rank = next(i for i, d in enumerate(sorted_projects) if d.get("project") == project) + 1
                    proj_entry["rank"] = rank
                    proj_entry["total_projects"] = len(sorted_projects)
                    project_report["benchmarks"][metric_name] = proj_entry

        return project_report

    def get_benchmark_text(self, project: Optional[str] = None) -> str:
        """生成可注入 prompt 的对标文本。"""
        if project:
            return self._single_project_text(project)
        return self._overview_text()

    # ========== 各维度对标 ==========

    def _benchmark_defect_density(self) -> List[Dict]:
        """缺陷密度对比。"""
        if not self.analytics:
            return []

        df = self.analytics.query("""
            SELECT project, SUM(defect_count) as total_defects
            FROM defect_daily_agg
            WHERE agg_date >= CURRENT_DATE - INTERVAL '90' DAY
            GROUP BY project
            ORDER BY total_defects DESC
        """)
        if df.empty:
            return []

        avg_defects = df["total_defects"].mean()
        results = []
        for _, row in df.iterrows():
            density = row["total_defects"] / 90.0  # 日均
            level = "高" if density > avg_defects / 90 * 1.5 else (
                "中" if density > avg_defects / 90 * 0.5 else "低"
            )
            results.append({
                "project": row["project"],
                "total_defects": int(row["total_defects"]),
                "density": round(density, 2),
                "level": level,
            })
        return results

    def _benchmark_severity(self) -> List[Dict]:
        """严重度分布对比。"""
        if not self.analytics:
            return []

        df = self.analytics.query("""
            SELECT project, severity, SUM(defect_count) as cnt
            FROM defect_daily_agg
            WHERE agg_date >= CURRENT_DATE - INTERVAL '90' DAY
            GROUP BY project, severity
        """)
        if df.empty:
            return []

        high_sev = ["1A", "1B", "1C", "1D", "1E"]
        project_totals = df.groupby("project")["cnt"].sum().to_dict()
        high_sev_df = df[df["severity"].isin(high_sev)]
        high_by_project = high_sev_df.groupby("project")["cnt"].sum()

        results = []
        for proj in project_totals:
            total = project_totals[proj]
            high = high_by_project.get(proj, 0)
            ratio = high / total if total > 0 else 0
            results.append({
                "project": proj,
                "total": int(total),
                "high_severity_count": int(high),
                "high_severity_ratio": round(ratio, 3),
            })

        return sorted(results, key=lambda x: x["high_severity_ratio"], reverse=True)

    def _benchmark_resolution(self) -> List[Dict]:
        """解决效率对比。"""
        if not self.sqlite_db_path:
            return []

        import sqlite3
        try:
            con = sqlite3.connect(self.sqlite_db_path)
            df = pd.read_sql("""
                SELECT
                    team as project,
                    COUNT(*) as total,
                    SUM(CASE WHEN status_phase = 'Closed' THEN 1 ELSE 0 END) as closed,
                    AVG(
                        CASE WHEN status_phase = 'Closed' AND last_modified IS NOT NULL AND creation_time IS NOT NULL
                        THEN julianday(last_modified) - julianday(creation_time)
                        END
                    ) as avg_days_to_close
                FROM octane_defects
                WHERE creation_time >= date('now', '-90 days')
                GROUP BY team
            """, con)
            con.close()
        except Exception as e:
            logger.debug(f"解决效率对比跳过: {e}")
            return []

        results = []
        for _, row in df.iterrows():
            closed_rate = row["closed"] / row["total"] if row["total"] > 0 else 0
            results.append({
                "project": row["project"],
                "total": int(row["total"]),
                "closed_rate": round(closed_rate, 3),
                "avg_days": round(row["avg_days_to_close"] or 0, 1),
            })
        return results

    # ========== 文本生成 ==========

    def _single_project_text(self, project: str) -> str:
        """单项目对标文本。"""
        report = self.benchmark_project(project)
        benchmarks = report.get("benchmarks", {})
        if not benchmarks:
            return ""

        lines = [f"📊 项目 {project} 对标:"]
        for metric, data in benchmarks.items():
            rank = data.get("rank", "?")
            total = data.get("total_projects", "?")
            if metric == "defect_density":
                lines.append(f"  缺陷密度: 排名{rank}/{total}（日均{data.get('density', '?')}个，级别{data.get('level', '?')}）")
            elif metric == "severity_distribution":
                lines.append(f"  高严重度占比: {data.get('high_severity_ratio', '?')*100:.1f}%")
            elif metric == "resolution_efficiency":
                lines.append(f"  关闭率: {data.get('closed_rate', '?')*100:.1f}%，平均{data.get('avg_days', '?')}天")

        return "\n".join(lines)

    def _overview_text(self) -> str:
        """全局概览文本。"""
        density = self._benchmark_defect_density()
        if not density:
            return ""

        lines = ["📊 跨项目对标概览:"]
        top3 = sorted(density, key=lambda x: x["density"], reverse=True)[:3]
        for d in top3:
            lines.append(f"  {d['project']}: 日均{d['density']}个（{d['level']}密度，共{d['total_defects']}个）")

        return "\n".join(lines)


def create_benchmark(duckdb_layer=None,
                     sqlite_db_path: Optional[str] = None) -> Optional[CrossProjectBenchmark]:
    """创建对标分析器（如果启用）。"""
    if not ENABLED:
        return None
    return CrossProjectBenchmark(duckdb_layer, sqlite_db_path)
