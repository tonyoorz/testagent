import unittest

from agent.core.guardrails import GuardrailEngine


class GuardrailTests(unittest.TestCase):
    def test_allows_normal_request(self):
        engine = GuardrailEngine()

        decision = engine.evaluate(
            question='show weekly defects',
            request={'question': 'show weekly defects'},
            page_context={'dashboard_type': 'defect'},
            agent_results={},
        )

        self.assertEqual(decision.action, 'allow')
        self.assertEqual(decision.reason_code, 'allowed')

    def test_requires_confirmation_when_pending_confirmation_exists(self):
        engine = GuardrailEngine()

        decision = engine.evaluate(
            question='继续',
            request={'question': '继续'},
            page_context={'dashboard_type': 'defect'},
            agent_results={'last_agent_context': {'confirmation_pending': True}},
        )

        self.assertEqual(decision.action, 'confirm')
        self.assertEqual(decision.reason_code, 'confirmation_required')

    def test_falls_back_when_request_has_no_page_context(self):
        engine = GuardrailEngine()

        decision = engine.evaluate(
            question='show weekly defects',
            request={'question': 'show weekly defects'},
            page_context={},
            agent_results={},
        )

        self.assertEqual(decision.action, 'fallback')
        self.assertEqual(decision.reason_code, 'missing_page_context')


if __name__ == '__main__':
    unittest.main()