"""
智能上下文引擎 - 让 Agent 高效理解本地数据

核心能力：
1. 意图理解 - 识别用户需要什么数据
2. 语义检索 - 基于相似度找到最相关的数据
3. 渐进式加载 - 按需加载，控制 Token 消耗
4. 动态窗口管理 - 智能控制上下文大小

对标框架：
- Manus AI 的 Context Engineering
- OpenAI Agents SDK 的 Sessions
- Claude Code 的上下文管理

作者: WorkBuddy
日期: 2026-03-17
版本: 1.0
"""

import os
import re
import json
import sqlite3
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import threading

# 延迟导入，避免依赖问题
try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构定义
# ============================================================================

@dataclass
class Intent:
    """用户意图"""
    query: str  # 原始查询
    data_type: str = "defect"  # defect, test, both
    project: Optional[str] = None
    module: Optional[str] = None  # AIDA/PU 模块
    time_range: str = "all"  # last_week, last_2_weeks, last_month, all
    focus: str = "general"  # trend, risk, coverage, strategy, comparison
    severity: Optional[List[str]] = None
    dimensions: List[str] = field(default_factory=list)  # 分析维度
    confidence: float = 0.0


@dataclass
class Context:
    """上下文数据"""
    content: str  # 上下文文本
    token_count: int = 0
    relevance_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)  # 数据来源
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DataSummary:
    """数据摘要"""
    total_count: int
    time_range: Tuple[str, str]  # (开始时间, 结束时间)
    key_metrics: Dict[str, Any]
    top_items: Dict[str, List[Any]]  # Top N 项目/模块等
    distribution: Dict[str, Dict[str, int]]  # 分布统计


@dataclass
class RetrievalResult:
    """检索结果"""
    records: List[Dict[str, Any]]
    scores: List[float]
    total_found: int
    query_used: str


# ============================================================================
# 意图理解器
# ============================================================================

