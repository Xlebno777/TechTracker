from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from inventory_api.forecasting.lstm_remote_client import LSTMRemoteClient
from inventory_api.forecasting.lstm_remote_service import (
    poll_lstm_remote_runs,
    run_lstm_remote_forecasts,
)
from inventory_api.models import (
    Device,
    DeviceType,
    ForecastPoint,
    ForecastRun,
    LSTMRemoteQueueJob,
    RawMetric,
    StateEstimate,
)


class LSTMRemoteClientTests(SimpleTestCase):
    def test_from_env_defaults(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            client = LSTMRemoteClient.from_env()
        self.assertEqual(client.base_url, "http://127.0.0.1:8099")
        self.assertEqual(client.api_token, "")
        self.assertEqual(client.timeout_sec, 20.0)
        self.assertFalse(client.verify_ssl)
        self.assertFalse(client.session.trust_env)

    def test_submit_job_sends_api_key(self):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"job_id": "abc", "status": "queued"}

        client = LSTMRemoteClient(base_url="http://test", api_token="secret", timeout_sec=5, verify_ssl=False)
        client.session.post = mock.Mock(return_value=response)
        out = client.submit_job({"device_serial": "HOST-1", "metrics": {}})

        self.assertEqual(out.get("job_id"), "abc")
        called_headers = client.session.post.call_args.kwargs["headers"]
        self.assertEqual(called_headers.get("X-API-Key"), "secret")

    def test_health_uses_session_without_env_proxy(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "ok", "service": "lstm_remote", "version": "0.1.0"}

        client = LSTMRemoteClient(base_url="http://test", api_token="secret", timeout_sec=5, verify_ssl=False)
        client.session.get = mock.Mock(return_value=response)

        out = client.check_health()

        self.assertEqual(out.get("status"), "ok")
        self.assertFalse(client.session.trust_env)
        self.assertEqual(client.session.get.call_args.args[0], "http://test/health")


