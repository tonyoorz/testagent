import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from semantic_catalog.deterministic_query_hints import build_deterministic_query_hints

try:
    from semantic_catalog.term_adapter import build_unified_query_intent
except Exception:
    build_unified_query_intent = None  # type: ignore[assignment]


_EN_STOP_WORDS = {
    "aida", "ticket", "topissue", "issue", "defect", "summary", "agent", "sqlite",
    "tester", "reporter", "owner", "team", "project", "status", "phase", "query",
    "trend", "efficiency", "analysis", "analyze", "recommend", "recommendation", "improve", "optimization",
    "showstopper", "candidate",
    "passed", "failed", "blocked", "requires", "attention", "coverage", "frequency", "week", "monthly",
    "please", "kindly", "thanks", "thank", "thx", "assistant", "copilot", "chatgpt", "sisi",
    "matrix", "distribution", "severity", "priority",
}

_CONFIRMATION_REPLY_TERMS = {
    "继续", "继续执行", "确认", "确认执行", "是", "好的", "好",
    "ok", "yes", "y", "proceed", "continue",
    "取消", "停止", "不执行", "算了", "否", "不要",
    "no", "n", "cancel", "stop",
}

_SCOPE_TEAM_DISABLED_TOKENS = {
    "*",
    "all",
    "any",
    "none",
    "off",
    "false",
    "0",
}

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
    "测试用例情况",
    "用例情况",
    "testcase status",
    "test case status",
    "test cases status",
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

_MANUAL_RUN_CASE_SUMMARY_TERMS = (
    "测试用例情况",
    "用例情况",
    "case status",
    "cases status",
    "testcase status",
    "test case status",
    "test cases status",
)

_RELATIVE_PERIOD_ALIASES: Dict[str, tuple] = {
    "last_week": ("上周", "上星期", "上一周", "last week"),
    "this_week": ("本周", "这周", "本星期", "this week"),
    "last_month": ("上月", "上个月", "last month"),
    "this_month": ("本月", "这个月", "this month"),
}

_MATRIX_LEVEL_TOKEN_PATTERN = re.compile(r"^[1-5][a-e]?$", re.IGNORECASE)


