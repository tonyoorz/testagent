import unittest
from unittest.mock import patch

from agent.core.intelligent_agent import (
    _load_anomaly_rule_configs,
    clear_anomaly_rule_config_cache,
    evaluate_anomaly_rules,
)


class AnomalyRuleTests(unittest.TestCase):
    def test_anomaly_rule_configs_load_expected_catalog_keys(self):
        clear_anomaly_rule_config_cache()
        configs = _load_anomaly_rule_configs()

        self.assertIn("wow_spike_300pct", configs)
        self.assertIn("sparse_signal_suppression", configs)
        self.assertIn("risk_concentration_shift", configs)

        self.assertEqual(str(configs["wow_spike_300pct"].get("rule_key")), "wow_spike_300pct")
        self.assertEqual(str(configs["sparse_signal_suppression"].get("rule_key")), "sparse_signal_suppression")
        self.assertEqual(str(configs["risk_concentration_shift"].get("rule_key")), "risk_concentration_shift")

        self.assertEqual(float(configs["wow_spike_300pct"].get("threshold_pct")), 300.0)
        self.assertEqual(float(configs["sparse_signal_suppression"].get("min_baseline")), 3.0)
        self.assertEqual(float(configs["risk_concentration_shift"].get("share_shift_threshold_pct")), 20.0)

    def test_anomaly_detector_flags_week_over_week_spike_over_300_percent(self):
        trend_data = [
            {"group": "2026-CW10", "value": 10},
            {"group": "2026-CW11", "value": 45},
        ]

        findings = evaluate_anomaly_rules(trend_data)

        self.assertTrue(any(item.get("rule_id") == "wow_spike_300pct" for item in findings))

    def test_anomaly_detector_suppresses_sparse_signal(self):
        trend_data = [
            {"group": "2026-CW10", "value": 1},
            {"group": "2026-CW11", "value": 5},
        ]

        findings = evaluate_anomaly_rules(trend_data)

        self.assertFalse(any(item.get("rule_id") == "wow_spike_300pct" for item in findings))

    def test_anomaly_detector_flags_risk_concentration_shift(self):
        trend_data = [
            {
                "group": "2026-CW10",
                "value": 100,
                "top_risk_bucket": "SW",
                "top_share_pct": 30,
            },
            {
                "group": "2026-CW11",
                "value": 110,
                "top_risk_bucket": "Integration",
                "top_share_pct": 55,
            },
        ]

        with patch(
            "agent.core.intelligent_agent._load_anomaly_rule_configs",
            return_value={
                "wow_spike_300pct": {"enabled": True, "threshold_pct": 300.0},
                "sparse_signal_suppression": {"enabled": True, "min_baseline": 3.0, "min_current": 3.0},
                "risk_concentration_shift": {"enabled": True, "share_shift_threshold_pct": 20.0},
            },
        ):
            findings = evaluate_anomaly_rules(trend_data)

        risk_findings = [item for item in findings if item.get("rule_id") == "risk_concentration_shift"]
        self.assertEqual(len(risk_findings), 1)
        self.assertEqual(risk_findings[0].get("share_shift_pct"), 25.0)

    def test_anomaly_detector_honors_wow_threshold_override(self):
        trend_data = [
            {"group": "2026-CW10", "value": 10},
            {"group": "2026-CW11", "value": 45},
        ]

        with patch(
            "agent.core.intelligent_agent._load_anomaly_rule_configs",
            return_value={
                "wow_spike_300pct": {"enabled": True, "threshold_pct": 400.0},
                "sparse_signal_suppression": {"enabled": True, "min_baseline": 3.0, "min_current": 3.0},
                "risk_concentration_shift": {"enabled": False, "share_shift_threshold_pct": 20.0},
            },
        ):
            findings = evaluate_anomaly_rules(trend_data)

        self.assertFalse(any(item.get("rule_id") == "wow_spike_300pct" for item in findings))

    def test_sparse_suppression_does_not_block_risk_concentration_shift(self):
        trend_data = [
            {
                "group": "2026-CW10",
                "value": 1,
                "top_risk_bucket": "SW",
                "top_share_pct": 30,
            },
            {
                "group": "2026-CW11",
                "value": 2,
                "top_risk_bucket": "Integration",
                "top_share_pct": 60,
            },
        ]

        with patch(
            "agent.core.intelligent_agent._load_anomaly_rule_configs",
            return_value={
                "wow_spike_300pct": {"enabled": True, "threshold_pct": 300.0},
                "sparse_signal_suppression": {"enabled": True, "min_baseline": 3.0, "min_current": 3.0},
                "risk_concentration_shift": {"enabled": True, "share_shift_threshold_pct": 20.0},
            },
        ):
            findings = evaluate_anomaly_rules(trend_data)

        self.assertFalse(any(item.get("rule_id") == "wow_spike_300pct" for item in findings))
        self.assertTrue(any(item.get("rule_id") == "risk_concentration_shift" for item in findings))


if __name__ == "__main__":
    unittest.main()
