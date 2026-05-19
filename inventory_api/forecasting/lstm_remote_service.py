from __future__ import annotations

import os
import time
from datetime import timedelta, timezone as dt_timezone

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from inventory_api.forecasting.baseline_service import (
    DEFAULT_METRIC_CODES,
    FORECAST_ALPHA,
    _sanitize_prediction,
)
from inventory_api.forecasting.lstm_remote_client import LSTMRemoteClient
from inventory_api.forecasting.risk_assessment_service import (
    build_state_risk_features_for_points,
)
from inventory_api.forecasting.state_inference_service import (
    infer_state_distribution,
    get_forecast_metric_controls_config,
    get_active_state_inference_profile_config,
    resolve_metric_codes_for_source,
)
from inventory_api.models import (
    Device,
    ForecastPoint,
    ForecastRun,
    LSTMRemoteQueueJob,
    RawMetric,
    StateEstimate,
)


ACTIVE_QUEUE_STATUSES = ["queued", "submitting", "submitted", "polling", "retry_wait"]
QUEUE_LEASE_SEC = 90
QUEUE_RETRY_BASE_SEC = 5
QUEUE_RETRY_MAX_SEC = 600


def _env_int(name: str, default: int):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float):
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _env_bool(name: str, default: bool):
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _normalize_horizons(horizons: list[str] | None):
    raw = horizons or ["24h", "7d", "30d"]
    out = []
    for item in raw:
        h = str(item or "").strip()
        if not h:
            continue
        if h not in out:
            out.append(h)
    return out or ["24h", "7d", "30d"]


def _horizon_to_timedelta_local(horizon: str):
    raw = str(horizon or "").strip().lower()
    if raw.endswith("h"):
        return timedelta(hours=int(raw[:-1]))
    if raw.endswith("d"):
        return timedelta(days=int(raw[:-1]))
    raise ValueError(f"Unsupported horizon: {horizon}")


def _freq_to_timedelta_local(freq: str | None):
    raw = str(freq or "").strip().lower()
    if raw.endswith("min"):
        return timedelta(minutes=max(1, int(raw[:-3] or "1")))
    if raw.endswith("h"):
        return timedelta(hours=max(1, int(raw[:-1] or "1")))
    if raw.endswith("d"):
        return timedelta(days=max(1, int(raw[:-1] or "1")))
    return timedelta(hours=1)


def _horizon_to_steps_local(horizon: str, freq: str | None):
    total = _horizon_to_timedelta_local(horizon)
    step = _freq_to_timedelta_local(freq)
    step_sec = int(step.total_seconds())
    if step_sec <= 0:
        return 1
    return max(1, int(round(total.total_seconds() / float(step_sec))))


def _steps_per_day(freq: str | None):
    step = _freq_to_timedelta_local(freq)
    step_sec = max(60, int(step.total_seconds()))
    return max(1, int(round(86400.0 / float(step_sec))))


def _default_lags_for_freq(freq: str | None):
    step_per_day = _steps_per_day(freq)
    out = []
    for lag in (1, step_per_day, step_per_day * 7):
        lag = max(1, int(lag))
        if lag not in out:
            out.append(lag)
    return out


def _max_horizon_steps(horizons: list[str] | None, freq: str | None) -> int:
    values = _normalize_horizons(horizons)
    return max((_horizon_to_steps_local(item, freq) for item in values), default=1)


def _max_horizon_key(horizons: list[str] | None, freq: str | None) -> str:
    values = _normalize_horizons(horizons)
    if not values:
        return "24h"
    return max(values, key=lambda item: _horizon_to_steps_local(item, freq))


def _recommended_history_days_for_horizons(horizons: list[str] | None, freq: str | None) -> int:
    steps_day = _steps_per_day(freq)
    max_steps = _max_horizon_steps(horizons, freq)
    if max_steps <= steps_day:
        return _env_int("LSTM_REMOTE_HISTORY_DAYS_24H", 60)
    if max_steps <= steps_day * 7:
        return _env_int("LSTM_REMOTE_HISTORY_DAYS_7D", 120)
    return _env_int("LSTM_REMOTE_HISTORY_DAYS_30D", 365)


def _minimum_history_days_for_horizons(horizons: list[str] | None, freq: str | None) -> int:
    steps_day = _steps_per_day(freq)
    max_steps = _max_horizon_steps(horizons, freq)
    if max_steps <= steps_day:
        return _env_int("LSTM_REMOTE_HISTORY_DAYS_24H_MIN", 30)
    if max_steps <= steps_day * 7:
        return _env_int("LSTM_REMOTE_HISTORY_DAYS_7D_MIN", 90)
    return _env_int("LSTM_REMOTE_HISTORY_DAYS_30D_MIN", 180)


def _recommended_remote_lookback(*, freq: str, horizons: list[str] | None) -> int:
    steps_day = _steps_per_day(freq)
    max_steps = _max_horizon_steps(horizons, freq)
    if max_steps <= steps_day:
        return _env_int("LSTM_REMOTE_DEFAULT_LOOKBACK_24H", steps_day * 14)
    if max_steps <= steps_day * 7:
        return _env_int("LSTM_REMOTE_DEFAULT_LOOKBACK_7D", steps_day * 28)
    return _env_int("LSTM_REMOTE_DEFAULT_LOOKBACK_30D", steps_day * 60)


