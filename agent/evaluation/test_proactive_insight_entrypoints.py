import unittest

from agent.core.enhanced_ai_chat_manager import EnhancedAIChatManager


class ProactiveInsightEntrypointTests(unittest.TestCase):
    def test_detects_slash_command_and_sets_mode(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='/proactive-insight',
            trigger_key=None,
            extra_context={'chat_id_prefix': 'defect-chat'},
        )

        self.assertEqual(normalized['question'], '请做主动洞察')
        self.assertEqual(normalized['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(normalized['extra_context']['entry_point'], 'proactive_insight_slash')

    def test_detects_preset_button_and_sets_mode(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='请做主动洞察',
            trigger_key='proactive_insight',
            extra_context={},
        )

        self.assertEqual(normalized['extra_context']['mode'], 'proactive_insight')
        self.assertEqual(normalized['extra_context']['entry_point'], 'proactive_insight_button')

    def test_leaves_normal_question_unchanged(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='show weekly defects',
            trigger_key=None,
            extra_context={'page_filters': {'project': ['MGU']}},
        )

        self.assertEqual(normalized['question'], 'show weekly defects')
        self.assertNotIn('mode', normalized['extra_context'])

    def test_does_not_match_slash_prefix_variants(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)

        normalized = manager._normalize_proactive_insight_entry(
            question='/proactive-insightful',
            trigger_key=None,
            extra_context={},
        )

        self.assertEqual(normalized['question'], '/proactive-insightful')
        self.assertNotIn('mode', normalized['extra_context'])

    def test_general_presets_include_proactive_insight(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'general'
        manager.preset_questions = EnhancedAIChatManager.__dict__['_build_default_presets'](manager)

        self.assertIn('proactive_insight', manager.preset_questions['general'])

    def test_defect_explore_presets_include_proactive_insight(self):
        manager = EnhancedAIChatManager.__new__(EnhancedAIChatManager)
        manager.dashboard_type = 'defect_explore'
        manager.preset_questions = EnhancedAIChatManager.__dict__['_build_default_presets'](manager)

        self.assertIn('proactive_insight', manager.preset_questions['defect_explore'])


if __name__ == '__main__':
    unittest.main()