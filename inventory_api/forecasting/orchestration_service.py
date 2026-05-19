from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import json
import math
import os

from django.db import transaction
from django.utils import timezone

from inventory_api.forecasting.baseline_service import (
    DEFAULT_METRIC_CODES,
    FORECAST_ALPHA,
    _sanitize_prediction,
    project_recent_trend_adjustment,
    project_repeating_seasonality,
    run_baseline_forecasts,
)
from inventory_api.forecasting.lstm_remote_service import (
    poll_lstm_remote_runs,
    run_lstm_remote_forecasts,
)
from inventory_api.forecasting.preprocess import horizon_to_steps, preprocess_points
from inventory_api.forecasting.risk_assessment_service import (
    build_state_risk_features_for_points,
)
from inventory_api.forecasting.state_inference_service import (
    FORECAST_ALPHA_MODE_MANUAL,
    get_active_state_inference_profile_config,
    get_orchestrator_controls_config,
    get_metric_forecast_control,
    infer_state_distribution,
    resolve_metric_codes_for_source,
)
from inventory_api.models import ForecastPoint, ForecastRun, RawMetric, StateEstimate


ORCHESTRATOR_KIND = "sarima_lstm"
DEFAULT_ENSEMBLE_WEIGHTS = {
    "sarima": 0.5,
    "lstm": 0.5,
}
ENSEMBLE_DISAGREEMENT_BETA = 0.5
ENSEMBLE_WINNER_MARGIN = 1.2
ENSEMBLE_WINNER_WEIGHT = 0.85
ALPHA_AUTO_EPS = 1e-6
ALPHA_HISTORY_LIMIT = 18
ALPHA_MATCH_WINDOW_FALLBACK = timedelta(hours=2)


def _env_float(name: str, default: float):
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _default_ensemble_beta():
    return max(0.0, _env_float("FORECAST_ENSEMBLE_BETA", ENSEMBLE_DISAGREEMENT_BETA))


def _default_ensemble_winner_margin():
    return max(1.0, _env_float("FORECAST_ENSEMBLE_WINNER_MARGIN", ENSEMBLE_WINNER_MARGIN))


def _default_ensemble_winner_weight():
    return max(0.5, min(1.0, _env_float("FORECAST_ENSEMBLE_WINNER_WEIGHT", ENSEMBLE_WINNER_WEIGHT)))


def _default_ensemble_weights():
    sarima_default = _env_float("FORECAST_ENSEMBLE_DEFAULT_SARIMA_WEIGHT", DEFAULT_ENSEMBLE_WEIGHTS["sarima"])
    lstm_default = _env_float("FORECAST_ENSEMBLE_DEFAULT_LSTM_WEIGHT", DEFAULT_ENSEMBLE_WEIGHTS["lstm"])
    return _normalize_weights({
        "sarima": sarima_default,
        "lstm": lstm_default,
    })


def _normalize_weights(weights: dict | None = None):
    raw = dict(DEFAULT_ENSEMBLE_WEIGHTS)
    if isinstance(weights, dict):
        raw.update(weights)

    sarima_weight = max(0.0, float(raw.get("sarima", 0.5) or 0.0))
    lstm_weight = max(0.0, float(raw.get("lstm", 0.5) or 0.0))
    total = sarima_weight + lstm_weight
    if total <= 0:
        return dict(DEFAULT_ENSEMBLE_WEIGHTS)
    return {
        "sarima": sarima_weight / total,
        "lstm": lstm_weight / total,
    }


def _runs_by_device(run_ids: list[int] | None):
    rows = (
        ForecastRun.objects
        .filter(id__in=list(run_ids or []))
        .select_related("device")
    )
    return {row.device_id: row for row in rows}


def _merge_numeric(sarima_value, lstm_value, *, weights: dict[str, float]):
    if sarima_value is None and lstm_value is None:
        return None
    if sarima_value is None:
        return float(lstm_value)
    if lstm_value is None:
        return float(sarima_value)
    return float(sarima_value) * float(weights["sarima"]) + float(lstm_value) * float(weights["lstm"])


def _interval_half_width(point):
    if point is None:
        return None
    p10 = getattr(point, "p10", None)
    p90 = getattr(point, "p90", None)
    if p10 is None or p90 is None:
        return None
    return max(0.0, (float(p90) - float(p10)) / 2.0)


def _freq_to_timedelta(freq: str | None):
    raw = str(freq or "").strip().lower()
    if raw.endswith("min"):
        return timedelta(minutes=int(raw[:-3]))
    if raw.endswith("h"):
        return timedelta(hours=int(raw[:-1]))
    if raw.endswith("d"):
        return timedelta(days=int(raw[:-1]))
    return ALPHA_MATCH_WINDOW_FALLBACK


def _point_match_window(point):
    if point is None:
        return ALPHA_MATCH_WINDOW_FALLBACK
    freq = None
    labels = getattr(point, "labels", None)
    if isinstance(labels, dict):
        freq = labels.get("freq")
    if not freq and getattr(point, "run", None) is not None:
        params = getattr(point.run, "parameters", None)
        if isinstance(params, dict):
            freq = params.get("freq")
    base = _freq_to_timedelta(freq)
    return max(ALPHA_MATCH_WINDOW_FALLBACK, base * 2)


def _forecast_step_from_point(point):
    if point is None:
        return None
    labels = getattr(point, "labels", None)
    if isinstance(labels, dict):
        try:
            step = int(labels.get("forecast_step"))
        except (TypeError, ValueError):
            step = None
        if step is not None and step > 0:
            return int(step)
    return None


def _orchestrator_segment_boundaries(orchestrator_controls: dict | None):
    raw = (orchestrator_controls or {}).get("segment_boundaries_hours")
    if not isinstance(raw, (list, tuple)):
        raw = [24, 168, 720]
    out = []
    for item in raw:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            out.append(parsed)
    out = sorted(set(out))
    return out if len(out) >= 2 else [24, 168, 720]


