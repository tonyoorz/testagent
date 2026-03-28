"""
统一提示词管理层 - PreAnalysis 项目
=====================================

提示词分层架构：
  1. 通用层 (common.py)       - 格式规范、行为准则
  2. 业务知识层 (business.py)  - DTSV 领域知识、Risk Score、AIDA
  3. 角色定义层 (roles.py)     - PM/DEV/QA/Coordinator 角色
  4. 数据层 (data.py)          - 数据库 Schema、字段含义

使用方法：
    from prompts import get_system_prompt, ROLES

    # 获取 AI 聊天的系统提示词
    prompt = get_system_prompt("chat", context={"db_schema": "..."})

    # 获取角色定义
    pm_soul = ROLES["pm"]

版本: 1.0
日期: 2026-03-22
"""

from .common import COMMON_RULES, FORMAT_RULES
from .business import BUSINESS_KNOWLEDGE, RISK_SCORE_KNOWLEDGE, DEFECT_STATUS_KNOWLEDGE
from .roles import ROLES, get_role_prompt
from .data import DB_SCHEMA_CONTEXT, get_db_context
from .chat import (
    CHAT_SYSTEM_PROMPT,
    DEFECT_ANALYSIS_PROMPT,
    TEST_ANALYSIS_PROMPT,
    GENERAL_ANALYSIS_PROMPT,
    DATA_ANALYSIS_PROMPTS,
    AI_CHAT_SYSTEM_PROMPTS,
    AI_CHAT_PROMPT_TEMPLATE,
    BASIC_ASSISTANT_PROMPT,
    CHART_PROMPT,
)

__all__ = [
    # 通用
    "COMMON_RULES",
    "FORMAT_RULES",
    # 业务知识
    "BUSINESS_KNOWLEDGE",
    "RISK_SCORE_KNOWLEDGE",
    "DEFECT_STATUS_KNOWLEDGE",
    # 角色
    "ROLES",
    "get_role_prompt",
    # 数据
    "DB_SCHEMA_CONTEXT",
    "get_db_context",
    # 聊天 & 数据分析提示词
    "CHAT_SYSTEM_PROMPT",
    "DEFECT_ANALYSIS_PROMPT",
    "TEST_ANALYSIS_PROMPT",
    "GENERAL_ANALYSIS_PROMPT",
    "DATA_ANALYSIS_PROMPTS",
    "AI_CHAT_SYSTEM_PROMPTS",
    "AI_CHAT_PROMPT_TEMPLATE",
    "BASIC_ASSISTANT_PROMPT",
    "CHART_PROMPT",
    # 便捷函数
    "get_system_prompt",
]


def get_system_prompt(mode: str = "chat", context: dict = None) -> str:
    """
    获取系统提示词

    :param mode: 模式 - "chat"(通用聊天) | "code_interpreter" | "multi_agent"
    :param context: 动态上下文变量
    :return: 完整系统提示词字符串
    """
    context = context or {}

    if mode == "chat":
        from .chat import CHAT_SYSTEM_PROMPT
        return CHAT_SYSTEM_PROMPT.format(**context) if context else CHAT_SYSTEM_PROMPT

    elif mode == "code_interpreter":
        from .code_interpreter import CODE_INTERPRETER_SYSTEM_PROMPT
        return CODE_INTERPRETER_SYSTEM_PROMPT.format(**context) if context else CODE_INTERPRETER_SYSTEM_PROMPT

    elif mode == "coordinator":
        return get_role_prompt("coordinator")

    elif mode == "pm":
        return get_role_prompt("pm")

    elif mode == "dev":
        return get_role_prompt("dev")

    elif mode == "qa":
        return get_role_prompt("qa")

    else:
        return COMMON_RULES