class IntentAnalyzer:
    """
    意图理解器 - 分析用户问题，提取数据需求
    
    不依赖 LLM，使用规则 + 关键词匹配
    """
    
    # 项目名称映射
    PROJECT_PATTERNS = {
        'abs': ['abs', 'antiblock', '防抱死'],
        'esp': ['esp', 'esc', '车身稳定'],
        'adc': ['adc', 'autopilot', '自动驾驶'],
        'idcevo': ['idcevo', 'idc'],
        'app': ['app', 'application'],
        'bdc': ['bdc', 'domain'],
    }
    
    # 时间范围关键词
    TIME_PATTERNS = {
        'last_week': ['最近一周', '上周', 'past week', 'last week'],
        'last_2_weeks': ['最近两周', '近两周', 'past 2 weeks', 'last 2 weeks'],
        'last_month': ['最近一个月', '上个月', 'past month', 'last month'],
        'last_3_months': ['最近三个月', '近三月', 'past 3 months'],
    }
    
    # 分析焦点关键词
    FOCUS_PATTERNS = {
        'trend': ['趋势', '变化', '走势', 'trend', 'tendency'],
        'risk': ['风险', '高危', '危险', 'risk', 'danger'],
        'coverage': ['覆盖率', '覆盖', '盲区', 'coverage', 'gap'],
        'strategy': ['策略', '建议', '方案', 'strategy', 'recommendation', '建议'],
        'comparison': ['对比', '比较', '差异', 'comparison', 'compare'],
        'root_cause': ['原因', '根因', '根因分析', 'root cause'],
    }
    
    # 严重程度关键词
    SEVERITY_PATTERNS = {
        'Critical': ['critical', '致命', '严重', '高优先级'],
        'Major': ['major', '主要', '重要'],
        'Minor': ['minor', '次要', '轻微', '低优先级'],
    }
    
    def analyze(self, query: str) -> Intent:
        """
        分析用户意图
        
        Args:
            query: 用户问题
            
        Returns:
            Intent: 解析后的意图
        """
        query_lower = query.lower()
        
        intent = Intent(query=query)
        
        # 1. 识别数据类型
        intent.data_type = self._detect_data_type(query_lower)
        
        # 2. 识别项目
        intent.project = self._detect_project(query_lower)
        
        # 3. 识别模块 (AIDA/PU)
        intent.module = self._detect_module(query)
        
        # 4. 识别时间范围
        intent.time_range = self._detect_time_range(query_lower)
        
        # 5. 识别分析焦点
        intent.focus = self._detect_focus(query_lower)
        
        # 6. 识别严重程度
        intent.severity = self._detect_severity(query_lower)
        
        # 7. 识别分析维度
        intent.dimensions = self._detect_dimensions(query_lower)
        
        # 8. 计算置信度
        intent.confidence = self._calculate_confidence(intent)
        
        return intent
    
    def _detect_data_type(self, query: str) -> str:
        """检测数据类型"""
        test_keywords = ['测试', 'test', '覆盖率', '测试用例', 'test case']
        defect_keywords = ['缺陷', 'defect', 'bug', '问题', 'issue']
        
        has_test = any(kw in query for kw in test_keywords)
        has_defect = any(kw in query for kw in defect_keywords)
        
        if has_test and has_defect:
            return 'both'
        elif has_test:
            return 'test'
        elif has_defect:
            return 'defect'
        else:
            return 'defect'  # 默认
    
    def _detect_project(self, query: str) -> Optional[str]:
        """检测项目"""
        for project, patterns in self.PROJECT_PATTERNS.items():
            for pattern in patterns:
                if pattern in query:
                    return project.upper() if project in ['abs', 'esp', 'adc', 'bdc'] else project
        return None
    
    def _detect_module(self, query: str) -> Optional[str]:
        """检测模块 (AIDA/PU)"""
        # AIDA 模式
        aida_match = re.search(r'\baida[:\s]*([a-z0-9_\-\.]+)', query, re.IGNORECASE)
        if aida_match:
            return aida_match.group(1).upper()
        
        # PU 模式
        pu_match = re.search(r'\bpu[:\s]*([a-z0-9_\-\.]+)', query, re.IGNORECASE)
        if pu_match:
            return pu_match.group(1).upper()
        
        return None
    
    def _detect_time_range(self, query: str) -> str:
        """检测时间范围"""
        for time_range, patterns in self.TIME_PATTERNS.items():
            for pattern in patterns:
                if pattern in query:
                    return time_range
        return 'all'
    
    def _detect_focus(self, query: str) -> str:
        """检测分析焦点"""
        for focus, patterns in self.FOCUS_PATTERNS.items():
            for pattern in patterns:
                if pattern in query:
                    return focus
        return 'general'
    
    def _detect_severity(self, query: str) -> Optional[List[str]]:
        """检测严重程度"""
        severities = []
        for severity, patterns in self.SEVERITY_PATTERNS.items():
            for pattern in patterns:
                if pattern in query:
                    severities.append(severity)
                    break
        return severities if severities else None
    
    def _detect_dimensions(self, query: str) -> List[str]:
        """检测分析维度"""
        dimensions = []
        
        dimension_keywords = {
            'project': ['按项目', '各项目', 'by project'],
            'severity': ['按严重程度', '各严重程度', 'by severity'],
            'module': ['按模块', '各模块', 'by module', '按aida'],
            'week': ['按周', '每周', 'weekly', 'by week'],
            'month': ['按月', '每月', 'monthly', 'by month'],
            'team': ['按团队', '各团队', 'by team'],
        }
        
        for dim, keywords in dimension_keywords.items():
            for kw in keywords:
                if kw in query:
                    dimensions.append(dim)
                    break
        
        return dimensions
    
    def _calculate_confidence(self, intent: Intent) -> float:
        """计算意图置信度"""
        score = 0.5  # 基础分
        
        if intent.project:
            score += 0.2
        if intent.time_range != 'all':
            score += 0.1
        if intent.focus != 'general':
            score += 0.1
        if intent.module:
            score += 0.1
        
        return min(1.0, score)


# ============================================================================
# 语义检索器
# ============================================================================