def _segment_key_from_offset_hours(offset_hours: float | None, orchestrator_controls: dict | None):
    if offset_hours is None:
        return "all"
    boundaries = _orchestrator_segment_boundaries(orchestrator_controls)
    lower = 0
    for upper in boundaries:
        if float(offset_hours) <= float(upper):
            return f"{int(lower)}_{int(upper)}h"
        lower = upper
    return f"{int(boundaries[-1])}_plus"


def _segment_key_for_point(point, orchestrator_controls: dict | None):
    if point is None:
        return "all"
    forecast_step = _forecast_step_from_point(point)
    if forecast_step is None:
        return "all"
    freq = None
    labels = getattr(point, "labels", None)
    if isinstance(labels, dict):
        freq = labels.get("freq")
    if not freq and getattr(point, "run", None) is not None:
        params = getattr(point.run, "parameters", None)
        if isinstance(params, dict):
            freq = params.get("freq")
    freq_td = _freq_to_timedelta(freq)
    offset_hours = float(forecast_step) * (float(freq_td.total_seconds()) / 3600.0)
    return _segment_key_from_offset_hours(offset_hours, orchestrator_controls)


def _relevant_run_signature_payload(run):
    if run is None:
        return {}
    params = getattr(run, "parameters", None) or {}
    quality = getattr(run, "quality", None) or {}
    model_kind = str(getattr(run, "model_kind", "") or "").strip().lower()
    if model_kind == "sarima":
        return {
            "model_kind": "sarima",
            "freq": params.get("freq"),
            "preprocess": params.get("preprocess"),
            "seasonality_mode": params.get("seasonality_mode"),
            "lookback_days": params.get("lookback_days"),
        }
    if model_kind == "lstm":
        remote_options = params.get("remote_model_options") if isinstance(params.get("remote_model_options"), dict) else {}
        remote_quality = quality.get("remote_quality") if isinstance(quality.get("remote_quality"), dict) else {}
        model_version = remote_quality.get("model_version")
        return {
            "model_kind": "lstm",
            "freq": params.get("freq"),
            "lookback_days": params.get("lookback_days"),
            "model_version": model_version,
            "remote_model_options": {
                "lookback": remote_options.get("lookback"),
                "epochs": remote_options.get("epochs"),
                "hidden_size": remote_options.get("hidden_size"),
                "loss_kind": remote_options.get("loss_kind"),
                "output_mode": remote_options.get("output_mode"),
                "target_mode": remote_options.get("target_mode"),
                "seasonality_mode": remote_options.get("seasonality_mode"),
                "seasonality_window_days": remote_options.get("seasonality_window_days"),
                "use_calendar_features": remote_options.get("use_calendar_features"),
                "use_seasonal_residual": remote_options.get("use_seasonal_residual"),
                "recency_weighted_loss": remote_options.get("recency_weighted_loss"),
                "train_mode": remote_options.get("train_mode"),
                "forecast_stride": remote_options.get("forecast_stride"),
                "lags": remote_options.get("lags"),
            },
        }
    return {
        "model_kind": model_kind,
        "parameters": params,
    }


def _run_generation_signature(run):
    payload = _relevant_run_signature_payload(run)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _compatible_history_run_ids(
    *,
    device,
    model_kind: str,
    current_point,
    orchestrator_controls: dict | None = None,
    exclude_run_ids: set[int] | None = None,
):
    controls = dict(orchestrator_controls or {})
    if not bool(controls.get("alpha_version_aware", True)):
        return None, None
    current_run = getattr(current_point, "run", None)
    if current_run is None:
        return None, None

    signature = _run_generation_signature(current_run)
    limit = max(1, int((controls or {}).get("compatible_history_runs") or 6))
    exclude_ids = set(exclude_run_ids or set())
    run_ids = []
    qs = (
        ForecastRun.objects
        .filter(device=device, model_kind=model_kind, status="success")
        .order_by("-created_at", "-id")
    )
    for row in qs:
        if row.id in exclude_ids:
            continue
        if _run_generation_signature(row) != signature:
            continue
        run_ids.append(int(row.id))
        if len(run_ids) >= limit:
            break
    return set(run_ids), signature


def _metric_error_scale(
    *,
    device,
    metric_code: str,
    reference_ts,
    orchestrator_controls: dict | None = None,
):
    controls = dict(orchestrator_controls or {})
    lookback_days = max(1, int(controls.get("error_scale_lookback_days") or 60))
    ref_ts = reference_ts or timezone.now()
    since = ref_ts - timedelta(days=lookback_days)
    values = list(
        RawMetric.objects
        .filter(device=device, code=metric_code, timestamp__gte=since, timestamp__lte=ref_ts)
        .order_by("timestamp")
        .values_list("value", flat=True)[:5000]
    )
    parsed_values = []
    for raw in values:
        try:
            parsed_values.append(float(raw))
        except (TypeError, ValueError):
            continue
    if len(parsed_values) < 2:
        return 1.0

    diffs = [abs(parsed_values[idx] - parsed_values[idx - 1]) for idx in range(1, len(parsed_values))]
    mean_abs_diff = (sum(diffs) / len(diffs)) if diffs else 0.0
    mean_level = sum(abs(item) for item in parsed_values) / max(1, len(parsed_values))
    scale = max(float(mean_abs_diff), float(mean_level) * 0.05, 1e-3)
    return float(scale)


def _point_time_bucket(point):
    if point is None:
        return None
    target_ts = getattr(point, "target_ts", None)
    if target_ts is None:
        return None

    freq = None
    labels = getattr(point, "labels", None)
    if isinstance(labels, dict):
        freq = labels.get("freq")
    if not freq and getattr(point, "run", None) is not None:
        params = getattr(point.run, "parameters", None)
        if isinstance(params, dict):
            freq = params.get("freq")

    step_td = _freq_to_timedelta(freq)
    step_seconds = int(step_td.total_seconds()) if step_td else 0
    if step_seconds <= 0:
        step_seconds = int(ALPHA_MATCH_WINDOW_FALLBACK.total_seconds())
    step_seconds = max(60, step_seconds)
    return int(round(float(target_ts.timestamp()) / float(step_seconds)))


