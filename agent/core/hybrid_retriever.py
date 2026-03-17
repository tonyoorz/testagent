"""
Hybrid Retriever - 混合检索策略

Features:
1. Structured filtering (exact match)
2. Semantic retrieval (TF-IDF based)
3. Automatic fallback and result ranking
4. Reuse of duplicate_issue_finder TF-IDF implementation

Author: AI Assistant
Date: 2025-02-21
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.preprocessing import normalize
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    TfidfVectorizer = None
    TruncatedSVD = None
    cosine_similarity = None
    normalize = None
    logger.warning("sklearn not available, hybrid retriever will use keyword fallback")


@dataclass
class RetrievalResult:
    """检索结果"""
    data: pd.DataFrame
    method: str  # 'structured', 'semantic', 'hybrid', 'keyword_fallback'
    filtered_count: int
    original_count: int
    top_k_applied: bool = False


class HybridRetriever:
    """
    混合检索器

    策略：
    1. 首先应用结构化过滤（精确匹配）
    2. 如果结果过多(>100)，使用语义检索筛选top-k
    3. 如果语义检索失败，回退到关键词匹配
    """

    # 语义检索配置
    SEMANTIC_TOP_K = 50
    SEMANTIC_THRESHOLD = 0.1
    MAX_STRUCTURAL_RESULTS = 100
    CACHE_MAX_ENTRIES = 6
    LSA_COMPONENTS = 64
    FUSION_ALPHA = 0.6

    # 文本字段优先级（用于语义检索）
    TEXT_FIELDS_PRIORITY = [
        'name', 'description', 'title', 'summary',
        'aida_english', 'aida_chinese', 'top_aida',
        'project', 'tproject', 'pu', 'ecu',
        'matrix_display', 'status_phase'
    ]

    def __init__(self):
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._vector_cache: Dict[str, Any] = {}
        self._cache_lock = threading.RLock()

    def retrieve(self, question: str, data: pd.DataFrame,
                 structured_constraints: Optional[Dict] = None,
                 semantic_top_k: int = 50,
                 dataset_key: Optional[str] = None) -> RetrievalResult:
        """
        执行混合检索

        Args:
            question: 用户问题
            data: 完整数据集
            structured_constraints: 结构化过滤条件（如 {'project': 'G01', 'severity': 'Critical'}）
            semantic_top_k: 语义检索返回的最大数量

        Returns:
            RetrievalResult with filtered data and metadata
        """
        if data is None or data.empty:
            return RetrievalResult(
                data=pd.DataFrame(),
                method='none',
                filtered_count=0,
                original_count=0
            )

        original_count = len(data)

        # 1. 结构化过滤
        if structured_constraints:
            filtered = self._apply_structured_filter(data, structured_constraints)
            method = 'structured'
        else:
            filtered = data
            method = 'none'

        structured_count = len(filtered)

        # 如果结构化过滤后已经没有数据，直接返回
        if filtered.empty:
            return RetrievalResult(
                data=filtered,
                method=method,
                filtered_count=0,
                original_count=original_count
            )

        # 2. 如果结果太多，使用语义检索
        if len(filtered) > self.MAX_STRUCTURAL_RESULTS:
            semantic_result = self.semantic_filter(
                question, filtered,
                top_k=semantic_top_k or self.SEMANTIC_TOP_K,
                dataset_key=dataset_key
            )

            if semantic_result is not None and not semantic_result.empty:
                filtered = semantic_result
                method = 'hybrid' if structured_constraints else 'semantic'
            else:
                # 语义检索失败，使用简单关键词过滤
                filtered = self._keyword_filter(question, filtered)
                method = 'keyword_fallback'

        return RetrievalResult(
            data=filtered,
            method=method,
            filtered_count=len(filtered),
            original_count=original_count,
            top_k_applied=len(filtered) < structured_count
        )

    def _apply_structured_filter(self, data: pd.DataFrame,
                                  constraints: Dict[str, Any]) -> pd.DataFrame:
        """
        应用结构化过滤条件

        Args:
            data: 数据集
            constraints: 过滤条件字典，如 {'project': 'G01', 'severity': ['Critical', 'Major']}

        Returns:
            过滤后的数据集
        """
        if not constraints:
            return data

        mask = pd.Series([True] * len(data), index=data.index)

        for column, value in constraints.items():
            if column not in data.columns:
                continue

            try:
                if isinstance(value, list):
                    # 多值匹配
                    mask &= data[column].isin(value)
                elif isinstance(value, str):
                    # 字符串匹配（不区分大小写）
                    if data[column].dtype == 'object':
                        mask &= data[column].astype(str).str.lower() == value.lower()
                    else:
                        mask &= data[column] == value
                elif isinstance(value, (int, float, bool)):
                    # 数值/布尔匹配
                    mask &= data[column] == value
                elif callable(value):
                    # 自定义过滤函数
                    mask &= data[column].apply(value)
            except Exception as e:
                logger.warning(f"Filter error for column {column}: {e}")
                continue

        return data[mask]

    def semantic_filter(self, question: str, data: pd.DataFrame,
                        top_k: int = 50,
                        dataset_key: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        使用TF-IDF语义过滤数据

        复用 duplicate_issue_finder 的TF-IDF逻辑：
        - Character n-grams (3-5)
        - 20万 max features
        - Cosine similarity

        Args:
            question: 用户问题
            data: 数据集（已结构过滤）
            top_k: 返回最相关的k条

        Returns:
            过滤后的数据集，或None如果失败
        """
        if not SKLEARN_AVAILABLE or data is None or data.empty:
            return None

        try:
            # 构建文档（按优先级组合文本字段）
            documents = self._build_documents(data)

            if not documents or all(not d.strip() for d in documents):
                return None

            query_doc = self._build_query_document(question)
            cache_key = self._make_cache_key(dataset_key, data)
            vectorizer, doc_matrix, lsa_svd, lsa_matrix = self._get_or_build_semantic_index(cache_key, documents)
            query_vector = vectorizer.transform([query_doc])

            similarities_tfidf = cosine_similarity(doc_matrix, query_vector).flatten()
            similarities = similarities_tfidf

            if lsa_svd is not None and lsa_matrix is not None:
                try:
                    query_lsa = lsa_svd.transform(query_vector)
                    query_lsa = normalize(query_lsa).astype(np.float32, copy=False)
                    similarities_lsa = (lsa_matrix @ query_lsa.reshape(-1, 1)).reshape(-1)
                    similarities = self.FUSION_ALPHA * similarities_lsa + (1.0 - self.FUSION_ALPHA) * similarities_tfidf
                except Exception as e:
                    logger.debug(f"LSA scoring failed, fallback to TF-IDF only: {e}")

            # 如果最高相似度太低，可能相关性都不高
            if similarities.max() < self.SEMANTIC_THRESHOLD:
                logger.debug(f"Low max similarity ({similarities.max():.3f}), returning top {top_k} by score")

            # 获取top-k索引
            top_indices = np.argsort(similarities)[-top_k:][::-1]

            # 返回对应数据
            result = data.iloc[top_indices].copy()
            result['_semantic_score'] = similarities[top_indices]
            result['_semantic_score_tfidf'] = similarities_tfidf[top_indices]

            return result

        except Exception as e:
            logger.warning(f"Semantic filter failed: {e}")
            return None

    def _make_cache_key(self, dataset_key: Optional[str], data: pd.DataFrame) -> str:
        base = dataset_key.strip() if isinstance(dataset_key, str) and dataset_key.strip() else "auto"
        cols = ",".join(sorted([str(c) for c in data.columns]))
        n = len(data)

        id_col = None
        for c in ("id", "defect_id", "ticket_id"):
            if c in data.columns:
                id_col = c
                break
        id_head = ""
        id_tail = ""
        if id_col:
            try:
                s = data[id_col].astype(str)
                id_head = s.iloc[0]
                id_tail = s.iloc[-1]
            except Exception:
                id_head = ""
                id_tail = ""

        ts = ""
        for c in ("fetched_at", "tcreationtime", "created_date", "finished_udf_dt"):
            if c in data.columns:
                try:
                    m = pd.to_datetime(data[c], errors="coerce").dropna()
                    if not m.empty:
                        ts = str(int(m.max().timestamp()))
                except Exception:
                    ts = ""
                break

        return f"{base}|n={n}|cols={hash(cols)}|id={id_head}:{id_tail}|ts={ts}"

    def _get_or_build_semantic_index(self, cache_key: str, documents: List[str]):
        with self._cache_lock:
            cached = self._vector_cache.get(cache_key)
            if cached and cached.get("doc_count") == len(documents):
                cached["last_used"] = time.time()
                return cached["vectorizer"], cached["doc_matrix"], cached.get("lsa_svd"), cached.get("lsa_matrix")

        vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(3, 5),
            max_features=200_000,
            lowercase=True
        )
        doc_matrix = vectorizer.fit_transform(documents)

        lsa_svd = None
        lsa_matrix = None
        if TruncatedSVD is not None and normalize is not None:
            try:
                n_components = min(self.LSA_COMPONENTS, max(0, doc_matrix.shape[0] - 1), max(0, doc_matrix.shape[1] - 1))
                if n_components >= 2:
                    lsa_svd = TruncatedSVD(n_components=int(n_components), random_state=42)
                    doc_lsa = lsa_svd.fit_transform(doc_matrix)
                    doc_lsa = normalize(doc_lsa).astype(np.float32, copy=False)
                    lsa_matrix = doc_lsa
            except Exception as e:
                logger.debug(f"LSA build failed, fallback to TF-IDF only: {e}")
                lsa_svd = None
                lsa_matrix = None

        with self._cache_lock:
            self._vector_cache[cache_key] = {
                "vectorizer": vectorizer,
                "doc_matrix": doc_matrix,
                "lsa_svd": lsa_svd,
                "lsa_matrix": lsa_matrix,
                "doc_count": len(documents),
                "built_at": time.time(),
                "last_used": time.time(),
            }
            if len(self._vector_cache) > self.CACHE_MAX_ENTRIES:
                items = list(self._vector_cache.items())
                items.sort(key=lambda kv: float(kv[1].get("last_used", 0.0)))
                for k, _ in items[: max(0, len(self._vector_cache) - self.CACHE_MAX_ENTRIES)]:
                    self._vector_cache.pop(k, None)

        return vectorizer, doc_matrix, lsa_svd, lsa_matrix

    def _build_documents(self, data: pd.DataFrame) -> List[str]:
        """
        为数据行构建文本文档

        Args:
            data: 数据集

        Returns:
            文档列表
        """
        documents = []

        # 确定可用的文本字段
        available_fields = [f for f in self.TEXT_FIELDS_PRIORITY if f in data.columns]

        if not available_fields:
            # 如果没有优先字段，使用所有字符串列
            available_fields = [c for c in data.columns if data[c].dtype == 'object']

        for idx in range(len(data)):
            parts = []
            for field in available_fields[:5]:  # 限制字段数量
                try:
                    value = data.iloc[idx].get(field)
                    if pd.notna(value):
                        parts.append(str(value))
                except:
                    continue

            doc = ' '.join(parts) if parts else ''
            documents.append(doc)

        return documents

    def _build_query_document(self, question: str) -> str:
        """
        构建查询文档（提取问题中的关键词）

        Args:
            question: 用户问题

        Returns:
            处理后的查询文档
        """
        # 移除常见的停用词和疑问词
        stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '什么', '怎么', '如何', '请', '问', '一下'}

        words = []
        for word in question.split():
            word = word.strip()
            if word and word.lower() not in stop_words:
                words.append(word)

        return ' '.join(words) if words else question

    def _keyword_filter(self, question: str, data: pd.DataFrame) -> pd.DataFrame:
        """
        关键词过滤回退方案

        Args:
            question: 用户问题
            data: 数据集

        Returns:
            过滤后的数据集
        """
        if data.empty:
            return data

        # 提取关键词
        keywords = self._extract_keywords(question)

        if not keywords:
            return data.head(self.SEMANTIC_TOP_K)  # 返回前N条

        # 在文本字段中搜索关键词
        available_fields = [f for f in self.TEXT_FIELDS_PRIORITY if f in data.columns]
        if not available_fields:
            available_fields = [c for c in data.columns if data[c].dtype == 'object']

        scores = np.zeros(len(data))

        for field in available_fields:
            try:
                field_values = data[field].astype(str).str.lower()
                for keyword in keywords:
                    matches = field_values.str.contains(keyword, na=False, regex=False)
                    scores += matches.astype(int)
            except:
                continue

        # 按分数排序并返回top-k
        if scores.max() > 0:
            top_indices = np.argsort(scores)[-self.SEMANTIC_TOP_K:][::-1]
            return data.iloc[top_indices]
        else:
            return data.head(self.SEMANTIC_TOP_K)

    def _extract_keywords(self, question: str) -> Set[str]:
        """
        从问题中提取关键词

        Args:
            question: 用户问题

        Returns:
            关键词集合
        """
        keywords = set()
        question_lower = question.lower()

        # 项目代码模式
        import re
        project_pattern = re.compile(r'\b([gfiu]\d{2,3}[a-z]?)\b', re.IGNORECASE)
        keywords.update(project_pattern.findall(question_lower))

        # 常见分析关键词
        analysis_keywords = [
            'critical', 'major', 'minor', 'severe', 'risk', 'topissue',
            'longrunner', 'defect', 'test', 'coverage', 'failure',
            'g01', 'g20', 'f30', 'idcevo', 'mgu'
        ]

        for kw in analysis_keywords:
            if kw in question_lower:
                keywords.add(kw)

        # 引号内的内容
        quoted = re.findall(r'"([^"]+)"', question)
        keywords.update([q.lower() for q in quoted])

        return keywords

    def build_structured_constraints(self, question: str,
                                      available_columns: List[str]) -> Dict[str, Any]:
        """
        从问题中自动构建结构化约束

        Args:
            question: 用户问题
            available_columns: 可用的列名

        Returns:
            结构化约束字典
        """
        constraints = {}
        question_lower = question.lower()

        # 项目过滤
        project_cols = [c for c in available_columns if c in ['project', 'tproject']]
        if project_cols:
            import re
            projects = re.findall(r'\b([GFIU]\d{2,3}[a-z]?)\b', question, re.IGNORECASE)
            if projects:
                constraints[project_cols[0]] = projects[0].upper()

        # 严重性过滤
        severity_cols = [c for c in available_columns if 'severity' in c.lower()]
        if severity_cols:
            if 'critical' in question_lower:
                constraints[severity_cols[0]] = 'Critical'
            elif 'major' in question_lower:
                constraints[severity_cols[0]] = 'Major'

        # 状态过滤
        status_cols = [c for c in available_columns if 'status' in c.lower()]
        if status_cols:
            status_map = {
                'open': ['Open', 'New'],
                'close': ['Closed', 'Resolved'],
                'in progress': ['In Progress', 'Analyzing']
            }
            for key, values in status_map.items():
                if key in question_lower:
                    constraints[status_cols[0]] = values
                    break

        return constraints


