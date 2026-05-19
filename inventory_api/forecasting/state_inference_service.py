from __future__ import annotations

import math
from typing import Any


STATE_KEYS = ("s0", "s1", "s2")
STATE_FEATURE_KEYS = (
    "metric_aggregate_risk",
    "markov_p_s2",
    "top1_risk",
    "top3_risk",
    "temperature_risk",
    "wear_risk",
    "latency_risk",
)
FORECAST_ALPHA_MODE_AUTO = "auto"
FORECAST_ALPHA_MODE_MANUAL = "manual"
FORECAST_SOURCE_KEYS = ("sarima", "lstm")
FORECAST_TREND_MODE_MEAN = "mean_regression"
FORECAST_TREND_MODE_BLEND = "upper_envelope_blend"
FORECAST_TREND_MODE_FLOOR = "upper_envelope_floor"
FORECAST_TREND_MODE_CHOICES = (
    FORECAST_TREND_MODE_MEAN,
    FORECAST_TREND_MODE_BLEND,
    FORECAST_TREND_MODE_FLOOR,
)
KNOWN_FORECAST_METRIC_CODES = (
    "cpu_load_total",
    "mem_usage_percent",
    "net_bytes_sent",
    "net_bytes_recv",
    "ping_latency_gateway",
    "system_temperature",
    "storcli_drive_temperature",
    "storcli_predictive_failure_count",
)
DEFAULT_ORCHESTRATOR_CONTROLS = {
    "alpha_version_aware": True,
    "normalize_errors_by_scale": True,
    "compatible_history_runs": 6,
    "history_limit_per_segment": 18,
    "segment_boundaries_hours": [24, 168, 720],
    "error_scale_lookback_days": 60,
    "winner_margin": 1.2,
    "winner_weight": 0.85,
}

DEFAULT_STATE_SCORE_WEIGHTS = {
    "s0": {
        "bias": 0.20,
        "metric_aggregate_risk": 1.90,
        "markov_p_s2": 1.20,
        "top1_risk": 1.50,
        "top3_risk": 1.10,
        "temperature_risk": 0.80,
        "wear_risk": 0.90,
        "latency_risk": 0.60,
    },
    "s1": {
        "bias": 0.30,
        "metric_aggregate_risk": 1.40,
        "markov_p_s2": 0.80,
        "top1_risk": 0.90,
        "top3_risk": 1.20,
        "temperature_risk": 0.80,
        "wear_risk": 0.70,
        "latency_risk": 0.70,
    },
    "s2": {
        "bias": 0.10,
        "metric_aggregate_risk": 2.20,
        "markov_p_s2": 1.80,
        "top1_risk": 1.60,
        "top3_risk": 1.20,
        "temperature_risk": 1.20,
        "wear_risk": 1.40,
        "latency_risk": 0.80,
    },
}


