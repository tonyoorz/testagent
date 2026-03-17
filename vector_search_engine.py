"""
向量检索引擎 - 支持多种后端

支持的向量检索后端：
1. FAISS（推荐）- 高效的向量相似度搜索
2. Sentence Transformers - 端到端语义向量
3. TF-IDF（后备）- 传统文本相似度

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import pickle
import logging
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)

# ============================================================================
# 可选依赖导入
# ============================================================================

# FAISS（可选）
try:
    import faiss
    FAISS_AVAILABLE = True
    logger.info("FAISS 向量引擎可用")
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None
    logger.info("FAISS 不可用，将使用备选方案")

# Sentence Transformers（可选）
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
    logger.info("Sentence Transformers 可用")
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    logger.info("Sentence Transformers 不可用，将使用 TF-IDF")


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class VectorSearchResult:
    """向量搜索结果"""
    id: int
    score: float
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorIndex:
    """向量索引"""
    vectors: np.ndarray
    texts: List[str]
    metadata: List[Dict[str, Any]]
    dimension: int
    
    def __post_init__(self):
        if len(self.texts) != len(self.metadata):
            raise ValueError("texts 和 metadata 长度必须一致")


# ============================================================================
# 向量化器基类
# ============================================================================

class Vectorizer:
    """向量化器基类"""
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """将文本转换为向量"""
        raise NotImplementedError
    
    def get_dimension(self) -> int:
        """获取向量维度"""
        raise NotImplementedError


class SentenceTransformerVectorizer(Vectorizer):
    """Sentence Transformers 向量化器"""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化
        
        Args:
            model_name: 模型名称，默认使用轻量级模型
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("Sentence Transformers 不可用")
        
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"加载 SentenceTransformer 模型: {model_name}, 维度: {self.dimension}")
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """编码文本为向量"""
        return self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    
    def get_dimension(self) -> int:
        return self.dimension


class TFIDFVectorizer(Vectorizer):
    """TF-IDF 向量化器（后备方案）"""
    
    def __init__(self, max_features: int = 768):
        """
        初始化
        
        Args:
            max_features: 最大特征数（模拟向量维度）
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=(1, 2),
            stop_words=None
        )
        self.dimension = max_features
        self._fitted = False
    
    def fit(self, texts: List[str]):
        """训练 TF-IDF 模型"""
        self.vectorizer.fit(texts)
        self._fitted = True
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """编码文本为向量"""
        if not self._fitted:
            self.fit(texts)
        
        vectors = self.vectorizer.transform(texts).toarray()
        
        # 确保维度一致
        if vectors.shape[1] < self.dimension:
            padding = np.zeros((vectors.shape[0], self.dimension - vectors.shape[1]))
            vectors = np.hstack([vectors, padding])
        
        return vectors
    
    def get_dimension(self) -> int:
        return self.dimension


# ============================================================================
# 向量存储基类
# ============================================================================

class VectorStore:
    """向量存储基类"""
    
    def add(self, vectors: np.ndarray, texts: List[str], metadata: List[Dict]):
        """添加向量"""
        raise NotImplementedError
    
    def search(self, query_vector: np.ndarray, k: int = 10) -> List[VectorSearchResult]:
        """搜索相似向量"""
        raise NotImplementedError
    
    def save(self, path: str):
        """保存索引"""
        raise NotImplementedError
    
    def load(self, path: str):
        """加载索引"""
        raise NotImplementedError


