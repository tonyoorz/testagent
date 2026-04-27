"""
Retry Strategy — 错误分类分级 + 重试策略 + 预算控制

Layer 4: 自愈修复层 — 区分可重试错误 vs 不可重试错误，实现智能重试。

环境变量 AGENT_SMART_RETRY=1 开启，默认关闭。
"""

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SMART_RETRY_ENABLED = os.getenv("AGENT_SMART_RETRY", "0") == "1"


class ErrorCategory(Enum):
    """错误分类"""
    RETRYABLE = "retryable"  # 可重试：参数格式错误、超时、临时网络错误
    REPHRASE = "rephrase"   # 需要重新生成参数：LLM 生成了错误参数格式
    SKIP = "skip"           # 不重试：数据不存在、表为空、无匹配
    FATAL = "fatal"         # 致命：权限错误、代码bug


@dataclass
class ErrorInfo:
    """错误信息封装"""
    category: ErrorCategory
    message: str
    retryable: bool
    original_error: Optional[str] = None


@dataclass
class RetryBudget:
    """重试预算控制"""
    total_retries: int = 0
    max_total_retries: int = 10  # 全局最大重试次数
    tool_retries: Dict[str, int] = field(default_factory=dict)
    max_tool_retries: int = 3  # 每个工具最大重试次数
    cooldown_seconds: float = 1.0  # 连续重试的冷却时间

    def can_retry(self, tool_name: str) -> bool:
        """检查是否可以重试。"""
        if self.total_retries >= self.max_total_retries:
            logger.warning(f"全局重试次数已达上限 ({self.max_total_retries})")
            return False

        tool_count = self.tool_retries.get(tool_name, 0)
        if tool_count >= self.max_tool_retries:
            logger.warning(f"工具 {tool_name} 重试次数已达上限 ({self.max_tool_retries})")
            return False

        return True

    def record_retry(self, tool_name: str) -> None:
        """记录一次重试。"""
        self.total_retries += 1
        self.tool_retries[tool_name] = self.tool_retries.get(tool_name, 0) + 1
        logger.debug(
            f"重试记录: 全局 {self.total_retries}/{self.max_total_retries}, "
            f"工具 {tool_name} {self.tool_retries[tool_name]}/{self.max_tool_retries}"
        )

    def need_cooldown(self) -> bool:
        """是否需要冷却（连续重试）。"""
        return False  # 简化实现，暂时不追踪连续重试


class ErrorClassifier:
    """错误分类器"""

    # 可重试的错误模式
    RETRYABLE_PATTERNS = [
        "timeout",
        "timed out",
        "connection",
        "network",
        "temporary",
        "rate limit",
        "429",
        "503",
        "502",
    ]

    # 参数错误（需要重新生成）
    REPHRASE_PATTERNS = [
        "invalid parameter",
        "missing parameter",
        "unknown parameter",
        "unexpected keyword",
        "validation error",
        "type error",
        "does not exist",
        "no such column",
        "column not found",
        "key error",
    ]

    # 不重试的错误（数据问题）
    SKIP_PATTERNS = [
        "no data",
        "empty",
        "no matching",
        "not found",
        "data is empty",
        "result is empty",
    ]

    # 致命错误
    FATAL_PATTERNS = [
        "permission denied",
        "access denied",
        "unauthorized",
        "forbidden",
        "authentication",
        "import error",
        "module not found",
        "name error",
    ]

    def classify(self, error_message: str, tool_name: str) -> ErrorInfo:
        """分类错误。

        Returns:
            ErrorInfo
        """
        msg_lower = error_message.lower()

        # 1. 检查致命错误
        for pattern in self.FATAL_PATTERNS:
            if pattern in msg_lower:
                return ErrorInfo(
                    category=ErrorCategory.FATAL,
                    message=f"致命错误，无法重试: {error_message}",
                    retryable=False,
                    original_error=error_message,
                )

        # 2. 检查不重试错误（数据问题）
        for pattern in self.SKIP_PATTERNS:
            if pattern in msg_lower:
                return ErrorInfo(
                    category=ErrorCategory.SKIP,
                    message=f"数据不存在，跳过: {error_message}",
                    retryable=False,
                    original_error=error_message,
                )

        # 3. 检查参数错误（需要重新生成）
        for pattern in self.REPHRASE_PATTERNS:
            if pattern in msg_lower:
                return ErrorInfo(
                    category=ErrorCategory.REPHRASE,
                    message=f"参数错误，需要重新生成: {error_message}",
                    retryable=True,
                    original_error=error_message,
                )

        # 4. 检查可重试错误
        for pattern in self.RETRYABLE_PATTERNS:
            if pattern in msg_lower:
                return ErrorInfo(
                    category=ErrorCategory.RETRYABLE,
                    message=f"临时错误，可重试: {error_message}",
                    retryable=True,
                    original_error=error_message,
                )

        # 默认：未知错误，尝试重试一次
        return ErrorInfo(
            category=ErrorCategory.RETRYABLE,
            message=f"未知错误，尝试重试: {error_message}",
            retryable=True,
            original_error=error_message,
        )


class RetryStrategy:
    """重试策略管理器"""

    def __init__(self):
        self.classifier = ErrorClassifier()
        self.budget = RetryBudget()

    def should_retry(
        self,
        tool_name: str,
        error_message: str,
        attempt: int = 0,
    ) -> ErrorInfo:
        """判断是否应该重试，并返回错误分类。

        Args:
            tool_name: 工具名称
            error_message: 错误消息
            attempt: 当前尝试次数

        Returns:
            ErrorInfo
        """
        if not SMART_RETRY_ENABLED:
            # 未启用智能重试时，默认允许一次重试
            return ErrorInfo(
                category=ErrorCategory.RETRYABLE,
                message=f"智能重试未启用，默认重试: {error_message}",
                retryable=True,
                original_error=error_message,
            )

        error_info = self.classifier.classify(error_message, tool_name)

        # 检查预算
        if error_info.retryable and not self.budget.can_retry(tool_name):
            return ErrorInfo(
                category=ErrorCategory.FATAL,
                message=f"重试预算耗尽，停止重试: {error_message}",
                retryable=False,
                original_error=error_message,
            )

        return error_info

    def record_retry(self, tool_name: str) -> None:
        """记录一次重试。"""
        self.budget.record_retry(tool_name)

    def need_cooldown(self) -> bool:
        """检查是否需要冷却。"""
        return self.budget.need_cooldown()

    def cooldown(self) -> None:
        """执行冷却。"""
        time.sleep(self.budget.cooldown_seconds)

    def get_stats(self) -> Dict[str, Any]:
        """获取重试统计。"""
        return {
            "total_retries": self.budget.total_retries,
            "max_total_retries": self.budget.max_total_retries,
            "tool_retries": self.budget.tool_retries,
            "max_tool_retries": self.budget.max_tool_retries,
        }
