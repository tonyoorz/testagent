import unittest
from datetime import datetime, timezone
import importlib.util
import pathlib

import longrunner_analysis


def _load_phase_transfer_report_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    module_path = repo_root / "report" / "generate_phase_transfer_report.py"
    spec = importlib.util.spec_from_file_location("phase_transfer_report_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PhaseTransferReportTests(unittest.TestCase):
    def test_build_phase_segments_extends_latest_open_phase(self):
        history_data = {
            "data": [
                {
                    "timestamp": "2026-04-01T08:00:00Z",
                    "user_name": "tester-a",
                    "change_set": [
                        {
                            "field_name": "phase",
                            "old_value_text": "01-New",
                            "value_text": "02-In Pre-Analysis",
                        }
                    ],
                },
                {
                    "timestamp": "2026-04-03T08:00:00Z",
                    "user_name": "tester-b",
                    "change_set": [
                        {
                            "field_name": "phase",
                            "old_value_text": "02-In Pre-Analysis",
                            "value_text": "03-In Analysis",
                        }
                    ],
                },
            ]
        }

        now = datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc)

        segments = longrunner_analysis.build_phase_segments(
            history_data,
            ticket_meta={"ticket_id": "2595772", "ticket_name": "Demo ticket"},
            now=now,
        )

        self.assertEqual(len(segments), 2)

        self.assertEqual(segments[0]["phase"], "02-In Pre-Analysis")
        self.assertEqual(segments[0]["duration_hours"], 48.0)
        self.assertFalse(segments[0]["is_open_segment"])

        self.assertEqual(segments[1]["phase"], "03-In Analysis")
        self.assertEqual(segments[1]["duration_hours"], 48.0)
        self.assertTrue(segments[1]["is_open_segment"])
        self.assertEqual(segments[1]["ticket_id"], "2595772")
        self.assertEqual(segments[1]["ticket_name"], "Demo ticket")

    def test_build_group_time_statistics_uses_existing_qgate_classification(self):
        report_module = _load_phase_transfer_report_module()
        stats = report_module.build_group_time_statistics(
            [
                {
                    "ticket_id": "1",
                    "from_phase": "02-In Pre-Analysis",
                    "phase": "03-In Analysis",
                    "to_phase": "03-In Analysis",
                    "duration_days": 1.5,
                },
                {
                    "ticket_id": "1",
                    "from_phase": "03-In Analysis",
                    "phase": "04-In Progress",
                    "to_phase": "04-In Progress",
                    "duration_days": 2.0,
                },
                {
                    "ticket_id": "2",
                    "from_phase": "01-New",
                    "phase": "02-In Pre-Analysis",
                    "to_phase": "02-In Pre-Analysis",
                    "duration_days": 3.0,
                },
            ]
        )

        self.assertEqual([row["Group"] for row in stats], ["Q-Gate", "Integration", "CoC"])
        self.assertEqual(stats[0]["Transfers"], 1)
        self.assertEqual(stats[0]["Total Days"], 1.5)
        self.assertEqual(stats[1]["Total Days"], 3.0)
        self.assertEqual(stats[2]["Avg Days"], 2.0)

    def test_build_group_transition_rankings_sorts_by_avg_days_desc(self):
        report_module = _load_phase_transfer_report_module()
        rankings = report_module.build_group_transition_rankings(
            [
                {
                    "ticket_id": "1",
                    "from_phase": "02-In Pre-Analysis",
                    "phase": "03-In Analysis",
                    "to_phase": "03-In Analysis",
                    "duration_days": 1.0,
                },
                {
                    "ticket_id": "2",
                    "from_phase": "02-In Pre-Analysis",
                    "phase": "03-In Analysis",
                    "to_phase": "03-In Analysis",
                    "duration_days": 3.0,
                },
                {
                    "ticket_id": "1",
                    "from_phase": "03-In Analysis",
                    "phase": "04-In Progress",
                    "to_phase": "04-In Progress",
                    "duration_days": 5.0,
                },
                {
                    "ticket_id": "2",
                    "from_phase": "03-In Analysis",
                    "phase": "04-In Progress",
                    "to_phase": "04-In Progress",
                    "duration_days": 1.0,
                },
                {
                    "ticket_id": "9",
                    "from_phase": "01-New",
                    "phase": "02-In Pre-Analysis",
                    "to_phase": "02-In Pre-Analysis",
                    "duration_days": 2.0,
                },
            ]
        )

        self.assertEqual(list(rankings.keys()), ["Q-Gate", "Integration", "CoC"])
        self.assertEqual(rankings["CoC"][0]["Phase Transition"], "03-In Analysis → 04-In Progress")
        self.assertEqual(rankings["CoC"][0]["Avg Days"], 3.0)
        self.assertEqual(rankings["Q-Gate"][0]["Count"], 2)
        self.assertEqual(rankings["Integration"][0]["Avg Days"], 2.0)

    def test_build_timeline_figure_uses_top_date_axis_and_defect_id_labels(self):
        report_module = _load_phase_transfer_report_module()
        figure = report_module._build_timeline_figure(
            [
                {
                    "ticket_id": "2595772",
                    "ticket_name": "Demo ticket A",
                    "phase": "02-In Pre-Analysis",
                    "start_time": "2026-04-01T08:00:00+00:00",
                    "end_time": "2026-04-03T08:00:00+00:00",
                    "duration_days": 2.0,
                    "is_open_segment": False,
                },
                {
                    "ticket_id": "2601939",
                    "ticket_name": "Long title that should not be used as y label",
                    "phase": "03-In Analysis",
                    "start_time": "2026-04-02T08:00:00+00:00",
                    "end_time": "2026-04-05T08:00:00+00:00",
                    "duration_days": 3.0,
                    "is_open_segment": False,
                },
            ]
        )

        self.assertEqual(figure.layout.yaxis.title.text, "Defect ID")
        self.assertEqual(figure.layout.xaxis.side, "top")
        self.assertGreaterEqual(figure.layout.height, 500)
        self.assertIn("2595772", list(figure.data[0].y))
        self.assertNotIn("2595772 | Demo ticket A", list(figure.data[0].y))

    def test_render_html_report_contains_ticket_names_and_summary(self):
        report_module = _load_phase_transfer_report_module()
        html_text = report_module.render_phase_transfer_report_html(
            {
                "summary": {
                    "ticket_count": 1,
                    "segment_count": 2,
                    "avg_duration_days": 2.0,
                    "longest_segment_label": "03-In Analysis",
                },
                "group_time_stats": [
                    {
                        "Group": "Q-Gate",
                        "Transfers": 1,
                        "Tickets": 1,
                        "Total Days": 2.0,
                        "Avg Days": 2.0,
                        "Median Days": 2.0,
                        "Max Days": 2.0,
                    }
                ],
                "group_transition_rankings": {
                    "Q-Gate": [
                        {
                            "Phase Transition": "02-In Pre-Analysis → 03-In Analysis",
                            "Avg Days": 2.0,
                            "Count": 1,
                            "Total Days": 2.0,
                        }
                    ],
                    "Integration": [],
                    "CoC": [],
                },
                "segments": [
                    {
                        "ticket_id": "2595772",
                        "ticket_name": "Demo ticket",
                        "phase": "02-In Pre-Analysis",
                        "start_time": "2026-04-01T08:00:00+00:00",
                        "end_time": "2026-04-03T08:00:00+00:00",
                        "duration_hours": 48.0,
                        "duration_days": 2.0,
                        "is_open_segment": False,
                    },
                    {
                        "ticket_id": "2595772",
                        "ticket_name": "Demo ticket",
                        "phase": "03-In Analysis",
                        "start_time": "2026-04-03T08:00:00+00:00",
                        "end_time": "2026-04-05T08:00:00+00:00",
                        "duration_hours": 48.0,
                        "duration_days": 2.0,
                        "is_open_segment": True,
                    },
                ],
                "missing_ticket_ids": ["9999999"],
                "generated_at": "2026-04-16T10:00:00+00:00",
            }
        )

        self.assertIn("Phase Transfer Report", html_text)
        self.assertIn("2595772", html_text)
        self.assertIn("Demo ticket", html_text)
        self.assertIn("Avg Duration", html_text)
        self.assertIn("Q-Gate", html_text)
        self.assertIn("Group Time Statistics", html_text)
        self.assertIn("Top Transition Rankings", html_text)
        self.assertIn("02-In Pre-Analysis → 03-In Analysis", html_text)
        self.assertIn('href="https://octane-prod.bmwgroup.net/ui/entity-navigation?p=1002/2001&entityType=work_item&id=2595772"', html_text)
        self.assertIn("9999999", html_text)


if __name__ == "__main__":
    unittest.main()