def _normalize_relative_period(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for canonical, aliases in _RELATIVE_PERIOD_ALIASES.items():
        for alias in aliases:
            if text == alias.lower():
                return canonical
    if text in _RELATIVE_PERIOD_ALIASES:
        return text
    return ""


def _normalize_week_year(value: Any) -> Optional[int]:
    try:
        year = int(value)
    except Exception:
        return None
    if 2000 <= year <= 2100:
        return year
    return None


def _normalize_week_number(value: Any) -> Optional[int]:
    try:
        week_number = int(value)
    except Exception:
        return None
    if 1 <= week_number <= 53:
        return week_number
    return None


def _normalize_rolling_days(value: Any) -> Optional[int]:
    try:
        days = int(value)
    except Exception:
        return None
    if 1 <= days <= 366:
        return days
    return None


def _normalize_matrix_level(value: Any) -> str:
    token = str(value or "").strip().lower()
    token = token.replace(" ", "").replace("-", "")
    if token.startswith("matrix"):
        token = token[6:]
    if token.startswith("矩阵"):
        token = token[2:]
    if _MATRIX_LEVEL_TOKEN_PATTERN.match(token):
        return token
    return ""


def _extract_matrix_levels_from_question(question_text: str) -> List[str]:
    q = str(question_text or "")
    ql = q.lower()
    levels: List[str] = []

    for match in re.finditer(r"(?:matrix|矩阵)\s*([1-5](?:[a-e])?)", ql, flags=re.IGNORECASE):
        normalized = _normalize_matrix_level(match.group(1))
        if normalized:
            levels.append(normalized)

    if ("matrix" in ql) or ("矩阵" in q):
        for match in re.finditer(r"\b([1-5][a-e])\b", ql, flags=re.IGNORECASE):
            normalized = _normalize_matrix_level(match.group(1))
            if normalized:
                levels.append(normalized)

    dedup_levels: List[str] = []
    seen = set()
    for item in levels:
        if item and item not in seen:
            seen.add(item)
            dedup_levels.append(item)
    return dedup_levels[:6]


def _extract_explicit_week_scope(question_text: str) -> Dict[str, Any]:
    q = str(question_text or "")
    ql = q.lower()

    patterns_with_year = [
        re.search(r"\b(20\d{2})\s*[-_/]?\s*(?:cw|w)\s*([0-4]?\d|5[0-3])\b", ql),
        re.search(r"(20\d{2})\s*年\s*第?\s*([0-4]?\d|5[0-3])\s*(?:周|星期)", q),
    ]
    for match in patterns_with_year:
        if not match:
            continue
        year = _normalize_week_year(match.group(1))
        week_number = _normalize_week_number(match.group(2))
        if year is not None and week_number is not None:
            return {
                "week_year": year,
                "week_number": week_number,
                "test_week": f"{year}-CW{week_number:02d}",
            }

    patterns_without_year = [
        re.search(r"\b(?:cw|w)\s*([0-4]?\d|5[0-3])\b", ql),
        re.search(r"第?\s*([0-4]?\d|5[0-3])\s*(?:周|星期)", q),
    ]
    for match in patterns_without_year:
        if not match:
            continue
        week_number = _normalize_week_number(match.group(1))
        if week_number is None:
            continue
        iso_year = int(datetime.now().isocalendar()[0])
        return {
            "week_year": iso_year,
            "week_number": week_number,
            "test_week": f"{iso_year}-CW{week_number:02d}",
        }

    return {}


def _extract_time_scope_from_question(question_text: str) -> Dict[str, Any]:
    q = str(question_text or "")
    ql = q.lower()

    out: Dict[str, Any] = {
        "relative_period": "",
        "rolling_days": None,
        "week_year": None,
        "week_number": None,
        "test_week": "",
    }

    if any(token in q for token in ["最近一周", "近一周"]) or any(token in ql for token in ["last 7 days", "past 7 days", "recent 7 days"]):
        out["rolling_days"] = 7

    zh_days = re.search(r"(?:最近|近|过去)\s*(\d{1,3})\s*天", q)
    en_days = re.search(r"\b(?:last|past|recent)\s*(\d{1,3})\s*days?\b", ql)
    day_match = zh_days or en_days
    if day_match:
        days = _normalize_rolling_days(day_match.group(1))
        if days is not None:
            out["rolling_days"] = days

    relative_period = ""
    for canonical, aliases in _RELATIVE_PERIOD_ALIASES.items():
        if any(alias in q for alias in aliases if not alias.isascii()) or any(alias in ql for alias in aliases if alias.isascii()):
            relative_period = canonical
            break
    if relative_period:
        out["relative_period"] = relative_period

    explicit_week = _extract_explicit_week_scope(q)
    if explicit_week:
        out.update(explicit_week)

    return out

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

_STRUCTURED_QUERY_TERMS = (
    "trend",
    "distribution",
    "top ",
    "top-",
    "top_",
    "topn",
    "top n",
    "ranking",
    "rank",
    "pass rate",
    "manual run",
    "manual runs",
    "matrix",
    "aida",
    "risk",
    "test coverage",
    "测试通过率",
    "通过率",
    "覆盖率",
    "趋势",
    "分布",
    "排行",
    "排名",
    "top",
    "矩阵",
    "风险",
    "测试覆盖",
)

_WEAK_QUERY_TERMS = (
    "root cause",
    "root-cause",
    "recommendation",
    "recommend",
    "advice",
    "define",
    "definition",
    "what is",
    "why",
    "how to improve",
    "根因",
    "原因",
    "建议",
    "定义",
    "是什么",
    "为什么",
    "如何改进",
)

_STRONG_STRUCTURED_QUERY_TERMS = (
    "compare",
    "comparison",
    "vs",
    "versus",
    "count",
    "counts",
    "统计",
    "数量",
    "总数",
    "多少",
    "占比",
    "比例",
    "对比",
    "比较",
    "环比",
    "同比",
)

_PROJECT_DIMENSION_TERMS = (
    "各项目",
    "项目",
    "project",
    "projects",
    "团队",
    "team",
    "teams",
)

_PROJECT_ANALYSIS_TERMS = (
    "对比",
    "比较",
    "分析",
    "分布",
    "情况",
    "compare",
    "comparison",
    "breakdown",
    "overview",
    "across",
)


def _contains_any(text: str, terms: tuple) -> bool:
    return any(term in text for term in terms)


def _has_strong_structured_intent(question_text: str) -> bool:
    q = str(question_text or "")
    ql = q.lower()
    if _contains_any(ql, _STRONG_STRUCTURED_QUERY_TERMS):
        return True
    if re.search(r"\btop\s*\d+\b", ql) or re.search(r"前\s*\d+", q):
        return True
    if re.search(r"\bby\s+(week|month|team|project|owner|tester)\b", ql):
        return True
    return False


def _extract_scope_team_from_hints(semantic_hints: Optional[Dict[str, Any]]) -> str:
    if not isinstance(semantic_hints, dict):
        return ""
    for key in ["scope_team", "force_team", "team_scope"]:
        value = str(semantic_hints.get(key) or "").strip()
        if value and value.lower() not in _SCOPE_TEAM_DISABLED_TOKENS:
            return value
    return ""


def _normalize_entity_token(token: Any) -> str:
    text = str(token or "").strip().lower()
    return text.strip(" \t\r\n,，。.!！？、；;:：")


def _is_noise_entity_token(token: Any) -> bool:
    normalized = _normalize_entity_token(token)
    if not normalized:
        return True
    if _normalize_matrix_level(normalized):
        return True
    return normalized in _EN_STOP_WORDS or normalized in _CONFIRMATION_REPLY_TERMS


def _is_manual_run_question(question_text: str) -> bool:
    q = (question_text or "").lower()
    if _contains_any(q, _MANUAL_RUN_DIRECT_TERMS):
        return True
    if _contains_any(q, _MANUAL_RUN_CASE_TERMS) and _contains_any(q, _MANUAL_RUN_CASE_SUMMARY_TERMS):
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


def guess_target_table(question_text: str) -> str:
    q = (question_text or "").lower()
    if _is_manual_run_question(q):
        return "octane_manual_runs"
    if _is_history_question(q):
        return "octane_defect_histories"
    return "octane_defects"


def _extract_semantic_hints_from_unified_intent(unified_intent: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(unified_intent, dict):
        return {}

    merged: Dict[str, Any] = {}

    entity_filters = unified_intent.get("entity_filters")
    if isinstance(entity_filters, list):
        merged["entity_tokens"] = [str(t).strip() for t in entity_filters if str(t).strip()]

    semantic_constraints = unified_intent.get("semantic_constraints")
    if isinstance(semantic_constraints, dict):
        for key, value in semantic_constraints.items():
            if isinstance(value, bool) and value:
                merged[key] = True
            elif key == "preferred_dimension":
                preferred_dimension = str(value or "").strip()
                if preferred_dimension:
                    merged["preferred_dimension"] = preferred_dimension
            elif key == "mapped_dimensions" and isinstance(value, list):
                normalized_dims = [str(item or "").strip() for item in value if str(item or "").strip()]
                if normalized_dims:
                    merged["mapped_dimensions"] = normalized_dims[:16]
            elif key == "month_number" and isinstance(value, int) and 1 <= value <= 12:
                merged["month_number"] = value
            elif key == "week_year":
                normalized_year = _normalize_week_year(value)
                if normalized_year is not None:
                    merged["week_year"] = normalized_year
            elif key == "week_number":
                normalized_week = _normalize_week_number(value)
                if normalized_week is not None:
                    merged["week_number"] = normalized_week
            elif key == "rolling_days":
                normalized_days = _normalize_rolling_days(value)
                if normalized_days is not None:
                    merged["rolling_days"] = normalized_days
            elif key == "relative_period":
                normalized_period = _normalize_relative_period(value)
                if normalized_period:
                    merged["relative_period"] = normalized_period
            elif key == "test_week":
                test_week = str(value or "").strip()
                if test_week:
                    merged["test_week"] = test_week

    time_scope = unified_intent.get("time_scope")
    if isinstance(time_scope, dict):
        month_number = time_scope.get("month_number")
        if isinstance(month_number, int) and 1 <= month_number <= 12 and merged.get("month_number") is None:
            merged["month_number"] = month_number

        week_year = _normalize_week_year(time_scope.get("week_year"))
        if week_year is not None and merged.get("week_year") is None:
            merged["week_year"] = week_year

        week_number = _normalize_week_number(time_scope.get("week_number"))
        if week_number is not None and merged.get("week_number") is None:
            merged["week_number"] = week_number

        rolling_days = _normalize_rolling_days(time_scope.get("rolling_days"))
        if rolling_days is not None and merged.get("rolling_days") is None:
            merged["rolling_days"] = rolling_days

        relative_period = _normalize_relative_period(time_scope.get("relative_period") or time_scope.get("period"))
        if relative_period and not merged.get("relative_period"):
            merged["relative_period"] = relative_period

        test_week = str(time_scope.get("test_week") or "").strip()
        if test_week and not str(merged.get("test_week") or "").strip():
            merged["test_week"] = test_week

    return merged


def _is_valid_month_number(value: Any) -> bool:
    return isinstance(value, int) and 1 <= value <= 12


def _is_meaningful_semantic_value(key: str, value: Any) -> bool:
    if key == "preferred_dimension":
        return bool(str(value or "").strip())
    if key == "month_number":
        return _is_valid_month_number(value)
    if key == "week_year":
        return _normalize_week_year(value) is not None
    if key == "week_number":
        return _normalize_week_number(value) is not None
    if key == "rolling_days":
        return _normalize_rolling_days(value) is not None
    if key == "relative_period":
        return bool(_normalize_relative_period(value))
    if key == "test_week":
        return bool(str(value or "").strip())
    if key == "entity_tokens" and isinstance(value, list):
        return any(str(token or "").strip() for token in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _should_adapt_with_unified_intent(semantic_hints: Optional[Dict[str, Any]]) -> bool:
    return not (isinstance(semantic_hints, dict) and bool(semantic_hints))


def extract_query_hints(
    question: str,
    columns: List[str],
    semantic_hints: Optional[Dict[str, Any]] = None,
    adapt_with_unified_intent: bool = True,
) -> Dict[str, Any]:
    q = str(question or "")
    ql = q.lower()

    base_semantic_hints = semantic_hints if isinstance(semantic_hints, dict) else {}
    unified_semantic_hints: Dict[str, Any] = {}
    if adapt_with_unified_intent and callable(build_unified_query_intent):
        try:
            unified_intent = build_unified_query_intent(
                question=q,
                columns=columns,
                table_name=guess_target_table(q),
                semantic_hints=base_semantic_hints,
            )
            unified_semantic_hints = _extract_semantic_hints_from_unified_intent(unified_intent)
        except Exception:
            unified_semantic_hints = {}

    semantic_hints = dict(unified_semantic_hints)
    if base_semantic_hints:
        for key, value in base_semantic_hints.items():
            if key == "entity_tokens" and isinstance(value, list):
                tokens = semantic_hints.setdefault("entity_tokens", [])
                if not isinstance(tokens, list):
                    tokens = []
                    semantic_hints["entity_tokens"] = tokens
                seen = {_normalize_entity_token(t) for t in tokens if _normalize_entity_token(t)}
                for token in value:
                    text = str(token or "").strip()
                    text_l = _normalize_entity_token(text)
                    if not text or not text_l or text_l in seen or _is_noise_entity_token(text):
                        continue
                    seen.add(text_l)
                    tokens.append(text)
            elif key == "preferred_dimension":
                preferred_dimension = str(value or "").strip()
                if preferred_dimension:
                    semantic_hints["preferred_dimension"] = preferred_dimension
            elif key == "month_number":
                if _is_valid_month_number(value):
                    semantic_hints["month_number"] = value
            elif isinstance(value, bool):
                if value:
                    semantic_hints[key] = True
            else:
                if _is_meaningful_semantic_value(key, value):
                    semantic_hints[key] = value

    shared_hints = build_deterministic_query_hints(q, columns)
    dedup_tokens: List[str] = []
    seen = set()
    for token in (shared_hints.get("entity_tokens") or []):
        text = str(token or "").strip()
        normalized = _normalize_entity_token(text)
        if not text or not normalized or normalized in seen or _is_noise_entity_token(text):
            continue
        seen.add(normalized)
        dedup_tokens.append(text)

    wants_distribution = bool(shared_hints.get("wants_distribution"))
    wants_matrix = bool(shared_hints.get("wants_matrix"))
    wants_severity = bool(shared_hints.get("wants_severity"))
    wants_matrix_severity = bool(shared_hints.get("wants_matrix_severity"))
    wants_aida_dist = bool(shared_hints.get("wants_aida_dist"))
    wants_topissue = bool(shared_hints.get("wants_topissue"))
    wants_detail = bool(shared_hints.get("wants_detail"))
    wants_tester = bool(shared_hints.get("wants_tester"))
    wants_trend = bool(shared_hints.get("wants_trend"))
    wants_efficiency = bool(shared_hints.get("wants_efficiency"))
    wants_test_coverage = bool(shared_hints.get("wants_test_coverage"))
    wants_recommendation = bool(shared_hints.get("wants_recommendation"))
    wants_analysis = bool(shared_hints.get("wants_analysis"))
    wants_project_breakdown = bool(shared_hints.get("wants_project_breakdown"))

    project_dimension_requested = _contains_any(ql, _PROJECT_DIMENSION_TERMS)
    project_analysis_requested = _contains_any(ql, _PROJECT_ANALYSIS_TERMS)
    if project_dimension_requested and project_analysis_requested:
        wants_project_breakdown = True
        wants_analysis = True

    if guess_target_table(q) == "octane_manual_runs":
        wants_test_coverage = True
        wants_analysis = True

    wants_feature_breakdown = any(
        k in ql
        for k in ["功能", "哪些功能", "模块", "领域", "feature", "features", "module", "service", "aida"]
    )
    wants_aida_dist = bool(
        wants_aida_dist
        or wants_feature_breakdown
        or ("aida" in ql)
        or (wants_distribution and any(k in ql for k in ["领域", "模块", "domain", "功能", "feature"]))
    )

    wants_showstopper = bool(shared_hints.get("wants_business_tag_focus")) or any(
        k in ql for k in ["showstopper candidate", "showstopper", "show stopper"]
    )

    month_number: Optional[int] = None
    month_match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*月", q)
    if month_match:
        try:
            month_number = int(month_match.group(1))
        except Exception:
            month_number = None

    parsed_time_scope = _extract_time_scope_from_question(q)
    relative_period = str(parsed_time_scope.get("relative_period") or "").strip()
    rolling_days = _normalize_rolling_days(parsed_time_scope.get("rolling_days"))
    week_year = _normalize_week_year(parsed_time_scope.get("week_year"))
    week_number = _normalize_week_number(parsed_time_scope.get("week_number"))
    test_week = str(parsed_time_scope.get("test_week") or "").strip()
    matrix_levels = _extract_matrix_levels_from_question(q)

    if semantic_hints:
        semantic_tokens = semantic_hints.get("entity_tokens")
        if isinstance(semantic_tokens, list):
            for token in semantic_tokens:
                text = str(token or "").strip()
                text_l = _normalize_entity_token(text)
                if not text or not text_l or text_l in seen or _is_noise_entity_token(text):
                    continue
                seen.add(text_l)
                dedup_tokens.append(text)

        wants_feature_breakdown = wants_feature_breakdown or bool(semantic_hints.get("wants_feature_breakdown"))
        wants_aida_dist = wants_aida_dist or bool(semantic_hints.get("wants_aida_dist"))
        wants_showstopper = wants_showstopper or bool(semantic_hints.get("wants_showstopper"))
        wants_project_breakdown = wants_project_breakdown or bool(semantic_hints.get("wants_project_breakdown"))

        semantic_month = semantic_hints.get("month_number")
        if month_number is None and isinstance(semantic_month, int) and 1 <= semantic_month <= 12:
            month_number = semantic_month

        semantic_relative_period = _normalize_relative_period(semantic_hints.get("relative_period"))
        if not relative_period and semantic_relative_period:
            relative_period = semantic_relative_period

        semantic_rolling_days = _normalize_rolling_days(semantic_hints.get("rolling_days"))
        if rolling_days is None and semantic_rolling_days is not None:
            rolling_days = semantic_rolling_days

        semantic_week_year = _normalize_week_year(semantic_hints.get("week_year"))
        if week_year is None and semantic_week_year is not None:
            week_year = semantic_week_year

        semantic_week_number = _normalize_week_number(semantic_hints.get("week_number"))
        if week_number is None and semantic_week_number is not None:
            week_number = semantic_week_number

        semantic_test_week = str(semantic_hints.get("test_week") or "").strip()
        if not test_week and semantic_test_week:
            test_week = semantic_test_week

        semantic_matrix_levels = semantic_hints.get("matrix_levels")
        if isinstance(semantic_matrix_levels, list):
            seen_levels = {lvl for lvl in matrix_levels}
            for item in semantic_matrix_levels:
                normalized_level = _normalize_matrix_level(item)
                if normalized_level and normalized_level not in seen_levels:
                    seen_levels.add(normalized_level)
                    matrix_levels.append(normalized_level)

        semantic_time_scope = semantic_hints.get("time_scope") if isinstance(semantic_hints.get("time_scope"), dict) else {}
        if semantic_time_scope:
            if not relative_period:
                relative_period = _normalize_relative_period(semantic_time_scope.get("relative_period") or semantic_time_scope.get("period"))
            if rolling_days is None:
                rolling_days = _normalize_rolling_days(semantic_time_scope.get("rolling_days"))
            if week_year is None:
                week_year = _normalize_week_year(semantic_time_scope.get("week_year"))
            if week_number is None:
                week_number = _normalize_week_number(semantic_time_scope.get("week_number"))
            if not test_week:
                test_week = str(semantic_time_scope.get("test_week") or "").strip()

    wants_showstopper_candidate = ("candidate" in ql) or bool(semantic_hints.get("wants_showstopper_candidate"))
    if matrix_levels:
        wants_matrix = True
        wants_matrix_severity = True
    preferred_dimension = str(semantic_hints.get("preferred_dimension") or "").strip()
    scope_team = _extract_scope_team_from_hints(semantic_hints)
    if preferred_dimension in {"project", "tproject", "team"}:
        wants_project_breakdown = True
        wants_analysis = True

    return {
        "entity_tokens": dedup_tokens[:6],
        "wants_distribution": wants_distribution,
        "wants_matrix": wants_matrix,
        "wants_severity": wants_severity,
        "wants_matrix_severity": wants_matrix_severity,
        "wants_feature_breakdown": wants_feature_breakdown,
        "wants_showstopper": wants_showstopper,
        "wants_showstopper_candidate": wants_showstopper_candidate,
        "wants_aida_dist": wants_aida_dist,
        "wants_topissue": wants_topissue,
        "wants_detail": wants_detail,
        "wants_tester": wants_tester,
        "wants_trend": wants_trend,
        "wants_efficiency": wants_efficiency,
        "wants_test_coverage": wants_test_coverage,
        "wants_recommendation": wants_recommendation,
        "wants_analysis": wants_analysis,
        "wants_project_breakdown": wants_project_breakdown,
        "month_number": month_number,
        "relative_period": relative_period,
        "rolling_days": rolling_days,
        "week_year": week_year,
        "week_number": week_number,
        "test_week": test_week,
        "matrix_levels": matrix_levels,
        "preferred_dimension": preferred_dimension,
        "scope_team": scope_team,
        "columns": set(shared_hints.get("columns") or columns or []),
    }


def decide_query_execution_strategy(
    question: str,
    columns: Optional[List[str]] = None,
    semantic_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    q = str(question or "").strip()
    ql = q.lower()
    cols = list(columns or [])
    hints = extract_query_hints(
        q,
        cols,
        semantic_hints=semantic_hints,
        adapt_with_unified_intent=_should_adapt_with_unified_intent(semantic_hints),
    )

    structured_signals: List[str] = []
    weak_signals: List[str] = []

    structured_hint_keys = {
        "wants_trend": "trend",
        "wants_distribution": "distribution",
        "wants_matrix": "matrix",
        "wants_matrix_severity": "matrix_severity",
        "wants_aida_dist": "aida_distribution",
        "wants_topissue": "topissue",
        "wants_test_coverage": "test_coverage",
        "wants_efficiency": "efficiency",
        "wants_project_breakdown": "project_breakdown",
    }
    for key, label in structured_hint_keys.items():
        if hints.get(key):
            structured_signals.append(label)

    if _is_manual_run_question(q):
        structured_signals.append("manual_runs")
    if _is_history_question(q):
        structured_signals.append("history")
    if re.search(r"\btop\s*\d+\b", ql) or re.search(r"前\s*\d+", q):
        structured_signals.append("top_n")
    if any(term in ql for term in _STRUCTURED_QUERY_TERMS):
        structured_signals.append("structured_keyword")

    if hints.get("wants_recommendation"):
        weak_signals.append("recommendation_hint")
    if any(term in ql for term in _WEAK_QUERY_TERMS):
        weak_signals.append("weak_keyword")

    strong_structured_intent = _has_strong_structured_intent(q)
    if strong_structured_intent:
        structured_signals.append("strong_structured_intent")
        # Recommendation words often appear in BI asks; don't let them demote clearly structured queries.
        weak_signals = [sig for sig in weak_signals if sig != "recommendation_hint"]

    # Definition-like requests are usually weakly structured unless accompanied by strong metrics asks.
    if re.search(r"\bwhat\s+is\b", ql) or ("定义" in q):
        weak_signals.append("definition_style")

    structured_count = len(structured_signals)
    weak_count = len(weak_signals)

    if strong_structured_intent and structured_count > 0:
        strategy = "deterministic_first"
    elif structured_count > 0 and weak_count == 0:
        strategy = "deterministic_first"
    elif weak_count > 0 and structured_count == 0:
        strategy = "constrained_fallback"
    elif structured_count >= (weak_count + 1):
        strategy = "deterministic_first"
    else:
        strategy = "constrained_fallback"

    confidence = 0.45 + (0.1 * structured_count) - (0.12 * weak_count)
    if strategy == "deterministic_first":
        confidence = max(confidence, 0.65)
        if strong_structured_intent:
            confidence = max(confidence, 0.72)
    else:
        confidence = min(confidence, 0.55)
    confidence = max(0.05, min(0.95, confidence))

    return {
        "strategy": strategy,
        "confidence": round(confidence, 3),
        "prefer_deterministic": bool(strategy == "deterministic_first" and confidence >= 0.55),
        "strong_structured_intent": bool(strong_structured_intent),
        "structured_signals": structured_signals,
        "weak_signals": weak_signals,
    }


def build_deterministic_sql(
    question: str,
    table_name: str,
    columns: List[str],
    entity_tokens_override: Optional[List[str]] = None,
    semantic_hints: Optional[Dict[str, Any]] = None,
    row_limit: Optional[int] = 120,
) -> str:
    hints = extract_query_hints(
        question,
        columns,
        semantic_hints=semantic_hints,
        adapt_with_unified_intent=_should_adapt_with_unified_intent(semantic_hints),
    )
    history_question = _is_history_question(question)
    if entity_tokens_override is not None:
        hints["entity_tokens"] = [str(t).strip() for t in (entity_tokens_override or []) if str(t).strip()][:6]

    def _limit_clause(limit_value: Optional[int], default_limit: int = 120) -> str:
        try:
            resolved = int(default_limit if limit_value is None else limit_value)
        except Exception:
            resolved = int(default_limit)
        if resolved <= 0:
            return ""
        return f" LIMIT {resolved}"

    cols = hints["columns"]

    def _esc_like(token: str) -> str:
        return str(token or "").replace("'", "''")

    def _coalesced_text_expr(col_name: str) -> str:
        return f"COALESCE(NULLIF(TRIM(CAST({col_name} AS TEXT)), ''), '未标注')"

    def _count_distinct_text_expr(col_name: str) -> str:
        return f"COUNT(DISTINCT NULLIF(TRIM(CAST({col_name} AS TEXT)), ''))"

    def _is_groupable_dimension(col_name: str) -> bool:
        lowered = str(col_name or "").strip().lower()
        if not lowered:
            return False
        if lowered in {
            "id",
            "defect_id",
            "mr_id",
            "test_id",
            "raw_json",
            "year",
            "spec",
            "creation_time",
            "last_modified",
            "started",
            "finished",
            "fetched_at",
            "version_stamp",
        }:
            return False
        if lowered.endswith("_id"):
            return False
        return True

    select_cols: List[str] = []
    for col in [
        "defect_id",
        "id",
        "name",
        "test_name",
        "test_id",
        "project",
        "tproject",
        "team",
        "ecu",
        "aida_english",
        "top_aida",
        "status_phase",
        "phase",
        "severity_group",
        "tester",
        "run_by",
        "author",
        "detected_by",
        "reporter",
        "found_by",
        "author_name",
        "owner",
        "topissue_display",
        "creation_time",
        "last_modified",
    ]:
        if col in cols:
            select_cols.append(col)

    if not select_cols:
        select_cols = list(columns[:10]) if columns else ["*"]

    where_parts: List[str] = []

    scope_team = str(hints.get("scope_team") or "").strip()
    if scope_team:
        scope_col = ""
        if table_name == "octane_manual_runs":
            scope_col = next((c for c in ["run_team", "team", "project", "tproject"] if c in cols), "")
        elif table_name == "octane_defects":
            scope_col = next((c for c in ["problem_finder_team", "team", "project", "tproject"] if c in cols), "")
        elif table_name == "octane_defect_histories":
            scope_col = next((c for c in ["team"] if c in cols), "")
        else:
            scope_col = next((c for c in ["team", "problem_finder_team", "project", "tproject"] if c in cols), "")

        if scope_col:
            safe_scope_team = _esc_like(scope_team)
            where_parts.append(f"LOWER(TRIM(CAST({scope_col} AS TEXT))) = LOWER('{safe_scope_team}')")

    week_col_for_filter = "test_week" if "test_week" in cols else ""
    if table_name == "octane_manual_runs":
        time_col_candidates = ["finished", "started", "creation_time", "last_modified", "fetched_at", "finished_udf_dt", "finished_udf", "tcreationtime"]
    elif table_name == "octane_defect_histories":
        time_col_candidates = ["fetched_at"]
    else:
        time_col_candidates = ["creation_time", "last_modified", "fetched_at"]
    time_col_for_range = next((c for c in time_col_candidates if c in cols), "")

    relative_period = _normalize_relative_period(hints.get("relative_period"))
    rolling_days = _normalize_rolling_days(hints.get("rolling_days"))
    week_year = _normalize_week_year(hints.get("week_year"))
    week_number = _normalize_week_number(hints.get("week_number"))
    test_week_value = str(hints.get("test_week") or "").strip()

    now_date = datetime.now().date()
    week_filter_year = week_year
    week_filter_number = week_number
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None

    if week_number is not None:
        if week_year is None:
            week_year = int(now_date.isocalendar()[0])
        try:
            start_date = datetime.fromisocalendar(week_year, week_number, 1).date()
            end_date = start_date + timedelta(days=7)
            range_start = datetime.combine(start_date, datetime.min.time())
            range_end = datetime.combine(end_date, datetime.min.time())
            week_filter_year = week_year
            week_filter_number = week_number
            if not test_week_value:
                test_week_value = f"{week_year}-CW{week_number:02d}"
        except Exception:
            range_start = None
            range_end = None

    if range_start is None and range_end is None:
        if relative_period in {"last_week", "this_week"}:
            this_monday = now_date - timedelta(days=now_date.weekday())
            if relative_period == "last_week":
                start_date = this_monday - timedelta(days=7)
                end_date = this_monday
            else:
                start_date = this_monday
                end_date = this_monday + timedelta(days=7)
            range_start = datetime.combine(start_date, datetime.min.time())
            range_end = datetime.combine(end_date, datetime.min.time())
            iso = start_date.isocalendar()
            week_filter_year = int(iso[0])
            week_filter_number = int(iso[1])
            if not test_week_value:
                test_week_value = f"{week_filter_year}-CW{week_filter_number:02d}"
        elif relative_period in {"last_month", "this_month"}:
            month_start = now_date.replace(day=1)
            if relative_period == "last_month":
                end_date = month_start
                prev_month_last_day = month_start - timedelta(days=1)
                start_date = prev_month_last_day.replace(day=1)
            else:
                start_date = month_start
                if month_start.month == 12:
                    end_date = month_start.replace(year=month_start.year + 1, month=1, day=1)
                else:
                    end_date = month_start.replace(month=month_start.month + 1, day=1)
            range_start = datetime.combine(start_date, datetime.min.time())
            range_end = datetime.combine(end_date, datetime.min.time())
        elif rolling_days is not None:
            start_date = now_date - timedelta(days=max(0, rolling_days - 1))
            end_date = now_date + timedelta(days=1)
            range_start = datetime.combine(start_date, datetime.min.time())
            range_end = datetime.combine(end_date, datetime.min.time())

    if range_start is not None and range_end is not None and time_col_for_range:
        time_expr = f"date(CAST({time_col_for_range} AS TEXT))"
        where_parts.append(f"{time_expr} >= '{range_start.date().isoformat()}'")
        where_parts.append(f"{time_expr} < '{range_end.date().isoformat()}'")
    elif week_col_for_filter and week_filter_number is not None:
        normalized_week_year = week_filter_year if week_filter_year is not None else int(now_date.isocalendar()[0])
        normalized_week = week_filter_number
        week_candidates = [
            f"{normalized_week_year}-CW{normalized_week:02d}",
            f"{normalized_week_year}-W{normalized_week:02d}",
            f"{normalized_week_year}CW{normalized_week:02d}",
            f"{normalized_week_year}W{normalized_week:02d}",
            f"CW{normalized_week:02d}",
            f"W{normalized_week:02d}",
        ]
        if test_week_value:
            week_candidates.insert(0, test_week_value)
        dedup_candidates: List[str] = []
        seen_candidates = set()
        for item in week_candidates:
            normalized_item = str(item or "").strip().lower()
            if not normalized_item or normalized_item in seen_candidates:
                continue
            seen_candidates.add(normalized_item)
            dedup_candidates.append(str(item).strip())
        in_values = ", ".join([f"LOWER('{_esc_like(item)}')" for item in dedup_candidates])
        where_parts.append(f"LOWER(TRIM(CAST({week_col_for_filter} AS TEXT))) IN ({in_values})")

    month_number = hints.get("month_number")
    time_col_for_month = next((c for c in ["creation_time", "last_modified", "fetched_at", "finished", "started", "finished_udf_dt", "finished_udf", "tcreationtime"] if c in cols), "")
    if isinstance(month_number, int) and (1 <= month_number <= 12) and time_col_for_month:
        where_parts.append(f"strftime('%m', {time_col_for_month}) = '{month_number:02d}'")

    if hints.get("wants_showstopper"):
        showstopper_fields = [c for c in ["status_phase", "phase", "status", "topissue_display", "severity_group", "name"] if c in cols]
        if showstopper_fields:
            requires_candidate = bool(hints.get("wants_showstopper_candidate"))
            showstopper_conditions: List[str] = []
            for col in showstopper_fields:
                text_expr = f"LOWER(CAST({col} AS TEXT))"
                if requires_candidate:
                    showstopper_conditions.append(
                        f"({text_expr} LIKE '%showstopper%' AND {text_expr} LIKE '%candidate%')"
                    )
                else:
                    showstopper_conditions.append(f"{text_expr} LIKE '%showstopper%'")
            if showstopper_conditions:
                where_parts.append("(" + " OR ".join(showstopper_conditions) + ")")

    if hints["wants_topissue"]:
        if "topissue_display" in cols:
            where_parts.append("topissue_display IS NOT NULL AND CAST(topissue_display AS TEXT) <> ''")
        elif "severity_group" in cols:
            where_parts.append("LOWER(CAST(severity_group AS TEXT)) IN ('critical','high','s1','s2')")

    matrix_levels_for_filter: List[str] = []
    seen_matrix_levels = set()
    for item in (hints.get("matrix_levels") or []):
        normalized_level = _normalize_matrix_level(item)
        if not normalized_level or normalized_level in seen_matrix_levels:
            continue
        seen_matrix_levels.add(normalized_level)
        matrix_levels_for_filter.append(normalized_level)

    if matrix_levels_for_filter:
        matrix_cols = [c for c in ["topissue_display", "risk_matrix", "risk_zone"] if c in cols]
        if matrix_cols:
            matrix_col_conditions: List[str] = []
            for col in matrix_cols:
                normalized_col = f"LOWER(REPLACE(REPLACE(TRIM(CAST({col} AS TEXT)), ' ', ''), '-', ''))"
                matrix_value_conditions: List[str] = []
                for level in matrix_levels_for_filter:
                    safe_level = _esc_like(level)
                    matrix_value_conditions.append(f"{normalized_col} = '{safe_level}'")
                    matrix_value_conditions.append(f"{normalized_col} = 'matrix{safe_level}'")
                    matrix_value_conditions.append(f"{normalized_col} LIKE '%{safe_level}%'")
                matrix_col_conditions.append("(" + " OR ".join(matrix_value_conditions) + ")")
            where_parts.append("(" + " OR ".join(matrix_col_conditions) + ")")

    if hints["entity_tokens"]:
        person_fields = [
            c
            for c in ["tester", "run_by", "author", "detected_by", "reporter", "found_by", "author_name", "owner"]
            if c in cols
        ]
        generic_fields = [c for c in ["project", "tproject", "team", "ecu", "name", "test_name", "test_id"] if c in cols]
        searchable = person_fields if (hints.get("wants_tester") and person_fields) else (person_fields + generic_fields if person_fields else generic_fields)
        for token in hints["entity_tokens"]:
            token_l = str(token).strip().lower()
            if hints.get("wants_test_coverage") and token_l in {
                "passed",
                "failed",
                "blocked",
                "requires",
                "attention",
                "status",
                "run",
                "test",
                "week",
            }:
                continue
            if searchable:
                safe_tok = _esc_like(token)
                like_group = " OR ".join([f"LOWER(CAST({c} AS TEXT)) LIKE LOWER('%{safe_tok}%')" for c in searchable])
                where_parts.append(f"({like_group})")

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    if table_name == "octane_defect_histories" and history_question:
        history_cols = [c for c in ["defect_id", "team", "total_count", "fetched_at"] if c in cols]
        history_select = history_cols or select_cols
        order_sql = ""
        if "total_count" in cols:
            order_sql = " ORDER BY COALESCE(total_count, 0) DESC"
            if "fetched_at" in cols:
                order_sql = " ORDER BY COALESCE(total_count, 0) DESC, fetched_at DESC"
        elif "fetched_at" in cols:
            order_sql = " ORDER BY fetched_at DESC"
        return f'SELECT {", ".join(history_select)} FROM "{table_name}"{where_sql}{order_sql}{_limit_clause(row_limit)}'

    if hints.get("wants_project_breakdown"):
        preferred_dimension = str(hints.get("preferred_dimension") or "").strip()
        project_col = preferred_dimension if preferred_dimension in cols else ""
        if not project_col:
            project_col = next((c for c in ["run_team", "project", "tproject", "team", "aida_english", "top_aida", "ecu"] if c in cols), "")

        if project_col:
            project_expr = _coalesced_text_expr(project_col)

            if table_name == "octane_manual_runs":
                status_col = "run_status" if "run_status" in cols else ("status" if "status" in cols else ("execution_status" if "execution_status" in cols else ""))
                status_text_expr = f"LOWER(CAST({status_col} AS TEXT))" if status_col else ""
                testcase_col = next(
                    (c for c in ["test_id", "test_name", "testcase", "test_case", "case_id", "case_name", "name"] if c in cols),
                    "",
                )
                testcase_count_sql = (
                    f"{_count_distinct_text_expr(testcase_col)} AS testcase_count, " if testcase_col else ""
                )
                if status_col:
                    passed_expr = (
                        "SUM(CASE WHEN ("
                        f"{status_text_expr} IN ('passed','pass') "
                        f"OR {status_text_expr} LIKE 'pass%')"
                        " THEN 1 ELSE 0 END)"
                    )
                    failed_expr = (
                        "SUM(CASE WHEN ("
                        f"{status_text_expr} IN ('failed','failure') "
                        f"OR {status_text_expr} LIKE 'fail%')"
                        " THEN 1 ELSE 0 END)"
                    )
                    blocked_expr = (
                        "SUM(CASE WHEN ("
                        f"{status_text_expr} IN ('blocked','requires attention','requires_attention','attention required') "
                        f"OR {status_text_expr} LIKE '%block%' "
                        f"OR {status_text_expr} LIKE '%require%attention%' "
                        f"OR {status_text_expr} LIKE '%attention required%')"
                        " THEN 1 ELSE 0 END)"
                    )
                    return (
                        f"SELECT {project_expr} AS project, "
                        f"{testcase_count_sql}"
                        "COUNT(*) AS run_count, "
                        f"{passed_expr} AS passed_count, "
                        f"{failed_expr} AS failed_count, "
                        f"{blocked_expr} AS blocked_count, "
                        f"ROUND(100.0 * {passed_expr} / NULLIF(COUNT(*), 0), 2) AS pass_rate "
                        f'FROM "{table_name}" '
                        f"{where_sql} "
                        "GROUP BY 1 "
                        "ORDER BY run_count DESC, pass_rate DESC "
                        "LIMIT 30"
                    )

                return (
                    f"SELECT {project_expr} AS project, "
                    f"{testcase_count_sql}"
                    "COUNT(*) AS run_count "
                    f'FROM "{table_name}" '
                    f"{where_sql} "
                    "GROUP BY 1 "
                    "ORDER BY run_count DESC "
                    "LIMIT 30"
                )

            status_candidates = [c for c in ["status_phase", "phase", "status"] if c in cols]
            status_text_expr = ""
            if status_candidates:
                if len(status_candidates) == 1:
                    status_text_expr = f"LOWER(CAST({status_candidates[0]} AS TEXT))"
                else:
                    status_text_expr = f"LOWER(CAST(COALESCE({', '.join(status_candidates)}) AS TEXT))"

            tester_col = next(
                (c for c in ["detected_by", "tester", "run_by", "author", "reporter", "owner", "found_by", "author_name"] if c in cols),
                "",
            )
            severity_col = next((c for c in ["severity_group", "severity", "priority"] if c in cols), "")

            select_parts: List[str] = [
                f"{project_expr} AS project",
                "COUNT(*) AS defect_count",
            ]
            if tester_col:
                select_parts.append(f"{_count_distinct_text_expr(tester_col)} AS active_tester_count")

            if severity_col:
                severity_text_expr = f"LOWER(CAST({severity_col} AS TEXT))"
                high_expr = (
                    "SUM(CASE WHEN ("
                    f"{severity_text_expr} IN ('high','critical','s1','s2','p1') "
                    f"OR {severity_text_expr} LIKE '%high%' "
                    f"OR {severity_text_expr} LIKE '%critical%' "
                    f"OR {severity_text_expr} LIKE '%p1%')"
                    " THEN 1 ELSE 0 END)"
                )
                select_parts.append(f"{high_expr} AS high_risk_count")

            if status_text_expr:
                draft_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} LIKE '%draft%' "
                    f"OR {status_text_expr} LIKE '%new%' "
                    f"OR {status_text_expr} LIKE '%pre-analysis%' "
                    f"OR {status_text_expr} LIKE '%analysis%')"
                    " THEN 1 ELSE 0 END)"
                )
                progress_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} LIKE '%progress%' "
                    f"OR {status_text_expr} LIKE '%fix%' "
                    f"OR {status_text_expr} LIKE '%processing%')"
                    " THEN 1 ELSE 0 END)"
                )
                closed_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} LIKE '%closed%' "
                    f"OR {status_text_expr} LIKE '%resolved%' "
                    f"OR {status_text_expr} LIKE '%conclud%' "
                    f"OR {status_text_expr} LIKE '%fixed%')"
                    " THEN 1 ELSE 0 END)"
                )
                select_parts.append(f"{draft_expr} AS early_stage_count")
                select_parts.append(f"{progress_expr} AS in_progress_count")
                select_parts.append(f"{closed_expr} AS closed_count")

            return (
                f"SELECT {', '.join(select_parts)} "
                f'FROM "{table_name}" '
                f"{where_sql} "
                "GROUP BY 1 "
                "ORDER BY defect_count DESC "
                "LIMIT 30"
            )

    if hints.get("wants_aida_dist"):
        preferred_dimension = str(hints.get("preferred_dimension") or "").strip()
        aida_col = preferred_dimension if preferred_dimension in cols else ""
        if not aida_col:
            aida_col = next(
                (c for c in ["top_aida", "aida_english", "aida", "product_area", "service", "module"] if c in cols),
                "",
            )
        if aida_col:
            aida_expr = _coalesced_text_expr(aida_col)
            return (
                f"SELECT {aida_expr} AS aida, COUNT(*) AS defect_count "
                f'FROM "{table_name}" '
                f"{where_sql} "
                "GROUP BY 1 "
                "ORDER BY defect_count DESC "
                "LIMIT 20"
            )

    if hints.get("wants_matrix_severity"):
        matrix_col = next((c for c in ["topissue_display", "risk_zone", "risk_matrix"] if c in cols), "")
        severity_col = next((c for c in ["severity_group", "severity", "severity_level", "priority"] if c in cols), "")

        if matrix_col and severity_col:
            matrix_expr = _coalesced_text_expr(matrix_col)
            severity_expr = _coalesced_text_expr(severity_col)
            return (
                f"SELECT {matrix_expr} AS matrix_zone, "
                f"{severity_expr} AS severity, "
                "COUNT(*) AS defect_count "
                f'FROM "{table_name}" '
                f"{where_sql} "
                "GROUP BY 1, 2 "
                "ORDER BY defect_count DESC "
                "LIMIT 60"
            )

        if (not matrix_col) and severity_col and table_name == "octane_defects" and ("defect_id" in cols):
            matrix_expr = "COALESCE(NULLIF(TRIM(CAST(df.topissue_display AS TEXT)), ''), '未标注')"
            severity_expr = _coalesced_text_expr(f"d.{severity_col}")
            return (
                f"SELECT {matrix_expr} AS matrix_zone, "
                f"{severity_expr} AS severity, "
                "COUNT(*) AS defect_count "
                f'FROM "{table_name}" d '
                'LEFT JOIN "defect_features" df ON CAST(df.defect_id AS TEXT) = CAST(d.defect_id AS TEXT) '
                f"{where_sql} "
                "GROUP BY 1, 2 "
                "ORDER BY defect_count DESC "
                "LIMIT 60"
            )

        if severity_col:
            severity_expr = _coalesced_text_expr(severity_col)
            return (
                f"SELECT {severity_expr} AS severity, COUNT(*) AS defect_count "
                f'FROM "{table_name}" '
                f"{where_sql} "
                "GROUP BY 1 "
                "ORDER BY defect_count DESC "
                "LIMIT 20"
            )

        if matrix_col:
            matrix_expr = _coalesced_text_expr(matrix_col)
            return (
                f"SELECT {matrix_expr} AS matrix_zone, COUNT(*) AS defect_count "
                f'FROM "{table_name}" '
                f"{where_sql} "
                "GROUP BY 1 "
                "ORDER BY defect_count DESC "
                "LIMIT 20"
            )

    if hints.get("wants_distribution"):
        preferred_dimension = str(hints.get("preferred_dimension") or "").strip()
        distribution_col = ""
        if preferred_dimension in cols and _is_groupable_dimension(preferred_dimension):
            distribution_col = preferred_dimension
        if not distribution_col:
            distribution_col = next(
                (
                    c
                    for c in [
                        "status_phase",
                        "phase",
                        "status",
                        "severity_group",
                        "severity",
                        "project",
                        "tproject",
                        "team",
                        "run_team",
                        "top_aida",
                        "aida_english",
                        "blocking_reason",
                        "domain",
                        "solution_cluster",
                        "release",
                        "software_version",
                        "testing_tool_type",
                        "test_phase",
                    ]
                    if c in cols
                ),
                "",
            )

        if distribution_col:
            distribution_expr = _coalesced_text_expr(distribution_col)
            return (
                f"SELECT {distribution_expr} AS dimension, COUNT(*) AS record_count "
                f'FROM "{table_name}" '
                f"{where_sql} "
                "GROUP BY 1 "
                "ORDER BY record_count DESC "
                "LIMIT 30"
            )

    if hints.get("wants_analysis"):
        if hints.get("wants_test_coverage"):
            status_col = "run_status" if "run_status" in cols else ("status" if "status" in cols else ("execution_status" if "execution_status" in cols else ""))
            status_text_expr = f"LOWER(CAST({status_col} AS TEXT))" if status_col else ""
            manual_run_person_col = next(
                (c for c in ["run_by", "author", "owner", "tester", "author_name", "detected_by", "reporter", "found_by"] if c in cols),
                "",
            )
            manual_run_case_col = next(
                (c for c in ["test_id", "test_name", "testcase", "test_case", "case_id", "case_name", "name"] if c in cols),
                "",
            )

            if manual_run_person_col and hints.get("wants_tester") and not hints.get("wants_trend"):
                tester_expr = _coalesced_text_expr(manual_run_person_col)
                testcase_count_sql = (
                    f"{_count_distinct_text_expr(manual_run_case_col)} AS testcase_count, " if manual_run_case_col else ""
                )
                if status_col:
                    passed_expr = (
                        "SUM(CASE WHEN ("
                        f"{status_text_expr} IN ('passed','pass') "
                        f"OR {status_text_expr} LIKE 'pass%')"
                        " THEN 1 ELSE 0 END)"
                    )
                    failed_expr = (
                        "SUM(CASE WHEN ("
                        f"{status_text_expr} IN ('failed','failure') "
                        f"OR {status_text_expr} LIKE 'fail%')"
                        " THEN 1 ELSE 0 END)"
                    )
                    blocked_expr = (
                        "SUM(CASE WHEN ("
                        f"{status_text_expr} IN ('blocked','requires attention','requires_attention','attention required') "
                        f"OR {status_text_expr} LIKE '%block%' "
                        f"OR {status_text_expr} LIKE '%require%attention%' "
                        f"OR {status_text_expr} LIKE '%attention required%')"
                        " THEN 1 ELSE 0 END)"
                    )
                    return (
                        f"SELECT {tester_expr} AS tester, "
                        f"{testcase_count_sql}"
                        "COUNT(*) AS run_count, "
                        f"{passed_expr} AS passed_count, "
                        f"{failed_expr} AS failed_count, "
                        f"{blocked_expr} AS blocked_count, "
                        f"ROUND(100.0 * {passed_expr} / NULLIF(COUNT(*), 0), 2) AS pass_rate "
                        f'FROM "{table_name}" '
                        f"{where_sql} "
                        "GROUP BY 1 "
                        "ORDER BY run_count DESC, pass_rate DESC "
                        "LIMIT 30"
                    )
                return (
                    f"SELECT {tester_expr} AS tester, "
                    f"{testcase_count_sql}"
                    "COUNT(*) AS run_count "
                    f'FROM "{table_name}" '
                    f"{where_sql} "
                    "GROUP BY 1 "
                    "ORDER BY run_count DESC "
                    "LIMIT 30"
                )

            week_col = "test_week" if "test_week" in cols else ("creation_time" if "creation_time" in cols else "")
            if week_col and status_col:
                week_bucket_expr = week_col if week_col == "test_week" else f"strftime('%Y-W%W', {week_col})"
                passed_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} IN ('passed','pass') "
                    f"OR {status_text_expr} LIKE 'pass%')"
                    " THEN 1 ELSE 0 END)"
                )
                failed_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} IN ('failed','failure') "
                    f"OR {status_text_expr} LIKE 'fail%')"
                    " THEN 1 ELSE 0 END)"
                )
                blocked_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} IN ('blocked','requires attention','requires_attention','attention required') "
                    f"OR {status_text_expr} LIKE '%block%' "
                    f"OR {status_text_expr} LIKE '%require%attention%' "
                    f"OR {status_text_expr} LIKE '%attention required%')"
                    " THEN 1 ELSE 0 END)"
                )
                return (
                    f"SELECT {week_bucket_expr} AS week, "
                    "COUNT(*) AS run_count, "
                    f"{passed_expr} AS passed_count, "
                    f"{failed_expr} AS failed_count, "
                    f"{blocked_expr} AS blocked_count, "
                    f"ROUND(100.0 * {passed_expr} / NULLIF(COUNT(*), 0), 2) AS pass_rate "
                    f'FROM "{table_name}" '
                    f"{where_sql} "
                    f"GROUP BY {week_bucket_expr} "
                    "ORDER BY week DESC "
                    "LIMIT 20"
                )

        time_col = "creation_time" if "creation_time" in cols else ("last_modified" if "last_modified" in cols else "")
        status_candidates = [c for c in ["status", "phase", "status_phase"] if c in cols]
        status_col = status_candidates[0] if status_candidates else ""
        status_text_expr = ""
        if status_candidates:
            if len(status_candidates) == 1:
                status_text_expr = f"LOWER(CAST({status_candidates[0]} AS TEXT))"
            else:
                status_text_expr = f"LOWER(CAST(COALESCE({', '.join(status_candidates)}) AS TEXT))"

        if time_col:
            closed_expr = "0"
            if status_text_expr:
                closed_expr = (
                    "SUM(CASE WHEN ("
                    f"{status_text_expr} IN ('closed','fixed','resolved','done','completed','concluded','concluded without action') "
                    f"OR {status_text_expr} LIKE '%conclud%' "
                    f"OR {status_text_expr} LIKE '%resolv%' "
                    f"OR {status_text_expr} LIKE '%clos%' "
                    f"OR {status_text_expr} LIKE '%fix%' "
                    f"OR {status_text_expr} LIKE '%complet%' "
                    f"OR {status_text_expr} LIKE '%已关闭%' "
                    f"OR {status_text_expr} LIKE '%已解决%' "
                    f"OR {status_text_expr} LIKE '%已修复%' "
                    f"OR {status_text_expr} LIKE '%结案%')"
                    " THEN 1 ELSE 0 END)"
                )
            where_with_time = where_parts + [f"{time_col} IS NOT NULL"]
            where_sql_analysis = " WHERE " + " AND ".join(where_with_time)
            return (
                f"SELECT strftime('%Y-W%W', {time_col}) AS week, "
                "COUNT(*) AS defect_count, "
                f"{closed_expr} AS closed_count, "
                f"ROUND(100.0 * {closed_expr} / NULLIF(COUNT(*), 0), 2) AS close_rate "
                f'FROM "{table_name}" '
                f"{where_sql_analysis} "
                "GROUP BY week "
                "ORDER BY week DESC "
                "LIMIT 16"
            )

        if status_col:
            return (
                f"SELECT {status_col} AS status, COUNT(*) AS defect_count "
                f'FROM "{table_name}" '
                f"{where_sql} "
                f"GROUP BY {status_col} "
                "ORDER BY defect_count DESC "
                "LIMIT 12"
            )

    order_col = "creation_time" if "creation_time" in cols else ("last_modified" if "last_modified" in cols else None)
    order_sql = f" ORDER BY {order_col} DESC" if order_col else ""
    return f'SELECT {", ".join(select_cols)} FROM "{table_name}"{where_sql}{order_sql}{_limit_clause(row_limit)}'
