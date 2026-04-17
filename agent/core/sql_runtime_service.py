import re
import sqlite3
from typing import Any, Dict, List, Optional


_WRITE_SQL_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|attach|detach|pragma\s+write)\b",
    flags=re.IGNORECASE,
)


def _fallback_sql(table_name: str, default_limit: int = 50) -> str:
    safe_table = str(table_name or "").strip() or "octane_defects"
    return f'SELECT * FROM "{safe_table}" LIMIT {int(max(1, default_limit))}'


def sanitize_select_sql(sql_text: str, table_name: str, default_limit: int = 50) -> str:
    sql_clean = str(sql_text or "").strip().rstrip(";")
    if not sql_clean:
        return _fallback_sql(table_name, default_limit)

    if not re.match(r"^\s*(select|with)\b", sql_clean, flags=re.IGNORECASE):
        return _fallback_sql(table_name, default_limit)

    if _WRITE_SQL_RE.search(sql_clean):
        return _fallback_sql(table_name, default_limit)

    return sql_clean


def _unwrap_sql_for_count(sql_text: str, table_name: str) -> str:
    sql_clean = str(sql_text or "").strip().rstrip(";")
    if not sql_clean:
        return _fallback_sql(table_name)

    # run_sqlite_query 常见返回形态: SELECT * FROM (<inner>) AS _q LIMIT N
    wrapped = re.match(
        r"^\s*SELECT\s+\*\s+FROM\s+\((.*)\)\s+AS\s+_q\s+LIMIT\s+\d+\s*$",
        sql_clean,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if wrapped:
        sql_clean = str(wrapped.group(1) or "").strip()

    sql_clean = re.sub(r"\s+LIMIT\s+\d+\s*$", "", sql_clean, flags=re.IGNORECASE)
    if not re.match(r"^\s*(select|with)\b", sql_clean, flags=re.IGNORECASE):
        return _fallback_sql(table_name)
    return sql_clean


def _normalize_row_limit(row_limit: int) -> Optional[int]:
    try:
        value = int(row_limit)
    except Exception:
        value = 1
    if value <= 0:
        return None
    return max(1, value)


def _normalize_tool_rows(items: Any, row_limit: Optional[int]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return rows
    iter_rows = items if row_limit is None else items[:row_limit]
    for row in iter_rows:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def build_evidence_bundle(
    *,
    sql_used: str,
    rows: Optional[List[Dict[str, Any]]] = None,
    sample_count: Optional[int] = None,
    total_count: Optional[int] = None,
    key_fields: Optional[List[str]] = None,
    rule_ids: Optional[List[str]] = None,
    evidence_gap: Optional[List[str]] = None,
) -> Dict[str, Any]:
    normalized_rows: List[Dict[str, Any]] = []
    for row in (rows or []):
        if isinstance(row, dict):
            normalized_rows.append(row)

    if isinstance(sample_count, int) and sample_count >= 0:
        safe_sample_count = int(sample_count)
    else:
        safe_sample_count = len(normalized_rows)

    safe_total_count: Optional[int] = None
    if isinstance(total_count, int):
        safe_total_count = max(0, int(total_count))

    inferred_fields: List[str] = []
    if isinstance(key_fields, list) and key_fields:
        inferred_fields = [str(field) for field in key_fields if str(field).strip()]
    elif normalized_rows:
        inferred_fields = [str(field) for field in list(normalized_rows[0].keys())]

    normalized_rule_ids: List[str] = []
    for item in (rule_ids or []):
        text = str(item or "").strip()
        if text:
            normalized_rule_ids.append(text)

    normalized_gaps: List[str] = []
    for gap in (evidence_gap or []):
        text = str(gap or "").strip()
        if text:
            normalized_gaps.append(text)

    return {
        "sql_used": str(sql_used or "").strip(),
        "sample_count": safe_sample_count,
        "total_count": safe_total_count,
        "key_fields": inferred_fields,
        "rule_ids": normalized_rule_ids,
        "evidence_gap": normalized_gaps,
    }


def execute_query_with_fix(
    *,
    question: str,
    table_name: str,
    row_limit: int,
    tool_executor: Optional[Any],
    semantic_hints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_limit = _normalize_row_limit(row_limit)
    safe_limit = normalized_limit if normalized_limit is not None else 200
    safe_table = str(table_name or "").strip()
    safe_question = str(question or "").strip()
    safe_semantic_hints = semantic_hints if isinstance(semantic_hints, dict) else {}

    if tool_executor is None:
        return {
            "success": False,
            "rows": [],
            "sql": "",
            "business_explanation": {},
            "source": "query_sqlite_with_fix",
            "error": "tool_executor_unavailable",
        }

    try:
        tool_out = tool_executor.execute_tool(
            "query_sqlite_with_fix",
            None,
            question=safe_question,
            limit=safe_limit,
            table=safe_table,
            semantic_hints=safe_semantic_hints,
        )
    except Exception as exc:
        return {
            "success": False,
            "rows": [],
            "sql": "",
            "business_explanation": {},
            "source": "query_sqlite_with_fix",
            "error": str(exc),
        }

    if not isinstance(tool_out, dict):
        return {
            "success": False,
            "rows": [],
            "sql": "",
            "business_explanation": {},
            "source": "query_sqlite_with_fix",
            "error": "query_sqlite_with_fix_invalid_payload",
        }

    result = tool_out.get("result") or {}
    sql_raw = str(result.get("generated_sql") or result.get("sql") or "").strip()
    sql_used = sanitize_select_sql(sql_text=sql_raw, table_name=safe_table or "octane_defects", default_limit=50) if sql_raw else ""
    rows = _normalize_tool_rows(result.get("rows"), row_limit=normalized_limit)
    explanation = result.get("business_explanation") if isinstance(result.get("business_explanation"), dict) else {}

    if tool_out.get("success") is True:
        return {
            "success": True,
            "rows": rows,
            "sql": sql_used,
            "business_explanation": explanation,
            "source": "query_sqlite_with_fix",
            "error": "",
        }

    return {
        "success": False,
        "rows": [],
        "sql": sql_used,
        "business_explanation": {},
        "source": "query_sqlite_with_fix",
        "error": str(tool_out.get("error") or "query_sqlite_with_fix_failed"),
    }


def execute_sql_rows(
    *,
    sql_text: str,
    db_path: str,
    table_name: str,
    row_limit: int,
    tool_executor: Optional[Any],
) -> Dict[str, Any]:
    normalized_limit = _normalize_row_limit(row_limit)
    safe_limit = normalized_limit if normalized_limit is not None else 0
    sql_clean = sanitize_select_sql(sql_text=sql_text, table_name=table_name, default_limit=50)

    tool_error = ""
    if tool_executor is not None and normalized_limit is not None:
        try:
            tool_out = tool_executor.execute_tool("run_sqlite_query", None, sql=sql_clean, limit=safe_limit)
            if isinstance(tool_out, dict) and tool_out.get("success") is True:
                result = tool_out.get("result") or {}
                rows = _normalize_tool_rows(result.get("rows"), row_limit=normalized_limit)
                sql_used = str(result.get("sql") or sql_clean)
                return {
                    "success": True,
                    "rows": rows,
                    "sql": sql_used,
                    "source": "tool",
                    "error": "",
                }
            tool_error = str((tool_out or {}).get("error") or "run_sqlite_query_failed")
        except Exception as exc:
            tool_error = str(exc)

    rows_local: List[Dict[str, Any]] = []
    sql_used = sql_clean
    local_error = ""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("PRAGMA query_only = ON")
        except Exception:
            pass

        try:
            cur.execute(sql_clean)
            if normalized_limit is None:
                fetched = cur.fetchall()
            else:
                fetched = cur.fetchmany(max(200, safe_limit))
        except Exception:
            sql_used = _fallback_sql(table_name, default_limit=50)
            cur.execute(sql_used)
            if normalized_limit is None:
                fetched = cur.fetchall()
            else:
                fetched = cur.fetchmany(max(200, safe_limit))

        row_iter = (fetched or []) if normalized_limit is None else (fetched or [])[:safe_limit]
        for row in row_iter:
            try:
                item = dict(row) if row is not None else {}
            except Exception:
                item = {}
            rows_local.append({k: item.get(k) for k in list(item.keys())[:18]})

        conn.close()
        return {
            "success": True,
            "rows": rows_local,
            "sql": sql_used,
            "source": "local",
            "error": tool_error,
        }
    except Exception as exc:
        local_error = str(exc)

    merged_error = "; ".join([v for v in [tool_error, local_error] if v])
    return {
        "success": False,
        "rows": [],
        "sql": sql_used,
        "source": "none",
        "error": merged_error or "sql_execution_failed",
    }


def compute_total_count(
    *,
    db_path: str,
    table_name: str,
    sql_text: str,
    tool_executor: Optional[Any],
) -> Optional[int]:
    base_sql = _unwrap_sql_for_count(sql_text=sql_text, table_name=table_name)
    count_sql = f"SELECT COUNT(*) AS total_count FROM ({base_sql}) AS _cnt"

    if tool_executor is not None:
        try:
            out = tool_executor.execute_tool("run_sqlite_query", None, sql=count_sql, limit=1)
            if isinstance(out, dict) and out.get("success") is True:
                result = out.get("result") or {}
                rows = result.get("rows") or []
                if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                    value = rows[0].get("total_count")
                    if value is not None:
                        return int(value)
        except Exception:
            pass

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cur = conn.cursor()
        try:
            cur.execute("PRAGMA query_only = ON")
        except Exception:
            pass
        cur.execute(count_sql)
        one = cur.fetchone()
        conn.close()
        if one is not None:
            return int(one[0])
    except Exception:
        return None

    return None
