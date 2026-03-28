#!/usr/bin/env python3
"""
SQL 查询引擎 - 性能优化版本

优化点：
1. 缓存 Prompt 组件（Schema、BusinessKnowledge、Few-shot）
2. 动态示例选择（基于问题类型选择最相关示例）
3. 连接池（SQLite 连接复用）
4. 智能 LRU 缓存（限制大小 + 过期策略）
5. 优化 Prompt 长度（压缩重复内容）

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import sqlite3
import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from collections import OrderedDict
import pandas as pd

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 导入原始配置
# ============================================================================

from sql_query_engine import SQLQueryConfig


# ============================================================================
# 配置类（扩展）
# ============================================================================

@dataclass
class SQLQueryConfigOptimized(SQLQueryConfig):
    """优化的 SQL 查询配置"""
    cache_max_size: int = 100  # 最大缓存条目数
    cache_cleanup_interval: int = 3600  # 缓存清理间隔（秒）
    enable_connection_pool: bool = True  # 是否启用连接池
    max_connections: int = 5  # 最大连接数
    prompt_cache_enabled: bool = True  # 是否缓存 Prompt 组件


# ============================================================================
# 连接池
# ============================================================================

class SQLiteConnectionPool:
    """SQLite 连接池"""

    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self.max_connections = max_connections
        self._pool = []
        self._lock = __import__('threading').Lock()
        logger.info(f"SQLite 连接池初始化: max_connections={max_connections}")

    def get_connection(self):
        """获取连接"""
        with self._lock:
            if self._pool:
                conn = self._pool.pop()
                return conn
            else:
                return sqlite3.connect(self.db_path)

    def return_connection(self, conn):
        """归还连接"""
        with self._lock:
            if len(self._pool) < self.max_connections:
                self._pool.append(conn)
            else:
                conn.close()

    def close_all(self):
        """关闭所有连接"""
        with self._lock:
            for conn in self._pool:
                conn.close()
            self._pool.clear()


# ============================================================================
# 智能缓存（LRU + 过期）
# ============================================================================

class SmartCache:
    """智能 LRU 缓存（支持过期策略）"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache = OrderedDict()
        self._lock = __import__('threading').Lock()
        self._last_cleanup = 0
        logger.info(f"智能缓存初始化: max_size={max_size}, ttl={ttl_seconds}s")

    def get(self, key: str) -> Optional[Dict]:
        """获取缓存"""
        with self._lock:
            if key not in self._cache:
                return None

            value = self._cache[key]

            # 检查是否过期
            if datetime.now().timestamp() - value['timestamp'] > self.ttl_seconds:
                del self._cache[key]
                return None

            # LRU: 移到末尾
            self._cache.move_to_end(key)
            return value

    def put(self, key: str, value: Dict):
        """存入缓存"""
        with self._lock:
            self._cleanup_if_needed()

            # 如果已存在，更新
            if key in self._cache:
                self._cache[key] = value
                self._cache.move_to_end(key)
            else:
                # 新增
                self._cache[key] = value

    def _cleanup_if_needed(self):
        """如果需要，清理过期或最旧的缓存"""
        current_time = datetime.now().timestamp()

        # 定期清理过期缓存
        if current_time - self._last_cleanup > self.ttl_seconds:
            expired_keys = [
                k for k, v in self._cache.items()
                if current_time - v['timestamp'] > self.ttl_seconds
            ]
            for k in expired_keys:
                del self._cache[k]
            self._last_cleanup = current_time
            logger.info(f"清理过期缓存: {len(expired_keys)} 条")

        # 如果超过最大大小，删除最旧的
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()


# ============================================================================
# 动态示例选择器
# ============================================================================

