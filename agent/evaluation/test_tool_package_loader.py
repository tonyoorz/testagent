import unittest
from unittest.mock import patch

from agent.core.tool_executor import ToolExecutor


class _FakeTool:
    def __init__(self, name='packaged_tool'):
        self.name = name
        self.description = name
        self.parameters = {}

    def expects_datasets(self):
        return False

    def execute(self, data, **kwargs):
        return {'success': True, 'tool': self.name, 'result': {'ok': True}}


class ToolPackageLoaderTests(unittest.TestCase):
    def test_tool_executor_prefers_packaged_tool_suite(self):
        with patch('agent.tools.build_tool_suite', return_value=[_FakeTool('packaged_tool')]) as packaged_factory:
            executor = ToolExecutor(default_tool_factory=None)

        self.assertIn('packaged_tool', executor.tools)
        packaged_factory.assert_called_once()

    def test_tool_executor_falls_back_when_packaged_tool_suite_fails(self):
        with patch('agent.tools.build_tool_suite', side_effect=RuntimeError('boom')):
            executor = ToolExecutor(default_tool_factory=lambda llm, db_path: [_FakeTool('legacy_tool')])

        self.assertIn('legacy_tool', executor.tools)


if __name__ == '__main__':
    unittest.main()