def _profile_metric_overrides(profile_config: dict | None, metric_codes: list[str]) -> dict[str, dict]:
    controls = get_forecast_metric_controls_config(config=profile_config or {})
    overrides: dict[str, dict] = {}
    for metric_code in metric_codes:
        raw = controls.get(metric_code)
        if not isinstance(raw, dict):
            continue
        overrides[metric_code] = {
            "trend_long_mode": raw.get("trend_long_mode"),
            "trend_transition_steps": raw.get("trend_transition_steps"),
            "trend_envelope_weight": raw.get("trend_envelope_weight"),
            "bias_correction_strength": raw.get("bias_correction_strength"),
        }
    return overrides


def _default_remote_model_options(*, lookback_days: int, freq: str, horizons: list[str] | None, profile_config: dict | None = None, metric_codes: list[str] | None = None):
    steps_day = _steps_per_day(freq)
    history_steps = max(steps_day * max(1, int(lookback_days)), steps_day * 2)
    preferred_lookback = _recommended_remote_lookback(freq=freq, horizons=horizons)
    max_usable_lookback = max(24, history_steps - 8)
    effective_lookback = max(24, min(preferred_lookback, max_usable_lookback))
    horizon_key = _max_horizon_key(horizons, freq)

    return {
        "epochs": _env_int("LSTM_REMOTE_DEFAULT_EPOCHS", 80),
        "lookback": effective_lookback,
        "hidden_size": _env_int("LSTM_REMOTE_DEFAULT_HIDDEN_SIZE", 96),
        "learning_rate": _env_float("LSTM_REMOTE_DEFAULT_LR", 0.001),
        "dropout": _env_float("LSTM_REMOTE_DEFAULT_DROPOUT", 0.15),
        "weight_decay": _env_float("LSTM_REMOTE_DEFAULT_WEIGHT_DECAY", 1e-5),
        "batch_size": _env_int("LSTM_REMOTE_DEFAULT_BATCH_SIZE", 64),
        "use_calendar_features": _env_bool("LSTM_REMOTE_DEFAULT_USE_CALENDAR", True),
        "use_seasonal_residual": _env_bool("LSTM_REMOTE_DEFAULT_USE_SEASONAL_RESIDUAL", True),
        "seasonality_mode": str(os.environ.get("LSTM_REMOTE_DEFAULT_SEASONALITY_MODE", "rolling_profile") or "rolling_profile").strip().lower(),
        "seasonality_window_days": _env_int("LSTM_REMOTE_DEFAULT_SEASONALITY_WINDOW_DAYS", 14),
        "lags": _default_lags_for_freq(freq),
        "loss_kind": str(os.environ.get("LSTM_REMOTE_DEFAULT_LOSS_KIND", "quantile") or "quantile").strip().lower(),
        "output_mode": str(os.environ.get("LSTM_REMOTE_DEFAULT_OUTPUT_MODE", "direct_multi_horizon") or "direct_multi_horizon").strip().lower(),
        "forecast_stride": 1,
        "train_mode": str(os.environ.get("LSTM_REMOTE_DEFAULT_TRAIN_MODE", "warm_start") or "warm_start").strip().lower(),
        "target_mode": str(os.environ.get("LSTM_REMOTE_DEFAULT_TARGET_MODE", "anchored_delta") or "anchored_delta").strip().lower(),
        "recency_weighted_loss": _env_bool("LSTM_REMOTE_DEFAULT_RECENCY_WEIGHTED_LOSS", True),
        "recency_weight_min": _env_float("LSTM_REMOTE_DEFAULT_RECENCY_WEIGHT_MIN", 0.35),
        "recency_weight_power": _env_float("LSTM_REMOTE_DEFAULT_RECENCY_WEIGHT_POWER", 2.0),
        "early_stopping_enabled": _env_bool("LSTM_REMOTE_DEFAULT_EARLY_STOPPING", True),
        "early_stopping_patience": _env_int("LSTM_REMOTE_DEFAULT_EARLY_STOPPING_PATIENCE", 10),
        "early_stopping_min_delta": _env_float("LSTM_REMOTE_DEFAULT_EARLY_STOPPING_MIN_DELTA", 0.0005),
        "lr_scheduler_kind": str(os.environ.get("LSTM_REMOTE_DEFAULT_SCHEDULER_KIND", "plateau") or "plateau").strip().lower(),
        "lr_scheduler_patience": _env_int("LSTM_REMOTE_DEFAULT_SCHEDULER_PATIENCE", 4),
        "lr_scheduler_factor": _env_float("LSTM_REMOTE_DEFAULT_SCHEDULER_FACTOR", 0.5),
        "lr_scheduler_min_lr": _env_float("LSTM_REMOTE_DEFAULT_SCHEDULER_MIN_LR", 1e-5),
        "horizon_key": horizon_key,
        "metric_overrides": _profile_metric_overrides(profile_config, metric_codes or []),
    }


