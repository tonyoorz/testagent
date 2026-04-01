import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


class ConversationMemory:
    """对话记忆系统 - 管理短期和长期记忆"""

    def __init__(
        self,
        max_short_term: int = 10,
        max_long_term: int = 100,
        memory_file: Optional[str] = None,
        autosave: bool = False,
    ):
        self.max_short_term = max_short_term
        self.max_long_term = max_long_term

        self.short_term = []
        self.long_term = []
        self.user_preferences = {}
        self.memory_file = memory_file
        self.autosave = autosave

        if self.memory_file:
            self._load()

    def add_fact(
        self,
        content: str,
        importance: float = 0.95,
        tags: Optional[List[str]] = None,
        entities: Optional[Dict[str, Any]] = None,
    ):
        text = (content or "").strip()
        if not text:
            return
        self.long_term.append(
            {
                "kind": "fact",
                "content": text[:600],
                "timestamp": datetime.now().isoformat(),
                "importance": float(max(0.0, min(1.0, importance))),
                "tags": list(tags or []),
                "entities": entities or {},
            }
        )
        self._trim_long_term()
        if self.autosave:
            self.save()

    def forget(self, needle: str) -> int:
        key = (needle or "").strip().lower()
        if not key:
            return 0
        before = len(self.long_term)
        kept = []
        for memory in self.long_term:
            content = str((memory or {}).get("content") or "").lower()
            if key and key in content:
                continue
            kept.append(memory)
        self.long_term = kept
        removed = before - len(self.long_term)
        if removed and self.autosave:
            self.save()
        return removed

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None):
        """添加消息到短期记忆"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        self.short_term.append(message)
        if len(self.short_term) > self.max_short_term:
            self._summarize_and_archive()
        if self.autosave:
            self.save()

    def _trim_long_term(self):
        now = datetime.now()
        trimmed = []
        for memory in self.long_term:
            try:
                ts = str((memory or {}).get("timestamp") or "")
                dt = datetime.fromisoformat(ts) if ts else None
            except Exception:
                dt = None
            importance = float((memory or {}).get("importance") or 0.5)
            if dt:
                age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
                importance = max(0.05, min(1.0, importance * (0.985 ** age_days)))
            normalized = dict(memory or {})
            normalized["importance"] = importance
            trimmed.append(normalized)
        trimmed.sort(key=lambda item: float(item.get("importance") or 0.0), reverse=True)
        self.long_term = trimmed[: self.max_long_term]

    def _summarize_and_archive(self):
        if len(self.short_term) <= self.max_short_term:
            return

        archived = self.short_term[: len(self.short_term) - self.max_short_term]
        self.short_term = self.short_term[-self.max_short_term :]

        summary = self._summarize_messages(archived)
        if summary:
            self.long_term.append(
                {
                    "kind": "summary",
                    "content": summary,
                    "timestamp": datetime.now().isoformat(),
                    "importance": 0.7,
                    "tags": self._extract_tags(summary),
                    "entities": self._extract_entities(summary),
                }
            )

        for msg in archived:
            if msg["role"] == "assistant" and len(msg["content"]) > 80:
                importance = self._calculate_importance(msg)
                if importance >= 0.7:
                    self.long_term.append(
                        {
                            "kind": "insight",
                            "content": msg["content"][:400],
                            "timestamp": msg["timestamp"],
                            "importance": importance,
                            "tags": self._extract_tags(msg["content"]),
                            "entities": self._extract_entities(msg["content"]),
                        }
                    )

        self._trim_long_term()

    def _calculate_importance(self, message: Dict[str, Any]) -> float:
        """计算消息重要性"""
        importance = 0.5

        content = message["content"].lower()
        important_keywords = ["风险", "异常", "建议", "improvement", "异常", "critical"]
        if any(keyword in content for keyword in important_keywords):
            importance += 0.3

        if len(message["content"]) > 100:
            importance += 0.2

        return min(importance, 1.0)

    def _extract_tags(self, text: str) -> List[str]:
        content = (text or "").lower()
        tags = []
        for tag in ["sql", "sqlite", "口径", "定义", "字段", "风险", "建议", "重复", "已知问题", "测试", "缺陷", "project", "pu", "fv"]:
            if tag in content:
                tags.append(tag)
        return tags[:8]

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        content = (text or "").strip()
        lower = content.lower()
        entities: Dict[str, Any] = {}
        projects = []
        for project in ["idcevo", "idevo", "app"]:
            if project in lower:
                projects.append(project)
        if projects:
            entities["projects"] = sorted(list(set(projects)))
        matches = re.findall(r"\bpu\s*[:：]?\s*([a-z0-9._-]{2,})\b", lower, flags=re.IGNORECASE)
        if matches:
            entities["pu"] = sorted(list(set([item.strip() for item in matches if item and item.strip()])))[:5]
        numbers = re.findall(r"\b\d{2,}\b", lower)
        if numbers:
            entities["numbers"] = numbers[:6]
        return entities

    def get_relevant_history(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """获取相关历史记录（简单实现：基于关键词匹配）"""
        query_lower = (query or "").lower()
        tokens = [token.strip() for token in re.split(r"[\s,，。；;]+", query_lower) if token and len(token.strip()) >= 2]
        tokens = tokens[:12]

        def _score(text: str) -> int:
            content = (text or "").lower()
            return sum(1 for token in tokens if token in content)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for msg in self.short_term or []:
            content = msg.get("content") or ""
            hit = _score(content)
            if hit <= 0:
                continue
            scored.append((1000.0 + float(hit), msg))

        for memory in self.long_term or []:
            content = memory.get("content", "") or ""
            hit = _score(content)
            if hit <= 0:
                continue
            base = float(memory.get("importance") or 0.5) * 10.0
            scored.append(
                (
                    base + float(hit),
                    {
                        "role": "assistant",
                        "content": content,
                        "timestamp": memory.get("timestamp"),
                        "from_memory": True,
                        "kind": memory.get("kind"),
                        "tags": memory.get("tags") or [],
                        "entities": memory.get("entities") or {},
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[: max(1, int(top_k))]]

    def save_preference(self, key: str, value: Any):
        """保存用户偏好"""
        self.user_preferences[key] = value
        self.user_preferences["updated_at"] = datetime.now().isoformat()
        if self.autosave:
            self.save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self.user_preferences.get(key, default)

    def get_conversation_context(self) -> str:
        """获取对话上下文摘要"""
        context_parts = []

        if self.short_term:
            context_parts.append(f"当前对话包含 {len(self.short_term)} 条消息")

        if self.user_preferences:
            context_parts.append(f"用户偏好: {list(self.user_preferences.keys())}")

        return "\n".join(context_parts)

    def build_prompt_context(self, query: str, max_chars: int = 4000) -> str:
        parts = []
        if self.user_preferences:
            pref_items = {k: v for k, v in self.user_preferences.items() if k != "updated_at"}
            if pref_items:
                parts.append(f"用户偏好: {pref_items}")

        recent = self.short_term[-self.max_short_term :]
        if recent:
            parts.append("最近对话：")
            for msg in recent:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = (msg.get("content") or "").strip()
                if content:
                    parts.append(f"{role}: {content}")

        memories = self.get_relevant_history(query, top_k=5)
        if memories:
            parts.append("相关记忆：")
            for memory in memories:
                parts.append(f"- {memory.get('content', '')}")

        text = "\n".join(parts)
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return ""
        user_msgs = [msg.get("content", "").strip() for msg in messages if msg.get("role") == "user" and msg.get("content")]
        assistant_msgs = [msg.get("content", "").strip() for msg in messages if msg.get("role") == "assistant" and msg.get("content")]

        highlights = []
        for text in assistant_msgs[-3:]:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith(("-", "•")):
                    highlights.append(line.lstrip("-• ").strip())
                elif re.match(r"^\d+[\.\)]\s+", line):
                    highlights.append(re.sub(r"^\d+[\.\)]\s+", "", line))
        highlights = [item for item in highlights if 6 <= len(item) <= 120]
        highlights = highlights[:6]

        last_question = user_msgs[-1] if user_msgs else ""
        parts = []
        if last_question:
            parts.append(f"归档对话主题: {last_question[:120]}")
        if highlights:
            parts.append("要点: " + "；".join(highlights))
        if not parts:
            compact = " ".join((user_msgs + assistant_msgs)[-6:])
            return compact[:400]
        return "\n".join(parts)[:600]

    def _load(self):
        try:
            if not self.memory_file or not os.path.exists(self.memory_file):
                return
            with open(self.memory_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.long_term = payload.get("long_term", []) or []
            self.user_preferences = payload.get("user_preferences", {}) or {}
        except Exception as exc:
            logger.warning(f"加载记忆文件失败: {exc}")

    def save(self):
        if not self.memory_file:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.memory_file)), exist_ok=True)
            payload = {
                "long_term": self.long_term[-self.max_long_term :],
                "user_preferences": self.user_preferences,
            }
            with open(self.memory_file, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"保存记忆文件失败: {exc}")


__all__ = ["ConversationMemory"]