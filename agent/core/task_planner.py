import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd


logger = logging.getLogger(__name__)


class TaskPlanner:
    """任务规划器 - 分解复杂任务"""

    def __init__(
        self,
        tool_executor: Any,
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

    def _apply_smart_tool_selector(self, query: str, context: Dict[str, Any], steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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

            intents = [str(item) for item in ((context or {}).get("intents") or []) if str(item).strip()]
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
                key=lambda step: (
                    priority_index.get(str((step or {}).get("tool") or "").strip(), 999),
                    int((step or {}).get("step") or 0),
                ),
            )

            normalized_steps: List[Dict[str, Any]] = []
            for idx, step in enumerate(reordered, start=1):
                normalized = dict(step or {})
                normalized["step"] = idx
                normalized_steps.append(normalized)

            if isinstance(context, dict):
                context["smart_tool_selector"] = {
                    "enabled": True,
                    "applied": True,
                    "mapped_priority": mapped_priority,
                    "recommendations": mapped_details,
                }
            return normalized_steps
        except Exception as exc:
            logger.warning(f"Smart tool selector application failed: {exc}")
            if isinstance(context, dict):
                context["smart_tool_selector"] = {
                    "enabled": bool(self.tool_selector),
                    "applied": False,
                    "error": str(exc),
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

            intents = [str(item) for item in ((context or {}).get("intents") or []) if str(item).strip()]
            self.tool_selector.record_execution(
                tool_name=str(tool_name or ""),
                success=success,
                execution_time=max(0.0, float(duration_ms) / 1000.0),
                result_quality=1.0 if success else 0.0,
                data_size=int(data_size),
                intents=intents,
                error_message=error_message,
            )
        except Exception as exc:
            logger.debug(f"Smart tool selector feedback skipped: {exc}")

    def _is_empty_tool_output(self, result: Dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("success") is not True:
            return False
        payload = result.get("result")
        if payload is None:
            return True
        if isinstance(payload, dict):
            rows = payload.get("rows")
            if isinstance(rows, list) and len(rows) == 0:
                return True
            data = payload.get("data")
            if isinstance(data, list) and len(data) == 0:
                return True
            count = payload.get("count")
            if isinstance(count, (int, float)) and int(count) == 0:
                return True
        if isinstance(payload, list) and len(payload) == 0:
            return True
        return False

    def _build_replan_steps(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        replan_depth: int,
    ) -> List[Dict[str, Any]]:
        enabled = str(os.getenv("AGENT_REPLAN_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no"}
        if not enabled:
            return []

        try:
            max_replans = int(os.getenv("AGENT_MAX_REPLANS", "1") or 1)
        except Exception:
            max_replans = 1
        max_replans = max(0, max_replans)
        if replan_depth >= max_replans:
            return []

        if not isinstance(result, dict):
            return []

        failed_tool = str((step or {}).get("tool") or "").strip()
        if not failed_tool or failed_tool == "statistical_summary":
            return []

        params = dict((step or {}).get("params") or {})
        dataset = params.get("dataset") or (context or {}).get("primary_dataset")
        replan_steps: List[Dict[str, Any]] = []

        failed = result.get("success") is False
        empty_success = self._is_empty_tool_output(result)

        if not failed and not empty_success:
            return []

        error_text = str(result.get("error") or "")
        schema_like_error = bool(re.search(r"column|schema|field|列|字段|参数", error_text, flags=re.IGNORECASE))
        tools = (getattr(self.tool_executor, "tools", {}) or {}) if hasattr(self.tool_executor, "tools") else {}

        if failed and schema_like_error and ("describe_dataset" in tools) and failed_tool != "describe_dataset":
            desc_params = {"dataset": dataset} if dataset else {}
            replan_steps.append(
                {
                    "step": len(replan_steps) + 1,
                    "tool": "describe_dataset",
                    "description": "重规划：先读取数据集结构，修复字段/参数不匹配",
                    "params": desc_params,
                }
            )

        summary_params = {"dataset": dataset} if dataset else {}
        replan_steps.append(
            {
                "step": len(replan_steps) + 1,
                "tool": "statistical_summary",
                "description": "重规划：失败/空结果后回退到统计摘要，保证返回可解释结果",
                "params": summary_params,
            }
        )
        return replan_steps

    def plan(self, query: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """规划任务步骤"""
        steps = []

        intents = context.get("intents", [])
        entities = context.get("entities", {})
        primary_dataset = context.get("primary_dataset", "defects")
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
            match = re.search(r"(top|前)\s*(\d{1,3})", q)
            if match:
                try:
                    value = int(match.group(2))
                    return max(1, min(200, value))
                except Exception:
                    return default
            return default

        def _choose_case_col(available_cols: List[str]) -> Optional[str]:
            if not available_cols:
                return None
            cols = set(available_cols)
            for col in ["test_case", "testcase", "case", "case_id", "case_name", "test_name", "test_id", "name", "title"]:
                if col in cols:
                    return col
            for col in available_cols:
                lower = col.lower()
                if "case" in lower and ("id" in lower or "name" in lower):
                    return col
            for col in available_cols:
                lower = col.lower()
                if lower in {"test_id", "test_name"}:
                    return col
            return None

        wants_semantic = any(k in q for k in ["口径", "定义", "字段", "含义", "怎么计算", "如何计算", "calculation", "definition", "metric"])
        semantic_catalog_enabled = (os.getenv("AGENT_SEMANTIC_CATALOG_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no", "off"}
        if (semantic_catalog_enabled and wants_semantic) and (
            hasattr(self.tool_executor, "tools") and ("consult_semantic_catalog" in (self.tool_executor.tools or {}))
        ):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "consult_semantic_catalog",
                    "description": "检索语义目录（口径/字段/误用风险）",
                    "params": {"question": query, "dashboard": str(context.get("dashboard_type") or "")},
                }
            )

        wants_duplicate = any(k in q for k in ["重复", "相似", "类似", "已知问题", "known issue", "duplicate"])
        if wants_duplicate and ("defects" in (context.get("datasets") or {})) and (
            hasattr(self.tool_executor, "tools") and ("search_similar_issues" in (self.tool_executor.tools or {}))
        ):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "search_similar_issues",
                    "description": "检索相似缺陷/已知问题（重复提票检测）",
                    "params": {"query": query, "top_k": 8, "dataset": "defects", "cache_key": "defects"},
                }
            )

        if ("tester" in intents) and primary_dataset != "tests" and (
            hasattr(self.tool_executor, "tools") and ("match_tester_tickets" in (self.tool_executor.tools or {}))
        ):
            person = None
            match = re.search(r"([\u4e00-\u9fff]{2,6})\s*(?:提|报|发现)", query)
            if match:
                person = match.group(1)
            if not person:
                match = re.match(r"^\s*([\u4e00-\u9fff]{2,6})", query)
                if match:
                    person = match.group(1)
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

        if (("sql" in intents) or any(k in q for k in ["sql", "sqlite", "数据库", "db"])) and (
            hasattr(self.tool_executor, "tools") and ("query_sqlite_with_fix" in (self.tool_executor.tools or {}))
        ):
            if hasattr(self.tool_executor, "tools") and ("get_db_profile" in (self.tool_executor.tools or {})):
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "get_db_profile",
                        "description": "获取数据库画像（字段/高频值/空值率）以提升SQL生成准确率",
                        "params": {"top_n": 5, "sample_columns": 20},
                    }
                )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "query_sqlite_with_fix",
                    "description": "将自然语言问题转为SQLite只读查询并执行（失败自动纠错）",
                    "params": {"question": query, "limit": 200},
                }
            )
            return steps

        wants_recent_weeks = any(k in q for k in ["最近", "近", "过去"]) and ("周" in q or "week" in q)
        wants_defect_test_joint = any(k in q for k in ["缺陷", "defect", "bug"]) and any(k in q for k in ["测试", "test", "执行", "run"])
        if wants_recent_weeks and wants_defect_test_joint and ("defects" in (context.get("datasets") or {})) and ("tests" in (context.get("datasets") or {})) and (
            hasattr(self.tool_executor, "tools") and ("analyze_project_recent_weeks" in (self.tool_executor.tools or {}))
        ):
            project = None
            if isinstance(entities.get("projects"), list) and entities.get("projects"):
                project = str(entities.get("projects")[0] or "").strip()
            if not project:
                match = re.search(r"\\b(idcevo|idc|mgu|app|rsu)\\b", q)
                if match:
                    project = match.group(1)
            if project:
                n_weeks = 4
                for number in (entities.get("numbers") or []):
                    try:
                        if 1 <= int(number) <= 26:
                            n_weeks = int(number)
                            break
                    except Exception:
                        continue
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_project_recent_weeks",
                        "description": f"评估项目 {project} 最近{n_weeks}周缺陷发现与测试失败率是否恶化",
                        "params": {"project": project, "weeks": n_weeks},
                    }
                )
                return steps

        if ("tests" in (context.get("datasets") or {})) and ("test" in intents or "execution" in intents) and (
            ("project" in intents) or ("各项目" in q) or ("项目" in q)
        ) and any(k in q for k in ["执行情况", "执行状态", "通过情况", "状态", "pass", "passed", "fail", "failed"]):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_test_run",
                    "description": "按项目对比测试执行状态与失败率",
                    "params": {"group_by": "project", "dataset": "tests"},
                }
            )
            return steps

        if ("tests" in (context.get("datasets") or {})) and ("tester" in intents) and ("test" in intents or "execution" in intents) and any(
            k in q for k in ["测试人员", "测试员", "tester", "情况", "如何", "怎么样", "who"]
        ):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_test_run",
                    "description": "按测试人员统计测试执行状态与失败率",
                    "params": {"group_by": "tester", "dataset": "tests"},
                }
            )
            return steps

        if ("tester" in intents) and ("defects" in (context.get("datasets") or {})) and any(k in q for k in ["测试人员", "tester", "发现人", "谁发现", "不同测试人员"]):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_tester_findings",
                    "description": "按 tester 统计缺陷发现分布与严重/TopIssue 占比",
                    "params": {"top_n": 15, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_dashboard",
                    "description": "补充 tester 相关看板图表（严重率/效率）",
                    "params": {"question": query, "max_items": 15},
                }
            )
            return steps

        wants_case_ranking = any(k in q for k in ["哪些", "top", "前", "容易", "出错", "失败率"]) or ("case" in q)
        if wants_case_ranking and ("test" in intents or "case" in intents) and ("tests" in (context.get("datasets") or {})) and any(
            k in q for k in ["case", "用例", "testcase", "test case"]
        ):
            tests_meta = (context.get("datasets") or {}).get("tests") or {}
            case_col = _choose_case_col(tests_meta.get("available_columns") or [])
            if not case_col:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_test_run",
                        "description": "缺少 case 字段，退化为按周统计测试失败率",
                        "params": {"group_by": "week", "dataset": "tests"},
                    }
                )
                return steps

            top_n = _extract_top_n(20)
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "groupby_aggregate",
                    "description": f"按用例维度统计失败率（{case_col}）",
                    "params": {
                        "dataset": "tests",
                        "group_by": case_col,
                        "aggregations": [{"op": "failure_rate", "column": "", "name": "failure_rate"}],
                        "top_n": top_n,
                        "sort_by": "failure_rate",
                        "descending": True,
                        "status_column": "run_status",
                    },
                }
            )
            return steps

        if "strategy" in intents:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_dashboard",
                    "description": "汇总看板业务图表指标（用于策略输入）",
                    "params": {
                        "question": query,
                        "max_items": 20,
                        "include_inflow_outflow": ("throughput" in intents) or any(k in (query or "").lower() for k in ["inflow", "outflow", "收敛", "吞吐", "净积压"]),
                        "include_longrunner": any(k in (query or "").lower() for k in ["long runner", "longrunner", "长周期", "阶段耗时"]),
                    },
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_kpis",
                    "description": "生成看板 KPI 概览",
                    "params": {"dataset": "defects"},
                }
            )
            if "tests" in (context.get("datasets") or {}):
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_test_run",
                        "description": "分析测试失败率（按周）",
                        "params": {"group_by": "week", "dataset": "tests"},
                    }
                )
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_test_run",
                        "description": "分析测试失败率（按项目）",
                        "params": {"group_by": "project", "dataset": "tests"},
                    }
                )
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "correlate_defects_tests",
                        "description": "关联缺陷与测试（发现高风险项目）",
                        "params": {"top_n": 10},
                    }
                )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_risk",
                    "description": "分析风险（按project维度）",
                    "params": {"dimension": "project", "top_n": 10, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_matrix_aida_hotspots",
                    "description": "分析 matrix×AIDA 热点（用于测试重点）",
                    "params": {"top_matrices": 10, "top_aidas": 8, "sample_tickets": 2, "include_unknown": True, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_topissue_hotlist",
                    "description": "输出 TopIssue 高风险票据清单",
                    "params": {"top_n": 15, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_longrunner_hotlist",
                    "description": "输出 LongRunner 票据清单",
                    "params": {"top_n": 15, "dataset": "defects"},
                }
            )
            return steps

        if ("auto" in intents) and auto_strong:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_dashboard",
                    "description": "汇总看板业务图表指标（按问题聚焦）",
                    "params": {
                        "question": query,
                        "max_items": 15,
                        "include_inflow_outflow": ("throughput" in intents) or any(k in (query or "").lower() for k in ["inflow", "outflow", "收敛", "吞吐", "净积压"]),
                        "include_longrunner": any(k in (query or "").lower() for k in ["long runner", "longrunner", "长周期", "阶段耗时"]),
                    },
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_kpis",
                    "description": "生成看板 KPI 概览",
                    "params": {"dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_risk",
                    "description": "分析风险（按project维度）",
                    "params": {"dimension": "project", "top_n": 10, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_trend",
                    "description": "分析趋势（按week分组）",
                    "params": {"group_by": "week", "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_trend",
                    "description": "按 FV 统计 Top 分布",
                    "params": {"group_by": "fv", "metric": "count", "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_trend",
                    "description": "按 AIDA 统计 Top 分布",
                    "params": {"group_by": "aida", "metric": "count", "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_trend",
                    "description": "按 Solution Cluster/Domain 统计 Top 分布",
                    "params": {"group_by": "domain", "metric": "count", "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_matrix_distribution",
                    "description": "分析缺陷矩阵分布",
                    "params": {"include_unknown": True, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_matrix_aida_hotspots",
                    "description": "分析 matrix×AIDA 热点",
                    "params": {"top_matrices": 15, "top_aidas": 5, "sample_tickets": 3, "include_unknown": True, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_tester_findings",
                    "description": "分析发现问题最多的 tester",
                    "params": {"top_n": 10, "sample_per_tester": 5, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_topissue_hotlist",
                    "description": "输出 TopIssue 高风险票据清单",
                    "params": {"top_n": 20, "dataset": "defects"},
                }
            )
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_longrunner_hotlist",
                    "description": "输出 LongRunner 票据清单",
                    "params": {"top_n": 20, "dataset": "defects"},
                }
            )
            if "tests" in (context.get("datasets") or {}):
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_test_run",
                        "description": "分析测试运行状态与失败率",
                        "params": {"group_by": "week", "dataset": "tests"},
                    }
                )
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "correlate_defects_tests",
                        "description": "关联缺陷与测试，发现高风险项目",
                        "params": {"top_n": 10},
                    }
                )
            return steps

        if "dashboard" in intents:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_dashboard",
                    "description": "汇总看板业务图表指标（按问题聚焦）",
                    "params": {
                        "question": query,
                        "max_items": 15,
                        "include_inflow_outflow": ("throughput" in intents) or any(k in (query or "").lower() for k in ["inflow", "outflow", "收敛", "吞吐", "净积压"]),
                        "include_longrunner": any(k in (query or "").lower() for k in ["long runner", "longrunner", "长周期", "阶段耗时"]),
                    },
                }
            )

        if "summary" in intents:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "defect_explore_kpis",
                    "description": "生成看板 KPI 概览",
                    "params": {"dataset": primary_dataset},
                }
            )

        if "trend" in intents:
            time_range = entities.get("time_range", "week")
            group_by = "week" if time_range == "week" else "month"
            steps.append(
                {
                    "step": 1,
                    "tool": "analyze_trend",
                    "description": f"分析趋势（按{group_by}分组）",
                    "params": {"group_by": group_by, "dataset": primary_dataset},
                }
            )

        if "risk" in intents and primary_dataset != "tests":
            dimension = entities.get("dimension", "project")
            top_n = 10
            if isinstance(entities.get("numbers"), list) and entities["numbers"]:
                top_n = max(1, min(int(entities["numbers"][0]), 50))
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_risk",
                    "description": f"分析风险（按{dimension}维度）",
                    "params": {"dimension": dimension, "top_n": top_n, "dataset": primary_dataset},
                }
            )

        if "comparison" in intents:
            if "projects" in entities and entities["projects"]:
                items = entities["projects"]
                auto_mode = None
            else:
                items = []
                auto_mode = "top_risk"
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "compare_items",
                    "description": "对比项目",
                    "params": {
                        "items": items,
                        "dimension": "project",
                        "_auto": auto_mode,
                        "dataset": primary_dataset,
                    },
                }
            )

        query_lower = (query or "").lower()
        aida_failure_focus = (
            ("aida" in intents)
            and (("case" in intents) or any(k in query_lower for k in ["容易出错", "出错", "失败最多", "问题类型", "什么样的问题", "哪类问题"]))
        )
        if aida_failure_focus:
            datasets_in_context = (context.get("datasets") or {}) if isinstance(context, dict) else {}
            if "tests" in datasets_in_context:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_test_run",
                        "description": "按 AIDA 分析测试失败率，定位容易出错模块",
                        "params": {"group_by": "aida", "dataset": "tests"},
                    }
                )
            if primary_dataset != "tests":
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_trend",
                        "description": "按 AIDA 统计问题分布（缺陷侧）",
                        "params": {"group_by": "aida", "metric": "count", "dataset": primary_dataset},
                    }
                )

        if "test" in intents:
            group_by = "week"
            if any(k in query_lower for k in ["按周", "按月", "week", "month", "cw", "calendar_week", "测试周"]):
                group_by = "week" if "month" not in query_lower else "month"
            else:
                dimension = str((entities or {}).get("dimension") or "").strip()
                if "tester" in intents or any(k in query_lower for k in ["测试人员", "测试员", "tester", "谁"]):
                    group_by = "tester"
                elif "fv" in intents or "feature team" in query_lower or "feature_team" in query_lower:
                    group_by = "fv"
                elif "aida" in intents or any(k in query_lower for k in ["功能", "模块", "service", "services"]):
                    group_by = "aida"
                elif dimension and dimension.lower() not in {"id", "_id", "test_id", "run_id", "mr_id"}:
                    group_by = dimension
                elif "project" in intents or "各项目" in query_lower or "项目" in query_lower or "project" in query_lower:
                    group_by = "project"
            planned_test_run = any(str(step.get("tool") or "").strip() == "analyze_test_run" for step in steps)
            if not planned_test_run:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_test_run",
                        "description": f"分析测试运行状态与失败率（按{group_by}分组）",
                        "params": {"group_by": group_by, "dataset": "tests"},
                    }
                )

        if "cross" in intents:
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "correlate_defects_tests",
                    "description": "关联缺陷与测试，发现高风险项目",
                    "params": {"top_n": 10},
                }
            )

        if "matrix" in intents and "aida" in intents and primary_dataset != "tests":
            query_lower = (query or "").lower()
            top_matrices = 10
            if any(k in query_lower for k in ["每个", "全部", "所有", "all"]):
                top_matrices = 30
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_matrix_aida_hotspots",
                    "description": "分析 matrix×AIDA 热点",
                    "params": {"top_matrices": top_matrices, "top_aidas": 5, "sample_tickets": 3, "include_unknown": True, "dataset": primary_dataset},
                }
            )
        elif "matrix" in intents and primary_dataset != "tests":
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_matrix_distribution",
                    "description": "分析缺陷矩阵分布",
                    "params": {"include_unknown": True, "dataset": primary_dataset},
                }
            )

        if (("distribution" in intents) or ("top" in intents)) and primary_dataset != "tests":
            handled = False
            if "aida" in intents:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_trend",
                        "description": "按 AIDA 统计 Top 分布",
                        "params": {"group_by": "aida", "metric": "count", "dataset": primary_dataset},
                    }
                )
                handled = True
            if "fv" in intents:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_trend",
                        "description": "按 FV 统计 Top 分布",
                        "params": {"group_by": "fv", "metric": "count", "dataset": primary_dataset},
                    }
                )
                handled = True
            if "domain" in intents:
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_trend",
                        "description": "按 Solution Cluster/Domain 统计 Top 分布",
                        "params": {"group_by": "domain", "metric": "count", "dataset": primary_dataset},
                    }
                )
                handled = True
            if (not handled) and entities.get("dimension"):
                dimension = str(entities.get("dimension") or "").strip()
                if dimension:
                    steps.append(
                        {
                            "step": len(steps) + 1,
                            "tool": "analyze_trend",
                            "description": f"按 {dimension} 统计 Top 分布",
                            "params": {"group_by": dimension, "metric": "count", "dataset": primary_dataset},
                        }
                    )

        if (("distribution" in intents) or ("top" in intents)) and primary_dataset == "tests" and ("test" not in intents):
            dimension = str((entities or {}).get("dimension") or "").strip() or "project"
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_trend",
                    "description": f"按 {dimension} 统计 Top 分布",
                    "params": {"group_by": dimension, "metric": "count", "dataset": "tests"},
                }
            )

        if "tester" in intents and primary_dataset != "tests":
            top_n = 10
            if isinstance(entities.get("numbers"), list) and entities["numbers"]:
                top_n = max(1, min(int(entities["numbers"][0]), 50))
            query_lower = (query or "").lower()
            sample_per_tester = 5
            if any(k in query_lower for k in ["都是什么", "详细", "列出", "列表", "明细", "all"]):
                sample_per_tester = 10
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "analyze_tester_findings",
                    "description": "分析发现问题最多的 tester",
                    "params": {"top_n": top_n, "sample_per_tester": sample_per_tester, "dataset": primary_dataset},
                }
            )

        if not steps:
            steps.append(
                {
                    "step": 1,
                    "tool": "statistical_summary",
                    "description": "生成数据摘要",
                    "params": {"dataset": primary_dataset},
                }
            )

        if isinstance(context, dict):
            steps = self._apply_smart_tool_selector(query=query, context=context, steps=steps)

        return steps

    def execute_plan(
        self,
        steps: List[Dict[str, Any]],
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        context: Optional[Dict[str, Any]] = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        _replan_depth: int = 0,
        _tracer: Any = None,
    ) -> List[Dict[str, Any]]:
        """执行计划"""
        results = []
        datasets_meta = (context or {}).get("datasets") or {}
        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        primary_dataset = (context or {}).get("primary_dataset") or ("defects" if isinstance(data, dict) and "defects" in data else None)

        total_steps = len(steps or [])
        for idx, step in enumerate(steps or [], start=1):
            tool_name = step["tool"]
            params = step.get("params", {})

            dataset_used: Optional[str] = None
            if isinstance(data, dict):
                tool = (getattr(self.tool_executor, "tools", {}) or {}).get(tool_name)
                if tool is not None and getattr(tool, "expects_datasets", lambda: False)():
                    dataset_used = "datasets"
                else:
                    dataset_used = params.get("dataset") or ("defects" if "defects" in data else next(iter(data.keys()), None))

            if tool_name == "compare_items":
                auto_mode = params.get("_auto")
                if (not params.get("items")) and auto_mode == "top_risk":
                    for previous in results:
                        if previous.get("tool") == "analyze_risk":
                            prev_out = previous.get("result") or {}
                            prev_res = prev_out.get("result") or {}
                            risk_items = prev_res.get("risk_items") or []
                            top_projects = [item.get("name") for item in risk_items[:2] if item.get("name")]
                            if len(top_projects) >= 2:
                                params = dict(params)
                                params["items"] = top_projects
                            break

            params = {key: value for key, value in params.items() if not str(key).startswith("_")}
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
            start = time.perf_counter()
            _tool_span = None
            if _tracer and hasattr(_tracer, "span"):
                _tool_span = _tracer.span(tool_name, **{k: v for k, v in params.items() if isinstance(v, (str, int, float, bool))})
                _tool_span.__enter__()
            try:
                if hasattr(self.tool_executor, "execute_with_retry"):
                    result = self.tool_executor.execute_with_retry(tool_name, data, **params)
                else:
                    result = self.tool_executor.execute_tool(tool_name, data, **params)
            except Exception as _tool_err:
                result = {"success": False, "tool": tool_name, "error": str(_tool_err)}
            finally:
                if _tool_span:
                    _tool_span.__exit__(None, None, None)

            if tool_name == "analyze_test_run" and isinstance(result, dict) and result.get("success") is False:
                current_group = str((params or {}).get("group_by") or "").strip().lower()
                for alt_group in ["project", "aida", "tester", "week"]:
                    if alt_group == current_group:
                        continue
                    alt_params = dict(params)
                    alt_params["group_by"] = alt_group
                    alt_result = self.tool_executor.execute_tool(tool_name, data, **alt_params)
                    if isinstance(alt_result, dict) and alt_result.get("success") is True:
                        params = alt_params
                        result = alt_result
                        break
            # P0 Self-Correction: LLM-driven correction on failure
            if isinstance(result, dict) and result.get("success") is False:
                corrector = getattr(self, "_self_corrector", None)
                if corrector is not None:
                    try:
                        corrected = corrector.try_correct(
                            tool_name=tool_name,
                            original_params=params,
                            error_message=str(result.get("error", "")),
                            context=context or {},
                            data=data,
                            available_tools=getattr(self.tool_executor, "tools", {}),
                        )
                        if isinstance(corrected, dict) and corrected.get("success") is True:
                            result = corrected
                            logger.info(f"Self-correction succeeded for {tool_name}")
                    except Exception as _sc_err:
                        logger.debug(f"Self-correction skipped for {tool_name}: {_sc_err}")

            duration_ms = int((time.perf_counter() - start) * 1000)
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
            results.append(
                {
                    "step": step["step"],
                    "tool": tool_name,
                    "description": step["description"],
                    "result": result,
                    "trace": {
                        "tool": tool_name,
                        "dataset": dataset_used,
                        "params": dict(params),
                        "duration_ms": duration_ms,
                        "tool_limit": (meta or {}).get("tool_limit") if isinstance(meta, dict) else None,
                        "sampling": (meta or {}).get("sampling") if isinstance(meta, dict) else None,
                        "gate": gate,
                    },
                }
            )
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

            replan_steps = self._build_replan_steps(
                step=step,
                result=result if isinstance(result, dict) else {},
                context=context,
                replan_depth=_replan_depth,
            )
            if replan_steps:
                if progress_cb:
                    try:
                        progress_cb(
                            {
                                "event": "replan",
                                "step_index": idx,
                                "total_steps": total_steps,
                                "failed_tool": tool_name,
                                "replan_depth": _replan_depth + 1,
                                "replan_tools": [s.get("tool") for s in replan_steps],
                            }
                        )
                    except Exception:
                        pass
                child_results = self.execute_plan(
                    replan_steps,
                    data,
                    context=context,
                    progress_cb=progress_cb,
                    _replan_depth=_replan_depth + 1,
                )
                for item in child_results:
                    trace = item.get("trace") if isinstance(item, dict) else None
                    if not isinstance(trace, dict):
                        continue
                    gate = trace.get("gate") if isinstance(trace.get("gate"), dict) else {}
                    if gate.get("action") in {None, "", "none"}:
                        gate["action"] = "replan_child"
                    gate.setdefault("reason", f"from:{tool_name}")
                    trace["gate"] = gate
                    trace["replan_depth"] = _replan_depth + 1
                results.extend(child_results)
                break

            if validation_enabled and gate.get("action") == "stop":
                has_success = any(isinstance(item.get("result"), dict) and item["result"].get("success") for item in results)
                if (not has_success) and tool_name != "statistical_summary" and primary_dataset:
                    fallback_params = {"dataset": primary_dataset} if isinstance(data, dict) else {}
                    fallback_start = time.perf_counter()
                    fallback = self.tool_executor.execute_tool("statistical_summary", data, **fallback_params)
                    fallback_ms = int((time.perf_counter() - fallback_start) * 1000)
                    fallback_meta = datasets_meta.get(primary_dataset) if isinstance(datasets_meta, dict) else None
                    results.append(
                        {
                            "step": int(step.get("step") or 0) + 1,
                            "tool": "statistical_summary",
                            "description": "执行失败后的退化：生成数据摘要",
                            "result": fallback,
                            "trace": {
                                "tool": "statistical_summary",
                                "dataset": primary_dataset,
                                "params": dict(fallback_params),
                                "duration_ms": fallback_ms,
                                "tool_limit": (fallback_meta or {}).get("tool_limit") if isinstance(fallback_meta, dict) else None,
                                "sampling": (fallback_meta or {}).get("sampling") if isinstance(fallback_meta, dict) else None,
                                "gate": {"enabled": True, "action": "fallback", "reason": gate.get("reason") or ""},
                            },
                        }
                    )
                break

        return results


__all__ = ["TaskPlanner"]