DEFAULT_STATE_PROFILE = {
    "name": "Базовый профиль состояния",
    "version": 1,
    "is_active": True,
    "notes": "Стартовый профиль оценки состояния S0/S1/S2.",
    "thresholds": {
        "cpu_load_total": 90.0,
        "mem_usage_percent": 92.0,
        "ping_latency_gateway": 150.0,
        "system_temperature": 80.0,
        "storcli_drive_temperature": 58.0,
        "storcli_predictive_failure_count": 1.0,
    },
    "forecast_metric_controls": {
        metric_code: {
            "sarima_enabled": metric_code != "storcli_predictive_failure_count",
            "lstm_enabled": True,
            "alpha_mode": (
                FORECAST_ALPHA_MODE_MANUAL
                if metric_code == "storcli_predictive_failure_count"
                else FORECAST_ALPHA_MODE_AUTO
            ),
            "manual_alpha_sarima": 0.0 if metric_code == "storcli_predictive_failure_count" else 0.5,
            "trend_long_mode": (
                FORECAST_TREND_MODE_FLOOR
                if metric_code in {"cpu_load_total", "mem_usage_percent"} or "temperature" in metric_code
                else FORECAST_TREND_MODE_MEAN
            ),
            "trend_transition_steps": 0,
            "trend_envelope_weight": (
                0.55
                if metric_code == "cpu_load_total"
                else 0.50
                if metric_code == "mem_usage_percent"
                else 0.45
                if "temperature" in metric_code
                else 0.0
            ),
            "bias_correction_strength": (
                0.55
                if metric_code == "cpu_load_total"
                else 0.50
                if metric_code == "mem_usage_percent"
                else 0.45
                if "temperature" in metric_code
                else 0.40
                if metric_code in {"storcli_predictive_failure_count", "ping_latency_gateway"}
                else 0.25
            ),
        }
        for metric_code in KNOWN_FORECAST_METRIC_CODES
    },
    "orchestrator_controls": dict(DEFAULT_ORCHESTRATOR_CONTROLS),
    "risk_ratio_baseline": 0.70,
    "risk_ratio_scale": 0.30,
    "medium_risk_level": 0.40,
    "critical_risk_level": 0.85,
    "overall_hint_weight": 0.25,
    "softmax_temperature": 1.0,
    "score_weights": {
        state_key: dict(weights)
        for state_key, weights in DEFAULT_STATE_SCORE_WEIGHTS.items()
    },
    "s0_bias": 0.15,
    "s0_effective_weight": 0.85,
    "s0_avg_weight": 0.45,
    "s0_medium_weight": 0.35,
    "s0_critical_weight": 0.55,
    "s1_bias": 0.10,
    "s1_avg_weight": 0.90,
    "s1_medium_weight": 0.45,
    "s1_markov_weight": 0.10,
    "s2_bias": 0.05,
    "s2_effective_power": 1.60,
    "s2_critical_weight": 0.30,
    "s2_medium_weight": 0.15,
    "s2_markov_weight": 0.10,
    "confidence_max": 0.98,
    "confidence_base": 0.36,
    "confidence_component_weight": 0.08,
    "confidence_feature_weight": 0.07,
    "confidence_margin_weight": 0.35,
    "confidence_component_cap": 5,
}

DEFAULT_STATE_THRESHOLDS = dict(DEFAULT_STATE_PROFILE["thresholds"])


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:
        return default
    return out


