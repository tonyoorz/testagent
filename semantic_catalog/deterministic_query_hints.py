import re
from typing import Any, Dict, Iterable, List


_EN_STOP_WORDS = {
    "aida", "ticket", "topissue", "issue", "defect", "summary", "agent", "sqlite",
    "tester", "reporter", "owner", "team", "project", "status", "phase", "query",
    "trend", "efficiency", "analysis", "analyze", "recommend", "recommendation", "improve", "optimization",
    "passed", "failed", "blocked", "requires", "attention", "coverage", "frequency", "week", "monthly",
    "please", "kindly", "thanks", "thank", "thx", "assistant", "copilot", "chatgpt", "sisi",
    "matrix", "distribution", "severity", "priority", "risk",
    "showstopper", "confirmed", "candidate", "maturity",
    "preventing", "obstructing", "grade", "tag", "tags", "count",
    "fv", "fvp",
}

_TOPISSUE_TERMS = [
    "topissue", "top issue", "high risk", "risk matrix", "showstopper", "maturity",
    "showstopper_confirmed", "showstopper_candidate", "preventing_maturity", "obstructing_maturity",
    "showstopper confirmed", "showstopper candidate", "preventing maturity", "obstructing maturity",
]

_ZH_SKIP_EXACT = {"您好", "你好", "请问", "麻烦", "谢谢", "辛苦", "布和", "多少"}

_ZH_SKIP_CONTAINS = [
    "提票", "情况", "如何", "分析", "查询", "统计", "数据", "测试", "缺陷", "团队", "项目",
    "建议", "改进", "优化", "趋势", "效率", "复盘", "对策", "提升", "比较", "执行状态",
    "通过率", "覆盖率", "关闭率", "周变化", "周趋势", "高风险", "数据库", "优先处理", "状态分布",
    "分布", "矩阵", "维度", "严重", "严重性", "等级", "占比", "比例", "问题",
    "业务关注", "关注", "相关区域", "我们业务",
]


# Shared deterministic intent hints for runtime and regression to prevent rule drift.
def build_deterministic_query_hints(question: str, columns: Iterable[str]) -> Dict[str, Any]:
    q = str(question or "")
    ql = q.lower()

    en_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", q)
    zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,8}", q)

    entity_tokens: List[str] = []

    for token in en_tokens:
        tl = token.lower()
        if tl in _EN_STOP_WORDS:
            continue
        if len(tl) <= 1:
            continue
        entity_tokens.append(token)

    for token in zh_tokens:
        if token.startswith("请"):
            continue
        if token in _ZH_SKIP_EXACT:
            continue
        if any(k in token for k in _ZH_SKIP_CONTAINS):
            continue
        entity_tokens.append(token)

    dedup_tokens: List[str] = []
    seen = set()
    for token in entity_tokens:
        tl = str(token).strip().lower()
        if not tl or tl in seen:
            continue
        seen.add(tl)
        dedup_tokens.append(str(token).strip())

    wants_distribution = any(k in ql for k in ["分布", "distribution", "占比", "比例"])
    wants_matrix = any(k in ql for k in ["矩阵", "matrix"])
    wants_severity = any(k in ql for k in [
        "严重性", "severity", "严重等级", "等级", "priority", "critical", "major", "minor", "s1", "s2", "s3",
        "showstopper", "maturity",
    ])
    wants_matrix_severity = bool(wants_matrix or (wants_distribution and wants_severity))
    wants_aida_dist = (
        ("aida" in ql)
        or any(k in ql for k in ["fv", "fvp", "feature version", "solution cluster", "业务域", "功能域", "domain"])
        or (wants_distribution and any(k in ql for k in ["领域", "模块", "domain"]))
    )
    wants_topissue = any(k in ql for k in [
        "高风险", "风险", "风险矩阵", "1a", "1b", "1c", "1d", "1e",
    ]) or any(k in ql for k in _TOPISSUE_TERMS)
    wants_business_tag_focus = any(k in ql for k in [
        "showstopper", "candidate", "confirmed", "maturity", "topissue", "top issue",
        "候选", "确认", "成熟度", "标签",
    ])
    wants_detail = any(k in ql for k in ["详情", "详细", "detail", "ticket", "列表", "哪些"])
    wants_tester = any(k in ql for k in [
        "提票", "提单", "报缺陷", "提交人", "报告人", "发现人", "测试员", "测试人员", "tester", "reporter",
        "found by", "found_by", "detected by", "detected_by",
    ])
    wants_trend = any(k in ql for k in ["趋势", "trend", "走势", "变化", "周", "月"])
    wants_efficiency = any(k in ql for k in ["效率", "efficiency", "修复", "关闭率", "通过率", "处理时长", "时效"])
    wants_test_coverage = any(k in ql for k in [
        "测试覆盖", "覆盖率", "pass rate", "test frequency", "通过率", "执行状态", "run status", "blocked", "requires attention",
    ])
    wants_recommendation = any(k in ql for k in ["建议", "recommend", "改进", "优化", "improve", "复盘", "对策"])

    wants_analysis = bool(
        wants_trend
        or wants_efficiency
        or wants_recommendation
        or wants_test_coverage
        or wants_matrix_severity
        or wants_aida_dist
    )

    return {
        "entity_tokens": dedup_tokens[:6],
        "wants_distribution": wants_distribution,
        "wants_matrix": wants_matrix,
        "wants_severity": wants_severity,
        "wants_matrix_severity": wants_matrix_severity,
        "wants_aida_dist": wants_aida_dist,
        "wants_topissue": wants_topissue,
        "wants_business_tag_focus": wants_business_tag_focus,
        "wants_detail": wants_detail,
        "wants_tester": wants_tester,
        "wants_trend": wants_trend,
        "wants_efficiency": wants_efficiency,
        "wants_test_coverage": wants_test_coverage,
        "wants_recommendation": wants_recommendation,
        "wants_analysis": wants_analysis,
        "columns": set(columns or []),
    }