class SemanticRetriever:
    """
    语义检索器 - 基于向量相似度检索数据
    
    支持：
    1. TF-IDF 向量化
    2. 余弦相似度计算
    3. 预计算索引加速
    """
    
    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.doc_vectors: Optional[np.ndarray] = None
        self.doc_ids: List[str] = []
        self.doc_contents: Dict[str, str] = {}
        
        # 简单缓存
        self._cache: Dict[str, RetrievalResult] = {}
        self._cache_lock = threading.Lock()
    
    def build_index(self, records: List[Dict[str, Any]], text_fields: List[str] = None):
        """
        构建语义索引
        
        Args:
            records: 数据记录列表
            text_fields: 用于构建索引的文本字段
        """
        if not HAS_SKLEARN:
            logger.warning("sklearn 未安装，语义检索将降级为关键词匹配")
            return
        
        if text_fields is None:
            text_fields = ['name', 'title', 'description', 'project', 'pu', 'aida']
        
        self.doc_ids = []
        doc_texts = []
        
        for i, record in enumerate(records):
            doc_id = record.get('id', str(i))
            self.doc_ids.append(doc_id)
            
            # 构建文档文本
            text_parts = []
            for field in text_fields:
                if field in record and record[field]:
                    text_parts.append(str(record[field]))
            
            doc_text = ' '.join(text_parts)
            doc_texts.append(doc_text)
            self.doc_contents[doc_id] = doc_text
        
        # 构建 TF-IDF 向量
        self.vectorizer = TfidfVectorizer(
            max_features=1000,
            ngram_range=(1, 2),
            stop_words='english'
        )
        
        self.doc_vectors = self.vectorizer.fit_transform(doc_texts)
        
        logger.info(f"语义索引构建完成: {len(self.doc_ids)} 条记录")
    
    def search(
        self, 
        query: str, 
        top_k: int = 20,
        min_score: float = 0.1
    ) -> RetrievalResult:
        """
        语义搜索
        
        Args:
            query: 查询文本
            top_k: 返回前 K 个结果
            min_score: 最小相似度阈值
            
        Returns:
            RetrievalResult: 检索结果
        """
        # 检查缓存
        cache_key = hashlib.md5(f"{query}:{top_k}".encode()).hexdigest()
        if self.use_cache:
            with self._cache_lock:
                if cache_key in self._cache:
                    return self._cache[cache_key]
        
        if not HAS_SKLEARN or self.vectorizer is None:
            # 降级为关键词匹配
            return self._keyword_search(query, top_k)
        
        # 向量化查询
        query_vector = self.vectorizer.transform([query])
        
        # 计算相似度
        similarities = cosine_similarity(query_vector, self.doc_vectors)[0]
        
        # 排序并筛选
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        records = []
        scores = []
        
        for idx in top_indices:
            score = similarities[idx]
            if score >= min_score:
                records.append({'id': self.doc_ids[idx]})
                scores.append(float(score))
        
        result = RetrievalResult(
            records=records,
            scores=scores,
            total_found=len(records),
            query_used=query
        )
        
        # 缓存结果
        if self.use_cache:
            with self._cache_lock:
                self._cache[cache_key] = result
        
        return result
    
    def _keyword_search(self, query: str, top_k: int) -> RetrievalResult:
        """关键词匹配（降级方案）"""
        query_words = set(query.lower().split())
        
        results = []
        for doc_id, content in self.doc_contents.items():
            content_words = set(content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score = overlap / len(query_words)
                results.append((doc_id, score))
        
        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:top_k]
        
        return RetrievalResult(
            records=[{'id': doc_id} for doc_id, _ in results],
            scores=[score for _, score in results],
            total_found=len(results),
            query_used=query
        )


# ============================================================================
# 数据摘要生成器
# ============================================================================

