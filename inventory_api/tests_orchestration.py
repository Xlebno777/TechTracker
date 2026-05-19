from __future__ import annotations

from datetime import timedelta
import math

from django.test import TestCase
from django.utils import timezone

from inventory_api.forecasting.orchestration_service import (
    ORCHESTRATOR_KIND,
    _build_ensemble_prediction,
    _metric_alpha_for_device,
    build_ensemble_run_for_sources,
    materialize_pending_ensembles,
)
from inventory_api.models import Device, DeviceType, ForecastPoint, ForecastRun, RawMetric, StateEstimate, StateInferenceProfile


class ForecastOrchestrationTests(TestCase):
    def setUp(self):
        self.device_type = DeviceType.objects.create(name="Сервер")
        self.device = Device.objects.create(
            name="Srv 1",
            serial_number="HOST-001",
            device_type=self.device_type,
            status="active",
        )

    def test_materialize_pending_ensembles_builds_uncertainty_aware_points(self):
        now = timezone.now()
        previous_sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )
        previous_lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h,7d,30d",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h,7d,30d",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={
                "freq": "1h",
                "orchestrator_kind": ORCHESTRATOR_KIND,
                "paired_sarima_run_id": sarima_run.id,
                "ensemble_weights": {"sarima": 0.5, "lstm": 0.5},
            },
            quality={},
        )

        historical_target = now - timedelta(days=1)
        RawMetric.objects.create(
            device=self.device,
            code="cpu_load_total",
            value=44.0,
            unit="%",
            timestamp=historical_target,
            labels={"source": "test"},
        )
        ForecastPoint.objects.create(
            run=previous_sarima_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=historical_target,
            model_kind="sarima",
            y_hat=43.0,
            p10=38.0,
            p50=43.0,
            p90=48.0,
            alpha=0.2,
            labels={"source": "sarima_baseline", "freq": "1h"},
        )
        ForecastPoint.objects.create(
            run=previous_lstm_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=historical_target,
            model_kind="lstm",
            y_hat=54.0,
            p10=49.0,
            p50=54.0,
            p90=59.0,
            alpha=0.2,
            labels={"source": "lstm_remote", "freq": "1h"},
        )
        ForecastPoint.objects.create(
            run=sarima_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="sarima",
            y_hat=40.0,
            p10=35.0,
            p50=40.0,
            p90=45.0,
            alpha=0.2,
            labels={"source": "sarima_baseline"},
        )
        ForecastPoint.objects.create(
            run=lstm_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=24, minutes=1),
            model_kind="lstm",
            y_hat=50.0,
            p10=45.0,
            p50=50.0,
            p90=55.0,
            alpha=0.2,
            labels={"source": "lstm_remote"},
        )

        payload = materialize_pending_ensembles(run_id=lstm_run.id)
        self.assertEqual(payload["ensemble_runs_created"], 1)

        lstm_run.refresh_from_db()
        ensemble_run_id = lstm_run.parameters.get("ensemble_run_id")
        self.assertIsNotNone(ensemble_run_id)

        ensemble_run = ForecastRun.objects.get(id=ensemble_run_id)
        self.assertEqual(ensemble_run.model_kind, "ensemble")
        self.assertEqual(ensemble_run.status, "success")

        point = ForecastPoint.objects.get(run=ensemble_run, metric_code="cpu_load_total", horizon="24h")
        expected_alpha = 0.85
        self.assertAlmostEqual(point.alpha, expected_alpha, places=4)
        expected_y_hat = expected_alpha * 40.0 + (1.0 - expected_alpha) * 50.0
        expected_half_width = math.sqrt(
            (expected_alpha * 5.0) ** 2
            + ((1.0 - expected_alpha) * 5.0) ** 2
            + (0.5 * 10.0) ** 2
        )
        self.assertAlmostEqual(point.y_hat, expected_y_hat, places=4)
        self.assertAlmostEqual(point.p10, expected_y_hat - expected_half_width, places=4)
        self.assertAlmostEqual(point.p90, expected_y_hat + expected_half_width, places=4)
        self.assertEqual(point.labels["uncertainty_method"], "weighted_interval_plus_model_disagreement")
        self.assertAlmostEqual(point.labels["uncertainty_components"]["model_disagreement"], 5.0, places=4)
        self.assertEqual(point.labels["alpha_selection"]["selection_method"], "winner_bias_recent_compatible_error")
        self.assertEqual(point.labels["alpha_selection"]["sarima"]["mode"], "historical_segment_error")
        self.assertEqual(point.labels["alpha_selection"]["lstm"]["mode"], "historical_segment_error")

        self.assertTrue(StateEstimate.objects.filter(run=ensemble_run, horizon="24h").exists())

    def test_profile_controls_override_alpha_and_disable_sarima_metric(self):
        StateInferenceProfile.objects.create(
            name="Профиль источников",
            version=1,
            is_active=True,
            forecast_metric_controls={
                "cpu_load_total": {
                    "sarima_enabled": True,
                    "lstm_enabled": True,
                    "alpha_mode": "manual",
                    "manual_alpha_sarima": 0.25,
                },
                "storcli_predictive_failure_count": {
                    "sarima_enabled": False,
                    "lstm_enabled": True,
                    "alpha_mode": "manual",
                    "manual_alpha_sarima": 0.0,
                },
            },
        )

        now = timezone.now()
        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={
                "orchestrator_kind": ORCHESTRATOR_KIND,
                "paired_sarima_run_id": sarima_run.id,
                "ensemble_weights": {"sarima": 0.5, "lstm": 0.5},
            },
            quality={},
        )

        ForecastPoint.objects.create(
            run=sarima_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="sarima",
            y_hat=40.0,
            p10=35.0,
            p50=40.0,
            p90=45.0,
            alpha=0.2,
            labels={"source": "sarima_baseline"},
        )
        ForecastPoint.objects.create(
            run=lstm_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="lstm",
            y_hat=60.0,
            p10=54.0,
            p50=60.0,
            p90=66.0,
            alpha=0.2,
            labels={"source": "lstm_remote"},
        )
        ForecastPoint.objects.create(
            run=sarima_run,
            device=self.device,
            metric_code="storcli_predictive_failure_count",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="sarima",
            y_hat=2.0,
            p10=1.0,
            p50=2.0,
            p90=3.0,
            alpha=0.2,
            labels={"source": "sarima_baseline"},
        )
        ForecastPoint.objects.create(
            run=lstm_run,
            device=self.device,
            metric_code="storcli_predictive_failure_count",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="lstm",
            y_hat=1.0,
            p10=0.5,
            p50=1.0,
            p90=1.5,
            alpha=0.2,
            labels={"source": "lstm_remote"},
        )

        payload = materialize_pending_ensembles(run_id=lstm_run.id)
        self.assertEqual(payload["ensemble_runs_created"], 1)

        lstm_run.refresh_from_db()
        ensemble_run = ForecastRun.objects.get(id=lstm_run.parameters["ensemble_run_id"])

        cpu_point = ForecastPoint.objects.get(run=ensemble_run, metric_code="cpu_load_total", horizon="24h")
        self.assertAlmostEqual(cpu_point.alpha, 0.25, places=6)
        self.assertAlmostEqual(cpu_point.y_hat, 55.0, places=6)
        self.assertEqual(cpu_point.labels["alpha_selection"]["selection_method"], "manual_profile_override")

        predictive_point = ForecastPoint.objects.get(
            run=ensemble_run,
            metric_code="storcli_predictive_failure_count",
            horizon="24h",
        )
        self.assertAlmostEqual(predictive_point.alpha, 0.0, places=6)
        self.assertAlmostEqual(predictive_point.y_hat, 1.0, places=6)
        self.assertEqual(predictive_point.labels["source_mode"], "lstm_only")

    def test_auto_alpha_uses_trend_proxy_when_history_is_missing(self):
        now = timezone.now()
        start = now - timedelta(days=20)
        rows = []
        for idx in range(20 * 24):
            ts = start + timedelta(hours=idx)
            value = 20.0 + (idx * 0.08)
            rows.append(
                RawMetric(
                    device=self.device,
                    code="cpu_load_total",
                    value=value,
                    unit="%",
                    timestamp=ts,
                    labels={"source": "test"},
                )
            )
        RawMetric.objects.bulk_create(rows, batch_size=500)

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={"freq": "1h"},
            quality={},
        )

        sarima_point = ForecastPoint.objects.create(
            run=sarima_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="30d",
            target_ts=now + timedelta(days=30),
            model_kind="sarima",
            y_hat=52.0,
            p10=42.0,
            p50=52.0,
            p90=62.0,
            alpha=0.2,
            labels={"source": "sarima_baseline", "freq": "1h"},
        )
        lstm_point = ForecastPoint.objects.create(
            run=lstm_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="30d",
            target_ts=now + timedelta(days=30),
            model_kind="lstm",
            y_hat=31.0,
            p10=21.0,
            p50=31.0,
            p90=41.0,
            alpha=0.2,
            labels={"source": "lstm_remote", "freq": "1h"},
        )

        alpha, evidence = _metric_alpha_for_device(
            device=self.device,
            metric_code="cpu_load_total",
            horizon="30d",
            sarima_point=sarima_point,
            lstm_point=lstm_point,
            default_alpha_sarima=0.5,
            metric_control={"sarima_enabled": True, "lstm_enabled": True, "alpha_mode": "auto"},
        )

        self.assertEqual(evidence["selection_method"], "trend_proxy")
        self.assertGreater(alpha, 0.5)

    def test_metric_alpha_not_stuck_when_first_bucket_is_sarima_only(self):
        now = timezone.now()
        history_start = now - timedelta(days=10)
        history_rows = []
        for idx in range(10 * 24):
            ts = history_start + timedelta(hours=idx)
            history_rows.append(
                RawMetric(
                    device=self.device,
                    code="cpu_load_total",
                    value=25.0 + (idx * 0.12),
                    unit="%",
                    timestamp=ts,
                    labels={"source": "test"},
                )
            )
        RawMetric.objects.bulk_create(history_rows, batch_size=500)

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={"freq": "1h"},
            quality={},
        )

        ForecastPoint.objects.create(
            run=sarima_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=1),
            model_kind="sarima",
            y_hat=38.0,
            p10=34.0,
            p50=38.0,
            p90=42.0,
            alpha=0.2,
            labels={"source": "sarima_baseline", "freq": "1h", "forecast_step": 1, "forecast_steps_total": 24},
        )
        ForecastPoint.objects.create(
            run=sarima_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=2),
            model_kind="sarima",
            y_hat=58.0,
            p10=52.0,
            p50=58.0,
            p90=64.0,
            alpha=0.2,
            labels={"source": "sarima_baseline", "freq": "1h", "forecast_step": 2, "forecast_steps_total": 24},
        )
        ForecastPoint.objects.create(
            run=lstm_run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=2, minutes=1),
            model_kind="lstm",
            y_hat=50.0,
            p10=45.0,
            p50=50.0,
            p90=55.0,
            alpha=0.2,
            labels={"source": "lstm_remote", "freq": "1h", "forecast_step": 2, "forecast_steps_total": 24},
        )

        ensemble_run, created, _meta = build_ensemble_run_for_sources(
            sarima_run=sarima_run,
            lstm_run=lstm_run,
            weights={"sarima": 0.5, "lstm": 0.5},
            disagreement_beta=0.5,
        )
        self.assertTrue(created)
        self.assertEqual(ensemble_run.status, "success")

        blended_point = (
            ForecastPoint.objects
            .filter(run=ensemble_run, metric_code="cpu_load_total", horizon="24h", labels__source_mode="blended")
            .order_by("target_ts", "id")
            .first()
        )
        self.assertIsNotNone(blended_point)
        self.assertLess(float(blended_point.alpha), 1.0)
        self.assertGreater(float(blended_point.alpha), 0.0)
        self.assertNotEqual(
            blended_point.labels.get("alpha_selection", {}).get("selection_method"),
            "sarima_only",
        )

    def test_orchestration_uses_different_alpha_per_horizon(self):
        now = timezone.now()

        hist_sarima_24 = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )
        hist_lstm_24 = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )
        hist_sarima_30 = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(days=40),
            finished_at=now - timedelta(days=40, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )
        hist_lstm_30 = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(days=40),
            finished_at=now - timedelta(days=40, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )

        actual_24 = now - timedelta(hours=12)
        actual_30 = now - timedelta(days=1)
        RawMetric.objects.create(device=self.device, code="cpu_load_total", value=50.0, unit="%", timestamp=actual_24, labels={"source": "test"})
        RawMetric.objects.create(device=self.device, code="cpu_load_total", value=80.0, unit="%", timestamp=actual_30, labels={"source": "test"})

        ForecastPoint.objects.create(
            run=hist_sarima_24, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=actual_24, model_kind="sarima", y_hat=50.0, p10=45.0, p50=50.0, p90=55.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=hist_lstm_24, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=actual_24, model_kind="lstm", y_hat=60.0, p10=55.0, p50=60.0, p90=65.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=hist_sarima_30, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=actual_30, model_kind="sarima", y_hat=95.0, p10=90.0, p50=95.0, p90=100.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=hist_lstm_30, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=actual_30, model_kind="lstm", y_hat=82.0, p10=77.0, p50=82.0, p90=87.0, alpha=0.2, labels={}
        )

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h,30d",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h,30d",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={"freq": "1h"},
            quality={},
        )
        ForecastPoint.objects.create(
            run=sarima_run, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=now + timedelta(hours=24), model_kind="sarima", y_hat=55.0, p10=50.0, p50=55.0, p90=60.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=lstm_run, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=now + timedelta(hours=24), model_kind="lstm", y_hat=70.0, p10=65.0, p50=70.0, p90=75.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=sarima_run, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=now + timedelta(days=30), model_kind="sarima", y_hat=90.0, p10=85.0, p50=90.0, p90=95.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=lstm_run, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=now + timedelta(days=30), model_kind="lstm", y_hat=82.0, p10=77.0, p50=82.0, p90=87.0, alpha=0.2, labels={}
        )

        ensemble_run, created, _ = build_ensemble_run_for_sources(
            sarima_run=sarima_run,
            lstm_run=lstm_run,
            weights={"sarima": 0.5, "lstm": 0.5},
            disagreement_beta=0.5,
        )
        self.assertTrue(created)

        point_24 = ForecastPoint.objects.get(run=ensemble_run, metric_code="cpu_load_total", horizon="24h")
        point_30 = ForecastPoint.objects.get(run=ensemble_run, metric_code="cpu_load_total", horizon="30d")

        self.assertGreater(float(point_24.alpha), 0.5)
        self.assertLess(float(point_30.alpha), 0.5)
        self.assertEqual(point_24.labels["alpha_selection"]["sarima"]["mode"], "historical_segment_error")
        self.assertEqual(point_30.labels["alpha_selection"]["lstm"]["mode"], "historical_segment_error")

    def test_metric_alpha_switches_to_winner_bias_when_gap_is_large(self):
        now = timezone.now()
        actual_ts = now - timedelta(hours=12)
        RawMetric.objects.create(
            device=self.device,
            code="cpu_load_total",
            value=50.0,
            unit="%",
            timestamp=actual_ts,
            labels={"source": "test"},
        )

        sarima_hist = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_hist = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2, minutes=-1),
            parameters={"freq": "1h"},
            quality={},
        )
        ForecastPoint.objects.create(
            run=sarima_hist, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=actual_ts, model_kind="sarima", y_hat=50.5, p10=45.0, p50=50.5, p90=56.0, alpha=0.2, labels={}
        )
        ForecastPoint.objects.create(
            run=lstm_hist, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=actual_ts, model_kind="lstm", y_hat=70.0, p10=65.0, p50=70.0, p90=75.0, alpha=0.2, labels={}
        )

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h"},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={"freq": "1h"},
            quality={},
        )
        sarima_point = ForecastPoint.objects.create(
            run=sarima_run, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=now + timedelta(hours=24), model_kind="sarima", y_hat=54.0, p10=49.0, p50=54.0, p90=59.0, alpha=0.2, labels={}
        )
        lstm_point = ForecastPoint.objects.create(
            run=lstm_run, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=now + timedelta(hours=24), model_kind="lstm", y_hat=68.0, p10=63.0, p50=68.0, p90=73.0, alpha=0.2, labels={}
        )

        alpha, evidence = _metric_alpha_for_device(
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            sarima_point=sarima_point,
            lstm_point=lstm_point,
            default_alpha_sarima=0.5,
            metric_control={"sarima_enabled": True, "lstm_enabled": True, "alpha_mode": "auto"},
        )
        self.assertEqual(evidence["selection_method"], "winner_bias_recent_compatible_error")
        self.assertAlmostEqual(alpha, 0.85, places=6)

    def test_long_horizon_keeps_blended_point_and_blended_uncertainty(self):
        prediction = _build_ensemble_prediction(
            metric_code="cpu_load_total",
            horizon="30d",
            sarima_point=type("P", (), {"y_hat": 90.0, "p10": 80.0, "p90": 100.0})(),
            lstm_point=type("P", (), {"y_hat": 70.0, "p10": 65.0, "p90": 75.0})(),
            alpha_sarima=0.15,
            disagreement_beta=0.5,
            alpha_evidence={"selection_method": "winner_bias_recent_compatible_error"},
        )

        self.assertIsNotNone(prediction)
        self.assertEqual(prediction["point_aggregation_method"], "weighted_average")
        self.assertEqual(prediction["point_source"], "blend")
        self.assertAlmostEqual(prediction["y_hat"], 73.0, places=6)
        self.assertAlmostEqual(prediction["p50"], 73.0, places=6)
        self.assertGreater(prediction["u_e"], 5.0)
        self.assertAlmostEqual(prediction["p90"] - prediction["p50"], prediction["u_e"], places=6)
        self.assertAlmostEqual(prediction["p50"] - prediction["p10"], prediction["u_e"], places=6)

    def test_orchestration_uses_different_alpha_per_segment_within_same_horizon(self):
        now = timezone.now()

        hist_sarima = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(days=10),
            finished_at=now - timedelta(days=10, minutes=-1),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )
        hist_lstm = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(days=10),
            finished_at=now - timedelta(days=10, minutes=-1),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )

        early_actual_ts = now - timedelta(hours=12)
        late_actual_ts = now - timedelta(hours=24)
        RawMetric.objects.create(device=self.device, code="cpu_load_total", value=48.0, unit="%", timestamp=early_actual_ts, labels={"source": "test"})
        RawMetric.objects.create(device=self.device, code="cpu_load_total", value=82.0, unit="%", timestamp=late_actual_ts, labels={"source": "test"})

        ForecastPoint.objects.create(
            run=hist_sarima, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=early_actual_ts, model_kind="sarima", y_hat=48.0, p10=43.0, p50=48.0, p90=53.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 12, "forecast_steps_total": 720}
        )
        ForecastPoint.objects.create(
            run=hist_lstm, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=early_actual_ts, model_kind="lstm", y_hat=60.0, p10=55.0, p50=60.0, p90=65.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 12, "forecast_steps_total": 720}
        )
        ForecastPoint.objects.create(
            run=hist_sarima, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=late_actual_ts, model_kind="sarima", y_hat=96.0, p10=91.0, p50=96.0, p90=101.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 300, "forecast_steps_total": 720}
        )
        ForecastPoint.objects.create(
            run=hist_lstm, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=late_actual_ts, model_kind="lstm", y_hat=82.0, p10=77.0, p50=82.0, p90=87.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 300, "forecast_steps_total": 720}
        )

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="30d",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )
        ForecastPoint.objects.create(
            run=sarima_run, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=now + timedelta(hours=12), model_kind="sarima", y_hat=52.0, p10=47.0, p50=52.0, p90=57.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 12, "forecast_steps_total": 720}
        )
        ForecastPoint.objects.create(
            run=lstm_run, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=now + timedelta(hours=12), model_kind="lstm", y_hat=64.0, p10=59.0, p50=64.0, p90=69.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 12, "forecast_steps_total": 720}
        )
        ForecastPoint.objects.create(
            run=sarima_run, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=now + timedelta(hours=300), model_kind="sarima", y_hat=94.0, p10=89.0, p50=94.0, p90=99.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 300, "forecast_steps_total": 720}
        )
        ForecastPoint.objects.create(
            run=lstm_run, device=self.device, metric_code="cpu_load_total", horizon="30d",
            target_ts=now + timedelta(hours=300), model_kind="lstm", y_hat=84.0, p10=79.0, p50=84.0, p90=89.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 300, "forecast_steps_total": 720}
        )

        ensemble_run, created, _ = build_ensemble_run_for_sources(
            sarima_run=sarima_run,
            lstm_run=lstm_run,
            weights={"sarima": 0.5, "lstm": 0.5},
            disagreement_beta=0.5,
        )
        self.assertTrue(created)

        points = list(
            ForecastPoint.objects
            .filter(run=ensemble_run, metric_code="cpu_load_total", horizon="30d")
            .order_by("target_ts", "id")
        )
        early_point = next(item for item in points if int(item.labels.get("forecast_step") or 0) == 1)
        late_point = next(item for item in points if int(item.labels.get("forecast_step") or 0) == 2)

        self.assertGreater(float(early_point.alpha), 0.5)
        self.assertLess(float(late_point.alpha), 0.5)
        self.assertEqual(early_point.labels["segment_key"], "0_24h")
        self.assertEqual(late_point.labels["segment_key"], "168_720h")

    def test_version_aware_alpha_ignores_incompatible_history_generations(self):
        now = timezone.now()
        actual_ts = now - timedelta(hours=12)
        RawMetric.objects.create(
            device=self.device,
            code="cpu_load_total",
            value=50.0,
            unit="%",
            timestamp=actual_ts,
            labels={"source": "test"},
        )

        sarima_hist_incompatible = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=3),
            finished_at=now - timedelta(days=3, minutes=-1),
            parameters={"freq": "1h", "lookback_days": 30},
            quality={},
        )
        lstm_hist_compatible = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2, minutes=-1),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )

        ForecastPoint.objects.create(
            run=sarima_hist_incompatible, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=actual_ts, model_kind="sarima", y_hat=50.0, p10=45.0, p50=50.0, p90=55.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 24, "forecast_steps_total": 24}
        )
        ForecastPoint.objects.create(
            run=lstm_hist_compatible, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=actual_ts, model_kind="lstm", y_hat=51.0, p10=46.0, p50=51.0, p90=56.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 24, "forecast_steps_total": 24}
        )

        sarima_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="sarima",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )
        lstm_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="lstm",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=3),
            finished_at=now - timedelta(minutes=2),
            parameters={"freq": "1h", "lookback_days": 60},
            quality={},
        )
        sarima_point = ForecastPoint.objects.create(
            run=sarima_run, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=now + timedelta(hours=24), model_kind="sarima", y_hat=54.0, p10=49.0, p50=54.0, p90=59.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 24, "forecast_steps_total": 24}
        )
        lstm_point = ForecastPoint.objects.create(
            run=lstm_run, device=self.device, metric_code="cpu_load_total", horizon="24h",
            target_ts=now + timedelta(hours=24), model_kind="lstm", y_hat=53.0, p10=48.0, p50=53.0, p90=58.0, alpha=0.2,
            labels={"freq": "1h", "forecast_step": 24, "forecast_steps_total": 24}
        )

        alpha_version_aware, evidence_version_aware = _metric_alpha_for_device(
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            sarima_point=sarima_point,
            lstm_point=lstm_point,
            orchestrator_controls={"alpha_version_aware": True, "winner_margin": 10.0},
            default_alpha_sarima=0.5,
            metric_control={"sarima_enabled": True, "lstm_enabled": True, "alpha_mode": "auto"},
        )
        alpha_full_archive, _evidence_full_archive = _metric_alpha_for_device(
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            sarima_point=sarima_point,
            lstm_point=lstm_point,
            orchestrator_controls={"alpha_version_aware": False, "winner_margin": 10.0},
            default_alpha_sarima=0.5,
            metric_control={"sarima_enabled": True, "lstm_enabled": True, "alpha_mode": "auto"},
        )

        self.assertLess(alpha_version_aware, 0.5)
        self.assertGreater(alpha_full_archive, alpha_version_aware)
        self.assertNotIn(sarima_hist_incompatible.id, evidence_version_aware["sarima"]["compatible_run_ids"])
