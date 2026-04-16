"""
Context Provider — 统一上下文构建

解决：context 准备逻辑散落在 process() 里上百行，不同环节各自拼装。
方案：每个 Provider 负责一类上下文，按优先级依次注入。

用法:
    chain = ContextChain([
        DataSummaryProvider(),
        SemanticCatalogProvider(),
        HistoryProvider(memory),
        BusinessKnowledgeProvider(),
    ])
    context = chain.build(data, question)
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class ContextProvider(ABC):
    """上下文提供者基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称，用于 tracing。"""

    @abstractmethod
    def provide(self, data: Any, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        """返回要注入的上下文 key-value。

        Args:
            data: 原始数据
            question: 用户问题
            existing: 已有的上下文（前面 Provider 注入的）

        Returns:
            新的上下文 key-value dict
        """

    def priority(self) -> int:
        """优先级，数字小的先执行。默认 100。"""
        return 100


class DataSummaryProvider(ContextProvider):
    """数据摘要 — 数据形状、列信息、统计。"""

    @property
    def name(self) -> str:
        return "data_summary"

    def priority(self) -> int:
        return 10  # 最先执行

    def provide(self, data: Any, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, pd.DataFrame) or data.empty:
            return {"data_summary": "无数据"}

        parts = []
        parts.append(f"数据集: {data.shape[0]} 行 × {data.shape[1]} 列")

        # 列信息
        dims = []
        measures = []
        for col in data.columns:
            if data[col].dtype == 'object' or str(data[col].dtype) == 'category':
                nunique = data[col].nunique()
                if nunique <= 30:
                    top_vals = data[col].value_counts().head(5)
                    dims.append(f"  {col}: {nunique}个值 ({', '.join(f'{v}({c})' for v, c in top_vals.items())})")
                else:
                    dims.append(f"  {col}: {nunique}个值")
            else:
                measures.append(f"  {col}: min={data[col].min()}, max={data[col].max()}, mean={data[col].mean():.1f}")

        if dims:
            parts.append("维度列:\n" + "\n".join(dims))
        if measures:
            parts.append("数值列:\n" + "\n".join(measures))

        # 时间范围
        time_cols = [c for c in data.columns if 'time' in c.lower() or 'date' in c.lower()]
        for tc in time_cols:
            try:
                ts = pd.to_datetime(data[tc])
                parts.append(f"时间范围: {ts.min()} ~ {ts.max()}")
            except Exception:
                pass

        return {"data_summary": "\n".join(parts)}


class SemanticCatalogProvider(ContextProvider):
    """语义目录 — 业务概念、规则、数据集定义。"""

    @property
    def name(self) -> str:
        return "semantic_catalog"

    def priority(self) -> int:
        return 20

    def provide(self, data: Any, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        try:
            from semantic_catalog.runtime import SemanticCatalog
            catalog = SemanticCatalog().load_catalog()
            if catalog:
                # 提取相关概念
                concepts = catalog.get("business_concepts", [])
                if concepts:
                    relevant = []
                    q_lower = question.lower()
                    for c in concepts:
                        name = str(c.get("name", ""))
                        aliases = [str(a) for a in c.get("aliases", [])]
                        if name.lower() in q_lower or any(a.lower() in q_lower for a in aliases):
                            relevant.append(c)
                    if relevant:
                        result["semantic_context"] = "\n".join(
                            f"- {c.get('name')}: {c.get('description', '')}" for c in relevant[:10]
                        )
                    else:
                        # 返回前5个核心概念
                        result["semantic_context"] = "\n".join(
                            f"- {c.get('name')}: {c.get('description', '')}" for c in concepts[:5]
                        )

                # 提取相关规则
                rules = catalog.get("business_rules", [])
                if rules:
                    risk_rules = [r for r in rules if "risk" in str(r.get("name", "")).lower()
                                  or "风险" in str(r.get("description", ""))]
                    if risk_rules:
                        result["business_rules"] = "\n".join(
                            f"- {r.get('name')}: {r.get('description', '')}" for r in risk_rules[:5]
                        )

                result["catalog_loaded"] = True
        except Exception as e:
            result["semantic_context"] = f"语义目录加载失败: {e}"
            result["catalog_loaded"] = False

        return result


class HistoryProvider(ContextProvider):
    """对话历史 — 从记忆中提取相关上下文。"""

    def __init__(self, memory=None):
        self._memory = memory

    @property
    def name(self) -> str:
        return "history"

    def priority(self) -> int:
        return 30

    def provide(self, data: Any, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        if not self._memory:
            return {}

        result = {}
        try:
            relevant = self._memory.get_relevant_history(question)
            if relevant:
                # Return both formats for compatibility
                result["relevant_history"] = relevant  # Original list of dicts
                # And a formatted string for LLM context
                history_items = []
                for h in relevant[:5]:
                    role = h.get("role", "unknown")
                    content = str(h.get("content", ""))[:200]
                    history_items.append(f"[{role}]: {content}")
                result["relevant_history_text"] = "\n".join(history_items)
        except Exception:
            pass

        return result


class BusinessKnowledgeProvider(ContextProvider):
    """业务知识注入 — 缺陷分析领域知识。"""

    KNOWLEDGE = """
## 缺陷分析领域知识

### 核心指标
- 缺陷密度: 缺陷数/测试用例数
- 严重缺陷率: Critical+Major / 总缺陷
- 关闭率: Closed / 总缺陷
- 平均修复时长: 从 New 到 Closed 的天数
- 乒乓率: 反复开关的缺陷比例

### 风险评估维度 (8维200分制)
1. 缺陷严重程度 (30分)
2. 缺陷数量趋势 (25分)
3. 影响范围 (25分)
4. 修复难度 (20分)
5. 修复紧迫度 (20分)
6. ECU关键性 (25分)
7. 历史重开率 (25分)
8. 测试覆盖率差距 (30分)

### 分析模式
- TOP Issue 分析: 按风险评分排序的缺陷清单
- Matrix分布: 缺陷在测试矩阵中的分布
- ECU乒乓分析: 同一ECU缺陷反复出现
- 趋势分析: 时间序列上的缺陷变化
- 根因分析: 从现象追溯到根因
"""

    @property
    def name(self) -> str:
        return "business_knowledge"

    def priority(self) -> int:
        return 40

    def provide(self, data: Any, question: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        return {"domain_knowledge": self.KNOWLEDGE.strip()}


class ContextChain:
    """上下文构建链 — 按优先级依次调用 Provider。"""

    def __init__(self, providers: Optional[List[ContextProvider]] = None):
        self._providers = sorted(providers or [], key=lambda p: p.priority())

    def add(self, provider: ContextProvider):
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority())

    def build(self, data: Any, question: str, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """构建完整上下文。"""
        context = dict(base or {})

        for provider in self._providers:
            try:
                additions = provider.provide(data, question, context)
                if isinstance(additions, dict):
                    context.update(additions)
            except Exception as e:
                logger.warning(f"Context provider '{provider.name}' failed: {e}")
                context[f"_provider_error_{provider.name}"] = str(e)

        return context

    @property
    def provider_names(self) -> List[str]:
        return [p.name for p in self._providers]


def create_default_context_chain(memory=None) -> ContextChain:
    """创建默认的上下文构建链。"""
    return ContextChain([
        DataSummaryProvider(),
        SemanticCatalogProvider(),
        HistoryProvider(memory),
        BusinessKnowledgeProvider(),
    ])
