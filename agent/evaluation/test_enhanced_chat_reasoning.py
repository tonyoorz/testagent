import unittest
import os
from unittest.mock import patch

from agent.core.enhanced_ai_chat_manager import (
    apply_summary_query_strategy_override,
    append_stream_event_to_store,
    build_summary_schema_column_views,
    build_stream_reasoning_content,
    build_summary_uncertainty_line,
    build_timeline_view_models,
    decide_summary_query_execution_strategy,
    downgrade_unsupported_claims,
    format_total_count_display,
    infer_summary_evidence_gaps,
    resolve_summary_scope_team,
    should_resume_pending_agent_confirmation,
)


class EnhancedChatReasoningTests(unittest.TestCase):
    def test_build_summary_schema_column_views_keeps_full_schema_for_runtime(self):
        columns = [f"col_{idx}" for idx in range(48)] + ["project", "tproject", "severity_group"]

        views = build_summary_schema_column_views(columns, preview_limit=30)

        self.assertEqual(len(views["preview"]), 30)
        self.assertNotIn("project", views["preview"])
        self.assertIn("project", views["full"])
        self.assertIn("tproject", views["full"])

    def test_resolve_summary_scope_team_returns_empty_without_env_or_hints(self):
        with patch.dict(os.environ, {}, clear=True):
            resolved = resolve_summary_scope_team({})

        self.assertEqual(resolved.get("scope_team"), "")
        self.assertEqual(resolved.get("source"), "")

    def test_format_total_count_display_uses_numeric_when_known(self):
        self.assertEqual(format_total_count_display(128), "128")

    def test_format_total_count_display_uses_unknown_marker_when_unknown(self):
        self.assertEqual(format_total_count_display(None), "unknown")

    def test_build_summary_uncertainty_line_reports_insufficient_evidence_when_gap_exists(self):
        text = build_summary_uncertainty_line(["结果缺少功能字段，无法回答模块分布"])

        self.assertIn("insufficient evidence", text.lower())
        self.assertIn("结果缺少功能字段", text)

    def test_decide_summary_query_execution_strategy_prefers_deterministic_for_structured_asks(self):
        decision = decide_summary_query_execution_strategy(
            question="请给我matrix severity分布Top 10，并看通过率趋势",
            columns=["topissue_display", "severity_group", "test_week", "run_status"],
        )

        self.assertEqual(decision.get("strategy"), "deterministic_first")

    def test_apply_summary_query_strategy_override_forces_deterministic_metadata(self):
        overridden = apply_summary_query_strategy_override(
            query_strategy={"strategy": "constrained_fallback", "confidence": 0.22},
            configured_mode="deterministic",
        )

        self.assertEqual(overridden.get("strategy"), "deterministic_first")
        self.assertGreaterEqual(float(overridden.get("confidence") or 0.0), 0.65)
        self.assertEqual(overridden.get("forced_by_env"), "deterministic")
        self.assertTrue(overridden.get("prefer_deterministic"))

    def test_apply_summary_query_strategy_override_forces_agent_metadata(self):
        overridden = apply_summary_query_strategy_override(
            query_strategy={"strategy": "deterministic_first", "confidence": 0.9, "prefer_deterministic": True},
            configured_mode="agent",
        )

        self.assertEqual(overridden.get("strategy"), "constrained_fallback")
        self.assertLessEqual(float(overridden.get("confidence") or 1.0), 0.55)
        self.assertEqual(overridden.get("forced_by_env"), "agent")
        self.assertFalse(overridden.get("prefer_deterministic"))

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

    def test_downgrade_unsupported_claims_softens_strong_confident_phrasing_when_gaps_exist(self):
        answer = "该问题已经被完全证明，结论是必然的，并且一定正确。"
        evidence_bundle = {"evidence_gap": ["结果中缺少关键字段，无法确认全部结论"]}

        downgraded = downgrade_unsupported_claims(answer, evidence_bundle)

        self.assertNotIn("完全证明", downgraded)
        self.assertNotIn("必然", downgraded)
        self.assertNotIn("一定", downgraded)
        self.assertIn("无法确认", downgraded)

    def test_downgrade_unsupported_claims_keeps_text_when_no_evidence_gap(self):
        answer = "结论是必然的。"
        evidence_bundle = {"evidence_gap": []}

        same_text = downgrade_unsupported_claims(answer, evidence_bundle)

        self.assertEqual(same_text, answer)

    def test_downgrade_unsupported_claims_handles_proven_and_proved_variants(self):
        answer = "This trend is proven and was proved by last week's data."
        evidence_bundle = {"evidence_gap": ["sample is partial"]}

        downgraded = downgrade_unsupported_claims(answer, evidence_bundle)

        self.assertNotRegex(downgraded, r"\bproven\b")
        self.assertNotRegex(downgraded, r"\bproved\b")
        self.assertIn("suggests", downgraded.lower())
        self.assertIn("无法确认", downgraded)

    def test_should_resume_pending_agent_confirmation_detects_positive_reply(self):
        self.assertTrue(
            should_resume_pending_agent_confirmation(
                user_message="继续",
                agent_results={
                    "last_agent_context": {
                        "needs_confirmation": True,
                        "confirmation_pending": True,
                    }
                },
            )
        )

    def test_should_resume_pending_agent_confirmation_ignores_normal_query(self):
        self.assertFalse(
            should_resume_pending_agent_confirmation(
                user_message="请看IDCEVO缺陷趋势",
                agent_results={
                    "last_agent_context": {
                        "needs_confirmation": True,
                        "confirmation_pending": True,
                    }
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
