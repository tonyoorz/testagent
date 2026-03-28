#!/usr/bin/env python3
"""
Text-to-SQL Agent for Car Software Defect Management System

基于 LangChain + SQLDatabaseChain 的 text-to-SQL 智能代理。
利用业务规则和 Few-shot 示例，提供准确的自然语言到 SQL 的转换。

核心特性：
- 基于 LangChain 的 SQLDatabaseChain
- 集成业务规则（business_rules.py）
- Few-shot 示例学习（fewshot_examples.md）
- Schema 描述支持（schema_description.md）
- 智能错误恢复和重试
- 查询缓存机制
- 详细的日志记录

使用方法：
from chatdb.text_to_sql_agent import TextToSQLAgent

# 初始化 agent
agent = TextToSQLAgent(
    db_path="database/local_data.db",
    schema_path="chatdb/schema_description.md",
    business_rules_path="chatdb/business_rules.py",
    fewshot_path="chatdb/fewshot_examples.md"
)

# 查询
result = agent.query("查询所有 TopIssue 缺陷，按风险评分降序排列")
print(result["answer"])
print(f"执行的SQL: {result['sql']}")

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import os
import sys
import sqlite3
import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入业务规则
try:
    from chatdb.business_rules import (
        TOP_ISSUE_THRESHOLD,
        HIGH_RUNNER_THRESHOLD,
        LONG_RUNNER_THRESHOLD,
        BUSINESS_TERM_TO_SQL,
        get_top_issue_level,
        is_high_runner,
        is_long_runner,
        get_matrix_severity_group
    )
except ImportError:
    # 如果导入失败，定义基本常量
    TOP_ISSUE_THRESHOLD = 60
    HIGH_RUNNER_THRESHOLD = 3
    LONG_RUNNER_THRESHOLD = 30
    BUSINESS_TERM_TO_SQL = {}
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ business_rules 导入失败，使用默认常量")

# 导入新模块（业务规则解释器、业务语义理解、业务洞察生成器）
try:
    from chatdb.business_rule_explainer import BusinessRuleExplainer
    from chatdb.business_semantics import BusinessSemantics
    from chatdb.insight_generator import InsightGenerator
    NEW_MODULES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ 新模块导入失败: {e}")
    NEW_MODULES_AVAILABLE = False

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 配置类
# ============================================================================

@dataclass
class TextToSQLAgentConfig:
    """Text-to-SQL Agent 配置"""
    db_path: str = "database/local_data.db"
    schema_path: str = "chatdb/schema_description.md"
    business_rules_path: str = "chatdb/business_rules.py"
    fewshot_path: str = "chatdb/fewshot_examples.md"
    
    # LLM 配置
    model_name: str = "deepseek-chat"
    temperature: float = 0.1  # 低温度提高准确性
    max_tokens: int = 2000
    
    # 重试配置
    max_retries: int = 3
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600  # 缓存 1 小时
    
    # 安全配置
    dangerous_keywords: List[str] = field(default_factory=lambda: [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT", "CREATE"
    ])
    allow_write_operations: bool = False
    
    # 调试配置
    verbose: bool = True
    log_sql: bool = True
    
    # 新模块配置
    enable_business_explanation: bool = True  # 启用业务规则解释
    enable_business_semantics: bool = True   # 启用业务语义理解
    enable_insight_generation: bool = True  # 启用业务洞察生成


# ============================================================================
# 查询缓存类
# ============================================================================

@dataclass
class CacheEntry:
    """缓存条目"""
    query: str
    sql: str
    result: pd.DataFrame
    timestamp: datetime
    hash: str
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """检查缓存是否过期"""
        return (datetime.now() - self.timestamp).total_seconds() > ttl_seconds


class QueryCache:
    """查询缓存管理器"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, CacheEntry] = {}
    
    def _hash_query(self, query: str) -> str:
        """生成查询哈希"""
        return hashlib.md5(query.encode('utf-8')).hexdigest()
    
    def get(self, query: str) -> Optional[CacheEntry]:
        """获取缓存"""
        hash_key = self._hash_query(query)
        entry = self.cache.get(hash_key)
        
        if entry and not entry.is_expired(self.ttl_seconds):
            logger.info(f"✅ 缓存命中: {query[:50]}...")
            return entry
        
        return None
    
    def set(self, query: str, sql: str, result: pd.DataFrame) -> CacheEntry:
        """设置缓存"""
        hash_key = self._hash_query(query)
        entry = CacheEntry(
            query=query,
            sql=sql,
            result=result.copy(),
            timestamp=datetime.now(),
            hash=hash_key
        )
        self.cache[hash_key] = entry
        logger.info(f"💾 缓存已保存: {query[:50]}...")
        return entry
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        logger.info("🗑️ 缓存已清空")