class DataSummarizer:
    """
    数据摘要生成器 - 生成数据概览
    
    用于快速了解数据全貌，而不加载全部数据
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_defect_summary(
        self, 
        project: Optional[str] = None,
        time_range: str = "all"
    ) -> DataSummary:
        """获取缺陷数据摘要"""
        conn = sqlite3.connect(self.db_path)
        
        try:
            # 构建查询条件
            conditions = []
            params = []
            
            if project:
                conditions.append("tproject = ?")
                params.append(project)
            
            if time_range != "all":
                time_condition = self._get_time_condition(time_range)
                conditions.append(time_condition)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # 查询总数
            count_sql = f"SELECT COUNT(*) FROM defects WHERE {where_clause}"
            total_count = conn.execute(count_sql, params).fetchone()[0]
            
            # 查询时间范围
            time_sql = f"""
                SELECT MIN(creation_time), MAX(creation_time) 
                FROM defects 
                WHERE {where_clause}
            """
            time_result = conn.execute(time_sql, params).fetchone()
            time_range_result = (time_result[0] or '', time_result[1] or '')
            
            # 查询关键指标
            metrics_sql = f"""
                SELECT 
                    COUNT(CASE WHEN severity_group = 'Critical' THEN 1 END) as critical_count,
                    COUNT(CASE WHEN topissue = 'TopIssue' THEN 1 END) as topissue_count,
                    COUNT(DISTINCT tproject) as project_count
                FROM defects 
                WHERE {where_clause}
            """
            metrics_result = conn.execute(metrics_sql, params).fetchone()
            
            key_metrics = {
                'critical_count': metrics_result[0] or 0,
                'topissue_count': metrics_result[1] or 0,
                'project_count': metrics_result[2] or 0,
            }
            
            # 查询 Top 项目
            top_projects_sql = f"""
                SELECT tproject, COUNT(*) as cnt
                FROM defects
                WHERE {where_clause}
                GROUP BY tproject
                ORDER BY cnt DESC
                LIMIT 10
            """
            top_projects = conn.execute(top_projects_sql, params).fetchall()
            
            # 查询分布
            severity_dist_sql = f"""
                SELECT severity_group, COUNT(*) as cnt
                FROM defects
                WHERE {where_clause}
                GROUP BY severity_group
            """
            severity_dist = dict(conn.execute(severity_dist_sql, params).fetchall())
            
            return DataSummary(
                total_count=total_count,
                time_range=time_range_result,
                key_metrics=key_metrics,
                top_items={'projects': [{'name': p, 'count': c} for p, c in top_projects]},
                distribution={'severity': severity_dist}
            )
            
        finally:
            conn.close()
    
    def get_test_summary(
        self,
        project: Optional[str] = None,
        time_range: str = "all"
    ) -> DataSummary:
        """获取测试数据摘要"""
        conn = sqlite3.connect(self.db_path)
        
        try:
            # 检查表是否存在
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='test_runs'"
            )
            if not cursor.fetchone():
                # 表不存在，返回空摘要
                return DataSummary(
                    total_count=0,
                    time_range=('', ''),
                    key_metrics={'total_tests': 0, 'failed_tests': 0, 'failure_rate': 0},
                    top_items={},
                    distribution={}
                )
            
            conditions = []
            params = []
            
            if project:
                conditions.append("project = ?")
                params.append(project)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # 查询总数和关键指标
            metrics_sql = f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN run_status = 'Failed' THEN 1 END) as failed,
                    COUNT(DISTINCT aida) as aida_count
                FROM test_runs
                WHERE {where_clause}
            """
            metrics_result = conn.execute(metrics_sql, params).fetchone()
            
            total_count = metrics_result[0] or 0
            failed_count = metrics_result[1] or 0
            
            key_metrics = {
                'total_tests': total_count,
                'failed_tests': failed_count,
                'failure_rate': round(failed_count / total_count * 100, 2) if total_count > 0 else 0,
                'aida_count': metrics_result[2] or 0,
            }
            
            return DataSummary(
                total_count=total_count,
                time_range=('', ''),
                key_metrics=key_metrics,
                top_items={},
                distribution={}
            )
            
        finally:
            conn.close()
    
    def _get_time_condition(self, time_range: str) -> str:
        """生成时间查询条件"""
        time_map = {
            'last_week': "creation_time >= datetime('now', '-7 days')",
            'last_2_weeks': "creation_time >= datetime('now', '-14 days')",
            'last_month': "creation_time >= datetime('now', '-30 days')",
            'last_3_months': "creation_time >= datetime('now', '-90 days')",
        }
        return time_map.get(time_range, "1=1")


