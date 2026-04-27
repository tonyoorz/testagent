"""Minimal modular tool package skeleton.

This package exposes a stable package-level tool factory while the majority of
tool implementations still live in agent.core.intelligent_agent.
"""

import importlib
from typing import Any, List

from agent.tools.analysis.comparison import ComparisonTool
from agent.tools.analysis.correlate_defects_tests import CorrelateDefectsTestsTool
from agent.tools.analysis.defect_explore_dashboard import DefectExploreDashboardTool
from agent.tools.analysis.defect_explore_kpis import DefectExploreKpiTool
from agent.tools.analysis.duplicate_feedback import SubmitDuplicateSearchFeedbackTool
from agent.tools.analysis.duplicate_issue_search import DuplicateIssueSearchTool
from agent.tools.analysis.groupby_aggregate import GroupbyAggregateTool
from agent.tools.analysis.longrunner_hotlist import LongRunnerHotlistTool
from agent.tools.analysis.matrix_distribution import MatrixDistributionTool
from agent.tools.analysis.matrix_hotspots import MatrixAidaHotspotsTool
from agent.tools.analysis.project_health import ProjectRecentWeeksHealthTool
from agent.tools.analysis.risk import RiskAnalysisTool
from agent.tools.analysis.test_run import AnalyzeTestRunTool
from agent.tools.analysis.tester_findings import AnalyzeTesterFindingsTool
from agent.tools.analysis.topissue_hotlist import TopIssueHotlistTool
from agent.tools.analysis.trend import TrendAnalysisTool
from agent.tools.analysis.statistical_summary import StatisticalSummaryTool
from agent.tools.base import DataAnalysisTool
from agent.tools.semantic.catalog import SemanticCatalogTool
from agent.tools.semantic.coverage_report import SemanticCoverageReportTool
from agent.tools.semantic.describe import DescribeDatasetTool
from agent.tools.semantic.match_tester_tickets import MatchTesterTicketsTool
from agent.tools.semantic.schema_report import DefectExploreSchemaReportTool
from agent.tools.sql.db_profile import SQLiteDBProfileTool
from agent.tools.sql.query import SQLiteQueryTool
from agent.tools.sql.query_with_fix import SQLiteNLQueryWithFixTool
from agent.tools.sql.schema import SQLiteSchemaTool


def build_tool_suite(llm: Any = None, db_path: str = None, **kwargs: Any) -> List[DataAnalysisTool]:
	packaged_tools: List[DataAnalysisTool] = [
		TrendAnalysisTool(),
		RiskAnalysisTool(),
		ComparisonTool(),
		DefectExploreKpiTool(),
		DefectExploreDashboardTool(),
		MatrixDistributionTool(),
		MatrixAidaHotspotsTool(),
		TopIssueHotlistTool(),
		LongRunnerHotlistTool(),
		CorrelateDefectsTestsTool(),
		DuplicateIssueSearchTool(),
		SubmitDuplicateSearchFeedbackTool(),
		AnalyzeTesterFindingsTool(),
		AnalyzeTestRunTool(),
		GroupbyAggregateTool(),
		ProjectRecentWeeksHealthTool(),
		StatisticalSummaryTool(),
		SemanticCatalogTool(db_path=db_path),
		DescribeDatasetTool(),
		MatchTesterTicketsTool(),
		SemanticCoverageReportTool(),
		DefectExploreSchemaReportTool(),
	]
	if db_path:
		packaged_tools.extend(
			[
				SQLiteSchemaTool(db_path=db_path),
				SQLiteDBProfileTool(db_path=db_path),
				SQLiteQueryTool(db_path=db_path),
				SQLiteNLQueryWithFixTool(db_path=db_path, llm=llm),
			]
		)

	names = {tool.name for tool in packaged_tools}
	legacy_agent = importlib.import_module('agent.core.intelligent_agent')
	legacy_factory = getattr(legacy_agent, 'build_default_tools', None)
	if callable(legacy_factory):
		for tool in list(legacy_factory(llm=llm, db_path=db_path) or []):
			if getattr(tool, 'name', None) not in names:
				packaged_tools.append(tool)
	return packaged_tools


__all__ = [
	'DataAnalysisTool',
	'build_tool_suite',
	'TrendAnalysisTool',
	'RiskAnalysisTool',
	'ComparisonTool',
	'DefectExploreKpiTool',
	'DefectExploreDashboardTool',
	'MatrixDistributionTool',
	'MatrixAidaHotspotsTool',
	'TopIssueHotlistTool',
	'LongRunnerHotlistTool',
	'CorrelateDefectsTestsTool',
	'DuplicateIssueSearchTool',
	'SubmitDuplicateSearchFeedbackTool',
	'AnalyzeTesterFindingsTool',
	'AnalyzeTestRunTool',
	'GroupbyAggregateTool',
	'ProjectRecentWeeksHealthTool',
	'StatisticalSummaryTool',
	'SemanticCatalogTool',
	'DescribeDatasetTool',
	'MatchTesterTicketsTool',
	'SemanticCoverageReportTool',
	'DefectExploreSchemaReportTool',
	'SQLiteSchemaTool',
	'SQLiteDBProfileTool',
	'SQLiteQueryTool',
	'SQLiteNLQueryWithFixTool',
]

