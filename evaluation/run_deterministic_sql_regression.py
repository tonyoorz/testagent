import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from semantic_catalog.runtime import build_semantic_context
from agent.core.deterministic_sql_service import (
    build_deterministic_sql as shared_build_deterministic_sql,
    guess_target_table as shared_guess_target_table,
)
from agent.core.sql_runtime_service import execute_sql_rows

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
    "所有测试人员测试用例执行情况",
    "please summarize test cases execution",
    "请比较Passed与Failed周变化",
    "请看requires attention趋势",
    "状态变更记录",
    "请看AIDA维度缺陷状态分布",
    "请给出当前数据库里最需要优先处理的问题趋势",
]


def _open_ro(db_path: str) -> sqlite3.Connection:
    uri = f"file:{Path(db_path).resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


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
            table = shared_guess_target_table(q)
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
                sql = shared_build_deterministic_sql(q, table, cols)
                row["sql"] = sql

                sem = build_semantic_context(question=q, db_path=DB_PATH, max_each=6)
                row["rule_ids"] = _extract_rule_ids(sem)

                run_out = execute_sql_rows(
                    sql_text=sql,
                    db_path=DB_PATH,
                    table_name=table,
                    row_limit=500,
                    tool_executor=None,
                )
                fetched = list(run_out.get("rows") or [])
                row["row_count"] = len(fetched)
                row["success"] = bool(run_out.get("success"))
                if (not row["success"]) and run_out.get("error"):
                    row["error"] = str(run_out.get("error"))
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
