"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool
import json
import time

logger = logging.getLogger(__name__)


class SQLiteNLQueryWithFixTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str], llm: Any = None):
        super().__init__(
            name="query_sqlite_with_fix",
            description="把自然语言问题转为SQLite只读SQL并执行；失败时自动纠错重试",
            parameters={
                "question": {"type": "string", "description": "自然语言问题"},
                "limit": {"type": "integer", "description": "最大返回行数", "default": 200},
                "table": {"type": "string", "description": "可选：限制在某一张表", "default": ""},
            },
        )
        self._db_path = db_path
        self._llm = llm
        self._sql_cache: Dict[str, str] = {}
        self._schema_tool = SQLiteSchemaTool(db_path)
        self._profile_tool = SQLiteDBProfileTool(db_path)
        self._query_tool = SQLiteQueryTool(db_path)
        self._schema_cache: Dict[str, Any] = {}
        self._profile_cache: Dict[str, Any] = {}
        self._meta_cache_ts: Dict[str, float] = {}
        self._result_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        try:
            self._schema_cache_ttl = max(30, int(os.getenv("AGENT_SQL_SCHEMA_CACHE_TTL", "300") or 300))
        except Exception:
            self._schema_cache_ttl = 300
        try:
            self._result_cache_ttl = max(10, int(os.getenv("AGENT_SQL_RESULT_CACHE_TTL", "60") or 60))
        except Exception:
            self._result_cache_ttl = 60
        try:
            self._result_cache_max_rows = max(50, int(os.getenv("AGENT_SQL_RESULT_CACHE_MAX_ROWS", "500") or 500))
        except Exception:
            self._result_cache_max_rows = 500

    # 列名与业务语义的对照映射，用于 NL→SQL prompt 注入
    _COLUMN_SEMANTICS: Dict[str, Dict[str, str]] = {
        "tproject": {"cn": "项目/车系", "desc": "如 IDCevo/IDC/MGU/RSU/App 等项目缩写", "example": "IDCevo, MGU22, RSU"},
        "project": {"cn": "项目/车系", "desc": "同 tproject，映射后的项目字段", "example": "IDCevo, IDC, MGU, RSU, App"},
        "severity_group": {"cn": "严重度", "desc": "缺陷严重等级", "example": "Critical, Major, Minor"},
        "severity": {"cn": "严重度", "desc": "原始严重度字段", "example": "1-Critical, 2-Major, 3-Minor"},
        "matrix_display": {"cn": "风险矩阵标签", "desc": "风险等级标签(矩阵位置)", "example": "MATRIX-1A, MATRIX-1B, MATRIX-2C"},
        "aida_english": {"cn": "功能模块/AIDA", "desc": "功能域英文名", "example": "Audio, Navigation, Bluetooth"},
        "top_aida": {"cn": "主AIDA", "desc": "团队口径的主要AIDA", "example": "Audio, HMI"},
        "topissue": {"cn": "TopIssue标记", "desc": "是否为关键问题", "example": "TopIssue"},
        "topissue_display": {"cn": "TopIssue分类标签", "desc": "如 showstopper_confirmed 等", "example": "showstopper_candidate, confirmed"},
        "tester": {"cn": "测试人员/发现人", "desc": "缺陷报告人", "example": "人名"},
        "status_phase": {"cn": "缺陷状态/阶段", "desc": "缺陷生命周期阶段", "example": "New, Open, Fixed, Closed, Reopen"},
        "fv": {"cn": "Feature Team/功能团队", "desc": "功能负责团队(DTSV)", "example": "团队名"},
        "pu": {"cn": "PU/SOP", "desc": "first_use_sop 字段", "example": "SOP日期"},
        "domain": {"cn": "Solution Cluster/开发团队", "desc": "负责修复的开发团队", "example": "团队名"},
        "ecu": {"cn": "ECU名称", "desc": "关联的ECU", "example": "ECU-xxx"},
        "creation_time": {"cn": "创建时间", "desc": "缺陷/记录创建时间", "example": "2025-01-15 10:30:00"},
        "tcreationtime": {"cn": "创建时间", "desc": "缺陷创建时间(原始字段)", "example": "2025-01-15"},
        "test_week": {"cn": "测试周(CW)", "desc": "日历周编号", "example": "CW01, CW25"},
        "run_status": {"cn": "测试执行状态", "desc": "manual run 执行结果", "example": "Passed, Failed, Blocked"},
        "software_version": {"cn": "软件版本", "desc": "被测软件版本号", "example": "版本号"},
        "detected_by": {"cn": "发现人", "desc": "同 tester", "example": "人名"},
        "processing_cycle_days": {"cn": "处理天数", "desc": "缺陷处理周期(天)", "example": "30, 60, 120"},
        "run_by": {"cn": "执行人", "desc": "测试用例执行者", "example": "人名"},
        "author_name": {"cn": "提交人", "desc": "测试用例作者", "example": "人名"},
    }

    # 项目名别名映射（用于 entity token 标准化）
    _PROJECT_ALIASES: Dict[str, List[str]] = {
        "idcevo": ["idcevo", "idcevo25", "idc evo", "idc-evo", "idcevo_25", "idcevo-25"],
        "idc": ["idc", "idc4", "idc 4"],
        "mgu": ["mgu", "mgu22", "mgu21", "mgu18", "mgu 22"],
        "rsu": ["rsu", "rsu2", "rsu3"],
        "app": ["app", "application"],
    }

    def _build_column_semantics_prompt(self, schema: Dict[str, Any]) -> str:
        """从 schema 和预设语义映射生成列说明文本，注入 system prompt。"""
        lines: List[str] = []
        tables = schema.get("tables") or {}

        # 构建反向映射：列名→用户可能的说法
        col_to_nl: Dict[str, List[str]] = {}
        for nl_term, col_name in self._NL_TO_COLUMN_MAP.items():
            col_to_nl.setdefault(col_name, []).append(nl_term)

        for table_name, table_info in tables.items():
            if not isinstance(table_info, list):
                continue
            for col_info in table_info:
                col_name = col_info.get("name", "") if isinstance(col_info, dict) else ""
                if not col_name:
                    continue
                sem = self._COLUMN_SEMANTICS.get(col_name)
                if sem:
                    nl_terms = col_to_nl.get(col_name, [])
                    nl_hint = f"（用户可能说：{'/'.join(nl_terms)}）" if nl_terms else ""
                    lines.append(
                        f"- {col_name}: {sem['cn']}。{sem['desc']}。典型值: {sem.get('example', '')} {nl_hint}"
                    )
                else:
                    col_type = col_info.get("type", "") if isinstance(col_info, dict) else ""
                    lines.append(f"- {col_name} ({col_type})")
        return "\n".join(lines) if lines else "(无列语义信息)"

    # P2: 用户自然语言→列名的桥接映射
    _NL_TO_COLUMN_MAP: Dict[str, str] = {
        "项目": "tproject",
        "车系": "tproject",
        "严重度": "severity_group",
        "严重等级": "severity_group",
        "风险矩阵": "matrix_display",
        "矩阵标签": "matrix_display",
        "功能模块": "aida_english",
        "模块": "aida_english",
        "领域": "aida_english",
        "AIDA": "aida_english",
        "状态": "status_phase",
        "阶段": "status_phase",
        "测试人员": "tester",
        "发现人": "tester",
        "报告人": "tester",
        "功能团队": "fv",
        "Feature Team": "fv",
        "开发团队": "domain",
        "Solution Cluster": "domain",
        "ECU": "ecu",
        "软件版本": "software_version",
        "测试周": "test_week",
        "执行状态": "run_status",
        "执行人": "run_by",
        "创建时间": "creation_time",
        "处理天数": "processing_cycle_days",
    }

    def _normalize_project_token(self, token: str) -> Optional[str]:
        """将用户输入的项目名标准化为数据库中可能的形式。"""
        tl = str(token or "").strip().lower()
        if not tl:
            return None
        for canonical, aliases in self._PROJECT_ALIASES.items():
            if tl in aliases or tl == canonical:
                return canonical
            # 模糊匹配：别名前缀
            for alias in aliases:
                if alias.startswith(tl) or tl.startswith(alias):
                    return canonical
        return None

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        if not self._db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}
        if not self._llm or not hasattr(self._llm, "chat_completion"):
            return {"success": False, "tool": self.name, "error": "未配置可用的LLM（需要 llm.chat_completion ）"}
        question = str(kwargs.get("question") or "").strip()
        if not question:
            return {"success": False, "tool": self.name, "error": "question 不能为空"}
        limit = int(kwargs.get("limit") or 200)
        table = str(kwargs.get("table") or "").strip()
        incoming_semantic_hints = kwargs.get("semantic_hints") if isinstance(kwargs.get("semantic_hints"), dict) else {}

        semantic_adapter: Dict[str, Any] = {}
        semantic_hints: Dict[str, Any] = dict(incoming_semantic_hints or {})
        try:
            from semantic_catalog.term_adapter import adapt_question_with_semantic_terms, is_semantic_catalog_enabled, merge_semantic_hints

            if is_semantic_catalog_enabled():
                semantic_adapter = adapt_question_with_semantic_terms(
                    question=question,
                    table_name=table,
                    db_path=self._db_path,
                    prefer_db=True,
                )
                semantic_hints = merge_semantic_hints(semantic_hints, semantic_adapter.get("semantic_hints"))
        except Exception as e:
            logger.debug(f"semantic term adapter skipped: {e}")

        normalized_question, business_hints = _augment_question_with_business_hints(question)
        query_strategy = decide_query_execution_strategy(
            question=question,
            columns=[],
            semantic_hints=semantic_hints,
        )
        business_hints["query_execution_strategy"] = query_strategy
        if semantic_hints:
            business_hints["semantic_term_hints"] = semantic_hints
            mapped_dimensions = semantic_adapter.get("mapped_dimensions") if isinstance(semantic_adapter, dict) else []
            matched_rule_ids = semantic_adapter.get("matched_rule_ids") if isinstance(semantic_adapter, dict) else []
            if isinstance(mapped_dimensions, list) and mapped_dimensions:
                business_hints["semantic_mapped_dimensions"] = mapped_dimensions[:10]
            if isinstance(matched_rule_ids, list) and matched_rule_ids:
                business_hints["semantic_rule_ids"] = matched_rule_ids[:20]

            semantic_tokens: List[str] = []
            if semantic_hints.get("wants_aida_dist"):
                semantic_tokens.append("aida")
            if semantic_hints.get("wants_showstopper"):
                semantic_tokens.append("showstopper")
            if semantic_hints.get("wants_showstopper_candidate"):
                semantic_tokens.append("candidate")
            month_number = semantic_hints.get("month_number")
            if isinstance(month_number, int) and 1 <= month_number <= 12:
                semantic_tokens.append(f"month={month_number:02d}")
            if semantic_tokens:
                normalized_question = f"{normalized_question}\n\nsemantic_terms: {' '.join(sorted(set(semantic_tokens)))}"

        now = time.time()

        cache_key = f"{question}||{table or '*'}"
        cached_result_entry = self._result_cache.get(cache_key)
        if cached_result_entry:
            cache_ts, cached_payload = cached_result_entry
            if (now - float(cache_ts)) < self._result_cache_ttl:
                out = deepcopy(cached_payload)
                out.setdefault("result", {})
                out["result"]["cache_hit"] = True
                out["result"]["cache_type"] = "result_cache"
                out["result"]["query_execution_strategy"] = query_strategy
                existing_hints = out["result"].get("business_hints") if isinstance(out["result"].get("business_hints"), dict) else {}
                merged_hints = dict(existing_hints)
                merged_hints["query_execution_strategy"] = query_strategy
                out["result"]["business_hints"] = merged_hints
                out["tool"] = self.name
                return out

        cached_sql = self._sql_cache.get(cache_key)
        if cached_sql:
            cached_run = self._query_tool.execute(None, sql=cached_sql, limit=limit)
            if cached_run.get("success") is True:
                cached_run["result"] = cached_run.get("result") or {}
                cached_run["result"]["generated_sql"] = cached_sql
                cached_run["result"]["attempts"] = 0
                cached_run["result"]["cache_hit"] = True
                cached_run["result"]["cache_type"] = "sql_cache"
                rows_cached = cached_run["result"].get("rows") or []
                cached_run["result"]["business_hints"] = business_hints
                cached_run["result"]["query_execution_strategy"] = query_strategy
                cached_run["result"]["business_explanation"] = _build_sql_result_explanation(question, cached_sql, rows_cached, business_hints)
                cached_run["result"]["evidence_bundle"] = build_evidence_bundle(
                    sql_used=cached_sql,
                    rows=rows_cached,
                    total_count=None,
                    key_fields=cached_run["result"].get("columns") if isinstance(cached_run["result"].get("columns"), list) else None,
                    rule_ids=business_hints.get("semantic_rule_ids") if isinstance(business_hints.get("semantic_rule_ids"), list) else [],
                    evidence_gap=[],
                )
                cached_run["tool"] = self.name
                if len(rows_cached) <= self._result_cache_max_rows:
                    self._result_cache[cache_key] = (now, deepcopy(cached_run))
                return cached_run

        cache_meta_key = table or "*"
        meta_ts = float(self._meta_cache_ts.get(cache_meta_key) or 0)
        schema = {}
        profile = {}
        if (
            cache_meta_key in self._schema_cache
            and cache_meta_key in self._profile_cache
            and (now - meta_ts) < self._schema_cache_ttl
        ):
            schema = self._schema_cache.get(cache_meta_key) or {}
            profile = self._profile_cache.get(cache_meta_key) or {}
        else:
            schema_out = self._schema_tool.execute(None, table=table)
            if schema_out.get("success") is not True:
                return {"success": False, "tool": self.name, "error": schema_out.get("error") or "读取schema失败"}
            schema = (schema_out.get("result") or {})

            profile_out = self._profile_tool.execute(None, table=table, top_n=5, sample_columns=20)
            profile = (profile_out.get("result") or {}) if profile_out.get("success") is True else {}

            self._schema_cache[cache_meta_key] = schema
            self._profile_cache[cache_meta_key] = profile
            self._meta_cache_ts[cache_meta_key] = now

        semantic_context = ""
        try:
            from semantic_catalog.term_adapter import is_semantic_catalog_enabled
            from semantic_catalog.runtime import build_semantic_context

            if is_semantic_catalog_enabled():
                semantic_context = build_semantic_context(question=normalized_question, db_path=self._db_path, max_each=6)
        except Exception as e:
            logger.debug(f"build_semantic_context skipped: {e}")

        column_semantics = self._build_column_semantics_prompt(schema)
        sys_prompt = (
            "你是SQLite专家。根据用户问题与数据库schema生成只读SQL。\n"
            "严格要求：只允许 SELECT 或 WITH；必须使用 schema 中存在的表与列；只输出JSON。\n"
            "优先参考 semantic_context 中的业务定义和指标口径，结合 business_hints 约束筛选条件。\n"
            "优先参考业务语义提示中的 time_range、severity、status、matrix_levels、aida_keywords、ecu_keywords、project_tokens。\n"
            "\n"
            "## 列名与业务含义对照表\n"
            "以下是数据库列名对应的中文业务含义和典型值，生成SQL时必须参照此映射：\n"
            + column_semantics + "\n"
            '输出格式：{\"sql\":\"...\"}'
        )
        user_payload = {
            "question": question,
            "normalized_question": normalized_question,
            "business_hints": business_hints,
            "semantic_term_hints": semantic_hints,
            "semantic_term_adapter": {
                "mapped_dimensions": (semantic_adapter.get("mapped_dimensions") if isinstance(semantic_adapter, dict) else []) or [],
                "matched_rule_ids": (semantic_adapter.get("matched_rule_ids") if isinstance(semantic_adapter, dict) else []) or [],
            },
            "schema": schema,
            "db_profile": profile,
            "semantic_context": semantic_context,
            "limit_hint": limit,
        }
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}]
        first = self._llm.chat_completion(messages, temperature=0.1, max_tokens=800)
        obj = _extract_json_object(first) or {}
        sql = str(obj.get("sql") or "").strip()
        if not sql:
            return {
                "success": False,
                "tool": self.name,
                "error": "模型未返回可解析的SQL",
                "result": {
                    "raw": first,
                    "business_hints": business_hints,
                    "query_execution_strategy": query_strategy,
                },
            }

        run_out = self._query_tool.execute(None, sql=sql, limit=limit)
        if run_out.get("success") is True:
            self._sql_cache[cache_key] = sql
            run_out["result"] = run_out.get("result") or {}
            run_out["result"]["generated_sql"] = sql
            run_out["result"]["attempts"] = 1
            run_out["result"]["cache_hit"] = False
            run_out["result"]["cache_type"] = "none"
            rows_out = run_out["result"].get("rows") or []
            run_out["result"]["business_hints"] = business_hints
            run_out["result"]["query_execution_strategy"] = query_strategy
            run_out["result"]["business_explanation"] = _build_sql_result_explanation(question, sql, rows_out, business_hints)
            run_out["result"]["evidence_bundle"] = build_evidence_bundle(
                sql_used=sql,
                rows=rows_out,
                total_count=None,
                key_fields=run_out["result"].get("columns") if isinstance(run_out["result"].get("columns"), list) else None,
                rule_ids=business_hints.get("semantic_rule_ids") if isinstance(business_hints.get("semantic_rule_ids"), list) else [],
                evidence_gap=[],
            )
            run_out["tool"] = self.name
            if len(rows_out) <= self._result_cache_max_rows:
                self._result_cache[cache_key] = (time.time(), deepcopy(run_out))
            return run_out

        # P3: SQL 纠错重试循环（最多 3 轮）
        err = str(run_out.get("error") or "")
        fix_prompt_template = (
            "上一次SQL执行失败。请根据错误信息与schema修复SQL。\n"
            "修复时必须严格遵循列名业务含义映射，特别注意：\n"
            + column_semantics + "\n"
            "同时参考 semantic_context 的口径定义，并保持与 business_hints 一致。\n"
            "仍然只允许 SELECT 或 WITH；只输出JSON。\n"
            '输出格式：{"sql":"..."}'
        )

        previous_sql = sql
        previous_err = err
        max_fix_attempts = 3

        for attempt_idx in range(1, max_fix_attempts + 1):
            fix_payload = {
                "question": question,
                "normalized_question": normalized_question,
                "business_hints": business_hints,
                "schema": schema,
                "semantic_context": semantic_context,
                "previous_sql": previous_sql,
                "error": previous_err,
                "attempt": attempt_idx,
                "limit_hint": limit,
            }
            messages = [{"role": "system", "content": fix_prompt_template}, {"role": "user", "content": json.dumps(fix_payload, ensure_ascii=False)}]
            fix_response = self._llm.chat_completion(messages, temperature=0.1, max_tokens=900)
            obj_fix = _extract_json_object(fix_response) or {}
            sql_fix = str(obj_fix.get("sql") or "").strip()
            if not sql_fix:
                if attempt_idx < max_fix_attempts:
                    continue
                return {
                    "success": False,
                    "tool": self.name,
                    "error": f"SQL纠错失败（{attempt_idx}轮）：模型未返回可解析SQL",
                    "result": {
                        "raw": fix_response,
                        "previous_sql": previous_sql,
                        "error": previous_err,
                        "business_hints": business_hints,
                        "query_execution_strategy": query_strategy,
                    },
                }

            run_fix = self._query_tool.execute(None, sql=sql_fix, limit=limit)
            if run_fix.get("success") is True:
                self._sql_cache[cache_key] = sql_fix
                run_fix["result"] = run_fix.get("result") or {}
                run_fix["result"]["generated_sql"] = sql_fix
                run_fix["result"]["attempts"] = 1 + attempt_idx
                run_fix["result"]["cache_hit"] = False
                run_fix["result"]["cache_type"] = "none"
                rows_fix = run_fix["result"].get("rows") or []
                run_fix["result"]["business_hints"] = business_hints
                run_fix["result"]["query_execution_strategy"] = query_strategy
                run_fix["result"]["business_explanation"] = _build_sql_result_explanation(question, sql_fix, rows_fix, business_hints)
                run_fix["result"]["evidence_bundle"] = build_evidence_bundle(
                    sql_used=sql_fix,
                    rows=rows_fix,
                    total_count=None,
                    key_fields=run_fix["result"].get("columns") if isinstance(run_fix["result"].get("columns"), list) else None,
                    rule_ids=business_hints.get("semantic_rule_ids") if isinstance(business_hints.get("semantic_rule_ids"), list) else [],
                    evidence_gap=[],
                )
                run_fix["tool"] = self.name
                if len(rows_fix) <= self._result_cache_max_rows:
                    self._result_cache[cache_key] = (time.time(), deepcopy(run_fix))
                return run_fix

            previous_sql = sql_fix
            previous_err = str(run_fix.get("error") or "")

        return {
            "success": False,
            "tool": self.name,
            "error": f"SQL纠错{max_fix_attempts}轮后仍失败: {previous_err}",
            "result": {
                "last_fixed_sql": previous_sql,
                "last_error": previous_err,
                "original_sql": sql,
                "business_hints": business_hints,
                "query_execution_strategy": query_strategy,
            },
        }

    def clear_cache(self) -> None:
        """Clear SQL/schema/profile/result caches for this tool instance."""
        self._sql_cache.clear()
        self._schema_cache.clear()
        self._profile_cache.clear()
        self._meta_cache_ts.clear()
        self._result_cache.clear()

    def refresh_schema_cache(self, table: str = "") -> None:
        """Force refresh schema/profile cache for a specific table or all tables."""
        table_key = str(table or "").strip()
        cache_meta_key = table_key or "*"
        schema_out = self._schema_tool.execute(None, table=table_key)
        if schema_out.get("success") is not True:
            raise RuntimeError(str(schema_out.get("error") or "读取schema失败"))
        profile_out = self._profile_tool.execute(None, table=table_key, top_n=5, sample_columns=20)
        self._schema_cache[cache_meta_key] = schema_out.get("result") or {}
        self._profile_cache[cache_meta_key] = (profile_out.get("result") or {}) if profile_out.get("success") is True else {}
        self._meta_cache_ts[cache_meta_key] = time.time()
