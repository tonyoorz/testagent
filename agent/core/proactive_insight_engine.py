from __future__ import annotations

from typing import Any

import pandas as pd

from agent.core.proactive_insight_models import (
    InsightCard,
    InsightEvidence,
    ProactiveInsightRequest,
)


class ProactiveInsightEngine:
    def generate(
        self,
        *,
        request: ProactiveInsightRequest,
        datasets: dict[str, Any],
    ) -> list[InsightCard]:
        cards: list[InsightCard] = []
        defects = datasets.get('defects')
        tests = datasets.get('tests')

        if isinstance(defects, pd.DataFrame) and not defects.empty:
            cards.extend(self._build_hotspot_cards(defects, tests))
            anomaly_card = self._build_anomaly_card(defects)
            if anomaly_card is not None:
                cards.append(anomaly_card)
            turning_point_card = self._build_turning_point_card(defects, tests)
            if turning_point_card is not None:
                cards.append(turning_point_card)

        if (
            isinstance(defects, pd.DataFrame)
            and not defects.empty
            and isinstance(tests, pd.DataFrame)
            and not tests.empty
        ):
            divergence_card = self._build_divergence_card(request, defects, tests)
            if divergence_card is not None:
                cards.append(divergence_card)

        return cards

    def _build_hotspot_cards(self, defects: pd.DataFrame, tests: Any) -> list[InsightCard]:
        if 'project' not in defects.columns:
            return []

        counts = defects['project'].astype(str).value_counts()
        if counts.empty:
            return []

        top_count = int(counts.iloc[0])
        total_count = int(counts.sum())
        if top_count < max(2, total_count / 2):
            return []

        project = str(counts.index[0])
        test_count = 0
        if isinstance(tests, pd.DataFrame) and not tests.empty and 'project' in tests.columns:
            test_count = int((tests['project'].astype(str) == project).sum())
        return [
            InsightCard(
                type='hotspot',
                title=f'{project} defect hotspot',
                summary=f'{project} defects dominate the current slice.',
                scope={'project': project},
                confidence=0.7,
                severity='medium',
                evidence=[
                    InsightEvidence(label='defect_count', value=top_count),
                    InsightEvidence(label='linked_test_count', value=test_count),
                ],
                metrics={'defect_count': top_count, 'linked_test_count': test_count},
            )
        ]

    def _build_anomaly_card(self, defects: pd.DataFrame) -> InsightCard | None:
        if 'week' not in defects.columns:
            return None

        weekly_counts = defects['week'].astype(str).value_counts()
        if len(weekly_counts) < 2:
            return None

        top_week = str(weekly_counts.index[0])
        top_count = int(weekly_counts.iloc[0])
        baseline = float(weekly_counts.iloc[1:].mean()) if len(weekly_counts) > 1 else 0.0
        if top_count < max(3, baseline * 2):
            return None

        return InsightCard(
            type='anomaly',
            title=f'Weekly defect spike in {top_week}',
            summary=f'Defect volume in {top_week} is materially above the recent weekly baseline.',
            scope={'week': top_week},
            confidence=0.72,
            severity='high',
            evidence=[
                InsightEvidence(label='week_defect_count', value=top_count),
                InsightEvidence(label='baseline_weekly_defects', value=round(baseline, 2)),
            ],
            metrics={
                'week_defect_count': top_count,
                'baseline_weekly_defects': round(baseline, 2),
            },
        )

    def _build_divergence_card(
        self,
        request: ProactiveInsightRequest,
        defects: pd.DataFrame,
        tests: pd.DataFrame,
    ) -> InsightCard | None:
        if 'project' not in defects.columns or 'project' not in tests.columns:
            return None

        defect_counts = defects['project'].astype(str).value_counts()
        test_counts = tests['project'].astype(str).value_counts()
        best_project = None
        best_defects = 0
        best_tests = 0
        for project, defect_count in defect_counts.items():
            test_count = int(test_counts.get(project, 0))
            if defect_count >= max(3, test_count * 2) and defect_count > best_defects:
                best_project = str(project)
                best_defects = int(defect_count)
                best_tests = test_count

        if best_project is None:
            return None

        return InsightCard(
            type='divergence',
            title='Defect/Test imbalance detected',
            summary='Defect volume is materially higher than test activity in the current slice.',
            scope={'dataset_scope': request.dataset_scope, 'project': best_project},
            confidence=0.75,
            severity='high',
            evidence=[
                InsightEvidence(label='project', value=best_project),
                InsightEvidence(label='defect_count', value=best_defects),
                InsightEvidence(label='test_count', value=best_tests),
            ],
            metrics={
                'defect_count': best_defects,
                'test_count': best_tests,
            },
        )

    def _build_turning_point_card(self, defects: pd.DataFrame, tests: Any) -> InsightCard | None:
        if 'week' not in defects.columns:
            return None

        weekly_defects = defects['week'].astype(str).value_counts().sort_index()
        if len(weekly_defects) < 3:
            return None

        counts = [int(value) for value in weekly_defects.tolist()]
        weeks = [str(value) for value in weekly_defects.index.tolist()]
        peak_index = max(range(1, len(counts) - 1), key=lambda index: counts[index])
        if not (counts[peak_index] > counts[peak_index - 1] and counts[peak_index] > counts[peak_index + 1]):
            return None

        linked_test_count = 0
        if isinstance(tests, pd.DataFrame) and not tests.empty and 'week' in tests.columns:
            linked_test_count = int((tests['week'].astype(str) == weeks[peak_index]).sum())

        return InsightCard(
            type='turning_point',
            title=f'Turning point around {weeks[peak_index]}',
            summary='Defect activity changed direction sharply around this week.',
            scope={'week': weeks[peak_index]},
            confidence=0.68,
            severity='medium',
            evidence=[
                InsightEvidence(label='previous_week_defects', value=counts[peak_index - 1]),
                InsightEvidence(label='current_week_defects', value=counts[peak_index]),
                InsightEvidence(label='next_week_defects', value=counts[peak_index + 1]),
                InsightEvidence(label='linked_test_count', value=linked_test_count),
            ],
            metrics={
                'previous_week_defects': counts[peak_index - 1],
                'current_week_defects': counts[peak_index],
                'next_week_defects': counts[peak_index + 1],
                'linked_test_count': linked_test_count,
            },
        )