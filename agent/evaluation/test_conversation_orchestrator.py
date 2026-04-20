import unittest

from agent.core.conversation_orchestrator import ConversationOrchestrator


class ConversationOrchestratorTests(unittest.TestCase):
    def test_build_request_merges_page_context_and_question(self):
        orchestrator = ConversationOrchestrator()
        request = orchestrator.build_request(
            question="按项目看风险",
            dashboard_type="defect",
            current_data={"defects": object()},
            conversation_state={"selected_team": "DTSV_China"},
            extra_context={"page_filters": {"project": ["MGU"]}},
        )
        self.assertEqual(request["question"], "按项目看风险")
        self.assertEqual(request["page_context"]["dashboard_type"], "defect")
        self.assertEqual(request["page_context"]["page_filters"], {"project": ["MGU"]})

    def test_initialize_stream_state_uses_protocol_module(self):
        orchestrator = ConversationOrchestrator()
        stream_state = orchestrator.initialize_stream_state("处理中")
        self.assertEqual(stream_state["status"], "processing")
        self.assertIn("events", stream_state)


if __name__ == "__main__":
    unittest.main()