class DynamicExampleSelector:
    """动态 Few-shot 示例选择器"""

    EXAMPLES = [
        {
            "question": "统计所有缺陷的数量",
            "sql": "SELECT COUNT(*) as total_defects FROM defects",
            "tags": ["数量", "统计", "简单"]
        },
        {
            "question": "统计 Critical 级别的缺陷数量",
            "sql": "SELECT COUNT(*) as critical_defects FROM defects WHERE severity = 'Critical'",
            "tags": ["数量", "严重度", "条件"]
        },
        {
            "question": "各模块的缺陷数量统计",
            "sql": "SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module ORDER BY defect_count DESC",
            "tags": ["数量", "分组", "排序", "模块"]
        },
        {
            "question": "测试通过率是多少",
            "sql": "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs",
            "tags": ["通过率", "百分比", "计算"]
        },
        {
            "question": "最近7天的测试通过率",
            "sql": "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs WHERE start_time >= date('now', '-7 days')",
            "tags": ["通过率", "时间", "最近"]
        },
        {
            "question": "各项目的测试数量统计",
            "sql": "SELECT project, COUNT(*) as test_count FROM test_runs GROUP BY project ORDER BY test_count DESC",
            "tags": ["数量", "分组", "项目"]
        },
        {
            "question": "最近创建的 10 个缺陷",
            "sql": "SELECT * FROM defects ORDER BY creation_time DESC LIMIT 10",
            "tags": ["列表", "最近", "排序"]
        },
        {
            "question": "本周的测试覆盖率",
            "sql": "SELECT module, component, coverage_percent FROM test_coverage WHERE test_week = (SELECT MAX(test_week) FROM test_coverage)",
            "tags": ["覆盖率", "本周"]
        },
        {
            "question": "高风险缺陷（Critical + 重开 > 3 次）",
            "sql": "SELECT * FROM defects WHERE severity = 'Critical' AND pingpong > 3",
            "tags": ["风险", "严重度", "条件组合"]
        },
        {
            "question": "各严重度级别的缺陷数量",
            "sql": "SELECT severity, COUNT(*) as count FROM defects GROUP BY severity ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END",
            "tags": ["数量", "分组", "严重度", "排序"]
        },
        {
            "question": "测试执行失败的详细信息",
            "sql": "SELECT tr.test_name, tr.project, tr.module, tr.result, tr.start_time FROM test_runs tr WHERE tr.result = 'Failed' ORDER BY tr.start_time DESC LIMIT 10",
            "tags": ["失败", "列表", "测试"]
        },
        {
            "question": "缺陷趋势分析（按月）",
            "sql": "SELECT strftime('%Y-%m', creation_time) as month, COUNT(*) as total_defects, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical_count FROM defects WHERE creation_time IS NOT NULL GROUP BY strftime('%Y-%m', creation_time) ORDER BY month DESC LIMIT 12",
            "tags": ["趋势", "时间", "分组", "复杂"]
        }
    ]

    @classmethod
    def select_examples(cls, question: str, limit: int = 3) -> List[Dict]:
        """根据问题选择最相关的示例"""
        question_lower = question.lower()

        # 计算每个示例的相关性分数
        scored_examples = []
        for example in cls.EXAMPLES:
            score = 0

            # 标签匹配（权重高）
            for tag in example["tags"]:
                if tag in question_lower:
                    score += 10

            # 问题关键词匹配（权重中）
            q_words = set(question_lower.split())
            e_words = set(example["question"].lower().split())
            if q_words & e_words:  # 交集
                score += 5 * len(q_words & e_words)

            # SQL 关键词匹配（权重低）
            sql_keywords = ["count", "group by", "order by", "limit", "where"]
            for kw in sql_keywords:
                if kw in example["sql"].lower() and kw in question_lower:
                    score += 2

            scored_examples.append((score, example))

        # 按分数排序，取前 limit 个
        scored_examples.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored_examples[:limit]]

    @classmethod
    def get_formatted_examples(cls, selected: List[Dict]) -> str:
        """格式化选中的示例"""
        if not selected:
            return ""

        parts = ["\n示例查询（学习这些模式）：\n"]
        for i, ex in enumerate(selected, 1):
            parts.append(f"\n示例 {i}:")
            parts.append(f"问题: {ex['question']}")
            parts.append(f"SQL: {ex['sql']}")
        return "\n".join(parts)


# 导入原有的类
from sql_query_engine import SchemaManager, BusinessKnowledge, SQLValidator


# ============================================================================
# 优化的 SQL 查询引擎
# ============================================================================

