import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from semantic_catalog.runtime import build_semantic_context

DB_PATH = "database/local_data_rebuilt.db"
OUT_JSON = "evaluation/deterministic_sql_regression_report.json"
OUT_MD = "evaluation/deterministic_sql_regression_report.md"

QUESTIONS = [
    "请基于缺陷趋势和测试效率给出改进建议",
    "请看TopIssue风险和关闭率趋势",
    "请分析DTSV团队高风险缺陷趋势",
    "请分析缺陷矩阵分布和严重性问题",
    "请看IDCEVO项目近16周缺陷关闭率",
    "请统计本月各状态缺陷分布",
    "请看提票人Wei Yang相关缺陷趋势",
    "请看G70相关缺陷走势并给建议",
    "请看NA6高风险缺陷周趋势",
    "请分析测试覆盖率和高风险AIDA并给改进建议",
    "请看DTSV团队测试通过率趋势并给建议",
    "请看执行状态中Blocked和Failed周趋势",
    "请比较Passed与Failed周变化",
    "请看requires attention趋势",
    "请看AIDA维度缺陷状态分布",
    "请给出当前数据库里最需要优先处理的问题趋势",
]


def _open_ro(db_path: str) -> sqlite3.Connection:
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _guess_target_table(question_text: str) -> str:
    q = (question_text or "").lower()
    if any(k in q for k in [
        "manual run", "testrun", "测试执行", "测试运行", "覆盖率", "通过率", "执行状态",
        "run status", "execution status", "blocked", "failed", "passed", "requires attention"
    ]):
        return "octane_manual_runs"
    if any(k in q for k in ["history", "历史", "阶段变化", "phase"]):
        return "octane_defect_histories"
    return "octane_defects"


