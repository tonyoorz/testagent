import unittest
from types import SimpleNamespace

from agent.core.task_planner import TaskPlanner


class _DummyTool:
    def __init__(self, expects_datasets=False):
        self._expects_datasets = expects_datasets

    def expects_datasets(self):
        return self._expects_datasets


class _DummyExecutor:
    def __init__(self):
        self.tools = {
            "semantic_coverage_report": _DummyTool(),
            "get_db_profile": _DummyTool(),
            "query_sqlite_with_fix": _DummyTool(),
            "groupby_aggregate": _DummyTool(),
            "analyze_risk": _DummyTool(),
            "analyze_trend": _DummyTool(),
            "statistical_summary": _DummyTool(),
        }


class _DummySelector:
    def select_tools(self, **kwargs):
        return [SimpleNamespace(tool_name="severity_rate_by", confidence=0.9, reason="risk-first")]

    def record_execution(self, **kwargs):
        return None


class TaskPlannerRegressionTests(unittest.TestCase):
    def test_semantic_coverage_short_circuit(self):
        planner = TaskPlanner(_DummyExecutor())
        context = {
            "intents": ["general"],
            "entities": {},
            "primary_dataset": "defects",
            "dashboard_type": "defect_explore",
            "datasets": {"defects": {"available_columns": ["severity"]}},
        }

        steps = planner.plan("请给我语义覆盖率报告", context)

        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["tool"], "semantic_coverage_report")

    def test_sql_intent_prefers_profile_then_query(self):
        planner = TaskPlanner(_DummyExecutor())
        context = {
            "intents": ["sql"],
            "entities": {},
            "primary_dataset": "defects",
            "dashboard_type": "defect_explore",
            "datasets": {"defects": {"available_columns": ["severity"]}},
        }

        steps = planner.plan("请用 SQL 查询高风险缺陷", context)

        self.assertGreaterEqual(len(steps), 2)
        self.assertEqual(steps[0]["tool"], "get_db_profile")
        self.assertEqual(steps[1]["tool"], "query_sqlite_with_fix")

    def test_case_ranking_uses_groupby_aggregate_when_case_column_exists(self):
        planner = TaskPlanner(_DummyExecutor())
        context = {
            "intents": ["test", "case"],
            "entities": {},
            "primary_dataset": "tests",
            "datasets": {
                "tests": {
                    "available_columns": ["test_case", "run_status", "project"],
                }
            },
        }

        steps = planner.plan("哪些 test case 失败率最高 top 5", context)

        self.assertGreaterEqual(len(steps), 1)
        self.assertEqual(steps[0]["tool"], "groupby_aggregate")
        self.assertEqual(steps[0]["params"]["group_by"], "test_case")

    def test_selector_removed_steps_stay_in_plan_order(self):
        """SmartToolSelector was removed — steps now keep their original plan order."""
        context = {
            "intents": ["trend", "risk"],
            "entities": {},
            "primary_dataset": "defects",
            "datasets": {
                "defects": {
                    "available_columns": ["severity", "project", "creation_time"],
                    "tool_size": 120,
                }
            },
        }
        planner = TaskPlanner(_DummyExecutor(), tool_selector=_DummySelector())

        steps = planner.plan("请给我风险趋势", context)

        self.assertGreaterEqual(len(steps), 2)
        # Without SmartToolSelector, trend comes before risk (plan order)
        self.assertEqual(steps[0]["tool"], "analyze_trend")
        self.assertFalse(context.get("smart_tool_selector", {}).get("applied", False))


if __name__ == "__main__":
    unittest.main()