# ============================================================================
# Schema 描述加载器
# ============================================================================

class SchemaDescriptionLoader:
    """Schema 描述加载器"""
    
    def __init__(self, schema_path: str):
        self.schema_path = schema_path
        self._description = None
    
    def load(self, force_refresh: bool = False) -> str:
        """加载 Schema 描述"""
        if self._description and not force_refresh:
            return self._description
        
        try:
            with open(self.schema_path, 'r', encoding='utf-8') as f:
                self._description = f.read()
            
            logger.info(f"✅ Schema 描述已加载: {self.schema_path}")
            return self._description
        except FileNotFoundError:
            logger.warning(f"⚠️ Schema 描述文件不存在: {self.schema_path}")
            return ""
        except Exception as e:
            logger.error(f"❌ 加载 Schema 描述失败: {e}")
            return ""
    
    def load_business_terms(self) -> Dict[str, str]:
        """从 Schema 描述中提取业务术语映射"""
        description = self.load()
        
        # 提取业务术语映射部分
        match = re.search(r'## 📋 数据库概览.*?(?=##|$)', description, re.DOTALL)
        if not match:
            return {}
        
        terms = {}
        # 这里可以添加更复杂的解析逻辑
        # 目前返回业务规则中定义的映射
        return BUSINESS_TERM_TO_SQL


# ============================================================================
# Few-shot 示例加载器
# =============================================================================

