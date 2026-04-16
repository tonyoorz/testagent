"""
Tool Regression Tests — 工具回归测试框架

用法:
    python -m agent.tests.test_tools          # 全部测试
    python -m agent.tests.test_tools -k risk   # 只跑 risk 相关
    AGENT_TEST_QUICK=1 python -m agent.tests.test_tools  # 快速模式

每个测试用例:
1. 构造标准测试数据
2. 调用指定工具
3. 验证输出结构 + 业务逻辑
"""

import os
import sys
import time
import unittest
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def make_defect_df(n=200, seed=42) -> pd.DataFrame:
    """构造标准缺陷测试数据。"""
    rng = np.random.RandomState(seed)
    projects = ["IDCevo", "MGU", "App"]
    severities = ["Critical Issues", "Major", "Minor"]
    ecus = ["HU-MGU", "IDCEVO", "RSU-1"]
    matrices = ["Matrix-1A", "Matrix-2B", "Matrix-3A"]
    statuses = ["New", "In Progress", "Closed"]

    return pd.DataFrame({
        "tproject": rng.choice(projects, n),
        "severity_group": rng.choice(severities, n, p=[0.15, 0.55, 0.30]),
        "ecu": rng.choice(ecus, n),
        "matrix": rng.choice(matrices, n),
        "status": rng.choice(statuses, n),
        "tcreationtime": pd.date_range("2025-01-01", periods=n, freq="6h"),
        "tester": [f"tester_{i % 8}" for i in range(n)],
    })


class ToolTestCase(unittest.TestCase):
    """工具测试基类 — 提供通用 fixture。"""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("AGENT_CONFIRM_MULTISTEP", "0")
        cls.data = make_defect_df()
        cls.quick = os.getenv("AGENT_TEST_QUICK", "0") == "1"

    def _get_tool(self, name: str):
        """从 ToolExecutor 获取工具实例。"""
        from agent.core.intelligent_agent import IntelligentAgent
        agent = IntelligentAgent(dashboard_type="general")
        return agent.tool_executor.tools.get(name)

    def _run_tool(self, name: str, data: pd.DataFrame = None, **kwargs) -> Dict[str, Any]:
        """执行工具并返回结果。"""
        tool = self._get_tool(name)
        self.assertIsNotNone(tool, f"Tool '{name}' not found")
        result = tool.execute(data or self.data, **kwargs)
        self.assertIsInstance(result, dict, f"Tool {name} should return dict")
        return result

    def assert_success(self, result: dict, msg=""):
        self.assertTrue(result.get("success"), f"Tool failed: {result.get('error', msg)}")


class TestRiskAnalysis(ToolTestCase):
    """风险分析工具测试。"""

    def test_basic_risk(self):
        r = self._run_tool("analyze_risk")
        self.assert_success(r)

    def test_risk_by_ecu(self):
        r = self._run_tool("analyze_risk", dimension="ecu")
        self.assert_success(r)

    def test_risk_top_n(self):
        r = self._run_tool("analyze_risk", top_n=3)
        self.assert_success(r)

    def test_risk_has_ranking(self):
        r = self._run_tool("analyze_risk")
        self.assert_success(r)
        # Should have risk ranking data
        self.assertTrue(
            any(k in r for k in ["ranking", "risk_ranking", "analysis", "data", "result"]),
            "Risk result should contain ranking data"
        )


class TestTrendAnalysis(ToolTestCase):
    """趋势分析工具测试。"""

    def test_basic_trend(self):
        r = self._run_tool("analyze_trend")
        self.assert_success(r)

    def test_trend_by_week(self):
        r = self._run_tool("analyze_trend", group_by="week")
        self.assert_success(r)

    def test_trend_by_month(self):
        r = self._run_tool("analyze_trend", group_by="month")
        self.assert_success(r)


class TestStatisticalSummary(ToolTestCase):
    """统计摘要工具测试。"""

    def test_basic_summary(self):
        r = self._run_tool("statistical_summary")
        self.assert_success(r)


class TestDescribeDataset(ToolTestCase):
    """数据描述工具测试。"""

    def test_describe(self):
        r = self._run_tool("describe_dataset")
        self.assert_success(r)


