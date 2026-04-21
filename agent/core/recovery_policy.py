from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason_code: str
    message: str = ''
    preserve_events: bool = True
    legacy_path: str = 'legacy_process_with_agent'


class RecoveryPolicy:
    def resolve(self, *, reason_code: str, error: Any = None) -> RecoveryDecision:
        if reason_code == 'blocked':
            return RecoveryDecision(
                action='fail',
                reason_code='blocked',
                message='request blocked by runtime policy',
                preserve_events=True,
                legacy_path='',
            )
        return RecoveryDecision(
            action='fallback',
            reason_code=str(reason_code or 'runtime_exception'),
            message=str(error or reason_code or 'runtime_exception'),
        )