class FewshotExamplesLoader:
    """Few-shot 示例加载器"""
    
    def __init__(self, fewshot_path: str, max_examples: int = 10):
        self.fewshot_path = fewshot_path
        self.max_examples = max_examples
        self._examples = None
    
    def load(self, force_refresh: bool = False) -> List[Dict[str, str]]:
        """加载 Few-shot 示例"""
        if self._examples and not force_refresh:
            return self._examples
        
        try:
            with open(self.fewshot_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 Few-shot 示例
            examples = self._parse_examples(content)
            self._examples = examples[:self.max_examples]
            
            logger.info(f"✅ Few-shot 示例已加载: {len(self._examples)} 个示例")
            return self._examples
        except FileNotFoundError:
            logger.warning(f"⚠️ Few-shot 示例文件不存在: {self.fewshot_path}")
            return []
        except Exception as e:
            logger.error(f"❌ 加载 Few-shot 示例失败: {e}")
            return []
    
    def _parse_examples(self, content: str) -> List[Dict[str, str]]:
        """解析 Few-shot 示例"""
        examples = []
        
        # 按示例分割
        sections = re.split(r'### 示例 \d+\.\d+:', content)
        
        for section in sections[1:]:  # 跳过第一个空部分
            try:
                example = {}
                
                # 提取用户问题
                question_match = re.search(r'\*\*用户问题：\*\*\s*\n>(.*?)\n\n', section, re.DOTALL)
                if question_match:
                    example['question'] = question_match.group(1).strip()
                
                # 提取 SQL 查询
                sql_match = re.search(r'\*\*SQL 查询：\*\*\s*\n```sql\n(.*?)\n```', section, re.DOTALL)
                if sql_match:
                    example['sql'] = sql_match.group(1).strip()
                
                # 提取查询说明
                desc_match = re.search(r'\*\*查询说明：\*\*\s*\n(.*?)\n\n', section, re.DOTALL)
                if desc_match:
                    example['description'] = desc_match.group(1).strip()
                
                if example.get('question') and example.get('sql'):
                    examples.append(example)
            except Exception as e:
                logger.warning(f"⚠️ 解析示例失败: {e}")
                continue
        
        return examples
    
    def get_similar_examples(self, question: str, top_k: int = 3) -> List[Dict[str, str]]:
        """获取与问题最相似的示例"""
        examples = self.load()
        
        if not examples:
            return []
        
        # 简单的关键词匹配
        question_lower = question.lower()
        question_words = set(re.findall(r'\w+', question_lower))
        
        scored = []
        for example in examples:
            example_words = set(re.findall(r'\w+', example['question'].lower()))
            
            # 计算交集比例
            if question_words:
                intersection = question_words & example_words
                score = len(intersection) / len(question_words)
            else:
                score = 0.0
            
            scored.append((score, example))
        
        # 按分数排序，返回前 top_k 个
        scored.sort(key=lambda x: x[0], reverse=True)
        return [example for _, example in scored[:top_k]]


# ============================================================================
# SQL 验证器
# =============================================================================

class SQLValidator:
    """SQL 验证器"""
    
    def __init__(self, dangerous_keywords: List[str], allow_write_operations: bool = False):
        self.dangerous_keywords = dangerous_keywords
        self.allow_write_operations = allow_write_operations
    
    def validate(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        验证 SQL 查询
        
        Returns:
            (is_valid, error_message)
        """
        sql_upper = sql.upper()
        
        # 检查危险操作
        for keyword in self.dangerous_keywords:
            if keyword in sql_upper:
                if not self.allow_write_operations:
                    return False, f"不允许执行 {keyword} 操作"
        
        # 检查是否为 SELECT 查询
        if not sql_upper.strip().startswith('SELECT'):
            if not self.allow_write_operations:
                return False, "只允许执行 SELECT 查询"
        
        # 基本语法检查
        try:
            # 简单的括号匹配检查
            if sql.count('(') != sql.count(')'):
                return False, "SQL 括号不匹配"
            
            # 检查是否有 FROM 子句
            if 'FROM' not in sql_upper:
                return False, "SQL 查询缺少 FROM 子句"
        except Exception as e:
            return False, f"SQL 语法检查失败: {str(e)}"
        
        return True, None


# ============================================================================
# SQL 执行器
# =============================================================================

class SQLExecutor:
    """SQL 执行器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def execute(self, sql: str) -> Tuple[bool, Optional[pd.DataFrame], Optional[str]]:
        """
        执行 SQL 查询
        
        Returns:
            (success, result_df, error_message)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 执行查询
            df = pd.read_sql_query(sql, conn)
            
            conn.close()
            
            logger.info(f"✅ SQL 执行成功，返回 {len(df)} 行数据")
            return True, df, None
        except sqlite3.OperationalError as e:
            error_msg = f"SQL 执行错误: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, None, error_msg
        except Exception as e:
            error_msg = f"SQL 执行异常: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, None, error_msg


# ============================================================================
# Text-to-SQL Agent (基于 LangChain)
# =============================================================================

class TextToSQLAgent:
    """
    Text-to-SQL Agent
    
    集成 LangChain + 业务规则 + Few-shot 学习
    """
    
    def __init__(self, config: TextToSQLAgentConfig = None):
        """
        初始化 Agent
        
        Args:
            config: Agent 配置
        """
        self.config = config or TextToSQLAgentConfig()
        
        # 初始化组件
        self.cache = QueryCache(ttl_seconds=self.config.cache_ttl_seconds)
        self.validator = SQLValidator(
            dangerous_keywords=self.config.dangerous_keywords,
            allow_write_operations=self.config.allow_write_operations
        )
        self.executor = SQLExecutor(self.config.db_path)
        
        # 加载外部资源
        self.schema_loader = SchemaDescriptionLoader(self.config.schema_path)
        self.fewshot_loader = FewshotExamplesLoader(
            self.config.fewshot_path,
            max_examples=10
        )
        
        # 初始化 LangChain 组件
        self._init_langchain()
        
        # 初始化新模块（如果可用）
        self.business_explainer = None
        self.business_semantics = None
        self.insight_generator = None
        
        if NEW_MODULES_AVAILABLE:
            if self.config.enable_business_explanation:
                from chatdb.business_rule_explainer import BusinessRuleExplainer
                self.business_explainer = BusinessRuleExplainer()
                logger.info("✅ 业务规则解释器已初始化")
            
            if self.config.enable_business_semantics:
                from chatdb.business_semantics import BusinessSemantics
                self.business_semantics = BusinessSemantics()
                logger.info("✅ 业务语义理解已初始化")
            
            if self.config.enable_insight_generation:
                from chatdb.insight_generator import InsightGenerator
                self.insight_generator = InsightGenerator()
                logger.info("✅ 业务洞察生成器已初始化")
        
        logger.info("✅ Text-to-SQL Agent 初始化完成")
    
    def _init_langchain(self):
        """初始化 LangChain 组件"""
        try:
            from langchain_community.utilities import SQLDatabase
            from langchain.chains import create_sql_query_chain
            from langchain_openai import ChatOpenAI
            
            # 创建数据库连接
            self.db = SQLDatabase.from_uri(f"sqlite:///{self.config.db_path}")
            
            # 创建 LLM
            self.llm = ChatOpenAI(
                model=self.config.model_name,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                base_url=os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
                api_key=os.environ.get("DEEPSEEK_API_KEY", "")
            )
            
            # 创建 SQL 查询链
            self.sql_chain = create_sql_query_chain(self.llm, self.db)
            
            logger.info("✅ LangChain 组件初始化成功")
        except ImportError as e:
            logger.warning(f"⚠️ LangChain 依赖未安装: {e}")
            self.llm = None
            self.sql_chain = None
        except Exception as e:
            logger.warning(f"⚠️ LangChain 初始化失败: {e}")
            self.llm = None
            self.sql_chain = None
    
    def query(
        self,
        question: str,
        use_cache: bool = None,
        data_context: Optional[str] = None,
        project: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行查询（增强版：支持业务语义理解和项目上下文）
        
        Args:
            question: 用户问题
            use_cache: 是否使用缓存
            data_context: 数据上下文（可选）
            project: 项目名称（可选，用于添加项目上下文）
        
        Returns:
            {
                "success": bool,
                "answer": str,
                "sql": str,
                "data": pd.DataFrame,
                "retries": int,
                "from_cache": bool,
                "execution_time_ms": int,
                "error": Optional[str],
                "context": Optional[Dict]  # 新增：查询上下文信息
                "insights": Optional[List[str]]  # 新增：业务洞察
            }
        """
        start_time = datetime.now()
        use_cache = use_cache if use_cache is not None else self.config.enable_cache
        
        # 业务语义理解（新功能）
        context_info = {}
        insights = []
        
        if self.business_semantics and self.config.enable_business_semantics:
            # 1. 解析时间范围
            time_range = self.business_semantics.parse_time_range(question)
            if time_range:
                context_info['time_range'] = {
                    'start': time_range[0].strftime('%Y-%m-%d %H:%M'),
                    'end': time_range[1].strftime('%Y-%m-%d %H:%M')
                }
                logger.info(f"✅ 识别时间范围: {time_range[0]} ~ {time_range[1]}")
            
            # 2. 识别业务术语
            business_terms = self.business_semantics.identify_business_terms(question)
            if business_terms:
                context_info['business_terms'] = [term['term'] for term in business_terms]
                logger.info(f"✅ 识别业务术语: {context_info['business_terms']}")
            
            # 3. 获取项目上下文
            project_context = self.business_semantics.get_project_context(project or self._extract_project(question))
            if project_context:
                context_info['project'] = project_context
                logger.info(f"✅ 项目上下文: {project_context.get('name', '')}")
            
            # 4. 扩展查询上下文
            expanded_query = self.business_semantics.expand_query_with_context(
                question,
                project or self._extract_project(question)
            )
            
            # 生成查询上下文说明
            query_context_exp = self.business_semantics.explain_query_with_context(
                question,
                project or self._extract_project(question)
            )
            if query_context_exp:
                context_info['query_explanation'] = query_context_exp
        
        # 检查缓存
        if use_cache:
            cached = self.cache.get(question)
            if cached:
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                return {
                    "success": True,
                    "answer": self._generate_natural_answer(
                        question, 
                        cached.sql, 
                        cached.result,
                        context_info=context_info,
                        insights=insights
                    ),
                    "sql": cached.sql,
                    "data": cached.result,
                    "retries": 0,
                    "from_cache": True,
                    "execution_time_ms": int(execution_time),
                    "error": None,
                    "context": context_info,
                    "insights": insights
                }
        
        # 生成 SQL（使用增强的查询上下文）
        query_for_sql = expanded_query if 'expanded_query' in locals() else question
        if 'query_context_exp' in locals() and query_context_exp:
            data_context = f"{data_context}\n\n{query_context_exp}" if data_context else query_context_exp
        
        sql, retries = self._generate_sql(query_for_sql, data_context)
        
        if not sql:
            return {
                "success": False,
                "answer": "无法生成有效的 SQL 查询",
                "sql": None,
                "data": None,
                "retries": retries,
                "from_cache": False,
                "execution_time_ms": 0,
                "error": "SQL 生成失败",
                "context": context_info,
                "insights": insights
            }
        
        # 验证 SQL
        is_valid, error = self.validator.validate(sql)
        if not is_valid:
            return {
                "success": False,
                "answer": f"SQL 验证失败: {error}",
                "sql": sql,
                "data": None,
                "retries": retries,
                "from_cache": False,
                "execution_time_ms": 0,
                "error": error,
                "context": context_info,
                "insights": insights
            }
        
        # 执行 SQL
        success, result, error = self.executor.execute(sql)
        if not success:
            return {
                "success": False,
                "answer": f"SQL 执行失败: {error}",
                "sql": sql,
                "data": None,
                "retries": retries,
                "from_cache": False,
                "execution_time_ms": 0,
                "error": error,
                "context": context_info,
                "insights": insights
            }
        
        # 生成业务洞察（新功能）
        if self.insight_generator and self.config.enable_insight_generation:
            # 如果结果是单行，生成详细的业务洞察
            if len(result) == 1:
                defect_data = result.iloc[0].to_dict()
                
                # 判断是否是 TopIssue/High Runner/Long Runner
                is_topissue = defect_data.get('is_topissue', False)
                ecu_transfers = defect_data.get('ecu_no_of_changes', 0)
                processing_days = defect_data.get('processing_cycle_days', 0)
                
                # 根据业务规则类型生成解释
                if is_topissue and self.business_explainer:
                    explanation = self.business_explainer.explain_top_issue(defect_data)
                    insights.append(explanation)
                
                elif ecu_transfers >= HIGH_RUNNER_THRESHOLD and self.business_explainer:
                    explanation = self.business_explainer.explain_high_runner(defect_data)
                    insights.append(explanation)
                
                elif processing_days >= LONG_RUNNER_THRESHOLD and self.business_explainer:
                    explanation = self.business_explainer.explain_long_runner(defect_data)
                    insights.append(explanation)
            
            # 生成数据集级别的洞察
            if len(result) > 1:
                dataset_insights = self.insight_generator.generate_insights(result)
                if dataset_insights:
                    insights.extend(dataset_insights)
        
        # 保存缓存
        if use_cache:
            self.cache.set(question, sql, result)
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "success": True,
            "answer": self._generate_natural_answer(
                question, 
                sql, 
                result,
                context_info=context_info,
                insights=insights
            ),
            "sql": sql,
            "data": result,
            "retries": retries,
            "from_cache": False,
            "execution_time_ms": int(execution_time),
            "error": None,
            "context": context_info,
            "insights": insights
        }
    
    def _generate_sql(
        self,
        question: str,
        data_context: Optional[str] = None
    ) -> Tuple[Optional[str], int]:
        """
        生成 SQL 查询
        
        Returns:
            (sql, retries)
        """
        # 如果 LangChain 可用，使用 LangChain
        if self.sql_chain:
            try:
                sql = self._generate_sql_with_langchain(question, data_context)
                if sql:
                    return sql, 0
            except Exception as e:
                logger.warning(f"⚠️ LangChain SQL 生成失败: {e}")
        
        # 降级：使用 Few-shot 示例 + 业务规则
        return self._generate_sql_with_fewshot(question, data_context)
    
    def _generate_sql_with_langchain(
        self,
        question: str,
        data_context: Optional[str] = None
    ) -> Optional[str]:
        """使用 LangChain 生成 SQL"""
        try:
            # 构建提示词
            prompt = self._build_langchain_prompt(question, data_context)
            
            # 调用 SQL 链
            result = self.sql_chain.invoke({"question": prompt})
            sql = result.get("result", "").strip()
            
            # 清理 SQL
            sql = self._clean_sql(sql)
            
            if self.config.verbose:
                logger.info(f"🔍 生成的 SQL (LangChain): {sql}")
            
            return sql
        except Exception as e:
            logger.error(f"❌ LangChain SQL 生成失败: {e}")
            return None
    
    def _generate_sql_with_fewshot(
        self,
        question: str,
        data_context: Optional[str] = None
    ) -> Tuple[Optional[str], int]:
        """使用 Few-shot 示例生成 SQL"""
        
        # 获取相似示例
        similar_examples = self.fewshot_loader.get_similar_examples(question)
        
        # 构建提示词
        prompt = self._build_fewshot_prompt(question, similar_examples, data_context)
        
        # 使用 LLM 生成 SQL
        for retry in range(self.config.max_retries):
            try:
                # 如果有 LLM，使用 LLM
                if self.llm:
                    response = self.llm.invoke(prompt)
                    sql = self._extract_sql_from_response(response.content)
                else:
                    # 降级：使用简单匹配
                    sql = self._match_to_example(question, similar_examples)
                
                if sql:
                    sql = self._clean_sql(sql)
                    
                    if self.config.verbose:
                        logger.info(f"🔍 生成的 SQL (Few-shot, 尝试 {retry + 1}): {sql}")
                    
                    return sql, retry
                
            except Exception as e:
                logger.warning(f"⚠️ SQL 生成尝试 {retry + 1} 失败: {e}")
                continue
        
        return None, self.config.max_retries
    
    def _build_langchain_prompt(
        self,
        question: str,
        data_context: Optional[str] = None
    ) -> str:
        """构建 LangChain 提示词"""
        parts = [
            f"用户问题：{question}\n"
        ]
        
        # 添加数据上下文
        if data_context:
            parts.append(f"\n数据上下文：\n{data_context}\n")
        
        # 添加业务规则
        parts.append("\n业务规则：\n")
        parts.append(f"- TopIssue 阈值: {TOP_ISSUE_THRESHOLD}\n")
        parts.append(f"- High Runner 阈值: {HIGH_RUNNER_THRESHOLD}\n")
        parts.append(f"- Long Runner 阈值: {LONG_RUNNER_THRESHOLD}\n")
        
        # 添加业务术语映射
        parts.append("\n业务术语映射：\n")
        for term, condition in list(BUSINESS_TERM_TO_SQL.items())[:5]:
            parts.append(f"- {term}: {condition}\n")
        
        return "".join(parts)
    
    def _build_fewshot_prompt(
        self,
        question: str,
        examples: List[Dict[str, str]],
        data_context: Optional[str] = None
    ) -> str:
        """构建 Few-shot 提示词"""
        parts = [
            "你是一个 SQL 查询专家。请根据以下示例和业务规则，生成对应的 SQL 查询。\n\n"
        ]
        
        # 添加示例
        if examples:
            parts.append("示例：\n")
            for i, example in enumerate(examples[:3], 1):
                parts.append(f"\n示例 {i}:\n")
                parts.append(f"问题：{example['question']}\n")
                parts.append(f"SQL：{example['sql']}\n")
                parts.append(f"说明：{example.get('description', '')}\n")
        
        # 添加业务规则
        parts.append("\n业务规则：\n")
        parts.append(f"- TopIssue 阈值: {TOP_ISSUE_THRESHOLD}\n")
        parts.append(f"- High Runner 阈值: {HIGH_RUNNER_THRESHOLD}\n")
        parts.append(f"- Long Runner 阈值: {LONG_RUNNER_THRESHOLD}\n")
        
        # 添加业务术语映射
        parts.append("\n业务术语映射：\n")
        for term, condition in list(BUSINESS_TERM_TO_SQL.items())[:5]:
            parts.append(f"- {term}: {condition}\n")
        
        # 添加数据上下文
        if data_context:
            parts.append(f"\n数据上下文：\n{data_context}\n")
        
        # 添加当前问题
        parts.append(f"\n当前问题：{question}\n")
        parts.append("\n请生成对应的 SQL 查询（只输出 SQL，不要解释）：\n")
        
        return "".join(parts)
    
    def _clean_sql(self, sql: str) -> str:
        """清理 SQL 查询"""
        # 移除 markdown 标记
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*$', '', sql)
        
        # 移除多余空行
        sql = re.sub(r'\n\s*\n', '\n', sql)
        
        # 移除注释
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        
        # 移除末尾分号
        sql = sql.rstrip().rstrip(';')
        
        return sql.strip()
    
    def _extract_sql_from_response(self, response: str) -> Optional[str]:
        """从响应中提取 SQL"""
        # 尝试提取 markdown 代码块
        match = re.search(r'```sql\n(.*?)\n```', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 尝试提取任何代码块
        match = re.search(r'```\n(.*?)\n```', response, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 如果没有代码块，检查是否直接返回 SQL
        if response.strip().upper().startswith('SELECT'):
            return response.strip()
        
        return None
    
    def _match_to_example(
        self,
        question: str,
        examples: List[Dict[str, str]]
    ) -> Optional[str]:
        """简单匹配到示例"""
        if not examples:
            return None
        
        # 返回最相似示例的 SQL
        return examples[0]['sql']
    
    def _generate_natural_answer(
        self,
        question: str,
        sql: str,
        result: pd.DataFrame,
        context_info: Optional[Dict] = None,
        insights: Optional[List[str]] = None
    ) -> str:
        """
        生成自然语言回答（增强版：支持业务规则解释和业务洞察）
        
        Args:
            question: 原始问题
            sql: SQL 查询
            result: 查询结果
            context_info: 查询上下文（时间范围、项目等）
            insights: 业务洞察列表
        """
        if result.empty:
            return f"查询结果为空。执行的SQL：{sql}"
        
        answer_parts = [f"根据查询，"]
        
        # 1. 显示查询上下文（新功能）
        if context_info:
            context_parts = []
            if 'time_range' in context_info:
                start, end = context_info['time_range']['start'], context_info['time_range']['end']
                context_parts.append(f"📅 时间范围: {start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%Y-%m-%d %H:%M')}")
            
            if 'project' in context_info:
                proj_info = context_info['project']
                context_parts.append(f"📋 项目: {proj_info.get('name', '')}")
                if 'focus' in proj_info:
                    context_parts.append(f"   📝 专注: {proj_info['focus']}")
                if 'common_issues' in proj_info:
                    common_issues = ', '.join(proj_info['common_issues'][:3])
                    context_parts.append(f"   🔍 常见问题: {common_issues}")
            
            if 'business_terms' in context_info:
                context_parts.append(f"🏷️  识别的业务术语: {', '.join(context_info['business_terms'][:3])}")
            
            if context_parts:
                answer_parts.append("\n### 📊 查询上下文\n")
                for part in context_parts:
                    answer_parts.append(f"{part}")
        
        # 2. 简单的结果描述
        if len(result) == 1:
            answer_parts.append(f"\n找到 1 条记录。")
        else:
            answer_parts.append(f"\n找到 {len(result)} 条记录。")
        
        # 3. 显示前几列的值
        if len(result.columns) <= 3:
            for idx, row in result.head(3).iterrows():
                answer_parts.append(f"\n记录 {idx + 1}: " + ", ".join(
                    f"{col}={row[col]}" for col in result.columns
                ))
        else:
            answer_parts.append(f"\n列: {', '.join(result.columns[:5])}")
            answer_parts.append(f"前 3 行:")
            answer_parts.append(result.head(3).to_string())
        
        # 4. 显示业务洞察（新功能）
        if insights:
            answer_parts.append("\n### 💡 业务洞察\n")
            for insight in insights:
                answer_parts.append(f"{insight}")
        
        # 5. 显示执行的 SQL
        if self.config.log_sql:
            answer_parts.append(f"\n### 🔍 执行的 SQL\n")
            answer_parts.append(f"```sql\n{sql}\n```")
        
        return "".join(answer_parts)
    
    def _extract_project(self, question: str) -> Optional[str]:
        """从问题中提取项目名称"""
        projects = ['App', 'IDC', 'IDCevo', 'MGU', 'RSU']
        question_lower = question.lower()
        
        for project in projects:
            if project.lower() in question_lower:
                return project
        
        return None
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()


# ============================================================================
# 工厂函数
# =============================================================================

def create_text_to_sql_agent(
    db_path: str = None,
    schema_path: str = None,
    business_rules_path: str = None,
    fewshot_path: str = None,
    **kwargs
) -> TextToSQLAgent:
    """
    创建 Text-to-SQL Agent
    
    Args:
        db_path: 数据库路径
        schema_path: Schema 描述路径
        business_rules_path: 业务规则路径
        fewshot_path: Few-shot 示例路径
        **kwargs: 其他配置参数
    
    Returns:
        TextToSQLAgent 实例
    """
    config = TextToSQLAgentConfig(
        db_path=db_path or "database/local_data.db",
        schema_path=schema_path or "chatdb/schema_description.md",
        business_rules_path=business_rules_path or "chatdb/business_rules.py",
        fewshot_path=fewshot_path or "chatdb/fewshot_examples.md",
        **kwargs
    )
    
    return TextToSQLAgent(config)


# ============================================================================
# 示例使用
# =============================================================================

if __name__ == "__main__":
    # 示例使用
    agent = create_text_to_sql_agent()
    
    # 测试查询
    test_questions = [
        "查询所有 TopIssue 缺陷，按风险评分降序排列",
        "按项目统计缺陷总数",
        "查询所有 High Runner 缺陷",
        "查询 Long Runner 缺陷（处理周期≥30天）"
    ]
    
    for question in test_questions:
        print(f"\n{'='*60}")
        print(f"问题: {question}")
        print('='*60)
        
        result = agent.query(question)
        
        if result["success"]:
            print(f"✅ 回答: {result['answer']}")
            print(f"🔍 SQL: {result['sql']}")
            print(f"📊 数据行数: {len(result['data'])}")
            print(f"⏱️ 执行时间: {result['execution_time_ms']}ms")
        else:
            print(f"❌ 错误: {result['error']}")
