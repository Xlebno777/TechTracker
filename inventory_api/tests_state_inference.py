from __future__ import annotations

from django.test import SimpleTestCase

from inventory_api.forecasting.state_inference_service import (
    get_metric_forecast_control,
    infer_state_distribution,
    normalize_state_probabilities,
    resolve_metric_codes_for_source,
)


class StateInferenceServiceTests(SimpleTestCase):
    def test_low_risk_points_favor_s0(self):
        result = infer_state_distribution(
            points_by_metric={
                "cpu_load_total": 32.0,
                "mem_usage_percent": 41.0,
                "system_temperature": 39.0,
            },
        )

        self.assertEqual(result["state"], "s0")
        self.assertGreater(result["p_s0"], result["p_s1"])
        self.assertGreater(result["p_s0"], result["p_s2"])
        self.assertGreater(result["confidence"], 0.0)

    def test_high_risk_points_favor_s2(self):
        result = infer_state_distribution(
            points_by_metric={
                "cpu_load_total": 128.0,
                "mem_usage_percent": 100.0,
                "storcli_drive_temperature": 91.0,
            },
        )

        self.assertEqual(result["state"], "s2")
        self.assertGreater(result["p_s2"], result["p_s1"])
        self.assertGreater(result["p_s2"], result["p_s0"])
        top_components = result["evidence"]["top_components"]
        self.assertTrue(top_components)
        self.assertIn(
            top_components[0]["metric_code"],
            {"cpu_load_total", "mem_usage_percent", "storcli_drive_temperature"},
        )
        self.assertGreaterEqual(float(top_components[0]["risk_component"]), 0.9)

    def test_risk_features_only_mode_returns_distribution(self):
        result = infer_state_distribution(
            risk_features={
                "metric_aggregate_risk": 0.72,
                "markov_projected_p_s2": 0.95,
                "metric_results": [
                    {
                        "metric_code": "cpu_load_total",
                        "risk": 0.88,
                        "threshold": 90.0,
                        "forecast": {"y_hat": 94.0},
                    },
                    {
                        "metric_code": "system_temperature",
                        "risk": 0.93,
                        "threshold": 80.0,
                        "forecast": {"y_hat": 84.0},
                    },
                ],
            },
        )

        total = float(result["p_s0"] + result["p_s1"] + result["p_s2"])
        self.assertEqual(result["state"], "s2")
        self.assertAlmostEqual(total, 1.0, places=6)
        self.assertEqual(result["evidence"]["inference_mode"], "metric_components")

    def test_profile_override_changes_threshold_behavior(self):
        result = infer_state_distribution(
            points_by_metric={"cpu_load_total": 72.0},
            profile={
                "name": "Строгий профиль",
                "version": 2,
                "thresholds": {"cpu_load_total": 60.0},
                "risk_ratio_baseline": 0.75,
                "risk_ratio_scale": 0.75,
            },
        )

        self.assertEqual(result["evidence"]["profile"]["name"], "Строгий профиль")
        self.assertGreater(result["evidence"]["top_components"][0]["risk_component"], 0.0)
        self.assertIn("score_breakdown", result["evidence"])

    def test_formal_feature_softmax_model_exposes_features(self):
        result = infer_state_distribution(
            risk_features={
                "metric_aggregate_risk": 0.62,
                "markov_projected_p_s2": 0.78,
                "metric_results": [
                    {
                        "metric_code": "mem_usage_percent",
                        "risk": 0.71,
                        "threshold": 92.0,
                        "forecast": {"y_hat": 89.0},
                    },
                    {
                        "metric_code": "storcli_drive_temperature",
                        "risk": 0.66,
                        "threshold": 58.0,
                        "forecast": {"y_hat": 55.0},
                    },
                    {
                        "metric_code": "ping_latency_gateway",
                        "risk": 0.44,
                        "threshold": 150.0,
                        "forecast": {"y_hat": 121.0},
                    },
                ],
            },
        )

        features = result["evidence"]["feature_values"]
        self.assertIn("metric_aggregate_risk", features)
        self.assertIn("markov_p_s2", features)
        self.assertIn("temperature_risk", features)
        self.assertIn("latency_risk", features)
        self.assertEqual(result["evidence"]["score_model"]["kind"], "feature_score_softmax")
        self.assertAlmostEqual(result["p_s0"] + result["p_s1"] + result["p_s2"], 1.0, places=6)
        self.assertGreater(features["temperature_risk"], 0.0)
        self.assertGreater(features["latency_risk"], 0.0)

    def test_normalize_state_probabilities_normalizes_values(self):
        result = normalize_state_probabilities(
            p_s0=0.2,
            p_s1=0.3,
            p_s2=0.7,
        )

        self.assertAlmostEqual(result["p_s0"] + result["p_s1"] + result["p_s2"], 1.0, places=6)
        self.assertEqual(result["state"], "s2")

    def test_default_forecast_metric_controls_disable_predictive_failure_for_sarima(self):
        sarima_codes = resolve_metric_codes_for_source("sarima")
        lstm_codes = resolve_metric_codes_for_source("lstm")

        self.assertNotIn("storcli_predictive_failure_count", sarima_codes)
        self.assertIn("storcli_predictive_failure_count", lstm_codes)

        control = get_metric_forecast_control("storcli_predictive_failure_count")
        self.assertFalse(control["sarima_enabled"])
        self.assertTrue(control["lstm_enabled"])
        self.assertEqual(control["alpha_mode"], "manual")
        self.assertEqual(control["manual_alpha_sarima"], 0.0)
