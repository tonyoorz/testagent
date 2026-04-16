"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
import sqlite3
import json

logger = logging.getLogger(__name__)


class SQLiteQueryTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        super().__init__(
            name="run_sqlite_query",
            description="执行SQLite只读查询（SELECT/WITH），并返回结果样本",
            parameters={
                "sql": {"type": "string", "description": "SQL 查询语句（只允许 SELECT / WITH）"},
                "limit": {"type": "integer", "description": "最大返回行数", "default": 200},
            },
        )
        self._db_path = db_path

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        db_path = self._db_path
        if not db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}
        sql = str(kwargs.get("sql") or "").strip()
        limit = int(kwargs.get("limit") or 200)
        if limit <= 0:
            limit = 200
        if not _is_safe_readonly_sql(sql):
            return {"success": False, "tool": self.name, "error": "仅允许只读查询（SELECT/WITH），且禁止多语句与写操作"}
        try:
            final_sql = _ensure_limit(sql, limit)
            conn = _open_sqlite_readonly(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(final_sql)
            rows = cur.fetchall()
            conn.close()
            items = [dict(r) for r in rows]
            cols = list(items[0].keys()) if items else []
            evidence_bundle = build_evidence_bundle(
                sql_used=final_sql,
                rows=items,
                total_count=None,
                key_fields=cols,
                rule_ids=[],
                evidence_gap=[],
            )
            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "columns": cols,
                    "rows": items,
                    "row_count": len(items),
                    "sql": final_sql,
                    "evidence_bundle": evidence_bundle,
                },
            }
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e), "result": {"sql": sql}}


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    m = re.search(r"\{[\\s\\S]*\}", s)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _extract_business_query_hints(question: str) -> Dict[str, Any]:
    q = str(question or "").strip()
    ql = q.lower()
    hints: Dict[str, Any] = {
        "time_range": "",
        "severity": [],
        "status": [],
        "matrix_levels": [],
        "flags": [],
        "module_keywords": [],
        "aida_keywords": [],
        "ecu_keywords": [],
        "project_tokens": [],
    }

    if any(k in q for k in ["昨天", "昨日"]) or "yesterday" in ql:
        hints["time_range"] = "yesterday"
    elif any(k in q for k in ["今天", "今日"]) or "today" in ql:
        hints["time_range"] = "today"
    elif any(k in q for k in ["本周", "这周"]) or "this week" in ql:
        hints["time_range"] = "this_week"
    elif any(k in q for k in ["上周", "前一周"]) or "last week" in ql:
        hints["time_range"] = "last_week"

    sev = []
    if any(k in q for k in ["高优先级", "严重", "紧急", "高风险"]) or any(k in ql for k in ["critical", "major", "high", "s1", "s2"]):
        sev.extend(["critical", "major", "high"])
    if any(k in q for k in ["中优先级", "中风险"]) or any(k in ql for k in ["medium", "s3"]):
        sev.append("medium")
    if any(k in q for k in ["低优先级", "低风险"]) or any(k in ql for k in ["minor", "low", "s4"]):
        sev.append("low")
    if sev:
        hints["severity"] = sorted(set(sev))

    if "topissue" in ql or "top issue" in ql or "topissue" in q:
        hints["flags"].append("topissue")
    if any(k in q for k in ["长跑", "长周期"]) or "long runner" in ql or "longrunner" in ql:
        hints["flags"].append("long_runner")

    status_tokens = {
        "open": ["open", "打开", "待修复", "未关闭", "new", "draft", "待处理", "未解决"],
        "closed": [
            "closed", "关闭", "已关闭", "已修复", "resolved", "fixed", "done", "completed",
            "concluded", "结案", "已结案", "无需处理", "cwa", "concluded without action"
        ],
        "in_progress": [
            "处理中", "进行中", "in progress", "working", "analysis", "testing", "verification",
            "预分析", "分析中", "验证中", "测试中"
        ],
        "reopen": ["reopen", "重开", "重新打开"],
    }
    for canonical, keys in status_tokens.items():
        if any(str(k).lower() in ql for k in keys):
            hints["status"].append(canonical)

    for lv in ["1a", "1b", "1c", "2a", "2b", "2c", "3a", "3b", "4a", "4b", "4c", "4d", "4e"]:
        if lv in ql:
            hints["matrix_levels"].append(lv.upper())
    if "matrix" in ql or "矩阵" in q or "等级" in q:
        hints["flags"].append("matrix")

    aida_terms = ["aida", "音频", "导航", "蓝牙", "车机", "hmi", "voice", "display", "carplay", "android auto"]
    for term in aida_terms:
        if str(term).lower() in ql:
            hints["aida_keywords"].append(str(term).lower())

    ecu_patterns = re.findall(r"\bECU[_\-]?[A-Za-z0-9]+\b", q, flags=re.IGNORECASE)
    if ecu_patterns:
        hints["ecu_keywords"] = [str(e).upper() for e in ecu_patterns[:6]]

    proj_tokens = re.findall(r"\b[A-Z]{2,}[A-Z0-9_\-]{1,}\b", q)
    if proj_tokens:
        hints["project_tokens"] = [p for p in proj_tokens[:6]]

    module_map = {
        "audio": ["音频", "声音", "audio"],
        "navigation": ["导航", "地图", "navigation", "map"],
        "connectivity": ["互联", "连接", "蓝牙", "carplay", "android auto", "connect"],
        "display": ["显示", "屏幕", "display", "hmi"],
        "voice": ["语音", "voice", "asr"],
    }
    modules = []
    for canonical, keys in module_map.items():
        if any(k in ql for k in [str(x).lower() for x in keys]):
            modules.append(canonical)
    if modules:
        hints["module_keywords"] = sorted(set(modules))

    hints["flags"] = sorted(set(hints["flags"]))
    hints["status"] = sorted(set(hints["status"]))
    hints["matrix_levels"] = sorted(set(hints["matrix_levels"]))
    hints["aida_keywords"] = sorted(set(hints["aida_keywords"]))
    hints["ecu_keywords"] = sorted(set(hints["ecu_keywords"]))
    hints["project_tokens"] = sorted(set(hints["project_tokens"]))
    return hints


