"""
智能 Agent 系统 - 为数据分析提供增强的 AI 对话能力

核心功能：
1. 工具调用系统 - AI 可执行数据分析操作
2. 智能上下文管理 - 根据问题动态筛选数据
3. 对话记忆系统 - 记住关键洞察和用户偏好
4. 知识库集成 - RAG 能力提供领域知识
5. 任务规划能力 - 分解复杂任务
6. 增强系统提示词 - 专业领域知识

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Generator, Union, Tuple
import re
import sqlite3
import time
import multiprocessing
from functools import lru_cache
from collections import defaultdict
from copy import deepcopy
import logging
from urllib.parse import quote
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.core.conversation_memory import ConversationMemory as ExtractedConversationMemory
from agent.core.task_planner import TaskPlanner as ExtractedTaskPlanner
from agent.core.tool_executor import (
    ToolExecutor as ExtractedToolExecutor,
    ToolExecutorWithRetry as ExtractedToolExecutorWithRetry,
)
from agent.core.conversation_runtime import (
    init_analysis_trace,
    resolve_execution_mode,
    serialize_plan_trace,
)
from agent.core.agentic_runtime import (
    build_tool_specs,
    run_agentic_loop,
)
from agent.core.deterministic_sql_service import decide_query_execution_strategy
from agent.core.sql_runtime_service import build_evidence_bundle

from analysis_utils import (
    compute_defect_explore_kpis,
    defect_quality_stats,
    defect_wordcloud_source,
    inflow_outflow_summary,
    longrunner_phase_statistics,
    nunique_by,
    pick_risk_score_column,
    severity_rate_by,
    stacked_top_counts,
    time_series_counts,
    top_counts,
    word_frequencies,
)

try:
    from agent.tools.smart_tool_selector import (
        SmartToolSelector,
        create_smart_tool_selector,
    )
    SMART_TOOL_SELECTOR_AVAILABLE = True
except Exception:
    SmartToolSelector = None
    create_smart_tool_selector = None
    SMART_TOOL_SELECTOR_AVAILABLE = False

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _tokenize_text(text: str) -> List[str]:
    if not text:
        return []
    toks = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", str(text).lower())
    out = []
    for t in toks:
        s = str(t).strip()
        if not s or len(s) <= 1:
            continue
        out.append(s)
    return out


def _collect_evidence_bundles(context: Dict[str, Any], execution_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bundles: List[Dict[str, Any]] = []
    for candidate in [
        context.get("critic_evidence_bundle"),
        context.get("evidence_bundle"),
    ]:
        if isinstance(candidate, dict):
            bundles.append(candidate)

    for row in (execution_results or []):
        if not isinstance(row, dict):
            continue
        tool_output = row.get("result") if isinstance(row.get("result"), dict) else {}
        nested_result = tool_output.get("result") if isinstance(tool_output.get("result"), dict) else {}
        for candidate in [
            row.get("evidence_bundle"),
            tool_output.get("evidence_bundle"),
            nested_result.get("evidence_bundle"),
        ]:
            if isinstance(candidate, dict):
                bundles.append(candidate)

    return bundles


def _build_critic_evidence_bundle(context: Dict[str, Any], execution_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    bundles = _collect_evidence_bundles(context, execution_results)

    merged: Dict[str, Any] = {
        "sql_used": "",
        "sample_count": 0,
        "total_count": None,
        "key_fields": [],
        "rule_ids": [],
        "evidence_gap": [],
    }
    seen_gaps = set()
    seen_fields = set()
    seen_rules = set()

    for bundle in bundles:
        sql_used = str(bundle.get("sql_used") or bundle.get("sql") or "").strip()
        if sql_used and not merged["sql_used"]:
            merged["sql_used"] = sql_used

        total_count = bundle.get("total_count")
        if merged["total_count"] is None and isinstance(total_count, (int, np.integer)):
            merged["total_count"] = int(total_count)

        sample_count = bundle.get("sample_count")
        if isinstance(sample_count, (int, np.integer, float)):
            try:
                merged["sample_count"] = max(int(merged.get("sample_count") or 0), int(sample_count))
            except Exception:
                pass

        key_fields = bundle.get("key_fields") if isinstance(bundle.get("key_fields"), list) else []
        for field in key_fields:
            text = str(field or "").strip()
            key = text.lower()
            if text and key not in seen_fields:
                seen_fields.add(key)
                merged["key_fields"].append(text)

        rule_ids = bundle.get("rule_ids") if isinstance(bundle.get("rule_ids"), list) else []
        for rule in rule_ids:
            text = str(rule or "").strip()
            key = text.lower()
            if text and key not in seen_rules:
                seen_rules.add(key)
                merged["rule_ids"].append(text)

        evidence_gaps = bundle.get("evidence_gap") if isinstance(bundle.get("evidence_gap"), list) else []
        for gap in evidence_gaps:
            text = str(gap or "").strip()
            key = text.lower()
            if text and key not in seen_gaps:
                seen_gaps.add(key)
                merged["evidence_gap"].append(text)

    # Fallback: derive minimal evidence signals from successful tool outputs
    # when explicit evidence bundles are unavailable.
    if not bundles:
        fallback_sample_count = 0
        for row in (execution_results or []):
            if not isinstance(row, dict):
                continue
            tool_output = row.get("result") if isinstance(row.get("result"), dict) else {}
            if tool_output.get("success") is not True:
                continue
            nested_result = tool_output.get("result") if isinstance(tool_output.get("result"), dict) else {}

            rows = nested_result.get("rows") if isinstance(nested_result.get("rows"), list) else []
            dict_rows = [r for r in rows if isinstance(r, dict)]
            if dict_rows:
                fallback_sample_count += len(dict_rows)
                for field in list(dict_rows[0].keys()):
                    text = str(field or "").strip()
                    key = text.lower()
                    if text and key not in seen_fields:
                        seen_fields.add(key)
                        merged["key_fields"].append(text)

            sql_used = str(nested_result.get("sql") or nested_result.get("generated_sql") or "").strip()
            if sql_used and not merged["sql_used"]:
                merged["sql_used"] = sql_used

        if fallback_sample_count > 0:
            merged["sample_count"] = fallback_sample_count

    # If still empty, return empty payload to avoid implying fake evidence.
    if (
        not str(merged.get("sql_used") or "").strip()
        and int(merged.get("sample_count") or 0) <= 0
        and merged.get("total_count") is None
        and not merged.get("key_fields")
        and not merged.get("evidence_gap")
    ):
        return {}

    return merged


@lru_cache(maxsize=16)
def _semantic_core_dimensions(dataset: str) -> List[Dict[str, Any]]:
    try:
        from semantic_catalog.runtime import SemanticCatalog

        catalog = SemanticCatalog().load_catalog() or {}
        dkey = str(dataset or "").strip().lower()
        for ds in (catalog.get("datasets") or []):
            aliases = [str(a).strip().lower() for a in (ds.get("aliases") or [])]
            if str(ds.get("id", "")).strip().lower() == dkey or dkey in aliases:
                dims = ds.get("core_dimensions") or []
                return [d for d in dims if isinstance(d, dict)]
    except Exception:
        return []
    return []


def _resolve_dimension_to_column(dataset: str, dim_or_alias: str, dataframe_columns: List[str]) -> Optional[str]:
    if not dim_or_alias:
        return None
    cols = [str(c) for c in (dataframe_columns or [])]
    col_set = set(cols)
    raw = str(dim_or_alias).strip()
    if raw in col_set:
        return raw
    key = raw.lower()
    for d in _semantic_core_dimensions(str(dataset or "").strip().lower()):
        name = str(d.get("name", "")).strip()
        if not name:
            continue
        aliases = [str(a).strip() for a in (d.get("aliases") or []) if a is not None and str(a).strip()]
        alias_l = [a.lower() for a in aliases]
        if key == name.lower() or key in alias_l:
            if name in col_set:
                return name
            for a in aliases:
                if a in col_set:
                    return a
    if key in col_set:
        return key
    for c in cols:
        if c.lower() == key:
            return c
    return None


_DEFAULT_ANOMALY_RULE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "wow_spike_300pct": {
        "enabled": True,
        "threshold_pct": 300.0,
    },
    "sparse_signal_suppression": {
        "enabled": True,
        "min_baseline": 3.0,
        "min_current": 3.0,
    },
    "risk_concentration_shift": {
        "enabled": False,
        "share_shift_threshold_pct": 20.0,
    },
}


def _coerce_float(value: Any, default: float) -> float:
    try:
        result = float(value)
        if np.isfinite(result):
            return result
    except Exception:
        pass
    return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


@lru_cache(maxsize=1)
def _load_anomaly_rule_configs() -> Dict[str, Dict[str, Any]]:
    configs = deepcopy(_DEFAULT_ANOMALY_RULE_CONFIGS)
    path = os.path.join(PROJECT_ROOT, "semantic_catalog", "business_rules.json")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return configs

    rules = payload.get("business_rules") if isinstance(payload, dict) else []
    if not isinstance(rules, list):
        return configs

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        cfg = rule.get("config")
        if not isinstance(cfg, dict):
            continue
        rule_key = str(cfg.get("rule_key") or "").strip().lower()
        if rule_key not in configs:
            continue

        merged = deepcopy(configs[rule_key])
        merged.update(cfg)
        merged["enabled"] = _coerce_bool(cfg.get("enabled"), bool(merged.get("enabled", True)))

        if rule_key == "wow_spike_300pct":
            merged["threshold_pct"] = _coerce_float(cfg.get("threshold_pct"), float(configs[rule_key]["threshold_pct"]))
        elif rule_key == "sparse_signal_suppression":
            merged["min_baseline"] = _coerce_float(cfg.get("min_baseline"), float(configs[rule_key]["min_baseline"]))
            merged["min_current"] = _coerce_float(cfg.get("min_current"), float(configs[rule_key]["min_current"]))
        elif rule_key == "risk_concentration_shift":
            merged["share_shift_threshold_pct"] = _coerce_float(
                cfg.get("share_shift_threshold_pct"),
                float(configs[rule_key]["share_shift_threshold_pct"]),
            )

        configs[rule_key] = merged

    return configs


def clear_anomaly_rule_config_cache() -> None:
    """Clear the in-process anomaly rule configuration cache."""
    _load_anomaly_rule_configs.cache_clear()


def _extract_risk_share_pct(row: Dict[str, Any]) -> Optional[float]:
    if not isinstance(row, dict):
        return None

    for key in [
        "top_share_pct",
        "dominant_share_pct",
        "share_pct",
        "risk_share_pct",
        "top_share",
        "share",
    ]:
        raw = row.get(key)
        try:
            value = float(raw)
        except Exception:
            continue
        if not np.isfinite(value):
            continue
        if 0.0 <= value <= 1.0:
            return value * 100.0
        return value

    top_bucket = row.get("top_risk_bucket")
    for key in ["risk_distribution", "risk_bucket_distribution", "bucket_distribution"]:
        dist = row.get(key)
        if not isinstance(dist, dict) or not dist:
            continue

        numeric_items: Dict[str, float] = {}
        total = 0.0
        for bucket_name, raw_value in dist.items():
            try:
                bucket_value = float(raw_value)
            except Exception:
                continue
            if not np.isfinite(bucket_value) or bucket_value < 0:
                continue
            numeric_items[str(bucket_name)] = bucket_value
            total += bucket_value

        if total <= 0:
            continue

        if isinstance(top_bucket, str) and top_bucket in numeric_items:
            return (numeric_items[top_bucket] / total) * 100.0

        return (max(numeric_items.values()) / total) * 100.0

    return None


def evaluate_anomaly_rules(trend_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluate configurable anomaly rules against trend points."""
    if not isinstance(trend_data, list) or len(trend_data) < 2:
        return []

    configs = _load_anomaly_rule_configs()
    wow_cfg = configs.get("wow_spike_300pct", {})
    sparse_cfg = configs.get("sparse_signal_suppression", {})
    risk_cfg = configs.get("risk_concentration_shift", {})

    wow_enabled = bool(wow_cfg.get("enabled", True))
    wow_threshold_pct = _coerce_float(wow_cfg.get("threshold_pct"), 300.0)

    sparse_enabled = bool(sparse_cfg.get("enabled", True))
    sparse_baseline = _coerce_float(sparse_cfg.get("min_baseline"), 3.0)
    sparse_current = _coerce_float(sparse_cfg.get("min_current"), 3.0)

    risk_enabled = bool(risk_cfg.get("enabled", False))
    risk_share_shift_threshold = _coerce_float(risk_cfg.get("share_shift_threshold_pct"), 20.0)

    findings: List[Dict[str, Any]] = []

    for idx in range(1, len(trend_data)):
        prev_row = trend_data[idx - 1] if isinstance(trend_data[idx - 1], dict) else {}
        curr_row = trend_data[idx] if isinstance(trend_data[idx], dict) else {}

        try:
            prev_value = float(prev_row.get("value"))
            curr_value = float(curr_row.get("value"))
        except Exception:
            continue

        if not np.isfinite(prev_value) or not np.isfinite(curr_value):
            continue

        sparse_blocked = bool(
            sparse_enabled and (prev_value < sparse_baseline or curr_value < sparse_current)
        )

        if wow_enabled and (not sparse_blocked) and prev_value > 0:
            change_pct = ((curr_value - prev_value) / prev_value) * 100.0
            if change_pct >= wow_threshold_pct:
                findings.append(
                    {
                        "rule_id": "wow_spike_300pct",
                        "severity": "high",
                        "index": idx,
                        "group": curr_row.get("group"),
                        "value": curr_value,
                        "previous_group": prev_row.get("group"),
                        "previous_value": prev_value,
                        "change_pct": round(change_pct, 2),
                    }
                )

        if risk_enabled:
            prev_share_pct = _extract_risk_share_pct(prev_row)
            curr_share_pct = _extract_risk_share_pct(curr_row)

            if prev_share_pct is not None and curr_share_pct is not None:
                share_shift_pct = abs(curr_share_pct - prev_share_pct)
                if share_shift_pct >= risk_share_shift_threshold:
                    findings.append(
                        {
                            "rule_id": "risk_concentration_shift",
                            "severity": "medium",
                            "index": idx,
                            "group": curr_row.get("group"),
                            "previous_group": prev_row.get("group"),
                            "top_risk_bucket": curr_row.get("top_risk_bucket"),
                            "previous_top_risk_bucket": prev_row.get("top_risk_bucket"),
                            "top_share_pct": round(curr_share_pct, 2),
                            "previous_top_share_pct": round(prev_share_pct, 2),
                            "share_shift_pct": round(share_shift_pct, 2),
                        }
                    )

    return findings

# ============================================================================
# 1. 工具调用系统
# ============================================================================


# ============================================================================
# Tool definitions — extracted to agent/tools/
# ============================================================================
# Tools are now in individual modules under agent/tools/.
# Use: from agent.tools import build_default_tools
# Or:  from agent.tools.analysis.risk import RiskAnalysisTool

# Helper functions — now in agent/tools/helpers.py
from agent.tools.helpers import (
    resolve_dimension_to_column as _resolve_dimension_to_column,
    semantic_core_dimensions as _semantic_core_dimensions,
    coerce_float as _coerce_float,
    coerce_bool as _coerce_bool,
    load_anomaly_rule_configs as _load_anomaly_rule_configs,
    clear_anomaly_rule_config_cache,
    extract_risk_share_pct as _extract_risk_share_pct,
    evaluate_anomaly_rules,
)

# Unified tool builder
from agent.tools import build_default_tools

# Re-export base class
from agent.tools.base import DataAnalysisTool