def _point_merge_key(point):
    if point is None:
        return None
    metric_code = str(getattr(point, "metric_code", "") or "").strip()
    horizon = str(getattr(point, "horizon", "") or "").strip()
    if not metric_code or not horizon:
        return None
    labels = getattr(point, "labels", None)
    if isinstance(labels, dict):
        try:
            forecast_step = int(labels.get("forecast_step"))
        except (TypeError, ValueError):
            forecast_step = None
        if forecast_step is not None and forecast_step > 0:
            return metric_code, horizon, int(forecast_step)
    bucket = _point_time_bucket(point)
    if bucket is None:
        fallback_step = None
        if isinstance(labels, dict):
            try:
                fallback_step = int(labels.get("forecast_step"))
            except (TypeError, ValueError):
                fallback_step = None
        if fallback_step is None:
            fallback_step = int(getattr(point, "id", 0) or 0)
        bucket = int(fallback_step)
    return metric_code, horizon, int(bucket)


def _point_order_key(point):
    target_ts = getattr(point, "target_ts", None)
    ts_value = float(target_ts.timestamp()) if target_ts is not None else 0.0
    point_id = int(getattr(point, "id", 0) or 0)
    return ts_value, point_id


def _build_point_map(points):
    grouped = defaultdict(list)
    for row in points:
        metric_code = str(getattr(row, "metric_code", "") or "").strip()
        horizon = str(getattr(row, "horizon", "") or "").strip()
        if not metric_code or not horizon:
            continue
        grouped[(metric_code, horizon)].append(row)

    point_map = {}
    for (metric_code, horizon), rows in grouped.items():
        rows = sorted(rows, key=_point_order_key)
        for idx, row in enumerate(rows, start=1):
            labels = getattr(row, "labels", None)
            forecast_step = None
            if isinstance(labels, dict):
                try:
                    forecast_step = int(labels.get("forecast_step"))
                except (TypeError, ValueError):
                    forecast_step = None
            if forecast_step is None or forecast_step <= 0:
                forecast_step = idx
            key = (metric_code, horizon, int(forecast_step))
            existing = point_map.get(key)
            if existing is None or _point_order_key(row) >= _point_order_key(existing):
                point_map[key] = row
    return point_map


def _build_metric_alpha_sources(all_keys, sarima_map, lstm_map, *, orchestrator_controls: dict | None = None):
    per_metric_horizon_keys = defaultdict(list)
    for metric_code, horizon, bucket in all_keys:
        point = sarima_map.get((metric_code, horizon, bucket)) or lstm_map.get((metric_code, horizon, bucket))
        segment_key = _segment_key_for_point(point, orchestrator_controls)
        per_metric_horizon_keys[(metric_code, horizon, segment_key)].append((metric_code, horizon, bucket))

    out = {}
    for metric_horizon_key, metric_keys in per_metric_horizon_keys.items():
        paired = None
        first_sarima = None
        first_lstm = None
        for key in metric_keys:
            sarima_point = sarima_map.get(key)
            lstm_point = lstm_map.get(key)
            if sarima_point is not None and first_sarima is None:
                first_sarima = sarima_point
            if lstm_point is not None and first_lstm is None:
                first_lstm = lstm_point
            if sarima_point is not None and lstm_point is not None:
                paired = (sarima_point, lstm_point)
                break
        if paired is not None:
            out[metric_horizon_key] = paired
        else:
            out[metric_horizon_key] = (first_sarima, first_lstm)
    return out


def _lookup_actual_value(device, metric_code: str, target_ts, tolerance: timedelta):
    rows = list(
        RawMetric.objects
        .filter(
            device=device,
            code=metric_code,
            timestamp__gte=target_ts - tolerance,
            timestamp__lte=target_ts + tolerance,
        )
        .values_list("timestamp", "value")
        .order_by("timestamp")
    )
    if not rows:
        return None

    best_ts = None
    best_value = None
    best_delta = None
    for ts, value in rows:
        delta = abs((ts - target_ts).total_seconds())
        if best_delta is None or delta < best_delta:
            best_ts = ts
            best_value = float(value)
            best_delta = delta
    if best_ts is None:
        return None
    return best_value


def _recent_model_errors(
    *,
    device,
    metric_code: str,
    horizon: str | None,
    model_kind: str,
    current_point,
    segment_key: str | None = None,
    orchestrator_controls: dict | None = None,
    exclude_run_ids: set[int] | None = None,
    limit: int = ALPHA_HISTORY_LIMIT,
):
    exclude_ids = set(exclude_run_ids or set())
    compatible_run_ids, generation_signature = _compatible_history_run_ids(
        device=device,
        model_kind=model_kind,
        current_point=current_point,
        orchestrator_controls=orchestrator_controls,
        exclude_run_ids=exclude_ids,
    )
    if compatible_run_ids is not None and not compatible_run_ids:
        return {
            "errors": [],
            "segment_key": segment_key or "all",
            "compatible_run_ids": [],
            "generation_signature": generation_signature,
        }

    qs = (
        ForecastPoint.objects
        .filter(
            device=device,
            metric_code=metric_code,
            model_kind=model_kind,
            run__status="success",
            target_ts__lte=timezone.now(),
        )
        .select_related("run")
        .order_by("-target_ts", "-id")
    )
    if horizon:
        qs = qs.filter(horizon=horizon)
    if compatible_run_ids is not None:
        qs = qs.filter(run_id__in=list(compatible_run_ids))
    errors = []
    cache = {}
    for point in qs:
        if point.run_id in exclude_ids:
            continue
        if segment_key and segment_key != "all":
            historical_segment = _segment_key_for_point(point, orchestrator_controls)
            if historical_segment != segment_key:
                continue
        tolerance = _point_match_window(point)
        cache_key = (point.metric_code, point.target_ts, tolerance)
        if cache_key not in cache:
            cache[cache_key] = _lookup_actual_value(device, metric_code, point.target_ts, tolerance)
        actual = cache[cache_key]
        if actual is None:
            continue
        errors.append(abs(float(actual) - float(point.y_hat)))
        if len(errors) >= max(1, int(limit)):
            break
    return {
        "errors": errors,
        "segment_key": segment_key or "all",
        "compatible_run_ids": sorted(int(item) for item in (compatible_run_ids or [])),
        "generation_signature": generation_signature,
    }


