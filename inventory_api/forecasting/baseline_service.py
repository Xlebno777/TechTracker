from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from inventory_api.forecasting.preprocess import (
    preprocess_points,
    horizon_to_steps,
)
from inventory_api.forecasting.sarima_model import fit_sarima, forecast_with_intervals
from inventory_api.forecasting.risk_assessment_service import (
    build_state_risk_features_for_points,
)
from inventory_api.forecasting.state_inference_service import (
    infer_state_distribution,
    get_active_state_inference_profile_config,
    resolve_metric_codes_for_source,
)
from inventory_api.models import (
    Device,
    RawMetric,
    ComputedMetric,
    ForecastRun,
    ForecastPoint,
    StateEstimate,
)


DEFAULT_METRIC_CODES = [
    "cpu_load_total",
    "mem_usage_percent",
    "net_bytes_sent",
    "net_bytes_recv",
    "ping_latency_gateway",
    "system_temperature",
    "storcli_drive_temperature",
    "storcli_predictive_failure_count",
]

FORECAST_ALPHA = 0.2
SEASONALITY_MODE_SARIMA_SEASONAL = "sarima_seasonal"
SEASONALITY_MODE_STL_RESEASONALIZED = "stl_reseasonalized"
DEFAULT_SEASONALITY_MODE = SEASONALITY_MODE_STL_RESEASONALIZED


def _ensure_dependencies():
    # Local import check so server still runs if these deps are not installed.
    try:
        import pandas  # noqa: F401
        import statsmodels  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "Baseline SARIMA dependencies are missing. Install pandas and statsmodels."
        ) from exc


def _is_percent_metric(metric_code: str) -> bool:
    raw = (metric_code or "").strip().lower()
    if raw in {"cpu_load_total", "mem_usage_percent"}:
        return True
    return "percent" in raw or raw.endswith("_pct") or raw.endswith("_percentage")


def _metric_bounds(metric_code: str):
    raw = (metric_code or "").strip().lower()
    if "temp" in raw or "temperature" in raw:
        return 0.0, None
    if _is_percent_metric(raw):
        return 0.0, 100.0
    # For this system all telemetry values are non-negative by physical constraints.
    return 0.0, None


def _clamp_metric_value(metric_code: str, value: float | None):
    if value is None:
        return None
    min_v, max_v = _metric_bounds(metric_code)
    out = float(value)
    if min_v is not None:
        out = max(min_v, out)
    if max_v is not None:
        out = min(max_v, out)
    return out


def _sanitize_prediction(metric_code: str, y_hat: float, p10: float, p50: float, p90: float):
    y = _clamp_metric_value(metric_code, y_hat)
    low = _clamp_metric_value(metric_code, p10)
    med = _clamp_metric_value(metric_code, p50)
    high = _clamp_metric_value(metric_code, p90)

    if low is None:
        low = med if med is not None else y
    if high is None:
        high = med if med is not None else y
    if med is None:
        med = y

    if low is None:
        low = 0.0
    if high is None:
        high = low
    if med is None:
        med = low

    if low > high:
        low, high = high, low
    med = min(max(med, low), high)
    y = med if y is None else min(max(y, low), high)

    return float(y), float(low), float(med), float(high)


