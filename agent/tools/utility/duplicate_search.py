"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class DuplicateIssueSearchTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="search_similar_issues",
            description="在历史缺陷/提票数据中检索相似问题（用于重复提票/已知问题识别）",
            parameters={
                "query": {"type": "string", "description": "检索文本"},
                "top_k": {"type": "integer", "description": "返回候选数量", "default": 8},
                "cache_key": {"type": "string", "description": "索引缓存Key（同数据集复用索引）", "default": "defects"},
            },
        )

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return {"success": False, "tool": self.name, "error": "query 不能为空"}
        top_k = int(kwargs.get("top_k") or 8)
        top_k = max(1, min(50, top_k))
        cache_key = str(kwargs.get("cache_key") or "defects").strip() or "defects"
        try:
            from duplicate_issue_finder import extract_hints, get_or_build_index

            df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
            idx = get_or_build_index(cache_key, df)
            hints = extract_hints(query)
            candidates = idx.search(query, hints=hints, top_k=top_k)
            items = []
            for c in candidates:
                items.append(
                    {
                        "score_1_10": int(getattr(c, "score_1_10", 1)),
                        "similarity": float(getattr(c, "similarity", 0.0)),
                        "ticket_id": getattr(c, "ticket_id", None),
                        "name": getattr(c, "name", ""),
                        "project": getattr(c, "project", None),
                        "pu": getattr(c, "pu", None),
                        "status_phase": getattr(c, "status_phase", None),
                        "snippet": getattr(c, "snippet", ""),
                    }
                )
            return {"success": True, "tool": self.name, "result": {"candidates": items}}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


def build_default_tools(llm: Any = None, db_path: Optional[str] = None) -> List[DataAnalysisTool]:
    """Build the default tool set for extracted executors."""
    default_tools: List[DataAnalysisTool] = [
        TrendAnalysisTool(),
        RiskAnalysisTool(),
        ComparisonTool(),
        StatisticalSummaryTool(),
        DefectExploreKpiTool(),
        DefectExploreDashboardTool(),
        MatrixDistributionTool(),
        MatrixAidaHotspotsTool(),
        TopIssueHotlistTool(),
        LongRunnerHotlistTool(),
        AnalyzeTesterFindingsTool(),
        AnalyzeTestRunTool(),
        GroupbyAggregateTool(),
        CorrelateDefectsTestsTool(),
        ProjectRecentWeeksHealthTool(),
        SemanticCatalogTool(db_path=db_path),
        DuplicateIssueSearchTool(),
        DescribeDatasetTool(),
        MatchTesterTicketsTool(),
        SemanticCoverageReportTool(),
        DefectExploreSchemaReportTool(),
    ]
    if db_path:
        default_tools.extend(
            [
                SQLiteDBProfileTool(db_path),
                SQLiteSchemaTool(db_path),
                SQLiteQueryTool(db_path),
                SQLiteNLQueryWithFixTool(db_path, llm=llm),
            ]
        )
    return default_tools