def _augment_question_with_business_hints(question: str) -> Tuple[str, Dict[str, Any]]:
    q = str(question or "").strip()
    hints = _extract_business_query_hints(q)

    # P1: 项目别名标准化 - 将用户口语化的项目名统一
    _PROJECT_ALIAS_MAP: Dict[str, str] = {
        "idcevo": "IDCevo", "idcevo25": "IDCevo", "idc evo": "IDCevo", "idc-evo": "IDCevo",
        "idc": "IDC", "idc4": "IDC",
        "mgu": "MGU", "mgu22": "MGU", "mgu21": "MGU", "mgu18": "MGU",
        "rsu": "RSU",
        "app": "App",
    }
    normalized_projects: List[str] = []
    q_lower = q.lower()
    for alias, canonical in _PROJECT_ALIAS_MAP.items():
        if alias in q_lower and canonical not in hints.get("project_tokens", []):
            normalized_projects.append(canonical)
    if normalized_projects and "project_tokens" not in hints:
        hints["project_tokens"] = []
    if normalized_projects:
        hints["project_tokens"] = list(set(hints.get("project_tokens", []) + normalized_projects))

    hint_lines = []
    if hints.get("time_range"):
        hint_lines.append(f"time_range={hints['time_range']}")
    if hints.get("severity"):
        hint_lines.append(f"severity={','.join(hints['severity'])}")
    if hints.get("status"):
        hint_lines.append(f"status={','.join(hints['status'])}")
    if hints.get("matrix_levels"):
        hint_lines.append(f"matrix_levels={','.join(hints['matrix_levels'])}")
    if hints.get("flags"):
        hint_lines.append(f"flags={','.join(hints['flags'])}")
    if hints.get("module_keywords"):
        hint_lines.append(f"module_keywords={','.join(hints['module_keywords'])}")
    if hints.get("aida_keywords"):
        hint_lines.append(f"aida_keywords={','.join(hints['aida_keywords'])}")
    if hints.get("ecu_keywords"):
        hint_lines.append(f"ecu_keywords={','.join(hints['ecu_keywords'])}")
    if hints.get("project_tokens"):
        hint_lines.append(f"project_tokens={','.join(hints['project_tokens'])}")
    if not hint_lines:
        return q, hints
    augmented = f"{q}\n\n业务语义提示: {'; '.join(hint_lines)}"
    return augmented, hints


def _build_sql_result_explanation(question: str, sql: str, rows: List[Dict[str, Any]], hints: Dict[str, Any]) -> Dict[str, Any]:
    row_count = len(rows or [])
    cols = list(rows[0].keys()) if row_count else []
    highlights: List[str] = [f"命中 {row_count} 条记录"]
    if hints.get("time_range"):
        highlights.append(f"时间范围推断: {hints.get('time_range')}")
    if hints.get("severity"):
        highlights.append(f"严重度关注: {', '.join(hints.get('severity') or [])}")
    if hints.get("status"):
        highlights.append(f"状态关注: {', '.join(hints.get('status') or [])}")
    if hints.get("flags"):
        highlights.append(f"业务标签: {', '.join(hints.get('flags') or [])}")
    cautions: List[str] = []
    if row_count == 0:
        cautions.append("查询结果为空，建议放宽时间或筛选条件")
    if row_count >= 180:
        cautions.append("结果接近返回上限，建议追加聚合条件")
    rule_ids = hints.get("semantic_rule_ids") if isinstance(hints, dict) and isinstance(hints.get("semantic_rule_ids"), list) else []
    evidence_bundle = build_evidence_bundle(
        sql_used=sql,
        rows=rows,
        total_count=None,
        key_fields=cols,
        rule_ids=rule_ids,
        evidence_gap=[],
    )
    return {
        "question": str(question or ""),
        "sql": str(sql or ""),
        "row_count": row_count,
        "columns": cols,
        "highlights": highlights,
        "cautions": cautions,
        "evidence_bundle": evidence_bundle,
    }
