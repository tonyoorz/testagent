import json
import unittest
from types import SimpleNamespace

from agent.core.agentic_runtime import build_tool_specs, run_agentic_loop


def _tool_call(name, args):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def _response(content="", tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


class _FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("No more fake responses")
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.completions = _FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=self.completions)


class AgenticRuntimeTests(unittest.TestCase):
    def test_build_tool_specs_converts_parameter_schema(self):
        tool_specs = build_tool_specs(
            {
                "analyze_trend": {
                    "description": "Analyze trend",
                    "parameters": {
                        "top_n": {"type": "integer", "description": "Top N"},
                        "dimension": {"type": "string", "enum": ["week", "month"]},
                    },
                }
            }
        )

        self.assertEqual(len(tool_specs), 1)
        function_spec = tool_specs[0]["function"]
        self.assertEqual(function_spec["name"], "analyze_trend")
        self.assertEqual(function_spec["parameters"]["properties"]["top_n"]["type"], "integer")
        self.assertEqual(function_spec["parameters"]["properties"]["dimension"]["enum"], ["week", "month"])

    def test_run_agentic_loop_executes_tool_then_returns_final_answer(self):
        responses = [
            _response(
                content="",
                tool_calls=[_tool_call("analyze_trend", {"top_n": 5, "dataset": "defects"})],
            ),
            _response(content="最终结论"),
        ]
        client = _FakeClient(responses)

        executed = []

        def _execute_tool(name, args):
            executed.append((name, args))
            return {"success": True, "result": {"rows": [{"metric": 1}]}}

        result = run_agentic_loop(
            llm_client=client,
            llm_model="fake-model",
            tool_specs=build_tool_specs({"analyze_trend": {"parameters": {}}}),
            question="请分析趋势",
            data_summary="rows=10",
            execute_tool=_execute_tool,
            tool_call_max=3,
            max_iters=3,
        )

        self.assertEqual(result["stop_reason"], "model_final_answer")
        self.assertEqual(result["final_text"], "最终结论")
        self.assertEqual(len(result["execution_rows"]), 1)
        self.assertTrue(result["execution_rows"][0]["success"])
        self.assertEqual(executed[0][0], "analyze_trend")

    def test_run_agentic_loop_stops_when_tool_budget_exhausted(self):
        responses = [_response(content="", tool_calls=[_tool_call("analyze_trend", {"top_n": 5})])]
        client = _FakeClient(responses)

        def _execute_tool(name, args):
            return {"success": True, "result": {"rows": [{"metric": 1}]}}

        result = run_agentic_loop(
            llm_client=client,
            llm_model="fake-model",
            tool_specs=build_tool_specs({"analyze_trend": {"parameters": {}}}),
            question="请分析趋势",
            data_summary="",
            execute_tool=_execute_tool,
            tool_call_max=0,
            max_iters=2,
        )

        self.assertEqual(result["stop_reason"], "tool_budget_exhausted")
        self.assertEqual(len(result["execution_rows"]), 1)
        self.assertFalse(result["execution_rows"][0]["success"])
        self.assertIn("预算", str(result["execution_rows"][0].get("error") or ""))


if __name__ == "__main__":
    unittest.main()