def _source_reliability(
    *,
    device,
    metric_code: str,
    horizon: str | None,
    model_kind: str,
    current_point,
    orchestrator_controls: dict | None = None,
    exclude_run_ids: set[int] | None = None,
):
    controls = dict(orchestrator_controls or {})
    segment_key = _segment_key_for_point(current_point, controls)
    history_limit = max(1, int(controls.get("history_limit_per_segment") or ALPHA_HISTORY_LIMIT))
    error_scale = _metric_error_scale(
        device=device,
        metric_code=metric_code,
        reference_ts=getattr(current_point, "target_ts", None),
        orchestrator_controls=controls,
    )
    history = _recent_model_errors(
        device=device,
        metric_code=metric_code,
        horizon=horizon,
        model_kind=model_kind,
        current_point=current_point,
        segment_key=segment_key,
        orchestrator_controls=controls,
        exclude_run_ids=exclude_run_ids,
        limit=history_limit,
    )
    errors = list(history.get("errors") or [])
    if errors:
        mae = sum(errors) / len(errors)
        normalized_errors = [float(item) / max(ALPHA_AUTO_EPS, float(error_scale)) for item in errors]
        normalized_mae = sum(normalized_errors) / len(normalized_errors)
        score_base = normalized_mae if bool(controls.get("normalize_errors_by_scale", True)) else mae
        return {
            "score": 1.0 / (float(score_base) + ALPHA_AUTO_EPS),
            "mode": "historical_segment_error",
            "mae": float(mae),
            "normalized_mae": float(normalized_mae),
            "error_scale": float(error_scale),
            "samples": len(errors),
            "segment_key": segment_key,
            "generation_signature": history.get("generation_signature"),
            "compatible_run_ids": history.get("compatible_run_ids") or [],
        }

    width = _interval_half_width(current_point)
    if width is not None and width > 0:
        return {
            "score": 1.0 / (float(width) + ALPHA_AUTO_EPS),
            "mode": "interval_width_proxy",
            "mae": None,
            "normalized_mae": None,
            "error_scale": float(error_scale),
            "samples": 0,
            "interval_half_width": float(width),
            "segment_key": segment_key,
            "generation_signature": history.get("generation_signature"),
            "compatible_run_ids": history.get("compatible_run_ids") or [],
        }

    if current_point is not None:
        return {
            "score": 1.0,
            "mode": "presence_fallback",
            "mae": None,
            "normalized_mae": None,
            "error_scale": float(error_scale),
            "samples": 0,
            "segment_key": segment_key,
            "generation_signature": history.get("generation_signature"),
            "compatible_run_ids": history.get("compatible_run_ids") or [],
        }

    return {
        "score": 0.0,
        "mode": "missing",
        "mae": None,
        "normalized_mae": None,
        "error_scale": float(error_scale),
        "samples": 0,
        "segment_key": segment_key,
        "generation_signature": history.get("generation_signature"),
        "compatible_run_ids": history.get("compatible_run_ids") or [],
    }


def _forecast_target_proxy(device, metric_code: str, point) -> dict | None:
    if point is None or not getattr(point, "horizon", None):
        return None

    freq = None
    labels = getattr(point, "labels", None)
    if isinstance(labels, dict):
        freq = labels.get("freq")
    if not freq and getattr(point, "run", None) is not None:
        params = getattr(point.run, "parameters", None)
        if isinstance(params, dict):
            freq = params.get("freq")
    freq = str(freq or "1h")

    now = timezone.now()
    since = now - timedelta(days=60)
    rows = list(
        RawMetric.objects
        .filter(device=device, code=metric_code, timestamp__gte=since, timestamp__lte=now)
        .values_list("timestamp", "value")
        .order_by("timestamp")
    )
    if len(rows) < 40:
        return None

    try:
        pre = preprocess_points(rows, freq=freq, clip_quantile=0.01, max_points=1200)
        steps = horizon_to_steps(str(point.horizon), freq)
        idx = steps - 1
        if idx < 0:
            return None
        future_trend_delta, trend_projection = project_recent_trend_adjustment(pre, steps=steps)
        future_seasonality = project_repeating_seasonality(pre, steps=steps)
        trend_series = pre.trend.dropna().astype(float)
        if trend_series.empty:
            return None
        projected_trend_value = float(trend_series.iloc[-1]) + float(future_trend_delta[idx])
        target_value = projected_trend_value + float(future_seasonality[idx])
        return {
            "target": float(target_value),
            "freq": freq,
            "steps": int(steps),
            "trend_projection": {
                **trend_projection,
                "projected_trend_value": projected_trend_value,
            },
        }
    except Exception:
        return None


