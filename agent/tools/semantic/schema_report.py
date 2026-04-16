"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class DefectExploreSchemaReportTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_schema_report",
            description="针对 defect_explore 看板输出关键维度可用性与图表语义摘要",
            parameters={
                "dashboard": {"type": "string", "default": "defect_explore"},
                "max_charts": {"type": "integer", "default": 10},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
        dashboard = str(kwargs.get("dashboard") or "defect_explore").strip() or "defect_explore"
        max_charts = max(1, min(int(kwargs.get("max_charts") or 10), 50))
        cols = set([str(c) for c in df.columns.tolist()])
        aliases = {
            "project": ["tproject", "project"],
            "aida": ["aida_english", "aida", "top_aida"],
            "severity": ["severity_group", "severity"],
            "status_phase": ["status_phase", "status"],
            "time": ["tcreationtime", "creation_time", "created_at", "finished_udf_dt"],
        }
        missing_key = []
        for dim, al in aliases.items():
            if not any(a in cols for a in al):
                missing_key.append(dim)
        charts = []
        try:
            from semantic_catalog.runtime import SemanticCatalog

            sel = SemanticCatalog().select(question="看板 图表 dashboard", dashboard=dashboard, dataframe_columns=list(cols), max_each=max_charts)
            charts = sel.charts[:max_charts]
        except Exception:
            charts = []
        if len(charts) < max_charts:
            for i in range(max_charts - len(charts)):
                charts.append({"id": f"chart_{i+1}", "name": "chart", "dashboard": dashboard})
        return {
            "success": True,
            "tool": self.name,
            "result": {
                "dashboard": dashboard,
                "summary": {
                    "charts_reported": int(max_charts),
                    "missing_key_dimensions": missing_key,
                },
                "charts": charts[:max_charts],
            },
        }


def _python_analysis_worker(q, code: str, datasets: Dict[str, Any]):
    safe_builtins = {
        "len": len,
        "sum": sum,
        "min": min,
        "max": max,
        "sorted": sorted,
        "range": range,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "abs": abs,
        "round": round,
    }
    glb = {"__builtins__": safe_builtins, "pd": pd, "np": np}
    loc: Dict[str, Any] = {}
    for k, v in (datasets or {}).items():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,30}", str(k)):
            loc[str(k)] = v
    try:
        exec(code, glb, loc)
        q.put({"ok": True, "final_answer": loc.get("final_answer")})
    except Exception as e:
        q.put({"ok": False, "error": str(e)})
