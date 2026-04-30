"""
Tool Retriever — 工具语义检索

Layer 2: 推理策略层 — 根据用户问题检索最相关的 top-K 工具，
避免把全部 26 个工具塞给 LLM（降低 token 消耗 + 提高选对概率）。

环境变量 AGENT_TOOL_RETRIEVAL=1 开启，默认关闭。

策略：
1. 关键词匹配：用户问题中的词 vs 工具名称/描述/参数中的关键词
2. 语义目录映射：business_concepts → 推荐工具
3. 意图关键词映射：预定义 意图→工具 的映射表
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

RETRIEVAL_ENABLED = os.getenv("AGENT_TOOL_RETRIEVAL", "0") == "1"

# 默认 top-K（给 LLM 的工具数量上限）
DEFAULT_TOP_K = 8

# ─── 意图关键词 → 工具映射 ───
INTENT_TOOL_MAP: Dict[str, List[str]] = {
    # 缺陷趋势
    "趋势": ["trend", "defect_explore_kpis", "anomaly_scan"],
    "trend": ["trend", "defect_explore_kpis", "anomaly_scan"],
    "变化": ["trend", "comparison", "anomaly_scan"],
    # 风险
    "风险": ["risk", "risk_heatmap", "predictive_risk", "project_health"],
    "risk": ["risk", "risk_heatmap", "predictive_risk", "project_health"],
    "topissue": ["topissue", "root_cause", "longrunner", "risk"],
    # Matrix / 分布
    "matrix": ["matrix_distribution", "matrix_aida", "defect_explore_kpis"],
    "分布": ["matrix_distribution", "groupby_aggregate", "statistical_summary"],
    "distribution": ["matrix_distribution", "groupby_aggregate", "statistical_summary"],
    # 对比
    "对比": ["comparison", "groupby_aggregate", "correlate"],
    "compare": ["comparison", "groupby_aggregate", "correlate"],
    "比较": ["comparison", "groupby_aggregate", "correlate"],
    # 测试人员
    "测试人员": ["tester_findings", "defect_explore_kpis", "groupby_aggregate"],
    "tester": ["tester_findings", "defect_explore_kpis", "groupby_aggregate"],
    # 长期/积压
    "长期": ["longrunner", "topissue", "root_cause"],
    "积压": ["longrunner", "topissue", "project_health"],
    "longrunner": ["longrunner", "topissue", "root_cause"],
    # 异常
    "异常": ["anomaly_scan", "association_discovery", "root_cause"],
    "anomaly": ["anomaly_scan", "association_discovery", "root_cause"],
    # 关联
    "关联": ["association_discovery", "correlate", "root_cause"],
    "correlat": ["association_discovery", "correlate"],
    # 根因
    "根因": ["root_cause", "anomaly_scan", "topissue", "association_discovery"],
    "why": ["root_cause", "anomaly_scan", "topissue"],
    "为什么": ["root_cause", "anomaly_scan", "topissue", "association_discovery"],
    # 看板/KPI
    "kpi": ["defect_explore_kpis", "defect_dashboard", "project_health"],
    "看板": ["defect_dashboard", "defect_explore_kpis", "project_health"],
    "dashboard": ["defect_dashboard", "defect_explore_kpis", "project_health"],
    # 概览/健康度
    "概览": ["project_health", "defect_dashboard", "defect_explore_kpis", "statistical_summary"],
    "health": ["project_health", "defect_dashboard", "defect_explore_kpis"],
    "健康": ["project_health", "defect_explore_kpis"],
    # 统计
    "统计": ["statistical_summary", "groupby_aggregate", "defect_explore_kpis"],
    "summary": ["statistical_summary", "groupby_aggregate"],
    # 测试策略
    "策略": ["test_strategy", "strategy_evaluator", "test_run"],
    "strategy": ["test_strategy", "strategy_evaluator", "test_run"],
    # 热力图
    "热力图": ["risk_heatmap", "risk", "matrix_distribution"],
    "heatmap": ["risk_heatmap", "risk", "matrix_distribution"],
    # AIDA
    "aida": ["matrix_aida", "defect_explore_kpis"],
    # 测试执行
    "测试执行": ["test_run", "defect_explore_kpis", "test_strategy"],
    "test_run": ["test_run", "test_strategy", "strategy_evaluator"],
    # 预测
    "预测": ["predictive_risk", "anomaly_scan", "trend"],
    "predict": ["predictive_risk", "anomaly_scan", "trend"],
    # 重复
    "重复": ["duplicate_search", "groupby_aggregate"],
    "duplicate": ["duplicate_search", "groupby_aggregate"],
    # SQL/查询
    "sql": ["nl_query", "query", "schema"],
    "查询": ["nl_query", "query", "schema"],
}

# 工具名称关键词（用于匹配用户问题中出现的工具名）
TOOL_NAME_KEYWORDS: Dict[str, str] = {
    "trend": "trend",
    "矩阵": "matrix_distribution",
    "matrix": "matrix_distribution",
    "topissue": "topissue",
    "长期": "longrunner",
    "longrunner": "longrunner",
    "热力图": "risk_heatmap",
    "heatmap": "risk_heatmap",
    "kpi": "defect_explore_kpis",
    "看板": "defect_dashboard",
    "dashboard": "defect_dashboard",
    "aida": "matrix_aida",
    "风险": "risk",
    "风险热力图": "risk_heatmap",
}


class ToolRetriever:
    """根据用户问题检索最相关的工具。"""

    def __init__(self, all_tool_schemas: Optional[List[Dict[str, Any]]] = None):
        """
        Args:
            all_tool_schemas: 全量工具 schema 列表（OpenAI function-calling 格式）
        """
        self._all_schemas = all_tool_schemas or []
        self._tool_names: List[str] = []
        self._tool_desc_map: Dict[str, str] = {}

        for schema in self._all_schemas:
            func = (schema.get("function") or schema) if isinstance(schema, dict) else {}
            name = func.get("name", "")
            desc = func.get("description", "")
            if name:
                self._tool_names.append(name)
                self._tool_desc_map[name] = desc.lower()

    def retrieve(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
        always_include: Optional[List[str]] = None,
    ) -> List[str]:
        """检索与问题最相关的 top-K 工具名称。

        Args:
            question: 用户问题
            top_k: 返回的最大工具数
            always_include: 无论得分如何都包含的工具名

        Returns:
            排序后的工具名列表（最相关的在前）
        """
        if not RETRIEVAL_ENABLED or not self._tool_names:
            return self._tool_names  # 未启用时返回全量

        q_lower = question.lower()
        scores: Dict[str, float] = {name: 0.0 for name in self._tool_names}

        # 1. 意图关键词匹配
        for keyword, tools in INTENT_TOOL_MAP.items():
            if keyword in q_lower:
                for tool in tools:
                    if tool in scores:
                        scores[tool] += 2.0

        # 2. 工具名称直接匹配
        for keyword, tool_name in TOOL_NAME_KEYWORDS.items():
            if keyword in q_lower and tool_name in scores:
                scores[tool_name] += 3.0  # 直接提到工具名，高分

        # 3. 描述关键词匹配
        q_words = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]+", q_lower))
        for name, desc in self._tool_desc_map.items():
            desc_words = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]+", desc))
            overlap = len(q_words & desc_words)
            if overlap > 0:
                scores[name] += overlap * 0.5

        # 4. 排序取 top-K
        sorted_tools = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 确保所有得分>0的都包含，但不超过 top_k
        result = [name for name, score in sorted_tools if score > 0][:top_k]

        # 补充 always_include
        if always_include:
            for name in always_include:
                if name in scores and name not in result:
                    result.append(name)

        # 兜底：如果没有任何匹配，返回前 top_k 个
        if not result:
            result = self._tool_names[:top_k]

        logger.debug(f"工具检索: question='{question[:50]}' → {result}")
        return result

    def filter_schemas(self, question: str, top_k: int = DEFAULT_TOP_K) -> List[Dict[str, Any]]:
        """检索并返回对应的 tool schemas（直接传给 LLM）。"""
        selected_names = self.retrieve(question, top_k)
        selected_set = set(selected_names)

        result = []
        for schema in self._all_schemas:
            func = (schema.get("function") or schema) if isinstance(schema, dict) else {}
            name = func.get("name", "")
            if name in selected_set:
                result.append(schema)

        return result
