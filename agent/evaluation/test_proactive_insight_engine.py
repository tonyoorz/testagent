import unittest

import pandas as pd

from agent.core.proactive_insight_engine import ProactiveInsightEngine
from agent.core.proactive_insight_models import ProactiveInsightRequest


class ProactiveInsightEngineTests(unittest.TestCase):
    def test_generates_divergence_card_for_defect_test_mismatch(self):
        engine = ProactiveInsightEngine()
        request = ProactiveInsightRequest(
            mode='proactive_insight', dataset_scope='defect_test'
        )
        defects = pd.DataFrame(
            [
                {'project': 'MGU', 'week': '2026-W10', 'id': 1},
                {'project': 'MGU', 'week': '2026-W10', 'id': 2},
                {'project': 'MGU', 'week': '2026-W10', 'id': 3},
            ]
        )
        tests = pd.DataFrame([
            {'project': 'MGU', 'week': '2026-W10', 'test_id': 1},
        ])

        cards = engine.generate(request=request, datasets={'defects': defects, 'tests': tests})

        self.assertTrue(any(card.type == 'divergence' for card in cards))

    def test_generates_hotspot_card_for_dominant_project(self):
        engine = ProactiveInsightEngine()
        request = ProactiveInsightRequest(
            mode='proactive_insight', dataset_scope='defect_test'
        )
        defects = pd.DataFrame(
            [
                {'project': 'MGU', 'week': '2026-W10', 'id': 1},
                {'project': 'MGU', 'week': '2026-W10', 'id': 2},
                {'project': 'BMS', 'week': '2026-W10', 'id': 3},
            ]
        )

        cards = engine.generate(
            request=request,
            datasets={'defects': defects, 'tests': pd.DataFrame()},
        )

        self.assertTrue(any(card.type == 'hotspot' for card in cards))

    def test_generates_anomaly_card_for_weekly_spike(self):
        engine = ProactiveInsightEngine()
        request = ProactiveInsightRequest(
            mode='proactive_insight', dataset_scope='defect_test'
        )
        defects = pd.DataFrame(
            [
                {'project': 'MGU', 'week': '2026-W09', 'id': 1},
                {'project': 'MGU', 'week': '2026-W10', 'id': 2},
                {'project': 'MGU', 'week': '2026-W10', 'id': 3},
                {'project': 'MGU', 'week': '2026-W10', 'id': 4},
                {'project': 'MGU', 'week': '2026-W10', 'id': 5},
                {'project': 'MGU', 'week': '2026-W11', 'id': 6},
            ]
        )

        cards = engine.generate(
            request=request,
            datasets={'defects': defects, 'tests': pd.DataFrame()},
        )

        self.assertTrue(any(card.type == 'anomaly' for card in cards))

    def test_generates_turning_point_card_for_weekly_reversal(self):
        engine = ProactiveInsightEngine()
        request = ProactiveInsightRequest(
            mode='proactive_insight', dataset_scope='defect_test'
        )
        defects = pd.DataFrame(
            [
                {'project': 'MGU', 'week': '2026-W09', 'id': 1},
                {'project': 'MGU', 'week': '2026-W10', 'id': 2},
                {'project': 'MGU', 'week': '2026-W10', 'id': 3},
                {'project': 'MGU', 'week': '2026-W11', 'id': 4},
                {'project': 'MGU', 'week': '2026-W11', 'id': 5},
                {'project': 'MGU', 'week': '2026-W11', 'id': 6},
                {'project': 'MGU', 'week': '2026-W12', 'id': 7},
            ]
        )
        tests = pd.DataFrame(
            [
                {'project': 'MGU', 'week': '2026-W11', 'test_id': 1},
            ]
        )

        cards = engine.generate(
            request=request,
            datasets={'defects': defects, 'tests': tests},
        )

        self.assertTrue(any(card.type == 'turning_point' for card in cards))


if __name__ == '__main__':
    unittest.main()