def _expand_terminal_lstm_items_if_needed(
    *,
    device: Device,
    run: ForecastRun,
    horizons: list[str],
    freq: str,
    items: list[dict],
):
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in items:
        metric_code = str(item.get("metric_code") or "").strip()
        horizon = str(item.get("horizon") or "").strip()
        if not metric_code or not horizon or horizon not in horizons:
            continue
        grouped.setdefault((metric_code, horizon), []).append(item)

    if not grouped:
        return items, {"mode": "native", "expanded": False, "reason": "no_valid_items"}

    has_explicit_steps = any(
        item.get("forecast_step") is not None or item.get("forecast_steps_total") is not None
        for item in items
    )
    has_multi_per_group = any(len(rows) > 1 for rows in grouped.values())
    if has_explicit_steps or has_multi_per_group:
        return items, {
            "mode": "native",
            "expanded": False,
            "groups": len(grouped),
            "has_explicit_steps": bool(has_explicit_steps),
            "has_multi_per_group": bool(has_multi_per_group),
        }

    metric_codes = sorted({code for code, _ in grouped.keys()})
    latest_raw_by_code = {}
    latest_rows = (
        RawMetric.objects
        .filter(device=device, code__in=metric_codes)
        .order_by("code", "-timestamp", "-id")
    )
    for row in latest_rows:
        if row.code not in latest_raw_by_code:
            try:
                latest_raw_by_code[row.code] = float(row.value)
            except (TypeError, ValueError):
                continue

    step_delta = _freq_to_timedelta_local(freq)
    base_ts = run.created_at or run.started_at or timezone.now()
    expanded_items = []

    for (metric_code, horizon), rows in grouped.items():
        item = rows[0]
        try:
            y_hat_h = float(item.get("y_hat"))
            p10_h = float(item.get("p10", y_hat_h))
            p50_h = float(item.get("p50", y_hat_h))
            p90_h = float(item.get("p90", y_hat_h))
        except (TypeError, ValueError):
            continue
        steps_total = _horizon_to_steps_local(horizon, freq)
        start_value = latest_raw_by_code.get(metric_code, y_hat_h)
        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}

        for step_idx in range(1, steps_total + 1):
            ratio = float(step_idx) / float(steps_total)
            y_hat = start_value + (y_hat_h - start_value) * ratio
            p10 = start_value + (p10_h - start_value) * ratio
            p50 = start_value + (p50_h - start_value) * ratio
            p90 = start_value + (p90_h - start_value) * ratio
            target_ts = base_ts + (step_delta * step_idx)
            expanded_items.append(
                {
                    **item,
                    "metric_code": metric_code,
                    "horizon": horizon,
                    "target_ts": target_ts.isoformat(),
                    "forecast_step": int(step_idx),
                    "forecast_steps_total": int(steps_total),
                    "y_hat": float(y_hat),
                    "p10": float(p10),
                    "p50": float(p50),
                    "p90": float(p90),
                    "labels": {
                        **labels,
                        "trajectory_expanded": True,
                        "trajectory_expansion_method": "linear_to_horizon",
                        "trajectory_start_value": float(start_value),
                    },
                }
            )

    if not expanded_items:
        return items, {"mode": "native", "expanded": False, "reason": "expansion_empty"}
    return expanded_items, {
        "mode": "terminal_to_trajectory",
        "expanded": True,
        "groups": len(grouped),
        "points_created": len(expanded_items),
    }


def _retry_backoff_seconds(retry_count: int):
    exponent = max(0, min(int(retry_count) - 1, 8))
    return int(min(QUEUE_RETRY_MAX_SEC, QUEUE_RETRY_BASE_SEC * (2 ** exponent)))


def _append_note(run: ForecastRun, note: str):
    note = str(note or "").strip()
    if not note:
        return run.notes
    if run.notes:
        return f"{run.notes}\n{note}"
    return note


def _mark_failed(run: ForecastRun, message: str, quality: dict):
    quality = dict(quality or {})
    quality.setdefault("errors", []).append(str(message))
    run.status = "failed"
    run.finished_at = timezone.now()
    run.quality = quality
    run.notes = _append_note(run, f"Error: {message}")
    run.save(update_fields=["status", "finished_at", "quality", "notes", "updated_at"])


def _mark_pending(run: ForecastRun, quality: dict, note: str = ""):
    run.status = "pending"
    run.quality = dict(quality or {})
    if note:
        run.notes = _append_note(run, note)
    run.save(update_fields=["status", "quality", "notes", "updated_at"])


def _mark_running(run: ForecastRun, quality: dict, note: str = ""):
    run.status = "running"
    run.quality = dict(quality or {})
    if note:
        run.notes = _append_note(run, note)
    run.save(update_fields=["status", "quality", "notes", "updated_at"])


