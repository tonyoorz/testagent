import unittest
from unittest.mock import Mock

from agent.core.conversation_orchestrator import ConversationOrchestrator
from agent.core.enhanced_ai_chat_manager import EnhancedAIChatManager
from agent.core.session_manager import SessionManager


class EnhancedChatManagerSpineTests(unittest.TestCase):
    def test_initialize_stream_state_includes_runtime_metadata(self):
        orchestrator = ConversationOrchestrator()

        state = orchestrator.initialize_stream_state('starting')

        self.assertEqual(state['runtime_stage'], 'received')
        self.assertFalse(state['fallback_active'])
        self.assertFalse(state['confirmation_pending'])

    def test_orchestrator_runs_guardrails(self):
        orchestrator = ConversationOrchestrator()

        runtime = orchestrator.prepare_runtime(
            question='show weekly defects',
            dashboard_type='defect',
            current_data=None,
            conversation_state=None,
            extra_context=None,
            agent_results={},
            progress='starting',
        )

        self.assertEqual(runtime['guardrail_decision'].action, 'allow')
        self.assertEqual(runtime['stream_state']['runtime_stage'], 'guarded')

    def test_build_agent_request_records_session_context(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager.session_manager = SessionManager()

        request = manager._build_agent_request(
            question='show weekly defects',
            current_data=None,
            conversation_state={'selected_team': 'DTSV_China'},
            extra_context={'chat_id_prefix': 'defect-chat', 'page_filters': {'project': ['MGU']}},
        )

        session = manager.session_manager.get_or_create('defect-chat:defect', dashboard_type='defect')
        self.assertEqual(session.data_context.last_question, 'show weekly defects')
        self.assertEqual(session.data_context.page_filters, {'project': ['MGU']})
        self.assertEqual(request['session_id'], 'defect-chat:defect')

    def test_get_enhanced_system_prompt_prefers_prompt_registry(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = False
        manager.intelligent_agent = None
        manager.prompt_registry = Mock()
        manager.prompt_registry.render_dashboard_prompt.return_value = 'registry prompt'

        prompt = manager._get_enhanced_system_prompt('ctx')

        self.assertIn('registry prompt', prompt)
        manager.prompt_registry.render_dashboard_prompt.assert_called_once_with('defect', data_context='ctx')

    def test_build_agent_request_uses_conversation_orchestrator(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager.session_manager = None

        request = manager._build_agent_request(
            question='show weekly defects',
            current_data=None,
            conversation_state={'filters': {'year': 2025}},
            extra_context={'entry_point': 'test'},
        )

        self.assertEqual(request['question'], 'show weekly defects')
        self.assertEqual(request['page_context']['dashboard_type'], 'defect')
        self.assertEqual(request['page_context']['conversation_state']['filters']['year'], 2025)
        self.assertEqual(request['entry_point'], 'test')

    def test_process_with_agent_forwards_page_context_to_intelligent_agent(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()

        intelligent_agent = Mock()
        intelligent_agent.process.return_value = {
            'text': 'ok',
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {},
        }
        manager.intelligent_agent = intelligent_agent

        result = manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
            conversation_state={'selected_team': 'DTSV_China'},
            extra_context={'page_filters': {'project': ['MGU']}},
        )

        self.assertTrue(result['success'])
        forwarded_page_context = intelligent_agent.process.call_args.kwargs['page_context']
        self.assertEqual(forwarded_page_context['dashboard_type'], 'defect')
        self.assertEqual(forwarded_page_context['selected_team'], 'DTSV_China')
        self.assertEqual(forwarded_page_context['page_filters'], {'project': ['MGU']})

    def test_process_with_agent_forwards_standard_request_to_intelligent_agent(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()

        intelligent_agent = Mock()
        intelligent_agent.process.return_value = {
            'text': 'ok',
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {},
        }
        manager.intelligent_agent = intelligent_agent

        manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
            conversation_state={'selected_team': 'DTSV_China'},
            extra_context={'page_filters': {'project': ['MGU']}, 'entry_point': 'dash_chat'},
        )

        forwarded_request = intelligent_agent.process.call_args.kwargs['request']
        self.assertEqual(forwarded_request['question'], 'show weekly defects')
        self.assertEqual(forwarded_request['entry_point'], 'dash_chat')
        self.assertEqual(forwarded_request['page_context']['dashboard_type'], 'defect')

    def test_process_with_agent_reuses_supplied_request(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager._build_agent_request = Mock(side_effect=AssertionError('should not rebuild request'))

        intelligent_agent = Mock()
        intelligent_agent.process.return_value = {
            'text': 'ok',
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {},
        }
        manager.intelligent_agent = intelligent_agent

        supplied_request = {
            'question': 'prefetched question',
            'entry_point': 'stream_worker',
            'page_context': {
                'dashboard_type': 'defect',
                'selected_team': 'DTSV_China',
                'page_filters': {'project': ['MGU']},
            },
        }

        result = manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
            conversation_state={'selected_team': 'DTSV_China'},
            extra_context={'page_filters': {'project': ['MGU']}},
            agent_request=supplied_request,
        )

        self.assertTrue(result['success'])
        forwarded_request = intelligent_agent.process.call_args.kwargs['request']
        self.assertIs(forwarded_request, supplied_request)
        self.assertEqual(intelligent_agent.process.call_args.kwargs['page_context']['page_filters'], {'project': ['MGU']})

    def test_process_with_agent_updates_request_question_after_entity_resolution(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager._conversation_orchestrator = ConversationOrchestrator()

        class FakeTracker:
            def resolve_references(self, question, state):
                return 'resolved weekly defects'

        manager.entity_tracker = FakeTracker()

        intelligent_agent = Mock()
        intelligent_agent.process.return_value = {
            'text': 'ok',
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {},
        }
        manager.intelligent_agent = intelligent_agent

        manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
            conversation_state={},
            extra_context={'entry_point': 'dash_chat'},
        )

        forwarded_request = intelligent_agent.process.call_args.kwargs['request']
        self.assertEqual(forwarded_request['question'], 'resolved weekly defects')
        self.assertEqual(intelligent_agent.process.call_args.args[0], 'resolved weekly defects')

    def test_process_with_agent_falls_back_on_runtime_failure(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager._legacy_process_with_agent = Mock(return_value={'success': True, 'mode': 'legacy-fallback'})

        intelligent_agent = Mock()
        intelligent_agent.process.side_effect = RuntimeError('boom')
        manager.intelligent_agent = intelligent_agent

        result = manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['mode'], 'legacy-fallback')

    def test_process_with_agent_prefers_supplied_request_question(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()

        intelligent_agent = Mock()
        intelligent_agent.process.return_value = {
            'text': 'ok',
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {},
        }
        manager.intelligent_agent = intelligent_agent

        supplied_request = {
            'question': 'prefetched question',
            'entry_point': 'stream_worker',
            'page_context': {
                'dashboard_type': 'defect',
                'selected_team': 'DTSV_China',
                'page_filters': {'project': ['MGU']},
            },
        }

        manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
            conversation_state={'selected_team': 'DTSV_China'},
            agent_request=supplied_request,
        )

        self.assertEqual(intelligent_agent.process.call_args.args[0], 'prefetched question')
        self.assertEqual(intelligent_agent.process.call_args.kwargs['request']['question'], 'prefetched question')

    def test_process_with_agent_resolves_references_from_supplied_request_question(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager._conversation_orchestrator = ConversationOrchestrator()

        class FakeTracker:
            def resolve_references(self, question, state):
                if question == 'prefetched question':
                    return 'resolved prefetched question'
                return 'wrong source question'

            def update_state(self, state, resolved_question, intent=None, tools_used=None):
                return state

        manager.entity_tracker = FakeTracker()

        intelligent_agent = Mock()
        intelligent_agent.process.return_value = {
            'text': 'ok',
            'insights': [],
            'visualizations': [],
            'tools_used': [],
            'context': {},
        }
        manager.intelligent_agent = intelligent_agent

        supplied_request = {
            'question': 'prefetched question',
            'page_context': {
                'dashboard_type': 'defect',
                'selected_team': 'DTSV_China',
                'page_filters': {},
            },
        }

        manager.process_with_agent(
            'show weekly defects',
            data=None,
            conversation_history=[],
            conversation_state={},
            agent_request=supplied_request,
        )

        self.assertEqual(intelligent_agent.process.call_args.args[0], 'resolved prefetched question')
        self.assertEqual(intelligent_agent.process.call_args.kwargs['request']['question'], 'resolved prefetched question')


if __name__ == '__main__':
    unittest.main()