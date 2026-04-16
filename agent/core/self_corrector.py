"""
Self-Corrector — 工具执行失败时由 LLM 分析错误并修正参数

当工具执行失败时：
1. 收集：原始问题、工具名、原始参数、错误信息
2. 让 LLM 分析原因，返回修正后的参数
3. 用修正参数重试（最多 N 轮）

默认关闭，通过 AGENT_SELF_CORRECTION=1 开启。
"""

import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_CORRECTION_RETRIES = 2

_CORRECTION_PROMPT = """\
你是一个数据分析工具的调试专家。一个工具执行失败了，请分析原因并返回修正后的参数。

## 原始用户问题
{question}

## 上下文信息
- 已识别意图：{intents}
- 主要数据集：{primary_dataset}
- 数据概况：{data_summary}

## 失败的工具
- 工具名：{tool_name}
- 原始参数：{original_params}
- 错误信息：{error_message}

## 可用工具列表
{available_tools}

## 要求
分析失败原因（参数错误？维度不对？数据缺失？），然后返回修正后的完整参数 JSON。
只返回一个 JSON 对象，不要解释。如果无法修正，返回 {{"__give_up": true, "reason": "..."}}。
"""


class CorrectionResult:
    """One correction attempt."""

    __slots__ = ("attempt", "corrected_params", "reason", "success", "duration_ms")

    def __init__(
        self,
        attempt: int,
        corrected_params: Dict[str, Any],
        reason: str = "",
        success: bool = False,
        duration_ms: int = 0,
    ):
        self.attempt = attempt
        self.corrected_params = corrected_params
        self.reason = reason
        self.success = success
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt": self.attempt,
            "corrected_params": self.corrected_params,
            "reason": self.reason,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }


class SelfCorrector:
    """LLM-driven tool error correction."""

    def __init__(
        self,
        llm: Any = None,
        execute_fn: Optional[Callable] = None,
        max_retries: int = 0,
    ):
        self._llm = llm
        self._execute_fn = execute_fn
        self._max_retries = max_retries or self._default_max_retries()
        self._history: List[CorrectionResult] = []

    @staticmethod
    def _default_max_retries() -> int:
        try:
            return max(0, min(int(os.getenv("AGENT_SELF_CORRECTION_MAX_RETRIES", "2") or "2"), 5))
        except Exception:
            return 2

    @staticmethod
    def is_enabled() -> bool:
        return os.getenv("AGENT_SELF_CORRECTION", "0") == "1"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def try_correct(
        self,
        tool_name: str,
        original_params: Dict[str, Any],
        error_message: str,
        context: Dict[str, Any],
        data: Any,
        available_tools: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Attempt to correct a failed tool execution.

        Returns the final tool execution result (either corrected or last failure).
        """
        self._history.clear()

        if not self._llm or not self._execute_fn:
            return {
                "success": False,
                "tool": tool_name,
                "error": error_message,
                "correction": {"applied": False, "reason": "no_llm_or_execute_fn"},
            }

        question = str((context or {}).get("_original_question") or "")
        intents = list((context or {}).get("intents") or [])
        primary_dataset = str((context or {}).get("primary_dataset") or "")
        data_summary = str((context or {}).get("data_summary") or "")
        tool_list = ", ".join(sorted((available_tools or {}).keys())) if available_tools else ""

        current_params = dict(original_params)

        for attempt in range(1, self._max_retries + 1):
            t0 = time.perf_counter()
            try:
                corrected = self._ask_llm(
                    question=question,
                    intents=intents,
                    primary_dataset=primary_dataset,
                    data_summary=data_summary,
                    tool_name=tool_name,
                    original_params=current_params,
                    error_message=error_message,
                    available_tools=tool_list,
                    attempt=attempt,
                )
                duration_ms = int((time.perf_counter() - t0) * 1000)

                if corrected.get("__give_up"):
                    cr = CorrectionResult(
                        attempt=attempt,
                        corrected_params=corrected,
                        reason=corrected.get("reason", "give_up"),
                        success=False,
                        duration_ms=duration_ms,
                    )
                    self._history.append(cr)
                    logger.info(f"Self-correction attempt {attempt}: LLM gave up — {corrected.get('reason')}")
                    break

                # Remove internal keys
                clean_params = {k: v for k, v in corrected.items() if not k.startswith("__")}
                # Preserve reserved keys from original
                for k in ("dataset",):
                    if k in current_params and k not in clean_params:
                        clean_params[k] = current_params[k]

                cr = CorrectionResult(
                    attempt=attempt,
                    corrected_params=clean_params,
                    reason=f"LLM suggested correction",
                    duration_ms=duration_ms,
                )
                self._history.append(cr)

                logger.info(f"Self-correction attempt {attempt}: params={clean_params}")

                # Execute with corrected params
                result = self._execute_fn(tool_name, data, **clean_params)

                if isinstance(result, dict) and result.get("success") is True:
                    cr.success = True
                    result["correction"] = {
                        "applied": True,
                        "attempt": attempt,
                        "corrected_params": clean_params,
                    }
                    return result

                # Still failing, update error for next attempt
                error_message = str((result or {}).get("error") or "unknown")
                current_params = clean_params

            except Exception as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                cr = CorrectionResult(
                    attempt=attempt,
                    corrected_params={},
                    reason=str(e),
                    success=False,
                    duration_ms=duration_ms,
                )
                self._history.append(cr)
                logger.warning(f"Self-correction attempt {attempt} exception: {e}")
                error_message = str(e)

        # All attempts exhausted
        return {
            "success": False,
            "tool": tool_name,
            "error": error_message,
            "correction": {
                "applied": False,
                "attempts": len(self._history),
                "history": [cr.to_dict() for cr in self._history],
            },
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ask_llm(
        self,
        question: str,
        intents: List[str],
        primary_dataset: str,
        data_summary: str,
        tool_name: str,
        original_params: Dict[str, Any],
        error_message: str,
        available_tools: str,
        attempt: int,
    ) -> Dict[str, Any]:
        prompt = _CORRECTION_PROMPT.format(
            question=question,
            intents=", ".join(intents),
            primary_dataset=primary_dataset,
            data_summary=data_summary[:500],
            tool_name=tool_name,
            original_params=json.dumps(original_params, ensure_ascii=False, default=str),
            error_message=error_message[:500],
            available_tools=available_tools[:500] if available_tools else "(unknown)",
        )

        # Try the LLM client
        client = getattr(self._llm, "client", self._llm)
        model = getattr(self._llm, "model", None)

        if hasattr(client, "chat") and callable(client.chat):
            messages = [{"role": "user", "content": prompt}]
            resp = client.chat(messages=messages, model=model)
        elif hasattr(client, "create") and callable(client.create):
            resp = client.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
        else:
            return {"__give_up": True, "reason": "no compatible LLM client"}

        # Extract text
        text = ""
        if isinstance(resp, dict):
            choices = resp.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                text = msg.get("content") or ""
        elif hasattr(resp, "choices"):
            text = resp.choices[0].message.content
        elif isinstance(resp, str):
            text = resp

        text = text.strip()
        if not text:
            return {"__give_up": True, "reason": "empty LLM response"}

        # Strip markdown fences
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return {"__give_up": True, "reason": "non-dict response"}
            return parsed
        except json.JSONDecodeError as e:
            return {"__give_up": True, "reason": f"json parse error: {e}"}

    @property
    def history(self) -> List[CorrectionResult]:
        return list(self._history)
