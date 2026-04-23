import unittest
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

import agent.core.enhanced_ai_chat_manager as enhanced_chat_module
from agent.core.conversation_orchestrator import ConversationOrchestrator
from agent.core.enhanced_ai_chat_manager import EnhancedAIChatManager
from agent.core.harness_router import HarnessRouteDecision, HarnessRouteHandler
from agent.core.proactive_insight_models import (
    InsightCard,
    InsightEvidence,
    ProactiveInsightRequest,
)
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

    def test_process_with_agent_uses_proactive_insight_path_when_router_matches(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager.proactive_insight_router = Mock()
        manager.proactive_insight_engine = Mock()
        manager.proactive_insight_reporter = Mock()
        manager.intelligent_agent = Mock()

        request = ProactiveInsightRequest(mode='proactive_insight', dataset_scope='defect_test')
        cards = [
            InsightCard(
                type='divergence',
                title='Defect/Test imbalance detected',
                summary='Defect volume is materially higher than test activity in the current slice.',
                scope={'project': 'MGU'},
                confidence=0.75,
                severity='high',
                evidence=[InsightEvidence(label='defect_count', value=3)],
                metrics={'defect_count': 3},
            )
        ]
        manager.proactive_insight_router.match.return_value = (True, request)
        manager.proactive_insight_engine.generate.return_value = cards
        manager.proactive_insight_reporter.render.return_value = '主动洞察报告'

        result = manager.process_with_agent(
            '请做主动洞察',
            data={'defects': pd.DataFrame(), 'tests': pd.DataFrame()},
            conversation_history=[],
            extra_context={'mode': 'proactive_insight'},
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['text'], '主动洞察报告')
        self.assertEqual(result['context']['proactive_insight_request']['dataset_scope'], 'defect_test')
        self.assertEqual(result['context']['proactive_insight_cards'][0]['type'], 'divergence')
        self.assertEqual(result['context']['mode'], 'proactive_insight')
        self.assertEqual(result['context']['page_context']['dashboard_type'], 'defect')
        manager.intelligent_agent.process.assert_not_called()

    def test_process_with_agent_allows_proactive_insight_without_intelligent_agent(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = False
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager.proactive_insight_router = Mock()
        manager.proactive_insight_engine = Mock()
        manager.proactive_insight_reporter = Mock()
        manager.intelligent_agent = None

        request = ProactiveInsightRequest(mode='proactive_insight', dataset_scope='defect_test')
        cards = [
            InsightCard(
                type='divergence',
                title='Defect/Test imbalance detected',
                summary='Defect volume is materially higher than test activity in the current slice.',
                scope={'project': 'MGU'},
                confidence=0.75,
                severity='high',
                evidence=[InsightEvidence(label='defect_count', value=3)],
                metrics={'defect_count': 3},
            )
        ]
        manager.proactive_insight_router.match.return_value = (True, request)
        manager.proactive_insight_engine.generate.return_value = cards
        manager.proactive_insight_reporter.render.return_value = '主动洞察报告'

        result = manager.process_with_agent(
            '请做主动洞察',
            data={'defects': pd.DataFrame(), 'tests': pd.DataFrame()},
            conversation_history=[],
            extra_context={'mode': 'proactive_insight'},
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['text'], '主动洞察报告')
        self.assertEqual(result['context']['proactive_insight_cards'][0]['type'], 'divergence')

    def test_process_with_agent_falls_back_on_proactive_runtime_failure(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect'
        manager.use_agent = True
        manager.entity_tracker = None
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager.proactive_insight_router = Mock(side_effect=RuntimeError('boom'))
        manager.proactive_insight_engine = Mock()
        manager.proactive_insight_reporter = Mock()
        manager.intelligent_agent = Mock()

        result = manager.process_with_agent(
            '请做主动洞察',
            data={'defects': pd.DataFrame(), 'tests': pd.DataFrame()},
            conversation_history=[],
            extra_context={'mode': 'proactive_insight'},
        )

        self.assertTrue(result['success'])
        self.assertTrue(result['context']['proactive_insight_mode'])
        self.assertIn('无法完成分析', result['text'])

    def test_callback_preset_button_normalizes_proactive_mode_into_agent_request(self):
        manager = self._build_callback_test_manager()
        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]

        with patch.object(
            enhanced_chat_module,
            'callback_context',
            SimpleNamespace(triggered=[{'prop_id': 'defect-chat-proactive_insight-btn.n_clicks'}]),
        ), patch.object(enhanced_chat_module, 'resolve_harness_route', return_value=make_skill_agent_route()), patch.object(
            enhanced_chat_module,
            'should_load_local_data',
            return_value=False,
        ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
            enhanced_chat_module.time,
            'sleep',
            lambda _seconds: None,
        ):
            callback_fn(*self._callback_args_for_preset(manager, 'proactive_insight'))

        build_kwargs = manager._build_agent_request.call_args.kwargs
        self.assertEqual(build_kwargs['question'], '请做主动洞察')
        self.assertEqual(build_kwargs['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(build_kwargs['extra_context']['entry_point'], 'proactive_insight_button')

        process_kwargs = manager.process_with_agent.call_args.kwargs
        self.assertEqual(process_kwargs['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(process_kwargs['extra_context']['entry_point'], 'proactive_insight_button')
        self.assertEqual(process_kwargs['agent_request']['question'], '请做主动洞察')

    def test_callback_slash_command_normalizes_proactive_mode_into_agent_request(self):
        manager = self._build_callback_test_manager()
        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]

        with patch.object(
            enhanced_chat_module,
            'callback_context',
            SimpleNamespace(triggered=[{'prop_id': 'defect-chat-send-button.n_clicks'}]),
        ), patch.object(enhanced_chat_module, 'resolve_harness_route', return_value=make_skill_agent_route()), patch.object(
            enhanced_chat_module,
            'should_load_local_data',
            return_value=False,
        ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
            enhanced_chat_module.time,
            'sleep',
            lambda _seconds: None,
        ):
            callback_fn(*self._callback_args_for_send(manager, '/proactive-insight'))

        build_kwargs = manager._build_agent_request.call_args.kwargs
        self.assertEqual(build_kwargs['question'], '请做主动洞察')
        self.assertEqual(build_kwargs['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(build_kwargs['extra_context']['entry_point'], 'proactive_insight_slash')

        process_kwargs = manager.process_with_agent.call_args.kwargs
        self.assertEqual(process_kwargs['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(process_kwargs['extra_context']['entry_point'], 'proactive_insight_slash')
        self.assertEqual(process_kwargs['agent_request']['question'], '请做主动洞察')

    def test_callback_slash_command_promotes_default_summary_mode_to_agent_route(self):
        manager = self._build_callback_test_manager()
        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]
        captured_request = {}

        def capture_route(request, has_data):
            captured_request['selected_mode'] = request.selected_mode
            return make_skill_agent_route()

        with patch.object(
            enhanced_chat_module,
            'callback_context',
            SimpleNamespace(triggered=[{'prop_id': 'defect-chat-send-button.n_clicks'}]),
        ), patch.object(enhanced_chat_module, 'resolve_harness_route', side_effect=capture_route), patch.object(
            enhanced_chat_module,
            'should_load_local_data',
            return_value=False,
        ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
            enhanced_chat_module.time,
            'sleep',
            lambda _seconds: None,
        ):
            callback_fn(*self._callback_args_for_send(manager, '/proactive-insight', chat_mode='summary'))

        self.assertEqual(captured_request['selected_mode'], 'agent')

    def test_callback_normal_message_keeps_default_summary_mode(self):
        manager = self._build_callback_test_manager()
        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]
        captured_request = {}

        def capture_route(request, has_data):
            captured_request['selected_mode'] = request.selected_mode
            return make_skill_agent_route()

        with patch.object(
            enhanced_chat_module,
            'callback_context',
            SimpleNamespace(triggered=[{'prop_id': 'defect-chat-send-button.n_clicks'}]),
        ), patch.object(enhanced_chat_module, 'resolve_harness_route', side_effect=capture_route), patch.object(
            enhanced_chat_module,
            'should_load_local_data',
            return_value=False,
        ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
            enhanced_chat_module.time,
            'sleep',
            lambda _seconds: None,
        ):
            callback_fn(*self._callback_args_for_send(manager, 'show weekly defects', chat_mode='summary'))

        self.assertEqual(captured_request['selected_mode'], 'summary')

    def test_callback_database_summary_uses_full_schema_for_project_breakdown_sql(self):
        manager = self._build_callback_test_manager()
        manager.chatbot.chat_completion.return_value = '按项目汇总完成'

        captured = {'sql': ''}
        schema_columns = [
            {'name': f'col_{idx}'} for idx in range(24)
        ] + [
            {'name': 'team'},
            {'name': 'status_phase'},
            {'name': 'severity_group'},
            {'name': 'defect_id'},
            {'name': 'detected_by'},
            {'name': 'creation_time'},
            {'name': 'project'},
            {'name': 'tproject'},
        ]

        def execute_tool(name, _context, **kwargs):
            if name == 'get_sqlite_schema':
                return {
                    'success': True,
                    'result': {
                        'tables': {
                            'octane_defects': schema_columns,
                        }
                    },
                }
            if name == 'run_sqlite_query':
                captured['sql'] = str(kwargs.get('sql') or '')
                return {
                    'success': True,
                    'result': {
                        'sql': captured['sql'],
                        'rows': [
                            {'project': 'IDC', 'defect_count': 12, 'active_tester_count': 4},
                            {'project': 'IDCEVO', 'defect_count': 9, 'active_tester_count': 3},
                        ],
                    },
                }
            raise AssertionError(f'unexpected tool call: {name}')

        manager.intelligent_agent = SimpleNamespace(
            tool_executor=SimpleNamespace(execute_tool=Mock(side_effect=execute_tool))
        )

        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, 'summary.db')
            sqlite3.connect(db_path).close()

            with patch.object(
                enhanced_chat_module,
                'callback_context',
                SimpleNamespace(triggered=[{'prop_id': 'defect-chat-send-button.n_clicks'}]),
            ), patch.object(enhanced_chat_module, 'resolve_harness_route', return_value=make_database_summary_route()), patch.object(
                enhanced_chat_module,
                'should_load_local_data',
                return_value=False,
            ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
                enhanced_chat_module,
                'compute_total_count',
                return_value=2,
            ), patch.object(
                enhanced_chat_module.time,
                'sleep',
                lambda _seconds: None,
            ), patch.dict(
                os.environ,
                {
                    'AGENT_SQLITE_DB_PATH': db_path,
                    'CHAT_SUMMARY_SQL_MODE': 'deterministic',
                    'CHAT_SUMMARY_SCOPE_TEAM': 'DTSV_China',
                },
                clear=False,
            ):
                callback_fn(*self._callback_args_for_send(manager, '请对比分析各项目的缺陷与测试情况', chat_mode='summary'))

        self.assertIn("CAST(project AS TEXT)", captured['sql'])
        self.assertNotIn("CAST(team AS TEXT)), ''), '未标注') AS project", captured['sql'])

    def test_callback_database_summary_prefers_problem_finder_team_scope_for_defects(self):
        manager = self._build_callback_test_manager()
        manager.chatbot.chat_completion.return_value = '按项目汇总完成'

        captured = {'sql': ''}
        schema_columns = [
            {'name': 'team'},
            {'name': 'problem_finder_team'},
            {'name': 'project'},
            {'name': 'status_phase'},
            {'name': 'severity_group'},
            {'name': 'detected_by'},
        ]

        def execute_tool(name, _context, **kwargs):
            if name == 'get_sqlite_schema':
                return {
                    'success': True,
                    'result': {
                        'tables': {
                            'octane_defects': schema_columns,
                        }
                    },
                }
            if name == 'run_sqlite_query':
                captured['sql'] = str(kwargs.get('sql') or '')
                return {
                    'success': True,
                    'result': {
                        'sql': captured['sql'],
                        'rows': [
                            {'project': 'IDC', 'defect_count': 12, 'active_tester_count': 4},
                            {'project': 'IDCEVO', 'defect_count': 9, 'active_tester_count': 3},
                        ],
                    },
                }
            raise AssertionError(f'unexpected tool call: {name}')

        manager.intelligent_agent = SimpleNamespace(
            tool_executor=SimpleNamespace(execute_tool=Mock(side_effect=execute_tool))
        )

        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, 'summary.db')
            sqlite3.connect(db_path).close()

            with patch.object(
                enhanced_chat_module,
                'callback_context',
                SimpleNamespace(triggered=[{'prop_id': 'defect-chat-send-button.n_clicks'}]),
            ), patch.object(enhanced_chat_module, 'resolve_harness_route', return_value=make_database_summary_route()), patch.object(
                enhanced_chat_module,
                'should_load_local_data',
                return_value=False,
            ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
                enhanced_chat_module,
                'compute_total_count',
                return_value=2,
            ), patch.object(
                enhanced_chat_module.time,
                'sleep',
                lambda _seconds: None,
            ), patch.dict(
                os.environ,
                {
                    'AGENT_SQLITE_DB_PATH': db_path,
                    'CHAT_SUMMARY_SQL_MODE': 'deterministic',
                    'CHAT_SUMMARY_SCOPE_TEAM': 'DTSV_China',
                },
                clear=False,
            ):
                callback_fn(*self._callback_args_for_send(manager, '请对比分析各项目的缺陷与测试情况', chat_mode='summary'))

        self.assertIn("CAST(problem_finder_team AS TEXT)", captured['sql'])
        self.assertNotIn("LOWER(TRIM(CAST(team AS TEXT))) = LOWER('DTSV_China')", captured['sql'])

    def test_callback_database_summary_does_not_inject_default_scope_team_without_env(self):
        manager = self._build_callback_test_manager()
        manager.chatbot.chat_completion.return_value = '按项目汇总完成'

        captured = {'sql': ''}
        schema_columns = [
            {'name': 'team'},
            {'name': 'problem_finder_team'},
            {'name': 'project'},
            {'name': 'status_phase'},
            {'name': 'severity_group'},
            {'name': 'detected_by'},
        ]

        def execute_tool(name, _context, **kwargs):
            if name == 'get_sqlite_schema':
                return {
                    'success': True,
                    'result': {
                        'tables': {
                            'octane_defects': schema_columns,
                        }
                    },
                }
            if name == 'run_sqlite_query':
                captured['sql'] = str(kwargs.get('sql') or '')
                return {
                    'success': True,
                    'result': {
                        'sql': captured['sql'],
                        'rows': [
                            {'project': 'IDC', 'defect_count': 12, 'active_tester_count': 4},
                            {'project': 'IDCEVO', 'defect_count': 9, 'active_tester_count': 3},
                        ],
                    },
                }
            raise AssertionError(f'unexpected tool call: {name}')

        manager.intelligent_agent = SimpleNamespace(
            tool_executor=SimpleNamespace(execute_tool=Mock(side_effect=execute_tool))
        )

        app = FakeDashApp()
        manager.register_enhanced_callbacks(app, chat_id_prefix='defect-chat', data_store_id='defect-data')
        callback_fn = app.callbacks[0]

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, 'summary.db')
            sqlite3.connect(db_path).close()

            with patch.object(
                enhanced_chat_module,
                'callback_context',
                SimpleNamespace(triggered=[{'prop_id': 'defect-chat-send-button.n_clicks'}]),
            ), patch.object(enhanced_chat_module, 'resolve_harness_route', return_value=make_database_summary_route()), patch.object(
                enhanced_chat_module,
                'should_load_local_data',
                return_value=False,
            ), patch.object(enhanced_chat_module.threading, 'Thread', InlineThread), patch.object(
                enhanced_chat_module,
                'compute_total_count',
                return_value=2,
            ), patch.object(
                enhanced_chat_module.time,
                'sleep',
                lambda _seconds: None,
            ), patch.dict(
                os.environ,
                {
                    'AGENT_SQLITE_DB_PATH': db_path,
                    'CHAT_SUMMARY_SQL_MODE': 'deterministic',
                    'CHAT_SUMMARY_SCOPE_TEAM': '',
                    'OCTANE_TEAM': '',
                },
                clear=False,
            ):
                callback_fn(*self._callback_args_for_send(manager, '请对比分析各项目的缺陷与测试情况', chat_mode='summary'))

        self.assertNotIn('CAST(problem_finder_team AS TEXT)', captured['sql'])
        self.assertNotIn("LOWER(TRIM(CAST(team AS TEXT))) = LOWER('DTSV_China')", captured['sql'])

    def _build_callback_test_manager(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect_explore'
        manager.use_agent = True
        manager.assistant_name = 'Test Assistant'
        manager._conversation_orchestrator = ConversationOrchestrator()
        manager.preset_questions = EnhancedAIChatManager._build_default_presets(manager)
        manager.chatbot = Mock()
        manager.chatbot.chat_completion = Mock(return_value='ok')
        manager.process_with_agent = Mock(
            return_value={
                'success': True,
                'text': '主动洞察报告',
                'insights': [],
                'tools_used': [],
                'conversation_state': {},
                'context': {},
                'resolved_question': None,
            }
        )
        manager._format_agent_message = Mock(side_effect=lambda text, *_args: text)
        manager._build_route_reasoning = Mock(return_value='route reasoning')
        manager._build_agent_request = Mock(side_effect=self._capture_agent_request)
        return manager

    def _capture_agent_request(self, question, current_data, conversation_state=None, extra_context=None):
        return {
            'question': question,
            'entry_point': (extra_context or {}).get('entry_point'),
            'page_context': {'dashboard_type': 'defect_explore'},
        }

    def _callback_args_for_preset(self, manager, preset_key, chat_mode='agent'):
        preset_values = [
            1 if key == preset_key else 0
            for key in manager.preset_questions[manager.dashboard_type].keys()
        ]
        return (0, 0, 0, *preset_values, '', [], {'active': False, 'task_id': None}, None, chat_mode, [], {}, {})

    def _callback_args_for_send(self, manager, input_value, chat_mode='agent'):
        preset_values = [0 for _key in manager.preset_questions[manager.dashboard_type].keys()]
        return (1, 0, 0, *preset_values, input_value, [], {'active': False, 'task_id': None}, None, chat_mode, [], {}, {})


class FakeDashApp:
    def __init__(self):
        self.callbacks = []

    def callback(self, *_args, **_kwargs):
        def decorator(func):
            self.callbacks.append(func)
            return func

        return decorator


class InlineThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        if callable(self.target) and getattr(self.target, '__name__', '') != 'heartbeat':
            self.target()


def make_skill_agent_route():
    return HarnessRouteDecision(
        requested_mode='agent',
        handler=HarnessRouteHandler.SKILL_AGENT,
        reason='test route',
        llm_mode='summary',
        advanced_query=False,
        known_issues_enabled=False,
        use_agent_enabled=True,
        has_data=False,
        should_try_local_data=False,
    )


def make_database_summary_route():
    return HarnessRouteDecision(
        requested_mode='summary',
        handler=HarnessRouteHandler.DATABASE_SUMMARY,
        reason='test route',
        llm_mode='summary',
        advanced_query=True,
        known_issues_enabled=False,
        use_agent_enabled=True,
        has_data=False,
        should_try_local_data=False,
    )


if __name__ == '__main__':
    unittest.main()