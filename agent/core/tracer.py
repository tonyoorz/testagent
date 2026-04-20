import time
from typing import Any, Dict, List


class AgentTracer:
    def __init__(self, enabled: bool = True):
        self.enabled = bool(enabled)
        self._events: List[Dict[str, Any]] = []

    def record(self, event: str, **payload: Any) -> None:
        if not self.enabled:
            return
        row = {
            'event': str(event or 'unknown'),
            'ts': time.time(),
        }
        for key, value in payload.items():
            row[str(key)] = value
        self._events.append(row)

    def export(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._events]