def _as_int(value: Any, default: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out


def build_default_state_inference_profile_payload() -> dict[str, Any]:
    return {
        key: (
            {
                nested_key: dict(nested_value) if isinstance(nested_value, dict) else nested_value
                for nested_key, nested_value in value.items()
            }
            if key in {"score_weights", "forecast_metric_controls", "orchestrator_controls"} and isinstance(value, dict)
            else (dict(value) if isinstance(value, dict) else value)
        )
        for key, value in DEFAULT_STATE_PROFILE.items()
    }


def _normalize_thresholds(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return dict(DEFAULT_STATE_THRESHOLDS)
    normalized: dict[str, float] = {}
    for key, value in raw.items():
        metric_code = str(key or "").strip()
        parsed = _as_float(value, None)
        if metric_code and parsed is not None and parsed > 0:
            normalized[metric_code] = float(parsed)
    return normalized or dict(DEFAULT_STATE_THRESHOLDS)


def _normalize_score_weights(raw: Any) -> dict[str, dict[str, float]]:
    normalized = {
        state_key: dict(weights)
        for state_key, weights in DEFAULT_STATE_SCORE_WEIGHTS.items()
    }
    if not isinstance(raw, dict):
        return normalized

    for state_key in STATE_KEYS:
        state_payload = raw.get(state_key)
        if not isinstance(state_payload, dict):
            continue
        for feature_key in normalized[state_key]:
            parsed = _as_float(state_payload.get(feature_key), None)
            if parsed is not None:
                normalized[state_key][feature_key] = float(parsed)
    return normalized


def _default_forecast_metric_control(metric_code: str) -> dict[str, Any]:
    metric_key = str(metric_code or "").strip()
    defaults = DEFAULT_STATE_PROFILE.get("forecast_metric_controls", {})
    default = defaults.get(metric_key) if isinstance(defaults, dict) else None
    if isinstance(default, dict):
        return dict(default)
    return {
        "sarima_enabled": True,
        "lstm_enabled": True,
        "alpha_mode": FORECAST_ALPHA_MODE_AUTO,
        "manual_alpha_sarima": 0.5,
        "trend_long_mode": (
            FORECAST_TREND_MODE_FLOOR
            if metric_key in {"cpu_load_total", "mem_usage_percent"} or "temperature" in metric_key
            else FORECAST_TREND_MODE_MEAN
        ),
        "trend_transition_steps": 0,
        "trend_envelope_weight": (
            0.55
            if metric_key == "cpu_load_total"
            else 0.50
            if metric_key == "mem_usage_percent"
            else 0.45
            if "temperature" in metric_key
            else 0.0
        ),
        "bias_correction_strength": (
            0.55
            if metric_key == "cpu_load_total"
            else 0.50
            if metric_key == "mem_usage_percent"
            else 0.45
            if "temperature" in metric_key
            else 0.40
            if metric_key in {"storcli_predictive_failure_count", "ping_latency_gateway"}
            else 0.25
        ),
    }


def _normalize_forecast_metric_controls(raw: Any) -> dict[str, dict[str, Any]]:
    normalized = {
        metric_code: _default_forecast_metric_control(metric_code)
        for metric_code in KNOWN_FORECAST_METRIC_CODES
    }
    if not isinstance(raw, dict):
        return normalized

    for key, value in raw.items():
        metric_code = str(key or "").strip()
        if not metric_code or not isinstance(value, dict):
            continue
        item = _default_forecast_metric_control(metric_code)
        if "sarima_enabled" in value:
            item["sarima_enabled"] = bool(value.get("sarima_enabled"))
        if "lstm_enabled" in value:
            item["lstm_enabled"] = bool(value.get("lstm_enabled"))
        alpha_mode = str(value.get("alpha_mode", item["alpha_mode"]) or item["alpha_mode"]).strip().lower()
        if alpha_mode not in {FORECAST_ALPHA_MODE_AUTO, FORECAST_ALPHA_MODE_MANUAL}:
            alpha_mode = item["alpha_mode"]
        item["alpha_mode"] = alpha_mode
        manual_alpha = _as_float(value.get("manual_alpha_sarima"), item["manual_alpha_sarima"])
        item["manual_alpha_sarima"] = _clamp(
            manual_alpha if manual_alpha is not None else item["manual_alpha_sarima"]
        )
        trend_long_mode = str(value.get("trend_long_mode", item["trend_long_mode"]) or item["trend_long_mode"]).strip().lower()
        if trend_long_mode not in FORECAST_TREND_MODE_CHOICES:
            trend_long_mode = item["trend_long_mode"]
        item["trend_long_mode"] = trend_long_mode
        trend_transition_steps = _as_int(value.get("trend_transition_steps"), item["trend_transition_steps"])
        item["trend_transition_steps"] = max(0, min(10000, trend_transition_steps))
        trend_envelope_weight = _as_float(value.get("trend_envelope_weight"), item["trend_envelope_weight"])
        if trend_envelope_weight is not None:
            item["trend_envelope_weight"] = _clamp(trend_envelope_weight, 0.0, 1.0)
        bias_correction_strength = _as_float(value.get("bias_correction_strength"), item["bias_correction_strength"])
        if bias_correction_strength is not None:
            item["bias_correction_strength"] = _clamp(bias_correction_strength, 0.0, 1.0)
        normalized[metric_code] = item
    return normalized


def _normalize_orchestrator_controls(raw: Any) -> dict[str, Any]:
    normalized = dict(DEFAULT_ORCHESTRATOR_CONTROLS)
    if not isinstance(raw, dict):
        return normalized

    if "alpha_version_aware" in raw:
        normalized["alpha_version_aware"] = bool(raw.get("alpha_version_aware"))
    if "normalize_errors_by_scale" in raw:
        normalized["normalize_errors_by_scale"] = bool(raw.get("normalize_errors_by_scale"))

    compatible_history_runs = _as_int(raw.get("compatible_history_runs"), normalized["compatible_history_runs"])
    normalized["compatible_history_runs"] = max(1, min(50, compatible_history_runs))

    history_limit = _as_int(raw.get("history_limit_per_segment"), normalized["history_limit_per_segment"])
    normalized["history_limit_per_segment"] = max(1, min(200, history_limit))

    lookback_days = _as_int(raw.get("error_scale_lookback_days"), normalized["error_scale_lookback_days"])
    normalized["error_scale_lookback_days"] = max(1, min(3650, lookback_days))

    winner_margin = _as_float(raw.get("winner_margin"), normalized["winner_margin"])
    if winner_margin is not None:
        normalized["winner_margin"] = max(1.0, min(10.0, float(winner_margin)))

    winner_weight = _as_float(raw.get("winner_weight"), normalized["winner_weight"])
    if winner_weight is not None:
        normalized["winner_weight"] = max(0.5, min(1.0, float(winner_weight)))

    raw_boundaries = raw.get("segment_boundaries_hours")
    if isinstance(raw_boundaries, (list, tuple)):
        parsed_boundaries = []
        for item in raw_boundaries:
            parsed = _as_int(item, 0)
            if parsed > 0:
                parsed_boundaries.append(parsed)
        parsed_boundaries = sorted(set(parsed_boundaries))
        if len(parsed_boundaries) >= 2:
            normalized["segment_boundaries_hours"] = parsed_boundaries

    return normalized


def _profile_to_config(profile: Any) -> dict[str, Any]:
    base = build_default_state_inference_profile_payload()
    if profile is None:
        return base

    if isinstance(profile, dict):
        data = profile
    else:
        fields = [
            "id",
            "name",
            "version",
            "is_active",
            "notes",
            "thresholds",
            "forecast_metric_controls",
            "orchestrator_controls",
            "risk_ratio_baseline",
            "risk_ratio_scale",
            "medium_risk_level",
            "critical_risk_level",
            "overall_hint_weight",
            "softmax_temperature",
            "score_weights",
            "s0_bias",
            "s0_effective_weight",
            "s0_avg_weight",
            "s0_medium_weight",
            "s0_critical_weight",
            "s1_bias",
            "s1_avg_weight",
            "s1_medium_weight",
            "s1_markov_weight",
            "s2_bias",
            "s2_effective_power",
            "s2_critical_weight",
            "s2_medium_weight",
            "s2_markov_weight",
            "confidence_max",
            "confidence_base",
            "confidence_component_weight",
            "confidence_feature_weight",
            "confidence_margin_weight",
            "confidence_component_cap",
        ]
        data = {field: getattr(profile, field, None) for field in fields}

    for key, value in data.items():
        if key in {"thresholds", "forecast_metric_controls", "orchestrator_controls"}:
            continue
        if value is not None:
            base[key] = value
    base["thresholds"] = _normalize_thresholds(data.get("thresholds"))
    base["forecast_metric_controls"] = _normalize_forecast_metric_controls(data.get("forecast_metric_controls"))
    base["orchestrator_controls"] = _normalize_orchestrator_controls(data.get("orchestrator_controls"))
    base["score_weights"] = _normalize_score_weights(data.get("score_weights"))
    return base


def get_active_state_inference_profile_config(
    *,
    profile: Any | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    config = _profile_to_config(profile)
    if profile is None:
        try:
            from inventory_api.models import StateInferenceProfile

            active = (
                StateInferenceProfile.objects
                .filter(is_active=True)
                .order_by("-updated_at", "-id")
                .first()
            )
            if active is not None:
                config = _profile_to_config(active)
        except Exception:
            config = _profile_to_config(None)

    if thresholds:
        config["thresholds"] = {
            **config["thresholds"],
            **_normalize_thresholds(thresholds),
        }
    return config


def get_forecast_metric_controls_config(
    *,
    profile: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    resolved = config or get_active_state_inference_profile_config(profile=profile)
    return _normalize_forecast_metric_controls(resolved.get("forecast_metric_controls"))


def get_orchestrator_controls_config(
    *,
    profile: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = config or get_active_state_inference_profile_config(profile=profile)
    return _normalize_orchestrator_controls(resolved.get("orchestrator_controls"))


def get_metric_forecast_control(
    metric_code: str,
    *,
    profile: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    controls = get_forecast_metric_controls_config(profile=profile, config=config)
    metric_key = str(metric_code or "").strip()
    if metric_key in controls:
        return dict(controls[metric_key])
    return _default_forecast_metric_control(metric_key)


def resolve_metric_codes_for_source(
    source_kind: str,
    *,
    requested_codes: list[str] | None = None,
    profile: Any | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    source_key = str(source_kind or "").strip().lower()
    if source_key not in FORECAST_SOURCE_KEYS:
        return [
            code
            for code in [str(item or "").strip() for item in (requested_codes or KNOWN_FORECAST_METRIC_CODES)]
            if code
        ]

    controls = get_forecast_metric_controls_config(profile=profile, config=config)
    if requested_codes:
        ordered_codes = []
        seen = set()
        for item in requested_codes:
            code = str(item or "").strip()
            if code and code not in seen:
                ordered_codes.append(code)
                seen.add(code)
    else:
        ordered_codes = list(KNOWN_FORECAST_METRIC_CODES)
        for code in controls.keys():
            if code not in ordered_codes:
                ordered_codes.append(code)

    flag_name = f"{source_key}_enabled"
    filtered = []
    for code in ordered_codes:
        control = controls.get(code) or _default_forecast_metric_control(code)
        if bool(control.get(flag_name, True)):
            filtered.append(code)
    return filtered


def ensure_default_state_inference_profile(*, created_by=None):
    from django.db import transaction
    from inventory_api.models import StateInferenceProfile

    payload = build_default_state_inference_profile_payload()
    with transaction.atomic():
        profile = (
            StateInferenceProfile.objects
            .filter(name=payload["name"], version=payload["version"])
            .first()
        )
        if profile is None:
            profile = StateInferenceProfile.objects.create(
                **payload,
                created_by=created_by,
            )
        else:
            for key, value in payload.items():
                setattr(profile, key, value)
            if created_by and profile.created_by_id is None:
                profile.created_by = created_by
            profile.save()
        StateInferenceProfile.objects.exclude(id=profile.id).filter(is_active=True).update(is_active=False)
    return profile


def _risk_from_ratio(ratio: float | None, *, config: dict[str, Any]) -> float:
    if ratio is None:
        return 0.0
    baseline = _as_float(config.get("risk_ratio_baseline"), 0.75) or 0.75
    scale = _as_float(config.get("risk_ratio_scale"), 0.75) or 0.75
    scale = max(1e-6, scale)
    return _clamp((float(ratio) - baseline) / scale)


def _normalize_probabilities(
    *,
    p_s0: float | None,
    p_s1: float | None,
    p_s2: float | None,
) -> dict[str, Any]:
    values = [
        _as_float(p_s0, None),
        _as_float(p_s1, None),
        _as_float(p_s2, None),
    ]
    if all(item is None for item in values):
        return {
            "state": "unknown",
            "p_s0": None,
            "p_s1": None,
            "p_s2": None,
        }

    normalized = [max(0.0, float(item or 0.0)) for item in values]
    total = sum(normalized)
    if total <= 1e-12:
        return {
            "state": "unknown",
            "p_s0": None,
            "p_s1": None,
            "p_s2": None,
        }

    normalized = [item / total for item in normalized]
    labels = {
        "s0": normalized[0],
        "s1": normalized[1],
        "s2": normalized[2],
    }
    state = max(labels, key=labels.get)
    return {
        "state": state,
        "p_s0": labels["s0"],
        "p_s1": labels["s1"],
        "p_s2": labels["s2"],
    }


def normalize_state_probabilities(
    *,
    p_s0: float | None,
    p_s1: float | None,
    p_s2: float | None,
) -> dict[str, Any]:
    return _normalize_probabilities(p_s0=p_s0, p_s1=p_s1, p_s2=p_s2)


def _component_from_points(
    *,
    metric_code: str,
    value: float | None,
    thresholds: dict[str, float],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    threshold = _as_float(thresholds.get(metric_code), None)
    value_f = _as_float(value, None)
    if threshold is None or threshold <= 0 or value_f is None:
        return None

    ratio = value_f / threshold
    return {
        "metric_code": metric_code,
        "value": value_f,
        "threshold": threshold,
        "ratio": ratio,
        "risk_component": _risk_from_ratio(ratio, config=config),
        "source": "thresholds",
    }


def _component_from_metric_result(item: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any] | None:
    metric_code = str(item.get("metric_code") or "").strip()
    if not metric_code:
        return None

    forecast = item.get("forecast") if isinstance(item.get("forecast"), dict) else {}
    risk = _as_float(item.get("risk"), None)
    if risk is None:
        ratio = _as_float(item.get("ratio"), None)
        if ratio is not None:
            risk = _risk_from_ratio(ratio, config=config)
        else:
            return None

    value = _as_float(forecast.get("y_hat"), None)
    if value is None:
        value = _as_float(item.get("current_value"), None)
    threshold = _as_float(item.get("threshold"), None)
    ratio = _as_float(item.get("ratio"), None)
    if ratio is None and value is not None and threshold is not None and threshold > 0:
        ratio = value / threshold

    return {
        "metric_code": metric_code,
        "value": value,
        "threshold": threshold,
        "ratio": ratio,
        "risk_component": _clamp(risk),
        "source": str(item.get("method") or "risk_features"),
    }


def _collect_metric_components(
    *,
    points_by_metric: dict[str, float] | None,
    risk_features: dict[str, Any] | None,
    thresholds: dict[str, float],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    feature_rows = risk_features.get("metric_results") if isinstance(risk_features, dict) else None
    if isinstance(feature_rows, list):
        for item in feature_rows:
            if not isinstance(item, dict):
                continue
            component = _component_from_metric_result(item, config=config)
            if component is not None:
                components.append(component)

    if components:
        return components

    for metric_code, value in (points_by_metric or {}).items():
        component = _component_from_points(
            metric_code=str(metric_code or "").strip(),
            value=value,
            thresholds=thresholds,
            config=config,
        )
        if component is not None:
            components.append(component)
    return components


def _is_temperature_metric(metric_code: str) -> bool:
    raw = str(metric_code or "").strip().lower()
    return "temp" in raw or "temperature" in raw


def _is_latency_metric(metric_code: str) -> bool:
    raw = str(metric_code or "").strip().lower()
    return (
        "latency" in raw
        or raw.startswith("ping_")
        or "packet_loss" in raw
        or "jitter" in raw
    )


def _is_wear_metric(metric_code: str) -> bool:
    raw = str(metric_code or "").strip().lower()
    return (
        "wear" in raw
        or "tbw" in raw
        or "percentage_used" in raw
        or "life_left" in raw
        or raw == "storcli_predictive_failure_count"
    )


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _derive_metric_aggregate_risk(component_risks: list[float]) -> float:
    if not component_risks:
        return 0.0
    top1 = max(component_risks)
    top3 = _mean(sorted(component_risks, reverse=True)[:3])
    avg = _mean(component_risks)
    return _clamp(0.45 * top1 + 0.35 * top3 + 0.20 * avg)


def _compute_state_features(
    *,
    components: list[dict[str, Any]],
    risk_features: dict[str, Any],
) -> dict[str, float]:
    component_risks = [
        _clamp(_as_float(item.get("risk_component"), 0.0) or 0.0)
        for item in components
    ]
    component_risks = [value for value in component_risks if value is not None]
    ordered = sorted(component_risks, reverse=True)

    metric_aggregate_risk = _as_float(risk_features.get("metric_aggregate_risk"), None)
    if metric_aggregate_risk is None:
        metric_aggregate_risk = _derive_metric_aggregate_risk(ordered)

    markov_p_s2 = _clamp(
        _as_float(risk_features.get("markov_p_s2", risk_features.get("markov_projected_p_s2")), 0.0) or 0.0
    )

    temperature_risk = 0.0
    wear_risk = 0.0
    latency_risk = 0.0
    for item in components:
        metric_code = str(item.get("metric_code") or "").strip()
        risk_value = _clamp(_as_float(item.get("risk_component"), 0.0) or 0.0)
        if _is_temperature_metric(metric_code):
            temperature_risk = max(temperature_risk, risk_value)
        if _is_wear_metric(metric_code):
            wear_risk = max(wear_risk, risk_value)
        if _is_latency_metric(metric_code):
            latency_risk = max(latency_risk, risk_value)

    return {
        "metric_aggregate_risk": _clamp(metric_aggregate_risk or 0.0),
        "markov_p_s2": markov_p_s2,
        "top1_risk": ordered[0] if ordered else 0.0,
        "top3_risk": _mean(ordered[:3]),
        "temperature_risk": temperature_risk,
        "wear_risk": wear_risk,
        "latency_risk": latency_risk,
    }


def _score_transform(state_key: str, value: float) -> float:
    x = _clamp(value)
    if state_key == "s0":
        return 1.0 - x
    if state_key == "s1":
        return _clamp(4.0 * x * (1.0 - x))
    return x


def _softmax_scores(scores: dict[str, float], *, temperature: float) -> dict[str, float]:
    temp = max(1e-6, float(temperature or 1.0))
    logits = {key: float(value) / temp for key, value in scores.items()}
    max_logit = max(logits.values())
    exp_scores = {key: math.exp(value - max_logit) for key, value in logits.items()}
    denom = sum(exp_scores.values())
    if denom <= 1e-12:
        return {key: 0.0 for key in scores}
    return {key: exp_scores[key] / denom for key in scores}


def infer_state_distribution(
    *,
    points_by_metric: dict[str, float] | None = None,
    risk_features: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
    profile: Any | None = None,
) -> dict[str, Any]:
    risk_features = dict(risk_features or {})
    config = get_active_state_inference_profile_config(profile=profile, thresholds=thresholds)
    thresholds_map = dict(config["thresholds"])
    components = _collect_metric_components(
        points_by_metric=points_by_metric,
        risk_features=risk_features,
        thresholds=thresholds_map,
        config=config,
    )

    external_metric_risk = _as_float(risk_features.get("metric_aggregate_risk"), None)
    external_overall_risk = _as_float(risk_features.get("overall_risk"), None)
    external_markov_risk = _as_float(
        risk_features.get("markov_p_s2", risk_features.get("markov_projected_p_s2")),
        None,
    )

    if not components and external_metric_risk is None and external_overall_risk is None and external_markov_risk is None:
        return {
            "state": "unknown",
            "p_s0": None,
            "p_s1": None,
            "p_s2": None,
            "confidence": 0.0,
            "evidence": {
                "reason": "no_state_signal",
                "inference_version": "state_inference_v3",
                "profile": {
                    "id": config.get("id"),
                    "name": config.get("name"),
                    "version": config.get("version"),
                },
            },
        }

    component_risks = [float(item["risk_component"]) for item in components]
    max_component_risk = max(component_risks) if component_risks else 0.0
    avg_component_risk = _mean(component_risks)
    medium_level = _clamp(_as_float(config.get("medium_risk_level"), 0.40) or 0.40)
    critical_level = _clamp(_as_float(config.get("critical_risk_level"), 0.85) or 0.85)
    medium_ratio = (
        sum(1 for value in component_risks if value >= medium_level) / len(component_risks)
        if component_risks else 0.0
    )
    critical_ratio = (
        sum(1 for value in component_risks if value >= critical_level) / len(component_risks)
        if component_risks else 0.0
    )

    features = _compute_state_features(
        components=components,
        risk_features=risk_features,
    )
    score_weights = _normalize_score_weights(config.get("score_weights"))
    softmax_temperature = max(1e-6, _as_float(config.get("softmax_temperature"), 1.0) or 1.0)

    state_scores: dict[str, float] = {}
    state_feature_contributions: dict[str, dict[str, float]] = {}
    state_feature_inputs: dict[str, dict[str, float]] = {}
    for state_key in STATE_KEYS:
        weights = score_weights.get(state_key) or {}
        bias = _as_float(weights.get("bias"), 0.0) or 0.0
        state_scores[state_key] = bias
        state_feature_contributions[state_key] = {"bias": bias}
        state_feature_inputs[state_key] = {"bias": 1.0}
        for feature_key in STATE_FEATURE_KEYS:
            raw_value = _clamp(_as_float(features.get(feature_key), 0.0) or 0.0)
            transformed = _score_transform(state_key, raw_value)
            contribution = (weights.get(feature_key) or 0.0) * transformed
            state_scores[state_key] += contribution
            state_feature_contributions[state_key][feature_key] = contribution
            state_feature_inputs[state_key][feature_key] = transformed

    probabilities = _softmax_scores(state_scores, temperature=softmax_temperature)
    normalized = _normalize_probabilities(
        p_s0=probabilities.get("s0"),
        p_s1=probabilities.get("s1"),
        p_s2=probabilities.get("s2"),
    )
    sorted_probs = sorted(
        [
            normalized["p_s0"] or 0.0,
            normalized["p_s1"] or 0.0,
            normalized["p_s2"] or 0.0,
        ],
        reverse=True,
    )
    margin = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) >= 2 else 0.0
    feature_count = sum(
        1 for item in (external_metric_risk, external_overall_risk, external_markov_risk)
        if item is not None
    )
    confidence = min(
        _as_float(config.get("confidence_max"), 0.98) or 0.98,
        (_as_float(config.get("confidence_base"), 0.36) or 0.36)
        + (_as_float(config.get("confidence_component_weight"), 0.08) or 0.08)
        * min(len(components), max(1, _as_int(config.get("confidence_component_cap"), 5)))
        + (_as_float(config.get("confidence_feature_weight"), 0.07) or 0.07) * feature_count
        + (_as_float(config.get("confidence_margin_weight"), 0.35) or 0.35) * max(0.0, margin),
    )

    top_components = sorted(
        components,
        key=lambda item: float(item.get("risk_component") or 0.0),
        reverse=True,
    )[:5]

    return {
        "state": normalized["state"],
        "p_s0": normalized["p_s0"],
        "p_s1": normalized["p_s1"],
        "p_s2": normalized["p_s2"],
        "confidence": confidence,
        "evidence": {
            "inference_version": "state_inference_v3",
            "inference_mode": "metric_components" if components else "risk_features_only",
            "profile": {
                "id": config.get("id"),
                "name": config.get("name"),
                "version": config.get("version"),
            },
            "score_breakdown": {
                "s0": state_scores["s0"],
                "s1": state_scores["s1"],
                "s2": state_scores["s2"],
            },
            "score_model": {
                "kind": "feature_score_softmax",
                "softmax_temperature": softmax_temperature,
            },
            "feature_values": features,
            "feature_transforms": state_feature_inputs,
            "feature_contributions": state_feature_contributions,
            "score_weights": score_weights,
            "logits": {
                "s0": state_scores["s0"],
                "s1": state_scores["s1"],
                "s2": state_scores["s2"],
            },
            "summary": {
                "component_count": len(components),
                "max_component_risk": max_component_risk,
                "avg_component_risk": avg_component_risk,
                "medium_ratio": medium_ratio,
                "critical_ratio": critical_ratio,
                "effective_metric_risk": features["metric_aggregate_risk"],
                "markov_hint_p_s2": external_markov_risk,
                "overall_risk_hint": external_overall_risk,
                "metric_aggregate_risk_hint": external_metric_risk,
            },
            "top_components": top_components,
        },
    }
