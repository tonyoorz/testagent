"""
数据分析工具基类 + Pydantic 参数校验

Layer 1: 结构化定义层 — 用 Pydantic 强类型约束工具参数。
环境变量 AGENT_TOOL_VALIDATION=1 开启校验，默认关闭（优雅降级）。
"""

import logging
import os
from typing import Any, ClassVar, Dict, List, Optional, Type

import pandas as pd
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# 全局开关
VALIDATION_ENABLED = os.getenv("AGENT_TOOL_VALIDATION", "0") == "1"


class DataAnalysisTool:
    """数据分析工具基类。

    子类可选择性提供 ``param_model`` (Pydantic BaseModel) 以启用参数强类型校验。
    如果不提供，仍使用原有 dict parameters 行为（向后兼容）。
    """

    # 子类可覆盖：工具使用指南（什么时候用/不用/边界条件）
    usage_guide: ClassVar[str] = ""

    # 子类可覆盖：高风险操作标记
    is_dangerous: ClassVar[bool] = False

    # 子类可覆盖：工具所属分类
    category: ClassVar[str] = "analysis"

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        param_model: Optional[Type[BaseModel]] = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.param_model = param_model

    def validate_params(self, **kwargs) -> Dict[str, Any]:
        """校验参数，返回清洗后的参数 dict。

        - 如果开启了 AGENT_TOOL_VALIDATION 且有 param_model → Pydantic 校验
        - 否则直接返回 kwargs（向后兼容）
        """
        if not VALIDATION_ENABLED or self.param_model is None:
            return kwargs

        try:
            # 过滤掉 None / 空字符串，让 Pydantic 使用默认值
            cleaned = {k: v for k, v in kwargs.items() if v is not None and v != ""}
            model = self.param_model(**cleaned)
            return model.model_dump()
        except ValidationError as e:
            logger.warning(f"工具 {self.name} 参数校验失败: {e}")
            raise ToolValidationError(tool_name=self.name, errors=e.errors()) from e

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行工具逻辑，由子类实现"""
        raise NotImplementedError

    def expects_datasets(self) -> bool:
        return False

    def get_full_description(self) -> str:
        """返回包含使用指南的完整描述（供 LLM 参考）。"""
        parts = [self.description]
        if self.usage_guide:
            parts.append(f"\n使用指南: {self.usage_guide}")
        return "\n".join(parts)


class ToolValidationError(Exception):
    """工具参数校验失败异常。"""

    def __init__(self, tool_name: str, errors: List[Dict[str, Any]]):
        self.tool_name = tool_name
        self.errors = errors
        # 生成人类可读的错误消息
        msgs = []
        for e in errors:
            loc = " -> ".join(str(l) for l in e.get("loc", []))
            msgs.append(f"{loc}: {e.get('msg', '')}")
        super().__init__(f"工具 [{tool_name}] 参数校验失败: {'; '.join(msgs)}")