# ============================================================================
# 核心上下文引擎
# ============================================================================

class ContextEngine:
    """
    智能上下文引擎 - 核心类
    
    功能：
    1. 意图理解
    2. 语义检索
    3. 渐进式加载
    4. 动态窗口管理
    
    使用示例：
    ```python
    engine = ContextEngine(db_path="database/local_data.db")
    
    context = engine.progressive_load(
        query="最近两周 ABS 模块的测试策略建议",
        max_tokens=4000
    )
    
    print(context.content)
    print(f"Token 消耗: {context.token_count}")
    ```
    """
    
    # Token 估算：平均 1 token ≈ 1.5 中文字符 或 0.75 英文单词
    TOKEN_RATIO_CN = 1.5
    TOKEN_RATIO_EN = 4  # 英文单词平均长度
    
    def __init__(
        self,
        db_path: str = None,
        use_semantic_search: bool = True,
        cache_ttl: int = 3600  # 缓存时间（秒）
    ):
        """
        初始化上下文引擎
        
        Args:
            db_path: 数据库路径
            use_semantic_search: 是否启用语义检索
            cache_ttl: 缓存过期时间
        """
        self.db_path = db_path or os.environ.get(
            "DATABASE_PATH",
            "database/local_data.db"
        )
        
        # 初始化组件
        self.intent_analyzer = IntentAnalyzer()
        self.semantic_retriever = SemanticRetriever() if use_semantic_search else None
        self.data_summarizer = DataSummarizer(self.db_path)
        
        # 缓存
        self._context_cache: Dict[str, Context] = {}
        self._cache_ttl = cache_ttl
        self._cache_lock = threading.Lock()
        
        # 预构建索引标记
        self._index_built = False
        
        logger.info(f"ContextEngine 初始化完成，数据库: {self.db_path}")
    
    def build_index(self, force_rebuild: bool = False):
        """
        预构建语义索引（推荐在系统启动时调用）
        
        Args:
            force_rebuild: 是否强制重建
        """
        if self._index_built and not force_rebuild:
            return
        
        if self.semantic_retriever is None:
            return
        
        logger.info("开始构建语义索引...")
        
        # 从数据库加载所有记录
        conn = sqlite3.connect(self.db_path)
        try:
            # 加载缺陷数据
            cursor = conn.execute("""
                SELECT id, name, description, tproject, pu, aida
                FROM defects
                LIMIT 10000
            """)
            
            records = []
            for row in cursor:
                records.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'project': row[3],
                    'pu': row[4],
                    'aida': row[5]
                })
            
            # 构建索引
            self.semantic_retriever.build_index(records)
            self._index_built = True
            
            logger.info(f"语义索引构建完成: {len(records)} 条记录")
            
        finally:
            conn.close()
    
    def progressive_load(
        self,
        query: str,
        max_tokens: int = 4000,
        include_details: bool = True
    ) -> Context:
        """
        渐进式上下文加载 - 核心方法
        
        流程：
        1. 意图理解 → 识别需要什么数据
        2. 数据摘要 → 快速获取数据概览
        3. 语义检索 → 找到最相关的记录
        4. 分层加载 → 按优先级填充上下文
        5. 动态窗口 → 控制 Token 消耗
        
        Args:
            query: 用户问题
            max_tokens: 最大 Token 数
            include_details: 是否包含详细记录
            
        Returns:
            Context: 上下文对象
        """
        start_time = datetime.now()
        
        # 检查缓存
        cache_key = hashlib.md5(f"{query}:{max_tokens}".encode()).hexdigest()
        with self._cache_lock:
            if cache_key in self._context_cache:
                cached_context, cached_time = self._context_cache[cache_key]
                if (datetime.now() - cached_time).seconds < self._cache_ttl:
                    logger.info("使用缓存的上下文")
                    return cached_context
        
        # Step 1: 意图理解
        intent = self.intent_analyzer.analyze(query)
        logger.info(f"意图分析: {intent}")
        
        # Step 2: 准备上下文容器
        context_parts = []
        current_tokens = 0
        sources = []
        
        # Step 3: 分层加载
        
        # 3.1 第一层：项目概览（高优先级，Token 预算 30%）
        overview_budget = int(max_tokens * 0.3)
        if current_tokens < overview_budget:
            overview = self._load_overview(intent)
            overview_tokens = self._estimate_tokens(overview)
            
            if current_tokens + overview_tokens <= overview_budget:
                context_parts.append(overview)
                current_tokens += overview_tokens
                sources.append("overview")
        
        # 3.2 第二层：数据摘要（中优先级，Token 预算 30%）
        summary_budget = int(max_tokens * 0.3)
        if current_tokens < overview_budget + summary_budget:
            summary = self._load_summary(intent)
            summary_tokens = self._estimate_tokens(summary)
            
            if current_tokens + summary_tokens <= overview_budget + summary_budget:
                context_parts.append(summary)
                current_tokens += summary_tokens
                sources.append("summary")
        
        # 3.3 第三层：关键记录（中优先级，Token 预算 30%）
        if include_details:
            details_budget = int(max_tokens * 0.3)
            if current_tokens < overview_budget + summary_budget + details_budget:
                details = self._load_key_records(intent, max_records=20)
                details_tokens = self._estimate_tokens(details)
                
                # 如果超出预算，截断
                if current_tokens + details_tokens > max_tokens:
                    available = max_tokens - current_tokens
                    details = self._truncate_to_tokens(details, available)
                    details_tokens = self._estimate_tokens(details)
                
                if details.strip():
                    context_parts.append(details)
                    current_tokens += details_tokens
                    sources.append("key_records")
        
        # 3.4 第四层：统计信息（低优先级，Token 预算剩余）
        remaining_budget = max_tokens - current_tokens
        if remaining_budget > 100:
            stats = self._load_statistics(intent)
            stats = self._truncate_to_tokens(stats, remaining_budget)
            stats_tokens = self._estimate_tokens(stats)
            
            if stats.strip():
                context_parts.append(stats)
                current_tokens += stats_tokens
                sources.append("statistics")
        
        # Step 4: 组装上下文
        context_content = "\n\n---\n\n".join(context_parts)
        
        # 计算相关性评分
        relevance_score = self._calculate_relevance(intent, context_content)
        
        context = Context(
            content=context_content,
            token_count=current_tokens,
            relevance_score=relevance_score,
            metadata={
                'intent': asdict(intent),
                'query': query,
                'max_tokens': max_tokens,
                'load_time_ms': int((datetime.now() - start_time).total_seconds() * 1000)
            },
            sources=sources
        )
        
        # 缓存结果
        with self._cache_lock:
            self._context_cache[cache_key] = (context, datetime.now())
        
        logger.info(
            f"上下文加载完成: {current_tokens} tokens, "
            f"相关性: {relevance_score:.2f}, "
            f"耗时: {context.metadata['load_time_ms']}ms"
        )
        
        return context
    
    def _load_overview(self, intent: Intent) -> str:
        """加载项目概览"""
        parts = ["## 项目概览\n"]
        
        if intent.project:
            parts.append(f"**项目**: {intent.project}\n")
        
        if intent.module:
            parts.append(f"**模块**: {intent.module}\n")
        
        if intent.time_range != "all":
            time_desc = {
                'last_week': '最近一周',
                'last_2_weeks': '最近两周',
                'last_month': '最近一个月',
                'last_3_months': '最近三个月'
            }.get(intent.time_range, intent.time_range)
            parts.append(f"**时间范围**: {time_desc}\n")
        
        parts.append(f"**分析焦点**: {intent.focus}\n")
        
        return "".join(parts)
    
    def _load_summary(self, intent: Intent) -> str:
        """加载数据摘要"""
        parts = ["## 数据摘要\n"]
        
        # 获取缺陷摘要
        if intent.data_type in ['defect', 'both']:
            defect_summary = self.data_summarizer.get_defect_summary(
                project=intent.project,
                time_range=intent.time_range
            )
            
            parts.append("\n### 缺陷数据\n")
            parts.append(f"- 总数: {defect_summary.total_count}\n")
            parts.append(f"- 时间范围: {defect_summary.time_range[0]} ~ {defect_summary.time_range[1]}\n")
            parts.append(f"- Critical 缺陷: {defect_summary.key_metrics.get('critical_count', 0)}\n")
            parts.append(f"- TopIssue: {defect_summary.key_metrics.get('topissue_count', 0)}\n")
            
            if defect_summary.distribution.get('severity'):
                parts.append("\n**严重程度分布**:\n")
                for sev, count in defect_summary.distribution['severity'].items():
                    parts.append(f"  - {sev}: {count}\n")
        
        # 获取测试摘要
        if intent.data_type in ['test', 'both']:
            test_summary = self.data_summarizer.get_test_summary(
                project=intent.project,
                time_range=intent.time_range
            )
            
            parts.append("\n### 测试数据\n")
            parts.append(f"- 总测试数: {test_summary.total_count}\n")
            parts.append(f"- 失败数: {test_summary.key_metrics.get('failed_tests', 0)}\n")
            parts.append(f"- 失败率: {test_summary.key_metrics.get('failure_rate', 0)}%\n")
        
        return "".join(parts)
    
    def _load_key_records(self, intent: Intent, max_records: int = 20) -> str:
        """加载关键记录"""
        parts = ["## 关键记录\n"]
        
        conn = sqlite3.connect(self.db_path)
        try:
            # 构建查询
            conditions = []
            params = []
            
            if intent.project:
                conditions.append("tproject = ?")
                params.append(intent.project)
            
            if intent.module:
                conditions.append("(pu LIKE ? OR aida LIKE ?)")
                params.extend([f"%{intent.module}%", f"%{intent.module}%"])
            
            if intent.time_range != "all":
                conditions.append(self._get_time_condition(intent.time_range))
            
            if intent.severity:
                placeholders = ",".join("?" * len(intent.severity))
                conditions.append(f"severity_group IN ({placeholders})")
                params.extend(intent.severity)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # 根据焦点排序
            order_by = {
                'risk': "ORDER BY severity_group DESC, creation_time DESC",
                'trend': "ORDER BY creation_time DESC",
                'coverage': "ORDER BY aida, creation_time DESC",
            }.get(intent.focus, "ORDER BY creation_time DESC")
            
            sql = f"""
                SELECT id, name, tproject, severity_group, creation_time, pu, aida
                FROM defects
                WHERE {where_clause}
                {order_by}
                LIMIT ?
            """
            params.append(max_records)
            
            cursor = conn.execute(sql, params)
            records = cursor.fetchall()
            
            if records:
                parts.append(f"\n共 {len(records)} 条相关记录：\n")
                
                for i, record in enumerate(records, 1):
                    defect_id, name, project, severity, time, pu, aida = record
                    
                    parts.append(f"\n{i}. **{name[:50]}{'...' if len(name) > 50 else ''}**\n")
                    parts.append(f"   - ID: {defect_id}\n")
                    parts.append(f"   - 项目: {project}\n")
                    parts.append(f"   - 严重程度: {severity}\n")
                    parts.append(f"   - 时间: {time}\n")
                    if pu:
                        parts.append(f"   - PU: {pu}\n")
                    if aida:
                        parts.append(f"   - AIDA: {aida}\n")
            else:
                parts.append("\n无相关记录\n")
            
            return "".join(parts)
            
        finally:
            conn.close()
    
    def _load_statistics(self, intent: Intent) -> str:
        """加载统计信息"""
        parts = ["## 统计分析\n"]
        
        conn = sqlite3.connect(self.db_path)
        try:
            # 按项目统计
            sql = """
                SELECT tproject, COUNT(*) as cnt
                FROM defects
                GROUP BY tproject
                ORDER BY cnt DESC
                LIMIT 10
            """
            project_stats = conn.execute(sql).fetchall()
            
            if project_stats:
                parts.append("\n**项目缺陷 TOP 10**:\n")
                for project, count in project_stats:
                    parts.append(f"  - {project}: {count}\n")
            
            # 按严重程度统计
            sql = """
                SELECT severity_group, COUNT(*) as cnt
                FROM defects
                GROUP BY severity_group
            """
            severity_stats = conn.execute(sql).fetchall()
            
            if severity_stats:
                parts.append("\n**严重程度分布**:\n")
                for severity, count in severity_stats:
                    parts.append(f"  - {severity}: {count}\n")
            
            return "".join(parts)
            
        finally:
            conn.close()
    
    def _get_time_condition(self, time_range: str) -> str:
        """生成时间查询条件"""
        time_map = {
            'last_week': "creation_time >= datetime('now', '-7 days')",
            'last_2_weeks': "creation_time >= datetime('now', '-14 days')",
            'last_month': "creation_time >= datetime('now', '-30 days')",
            'last_3_months': "creation_time >= datetime('now', '-90 days')",
        }
        return time_map.get(time_range, "1=1")
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 Token 数"""
        if not text:
            return 0
        
        # 简单估算：中文按字符数，英文按单词数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        tokens = int(chinese_chars / self.TOKEN_RATIO_CN) + int(english_words / self.TOKEN_RATIO_EN)
        
        return max(1, tokens)
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 Token 数"""
        if not text:
            return ""
        
        estimated = self._estimate_tokens(text)
        if estimated <= max_tokens:
            return text
        
        # 估算字符数
        ratio = max_tokens / estimated
        target_chars = int(len(text) * ratio * 0.9)  # 留一些余量
        
        return text[:target_chars] + "\n...[已截断]"
    
    def _calculate_relevance(self, intent: Intent, context: str) -> float:
        """计算上下文相关性"""
        score = 0.5  # 基础分
        
        # 检查关键信息是否包含
        if intent.project and intent.project in context:
            score += 0.2
        if intent.module and intent.module in context:
            score += 0.2
        if intent.focus in context:
            score += 0.1
        
        return min(1.0, score)