def _collect_metric_payload(device: Device, *, metric_codes: list[str], since):
    now = timezone.now()
    payload_metrics = {}
    quality = {
        "metrics_requested": len(metric_codes),
        "metrics_processed": 0,
        "metrics_skipped": 0,
        "errors": [],
        "history_points_total": 0,
        "history_points_by_metric": {},
    }

    for metric_code in metric_codes:
        try:
            rows = list(
                RawMetric.objects
                .filter(device=device, code=metric_code, timestamp__gte=since, timestamp__lte=now)
                .values_list("timestamp", "value")
                .order_by("timestamp")
            )
            if len(rows) < 40:
                quality["history_points_by_metric"][metric_code] = len(rows)
                quality["history_points_total"] += len(rows)
                quality["metrics_skipped"] += 1
                continue

            payload_metrics[metric_code] = [
                {"timestamp": ts.isoformat(), "value": float(value)}
                for ts, value in rows
            ]
            quality["history_points_by_metric"][metric_code] = len(rows)
            quality["history_points_total"] += len(rows)
            quality["metrics_processed"] += 1
        except Exception as exc:
            quality["metrics_skipped"] += 1
            quality["errors"].append(f"{metric_code}: {exc}")

    return payload_metrics, quality


def _persist_completed_job(
    *,
    run: ForecastRun,
    device: Device,
    horizons: list[str],
    freq: str,
    remote_job_id: str,
    remote_payload: dict,
):
    if ForecastPoint.objects.filter(run=run).exists():
        run.status = "success"
        if not run.finished_at:
            run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])
        return {"points": 0, "states": 0, "already_imported": True}

    result = remote_payload.get("result") or {}
    items_raw = result.get("forecasts") or []
    if not isinstance(items_raw, list):
        raise RuntimeError("Remote result has invalid forecasts format")
    items = [item for item in items_raw if isinstance(item, dict)]
    if not items:
        raise RuntimeError("Remote result has empty forecast points")

    expanded_items, expansion_meta = _expand_terminal_lstm_items_if_needed(
        device=device,
        run=run,
        horizons=horizons,
        freq=freq,
        items=items,
    )

    points_batch = []
    states_batch = []
    per_horizon_points = {h: [] for h in horizons}
    now = timezone.now()

    for item in expanded_items:
        metric_code = str(item.get("metric_code") or "").strip()
        horizon = str(item.get("horizon") or "").strip()
        if not metric_code or not horizon or horizon not in per_horizon_points:
            continue

        y_hat_raw = float(item.get("y_hat"))
        p10_raw = float(item.get("p10", y_hat_raw))
        p50_raw = float(item.get("p50", y_hat_raw))
        p90_raw = float(item.get("p90", y_hat_raw))
        y_hat, p10, p50, p90 = _sanitize_prediction(
            metric_code=metric_code,
            y_hat=y_hat_raw,
            p10=p10_raw,
            p50=p50_raw,
            p90=p90_raw,
        )

        target_ts = None
        target_raw = item.get("target_ts")
        if target_raw:
            parsed = parse_datetime(str(target_raw))
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, dt_timezone.utc)
                target_ts = parsed
        if target_ts is None:
            target_ts = now + _horizon_to_timedelta_local(horizon)

        labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
        forecast_step = item.get("forecast_step")
        forecast_steps_total = item.get("forecast_steps_total")
        try:
            forecast_step = int(forecast_step) if forecast_step is not None else None
        except (TypeError, ValueError):
            forecast_step = None
        try:
            forecast_steps_total = int(forecast_steps_total) if forecast_steps_total is not None else None
        except (TypeError, ValueError):
            forecast_steps_total = None
        labels = {
            "source": "lstm_remote",
            "remote_job_id": remote_job_id,
            "freq": freq,
            **({"forecast_step": int(forecast_step)} if forecast_step is not None and forecast_step > 0 else {}),
            **(
                {"forecast_steps_total": int(forecast_steps_total)}
                if forecast_steps_total is not None and forecast_steps_total > 0
                else {}
            ),
            **labels,
        }

        alpha = item.get("alpha")
        try:
            alpha_val = float(alpha)
        except (TypeError, ValueError):
            alpha_val = FORECAST_ALPHA

        point = ForecastPoint(
            run=run,
            device=device,
            metric_code=metric_code,
            horizon=horizon,
            target_ts=target_ts,
            model_kind="lstm",
            y_hat=y_hat,
            p10=p10,
            p50=p50,
            p90=p90,
            alpha=alpha_val,
            labels=labels,
        )
        points_batch.append(point)
        per_horizon_points[horizon].append(point)

    if not points_batch:
        raise RuntimeError("Remote result has no usable forecast points")

    for horizon in horizons:
        state_risk_features = build_state_risk_features_for_points(
            device=device,
            horizon=horizon,
            points=per_horizon_points[horizon],
            source_model="lstm",
            personalized_thresholds=True,
            markov_from_latest_state=False,
        )
        state_result = infer_state_distribution(
            points_by_metric=None,
            risk_features=state_risk_features,
        )
        states_batch.append(
            StateEstimate(
                run=run,
                device=device,
                horizon=horizon,
                state=state_result["state"],
                p_s0=state_result["p_s0"],
                p_s1=state_result["p_s1"],
                p_s2=state_result["p_s2"],
                confidence=state_result["confidence"],
                evidence={
                    "source": "lstm_remote",
                    "remote_job_id": remote_job_id,
                    **(state_result["evidence"] or {}),
                },
                timestamp=now,
            )
        )

    with transaction.atomic():
        ForecastPoint.objects.bulk_create(points_batch, batch_size=500)
        StateEstimate.objects.bulk_create(states_batch, batch_size=100)

        remote_quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
        quality = dict(run.quality or {})
        quality.update({
            "remote_job_id": remote_job_id,
            "points_created": len(points_batch),
            "states_created": len(states_batch),
            "remote_quality": remote_quality,
            "trajectory_import": expansion_meta,
        })
        run.status = "success"
        run.finished_at = timezone.now()
        run.quality = quality
        run.save(update_fields=["status", "finished_at", "quality", "updated_at"])

    return {"points": len(points_batch), "states": len(states_batch), "already_imported": False}