def _metric_alpha_for_device(
    *,
    device,
    metric_code: str,
    horizon: str | None,
    sarima_point,
    lstm_point,
    orchestrator_controls: dict | None = None,
    exclude_run_ids: set[int] | None = None,
    default_alpha_sarima: float = 0.5,
    metric_control: dict | None = None,
):
    control = dict(metric_control or {})
    orchestrator_control = dict(orchestrator_controls or {})
    if sarima_point is not None and lstm_point is None:
        return 1.0, {
            "selection_method": "sarima_only",
            "sarima": {"score": 1.0, "mode": "sarima_only"},
            "lstm": {"score": 0.0, "mode": "missing"},
            "control": control,
            "orchestrator_control": orchestrator_control,
        }
    if lstm_point is not None and sarima_point is None:
        return 0.0, {
            "selection_method": "lstm_only",
            "sarima": {"score": 0.0, "mode": "missing"},
            "lstm": {"score": 1.0, "mode": "lstm_only"},
            "control": control,
            "orchestrator_control": orchestrator_control,
        }

    if control.get("alpha_mode") == FORECAST_ALPHA_MODE_MANUAL:
        alpha = float(max(0.0, min(1.0, float(control.get("manual_alpha_sarima", default_alpha_sarima)))))
        return alpha, {
            "selection_method": "manual_profile_override",
            "sarima": {"score": None, "mode": "manual_override"},
            "lstm": {"score": None, "mode": "manual_override"},
            "control": control,
            "orchestrator_control": orchestrator_control,
        }

    sarima_rel = _source_reliability(
        device=device,
        metric_code=metric_code,
        horizon=horizon,
        model_kind="sarima",
        current_point=sarima_point,
        orchestrator_controls=orchestrator_control,
        exclude_run_ids=exclude_run_ids,
    )
    lstm_rel = _source_reliability(
        device=device,
        metric_code=metric_code,
        horizon=horizon,
        model_kind="lstm",
        current_point=lstm_point,
        orchestrator_controls=orchestrator_control,
        exclude_run_ids=exclude_run_ids,
    )

    sarima_score = float(sarima_rel.get("score", 0.0) or 0.0)
    lstm_score = float(lstm_rel.get("score", 0.0) or 0.0)
    has_historical_error = (
        sarima_rel.get("mode") == "historical_segment_error"
        or lstm_rel.get("mode") == "historical_segment_error"
    )
    if not has_historical_error:
        proxy = _forecast_target_proxy(
            device=device,
            metric_code=metric_code,
            point=sarima_point or lstm_point,
        )
        if proxy is not None:
            proxy_target = float(proxy["target"])
            sarima_proxy_score = 1.0 / (abs(float(getattr(sarima_point, "y_hat", 0.0)) - proxy_target) + ALPHA_AUTO_EPS)
            lstm_proxy_score = 1.0 / (abs(float(getattr(lstm_point, "y_hat", 0.0)) - proxy_target) + ALPHA_AUTO_EPS)
            total_proxy = sarima_proxy_score + lstm_proxy_score
            if total_proxy > 0:
                alpha = sarima_proxy_score / total_proxy
                return float(max(0.0, min(1.0, alpha))), {
                    "selection_method": "trend_proxy",
                    "sarima": {**sarima_rel, "proxy_score": float(sarima_proxy_score)},
                    "lstm": {**lstm_rel, "proxy_score": float(lstm_proxy_score)},
                    "proxy": proxy,
                    "control": control,
                    "orchestrator_control": orchestrator_control,
                }

    total_score = sarima_score + lstm_score
    if total_score <= 0 or not has_historical_error:
        alpha = float(max(0.0, min(1.0, default_alpha_sarima)))
        selection_method = "default_prior"
    else:
        winner_margin = float(orchestrator_control.get("winner_margin") or _default_ensemble_winner_margin())
        winner_weight = float(orchestrator_control.get("winner_weight") or _default_ensemble_winner_weight())
        if sarima_score > 0 and sarima_score >= (lstm_score * winner_margin):
            alpha = float(winner_weight)
            selection_method = "winner_bias_recent_compatible_error"
        elif lstm_score > 0 and lstm_score >= (sarima_score * winner_margin):
            alpha = float(1.0 - winner_weight)
            selection_method = "winner_bias_recent_compatible_error"
        else:
            alpha = sarima_score / total_score
            selection_method = "automatic_segment_weight"

    return float(max(0.0, min(1.0, alpha))), {
        "selection_method": selection_method,
        "sarima": sarima_rel,
        "lstm": lstm_rel,
        "control": control,
        "orchestrator_control": orchestrator_control,
    }


def _build_ensemble_prediction(
    *,
    metric_code: str,
    horizon: str | None,
    sarima_point,
    lstm_point,
    alpha_sarima: float,
    disagreement_beta: float,
    alpha_evidence: dict | None = None,
):
    y_s = getattr(sarima_point, "y_hat", None)
    y_l = getattr(lstm_point, "y_hat", None)
    weights = {
        "sarima": float(max(0.0, min(1.0, alpha_sarima))),
        "lstm": float(max(0.0, min(1.0, 1.0 - alpha_sarima))),
    }
    point_aggregation_method = "weighted_average"
    point_source = "blend"
    if y_s is None and y_l is not None:
        y_e = float(y_l)
        point_source = "lstm"
        point_aggregation_method = "single_source_passthrough"
    elif y_l is None and y_s is not None:
        y_e = float(y_s)
        point_source = "sarima"
        point_aggregation_method = "single_source_passthrough"
    else:
        y_e = _merge_numeric(y_s, y_l, weights=weights)
    if y_e is None:
        return None

    u_s = _interval_half_width(sarima_point)
    u_l = _interval_half_width(lstm_point)
    if u_s is None and sarima_point is not None and y_s is not None:
        u_s = 0.0
    if u_l is None and lstm_point is not None and y_l is not None:
        u_l = 0.0

    if y_s is not None and y_l is not None and weights["sarima"] > 0.0 and weights["lstm"] > 0.0:
        disagreement = float(max(0.0, disagreement_beta)) * abs(float(y_s) - float(y_l))
    else:
        disagreement = 0.0

    if y_s is None:
        u_e = float(u_l or 0.0)
    elif y_l is None:
        u_e = float(u_s or 0.0)
    else:
        u_e = math.sqrt(
            ((float(weights["sarima"]) * float(u_s or 0.0)) ** 2)
            + ((float(weights["lstm"]) * float(u_l or 0.0)) ** 2)
            + (float(disagreement) ** 2)
        )

    p10 = float(y_e) - float(u_e)
    p50 = float(y_e)
    p90 = float(y_e) + float(u_e)
    y_hat, p10, p50, p90 = _sanitize_prediction(
        metric_code=metric_code,
        y_hat=float(y_e),
        p10=p10,
        p50=p50,
        p90=p90,
    )

    return {
        "y_hat": y_hat,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "alpha": float(weights["sarima"]),
        "u_s": None if u_s is None else float(u_s),
        "u_l": None if u_l is None else float(u_l),
        "u_e": float(max(0.0, u_e)),
        "disagreement": float(max(0.0, disagreement)),
        "interval_alpha": float(FORECAST_ALPHA),
        "point_aggregation_method": point_aggregation_method,
        "point_source": point_source,
    }


def _ensemble_run_queryset():
    return ForecastRun.objects.filter(model_kind="ensemble", parameters__orchestrator_kind=ORCHESTRATOR_KIND)