class FAISSVectorStore(VectorStore):
    """FAISS 向量存储"""
    
    def __init__(self, dimension: int):
        """
        初始化
        
        Args:
            dimension: 向量维度
        """
        if not FAISS_AVAILABLE:
            raise ImportError("FAISS 不可用")
        
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)  # 内积相似度
        self.texts: List[str] = []
        self.metadata: List[Dict] = []
    
    def add(self, vectors: np.ndarray, texts: List[str], metadata: List[Dict]):
        """添加向量"""
        # 归一化向量（用于内积相似度）
        faiss.normalize_L2(vectors)
        
        # 添加到索引
        self.index.add(vectors.astype('float32'))
        self.texts.extend(texts)
        self.metadata.extend(metadata)
        
        logger.info(f"添加 {len(texts)} 个向量到 FAISS 索引")
    
    def search(self, query_vector: np.ndarray, k: int = 10) -> List[VectorSearchResult]:
        """搜索相似向量"""
        # 归一化查询向量
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        faiss.normalize_L2(query_vector.astype('float32'))
        
        # 搜索
        scores, indices = self.index.search(query_vector.astype('float32'), k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(self.texts):
                results.append(VectorSearchResult(
                    id=int(idx),
                    score=float(score),
                    text=self.texts[idx],
                    metadata=self.metadata[idx]
                ))
        
        return results
    
    def save(self, path: str):
        """保存索引"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # 保存 FAISS 索引
        faiss.write_index(self.index, f"{path}.faiss")
        
        # 保存文本和元数据
        with open(f"{path}.data", 'wb') as f:
            pickle.dump({
                'texts': self.texts,
                'metadata': self.metadata,
                'dimension': self.dimension
            }, f)
        
        logger.info(f"FAISS 索引已保存: {path}")
    
    def load(self, path: str):
        """加载索引"""
        # 加载 FAISS 索引
        self.index = faiss.read_index(f"{path}.faiss")
        
        # 加载文本和元数据
        with open(f"{path}.data", 'rb') as f:
            data = pickle.load(f)
            self.texts = data['texts']
            self.metadata = data['metadata']
            self.dimension = data['dimension']
        
        logger.info(f"FAISS 索引已加载: {path}, 共 {len(self.texts)} 条记录")


class SimpleVectorStore(VectorStore):
    """简单的向量存储（后备方案）"""
    
    def __init__(self, dimension: int):
        self.dimension = dimension
        self.vectors: np.ndarray = np.array([])
        self.texts: List[str] = []
        self.metadata: List[Dict] = []
    
    def add(self, vectors: np.ndarray, texts: List[str], metadata: List[Dict]):
        """添加向量"""
        if len(self.vectors) == 0:
            self.vectors = vectors
        else:
            self.vectors = np.vstack([self.vectors, vectors])
        
        self.texts.extend(texts)
        self.metadata.extend(metadata)
    
    def search(self, query_vector: np.ndarray, k: int = 10) -> List[VectorSearchResult]:
        """搜索相似向量（使用余弦相似度）"""
        if len(self.vectors) == 0:
            return []
        
        # 计算余弦相似度
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        # 归一化
        query_norm = query_vector / (np.linalg.norm(query_vector) + 1e-8)
        vectors_norm = self.vectors / (np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8)
        
        # 计算相似度
        similarities = np.dot(vectors_norm, query_norm.T).flatten()
        
        # 排序
        top_indices = np.argsort(similarities)[::-1][:k]
        
        results = []
        for idx in top_indices:
            results.append(VectorSearchResult(
                id=int(idx),
                score=float(similarities[idx]),
                text=self.texts[idx],
                metadata=self.metadata[idx]
            ))
        
        return results
    
    def save(self, path: str):
        """保存索引"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(f"{path}.pkl", 'wb') as f:
            pickle.dump({
                'vectors': self.vectors,
                'texts': self.texts,
                'metadata': self.metadata,
                'dimension': self.dimension
            }, f)
    
    def load(self, path: str):
        """加载索引"""
        with open(f"{path}.pkl", 'rb') as f:
            data = pickle.load(f)
            self.vectors = data['vectors']
            self.texts = data['texts']
            self.metadata = data['metadata']
            self.dimension = data['dimension']


# ============================================================================
# 高级向量检索引擎
# ============================================================================

class VectorSearchEngine:
    """
    高级向量检索引擎
    
    自动选择最佳可用的向量化和存储方案：
    1. FAISS + Sentence Transformers（最佳）
    2. FAISS + TF-IDF（良好）
    3. Simple + TF-IDF（后备）
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        dimension: int = 384,
        cache_dir: str = ".vector_cache"
    ):
        """
        初始化向量检索引擎
        
        Args:
            model_name: Sentence Transformers 模型名称
            dimension: 向量维度（用于 TF-IDF 后备方案）
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # 选择向量化器
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.vectorizer = SentenceTransformerVectorizer(model_name)
                logger.info(f"✅ 使用 Sentence Transformers 向量化器")
            except Exception as e:
                logger.warning(f"Sentence Transformers 初始化失败: {e}")
                self.vectorizer = TFIDFVectorizer(dimension)
                logger.info("⚠️ 使用 TF-IDF 向量化器")
        else:
            self.vectorizer = TFIDFVectorizer(dimension)
            logger.info("⚠️ 使用 TF-IDF 向量化器")
        
        # 选择向量存储
        if FAISS_AVAILABLE:
            self.store = FAISSVectorStore(self.vectorizer.get_dimension())
            logger.info("✅ 使用 FAISS 向量存储")
        else:
            self.store = SimpleVectorStore(self.vectorizer.get_dimension())
            logger.info("⚠️ 使用简单向量存储")
    
    def index_documents(
        self,
        documents: List[Dict[str, Any]],
        text_key: str = "text",
        batch_size: int = 100
    ):
        """
        索引文档
        
        Args:
            documents: 文档列表
            text_key: 文本字段名
            batch_size: 批量处理大小
        """
        if not documents:
            logger.warning("没有文档需要索引")
            return
        
        texts = []
        metadata = []
        
        for doc in documents:
            text = doc.get(text_key, "")
            if text:
                texts.append(text)
                metadata.append({k: v for k, v in doc.items() if k != text_key})
        
        # 批量向量化
        logger.info(f"开始向量化 {len(texts)} 个文档...")
        
        all_vectors = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            batch_vectors = self.vectorizer.encode(batch_texts)
            all_vectors.append(batch_vectors)
        
        vectors = np.vstack(all_vectors)
        
        # 添加到存储
        self.store.add(vectors, texts, metadata)
        
        logger.info(f"✅ 索引完成，共 {len(texts)} 个文档")
    
    def search(
        self,
        query: str,
        k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[VectorSearchResult]:
        """
        搜索相似文档
        
        Args:
            query: 查询文本
            k: 返回结果数
            filters: 过滤条件（可选）
            
        Returns:
            搜索结果列表
        """
        # 向量化查询
        query_vector = self.vectorizer.encode([query])[0]
        
        # 搜索
        results = self.store.search(query_vector, k=k)
        
        # 应用过滤
        if filters:
            results = [
                r for r in results
                if all(r.metadata.get(k) == v for k, v in filters.items())
            ]
        
        return results
    
    def hybrid_search(
        self,
        query: str,
        keywords: List[str],
        k: int = 10,
        alpha: float = 0.7
    ) -> List[VectorSearchResult]:
        """
        混合搜索（向量 + 关键词）
        
        Args:
            query: 查询文本
            keywords: 关键词列表
            k: 返回结果数
            alpha: 向量搜索权重（0-1）
            
        Returns:
            搜索结果列表
        """
        # 向量搜索
        vector_results = self.search(query, k=k*2)
        
        # 关键词匹配
        keyword_scores = {}
        for result in vector_results:
            text_lower = result.text.lower()
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            keyword_scores[result.id] = score / max(len(keywords), 1)
        
        # 混合打分
        for result in vector_results:
            vector_score = result.score
            keyword_score = keyword_scores.get(result.id, 0)
            result.score = alpha * vector_score + (1 - alpha) * keyword_score
        
        # 重新排序
        vector_results.sort(key=lambda x: x.score, reverse=True)
        
        return vector_results[:k]
    
    def save_index(self, name: str):
        """保存索引"""
        path = os.path.join(self.cache_dir, name)
        self.store.save(path)
        logger.info(f"索引已保存: {name}")
    
    def load_index(self, name: str) -> bool:
        """加载索引"""
        path = os.path.join(self.cache_dir, name)
        
        try:
            self.store.load(path)
            logger.info(f"索引已加载: {name}")
            return True
        except Exception as e:
            logger.warning(f"加载索引失败: {e}")
            return False


# ============================================================================
# 工厂函数
# ============================================================================

def create_vector_engine(
    model_name: str = "all-MiniLM-L6-v2",
    cache_dir: str = ".vector_cache"
) -> VectorSearchEngine:
    """
    创建向量检索引擎
    
    Args:
        model_name: 模型名称
        cache_dir: 缓存目录
        
    Returns:
        VectorSearchEngine 实例
    """
    return VectorSearchEngine(model_name=model_name, cache_dir=cache_dir)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("向量检索引擎测试")
    print("=" * 70)
    
    # 创建引擎
    engine = create_vector_engine()
    
    # 测试文档
    documents = [
        {"id": 1, "text": "ABS 系统刹车失灵，需要紧急修复", "project": "ABS", "severity": "高"},
        {"id": 2, "text": "IDCEVO 显示屏闪烁问题", "project": "IDCEVO", "severity": "中"},
        {"id": 3, "text": "ABS 传感器故障导致报警", "project": "ABS", "severity": "高"},
        {"id": 4, "text": "测试用例覆盖率不足", "project": "测试", "severity": "低"},
        {"id": 5, "text": "刹车系统压力异常", "project": "ABS", "severity": "高"},
    ]
    
    # 索引文档
    engine.index_documents(documents)
    
    # 搜索
    print("\n搜索: '刹车问题'")
    results = engine.search("刹车问题", k=3)
    for r in results:
        print(f"  - [{r.score:.3f}] {r.text[:50]}... (项目: {r.metadata.get('project')})")
    
    # 混合搜索
    print("\n混合搜索: 'ABS 刹车' + 关键词 ['ABS', '刹车']")
    results = engine.hybrid_search("ABS 刹车", keywords=["ABS", "刹车"], k=3)
    for r in results:
        print(f"  - [{r.score:.3f}] {r.text[:50]}...")
