import unittest

import pandas as pd

from agent.core.tool_executor import ToolExecutorWithRetry


class _BaseTool:
    def __init__(self, name, parameters=None):
        self.name = name
        self.description = name
        self.parameters = parameters or {}

    def expects_datasets(self):
        return False


class _TrendEmptyThenSuccessTool(_BaseTool):
    def __init__(self):
        super().__init__(
            name="analyze_trend",
            parameters={"top_n": {"type": "integer", "default": 5}},
        )
        self.calls = 0

    def execute(self, data, **kwargs):
        self.calls += 1
        top_n = int(kwargs.get("top_n") or 0)
        if top_n < 50:
            return {"success": True, "result": {"rows": []}}
        return {"success": True, "result": {"rows": [{"metric": 1}]}}


class _AlwaysFailTrendTool(_BaseTool):
    def __init__(self):
        super().__init__(name="analyze_trend", parameters={"top_n": {"type": "integer", "default": 5}})
        self.calls = 0

    def execute(self, data, **kwargs):
        self.calls += 1
        return {"success": False, "error": "参数错误"}


class _StatSummaryTool(_BaseTool):
    def __init__(self):
        super().__init__(name="statistical_summary", parameters={"dataset": {"type": "string", "default": "defects"}})

    def execute(self, data, **kwargs):
        return {"success": True, "result": {"total_records": len(data)}}


class ToolExecutorRetryTests(unittest.TestCase):
    def test_empty_result_retries_with_relaxed_top_n(self):
        trend_tool = _TrendEmptyThenSuccessTool()
        summary_tool = _StatSummaryTool()

        executor = ToolExecutorWithRetry(
            max_retry=1,
            default_tool_factory=lambda llm, db_path: [trend_tool, summary_tool],
        )

        result = executor.execute_with_retry(
            "analyze_trend",
            pd.DataFrame({"value": [1, 2, 3]}),
            top_n=5,
        )

        self.assertTrue(result.get("success"))
        self.assertFalse(result.get("fallback", False))
        self.assertEqual(trend_tool.calls, 2)

    def test_failed_tool_falls_back_to_statistical_summary(self):
        trend_tool = _AlwaysFailTrendTool()
        summary_tool = _StatSummaryTool()

        executor = ToolExecutorWithRetry(
            max_retry=1,
            default_tool_factory=lambda llm, db_path: [trend_tool, summary_tool],
        )

        result = executor.execute_with_retry(
            "analyze_trend",
            pd.DataFrame({"value": [1, 2, 3]}),
            top_n=5,
        )

        self.assertTrue(result.get("success"))
        self.assertTrue(result.get("fallback"))
        self.assertEqual(result.get("tool"), "analyze_trend")
        self.assertGreaterEqual(trend_tool.calls, 2)


if __name__ == "__main__":
    unittest.main()