def normalize_seasonality_mode(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {SEASONALITY_MODE_SARIMA_SEASONAL, SEASONALITY_MODE_STL_RESEASONALIZED}:
        return raw
    return DEFAULT_SEASONALITY_MODE


def seasonality_mode_label(value: str | None) -> str:
    mode = normalize_seasonality_mode(value)
    if mode == SEASONALITY_MODE_SARIMA_SEASONAL:
        return "SARIMA с сезонностью"
    return "STL + возврат сезонности"


def _freq_to_timedelta(freq: str | None) -> timedelta:
    raw = str(freq or "").strip().lower()
    if raw.endswith("min"):
        return timedelta(minutes=max(1, int(raw[:-3] or "1")))
    if raw.endswith("h"):
        return timedelta(hours=max(1, int(raw[:-1] or "1")))
    if raw.endswith("d"):
        return timedelta(days=max(1, int(raw[:-1] or "1")))
    return timedelta(hours=1)


def project_repeating_seasonality(preprocess_result, *, steps: int) -> list[float]:
    if steps <= 0:
        return []

    seasonal_series = getattr(preprocess_result, "seasonal", None)
    seasonal_period = int(getattr(preprocess_result, "seasonal_period", 0) or 0)
    if seasonal_series is None or seasonal_period <= 0:
        return [0.0 for _ in range(steps)]

    seasonal_values = seasonal_series.dropna().astype(float)
    if seasonal_values.empty:
        return [0.0 for _ in range(steps)]

    pattern = seasonal_values.iloc[-seasonal_period:].tolist()
    if not pattern:
        return [0.0 for _ in range(steps)]
    return [float(pattern[idx % len(pattern)]) for idx in range(steps)]


def project_recent_trend_adjustment(preprocess_result, *, steps: int):
    if steps <= 0:
        return [], {
            "applied": False,
            "reason": "no_steps",
            "slope_per_step": 0.0,
            "window": 0,
        }

    trend_series = getattr(preprocess_result, "trend", None)
    seasonal_period = int(getattr(preprocess_result, "seasonal_period", 0) or 0)
    zeros = [0.0 for _ in range(steps)]
    if trend_series is None:
        return zeros, {
            "applied": False,
            "reason": "missing_trend",
            "slope_per_step": 0.0,
            "window": 0,
        }

    trend_values = trend_series.dropna().astype(float)
    if trend_values.empty:
        return zeros, {
            "applied": False,
            "reason": "empty_trend",
            "slope_per_step": 0.0,
            "window": 0,
        }

    min_window = max(24, seasonal_period)
    recent_window = min(len(trend_values) // 2, max(48, seasonal_period * 3))
    if recent_window < min_window:
        return zeros, {
            "applied": False,
            "reason": "not_enough_history",
            "slope_per_step": 0.0,
            "window": int(max(0, recent_window)),
        }

    previous_segment = trend_values.iloc[-2 * recent_window:-recent_window]
    recent_segment = trend_values.iloc[-recent_window:]
    if len(previous_segment) < recent_window or len(recent_segment) < recent_window:
        return zeros, {
            "applied": False,
            "reason": "window_split_failed",
            "slope_per_step": 0.0,
            "window": int(recent_window),
        }

    previous_mean = float(previous_segment.mean())
    recent_mean = float(recent_segment.mean())
    delta = recent_mean - previous_mean
    recent_std = float(recent_segment.std(ddof=0) or 0.0)
    minimum_signal = max(
        0.05,
        abs(recent_mean) * 0.005,
        recent_std * 0.15,
    )
    if abs(delta) < minimum_signal:
        return zeros, {
            "applied": False,
            "reason": "weak_recent_trend",
            "delta": delta,
            "minimum_signal": minimum_signal,
            "slope_per_step": 0.0,
            "window": int(recent_window),
        }

    slope_per_step = delta / float(recent_window)
    adjustments = [float(slope_per_step * (idx + 1)) for idx in range(steps)]
    return adjustments, {
        "applied": True,
        "method": "recent_mean_delta",
        "delta": delta,
        "minimum_signal": minimum_signal,
        "recent_mean": recent_mean,
        "previous_mean": previous_mean,
        "recent_std": recent_std,
        "slope_per_step": float(slope_per_step),
        "window": int(recent_window),
        "last_trend_value": float(trend_values.iloc[-1]),
    }


def run_baseline_forecasts(
    *,
    serial: str | None = None,
    lookback_days: int = 60,
    freq: str = "1h",
    horizons: list[str] | None = None,
    metric_codes: list[str] | None = None,
    save_stl_components: bool = True,
    seasonality_mode: str | None = None,
):
    _ensure_dependencies()

    now = timezone.now()
    horizons = horizons or ["24h", "7d", "30d"]
    requested_metric_codes = metric_codes or list(DEFAULT_METRIC_CODES)
    profile_config = get_active_state_inference_profile_config()
    metric_codes = resolve_metric_codes_for_source(
        "sarima",
        requested_codes=requested_metric_codes,
        config=profile_config,
    )
    resolved_seasonality_mode = normalize_seasonality_mode(seasonality_mode)
    disabled_metric_codes = [code for code in requested_metric_codes if code not in metric_codes]

    devices_qs = Device.objects.all()
    if serial:
        devices_qs = devices_qs.filter(serial_number=serial)
    devices = list(devices_qs)
    if not devices:
        return {"created_runs": 0, "created_points": 0, "created_states": 0, "failed_runs": 0, "detail": "No devices found"}
    if not metric_codes:
        return {
            "created_runs": 0,
            "created_points": 0,
            "created_states": 0,
            "failed_runs": 0,
            "detail": "Для SARIMA нет активных метрик в настройках профиля.",
        }

    created_runs = 0
    created_points = 0
    created_states = 0
    failed_runs = 0
    run_ids = []

    since = now - timedelta(days=max(1, lookback_days))

    for device in devices:
        run = ForecastRun.objects.create(
            device=device,
            model_kind="sarima",
            horizon_set=",".join(horizons),
            status="running",
            started_at=now,
            parameters={
                "lookback_days": lookback_days,
                "freq": freq,
                "horizons": horizons,
                "metric_codes_requested": requested_metric_codes,
                "metric_codes": metric_codes,
                "metrics_disabled_by_profile": disabled_metric_codes,
                "preprocess": "stl_trend_plus_resid",
                "seasonality_mode": resolved_seasonality_mode,
                "seasonality_mode_label": seasonality_mode_label(resolved_seasonality_mode),
            },
            notes="Local baseline SARIMA forecast run",
        )
        created_runs += 1
        run_ids.append(run.id)

        points_batch = []
        states_batch = []
        stl_components_batch = []
        per_horizon_points = {h: [] for h in horizons}
        quality = {"metrics_processed": 0, "metrics_skipped": 0, "errors": []}
        quality["history_points_total"] = 0
        quality["history_points_by_metric"] = {}
        quality["seasonality_mode"] = resolved_seasonality_mode
        quality["metric_codes_requested"] = requested_metric_codes
        quality["metric_codes_effective"] = metric_codes
        quality["metrics_disabled_by_profile"] = disabled_metric_codes

        step_delta = _freq_to_timedelta(freq)

        try:
            for metric_code in metric_codes:
                try:
                    rows = list(
                        RawMetric.objects
                        .filter(device=device, code=metric_code, timestamp__gte=since, timestamp__lte=now)
                        .values_list("timestamp", "value")
                        .order_by("timestamp")
                    )
                    quality["history_points_by_metric"][metric_code] = len(rows)
                    quality["history_points_total"] += len(rows)
                    if len(rows) < 40:
                        quality["metrics_skipped"] += 1
                        continue

                    preprocess_seasonal_period = None
                    if resolved_seasonality_mode == SEASONALITY_MODE_SARIMA_SEASONAL:
                        # Keep SARIMA-seasonal mode lightweight and stable with daily period.
                        preprocess_seasonal_period = horizon_to_steps("24h", freq)
                    pre = preprocess_points(
                        rows,
                        freq=freq,
                        clip_quantile=0.01,
                        max_points=1200,
                        seasonal_period=preprocess_seasonal_period,
                    )
                    model_series = (
                        pre.resampled
                        if resolved_seasonality_mode == SEASONALITY_MODE_SARIMA_SEASONAL
                        else pre.resid
                    )
                    fit_seasonal_period = (
                        pre.seasonal_period
                        if resolved_seasonality_mode == SEASONALITY_MODE_SARIMA_SEASONAL
                        else 0
                    )
                    fitted, order, seasonal_order = fit_sarima(model_series, fit_seasonal_period)
                    quality["metrics_processed"] += 1

                    max_steps = max(horizon_to_steps(h, freq) for h in horizons)
                    mean, lower, upper = forecast_with_intervals(fitted, steps=max_steps, alpha=FORECAST_ALPHA)
                    future_trend_delta, trend_projection = project_recent_trend_adjustment(pre, steps=max_steps)
                    last_trend_value = float(pre.trend.dropna().iloc[-1]) if len(pre.trend.dropna()) else 0.0
                    future_seasonality = (
                        project_repeating_seasonality(pre, steps=max_steps)
                        if resolved_seasonality_mode == SEASONALITY_MODE_STL_RESEASONALIZED
                        else [0.0 for _ in range(max_steps)]
                    )

                    if save_stl_components and len(pre.cleaned) > 0:
                        last_ts = pre.cleaned.index[-1].to_pydatetime()
                        labels = {"metric_code": metric_code, "freq": freq, "source": "sarima_baseline"}
                        stl_components_batch.extend([
                            ComputedMetric(
                                device=device,
                                code=f"stl_trend_{metric_code}",
                                value=float(pre.trend.iloc[-1]),
                                unit="value",
                                window="current",
                                timestamp=last_ts,
                                labels=labels,
                            ),
                            ComputedMetric(
                                device=device,
                                code=f"stl_seasonal_{metric_code}",
                                value=float(pre.seasonal.iloc[-1]),
                                unit="value",
                                window="current",
                                timestamp=last_ts,
                                labels=labels,
                            ),
                            ComputedMetric(
                                device=device,
                                code=f"stl_resid_{metric_code}",
                                value=float(pre.resid.iloc[-1]),
                                unit="value",
                                window="current",
                                timestamp=last_ts,
                                labels=labels,
                            ),
                        ])

                    for horizon in horizons:
                        steps = horizon_to_steps(horizon, freq)
                        for step_index in range(1, steps + 1):
                            idx = step_index - 1
                            if idx >= len(mean):
                                break
                            seasonal_adjustment = float(future_seasonality[idx]) if idx < len(future_seasonality) else 0.0
                            trend_delta = float(future_trend_delta[idx]) if idx < len(future_trend_delta) else 0.0
                            if resolved_seasonality_mode == SEASONALITY_MODE_STL_RESEASONALIZED:
                                projected_trend_value = last_trend_value + trend_delta
                                y_hat_raw = float(mean.iloc[idx]) + projected_trend_value + seasonal_adjustment
                                p10_raw = float(lower.iloc[idx]) + projected_trend_value + seasonal_adjustment
                                p50_raw = float(mean.iloc[idx]) + projected_trend_value + seasonal_adjustment
                                p90_raw = float(upper.iloc[idx]) + projected_trend_value + seasonal_adjustment
                            else:
                                projected_trend_value = None
                                y_hat_raw = float(mean.iloc[idx]) + trend_delta
                                p10_raw = float(lower.iloc[idx]) + trend_delta
                                p50_raw = float(mean.iloc[idx]) + trend_delta
                                p90_raw = float(upper.iloc[idx]) + trend_delta
                            y_hat, p10, p50, p90 = _sanitize_prediction(
                                metric_code=metric_code,
                                y_hat=y_hat_raw,
                                p10=p10_raw,
                                p50=p50_raw,
                                p90=p90_raw,
                            )
                            target_ts = now + (step_delta * step_index)
                            point = ForecastPoint(
                                run=run,
                                device=device,
                                metric_code=metric_code,
                                horizon=horizon,
                                target_ts=target_ts,
                                model_kind="sarima",
                                y_hat=y_hat,
                                p10=p10,
                                p50=p50,
                                p90=p90,
                                alpha=FORECAST_ALPHA,
                                labels={
                                    "freq": freq,
                                    "order": list(order),
                                    "seasonal_order": list(seasonal_order),
                                    "source": "sarima_baseline",
                                    "seasonality_mode": resolved_seasonality_mode,
                                    "seasonality_mode_label": seasonality_mode_label(resolved_seasonality_mode),
                                    "seasonal_component_added": seasonal_adjustment,
                                    "trend_delta_added": trend_delta,
                                    "forecast_step": int(step_index),
                                    "forecast_steps_total": int(steps),
                                    "trend_projection": {
                                        **trend_projection,
                                        "projected_trend_value": projected_trend_value,
                                    },
                                    "model_series": (
                                        "resampled"
                                        if resolved_seasonality_mode == SEASONALITY_MODE_SARIMA_SEASONAL
                                        else "stl_residual_plus_projected_trend_and_seasonal"
                                    ),
                                },
                            )
                            points_batch.append(point)
                            per_horizon_points[horizon].append(point)
                except Exception as metric_exc:
                    quality["metrics_skipped"] += 1
                    quality["errors"].append(f"{metric_code}: {metric_exc}")
                    continue

            if not points_batch:
                raise RuntimeError("SARIMA did not produce forecast points for any metric")

            if points_batch:
                ForecastPoint.objects.bulk_create(points_batch, batch_size=500)
                created_points += len(points_batch)

            if stl_components_batch:
                ComputedMetric.objects.bulk_create(stl_components_batch, batch_size=500)

            for horizon in horizons:
                state_risk_features = build_state_risk_features_for_points(
                    device=device,
                    horizon=horizon,
                    points=per_horizon_points[horizon],
                    source_model="sarima",
                    personalized_thresholds=True,
                    threshold_lookback_days=lookback_days,
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
                        evidence={"source": "sarima_baseline", **(state_result["evidence"] or {})},
                        timestamp=now,
                    )
                )
            if states_batch:
                StateEstimate.objects.bulk_create(states_batch, batch_size=100)
                created_states += len(states_batch)

            run.status = "success"
            run.finished_at = timezone.now()
            quality["points_created"] = len(points_batch)
            quality["states_created"] = len(states_batch)
            run.quality = quality
            run.save(update_fields=["status", "finished_at", "quality", "updated_at"])
        except Exception as exc:
            failed_runs += 1
            run.status = "failed"
            run.finished_at = timezone.now()
            quality["errors"].append(str(exc))
            run.quality = quality
            run.notes = f"{run.notes}\nError: {exc}"
            run.save(update_fields=["status", "finished_at", "quality", "notes", "updated_at"])

    return {
        "created_runs": created_runs,
        "created_points": created_points,
        "created_states": created_states,
        "failed_runs": failed_runs,
        "run_ids": run_ids,
    }
