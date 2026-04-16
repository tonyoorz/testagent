"""
Query Memory — 查询级别的成功记忆

记录每次成功的查询方案（问题 + 工具 + 参数 + 结果质量），
下次遇到相似问题时直接复用已验证的方案。

特性：
1. 语义相似度匹配（新问题 vs 历史成功问题）
2. 方案复用（工具 + 参数 + 数据集）
3. 质量评分（用户反馈 + 结果完整性）
4. 自动衰减（过时的方案降权）

用法：
    from agent.core.query_memory import QueryMemory

    qm = QueryMemory()
    # 查询时
    match = qm.find_similar("ECU乒乓率最高的项目")
    if match:
        plan = match.suggested_plan  # 复用成功方案

    # 成功后记录
    qm.record(question="...", plan=[...], result_quality=0.9)

存储：SQLite (database/query_memory.db)
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "database")
_DB_PATH = os.path.join(_DB_DIR, "query_memory.db")


@dataclass
class QueryRecord:
    """一条查询记忆。"""
    id: Optional[int] = None
    question: str = ""
    question_hash: str = ""
    intents: str = ""  # JSON list
    plan_json: str = ""  # JSON list of steps
    tools_used: str = ""  # JSON list
    result_quality: float = 0.0  # 0-1
    success: bool = False
    dataset: str = ""
    execution_ms: int = 0
    created_at: float = 0.0
    last_used_at: float = 0.0
    use_count: int = 0
    tags: str = ""  # JSON list


@dataclass
class QueryMatch:
    """查询匹配结果。"""
    record: QueryRecord
    similarity: float  # 0-1
    suggested_plan: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def quality(self) -> float:
        """综合质量 = 相似度 × 结果质量 × 使用次数加成。"""
        use_bonus = min(self.record.use_count / 10, 0.2)
        return self.similarity * (self.record.result_quality + use_bonus)


class QueryMemory:
    """查询级别的成功记忆系统。"""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 表。"""
        with sqlite3.connect(self._db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS query_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    question_hash TEXT NOT NULL,
                    intents TEXT DEFAULT '[]',
                    plan_json TEXT DEFAULT '[]',
                    tools_used TEXT DEFAULT '[]',
                    result_quality REAL DEFAULT 0.0,
                    success INTEGER DEFAULT 0,
                    dataset TEXT DEFAULT '',
                    execution_ms INTEGER DEFAULT 0,
                    created_at REAL DEFAULT 0,
                    last_used_at REAL DEFAULT 0,
                    use_count INTEGER DEFAULT 0,
                    tags TEXT DEFAULT '[]'
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_qm_hash ON query_memory(question_hash)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_qm_quality ON query_memory(result_quality DESC)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_qm_last ON query_memory(last_used_at DESC)")

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    def record(
        self,
        question: str,
        plan: List[Dict[str, Any]],
        tools_used: List[str],
        success: bool = True,
        result_quality: float = 0.8,
        intents: Optional[List[str]] = None,
        dataset: str = "",
        execution_ms: int = 0,
        tags: Optional[List[str]] = None,
    ):
        """记录一次查询结果。"""
        q_hash = self._hash_question(question)

        with sqlite3.connect(self._db_path) as con:
            # 检查是否已有相似记录（同hash）
            existing = con.execute(
                "SELECT id, use_count FROM query_memory WHERE question_hash = ? ORDER BY result_quality DESC LIMIT 1",
                (q_hash,)
            ).fetchone()

            now = time.time()
            if existing:
                # 更新已有记录（加权平均质量）
                old_id, old_count = existing
                new_quality = (existing[0] * 0.0 + result_quality) / 1.0  # 简化：用最新质量
                con.execute("""
                    UPDATE query_memory SET
                        result_quality = ?,
                        last_used_at = ?,
                        use_count = use_count + 1,
                        plan_json = ?,
                        tools_used = ?
                    WHERE id = ?
                """, (result_quality, now, json.dumps(plan, ensure_ascii=False),
                      json.dumps(tools_used, ensure_ascii=False), old_id))
            else:
                con.execute("""
                    INSERT INTO query_memory
                    (question, question_hash, intents, plan_json, tools_used,
                     result_quality, success, dataset, execution_ms, created_at, last_used_at, use_count, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    question, q_hash,
                    json.dumps(intents or [], ensure_ascii=False),
                    json.dumps(plan, ensure_ascii=False),
                    json.dumps(tools_used, ensure_ascii=False),
                    result_quality, int(success), dataset, execution_ms,
                    now, now,
                    json.dumps(tags or [], ensure_ascii=False),
                ))

    # ------------------------------------------------------------------
    # 查询匹配
    # ------------------------------------------------------------------

    def find_similar(
        self,
        question: str,
        intents: Optional[List[str]] = None,
        min_quality: float = 0.5,
        max_age_days: float = 90,
        limit: int = 5,
    ) -> Optional[QueryMatch]:
        """查找相似的历史成功查询。"""
        q_hash = self._hash_question(question)

        with sqlite3.connect(self._db_path) as con:
            # 先精确匹配
            exact = con.execute(
                "SELECT * FROM query_memory WHERE question_hash = ? AND success = 1 AND result_quality >= ? LIMIT 1",
                (q_hash, min_quality)
            ).fetchone()

            if exact:
                rec = self._row_to_record(exact)
                return QueryMatch(
                    record=rec,
                    similarity=1.0,
                    suggested_plan=json.loads(rec.plan_json),
                )

            # 关键词匹配
            keywords = self._extract_keywords(question)
            if not keywords:
                return None

            cutoff = time.time() - max_age_days * 86400
            candidates = con.execute("""
                SELECT * FROM query_memory
                WHERE success = 1 AND result_quality >= ? AND last_used_at >= ?
                ORDER BY result_quality DESC, use_count DESC
                LIMIT 100
            """, (min_quality, cutoff)).fetchall()

            if not candidates:
                return None

            best_match = None
            best_score = 0.0

            for row in candidates:
                rec = self._row_to_record(row)
                score = self._keyword_similarity(keywords, rec.question)
                # 加权：关键词匹配 × 结果质量 × 使用频次
                freq_bonus = min(rec.use_count / 20, 0.2)
                final_score = score * (rec.result_quality + freq_bonus)

                if final_score > best_score and score >= 0.3:
                    best_score = final_score
                    best_match = rec

            if best_match and best_score >= 0.3:
                return QueryMatch(
                    record=best_match,
                    similarity=best_score,
                    suggested_plan=json.loads(best_match.plan_json),
                )

        return None

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self._db_path) as con:
            total = con.execute("SELECT COUNT(*) FROM query_memory").fetchone()[0]
            success = con.execute("SELECT COUNT(*) FROM query_memory WHERE success = 1").fetchone()[0]
            avg_quality = con.execute("SELECT AVG(result_quality) FROM query_memory WHERE success = 1").fetchone()[0]
            reused = con.execute("SELECT SUM(use_count) - COUNT(*) FROM query_memory").fetchone()[0]
            return {
                "total_records": total,
                "successful": success,
                "avg_quality": round(avg_quality or 0, 2),
                "times_reused": reused or 0,
            }

    def cleanup(self, max_age_days: float = 90):
        """清理过旧记录。"""
        cutoff = time.time() - max_age_days * 86400
        with sqlite3.connect(self._db_path) as con:
            deleted = con.execute("DELETE FROM query_memory WHERE last_used_at < ? AND use_count < 3", (cutoff,)).rowcount
        if deleted:
            logger.info(f"QueryMemory cleanup: removed {deleted} old records")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_question(question: str) -> str:
        """规范化问题后哈希。"""
        normalized = question.strip().lower()
        # 移除标点
        for ch in "，。！？、；：""''【】（）,.!?;:\"'()[]{}":
            normalized = normalized.replace(ch, "")
        return hashlib.md5(normalized.encode()).hexdigest()

    @staticmethod
    def _extract_keywords(question: str) -> List[str]:
        """从问题中提取关键词。"""
        # 简单分词：中文按字，英文按空格
        import re
        # 移除常见停用词
        stops = {"的", "了", "是", "在", "有", "和", "与", "或", "吗", "呢", "吧", "啊",
                 "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                 "have", "has", "had", "do", "does", "did", "will", "would", "could",
                 "should", "may", "might", "can", "shall", "what", "which", "who",
                 "when", "where", "how", "why", "this", "that", "these", "those"}

        words = re.findall(r'[a-zA-Z_]+', question.lower())
        # 中文：提取连续中文字符中的bigram
        zh_chars = re.findall(r'[\u4e00-\u9fff]+', question)
        zh_ngrams = []
        for seg in zh_chars:
            for i in range(len(seg)):
                zh_ngrams.append(seg[i])
                if i < len(seg) - 1:
                    zh_ngrams.append(seg[i:i+2])

        all_words = [w for w in words + zh_ngrams if w not in stops and len(w) > 1]
        return list(set(all_words))

    @staticmethod
    def _keyword_similarity(keywords: List[str], target: str) -> float:
        """关键词匹配相似度。"""
        if not keywords:
            return 0.0
        target_lower = target.lower()
        hits = sum(1 for kw in keywords if kw in target_lower)
        return hits / len(keywords)

    @staticmethod
    def _row_to_record(row) -> QueryRecord:
        return QueryRecord(
            id=row[0], question=row[1], question_hash=row[2],
            intents=row[3], plan_json=row[4], tools_used=row[5],
            result_quality=row[6], success=bool(row[7]),
            dataset=row[8], execution_ms=row[9],
            created_at=row[10], last_used_at=row[11],
            use_count=row[12], tags=row[13],
        )
