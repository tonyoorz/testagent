import unittest

from agent.core.streaming_protocol import append_event, init_stream_state


class StreamingProtocolTests(unittest.TestCase):
    def test_init_stream_state_sets_expected_defaults(self):
        state = init_stream_state("Agent working...")
        self.assertEqual(state["status"], "processing")
        self.assertEqual(state["progress"], "Agent working...")
        self.assertEqual(state["events"], [])

    def test_append_event_caps_event_count_and_normalizes_status(self):
        state = init_stream_state("x")
        for idx in range(3):
            append_event(state, kind="tool", title=f"step-{idx}", status="unknown", limit=2)
        self.assertEqual(len(state["events"]), 2)
        self.assertEqual(state["events"][-1]["status"], "info")
        self.assertEqual(state["events"][-1]["title"], "step-2")


if __name__ == "__main__":
    unittest.main()