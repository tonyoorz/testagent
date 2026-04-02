import re
from typing import Any, Dict, List, Optional

from semantic_catalog.deterministic_query_hints import build_deterministic_query_hints


_EN_STOP_WORDS = {
    "aida", "ticket", "topissue", "issue", "defect", "summary", "agent", "sqlite",
    "tester", "reporter", "owner", "team", "project", "status", "phase", "query",
    "trend", "efficiency", "analysis", "analyze", "recommend", "recommendation", "improve", "optimization",
    "showstopper", "candidate",
    "passed", "failed", "blocked", "requires", "attention", "coverage", "frequency", "week", "monthly",
    "please", "kindly", "thanks", "thank", "thx", "assistant", "copilot", "chatgpt", "sisi",
    "matrix", "distribution", "severity", "priority",
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


def guess_target_table(question_text: str) -> str:
    q = (question_text or "").lower()
    if _is_manual_run_question(q):
        return "octane_manual_runs"
    if _is_history_question(q):
        return "octane_defect_histories"
    return "octane_defects"


def extract_query_hints(question: str, columns: List[str], semantic_hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    q = str(question or "")
    ql = q.lower()

    shared_hints = build_deterministic_query_hints(q, columns)
    dedup_tokens: List[str] = [str(t).strip() for t in (shared_hints.get("entity_tokens") or []) if str(t).strip()]
    seen = {str(t).strip().lower() for t in dedup_tokens if str(t).strip()}

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

    semantic_hints = semantic_hints if isinstance(semantic_hints, dict) else {}
    if semantic_hints:
        semantic_tokens = semantic_hints.get("entity_tokens")
        if isinstance(semantic_tokens, list):
            for token in semantic_tokens:
                text = str(token or "").strip()
                if not text:
                    continue
                text_l = text.lower()
                if text_l in seen:
                    continue
                seen.add(text_l)
                dedup_tokens.append(text)

        wants_feature_breakdown = wants_feature_breakdown or bool(semantic_hints.get("wants_feature_breakdown"))
        wants_aida_dist = wants_aida_dist or bool(semantic_hints.get("wants_aida_dist"))
        wants_showstopper = wants_showstopper or bool(semantic_hints.get("wants_showstopper"))

        semantic_month = semantic_hints.get("month_number")
        if month_number is None and isinstance(semantic_month, int) and 1 <= semantic_month <= 12:
            month_number = semantic_month

    wants_showstopper_candidate = ("candidate" in ql) or bool(semantic_hints.get("wants_showstopper_candidate"))
    preferred_dimension = str(semantic_hints.get("preferred_dimension") or "").strip()

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
        "month_number": month_number,
        "preferred_dimension": preferred_dimension,
        "columns": set(shared_hints.get("columns") or columns or []),
    }


def build_deterministic_sql(
    question: str,
    table_name: str,
    columns: List[str],
    entity_tokens_override: Optional[List[str]] = None,
    semantic_hints: Optional[Dict[str, Any]] = None,
) -> str:
    hints = extract_query_hints(question, columns, semantic_hints=semantic_hints)
    history_question = _is_history_question(question)
    if entity_tokens_override is not None:
        hints["entity_tokens"] = [str(t).strip() for t in (entity_tokens_override or []) if str(t).strip()][:6]

    cols = hints["columns"]

    def _esc_like(token: str) -> str:
        return str(token or "").replace("'", "''")

    def _coalesced_text_expr(col_name: str) -> str:
        return f"COALESCE(NULLIF(TRIM(CAST({col_name} AS TEXT)), ''), '未标注')"

    def _count_distinct_text_expr(col_name: str) -> str:
        return f"COUNT(DISTINCT NULLIF(TRIM(CAST({col_name} AS TEXT)), ''))"

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

    month_number = hints.get("month_number")
    time_col_for_month = next((c for c in ["creation_time", "last_modified", "fetched_at"] if c in cols), "")
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
        return f'SELECT {", ".join(history_select)} FROM "{table_name}"{where_sql}{order_sql} LIMIT 120'

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
    return f'SELECT {", ".join(select_cols)} FROM "{table_name}"{where_sql}{order_sql} LIMIT 120'
