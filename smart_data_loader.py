"""
智能数据加载器 - 集成上下文引擎实现高效数据加载

核心功能：
1. 智能意图理解 - 根据用户问题识别需要什么数据
2. 渐进式加载 - 按需加载数据，节省 Token
3. 语义检索 - 找到最相关的数据
4. 缓存机制 - 避免重复加载

作者: AI Assistant
日期: 2025-01-19
"""

import os
import sqlite3
import logging
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import pandas as pd
from dataclasses import dataclass

# 导入上下文引擎
try:
    from intelligent_context_engine import (
        ContextEngine,
        IntentAnalyzer,
        LoadContext,
        DataSummary
    )
    CONTEXT_ENGINE_AVAILABLE = True
except ImportError:
    CONTEXT_ENGINE_AVAILABLE = False
    ContextEngine = None
    IntentAnalyzer = None
    DataSummary = None
    
    # 提供备用的 LoadContext 类
    @dataclass
    class LoadContext:
        """加载上下文（备用实现）"""
        token_count: int = 0
        relevance_score: float = 0.0
        sources: List[str] = None
        summary: Any = None
        key_records: List[Dict] = None
        statistics: Dict[str, Any] = None
        
        def __post_init__(self):
            if self.sources is None:
                self.sources = []
            if self.key_records is None:
                self.key_records = []
            if self.statistics is None:
                self.statistics = {}

logger = logging.getLogger(__name__)


# ============================================================================
# 数据加载配置
# ============================================================================

@dataclass
class LoaderConfig:
    """数据加载器配置"""
    # 数据库路径
    db_path: str = ""
    # 是否使用智能加载
    use_smart_loading: bool = True
    # 最大 Token 数（用于控制上下文大小）
    max_tokens: int = 8000
    # 是否使用语义检索
    use_semantic_search: bool = True
    # 缓存 TTL（秒）
    cache_ttl: int = 300  # 5分钟
    
    @classmethod
    def from_env(cls) -> "LoaderConfig":
        """从环境变量创建配置"""
        return cls(
            db_path=os.getenv("DB_PATH", ""),
            use_smart_loading=os.getenv("USE_SMART_LOADING", "true").lower() == "true",
            max_tokens=int(os.getenv("MAX_TOKENS", "8000")),
            use_semantic_search=os.getenv("USE_SEMANTIC_SEARCH", "true").lower() == "true",
        )


# ============================================================================
# 智能数据加载器
# ============================================================================

