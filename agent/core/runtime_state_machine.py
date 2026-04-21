from typing import Any, Dict, Set


class RuntimeStateMachine:
    _allowed_transitions = {
        'received': {'guarded', 'fallback', 'failed'},
        'guarded': {'routed', 'fallback', 'failed'},
        'routed': {'executing', 'fallback', 'failed'},
        'executing': {'recovering', 'completed', 'fallback', 'failed'},
        'recovering': {'fallback', 'completed', 'failed'},
        'fallback': {'completed', 'failed'},
        'completed': set(),
        'failed': set(),
    }

    def initialize(self) -> Dict[str, Any]:
        return {'runtime_stage': 'received'}

    def transition(self, state: Dict[str, Any], next_stage: str) -> Dict[str, Any]:
        current_stage = str((state or {}).get('runtime_stage') or 'received')
        allowed: Set[str] = self._allowed_transitions.get(current_stage, set())
        if next_stage not in allowed:
            raise ValueError(f'invalid transition: {current_stage} -> {next_stage}')
        updated_state = dict(state or {})
        updated_state['runtime_stage'] = next_stage
        return updated_state