def build_ensemble_run_for_sources(
    *,
    sarima_run: ForecastRun,
    lstm_run: ForecastRun,
    weights: dict | None = None,
    disagreement_beta: float | None = None,
):
    if sarima_run.device_id != lstm_run.device_id:
        raise RuntimeError("SARIMA and LSTM runs belong to different devices")
    if sarima_run.status != "success":
        raise RuntimeError("SARIMA run is not successful yet")
    if lstm_run.status != "success":
        raise RuntimeError("LSTM run is not successful yet")

    device = sarima_run.device
    profile_config = get_active_state_inference_profile_config()
    orchestrator_controls = get_orchestrator_controls_config(config=profile_config)
    allowed_sarima_codes = set(resolve_metric_codes_for_source("sarima", config=profile_config))
    allowed_lstm_codes = set(resolve_metric_codes_for_source("lstm", config=profile_config))
    weights = _normalize_weights(weights or _default_ensemble_weights())
    disagreement_beta = float(_default_ensemble_beta() if disagreement_beta is None else max(0.0, disagreement_beta))
    existing = (
        _ensemble_run_queryset()
        .filter(
            device=device,
            parameters__sarima_run_id=sarima_run.id,
            parameters__lstm_run_id=lstm_run.id,
        )
        .order_by("-created_at")
        .first()
    )
    if existing and ForecastPoint.objects.filter(run=existing).exists():
        return existing, False, {
            "points_created": ForecastPoint.objects.filter(run=existing).count(),
            "states_created": StateEstimate.objects.filter(run=existing).count(),
        }

    sarima_points = [
        row for row in ForecastPoint.objects.filter(run=sarima_run).order_by("metric_code", "horizon", "target_ts", "id")
        if row.metric_code in allowed_sarima_codes
    ]
    lstm_points = [
        row for row in ForecastPoint.objects.filter(run=lstm_run).order_by("metric_code", "horizon", "target_ts", "id")
        if row.metric_code in allowed_lstm_codes
    ]
    if not sarima_points and not lstm_points:
        raise RuntimeError("No source forecast points to build ensemble")

    sarima_map = _build_point_map(sarima_points)
    lstm_map = _build_point_map(lstm_points)
    all_keys = sorted(set(sarima_map.keys()) | set(lstm_map.keys()))
    alpha_sources_by_metric = _build_metric_alpha_sources(
        all_keys,
        sarima_map,
        lstm_map,
        orchestrator_controls=orchestrator_controls,
    )
    horizon_point_totals = defaultdict(int)
    for metric_code, horizon, _bucket in all_keys:
        horizon_point_totals[(metric_code, horizon)] += 1
    now = timezone.now()

    run = ForecastRun.objects.create(
        device=device,
        model_kind="ensemble",
        horizon_set=str(sarima_run.horizon_set or lstm_run.horizon_set or "24h,7d,30d"),
        status="running",
        started_at=now,
        parameters={
            "orchestrator_kind": ORCHESTRATOR_KIND,
            "sarima_run_id": sarima_run.id,
            "lstm_run_id": lstm_run.id,
            "weights": weights,
            "ensemble_beta": disagreement_beta,
            "orchestrator_controls": orchestrator_controls,
        },
        quality={},
        notes="Ensemble forecast run from SARIMA + LSTM",
    )

    points_batch = []
    states_batch = []
    per_horizon_points = defaultdict(list)
    source_counts = {"blended": 0, "sarima_only": 0, "lstm_only": 0}
    uncertainty_stats = {
        "sum_width": 0.0,
        "sum_disagreement": 0.0,
        "max_width": 0.0,
        "max_disagreement": 0.0,
    }
    alpha_by_metric_horizon = {}
    current_run_ids = {sarima_run.id, lstm_run.id}

    step_counters = defaultdict(int)
    for metric_code, horizon, _bucket in all_keys:
        sarima_point = sarima_map.get((metric_code, horizon, _bucket))
        lstm_point = lstm_map.get((metric_code, horizon, _bucket))
        if not sarima_point and not lstm_point:
            continue

        current_reference_point = sarima_point or lstm_point
        segment_key = _segment_key_for_point(current_reference_point, orchestrator_controls)
        alpha_key = (metric_code, horizon, segment_key)
        if alpha_key not in alpha_by_metric_horizon:
            metric_control = get_metric_forecast_control(metric_code, config=profile_config)
            alpha_source_sarima, alpha_source_lstm = alpha_sources_by_metric.get(alpha_key, (sarima_point, lstm_point))
            metric_alpha, alpha_evidence = _metric_alpha_for_device(
                device=device,
                metric_code=metric_code,
                horizon=horizon,
                sarima_point=alpha_source_sarima,
                lstm_point=alpha_source_lstm,
                orchestrator_controls=orchestrator_controls,
                exclude_run_ids=current_run_ids,
                default_alpha_sarima=float(weights["sarima"]),
                metric_control=metric_control,
            )
            alpha_by_metric_horizon[alpha_key] = {
                "alpha": metric_alpha,
                "evidence": alpha_evidence,
                "control": metric_control,
            }
        metric_alpha = float(alpha_by_metric_horizon[alpha_key]["alpha"])
        alpha_evidence = alpha_by_metric_horizon[alpha_key]["evidence"]

        target_candidates = [item.target_ts for item in (sarima_point, lstm_point) if item and item.target_ts]
        target_ts = max(target_candidates) if target_candidates else now

        if sarima_point and lstm_point:
            source_mode = "blended"
        elif sarima_point:
            source_mode = "sarima_only"
        else:
            source_mode = "lstm_only"
        source_counts[source_mode] += 1

        ensemble_prediction = _build_ensemble_prediction(
            metric_code=metric_code,
            horizon=horizon,
            sarima_point=sarima_point,
            lstm_point=lstm_point,
            alpha_sarima=metric_alpha,
            disagreement_beta=disagreement_beta,
            alpha_evidence=alpha_evidence,
        )
        if ensemble_prediction is None:
            continue

        y_hat = float(ensemble_prediction["y_hat"])
        p10 = float(ensemble_prediction["p10"])
        p50 = float(ensemble_prediction["p50"])
        p90 = float(ensemble_prediction["p90"])
        interval_width = max(0.0, p90 - p10)
        disagreement = float(ensemble_prediction["disagreement"])
        uncertainty_stats["sum_width"] += interval_width
        uncertainty_stats["sum_disagreement"] += disagreement
        uncertainty_stats["max_width"] = max(uncertainty_stats["max_width"], interval_width)
        uncertainty_stats["max_disagreement"] = max(uncertainty_stats["max_disagreement"], disagreement)
        step_counters[(metric_code, horizon)] += 1
        step_index = int(step_counters[(metric_code, horizon)])

        labels = {
            "source": "sarima_lstm_ensemble",
            "source_mode": source_mode,
            "sarima_run_id": sarima_run.id,
            "lstm_run_id": lstm_run.id,
            "forecast_step": step_index,
            "forecast_steps_total": int(horizon_point_totals[(metric_code, horizon)]),
            "weights": {
                "sarima": metric_alpha,
                "lstm": 1.0 - metric_alpha,
            },
            "segment_key": segment_key,
            "alpha_weight_sarima": metric_alpha,
            "alpha_weight_lstm": 1.0 - metric_alpha,
            "alpha_selection": alpha_evidence,
            "point_aggregation_method": ensemble_prediction["point_aggregation_method"],
            "point_source": ensemble_prediction["point_source"],
            "uncertainty_method": "weighted_interval_plus_model_disagreement",
            "uncertainty_components": {
                "sarima_half_width": ensemble_prediction["u_s"],
                "lstm_half_width": ensemble_prediction["u_l"],
                "ensemble_half_width": ensemble_prediction["u_e"],
                "model_disagreement": disagreement,
                "interval_alpha": ensemble_prediction["interval_alpha"],
                "beta": disagreement_beta,
            },
        }
        point = ForecastPoint(
            run=run,
            device=device,
            metric_code=metric_code,
            horizon=horizon,
            target_ts=target_ts,
            model_kind="ensemble",
            y_hat=y_hat,
            p10=p10,
            p50=p50,
            p90=p90,
            alpha=metric_alpha,
            labels=labels,
        )
        points_batch.append(point)
        per_horizon_points[horizon].append(point)

    if not points_batch:
        run.status = "failed"
        run.finished_at = timezone.now()
        run.quality = {"errors": ["No merged ensemble points produced"]}
        run.save(update_fields=["status", "finished_at", "quality", "updated_at"])
        raise RuntimeError("No merged ensemble points produced")

    horizons = sorted({item.horizon for item in points_batch})
    for horizon in horizons:
        state_risk_features = build_state_risk_features_for_points(
            device=device,
            horizon=horizon,
            points=per_horizon_points[horizon],
            source_model="ensemble",
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
                    "source": "sarima_lstm_ensemble",
                    "sarima_run_id": sarima_run.id,
                    "lstm_run_id": lstm_run.id,
                    **(state_result["evidence"] or {}),
                },
                timestamp=now,
            )
        )

    with transaction.atomic():
        ForecastPoint.objects.bulk_create(points_batch, batch_size=500)
        StateEstimate.objects.bulk_create(states_batch, batch_size=100)
        run.status = "success"
        run.finished_at = timezone.now()
        point_count = len(points_batch)
        run.quality = {
            "points_created": point_count,
            "states_created": len(states_batch),
            "source_counts": source_counts,
            "weights": weights,
            "alpha_by_metric_horizon": {
                f"{code}:{horizon_key}:{segment_key}": {
                    "sarima": float(item["alpha"]),
                    "lstm": float(1.0 - float(item["alpha"])),
                    "metric_code": code,
                    "horizon": horizon_key,
                    "segment_key": segment_key,
                    "selection_method": item["evidence"].get("selection_method"),
                    "control": item.get("control") or {},
                    "orchestrator_control": orchestrator_controls,
                }
                for (code, horizon_key, segment_key), item in alpha_by_metric_horizon.items()
            },
            "alpha_by_metric": {
                code: {
                    "sarima": float(sum(item["alpha"] for (metric_key, _hz, _segment), item in alpha_by_metric_horizon.items() if metric_key == code) / max(1, sum(1 for (metric_key, _hz, _segment) in alpha_by_metric_horizon if metric_key == code))),
                    "lstm": float(sum(1.0 - float(item["alpha"]) for (metric_key, _hz, _segment), item in alpha_by_metric_horizon.items() if metric_key == code) / max(1, sum(1 for (metric_key, _hz, _segment) in alpha_by_metric_horizon if metric_key == code))),
                    "selection_method": "per_horizon_average",
                    "control": next((item.get("control") or {} for (metric_key, _hz, _segment), item in alpha_by_metric_horizon.items() if metric_key == code), {}),
                    "orchestrator_control": orchestrator_controls,
                }
                for code in sorted({metric_key for metric_key, _hz, _segment in alpha_by_metric_horizon})
            },
            "orchestrator_controls": orchestrator_controls,
            "uncertainty_method": "weighted_interval_plus_model_disagreement",
            "uncertainty_summary": {
                "avg_interval_width": (uncertainty_stats["sum_width"] / point_count) if point_count else 0.0,
                "avg_model_disagreement": (uncertainty_stats["sum_disagreement"] / point_count) if point_count else 0.0,
                "max_interval_width": uncertainty_stats["max_width"],
                "max_model_disagreement": uncertainty_stats["max_disagreement"],
                "beta": disagreement_beta,
            },
        }
        run.save(update_fields=["status", "finished_at", "quality", "updated_at"])

    return run, True, {
        "points_created": len(points_batch),
        "states_created": len(states_batch),
    }