class LSTMRemoteFlowTests(TestCase):
    def setUp(self):
        self.device_type = DeviceType.objects.create(name="Сервер")
        self.device = Device.objects.create(
            name="Srv 1",
            serial_number="HOST-001",
            device_type=self.device_type,
            status="active",
        )

        now = timezone.now()
        rows = []
        for idx in range(60):
            rows.append(
                RawMetric(
                    device=self.device,
                    code="cpu_load_total",
                    value=40.0 + (idx % 7),
                    unit="%",
                    timestamp=now - timedelta(hours=(60 - idx)),
                    labels={"source": "test"},
                )
            )
        RawMetric.objects.bulk_create(rows, batch_size=200)

    @staticmethod
    def _completed_payload(job_id="remote-job-1"):
        return {
            "job_id": job_id,
            "status": "completed",
            "result": {
                "model_kind": "lstm",
                "forecasts": [
                    {
                        "metric_code": "cpu_load_total",
                        "horizon": "24h",
                        "y_hat": 44.2,
                        "p10": 40.3,
                        "p50": 44.2,
                        "p90": 48.0,
                        "alpha": 0.2,
                        "labels": {"source": "lstm_remote"},
                    },
                    {
                        "metric_code": "cpu_load_total",
                        "horizon": "7d",
                        "y_hat": 46.1,
                        "p10": 39.8,
                        "p50": 46.1,
                        "p90": 52.5,
                        "alpha": 0.2,
                        "labels": {"source": "lstm_remote"},
                    },
                    {
                        "metric_code": "cpu_load_total",
                        "horizon": "30d",
                        "y_hat": 49.0,
                        "p10": 38.0,
                        "p50": 49.0,
                        "p90": 58.0,
                        "alpha": 0.2,
                        "labels": {"source": "lstm_remote"},
                    },
                ],
                "quality": {
                    "metrics_processed": 1,
                    "metrics_skipped": 0,
                    "errors": [],
                },
            },
        }

    @staticmethod
    def _completed_payload_with_native_steps(job_id="remote-job-native"):
        base = timezone.now().replace(minute=0, second=0, microsecond=0)
        return {
            "job_id": job_id,
            "status": "completed",
            "result": {
                "model_kind": "lstm",
                "forecasts": [
                    {
                        "metric_code": "cpu_load_total",
                        "horizon": "24h",
                        "target_ts": (base + timedelta(hours=1)).isoformat(),
                        "forecast_step": 1,
                        "forecast_steps_total": 3,
                        "y_hat": 44.0,
                        "p10": 40.0,
                        "p50": 44.0,
                        "p90": 48.0,
                        "alpha": 0.2,
                        "labels": {"source": "lstm_remote", "output_mode": "direct_multi_horizon"},
                    },
                    {
                        "metric_code": "cpu_load_total",
                        "horizon": "24h",
                        "target_ts": (base + timedelta(hours=2)).isoformat(),
                        "forecast_step": 2,
                        "forecast_steps_total": 3,
                        "y_hat": 46.0,
                        "p10": 41.0,
                        "p50": 46.0,
                        "p90": 51.0,
                        "alpha": 0.2,
                        "labels": {"source": "lstm_remote", "output_mode": "direct_multi_horizon"},
                    },
                    {
                        "metric_code": "cpu_load_total",
                        "horizon": "24h",
                        "target_ts": (base + timedelta(hours=3)).isoformat(),
                        "forecast_step": 3,
                        "forecast_steps_total": 3,
                        "y_hat": 49.0,
                        "p10": 43.0,
                        "p50": 49.0,
                        "p90": 55.0,
                        "alpha": 0.2,
                        "labels": {"source": "lstm_remote", "output_mode": "direct_multi_horizon"},
                    },
                ],
                "quality": {
                    "metrics_processed": 1,
                    "metrics_skipped": 0,
                    "errors": [],
                    "output_mode": "direct_multi_horizon",
                },
            },
        }

    def test_remote_lstm_enqueue_and_complete(self):
        completed_payload = self._completed_payload()

        with (
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.check_health",
                return_value={"status": "ok", "service": "lstm_remote", "version": "0.1.0"},
            ),
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.submit_job",
                return_value={"job_id": "remote-job-1", "status": "queued"},
            ),
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.get_job",
                return_value=completed_payload,
            ),
        ):
            enqueue_payload = run_lstm_remote_forecasts(
                serial=self.device.serial_number,
                lookback_days=30,
                freq="1h",
                horizons=["24h", "7d", "30d"],
                metric_codes=["cpu_load_total"],
                wait_for_result=False,
                max_retries=3,
            )

            self.assertEqual(enqueue_payload.get("created_runs"), 1)
            self.assertEqual(enqueue_payload.get("queued_jobs"), 1)

            run = ForecastRun.objects.filter(device=self.device, model_kind="lstm").order_by("-id").first()
            self.assertIsNotNone(run)
            self.assertIn(run.status, ["pending", "running"])

            poll_payload = poll_lstm_remote_runs(run_id=run.id, limit=10, poll_interval_sec=1)
            self.assertGreaterEqual(poll_payload.get("checked_jobs", 0), 1)

        run.refresh_from_db()
        self.assertEqual(run.status, "success")
        points = ForecastPoint.objects.filter(run=run, model_kind="lstm")
        self.assertGreaterEqual(points.count(), 24 + (7 * 24) + (30 * 24))
        first_point = points.order_by("target_ts", "id").first()
        self.assertIsNotNone(first_point)
        self.assertIsInstance(first_point.labels, dict)
        self.assertIsNotNone(first_point.labels.get("forecast_step"))
        self.assertEqual(StateEstimate.objects.filter(run=run).count(), 3)

        queue_job = LSTMRemoteQueueJob.objects.get(forecast_run=run)
        self.assertEqual(queue_job.status, "success")
        self.assertEqual(queue_job.remote_job_id, "remote-job-1")

    def test_poll_retry_does_not_resubmit_if_remote_job_exists(self):
        completed_payload = self._completed_payload(job_id="remote-job-2")

        with (
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.check_health",
                return_value={"status": "ok", "service": "lstm_remote", "version": "0.1.0"},
            ),
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.submit_job",
                return_value={"job_id": "remote-job-2", "status": "queued"},
            ) as mocked_submit,
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.get_job",
                side_effect=[RuntimeError("timeout"), completed_payload],
            ) as mocked_get_job,
        ):
            enqueue_payload = run_lstm_remote_forecasts(
                serial=self.device.serial_number,
                lookback_days=30,
                freq="1h",
                horizons=["24h", "7d", "30d"],
                metric_codes=["cpu_load_total"],
                wait_for_result=False,
                max_retries=3,
            )
            self.assertEqual(enqueue_payload.get("created_runs"), 1)
            self.assertEqual(enqueue_payload.get("queued_jobs"), 1)

            run = ForecastRun.objects.filter(device=self.device, model_kind="lstm").order_by("-id").first()
            self.assertIsNotNone(run)

            first_poll = poll_lstm_remote_runs(run_id=run.id, limit=10, poll_interval_sec=1)
            self.assertGreaterEqual(first_poll.get("retried", 0), 1)

            queue_job = LSTMRemoteQueueJob.objects.get(forecast_run=run)
            queue_job.next_retry_at = timezone.now() - timedelta(seconds=1)
            queue_job.save(update_fields=["next_retry_at", "updated_at"])

            second_poll = poll_lstm_remote_runs(run_id=run.id, limit=10, poll_interval_sec=1)
            self.assertGreaterEqual(second_poll.get("completed", 0), 1)

            self.assertEqual(mocked_submit.call_count, 1)
            self.assertEqual(mocked_get_job.call_count, 2)

        run.refresh_from_db()
        self.assertEqual(run.status, "success")
        queue_job = LSTMRemoteQueueJob.objects.get(forecast_run=run)
        self.assertEqual(queue_job.status, "success")
        self.assertEqual(queue_job.remote_job_id, "remote-job-2")

    def test_remote_lstm_passes_extended_model_options(self):
        custom_options = {
            "epochs": 77,
            "lookback": 240,
            "hidden_size": 128,
            "learning_rate": 0.0005,
            "dropout": 0.2,
            "weight_decay": 0.0001,
            "batch_size": 32,
            "use_calendar_features": True,
            "use_seasonal_residual": True,
            "seasonality_mode": "rolling_profile",
            "seasonality_window_days": 21,
            "lags": [1, 24, 168],
            "loss_kind": "quantile",
            "output_mode": "direct_multi_horizon",
            "forecast_stride": 1,
            "train_mode": "warm_start",
        }

        with (
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.check_health",
                return_value={"status": "ok", "service": "lstm_remote", "version": "0.1.0"},
            ),
        ):
            payload = run_lstm_remote_forecasts(
                serial=self.device.serial_number,
                lookback_days=60,
                freq="1h",
                horizons=["24h", "7d"],
                metric_codes=["cpu_load_total"],
                wait_for_result=False,
                max_retries=3,
                model_options=custom_options,
            )

        self.assertEqual(payload.get("created_runs"), 1)
        run = ForecastRun.objects.filter(device=self.device, model_kind="lstm").order_by("-id").first()
        self.assertIsNotNone(run)
        queue_job = LSTMRemoteQueueJob.objects.get(forecast_run=run)

        options = queue_job.request_payload.get("options", {})
        self.assertEqual(options.get("epochs"), 77)
        self.assertEqual(options.get("lookback"), 240)
        self.assertEqual(options.get("hidden_size"), 128)
        self.assertEqual(options.get("loss_kind"), "quantile")
        self.assertEqual(options.get("output_mode"), "direct_multi_horizon")
        self.assertEqual(options.get("train_mode"), "warm_start")
        self.assertEqual(options.get("alpha"), 0.2)

        self.assertEqual((run.parameters or {}).get("remote_model_options", {}).get("epochs"), 77)
        self.assertEqual((run.parameters or {}).get("remote_model_options", {}).get("train_mode"), "warm_start")
        self.assertEqual((run.quality or {}).get("remote_model_options", {}).get("lookback"), 240)
        self.assertEqual(queue_job.request_payload.get("options", {}).get("seasonality_window_days"), 21)

    def test_native_lstm_trajectory_is_imported_without_linear_expansion(self):
        completed_payload = self._completed_payload_with_native_steps()

        with (
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.check_health",
                return_value={"status": "ok", "service": "lstm_remote", "version": "0.1.0"},
            ),
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.submit_job",
                return_value={"job_id": "remote-job-native", "status": "queued"},
            ),
            mock.patch(
                "inventory_api.forecasting.lstm_remote_client.LSTMRemoteClient.get_job",
                return_value=completed_payload,
            ),
        ):
            enqueue_payload = run_lstm_remote_forecasts(
                serial=self.device.serial_number,
                lookback_days=30,
                freq="1h",
                horizons=["24h"],
                metric_codes=["cpu_load_total"],
                wait_for_result=False,
                max_retries=3,
            )
            self.assertEqual(enqueue_payload.get("created_runs"), 1)
            run = ForecastRun.objects.filter(device=self.device, model_kind="lstm").order_by("-id").first()
            self.assertIsNotNone(run)
            poll_payload = poll_lstm_remote_runs(run_id=run.id, limit=10, poll_interval_sec=1)
            self.assertGreaterEqual(poll_payload.get("completed", 0), 1)

        run.refresh_from_db()
        self.assertEqual(run.status, "success")
        points = list(ForecastPoint.objects.filter(run=run, model_kind="lstm").order_by("target_ts", "id"))
        self.assertEqual(len(points), 3)
        self.assertEqual([int((p.labels or {}).get("forecast_step", 0)) for p in points], [1, 2, 3])
        self.assertFalse(any((p.labels or {}).get("trajectory_expanded") for p in points))
        self.assertEqual((run.quality or {}).get("trajectory_import", {}).get("mode"), "native")