def _extract_query_hints(question: str, columns: List[str]) -> Dict[str, Any]:
    q = str(question or "")
    ql = q.lower()
    en_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", q)
    zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,8}", q)

    stop_words = {
        "aida", "ticket", "topissue", "issue", "defect", "summary", "agent", "sqlite",
        "tester", "reporter", "owner", "team", "project", "status", "phase", "query",
        "trend", "efficiency", "analysis", "analyze", "recommend", "recommendation", "improve", "optimization",
        "passed", "failed", "blocked", "requires", "attention", "coverage", "frequency", "week", "monthly",
        "please", "kindly", "thanks", "thank", "thx", "assistant", "copilot", "chatgpt", "sisi",
        "matrix", "distribution", "severity", "priority"
    }

    entity_tokens: List[str] = []
    for t in en_tokens:
        tl = t.lower()
        if tl in stop_words or len(tl) <= 1:
            continue
        entity_tokens.append(t)
    for t in zh_tokens:
        if t.startswith("请"):
            continue
        if t in {"您好", "你好", "请问", "麻烦", "谢谢", "辛苦"}:
            continue
        if any(k in t for k in [
            "提票", "情况", "如何", "分析", "查询", "统计", "数据", "测试", "缺陷", "团队", "项目",
            "建议", "改进", "优化", "趋势", "效率", "复盘", "对策", "提升", "比较", "执行状态",
            "通过率", "覆盖率", "关闭率", "周变化", "周趋势", "高风险", "数据库", "优先处理", "状态分布",
            "分布", "矩阵", "维度", "严重", "严重性", "等级", "占比", "比例", "问题"
        ]):
            continue
        entity_tokens.append(t)

    dedup_tokens = []
    seen = set()
    for t in entity_tokens:
        tl = str(t).strip().lower()
        if not tl or tl in seen:
            continue
        seen.add(tl)
        dedup_tokens.append(str(t).strip())

    wants_distribution = any(k in ql for k in ["分布", "distribution", "占比", "比例"])
    wants_matrix = any(k in ql for k in ["矩阵", "matrix"])
    wants_severity = any(k in ql for k in [
        "严重性", "severity", "严重等级", "等级", "priority", "critical", "major", "minor", "s1", "s2", "s3"
    ])
    wants_matrix_severity = bool(wants_matrix or (wants_distribution and wants_severity))
    wants_aida_dist = ("aida" in ql) or (wants_distribution and any(k in ql for k in ["领域", "模块", "domain"]))
    wants_topissue = any(k in ql for k in [
        "topissue", "top issue", "高风险", "high risk", "风险", "risk matrix", "风险矩阵", "1a", "1b", "1c", "1d", "1e"
    ])
    wants_tester = any(k in ql for k in ["提票", "提单", "报缺陷", "提交人", "报告人", "发现人", "测试员", "测试人员", "tester", "reporter", "found by", "found_by", "detected by", "detected_by"])
    wants_trend = any(k in ql for k in ["趋势", "trend", "走势", "变化", "周", "月"])
    wants_efficiency = any(k in ql for k in ["效率", "efficiency", "修复", "关闭率", "通过率", "处理时长", "时效"])
    wants_test_coverage = any(k in ql for k in [
        "测试覆盖", "覆盖率", "pass rate", "test frequency", "通过率", "执行状态", "run status", "blocked", "requires attention"
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
        "wants_tester": wants_tester,
        "wants_trend": wants_trend,
        "wants_efficiency": wants_efficiency,
        "wants_test_coverage": wants_test_coverage,
        "wants_recommendation": wants_recommendation,
        "wants_analysis": wants_analysis,
        "columns": set(columns or []),
    }


def _build_deterministic_sql(
    question: str,
    table_name: str,
    columns: List[str],
    entity_tokens_override: Optional[List[str]] = None,
) -> str:
    hints = _extract_query_hints(question, columns)
    if entity_tokens_override is not None:
        hints["entity_tokens"] = [
            str(t).strip()
            for t in (entity_tokens_override or [])
            if str(t).strip()
        ][:6]
    cols = hints["columns"]

    def _esc_like(token: str) -> str:
        return str(token or "").replace("'", "''")

    def _coalesced_text_expr(col_name: str) -> str:
        return f"COALESCE(NULLIF(TRIM(CAST({col_name} AS TEXT)), ''), '未标注')"

    select_cols = []
    for c in [
        "defect_id", "id", "name", "project", "tproject", "team", "ecu",
        "aida_english", "top_aida", "status_phase", "phase", "severity_group",
        "tester", "detected_by", "reporter", "found_by", "author_name", "owner",
        "topissue_display", "creation_time", "last_modified"
    ]:
        if c in cols:
            select_cols.append(c)

    if not select_cols:
        select_cols = list(columns[:10]) if columns else ["*"]

    where_parts = []

    if hints["wants_topissue"]:
        if "topissue_display" in cols:
            where_parts.append("topissue_display IS NOT NULL AND CAST(topissue_display AS TEXT) <> ''")
        elif "severity_group" in cols:
            where_parts.append("LOWER(CAST(severity_group AS TEXT)) IN ('critical','high','s1','s2')")

    if hints["entity_tokens"]:
        person_fields = [c for c in ["tester", "detected_by", "reporter", "found_by", "author_name", "owner"] if c in cols]
        generic_fields = [c for c in ["project", "tproject", "team", "ecu", "name"] if c in cols]
        searchable = person_fields if (hints.get("wants_tester") and person_fields) else (person_fields + generic_fields if person_fields else generic_fields)
        for tok in hints["entity_tokens"]:
            tok_l = str(tok).strip().lower()
            if hints.get("wants_test_coverage") and tok_l in {
                "passed", "failed", "blocked", "requires", "attention", "status", "run", "test", "week"
            }:
                continue
            if searchable:
                safe_tok = _esc_like(tok)
                like_group = " OR ".join([f"LOWER(CAST({c} AS TEXT)) LIKE LOWER('%{safe_tok}%')" for c in searchable])
                where_parts.append(f"({like_group})")

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    if hints.get("wants_aida_dist"):
        aida_col = "aida_english" if "aida_english" in cols else ("top_aida" if "top_aida" in cols else "")
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

        # 主缺陷表通常不含矩阵列，必要时联 defect_features 取 topissue_display。
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
            week_col = "test_week" if "test_week" in cols else ("creation_time" if "creation_time" in cols else "")
            status_col = "run_status" if "run_status" in cols else ("status" if "status" in cols else ("execution_status" if "execution_status" in cols else ""))
            if week_col and status_col:
                week_bucket_expr = week_col if week_col == "test_week" else f"strftime('%Y-W%W', {week_col})"
                status_text_expr = f"LOWER(CAST({status_col} AS TEXT))"
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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [str(r[1]) for r in rows]


def _extract_rule_ids(semantic_context: str) -> List[str]:
    out = []
    for ln in (semantic_context or "").splitlines():
        s = ln.strip()
        if s.startswith("- br_"):
            out.append(s)
    return out


def run_regression() -> Dict[str, Any]:
    conn = _open_ro(DB_PATH)
    results: List[Dict[str, Any]] = []
    try:
        for idx, q in enumerate(QUESTIONS, start=1):
            table = _guess_target_table(q)
            row: Dict[str, Any] = {
                "id": idx,
                "question": q,
                "table": table,
                "success": False,
                "sql": "",
                "row_count": 0,
                "error": "",
                "rule_ids": [],
            }
            try:
                cols = _table_columns(conn, table)
                sql = _build_deterministic_sql(q, table, cols)
                row["sql"] = sql

                sem = build_semantic_context(question=q, db_path=DB_PATH, max_each=6)
                row["rule_ids"] = _extract_rule_ids(sem)

                cur = conn.execute(sql)
                fetched = cur.fetchall()
                row["row_count"] = len(fetched)
                row["success"] = True
                if fetched:
                    first = dict(fetched[0])
                    row["sample_columns"] = list(first.keys())[:8]
                    row["sample_row"] = {k: first[k] for k in list(first.keys())[:5]}
            except Exception as e:
                row["error"] = str(e)
            results.append(row)
    finally:
        conn.close()

    success_n = sum(1 for r in results if r.get("success"))
    nonempty_n = sum(1 for r in results if r.get("success") and int(r.get("row_count") or 0) > 0)
    return {
        "generated_at": datetime.now().isoformat(),
        "db_path": DB_PATH,
        "total": len(results),
        "success": success_n,
        "nonempty": nonempty_n,
        "results": results,
    }


def write_reports(payload: Dict[str, Any]) -> None:
    Path("evaluation").mkdir(parents=True, exist_ok=True)
    Path(OUT_JSON).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Deterministic SQL Regression Report\n\n")
    lines.append(f"- generated_at: {payload.get('generated_at')}\n")
    lines.append(f"- db_path: {payload.get('db_path')}\n")
    lines.append(f"- total: {payload.get('total')}\n")
    lines.append(f"- success: {payload.get('success')}\n")
    lines.append(f"- nonempty: {payload.get('nonempty')}\n\n")

    for r in payload.get("results") or []:
        lines.append(f"## Case {r.get('id')}\n\n")
        lines.append(f"- Question: {r.get('question')}\n")
        lines.append(f"- Table: {r.get('table')}\n")
        lines.append(f"- Success: {r.get('success')}\n")
        lines.append(f"- RowCount: {r.get('row_count')}\n")
        if r.get("rule_ids"):
            lines.append(f"- Rules: {len(r.get('rule_ids') or [])}\n")
            for rid in (r.get("rule_ids") or [])[:12]:
                lines.append(f"  - {rid}\n")
        if r.get("error"):
            lines.append(f"- Error: {r.get('error')}\n")
        lines.append("\nSQL:\n\n")
        lines.append("```sql\n")
        lines.append(str(r.get("sql") or "") + "\n")
        lines.append("```\n\n")

    Path(OUT_MD).write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    report = run_regression()
    write_reports(report)
    print(OUT_JSON)
    print(OUT_MD)
