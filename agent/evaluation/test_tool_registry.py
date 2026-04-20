import unittest

from agent.tools.registry import ToolRegistry, normalize_params_to_json_schema


class DummyTool:
    name = 'analyze_trend'
    description = 'Analyze trend'
    parameters = {
        'group_by': {'type': 'string', 'description': 'Grouping dimension'},
        'top_n': {'type': 'integer', 'description': 'Top rows'},
    }


class ToolRegistryTests(unittest.TestCase):
    def test_normalize_params_to_json_schema_converts_parameter_map(self):
        schema = normalize_params_to_json_schema(
            {
                'group_by': {'type': 'string', 'description': 'Grouping dimension'},
                'top_n': {'type': 'integer', 'description': 'Top rows'},
            }
        )

        self.assertEqual(schema['type'], 'object')
        self.assertEqual(schema['properties']['group_by']['type'], 'string')
        self.assertEqual(schema['properties']['top_n']['type'], 'integer')

    def test_registry_exports_json_schema_for_registered_tool(self):
        registry = ToolRegistry()
        registry.register(DummyTool())

        exported = registry.export()['analyze_trend']

        self.assertEqual(exported['description'], 'Analyze trend')
        self.assertIn('parameters', exported)
        self.assertIn('json_schema', exported)
        self.assertEqual(exported['json_schema']['properties']['group_by']['type'], 'string')


if __name__ == '__main__':
    unittest.main()