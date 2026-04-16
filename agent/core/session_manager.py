"""
Session Manager — 多会话隔离管理

企业场景下，多个用户同时使用 Agent，需要隔离：
1. 对话历史（每个用户/会话独立的记忆）
2. 上下文（不同用户看不同项目的数据）
3. 确认状态（用户A的确认不影响用户B）

用法：
    from agent.core.session_manager import SessionManager

    sm = SessionManager()
    session = sm.get_or_create("user_123", dashboard_type="defect")
    agent = session.agent

    # 处理消息
    result = session.process("哪个ECU风险最高？")

    # 清理过期会话
    sm.cleanup(max_age_hours=24)

默认关闭，AGENT_SESSION_ENABLED=1 开启（或直接使用 SessionManager）。
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 会话最大存活时间（小时）
_DEFAULT_MAX_AGE_HOURS = 24
# 单用户最大会话数
_DEFAULT_MAX_SESSIONS_PER_USER = 5


@dataclass
class SessionInfo:
    """一个会话的元信息。"""

    session_id: str
    user_id: str
    dashboard_type: str = "general"
    created_at: float = 0.0
    last_active_at: float = 0.0
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.last_active_at:
            self.last_active_at = now

    @property
    def age_hours(self) -> float:
        return (time.time() - self.created_at) / 3600

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active_at

    def touch(self):
        self.last_active_at = time.time()
        self.message_count += 1


class AgentSession:
    """一个独立的 Agent 会话，拥有自己的 Agent 实例和状态。"""

    def __init__(self, session_id: str, user_id: str, dashboard_type: str = "general"):
        self.info = SessionInfo(
            session_id=session_id,
            user_id=user_id,
            dashboard_type=dashboard_type,
        )
        self._agent = None
        self._data = None  # 该会话的数据
        self._lock = threading.Lock()

    @property
    def agent(self):
        """懒加载 Agent 实例。"""
        if self._agent is None:
            from agent.core.intelligent_agent import IntelligentAgent
            self._agent = IntelligentAgent(dashboard_type=self.info.dashboard_type)
        return self._agent

    def set_data(self, data):
        """设置该会话的数据。"""
        self._data = data

    def process(self, question: str, data=None, **kwargs) -> Dict[str, Any]:
        """处理一条消息。"""
        with self._lock:
            self.info.touch()
            df = data or self._data
            if df is None:
                return {
                    "text": "请先加载数据。",
                    "success": False,
                    "tools_used": [],
                }
            return self.agent.process(question, df, **kwargs)

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取该会话的对话历史。"""
        if self._agent and hasattr(self._agent, "memory"):
            return (self._agent.memory.short_term or [])[-limit:]
        return []


class SessionManager:
    """多会话管理器。"""

    _instance: Optional["SessionManager"] = None

    def __init__(
        self,
        max_age_hours: float = _DEFAULT_MAX_AGE_HOURS,
        max_per_user: int = _DEFAULT_MAX_SESSIONS_PER_USER,
    ):
        self._sessions: Dict[str, AgentSession] = {}  # session_id -> AgentSession
        self._user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]
        self._lock = threading.Lock()
        self._max_age_hours = max_age_hours
        self._max_per_user = max_per_user

    @classmethod
    def get_instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def is_enabled() -> bool:
        return os.getenv("AGENT_SESSION_ENABLED", "0") == "1"

    # ------------------------------------------------------------------
    # 会话 CRUD
    # ------------------------------------------------------------------

    def create(self, user_id: str, dashboard_type: str = "general", session_id: Optional[str] = None) -> AgentSession:
        """创建新会话。"""
        if session_id is None:
            session_id = f"{user_id}_{int(time.time() * 1000)}"

        with self._lock:
            # 限制单用户会话数
            user_sids = self._user_sessions.get(user_id, [])
            if len(user_sids) >= self._max_per_user:
                # 淘汰最旧的
                oldest_sid = user_sids[0]
                self._remove_session(oldest_sid)

            session = AgentSession(session_id, user_id, dashboard_type)
            self._sessions[session_id] = session
            self._user_sessions.setdefault(user_id, []).append(session_id)
            logger.info(f"Session created: {session_id} for user {user_id}")
            return session

    def get(self, session_id: str) -> Optional[AgentSession]:
        """获取现有会话。"""
        session = self._sessions.get(session_id)
        if session:
            session.info.touch()
        return session

    def get_or_create(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        dashboard_type: str = "general",
    ) -> AgentSession:
        """获取或创建会话。"""
        if session_id:
            existing = self._sessions.get(session_id)
            if existing and existing.info.user_id == user_id:
                existing.info.touch()
                return existing

        return self.create(user_id, dashboard_type, session_id)

    def get_user_sessions(self, user_id: str) -> List[SessionInfo]:
        """获取用户的所有会话信息。"""
        sids = self._user_sessions.get(user_id, [])
        sessions = [self._sessions[sid] for sid in sids if sid in self._sessions]
        return [s.info for s in sessions]

    def delete(self, session_id: str) -> bool:
        """删除会话。"""
        with self._lock:
            return self._remove_session(session_id)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def cleanup(self, max_age_hours: Optional[float] = None) -> int:
        """清理过期会话。返回清理数量。"""
        max_age = max_age_hours or self._max_age_hours
        expired = [
            sid for sid, s in self._sessions.items()
            if s.info.age_hours > max_age
        ]
        with self._lock:
            for sid in expired:
                self._remove_session(sid)
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        return len(expired)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _remove_session(self, session_id: str) -> bool:
        """从所有索引中移除会话。"""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        user_id = session.info.user_id
        if user_id in self._user_sessions:
            self._user_sessions[user_id] = [
                sid for sid in self._user_sessions[user_id] if sid != session_id
            ]
            if not self._user_sessions[user_id]:
                del self._user_sessions[user_id]
        return True

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    @property
    def user_count(self) -> int:
        return len(self._user_sessions)

    def stats(self) -> Dict[str, Any]:
        return {
            "active_sessions": self.active_count,
            "active_users": self.user_count,
            "max_age_hours": self._max_age_hours,
            "max_per_user": self._max_per_user,
        }