class _LegacyToolExecutor:
    """工具执行器 - 管理所有工具的注册和执行"""

    def __init__(self, llm: Any = None, db_path: Optional[str] = None):
        self.tools = {}
        self._llm = llm
        self._db_path = db_path
        self._register_default_tools()

    def _register_default_tools(self):
        """注册默认工具"""
        default_tools = [
            TrendAnalysisTool(),
            RiskAnalysisTool(),
            ComparisonTool(),
            StatisticalSummaryTool(),
            DefectExploreKpiTool(),
            DefectExploreDashboardTool(),
            MatrixDistributionTool(),
            MatrixAidaHotspotsTool(),
            TopIssueHotlistTool(),
            LongRunnerHotlistTool(),
            AnalyzeTesterFindingsTool(),
            AnalyzeTestRunTool(),
            GroupbyAggregateTool(),
            CorrelateDefectsTestsTool(),
            ProjectRecentWeeksHealthTool(),
            SemanticCatalogTool(db_path=self._db_path),
            DuplicateIssueSearchTool(),
            DescribeDatasetTool(),
            MatchTesterTicketsTool(),
            SemanticCoverageReportTool(),
            DefectExploreSchemaReportTool(),
        ]

        for tool in default_tools:
            self.register_tool(tool)
        if self._db_path:
            self.register_tool(SQLiteDBProfileTool(self._db_path))
            self.register_tool(SQLiteSchemaTool(self._db_path))
            self.register_tool(SQLiteQueryTool(self._db_path))
            self.register_tool(SQLiteNLQueryWithFixTool(self._db_path, llm=self._llm))

    def register_tool(self, tool: DataAnalysisTool):
        """注册新工具"""
        self.tools[tool.name] = tool
        logger.info(f"已注册工具: {tool.name}")

    def _validate_and_normalize_params(self, tool: DataAnalysisTool, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        schema = (getattr(tool, "parameters", None) or {}) if isinstance(getattr(tool, "parameters", None), dict) else {}
        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        cleaned: Dict[str, Any] = {}
        reserved = {"dataset"}
        unknown = [k for k in (params or {}).keys() if (k not in schema) and (k not in reserved)]
        if unknown and validation_enabled:
            return False, {}, f"参数不支持: {', '.join([str(k) for k in unknown[:8]])}"

        for k, spec in schema.items():
            if not isinstance(spec, dict):
                continue
            if k in params:
                cleaned[k] = params.get(k)
            elif "default" in spec:
                cleaned[k] = spec.get("default")

        for k in reserved:
            if k in params:
                cleaned[k] = params.get(k)

        def _coerce_bool(v: Any) -> Tuple[bool, Optional[bool]]:
            if isinstance(v, bool):
                return True, v
            if isinstance(v, (int, float)):
                return True, bool(int(v))
            s = str(v).strip().lower()
            if s in {"true", "1", "yes", "y", "是", "对"}:
                return True, True
            if s in {"false", "0", "no", "n", "否", "不"}:
                return True, False
            return False, None

        def _coerce_int(v: Any) -> Tuple[bool, Optional[int]]:
            if isinstance(v, bool):
                return True, int(v)
            if isinstance(v, int):
                return True, v
            if isinstance(v, float) and float(v).is_integer():
                return True, int(v)
            s = str(v).strip()
            if re.fullmatch(r"[-+]?\d+", s):
                try:
                    return True, int(s)
                except Exception:
                    return False, None
            return False, None

        def _coerce_number(v: Any) -> Tuple[bool, Optional[float]]:
            if isinstance(v, bool):
                return True, float(int(v))
            if isinstance(v, (int, float)):
                return True, float(v)
            s = str(v).strip()
            try:
                return True, float(s)
            except Exception:
                return False, None

        def _coerce_array(v: Any) -> Tuple[bool, Optional[List[Any]]]:
            if v is None:
                return True, []
            if isinstance(v, list):
                return True, v
            if isinstance(v, tuple):
                return True, list(v)
            s = str(v).strip()
            if not s:
                return True, []
            parts = [p.strip() for p in re.split(r"[,，;；\n]+", s) if p and p.strip()]
            return True, parts

        def _coerce_object(v: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
            if v is None:
                return True, {}
            if isinstance(v, dict):
                return True, v
            s = str(v).strip()
            if not s:
                return True, {}
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return True, obj
                return False, None
            except Exception:
                return False, None

        for k, spec in schema.items():
            if k not in cleaned:
                continue
            t = str((spec or {}).get("type") or "").lower()
            if not t:
                continue
            v = cleaned.get(k)
            ok = True
            out: Any = v
            if t in {"string"}:
                out = "" if v is None else str(v)
            elif t in {"integer", "int"}:
                ok, out = _coerce_int(v)
            elif t in {"number", "float"}:
                ok, out = _coerce_number(v)
            elif t in {"boolean", "bool"}:
                ok, out = _coerce_bool(v)
            elif t in {"array", "list"}:
                ok, out = _coerce_array(v)
            elif t in {"object", "dict"}:
                ok, out = _coerce_object(v)
            else:
                out = v
            if not ok:
                return False, {}, f"参数类型错误: {k} 需要 {t}"
            if "enum" in spec and spec.get("enum") is not None:
                enum = list(spec.get("enum") or [])
                if enum and out not in enum:
                    return False, {}, f"参数取值错误: {k} 需要为 {enum}"
            cleaned[k] = out

        if not validation_enabled and unknown:
            for k in unknown:
                params.pop(k, None)
        return True, cleaned, ""

    def execute_tool(self, tool_name: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], **kwargs) -> Dict[str, Any]:
        """执行工具"""
        if tool_name not in self.tools:
            return {"success": False, "tool": tool_name, "error": f"工具 '{tool_name}' 不存在"}

        tool = self.tools[tool_name]
        ok, normalized, err = self._validate_and_normalize_params(tool, dict(kwargs))
        if not ok:
            return {"success": False, "tool": tool_name, "error": err or "参数类型错误"}
        kwargs = normalized
        if isinstance(data, dict) and not tool.expects_datasets():
            dataset = kwargs.pop("dataset", None)
            if not dataset:
                dataset = "defects" if "defects" in data else next(iter(data.keys()), None)
            dataset_df = data.get(dataset) if dataset else None
            if dataset_df is None:
                return {"success": False, "tool": tool_name, "error": f"数据集中未找到 dataset={dataset}"}
            output = tool.execute(dataset_df, **kwargs)
        else:
            output = tool.execute(data, **kwargs)
        if output is None:
            return {"success": False, "tool": tool_name, "error": "工具未返回结果"}
        if isinstance(output, dict) and output.get("success") is False:
            output.setdefault("tool", tool_name)
            return output
        if isinstance(output, dict) and "success" not in output and "error" in output:
            return {"success": False, "tool": tool_name, "error": output.get("error") or "未知错误"}
        return output

    def get_tool_schema(self, tool_name: str = None) -> Dict:
        """获取工具的 schema，用于 LLM 理解"""
        if tool_name:
            if tool_name not in self.tools:
                return {}
            tool = self.tools[tool_name]
            return {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
        else:
            return {
                tool.name: {
                    "description": tool.description,
                    "parameters": tool.parameters
                }
                for tool in self.tools.values()
            }


class _LegacyToolExecutorWithRetry(_LegacyToolExecutor):
    """
    带自我修正能力的工具执行器

    功能：
    1. 自动检测空结果并分析原因
    2. 自动修正参数并重试
    3. 错误处理和参数修复
    4. 最终回退到统计摘要
    """

    def __init__(self, llm: Any = None, db_path: Optional[str] = None, max_retry: int = 2):
        super().__init__(llm=llm, db_path=db_path)
        self.max_retry = max_retry
        self._retry_stats = {
            'total_calls': 0,
            'retry_attempts': 0,
            'fallbacks': 0
        }

    def execute_with_retry(self, tool_name: str,
                          data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
                          **kwargs) -> Dict[str, Any]:
        """
        执行工具，支持自动重试和修正

        Args:
            tool_name: 工具名称
            data: 数据集
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        self._retry_stats['total_calls'] += 1

        for attempt in range(self.max_retry + 1):
            result = self.execute_tool(tool_name, data, **kwargs)

            # 检查是否需要重试
            should_retry, analysis = self._analyze_result(result, tool_name, kwargs, data)

            if not should_retry:
                return result

            if attempt < self.max_retry:
                self._retry_stats['retry_attempts'] += 1
                logger.info(f"Tool {tool_name} retry {attempt + 1}: {analysis}")

                # 修正参数
                kwargs = self._fix_params(kwargs, analysis, tool_name)
            else:
                logger.warning(f"Tool {tool_name} max retries exceeded, using fallback")
                break

        # 最终回退
        self._retry_stats['fallbacks'] += 1
        return self._fallback_to_summary(data, tool_name, result)

    def _analyze_result(self, result: Dict[str, Any], tool_name: str,
                        params: Dict, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Tuple[bool, str]:
        """
        分析执行结果，判断是否需要重试

        Returns:
            (should_retry, analysis_reason)
        """
        # 检查执行错误
        if not result.get('success', True):
            error_msg = str(result.get('error', '')).lower()

            if 'not found' in error_msg or '不存在' in error_msg:
                return True, "tool_not_found"
            elif 'parameter' in error_msg or '参数' in error_msg:
                return True, "invalid_parameters"
            elif 'dataset' in error_msg or '数据集' in error_msg:
                return True, "dataset_issue"
            else:
                return False, f"execution_error: {error_msg}"

        # 检查结果是否为空
        tool_result = result.get('result', {})
        if self._is_empty_result(tool_result):
            return True, "empty_result"

        return False, "success"

    def _is_empty_result(self, result: Any) -> bool:
        """检查结果是否为空"""
        if result is None:
            return True
        if isinstance(result, dict):
            # 检查各种空结果模式
            if not result:
                return True
            if 'count' in result and result['count'] == 0:
                return True
            if 'items' in result and not result['items']:
                return True
            if 'data' in result and not result['data']:
                return True
            if 'rows' in result and not result['rows']:
                return True
        if isinstance(result, list) and not result:
            return True
        if isinstance(result, pd.DataFrame) and result.empty:
            return True
        return False

    def _fix_params(self, params: Dict, analysis: str, tool_name: str) -> Dict:
        """
        根据分析结果修正参数

        Args:
            params: 原始参数
            analysis: 分析结果
            tool_name: 工具名称

        Returns:
            修正后的参数
        """
        fixed_params = dict(params)

        if analysis == "empty_result":
            # 空结果 - 可能是过滤条件太严格
            # 放宽一些常见的过滤参数
            for key in list(fixed_params.keys()):
                if key in ['top_n', 'limit', 'max_items']:
                    # 增加返回数量
                    try:
                        current = int(fixed_params[key])
                        fixed_params[key] = max(current, 50)
                    except:
                        fixed_params[key] = 50

                elif key in ['severity', 'status', 'filter']:
                    # 移除严格过滤条件
                    if fixed_params.get(key) in ['Critical', 'Open']:
                        fixed_params.pop(key, None)

        elif analysis == "dataset_issue":
            # 数据集问题 - 尝试切换数据集
            if 'dataset' in fixed_params:
                current = fixed_params['dataset']
                alternatives = ['defects', 'tests'] if current == 'defects' else ['tests', 'defects']
                fixed_params['dataset'] = alternatives[0] if current != alternatives[0] else alternatives[1]

        elif analysis == "invalid_parameters":
            # 参数错误 - 移除未知参数
            known_tool = self.tools.get(tool_name)
            if known_tool and hasattr(known_tool, 'parameters'):
                valid_params = set(known_tool.parameters.keys()) | {'dataset'}
                fixed_params = {k: v for k, v in fixed_params.items() if k in valid_params}

        return fixed_params

    def _fallback_to_summary(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
                            original_tool: str,
                            last_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        回退到统计摘要

        Args:
            data: 数据集
            original_tool: 原始工具名称
            last_result: 最后一次执行结果

        Returns:
            回退结果
        """
        logger.info(f"Fallback to statistical_summary from {original_tool}")

        try:
            # 尝试执行统计摘要工具
            fallback_result = self.execute_tool('statistical_summary', data, dataset='defects')

            if fallback_result.get('success'):
                # 包装回退结果
                return {
                    'success': True,
                    'tool': original_tool,
                    'result': fallback_result.get('result', {}),
                    'fallback': True,
                    'fallback_reason': 'max_retries_exceeded',
                    'original_error': last_result.get('error', 'Unknown error')
                }
        except Exception as e:
            logger.error(f"Fallback failed: {e}")

        # 最终回退 - 返回基本数据信息
        summary = self._generate_basic_summary(data)
        return {
            'success': True,
            'tool': original_tool,
            'result': summary,
            'fallback': True,
            'fallback_reason': 'all_retries_failed',
            'note': '由于原始查询条件过于严格，返回基础数据摘要'
        }

    def _generate_basic_summary(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Dict[str, Any]:
        """生成基础数据摘要"""
        summary = {
            'total_records': 0,
            'summary_text': ''
        }

        try:
            if isinstance(data, dict):
                for name, df in data.items():
                    if isinstance(df, pd.DataFrame):
                        summary[f'{name}_count'] = len(df)
                        summary['total_records'] += len(df)
            elif isinstance(data, pd.DataFrame):
                summary['total_records'] = len(data)
                summary['defects_count'] = len(data)

            summary['summary_text'] = f"数据包含 {summary['total_records']} 条记录"
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            summary['error'] = str(e)

        return summary

    def get_retry_stats(self) -> Dict[str, int]:
        """获取重试统计信息"""
        return dict(self._retry_stats)


# ============================================================================
# 2. 智能上下文管理器
# ============================================================================

class IntelligentContextManager:
    """智能上下文管理器 - 根据问题动态筛选相关数据"""

    def __init__(self):
        self.intent_patterns = {
            'trend': ['趋势', '变化', '增长', '下降', '历史', '流转历史', '状态变更', '状态流转', 'trend', 'change', 'history', 'status history', 'change history'],
            'risk': ['风险', '高风险', '危险', 'risk', 'critical'],
            'comparison': ['对比', '比较', '差异', 'vs', 'compare', 'difference'],
            'summary': ['总结', '概览', '总体', 'summary', 'overview', 'kpi', '指标', '卡片'],
            'auto': ['一键', '自动', '综合', '全盘', '全景', '全量', '深度分析', '不用一个问题一个问题', 'deep dive'],
            'dashboard': ['看板', '图表', '仪表盘', 'dashboard', 'chart', '大屏', '报表', '总览', '总表'],
            'strategy': ['测试策略', '测试计划', '策略', '计划', '怎么测', '如何测试', '测试方案', '质量策略'],
            'distribution': ['分布', '占比', '比例', 'distribution', 'percentage'],
            'top': ['前', '最高', '最差', 'top', 'highest', 'worst', '最多', '最大', 'min', 'max'],
            'project': ['项目', '工程', 'project'],
            'severity': ['严重', '紧急', 'severity', 'critical'],
            'matrix': ['matrix', '矩阵'],
            'aida': ['aida', '功能', '模块', 'feature', 'service', 'services', 'call services'],
            'fv': ['fv', '版本', 'release', '交付版本', 'feature team', 'feature_team', 'feature-team', '功能团队', '责任团队'],
            'domain': ['solution cluster', 'domain', 'cluster', '解决簇', '解决群', 'solution_cluster'],
            'test': ['测试', 'test', 'run', 'case', 'cases', 'testcase', 'testcases', 'test case', 'test cases', 'coverage', '执行', '通过率', '失败率', '测', '测挂', '测失败', '回归', '测试情况', '测试状态', '测试用例'],
            'case': ['case', 'cases', 'testcase', 'testcases', 'test case', 'test cases', '用例', '测试用例', 'case容易', 'case出错', '容易出错'],
            'execution': ['执行', '执行情况', '执行状态', '执行概览', '通过情况', 'execution', 'pass', 'passed', 'fail', 'failed', 'error', 'blocked', '状态', 'run_status', '失败', '挂', '挂了', '成功率'],
            'cross': ['关联', '相关性', '联动', '交叉', 'correlate', 'relationship'],
            'tester': ['tester', '测试人员', '测试员', '发现人', '谁发现', '谁报', '谁提', '提交人', '报告人', 'reporter', 'found by', 'owner'],
            'wordcloud': ['词云', 'wordcloud', '关键词', '高频词', '热词'],
            'throughput': ['inflow', 'outflow', '收敛', '吞吐', '净积压', 'net accumulation'],
            'longrunner': ['long runner', 'longrunner', '长周期', '处理周期', '阶段耗时', 'phase duration']
            , 'sql': ['sql', 'sqlite', '数据库', 'db']
        }

    def analyze_intent(self, question: str) -> List[str]:
        """分析问题意图"""
        question_lower = question.lower()
        detected_intents = []

        for intent, patterns in self.intent_patterns.items():
            if intent == "aida" and ("feature team" in question_lower or "feature_team" in question_lower or "feature-team" in question_lower):
                patterns = [p for p in patterns if p != "feature"]
            if any(pattern in question_lower for pattern in patterns):
                detected_intents.append(intent)

        # 补充规则：显式“测试人员 + 情况”问法通常是测试运行视角
        if re.search(r"([a-z]{2,}\s+[a-z]{2,}|[\u4e00-\u9fff]{2,8})\s*(是|作为)?\s*测试(人员|员)", question_lower):
            if 'tester' not in detected_intents:
                detected_intents.append('tester')
            if 'test' not in detected_intents:
                detected_intents.append('test')
            if 'execution' not in detected_intents:
                detected_intents.append('execution')

        # 补充规则：“功能/模块 + 失败”优先走测试分析
        if any(k in question_lower for k in ['功能', '模块', 'service', 'services']) and any(k in question_lower for k in ['失败', 'fail', 'failed', '挂']):
            if 'test' not in detected_intents:
                detected_intents.append('test')
            if 'execution' not in detected_intents:
                detected_intents.append('execution')
            if 'aida' not in detected_intents:
                detected_intents.append('aida')

        # 补充规则：AIDA + 容易出错/问题类型 归入测试失败模式分析（避免退化到摘要）。
        if (
            'aida' in detected_intents
            and ('case' in detected_intents or any(k in question_lower for k in ['容易出错', '出错', '失败最多', '问题', '问题类型', '什么样']))
        ):
            if 'test' not in detected_intents:
                detected_intents.append('test')
            if 'execution' not in detected_intents:
                detected_intents.append('execution')
            if 'distribution' not in detected_intents:
                detected_intents.append('distribution')

        return detected_intents if detected_intents else ['general']

    def analyze_intent_with_confidence(self, question: str) -> Tuple[List[str], float, Optional[str]]:
        """Analyze intent confidence and return optional clarification when confidence is low."""
        intents = self.analyze_intent(question)
        q = str(question or "").strip()
        ql = q.lower()

        if not intents or intents == ['general']:
            clarification = (
                "我不太确定你想分析哪个方向。你可以直接说：\n"
                "1. 缺陷风险\n"
                "2. 测试通过率\n"
                "3. 项目对比\n"
                "4. 趋势分析"
            )
            return intents or ['general'], 0.3, clarification

        if len(intents) >= 4:
            clarification = f"你的问题覆盖多个方向（{', '.join(intents[:3])} 等），优先想看哪一个？"
            return intents, 0.55, clarification

        # 已经识别出明确单一意图时，不做早期拦截。
        if len(intents) <= 2 and intents != ['general']:
            return intents, 0.9, None

        vague_keywords = ['怎么样', '如何', '怎样', '情况', '分析', '统计', 'how', 'what']
        has_vague = any(k in ql for k in vague_keywords)
        if len(q) < 15 and has_vague:
            clarification = (
                "这个问题有点宽泛，可以补充下范围：\n"
                "- 关注项目（如 IDCevo / MGU）\n"
                "- 时间范围（本周 / 本月 / 本季度）"
            )
            return intents, 0.62, clarification

        return intents, 0.88, None

    @staticmethod
    def _tokenize_text(text: str) -> List[str]:
        if not text:
            return []
        toks = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", str(text).lower())
        out = []
        for t in toks:
            s = str(t).strip()
            if not s or len(s) <= 1:
                continue
            out.append(s)
        return out

    @staticmethod
    @lru_cache(maxsize=16)
    def _semantic_core_dimensions(dataset: str) -> List[Dict[str, Any]]:
        try:
            from semantic_catalog.runtime import SemanticCatalog

            catalog = SemanticCatalog().load_catalog() or {}
            for ds in (catalog.get("datasets") or []):
                aliases = [str(a).strip().lower() for a in (ds.get("aliases") or [])]
                if str(ds.get("id", "")).strip().lower() == str(dataset).strip().lower() or str(dataset).strip().lower() in aliases:
                    dims = ds.get("core_dimensions") or []
                    return [d for d in dims if isinstance(d, dict)]
        except Exception:
            return []
        return []

    def _detect_dimensions(self, question: str, dataset: str, dataframe_columns: List[str], top_k: int = 2) -> List[str]:
        ql = (question or "").lower()
        q_tokens = set(self._tokenize_text(ql))
        cols = [str(c) for c in (dataframe_columns or [])]
        col_set = set(cols)

        scored = []
        for dim in self._semantic_core_dimensions(str(dataset or "").strip().lower()):
            name = str(dim.get("name", "")).strip()
            if not name:
                continue
            aliases = [str(a).strip() for a in (dim.get("aliases") or []) if a is not None and str(a).strip()]
            meaning = str(dim.get("meaning", "")).strip()
            dim_text = " ".join([name, " ".join(aliases), meaning]).strip()
            d_tokens = set(self._tokenize_text(dim_text))
            score = 0
            overlap = len(q_tokens & d_tokens)
            score += overlap * 3
            if name.lower() in ql:
                score += 4
            for a in aliases[:8]:
                al = a.lower()
                if al and al in ql:
                    score += 6
            if name in col_set:
                score += 2
            scored.append((score, name))

        scored = [(s, n) for s, n in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [n for _, n in scored[: max(0, int(top_k))]]
        if picked:
            return picked

        col_scored = []
        for c in cols:
            ct = set(self._tokenize_text(c))
            s = len(q_tokens & ct)
            if s <= 0:
                continue
            col_scored.append((s, c))
        col_scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in col_scored[: max(0, int(top_k))]]

    def _wants_full_data(self, question: str) -> bool:
        q = (question or "").lower()
        return any(k in q for k in [
            "全量", "完整", "不要抽样", "不要采样", "不采样", "不抽样",
            "不要摘要", "不摘要", "不限制", "准确", "全面", "牺牲速度",
            "full", "all", "exact", "accurate", "no sampling"
        ])

    def extract_entities(self, question: str, data: pd.DataFrame, dataset: str = "defects") -> Dict[str, Any]:
        """提取问题中的实体（项目名、时间范围等）"""
        entities: Dict[str, Any] = {}
        q_raw = (question or "").strip()
        q_lower = q_raw.lower()

        def _norm_text(v: Any) -> str:
            s = str(v or "").strip().lower()
            s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _fuzzy_match_values(values: List[str], phrase: str, max_hits: int = 5) -> List[str]:
            p = _norm_text(phrase)
            if not p:
                return []
            p_tokens = [t for t in p.split(" ") if len(t) >= 2]
            scored: List[Tuple[int, str]] = []
            for v in values:
                vn = _norm_text(v)
                if not vn:
                    continue
                score = 0
                if vn == p:
                    score += 10
                if p in vn:
                    score += 8
                if vn in p and len(vn) >= 3:
                    score += 4
                for t in p_tokens:
                    if t in vn:
                        score += 2
                if score > 0:
                    scored.append((score, v))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [v for _, v in scored[:max(1, int(max_hits))]]

        try:
            dims = self._detect_dimensions(question, dataset=dataset, dataframe_columns=list(data.columns), top_k=2)
            if dims:
                entities["dimensions"] = dims
                entities["dimension"] = dims[0]
        except Exception:
            pass

        # 提取项目名
        project_col = None
        if 'tproject' in data.columns:
            project_col = 'tproject'
        elif 'project' in data.columns:
            project_col = 'project'
        if project_col:
            projects = (
                data[project_col]
                .dropna()
                .astype(str)
                .map(lambda s: s.strip())
            )
            projects = [p for p in projects.unique().tolist() if p and p.lower() not in {"nan", "none"}]
            q = (question or "").lower()
            mentioned_projects = []
            for p in projects:
                pl = str(p).strip().lower()
                if not pl:
                    continue
                pat = r"(?<![a-z0-9_])" + re.escape(pl) + r"(?![a-z0-9_])"
                if re.search(pat, q):
                    mentioned_projects.append(p)
            if mentioned_projects:
                try:
                    max_len = max(len(str(x)) for x in mentioned_projects)
                    mentioned_projects = [x for x in mentioned_projects if len(str(x)) == max_len]
                except Exception:
                    pass
                entities['projects'] = mentioned_projects

        def _extract_from_column(col: str, key: str, max_unique: int = 500) -> None:
            if col not in data.columns:
                return
            series = (
                data[col]
                .dropna()
                .astype(str)
                .map(lambda s: s.strip())
            )
            values = [v for v in series.unique().tolist() if v and v.lower() not in {"nan", "none"}]
            if len(values) > max_unique:
                values = values[:max_unique]
            q = q_lower
            qn = _norm_text(q)
            mentioned = []
            for v in values:
                vn = _norm_text(v)
                if not vn:
                    continue
                if (vn in qn) or (qn in vn and len(qn) >= 3):
                    mentioned.append(v)
            if mentioned:
                entities[key] = mentioned

        _extract_from_column("aida_english", "aidas")
        _extract_from_column("aida", "aidas")
        _extract_from_column("pu", "pus")
        _extract_from_column("fv", "fvs")
        _extract_from_column("domain", "domains")
        _extract_from_column("status_phase", "statuses")
        _extract_from_column("status", "statuses")
        _extract_from_column("tester", "testers")
        _extract_from_column("found_by", "testers")
        _extract_from_column("reporter", "testers")
        _extract_from_column("author_name", "testers")
        _extract_from_column("severity_group", "severities")
        _extract_from_column("severity", "severities")

        # 显式语法解析："fv是xxx" / "feature team是xxx" / "功能是xxx"
        def _get_col_values(col: str, max_unique: int = 1200) -> List[str]:
            if col not in data.columns:
                return []
            s = data[col].dropna().astype(str).map(lambda x: x.strip())
            vals = [v for v in s.unique().tolist() if v and v.lower() not in {"nan", "none"}]
            if len(vals) > max_unique:
                vals = vals[:max_unique]
            return vals

        m_fv = re.search(r"(?:^|\s|[，,。；;])(?:fv|feature\s*team)\s*(?:是|为|=)?\s*([a-z0-9_\- /\u4e00-\u9fff]+)", q_lower)
        if m_fv:
            raw_val = re.split(r"的|测试|情况|如何|怎么样|\?|？", m_fv.group(1), maxsplit=1)[0].strip()
            if raw_val:
                fv_vals = _get_col_values("fv")
                matched = _fuzzy_match_values(fv_vals, raw_val)
                if matched:
                    entities["fvs"] = list(dict.fromkeys((entities.get("fvs") or []) + matched))

        m_aida = re.search(r"(?:功能|模块|services?|call\s*services)\s*(?:是|为|=)?\s*([a-z0-9_\- /\u4e00-\u9fff]+)", q_lower)
        if m_aida:
            raw_val = re.split(r"的|测试|情况|如何|怎么样|\?|？", m_aida.group(1), maxsplit=1)[0].strip()
            if raw_val:
                aida_vals = _get_col_values("aida_english") + _get_col_values("aida") + _get_col_values("top_aida")
                matched = _fuzzy_match_values(list(dict.fromkeys(aida_vals)), raw_val)
                if matched:
                    entities["aidas"] = list(dict.fromkeys((entities.get("aidas") or []) + matched))

        # 提取人名作为 tester 兜底，避免唯一值截断导致命中失败
        q = q_raw
        ql = q.lower()
        candidate_people = []
        if any(k in ql for k in ["测试人员", "测试员", "tester", "情况", "如何", "怎么样", "who"]):
            m_en = re.search(r"\b([a-z]{2,}\s+[a-z]{2,})\b", ql)
            if m_en:
                candidate_people.append(m_en.group(1).strip())
            m_cn = re.search(r"([\u4e00-\u9fff]{2,8})\s*(是|作为)?\s*测试(人员|员)", q)
            if m_cn:
                candidate_people.append(m_cn.group(1).strip())
        if candidate_people:
            existing = entities.get("testers") or []
            entities["testers"] = list(dict.fromkeys(existing + candidate_people))

        ql = (question or "").lower()
        matrix_hits = set()
        matrix_hits.update([m.upper() for m in re.findall(r"\b([12][a-e])\b", ql)])
        matrix_hits.update([m.upper() for m in re.findall(r"matrix[-_ ]?([12][a-e])", ql)])
        if matrix_hits:
            entities["matrices"] = sorted(matrix_hits)

        # 提取时间范围
        time_patterns = {
            'week': ['本周', '这周', 'week'],
            'month': ['本月', '这月', 'month', '最近一个月', '近一个月', '过去一个月', '最近30天', '近30天', '30天'],
            'quarter': ['本季度', '季度', 'quarter'],
            'year': ['今年', '本年', 'year'],
            'all': ['全量', '全部', '所有', '全历史', '不限制时间', 'all time']
        }

        for time_unit, patterns in time_patterns.items():
            if any(pattern in question.lower() for pattern in patterns):
                entities['time_range'] = time_unit
                break

        # 提取数字
        numbers = re.findall(r'\d+', question)
        if numbers:
            entities['numbers'] = [int(n) for n in numbers]

        return entities

    def prepare_context(self, question: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Tuple[Dict[str, Any], Union[pd.DataFrame, Dict[str, pd.DataFrame]]]:
        intents = self.analyze_intent(question)
        try:
            context_max = int(os.getenv("AGENT_CONTEXT_MAX_ROWS_DEFAULT", "50000"))
        except Exception:
            context_max = 50000
        try:
            tool_max = int(os.getenv("AGENT_TOOL_MAX_ROWS_DEFAULT", "500000"))
        except Exception:
            tool_max = 500000
        full_data_default = os.getenv("AGENT_FULL_DATA_BY_DEFAULT", "0") == "1"
        full_context_default = full_data_default or (os.getenv("AGENT_FULL_CONTEXT_BY_DEFAULT", "0") == "1")
        full_tools_default = full_data_default or (os.getenv("AGENT_FULL_TOOLS_BY_DEFAULT", "0") == "1")
        if full_context_default:
            context_max = 10**12
        if full_tools_default:
            tool_max = 10**12

        if isinstance(data, dict):
            datasets = {k: (v if isinstance(v, pd.DataFrame) else pd.DataFrame()) for k, v in data.items()}
            primary_dataset = self._choose_primary_dataset(question, intents, datasets)
            primary_df = self._normalize_dataset(datasets.get(primary_dataset, pd.DataFrame()), primary_dataset)
            entities = self.extract_entities(question, primary_df, dataset=primary_dataset) if not primary_df.empty else {}
            if entities.get("dimension"):
                dim = str(entities.get("dimension") or "").strip().lower()
                if dim == "aida_english" and "aida" not in intents:
                    intents.append("aida")
                if dim == "fv" and "fv" not in intents:
                    intents.append("fv")
                if dim == "domain" and "domain" not in intents:
                    intents.append("domain")
                if dim == "tester" and "tester" not in intents:
                    intents.append("tester")
                if dim == "project" and "project" not in intents:
                    intents.append("project")

            prepared = {}
            context_views = {}
            dataset_meta = {}
            for name, df in datasets.items():
                norm = self._normalize_dataset(df, name)
                filtered = self._filter_data(norm, intents, entities, dataset=name)
                tool_df, tool_limit_info = self._apply_tool_limit(question, entities, filtered, dataset=name, max_rows=tool_max)
                sampled, sampling_info = self._apply_sampling(question, entities, tool_df, dataset=name, max_rows=context_max)
                selected_columns = self._select_columns(intents, entities, sampled, dataset=name)
                context_df = sampled[selected_columns].copy() if selected_columns else sampled.copy()
                prepared[name] = tool_df
                context_views[name] = context_df
                dataset_meta[name] = {
                    'data_size': int(len(df)),
                    'filtered_size': int(len(filtered)),
                    'tool_size': int(len(tool_df)),
                    'context_size': int(len(context_df)),
                    'available_columns': df.columns.tolist() if isinstance(df, pd.DataFrame) else [],
                    'selected_columns': selected_columns,
                    'tool_limit': tool_limit_info,
                    'sampling': sampling_info
                }

            primary_context = context_views.get(primary_dataset, pd.DataFrame())
            context = {
                'intents': self._postprocess_intents(intents, datasets),
                'entities': entities,
                'primary_dataset': primary_dataset,
                'datasets': dataset_meta,
                'suggested_tools': self._suggest_tools(intents, entities),
                'data_summary': self._generate_data_summary(primary_context, intents, dataset=primary_dataset),
                'sample_rows': self._sample_rows(primary_context)
            }
            return context, prepared

        df = self._normalize_dataset(data, "defects")
        entities = self.extract_entities(question, df, dataset="defects") if not df.empty else {}
        if entities.get("dimension"):
            dim = str(entities.get("dimension") or "").strip().lower()
            if dim == "aida_english" and "aida" not in intents:
                intents.append("aida")
            if dim == "fv" and "fv" not in intents:
                intents.append("fv")
            if dim == "domain" and "domain" not in intents:
                intents.append("domain")
            if dim == "tester" and "tester" not in intents:
                intents.append("tester")
            if dim == "project" and "project" not in intents:
                intents.append("project")
        filtered_data = self._filter_data(df, intents, entities, dataset="defects")
        tool_df, tool_limit_info = self._apply_tool_limit(question, entities, filtered_data, dataset="defects", max_rows=tool_max)
        sampled, sampling_info = self._apply_sampling(question, entities, tool_df, dataset="defects", max_rows=context_max)
        selected_columns = self._select_columns(intents, entities, sampled, dataset="defects")
        context_data = sampled[selected_columns].copy() if selected_columns else sampled.copy()

        context = {
            'intents': intents,
            'entities': entities,
            'primary_dataset': 'defects',
            'datasets': {
                'defects': {
                    'data_size': int(len(df)),
                    'filtered_size': int(len(filtered_data)),
                    'tool_size': int(len(tool_df)),
                    'context_size': int(len(context_data)),
                    'available_columns': df.columns.tolist(),
                    'selected_columns': selected_columns,
                    'tool_limit': tool_limit_info,
                    'sampling': sampling_info
                }
            },
            'suggested_tools': self._suggest_tools(intents, entities),
            'data_summary': self._generate_data_summary(context_data, intents, dataset="defects"),
            'sample_rows': self._sample_rows(context_data)
        }

        return context, tool_df

    def _postprocess_intents(self, intents: List[str], datasets: Dict[str, pd.DataFrame]) -> List[str]:
        out = list(intents)
        if 'tests' in datasets and 'defects' in datasets:
            if 'test' in intents and any(i in intents for i in ['risk', 'trend', 'comparison', 'summary']):
                if 'cross' not in out:
                    out.append('cross')
        return out

    def _choose_primary_dataset(self, question: str, intents: List[str], datasets: Dict[str, pd.DataFrame]) -> str:
        q = question.lower()
        if ('tests' in datasets) and any(i in intents for i in ['test', 'execution', 'case']):
            if any(k in q for k in ['缺陷', 'defect', 'bug']) and ('test' not in intents):
                return 'defects' if 'defects' in datasets else 'tests'
            return 'tests'
        if ('tester' in intents) and ('defects' in datasets):
            return 'defects'
        if ('tests' in datasets) and any(k in q for k in ['测试', 'test', 'run', 'case', 'coverage']):
            if any(k in q for k in ['缺陷', 'defect', 'bug']):
                return 'defects' if 'defects' in datasets else 'tests'
            return 'tests'
        return 'defects' if 'defects' in datasets else next(iter(datasets.keys()), 'defects')

    def _normalize_dataset(self, df: pd.DataFrame, dataset: str) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        if isinstance(df, pd.DataFrame) and df.empty:
            out = df.copy()
            if dataset == "tests":
                if "run_status" not in out.columns and "status" in out.columns:
                    out["run_status"] = out["status"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else str(x))
            return out
        out = df
        if dataset == "tests":
            if "project" in out.columns and "tproject" not in out.columns:
                out = out.copy()
                out["tproject"] = out["project"]
            if "run_status" not in out.columns and "status" in out.columns:
                if out is df:
                    out = out.copy()
                out["run_status"] = out["status"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else str(x))
            if "finished_udf_dt" in out.columns and "tcreationtime" not in out.columns:
                if out is df:
                    out = out.copy()
                out["tcreationtime"] = out["finished_udf_dt"]
            if "tcreationtime" in out.columns:
                out["tcreationtime"] = pd.to_datetime(out["tcreationtime"], errors="coerce")
        else:
            if "project" not in out.columns and "ecu" in out.columns:
                out = out.copy()
                out["project"] = out["ecu"]
            if "project" in out.columns and "tproject" not in out.columns:
                out = out.copy()
                out["tproject"] = out["project"]
            if "tcreationtime" not in out.columns and "creation_time" in out.columns:
                out = out.copy()
                out["tcreationtime"] = out["creation_time"]
            if "tcreationtime" in out.columns:
                out["tcreationtime"] = pd.to_datetime(out["tcreationtime"], errors="coerce")
            if "severity_group" not in out.columns and "severity" in out.columns:
                if out is df:
                    out = out.copy()
                sev = out["severity"].astype(str).str.lower()
                out["severity_group"] = np.select(
                    [sev.str.contains("critical"), sev.str.contains("major"), sev.str.contains("minor")],
                    ["Critical", "Major", "Minor"],
                    default=out["severity"].astype(str)
                )
            if "severity_group" in out.columns:
                sev2 = out["severity_group"].astype(str).str.lower()
                mapped = np.select(
                    [sev2.str.contains("critical"), sev2.str.contains("major"), sev2.str.contains("minor")],
                    ["Critical", "Major", "Minor"],
                    default=out["severity_group"].astype(str)
                )
                if out is df:
                    out = out.copy()
                out["severity_group"] = mapped
            if "matrix_display" not in out.columns and "matrix" in out.columns:
                if out is df:
                    out = out.copy()
                out["matrix_display"] = out["matrix"].astype(str).str.replace("matrix-", "", regex=False).str.upper()
            if "topissue" not in out.columns:
                if out is df:
                    out = out.copy()
                if "is_topissue" in out.columns:
                    out["topissue"] = out["is_topissue"].apply(lambda v: "TopIssue" if bool(v) else "")
                elif "tags" in out.columns:
                    def _is_topissue(v):
                        if isinstance(v, list):
                            return any(str(x).lower() == "topissue" for x in v)
                        s = str(v)
                        return "topissue" in s.lower()
                    out["topissue"] = out["tags"].apply(lambda v: "TopIssue" if _is_topissue(v) else "")
                else:
                    out["topissue"] = out.get("topissue", "")
        return out

    def _select_columns(self, intents: List[str], entities: Dict[str, Any], data: pd.DataFrame, dataset: str = "defects") -> List[str]:
        columns = []
        if data is None or data.empty:
            return columns

        base = ['tproject', 'tcreationtime']
        for col in base:
            if col in data.columns:
                columns.append(col)

        if 'risk' in intents:
            for col in ['severity_group', 'topissue', 'matrix_display', 'category', 'status_phase']:
                if col in data.columns:
                    columns.append(col)

        if 'auto' in intents and dataset != "tests":
            for col in [
                'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time',
                'tester', 'aida_english', 'aida', 'pu', 'domain', 'classification',
                'matrix_display', 'matrix', 'topissue', 'is_topissue',
                'topissue_risk_score', 'risk_score', 'processing_cycle_days', 'process_days',
                'status_phase', 'status', 'is_critical_issue', 'is_complex_ticket', 'is_long_runner'
            ]:
                if col in data.columns:
                    columns.append(col)

        if 'matrix' in intents and dataset != "tests":
            for col in ['matrix_display', 'matrix', 'severity_group', 'classification', 'is_topissue', 'topissue']:
                if col in data.columns:
                    columns.append(col)

        if ('aida' in intents) and dataset != "tests":
            for col in ['aida_english', 'aida', 'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time', 'matrix_display', 'matrix']:
                if col in data.columns:
                    columns.append(col)

        if ('fv' in intents) and dataset != "tests":
            for col in ['fv', 'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time', 'aida_english', 'aida']:
                if col in data.columns:
                    columns.append(col)

        if ('domain' in intents) and dataset != "tests":
            for col in ['domain', 'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time', 'aida_english', 'aida', 'fv']:
                if col in data.columns:
                    columns.append(col)

        if 'tester' in intents and dataset != "tests":
            for col in ['tester', 'id', '_id', 'name', 'title', 'aida_english', 'aida', 'pu', 'domain', 'classification']:
                if col in data.columns:
                    columns.append(col)

        if 'trend' in intents:
            for col in ['tcreationtime', 'tproject', 'severity_group', 'category']:
                if col in data.columns:
                    columns.append(col)

        if 'comparison' in intents:
            for col in ['tproject', 'severity_group', 'topissue', 'matrix_display', 'category']:
                if col in data.columns:
                    columns.append(col)

        if 'test' in intents or dataset == "tests":
            for col in ['run_status', 'finished_udf_dt', 'finished_udf', 'test_id', 'test_name', 'tester', 'aida_count', 'top_aida', 'pu']:
                if col in data.columns:
                    columns.append(col)

        if not columns:
            columns = data.columns[:12].tolist()

        seen = set()
        deduped = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                deduped.append(col)
        return deduped

    def _sample_rows(self, data: pd.DataFrame, max_rows: int = 6) -> List[Dict[str, Any]]:
        if data is None or data.empty:
            return []
        sample = data.sample(n=min(max_rows, len(data)), random_state=42)
        return sample.fillna("").to_dict(orient='records')

    def _suggest_tools(self, intents: List[str], entities: Dict) -> List[str]:
        """根据意图和实体建议工具"""
        tools = []

        if 'dashboard' in intents or 'auto' in intents:
            tools.append('defect_explore_dashboard')

        if 'summary' in intents or 'auto' in intents:
            tools.append('defect_explore_kpis')

        if 'trend' in intents:
            tools.append('analyze_trend')

        if 'risk' in intents:
            tools.append('analyze_risk')

        if 'comparison' in intents or any(key in entities for key in ['projects']):
            tools.append('compare_items')

        if 'test' in intents:
            tools.append('analyze_test_run')

        if 'cross' in intents:
            tools.append('correlate_defects_tests')

        if 'tester' in intents:
            tools.append('analyze_tester_findings')

        if 'matrix' in intents and 'aida' in intents:
            tools.append('analyze_matrix_aida_hotspots')
        elif 'matrix' in intents:
            tools.append('analyze_matrix_distribution')

        if not tools:
            tools.append('statistical_summary')

        return tools

    def _filter_data(self, data: pd.DataFrame, intents: List[str], entities: Dict, dataset: str = "defects") -> pd.DataFrame:
        """根据意图和实体筛选数据"""
        filtered = data
        if filtered is None:
            return pd.DataFrame()
        if isinstance(filtered, pd.DataFrame) and filtered.empty:
            return filtered

        def _norm_text(v: Any) -> str:
            s = str(v or "").strip().lower()
            s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _fuzzy_filter_by_values(df: pd.DataFrame, col: str, targets: List[Any]) -> pd.DataFrame:
            if col not in df.columns:
                return df
            tnorm = [_norm_text(x) for x in (targets or []) if _norm_text(x)]
            if not tnorm:
                return df
            s_norm = df[col].astype(str).map(_norm_text)
            mask = pd.Series(False, index=df.index)
            for t in tnorm:
                if not t:
                    continue
                mask = mask | (s_norm == t)
                mask = mask | s_norm.str.contains(re.escape(t), na=False)
                if len(t) >= 3:
                    mask = mask | s_norm.map(lambda sv: bool(sv) and sv in t)
            out = df[mask]
            return out if not out.empty else df

        # 按项目筛选
        if 'projects' in entities:
            project_col = 'tproject' if 'tproject' in filtered.columns else 'project' if 'project' in filtered.columns else None
            if project_col:
                def _norm_project(v: Any) -> str:
                    s = str(v or "").strip()
                    if not s:
                        return ""
                    u = s.upper()
                    if u in {"IDCEVO", "IDCEVO25", "IDCEVO_25"}:
                        return "IDCEVO"
                    if u in {"IDC"}:
                        return "IDC"
                    if u in {"MGU", "MGU22", "MGU21", "MGU18"}:
                        return "MGU"
                    if u in {"APP"}:
                        return "APP"
                    if u in {"RSU"}:
                        return "RSU"
                    return u

                target = set([_norm_project(x) for x in (entities.get("projects") or []) if str(x or "").strip()])
                if target:
                    series = filtered[project_col].map(_norm_project)
                    filtered = filtered[series.isin(target)]

        if 'aidas' in entities:
            aida_col = "aida_english" if "aida_english" in filtered.columns else "aida" if "aida" in filtered.columns else "top_aida" if "top_aida" in filtered.columns else None
            if aida_col:
                filtered = _fuzzy_filter_by_values(filtered, aida_col, entities["aidas"])

        if 'pus' in entities and 'pu' in filtered.columns:
            filtered = filtered[filtered["pu"].astype(str).isin([str(x) for x in entities["pus"]])]

        if 'fvs' in entities and 'fv' in filtered.columns:
            filtered = _fuzzy_filter_by_values(filtered, "fv", entities["fvs"])

        if 'domains' in entities and 'domain' in filtered.columns:
            filtered = _fuzzy_filter_by_values(filtered, "domain", entities["domains"])

        if 'statuses' in entities:
            status_col = "status_phase" if "status_phase" in filtered.columns else "status" if "status" in filtered.columns else None
            if status_col:
                filtered = filtered[filtered[status_col].astype(str).isin([str(x) for x in entities["statuses"]])]

        if 'testers' in entities:
            candidates = [c for c in ["tester", "found_by", "reporter", "author_name"] if c in filtered.columns]
            tester_col = None
            if candidates:
                best = None
                best_cnt = -1
                for c in candidates:
                    s = filtered[c].astype(str).map(lambda x: str(x).strip())
                    s = s[s.notna() & (s != "") & (s.str.lower() != "nan")]
                    cnt = int(len(s))
                    if cnt > best_cnt:
                        best_cnt = cnt
                        best = c
                tester_col = best
            if tester_col:
                def _norm_person(v: Any) -> str:
                    s = str(v or "").strip().lower()
                    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
                    tokens = [t for t in s.split() if t and t not in {"id", "uid", "userid", "user"}]
                    s2 = "".join(tokens)
                    if s2.endswith("id") and len(s2) >= 5:
                        s2 = s2[:-2]
                    return s2

                entity_norm = []
                for x in (entities.get("testers") or []):
                    nx = _norm_person(x)
                    if nx:
                        entity_norm.append(nx)
                entity_set = set(entity_norm)
                if entity_set:
                    series = filtered[tester_col].astype(str).map(_norm_person)
                    filtered = filtered[series.isin(entity_set)]

        if 'matrices' in entities:
            matrix_col = "matrix_display" if "matrix_display" in filtered.columns else "matrix" if "matrix" in filtered.columns else None
            if matrix_col:
                norm = (
                    filtered[matrix_col]
                    .astype(str)
                    .str.strip()
                    .str.replace("MATRIX-", "", regex=False)
                    .str.replace("Matrix-", "", regex=False)
                    .str.replace("matrix-", "", regex=False)
                    .str.replace("matrix_", "", regex=False)
                    .str.upper()
                )
                filtered = filtered[norm.isin([str(x).upper() for x in entities["matrices"]])]

        if 'severities' in entities:
            sev_col = "severity_group" if "severity_group" in filtered.columns else "severity" if "severity" in filtered.columns else None
            if sev_col:
                filtered = filtered[filtered[sev_col].astype(str).isin([str(x) for x in entities["severities"]])]

        # 按时间筛选
        if 'time_range' in entities and 'tcreationtime' in filtered.columns:
            now = pd.Timestamp.now()
            tr = entities['time_range']
            if tr == 'week':
                start = now - timedelta(weeks=1)
                filtered = filtered[filtered['tcreationtime'] >= start]
            elif tr == 'month':
                start = now - timedelta(days=30)
                filtered = filtered[filtered['tcreationtime'] >= start]
            elif tr == 'quarter':
                start = now - timedelta(days=90)
                filtered = filtered[filtered['tcreationtime'] >= start]

        return filtered

    def _apply_sampling(self, question: str, entities: Dict[str, Any], data: pd.DataFrame, dataset: str, max_rows: int = 200_000) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        if data is None:
            return pd.DataFrame(), {"mode": "empty"}
        if isinstance(data, pd.DataFrame) and data.empty:
            return data, {"mode": "empty", "rows": 0}
        if self._wants_full_data(question):
            return data, {"mode": "none_forced", "rows": int(len(data))}
        q = question.lower()
        explicit_year = any(k in q for k in ["全年", "今年", "year", "年度", "2024", "2025"])
        explicit_time = 'time_range' in entities or explicit_year

        if len(data) <= max_rows:
            return data, {"mode": "none", "rows": int(len(data))}

        df = data
        mode = "downsample"
        detail = {}
        if "tcreationtime" in df.columns and not explicit_time:
            recent_days = 90 if dataset == "defects" else 120
            cutoff = pd.Timestamp.now() - timedelta(days=recent_days)
            before = len(df)
            df = df[df["tcreationtime"] >= cutoff]
            after = len(df)
            mode = "recent_window"
            detail = {"days": recent_days, "before": int(before), "after": int(after)}

        if len(df) > max_rows:
            before = len(df)
            df = df.sample(n=max_rows, random_state=42)
            mode = "sample"
            detail = {"before": int(before), "after": int(len(df))}

        return df, {"mode": mode, "rows": int(len(df)), **detail}

    def _apply_tool_limit(self, question: str, entities: Dict[str, Any], data: pd.DataFrame, dataset: str, max_rows: int = 2_000_000) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        if data is None:
            return pd.DataFrame(), {"mode": "empty"}
        if isinstance(data, pd.DataFrame) and data.empty:
            return data, {"mode": "empty", "rows": 0}
        if self._wants_full_data(question):
            return data, {"mode": "none_forced", "rows": int(len(data))}
        q = question.lower()
        explicit_year = any(k in q for k in ["全年", "今年", "year", "年度", "2024", "2025"])
        explicit_time = 'time_range' in entities or explicit_year

        df = data
        mode = "none"
        detail: Dict[str, Any] = {"rows": int(len(df))}

        if len(df) > max_rows and "tcreationtime" in df.columns and not explicit_time:
            recent_days = 365 if dataset == "defects" else 365
            cutoff = pd.Timestamp.now() - timedelta(days=recent_days)
            before = len(df)
            df = df[df["tcreationtime"] >= cutoff]
            mode = "recent_window"
            detail = {"days": recent_days, "before": int(before), "after": int(len(df))}

        if len(df) > max_rows:
            before = len(df)
            df = df.sample(n=max_rows, random_state=42)
            mode = "sample_for_tools"
            detail = {"before": int(before), "after": int(len(df))}

        return df, {"mode": mode, **detail}

    def _generate_data_summary(self, data: pd.DataFrame, intents: List[str], dataset: str = "defects") -> str:
        """生成数据摘要"""
        summary_parts = []

        summary_parts.append(f"数据集包含 {len(data)} 条记录")

        # 根据意图添加特定信息
        if 'risk' in intents:
            if 'severity_group' in data.columns:
                severity_dist = data['severity_group'].value_counts().to_dict()
                summary_parts.append(f"严重性分布: {severity_dist}")

        if 'project' in intents or 'comparison' in intents:
            if 'tproject' in data.columns:
                top_projects = data['tproject'].value_counts().head(5).to_dict()
                summary_parts.append(f"Top 5 项目: {top_projects}")

        if dataset == "tests" or 'test' in intents:
            if 'run_status' in data.columns:
                status_top = data['run_status'].astype(str).value_counts().head(6).to_dict()
                summary_parts.append(f"测试状态Top: {status_top}")

        return "\n".join(summary_parts)


# ============================================================================
# 3. 对话记忆系统
# ============================================================================

class _LegacyConversationMemory:
    """对话记忆系统 - 管理短期和长期记忆"""

    def __init__(self, max_short_term: int = 10, max_long_term: int = 100, memory_file: Optional[str] = None, autosave: bool = False):
        self.max_short_term = max_short_term
        self.max_long_term = max_long_term

        self.short_term = []
        self.long_term = []
        self.user_preferences = {}
        self.memory_file = memory_file
        self.autosave = autosave

        if self.memory_file:
            self._load()

    def add_fact(self, content: str, importance: float = 0.95, tags: Optional[List[str]] = None, entities: Optional[Dict[str, Any]] = None):
        text = (content or "").strip()
        if not text:
            return
        self.long_term.append({
            'kind': 'fact',
            'content': text[:600],
            'timestamp': datetime.now().isoformat(),
            'importance': float(max(0.0, min(1.0, importance))),
            'tags': list(tags or []),
            'entities': entities or {}
        })
        self._trim_long_term()
        if self.autosave:
            self.save()

    def forget(self, needle: str) -> int:
        key = (needle or "").strip().lower()
        if not key:
            return 0
        before = len(self.long_term)
        kept = []
        for m in self.long_term:
            c = str((m or {}).get('content') or '').lower()
            if key and key in c:
                continue
            kept.append(m)
        self.long_term = kept
        removed = before - len(self.long_term)
        if removed and self.autosave:
            self.save()
        return removed

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """添加消息到短期记忆"""
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

        self.short_term.append(message)

        # 限制短期记忆大小
        if len(self.short_term) > self.max_short_term:
            # 将旧消息总结后存入长期记忆
            self._summarize_and_archive()
        if self.autosave:
            self.save()

    def _trim_long_term(self):
        now = datetime.now()
        trimmed = []
        for m in self.long_term:
            try:
                ts = str((m or {}).get('timestamp') or '')
                dt = datetime.fromisoformat(ts) if ts else None
            except Exception:
                dt = None
            importance = float((m or {}).get('importance') or 0.5)
            if dt:
                age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
                importance = max(0.05, min(1.0, importance * (0.985 ** age_days)))
            mm = dict(m or {})
            mm['importance'] = importance
            trimmed.append(mm)
        trimmed.sort(key=lambda x: float(x.get('importance') or 0.0), reverse=True)
        self.long_term = trimmed[:self.max_long_term]

    def _summarize_and_archive(self):
        if len(self.short_term) <= self.max_short_term:
            return

        archived = self.short_term[:len(self.short_term) - self.max_short_term]
        self.short_term = self.short_term[-self.max_short_term:]

        summary = self._summarize_messages(archived)
        if summary:
            self.long_term.append({
                'kind': 'summary',
                'content': summary,
                'timestamp': datetime.now().isoformat(),
                'importance': 0.7,
                'tags': self._extract_tags(summary),
                'entities': self._extract_entities(summary),
            })

        for msg in archived:
            if msg['role'] == 'assistant' and len(msg['content']) > 80:
                importance = self._calculate_importance(msg)
                if importance >= 0.7:
                    self.long_term.append({
                        'kind': 'insight',
                        'content': msg['content'][:400],
                        'timestamp': msg['timestamp'],
                        'importance': importance,
                        'tags': self._extract_tags(msg['content']),
                        'entities': self._extract_entities(msg['content']),
                    })

        self._trim_long_term()

    def _calculate_importance(self, message: Dict) -> float:
        """计算消息重要性"""
        importance = 0.5

        content = message['content'].lower()

        # 包含关键词的消息更重要
        important_keywords = ['风险', '异常', '建议', 'improvement', '异常', 'critical']
        if any(keyword in content for keyword in important_keywords):
            importance += 0.3

        # 较长的消息可能包含更多信息
        if len(message['content']) > 100:
            importance += 0.2

        return min(importance, 1.0)

    def _extract_tags(self, text: str) -> List[str]:
        s = (text or "").lower()
        tags = []
        for t in ["sql", "sqlite", "口径", "定义", "字段", "风险", "建议", "重复", "已知问题", "测试", "缺陷", "project", "pu", "fv"]:
            if t in s:
                tags.append(t)
        return tags[:8]

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        s = (text or "").strip()
        low = s.lower()
        entities: Dict[str, Any] = {}
        projects = []
        for p in ["idcevo", "idevo", "app"]:
            if p in low:
                projects.append(p)
        if projects:
            entities["projects"] = sorted(list(set(projects)))
        m = re.findall(r"\bpu\s*[:：]?\s*([a-z0-9._-]{2,})\b", low, flags=re.IGNORECASE)
        if m:
            entities["pu"] = sorted(list(set([x.strip() for x in m if x and x.strip()])))[:5]
        nums = re.findall(r"\b\d{2,}\b", low)
        if nums:
            entities["numbers"] = nums[:6]
        return entities

    def get_relevant_history(self, query: str, top_k: int = 3) -> List[Dict]:
        """获取相关历史记录（简单实现：基于关键词匹配）"""
        query_lower = (query or "").lower()
        tokens = [t.strip() for t in re.split(r"[\s,，。；;]+", query_lower) if t and len(t.strip()) >= 2]
        tokens = tokens[:12]

        def _score(text: str) -> int:
            s = (text or "").lower()
            return sum(1 for t in tokens if t in s)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for msg in (self.short_term or []):
            c = msg.get('content') or ''
            hit = _score(c)
            if hit <= 0:
                continue
            scored.append((1000.0 + float(hit), msg))

        for memory in (self.long_term or []):
            c = memory.get('content', '') or ''
            hit = _score(c)
            if hit <= 0:
                continue
            base = float(memory.get('importance') or 0.5) * 10.0
            scored.append((base + float(hit), {
                'role': 'assistant',
                'content': c,
                'timestamp': memory.get('timestamp'),
                'from_memory': True,
                'kind': memory.get('kind'),
                'tags': memory.get('tags') or [],
                'entities': memory.get('entities') or {}
            }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[: max(1, int(top_k))]]

    def save_preference(self, key: str, value: Any):
        """保存用户偏好"""
        self.user_preferences[key] = value
        self.user_preferences['updated_at'] = datetime.now().isoformat()
        if self.autosave:
            self.save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self.user_preferences.get(key, default)

    def get_conversation_context(self) -> str:
        """获取对话上下文摘要"""
        context_parts = []

        if self.short_term:
            context_parts.append(f"当前对话包含 {len(self.short_term)} 条消息")

        if self.user_preferences:
            context_parts.append(f"用户偏好: {list(self.user_preferences.keys())}")

        return "\n".join(context_parts)

    def build_prompt_context(self, query: str, max_chars: int = 4000) -> str:
        parts = []
        if self.user_preferences:
            pref_items = {k: v for k, v in self.user_preferences.items() if k != 'updated_at'}
            if pref_items:
                parts.append(f"用户偏好: {pref_items}")

        recent = self.short_term[-self.max_short_term:]
        if recent:
            parts.append("最近对话：")
            for msg in recent:
                role = "用户" if msg.get('role') == 'user' else "助手"
                content = (msg.get('content') or '').strip()
                if content:
                    parts.append(f"{role}: {content}")

        memories = self.get_relevant_history(query, top_k=5)
        if memories:
            parts.append("相关记忆：")
            for m in memories:
                parts.append(f"- {m.get('content', '')}")

        text = "\n".join(parts)
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _summarize_messages(self, messages: List[Dict]) -> str:
        if not messages:
            return ""
        user_msgs = [m.get('content', '').strip() for m in messages if m.get('role') == 'user' and m.get('content')]
        assistant_msgs = [m.get('content', '').strip() for m in messages if m.get('role') == 'assistant' and m.get('content')]

        highlights = []
        for text in assistant_msgs[-3:]:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith(('-', '•')):
                    highlights.append(line.lstrip('-• ').strip())
                elif re.match(r'^\d+[\.\)]\s+', line):
                    highlights.append(re.sub(r'^\d+[\.\)]\s+', '', line))
        highlights = [h for h in highlights if 6 <= len(h) <= 120]
        highlights = highlights[:6]

        last_question = user_msgs[-1] if user_msgs else ""
        parts = []
        if last_question:
            parts.append(f"归档对话主题: {last_question[:120]}")
        if highlights:
            parts.append("要点: " + "；".join(highlights))
        if not parts:
            compact = " ".join((user_msgs + assistant_msgs)[-6:])
            return compact[:400]
        return "\n".join(parts)[:600]

    def _load(self):
        try:
            if not self.memory_file or not os.path.exists(self.memory_file):
                return
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            self.long_term = payload.get('long_term', []) or []
            self.user_preferences = payload.get('user_preferences', {}) or {}
        except Exception as e:
            logger.warning(f"加载记忆文件失败: {e}")

    def save(self):
        if not self.memory_file:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.memory_file)), exist_ok=True)
            payload = {
                'long_term': self.long_term[-self.max_long_term:],
                'user_preferences': self.user_preferences
            }
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存记忆文件失败: {e}")


# ============================================================================
# 4. 知识库系统（RAG）
# ============================================================================

class KnowledgeBase:
    """知识库系统 - 提供领域知识"""

    def __init__(self, knowledge_file: str = None):
        self.knowledge = {}
        self._load_default_knowledge()

        if knowledge_file and os.path.exists(knowledge_file):
            self._load_from_file(knowledge_file)

    def _load_default_knowledge(self):
        """加载默认领域知识"""
        self.knowledge = {
            'defect_matrix': {
                '1A': '最高优先级 - 新发现且严重性高',
                '1B': '高优先级 - 重复发现且严重性高',
                '1C': '中高优先级 - 新发现且严重性中',
                '1D': '中高优先级 - 重复发现且严重性中',
                '1E': '中等优先级 - 新发现且严重性低',
                '2A': '中低优先级 - 特定条件下发现',
                '2B': '中低优先级 - 重复发现且严重性低',
                '2C': '低优先级 - 边缘情况',
                '2D': '低优先级 - 低影响',
                '2E': '极低优先级 - 微小影响'
            },
            'severity_levels': {
                'Critical': '可能导致系统崩溃、安全漏洞或数据丢失',
                'Major': '影响主要功能但系统仍可运行',
                'Minor': '影响次要功能或用户体验'
            },
            'risk_assessment': {
                'high': '风险评分 > 70，需要立即处理',
                'medium': '风险评分 40-70，需要计划处理',
                'low': '风险评分 < 40，可以延后处理'
            },
            'improvement_suggestions': {
                'reduction_trend': '缺陷数量呈下降趋势，说明质量改进措施有效',
                'increasing_trend': '缺陷数量呈上升趋势，建议：\n1. 加强代码审查\n2. 增加测试覆盖率\n3. 分析根本原因',
                'high_topissue': 'TopIssue 比例高，建议：\n1. 优先修复高影响缺陷\n2. 建立缺陷预防机制\n3. 加强回归测试'
            }
        }

    def _load_from_file(self, file_path: str):
        """从文件加载知识"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.knowledge.update(json.load(f))
            logger.info(f"已从文件加载知识库: {file_path}")
        except Exception as e:
            logger.warning(f"加载知识库文件失败: {e}")

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        """检索相关知识（简单实现：基于关键词匹配）"""
        query_lower = query.lower()
        retrieved = []

        # 简单的关键词匹配
        for category, items in self.knowledge.items():
            if any(keyword in query_lower for keyword in category.split('_')):
                for key, value in items.items():
                    retrieved.append({
                        'category': category,
                        'key': key,
                        'value': value
                    })

        return retrieved[:top_k]

    def get_knowledge_context(self, query: str) -> str:
        """获取知识的上下文描述"""
        relevant = self.retrieve(query)

        if not relevant:
            return ""

        context_parts = ["相关知识："]
        for item in relevant:
            context_parts.append(f"- {item['key']}: {item['value']}")

        return "\n".join(context_parts)


# ============================================================================
# 5. 任务规划器
# ============================================================================

class _LegacyTaskPlanner:
    """任务规划器 - 分解复杂任务"""

    def __init__(
        self,
        tool_executor: _LegacyToolExecutor,
        llm: Any = None,
        tool_selector: Optional[Any] = None,
    ):
        self.tool_executor = tool_executor
        self.tool_selector = tool_selector

    def _map_selector_tool(self, selector_tool: str, primary_dataset: str, intents: List[str]) -> Optional[str]:
        """Map SmartToolSelector tool names to ToolExecutor tool names."""
        name = str(selector_tool or "").strip()
        if not name:
            return None

        is_test_view = (primary_dataset == "tests") or ("test" in (intents or []))
        mapping = {
            "time_series_counts": "analyze_test_run" if is_test_view else "analyze_trend",
            "top_counts": "analyze_test_run" if is_test_view else "analyze_trend",
            "stacked_top_counts": "analyze_test_run" if is_test_view else "analyze_trend",
            "nunique_by": "analyze_test_run" if is_test_view else "analyze_trend",
            "severity_rate_by": "analyze_test_run" if is_test_view else "analyze_risk",
            "pick_risk_score_column": "analyze_test_run" if is_test_view else "analyze_risk",
            "defect_quality_stats": "analyze_test_run" if is_test_view else "analyze_risk",
            "compute_defect_explore_kpis": "defect_explore_kpis",
            "inflow_outflow_summary": "defect_explore_dashboard",
            "longrunner_phase_statistics": "analyze_longrunner_hotlist",
            "word_frequencies": "defect_explore_dashboard",
            "defect_wordcloud_source": "defect_explore_dashboard",
            "analyze_test_run": "analyze_test_run",
            "groupby_aggregate": "groupby_aggregate",
        }
        return mapping.get(name)

    def _apply_smart_tool_selector(self, query: str, context: Dict[str, Any], steps: List[Dict]) -> List[Dict]:
        """Re-rank planned steps using SmartToolSelector recommendations."""
        if not self.tool_selector or not steps:
            return steps

        try:
            primary_dataset = str((context or {}).get("primary_dataset") or "defects")
            datasets_meta = (context or {}).get("datasets") or {}
            primary_meta = datasets_meta.get(primary_dataset) if isinstance(datasets_meta, dict) else {}

            available_columns: List[str] = []
            if isinstance(primary_meta, dict):
                available_columns = list(primary_meta.get("available_columns") or [])
            if not available_columns and isinstance(datasets_meta, dict):
                for meta in datasets_meta.values():
                    if isinstance(meta, dict) and meta.get("available_columns"):
                        available_columns = list(meta.get("available_columns") or [])
                        break

            data_size = 0
            if isinstance(primary_meta, dict):
                for key in ["tool_size", "filtered_size", "data_size", "context_size"]:
                    try:
                        value = int(primary_meta.get(key) or 0)
                    except Exception:
                        value = 0
                    if value > 0:
                        data_size = value
                        break

            intents = [str(x) for x in ((context or {}).get("intents") or []) if str(x).strip()]
            recommendations = self.tool_selector.select_tools(
                question=query,
                intents=intents,
                data_context={"data_size": int(data_size)},
                available_columns=available_columns,
                max_tools=5,
            )

            mapped_priority: List[str] = []
            mapped_details: List[Dict[str, Any]] = []
            for rec in recommendations:
                selector_tool = str(getattr(rec, "tool_name", "") or "").strip()
                if not selector_tool:
                    continue
                exec_tool = self._map_selector_tool(selector_tool, primary_dataset, intents)
                if not exec_tool:
                    continue
                mapped_details.append(
                    {
                        "selector_tool": selector_tool,
                        "executor_tool": exec_tool,
                        "confidence": float(getattr(rec, "confidence", 0.0) or 0.0),
                        "reason": str(getattr(rec, "reason", "") or ""),
                    }
                )
                if exec_tool not in mapped_priority:
                    mapped_priority.append(exec_tool)

            if not mapped_priority:
                if isinstance(context, dict):
                    context["smart_tool_selector"] = {
                        "enabled": True,
                        "applied": False,
                        "reason": "no_mapped_recommendation",
                        "recommendations": mapped_details,
                    }
                return steps

            priority_index = {tool_name: idx for idx, tool_name in enumerate(mapped_priority)}
            reordered = sorted(
                steps,
                key=lambda s: (
                    priority_index.get(str((s or {}).get("tool") or "").strip(), 999),
                    int((s or {}).get("step") or 0),
                ),
            )

            normalized_steps: List[Dict[str, Any]] = []
            for idx, step in enumerate(reordered, start=1):
                s = dict(step or {})
                s["step"] = idx
                normalized_steps.append(s)

            if isinstance(context, dict):
                context["smart_tool_selector"] = {
                    "enabled": True,
                    "applied": True,
                    "mapped_priority": mapped_priority,
                    "recommendations": mapped_details,
                }
            return normalized_steps
        except Exception as e:
            logger.warning(f"Smart tool selector application failed: {e}")
            if isinstance(context, dict):
                context["smart_tool_selector"] = {
                    "enabled": bool(self.tool_selector),
                    "applied": False,
                    "error": str(e),
                }
            return steps

    def _record_tool_selector_feedback(
        self,
        tool_name: str,
        result: Dict[str, Any],
        duration_ms: int,
        context: Optional[Dict[str, Any]],
        dataset_used: Optional[str],
    ) -> None:
        """Record execution feedback for selector learning."""
        if not self.tool_selector:
            return

        try:
            success = bool(isinstance(result, dict) and result.get("success") is True)
            error_message = ""
            if isinstance(result, dict) and not success:
                error_message = str(result.get("error") or "")

            datasets_meta = (context or {}).get("datasets") or {}
            data_size = 0
            meta = {}
            if isinstance(datasets_meta, dict):
                if dataset_used and isinstance(datasets_meta.get(dataset_used), dict):
                    meta = datasets_meta.get(dataset_used) or {}
                else:
                    primary_dataset = (context or {}).get("primary_dataset")
                    if isinstance(datasets_meta.get(primary_dataset), dict):
                        meta = datasets_meta.get(primary_dataset) or {}

            if isinstance(meta, dict):
                for key in ["tool_size", "filtered_size", "data_size", "context_size"]:
                    try:
                        value = int(meta.get(key) or 0)
                    except Exception:
                        value = 0
                    if value > 0:
                        data_size = value
                        break

            intents = [str(x) for x in ((context or {}).get("intents") or []) if str(x).strip()]
            self.tool_selector.record_execution(
                tool_name=str(tool_name or ""),
                success=success,
                execution_time=max(0.0, float(duration_ms) / 1000.0),
                result_quality=1.0 if success else 0.0,
                data_size=int(data_size),
                intents=intents,
                error_message=error_message,
            )
        except Exception as e:
            logger.debug(f"Smart tool selector feedback skipped: {e}")

    def plan(self, query: str, context: Dict) -> List[Dict]:
        """规划任务步骤"""
        steps = []

        intents = context.get('intents', [])
        entities = context.get('entities', {})
        primary_dataset = context.get('primary_dataset', 'defects')
        q = (query or "").lower()
        auto_strong = any(k in q for k in ["一键", "综合", "全盘", "全景", "全量", "深度分析", "deep dive", "不用一个问题一个问题"])

        wants_semantic_introspection = any(k in q for k in ["语义覆盖率", "字段对账", "字段对齐", "字段覆盖", "semantic coverage"])
        if wants_semantic_introspection and (
            hasattr(self.tool_executor, "tools") and ("semantic_coverage_report" in (self.tool_executor.tools or {}))
        ):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "semantic_coverage_report",
                    "description": "生成语义覆盖率与字段对账报告",
                    "params": {"dashboard": str(context.get("dashboard_type") or "defect_explore"), "max_columns": 20, "sample_rows": 0},
                }
            )
            return steps

        def _extract_top_n(default: int) -> int:
            m = re.search(r"(top|前)\s*(\d{1,3})", q)
            if m:
                try:
                    v = int(m.group(2))
                    return max(1, min(200, v))
                except Exception:
                    return default
            return default

        def _choose_case_col(available_cols: List[str]) -> Optional[str]:
            if not available_cols:
                return None
            cols = set(available_cols)
            for c in ["test_case", "testcase", "case", "case_id", "case_name", "test_name", "test_id", "name", "title"]:
                if c in cols:
                    return c
            for c in available_cols:
                lc = c.lower()
                if "case" in lc and ("id" in lc or "name" in lc):
                    return c
            for c in available_cols:
                lc = c.lower()
                if lc in {"test_id", "test_name"}:
                    return c
            return None

        wants_semantic = any(k in q for k in ["口径", "定义", "字段", "含义", "怎么计算", "如何计算", "calculation", "definition", "metric"])
        semantic_catalog_enabled = (os.getenv("AGENT_SEMANTIC_CATALOG_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}
        if (semantic_catalog_enabled and wants_semantic) and (
            hasattr(self.tool_executor, 'tools') and ('consult_semantic_catalog' in (self.tool_executor.tools or {}))
        ):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'consult_semantic_catalog',
                'description': '检索语义目录（口径/字段/误用风险）',
                'params': {'question': query, 'dashboard': str(context.get('dashboard_type') or '')}
            })

        wants_duplicate = any(k in q for k in ["重复", "相似", "类似", "已知问题", "known issue", "duplicate"])
        if wants_duplicate and ('defects' in (context.get('datasets') or {})) and (
            hasattr(self.tool_executor, 'tools') and ('search_similar_issues' in (self.tool_executor.tools or {}))
        ):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'search_similar_issues',
                'description': '检索相似缺陷/已知问题（重复提票检测）',
                'params': {'query': query, 'top_k': 8, 'dataset': 'defects', 'cache_key': 'defects'}
            })

        if ('tester' in intents) and primary_dataset != "tests" and (
            hasattr(self.tool_executor, "tools") and ("match_tester_tickets" in (self.tool_executor.tools or {}))
        ):
            person = None
            m = re.search(r"([\u4e00-\u9fff]{2,6})\s*(?:提|报|发现)", query)
            if m:
                person = m.group(1)
            if not person:
                m2 = re.match(r"^\s*([\u4e00-\u9fff]{2,6})", query)
                if m2:
                    person = m2.group(1)
            if person and any(k in q for k in ["多少", "分布", "aida"]):
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "match_tester_tickets",
                        "description": "匹配指定人员并输出提票分布",
                        "params": {"person": person, "dimension": "aida", "top_n": _extract_top_n(10), "sample_n": 10, "dataset": primary_dataset},
                    }
                )
                return steps

        if (('sql' in intents) or any(k in q for k in ['sql', 'sqlite', '数据库', 'db'])) and (
            hasattr(self.tool_executor, 'tools') and ('query_sqlite_with_fix' in (self.tool_executor.tools or {}))
        ):
            if hasattr(self.tool_executor, 'tools') and ('get_db_profile' in (self.tool_executor.tools or {})):
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'get_db_profile',
                    'description': '获取数据库画像（字段/高频值/空值率）以提升SQL生成准确率',
                    'params': {'top_n': 5, 'sample_columns': 20}
                })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'query_sqlite_with_fix',
                'description': '将自然语言问题转为SQLite只读查询并执行（失败自动纠错）',
                'params': {'question': query, 'limit': 200}
            })
            return steps

        wants_recent_weeks = any(k in q for k in ["最近", "近", "过去"]) and ("周" in q or "week" in q)
        wants_defect_test_joint = any(k in q for k in ["缺陷", "defect", "bug"]) and any(k in q for k in ["测试", "test", "执行", "run"])
        if wants_recent_weeks and wants_defect_test_joint and ('defects' in (context.get('datasets') or {})) and ('tests' in (context.get('datasets') or {})) and (
            hasattr(self.tool_executor, "tools") and ("analyze_project_recent_weeks" in (self.tool_executor.tools or {}))
        ):
            proj = None
            if isinstance(entities.get("projects"), list) and entities.get("projects"):
                proj = str(entities.get("projects")[0] or "").strip()
            if not proj:
                m = re.search(r"\\b(idcevo|idc|mgu|app|rsu)\\b", q)
                if m:
                    proj = m.group(1)
            if proj:
                n_weeks = 4
                for n in (entities.get("numbers") or []):
                    try:
                        if 1 <= int(n) <= 26:
                            n_weeks = int(n)
                            break
                    except Exception:
                        continue
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_project_recent_weeks",
                        "description": f"评估项目 {proj} 最近{n_weeks}周缺陷发现与测试失败率是否恶化",
                        "params": {"project": proj, "weeks": n_weeks},
                    }
                )
                return steps

        if ('tests' in (context.get('datasets') or {})) and ('test' in intents or 'execution' in intents) and (
            ('project' in intents) or ('各项目' in q) or ('项目' in q)
        ) and any(k in q for k in ["执行情况", "执行状态", "通过情况", "状态", "pass", "passed", "fail", "failed"]):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_test_run',
                'description': '按项目对比测试执行状态与失败率',
                'params': {'group_by': 'project', 'dataset': 'tests'}
            })
            return steps

        if ('tests' in (context.get('datasets') or {})) and ('tester' in intents) and ('test' in intents or 'execution' in intents) and any(k in q for k in ["测试人员", "测试员", "tester", "情况", "如何", "怎么样", "who"]):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_test_run',
                'description': '按测试人员统计测试执行状态与失败率',
                'params': {'group_by': 'tester', 'dataset': 'tests'}
            })
            return steps

        if ('tester' in intents) and ('defects' in (context.get('datasets') or {})) and any(k in q for k in ["测试人员", "tester", "发现人", "谁发现", "不同测试人员"]):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_tester_findings',
                'description': '按 tester 统计缺陷发现分布与严重/TopIssue 占比',
                'params': {'top_n': 15, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '补充 tester 相关看板图表（严重率/效率）',
                'params': {'question': query, 'max_items': 15}
            })
            return steps

        wants_case_ranking = any(k in q for k in ["哪些", "top", "前", "容易", "出错", "失败率"]) or ("case" in q)
        if wants_case_ranking and ('test' in intents or 'case' in intents) and ('tests' in (context.get('datasets') or {})) and any(k in q for k in ["case", "用例", "testcase", "test case"]):
            tests_meta = (context.get('datasets') or {}).get('tests') or {}
            case_col = _choose_case_col(tests_meta.get('available_columns') or [])
            if not case_col:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '缺少 case 字段，退化为按周统计测试失败率',
                    'params': {'group_by': 'week', 'dataset': 'tests'}
                })
                return steps

            top_n = _extract_top_n(20)
            steps.append({
                'step': len(steps) + 1,
                'tool': 'groupby_aggregate',
                'description': f'按用例维度统计失败率（{case_col}）',
                'params': {
                    'dataset': 'tests',
                    'group_by': case_col,
                    'aggregations': [{'op': 'failure_rate', 'column': '', 'name': 'failure_rate'}],
                    'top_n': top_n,
                    'sort_by': 'failure_rate',
                    'descending': True,
                    'status_column': 'run_status'
                }
            })
            return steps

        if 'strategy' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '汇总看板业务图表指标（用于策略输入）',
                'params': {
                    'question': query,
                    'max_items': 20,
                    'include_inflow_outflow': ('throughput' in intents) or any(k in (query or '').lower() for k in ['inflow', 'outflow', '收敛', '吞吐', '净积压']),
                    'include_longrunner': any(k in (query or '').lower() for k in ['long runner', 'longrunner', '长周期', '阶段耗时'])
                }
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_kpis',
                'description': '生成看板 KPI 概览',
                'params': {'dataset': 'defects'}
            })
            if 'tests' in (context.get('datasets') or {}):
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '分析测试失败率（按周）',
                    'params': {'group_by': 'week', 'dataset': 'tests'}
                })
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '分析测试失败率（按项目）',
                    'params': {'group_by': 'project', 'dataset': 'tests'}
                })
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'correlate_defects_tests',
                    'description': '关联缺陷与测试（发现高风险项目）',
                    'params': {'top_n': 10}
                })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_risk',
                'description': '分析风险（按project维度）',
                'params': {'dimension': 'project', 'top_n': 10, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_aida_hotspots',
                'description': '分析 matrix×AIDA 热点（用于测试重点）',
                'params': {'top_matrices': 10, 'top_aidas': 8, 'sample_tickets': 2, 'include_unknown': True, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_topissue_hotlist',
                'description': '输出 TopIssue 高风险票据清单',
                'params': {'top_n': 15, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_longrunner_hotlist',
                'description': '输出 LongRunner 票据清单',
                'params': {'top_n': 15, 'dataset': 'defects'}
            })
            return steps

        if ('auto' in intents) and auto_strong:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '汇总看板业务图表指标（按问题聚焦）',
                'params': {
                    'question': query,
                    'max_items': 15,
                    'include_inflow_outflow': ('throughput' in intents) or any(k in (query or '').lower() for k in ['inflow', 'outflow', '收敛', '吞吐', '净积压']),
                    'include_longrunner': any(k in (query or '').lower() for k in ['long runner', 'longrunner', '长周期', '阶段耗时'])
                }
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_kpis',
                'description': '生成看板 KPI 概览',
                'params': {'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_risk',
                'description': '分析风险（按project维度）',
                'params': {'dimension': 'project', 'top_n': 10, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '分析趋势（按week分组）',
                'params': {'group_by': 'week', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '按 FV 统计 Top 分布',
                'params': {'group_by': 'fv', 'metric': 'count', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '按 AIDA 统计 Top 分布',
                'params': {'group_by': 'aida', 'metric': 'count', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '按 Solution Cluster/Domain 统计 Top 分布',
                'params': {'group_by': 'domain', 'metric': 'count', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_distribution',
                'description': '分析缺陷矩阵分布',
                'params': {'include_unknown': True, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_aida_hotspots',
                'description': '分析 matrix×AIDA 热点',
                'params': {'top_matrices': 15, 'top_aidas': 5, 'sample_tickets': 3, 'include_unknown': True, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_tester_findings',
                'description': '分析发现问题最多的 tester',
                'params': {'top_n': 10, 'sample_per_tester': 5, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_topissue_hotlist',
                'description': '输出 TopIssue 高风险票据清单',
                'params': {'top_n': 20, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_longrunner_hotlist',
                'description': '输出 LongRunner 票据清单',
                'params': {'top_n': 20, 'dataset': 'defects'}
            })
            if 'tests' in (context.get('datasets') or {}):
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '分析测试运行状态与失败率',
                    'params': {'group_by': 'week', 'dataset': 'tests'}
                })
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'correlate_defects_tests',
                    'description': '关联缺陷与测试，发现高风险项目',
                    'params': {'top_n': 10}
                })
            return steps

        # 根据意图创建步骤
        if 'dashboard' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '汇总看板业务图表指标（按问题聚焦）',
                'params': {
                    'question': query,
                    'max_items': 15,
                    'include_inflow_outflow': ('throughput' in intents) or any(k in (query or '').lower() for k in ['inflow', 'outflow', '收敛', '吞吐', '净积压']),
                    'include_longrunner': any(k in (query or '').lower() for k in ['long runner', 'longrunner', '长周期', '阶段耗时'])
                }
            })

        if 'summary' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_kpis',
                'description': '生成看板 KPI 概览',
                'params': {'dataset': primary_dataset}
            })

        if 'trend' in intents:
            time_range = entities.get('time_range', 'week')
            group_by = 'week' if time_range == 'week' else 'month'
            steps.append({
                'step': 1,
                'tool': 'analyze_trend',
                'description': f'分析趋势（按{group_by}分组）',
                'params': {'group_by': group_by, 'dataset': primary_dataset}
            })

        if 'risk' in intents and primary_dataset != 'tests':
            dimension = entities.get('dimension', 'project')
            top_n = 10
            if isinstance(entities.get('numbers'), list) and entities['numbers']:
                top_n = max(1, min(int(entities['numbers'][0]), 50))
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_risk',
                'description': f'分析风险（按{dimension}维度）',
                'params': {'dimension': dimension, 'top_n': top_n, 'dataset': primary_dataset}
            })

        if 'comparison' in intents:
            if 'projects' in entities and entities['projects']:
                items = entities['projects']
                auto_mode = None
            else:
                items = []
                auto_mode = 'top_risk'
            steps.append({
                'step': len(steps) + 1,
                'tool': 'compare_items',
                'description': '对比项目',
                'params': {
                    'items': items,
                    'dimension': 'project',
                    '_auto': auto_mode,
                    'dataset': primary_dataset
                }
            })

        ql = (query or "").lower()
        aida_failure_focus = (
            ('aida' in intents)
            and (
                ('case' in intents)
                or any(k in ql for k in ['容易出错', '出错', '失败最多', '问题类型', '什么样的问题', '哪类问题'])
            )
        )
        if aida_failure_focus:
            datasets_in_context = (context.get('datasets') or {}) if isinstance(context, dict) else {}
            if 'tests' in datasets_in_context:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '按 AIDA 分析测试失败率，定位容易出错模块',
                    'params': {'group_by': 'aida', 'dataset': 'tests'}
                })
            if primary_dataset != 'tests':
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 AIDA 统计问题分布（缺陷侧）',
                    'params': {'group_by': 'aida', 'metric': 'count', 'dataset': primary_dataset}
                })

        if 'test' in intents:
            group_by = "week"
            if any(k in ql for k in ["按周", "按月", "week", "month", "cw", "calendar_week", "测试周"]):
                group_by = "week" if "month" not in ql else "month"
            else:
                dim = str((entities or {}).get("dimension") or "").strip()
                if "tester" in intents or any(k in ql for k in ["测试人员", "测试员", "tester", "谁"]):
                    group_by = "tester"
                elif "fv" in intents or "feature team" in ql or "feature_team" in ql:
                    group_by = "fv"
                elif "aida" in intents or any(k in ql for k in ["功能", "模块", "service", "services"]):
                    group_by = "aida"
                elif dim and dim.lower() not in {"id", "_id", "test_id", "run_id", "mr_id"}:
                    group_by = dim
                elif "project" in intents or "各项目" in ql or "项目" in ql or "project" in ql:
                    group_by = "project"
            planned_test_run = any(str(s.get('tool') or '').strip() == 'analyze_test_run' for s in steps)
            if not planned_test_run:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': f'分析测试运行状态与失败率（按{group_by}分组）',
                    'params': {'group_by': group_by, 'dataset': 'tests'}
                })

        if 'cross' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'correlate_defects_tests',
                'description': '关联缺陷与测试，发现高风险项目',
                'params': {'top_n': 10}
            })

        if 'matrix' in intents and 'aida' in intents and primary_dataset != 'tests':
            ql = (query or "").lower()
            top_matrices = 10
            if any(k in ql for k in ['每个', '全部', '所有', 'all']):
                top_matrices = 30
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_aida_hotspots',
                'description': '分析 matrix×AIDA 热点',
                'params': {'top_matrices': top_matrices, 'top_aidas': 5, 'sample_tickets': 3, 'include_unknown': True, 'dataset': primary_dataset}
            })
        elif 'matrix' in intents and primary_dataset != 'tests':
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_distribution',
                'description': '分析缺陷矩阵分布',
                'params': {'include_unknown': True, 'dataset': primary_dataset}
            })

        if (('distribution' in intents) or ('top' in intents)) and primary_dataset != 'tests':
            handled = False
            if 'aida' in intents:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 AIDA 统计 Top 分布',
                    'params': {'group_by': 'aida', 'metric': 'count', 'dataset': primary_dataset}
                })
                handled = True
            if 'fv' in intents:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 FV 统计 Top 分布',
                    'params': {'group_by': 'fv', 'metric': 'count', 'dataset': primary_dataset}
                })
                handled = True
            if 'domain' in intents:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 Solution Cluster/Domain 统计 Top 分布',
                    'params': {'group_by': 'domain', 'metric': 'count', 'dataset': primary_dataset}
                })
                handled = True
            if (not handled) and entities.get("dimension"):
                dim = str(entities.get("dimension") or "").strip()
                if dim:
                    steps.append({
                        'step': len(steps) + 1,
                        'tool': 'analyze_trend',
                        'description': f'按 {dim} 统计 Top 分布',
                        'params': {'group_by': dim, 'metric': 'count', 'dataset': primary_dataset}
                    })

        if (('distribution' in intents) or ('top' in intents)) and primary_dataset == 'tests' and ('test' not in intents):
            dim = str((entities or {}).get("dimension") or "").strip() or "project"
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': f'按 {dim} 统计 Top 分布',
                'params': {'group_by': dim, 'metric': 'count', 'dataset': 'tests'}
            })

        if 'tester' in intents and primary_dataset != 'tests':
            top_n = 10
            if isinstance(entities.get('numbers'), list) and entities['numbers']:
                top_n = max(1, min(int(entities['numbers'][0]), 50))
            ql = (query or "").lower()
            sample_per_tester = 5
            if any(k in ql for k in ['都是什么', '详细', '列出', '列表', '明细', 'all']):
                sample_per_tester = 10
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_tester_findings',
                'description': '分析发现问题最多的 tester',
                'params': {'top_n': top_n, 'sample_per_tester': sample_per_tester, 'dataset': primary_dataset}
            })

        # 如果没有特定步骤，添加通用摘要
        if not steps:
            steps.append({
                'step': 1,
                'tool': 'statistical_summary',
                'description': '生成数据摘要',
                'params': {'dataset': primary_dataset}
            })

        if isinstance(context, dict):
            steps = self._apply_smart_tool_selector(query=query, context=context, steps=steps)

        return steps

    def execute_plan(
        self,
        steps: List[Dict],
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        context: Optional[Dict] = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict]:
        """执行计划"""
        results = []
        datasets_meta = (context or {}).get("datasets") or {}
        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        primary_dataset = (context or {}).get("primary_dataset") or ("defects" if isinstance(data, dict) and "defects" in data else None)

        total_steps = len(steps or [])
        for idx, step in enumerate(steps or [], start=1):
            tool_name = step['tool']
            params = step.get('params', {})

            dataset_used: Optional[str] = None
            if isinstance(data, dict):
                tool = (getattr(self.tool_executor, "tools", {}) or {}).get(tool_name)
                if tool is not None and getattr(tool, "expects_datasets", lambda: False)():
                    dataset_used = "datasets"
                else:
                    dataset_used = params.get("dataset") or ("defects" if "defects" in data else next(iter(data.keys()), None))

            if tool_name == 'compare_items':
                auto_mode = params.get('_auto')
                if (not params.get('items')) and auto_mode == 'top_risk':
                    for prev in results:
                        if prev.get('tool') == 'analyze_risk':
                            prev_out = prev.get('result') or {}
                            prev_res = prev_out.get('result') or {}
                            risk_items = prev_res.get('risk_items') or []
                            top_projects = [item.get('name') for item in risk_items[:2] if item.get('name')]
                            if len(top_projects) >= 2:
                                params = dict(params)
                                params['items'] = top_projects
                            break

            params = {k: v for k, v in params.items() if not str(k).startswith('_')}
            if progress_cb:
                try:
                    progress_cb(
                        {
                            "event": "tool_start",
                            "step_index": idx,
                            "total_steps": total_steps,
                            "tool": tool_name,
                            "dataset": dataset_used,
                            "params": dict(params),
                            "description": step.get("description"),
                        }
                    )
                except Exception:
                    pass
            t0 = time.perf_counter()
            # 使用带重试的执行方法（如果可用）
            if hasattr(self.tool_executor, 'execute_with_retry'):
                result = self.tool_executor.execute_with_retry(tool_name, data, **params)
            else:
                result = self.tool_executor.execute_tool(tool_name, data, **params)

            # analyze_test_run 失败时优先尝试更稳妥分组，避免直接退化为摘要
            if tool_name == 'analyze_test_run' and isinstance(result, dict) and result.get('success') is False:
                current_group = str((params or {}).get('group_by') or '').strip().lower()
                for alt_group in ['project', 'aida', 'tester', 'week']:
                    if alt_group == current_group:
                        continue
                    alt_params = dict(params)
                    alt_params['group_by'] = alt_group
                    alt_result = self.tool_executor.execute_tool(tool_name, data, **alt_params)
                    if isinstance(alt_result, dict) and alt_result.get('success') is True:
                        params = alt_params
                        result = alt_result
                        break
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self._record_tool_selector_feedback(
                tool_name=tool_name,
                result=result if isinstance(result, dict) else {},
                duration_ms=duration_ms,
                context=context,
                dataset_used=dataset_used,
            )
            meta = datasets_meta.get(dataset_used) if dataset_used else None
            gate: Dict[str, Any] = {"enabled": bool(validation_enabled), "action": "none", "reason": ""}
            if validation_enabled and isinstance(result, dict) and result.get("success") is False:
                gate["reason"] = str(result.get("error") or "工具执行失败")
                if tool_name in {"consult_semantic_catalog", "search_similar_issues"}:
                    gate["action"] = "continue_degraded"
                else:
                    gate["action"] = "stop"
            results.append({
                'step': step['step'],
                'tool': tool_name,
                'description': step['description'],
                'result': result,
                'trace': {
                    'tool': tool_name,
                    'dataset': dataset_used,
                    'params': dict(params),
                    'duration_ms': duration_ms,
                    'tool_limit': (meta or {}).get('tool_limit') if isinstance(meta, dict) else None,
                    'sampling': (meta or {}).get('sampling') if isinstance(meta, dict) else None,
                    'gate': gate,
                }
            })
            if progress_cb:
                try:
                    progress_cb(
                        {
                            "event": "tool_end",
                            "step_index": idx,
                            "total_steps": total_steps,
                            "tool": tool_name,
                            "dataset": dataset_used,
                            "duration_ms": duration_ms,
                            "success": bool(isinstance(result, dict) and result.get("success") is True),
                            "error": (result.get("error") if isinstance(result, dict) else None),
                            "gate": dict(gate),
                        }
                    )
                except Exception:
                    pass
            if validation_enabled and gate.get("action") == "stop":
                has_success = any(isinstance(r.get("result"), dict) and r["result"].get("success") for r in results)
                if (not has_success) and tool_name != "statistical_summary" and primary_dataset:
                    fallback_params = {"dataset": primary_dataset} if isinstance(data, dict) else {}
                    t1 = time.perf_counter()
                    fb = self.tool_executor.execute_tool("statistical_summary", data, **fallback_params)
                    fb_ms = int((time.perf_counter() - t1) * 1000)
                    fb_meta = datasets_meta.get(primary_dataset) if isinstance(datasets_meta, dict) else None
                    results.append({
                        'step': int(step.get("step") or 0) + 1,
                        'tool': "statistical_summary",
                        'description': "执行失败后的退化：生成数据摘要",
                        'result': fb,
                        'trace': {
                            'tool': "statistical_summary",
                            'dataset': primary_dataset,
                            'params': dict(fallback_params),
                            'duration_ms': fb_ms,
                            'tool_limit': (fb_meta or {}).get('tool_limit') if isinstance(fb_meta, dict) else None,
                            'sampling': (fb_meta or {}).get('sampling') if isinstance(fb_meta, dict) else None,
                            'gate': {"enabled": True, "action": "fallback", "reason": gate.get("reason") or ""},
                        }
                    })
                break

        return results


# ============================================================================
# 6. 智能 Agent 主类
# ============================================================================

# Active runtime aliases point at the extracted modules. The previous inline
# implementations remain private compatibility scaffolding and are no longer
# referenced by the public API.
ToolExecutor = ExtractedToolExecutor
ToolExecutorWithRetry = ExtractedToolExecutorWithRetry
ConversationMemory = ExtractedConversationMemory
TaskPlanner = ExtractedTaskPlanner

class IntelligentAgent:
    """智能 Agent - 整合所有功能"""

    def __init__(self, dashboard_type: str = 'general', llm: Any = None, db_path: Optional[str] = None):
        self.dashboard_type = dashboard_type

        # 初始化各组件
        # 使用带重试功能的工具执行器
        retry_enabled = os.getenv("AGENT_TOOL_RETRY_ENABLED", "1") == "1"
        tool_executor_kwargs = {
            'llm': llm,
            'db_path': db_path,
            'default_tool_factory': build_default_tools,
        }
        if retry_enabled:
            self.tool_executor = ToolExecutorWithRetry(max_retry=2, **tool_executor_kwargs)
        else:
            self.tool_executor = ToolExecutor(**tool_executor_kwargs)
        self.context_manager = IntelligentContextManager()
        self.smart_tool_selector = None
        if SMART_TOOL_SELECTOR_AVAILABLE and create_smart_tool_selector:
            try:
                selector_db_path = os.path.join(PROJECT_ROOT, "database", "tool_performance.db")
                self.smart_tool_selector = create_smart_tool_selector(db_path=selector_db_path)
                logger.info("智能工具选择器初始化成功")
            except Exception as e:
                logger.warning(f"智能工具选择器初始化失败: {e}")
        memory_enabled = os.getenv("AGENT_MEMORY_ENABLED", "0") == "1"
        memory_file = os.getenv("AGENT_MEMORY_FILE")
        if memory_enabled and not memory_file:
            base = os.path.join(PROJECT_ROOT, "history")
            memory_file = os.path.join(base, f"agent_memory_{dashboard_type}.json")
        autosave = os.getenv("AGENT_MEMORY_AUTOSAVE", "0") == "1"
        self.memory = ConversationMemory(memory_file=memory_file, autosave=autosave)
        self.knowledge_base = KnowledgeBase()
        self.task_planner = TaskPlanner(self.tool_executor, tool_selector=self.smart_tool_selector)
        self._pending_execution_confirmation: Optional[Dict[str, Any]] = None

        # 数据分析增强模块
        from agent.core.data_profiler import DataProfiler
        from agent.core.proactive_insights import ProactiveInsightEngine
        from agent.core.query_memory import QueryMemory
        from agent.core.code_interpreter import CodeInterpreter

        self._data_profiler = DataProfiler()
        self._proactive_engine = ProactiveInsightEngine()
        self._query_memory = QueryMemory()
        self._code_interpreter = CodeInterpreter(db_path=db_path)
        self._last_profile = None  # 缓存最近一次数据画像
        self._proactive_sent = False  # 是否已发送主动洞察

        logger.info(f"智能 Agent 初始化完成 (类型: {dashboard_type})")

        # P0 Framework: Tracer + Self-Corrector + Registry
        try:
            from agent.core.integration import patch_agent
            patch_agent(self)
        except Exception as _patch_err:
            logger.debug(f"Framework patch skipped: {_patch_err}")

    def _is_positive_confirmation(self, text: str) -> bool:
        s = str(text or "").strip().lower()
        if not s:
            return False
        positives = [
            "继续", "继续执行", "确认", "确认执行", "是", "好的", "好", "ok", "yes", "y", "proceed", "continue",
        ]
        return any(p == s or p in s for p in positives)

    def _is_negative_confirmation(self, text: str) -> bool:
        s = str(text or "").strip().lower()
        if not s:
            return False
        negatives = [
            "取消", "停止", "不执行", "算了", "否", "不要", "no", "n", "cancel", "stop",
        ]
        return any(n == s or n in s for n in negatives)

    def _should_require_step_confirmation(self, plan: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
        enabled = os.getenv("AGENT_CONFIRM_MULTISTEP", "1") != "0"
        if not enabled:
            return False
        min_steps = int(os.getenv("AGENT_CONFIRM_MIN_STEPS", "2") or 2)
        min_steps = max(2, min_steps)
        steps = plan or []
        if len(steps) < min_steps:
            return False
        return True

    def _build_confirmation_prompt(self, question: str, plan: List[Dict[str, Any]]) -> str:
        preview = []
        for i, step in enumerate((plan or [])[:8], start=1):
            tool = str(step.get("tool") or "")
            desc = str(step.get("description") or "")
            preview.append(f"{i}. {tool} - {desc}")
        lines = [
            f"问题: {question}",
            "已生成多步执行计划。为提升结果准确性和确定性，请先确认：",
            "",
            *preview,
            "",
            "回复 继续/确认 执行；回复 取消/停止 放弃本次计划。",
        ]
        return "\n".join(lines)

    def _normalize_response_payload(
        self,
        payload: Dict[str, Any],
        execution_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        out = dict(payload or {})
        out["text"] = str(out.get("text") or "").strip()

        raw_insights = out.get("insights")
        insights = []
        if isinstance(raw_insights, list):
            seen = set()
            for item in raw_insights:
                txt = str(item or "").strip()
                if txt and txt not in seen:
                    seen.add(txt)
                    insights.append(txt)
        out["insights"] = insights[:80]

        raw_viz = out.get("visualizations")
        visualizations = []
        if isinstance(raw_viz, list):
            for v in raw_viz:
                if isinstance(v, dict):
                    vv = dict(v)
                    data_obj = vv.get("data")
                    if isinstance(data_obj, list) and len(data_obj) > 200:
                        vv["data"] = data_obj[:200]
                    visualizations.append(vv)
        out["visualizations"] = visualizations

        tools_used = out.get("tools_used") if isinstance(out.get("tools_used"), list) else []
        if execution_results:
            for r in execution_results:
                t = str((r or {}).get("tool") or "").strip()
                if t:
                    tools_used.append(t)
        dedup_tools = []
        seen_tools = set()
        for t in tools_used:
            ts = str(t or "").strip()
            if ts and ts not in seen_tools:
                seen_tools.add(ts)
                dedup_tools.append(ts)
        out["tools_used"] = dedup_tools

        ctx = out.get("context")
        out["context"] = ctx if isinstance(ctx, dict) else {}

        summary = {
            "total_steps": 0,
            "success_steps": 0,
            "failed_steps": 0,
        }
        if isinstance(execution_results, list):
            total = len(execution_results)
            success = 0
            failed = 0
            for r in execution_results:
                rr = (r or {}).get("result")
                if isinstance(rr, dict):
                    if rr.get("success") is True:
                        success += 1
                    elif rr.get("success") is False:
                        failed += 1
            summary = {
                "total_steps": total,
                "success_steps": success,
                "failed_steps": failed,
            }

        out["execution_summary"] = summary
        out["response_schema_version"] = "v2"
        return out

    def process(
        self,
        question: str,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        conversation_history: List = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        处理用户问题

        Args:
            question: 用户问题
            data: 数据 DataFrame 或多数据集字典
            conversation_history: 对话历史（可选）

        Returns:
            包含答案、工具调用结果、洞察等的字典
        """
        start_time = datetime.now()

        # P0 Tracer: wrap the entire process() call
        _tracer = None
        try:
            from agent.core.integration import create_tracer
            _tracer = create_tracer(question or "")
        except Exception:
            pass

        qtext = (question or "").strip()

        # P1 Guardrails: input check
        _guardrail_results = []
        try:
            from agent.core.guardrails import GuardrailPipeline
            if GuardrailPipeline.is_enabled():
                _pipeline = GuardrailPipeline()
                _proceed, _guardrail_results = _pipeline.check_input(question or "")
                if not _proceed:
                    if _tracer:
                        _tracer.set_meta(guardrails="blocked")
                        _tracer.finish()
                    return self._normalize_response_payload({
                        "text": _pipeline.format_input_block_message(_guardrail_results),
                        "insights": [], "visualizations": [], "tools_used": [],
                        "context": {"guardrails": "blocked", "details": [r.reason for r in _guardrail_results if r.should_block]},
                    })
        except Exception:
            pass

        confirmed_now = False
        pending = self._pending_execution_confirmation
        if isinstance(pending, dict):
            ttl_sec = int(os.getenv("AGENT_CONFIRM_TTL_SEC", "600") or 600)
            created_at = float(pending.get("created_at") or 0)
            if created_at and (time.time() - created_at > max(30, ttl_sec)):
                self._pending_execution_confirmation = None
            elif self._is_negative_confirmation(qtext):
                self._pending_execution_confirmation = None
                return self._normalize_response_payload(
                    {
                        "text": "已取消待执行计划。请继续输入新的分析问题。",
                        "insights": [],
                        "visualizations": [],
                        "tools_used": [],
                        "context": {"confirmation": "cancelled"},
                    }
                )
            elif self._is_positive_confirmation(qtext):
                question = str(pending.get("question") or question)
                qtext = question.strip()
                confirmed_now = True
            else:
                self._pending_execution_confirmation = None

        if qtext.startswith("记住：") or qtext.lower().startswith("remember:"):
            payload = qtext.split("：", 1)[-1].strip() if "：" in qtext else qtext.split(":", 1)[-1].strip()
            self.memory.add_fact(payload, importance=0.98)
            return self._normalize_response_payload({"text": "已记住。", "insights": [], "visualizations": [], "tools_used": [], "context": {"memory": "saved"}})
        if qtext.startswith("忘记：") or qtext.lower().startswith("forget:"):
            payload = qtext.split("：", 1)[-1].strip() if "：" in qtext else qtext.split(":", 1)[-1].strip()
            removed = self.memory.forget(payload)
            return self._normalize_response_payload({"text": f"已删除 {removed} 条相关记忆。", "insights": [], "visualizations": [], "tools_used": [], "context": {"memory": "deleted", "removed": removed}})

        if conversation_history and os.getenv("AGENT_SYNC_UI_HISTORY", "1") == "1":
            try:
                max_ui = int(os.getenv("AGENT_UI_HISTORY_MAX_MESSAGES", str(self.memory.max_short_term)))
            except Exception:
                max_ui = self.memory.max_short_term
            ui_msgs = []
            for m in (conversation_history or []):
                try:
                    role = (m or {}).get("role")
                    if role not in {"user", "assistant"}:
                        continue
                    if (m or {}).get("type") in {"stream_response"}:
                        continue
                    content = str((m or {}).get("content") or "").strip()
                    if not content:
                        continue
                    ui_msgs.append(
                        {
                            "role": role,
                            "content": content,
                            "timestamp": (m or {}).get("timestamp") or datetime.now().isoformat(),
                            "metadata": {"from_ui": True},
                        }
                    )
                except Exception:
                    continue
            if max_ui > 0 and len(ui_msgs) > max_ui:
                ui_msgs = ui_msgs[-max_ui:]
            if ui_msgs:
                self.memory.short_term = ui_msgs[-self.memory.max_short_term :]

        # 1. 保存用户消息到记忆
        self.memory.add_message('user', question)

        analysis_question = str(question or "").strip()
        semantic_term_adapter: Dict[str, Any] = {}
        semantic_term_hints: Dict[str, Any] = {}
        try:
            from semantic_catalog.term_adapter import adapt_question_with_semantic_terms, is_semantic_catalog_enabled

            if is_semantic_catalog_enabled():
                db_path = getattr(self.tool_executor, "_db_path", None)
                semantic_term_adapter = adapt_question_with_semantic_terms(
                    question=analysis_question,
                    db_path=db_path,
                    table_name="",
                    prefer_db=bool(db_path),
                )
                semantic_term_hints = dict(semantic_term_adapter.get("semantic_hints") or {})
                normalized_question = str(semantic_term_adapter.get("normalized_question") or "").strip()
                if normalized_question:
                    analysis_question = normalized_question
        except Exception as sem_err:
            logger.debug(f"semantic term adapter skipped: {sem_err}")

        # 1.5 低置信度意图提前澄清，减少无效工具调用和不必要的SQL生成。
        early_intents, early_confidence, clarification = self.context_manager.analyze_intent_with_confidence(analysis_question)

        # 对“仅补充槽位”的追问（如“IDCevo 本季度”）自动继承最近一条明确意图。
        if early_intents == ['general']:
            q = str(question or "").strip()
            ql = q.lower()
            has_time_slot = any(k in ql for k in [
                '本周', '这周', '上周', '本月', '上月', '本季度', '季度', '本年', '今年',
                'today', 'yesterday', 'this week', 'last week', 'this month', 'quarter'
            ])
            has_project_slot = bool(re.search(r"\b(IDCEVO|IDC|MGU|APP|RSU|ENTRYEVO|G\d{2,})\b", q, flags=re.IGNORECASE))
            if has_time_slot or has_project_slot:
                inherited_intents: List[str] = []
                for m in reversed(conversation_history or []):
                    if str((m or {}).get('role') or '') != 'user':
                        continue
                    content = str((m or {}).get('content') or '').strip()
                    if not content or content == q:
                        continue
                    cand = self.context_manager.analyze_intent(content)
                    if cand and cand != ['general']:
                        inherited_intents = cand
                        break
                if inherited_intents:
                    early_intents = inherited_intents
                    early_confidence = 0.78
                    clarification = None

        if clarification and early_confidence < 0.7:
            return self._normalize_response_payload({
                "text": clarification,
                "insights": [],
                "visualizations": [],
                "tools_used": [],
                "context": {
                    "intents": early_intents,
                    "confidence": early_confidence,
                    "needs_clarification": True,
                },
            })

        # 2. 准备上下文
        if _tracer:
            _ctx_span = _tracer.span("context_preparation").__enter__()
        context, prepared_data = self.context_manager.prepare_context(analysis_question, data)
        self._last_context = context  # for self-corrector
        if _tracer:
            _ctx_span.__exit__(None, None, None)
        if semantic_term_adapter:
            context["semantic_term_adapter"] = semantic_term_adapter
        if semantic_term_hints:
            context["semantic_term_hints"] = semantic_term_hints
        if progress_cb:
            try:
                progress_cb(
                    {
                        "event": "context_ready",
                        "primary_dataset": context.get("primary_dataset"),
                        "intents": list(context.get("intents") or []),
                    }
                )
            except Exception:
                pass

        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        # 默认启用 agentic（若LLM可用），可通过 AGENT_AGENTIC_ENABLED=0 显式关闭。
        agentic_enabled = (os.getenv("AGENT_AGENTIC_ENABLED", "1") != "0") and (self.tool_executor._llm is not None)
        requested_mode = str(os.getenv("AGENT_MODE", "agentic") or "agentic").strip().lower()

        # ACCESSCODE 内网模板链路已在非流式调用中验证更稳定，但 function-calling 兼容性不稳定。
        # 在该链路下优先使用 hybrid，避免 agentic 每轮都因响应结构差异失败后再降级。
        llm_obj = self.tool_executor._llm
        internal_template_route = False
        try:
            checker = getattr(llm_obj, "_should_use_internal_template_for_nonstream", None)
            if callable(checker):
                internal_template_route = bool(checker())
        except Exception:
            internal_template_route = False

        if requested_mode == "agentic" and internal_template_route:
            logger.info("检测到ACCESSCODE内网模板链路，自动切换为hybrid模式以提升稳定性")
        mode = resolve_execution_mode(
            requested_mode=requested_mode,
            agentic_enabled=agentic_enabled,
            internal_template_route=internal_template_route,
        )
        analysis_trace = init_analysis_trace(
            mode=mode,
            validation_enabled=validation_enabled,
            internal_template_route=internal_template_route,
        )

        semantic_catalog_enabled = False
        try:
            from semantic_catalog.term_adapter import is_semantic_catalog_enabled

            semantic_catalog_enabled = is_semantic_catalog_enabled()
        except Exception:
            semantic_catalog_enabled = (os.getenv("AGENT_SEMANTIC_CATALOG_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}

        if semantic_catalog_enabled:
            try:
                from semantic_catalog.runtime import build_semantic_context

                dashboard = self.dashboard_type
                cols = []
                if isinstance(prepared_data, dict):
                    primary = context.get("primary_dataset") or ("defects" if "defects" in prepared_data else next(iter(prepared_data.keys()), None))
                    df = prepared_data.get(primary) if primary else None
                    if isinstance(df, pd.DataFrame):
                        cols = [str(c) for c in df.columns.tolist()]
                elif isinstance(prepared_data, pd.DataFrame):
                    cols = [str(c) for c in prepared_data.columns.tolist()]
                db_path = getattr(self.tool_executor, "_db_path", None)
                context["semantic_context"] = build_semantic_context(
                    question=analysis_question, dashboard=dashboard, dataframe_columns=cols, max_each=6, db_path=db_path
                )
            except Exception as e:
                context["semantic_context"] = f"语义目录加载失败: {e}"

        # === Unified Execution Engine ===
        # All modes (rule/agentic/hybrid) share the same execution loop.
        # Agentic mode auto-degrades to rule if no LLM available.
        _use_unified_engine = os.getenv("AGENT_UNIFIED_ENGINE", "1") == "1"


        # 3. 获取相关历史
        relevant_history = self.memory.get_relevant_history(question)
        if os.getenv("AGENT_MEMORY_DEBUG", "0") == "1":
            used = []
            for h in (relevant_history or [])[:5]:
                used.append({
                    "role": h.get("role"),
                    "from_memory": bool(h.get("from_memory")),
                    "kind": h.get("kind"),
                    "tags": h.get("tags") or [],
                    "content": (h.get("content") or "")[:160],
                })
            context["memory_debug"] = {
                "short_term_size": len(self.memory.short_term or []),
                "long_term_size": len(self.memory.long_term or []),
                "used": used,
            }

        # 4. 获取相关知识
        knowledge_context = self.knowledge_base.get_knowledge_context(analysis_question)

        # Streaming: emit intent_detected
        if progress_cb:
            try:
                progress_cb({"event": "intent_detected", "intents": list(context.get("intents") or []), "mode": mode})
            except Exception:
                pass

        # === 数据分析增强 ===

        # Data Profiling: 首次分析时自动画像
        _profile_summary = ""
        if prepared_data is not None:
            try:
                _df = prepared_data if isinstance(prepared_data, pd.DataFrame) else (list(prepared_data.values())[0] if isinstance(prepared_data, dict) and prepared_data else None)
                if _df is not None and (self._last_profile is None or self._last_profile[0] != id(_df)):
                    _profile = self._data_profiler.profile(_df, dataset_name=context.get("primary_dataset", "data"))
                    _profile_summary = self._data_profiler.generate_summary(_profile, max_length=1000)
                    self._last_profile = (id(_df), _profile, _profile_summary)
                    # 注入到 context
                    context["data_profile_summary"] = _profile_summary
                    context["data_profile"] = self._data_profiler.profile_to_dict(_profile)
                elif self._last_profile:
                    _profile_summary = self._last_profile[2]
                    context["data_profile_summary"] = _profile_summary
            except Exception as _dp_err:
                logger.debug(f"Data profiling skipped: {_dp_err}")

        # Query Memory: 查找相似历史成功查询
        _memory_match = None
        try:
            _memory_match = self._query_memory.find_similar(analysis_question, intents=list(context.get("intents") or []))
            if _memory_match and _memory_match.quality >= 0.6:
                context["memory_match"] = {
                    "similarity": round(_memory_match.similarity, 2),
                    "quality": round(_memory_match.quality, 2),
                    "plan": _memory_match.suggested_plan,
                }
                logger.info(f"QueryMemory match: similarity={_memory_match.similarity:.2f}, quality={_memory_match.quality:.2f}")
        except Exception as _qm_err:
            logger.debug(f"QueryMemory lookup skipped: {_qm_err}")

        # Proactive Insights: 首次查询时主动推送
        _proactive_text = ""
        if not self._proactive_sent and self._last_profile:
            try:
                _df_for_insights = prepared_data if isinstance(prepared_data, pd.DataFrame) else (list(prepared_data.values())[0] if isinstance(prepared_data, dict) and prepared_data else None)
                if _df_for_insights is not None:
                    _insights = self._proactive_engine.analyze(_df_for_insights, data_profile=self._last_profile[1])
                    if _insights:
                        _proactive_text = self._proactive_engine.format_insights(_insights)
                        context["proactive_insights"] = _proactive_text
                        self._proactive_sent = True
                        logger.info(f"Proactive insights: {len(_insights)} items")
            except Exception as _pi_err:
                logger.debug(f"Proactive insights skipped: {_pi_err}")

        # 5. 规划任务（若用户刚确认，则复用待确认计划）
        plan = None
        if isinstance(pending, dict) and self._is_positive_confirmation((qtext or "").strip()):
            reused_plan = pending.get("plan")
            if isinstance(reused_plan, list) and reused_plan:
                plan = reused_plan
            self._pending_execution_confirmation = None
        if plan is None:
            # Query Memory 复用: 如果历史方案质量够高，直接复用
            if _memory_match and _memory_match.quality >= 0.7 and _memory_match.suggested_plan:
                plan = _memory_match.suggested_plan
                logger.info(f"Reused plan from QueryMemory (quality={_memory_match.quality:.2f})")
                if progress_cb:
                    try:
                        progress_cb({"event": "plan_reused", "source": "query_memory", "quality": round(_memory_match.quality, 2)})
                    except Exception:
                        pass

            if plan is None:
                if _tracer:
                    _plan_span = _tracer.span("task_planning").__enter__()
                plan = self.task_planner.plan(analysis_question, context)
                if _tracer:
                    _plan_span.__exit__(None, None, None)
            # Streaming: emit plan_created
            if progress_cb:
                try:
                    progress_cb({"event": "plan_created", "steps": [{"tool": s.get("tool"), "desc": s.get("description", "")} for s in (plan or [])]})
                except Exception:
                    pass

        if (not confirmed_now) and self._should_require_step_confirmation(plan, context):
            self._pending_execution_confirmation = {
                "question": question,
                "plan": plan,
                "created_at": time.time(),
            }
            analysis_trace["plan"] = serialize_plan_trace(plan)
            context["analysis_trace"] = analysis_trace
            return self._normalize_response_payload(
                {
                    "text": self._build_confirmation_prompt(question, plan),
                    "insights": ["已进入多步执行确认模式"],
                    "visualizations": [],
                    "tools_used": [],
                    "context": {
                        **(context or {}),
                        "needs_confirmation": True,
                        "confirmation_pending": True,
                        "plan_steps": len(plan or []),
                    },
                }
            )

        if progress_cb:
            try:
                progress_cb(
                    {
                        "event": "planned",
                        "total_steps": len(plan or []),
                        "tools": [s.get("tool") for s in (plan or []) if isinstance(s, dict)],
                    }
                )
            except Exception:
                pass
        analysis_trace["plan"] = serialize_plan_trace(plan)

        # 6. 执行计划 — 统一执行引擎
        _exec_answer_text = ""
        if _use_unified_engine:
            try:
                from agent.core.execution_engine import UnifiedExecutionEngine
                _engine = UnifiedExecutionEngine(self)
                _exec_result = _engine.run(
                    question=analysis_question,
                    data=prepared_data,
                    context=context,
                    mode=mode,
                    plan=plan,
                    progress_cb=progress_cb,
                    tracer=_tracer,
                )
                # Convert unified results to legacy format
                execution_results = []
                for s in _exec_result.steps:
                    execution_results.append({
                        "step": execution_results.__len__() + 1 if execution_results else 1,
                        "tool": s.tool,
                        "description": "",
                        "result": s.result if isinstance(s.result, dict) else {"success": s.success},
                        "trace": {
                            "tool": s.tool,
                            "params": s.params,
                            "duration_ms": s.duration_ms,
                            "gate": {"enabled": False, "action": "none", "reason": ""},
                        },
                    })
                _exec_answer_text = _exec_result.answer_text
                analysis_trace["execution"] = [{"tool": s.tool, "params": s.params, "duration_ms": s.duration_ms} for s in _exec_result.steps]
                logger.info(f"Unified engine: mode={_exec_result.mode_used}, steps={len(_exec_result.steps)}, duration={_exec_result.total_duration_ms}ms")
            except Exception as _engine_err:
                logger.warning(f"Unified engine failed, falling back to legacy: {_engine_err}")
                execution_results = self.task_planner.execute_plan(plan, prepared_data, context=context, progress_cb=progress_cb, _tracer=_tracer)
                analysis_trace["execution"] = [r.get("trace") for r in (execution_results or []) if isinstance(r, dict) and r.get("trace")]
        else:
            execution_results = self.task_planner.execute_plan(plan, prepared_data, context=context, progress_cb=progress_cb, _tracer=_tracer)
            analysis_trace["execution"] = [r.get("trace") for r in (execution_results or []) if isinstance(r, dict) and r.get("trace")]
        context["analysis_trace"] = analysis_trace

        # 7. 生成综合答案
        if progress_cb:
            try:
                progress_cb({"event": "synthesize"})
            except Exception:
                pass
        # Agentic mode may have generated answer text directly
        if _exec_answer_text:
            answer = {"text": _exec_answer_text, "insights": [], "visualizations": []}
        else:
            answer = self._generate_answer(
                question=question,
                context=context,
                execution_results=execution_results,
                knowledge_context=knowledge_context,
                relevant_history=relevant_history
            )
        try:
            ctx_obj = answer.get("context") if isinstance(answer, dict) else None
            if isinstance(ctx_obj, dict):
                ctx_obj["analysis_trace"] = analysis_trace
        except Exception:
            pass

        # 8. 保存助手回复到记忆
        self.memory.add_message('assistant', answer['text'], {
            'tools_used': [r['tool'] for r in execution_results],
            'execution_time': (datetime.now() - start_time).total_seconds()
        })

        # P1 Guardrails: output check
        try:
            from agent.core.guardrails import GuardrailPipeline
            if GuardrailPipeline.is_enabled():
                _out_results = GuardrailPipeline().check_output(str(answer.get('text', '')), execution_results)
                _out_warns = [r for r in _out_results if r.action.value == "warn"]
                if _out_warns:
                    answer['text'] = str(answer.get('text', '')) + GuardrailPipeline().format_output_warnings(_out_results)
        except Exception:
            pass

        # Proactive Insights: 附加在首次回答末尾
        if _proactive_text and answer.get('text'):
            answer['text'] = str(answer['text']) + "\n\n---\n" + _proactive_text
            _proactive_text = ""  # 只附加一次

        # Query Memory: 记录本次成功查询
        try:
            _plan_for_memory = []
            for step in (plan or []):
                if isinstance(step, dict) and step.get("tool"):
                    _plan_for_memory.append({"tool": step["tool"], "params": step.get("params", {}), "description": step.get("description", "")})
            _tools_for_memory = list(set(r.get("tool") for r in execution_results if r.get("tool")))
            _has_success = any(isinstance(r.get("result"), dict) and r.get("result", {}).get("success") for r in execution_results)
            if _tools_for_memory:
                self._query_memory.record(
                    question=analysis_question,
                    plan=_plan_for_memory,
                    tools_used=_tools_for_memory,
                    success=_has_success,
                    result_quality=0.8 if _has_success else 0.3,
                    intents=list(context.get("intents") or []),
                    dataset=str(context.get("primary_dataset") or ""),
                )
        except Exception as _qm_err:
            logger.debug(f"QueryMemory record skipped: {_qm_err}")

        # P0 Tracer: finish trace
        if _tracer:
            try:
                _tracer.set_meta(
                    mode=str(context.get('analysis_trace', {}).get('mode', 'unknown')),
                    tools_used=[r['tool'] for r in execution_results],
                )
                _tracer.finish(answer_summary=str(answer.get('text', ''))[:500])
            except Exception:
                pass

        return self._normalize_response_payload(answer, execution_results=execution_results)

    def _generate_answer(self, question: str, context: Dict, execution_results: List[Dict],
                        knowledge_context: str, relevant_history: List) -> Dict[str, Any]:
        """生成综合答案"""
        answer_parts = []
        insights = []
        data_visualizations = []

        # 1. 开场白
        answer_parts.append(f"根据您的问题「{question}」，我进行了以下分析：\n")

        datasets_meta = context.get('datasets') or {}
        tool_limit_notes = []
        context_sampling_notes = []
        for name, meta in datasets_meta.items():
            tool_limit = (meta or {}).get('tool_limit') or {}
            tl_mode = tool_limit.get('mode')
            if tl_mode and tl_mode != 'none' and tl_mode != 'empty':
                tool_limit_notes.append(f"- 计算数据集[{name}] 采用 {tl_mode}")

            sampling = (meta or {}).get('sampling') or {}
            s_mode = sampling.get('mode')
            if s_mode and s_mode != 'none' and s_mode != 'empty':
                context_sampling_notes.append(f"- 上下文数据集[{name}] 采用 {s_mode}（rows={sampling.get('rows')}）")

        if tool_limit_notes or context_sampling_notes:
            answer_parts.append("\n为平衡速度与准确性，本次使用了如下策略：\n")
            if tool_limit_notes:
                answer_parts.append("计算侧：\n")
                answer_parts.extend([f"{n}\n" for n in tool_limit_notes])
            if context_sampling_notes:
                answer_parts.append("上下文侧（仅用于让模型阅读）：\n")
                answer_parts.extend([f"{n}\n" for n in context_sampling_notes])

        semantic_from_context = str((context or {}).get("semantic_context") or "").strip()
        semantic_already_in_steps = any((r or {}).get("tool") == "consult_semantic_catalog" for r in (execution_results or []))
        if semantic_from_context and (not semantic_already_in_steps):
            preview = semantic_from_context if len(semantic_from_context) <= 1600 else (semantic_from_context[:1600] + "\n...(已截断)")
            answer_parts.append("\n**语义目录（口径/字段/误用风险）**\n")
            answer_parts.append(preview + "\n")

        # 2. 工具执行结果
        for result in execution_results:
            tool_output = result.get('result') or {}
            if tool_output.get('success'):
                answer_parts.append(f"\n**{result['description']}**\n")

                tool_result = tool_output.get('result') or {}

                if result.get('tool') == 'consult_semantic_catalog':
                    semantic_text = (tool_result.get('semantic_context') or '').strip()
                    if semantic_text:
                        preview = semantic_text if len(semantic_text) <= 1600 else (semantic_text[:1600] + "\n...(已截断)")
                        answer_parts.append(preview + "\n")

                if result.get('tool') == 'search_similar_issues':
                    candidates = tool_result.get('candidates') or []
                    if candidates:
                        answer_parts.append("相似问题候选（Top）：\n")
                        for c in candidates[:8]:
                            tid = c.get("ticket_id") or ""
                            score = c.get("score_1_10")
                            proj = c.get("project") or ""
                            name = c.get("name") or ""
                            snippet = (c.get("snippet") or "").strip()
                            line = f"- {tid} | score={score} | {proj} | {name}".strip()
                            answer_parts.append(line + "\n")
                            if snippet:
                                answer_parts.append(f"  - {snippet[:160]}\n")

                if result.get('tool') in {'query_sqlite_with_fix', 'run_sqlite_query'}:
                    cols = tool_result.get("columns") or []
                    rows = tool_result.get("rows") or []
                    sql_used = tool_result.get("sql") or tool_result.get("generated_sql") or ""
                    if sql_used:
                        answer_parts.append(f"- SQL: {sql_used}\n")
                    if cols:
                        answer_parts.append(f"- 字段: {', '.join([str(c) for c in cols[:30]])}\n")
                    if rows:
                        answer_parts.append(f"- 返回行数: {tool_result.get('row_count', len(rows))}\n")
                        for r in rows[:8]:
                            if isinstance(r, dict):
                                brief = ", ".join(f"{k}={r.get(k)}" for k in list(r.keys())[:6])
                                answer_parts.append(f"  - {brief}\n")

                # 添加摘要
                if 'summary' in tool_result:
                    summary = tool_result['summary']
                    if 'direction' in summary:
                        answer_parts.append(
                            f"- 趋势方向: {summary['direction']}\n"
                            f"- 变化率: {summary['change_rate']}%\n"
                            f"- 总数: {summary['total']}\n"
                            f"- 平均: {summary['average']}\n"
                        )
                        data_visualizations.append({
                            'type': 'trend',
                            'data': tool_result.get('trend_data', [])
                        })

                if result.get('tool') == 'analyze_trend':
                    trend_rows = tool_result.get('trend_data') or []
                    desc = result.get('description') or ''
                    if trend_rows and any(k in desc for k in ['Top 分布', '按 FV', '按 AIDA', '按 Solution Cluster', '按项目', '按项目', '按严重', '按类别', '按状态', '按PU', '按tester']):
                        answer_parts.append("Top 分布：\n")
                        for r in trend_rows[:10]:
                            answer_parts.append(f"- {r.get('group')}: {r.get('value')}\n")

                if result.get('tool') == 'defect_explore_kpis':
                    k = tool_result
                    if isinstance(k, dict):
                        answer_parts.append(f"- 总缺陷数: {k.get('total_defects', 0)}\n")
                        answer_parts.append(f"- 严重缺陷率: {k.get('severe_rate', 0)}%\n")
                        answer_parts.append(f"- 活跃测试人员: {k.get('total_testers', 0)}\n")
                        if k.get('daily_avg', 0):
                            answer_parts.append(f"- 日均缺陷: {k.get('daily_avg')}\n")
                        if k.get('top_tester'):
                            answer_parts.append(f"- 最活跃 tester: {k.get('top_tester')}\n")

                if result.get('tool') == 'defect_explore_dashboard':
                    charts = (tool_result.get("charts") or []) if isinstance(tool_result, dict) else []
                    if not charts:
                        answer_parts.append("- 未匹配到可计算的看板图表（可能缺少字段或数据为空）\n")
                    for chart in charts:
                        cid = chart.get("id")
                        title = chart.get("title") or cid
                        cdata = chart.get("data")
                        answer_parts.append(f"\n- {title} ({cid})\n")
                        if isinstance(cdata, dict) and all(k in cdata for k in ["total_defects", "severe_rate", "total_testers"]):
                            answer_parts.append(f"  - 总缺陷数: {cdata.get('total_defects', 0)}\n")
                            answer_parts.append(f"  - 严重缺陷率: {cdata.get('severe_rate', 0)}%\n")
                            answer_parts.append(f"  - 活跃测试人员: {cdata.get('total_testers', 0)}\n")
                            if cdata.get("top_tester"):
                                answer_parts.append(f"  - 最活跃 tester: {cdata.get('top_tester')}\n")
                        elif isinstance(cdata, list):
                            for item in cdata[:10]:
                                if isinstance(item, dict):
                                    if "group" in item and "total" in item and "stacks" in item:
                                        answer_parts.append(f"  - {item.get('group')}: {item.get('total')}\n")
                                        stacks = item.get("stacks") or []
                                        if stacks:
                                            brief = ", ".join([f"{s.get('key')}:{s.get('count')}" for s in stacks[:5] if isinstance(s, dict)])
                                            if brief:
                                                answer_parts.append(f"    - {brief}\n")
                                    elif "key" in item and "count" in item:
                                        ratio = item.get("ratio")
                                        if ratio is None:
                                            answer_parts.append(f"  - {item.get('key')}: {item.get('count')}\n")
                                        else:
                                            answer_parts.append(f"  - {item.get('key')}: {item.get('count')} ({ratio}%)\n")
                                    elif "key" in item and "severe_rate" in item:
                                        answer_parts.append(
                                            f"  - {item.get('key')}: 严重率 {item.get('severe_rate')}% (总{item.get('total')}, 严重{item.get('severe')})\n"
                                        )
                                    elif "transition" in item and "avg_hours" in item:
                                        answer_parts.append(
                                            f"  - {item.get('transition')}: 平均 {item.get('avg_hours')}h, 总 {item.get('total_hours')}h, 次数 {item.get('count')}\n"
                                        )
                                    elif "word" in item and "count" in item:
                                        answer_parts.append(f"  - {item.get('word')}: {item.get('count')} ({item.get('ratio', 0)}%)\n")
                        elif isinstance(cdata, dict) and "stats" in cdata and "recent_weeks" in cdata:
                            stats = cdata.get("stats") or {}
                            answer_parts.append(
                                f"  - 总Inflow: {stats.get('total_inflow', 0)}, 总Outflow: {stats.get('total_outflow', 0)}, "
                                f"净积压: {stats.get('net_accumulation', 0)}, 收敛率: {stats.get('convergence_rate', 0)}%\n"
                            )
                        elif isinstance(cdata, dict) and "series" in cdata:
                            answer_parts.append("  - 时间序列已生成（略）\n")

                if result.get('tool') == 'groupby_aggregate' and isinstance(tool_result, dict):
                    rows = tool_result.get('rows') or []
                    group_by = tool_result.get('group_by') or []
                    if rows:
                        label = " / ".join(group_by) if isinstance(group_by, list) else str(group_by)
                        answer_parts.append(f"- 分组维度: {label}\n")
                        top_rows = rows[:20]
                        if 'failure_rate' in top_rows[0]:
                            answer_parts.append("失败率Top：\n")
                            for r in top_rows:
                                key = " / ".join([str(r.get(c)) for c in group_by]) if isinstance(group_by, list) and group_by else str(r.get('group') or r.get(label) or '')
                                answer_parts.append(
                                    f"- {key}: 失败率 {r.get('failure_rate')}% (失败 {r.get('failure', 0)} / 总计 {r.get('total', 0)})\n"
                                )
                        else:
                            answer_parts.append("Top 分布：\n")
                            sort_by = (tool_result.get('summary') or {}).get('sort_by')
                            for r in top_rows:
                                key = " / ".join([str(r.get(c)) for c in group_by]) if isinstance(group_by, list) and group_by else str(r.get('group') or '')
                                answer_parts.append(f"- {key}: {r.get(sort_by) if sort_by in r else r}\n")

                # 添加风险分析
                if 'risk_items' in tool_result:
                    top_risks = tool_result['risk_items'][:5]
                    answer_parts.append(f"Top 5 高风险项目：\n")
                    for item in top_risks:
                        answer_parts.append(
                            f"- {item['name']}: 风险评分 {item['risk_score']}, "
                            f"缺陷数 {item['defect_count']}\n"
                        )
                    data_visualizations.append({
                        'type': 'risk',
                        'data': top_risks
                    })

                # 添加对比结果
                if 'comparisons' in tool_result:
                    for comp in tool_result['comparisons']:
                        answer_parts.append(
                            f"- {comp['name']}: {comp['metrics']}\n"
                        )

                if 'rows' in tool_result and result.get('tool') == 'analyze_test_run':
                    summary = tool_result.get('summary') or {}
                    answer_parts.append(
                        f"- 总测试执行数: {summary.get('overall_total', 0)}\n"
                        f"- 失败数: {summary.get('overall_failure', 0)}\n"
                        f"- 总体失败率: {summary.get('overall_failure_rate', 0)}%\n"
                    )
                    all_rows = tool_result.get('rows', []) or []
                    overall_total = int(summary.get('overall_total') or 0)
                    ql = (question or '').lower()
                    min_total = 20 if overall_total >= 1000 else 5
                    if any(k in ql for k in ['经常', '稳定', '反复', '高频']):
                        min_total = max(min_total, 30 if overall_total >= 1000 else 8)
                    rows_with_min = [r for r in all_rows if int(r.get('total') or 0) >= min_total]
                    top_source = rows_with_min if rows_with_min else all_rows
                    top_rows = sorted(top_source, key=lambda r: (r.get('failure_rate', 0), r.get('total', 0)), reverse=True)[:5]
                    if top_rows:
                        answer_parts.append("失败率Top 5：\n")
                        for r in top_rows:
                            answer_parts.append(
                                f"- {r.get('group')}: 失败率 {r.get('failure_rate')}% (总计 {r.get('total')})\n"
                            )
                            status_keys = [k for k in r.keys() if k not in {"group", "total", "failure_rate"}]
                            numeric_status = []
                            for k in status_keys:
                                v = r.get(k)
                                if isinstance(v, (int, float)) and v:
                                    numeric_status.append((k, int(v)))
                            numeric_status = sorted(numeric_status, key=lambda x: x[1], reverse=True)[:4]
                            if numeric_status:
                                brief = ", ".join([f"{k}:{v}" for k, v in numeric_status])
                                answer_parts.append(f"  - 状态分布: {brief}\n")

                if result.get('tool') == 'correlate_defects_tests' and 'top' in tool_result:
                    top = tool_result.get('top') or []
                    answer_parts.append("缺陷-测试联动 Top：\n")
                    for row in top[:5]:
                        answer_parts.append(
                            f"- {row.get('project')} / {row.get('week')}: 缺陷 {row.get('defect_count')}, "
                            f"失败率 {row.get('failure_rate')}% (测试 {row.get('test_total')}), "
                            f"risk_index {row.get('risk_index')}\n"
                        )

                if result.get('tool') == 'analyze_matrix_distribution' and 'distribution' in tool_result:
                    total = tool_result.get('total', 0)
                    dist = tool_result.get('distribution') or []
                    answer_parts.append(f"- 缺陷总数（用于统计）：{total}\n")
                    if dist:
                        answer_parts.append("Matrix 分布：\n")
                        for r in dist:
                            answer_parts.append(f"- {r.get('matrix')}: {r.get('count')} ({r.get('ratio')}%)\n")

                if result.get('tool') == 'analyze_matrix_aida_hotspots' and 'matrices' in tool_result:
                    total = tool_result.get('total', 0)
                    matrices = tool_result.get('matrices') or []
                    answer_parts.append(f"- 缺陷总数（用于统计）：{total}\n")
                    if matrices:
                        for m in matrices:
                            answer_parts.append(f"\nMatrix {m.get('matrix')}（{m.get('matrix_total')} 条，占 {m.get('matrix_share')}%）：\n")
                            for a in (m.get('top_aidas') or []):
                                answer_parts.append(
                                    f"- {a.get('aida')}: {a.get('count')}（占该矩阵 {a.get('ratio_in_matrix')}%）\n"
                                )
                                samples = a.get('samples') or []
                                if samples:
                                    for s in samples:
                                        answer_parts.append(
                                            f"  - {s.get('id')}: {s.get('title')} ({s.get('project')}, {s.get('creation_time')})\n"
                                        )

                if result.get('tool') == 'analyze_topissue_hotlist' and 'rows' in tool_result:
                    rows = tool_result.get('rows') or []
                    total = tool_result.get('total', 0)
                    answer_parts.append(f"- TopIssue 总数（用于统计）：{total}\n")
                    if rows:
                        answer_parts.append("TopIssue Hotlist：\n")
                        for r in rows[:20]:
                            answer_parts.append(
                                f"- {r.get('id')}: {r.get('title')} (score={r.get('score')}, {r.get('project')}, {r.get('matrix')}, {r.get('aida')})\n"
                            )

                if result.get('tool') == 'analyze_longrunner_hotlist' and 'rows' in tool_result:
                    rows = tool_result.get('rows') or []
                    total = tool_result.get('total', 0)
                    answer_parts.append(f"- LongRunner 总数（用于统计）：{total}\n")
                    if rows:
                        answer_parts.append("LongRunner Hotlist：\n")
                        for r in rows[:20]:
                            answer_parts.append(
                                f"- {r.get('id')}: {r.get('title')} ({r.get('days')} 天, {r.get('project')}, {r.get('matrix')}, {r.get('status')})\n"
                            )

                if result.get('tool') == 'analyze_tester_findings' and 'top_testers' in tool_result:
                    total_defects = tool_result.get('total_defects', 0)
                    testers = tool_result.get('top_testers') or []
                    answer_parts.append(f"- 缺陷总数（用于统计）：{total_defects}\n")
                    if testers:
                        answer_parts.append("Top tester：\n")
                        for idx, t in enumerate(testers[:10]):
                            answer_parts.append(
                                f"- {t.get('tester')}: {t.get('defect_count')} 条（占 {t.get('share')}%），"
                                f"TopIssue {t.get('topissue_count')} 条（{t.get('topissue_ratio')}%）\n"
                            )
                            if t.get('top_projects'):
                                answer_parts.append(f"  - 主要项目: {t.get('top_projects')}\n")
                            if t.get('top_aidas'):
                                answer_parts.append(f"  - 主要AIDA: {t.get('top_aidas')}\n")
                            if t.get('samples'):
                                answer_parts.append("  - 代表性缺陷样本:\n")
                                sample_cap = 8 if idx == 0 and len(t.get('samples') or []) > 3 else 3
                                for s in (t.get('samples') or [])[:sample_cap]:
                                    answer_parts.append(
                                        f"    - {s.get('id')}: {s.get('title')} "
                                        f"({s.get('project')}, {s.get('severity')}, {s.get('matrix')}, {s.get('creation_time')})\n"
                                    )

                # 添加统计摘要
                if 'total_records' in tool_result:
                    answer_parts.append(f"- 总记录数: {tool_result['total_records']}\n")

                # 添加洞察
                if tool_output.get('insights'):
                    insights.extend(tool_output['insights'])
            else:
                error_msg = tool_output.get('error')
                if error_msg:
                    answer_parts.append(f"\n**{result['description']}**\n- 执行失败: {error_msg}\n")

        if 'strategy' in (context.get('intents') or []):
            overall_failure_rate = None
            top_failure_weeks: List[Dict[str, Any]] = []
            severe_rate = None
            top_risk_projects: List[Dict[str, Any]] = []
            top_matrices: List[Dict[str, Any]] = []
            topissue_total = None
            longrunner_total = None

            for r in execution_results:
                out = r.get('result') or {}
                if not out.get('success'):
                    continue
                tool = r.get('tool')
                res = out.get('result') or {}

                if tool == 'analyze_test_run' and isinstance(res, dict):
                    summary = res.get('summary') or {}
                    if overall_failure_rate is None:
                        overall_failure_rate = summary.get('overall_failure_rate')
                    rows = res.get('rows') or []
                    if rows and (not top_failure_weeks) and any(k in (r.get('description') or '') for k in ['按周', 'week']):
                        top_failure_weeks = sorted(rows, key=lambda x: x.get('failure_rate', 0), reverse=True)[:3]

                if tool == 'defect_explore_kpis' and isinstance(res, dict):
                    if severe_rate is None:
                        severe_rate = res.get('severe_rate')

                if tool == 'analyze_risk' and isinstance(res, dict):
                    items = res.get('risk_items') or []
                    if items and not top_risk_projects:
                        top_risk_projects = items[:5]

                if tool == 'analyze_matrix_aida_hotspots' and isinstance(res, dict):
                    matrices = res.get('matrices') or []
                    if matrices and not top_matrices:
                        top_matrices = matrices[:3]

                if tool == 'analyze_topissue_hotlist' and isinstance(res, dict):
                    if topissue_total is None:
                        topissue_total = res.get('total')

                if tool == 'analyze_longrunner_hotlist' and isinstance(res, dict):
                    if longrunner_total is None:
                        longrunner_total = res.get('total')

            answer_parts.append("\n**测试策略建议（基于上述统计）**\n")
            if overall_failure_rate is not None:
                answer_parts.append(f"- 测试侧现状：总体失败率 {overall_failure_rate}%（以此作为回归稳定性基线）\n")
                if top_failure_weeks:
                    wk = top_failure_weeks[0]
                    answer_parts.append(f"- 优先攻坚：失败率Top 周为 {wk.get('group')}（{wk.get('failure_rate')}%，总计 {wk.get('total')}）\n")
                    answer_parts.append("- 动作：回溯该周的环境/数据/版本/用例变更，建立“波峰周专项回归包”，将波峰周常见失败固化为准入门槛\n")
            if severe_rate is not None:
                answer_parts.append(f"- 缺陷侧现状：严重缺陷率 {severe_rate}%（用来定义发布门槛与P0范围）\n")
            if top_risk_projects:
                best = top_risk_projects[0]
                answer_parts.append(f"- 风险聚焦：最高风险项目为 {best.get('name')}（风险评分 {best.get('risk_score')}，缺陷数 {best.get('defect_count')}）\n")
                answer_parts.append("- 动作：对该项目建立“必测清单”（核心路径E2E + 关键接口/异常恢复），并优先分配自动化资源\n")
            if top_matrices:
                m0 = top_matrices[0]
                answer_parts.append(f"- 热点定位：矩阵 {m0.get('matrix')} 占比 {m0.get('matrix_share')}%（{m0.get('matrix_total')} 条）\n")
                top_aidas = (m0.get('top_aidas') or [])[:2]
                if top_aidas:
                    a0 = top_aidas[0]
                    answer_parts.append(f"- 热点AIDA：{a0.get('aida')}（{a0.get('count')} 条，占该矩阵 {a0.get('ratio_in_matrix')}%）\n")
                answer_parts.append("- 动作：以“矩阵×AIDA”作为用例优先级，优先补齐热点场景的边界/并发/恢复类用例\n")
            if topissue_total is not None or longrunner_total is not None:
                if topissue_total is not None:
                    answer_parts.append(f"- 缺陷治理：TopIssue 总数 {topissue_total}\n")
                if longrunner_total is not None:
                    answer_parts.append(f"- 积压治理：LongRunner 总数 {longrunner_total}\n")
                answer_parts.append("- 动作：把 TopIssue 作为“回归不放过”的红线；把 LongRunner 作为“流程卡点”治理，明确阻塞原因与处置策略\n")

            answer_parts.append("- 度量闭环：每周追踪 总体失败率/失败率Top周、严重缺陷率、TopIssue 与 LongRunner 数 的变化，并用回归门槛和准入规则固化\n")

        if 'case' in (context.get('intents') or []) and any(k in (question or '').lower() for k in ['case', '用例', 'testcase', 'test case']):
            case_top: List[Dict[str, Any]] = []
            case_group_cols: List[str] = []
            for r in execution_results:
                if r.get('tool') != 'groupby_aggregate':
                    continue
                out = r.get('result') or {}
                if not out.get('success'):
                    continue
                res = out.get('result') or {}
                rows = res.get('rows') or []
                if rows and 'failure_rate' in rows[0]:
                    case_top = rows[:10]
                    gb = res.get('group_by') or []
                    case_group_cols = gb if isinstance(gb, list) else [str(gb)]
                    break

            if case_top:
                answer_parts.append("\n**结论与建议（按用例失败率）**\n")
                top1 = case_top[0]
                label = " / ".join([str(top1.get(c)) for c in case_group_cols]) if case_group_cols else str(top1.get('group') or '')
                answer_parts.append(f"- 最容易出错用例: {label}（失败率 {top1.get('failure_rate')}%，失败 {top1.get('failure')} / 总计 {top1.get('total')}）\n")
                answer_parts.append("- 落地做法：把 Top 用例纳入“准入回归包”，并对 Top 用例补齐稳定性/重试/环境依赖的诊断信息（日志、前置条件、数据集）\n")
                answer_parts.append("- 排查顺序：先区分环境不稳定（同用例跨项目/跨周波动）与真实功能缺陷（同用例持续高失败率）\n")
                answer_parts.append("- 进一步增强：如果 tests 数据里有 project/FV/AIDA，可对 Top 用例再做 project×case 或 FV×case 交叉，定位失败集中区域\n")

        # 3. 添加相关知识
        if knowledge_context:
            answer_parts.append(f"\n**参考知识**\n{knowledge_context}\n")

        # 4. 添加历史上下文
        if relevant_history:
            answer_parts.append(f"\n**相关历史对话**\n")
            for hist in relevant_history[:2]:
                answer_parts.append(f"- {hist['content'][:100]}...\n")

        # 5. 综合洞察和建议
        if insights:
            answer_parts.append(f"\n**关键洞察**\n")
            for i, insight in enumerate(insights[:5], 1):
                answer_parts.append(f"{i}. {insight}\n")

        # 6. 建议和后续行动
        answer_parts.append(f"\n**建议**\n")
        answer_parts.append(self._generate_recommendations(context, execution_results))

        answer_text = ''.join(answer_parts)
        critic_evidence_bundle = _build_critic_evidence_bundle(context, execution_results)
        if critic_evidence_bundle:
            context["critic_evidence_bundle"] = critic_evidence_bundle
            context["evidence_bundle"] = critic_evidence_bundle

        if os.getenv("AGENT_CRITIC_ENABLED") == "1":
            try:
                from agent.evaluation.agent_critic import CriticPipeline, RuleBasedCritic

                validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
                datasets_meta = (context or {}).get("datasets") or {}
                primary = (context or {}).get("primary_dataset") or ("defects" if "defects" in datasets_meta else next(iter(datasets_meta.keys()), None))
                primary_meta = datasets_meta.get(primary) if primary else None
                tool_size = (primary_meta or {}).get("tool_size") if isinstance(primary_meta, dict) else None
                has_success = any(isinstance((r or {}).get("result"), dict) and (r["result"].get("success") is True) for r in (execution_results or []))
                has_failure = any(isinstance((r or {}).get("result"), dict) and (r["result"].get("success") is False) for r in (execution_results or []))
                if validation_enabled and ((tool_size == 0) or (has_failure and not has_success)):
                    context["refusal"] = {
                        "should_refuse": True,
                        "reason": "数据不足或关键工具执行失败，无法给出可靠结论",
                    }

                pipeline = CriticPipeline([RuleBasedCritic()])
                critic_results = pipeline.run(
                    question=question,
                    context=context,
                    execution_results=execution_results,
                    draft_text=answer_text,
                )
                refusal = next((r for r in critic_results if getattr(r, "should_refuse", False)), None)
                critic_block = CriticPipeline.render(critic_results)
                if not critic_block:
                    critic_block = "\n**校验与质疑**\n- [info] 未发现明显风险提示缺失或工具异常。\n"
                if refusal is not None:
                    reason = getattr(refusal, "refusal_reason", "") or "数据不足"
                    context["refusal"] = {
                        "should_refuse": True,
                        "reason": str(reason),
                        "source": "critic",
                    }
                    answer_text = f"抱歉，当前无法给出可靠结论：{reason}\n" + critic_block
                    try:
                        trace = (context or {}).get("analysis_trace")
                        if isinstance(trace, dict):
                            trace["refused"] = True
                            trace["refusal_reason"] = str(reason)
                    except Exception:
                        pass
                else:
                    answer_text = answer_text + critic_block
            except Exception as e:
                answer_text = answer_text + f"\n**校验与质疑**\n- [warning] 校验流程执行失败：{e}\n"

        return {
            'text': answer_text,
            'insights': insights,
            'visualizations': data_visualizations,
            'tools_used': [r['tool'] for r in execution_results],
            'context': context
        }

    def _generate_recommendations(self, context: Dict, execution_results: List[Dict]) -> str:
        """生成改进建议"""
        recommendations = []

        intents = context.get('intents', [])

        # 根据分析结果生成建议
        for result in execution_results:
            tool_output = result.get('result') or {}
            if tool_output.get('success'):
                tool_result = tool_output.get('result') or {}

                # 趋势建议
                if 'summary' in tool_result:
                    summary = tool_result['summary']
                    if summary.get('direction') == '上升':
                        recommendations.append(
                            "- 缺陷数量呈上升趋势，建议加强代码审查和测试覆盖率\n"
                        )

                # 风险建议
                if 'risk_items' in tool_result:
                    risk_items = tool_result.get('risk_items') or []
                    if risk_items:
                        top_risk = risk_items[0]
                        if top_risk.get('risk_score', 0) > 70:
                            recommendations.append(
                                f"- 最高风险项目 '{top_risk.get('name')}' 评分 {top_risk.get('risk_score')}，"
                                f"建议优先处理其中的 TopIssue\n"
                            )

                # 对比建议
                if 'comparisons' in tool_result:
                    recommendations.append(
                        "- 建议对比表现较好项目的实践，推广到其他项目\n"
                    )

        # 通用建议
        if not recommendations:
            recommendations.append("- 建议定期监控关键指标，及时发现和解决问题\n")
            recommendations.append("- 加强团队协作和知识分享\n")

        return ''.join(recommendations)

    def get_enhanced_system_prompt(self, data_context: str = "") -> str:
        """获取增强的系统提示词 - 使用新的统一模板"""
        try:
            from prompt_templates import get_system_prompt
            return get_system_prompt(self.dashboard_type, data_context)
        except ImportError:
            # 降级处理：如果 prompt_templates 不存在，使用简化版
            logger.warning("prompt_templates 未找到，使用简化版 system prompt")
            base_prompt = f"""你是 BMW DTSV 数据分析助手。"""
            if data_context:
                base_prompt += f"\n\n数据上下文:\n{data_context}"
            return base_prompt

    def get_tool_schemas_for_llm(self) -> List[Dict]:
        """获取工具的 schema 格式，用于 LLM 函数调用"""
        schemas = []

        for tool_name, schema in self.tool_executor.get_tool_schema().items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": schema['name'],
                    "description": schema['description'],
                    "parameters": schema['parameters']
                }
            })

        return schemas


def create_agent(dashboard_type: str = 'general', llm: Any = None, db_path: Optional[str] = None) -> IntelligentAgent:
    """创建智能 Agent 实例"""
    return IntelligentAgent(dashboard_type, llm=llm, db_path=db_path)


def create_agent_for_defect() -> IntelligentAgent:
    """创建缺陷分析专用 Agent"""
    return IntelligentAgent('defect')


def create_agent_for_test() -> IntelligentAgent:
    """创建测试分析专用 Agent"""
    return IntelligentAgent('test')


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'IntelligentAgent',
    'create_agent',
    'create_agent_for_defect',
    'create_agent_for_test',
    'ToolExecutor',
    'IntelligentContextManager',
    'ConversationMemory',
    'KnowledgeBase',
    'TaskPlanner'
]


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("智能 Agent 系统")
    print("=" * 50)

    # 创建测试数据
    test_data = pd.DataFrame({
        '_id': range(1, 101),
        'tproject': ['Project_A'] * 50 + ['Project_B'] * 30 + ['Project_C'] * 20,
        'severity_group': ['Critical'] * 10 + ['Major'] * 40 + ['Minor'] * 50,
        'category': ['Functional'] * 60 + ['Performance'] * 25 + ['UI'] * 15,
        'topissue': ['TopIssue'] * 20 + [''] * 80,
        'matrix_display': ['1A'] * 5 + ['1B'] * 10 + ['1C'] * 15 + ['2A'] * 30 + ['2B'] * 40,
        'tcreationtime': pd.date_range('2025-01-01', periods=100, freq='D')
    })

    # 创建 Agent
    agent = create_agent_for_defect()

    print("\n测试问题:")
    questions = [
        "分析缺陷趋势",
        "哪个项目的风险最高？",
        "对比 Project_A 和 Project_B 的情况"
    ]

    for question in questions:
        print(f"\n问题: {question}")
        print("-" * 50)

        result = agent.process(question, test_data)

        print(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])

        if result['insights']:
            print("\n关键洞察:")
            for insight in result['insights']:
                print(f"- {insight}")

        print(f"\n使用的工具: {result['tools_used']}")
