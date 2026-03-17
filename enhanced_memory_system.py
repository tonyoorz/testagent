"""
增强版记忆系统 - 为 Agent 提供多层次记忆能力

核心优化：
1. 向量化检索 - 使用语义相似度而非关键词匹配
2. 三层记忆架构 - 短期/中期/长期记忆分层管理
3. 洞察沉淀 - 自动提取和持久化分析洞察
4. 会话隔离 - 支持多用户/多项目独立记忆
5. 主动回忆 - 每次对话主动注入相关上下文

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import sqlite3
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构定义
# ============================================================================

@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    role: str  # 'user' | 'assistant' | 'system' | 'insight'
    timestamp: str
    importance: float = 0.5
    metadata: Dict = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Insight:
    """分析洞察"""
    id: str
    question: str
    finding: str
    recommendation: str
    data_scope: str  # 数据范围描述
    tools_used: List[str]
    confidence: float
    timestamp: str
    verified: bool = False  # 用户是否确认有效
    
    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================================
# 向量化存储（复用 duplicate_issue_finder 的能力）
# ============================================================================

class VectorStore:
    """向量存储 - 用于语义检索"""
    
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.embeddings: Dict[str, List[float]] = {}
        self.contents: Dict[str, str] = {}
        
        # 尝试导入向量化库
        self._embedding_client = None
        self._init_embedding_client()
    
    def _init_embedding_client(self):
        """初始化嵌入模型客户端"""
        try:
            from openai import OpenAI
            api_base = os.environ.get("OPENAI_API_BASE", "https://api.deepseek.com")
            api_key = os.environ.get("OPENAI_API_KEY", os.environ.get("DEEPSEEK_API_KEY"))
            
            if api_key:
                self._embedding_client = OpenAI(
                    base_url=api_base,
                    api_key=api_key
                )
                logger.info("向量嵌入客户端初始化成功")
        except Exception as e:
            logger.warning(f"向量嵌入客户端初始化失败: {e}")
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取文本嵌入向量"""
        if not self._embedding_client:
            return None
        
        try:
            # 截断过长文本
            text = text[:8000]
            response = self._embedding_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning(f"获取嵌入向量失败: {e}")
            return None
    
    def add(self, id: str, content: str, embedding: List[float] = None):
        """添加向量"""
        if embedding is None:
            embedding = self.get_embedding(content)
        
        if embedding:
            self.embeddings[id] = embedding
            self.contents[id] = content
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """语义搜索"""
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return []
        
        # 计算余弦相似度
        scores = {}
        for id, emb in self.embeddings.items():
            score = self._cosine_similarity(query_embedding, emb)
            scores[id] = score
        
        # 排序返回 top_k
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:top_k]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        import numpy as np
        a_arr = np.array(a)
        b_arr = np.array(b)
        return np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))
    
    def save(self, path: str):
        """保存到文件"""
        data = {
            "embeddings": self.embeddings,
            "contents": self.contents
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    
    def load(self, path: str):
        """从文件加载"""
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.embeddings = data.get("embeddings", {})
        self.contents = data.get("contents", {})


# ============================================================================
# SQLite 中期记忆存储
# ============================================================================

class SQLiteMemoryStore:
    """SQLite 中期记忆存储"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取线程安全的连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 对话记忆表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_memory (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                importance REAL DEFAULT 0.5,
                metadata TEXT
            )
        ''')
        
        # 洞察表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                finding TEXT NOT NULL,
                recommendation TEXT,
                data_scope TEXT,
                tools_used TEXT,
                confidence REAL DEFAULT 0.5,
                timestamp TEXT NOT NULL,
                verified INTEGER DEFAULT 0,
                session_id TEXT
            )
        ''')
        
        # 用户偏好表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                preferences TEXT NOT NULL,
                updated_at TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_id ON conversation_memory(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON conversation_memory(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_insights_verified ON insights(verified)')
        
        conn.commit()
    
    def add_message(self, entry: MemoryEntry, session_id: str):
        """添加对话消息"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO conversation_memory 
            (id, session_id, role, content, timestamp, importance, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            entry.id, session_id, entry.role, entry.content,
            entry.timestamp, entry.importance, json.dumps(entry.metadata)
        ))
        conn.commit()
    
    def get_session_messages(self, session_id: str, limit: int = 50) -> List[MemoryEntry]:
        """获取会话消息"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversation_memory 
            WHERE session_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (session_id, limit))
        
        rows = cursor.fetchall()
        return [self._row_to_entry(row) for row in reversed(rows)]
    
    def search_messages(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """搜索消息（简单 LIKE 查询）"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversation_memory 
            WHERE content LIKE ? 
            ORDER BY importance DESC, timestamp DESC 
            LIMIT ?
        ''', (f'%{query}%', limit))
        
        rows = cursor.fetchall()
        return [self._row_to_entry(row) for row in rows]
    
    def add_insight(self, insight: Insight, session_id: str = None):
        """添加洞察"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO insights 
            (id, question, finding, recommendation, data_scope, 
             tools_used, confidence, timestamp, verified, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            insight.id, insight.question, insight.finding,
            insight.recommendation, insight.data_scope,
            json.dumps(insight.tools_used), insight.confidence,
            insight.timestamp, int(insight.verified), session_id
        ))
        conn.commit()
    
    def get_recent_insights(self, limit: int = 20) -> List[Insight]:
        """获取最近的洞察"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM insights 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        return [self._row_to_insight(row) for row in rows]
    
    def search_insights(self, query: str, limit: int = 5) -> List[Insight]:
        """搜索洞察"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM insights 
            WHERE question LIKE ? OR finding LIKE ? OR recommendation LIKE ?
            ORDER BY confidence DESC, timestamp DESC 
            LIMIT ?
        ''', (f'%{query}%', f'%{query}%', f'%{query}%', limit))
        
        rows = cursor.fetchall()
        return [self._row_to_insight(row) for row in rows]
    
    def _row_to_entry(self, row) -> MemoryEntry:
        """数据库行转 MemoryEntry"""
        return MemoryEntry(
            id=row['id'],
            content=row['content'],
            role=row['role'],
            timestamp=row['timestamp'],
            importance=row['importance'],
            metadata=json.loads(row['metadata'] or '{}')
        )
    
    def _row_to_insight(self, row) -> Insight:
        """数据库行转 Insight"""
        return Insight(
            id=row['id'],
            question=row['question'],
            finding=row['finding'],
            recommendation=row['recommendation'] or '',
            data_scope=row['data_scope'] or '',
            tools_used=json.loads(row['tools_used'] or '[]'),
            confidence=row['confidence'],
            timestamp=row['timestamp'],
            verified=bool(row['verified'])
        )
    
    def cleanup_old_messages(self, days: int = 30):
        """清理旧消息"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute('DELETE FROM conversation_memory WHERE timestamp < ?', (cutoff,))
        conn.commit()
        logger.info(f"清理了 {cursor.rowcount} 条旧消息")


# ============================================================================
# 增强版记忆管理器
# ============================================================================

class EnhancedMemorySystem:
    """增强版记忆系统"""
    
    def __init__(
        self,
        db_path: str = "memory/memory.db",
        vector_store_path: str = "memory/vectors.json",
        max_short_term: int = 10,
        enable_vector_search: bool = True
    ):
        """
        初始化增强版记忆系统
        
        Args:
            db_path: SQLite 数据库路径
            vector_store_path: 向量存储路径
            max_short_term: 短期记忆最大条数
            enable_vector_search: 是否启用向量检索
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 初始化各层存储
        self.short_term: List[MemoryEntry] = []  # 短期记忆（内存）
        self.sqlite_store = SQLiteMemoryStore(db_path)  # 中期记忆（SQLite）
        
        # 向量存储（可选）
        self.enable_vector_search = enable_vector_search
        self.vector_store: Optional[VectorStore] = None
        if enable_vector_search:
            self.vector_store = VectorStore()
            if os.path.exists(vector_store_path):
                self.vector_store.load(vector_store_path)
            self.vector_store_path = vector_store_path
        
        self.max_short_term = max_short_term
        self.current_session_id: str = self._generate_session_id()
        
        # 用户偏好
        self.user_preferences: Dict[str, Any] = {}
        
        logger.info(f"增强版记忆系统初始化完成，会话ID: {self.current_session_id}")
    
    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def _generate_id(self, content: str) -> str:
        """生成唯一ID"""
        return hashlib.md5(
            f"{content}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
    
    # ========================
    # 消息管理
    # ========================
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict = None,
        importance: float = None
    ) -> MemoryEntry:
        """
        添加消息到记忆系统
        
        Args:
            role: 角色 ('user' | 'assistant' | 'system')
            content: 消息内容
            metadata: 元数据
            importance: 重要性评分 (0-1)
        
        Returns:
            创建的记忆条目
        """
        # 计算重要性
        if importance is None:
            importance = self._calculate_importance(role, content)
        
        # 创建条目
        entry = MemoryEntry(
            id=self._generate_id(content),
            content=content,
            role=role,
            timestamp=datetime.now().isoformat(),
            importance=importance,
            metadata=metadata or {}
        )
        
        # 1. 添加到短期记忆
        self.short_term.append(entry)
        if len(self.short_term) > self.max_short_term:
            self.short_term.pop(0)
        
        # 2. 添加到中期记忆（SQLite）
        self.sqlite_store.add_message(entry, self.current_session_id)
        
        # 3. 添加到向量存储（如果启用）
        if self.vector_store and importance > 0.6:
            self.vector_store.add(entry.id, content)
        
        return entry
    
    def _calculate_importance(self, role: str, content: str) -> float:
        """计算消息重要性"""
        score = 0.5
        
        # 助手回复通常更重要
        if role == 'assistant':
            score += 0.1
        
        # 包含关键洞察的更重要
        insight_keywords = ['发现', '建议', '风险', '趋势', '关键', '重要', 'insight', 'recommendation']
        for kw in insight_keywords:
            if kw in content.lower():
                score += 0.1
        
        # 长内容可能包含更多信息
        if len(content) > 500:
            score += 0.1
        
        return min(score, 1.0)
    
    # ========================
    # 洞察管理
    # ========================
    
    def add_insight(
        self,
        question: str,
        finding: str,
        recommendation: str = "",
        data_scope: str = "",
        tools_used: List[str] = None,
        confidence: float = 0.7
    ) -> Insight:
        """
        添加分析洞察
        
        Args:
            question: 用户问题
            finding: 发现/结论
            recommendation: 建议
            data_scope: 数据范围
            tools_used: 使用的工具
            confidence: 置信度
        """
        insight = Insight(
            id=self._generate_id(finding),
            question=question,
            finding=finding,
            recommendation=recommendation,
            data_scope=data_scope,
            tools_used=tools_used or [],
            confidence=confidence,
            timestamp=datetime.now().isoformat()
        )
        
        # 存储到 SQLite
        self.sqlite_store.add_insight(insight, self.current_session_id)
        
        # 存储到向量库
        if self.vector_store:
            self.vector_store.add(
                insight.id,
                f"{question} {finding} {recommendation}"
            )
        
        logger.info(f"添加洞察: {finding[:50]}...")
        return insight
    
    # ========================
    # 检索功能
    # ========================
    
    def get_relevant_context(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        获取相关上下文（核心方法）
        
        Args:
            query: 用户查询
            top_k: 返回条数
        
        Returns:
            包含短期记忆、历史消息、洞察的上下文
        """
        context = {
            "short_term": [],
            "relevant_messages": [],
            "relevant_insights": [],
            "vector_matches": []
        }
        
        # 1. 短期记忆（最近对话）
        context["short_term"] = [
            {"role": e.role, "content": e.content}
            for e in self.short_term[-5:]
        ]
        
        # 2. 从 SQLite 搜索相关消息
        context["relevant_messages"] = [
            {"role": e.role, "content": e.content, "importance": e.importance}
            for e in self.sqlite_store.search_messages(query, top_k=3)
        ]
        
        # 3. 搜索相关洞察
        context["relevant_insights"] = [
            {
                "question": i.question,
                "finding": i.finding,
                "recommendation": i.recommendation,
                "confidence": i.confidence
            }
            for i in self.sqlite_store.search_insights(query, top_k=3)
        ]
        
        # 4. 向量检索（如果启用）
        if self.vector_store:
            matches = self.vector_store.search(query, top_k=3)
            for id, score in matches:
                if id in self.vector_store.contents:
                    context["vector_matches"].append({
                        "content": self.vector_store.contents[id],
                        "similarity": score
                    })
        
        return context
    
    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """格式化上下文用于 Prompt"""
        parts = []
        
        if context.get("short_term"):
            parts.append("## 最近对话\n")
            for msg in context["short_term"][-3:]:
                parts.append(f"- {msg['role']}: {msg['content'][:100]}...\n")
        
        if context.get("relevant_insights"):
            parts.append("\n## 相关历史洞察\n")
            for insight in context["relevant_insights"]:
                parts.append(f"- **{insight['finding'][:80]}**\n")
                if insight.get("recommendation"):
                    parts.append(f"  建议: {insight['recommendation'][:60]}\n")
        
        if context.get("vector_matches"):
            parts.append("\n## 语义相关内容\n")
            for match in context["vector_matches"][:2]:
                parts.append(f"- {match['content'][:100]} (相似度: {match['similarity']:.2f})\n")
        
        return "".join(parts) if parts else ""
    
    # ========================
    # 会话管理
    # ========================
    
    def start_new_session(self):
        """开始新会话"""
        self.current_session_id = self._generate_session_id()
        self.short_term = []
        logger.info(f"开始新会话: {self.current_session_id}")
    
    def get_session_summary(self) -> str:
        """获取会话摘要"""
        messages = self.sqlite_store.get_session_messages(self.current_session_id)
        if not messages:
            return "当前会话暂无对话记录"
        
        user_msgs = [m for m in messages if m.role == 'user']
        assistant_msgs = [m for m in messages if m.role == 'assistant']
        
        return f"当前会话共 {len(messages)} 条消息（用户 {len(user_msgs)} 条，助手 {len(assistant_msgs)} 条）"
    
    # ========================
    # 持久化
    # ========================
    
    def save(self):
        """保存记忆"""
        if self.vector_store:
            self.vector_store.save(self.vector_store_path)
        logger.info("记忆系统已保存")
    
    def cleanup(self, days: int = 30):
        """清理旧记忆"""
        self.sqlite_store.cleanup_old_messages(days)
        logger.info(f"已清理 {days} 天前的旧记忆")


# ============================================================================
# 工厂函数
# ============================================================================

def create_enhanced_memory(
    db_path: str = "memory/memory.db",
    enable_vector_search: bool = True
) -> EnhancedMemorySystem:
    """创建增强版记忆系统"""
    return EnhancedMemorySystem(
        db_path=db_path,
        enable_vector_search=enable_vector_search
    )


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'EnhancedMemorySystem',
    'MemoryEntry',
    'Insight',
    'VectorStore',
    'SQLiteMemoryStore',
    'create_enhanced_memory'
]
