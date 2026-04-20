import unittest

from agent.core.tracer import AgentTracer


class AgentTracerTests(unittest.TestCase):
    def test_record_captures_event_payload(self):
        tracer = AgentTracer(enabled=True)

        tracer.record('context_ready', primary_dataset='defects', intents=['trend'])

        exported = tracer.export()
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]['event'], 'context_ready')
        self.assertEqual(exported[0]['primary_dataset'], 'defects')
        self.assertEqual(exported[0]['intents'], ['trend'])

    def test_disabled_tracer_ignores_events(self):
        tracer = AgentTracer(enabled=False)

        tracer.record('runtime_mode', mode='rule')

        self.assertEqual(tracer.export(), [])


if __name__ == '__main__':
    unittest.main()