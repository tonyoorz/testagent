import unittest

from agent.core.proactive_insight_models import InsightCard, InsightEvidence
from agent.core.proactive_insight_reporter import ProactiveInsightReporter


class ProactiveInsightReporterTests(unittest.TestCase):
    def test_builds_complete_report_from_cards(self):
        reporter = ProactiveInsightReporter()
        cards = [
            InsightCard(
                type='divergence',
                title='Defect/Test imbalance detected',
                summary='Defect volume is materially higher than test activity in the current slice.',
                scope={'project': 'MGU'},
                confidence=0.75,
                severity='high',
                evidence=[
                    InsightEvidence(label='defect_count', value=3),
                    InsightEvidence(label='test_count', value=1),
                ],
                metrics={'defect_count': 3, 'test_count': 1},
            )
        ]

        report = reporter.render(cards)

        self.assertIn('总览', report)
        self.assertIn('缺陷-测试背离', report)
        self.assertIn('数据边界说明', report)
        self.assertIn('defect_count=3', report)
        self.assertIn('Defect/Test imbalance detected', report)
        self.assertIn('MGU', report)


if __name__ == '__main__':
    unittest.main()