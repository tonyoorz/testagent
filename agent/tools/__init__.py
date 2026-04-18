"""Tool modules for the data analysis agent.

All tools are auto-discovered from:
- agent/tools/analysis/   — core analysis tools
- agent/tools/sql/        — database query tools
- agent/tools/semantic/   — semantic catalog tools
- agent/tools/utility/    — utility tools
"""

from agent.tools.base import DataAnalysisTool

# Analysis tools
from agent.tools.analysis.trend import TrendAnalysisTool
from agent.tools.analysis.risk import RiskAnalysisTool
from agent.tools.analysis.comparison import ComparisonTool
from agent.tools.analysis.statistical_summary import StatisticalSummaryTool
from agent.tools.analysis.groupby_aggregate import GroupbyAggregateTool
from agent.tools.analysis.correlate import CorrelateDefectsTestsTool
from agent.tools.analysis.project_health import ProjectRecentWeeksHealthTool
from agent.tools.analysis.test_run import AnalyzeTestRunTool
from agent.tools.analysis.tester_findings import AnalyzeTesterFindingsTool
from agent.tools.analysis.defect_kpi import DefectExploreKpiTool
from agent.tools.analysis.defect_dashboard import DefectExploreDashboardTool
from agent.tools.analysis.matrix_distribution import MatrixDistributionTool
from agent.tools.analysis.matrix_aida import MatrixAidaHotspotsTool
from agent.tools.analysis.topissue import TopIssueHotlistTool
from agent.tools.analysis.longrunner import LongRunnerHotlistTool
from agent.tools.analysis.anomaly_scan import AnomalyScanTool
from agent.tools.analysis.root_cause import RootCauseTool
from agent.tools.analysis.risk_heatmap import RiskHeatmapTool
from agent.tools.analysis.test_strategy import TestStrategyTool
from agent.tools.analysis.association_discovery import AssociationDiscoveryTool
from agent.tools.analysis.strategy_evaluator import StrategyEvaluatorTool
from agent.tools.analysis.predictive_risk import PredictiveRiskTool

# SQL tools
from agent.tools.sql.schema import SQLiteSchemaTool
from agent.tools.sql.db_profile import SQLiteDBProfileTool
from agent.tools.sql.query import SQLiteQueryTool
from agent.tools.sql.nl_query import SQLiteNLQueryWithFixTool

# Semantic tools
from agent.tools.semantic.catalog import SemanticCatalogTool
from agent.tools.semantic.describe import DescribeDatasetTool
from agent.tools.semantic.match_tester import MatchTesterTicketsTool
from agent.tools.semantic.coverage import SemanticCoverageReportTool
from agent.tools.semantic.schema_report import DefectExploreSchemaReportTool

# Utility tools
from agent.tools.utility.python_analysis import PythonAnalysisTool
from agent.tools.utility.duplicate_search import DuplicateIssueSearchTool


def build_default_tools(llm=None, db_path=None, **kwargs):
    """Build the default set of analysis tools.

    Args:
        llm: Optional LLM client for tools that need it.
        db_path: Optional database path for SQL tools.

    Returns a list of instantiated DataAnalysisTool subclasses.
    """
    llm = kwargs.get('llm')
    db_path = kwargs.get('db_path')

    tools = [
        # Core analysis
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
        # Deep analysis (from agent/core/)
        AnomalyScanTool(),
        RootCauseTool(),
        RiskHeatmapTool(),
        TestStrategyTool(),
        AssociationDiscoveryTool(),
        # P1+P2 高阶编排工具
        StrategyEvaluatorTool(),
        PredictiveRiskTool(),
        # Semantic
        SemanticCatalogTool(),
        DescribeDatasetTool(),
        MatchTesterTicketsTool(),
        SemanticCoverageReportTool(),
        DefectExploreSchemaReportTool(),
        # Utility
        PythonAnalysisTool(),
        DuplicateIssueSearchTool(),
    ]

    # SQL tools (optional, need db_path)
    if db_path:
        tools.extend([
            SQLiteSchemaTool(db_path=db_path),
            SQLiteDBProfileTool(db_path=db_path),
            SQLiteQueryTool(db_path=db_path),
            SQLiteNLQueryWithFixTool(db_path=db_path, llm=llm),
        ])

    return tools


__all__ = [
    'DataAnalysisTool',
    'build_default_tools',
    'TrendAnalysisTool', 'RiskAnalysisTool', 'ComparisonTool',
    'StatisticalSummaryTool', 'DefectExploreKpiTool', 'DefectExploreDashboardTool',
    'MatrixDistributionTool', 'MatrixAidaHotspotsTool', 'TopIssueHotlistTool',
    'LongRunnerHotlistTool', 'AnalyzeTesterFindingsTool', 'AnalyzeTestRunTool',
    'GroupbyAggregateTool', 'CorrelateDefectsTestsTool', 'ProjectRecentWeeksHealthTool',
    'AnomalyScanTool', 'RootCauseTool', 'RiskHeatmapTool', 'TestStrategyTool', 'AssociationDiscoveryTool',
    'StrategyEvaluatorTool', 'PredictiveRiskTool',
    'SQLiteSchemaTool', 'SQLiteDBProfileTool', 'SQLiteQueryTool', 'SQLiteNLQueryWithFixTool',
    'SemanticCatalogTool', 'DescribeDatasetTool', 'MatchTesterTicketsTool',
    'SemanticCoverageReportTool', 'DefectExploreSchemaReportTool',
    'PythonAnalysisTool', 'DuplicateIssueSearchTool',
]
