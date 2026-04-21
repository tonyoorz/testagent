import unittest

from agent.core.query_memory import QueryMemory


class QueryMemoryTests(unittest.TestCase):
    def test_add_query_keeps_recent_entries(self):
        memory = QueryMemory(max_entries=2)

        memory.add_query('q1', answer='a1', intents=['general'])
        memory.add_query('q2', answer='a2', intents=['defect'])
        memory.add_query('q3', answer='a3', intents=['test'])

        entries = memory.list_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['question'], 'q2')
        self.assertEqual(entries[1]['question'], 'q3')

    def test_build_prompt_context_formats_recent_queries(self):
        memory = QueryMemory(max_entries=3)
        memory.add_query('show weekly defects', answer='weekly answer', intents=['defect'])

        context = memory.build_prompt_context()

        self.assertIn('show weekly defects', context)
        self.assertIn('weekly answer', context)


if __name__ == '__main__':
    unittest.main()