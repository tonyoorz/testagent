"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
import sqlite3

logger = logging.getLogger(__name__)


class SQLiteDBProfileTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        super().__init__(
            name="get_db_profile",
            description="获取SQLite表的轻量画像（行数、字段、空值率、高频值样本）",
            parameters={
                "table": {"type": "string", "description": "可选：指定表名", "default": ""},
                "top_n": {"type": "integer", "description": "每列高频值返回数量", "default": 5},
                "sample_columns": {"type": "integer", "description": "最多画像列数", "default": 20},
            },
        )
        self._db_path = db_path

    @staticmethod
    def _q_ident(name: str) -> str:
        return '"' + str(name).replace('"', '""') + '"'

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        db_path = self._db_path
        if not db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}

        table = str(kwargs.get("table") or "").strip()
        top_n = int(kwargs.get("top_n") or 5)
        top_n = max(1, min(20, top_n))
        sample_columns = int(kwargs.get("sample_columns") or 20)
        sample_columns = max(1, min(100, sample_columns))

        try:
            conn = _open_sqlite_readonly(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            all_tables = [r["name"] for r in cur.fetchall()]
            if not all_tables:
                conn.close()
                return {"success": True, "tool": self.name, "result": {"db_path": db_path, "tables": {}}}

            selected_tables = [table] if table else all_tables[:8]
            selected_tables = [t for t in selected_tables if t in all_tables]
            if table and not selected_tables:
                conn.close()
                return {"success": False, "tool": self.name, "error": f"表不存在: {table}"}

            prof: Dict[str, Any] = {"db_path": db_path, "tables": {}}
            for t in selected_tables:
                t_ident = self._q_ident(t)
                row_count = 0
                try:
                    cur.execute(f"SELECT COUNT(1) AS c FROM {t_ident}")
                    rr = cur.fetchone()
                    row_count = int(rr["c"]) if rr else 0
                except Exception:
                    row_count = 0

                cur.execute(f"PRAGMA table_info({t_ident})")
                cols = [dict(r) for r in cur.fetchall()]
                col_profiles = []
                for c in cols[:sample_columns]:
                    cname = str(c.get("name") or "")
                    if not cname:
                        continue
                    c_ident = self._q_ident(cname)
                    null_ratio = 0.0
                    top_values = []
                    try:
                        if row_count > 0:
                            cur.execute(
                                f"SELECT AVG(CASE WHEN {c_ident} IS NULL THEN 1.0 ELSE 0.0 END) AS r FROM {t_ident}"
                            )
                            rr = cur.fetchone()
                            null_ratio = round(float(rr["r"] or 0.0), 4) if rr else 0.0
                        cur.execute(
                            f"SELECT CAST({c_ident} AS TEXT) AS v, COUNT(1) AS n FROM {t_ident} "
                            f"WHERE {c_ident} IS NOT NULL GROUP BY CAST({c_ident} AS TEXT) ORDER BY n DESC LIMIT {top_n}"
                        )
                        top_values = [{"value": r["v"], "count": int(r["n"])} for r in cur.fetchall()]
                    except Exception:
                        pass

                    col_profiles.append(
                        {
                            "name": cname,
                            "type": str(c.get("type") or ""),
                            "null_ratio": null_ratio,
                            "top_values": top_values,
                        }
                    )

                prof["tables"][t] = {
                    "row_count": row_count,
                    "columns": col_profiles,
                }

            conn.close()
            return {"success": True, "tool": self.name, "result": prof}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


def _is_safe_readonly_sql(sql: str) -> bool:
    s = (sql or "").strip().lstrip("(").strip()
    if not s:
        return False
    head = s.split(None, 1)[0].lower()
    if head not in {"select", "with"}:
        return False
    if ";" in s:
        first, _, rest = s.partition(";")
        if rest.strip():
            return False
        s = first.strip()
    banned = ["insert", "update", "delete", "drop", "alter", "create", "attach", "detach", "pragma"]
    low = s.lower()
    if any(re.search(rf"\\b{b}\\b", low) for b in banned):
        return False
    return True


def _open_sqlite_readonly(db_path: str) -> sqlite3.Connection:
    abs_path = os.path.abspath(str(db_path or ""))
    # Use URI mode to enforce read-only access at the SQLite connection layer.
    normalized_path = abs_path.replace("\\", "/")
    uri = f"file:{quote(normalized_path, safe='/:')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
    except Exception:
        pass
    return conn


def _ensure_limit(sql: str, limit: int) -> str:
    s = (sql or "").strip()
    if ";" in s:
        s = s.split(";", 1)[0].strip()
    if re.search(r"\\blimit\\b", s, flags=re.IGNORECASE):
        return s
    return f"SELECT * FROM ({s}) AS _q LIMIT {int(limit)}"
