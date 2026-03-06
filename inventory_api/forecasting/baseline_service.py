from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from inventory_api.forecasting.preprocess import (
    preprocess_points,
    horizon_to_steps,
    horizon_to_timedelta,
)
from inventory_api.forecasting.sarima_model import fit_sarima, forecast_with_intervals
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


THRESHOLDS = {
    "cpu_load_total": 90.0,
    "mem_usage_percent": 92.0,
    "ping_latency_gateway": 150.0,
    "system_temperature": 80.0,
    "storcli_drive_temperature": 58.0,
    "storcli_predictive_failure_count": 1.0,
}


FORECAST_ALPHA = 0.2


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


def _estimate_state(points_by_metric):
    if not points_by_metric:
        return "unknown", None, None, None, 0.0, {"reason": "no_points"}

    components = []
    for code, value in points_by_metric.items():
        thr = THRESHOLDS.get(code)
        if thr is None or value is None:
            continue
        ratio = float(value) / float(thr) if thr > 0 else 0.0
        risk_component = min(max((ratio - 0.75) / 0.75, 0.0), 1.0)
        components.append((code, value, thr, risk_component))

    if not components:
        return "unknown", None, None, None, 0.0, {"reason": "no_threshold_match"}

    components.sort(key=lambda item: item[3], reverse=True)
    risk = max(item[3] for item in components)

    p_s2 = min(max(risk, 0.0), 1.0)
    p_s1 = min((1.0 - p_s2) * 0.6, 1.0)
    p_s0 = max(0.0, 1.0 - p_s2 - p_s1)

    if p_s2 >= max(p_s1, p_s0):
        state = "s2"
    elif p_s1 >= max(p_s0, p_s2):
        state = "s1"
    else:
        state = "s0"

    confidence = min(0.95, 0.35 + 0.12 * len(components))
    evidence = {
        "top_components": [
            {"metric_code": c, "y_hat": float(v), "threshold": float(t), "risk_component": float(r)}
            for c, v, t, r in components[:4]
        ]
    }
    return state, p_s0, p_s1, p_s2, confidence, evidence


def run_baseline_forecasts(
    *,
    serial: str | None = None,
    lookback_days: int = 60,
    freq: str = "1h",
    horizons: list[str] | None = None,
    metric_codes: list[str] | None = None,
    save_stl_components: bool = True,
):
    _ensure_dependencies()

    now = timezone.now()
    horizons = horizons or ["24h", "7d", "30d"]
    metric_codes = metric_codes or list(DEFAULT_METRIC_CODES)

    devices_qs = Device.objects.all()
    if serial:
        devices_qs = devices_qs.filter(serial_number=serial)
    devices = list(devices_qs)
    if not devices:
        return {"created_runs": 0, "created_points": 0, "created_states": 0, "failed_runs": 0, "detail": "No devices found"}

    created_runs = 0
    created_points = 0
    created_states = 0
    failed_runs = 0

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
                "metric_codes": metric_codes,
                "preprocess": "stl_trend_plus_resid",
            },
            notes="Local baseline SARIMA forecast run",
        )
        created_runs += 1

        points_batch = []
        states_batch = []
        stl_components_batch = []
        per_horizon_values = {h: {} for h in horizons}
        quality = {"metrics_processed": 0, "metrics_skipped": 0, "errors": []}

        try:
            for metric_code in metric_codes:
                rows = list(
                    RawMetric.objects
                    .filter(device=device, code=metric_code, timestamp__gte=since)
                    .values_list("timestamp", "value")
                    .order_by("timestamp")
                )
                if len(rows) < 40:
                    quality["metrics_skipped"] += 1
                    continue

                pre = preprocess_points(rows, freq=freq, clip_quantile=0.01, max_points=1200)
                fitted, order, seasonal_order = fit_sarima(pre.cleaned, pre.seasonal_period)
                quality["metrics_processed"] += 1

                max_steps = max(horizon_to_steps(h, freq) for h in horizons)
                mean, lower, upper = forecast_with_intervals(fitted, steps=max_steps, alpha=FORECAST_ALPHA)

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
                    idx = steps - 1
                    if idx >= len(mean):
                        continue
                    y_hat, p10, p50, p90 = _sanitize_prediction(
                        metric_code=metric_code,
                        y_hat=float(mean.iloc[idx]),
                        p10=float(lower.iloc[idx]),
                        p50=float(mean.iloc[idx]),
                        p90=float(upper.iloc[idx]),
                    )
                    target_ts = now + horizon_to_timedelta(horizon)
                    per_horizon_values[horizon][metric_code] = y_hat
                    points_batch.append(
                        ForecastPoint(
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
                            },
                        )
                    )

            if points_batch:
                ForecastPoint.objects.bulk_create(points_batch, batch_size=500)
                created_points += len(points_batch)

            if stl_components_batch:
                ComputedMetric.objects.bulk_create(stl_components_batch, batch_size=500)

            for horizon in horizons:
                state, p_s0, p_s1, p_s2, conf, evidence = _estimate_state(per_horizon_values[horizon])
                states_batch.append(
                    StateEstimate(
                        run=run,
                        device=device,
                        horizon=horizon,
                        state=state,
                        p_s0=p_s0,
                        p_s1=p_s1,
                        p_s2=p_s2,
                        confidence=conf,
                        evidence=evidence,
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
    }
