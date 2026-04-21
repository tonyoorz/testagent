import unittest

from agent.core.proactive_insight_router import ProactiveInsightRouter


class ProactiveInsightRouterTests(unittest.TestCase):
    def test_matches_explicit_entrypoint_flag(self):
        router = ProactiveInsightRouter()

        matched, request = router.match(
            question='请做主动洞察',
            extra_context={'mode': 'proactive_insight'},
        )

        self.assertTrue(matched)
        self.assertEqual(request.mode, 'proactive_insight')
        self.assertEqual(request.dataset_scope, 'defect_test')

    def test_ignores_standard_questions(self):
        router = ProactiveInsightRouter()

        matched, request = router.match(
            question='show weekly defects',
            extra_context={},
        )

        self.assertFalse(matched)
        self.assertIsNone(request)

    def test_rejects_missing_scope_with_explicit_command(self):
        router = ProactiveInsightRouter()

        with self.assertRaises(ValueError):
            router.parse(
                question='/proactive-insight',
                extra_context={'mode': 'proactive_insight', 'dataset_scope': ''},
            )

    def test_rejects_non_list_dimensions(self):
        router = ProactiveInsightRouter()

        with self.assertRaises(ValueError):
            router.parse(
                question='/proactive-insight',
                extra_context={'mode': 'proactive_insight', 'dimensions': 'project'},
            )


if __name__ == '__main__':
    unittest.main()