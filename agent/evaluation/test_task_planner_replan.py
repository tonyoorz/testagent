import os
import unittest
from unittest.mock import patch

import pandas as pd

from agent.core.task_planner import TaskPlanner


class _ToolStub:
    def __init__(self, expects_datasets=False):
        self._expects_datasets = expects_datasets

    def expects_datasets(self):
        return self._expects_datasets


class _ReplanExecutor:
    def __init__(self):
        self.tools = {
            "broken_tool": _ToolStub(),
            "empty_tool": _ToolStub(),
            "describe_dataset": _ToolStub(),
            "statistical_summary": _ToolStub(),
        }

    def execute_tool(self, tool_name, data, **kwargs):
        if tool_name == "broken_tool":
            return {"success": False, "error": "列 foo 不存在"}
        if tool_name == "empty_tool":
            return {"success": True, "result": {"rows": []}}
        if tool_name == "describe_dataset":
            return {"success": True, "result": {"columns": ["a", "b"]}}
        if tool_name == "statistical_summary":
            return {"success": True, "result": {"total_records": 3}}
        return {"success": False, "error": f"unexpected tool: {tool_name}"}


class TaskPlannerReplanTests(unittest.TestCase):
    def test_schema_failure_triggers_describe_then_summary_replan(self):
        planner = TaskPlanner(_ReplanExecutor())
        data = {"defects": pd.DataFrame({"a": [1, 2, 3]})}
        context = {"primary_dataset": "defects", "datasets": {"defects": {}}}
        steps = [
            {
                "step": 1,
                "tool": "broken_tool",
                "description": "trigger schema failure",
                "params": {"dataset": "defects"},
            }
        ]

        with patch.dict(os.environ, {"AGENT_REPLAN_ENABLED": "1", "AGENT_MAX_REPLANS": "1"}):
            result = planner.execute_plan(steps, data, context=context)

        tools = [item.get("tool") for item in result]
        self.assertEqual(tools, ["broken_tool", "describe_dataset", "statistical_summary"])

    def test_empty_success_triggers_summary_replan(self):
        planner = TaskPlanner(_ReplanExecutor())
        data = {"defects": pd.DataFrame({"a": [1, 2, 3]})}
        context = {"primary_dataset": "defects", "datasets": {"defects": {}}}
        steps = [
            {
                "step": 1,
                "tool": "empty_tool",
                "description": "trigger empty result",
                "params": {"dataset": "defects"},
            }
        ]

        with patch.dict(os.environ, {"AGENT_REPLAN_ENABLED": "1", "AGENT_MAX_REPLANS": "1"}):
            result = planner.execute_plan(steps, data, context=context)

        tools = [item.get("tool") for item in result]
        self.assertEqual(tools, ["empty_tool", "statistical_summary"])


if __name__ == "__main__":
    unittest.main()
