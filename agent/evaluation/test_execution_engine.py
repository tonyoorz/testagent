import unittest
from unittest.mock import Mock

from agent.core.execution_engine import UnifiedExecutionEngine


class UnifiedExecutionEngineTests(unittest.TestCase):
    def test_resolve_analysis_inputs_applies_semantic_adapter_and_intent_analysis(self):
        context_manager = Mock()
        context_manager.analyze_intent_with_confidence.return_value = (['trend'], 0.91, None)

        engine = UnifiedExecutionEngine(tool_executor=Mock(), task_planner=Mock())
        result = engine.resolve_analysis_inputs(
            question='show weekly defects',
            conversation_history=[],
            context_manager=context_manager,
            db_path='dummy.db',
            semantic_adapter_enabled=True,
            semantic_adapter_fn=lambda **_: {
                'normalized_question': 'normalized weekly defects',
                'semantic_hints': {'project': ['MGU']},
            },
        )

        self.assertEqual(result['analysis_question'], 'normalized weekly defects')
        self.assertEqual(result['semantic_term_hints'], {'project': ['MGU']})
        self.assertEqual(result['early_intents'], ['trend'])
        self.assertEqual(result['early_confidence'], 0.91)

    def test_gather_supporting_context_collects_history_and_knowledge(self):
        memory = Mock()
        memory.get_relevant_history.return_value = ['history-row']
        knowledge_base = Mock()
        knowledge_base.get_knowledge_context.return_value = 'knowledge-row'

        engine = UnifiedExecutionEngine(tool_executor=Mock(), task_planner=Mock())
        result = engine.gather_supporting_context(
            question='show weekly defects',
            analysis_question='normalized weekly defects',
            context={},
            memory=memory,
            knowledge_base=knowledge_base,
            memory_debug_enabled=False,
        )

        self.assertEqual(result['relevant_history'], ['history-row'])
        self.assertEqual(result['knowledge_context'], 'knowledge-row')

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

    def test_finalize_answer_records_memory_and_normalizes_payload(self):
        engine = UnifiedExecutionEngine(tool_executor=Mock(), task_planner=Mock())
        memory_writer = Mock()

        result = engine.finalize_answer(
            question='analyze trend',
            context={'analysis_trace': {'mode': 'rule'}},
            execution_results=[{'tool': 'analyze_trend', 'result': {'success': True}}],
            knowledge_context='knowledge',
            relevant_history=['history'],
            start_time_seconds=10.0,
            current_time_seconds=15.5,
            generate_answer_fn=lambda **_: {'text': 'final answer', 'context': {}},
            memory_add_message_fn=memory_writer,
            normalize_response_fn=lambda answer, execution_results: {
                'answer': answer,
                'execution_results': execution_results,
            },
        )

        memory_writer.assert_called_once()
        self.assertEqual(memory_writer.call_args.args[0], 'assistant')
        self.assertEqual(memory_writer.call_args.args[1], 'final answer')
        self.assertEqual(result['answer']['text'], 'final answer')
        self.assertEqual(result['answer']['context']['analysis_trace']['mode'], 'rule')


if __name__ == '__main__':
    unittest.main()