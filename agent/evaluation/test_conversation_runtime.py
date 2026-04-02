import unittest

from agent.core.conversation_runtime import (
    init_analysis_trace,
    resolve_execution_mode,
    serialize_plan_trace,
)


class ConversationRuntimeTests(unittest.TestCase):
    def test_invalid_mode_defaults_to_agentic(self):
        mode = resolve_execution_mode(
            requested_mode="unknown-mode",
            agentic_enabled=True,
            internal_template_route=False,
        )
        self.assertEqual(mode, "agentic")

    def test_internal_template_forces_hybrid_when_agentic_requested(self):
        mode = resolve_execution_mode(
            requested_mode="agentic",
            agentic_enabled=True,
            internal_template_route=True,
        )
        self.assertEqual(mode, "hybrid")

    def test_agentic_disabled_falls_back_to_rule(self):
        mode = resolve_execution_mode(
            requested_mode="agentic",
            agentic_enabled=False,
            internal_template_route=False,
        )
        self.assertEqual(mode, "rule")

    def test_trace_contains_internal_route_marker(self):
        trace = init_analysis_trace(
            mode="hybrid",
            validation_enabled=True,
            internal_template_route=True,
        )
        self.assertEqual(trace["mode"], "hybrid")
        self.assertEqual(trace["plan"], [])
        self.assertEqual(trace["execution"], [])
        self.assertTrue(trace["validation_enabled"])
        self.assertEqual(trace["llm_route"], "internal_template")

    def test_serialize_plan_trace_normalizes_step_shape(self):
        plan = [
            {
                "step": "2",
                "tool": "analyze_trend",
                "description": "Analyze trend",
                "params": {"dataset": "defects"},
                "ignored": "x",
            },
            "invalid",
        ]

        serialized = serialize_plan_trace(plan)

        self.assertEqual(
            serialized,
            [
                {
                    "step": 2,
                    "tool": "analyze_trend",
                    "description": "Analyze trend",
                    "params": {"dataset": "defects"},
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
