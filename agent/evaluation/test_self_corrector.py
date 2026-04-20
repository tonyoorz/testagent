import unittest

from agent.core.self_corrector import SelfCorrector


class SelfCorrectorTests(unittest.TestCase):
    def test_fix_params_removes_invalid_parameters(self):
        corrector = SelfCorrector()

        fixed = corrector.fix_params(
            {'group_by': 'project', 'invalid': 'x', 'dataset': 'defects'},
            analysis='invalid_parameters',
            valid_params={'group_by', 'dataset'},
        )

        self.assertEqual(fixed, {'group_by': 'project', 'dataset': 'defects'})

    def test_fix_params_expands_empty_result_limits(self):
        corrector = SelfCorrector()

        fixed = corrector.fix_params(
            {'top_n': 5, 'severity': 'Critical'},
            analysis='empty_result',
        )

        self.assertEqual(fixed['top_n'], 50)
        self.assertNotIn('severity', fixed)


if __name__ == '__main__':
    unittest.main()