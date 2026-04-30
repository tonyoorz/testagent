"""
Few-shot Templates — 正反工具调用示例

Layer 2: 推理策略层 — 给 LLM 提供正确的工具调用示例和常见错误示例，
引导模型做出正确的工具选择。

配合 tool_retriever.py 使用，AgenticDecider 注入到 system prompt。
"""

from typing import Any, Dict, List

# 每个 template 包含：user_query, correct_tool, correct_params, wrong_tool, reason
FEW_SHOT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "scenario": "缺陷趋势分析",
        "user_query": "最近一个月的缺陷趋势怎么样？",
        "correct_tool": "trend",
        "correct_params": {"granularity": "day", "days": 30},
        "wrong_tool": "matrix_distribution",
        "reason": "趋势分析应使用 trend 工具按时间维度展示变化，不是 matrix_distribution（矩阵分布）",
    },
    {
        "scenario": "风险评估",
        "user_query": "IDCevo 项目目前的风险怎么样？",
        "correct_tool": "risk",
        "correct_params": {"project": "IDCevo"},
        "wrong_tool": "defect_explore_kpis",
        "reason": "项目风险评估应使用 risk 工具，KPI 工具只提供基础统计指标",
    },
    {
        "scenario": "Matrix分布",
        "user_query": "各项目的 Matrix 等级分布",
        "correct_tool": "matrix_distribution",
        "correct_params": {},
        "wrong_tool": "trend",
        "reason": "Matrix 等级分布是横截面分析，不是时序趋势",
    },
    {
        "scenario": "TopIssue排查",
        "user_query": "当前最严重的 TopIssue 是什么？怎么解决？",
        "correct_tool": "root_cause",
        "correct_params": {},
        "wrong_tool": "defect_dashboard",
        "reason": "TopIssue 排查需要 root_cause 深度分析，dashboard 只是概览",
    },
    {
        "scenario": "测试人员分析",
        "user_query": "哪个测试人员发现的缺陷最多？",
        "correct_tool": "tester_findings",
        "correct_params": {},
        "wrong_tool": "project_health",
        "reason": "测试人员维度分析应使用 tester_findings，project_health 是项目整体健康度",
    },
    {
        "scenario": "长期未解决缺陷",
        "user_query": "有哪些缺陷长期没有关闭？",
        "correct_tool": "longrunner",
        "correct_params": {},
        "wrong_tool": "defect_explore_kpis",
        "reason": "长期未解决缺陷是 longrunner 工具的专项分析，KPI 不提供这个维度",
    },
    {
        "scenario": "异常检测",
        "user_query": "最近有没有什么异常情况？",
        "correct_tool": "anomaly_scan",
        "correct_params": {},
        "wrong_tool": "statistical_summary",
        "reason": "异常检测应使用 anomaly_scan 自动发现异常点，statistical_summary 只提供描述统计",
    },
    {
        "scenario": "多维对比",
        "user_query": "对比一下两个项目的缺陷分布差异",
        "correct_tool": "comparison",
        "correct_params": {},
        "wrong_tool": "groupby_aggregate",
        "reason": "跨项目对比应使用 comparison 工具，groupby_aggregate 是单数据集内的分组聚合",
    },
]


def get_relevant_templates(question: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """根据用户问题检索最相关的 few-shot 模板。

    简单策略：用关键词匹配 scenario 和 user_query。
    """
    q_lower = question.lower()
    scored = []

    for tpl in FEW_SHOT_TEMPLATES:
        score = 0.0
        # scenario 关键词
        for word in tpl["scenario"].split():
            if word in q_lower:
                score += 2.0
        # user_query 关键词匹配
        tpl_words = set(q_lower.split()) & set(tpl["user_query"].lower().split())
        score += len(tpl_words) * 1.0
        # correct_tool 名称在问题中出现
        if tpl["correct_tool"] in q_lower:
            score += 3.0

        scored.append((score, tpl))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [tpl for score, tpl in scored[:top_k] if score > 0]


def format_templates_for_prompt(templates: List[Dict[str, Any]]) -> str:
    """将模板格式化为 LLM system prompt 的一部分。"""
    if not templates:
        return ""

    parts = ["\n## 参考示例（正确 vs 错误的工具选择）：\n"]
    for i, tpl in enumerate(templates, 1):
        parts.append(
            f"{i}. 场景: {tpl['scenario']}\n"
            f'   用户问: "{tpl["user_query"]}"\n'
            f"   正确: {tpl['correct_tool']}({tpl['correct_params']})\n"
            f"   错误: {tpl['wrong_tool']} — {tpl['reason']}\n"
        )

    return "\n".join(parts)
