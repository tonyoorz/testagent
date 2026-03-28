#!/usr/bin/env python3
"""
增强的 AI Chat Manager with Optimized SQL

集成优化的 SQL 查询引擎，提供更好的 SQL 生成准确率

改进：
1. 集成优化的 SQL 查询引擎
2. 增强的智能路由
3. 改进的自然语言答案生成
4. 更好的错误处理
5. 性能监控

使用方法：
from ai_chat_with_sql_optimized import AIChatWithSQLOptimized
chat = AIChatWithSQLOptimized()
result = chat.ask("最近一周的测试通过率是多少？")

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional, Callable, Tuple
from datetime import datetime
from dataclasses import dataclass, field

# 导入优化的 SQL 查询引擎
from sql_query_engine_optimized_v2 import (
    OptimizedSQLQueryEngine,
    OptimizedQueryConfig,
    create_optimized_sql_query_engine
)

# 导入原有的 AI Chat Manager 组件
try:
    from ai_chat_manager import (
        DeepSeekStreamingChat,
        streaming_data,
        streaming_lock,
        DEEPSEEK_API_KEY,
        DEEPSEEK_API_BASE,
        DEEPSEEK_MODEL,
        DEFAULT_TEMPERATURE,
        DEFAULT_MAX_TOKENS
    )
except ImportError:
    # 降级：从 config_center 读取配置
    try:
        from config_center import cfg
        DEEPSEEK_API_KEY = cfg.DEEPSEEK_API_KEY
        DEEPSEEK_API_BASE = cfg.DEEPSEEK_API_BASE
        DEEPSEEK_MODEL = cfg.DEEPSEEK_MODEL
    except ImportError:
        DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
        DEEPSEEK_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 2000
    
    # 创建简单的占位类
    class DeepSeekStreamingChat:
        def __init__(self, *args, **kwargs):
            pass
        
        def complete(self, prompt: str, **kwargs) -> str:
            """简单的 LLM 调用（需要实现）"""
            import openai
            client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_API_BASE
            )
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS
            )
            return response.choices[0].message.content
    
    streaming_data = {}
    streaming_lock = __import__('threading').Lock()

import pandas as pd

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 查询统计
# ============================================================================

@dataclass
class QueryStats:
    """查询统计"""
    total_queries: int = 0
    sql_queries: int = 0
    llm_queries: int = 0
    successful_sql: int = 0
    failed_sql: int = 0
    cache_hits: int = 0
    total_time_ms: float = 0.0
    query_history: List[Dict[str, Any]] = field(default_factory=list)

    def add_query(self, query_type: str, success: bool, time_ms: float, from_cache: bool = False):
        """添加查询记录"""
        self.total_queries += 1

        if query_type == "sql":
            self.sql_queries += 1
            if success:
                self.successful_sql += 1
            else:
                self.failed_sql += 1
            if from_cache:
                self.cache_hits += 1
        else:
            self.llm_queries += 1

        self.total_time_ms += time_ms

        # 记录历史（最近 100 条）
        self.query_history.append({
            "timestamp": datetime.now().isoformat(),
            "type": query_type,
            "success": success,
            "time_ms": time_ms,
            "from_cache": from_cache
        })

        if len(self.query_history) > 100:
            self.query_history.pop(0)

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        sql_success_rate = (self.successful_sql / self.sql_queries * 100) if self.sql_queries > 0 else 0
        avg_time = (self.total_time_ms / self.total_queries) if self.total_queries > 0 else 0
        cache_hit_rate = (self.cache_hits / self.sql_queries * 100) if self.sql_queries > 0 else 0

        return {
            "total_queries": self.total_queries,
            "sql_queries": self.sql_queries,
            "llm_queries": self.llm_queries,
            "sql_success_rate": f"{sql_success_rate:.1f}%",
            "avg_time_ms": f"{avg_time:.1f}",
            "cache_hit_rate": f"{cache_hit_rate:.1f}%"
        }


# ============================================================================
# 增强的 AI Chat with SQL
# ============================================================================

class AIChatWithSQLOptimized:
    """带优化的 SQL 查询能力的 AI Chat Manager"""

    def __init__(
        self,
        db_path: str = None,
        config: OptimizedQueryConfig = None,
        use_enhanced_prompt: bool = True,
        llm_generate_func: Optional[Callable] = None
    ):
        """
        初始化

        Args:
            db_path: 数据库路径
            config: SQL 查询配置
            use_enhanced_prompt: 是否使用增强的 Prompt
            llm_generate_func: 自定义 LLM 生成函数（用于测试）
        """
        # 初始化优化的 SQL 查询引擎
        if config:
            self.sql_engine = OptimizedSQLQueryEngine(config)
        else:
            self.sql_engine = create_optimized_sql_query_engine(
                db_path=db_path,
                use_enhanced_prompt=use_enhanced_prompt
            )

        # 使用自定义或默认的 LLM
        self.llm_generate_func = llm_generate_func
        if self.llm_generate_func is None:
            # 初始化 DeepSeek 聊天
            try:
                self.chatbot = DeepSeekStreamingChat()
                logger.info("DeepSeek 聊天机器人初始化成功")
            except Exception as e:
                logger.warning(f"DeepSeek 聊天机器人初始化失败: {e}，使用降级方案")
                self.chatbot = DeepSeekStreamingChat()

        # 初始化查询统计
        self.stats = QueryStats()

        logger.info("增强的 AI Chat with SQL 初始化完成")

    def ask(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        enable_sql: bool = True,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        提问并回答

        Args:
            question: 用户问题
            data_context: 当前数据上下文（可选）
            enable_sql: 是否启用 SQL 查询
            use_cache: 是否使用 SQL 查询缓存

        Returns:
            {
                "success": bool,
                "answer": str,
                "sql": Optional[str],
                "data": Optional[pd.DataFrame],
                "source": "sql" | "llm",
                "error": Optional[str],
                "stats": Optional[Dict[str, Any]]
            }
        """
        import time
        start_time = time.time()

        try:
            # 判断查询类型
            query_type, confidence = self._classify_query(question, data_context)

            # 根据查询类型路由
            if enable_sql and query_type == "sql" and confidence > 0.7:
                result = self._ask_with_sql(
                    question,
                    data_context,
                    use_cache
                )
                query_type_str = "sql"
            else:
                result = self._ask_with_llm(question, data_context)
                query_type_str = "llm"

            # 记录统计
            elapsed_time = (time.time() - start_time) * 1000
            self.stats.add_query(
                query_type=query_type_str,
                success=result["success"],
                time_ms=elapsed_time,
                from_cache=result.get("from_cache", False)
            )

            # 添加统计信息
            result["stats"] = self.stats.get_summary()

            return result

        except Exception as e:
            logger.error(f"查询失败: {e}")
            elapsed_time = (time.time() - start_time) * 1000
            self.stats.add_query(
                query_type="llm",
                success=False,
                time_ms=elapsed_time
            )

            return {
                "success": False,
                "answer": f"查询过程中出现错误: {str(e)}",
                "source": "llm",
                "error": str(e),
                "stats": self.stats.get_summary()
            }

    def _classify_query(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None
    ) -> Tuple[str, float]:
        """
        分类查询类型

        Args:
            question: 用户问题
            data_context: 数据上下文

        Returns:
            (query_type, confidence)
            query_type: "sql" 或 "llm"
            confidence: 0-1 之间的置信度
        """
        # SQL 查询关键词
        sql_keywords = [
            ("统计", 0.9), ("数量", 0.9), ("查询", 0.9),
            ("通过率", 0.95), ("覆盖率", 0.95),
            ("缺陷", 0.85), ("测试", 0.8),
            ("排名", 0.9), ("最高", 0.85), ("最低", 0.85), ("平均", 0.85),
            ("趋势", 0.8), ("对比", 0.8), ("分布", 0.8),
            ("top", 0.9), ("前", 0.7),
            ("最近", 0.8), ("本周", 0.85), ("本月", 0.85),
            ("join", 0.9), ("关联", 0.8)
        ]

        # 知识问答关键词
        llm_keywords = [
            ("是什么", 0.9), ("为什么", 0.9), ("如何", 0.9),
            ("解释", 0.85), ("说明", 0.85),
            ("建议", 0.8), ("改进", 0.8)
        ]

        question_lower = question.lower()

        # 计算 SQL 查询得分
        sql_score = 0.0
        for keyword, weight in sql_keywords:
            if keyword in question_lower:
                sql_score += weight

        # 计算 LLM 查询得分
        llm_score = 0.0
        for keyword, weight in llm_keywords:
            if keyword in question_lower:
                llm_score += weight

        # 考虑数据上下文
        if data_context is not None and not data_context.empty:
            sql_score += 0.2

        # 归一化
        total_score = sql_score + llm_score
        if total_score > 0:
            sql_confidence = sql_score / total_score
        else:
            sql_confidence = 0.5

        # 判断类型
        query_type = "sql" if sql_confidence > 0.5 else "llm"
        confidence = max(sql_confidence, 1 - sql_confidence)

        return query_type, confidence

    def _ask_with_sql(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """使用 SQL 查询回答"""

        # 准备数据上下文
        data_context_str = None
        if data_context is not None and not data_context.empty:
            data_context_str = f"""
当前筛选的数据样本（前 3 行）：
{data_context.head(3).to_string()}
总行数: {len(data_context)}
"""

        # 调用 SQL 查询引擎
        # 使用自定义 LLM 生成函数或默认的 chatbot.complete
        llm_func = self.llm_generate_func or self.chatbot.complete

        result = self.sql_engine.query(
            question=question,
            llm_generate_func=llm_func,
            data_context=data_context_str,
            use_cache=use_cache
        )

        if result["success"]:
            # 生成自然语言答案
            answer = self._generate_natural_answer(
                question,
                result["sql"],
                result["result"]
            )

            return {
                "success": True,
                "answer": answer,
                "sql": result["sql"],
                "data": result["result"],
                "source": "sql",
                "from_cache": result.get("from_cache", False)
            }
        else:
            # SQL 查询失败，回退到 LLM
            logger.warning(f"SQL 查询失败，回退到 LLM: {result.get('error')}")
            return self._ask_with_llm(question, data_context, sql_error=result.get("error"))

    def _ask_with_llm(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        sql_error: Optional[str] = None
    ) -> Dict[str, Any]:
        """使用 LLM 直接回答"""

        # 构建 Prompt
        prompt = self._build_llm_prompt(question, data_context, sql_error)

        # 调用 LLM（使用自定义函数或默认的 chatbot.complete）
        llm_func = self.llm_generate_func or self.chatbot.complete

        try:
            answer = llm_func(prompt)

            return {
                "success": True,
                "answer": answer,
                "source": "llm"
            }
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {
                "success": False,
                "answer": f"AI 回答失败: {str(e)}",
                "source": "llm",
                "error": str(e)
            }

    def _generate_natural_answer(
        self,
        question: str,
        sql: str,
        data: pd.DataFrame
    ) -> str:
        """
        生成自然语言答案

        Args:
            question: 用户问题
            sql: SQL 查询语句
            data: 查询结果

        Returns:
            自然语言答案
        """
        # 简化版：直接返回结果
        if data.empty:
            return f"查询完成，但没有找到匹配的数据。\n\nSQL: {sql}"

        # 构建答案
        answer = f"查询完成！\n\n"

        # 添加数据摘要
        answer += f"找到 {len(data)} 条记录。\n\n"

        # 添加数据预览（前 5 行）
        if len(data) > 5:
            answer += f"数据预览（前 5 行）:\n"
            answer += data.head(5).to_string(index=False)
            answer += f"\n\n... (共 {len(data)} 条记录)"
        else:
            answer += f"查询结果:\n"
            answer += data.to_string(index=False)

        # 添加 SQL
        answer += f"\n\n生成的 SQL:\n{sql}"

        return answer

    def _build_llm_prompt(
        self,
        question: str,
        data_context: Optional[pd.DataFrame] = None,
        sql_error: Optional[str] = None
    ) -> str:
        """构建 LLM Prompt"""

        prompt_parts = [
            "你是一个专业的数据分析助手。\n\n",
            "请回答用户的问题。\n\n"
        ]

        # 添加数据上下文
        if data_context is not None and not data_context.empty:
            prompt_parts.append("当前数据上下文：\n")
            prompt_parts.append(data_context.head(5).to_string(index=False))
            prompt_parts.append("\n\n")

        # 添加 SQL 错误信息
        if sql_error:
            prompt_parts.append("注意：SQL 查询失败，请直接回答问题而不是生成 SQL。\n")
            prompt_parts.append(f"错误信息: {sql_error}\n\n")

        prompt_parts.append(f"用户问题: {question}\n\n")
        prompt_parts.append("请给出详细、准确的回答。")

        return "".join(prompt_parts)

    def get_stats(self) -> Dict[str, Any]:
        """获取查询统计"""
        return self.stats.get_summary()

    def clear_cache(self):
        """清空 SQL 查询缓存"""
        self.sql_engine.clear_cache()
        logger.info("SQL 查询缓存已清空")

    def get_engine_stats(self) -> Dict[str, Any]:
        """获取引擎统计"""
        return self.sql_engine.get_stats()


# ============================================================================
# 工厂函数
# ============================================================================

def create_ai_chat_with_sql_optimized(
    db_path: str = None,
    use_enhanced_prompt: bool = True
) -> AIChatWithSQLOptimized:
    """
    创建增强的 AI Chat with SQL

    Args:
        db_path: 数据库路径
        use_enhanced_prompt: 是否使用增强的 Prompt

    Returns:
        AIChatWithSQLOptimized 实例
    """
    return AIChatWithSQLOptimized(
        db_path=db_path,
        use_enhanced_prompt=use_enhanced_prompt
    )