# ============================================================================
# 便捷函数
# ============================================================================

def create_context_engine(db_path: str = None, **kwargs) -> ContextEngine:
    """
    创建上下文引擎的便捷函数
    
    Args:
        db_path: 数据库路径
        **kwargs: 其他参数
        
    Returns:
        ContextEngine: 上下文引擎实例
    """
    return ContextEngine(db_path=db_path, **kwargs)


def load_context(query: str, db_path: str = None, max_tokens: int = 4000) -> Context:
    """
    加载上下文的便捷函数
    
    Args:
        query: 用户问题
        db_path: 数据库路径
        max_tokens: 最大 Token 数
        
    Returns:
        Context: 上下文对象
    """
    engine = create_context_engine(db_path)
    return engine.progressive_load(query, max_tokens)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 核心类
    'ContextEngine',
    'IntentAnalyzer',
    'SemanticRetriever',
    'DataSummarizer',
    
    # 数据类
    'Intent',
    'LoadContext',
    'DataSummary',
    
    # 工厂函数
    'create_context_engine',
    'create_intent_analyzer',
    'quick_load',
]


# ============================================================================
# 测试
# ============================================================================

if __name__ == "__main__":
    # 测试意图理解
    analyzer = IntentAnalyzer()
    
    test_queries = [
        "最近两周 ABS 模块的测试策略建议",
        "上个月 IDCEVO 项目的缺陷趋势分析",
        "ADC 项目的风险最高的模块有哪些",
        "对比 APP 和 BDC 的测试覆盖率",
    ]
    
    print("=" * 60)
    print("意图理解测试")
    print("=" * 60)
    
    for query in test_queries:
        intent = analyzer.analyze(query)
        print(f"\n问题: {query}")
        print(f"  数据类型: {intent.data_type}")
        print(f"  项目: {intent.project}")
        print(f"  模块: {intent.module}")
        print(f"  时间范围: {intent.time_range}")
        print(f"  分析焦点: {intent.focus}")
        print(f"  置信度: {intent.confidence:.2f}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
