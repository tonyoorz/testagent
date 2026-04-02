import unittest

from agent.core.enhanced_ai_chat_manager import (
    append_stream_event_to_store,
    build_stream_reasoning_content,
    build_timeline_view_models,
    infer_summary_evidence_gaps,
)


class EnhancedChatReasoningTests(unittest.TestCase):
    def test_append_stream_event_creates_append_only_timeline(self):
        stream_entry = {"events": []}

        first = append_stream_event_to_store(stream_entry, kind="route_decision", title="route")
        second = append_stream_event_to_store(stream_entry, kind="tool_start", title="tool")

        self.assertEqual(len(stream_entry["events"]), 2)
        self.assertEqual(stream_entry["events"][0]["id"], first["id"])
        self.assertEqual(stream_entry["events"][1]["id"], second["id"])
        self.assertEqual(stream_entry["events"][0]["title"], "route")
        self.assertEqual(stream_entry["events"][1]["title"], "tool")

    def test_build_reasoning_content_dedupes_and_adds_elapsed(self):
        stream_data = {
            "route_reasoning": "请求模式: Agent\n执行路由: Agent (数据库直读)",
            "reasoning": "调用工具: get_db_profile\n调用工具: get_db_profile\n工具结果: get_db_profile [ok] 18ms",
            "progress": "正在执行数据库查询...",
            "summary_trace": {
                "stage": "run_sql_tool",
                "execution_path": ["sql_generate:tool", "sql_run:tool"],
            },
            "status": "processing",
            "started_at": 100.0,
        }

        content = build_stream_reasoning_content(stream_data, now_ts=108.9)

        self.assertIn("- 请求模式: Agent", content)
        self.assertIn("- 阶段: run_sql_tool", content)
        self.assertIn("- 路径: sql_generate:tool > sql_run:tool", content)
        self.assertIn("- 耗时: 8s", content)
        self.assertEqual(content.count("调用工具: get_db_profile"), 1)

    def test_build_reasoning_content_handles_empty_input(self):
        self.assertEqual(build_stream_reasoning_content({}, now_ts=123.0), "")
        self.assertEqual(build_stream_reasoning_content({"status": "completed"}, now_ts=123.0), "")

    def test_build_timeline_view_models_marks_error_events_expanded(self):
        stream_data = {
            "started_at": 100.0,
            "events": [
                {
                    "id": "evt_1",
                    "ts": 101.2,
                    "kind": "error",
                    "title": "工具执行失败",
                    "status": "error",
                    "summary": "bad request",
                    "details": {"tool": "query_sqlite_with_fix"},
                }
            ],
        }

        rows = build_timeline_view_models(stream_data, now_ts=103.0)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "工具执行失败")
        self.assertEqual(rows[0]["elapsed_label"], "+1.2s")
        self.assertTrue(rows[0]["expanded"])
        self.assertIn("query_sqlite_with_fix", rows[0]["details_text"])

    def test_infer_summary_evidence_gaps_for_feature_question_without_feature_fields(self):
        gaps = infer_summary_evidence_gaps(
            question="3月份showstopper candidate发现了多少 都是哪些功能",
            sql_used='SELECT week, defect_count FROM "octane_defects" GROUP BY week',
            rows=[{"week": "2026-W10", "defect_count": 228}],
            table_name="octane_defects",
        )

        self.assertTrue(any("功能" in gap for gap in gaps))
        self.assertTrue(any("showstopper" in gap.lower() for gap in gaps))
        self.assertTrue(any("聚合" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