def _queue_queryset(*, run_id: int | None = None, run_ids: list[int] | None = None, serial: str | None = None):
    qs = LSTMRemoteQueueJob.objects.select_related("forecast_run", "device")
    if run_id:
        qs = qs.filter(forecast_run_id=int(run_id))
    if run_ids:
        run_ids = [int(r) for r in run_ids if r]
        if run_ids:
            qs = qs.filter(forecast_run_id__in=run_ids)
    if serial:
        qs = qs.filter(device__serial_number=serial)
    return qs


def _claim_next_queue_job(*, run_id: int | None = None, run_ids: list[int] | None = None, serial: str | None = None):
    now = timezone.now()
    with transaction.atomic():
        qs = (
            _queue_queryset(run_id=run_id, run_ids=run_ids, serial=serial)
            .filter(status__in=ACTIVE_QUEUE_STATUSES)
            .filter(next_retry_at__lte=now)
            .filter(Q(locked_until__isnull=True) | Q(locked_until__lte=now))
            .order_by("next_retry_at", "id")
        )
        job = qs.select_for_update(skip_locked=True).first()
        if not job:
            return None

        job.locked_until = now + timedelta(seconds=QUEUE_LEASE_SEC)
        # Keep polling existing remote job after transient poll errors.
        should_submit = job.status in ("queued", "submitting") or (
            job.status == "retry_wait" and not str(job.remote_job_id or "").strip()
        )
        if should_submit:
            job.status = "submitting"
            job.attempts_submit = int(job.attempts_submit or 0) + 1
            job.save(update_fields=["locked_until", "status", "attempts_submit", "updated_at"])
        else:
            job.status = "polling"
            job.attempts_poll = int(job.attempts_poll or 0) + 1
            job.save(update_fields=["locked_until", "status", "attempts_poll", "updated_at"])
        return job


def _set_queue_retry_or_fail(
    job: LSTMRemoteQueueJob,
    *,
    error: str,
    clear_remote_job: bool = False,
    force_fail: bool = False,
):
    now = timezone.now()
    message = str(error or "Unexpected queue error")

    with transaction.atomic():
        row = LSTMRemoteQueueJob.objects.select_for_update().get(pk=job.pk)
        row.last_error = message
        row.locked_until = None

        if clear_remote_job:
            row.remote_job_id = None
            row.submit_response = {}

        if force_fail:
            row.status = "failed"
            row.next_retry_at = now
        else:
            row.retry_count = int(row.retry_count or 0) + 1
            if row.retry_count > int(row.max_retries or 0):
                row.status = "failed"
                row.next_retry_at = now
            else:
                row.status = "retry_wait"
                row.next_retry_at = now + timedelta(seconds=_retry_backoff_seconds(row.retry_count))

        row.save(
            update_fields=[
                "last_error",
                "locked_until",
                "remote_job_id",
                "submit_response",
                "retry_count",
                "status",
                "next_retry_at",
                "updated_at",
            ]
        )

    quality = dict(job.forecast_run.quality or {})
    quality.setdefault("errors", []).append(message)
    if row.status == "failed":
        _mark_failed(job.forecast_run, message, quality)
    else:
        _mark_pending(
            job.forecast_run,
            quality,
            note=f"LSTM queue retry #{row.retry_count}/{row.max_retries}: {message}",
        )

    return row.status


def _set_queue_submitted(job: LSTMRemoteQueueJob, submit_response: dict, remote_job_id: str):
    now = timezone.now()
    with transaction.atomic():
        row = LSTMRemoteQueueJob.objects.select_for_update().get(pk=job.pk)
        row.remote_job_id = remote_job_id
        row.submit_response = submit_response or {}
        row.last_error = ""
        row.status = "submitted"
        row.next_retry_at = now
        row.locked_until = None
        row.save(
            update_fields=[
                "remote_job_id",
                "submit_response",
                "last_error",
                "status",
                "next_retry_at",
                "locked_until",
                "updated_at",
            ]
        )

    run = job.forecast_run
    run.parameters = {
        **(run.parameters or {}),
        "remote_job_id": remote_job_id,
        "remote_submit_response": submit_response,
    }
    quality = dict(run.quality or {})
    quality["queue_job_id"] = job.id
    _mark_running(run, quality)
    run.save(update_fields=["parameters", "updated_at"])


def _set_queue_running(job: LSTMRemoteQueueJob, remote_payload: dict, poll_interval_sec: float):
    now = timezone.now()
    wait_sec = max(1.0, float(poll_interval_sec))
    with transaction.atomic():
        row = LSTMRemoteQueueJob.objects.select_for_update().get(pk=job.pk)
        row.status = "submitted"
        row.remote_snapshot = remote_payload if isinstance(remote_payload, dict) else {}
        row.next_retry_at = now + timedelta(seconds=wait_sec)
        row.locked_until = None
        row.save(update_fields=["status", "remote_snapshot", "next_retry_at", "locked_until", "updated_at"])

    _mark_running(job.forecast_run, dict(job.forecast_run.quality or {}))


