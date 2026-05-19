from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from inventory_api.forecasting.risk_assessment_service import (
    RiskAssessmentPrerequisiteError,
    build_state_risk_features_for_points,
    evaluate_risk_assessment,
)
from inventory_api.models import Device, DeviceType, ForecastPoint, ForecastRun, RawMetric, StateEstimate


class RiskAssessmentServiceTests(TestCase):
    def setUp(self):
        self.device_type = DeviceType.objects.create(name="Сервер")
        self.device = Device.objects.create(
            name="Srv Risk",
            serial_number="RISK-001",
            device_type=self.device_type,
            status="active",
        )

        now = timezone.now()
        raw_batch = []
        for idx in range(72):
            ts = now - timedelta(hours=72 - idx)
            raw_batch.append(
                RawMetric(
                    device=self.device,
                    code="cpu_load_total",
                    value=40.0 + (idx % 15),
                    unit="%",
                    timestamp=ts,
                    labels={"source": "test"},
                )
            )
            raw_batch.append(
                RawMetric(
                    device=self.device,
                    code="storcli_drive_wear_percent",
                    value=70.0 + (idx / 24.0),
                    unit="%",
                    timestamp=ts,
                    labels={"source": "test"},
                )
            )
        RawMetric.objects.bulk_create(raw_batch, batch_size=200)

        run = ForecastRun.objects.create(
            device=self.device,
            model_kind="ensemble",
            horizon_set="24h,7d,30d",
            status="success",
            started_at=now - timedelta(minutes=5),
            finished_at=now - timedelta(minutes=4),
            parameters={"source": "test"},
            quality={},
            notes="risk test run",
        )

        ForecastPoint.objects.create(
            run=run,
            device=self.device,
            metric_code="cpu_load_total",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="ensemble",
            y_hat=88.0,
            p10=70.0,
            p50=88.0,
            p90=96.0,
            alpha=0.5,
            labels={"source": "test"},
        )
        ForecastPoint.objects.create(
            run=run,
            device=self.device,
            metric_code="storcli_drive_wear_percent",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="ensemble",
            y_hat=84.0,
            p10=80.0,
            p50=84.0,
            p90=86.0,
            alpha=0.5,
            labels={"source": "test", "eta": 100.0, "beta": 2.1, "weibull_kind": "wear_percent"},
        )

        states = ["s0", "s0", "s1", "s1", "s2"]
        for i, state in enumerate(states):
            StateEstimate.objects.create(
                run=run,
                device=self.device,
                horizon="24h",
                state=state,
                p_s0=0.7 if state == "s0" else 0.1,
                p_s1=0.2 if state == "s1" else 0.2,
                p_s2=0.7 if state == "s2" else 0.1,
                confidence=0.8,
                evidence={"source": "test"},
                timestamp=now - timedelta(hours=6 - i),
            )

    def test_evaluate_risk_assessment_returns_mixed_methods(self):
        payload = evaluate_risk_assessment(
            serial=self.device.serial_number,
            horizons=["24h"],
            preferred_model_kind="ensemble",
            personalized_thresholds=True,
            threshold_lookback_days=30,
            markov_lookback_days=60,
            markov_smoothing=1.0,
            type_blend=0.3,
        )

        self.assertEqual(payload["device"]["serial_number"], self.device.serial_number)
        self.assertEqual(len(payload["horizons"]), 1)
        result = payload["horizons"][0]

        self.assertEqual(result["horizon"], "24h")
        self.assertGreaterEqual(result["overall_risk"], 0.0)
        self.assertLessEqual(result["overall_risk"], 1.0)
        self.assertEqual(len(result["transition_matrix"]), 3)
        self.assertEqual(len(result["transition_matrix"][0]), 3)
        self.assertIn("markov_projection_confidence", result)
        self.assertGreaterEqual(float(result["markov_projection_confidence"]), 0.0)
        self.assertLessEqual(float(result["markov_projection_confidence"]), 1.0)
        self.assertIn("markov_raw_projected_p_s2", result)

        methods = {item["metric_code"]: item["method"] for item in result["metrics"]}
        self.assertEqual(methods.get("cpu_load_total"), "threshold")
        self.assertEqual(methods.get("storcli_drive_wear_percent"), "weibull")

    def test_evaluate_risk_assessment_raises_on_unknown_device(self):
        with self.assertRaises(RuntimeError):
            evaluate_risk_assessment(serial="UNKNOWN-DEVICE")

    def test_evaluate_risk_assessment_stops_without_state_estimate(self):
        StateEstimate.objects.all().delete()
        with self.assertRaises(RiskAssessmentPrerequisiteError):
            evaluate_risk_assessment(
                serial=self.device.serial_number,
                horizons=["24h"],
                preferred_model_kind="ensemble",
            )

    def test_evaluate_risk_assessment_supplements_metrics_from_state_history(self):
        now = timezone.now()
        self.assertFalse(
            ForecastPoint.objects.filter(run__model_kind="ensemble", metric_code="storcli_drive_temperature").exists()
        )

        older_ensemble_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="ensemble",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=9),
            finished_at=now - timedelta(minutes=8),
            parameters={"source": "test-ensemble-history"},
            quality={},
            notes="state history supplementation test",
        )
        ForecastRun.objects.filter(id=older_ensemble_run.id).update(created_at=now - timedelta(hours=2))
        ForecastPoint.objects.create(
            run=older_ensemble_run,
            device=self.device,
            metric_code="storcli_drive_temperature",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="ensemble",
            y_hat=55.2,
            p10=53.0,
            p50=55.2,
            p90=57.1,
            alpha=0.2,
            labels={"source": "test-ensemble-history"},
        )
        StateEstimate.objects.filter(run__model_kind="ensemble", horizon="24h").delete()
        current_run = (
            ForecastRun.objects
            .filter(device=self.device, model_kind="ensemble", status="success")
            .order_by("-created_at", "-id")
            .first()
        )
        StateEstimate.objects.create(
            run=current_run,
            device=self.device,
            horizon="24h",
            state="s1",
            p_s0=0.28,
            p_s1=0.54,
            p_s2=0.18,
            confidence=0.81,
            evidence={
                "top_components": [
                    {
                        "metric_code": "storcli_drive_temperature",
                        "value": 55.2,
                        "threshold": 58.0,
                        "ratio": 0.95,
                        "risk_component": 0.0,
                        "source": "thresholds",
                    }
                ]
            },
            timestamp=now - timedelta(minutes=8),
        )

        payload = evaluate_risk_assessment(
            serial=self.device.serial_number,
            horizons=["24h"],
            preferred_model_kind="auto",
            history_limit=8,
        )

        result = payload["horizons"][0]
        metrics = {item["metric_code"]: item for item in result["metrics"]}
        self.assertIn("storcli_drive_temperature", metrics)
        self.assertTrue(metrics["storcli_drive_temperature"]["supplemented_from_state_history"])
        self.assertGreater(metrics["storcli_drive_temperature"]["state_history_signal"], 0.0)

    def test_evaluate_risk_assessment_excludes_metrics_outside_state_model(self):
        now = timezone.now()
        run = ForecastRun.objects.get(device=self.device, model_kind="ensemble", status="success")

        ForecastPoint.objects.create(
            run=run,
            device=self.device,
            metric_code="net_bytes_sent",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="ensemble",
            y_hat=1850.0,
            p10=1600.0,
            p50=1850.0,
            p90=2100.0,
            alpha=0.2,
            labels={"source": "test"},
        )
        RawMetric.objects.bulk_create([
            RawMetric(
                device=self.device,
                code="net_bytes_sent",
                value=1500.0 + (idx * 15.0),
                unit="KB/s",
                timestamp=now - timedelta(hours=24 - idx),
                labels={"source": "test"},
            )
            for idx in range(24)
        ])

        payload = evaluate_risk_assessment(
            serial=self.device.serial_number,
            horizons=["24h"],
            preferred_model_kind="ensemble",
        )

        metric_codes = {item["metric_code"] for item in payload["horizons"][0]["metrics"]}
        self.assertNotIn("net_bytes_sent", metric_codes)

    def test_build_state_risk_features_for_points_uses_personalized_thresholds(self):
        run = ForecastRun.objects.filter(device=self.device, model_kind="ensemble", status="success").first()
        points = list(ForecastPoint.objects.filter(run=run, horizon="24h").order_by("metric_code"))
        payload = build_state_risk_features_for_points(
            device=self.device,
            horizon="24h",
            points=points,
            source_model="ensemble",
            personalized_thresholds=True,
            threshold_lookback_days=30,
        )

        self.assertGreater(payload["metric_aggregate_risk"], 0.0)
        self.assertIn("metric_results", payload)
        row_map = {item["metric_code"]: item for item in payload["metric_results"]}
        self.assertIn("cpu_load_total", row_map)
        self.assertGreater(row_map["cpu_load_total"]["risk"], 0.0)

    def test_evaluate_risk_assessment_ignores_stale_history_only_metric(self):
        now = timezone.now()
        current_run = ForecastRun.objects.get(device=self.device, model_kind="ensemble", status="success")
        stale_run = ForecastRun.objects.create(
            device=self.device,
            model_kind="ensemble",
            horizon_set="24h",
            status="success",
            started_at=now - timedelta(minutes=20),
            finished_at=now - timedelta(minutes=19),
            parameters={"source": "stale-history"},
            quality={},
            notes="stale history only",
        )
        ForecastRun.objects.filter(id=stale_run.id).update(created_at=now - timedelta(hours=2))
        ForecastPoint.objects.create(
            run=stale_run,
            device=self.device,
            metric_code="storcli_predictive_failure_count",
            horizon="24h",
            target_ts=now + timedelta(hours=24),
            model_kind="ensemble",
            y_hat=1.0,
            p10=1.0,
            p50=1.0,
            p90=1.0,
            alpha=0.2,
            labels={"source": "stale-history"},
        )
        StateEstimate.objects.create(
            run=stale_run,
            device=self.device,
            horizon="24h",
            state="s1",
            p_s0=0.25,
            p_s1=0.55,
            p_s2=0.20,
            confidence=0.8,
            evidence={
                "top_components": [
                    {
                        "metric_code": "storcli_predictive_failure_count",
                        "value": 1.0,
                        "threshold": 1.0,
                        "ratio": 1.0,
                        "risk_component": 0.3333333333333333,
                        "source": "thresholds",
                    }
                ]
            },
            timestamp=now - timedelta(minutes=19),
        )
        StateEstimate.objects.filter(run=current_run, horizon="24h").delete()
        StateEstimate.objects.create(
            run=current_run,
            device=self.device,
            horizon="24h",
            state="s0",
            p_s0=0.82,
            p_s1=0.12,
            p_s2=0.06,
            confidence=0.92,
            evidence={
                "top_components": [
                    {
                        "metric_code": "mem_usage_percent",
                        "value": 88.0,
                        "threshold": 92.0,
                        "ratio": 0.9565,
                        "risk_component": 0.2753,
                        "source": "thresholds",
                    }
                ]
            },
            timestamp=now - timedelta(minutes=1),
        )

        payload = evaluate_risk_assessment(
            serial=self.device.serial_number,
            horizons=["24h"],
            preferred_model_kind="auto",
            history_limit=8,
        )

        metric_codes = {item["metric_code"] for item in payload["horizons"][0]["metrics"]}
        self.assertNotIn("storcli_predictive_failure_count", metric_codes)
