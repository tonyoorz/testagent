import importlib
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pandas as pd

from agent.core.self_corrector import SelfCorrector
from agent.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


class ToolExecutor:
    """工具执行器 - 管理所有工具的注册和执行"""

    def __init__(
        self,
        llm: Any = None,
        db_path: Optional[str] = None,
        default_tool_factory: Optional[Callable[[Any, Optional[str]], List[Any]]] = None,
    ):
        self.tools = {}
        self._llm = llm
        self._db_path = db_path
        self._default_tool_factory = default_tool_factory
        self.registry = ToolRegistry()
        self._register_default_tools()

    def _load_default_tools(self) -> List[Any]:
        factory = self._default_tool_factory
        if callable(factory):
            return list(factory(self._llm, self._db_path) or [])

        try:
            tool_package = importlib.import_module("agent.tools")
            package_factory = getattr(tool_package, "build_tool_suite", None)
            if callable(package_factory):
                return list(package_factory(llm=self._llm, db_path=self._db_path) or [])
        except Exception as exc:
            logger.warning(f"package tool suite unavailable, falling back to legacy factory: {exc}")

        legacy_agent = importlib.import_module("agent.core.intelligent_agent")
        factory = getattr(legacy_agent, "build_default_tools", None)
        if not callable(factory):
            raise RuntimeError("build_default_tools is unavailable")

        return list(factory(llm=self._llm, db_path=self._db_path) or [])

    def _register_default_tools(self):
        """注册默认工具"""
        for tool in self._load_default_tools():
            self.register_tool(tool)

    def register_tool(self, tool: Any):
        """注册新工具"""
        self.tools[tool.name] = tool
        self.registry.register(tool)
        logger.info(f"已注册工具: {tool.name}")

    def _validate_and_normalize_params(self, tool: Any, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        schema = (getattr(tool, "parameters", None) or {}) if isinstance(getattr(tool, "parameters", None), dict) else {}
        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        cleaned: Dict[str, Any] = {}
        reserved = {"dataset"}
        unknown = [k for k in (params or {}).keys() if (k not in schema) and (k not in reserved)]
        if unknown and validation_enabled:
            return False, {}, f"参数不支持: {', '.join([str(k) for k in unknown[:8]])}"

        for key, spec in schema.items():
            if not isinstance(spec, dict):
                continue
            if key in params:
                cleaned[key] = params.get(key)
            elif "default" in spec:
                cleaned[key] = spec.get("default")

        for key in reserved:
            if key in params:
                cleaned[key] = params.get(key)

        def _coerce_bool(value: Any) -> Tuple[bool, Optional[bool]]:
            if isinstance(value, bool):
                return True, value
            if isinstance(value, (int, float)):
                return True, bool(int(value))
            text = str(value).strip().lower()
            if text in {"true", "1", "yes", "y", "是", "对"}:
                return True, True
            if text in {"false", "0", "no", "n", "否", "不"}:
                return True, False
            return False, None

        def _coerce_int(value: Any) -> Tuple[bool, Optional[int]]:
            if isinstance(value, bool):
                return True, int(value)
            if isinstance(value, int):
                return True, value
            if isinstance(value, float) and float(value).is_integer():
                return True, int(value)
            text = str(value).strip()
            if re.fullmatch(r"[-+]?\d+", text):
                try:
                    return True, int(text)
                except Exception:
                    return False, None
            return False, None

        def _coerce_number(value: Any) -> Tuple[bool, Optional[float]]:
            if isinstance(value, bool):
                return True, float(int(value))
            if isinstance(value, (int, float)):
                return True, float(value)
            text = str(value).strip()
            try:
                return True, float(text)
            except Exception:
                return False, None

        def _coerce_array(value: Any) -> Tuple[bool, Optional[List[Any]]]:
            if value is None:
                return True, []
            if isinstance(value, list):
                return True, value
            if isinstance(value, tuple):
                return True, list(value)
            text = str(value).strip()
            if not text:
                return True, []
            parts = [part.strip() for part in re.split(r"[,，;；\n]+", text) if part and part.strip()]
            return True, parts

        def _coerce_object(value: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
            if value is None:
                return True, {}
            if isinstance(value, dict):
                return True, value
            text = str(value).strip()
            if not text:
                return True, {}
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    return True, obj
                return False, None
            except Exception:
                return False, None

        for key, spec in schema.items():
            if key not in cleaned:
                continue
            value_type = str((spec or {}).get("type") or "").lower()
            if not value_type:
                continue
            value = cleaned.get(key)
            ok = True
            out: Any = value
            if value_type in {"string"}:
                out = "" if value is None else str(value)
            elif value_type in {"integer", "int"}:
                ok, out = _coerce_int(value)
            elif value_type in {"number", "float"}:
                ok, out = _coerce_number(value)
            elif value_type in {"boolean", "bool"}:
                ok, out = _coerce_bool(value)
            elif value_type in {"array", "list"}:
                ok, out = _coerce_array(value)
            elif value_type in {"object", "dict"}:
                ok, out = _coerce_object(value)
            else:
                out = value
            if not ok:
                return False, {}, f"参数类型错误: {key} 需要 {value_type}"
            if "enum" in spec and spec.get("enum") is not None:
                enum = list(spec.get("enum") or [])
                if enum and out not in enum:
                    return False, {}, f"参数取值错误: {key} 需要为 {enum}"
            cleaned[key] = out

        if not validation_enabled and unknown:
            for key in unknown:
                params.pop(key, None)
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

    def get_tool_schema(self, tool_name: str = None) -> Dict[str, Any]:
        """获取工具的 schema，用于 LLM 理解"""
        if tool_name:
            if tool_name not in self.tools:
                return {}
            tool_schema = self.registry.export(tool_name)
            if tool_schema:
                tool_schema["name"] = tool_name
            return tool_schema
        return self.registry.export()


class ToolExecutorWithRetry(ToolExecutor):
    """
    带自我修正能力的工具执行器

    功能：
    1. 自动检测空结果并分析原因
    2. 自动修正参数并重试
    3. 错误处理和参数修复
    4. 最终回退到统计摘要
    """

    def __init__(
        self,
        llm: Any = None,
        db_path: Optional[str] = None,
        max_retry: int = 2,
        default_tool_factory: Optional[Callable[[Any, Optional[str]], List[Any]]] = None,
    ):
        super().__init__(llm=llm, db_path=db_path, default_tool_factory=default_tool_factory)
        self.max_retry = max_retry
        self.self_corrector = SelfCorrector()
        self._retry_stats = {
            "total_calls": 0,
            "retry_attempts": 0,
            "fallbacks": 0,
        }

    def execute_with_retry(
        self,
        tool_name: str,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        **kwargs,
    ) -> Dict[str, Any]:
        """执行工具，支持自动重试和修正"""
        self._retry_stats["total_calls"] += 1

        for attempt in range(self.max_retry + 1):
            result = self.execute_tool(tool_name, data, **kwargs)
            should_retry, analysis = self._analyze_result(result, tool_name, kwargs, data)

            if not should_retry:
                return result

            if attempt < self.max_retry:
                self._retry_stats["retry_attempts"] += 1
                logger.info(f"Tool {tool_name} retry {attempt + 1}: {analysis}")
                kwargs = self._fix_params(kwargs, analysis, tool_name)
            else:
                logger.warning(f"Tool {tool_name} max retries exceeded, using fallback")
                break

        self._retry_stats["fallbacks"] += 1
        return self._fallback_to_summary(data, tool_name, result)

    def _analyze_result(
        self,
        result: Dict[str, Any],
        tool_name: str,
        params: Dict[str, Any],
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    ) -> Tuple[bool, str]:
        """分析执行结果，判断是否需要重试"""
        if not result.get("success", True):
            error_msg = str(result.get("error", "")).lower()

            if "not found" in error_msg or "不存在" in error_msg:
                return True, "tool_not_found"
            if "parameter" in error_msg or "参数" in error_msg:
                return True, "invalid_parameters"
            if "dataset" in error_msg or "数据集" in error_msg:
                return True, "dataset_issue"
            return False, f"execution_error: {error_msg}"

        tool_result = result.get("result", {})
        if self._is_empty_result(tool_result):
            return True, "empty_result"

        return False, "success"

    def _is_empty_result(self, result: Any) -> bool:
        """检查结果是否为空"""
        if result is None:
            return True
        if isinstance(result, dict):
            if not result:
                return True
            if "count" in result and result["count"] == 0:
                return True
            if "items" in result and not result["items"]:
                return True
            if "data" in result and not result["data"]:
                return True
            if "rows" in result and not result["rows"]:
                return True
        if isinstance(result, list) and not result:
            return True
        if isinstance(result, pd.DataFrame) and result.empty:
            return True
        return False

    def _fix_params(self, params: Dict[str, Any], analysis: str, tool_name: str) -> Dict[str, Any]:
        """根据分析结果修正参数"""
        valid_params = None
        if analysis == "invalid_parameters":
            known_tool = self.tools.get(tool_name)
            if known_tool and hasattr(known_tool, "parameters"):
                valid_params = set(known_tool.parameters.keys()) | {"dataset"}

        return self.self_corrector.fix_params(
            params,
            analysis=analysis,
            valid_params=valid_params,
        )

    def _fallback_to_summary(
        self,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        original_tool: str,
        last_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """回退到统计摘要"""
        logger.info(f"Fallback to statistical_summary from {original_tool}")

        try:
            fallback_result = self.execute_tool("statistical_summary", data, dataset="defects")

            if fallback_result.get("success"):
                return {
                    "success": True,
                    "tool": original_tool,
                    "result": fallback_result.get("result", {}),
                    "fallback": True,
                    "fallback_reason": "max_retries_exceeded",
                    "original_error": last_result.get("error", "Unknown error"),
                }
        except Exception as exc:
            logger.error(f"Fallback failed: {exc}")

        summary = self._generate_basic_summary(data)
        return {
            "success": True,
            "tool": original_tool,
            "result": summary,
            "fallback": True,
            "fallback_reason": "all_retries_failed",
            "note": "由于原始查询条件过于严格，返回基础数据摘要",
        }

    def _generate_basic_summary(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Dict[str, Any]:
        """生成基础数据摘要"""
        summary = {
            "total_records": 0,
            "summary_text": "",
        }

        try:
            if isinstance(data, dict):
                for name, df in data.items():
                    if isinstance(df, pd.DataFrame):
                        summary[f"{name}_count"] = len(df)
                        summary["total_records"] += len(df)
            elif isinstance(data, pd.DataFrame):
                summary["total_records"] = len(data)
                summary["defects_count"] = len(data)

            summary["summary_text"] = f"数据包含 {summary['total_records']} 条记录"
        except Exception as exc:
            logger.error(f"Summary generation failed: {exc}")
            summary["error"] = str(exc)

        return summary

    def get_retry_stats(self) -> Dict[str, int]:
        """获取重试统计信息"""
        return dict(self._retry_stats)


__all__ = [
    "ToolExecutor",
    "ToolExecutorWithRetry",
]