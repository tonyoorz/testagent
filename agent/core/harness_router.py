from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class HarnessRouteHandler(str, Enum):
    LLM = "llm"
    DATABASE_SUMMARY = "database_summary"
    SKILL_AGENT = "skill_agent"
    DIFY_WORKFLOW = "dify_workflow"
    CONFLUENCE = "confluence"
    KNOWN_ISSUE = "known_issue"


_MODE_LABELS = {
    "pure": "纯聊天",
    "rag": "RAG",
    "confluence": "Confluence",
    "summary": "Agent（数据库直读）",
    "agent": "Skill（工具链）",
}

_HANDLER_LABELS = {
    HarnessRouteHandler.LLM: "LLM",
    HarnessRouteHandler.DATABASE_SUMMARY: "Agent（数据库直读）",
    HarnessRouteHandler.SKILL_AGENT: "Skill（工具链）",
    HarnessRouteHandler.DIFY_WORKFLOW: "RAG",
    HarnessRouteHandler.CONFLUENCE: "Confluence",
    HarnessRouteHandler.KNOWN_ISSUE: "已知问题检索",
}

_ADVANCED_KEYWORDS = (
    "趋势",
    "trend",
    "风险",
    "risk",
    "预测",
    "predict",
    "策略",
    "strategy",
    "建议",
    "recommend",
    "复盘",
    "retrospective",
    "恶化",
    "improve",
    "下个版本",
    "next release",
    "测试重点",
    "质量趋势",
    "根因",
    "priority",
)


@dataclass(frozen=True)
class HarnessRouteRequest:
    question: str
    selected_mode: str
    known_issues_enabled: bool
    use_agent: bool
    dashboard_type: str
    force_skill_agent: bool = False


@dataclass(frozen=True)
class HarnessRouteDecision:
    requested_mode: str
    handler: HarnessRouteHandler
    reason: str
    llm_mode: str
    advanced_query: bool
    known_issues_enabled: bool
    use_agent_enabled: bool
    has_data: bool
    should_try_local_data: bool
    used_fallback: bool = False
    fallback_reason: str = ""

    @property
    def requested_mode_label(self) -> str:
        return _MODE_LABELS.get(self.requested_mode, self.requested_mode or "未知模式")

    @property
    def handler_label(self) -> str:
        return _HANDLER_LABELS.get(self.handler, self.handler.value)

    @property
    def agent_used(self) -> bool:
        return self.handler == HarnessRouteHandler.SKILL_AGENT

    def to_trace(self) -> Dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "requested_mode_label": self.requested_mode_label,
            "handler": self.handler.value,
            "handler_label": self.handler_label,
            "reason": self.reason,
            "llm_mode": self.llm_mode,
            "advanced_query": self.advanced_query,
            "known_issues_enabled": self.known_issues_enabled,
            "use_agent_enabled": self.use_agent_enabled,
            "has_data": self.has_data,
            "should_try_local_data": self.should_try_local_data,
            "used_fallback": self.used_fallback,
            "fallback_reason": self.fallback_reason,
        }


def _normalize_mode(mode: str) -> str:
    return str(mode or "summary").strip().lower() or "summary"


def is_advanced_decision_query(text: str) -> bool:
    question = str(text or "").strip().lower()
    if not question:
        return False
    return any(keyword in question for keyword in _ADVANCED_KEYWORDS)


def should_load_local_data(request: HarnessRouteRequest) -> bool:
    mode = _normalize_mode(request.selected_mode)
    if request.known_issues_enabled:
        return True
    if request.force_skill_agent:
        return True
    if mode in {"rag", "confluence", "agent"}:
        return True
    if mode == "summary" and request.use_agent and is_advanced_decision_query(request.question):
        return True
    return False


