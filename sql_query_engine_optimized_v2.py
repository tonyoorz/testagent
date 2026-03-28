#!/usr/bin/env python3
"""
优化的 SQL 查询引擎

在原版基础上集成增强的 Prompt 构建器，提高 SQL 生成准确率

改进：
1. 集成增强的 Prompt 构建器
2. 添加思考过程引导
3. 增强错误分析
4. 添加 SQL 质量检查
5. 改进 Few-shot 示例展示

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import sqlite3
import re
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import pandas as pd

# 导入基础组件
from sql_query_engine import (
    SQLQueryConfig,
    SchemaManager,
    SQLValidator,
    BusinessKnowledge,
    FewShotExamples
)

# 导入增强组件
from enhanced_prompt_builder import (
    EnhancedPromptBuilder,
    PromptOptimizationConfig,
    create_enhanced_prompt_builder
)

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class OptimizedQueryConfig(SQLQueryConfig):
    """优化的查询配置"""
    use_enhanced_prompt: bool = True  # 使用增强的 Prompt
    prompt_config: PromptOptimizationConfig = None  # Prompt 优化配置

    def __post_init__(self):
        if self.prompt_config is None:
            self.prompt_config = PromptOptimizationConfig()


class OptimizedSQLQueryEngine:
    """优化的 SQL 查询引擎"""

    def __init__(self, config: Optional[OptimizedQueryConfig] = None):
        """
        初始化优化的 SQL 查询引擎

        Args:
            config: 优化配置
        """
        self.config = config or OptimizedQueryConfig()

        # 初始化基础组件
        self.schema_manager = SchemaManager(self.config.db_path)
        self.validator = SQLValidator(self.config.dangerous_keywords)
        self._query_cache = {}

        # 初始化增强的 Prompt 构建器
        if self.config.use_enhanced_prompt:
            self.prompt_builder = create_enhanced_prompt_builder(self.schema_manager)
            logger.info("使用增强的 Prompt 构建器")
        else:
            self.prompt_builder = None
            logger.info("使用基础 Prompt 构建")

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

        Args:
            question: 自然语言问题
            llm_generate_func: LLM 生成函数，接收 prompt 返回 SQL
            data_context: 额外的数据上下文（如当前筛选的数据）
            use_cache: 是否使用缓存

        Returns:
            {
                "success": bool,
                "sql": str,
                "result": pd.DataFrame,
                "error": Optional[str],
                "retries": int,
                "execution_time_ms": float,
                "attempt_info": List[Dict]  # 每次尝试的信息
            }
        """
        import time
        start_time = time.time()

        # 检查缓存
        cache_key = self._generate_cache_key(question, data_context)
        if use_cache and self.config.enable_cache and cache_key in self._query_cache:
            cached = self._query_cache[cache_key]
            if (time.time() - cached['timestamp']) < self.config.cache_ttl_seconds:
                if self.config.verbose:
                    logger.info(f"使用缓存结果: {question[:50]}...")
                return {
                    "success": True,
                    "sql": cached['sql'],
                    "result": cached['result'],
                    "retries": 0,
                    "execution_time_ms": (time.time() - start_time) * 1000,
                    "from_cache": True,
                    "attempt_info": []
                }

        # 生成 SQL
        sql = None
        last_error = None
        attempt_info = []

        for attempt in range(self.config.max_retries):
            attempt_start = time.time()

            try:
                # 构建 Prompt（使用增强版或基础版）
                prompt = self._build_prompt(
                    question,
                    data_context,
                    last_error,
                    attempt + 1
                )

                # 调用 LLM 生成 SQL
                sql = llm_generate_func(prompt)

                # 清理 SQL
                sql = self.validator.sanitize_sql(sql)

                # 验证 SQL
                is_valid, error_msg = self.validator.validate(sql)
                if not is_valid:
                    raise ValueError(error_msg)

                # 执行 SQL
                conn = sqlite3.connect(self.config.db_path)
                df = pd.read_sql_query(sql, conn)
                conn.close()

                execution_time = (time.time() - start_time) * 1000
                attempt_time = (time.time() - attempt_start) * 1000

                # 记录尝试信息
                attempt_info.append({
                    "attempt": attempt + 1,
                    "success": True,
                    "sql": sql,
                    "time_ms": attempt_time
                })

                # 缓存结果
                if self.config.enable_cache:
                    self._query_cache[cache_key] = {
                        'sql': sql,
                        'result': df,
                        'timestamp': time.time()
                    }

                if self.config.verbose:
                    logger.info(
                        f"SQL 查询成功（尝试 {attempt + 1}/{self.config.max_retries}，"
                        f"耗时 {attempt_time:.1f}ms）"
                    )

                return {
                    "success": True,
                    "sql": sql,
                    "result": df,
                    "retries": attempt,
                    "execution_time_ms": execution_time,
                    "from_cache": False,
                    "attempt_info": attempt_info
                }

            except Exception as e:
                last_error = str(e)
                attempt_time = (time.time() - attempt_start) * 1000

                # 记录尝试信息
                attempt_info.append({
                    "attempt": attempt + 1,
                    "success": False,
                    "sql": sql,
                    "error": last_error,
                    "time_ms": attempt_time
                })

                if self.config.verbose:
                    logger.warning(
                        f"SQL 查询失败（尝试 {attempt + 1}/{self.config.max_retries}，"
                        f"耗时 {attempt_time:.1f}ms）: {last_error}"
                    )

                if attempt >= self.config.max_retries - 1:
                    break

        return {
            "success": False,
            "sql": sql,
            "result": None,
            "error": last_error,
            "retries": self.config.max_retries,
            "execution_time_ms": (time.time() - start_time) * 1000,
            "from_cache": False,
            "attempt_info": attempt_info
        }

    def _build_prompt(
        self,
        question: str,
        data_context: Optional[str] = None,
        last_error: Optional[str] = None,
        attempt: int = 1
    ) -> str:
        """
        构建 SQL 生成 Prompt（支持增强版和基础版）

        Args:
            question: 用户问题
            data_context: 数据上下文
            last_error: 上次错误
            attempt: 尝试次数

        Returns:
            构建的 Prompt
        """
        # 使用增强的 Prompt 构建器
        if self.prompt_builder:
            return self.prompt_builder.build_prompt(
                question,
                data_context,
                last_error,
                attempt
            )

        # 使用基础 Prompt 构建
        return self._build_basic_prompt(question, data_context, last_error)

    def _build_basic_prompt(
        self,
        question: str,
        data_context: Optional[str] = None,
        last_error: Optional[str] = None
    ) -> str:
        """
        构建基础 Prompt（向后兼容）

        Args:
            question: 用户问题
            data_context: 数据上下文
            last_error: 上次错误

        Returns:
            基础 Prompt
        """
        prompt_parts = [
            "# SQL 查询助手\n",
            "你是一个专业的 SQL 查询助手，专门查询汽车测试数据库。\n",
            "## 数据库 Schema\n",
            self.schema_manager.get_schema(),
            "\n## 业务知识\n",
            BusinessKnowledge.get_knowledge(),
            "\n## 查询示例\n",
            FewShotExamples.get_examples(limit=5)
        ]

        # 添加相似示例
        similar_example = FewShotExamples.find_similar_example(question)
        if similar_example:
            prompt_parts.append("\n## 相似问题参考\n")
            prompt_parts.append(similar_example)

        # 添加数据上下文
        if data_context:
            prompt_parts.append("\n## 当前数据上下文\n")
            prompt_parts.append(data_context)

        # 添加历史错误
        if last_error:
            prompt_parts.append(f"\n## 上次错误\n{last_error}\n请根据错误修正 SQL。")

        # 用户问题
        prompt_parts.append(f"\n## 用户问题\n{question}\n")
        prompt_parts.append("请生成 SQL 查询语句。只输出 SQL，不要任何解释或多余文字。")

        return "\n".join(prompt_parts)

    def _generate_cache_key(self, question: str, data_context: Optional[str] = None) -> str:
        """生成缓存键"""
        key = question.lower()
        if data_context:
            key += f"|{data_context[:100]}"
        return key

    def clear_cache(self):
        """清空查询缓存"""
        self._query_cache.clear()
        logger.info("查询缓存已清空")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取引擎统计信息

        Returns:
            统计信息字典
        """
        return {
            "cache_size": len(self._query_cache),
            "cache_enabled": self.config.enable_cache,
            "enhanced_prompt": self.config.use_enhanced_prompt,
            "max_retries": self.config.max_retries,
            "prompt_optimizations": {
                "thinking_process": self.config.prompt_config.include_thinking_process,
                "quality_checks": self.config.prompt_config.include_quality_checks,
                "common_errors": self.config.prompt_config.include_common_errors,
                "best_practices": self.config.prompt_config.include_best_practices,
                "few_shot_count": self.config.prompt_config.few_shot_examples_count,
                "structured_examples": self.config.prompt_config.use_structured_examples
            }
        }


# ============================================================================
# 工厂函数
# ============================================================================

def create_optimized_sql_query_engine(
    db_path: Optional[str] = None,
    use_enhanced_prompt: bool = True
) -> OptimizedSQLQueryEngine:
    """
    创建优化的 SQL 查询引擎

    Args:
        db_path: 数据库路径
        use_enhanced_prompt: 是否使用增强的 Prompt

    Returns:
        OptimizedSQLQueryEngine 实例
    """
    config = OptimizedQueryConfig(
        db_path=db_path,
        use_enhanced_prompt=use_enhanced_prompt
    )

    return OptimizedSQLQueryEngine(config)
