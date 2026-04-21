import unittest

from agent.tools import build_tool_suite


class ToolPackageTests(unittest.TestCase):
    def test_build_tool_suite_includes_packaged_representative_tools(self):
        tools = build_tool_suite(llm=None, db_path='dummy.db')

        tool_map = {tool.name: tool for tool in tools}

        for tool_name in [
            'analyze_trend',
            'analyze_risk',
            'compare_items',
            'defect_explore_kpis',
            'defect_explore_dashboard',
            'analyze_matrix_distribution',
            'analyze_matrix_aida_hotspots',
            'analyze_topissue_hotlist',
            'analyze_longrunner_hotlist',
            'correlate_defects_tests',
            'search_similar_issues',
            'analyze_tester_findings',
            'analyze_test_run',
            'groupby_aggregate',
            'analyze_project_recent_weeks',
            'match_tester_tickets',
            'semantic_coverage_report',
            'defect_explore_schema_report',
            'statistical_summary',
            'describe_dataset',
            'consult_semantic_catalog',
            'get_sqlite_schema',
            'get_db_profile',
            'run_sqlite_query',
            'query_sqlite_with_fix',
        ]:
            self.assertIn(tool_name, tool_map)
            self.assertTrue(tool_map[tool_name].__class__.__module__.startswith('agent.tools.'))


if __name__ == '__main__':
    unittest.main()