# 工厂函数
def create_hybrid_retriever() -> HybridRetriever:
    """创建混合检索器实例"""
    return HybridRetriever()


# 便捷函数
def retrieve_relevant_data(question: str, data: pd.DataFrame,
                           constraints: Optional[Dict] = None,
                           top_k: int = 50) -> pd.DataFrame:
    """
    便捷函数：检索相关数据

    Args:
        question: 用户问题
        data: 完整数据集
        constraints: 结构化约束
        top_k: 语义检索top-k

    Returns:
        过滤后的数据集
    """
    retriever = create_hybrid_retriever()
    result = retriever.retrieve(question, data, constraints, top_k)
    return result.data


# 测试代码
if __name__ == "__main__":
    print("Hybrid Retriever Test")
    print("=" * 50)

    # 创建测试数据
    test_data = pd.DataFrame({
        'id': range(100),
        'name': [f"Defect {i}: {'Critical' if i % 5 == 0 else 'Major' if i % 3 == 0 else 'Minor'} issue in {'G01' if i < 50 else 'G20'} ECU" for i in range(100)],
        'project': ['G01'] * 50 + ['G20'] * 50,
        'severity': ['Critical' if i % 5 == 0 else 'Major' if i % 3 == 0 else 'Minor' for i in range(100)],
        'description': [f'This is a detailed description for defect {i} in project' for i in range(100)]
    })

    retriever = create_hybrid_retriever()

    # 测试1: 纯结构化过滤
    print("\n1. Structured filter test:")
    result1 = retriever.retrieve(
        "G01 project defects",
        test_data,
        structured_constraints={'project': 'G01'}
    )
    print(f"   Method: {result1.method}")
    print(f"   Results: {result1.filtered_count}/{result1.original_count}")

    # 测试2: 混合检索（结构化 + 语义）
    print("\n2. Hybrid retrieval test:")
    result2 = retriever.retrieve(
        "Critical severity issues in G01",
        test_data,
        structured_constraints={'project': 'G01', 'severity': 'Critical'},
        semantic_top_k=10
    )
    print(f"   Method: {result2.method}")
    print(f"   Results: {result2.filtered_count}/{result2.original_count}")

    # 测试3: 纯语义检索
    print("\n3. Semantic retrieval test:")
    result3 = retriever.retrieve(
        "Critical defects with high priority",
        test_data,
        semantic_top_k=20
    )
    print(f"   Method: {result3.method}")
    print(f"   Results: {result3.filtered_count}/{result3.original_count}")

    # 测试4: 自动构建约束
    print("\n4. Auto constraints test:")
    constraints = retriever.build_structured_constraints(
        "Show me G01 Critical defects",
        test_data.columns.tolist()
    )
    print(f"   Constraints: {constraints}")

    print("\n" + "=" * 50)
    print("测试完成!")