def _set_queue_success(job: LSTMRemoteQueueJob, remote_payload: dict):
    now = timezone.now()
    with transaction.atomic():
        row = LSTMRemoteQueueJob.objects.select_for_update().get(pk=job.pk)
        row.status = "success"
        row.remote_snapshot = remote_payload if isinstance(remote_payload, dict) else {}
        row.last_error = ""
        row.next_retry_at = now
        row.locked_until = None
        row.save(
            update_fields=["status", "remote_snapshot", "last_error", "next_retry_at", "locked_until", "updated_at"]
        )


def _non_retriable_submit_error(message: str):
    raw = str(message or "")
    return any(code in raw for code in ("HTTP 400", "HTTP 401", "HTTP 403"))


def _non_retriable_poll_error(message: str):
    raw = str(message or "")
    return any(code in raw for code in ("HTTP 400", "HTTP 401", "HTTP 403"))


def _process_submit_step(client: LSTMRemoteClient, job: LSTMRemoteQueueJob):
    try:
        submit_response = client.submit_job(job.request_payload or {})
        remote_job_id = str(submit_response.get("job_id") or "").strip()
        if not remote_job_id:
            raise RuntimeError("Remote submit returned empty job_id")

        _set_queue_submitted(job, submit_response, remote_job_id)
        return {"event": "submitted", "points": 0, "states": 0}
    except Exception as exc:
        message = str(exc)
        status = _set_queue_retry_or_fail(
            job,
            error=message,
            clear_remote_job=False,
            force_fail=_non_retriable_submit_error(message),
        )
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}


def _process_poll_step(client: LSTMRemoteClient, job: LSTMRemoteQueueJob, poll_interval_sec: float):
    remote_job_id = str(job.remote_job_id or "").strip()
    if not remote_job_id:
        status = _set_queue_retry_or_fail(
            job,
            error="Queue job has no remote_job_id",
            clear_remote_job=True,
        )
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    try:
        payload = client.get_job(remote_job_id)
    except Exception as exc:
        message = str(exc)
        status = _set_queue_retry_or_fail(
            job,
            error=message,
            clear_remote_job=("HTTP 404" in message),
            force_fail=_non_retriable_poll_error(message),
        )
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    if not isinstance(payload, dict):
        status = _set_queue_retry_or_fail(job, error="Remote LSTM job payload is not an object")
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    status_value = str(payload.get("status") or "").strip().lower()
    if not status_value:
        status = _set_queue_retry_or_fail(job, error="Remote LSTM job payload has empty status")
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    if status_value == "completed":
        try:
            result_counts = _persist_completed_job(
                run=job.forecast_run,
                device=job.device,
                horizons=_normalize_horizons((job.forecast_run.parameters or {}).get("horizons")),
                freq=str((job.forecast_run.parameters or {}).get("freq") or "1h"),
                remote_job_id=remote_job_id,
                remote_payload=payload,
            )
            _set_queue_success(job, payload)
            return {
                "event": "completed",
                "points": int(result_counts.get("points", 0)),
                "states": int(result_counts.get("states", 0)),
            }
        except Exception as exc:
            message = str(exc)
            status = _set_queue_retry_or_fail(job, error=message)
            return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    if status_value == "failed":
        message = str(payload.get("error") or "Remote LSTM job failed")
        status = _set_queue_retry_or_fail(job, error=message, clear_remote_job=True)
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    if status_value not in ("queued", "running", "submitted"):
        status = _set_queue_retry_or_fail(job, error=f"Remote LSTM returned unsupported status: {status_value}")
        return {"event": "failed" if status == "failed" else "retry", "points": 0, "states": 0}

    _set_queue_running(job, payload, poll_interval_sec)
    return {"event": "running", "points": 0, "states": 0}


def _enqueue_queue_job(
    *,
    run: ForecastRun,
    device: Device,
    request_payload: dict,
    max_retries: int,
):
    now = timezone.now()
    request_id = str(request_payload.get("request_id") or f"run-{run.id}").strip()
    payload = dict(request_payload or {})
    payload["request_id"] = request_id

    defaults = {
        "device": device,
        "request_id": request_id,
        "status": "queued",
        "request_payload": payload,
        "max_retries": max(0, int(max_retries)),
        "next_retry_at": now,
    }

    job, created = LSTMRemoteQueueJob.objects.get_or_create(
        forecast_run=run,
        defaults=defaults,
    )

    if not created and job.status not in ("success", "failed"):
        changed = False
        if job.request_payload != payload:
            job.request_payload = payload
            changed = True
        if job.max_retries != defaults["max_retries"]:
            job.max_retries = defaults["max_retries"]
            changed = True
        if job.status in ("retry_wait", "queued"):
            if job.next_retry_at > now:
                job.next_retry_at = now
                changed = True
        if changed:
            job.save(update_fields=["request_payload", "max_retries", "next_retry_at", "updated_at"])

    run.parameters = {
        **(run.parameters or {}),
        "request_id": request_id,
        "queue_job_id": job.id,
        "max_retries": max(0, int(max_retries)),
    }
    run.save(update_fields=["parameters", "updated_at"])
    return job, created