class SmartDataLoader:
    """
    智能数据加载器
    
    使用上下文引擎实现高效的数据加载：
    1. 分析用户问题意图
    2. 按需加载相关数据
    3. 渐进式返回结果
    """
    
    def __init__(self, config: Optional[LoaderConfig] = None):
        """
        初始化智能数据加载器
        
        Args:
            config: 加载器配置，如果为 None 则使用默认配置
        """
        self.config = config or LoaderConfig()
        
        # 初始化上下文引擎
        if CONTEXT_ENGINE_AVAILABLE and self.config.use_smart_loading:
            try:
                self.context_engine = ContextEngine(
                    db_path=self.config.db_path,
                    use_semantic_search=self.config.use_semantic_search
                )
                logger.info("✅ 智能上下文引擎初始化成功")
            except Exception as e:
                logger.warning(f"⚠️ 上下文引擎初始化失败: {e}，将使用传统加载方式")
                self.context_engine = None
        else:
            self.context_engine = None
            logger.info("使用传统数据加载方式")
        
        # 缓存
        self._cache: Dict[str, Tuple[pd.DataFrame, float]] = {}
        
    def load_for_question(
        self,
        question: str,
        data_type: str = "auto",
        project: Optional[str] = None,
        time_range: str = "all"
    ) -> Tuple[pd.DataFrame, LoadContext]:
        """
        根据问题智能加载数据
        
        Args:
            question: 用户问题
            data_type: 数据类型 ("defects", "tests", "auto")
            project: 项目名（可选）
            time_range: 时间范围
            
        Returns:
            (DataFrame, LoadContext) 数据和加载上下文
        """
        # 检查缓存
        cache_key = f"{question}:{data_type}:{project}:{time_range}"
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if (datetime.now().timestamp() - cached_time) < self.config.cache_ttl:
                logger.info(f"从缓存加载数据: {cache_key}")
                return cached_data, LoadContext(
                    token_count=self._estimate_tokens(cached_data),
                    relevance_score=1.0,
                    sources=["cache"]
                )
        
        # 使用上下文引擎加载
        if self.context_engine:
            try:
                load_context = self.context_engine.progressive_load(
                    query=question,
                    data_type=data_type if data_type != "auto" else None,
                    project=project,
                    time_range=time_range,
                    max_tokens=self.config.max_tokens
                )
                
                # 从上下文中获取数据
                df = self._context_to_dataframe(load_context)
                
                # 更新缓存
                self._cache[cache_key] = (df, datetime.now().timestamp())
                
                logger.info(
                    f"智能加载数据: {len(df)} 条记录, "
                    f"{load_context.token_count} tokens, "
                    f"相关性: {load_context.relevance_score:.2f}"
                )
                
                return df, load_context
                
            except Exception as e:
                logger.warning(f"智能加载失败: {e}，回退到传统加载")
        
        # 传统加载方式（回退）
        df = self._traditional_load(data_type, project, time_range)
        
        load_context = LoadContext(
            token_count=self._estimate_tokens(df),
            relevance_score=0.5,  # 传统方式相关性较低
            sources=["traditional"]
        )
        
        return df, load_context
    
    def load_defects(
        self,
        question: str = "",
        project: Optional[str] = None,
        time_range: str = "all"
    ) -> Tuple[pd.DataFrame, LoadContext]:
        """
        智能加载缺陷数据
        
        Args:
            question: 用户问题（用于意图理解）
            project: 项目名
            time_range: 时间范围
            
        Returns:
            (DataFrame, LoadContext)
        """
        return self.load_for_question(
            question=question or "显示所有缺陷",
            data_type="defects",
            project=project,
            time_range=time_range
        )
    
    def load_tests(
        self,
        question: str = "",
        project: Optional[str] = None,
        time_range: str = "all"
    ) -> Tuple[pd.DataFrame, LoadContext]:
        """
        智能加载测试数据
        
        Args:
            question: 用户问题
            project: 项目名
            time_range: 时间范围
            
        Returns:
            (DataFrame, LoadContext)
        """
        return self.load_for_question(
            question=question or "显示所有测试记录",
            data_type="tests",
            project=project,
            time_range=time_range
        )
    
    def load_all(
        self,
        question: str = ""
    ) -> Dict[str, Tuple[pd.DataFrame, LoadContext]]:
        """
        加载所有数据（智能判断需要哪些）
        
        Args:
            question: 用户问题
            
        Returns:
            字典: {"defects": (df, context), "tests": (df, context)}
        """
        result = {}
        
        # 分析意图
        if self.context_engine and question:
            intent = self.context_engine.intent_analyzer.analyze(question)
            
            # 根据意图决定加载哪些数据
            if intent.data_type in ["defects", "all"]:
                result["defects"] = self.load_defects(question)
            if intent.data_type in ["tests", "all"]:
                result["tests"] = self.load_tests(question)
            
            # 如果没有明确意图，加载所有
            if not result:
                result["defects"] = self.load_defects(question)
                result["tests"] = self.load_tests(question)
        else:
            # 无意图分析，加载所有
            result["defects"] = self.load_defects(question)
            result["tests"] = self.load_tests(question)
        
        return result
    
    # ========================================================================
    # 内部方法
    # ========================================================================
    
    def _context_to_dataframe(self, load_context: LoadContext) -> pd.DataFrame:
        """将加载上下文转换为 DataFrame"""
        records = []
        
        # 从统计数据中构建概览
        if load_context.summary:
            # 创建概览记录
            summary_record = {
                "type": "summary",
                "total_count": load_context.summary.total_count,
                "time_range_start": load_context.summary.time_range[0],
                "time_range_end": load_context.summary.time_range[1],
            }
            summary_record.update(load_context.summary.key_metrics)
            records.append(summary_record)
        
        # 添加关键记录
        for record in load_context.key_records:
            records.append(record)
        
        # 添加统计信息
        for key, value in load_context.statistics.items():
            records.append({"type": "stat", "key": key, "value": str(value)})
        
        return pd.DataFrame(records) if records else pd.DataFrame()
    
    def _traditional_load(
        self,
        data_type: str,
        project: Optional[str],
        time_range: str
    ) -> pd.DataFrame:
        """传统数据加载方式（回退方案）"""
        try:
            # 尝试从数据库加载
            if self.config.db_path and os.path.exists(self.config.db_path):
                conn = sqlite3.connect(self.config.db_path)
                
                # 确定表名
                table = "defects" if data_type in ["defects", "auto"] else "test_runs"
                
                # 构建查询
                sql = f"SELECT * FROM {table}"
                conditions = []
                params = []
                
                if project:
                    conditions.append("project = ?")
                    params.append(project)
                
                # 时间范围过滤
                if time_range != "all":
                    time_col = "tcreationtime" if table == "defects" else "run_time"
                    now = datetime.now()
                    if time_range == "week":
                        start = now - timedelta(days=7)
                    elif time_range == "month":
                        start = now - timedelta(days=30)
                    elif time_range == "quarter":
                        start = now - timedelta(days=90)
                    else:
                        start = None
                    
                    if start:
                        conditions.append(f"{time_col} >= ?")
                        params.append(start.strftime("%Y-%m-%d"))
                
                if conditions:
                    sql += " WHERE " + " AND ".join(conditions)
                
                # 限制返回数量
                sql += " LIMIT 1000"
                
                df = pd.read_sql_query(sql, conn, params=params)
                conn.close()
                
                return df
                
        except Exception as e:
            logger.error(f"传统加载失败: {e}")
        
        return pd.DataFrame()
    
    def _estimate_tokens(self, df: pd.DataFrame) -> int:
        """估算 DataFrame 的 Token 数"""
        if df.empty:
            return 0
        # 粗略估算：每行约 50 tokens
        return len(df) * 50 + len(df.columns) * 5
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        logger.info("缓存已清除")


