import unittest

from agent.core.intelligent_agent import IntelligentAgent


class IntelligentAgentRequestSpineTests(unittest.TestCase):
    def test_resolve_request_inputs_prefers_request_question(self):
        agent = IntelligentAgent.__new__(IntelligentAgent)

        effective_question, effective_page_context, request_payload = agent._resolve_request_inputs(
            question='fallback question',
            page_context=None,
            request={
                'question': 'prefetched question',
                'page_context': {'dashboard_type': 'defect'},
            },
        )

        self.assertEqual(effective_question, 'prefetched question')
        self.assertEqual(effective_page_context, {'dashboard_type': 'defect'})
        self.assertEqual(request_payload['question'], 'prefetched question')

    def test_resolve_request_inputs_syncs_request_page_context_with_explicit_value(self):
        agent = IntelligentAgent.__new__(IntelligentAgent)

        effective_question, effective_page_context, request_payload = agent._resolve_request_inputs(
            question='fallback question',
            page_context={'dashboard_type': 'risk', 'selected_team': 'DTSV_China'},
            request={
                'question': 'prefetched question',
                'page_context': {'dashboard_type': 'defect'},
            },
        )

        self.assertEqual(effective_question, 'prefetched question')
        self.assertEqual(effective_page_context['dashboard_type'], 'risk')
        self.assertEqual(request_payload['page_context']['dashboard_type'], 'risk')
        self.assertEqual(request_payload['page_context']['selected_team'], 'DTSV_China')


if __name__ == '__main__':
    unittest.main()