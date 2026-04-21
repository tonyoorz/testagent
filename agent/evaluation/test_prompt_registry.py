import unittest

from agent.core.prompt_registry import PromptRegistry


class PromptRegistryTests(unittest.TestCase):
    def test_render_uses_registered_template(self):
        registry = PromptRegistry(include_defaults=False)
        registry.register('demo', 'Hello {{name}}')

        self.assertEqual(registry.render('demo', name='BMW'), 'Hello BMW')

    def test_render_dashboard_prompt_falls_back_to_general(self):
        registry = PromptRegistry(include_defaults=True)

        prompt = registry.render_dashboard_prompt('unknown', data_context='ctx')

        self.assertIn('ctx', prompt)
        self.assertIn('data analysis assistant', prompt.lower())


if __name__ == '__main__':
    unittest.main()