def resolve_harness_route(request: HarnessRouteRequest, has_data: bool) -> HarnessRouteDecision:
    mode = _normalize_mode(request.selected_mode)
    advanced = is_advanced_decision_query(request.question)
    try_local_data = should_load_local_data(request)

    if request.force_skill_agent:
        if request.use_agent and has_data:
            return HarnessRouteDecision(
                requested_mode=mode,
                handler=HarnessRouteHandler.SKILL_AGENT,
                reason="待确认计划已存在，优先回到 Skill 工具链继续执行。",
                llm_mode="summary",
                advanced_query=True,
                known_issues_enabled=request.known_issues_enabled,
                use_agent_enabled=request.use_agent,
                has_data=has_data,
                should_try_local_data=try_local_data,
            )

        fallback_reason = "待确认计划需要本地数据。" if request.use_agent else "Skill 工具链当前不可用。"
        fallback_handler = HarnessRouteHandler.DATABASE_SUMMARY if mode == "summary" else HarnessRouteHandler.LLM
        return HarnessRouteDecision(
            requested_mode=mode,
            handler=fallback_handler,
            reason="待确认计划无法直接恢复，已回退到当前可用链路。",
            llm_mode="summary",
            advanced_query=True,
            known_issues_enabled=request.known_issues_enabled,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
            used_fallback=True,
            fallback_reason=fallback_reason,
        )

    if request.known_issues_enabled:
        return HarnessRouteDecision(
            requested_mode=mode,
            handler=HarnessRouteHandler.KNOWN_ISSUE,
            reason="已显式启用“已知问题”检索，优先走重复问题判定链路。",
            llm_mode="summary",
            advanced_query=advanced,
            known_issues_enabled=True,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
        )

    if mode == "pure":
        return HarnessRouteDecision(
            requested_mode=mode,
            handler=HarnessRouteHandler.LLM,
            reason="用户选择纯聊天模式，不接入本地数据和工具链。",
            llm_mode="pure",
            advanced_query=advanced,
            known_issues_enabled=False,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
        )

    if mode == "rag":
        return HarnessRouteDecision(
            requested_mode=mode,
            handler=HarnessRouteHandler.DIFY_WORKFLOW,
            reason="用户选择 RAG 模式，交由 Dify Workflow 处理。",
            llm_mode="summary",
            advanced_query=advanced,
            known_issues_enabled=False,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
        )

    if mode == "confluence":
        return HarnessRouteDecision(
            requested_mode=mode,
            handler=HarnessRouteHandler.CONFLUENCE,
            reason="用户选择 Confluence 模式，优先走知识空间检索。",
            llm_mode="summary",
            advanced_query=advanced,
            known_issues_enabled=False,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
        )

    if mode == "summary":
        if advanced and request.use_agent and has_data:
            return HarnessRouteDecision(
                requested_mode=mode,
                handler=HarnessRouteHandler.SKILL_AGENT,
                reason="问题属于高阶分析，且本地数据可用，已从数据库直读升级到 Skill 工具链。",
                llm_mode="summary",
                advanced_query=advanced,
                known_issues_enabled=False,
                use_agent_enabled=request.use_agent,
                has_data=has_data,
                should_try_local_data=try_local_data,
            )

        reason = "当前问题保持在数据库直读链路。"
        fallback_reason = ""
        if advanced and request.use_agent and not has_data:
            reason = "问题属于高阶分析，但本地数据不可用，因此保留在数据库直读链路。"
            fallback_reason = "未命中可用于 Skill 工具链的本地数据。"

        return HarnessRouteDecision(
            requested_mode=mode,
            handler=HarnessRouteHandler.DATABASE_SUMMARY,
            reason=reason,
            llm_mode="summary",
            advanced_query=advanced,
            known_issues_enabled=False,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
            used_fallback=bool(fallback_reason),
            fallback_reason=fallback_reason,
        )

    if mode == "agent":
        if request.use_agent and has_data:
            return HarnessRouteDecision(
                requested_mode=mode,
                handler=HarnessRouteHandler.SKILL_AGENT,
                reason="用户显式选择 Skill 工具链，且本地数据可用。",
                llm_mode="summary",
                advanced_query=advanced,
                known_issues_enabled=False,
                use_agent_enabled=request.use_agent,
                has_data=has_data,
                should_try_local_data=try_local_data,
            )

        fallback_reason = "Skill 工具链需要本地数据。" if request.use_agent else "Skill 工具链当前不可用。"
        return HarnessRouteDecision(
            requested_mode=mode,
            handler=HarnessRouteHandler.LLM,
            reason="Skill 模式无法满足执行条件，已回退到 LLM。",
            llm_mode="summary",
            advanced_query=advanced,
            known_issues_enabled=False,
            use_agent_enabled=request.use_agent,
            has_data=has_data,
            should_try_local_data=try_local_data,
            used_fallback=True,
            fallback_reason=fallback_reason,
        )

    return HarnessRouteDecision(
        requested_mode=mode,
        handler=HarnessRouteHandler.LLM,
        reason="未识别的模式，回退到 LLM。",
        llm_mode="summary",
        advanced_query=advanced,
        known_issues_enabled=False,
        use_agent_enabled=request.use_agent,
        has_data=has_data,
        should_try_local_data=try_local_data,
        used_fallback=True,
        fallback_reason="模式值不在已支持的路由集合中。",
    )


__all__ = [
    "HarnessRouteDecision",
    "HarnessRouteHandler",
    "HarnessRouteRequest",
    "is_advanced_decision_query",
    "resolve_harness_route",
    "should_load_local_data",
]