def materialize_pending_ensembles(
    *,
    run_id: int | None = None,
    run_ids: list[int] | None = None,
    serial: str | None = None,
):
    qs = ForecastRun.objects.filter(model_kind="lstm", status="success").select_related("device")
    if run_id:
        qs = qs.filter(id=int(run_id))
    if run_ids:
        qs = qs.filter(id__in=[int(item) for item in run_ids if item])
    if serial:
        qs = qs.filter(device__serial_number=serial)
    qs = qs.filter(parameters__orchestrator_kind=ORCHESTRATOR_KIND)

    ensemble_runs_created = 0
    ensemble_points_created = 0
    ensemble_states_created = 0
    skipped = 0
    created_run_ids = []

    for lstm_run in qs.order_by("id"):
        params = dict(lstm_run.parameters or {})
        ensemble_run_id = params.get("ensemble_run_id")
        if ensemble_run_id and ForecastRun.objects.filter(id=ensemble_run_id, model_kind="ensemble").exists():
            continue

        sarima_run_id = params.get("paired_sarima_run_id")
        if not sarima_run_id:
            skipped += 1
            continue

        sarima_run = (
            ForecastRun.objects
            .filter(id=int(sarima_run_id), model_kind="sarima", device=lstm_run.device)
            .first()
        )
        if not sarima_run:
            skipped += 1
            continue

        ensemble_run, created, counts = build_ensemble_run_for_sources(
            sarima_run=sarima_run,
            lstm_run=lstm_run,
            weights=params.get("ensemble_weights"),
            disagreement_beta=params.get("ensemble_beta"),
        )
        params["ensemble_run_id"] = ensemble_run.id
        lstm_run.parameters = params
        lstm_run.save(update_fields=["parameters", "updated_at"])

        if created:
            ensemble_runs_created += 1
            created_run_ids.append(ensemble_run.id)
            ensemble_points_created += int(counts.get("points_created", 0) or 0)
            ensemble_states_created += int(counts.get("states_created", 0) or 0)

    return {
        "ensemble_runs_created": ensemble_runs_created,
        "ensemble_points_created": ensemble_points_created,
        "ensemble_states_created": ensemble_states_created,
        "ensemble_run_ids": created_run_ids,
        "skipped": skipped,
    }