class TestToolRegistration(ToolTestCase):
    """工具注册测试。"""

    def test_all_tools_registered(self):
        from agent.core.intelligent_agent import IntelligentAgent
        agent = IntelligentAgent(dashboard_type="general")
        self.assertGreaterEqual(len(agent.tool_executor.tools), 20)

    def test_schema_is_json_schema(self):
        """验证所有工具的 schema 是标准 JSON Schema。"""
        from agent.core.intelligent_agent import IntelligentAgent
        agent = IntelligentAgent(dashboard_type="general")
        schemas = agent.tool_executor.get_tool_schema()

        for name, schema in schemas.items():
            params = schema.get("parameters", {})
            self.assertEqual(
                params.get("type"), "object",
                f"Tool {name} parameters should be type=object"
            )
            self.assertIn(
                "properties", params,
                f"Tool {name} parameters should have 'properties'"
            )

    def test_each_tool_executable(self):
        """验证每个工具都能被调用（不崩溃）。"""
        tools_to_test = [
            "analyze_risk", "analyze_trend", "statistical_summary",
            "describe_dataset", "analyze_matrix_distribution",
        ]
        for name in tools_to_test:
            if self.quick:
                continue
            try:
                r = self._run_tool(name)
                self.assertIsInstance(r, dict, f"{name} should return dict")
            except Exception as e:
                self.fail(f"Tool {name} crashed: {e}")


class TestExecutionEngine(ToolTestCase):
    """统一执行引擎测试。"""

    def test_rule_mode(self):
        from agent.core.execution_engine import UnifiedExecutionEngine
        from agent.core.intelligent_agent import IntelligentAgent

        agent = IntelligentAgent(dashboard_type="general")
        engine = UnifiedExecutionEngine(agent)
        plan = [{"tool": "analyze_risk", "params": {}, "step": 1}]

        result = engine.run(
            question="风险分析",
            data=self.data,
            context={},
            mode="rule",
            plan=plan,
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].tool, "analyze_risk")

    def test_multi_step_plan(self):
        from agent.core.execution_engine import UnifiedExecutionEngine
        from agent.core.intelligent_agent import IntelligentAgent

        agent = IntelligentAgent(dashboard_type="general")
        engine = UnifiedExecutionEngine(agent)
        plan = [
            {"tool": "analyze_risk", "params": {}, "step": 1},
            {"tool": "analyze_trend", "params": {}, "step": 2},
        ]

        result = engine.run(
            question="风险和趋势",
            data=self.data,
            context={},
            mode="rule",
            plan=plan,
        )
        self.assertTrue(result.success)
        self.assertGreaterEqual(len(result.steps), 1)  # At least one should succeed


class TestContextProvider(ToolTestCase):
    """Context Provider 测试。"""

    def test_data_summary_provider(self):
        from agent.core.context_provider import DataSummaryProvider
        p = DataSummaryProvider()
        result = p.provide(self.data, "风险分析", {})
        self.assertIn("data_summary", result)
        self.assertIn("行", result["data_summary"])

    def test_business_knowledge_provider(self):
        from agent.core.context_provider import BusinessKnowledgeProvider
        p = BusinessKnowledgeProvider()
        result = p.provide(self.data, "风险分析", {})
        self.assertIn("domain_knowledge", result)
        self.assertIn("缺陷密度", result["domain_knowledge"])

    def test_context_chain(self):
        from agent.core.context_provider import create_default_context_chain
        chain = create_default_context_chain()
        context = chain.build(self.data, "哪个项目风险最高？")
        self.assertIn("data_summary", context)
        self.assertIn("domain_knowledge", context)

    def test_provider_priority_order(self):
        from agent.core.context_provider import (
            DataSummaryProvider, SemanticCatalogProvider,
            HistoryProvider, BusinessKnowledgeProvider,
        )
        providers = [
            BusinessKnowledgeProvider(),
            DataSummaryProvider(),
            HistoryProvider(),
            SemanticCatalogProvider(),
        ]
        from agent.core.context_provider import ContextChain
        chain = ContextChain(providers)
        names = chain.provider_names
        # DataSummary (10) should be first
        self.assertEqual(names[0], "data_summary")


if __name__ == "__main__":
    unittest.main(verbosity=2)
