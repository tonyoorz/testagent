import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from agent.core.query_memory import QueryMemory
from agent.core.session_data_context import SessionDataContext

# Default location for persistent query memory DB
_DEFAULT_QUERY_MEMORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "database",
)


def _query_memory_db_path(session_id: str) -> str:
    """Build a per-session SQLite path for persistent query memory."""
    os.makedirs(_DEFAULT_QUERY_MEMORY_DIR, exist_ok=True)
    # Use a single shared DB for all sessions to avoid file sprawl
    return os.path.join(_DEFAULT_QUERY_MEMORY_DIR, "query_memory.db")


@dataclass
class AgentSession:
    session_id: str
    dashboard_type: str = 'general'
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    data_context: SessionDataContext = field(init=False)
    query_memory: QueryMemory = field(init=False)

    def __post_init__(self) -> None:
        self.data_context = SessionDataContext(dashboard_type=self.dashboard_type)
        db_path = _query_memory_db_path(self.session_id)
        self.query_memory = QueryMemory(db_path=db_path)

    def touch(self) -> None:
        self.last_active_at = time.time()


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, AgentSession] = {}

    def get_or_create(self, session_id: str, dashboard_type: str = 'general') -> AgentSession:
        key = str(session_id or '').strip() or str(dashboard_type or 'general')
        session = self._sessions.get(key)
        if session is None:
            session = AgentSession(session_id=key, dashboard_type=dashboard_type)
            self._sessions[key] = session
        session.touch()
        return session


__all__ = ['AgentSession', 'SessionManager']