def run_lstm_remote_forecasts(
    *,
    serial: str | None = None,
    lookback_days: int = 60,
    freq: str = "1h",
    horizons: list[str] | None = None,
    metric_codes: list[str] | None = None,
    wait_for_result: bool = True,
    poll_interval_sec: float = 2.0,
    max_wait_sec: float = 120.0,
    max_retries: int = 5,
    model_options: dict | None = None,
):
    # Validate remote client configuration, but do not require service availability
    # at enqueue time. Tasks should survive temporary remote downtime.
    LSTMRemoteClient.from_env()

    horizons = _normalize_horizons(horizons)
    requested_lookback_days = max(1, int(lookback_days))
    effective_lookback_days = max(
        requested_lookback_days,
        _minimum_history_days_for_horizons(horizons, freq),
    )
    requested_metric_codes = metric_codes or list(DEFAULT_METRIC_CODES)
    profile_config = get_active_state_inference_profile_config()
    metric_codes = resolve_metric_codes_for_source(
        "lstm",
        requested_codes=requested_metric_codes,
        config=profile_config,
    )
    since = timezone.now() - timedelta(days=effective_lookback_days)

    devices_qs = Device.objects.all()
    if serial:
        devices_qs = devices_qs.filter(serial_number=serial)
    devices = list(devices_qs)

    if not devices:
        return {
            "created_runs": 0,
            "queued_jobs": 0,
            "created_points": 0,
            "created_states": 0,
            "failed_runs": 0,
            "pending_runs": 0,
            "detail": "No devices found",
        }
    if not metric_codes:
        return {
            "created_runs": 0,
            "queued_jobs": 0,
            "created_points": 0,
            "created_states": 0,
            "failed_runs": 0,
            "pending_runs": 0,
            "detail": "Для LSTM нет активных метрик в настройках профиля.",
        }
    disabled_metric_codes = [code for code in requested_metric_codes if code not in metric_codes]

    created_runs = 0
    queued_jobs = 0
    run_ids: list[int] = []

    for device in devices:
        now = timezone.now()
        run = ForecastRun.objects.create(
            device=device,
            model_kind="lstm",
            horizon_set=",".join(horizons),
            status="pending",
            started_at=now,
            parameters={
                "mode": "lstm_remote",
                "lookback_days": int(effective_lookback_days),
                "lookback_days_requested": int(requested_lookback_days),
                "history_days_recommended": int(_recommended_history_days_for_horizons(horizons, freq)),
                "freq": freq,
                "horizons": horizons,
                "metric_codes_requested": requested_metric_codes,
                "metric_codes": metric_codes,
                "metrics_disabled_by_profile": disabled_metric_codes,
                "wait_for_result": bool(wait_for_result),
                "max_retries": max(0, int(max_retries)),
            },
            quality={},
            notes="Remote LSTM forecast run",
        )
        created_runs += 1
        run_ids.append(run.id)

        payload_metrics, quality = _collect_metric_payload(device, metric_codes=metric_codes, since=since)
        quality["metric_codes_requested"] = requested_metric_codes
        quality["metric_codes_effective"] = metric_codes
        quality["metrics_disabled_by_profile"] = disabled_metric_codes
        if not payload_metrics:
            _mark_failed(run, "No sufficient raw metrics for remote LSTM", quality)
            continue

        run.quality = quality
        run.save(update_fields=["quality", "updated_at"])

        remote_model_options = {
            **_default_remote_model_options(
                lookback_days=effective_lookback_days,
                freq=freq,
                horizons=horizons,
                profile_config=profile_config,
                metric_codes=metric_codes,
            ),
            **(model_options if isinstance(model_options, dict) else {}),
            "alpha": FORECAST_ALPHA,
        }
        recommended_lookback = _recommended_remote_lookback(freq=freq, horizons=horizons)
        explicit_model_lookback = isinstance(model_options, dict) and model_options.get("lookback") is not None
        try:
            requested_model_lookback = int(remote_model_options.get("lookback", recommended_lookback))
        except (TypeError, ValueError):
            requested_model_lookback = recommended_lookback
        history_steps = max(_steps_per_day(freq) * effective_lookback_days, _steps_per_day(freq) * 2)
        max_usable_lookback = max(24, history_steps - 8)
        effective_model_lookback = max(24, requested_model_lookback)
        if not explicit_model_lookback:
            effective_model_lookback = max(effective_model_lookback, recommended_lookback)
        remote_model_options["lookback"] = min(effective_model_lookback, max_usable_lookback)

        request_payload = {
            "request_id": f"run-{run.id}",
            "device_serial": device.serial_number,
            "freq": freq,
            "horizons": horizons,
            "metrics": payload_metrics,
            "options": remote_model_options,
        }
        quality = {
            **(quality or {}),
            "remote_model_options": remote_model_options,
            "lookback_days_requested": int(requested_lookback_days),
            "lookback_days_effective": int(effective_lookback_days),
            "history_days_recommended": int(_recommended_history_days_for_horizons(horizons, freq)),
        }
        run.parameters = {
            **(run.parameters or {}),
            "remote_model_options": remote_model_options,
        }
        run.quality = quality
        run.save(update_fields=["parameters", "quality", "updated_at"])

        _, created = _enqueue_queue_job(
            run=run,
            device=device,
            request_payload=request_payload,
            max_retries=max_retries,
        )
        if created:
            queued_jobs += 1
        _mark_pending(run, quality, note="Remote LSTM job queued")

    created_points = 0
    created_states = 0
    failed_runs = 0
    pending_runs = 0

    drain_error = ""
    if wait_for_result and run_ids:
        try:
            drain = drain_lstm_remote_queue(
                run_ids=run_ids,
                limit=max(1, len(run_ids)),
                poll_interval_sec=poll_interval_sec,
                max_wait_sec=max_wait_sec,
            )
            created_points = int(drain.get("imported_points", 0))
            created_states = int(drain.get("imported_states", 0))
        except Exception as exc:
            drain_error = str(exc)

    status_rows = ForecastRun.objects.filter(id__in=run_ids).values_list("status", flat=True)
    for st in status_rows:
        if st in ("pending", "running"):
            pending_runs += 1
        elif st == "failed":
            failed_runs += 1

    payload = {
        "created_runs": created_runs,
        "queued_jobs": queued_jobs,
        "created_points": created_points,
        "created_states": created_states,
        "failed_runs": failed_runs,
        "pending_runs": pending_runs,
        "run_ids": run_ids,
    }
    if drain_error:
        payload["drain_error"] = drain_error
    return payload


