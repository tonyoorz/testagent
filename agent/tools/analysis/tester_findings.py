"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class AnalyzeTesterFindingsTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_tester_findings",
            description="分析缺陷由谁发现最多（tester 维度），并给出代表性缺陷样本",
            parameters={
                "top_n": {
                    "type": "integer",
                    "description": "输出前 N 位 tester",
                    "default": 10
                },
                "sample_per_tester": {
                    "type": "integer",
                    "description": "每位 tester 展示的缺陷样本数",
                    "default": 5
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"top_testers": [], "total_defects": 0},
                    "insights": ["缺陷数据为空，无法统计 tester 发现问题情况"]
                }

            candidates = [c for c in ["tester", "found_by", "reporter", "author_name"] if c in data.columns]
            tester_col = None
            if candidates:
                best = None
                best_cnt = -1
                for c in candidates:
                    s = data[c].astype(str).map(lambda x: str(x).strip())
                    s = s[s.notna() & (s != "") & (s.str.lower() != "nan")]
                    cnt = int(len(s))
                    if cnt > best_cnt:
                        best_cnt = cnt
                        best = c
                tester_col = best
            if not tester_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 tester/发现人字段"}

            top_n = int(kwargs.get("top_n", 10))
            sample_per_tester = int(kwargs.get("sample_per_tester", 5))

            df = data.copy()
            df[tester_col] = df[tester_col].astype(str).map(lambda s: s.strip())
            df = df[df[tester_col].notna() & (df[tester_col] != "") & (df[tester_col].str.lower() != "nan")]
            if df.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"top_testers": [], "total_defects": int(len(data))},
                    "insights": ["缺陷数据存在，但 tester 字段为空/缺失，无法统计"]
                }

            total_defects = int(len(df))
            counts = df[tester_col].value_counts()
            top_testers = counts.head(max(1, min(top_n, 50))).to_dict()

            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None
            sev_col = "severity_group" if "severity_group" in df.columns else "severity" if "severity" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "phase" if "phase" in df.columns else None
            aida_col = "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None

            topissue_series = None
            if "is_topissue" in df.columns:
                topissue_series = df["is_topissue"].astype(bool)
            elif "topissue" in df.columns:
                topissue_series = df["topissue"].astype(str).str.lower().str.contains("topissue")

            results = []
            for tester, cnt in top_testers.items():
                g = df[df[tester_col] == tester]
                projects = g[project_col].value_counts().head(5).to_dict() if project_col else {}
                projects = {k: int(v) for k, v in projects.items() if str(k).strip() and str(k).strip().lower() not in {"nan", "none"}}
                aidas = g[aida_col].value_counts().head(5).to_dict() if aida_col else {}
                aidas = {k: int(v) for k, v in aidas.items() if str(k).strip() and str(k).strip().lower() not in {"nan", "none"}}
                severities = g[sev_col].value_counts().head(3).to_dict() if sev_col else {}

                topissue_cnt = int(topissue_series[g.index].sum()) if topissue_series is not None else 0
                topissue_ratio = round(topissue_cnt / len(g) * 100, 2) if len(g) else 0.0

                sample_df = g
                if time_col and time_col in g.columns:
                    sample_df = g.sort_values(time_col, ascending=False)
                sample_df = sample_df.head(max(0, sample_per_tester))

                samples = []
                for _, r in sample_df.iterrows():
                    samples.append({
                        "id": r.get(id_col) if id_col else None,
                        "title": r.get(title_col) if title_col else None,
                        "project": r.get(project_col) if project_col else None,
                        "creation_time": str(r.get(time_col)) if time_col else None,
                        "severity": r.get(sev_col) if sev_col else None,
                        "matrix": r.get(matrix_col) if matrix_col else None,
                        "status": r.get(status_col) if status_col else None,
                        "aida": r.get(aida_col) if aida_col else None,
                        "is_topissue": bool(r.get("is_topissue")) if "is_topissue" in df.columns else None
                    })

                results.append({
                    "tester": tester,
                    "defect_count": int(cnt),
                    "share": round(cnt / total_defects * 100, 2),
                    "topissue_count": topissue_cnt,
                    "topissue_ratio": topissue_ratio,
                    "top_projects": projects,
                    "top_aidas": aidas,
                    "top_severities": severities,
                    "samples": samples
                })

            insights = []
            if results:
                insights.append(f"发现问题最多的 tester: {results[0]['tester']}（{results[0]['defect_count']} 条，占 {results[0]['share']}%）")
                top5_sum = sum(r["defect_count"] for r in results[:5])
                insights.append(f"Top 5 tester 共发现 {top5_sum} 条，占 {round(top5_sum / total_defects * 100, 2)}%")

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "total_defects": total_defects,
                    "top_testers": results
                },
                "insights": insights
            }
        except Exception as e:
            logger.error(f"tester 发现问题分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}
