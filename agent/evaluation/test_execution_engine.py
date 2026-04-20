import unittest
from unittest.mock import Mock

from agent.core.execution_engine import UnifiedExecutionEngine


class UnifiedExecutionEngineTests(unittest.TestCase):
    def test_execute_agentic_returns_text_and_trace(self):
        tool_executor = Mock()
        tool_executor._llm = Mock()
        tool_executor._llm.client = object()
        tool_executor._llm.model = 'fake-model'
        tool_executor.get_tool_schema.return_value = {
            'analyze_trend': {
                'description': 'Analyze trend',
                'parameters': {},
                'json_schema': {'type': 'object', 'properties': {}, 'additionalProperties': True},
            }
        }
        tool_executor.execute_tool.return_value = {'success': True, 'result': {'rows': []}}

        engine = UnifiedExecutionEngine(tool_executor=tool_executor, task_planner=Mock())
        result = engine.execute_agentic(
            question='analyze trend',
            prepared_data=None,
            context={'data_summary': 'rows=3'},
            analysis_trace={'mode': 'agentic'},
            tool_call_max=1,
            max_iters=1,
            llm_client=Mock(),
            llm_model='fake-model',
            run_agentic_loop_fn=lambda **_: {
                'final_text': 'final answer',
                'execution_rows': [{'tool': 'analyze_trend', 'success': True}],
                'stop_reason': 'model_final_answer',
            },
        )

        self.assertEqual(result['text'], 'final answer')
        self.assertEqual(result['analysis_trace']['agentic_stop_reason'], 'model_final_answer')
        self.assertEqual(result['tools_used'], ['analyze_trend'])

    def test_execute_plan_flow_returns_execution_trace(self):
        planner = Mock()
        planner.plan.return_value = [{'step': 1, 'tool': 'analyze_trend', 'description': 'Analyze', 'params': {}}]
        planner.execute_plan.return_value = [{'tool': 'analyze_trend', 'description': 'Analyze', 'trace': {'tool': 'analyze_trend'}}]

        engine = UnifiedExecutionEngine(tool_executor=Mock(), task_planner=planner)
        result = engine.execute_plan_flow(
            question='analyze trend',
            prepared_data=None,
            context={},
            analysis_trace={'mode': 'rule'},
            pending_confirmation=None,
            confirmed_now=False,
            progress_cb=None,
            should_require_confirmation=lambda plan, context: False,
            build_confirmation_payload=lambda question, plan, context, analysis_trace: {'text': 'confirm'},
        )

        self.assertIn('execution_results', result)
        self.assertEqual(result['analysis_trace']['plan'][0]['tool'], 'analyze_trend')
        self.assertEqual(result['analysis_trace']['execution'][0]['tool'], 'analyze_trend')


if __name__ == '__main__':
    unittest.main()