def poll_lstm_remote_runs(
    *,
    run_id: int | None = None,
    run_ids: list[int] | None = None,
    serial: str | None = None,
    limit: int = 20,
    poll_interval_sec: float = 10.0,
):
    client = LSTMRemoteClient.from_env()
    client.check_health()

    limit = max(1, int(limit))
    poll_interval_sec = max(1.0, float(poll_interval_sec))

    processed = 0
    submitted = 0
    completed = 0
    failed = 0
    retried = 0
    running = 0
    imported_points = 0
    imported_states = 0

    while processed < limit:
        job = _claim_next_queue_job(run_id=run_id, run_ids=run_ids, serial=serial)
        if not job:
            break

        if job.status == "submitting":
            result = _process_submit_step(client, job)
        else:
            result = _process_poll_step(client, job, poll_interval_sec=poll_interval_sec)

        processed += 1
        event = result.get("event")
        if event == "submitted":
            submitted += 1
        elif event == "completed":
            completed += 1
            imported_points += int(result.get("points", 0) or 0)
            imported_states += int(result.get("states", 0) or 0)
        elif event == "failed":
            failed += 1
        elif event == "retry":
            retried += 1
        elif event == "running":
            running += 1

    qs_scope = _queue_queryset(run_id=run_id, run_ids=run_ids, serial=serial)
    active_after = qs_scope.filter(status__in=ACTIVE_QUEUE_STATUSES).count()
    retry_wait_after = qs_scope.filter(status="retry_wait").count()

    return {
        "checked_jobs": processed,
        "submitted": submitted,
        "completed": completed,
        "failed": failed,
        "retried": retried,
        "running": running,
        "active_after": active_after,
        "retry_wait_after": retry_wait_after,
        "imported_points": imported_points,
        "imported_states": imported_states,
    }


def drain_lstm_remote_queue(
    *,
    run_id: int | None = None,
    run_ids: list[int] | None = None,
    serial: str | None = None,
    limit: int = 20,
    poll_interval_sec: float = 2.0,
    max_wait_sec: float = 120.0,
):
    start = time.monotonic()
    timed_out = False

    total_checked = 0
    total_submitted = 0
    total_completed = 0
    total_failed = 0
    total_retried = 0
    total_running = 0
    total_points = 0
    total_states = 0

    while True:
        step = poll_lstm_remote_runs(
            run_id=run_id,
            run_ids=run_ids,
            serial=serial,
            limit=limit,
            poll_interval_sec=poll_interval_sec,
        )
        total_checked += int(step.get("checked_jobs", 0) or 0)
        total_submitted += int(step.get("submitted", 0) or 0)
        total_completed += int(step.get("completed", 0) or 0)
        total_failed += int(step.get("failed", 0) or 0)
        total_retried += int(step.get("retried", 0) or 0)
        total_running += int(step.get("running", 0) or 0)
        total_points += int(step.get("imported_points", 0) or 0)
        total_states += int(step.get("imported_states", 0) or 0)

        active_after = int(step.get("active_after", 0) or 0)
        if active_after <= 0:
            break

        elapsed = time.monotonic() - start
        if elapsed >= max(1.0, float(max_wait_sec)):
            timed_out = True
            break

        time.sleep(max(0.5, float(poll_interval_sec)))

    return {
        "timed_out": timed_out,
        "checked_jobs": total_checked,
        "submitted": total_submitted,
        "completed": total_completed,
        "failed": total_failed,
        "retried": total_retried,
        "running": total_running,
        "imported_points": total_points,
        "imported_states": total_states,
    }
