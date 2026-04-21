import unittest

from agent.core.recovery_policy import RecoveryPolicy


class RecoveryPolicyTests(unittest.TestCase):
    def test_fallbacks_on_runtime_error(self):
        policy = RecoveryPolicy()

        decision = policy.resolve(reason_code='runtime_exception', error=RuntimeError('boom'))

        self.assertEqual(decision.action, 'fallback')
        self.assertEqual(decision.reason_code, 'runtime_exception')

    def test_fails_when_blocked(self):
        policy = RecoveryPolicy()

        decision = policy.resolve(reason_code='blocked', error=None)

        self.assertEqual(decision.action, 'fail')
        self.assertEqual(decision.reason_code, 'blocked')


if __name__ == '__main__':
    unittest.main()