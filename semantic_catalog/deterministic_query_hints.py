import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List


_PROJECT_ALIAS_MAP = {
    "idcevo": ["idcevo", "idcevo25", "idc evo", "idc-evo", "idcevo_25", "idcevo-25"],
    "idc": ["idc", "idc4", "idc 4"],
    "mgu": ["mgu", "mgu22", "mgu21", "mgu18", "mgu 22"],
    "rsu": ["rsu", "rsu2", "rsu3"],
    "app": ["app", "application"],
}

_EN_STOP_WORDS = {
    "ticket", "topissue", "summary", "agent", "sqlite",
    "please", "kindly", "thanks", "thank", "thx", "assistant", "copilot", "chatgpt", "sisi",
    "showstopper", "confirmed", "candidate", "maturity",
    "preventing", "obstructing", "grade", "tag", "tags",
    "fv", "fvp",
    # 注意：以下业务词汇已从停用词中移除，避免误杀用户查询中的关键实体
    # "project", "team", "tester", "owner", "severity", "priority",
    # "issue", "defect", "status", "phase", "query",
    # "trend", "efficiency", "analysis", "analyze", "recommend", "recommendation", "improve", "optimization",
    # "aida", "reporter", "coverage", "frequency", "week", "monthly",
    # "passed", "failed", "blocked", "requires", "attention",
    # "matrix", "distribution", "severity", "priority", "risk", "count",
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

_MANUAL_RUN_DIRECT_TERMS = (
    "manual run",
    "manual runs",
    "testrun",
    "test run",
    "测试执行",
    "测试运行",
    "测试覆盖",
    "测试覆盖率",
    "覆盖率",
    "通过率",
    "执行状态",
    "run status",
    "execution status",
    "pass rate",
    "test frequency",
    "blocked",
    "failed",
    "passed",
    "requires attention",
    "测试用例执行",
    "测试用例执行情况",
    "用例执行",
    "用例执行情况",
    "testcase execution",
    "testcases execution",
    "test case execution",
    "test cases execution",
    "case execution",
)

_MANUAL_RUN_CONTEXT_TERMS = (
    "测试",
    "用例",
    "测试用例",
    "testcase",
    "testcases",
    "test case",
    "test cases",
    "manual run",
    "manual runs",
)

_MANUAL_RUN_EXECUTION_TERMS = (
    "执行",
    "执行情况",
    "执行状态",
    "执行进度",
    "运行情况",
    "通过情况",
    "execution",
    "run status",
    "execution status",
    "execution progress",
    "execution summary",
)

_MANUAL_RUN_PERSON_TERMS = (
    "测试人员",
    "测试员",
    "tester",
    "testers",
    "run by",
    "run_by",
    "author",
)

_MANUAL_RUN_CASE_TERMS = (
    "用例",
    "测试用例",
    "testcase",
    "testcases",
    "test case",
    "test cases",
    "case",
    "cases",
)

_MANUAL_RUN_ENTITY_SKIP_TERMS = {
    "test",
    "tests",
    "case",
    "cases",
    "testcase",
    "testcases",
    "execution",
    "status",
    "run",
    "runs",
    "manual",
    "coverage",
    "pass",
    "rate",
    "summary",
    "summarize",
}

_HISTORY_DIRECT_TERMS = (
    "history",
    "历史",
    "阶段变化",
    "phase",
    "phase history",
    "status history",
    "change history",
    "change log",
    "transition history",
    "state transition",
    "流转历史",
    "状态流转",
    "状态变更",
    "变更记录",
    "处理历史",
    "生命周期",
)

_HISTORY_ENTITY_SKIP_TERMS = {
    "history",
    "phase",
    "status",
    "change",
    "changes",
    "record",
    "records",
    "transition",
}

_HISTORY_ZH_SKIP_TERMS = (
    "历史",
    "流转历史",
    "状态流转",
    "状态变更",
    "变更记录",
    "状态变更记录",
    "阶段变化",
)

_QUERY_REGISTRY_REQUIRED_KEYS = {
    "target_tables",
    "required_dimensions",
    "parameter_slots",
    "output_contract",
    "constraints",
}

_QUERY_REGISTRY_REQUIRED_VALUE_TYPES = {
    "target_tables": list,
    "required_dimensions": list,
    "parameter_slots": dict,
    "output_contract": dict,
    "constraints": dict,
}

_LOGGER = logging.getLogger(__name__)


def _is_valid_query_registry_definition(definition: Dict[str, Any]) -> bool:
    if not _QUERY_REGISTRY_REQUIRED_KEYS.issubset(set(definition.keys())):
        return False
    for field, expected_type in _QUERY_REGISTRY_REQUIRED_VALUE_TYPES.items():
        if not isinstance(definition.get(field), expected_type):
            return False
    return True


def load_query_registry() -> Dict[str, Dict[str, Any]]:
    registry_path = Path(__file__).with_name("query_registry.json")

    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _LOGGER.warning("Failed to load query registry from %s: %s", registry_path, exc)
        return {}

    if not isinstance(payload, dict):
        return {}

    validated: Dict[str, Dict[str, Any]] = {}
    for family_name, definition in payload.items():
        if not isinstance(family_name, str):
            continue
        if not isinstance(definition, dict):
            continue
        if not _is_valid_query_registry_definition(definition):
            continue
        validated[family_name] = definition

    return validated


def _contains_any(text: str, terms: tuple) -> bool:
    return any(term in text for term in terms)


def _is_manual_run_question(question_text: str) -> bool:
    q = (question_text or "").lower()
    if _contains_any(q, _MANUAL_RUN_DIRECT_TERMS):
        return True
    if _contains_any(q, _MANUAL_RUN_CONTEXT_TERMS) and _contains_any(q, _MANUAL_RUN_EXECUTION_TERMS):
        return True
    return (
        _contains_any(q, _MANUAL_RUN_PERSON_TERMS)
        and _contains_any(q, _MANUAL_RUN_CASE_TERMS)
        and _contains_any(q, _MANUAL_RUN_EXECUTION_TERMS)
    )


def _is_history_question(question_text: str) -> bool:
    q = (question_text or "").lower()
    return _contains_any(q, _HISTORY_DIRECT_TERMS)


# Shared deterministic intent hints for runtime and regression to prevent rule drift.
def build_deterministic_query_hints(question: str, columns: Iterable[str]) -> Dict[str, Any]:
    q = str(question or "")
    ql = q.lower()
    manual_run_question = _is_manual_run_question(q)
    history_question = _is_history_question(q)

    en_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", q)
    zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,8}", q)

    entity_tokens: List[str] = []

    # P1: 先做项目别名匹配，补充标准化后的项目名
    q_lower = q.lower()
    seen_lower = set()
    for canonical, aliases in _PROJECT_ALIAS_MAP.items():
        for alias in aliases:
            if alias in q_lower:
                seen_lower.add(canonical.lower())
                entity_tokens.append(canonical)
                break

    for token in en_tokens:
        tl = token.lower()
        if tl in _EN_STOP_WORDS:
            continue
        if len(tl) <= 1:
            continue
        if tl in seen_lower:
            continue  # 已通过别名匹配添加，跳过重复
        if manual_run_question and tl in _MANUAL_RUN_ENTITY_SKIP_TERMS:
            continue
        if history_question and tl in _HISTORY_ENTITY_SKIP_TERMS:
            continue
        seen_lower.add(tl)
        entity_tokens.append(token)

    for token in zh_tokens:
        if token.startswith("请"):
            continue
        if token in _ZH_SKIP_EXACT:
            continue
        if any(k in token for k in _ZH_SKIP_CONTAINS):
            continue
        if manual_run_question and any(k in token for k in ["测试用例", "用例执行", "执行情况", "执行状态", "测试执行"]):
            continue
        if history_question and any(k in token for k in _HISTORY_ZH_SKIP_TERMS):
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
    wants_test_coverage = manual_run_question
    wants_recommendation = any(k in ql for k in ["建议", "recommend", "改进", "优化", "improve", "复盘", "对策"])

    wants_analysis = bool(
        wants_trend
        or wants_efficiency
        or wants_recommendation
        or wants_test_coverage
        or wants_matrix_severity
        or wants_aida_dist
    )

    # === 数值约束提取器 ===
    # 从用户自然语言中提取数值阈值条件
    numeric_constraints: List[Dict[str, Any]] = []
    _NUMERIC_PATTERNS: List[Dict[str, Any]] = [
        # ECU 乒乓次数
        {"field": "ecu_pingpong_count", "patterns": [
            r"ecu[^\w]*乒乓[^\w]*(?:超过|>=?|大于|不少于|至少)\s*(\d+)",
            r"ecu[^\w]*转移[^\w]*(?:超过|>=?|大于|不少于|至少)\s*(\d+)",
            r"ecu[^\w]*transfer[^\w]*(?:more than|>=?|over|at least)\s*(\d+)",
            r"乒乓[^\w]*(?:超过|>=?|大于|不少于|至少)\s*(\d+)\s*次",
            r"转移[^\w]*(?:超过|>=?|大于|不少于|至少)\s*(\d+)\s*次",
        ], "op": ">="},
        # Domain 乒乓次数
        {"field": "domain_pingpong_count", "patterns": [
            r"domain[^\w]*乒乓[^\w]*(?:超过|>=?|大于|不少于|至少)\s*(\d+)",
            r"域[^\w]*转移[^\w]*(?:超过|>=?|大于|不少于|至少)\s*(\d+)",
        ], "op": ">="},
        # 处理天数
        {"field": "processing_days", "patterns": [
            r"(?:处理|修复|解决|等待|开放).{0,4}(?:超过|>=?|大于|不少于|至少)\s*(\d+)\s*天",
            r"(?:超过|>=?|大于|不少于|至少)\s*(\d+)\s*天(?:未|没|没有)(?:处理|修复|解决|关闭)",
            r"long[^\w]*runner[^\w]*(?:more than|>=?|over|at least)\s*(\d+)",
            r"open[^\w]*(?:more than|>=?|over|at least)\s*(\d+)\s*days",
        ], "op": ">="},
        # TopIssue 风险分
        {"field": "topissue_risk_score", "patterns": [
            r"(?:风险分|评分|risk score).{0,4}(?:超过|>=?|大于|不少于|至少)\s*(\d+)",
            r"(?:超过|>=?|大于|不少于|至少)\s*(\d+)\s*分(?:的)?(?:风险|高分|topissue)",
        ], "op": ">="},
        # 子票数
        {"field": "child_count", "patterns": [
            r"子票.{0,4}(?:超过|>=?|大于|不少于|至少)\s*(\d+)",
            r"child.{0,4}(?:more than|>=?|over|at least)\s*(\d+)",
        ], "op": ">="},
    ]
    for constraint_def in _NUMERIC_PATTERNS:
        for pattern in constraint_def["patterns"]:
            match = re.search(pattern, ql)
            if match:
                try:
                    value = int(match.group(1))
                    if value > 0:
                        numeric_constraints.append({
                            "field": constraint_def["field"],
                            "op": constraint_def["op"],
                            "value": value,
                        })
                except (ValueError, IndexError):
                    pass
                break  # 每个字段只取第一个匹配

    # 隐含阈值推断：如果提到 ECU乒乓/高风险 但没给具体数值，给默认
    if any(k in ql for k in ["ecu乒乓", "ecu_pingpong", "ecus pingpong"]) and not any(c["field"] == "ecu_pingpong_count" for c in numeric_constraints):
        numeric_constraints.append({"field": "ecu_pingpong_count", "op": ">=", "value": 1})
    if any(k in ql for k in ["高风险票", "高风险缺陷", "topissue"]) and not any(c["field"] == "topissue_risk_score" for c in numeric_constraints):
        numeric_constraints.append({"field": "topissue_risk_score", "op": ">=", "value": 60})
    if any(k in ql for k in ["长期票", "长期未解决", "longrunner", "长周期"]) and not any(c["field"] == "processing_days" for c in numeric_constraints):
        numeric_constraints.append({"field": "processing_days", "op": ">=", "value": 30})

    # 区分测试人员查询意图：缺陷发现 vs 测试执行
    wants_tester_defects = wants_tester and not wants_test_coverage and any(
        k in ql for k in ["缺陷", "缺陷数", "bug", "issue", "发现", "提票", "提单", "报缺陷", "defect"]
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
        "numeric_constraints": numeric_constraints,
        "wants_tester_defects": wants_tester_defects,
        "columns": set(columns or []),
    }
