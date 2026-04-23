import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class QueryMemory:
    """查询记忆 — 支持可选 SQLite 持久化。
    
    新增字段（向后兼容）：
    - sql_used: 实际执行的 SQL
    - row_count: 返回行数
    - execution_time_ms: 执行耗时
    - columns_accessed: 涉及的列
    
    持久化：传入 db_path 即启用 SQLite 存储，否则纯内存。
    """

    _DDL = """
    CREATE TABLE IF NOT EXISTS query_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT DEFAULT '',
        intents TEXT DEFAULT '[]',
        sql_used TEXT DEFAULT '',
        row_count INTEGER DEFAULT 0,
        execution_time_ms INTEGER DEFAULT 0,
        columns_accessed TEXT DEFAULT '[]',
        trace TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}',
        timestamp TEXT NOT NULL
    )
    """

    def __init__(self, max_entries: int = 20, db_path: Optional[str] = None):
        self.max_entries = max(1, int(max_entries))
        self._entries: List[Dict[str, Any]] = []
        self._db_path = db_path
        if db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(self._DDL)
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("query_memory db init failed: %s", exc)
            self._db_path = None

    def _load_from_db(self) -> None:
        if not self._db_path:
            return
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM query_memory ORDER BY id DESC LIMIT ?",
                (self.max_entries,),
            ).fetchall()
            conn.close()
            for row in reversed(rows):
                self._entries.append({
                    'question': row['question'],
                    'answer': row['answer'],
                    'intents': json.loads(row['intents'] or '[]'),
                    'sql_used': row['sql_used'] or '',
                    'row_count': row['row_count'] or 0,
                    'execution_time_ms': row['execution_time_ms'] or 0,
                    'columns_accessed': json.loads(row['columns_accessed'] or '[]'),
                    'trace': json.loads(row['trace'] or '{}'),
                    'metadata': json.loads(row['metadata'] or '{}'),
                    'timestamp': row['timestamp'],
                })
        except Exception as exc:
            logger.warning("query_memory load failed: %s", exc)

    def add_query(
        self,
        question: str,
        *,
        answer: str = '',
        intents: Optional[List[str]] = None,
        trace: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        sql_used: str = '',
        row_count: int = 0,
        execution_time_ms: int = 0,
        columns_accessed: Optional[List[str]] = None,
    ) -> None:
        entry = {
            'question': str(question or '').strip(),
            'answer': str(answer or '').strip(),
            'intents': list(intents or []),
            'sql_used': str(sql_used or '').strip(),
            'row_count': int(row_count or 0),
            'execution_time_ms': int(execution_time_ms or 0),
            'columns_accessed': list(columns_accessed or []),
            'trace': dict(trace or {}),
            'metadata': dict(metadata or {}),
            'timestamp': datetime.now().isoformat(),
        }
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

        # 持久化
        if self._db_path:
            self._persist_entry(entry)

    def _persist_entry(self, entry: Dict[str, Any]) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                """INSERT INTO query_memory
                   (question, answer, intents, sql_used, row_count,
                    execution_time_ms, columns_accessed, trace, metadata, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry['question'],
                    entry['answer'],
                    json.dumps(entry['intents'], ensure_ascii=False),
                    entry['sql_used'],
                    entry['row_count'],
                    entry['execution_time_ms'],
                    json.dumps(entry['columns_accessed'], ensure_ascii=False),
                    json.dumps(entry['trace'], ensure_ascii=False),
                    json.dumps(entry['metadata'], ensure_ascii=False),
                    entry['timestamp'],
                ),
            )
            # 保持 DB 中最多 max_entries * 3 条，避免无限增长
            conn.execute(
                """DELETE FROM query_memory WHERE id NOT IN
                   (SELECT id FROM query_memory ORDER BY id DESC LIMIT ?)""",
                (self.max_entries * 3,),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("query_memory persist failed: %s", exc)

    def find_similar_query(self, question: str) -> Optional[Dict[str, Any]]:
        """查找历史中与当前问题最相似的查询（简单关键词匹配）。
        
        如果命中，可复用 sql_used 作为起点，避免重复生成。
        """
        import re as _re

        def _tokens(text: str) -> set:
            return set(_re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]+', text.lower()))

        q_tokens = _tokens(question)
        if not q_tokens:
            return None

        best_score = 0.0
        best_entry = None
        for entry in self._entries:
            e_tokens = _tokens(entry['question'])
            if not e_tokens:
                continue
            overlap = len(q_tokens & e_tokens) / len(q_tokens | e_tokens)
            if overlap > best_score and overlap > 0.5:
                best_score = overlap
                best_entry = entry

        return best_entry

    def list_entries(self) -> List[Dict[str, Any]]:
        return [dict(entry) for entry in self._entries]

    def build_prompt_context(self, max_chars: int = 1200) -> str:
        if not self._entries:
            return ''
        lines: List[str] = []
        for entry in self._entries[-5:]:
            question = str(entry.get('question') or '').strip()
            answer = str(entry.get('answer') or '').strip()
            intents = ', '.join(entry.get('intents') or [])
            sql_used = str(entry.get('sql_used') or '').strip()
            line = f"Q: {question}"
            if intents:
                line += f" | intents: {intents}"
            if sql_used:
                line += f" | SQL: {sql_used[:120]}"
            if answer:
                line += f" | A: {answer[:120]}"
            lines.append(line)
        return '\n'.join(lines)[-max_chars:]


__all__ = ['QueryMemory']