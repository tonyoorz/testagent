import os
import unittest
from unittest.mock import Mock, patch

from agent.core.intelligent_agent import IntelligentAgent


class IntelligentAgentRuntimeSpineTests(unittest.TestCase):
    def test_resolve_runtime_mode_prefers_request_execution_mode(self):
        agent = IntelligentAgent.__new__(IntelligentAgent)
        agent.tool_executor = Mock()
        agent.tool_executor._llm = object()

        with patch.dict(os.environ, {'AGENT_MODE': 'agentic'}, clear=False):
            runtime = agent._resolve_runtime_mode(request={'execution_mode': 'rule'})

        self.assertEqual(runtime['requested_mode'], 'rule')
        self.assertEqual(runtime['mode'], 'rule')

    def test_resolve_runtime_mode_keeps_internal_template_fallback(self):
        agent = IntelligentAgent.__new__(IntelligentAgent)
        llm = Mock()
        llm._should_use_internal_template_for_nonstream.return_value = True
        agent.tool_executor = Mock()
        agent.tool_executor._llm = llm

        with patch.dict(os.environ, {'AGENT_MODE': 'rule'}, clear=False):
            runtime = agent._resolve_runtime_mode(request={'execution_mode': 'agentic'})

        self.assertEqual(runtime['requested_mode'], 'agentic')
        self.assertTrue(runtime['internal_template_route'])
        self.assertEqual(runtime['mode'], 'hybrid')


if __name__ == '__main__':
    unittest.main()