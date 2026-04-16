"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
from datetime import datetime
from analysis_utils import top_counts, time_series_counts, severity_rate_by, compute_defect_explore_kpis, defect_quality_stats, stacked_top_counts, nunique_by, longrunner_phase_statistics, inflow_outflow_summary, word_frequencies, defect_wordcloud_source

logger = logging.getLogger(__name__)


class DefectExploreDashboardTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_dashboard",
            description="按 Defect Explore 看板口径汇总业务图表指标，并根据自然语言选择相关图表输出",
            parameters={
                "question": {"type": "string", "description": "用户自然语言问题（用于选择相关图表）", "default": ""},
                "max_items": {"type": "integer", "description": "每个图表最多输出条目数", "default": 15},
                "include_inflow_outflow": {"type": "boolean", "description": "是否包含 Inflow/Outflow（需 history 数据）", "default": False},
                "include_longrunner": {"type": "boolean", "description": "是否包含 LongRunner phase 耗时统计（需 history 数据）", "default": False},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
            question = (kwargs.get("question") or "").strip()
            q = question.lower()
            max_items = int(kwargs.get("max_items", 15))
            include_inflow_outflow = bool(kwargs.get("include_inflow_outflow", True))
            include_longrunner = bool(kwargs.get("include_longrunner", False))

            def wants_all() -> bool:
                return any(k in q for k in [
                    "所有", "全部", "全量", "全景", "全看板", "全部图表", "所有图表", "dashboard", "图表总览", "看板总览",
                    "测试策略", "测试计划", "测试方案", "质量策略", "策略", "计划"
                ])

            def want(keys: List[str]) -> bool:
                if wants_all():
                    return True
                return any(k in q for k in keys)

            def want_strict(keys: List[str]) -> bool:
                return any(k in q for k in keys)

            charts: List[Dict[str, Any]] = []

            if df is None or df.empty:
                return {"success": True, "tool": self.name, "result": {"charts": [], "note": "当前缺陷数据为空"}, "insights": ["缺陷数据为空，无法生成看板图表指标"]}

            aida_col = "top_aida" if "top_aida" in df.columns else "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None
            time_col = "creation_time" if "creation_time" in df.columns else "tcreationtime" if "tcreationtime" in df.columns else None
            domain_col = "domain_display" if "domain_display" in df.columns else "domain" if "domain" in df.columns else None
            project_col = "project" if "project" in df.columns else "tproject" if "tproject" in df.columns else "ecu" if "ecu" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "status" if "status" in df.columns else None
            fv_col = "fv" if "fv" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None

            if want(["kpi", "指标", "卡片", "概览", "总览"]):
                kpis = compute_defect_explore_kpis(df)
                charts.append({"id": "kpi-cards", "title": "KPI 卡片", "data": kpis})

            if want(["fv", "版本", "release"]):
                if fv_col and "severity_group" in df.columns:
                    charts.append({"id": "fv-distribution-chart", "title": "Top Issue by FV", "data": stacked_top_counts(df, fv_col, "severity_group", top_n=max_items)})
                elif fv_col:
                    charts.append({"id": "fv-distribution-chart", "title": "Top Issue by FV", "data": top_counts(df, fv_col, top_n=max_items)})

            if want(["aida", "功能", "模块"]):
                if aida_col and "severity_group" in df.columns:
                    charts.append({"id": "defect-status-chart", "title": "Top Issue by AIDA", "data": stacked_top_counts(df, aida_col, "severity_group", top_n=max_items)})
                elif aida_col:
                    charts.append({"id": "defect-status-chart", "title": "Top Issue by AIDA", "data": top_counts(df, aida_col, top_n=max_items)})

            if want(["solution cluster", "cluster", "domain", "解决簇", "解决群"]):
                if domain_col and "severity_group" in df.columns:
                    charts.append({"id": "solution-cluster-chart", "title": "Top Issue by Solution Cluster", "data": stacked_top_counts(df, domain_col, "severity_group", top_n=max_items)})
                elif domain_col:
                    charts.append({"id": "solution-cluster-chart", "title": "Top Issue by Solution Cluster", "data": top_counts(df, domain_col, top_n=max_items)})

            if want(["tester", "测试人员", "发现人", "谁发现"]):
                if "tester" in df.columns and "severity_group" in df.columns:
                    charts.append({"id": "tester-efficiency-chart", "title": "Tester Efficiency", "data": stacked_top_counts(df, "tester", "severity_group", top_n=min(20, max_items))})
                    charts.append({"id": "tester-severity-chart", "title": "Tester Severe Rate", "data": severity_rate_by(df, "tester", top_n=min(30, max_items))})

            if want(["状态", "status", "phase"]):
                if status_col:
                    charts.append({"id": "defect-status-distribution-chart", "title": "Status Distribution", "data": top_counts(df, status_col, top_n=max_items)})
                if status_col and "severity_group" in df.columns:
                    charts.append({"id": "status-transition-efficiency-chart", "title": "Status × Severity", "data": stacked_top_counts(df, status_col, "severity_group", top_n=max_items)})

            if want(["矩阵", "matrix"]):
                if matrix_col:
                    charts.append({"id": "defect-matrix-chart", "title": "Defect Matrix Distribution", "data": top_counts(df, matrix_col, top_n=max_items)})
                if project_col and matrix_col:
                    charts.append({"id": "project-matrix-distribution-chart", "title": "Project × Matrix", "data": stacked_top_counts(df, project_col, matrix_col, top_n=min(20, max_items))})

            if want(["项目", "project", "ecu", "贡献", "密度"]):
                if project_col:
                    if "severity_group" in df.columns:
                        charts.append({"id": "defect-density-chart", "title": "Defect Density (Project × Severity)", "data": stacked_top_counts(df, project_col, "severity_group", top_n=min(25, max_items))})
                        charts.append({"id": "project-defect-volume-chart", "title": "Project Defect Volume", "data": stacked_top_counts(df, project_col, "severity_group", top_n=min(25, max_items))})
                        charts.append({"id": "project-severity-rate-chart", "title": "Project Severe Rate", "data": severity_rate_by(df, project_col, top_n=min(30, max_items))})
                    if status_col:
                        charts.append({"id": "project-status-distribution-chart", "title": "Project × Status", "data": stacked_top_counts(df, project_col, status_col, top_n=min(20, max_items))})
                    if aida_col:
                        charts.append({"id": "project-aida-coverage-chart", "title": "Project AIDA Coverage", "data": nunique_by(df, project_col, aida_col, top_n=min(30, max_items))})
                    if want(["质量", "quality", "评分", "评估"]):
                        charts.append({"id": "quality-assessment-table", "title": "Quality Assessment", "data": defect_quality_stats(df, group_col=project_col, aida_col=aida_col or "aida_english", top_n=min(30, max_items))})

            if want(["趋势", "trend", "变化", "增长", "下降"]):
                if time_col:
                    charts.append({"id": "defect-discovery-trend-chart", "title": "Defect Discovery Trend", "data": time_series_counts(df, time_col, freq="D", stack_col="severity_group" if "severity_group" in df.columns else None)})
                    if project_col:
                        charts.append({"id": "project-trend-comparison-chart", "title": "Project Trend Comparison", "data": time_series_counts(df, time_col, freq="D", stack_col=project_col, top_stacks=10)})
                if aida_col and time_col:
                    dft = df.copy()
                    dft["_t"] = pd.to_datetime(dft[time_col], errors="coerce")
                    dft = dft[dft["_t"].notna()]
                    if not dft.empty:
                        span_days = max(1, int((dft["_t"].max() - dft["_t"].min()).days) + 1)
                        g = dft.groupby(aida_col).size().sort_values(ascending=False).head(20)
                        prod = []
                        for k, c in g.items():
                            prod.append({"key": str(k), "daily_productivity": round(int(c) / span_days, 3), "count": int(c), "span_days": span_days})
                        prod = sorted(prod, key=lambda x: x["daily_productivity"], reverse=True)[: min(10, max_items)]
                        charts.append({"id": "aida-productivity-chart", "title": "AIDA Productivity", "data": prod})

            if want(["词云", "wordcloud", "关键词", "高频词"]):
                texts = defect_wordcloud_source(df)
                charts.append({"id": "main-wordcloud-chart", "title": "Word Frequencies", "data": word_frequencies(texts, top_n=min(60, max_items * 4))})

            if include_inflow_outflow and want_strict(["inflow", "outflow", "收敛", "吞吐", "净积压", "net accumulation"]):
                charts.append({"id": "inflow-outflow-chart", "title": "Inflow/Outflow", "data": inflow_outflow_summary()})

            if include_longrunner and want_strict(["long runner", "longrunner", "长周期", "处理周期", "phase", "阶段耗时"]):
                id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
                if id_col and "processing_cycle_days" in df.columns:
                    sub = df.copy()
                    sub["_days"] = pd.to_numeric(sub["processing_cycle_days"], errors="coerce")
                    sub = sub[sub["_days"].notna() & (sub["_days"] >= 30)]
                    sub = sub.sort_values("_days", ascending=False).head(50)
                    ids = sub[id_col].tolist()
                    charts.append({"id": "phase-duration-bar-chart-lr", "title": "LongRunner Phase Duration", "data": longrunner_phase_statistics(ids)})

            insights: List[str] = []
            if charts:
                insights.append(f"已汇总图表数量: {len(charts)}")
            if wants_all() and not charts:
                insights.append("未能从当前数据集中识别可计算的图表字段")

            return {"success": True, "tool": self.name, "result": {"charts": charts}, "insights": insights}
        except Exception as e:
            logger.error(f"Defect Explore 看板汇总失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
