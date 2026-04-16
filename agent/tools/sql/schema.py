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


class SQLiteSchemaTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        super().__init__(
            name="get_sqlite_schema",
            description="获取SQLite数据库表与字段信息（只读）",
            parameters={
                "table": {"type": "string", "description": "可选：指定表名，仅返回该表", "default": ""},
            },
        )
        self._db_path = db_path

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        db_path = self._db_path
        if not db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}
        table = str(kwargs.get("table") or "").strip()
        try:
            conn = _open_sqlite_readonly(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            tables = []
            if table:
                tables = [table]
            else:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                tables = [r["name"] for r in cur.fetchall()]

            schema: Dict[str, Any] = {"db_path": db_path, "tables": {}}
            for t in tables:
                try:
                    table_esc = str(t).replace("'", "''")
                    cur.execute(f"PRAGMA table_info('{table_esc}')")
                    cols = []
                    for r in cur.fetchall():
                        cols.append(
                            {
                                "name": r["name"],
                                "type": r["type"],
                                "notnull": int(r["notnull"]) if "notnull" in r.keys() else 0,
                                "pk": int(r["pk"]) if "pk" in r.keys() else 0,
                            }
                        )
                    schema["tables"][t] = cols
                except Exception as e:
                    schema["tables"][t] = {"error": str(e)}
            conn.close()
            return {"success": True, "tool": self.name, "result": schema}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}
