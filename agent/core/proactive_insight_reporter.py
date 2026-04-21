from typing import Iterable

from agent.core.proactive_insight_models import InsightCard


class ProactiveInsightReporter:
    def render(self, cards: Iterable[InsightCard]) -> str:
        items = list(cards)
        lines = ['总览']
        if not items:
            lines.append('当前范围内未发现需要重点关注的主动洞察。')
            return '\n'.join(lines)

        lines.append(f'本次共生成 {len(items)} 条主动洞察。')
        section_specs = [
            ('关键热点与异常', {'hotspot', 'anomaly'}),
            ('缺陷-测试背离', {'divergence'}),
            ('值得关注的转折点', {'turning_point'}),
        ]
        for heading, included_types in section_specs:
            selected = [card for card in items if card.type in included_types]
            if not selected:
                continue
            lines.append(heading)
            for card in selected:
                scope_text = ', '.join(
                    f'{key}={value}' for key, value in (card.scope or {}).items()
                ) or 'scope=global'
                metrics_text = ', '.join(
                    f'{key}={value}' for key, value in (card.metrics or {}).items()
                )
                lines.append(f'- {card.title}: {card.summary} ({scope_text})')
                if metrics_text:
                    lines.append(f'  指标: {metrics_text}')
        lines.append('数据边界说明')
        lines.append(
            '该报告基于当前上下文中的 defect/test 数据切片，不代表完整历史全量结论。'
        )
        return '\n'.join(lines)