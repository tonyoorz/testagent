import unittest

from agent.core.harness_router import (
    HarnessRouteHandler,
    HarnessRouteRequest,
    resolve_harness_route,
    should_load_local_data,
)


def _request(**overrides):
    payload = {
        "question": "请总结当前数据情况",
        "selected_mode": "summary",
        "known_issues_enabled": False,
        "use_agent": True,
        "dashboard_type": "defect",
    }
    payload.update(overrides)
    return HarnessRouteRequest(**payload)


def test_known_issue_route_has_priority():
    decision = resolve_harness_route(
        _request(selected_mode="pure", known_issues_enabled=True),
        has_data=False,
    )

    assert decision.handler == HarnessRouteHandler.KNOWN_ISSUE
    assert decision.should_try_local_data is True


def test_summary_advanced_query_uses_skill_when_data_available():
    request = _request(question="请分析当前风险趋势并给出建议", selected_mode="summary")

    assert should_load_local_data(request) is True

    decision = resolve_harness_route(request, has_data=True)
    assert decision.handler == HarnessRouteHandler.SKILL_AGENT
    assert decision.agent_used is True


def test_summary_advanced_query_stays_database_direct_without_data():
    request = _request(question="请分析当前风险趋势并给出建议", selected_mode="summary")
    decision = resolve_harness_route(request, has_data=False)

    assert decision.handler == HarnessRouteHandler.DATABASE_SUMMARY
    assert decision.used_fallback is True
    assert "本地数据" in decision.fallback_reason


def test_skill_mode_falls_back_to_llm_without_data():
    decision = resolve_harness_route(
        _request(selected_mode="agent", question="请用工具链分析当前问题"),
        has_data=False,
    )

    assert decision.handler == HarnessRouteHandler.LLM
    assert decision.used_fallback is True
    assert decision.llm_mode == "summary"


def test_pure_mode_never_loads_local_data():
    request = _request(selected_mode="pure", question="你好")
    decision = resolve_harness_route(request, has_data=False)

    assert should_load_local_data(request) is False
    assert decision.handler == HarnessRouteHandler.LLM
    assert decision.llm_mode == "pure"


class HarnessRouterRegressionTests(unittest.TestCase):
    def test_known_issue_route_has_priority_unittest(self):
        test_known_issue_route_has_priority()

    def test_summary_advanced_query_uses_skill_when_data_available_unittest(self):
        test_summary_advanced_query_uses_skill_when_data_available()

    def test_summary_advanced_query_stays_database_direct_without_data_unittest(self):
        test_summary_advanced_query_stays_database_direct_without_data()

    def test_skill_mode_falls_back_to_llm_without_data_unittest(self):
        test_skill_mode_falls_back_to_llm_without_data()

    def test_pure_mode_never_loads_local_data_unittest(self):
        test_pure_mode_never_loads_local_data()


if __name__ == "__main__":
    unittest.main()