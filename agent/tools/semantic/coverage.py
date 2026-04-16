"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class SemanticCoverageReportTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="semantic_coverage_report",
            description="对比语义目录期望字段与实际数据列，输出覆盖率与缺失字段Top",
            parameters={
                "dashboard": {"type": "string", "default": "defect_explore"},
                "max_columns": {"type": "integer", "default": 50},
                "sample_rows": {"type": "integer", "default": 5},
            },
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        datasets = data if isinstance(data, dict) else {}
        dashboard = str(kwargs.get("dashboard") or "defect_explore").strip() or "defect_explore"
        max_columns = max(1, min(int(kwargs.get("max_columns") or 50), 200))
        sample_rows = max(0, min(int(kwargs.get("sample_rows") or 5), 20))
        try:
            from semantic_catalog.runtime import SemanticCatalog

            catalog = SemanticCatalog()
            out_sets = []
            for name, df in datasets.items():
                ddf = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
                cols = [str(c) for c in ddf.columns.tolist()][:max_columns]
                sel = catalog.select(question=f"{name} 缺陷 defects bug", dashboard=dashboard, dataframe_columns=cols, max_each=1)
                semantic_id = (sel.datasets[0].get("id") if sel.datasets else "") or ""
                semantic_item = sel.datasets[0] if sel.datasets else {}
                expected = []
                for k in ["time_columns", "common_columns", "core_dimensions"]:
                    v = semantic_item.get(k)
                    if isinstance(v, list):
                        expected.extend([str(x) for x in v if x is not None and str(x).strip()])
                expected = list(dict.fromkeys(expected))
                present = sum(1 for c in expected if c in cols)
                missing = [c for c in expected if c not in cols]
                null_top = []
                if not ddf.empty and cols:
                    ratios = []
                    for c in cols[:max_columns]:
                        try:
                            ratios.append((c, float(ddf[c].isna().mean())))
                        except Exception:
                            continue
                    ratios.sort(key=lambda x: x[1], reverse=True)
                    null_top = [{"column": c, "null_ratio": round(r, 4)} for c, r in ratios[:10]]
                sample = []
                if sample_rows > 0 and not ddf.empty:
                    for _, row in ddf[cols[: min(len(cols), 12)]].head(sample_rows).iterrows():
                        sample.append({c: row.get(c) for c in cols[: min(len(cols), 12)]})
                out_sets.append(
                    {
                        "dataset": name,
                        "semantic_id": semantic_id or ("octane_defects" if name == "defects" else ""),
                        "columns": cols,
                        "semantic_expected": expected,
                        "coverage": {
                            "expected_total": int(len(expected)),
                            "present": int(present),
                            "missing": missing[:50],
                        },
                        "null_top": null_top,
                        "sample_rows": sample,
                    }
                )
            return {"success": True, "tool": self.name, "result": {"dashboard": dashboard, "datasets": out_sets}}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}