class SQLQueryEngineOptimized:
    """优化的 SQL 查询引擎"""

    def __init__(self, config: Optional[SQLQueryConfigOptimized] = None):
        self.config = config or SQLQueryConfigOptimized()

        # 初始化连接池
        if self.config.enable_connection_pool:
            self.connection_pool = SQLiteConnectionPool(
                self.config.db_path,
                self.config.max_connections
            )
        else:
            self.connection_pool = None

        # 初始化组件
        self.schema_manager = SchemaManager(self.config.db_path)
        self.validator = SQLValidator(self.config.dangerous_keywords)

        # 使用智能缓存
        self._query_cache = SmartCache(
            max_size=self.config.cache_max_size,
            ttl_seconds=self.config.cache_ttl_seconds
        )

        # 缓存 Prompt 组件（如果启用）
        if self.config.prompt_cache_enabled:
            self._schema_cache = None
            self._business_knowledge_cache = None

        logger.info(f"优化的 SQL 查询引擎初始化完成: {self.config.db_path}")

    def query(
        self,
        question: str,
        llm_generate_func: callable,
        data_context: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        执行 Text-to-SQL 查询（优化版）

        Returns:
            {
                "success": bool,
                "sql": str,
                "result": pd.DataFrame,
                "error": Optional[str],
                "retries": int,
                "execution_time_ms": float,
                "from_cache": bool
            }
        """
        import time
        start_time = time.time()

        # 检查缓存
        cache_key = self._generate_cache_key(question, data_context)
        if use_cache and self.config.enable_cache:
            cached = self._query_cache.get(cache_key)
            if cached:
                if self.config.verbose:
                    logger.info(f"使用缓存结果: {question[:50]}...")
                return {
                    "success": True,
                    "sql": cached['sql'],
                    "result": cached['result'],
                    "retries": 0,
                    "execution_time_ms": (time.time() - start_time) * 1000,
                    "from_cache": True
                }

        # 生成 SQL
        sql = None
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                # 构建 Prompt（优化版）
                prompt = self._build_prompt_optimized(question, data_context, last_error)

                # 调用 LLM 生成 SQL
                sql = llm_generate_func(prompt)

                # 验证 SQL
                is_valid, error_msg = self.validator.validate(sql)
                if not is_valid:
                    raise ValueError(error_msg)

                # 执行 SQL（使用连接池）
                conn = self.connection_pool.get_connection() if self.connection_pool else sqlite3.connect(self.config.db_path)
                try:
                    df = pd.read_sql_query(sql, conn)
                finally:
                    if self.connection_pool:
                        self.connection_pool.return_connection(conn)
                    else:
                        conn.close()

                execution_time = (time.time() - start_time) * 1000

                # 缓存结果
                if self.config.enable_cache:
                    self._query_cache.put(cache_key, {
                        'sql': sql,
                        'result': df,
                        'timestamp': time.time()
                    })

                if self.config.verbose:
                    logger.info(f"SQL 查询成功（尝试 {attempt + 1}/{self.config.max_retries}）")

                return {
                    "success": True,
                    "sql": sql,
                    "result": df,
                    "retries": attempt,
                    "execution_time_ms": execution_time,
                    "from_cache": False
                }

            except Exception as e:
                last_error = str(e)
                if self.config.verbose:
                    logger.warning(f"SQL 查询失败（尝试 {attempt + 1}/{self.config.max_retries}）: {last_error}")

                if attempt >= self.config.max_retries - 1:
                    break

        return {
            "success": False,
            "sql": sql,
            "result": None,
            "error": last_error,
            "retries": self.config.max_retries,
            "execution_time_ms": (time.time() - start_time) * 1000,
            "from_cache": False
        }

    def _build_prompt_optimized(
        self,
        question: str,
        data_context: Optional[str] = None,
        last_error: Optional[str] = None
    ) -> str:
        """构建优化的 Prompt（使用缓存组件 + 动态示例）"""

        prompt_parts = [
            "# SQL 查询助手\n",
            "你是一个专业的 SQL 查询助手，专门查询汽车测试数据库。\n",
        ]

        # Schema（使用缓存）
        if self.config.prompt_cache_enabled and self._schema_cache is None:
            self._schema_cache = self.schema_manager.get_schema()
        schema_str = self._schema_cache if self.config.prompt_cache_enabled else self.schema_manager.get_schema()

        prompt_parts.extend([
            "## 数据库 Schema\n",
            schema_str,
            "\n## 业务知识（简版）\n"
        ])

        # 业务知识（使用缓存，但提供简版）
        if self.config.prompt_cache_enabled and self._business_knowledge_cache is None:
            self._business_knowledge_cache = BusinessKnowledge.get_knowledge()

        # 只提取关键信息
        bk_lines = (self._business_knowledge_cache if self.config.prompt_cache_enabled else BusinessKnowledge.get_knowledge()).split('\n')
        bk_essential = [line for line in bk_lines if any(kw in line for kw in ['test_week', 'severity', 'status', '通过率', '构建SQL', 'COUNT', 'SUM', 'AVG'])]
        prompt_parts.extend(bk_essential)

        # 动态选择示例
        selected_examples = DynamicExampleSelector.select_examples(question, limit=3)
        prompt_parts.extend([
            "\n## 相关示例\n",
            DynamicExampleSelector.get_formatted_examples(selected_examples)
        ])

        # 添加数据上下文
        if data_context:
            prompt_parts.append("\n## 当前数据上下文\n")
            # 限制上下文长度
            if len(data_context) > 500:
                data_context = data_context[:500] + "..."
            prompt_parts.append(data_context)

        # 添加历史错误
        if last_error:
            prompt_parts.append(f"\n## 上次错误\n{last_error}\n请根据错误修正 SQL。")

        # 用户问题
        prompt_parts.append(f"\n## 用户问题\n{question}\n")
        prompt_parts.append("请生成 SQL 查询语句。只输出 SQL，不要任何解释或多余文字。")

        return "\n".join(prompt_parts)

    def _generate_cache_key(self, question: str, data_context: Optional[str] = None) -> str:
        """生成缓存键（优化版：哈希压缩）"""
        import hashlib
        key_base = question.lower()
        if data_context:
            key_base += f"|{data_context[:200]}"
        return hashlib.md5(key_base.encode()).hexdigest()

    def clear_cache(self):
        """清空查询缓存"""
        self._query_cache.clear()
        logger.info("查询缓存已清空")

    def close(self):
        """关闭引擎，释放资源"""
        if self.connection_pool:
            self.connection_pool.close_all()
            logger.info("连接池已关闭")


# ============================================================================
# 快捷函数
# ============================================================================

def create_sql_engine_optimized(
    db_path: str = "database/local_data.db",
    **kwargs
) -> SQLQueryEngineOptimized:
    """创建优化的 SQL 查询引擎"""
    config = SQLQueryConfigOptimized(db_path=db_path, **kwargs)
    return SQLQueryEngineOptimized(config)


# ============================================================================
# 兼容性包装器（透明替换）
# ============================================================================

# 导入原始类
from sql_query_engine import SQLQueryEngine

# 如果需要透明替换，可以：
# SQLQueryEngine = SQLQueryEngineOptimized
# 但为了兼容性，建议显式使用 SQLQueryEngineOptimized


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="优化的 SQL 查询引擎测试")
    parser.add_argument("--question", "-q", type=str, help="测试问题")
    parser.add_argument("--db", "-d", type=str, default="database/local_data.db", help="数据库路径")
    parser.add_argument("--cache-size", "-c", type=int, default=100, help="缓存大小")
    parser.add_argument("--benchmark", "-b", action="store_true", help="性能基准测试")

    args = parser.parse_args()

    # 创建优化的引擎
    engine = create_sql_engine_optimized(
        db_path=args.db,
        cache_max_size=args.cache_size
    )

    # 基准测试
    if args.benchmark:
        print("=" * 60)
        print("性能基准测试")
        print("=" * 60)

        test_questions = [
            "统计所有缺陷的数量",
            "各模块的缺陷数量统计",
            "Critical 级别的缺陷数量",
            "测试通过率",
            "缺陷趋势分析（按月）"
        ]

        for q in test_questions:
            print(f"\n问题: {q}")

            # 不使用缓存
            start = time.time()
            result = engine.query(q, llm_generate_func=lambda p: f"SELECT COUNT(*) FROM defects", use_cache=False)
            no_cache_time = (time.time() - start) * 1000

            # 使用缓存
            start = time.time()
            result = engine.query(q, llm_generate_func=lambda p: f"SELECT COUNT(*) FROM defects", use_cache=True)
            cache_time = (time.time() - start) * 1000

            speedup = no_cache_time / cache_time if cache_time > 0 else 0

            print(f"  无缓存: {no_cache_time:.2f}ms")
            print(f"  有缓存: {cache_time:.2f}ms")
            print(f"  加速比: {speedup:.2f}x")

    # 单个问题测试
    if args.question:
        print("=" * 60)
        print(f"问题: {args.question}")
        print("=" * 60)

        # 测试动态示例选择
        selected = DynamicExampleSelector.select_examples(args.question, limit=3)
        print("\n动态选择的示例:")
        for i, ex in enumerate(selected, 1):
            print(f"  {i}. {ex['question']}")

        print("\n" + "=" * 60)
        print("生成的 Prompt（前 500 字符）:")
        print("=" * 60)
        print(engine._build_prompt_optimized(args.question)[:500])

    # 清理
    engine.close()
