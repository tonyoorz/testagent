from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ProactiveInsightRequest:
    mode: str
    dataset_scope: str
    dimensions: List[str] = field(
        default_factory=lambda: ['project', 'aida', 'severity', 'week']
    )
    time_window: str = 'recent'
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InsightEvidence:
    label: str
    value: Any

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InsightCard:
    type: str
    title: str
    summary: str
    scope: Dict[str, Any]
    confidence: float
    severity: str
    evidence: List[InsightEvidence]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload['evidence'] = [item.to_dict() for item in self.evidence]
        return payload