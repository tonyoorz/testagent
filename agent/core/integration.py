"""
集成补丁 — 将 Tracer + SelfCorrector + Registry 接入现有 IntelligentAgent

使用方式：在 IntelligentAgent.__init__ 末尾调用 patch_agent(self)。
改动极小：只替换内部组件引用，不改 process() 签名和返回值。
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def patch_agent(agent) -> None:
    """Patch an IntelligentAgent instance with tracer, self-corrector, and registry."""

    # 1. Tool Registry — import legacy tools
    if os.getenv("AGENT_TOOL_REGISTRY", "legacy") == "registry":
        try:
            from agent.tools.registry import get_registry

            registry = get_registry()
            registry.discover()
            existing_tools = list((getattr(agent, "tool_executor", None) or {}).get("tools", {}).values())
            if existing_tools:
                registry.import_from_legacy(existing_tools)
            logger.info(f"Tool Registry: {registry.count} tools registered")
        except Exception as e:
            logger.warning(f"Tool Registry init failed, staying legacy: {e}")

    # 2. Self-Corrector — inject into both agent and task_planner
    if os.getenv("AGENT_SELF_CORRECTION", "0") == "1":
        try:
            from agent.core.self_corrector import SelfCorrector

            llm = getattr(agent.tool_executor, "_llm", None)
            executor = agent.tool_executor

            corrector = SelfCorrector(
                llm=llm,
                execute_fn=lambda tool_name, data, **kw: executor.execute_tool(tool_name, data, **kw),
            )
            agent._self_corrector = corrector

            # 关键：注入到 task_planner，让 execute_plan() 失败时能调用
            if hasattr(agent, "task_planner"):
                agent.task_planner._self_corrector = corrector

            logger.info("Self-Corrector enabled (agent + task_planner)")
        except Exception as e:
            logger.warning(f"Self-Corrector init failed: {e}")
            agent._self_corrector = None
    else:
        agent._self_corrector = None


def create_tracer(question: str):
    """Create a tracer for one agent invocation."""
    from agent.core.tracer import AgentTracer

    return AgentTracer.enabled(question=question)