# ============================================================================
# 兼容性适配器
# ============================================================================

class DataLoaderAdapter:
    """
    数据加载器适配器
    
    提供与现有 data_processor 接口兼容的方法，
    内部使用 SmartDataLoader 实现智能加载
    """
    
    def __init__(self, config: Optional[LoaderConfig] = None):
        self.loader = SmartDataLoader(config)
    
    def load_defect_data(self, question: str = "") -> pd.DataFrame:
        """
        加载缺陷数据（兼容 data_processor.load_defect_data）
        
        Args:
            question: 用户问题（可选）
            
        Returns:
            DataFrame
        """
        df, context = self.loader.load_defects(question)
        return df
    
    def load_test_data(self, question: str = "") -> pd.DataFrame:
        """
        加载测试数据（兼容 data_processor.load_test_data）
        
        Args:
            question: 用户问题（可选）
            
        Returns:
            DataFrame
        """
        df, context = self.loader.load_tests(question)
        return df
    
    def get_history_data(
        self,
        question: str = "",
        data_type: str = "all"
    ) -> Dict[str, pd.DataFrame]:
        """
        获取历史数据（兼容 data_processor.get_history_data）
        
        Args:
            question: 用户问题
            data_type: 数据类型
            
        Returns:
            字典形式的 DataFrame
        """
        result = {}
        
        if data_type in ["defects", "all"]:
            result["defects"] = self.load_defect_data(question)
        
        if data_type in ["tests", "all"]:
            result["tests"] = self.load_test_data(question)
        
        return result


# ============================================================================
# 工厂函数
# ============================================================================

def create_smart_loader(db_path: str = "", **kwargs) -> SmartDataLoader:
    """
    创建智能数据加载器
    
    Args:
        db_path: 数据库路径
        **kwargs: 其他配置参数
        
    Returns:
        SmartDataLoader 实例
    """
    config = LoaderConfig(db_path=db_path, **kwargs)
    return SmartDataLoader(config)


def create_data_loader_adapter(db_path: str = "", **kwargs) -> DataLoaderAdapter:
    """
    创建数据加载适配器
    
    Args:
        db_path: 数据库路径
        **kwargs: 其他配置参数
        
    Returns:
        DataLoaderAdapter 实例
    """
    config = LoaderConfig(db_path=db_path, **kwargs)
    return DataLoaderAdapter(config)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 示例 1: 直接使用 SmartDataLoader
    print("=" * 70)
    print("示例 1: SmartDataLoader")
    print("=" * 70)
    
    loader = create_smart_loader(db_path="database/local_data.db")
    
    # 根据问题智能加载
    question = "最近两周 ABS 模块的缺陷趋势"
    df, context = loader.load_for_question(question)
    
    print(f"问题: {question}")
    print(f"加载记录数: {len(df)}")
    print(f"Token 数: {context.token_count}")
    print(f"相关性: {context.relevance_score:.2f}")
    print(f"数据来源: {', '.join(context.sources)}")
    
    print("\n" + "=" * 70)
    print("示例 2: DataLoaderAdapter（兼容旧接口）")
    print("=" * 70)
    
    adapter = create_data_loader_adapter(db_path="database/local_data.db")
    
    # 使用兼容接口
    defects_df = adapter.load_defect_data(question="IDCEVO 项目的缺陷")
    tests_df = adapter.load_test_data(question="最近的测试执行情况")
    
    print(f"缺陷数据: {len(defects_df)} 条")
    print(f"测试数据: {len(tests_df)} 条")
