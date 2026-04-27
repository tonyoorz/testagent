"""
Tool Call Guardrails — 工具调用前参数校验 + 风险操作检查

Layer 3: 执行护栏层 — 在工具调用执行前校验参数，避免无效/危险调用。

环境变量 AGENT_TOOL_CALL_GUARD=1 开启，默认关闭。
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GUARD_ENABLED = os.getenv("AGENT_TOOL_CALL_GUARD", "0") == "1"


class RiskLevel(Enum):
    """风险等级"""
    SAFE = "safe"          # 安全，直接执行
    CAUTION = "caution"    # 谨慎，建议确认
    DANGEROUS = "dangerous" # 危险，需要确认（暂时只标记）


@dataclass
class GuardrailResult:
    """校验结果"""
    passed: bool
    risk_level: RiskLevel = RiskLevel.SAFE
    message: str = ""
    error_details: List[str] = field(default_factory=list)

    @property
    def should_block(self) -> bool:
        return not self.passed


class ToolCallGuardrail:
    """工具调用前参数校验器"""

    # 高风险工具（暂时标记，未来可要求人工确认）
    HIGH_RISK_TOOLS = {
        # 目前没有真正的"危险"操作，留空
        # 示例: "delete_defect", "modify_test_data"
    }

    # 大数据量风险阈值（防止返回百万行）
    LARGE_RESULT_THRESHOLD = 500_000  # 50万行

    def __init__(self):
        pass

    def check_tool_call(
        self,
        tool_name: str,
        params: Dict[str, Any],
        tool_descriptor: Any = None,
    ) -> GuardrailResult:
        """检查工具调用是否安全/合法。

        Args:
            tool_name: 工具名称
            params: 调用参数
            tool_descriptor: ToolDescriptor 实例（可选）

        Returns:
            GuardrailResult
        """
        if not GUARD_ENABLED:
            return GuardrailResult(passed=True, risk_level=RiskLevel.SAFE)

        # 1. 参数校验（通过工具的 validate_params）
        if tool_descriptor and hasattr(tool_descriptor, "validate_params"):
            try:
                validated = tool_descriptor.validate_params(**params)
            except Exception as e:
                return GuardrailResult(
                    passed=False,
                    risk_level=RiskLevel.DANGEROUS,
                    message=f"参数校验失败: {e}",
                    error_details=[str(e)],
                )

        # 2. 风险等级评估
        risk_level = self._check_risk_level(tool_name, params)

        # 3. 特定参数检查（top_n 限制等）
        top_n_issue = self._check_top_n_params(tool_name, params)
        if top_n_issue:
            return GuardrailResult(
                passed=False,
                risk_level=RiskLevel.DANGEROUS,
                message=top_n_issue,
                error_details=[top_n_issue],
            )

        # 4. 日期范围合理性检查
        date_issue = self._check_date_range(tool_name, params)
        if date_issue:
            return GuardrailResult(
                passed=False,
                risk_level=RiskLevel.CAUTION,
                message=date_issue,
                error_details=[date_issue],
            )

        return GuardrailResult(
            passed=True,
            risk_level=risk_level,
            message="校验通过",
        )

    def _check_risk_level(self, tool_name: str, params: Dict[str, Any]) -> RiskLevel:
        """评估工具调用的风险等级。"""
        if tool_name in self.HIGH_RISK_TOOLS:
            return RiskLevel.DANGEROUS

        # 某些参数组合可能风险较高
        if tool_name in {"groupby_aggregate", "statistical_summary"}:
            # 无限制的聚合可能返回大量数据
            if params.get("include_all") or not params.get("top_n"):
                return RiskLevel.CAUTION

        return RiskLevel.SAFE

    def _check_top_n_params(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        """检查 top_n 参数是否合理。"""
        top_n = params.get("top_n")
        if top_n is not None:
            try:
                top_n_val = int(top_n)
                if top_n_val <= 0:
                    return f"top_n 必须大于 0，得到: {top_n}"
                if top_n_val > 1000:
                    return f"top_n 过大 ({top_n})，可能返回大量数据，建议不超过 1000"
            except (ValueError, TypeError):
                return f"top_n 必须是整数，得到: {top_n}"

        return None

    def _check_date_range(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        """检查日期范围是否合理。"""
        from datetime import datetime, timedelta

        start_date = params.get("start_date") or params.get("startDate")
        end_date = params.get("end_date") or params.get("endDate")

        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")

                if start > end:
                    return f"起始日期 ({start_date}) 不能晚于结束日期 ({end_date})"

                if (end - start).days > 365 * 2:  # 超过2年
                    return f"日期范围过大 ({(end - start).days} 天)，可能影响性能"
            except ValueError as e:
                return f"日期格式错误: {e}"

        return None

    def check_result_sanity(
        self,
        tool_name: str,
        result: Dict[str, Any],
        params: Dict[str, Any],
    ) -> GuardrailResult:
        """检查执行结果是否合理（后置校验）。

        检查：
        - 返回 0 行数据（可能参数错误）
        - 返回全 NULL
        - 返回行数异常大（> LARGE_RESULT_THRESHOLD）
        """
        if not GUARD_ENABLED:
            return GuardrailResult(passed=True, risk_level=RiskLevel.SAFE)

        if not isinstance(result, dict):
            return GuardrailResult(
                passed=True, risk_level=RiskLevel.SAFE
            )

        # 检查返回数据是否为空
        result_data = result.get("result", {})
        if isinstance(result_data, dict):
            distribution = result_data.get("distribution", [])
            trend_data = result_data.get("trend_data", [])
            risk_items = result_data.get("risk_items", [])

            if not any([distribution, trend_data, risk_items]):
                # 有可能是正常的（比如过滤后无数据）
                # 只警告，不阻止
                return GuardrailResult(
                    passed=True,
                    risk_level=RiskLevel.CAUTION,
                    message="工具返回空结果，可能是参数过滤条件过严或数据不存在",
                )

        # TODO: 可以增加更多合理性检查

        return GuardrailResult(passed=True, risk_level=RiskLevel.SAFE)
