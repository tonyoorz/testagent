import unittest
from dash import html

from agent.core.enhanced_ai_chat_manager import (
    build_duplicate_followup_query,
    count_duplicate_followup_rounds,
    append_duplicate_result_message,
    render_enhanced_duplicate_result_message,
)


class TestDuplicateFollowupQuery(unittest.TestCase):
    def test_merges_previous_user_message_when_assistant_requested_more_info(self):
        history = [
            {"role": "user", "content": "navigation failed NA6 26 07"},
            {"role": "assistant", "content": "需要补充信息后再判断，请补充具体现象。"},
            {"role": "user", "content": "地图加载失败"},
        ]

        effective_query = build_duplicate_followup_query("地图加载失败", history)

        self.assertEqual(
            effective_query,
            "navigation failed NA6 26 07\n补充信息：地图加载失败",
        )

    def test_keeps_current_message_when_no_followup_request_exists(self):
        history = [
            {"role": "user", "content": "navigation failed"},
            {"role": "assistant", "content": "这是一个新的分析结果。"},
            {"role": "user", "content": "地图加载失败"},
        ]

        effective_query = build_duplicate_followup_query("地图加载失败", history)

        self.assertEqual(effective_query, "地图加载失败")

    def test_accumulates_multiple_followup_rounds(self):
        """3-turn chain: Q1 → 需要补充 → Q2 → 需要补充 → Q3"""
        history = [
            {"role": "user", "content": "navigation failed NA6 26 07"},
            {"role": "assistant", "content": "需要补充信息后再判断，请补充具体现象。"},
            {"role": "user", "content": "车辆黑屏"},
            {"role": "assistant", "content": "需要补充信息后再判断，请补充触发场景。"},
            {"role": "user", "content": "出发场景 冷启动"},
        ]

        effective_query = build_duplicate_followup_query("出发场景 冷启动", history)

        self.assertEqual(
            effective_query,
            "navigation failed NA6 26 07\n补充信息：车辆黑屏；出发场景 冷启动",
        )

    def test_skips_reasoning_messages_in_chain(self):
        """Chat history contains reasoning/stream_response assistant messages that
        should be transparently skipped when walking the follow-up chain."""
        history = [
            {"role": "user", "content": "navigation failed NA6 26 07"},
            {"role": "assistant", "content": "AI正在思考...", "type": "reasoning"},
            {"role": "assistant", "content": "需要补充信息后再判断。"},
            {"role": "user", "content": "车辆黑屏"},
            {"role": "assistant", "content": "AI正在思考...", "type": "reasoning"},
            {"role": "assistant", "content": "需要补充信息后再判断。"},
            {"role": "user", "content": "出发场景 冷启动"},
        ]

        effective_query = build_duplicate_followup_query("出发场景 冷启动", history)

        self.assertEqual(
            effective_query,
            "navigation failed NA6 26 07\n补充信息：车辆黑屏；出发场景 冷启动",
        )

    def test_long_current_message_is_standalone(self):
        """If the current message is longer than the threshold, treat it as a new query."""
        long_msg = "A" * 50
        history = [
            {"role": "user", "content": "navigation failed NA6 26 07"},
            {"role": "assistant", "content": "需要补充信息后再判断。"},
            {"role": "user", "content": long_msg},
        ]
        self.assertEqual(build_duplicate_followup_query(long_msg, history), long_msg)


class TestCountDuplicateFollowupRounds(unittest.TestCase):
    def test_zero_when_no_followup(self):
        history = [
            {"role": "user", "content": "navigation failed"},
            {"role": "assistant", "content": "可以提票。"},
            {"role": "user", "content": "地图加载失败"},
        ]
        self.assertEqual(count_duplicate_followup_rounds("地图加载失败", history), 0)

    def test_one_for_single_followup(self):
        history = [
            {"role": "user", "content": "navigation failed NA6 26 07"},
            {"role": "assistant", "content": "需要补充信息后再判断。"},
            {"role": "user", "content": "车辆黑屏"},
        ]
        self.assertEqual(count_duplicate_followup_rounds("车辆黑屏", history), 1)

    def test_two_for_double_followup(self):
        history = [
            {"role": "user", "content": "navigation failed NA6 26 07"},
            {"role": "assistant", "content": "需要补充信息后再判断。"},
            {"role": "user", "content": "车辆黑屏"},
            {"role": "assistant", "content": "需要补充信息后再判断。"},
            {"role": "user", "content": "出发场景 冷启动"},
        ]
        self.assertEqual(count_duplicate_followup_rounds("出发场景 冷启动", history), 2)


class TestEnhancedDuplicateResultCards(unittest.TestCase):
    def test_render_enhanced_duplicate_result_message_contains_ticket_level_feedback_buttons(self):
        message = {
            "role": "assistant",
            "type": "duplicate-search-result",
            "content": "【结论】\n- 建议：不建议提票",
            "duplicate_result": {
                "query_text": "speech cannot wakeup",
                "dashboard_type": "defect",
                "candidates": [
                    {
                        "ticket_id": "2649794",
                        "name": "Speech can't wake up",
                        "project": "IDCEVO",
                        "pu": "26-11",
                        "status_phase": "04-In Progress",
                        "snippet": "标题完全一致，均为语音无法唤醒。",
                        "score_1_10": 9,
                        "similarity": 0.91,
                        "rank_pos": 0,
                    }
                ],
            },
        }

        component = render_enhanced_duplicate_result_message(message, chat_id_prefix="defect-explore-chat")

        self.assertIsInstance(component, html.Div)
        component_repr = repr(component)
        self.assertIn("2649794", component_repr)
        self.assertIn("👍 匹配", component_repr)
        self.assertIn("👎 不匹配", component_repr)
        self.assertIn("defect-explore-chat-dup-feedback", component_repr)

    def test_append_duplicate_result_message_adds_structured_card_after_llm_summary(self):
        chat_messages = [
            {"role": "assistant", "type": "stream_response", "content": "LLM summary"}
        ]
        streaming_state = {
            "is_duplicate_search": True,
            "duplicate_payload": {
                "query_text": "speech cannot wakeup",
                "dashboard_type": "defect",
                "candidates": [
                    {
                        "ticket_id": "2649794",
                        "name": "Speech can't wake up",
                        "score_1_10": 9,
                        "rank_pos": 0,
                    }
                ],
            },
        }

        updated_messages = append_duplicate_result_message(chat_messages, streaming_state)

        self.assertEqual(len(updated_messages), 2)
        self.assertEqual(updated_messages[-1]["type"], "duplicate-search-result")
        self.assertEqual(updated_messages[-1]["duplicate_result"]["candidates"][0]["ticket_id"], "2649794")


if __name__ == "__main__":
    unittest.main()