def run_orchestrated_forecasts(
    *,
    serial: str | None = None,
    sarima_lookback_days: int = 60,
    lstm_lookback_days: int = 60,
    sarima_freq: str = "1h",
    lstm_freq: str = "1h",
    horizons: list[str] | None = None,
    metric_codes: list[str] | None = None,
    save_stl_components: bool = True,
    sarima_seasonality_mode: str | None = None,
    wait_for_lstm: bool = False,
    poll_interval_sec: float = 2.0,
    max_wait_sec: float = 120.0,
    max_retries: int = 5,
    ensemble_weights: dict | None = None,
    ensemble_beta: float | None = None,
    lstm_model_options: dict | None = None,
):
    horizons = horizons or ["24h", "7d", "30d"]
    requested_metric_codes = metric_codes or list(DEFAULT_METRIC_CODES)
    profile_config = get_active_state_inference_profile_config()
    sarima_metric_codes = resolve_metric_codes_for_source(
        "sarima",
        requested_codes=requested_metric_codes,
        config=profile_config,
    )
    lstm_metric_codes = resolve_metric_codes_for_source(
        "lstm",
        requested_codes=requested_metric_codes,
        config=profile_config,
    )
    weights = _normalize_weights(ensemble_weights or _default_ensemble_weights())
    ensemble_beta = float(_default_ensemble_beta() if ensemble_beta is None else max(0.0, ensemble_beta))

    baseline_payload = run_baseline_forecasts(
        serial=serial,
        lookback_days=max(1, int(sarima_lookback_days)),
        freq=str(sarima_freq or "1h"),
        horizons=horizons,
        metric_codes=sarima_metric_codes,
        save_stl_components=save_stl_components,
        seasonality_mode=sarima_seasonality_mode,
    )
    lstm_payload = run_lstm_remote_forecasts(
        serial=serial,
        lookback_days=max(1, int(lstm_lookback_days)),
        freq=str(lstm_freq or "1h"),
        horizons=horizons,
        metric_codes=lstm_metric_codes,
        wait_for_result=bool(wait_for_lstm),
        poll_interval_sec=poll_interval_sec,
        max_wait_sec=max_wait_sec,
        max_retries=max_retries,
        model_options=lstm_model_options,
    )

    sarima_by_device = _runs_by_device(baseline_payload.get("run_ids"))
    lstm_by_device = _runs_by_device(lstm_payload.get("run_ids"))

    paired_runs = []
    for device_id, lstm_run in lstm_by_device.items():
        sarima_run = sarima_by_device.get(device_id)
        params = dict(lstm_run.parameters or {})
        params.update({
            "orchestrator_kind": ORCHESTRATOR_KIND,
            "paired_sarima_run_id": sarima_run.id if sarima_run else None,
            "ensemble_weights": weights,
            "ensemble_beta": ensemble_beta,
        })
        lstm_run.parameters = params
        lstm_run.save(update_fields=["parameters", "updated_at"])
        paired_runs.append({
            "device_id": device_id,
            "device_serial": lstm_run.device.serial_number,
            "sarima_run_id": sarima_run.id if sarima_run else None,
            "lstm_run_id": lstm_run.id,
        })

    ensemble_payload = materialize_pending_ensembles(run_ids=lstm_payload.get("run_ids"))
    return {
        "orchestrator_kind": ORCHESTRATOR_KIND,
        "baseline": baseline_payload,
        "lstm": lstm_payload,
        "ensemble": ensemble_payload,
        "paired_runs": paired_runs,
        "ensemble_calibration": {
            "default_weights": weights,
            "beta": ensemble_beta,
        },
        "metric_plan": {
            "requested_metric_codes": requested_metric_codes,
            "sarima_metric_codes": sarima_metric_codes,
            "lstm_metric_codes": lstm_metric_codes,
        },
    }


def poll_orchestrated_forecasts(
    *,
    run_id: int | None = None,
    serial: str | None = None,
    limit: int = 20,
    poll_interval_sec: float = 10.0,
):
    poll_payload = poll_lstm_remote_runs(
        run_id=run_id,
        serial=serial,
        limit=limit,
        poll_interval_sec=poll_interval_sec,
    )

    ensemble_payload = materialize_pending_ensembles(run_id=run_id, serial=serial)
    return {
        "orchestrator_kind": ORCHESTRATOR_KIND,
        "lstm_poll": poll_payload,
        "ensemble": ensemble_payload,
    }
