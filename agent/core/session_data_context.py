"""
Session Data Context — 会话级数据上下文

每次对话开始时自动加载：
- 用户画像（从历史查询学习常查的 project/关注维度）
- 数据热点（从 DuckDB anomaly_baselines 读取当前异常）
- 活跃过滤器（对话中动态更新的聚焦维度）

生成可注入 prompt 的上下文文本，让 Agent 每次对话都"带着记忆"。

环境变量：AGENT_SESSION_CONTEXT=1 启用
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 模块级开关（供 intelligent_agent.py 导入）
ENABLED = os.getenv("AGENT_SESSION_CONTEXT", "0").strip() in {"1", "true", "yes"}


def _is_enabled() -> bool:
    return ENABLED


class SessionDataContext:
    """会话级数据上下文 — 注入对话的"工作记忆"。"""

    def __init__(self, duckdb_layer=None, conversation_memory=None,
                 query_memory=None, user_id: str = "default"):
        self.analytics = duckdb_layer  # DuckDBAnalyticsLayer 实例
        self.conversation_memory = conversation_memory
        self.query_memory = query_memory
        self.user_id = user_id

        # 三层上下文
        self.user_profile: Dict[str, Any] = {}
        self.hotspots: List[Dict[str, Any]] = []
        self.active_filters: Dict[str, str] = {}

        self._loaded = False

    # ========== 加载 ==========

    def initialize(self) -> None:
        """初始化（兼容集成代码）。"""
        self.load()

    def load(self) -> None:
        """加载所有上下文。通常在对话开始时调用一次。"""
        if self._loaded:
            return

        self._load_user_profile()
        self._load_hotspots()
        self._loaded = True
        logger.info(f"SessionDataContext loaded: profile={bool(self.user_profile)}, hotspots={len(self.hotspots)}")

    # ========== 生成 Prompt 上下文 ==========

    def get_context_text(self, max_length: int = 800) -> str:
        """生成注入 prompt 的上下文文本。"""
        if not self._loaded:
            self.load()

        parts: List[str] = []

        # 1. 用户画像
        profile_text = self._format_user_profile()
        if profile_text:
            parts.append(profile_text)

        # 2. 数据热点
        hotspot_text = self._format_hotspots()
        if hotspot_text:
            parts.append(hotspot_text)

        # 3. 活跃过滤器
        if self.active_filters:
            filters = ", ".join(f"{k}={v}" for k, v in self.active_filters.items() if v)
            if filters:
                parts.append(f"当前对话聚焦: {filters}")

        result = "\n\n".join(parts)

        # 截断保护
        if len(result) > max_length:
            result = result[:max_length] + "\n...(上下文已截断)"

        return result

    # ========== 动态更新 ==========

    def update_from_query(self, query_result: Dict[str, Any]) -> None:
        """每次查询后更新活跃上下文。"""
        if not query_result:
            return

        # 从查询结果中提取用户关注的维度
        for key in ["project", "ecu", "severity", "program", "status"]:
            val = query_result.get(key)
            if val:
                self.active_filters[key] = str(val)

    def update_from_user_message(self, message: str) -> None:
        """从用户消息中提取隐含的聚焦维度。"""
        import re
        # 简单的关键词提取
        if not message:
            return

        # Project 模式：大写字母+数字（如 "ProjectA", "P123"）
        projects = re.findall(r'\b[A-Z][A-Z]*\d+\b', message)
        if projects:
            self.active_filters["project"] = projects[0]

        # ECU 模式
        ecus = re.findall(r'\bECU[-_]?[\w]+\b', message, re.IGNORECASE)
        if ecus:
            self.active_filters["ecu"] = ecus[0].upper()

        # Severity 模式
        severities = re.findall(r'\b[123][A-E]\b', message)
        if severities:
            self.active_filters["severity"] = severities[0]

    def record_user_interest(self, project: str = None, ecu: str = None,
                             dimension: str = None) -> None:
        """记录用户兴趣（用于下次对话的用户画像更新）。"""
        profile = self._read_profile_file()

        interests = profile.setdefault("interests", {})
        if project:
            cnt = interests.get(f"project:{project}", 0)
            interests[f"project:{project}"] = cnt + 1
        if ecu:
            cnt = interests.get(f"ecu:{ecu}", 0)
            interests[f"ecu:{ecu}"] = cnt + 1
        if dimension:
            cnt = interests.get(f"dim:{dimension}", 0)
            interests[f"dim:{dimension}"] = cnt + 1

        profile["last_active"] = datetime.now().isoformat()
        self._write_profile_file(profile)
        self.user_profile = profile

    # ========== 内部方法 ==========

    def _load_user_profile(self) -> None:
        """加载用户画像。"""
        self.user_profile = self._read_profile_file()

        # 如果画像为空，尝试从 query_memory 学习
        if not self.user_profile.get("interests"):
            self._learn_from_query_memory()

    def _load_hotspots(self) -> None:
        """从 DuckDB 加载当前数据热点。"""
        if not self.analytics:
            return
        try:
            self.hotspots = self.analytics.get_active_hotspots(zscore_threshold=2.0)
        except Exception as e:
            logger.warning(f"加载 hotspots 失败: {e}")
            self.hotspots = []

    def _learn_from_query_memory(self) -> None:
        """从 query_memory.db 学习用户偏好。"""
        import sqlite3
        try:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            qm_path = os.path.join(base, "database", "query_memory.db")
            if not os.path.exists(qm_path):
                return

            con = sqlite3.connect(qm_path)
            # 查询最近成功的查询
            rows = con.execute(
                """SELECT question, result_quality FROM query_memory
                   WHERE result_quality > 0.5
                   ORDER BY created_at DESC LIMIT 50"""
            ).fetchall()
            con.close()

            if not rows:
                return

            interests: Dict[str, int] = {}
            for question, _ in rows:
                # 简单提取关键词
                import re
                for proj in re.findall(r'\b[A-Z][A-Z]*\d+\b', question):
                    interests[f"project:{proj}"] = interests.get(f"project:{proj}", 0) + 1
                for ecu in re.findall(r'ECU[-_]?[\w]+', question, re.IGNORECASE):
                    key = f"ecu:{ecu.upper()}"
                    interests[key] = interests.get(key, 0) + 1

            if interests:
                profile = {"interests": interests, "learned_from": "query_memory"}
                self.user_profile = profile
                self._write_profile_file(profile)

        except Exception as e:
            logger.debug(f"从 query_memory 学习失败: {e}")

    def _format_user_profile(self) -> str:
        """格式化用户画像为文本。"""
        interests = self.user_profile.get("interests", {})
        if not interests:
            return ""

        # 取 top 5 兴趣
        top = sorted(interests.items(), key=lambda x: x[1], reverse=True)[:5]

        projects = [k.split(":")[1] for k, v in top if k.startswith("project:")]
        ecus = [k.split(":")[1] for k, v in top if k.startswith("ecu:")]

        parts = []
        if projects:
            parts.append(f"用户常查项目: {', '.join(projects[:3])}")
        if ecus:
            parts.append(f"用户常查ECU: {', '.join(ecus[:3])}")

        return "📋 用户画像:\n" + "\n".join(f"  - {p}" for p in parts) if parts else ""

    def _format_hotspots(self) -> str:
        """格式化数据热点为文本。"""
        if not self.hotspots:
            return ""

        lines = []
        for h in self.hotspots[:5]:
            dim = h.get("dimension_key", "?")
            zscore = h.get("zscore", 0)
            last = h.get("last_value", 0)
            mean = h.get("mean", 0)
            direction = "↑" if zscore > 0 else "↓"
            pct = abs(zscore) * 100
            lines.append(f"  - {dim}: {direction} 异常 (当前{last:.0f}, 均值{mean:.0f}, 偏离{pct:.0f}%)")

        return "⚠️ 当前数据异常:\n" + "\n".join(lines)

    # ========== 持久化 ==========

    @property
    def _profile_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        profiles_dir = os.path.join(base, "database", "user_profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        return os.path.join(profiles_dir, f"{self.user_id}.json")

    def _read_profile_file(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self._profile_path):
                with open(self._profile_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _write_profile_file(self, profile: Dict[str, Any]) -> None:
        try:
            with open(self._profile_path, "w") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存用户画像失败: {e}")


def create_session_context(duckdb_analytics=None,
                           user_id: str = "default") -> Optional[SessionDataContext]:
    """创建 SessionDataContext（如果启用）。"""
    if not _is_enabled():
        return None

    ctx = SessionDataContext(duckdb_analytics, user_id)
    try:
        ctx.load()
    except Exception as e:
        logger.warning(f"SessionDataContext 加载失败: {e}")
        return None

    return ctx


def create_session_context_provider(ctx: SessionDataContext):
    """创建 SessionDataContext Provider（注入到 ContextChain）。"""
    from agent.core.context_provider import ContextProvider

    class SessionContextProvider(ContextProvider):
        @property
        def name(self) -> str:
            return "session_data_context"

        def __init__(self, session_ctx):
            self.ctx = session_ctx

        def priority(self) -> int:
            return 55

        def provide(self, data, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
            result: Dict[str, Any] = {}
            try:
                text = self.ctx.get_context_text(max_length=600)
                if text:
                    result["session_context"] = text
            except Exception:
                pass
            return result

    return SessionContextProvider(ctx)
