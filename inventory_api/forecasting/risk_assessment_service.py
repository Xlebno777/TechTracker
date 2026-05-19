from __future__ import annotations

import math
from datetime import timedelta
from statistics import median
from typing import Iterable

from django.utils import timezone

from inventory_api.forecasting.state_inference_service import (
    get_active_state_inference_profile_config,
    normalize_state_probabilities,
)
from inventory_api.models import Device, ForecastPoint, ForecastRun, RawMetric, StateEstimate


DEFAULT_HORIZONS = ["24h", "7d", "30d"]
RISK_RATIO_BASELINE = 0.70
RISK_RATIO_SCALE = 0.30

# Threshold-based risk for non-wear metrics.
BASE_THRESHOLDS = {
    "cpu_load_total": 90.0,
    "mem_usage_percent": 92.0,
    "ping_latency_gateway": 150.0,
    "system_temperature": 80.0,
    "storcli_drive_temperature": 58.0,
    "storcli_predictive_failure_count": 1.0,
}

# Scientific core: Weibull is applied only to wear / aging related channels.
WEAR_WEIBULL_DEFAULTS = {
    "storcli_drive_wear_percent": {"eta": 100.0, "beta": 2.1, "kind": "wear_percent"},
    "storcli_ssd_wear_percent": {"eta": 100.0, "beta": 2.1, "kind": "wear_percent"},
    "nvme_percentage_used": {"eta": 100.0, "beta": 2.0, "kind": "wear_percent"},
    "ssd_tbw_used": {"eta": 1200.0, "beta": 2.4, "kind": "tbw"},
    "disk_tbw_used": {"eta": 1200.0, "beta": 2.4, "kind": "tbw"},
}

# Per-metric risk weights (can be calibrated later with historical outcomes).
BASE_METRIC_WEIGHTS = {
    "cpu_load_total": 1.0,
    "mem_usage_percent": 1.0,
    "net_bytes_sent": 0.7,
    "net_bytes_recv": 0.7,
    "ping_latency_gateway": 1.1,
    "system_temperature": 1.2,
    "storcli_drive_temperature": 1.3,
    "storcli_predictive_failure_count": 1.7,
    "storcli_drive_wear_percent": 1.8,
    "storcli_ssd_wear_percent": 1.8,
    "nvme_percentage_used": 1.8,
    "ssd_tbw_used": 1.8,
    "disk_tbw_used": 1.8,
}

STATE_HISTORY_MIN_SIGNAL = 0.05
STATE_HISTORY_BLEND = 0.25
STATE_HISTORY_WEIGHT_BOOST = 0.35
CURRENT_STATE_MIN_SIGNAL = 0.05
MARKOV_MIN_SUPPORT_TRANSITIONS = 24.0

DEFAULT_MARKOV_MATRIX = [
    [0.92, 0.08, 0.0],
    [0.0, 0.86, 0.14],
    [0.0, 0.0, 1.0],
]

STATE_KEYS = ("s0", "s1", "s2")

class RiskAssessmentError(RuntimeError):
    status_code = 400


class RiskAssessmentNotFoundError(RiskAssessmentError):
    status_code = 404


class RiskAssessmentPrerequisiteError(RiskAssessmentError):
    status_code = 409


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


def _as_float(value, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _is_percent_metric(metric_code: str) -> bool:
    raw = str(metric_code or "").strip().lower()
    if raw in {"cpu_load_total", "mem_usage_percent"}:
        return True
    return "percent" in raw or raw.endswith("_pct") or raw.endswith("_percentage")


def _metric_bounds(metric_code: str) -> tuple[float, float | None]:
    raw = str(metric_code or "").strip().lower()
    if "temp" in raw or "temperature" in raw:
        return 0.0, None
    if _is_percent_metric(raw):
        return 0.0, 100.0
    return 0.0, None


def _clamp_metric_value(metric_code: str, value: float | None) -> float | None:
    if value is None:
        return None
    out = float(value)
    min_v, max_v = _metric_bounds(metric_code)
    out = max(min_v, out)
    if max_v is not None:
        out = min(max_v, out)
    return out


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    q = _clamp(q, 0.0, 1.0)
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    idx = q * (len(xs) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return xs[lo]
    frac = idx - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _horizon_seconds(horizon: str) -> int:
    raw = str(horizon or "").strip().lower()
    if raw.endswith("h"):
        hours = int(raw[:-1] or "0")
        return max(3600, int(hours * 3600))
    if raw.endswith("d"):
        days = int(raw[:-1] or "1")
        return max(3600, int(days * 86400))
    return 86400


def _sort_horizon(value: str) -> tuple[int, str]:
    raw = str(value or "").strip().lower()
    if raw.endswith("h"):
        return int(raw[:-1] or "0"), raw
    if raw.endswith("d"):
        return int(raw[:-1] or "0") * 24, raw
    return 10_000, raw


def _parse_horizons(horizons: Iterable[str] | None) -> list[str]:
    if not horizons:
        return list(DEFAULT_HORIZONS)
    out = []
    for item in horizons:
        raw = str(item or "").strip()
        if raw:
            out.append(raw)
    if not out:
        return list(DEFAULT_HORIZONS)
    uniq = sorted(set(out), key=_sort_horizon)
    return uniq


def _risk_level(value: float) -> str:
    if value >= 0.85:
        return "critical"
    if value >= 0.65:
        return "high"
    if value >= 0.4:
        return "medium"
    return "low"


def _ratio_to_risk(ratio: float | None) -> float:
    if ratio is None:
        return 0.0
    return _clamp((float(ratio) - RISK_RATIO_BASELINE) / RISK_RATIO_SCALE)


def _infer_weibull_cfg(metric_code: str, labels: dict | None) -> dict | None:
    raw = str(metric_code or "").strip().lower()
    cfg = WEAR_WEIBULL_DEFAULTS.get(raw)

    if cfg is None:
        if "wear" in raw or "tbw" in raw or "percentage_used" in raw or "life_left" in raw:
            cfg = {"eta": 100.0, "beta": 2.0, "kind": "wear_percent"}
        else:
            return None

    labels = labels or {}
    eta = _as_float(labels.get("eta"), cfg.get("eta"))
    eta = _as_float(labels.get("tbw_total"), eta)
    beta = _as_float(labels.get("beta"), cfg.get("beta"))
    kind = str(labels.get("weibull_kind") or cfg.get("kind") or "wear_percent")
    if eta is None or eta <= 0 or beta is None or beta <= 0:
        return None
    return {"eta": eta, "beta": beta, "kind": kind}


def _normalize_wear_t(metric_code: str, value: float | None, *, kind: str, eta: float) -> float | None:
    if value is None:
        return None
    raw_code = str(metric_code or "").strip().lower()
    x = float(value)

    if kind == "tbw":
        return max(0.0, x)

    # Percent-like wear convention.
    if "life_left" in raw_code:
        x = 100.0 - x
    x = _clamp_metric_value(raw_code, x)
    if x is None:
        return None
    if eta == 100.0:
        return _clamp(x, 0.0, 100.0)
    return max(0.0, x)


def _weibull_survival(t: float, eta: float, beta: float) -> float:
    if eta <= 0 or beta <= 0:
        return 0.0
    x = max(0.0, t) / eta
    return math.exp(-(x ** beta))


def _weibull_conditional_failure(t0: float, tf: float, eta: float, beta: float) -> float:
    if tf < t0:
        tf = t0
    s0 = _weibull_survival(t0, eta, beta)
    sf = _weibull_survival(tf, eta, beta)
    if s0 <= 1e-12:
        return 1.0
    return _clamp(1.0 - (sf / s0))


def _threshold_from_history(
    metric_code: str,
    history_q95: float | None,
    *,
    base_threshold: float | None,
    personalized: bool,
    device_type_name: str,
) -> tuple[float | None, str]:
    source_parts = []
    threshold = _as_float(base_threshold, None)
    if threshold is not None:
        source_parts.append("base")

    if personalized and history_q95 is not None:
        hist_candidate = max(1e-6, history_q95 * 1.10)
        if threshold is None:
            threshold = hist_candidate
            source_parts.append("history_q95")
        else:
            threshold = 0.65 * threshold + 0.35 * hist_candidate
            source_parts.append("history_blend")

    if threshold is None and _is_percent_metric(metric_code):
        threshold = 90.0
        source_parts.append("percent_fallback")

    # Personalization by class of server.
    dtype = str(device_type_name or "").strip().lower()
    if threshold is not None and personalized:
        if ("storage" in dtype or "raid" in dtype) and "temperature" in metric_code:
            threshold *= 0.95
            source_parts.append("profile_storage_temp")
        if ("hyper-v" in dtype or "virtual" in dtype or "vm" in dtype) and metric_code in {"cpu_load_total", "mem_usage_percent"}:
            threshold *= 0.95
            source_parts.append("profile_virtual_headroom")

    if threshold is not None:
        threshold = max(1e-6, float(threshold))
    return threshold, "+".join(source_parts) if source_parts else "none"


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    out = [[0.0, 0.0, 0.0] for _ in range(3)]
    for i in range(3):
        for j in range(3):
            out[i][j] = (
                a[i][0] * b[0][j]
                + a[i][1] * b[1][j]
                + a[i][2] * b[2][j]
            )
    return out


def _mat_pow(base: list[list[float]], k: int) -> list[list[float]]:
    result = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    power = [row[:] for row in base]
    steps = max(1, int(k))
    while steps > 0:
        if steps & 1:
            result = _mat_mul(result, power)
        power = _mat_mul(power, power)
        steps >>= 1
    return result


def _vec_mul(v: list[float], m: list[list[float]]) -> list[float]:
    out = [
        v[0] * m[0][0] + v[1] * m[1][0] + v[2] * m[2][0],
        v[0] * m[0][1] + v[1] * m[1][1] + v[2] * m[2][1],
        v[0] * m[0][2] + v[1] * m[1][2] + v[2] * m[2][2],
    ]
    total = sum(out)
    if total > 0:
        out = [x / total for x in out]
    return [_clamp(x) for x in out]


def _collect_transition_counts(states: list[str]) -> dict[str, float]:
    out = {"n00": 0.0, "n01": 0.0, "n11": 0.0, "n12": 0.0}
    if len(states) < 2:
        return out
    for prev, curr in zip(states[:-1], states[1:]):
        if prev == "s0":
            if curr == "s0":
                out["n00"] += 1.0
            elif curr in ("s1", "s2"):
                out["n01"] += 1.0
        elif prev == "s1":
            if curr in ("s0", "s1"):
                out["n11"] += 1.0
            elif curr == "s2":
                out["n12"] += 1.0
    return out


def _estimate_transition_matrix(
    device: Device,
    *,
    horizon: str,
    lookback_days: int,
    smoothing: float,
    type_blend: float,
) -> tuple[list[list[float]], dict]:
    since = timezone.now() - timedelta(days=max(1, lookback_days))

    device_states = list(
        StateEstimate.objects
        .filter(device=device, horizon=horizon, timestamp__gte=since, state__in=STATE_KEYS)
        .order_by("timestamp", "id")
        .values_list("state", flat=True)
    )
    dev_counts = _collect_transition_counts(device_states)

    peer_counts = {"n00": 0.0, "n01": 0.0, "n11": 0.0, "n12": 0.0}
    if device.device_type_id:
        peer_states = list(
            StateEstimate.objects
            .filter(
                device__device_type_id=device.device_type_id,
                horizon=horizon,
                timestamp__gte=since,
                state__in=STATE_KEYS,
            )
            .exclude(device_id=device.id)
            .select_related("device")
            .order_by("device_id", "timestamp", "id")
            .values_list("device_id", "state")
        )
        by_device: dict[int, list[str]] = {}
        for device_id, state in peer_states:
            by_device.setdefault(device_id, []).append(state)
        for seq in by_device.values():
            cnt = _collect_transition_counts(seq)
            for k in peer_counts:
                peer_counts[k] += cnt[k]

    blend = max(0.0, float(type_blend))
    smooth = max(0.001, float(smoothing))
    n00 = dev_counts["n00"] + blend * peer_counts["n00"]
    n01 = dev_counts["n01"] + blend * peer_counts["n01"]
    n11 = dev_counts["n11"] + blend * peer_counts["n11"]
    n12 = dev_counts["n12"] + blend * peer_counts["n12"]

    d0 = n00 + n01
    d1 = n11 + n12
    if d0 <= 0 and d1 <= 0:
        matrix = [row[:] for row in DEFAULT_MARKOV_MATRIX]
    else:
        p00 = (n00 + smooth) / (n00 + n01 + 2.0 * smooth)
        p01 = 1.0 - p00
        p11 = (n11 + smooth) / (n11 + n12 + 2.0 * smooth)
        p12 = 1.0 - p11
        matrix = [
            [_clamp(p00, 0.001, 0.999), _clamp(p01, 0.001, 0.999), 0.0],
            [0.0, _clamp(p11, 0.001, 0.999), _clamp(p12, 0.001, 0.999)],
            [0.0, 0.0, 1.0],
        ]

    meta = {
        "device_transitions": int(sum(dev_counts.values())),
        "peer_transitions": int(sum(peer_counts.values())),
        "smoothing": smooth,
        "type_blend": blend,
        "default_matrix_used": int(sum(dev_counts.values()) + sum(peer_counts.values()) == 0),
    }
    return matrix, meta


def _model_kind_label(model_kind: str | None) -> str:
    raw = str(model_kind or "").strip().lower()
    if raw == "ensemble":
        return "Оркестр"
    if raw == "sarima":
        return "SARIMA"
    if raw == "lstm":
        return "LSTM"
    if raw == "auto":
        return "Авто"
    return raw or "неизвестный источник"


def _get_required_state_estimate(
    device: Device,
    horizon: str,
    *,
    run: ForecastRun | None,
) -> StateEstimate:
    qs = StateEstimate.objects.filter(device=device, horizon=horizon)
    if run is not None:
        qs = qs.filter(run=run)
    latest = (
        qs
        .order_by("-run__created_at", "-created_at", "-id")
        .first()
    )
    if latest is None:
        source_label = _model_kind_label(getattr(run, "model_kind", None))
        run_hint = f"run #{run.id}" if run is not None else "выбранного прогноза"
        raise RiskAssessmentPrerequisiteError(
            f"Расчет риска остановлен: для устройства «{device.name}» "
            f"не найдено рассчитанное состояние S0/S1/S2 (StateEstimate) "
            f"на горизонте {horizon} для источника «{source_label}» ({run_hint}). "
            f"Сначала запустите прогноз и дождитесь расчета состояния."
        )
    if latest.p_s0 is None or latest.p_s1 is None or latest.p_s2 is None:
        source_label = _model_kind_label(getattr(run, "model_kind", None))
        raise RiskAssessmentPrerequisiteError(
            f"Расчет риска остановлен: состояние S0/S1/S2 на горизонте {horizon} "
            f"для источника «{source_label}» найдено, но заполнено не полностью. "
            f"Сначала выполните корректный запуск прогноза."
        )
    return latest


def _extract_current_state_probs(
    device: Device,
    horizon: str,
    *,
    run: ForecastRun | None,
) -> dict[str, float]:
    latest = _get_required_state_estimate(device, horizon, run=run)
    normalized = normalize_state_probabilities(
        p_s0=latest.p_s0,
        p_s1=latest.p_s1,
        p_s2=latest.p_s2,
    )
    if normalized["p_s0"] is not None:
        return {
            "s0": normalized["p_s0"],
            "s1": normalized["p_s1"],
            "s2": normalized["p_s2"],
        }
    raise RiskAssessmentPrerequisiteError(
        f"Расчет риска остановлен: состояние S0/S1/S2 на горизонте {horizon} "
        f"не удалось нормализовать. Проверьте данные последнего прогноза."
    )


def _component_history_signal(component: dict | None) -> float:
    if not isinstance(component, dict):
        return 0.0
    risk_component = _clamp(_as_float(component.get("risk_component"), 0.0) or 0.0)
    ratio = _as_float(component.get("ratio"), None)
    proximity = 0.0
    if ratio is not None:
        proximity = _clamp((ratio - 0.70) / 0.30)
    return _clamp(max(risk_component, proximity))


def _collect_state_metric_history(
    device: Device,
    *,
    horizon: str,
    model_kind: str | None,
    limit: int,
) -> dict[str, dict]:
    qs = (
        StateEstimate.objects
        .filter(device=device, horizon=horizon)
        .exclude(evidence={})
        .select_related("run")
        .order_by("-run__created_at", "-created_at", "-id")
    )
    if model_kind in {"sarima", "lstm", "ensemble"}:
        qs = qs.filter(run__model_kind=model_kind)

    rows = list(qs[: max(3, int(limit or 12))])
    out: dict[str, dict[str, float | int | str | None]] = {}
    for idx, row in enumerate(rows):
        evidence = row.evidence if isinstance(row.evidence, dict) else {}
        top_components = evidence.get("top_components")
        if not isinstance(top_components, list):
            continue
        decay = 0.72 ** idx
        for component in top_components:
            if not isinstance(component, dict):
                continue
            metric_code = str(component.get("metric_code") or "").strip()
            if not metric_code:
                continue
            signal = _component_history_signal(component)
            if signal <= 0:
                continue
            bucket = out.setdefault(metric_code, {
                "signal_sum": 0.0,
                "weight_sum": 0.0,
                "count": 0,
                "last_signal": 0.0,
                "last_ratio": None,
                "last_threshold": None,
                "last_value": None,
                "last_model_kind": getattr(row.run, "model_kind", None),
            })
            bucket["signal_sum"] += signal * decay
            bucket["weight_sum"] += decay
            bucket["count"] += 1
            if bucket["count"] == 1:
                bucket["last_signal"] = signal
                bucket["last_ratio"] = _as_float(component.get("ratio"), None)
                bucket["last_threshold"] = _as_float(component.get("threshold"), None)
                bucket["last_value"] = _as_float(component.get("value"), None)
                bucket["last_model_kind"] = getattr(row.run, "model_kind", None)

    normalized: dict[str, dict] = {}
    for metric_code, bucket in out.items():
        signal_sum = float(bucket.get("signal_sum") or 0.0)
        weight_sum = float(bucket.get("weight_sum") or 0.0)
        normalized[metric_code] = {
            "signal": _clamp(signal_sum / weight_sum) if weight_sum > 0 else 0.0,
            "count": int(bucket.get("count") or 0),
            "last_signal": _clamp(_as_float(bucket.get("last_signal"), 0.0) or 0.0),
            "last_ratio": _as_float(bucket.get("last_ratio"), None),
            "last_threshold": _as_float(bucket.get("last_threshold"), None),
            "last_value": _as_float(bucket.get("last_value"), None),
            "last_model_kind": bucket.get("last_model_kind"),
        }
    return normalized


def _pick_latest_success_point(
    *,
    device: Device,
    horizon: str,
    metric_code: str,
    preferred_kind: str | None,
) -> ForecastPoint | None:
    base_qs = (
        ForecastPoint.objects
        .filter(
            device=device,
            horizon=horizon,
            metric_code=metric_code,
            run__status="success",
        )
        .select_related("run")
        .order_by("-run__created_at", "-target_ts", "-id")
    )

    if preferred_kind in {"sarima", "lstm", "ensemble"}:
        picked = base_qs.filter(run__model_kind=preferred_kind).first()
        if picked is not None:
            return picked

    return base_qs.first()


def _supplement_rows_from_state_history(
    *,
    device: Device,
    horizon: str,
    rows: list[ForecastPoint],
    state_metric_history: dict[str, dict],
    preferred_kind: str | None,
) -> list[ForecastPoint]:
    existing_codes = {str(row.metric_code or "").strip() for row in rows if row.metric_code}
    supplemented = list(rows)
    for metric_code, meta in state_metric_history.items():
        if metric_code in existing_codes:
            continue
        signal = _clamp(_as_float(meta.get("signal"), 0.0) or 0.0)
        if signal < STATE_HISTORY_MIN_SIGNAL:
            continue
        point = _pick_latest_success_point(
            device=device,
            horizon=horizon,
            metric_code=metric_code,
            preferred_kind=preferred_kind,
        )
        if point is None:
            continue
        supplemented.append(point)
        existing_codes.add(metric_code)
    return supplemented


def _state_relevant_metric_codes() -> set[str]:
    config = get_active_state_inference_profile_config()
    thresholds = config.get("thresholds") if isinstance(config, dict) else {}
    out = {
        str(metric_code or "").strip()
        for metric_code, value in (thresholds or {}).items()
        if str(metric_code or "").strip() and _as_float(value, None) is not None
    }
    out.update(WEAR_WEIBULL_DEFAULTS.keys())
    return out


def _collect_current_state_components(
    device: Device,
    *,
    horizon: str,
    run: ForecastRun | None,
) -> dict[str, dict]:
    row = _get_required_state_estimate(device, horizon, run=run)
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    top_components = evidence.get("top_components")
    if not isinstance(top_components, list):
        return {}

    out: dict[str, dict] = {}
    for component in top_components:
        if not isinstance(component, dict):
            continue
        metric_code = str(component.get("metric_code") or "").strip()
        if not metric_code:
            continue
        signal = _component_history_signal(component)
        out[metric_code] = {
            "signal": signal,
            "ratio": _as_float(component.get("ratio"), None),
            "threshold": _as_float(component.get("threshold"), None),
            "value": _as_float(component.get("value"), None),
            "risk_component": _clamp(_as_float(component.get("risk_component"), 0.0) or 0.0),
        }
    return out


def _choose_source_run(device: Device, preferred_model_kind: str = "auto") -> ForecastRun | None:
    preferred = str(preferred_model_kind or "auto").strip().lower()
    if preferred in {"ensemble", "sarima", "lstm"}:
        return (
            ForecastRun.objects
            .filter(device=device, model_kind=preferred, status="success")
            .order_by("-created_at", "-id")
            .first()
        )

    for kind in ("ensemble", "sarima", "lstm"):
        run = (
            ForecastRun.objects
            .filter(device=device, model_kind=kind, status="success")
            .order_by("-created_at", "-id")
            .first()
        )
        if run:
            return run
    return None


def _group_forecast_points(
    run: ForecastRun,
    horizons: list[str],
) -> dict[str, list[ForecastPoint]]:
    points = list(
        ForecastPoint.objects
        .filter(run=run, horizon__in=horizons)
        .order_by("horizon", "metric_code", "-target_ts", "-id")
    )
    grouped: dict[str, list[ForecastPoint]] = {h: [] for h in horizons}
    for row in points:
        grouped.setdefault(row.horizon, []).append(row)
    return {h: _select_representative_points(grouped.get(h, [])) for h in horizons}


def _infer_markov_step_seconds(device: Device, *, horizon: str, lookback_days: int) -> int:
    since = timezone.now() - timedelta(days=max(1, int(lookback_days)))
    ts_rows = list(
        StateEstimate.objects
        .filter(device=device, horizon=horizon, timestamp__gte=since)
        .order_by("timestamp", "id")
        .values_list("timestamp", flat=True)[:500]
    )
    diffs = []
    for prev, curr in zip(ts_rows[:-1], ts_rows[1:]):
        delta = (curr - prev).total_seconds()
        if delta > 0:
            diffs.append(delta)

    # Fallback to peers of same device type if own history is too short.
    if len(diffs) < 2 and device.device_type_id:
        peer_rows = list(
            StateEstimate.objects
            .filter(
                device__device_type_id=device.device_type_id,
                horizon=horizon,
                timestamp__gte=since,
            )
            .exclude(device_id=device.id)
            .order_by("device_id", "timestamp", "id")
            .values_list("device_id", "timestamp")[:2000]
        )
        by_device: dict[int, list] = {}
        for device_id, ts in peer_rows:
            by_device.setdefault(device_id, []).append(ts)
        for seq in by_device.values():
            for prev, curr in zip(seq[:-1], seq[1:]):
                delta = (curr - prev).total_seconds()
                if delta > 0:
                    diffs.append(delta)

    if not diffs:
        return 86400
    step = int(round(float(median(diffs))))
    return max(3600, min(step, 86400 * 30))


def _markov_projection_confidence(*, steps: int, matrix_meta: dict | None) -> float:
    meta = matrix_meta if isinstance(matrix_meta, dict) else {}
    transition_count = float(
        int(meta.get("device_transitions") or 0)
        + int(meta.get("peer_transitions") or 0)
    )
    support_floor = max(MARKOV_MIN_SUPPORT_TRANSITIONS, float(max(1, steps)))
    return _clamp(transition_count / support_floor, 0.0, 1.0)


def _risk_for_history_point(point: ForecastPoint) -> float:
    code = str(point.metric_code or "")
    y_hat = _as_float(point.y_hat, None)
    p90 = _as_float(point.p90, y_hat)
    worst_value = _clamp_metric_value(code, p90 if p90 is not None else y_hat)

    labels = point.labels if isinstance(point.labels, dict) else {}
    weibull_cfg = _infer_weibull_cfg(code, labels)
    if weibull_cfg is not None:
        eta = float(weibull_cfg["eta"])
        beta = float(weibull_cfg["beta"])
        kind = str(weibull_cfg["kind"])
        t0 = _normalize_wear_t(code, y_hat, kind=kind, eta=eta)
        tf = _normalize_wear_t(code, worst_value, kind=kind, eta=eta)
        if t0 is not None and tf is not None:
            return _weibull_conditional_failure(t0=t0, tf=tf, eta=eta, beta=beta)

    threshold = _as_float(BASE_THRESHOLDS.get(code), None)
    if threshold is None:
        return 0.0
    if worst_value is None or threshold <= 0:
        return 0.0
    ratio = float(worst_value) / float(threshold)
    return _ratio_to_risk(ratio)


def _aggregate_metric_risk_for_history(points: list[ForecastPoint]) -> float:
    if not points:
        return 0.0
    relevant_codes = _state_relevant_metric_codes()
    weighted_sum = 0.0
    weight_sum = 0.0
    max_risk = 0.0
    for row in points:
        if row.metric_code not in relevant_codes and _infer_weibull_cfg(row.metric_code, row.labels if isinstance(row.labels, dict) else None) is None:
            continue
        risk = _risk_for_history_point(row)
        weight = float(BASE_METRIC_WEIGHTS.get(row.metric_code, 1.0))
        weighted_sum += risk * weight
        weight_sum += weight
        max_risk = max(max_risk, risk)
    weighted_avg = (weighted_sum / weight_sum) if weight_sum > 0 else 0.0
    return _clamp(0.55 * weighted_avg + 0.45 * max_risk)


def _point_sort_value(point: ForecastPoint) -> tuple[float, int]:
    target_ts = getattr(point, "target_ts", None)
    ts_value = target_ts.timestamp() if target_ts else 0.0
    point_id = int(getattr(point, "id", 0) or 0)
    return ts_value, point_id


def _select_representative_points(points: list[ForecastPoint]) -> list[ForecastPoint]:
    """Collapse many horizon points to one representative point per metric.

    Rule:
    - keep point with highest risk score in horizon;
    - on ties, keep latest point.
    """
    best_by_metric: dict[str, tuple[ForecastPoint, float]] = {}
    for row in points or []:
        metric_code = str(getattr(row, "metric_code", "") or "").strip()
        if not metric_code:
            continue
        risk_value = _risk_for_history_point(row)
        current = best_by_metric.get(metric_code)
        if current is None:
            best_by_metric[metric_code] = (row, risk_value)
            continue
        best_row, best_risk = current
        if risk_value > (best_risk + 1e-9):
            best_by_metric[metric_code] = (row, risk_value)
            continue
        if abs(risk_value - best_risk) <= 1e-9 and _point_sort_value(row) > _point_sort_value(best_row):
            best_by_metric[metric_code] = (row, risk_value)
    return [best_by_metric[code][0] for code in sorted(best_by_metric.keys())]


def _mean(values: list[float]) -> float:
    return (sum(values) / len(values)) if values else 0.0


def _trajectory_signal_from_ratios(ratios: list[float]) -> dict:
    clean = [float(v) for v in (ratios or []) if v is not None and math.isfinite(float(v)) and float(v) >= 0.0]
    if not clean:
        return {
            "risk": 0.0,
            "head_mean_ratio": 0.0,
            "tail_mean_ratio": 0.0,
            "max_ratio": 0.0,
            "near_threshold_share": 0.0,
            "above_threshold_share": 0.0,
            "growth_signal": 0.0,
            "tail_pressure": 0.0,
            "points": 0,
        }

    count = len(clean)
    segment = max(1, int(round(count * 0.20)))
    head = clean[:segment]
    tail = clean[-segment:]
    head_mean = _mean(head)
    tail_mean = _mean(tail)
    max_ratio = max(clean)
    near_threshold_share = sum(1 for value in clean if value >= 0.95) / count
    above_threshold_share = sum(1 for value in clean if value >= 1.00) / count
    growth_signal = _clamp((tail_mean - head_mean) / 0.20)
    tail_pressure = _ratio_to_risk(tail_mean)
    risk = _clamp(
        0.35 * tail_pressure
        + 0.25 * near_threshold_share
        + 0.25 * above_threshold_share
        + 0.15 * growth_signal
    )
    return {
        "risk": risk,
        "head_mean_ratio": head_mean,
        "tail_mean_ratio": tail_mean,
        "max_ratio": max_ratio,
        "near_threshold_share": near_threshold_share,
        "above_threshold_share": above_threshold_share,
        "growth_signal": growth_signal,
        "tail_pressure": tail_pressure,
        "points": count,
    }


def _collect_history_values(
    *,
    device: Device,
    metric_codes: list[str],
    lookback_days: int,
) -> dict[str, list[float]]:
    now = timezone.now()
    since = now - timedelta(days=max(1, int(lookback_days)))
    history_values: dict[str, list[float]] = {code: [] for code in metric_codes}
    if not metric_codes:
        return history_values
    raw_qs = (
        RawMetric.objects
        .filter(device=device, code__in=metric_codes, timestamp__gte=since, timestamp__lte=now)
        .order_by("code", "timestamp")
        .values("code", "value")
    )
    for row in raw_qs:
        value = _as_float(row.get("value"), None)
        if value is None:
            continue
        history_values[row["code"]].append(value)
    return history_values


def build_state_risk_features_for_points(
    *,
    device: Device,
    horizon: str,
    points: list[ForecastPoint],
    source_model: str | None = None,
    personalized_thresholds: bool = True,
    threshold_lookback_days: int = 60,
    markov_from_latest_state: bool = True,
) -> dict:
    metric_points_map: dict[str, list[ForecastPoint]] = {}
    for row in points or []:
        code = str(getattr(row, "metric_code", "") or "").strip()
        if not code:
            continue
        metric_points_map.setdefault(code, []).append(row)
    for metric_rows in metric_points_map.values():
        metric_rows.sort(key=_point_sort_value)

    representative_points = _select_representative_points(points or [])
    representative_by_code = {
        str(getattr(row, "metric_code", "") or "").strip(): row
        for row in representative_points
        if str(getattr(row, "metric_code", "") or "").strip()
    }
    metric_codes = sorted({
        code
        for code in metric_points_map.keys()
        if code
    })
    history_values = _collect_history_values(
        device=device,
        metric_codes=metric_codes,
        lookback_days=threshold_lookback_days,
    )
    dtype_name = device.device_type.name if device.device_type_id else ""
    relevant_metric_codes = _state_relevant_metric_codes()
    weighted_risk_sum = 0.0
    weight_sum = 0.0
    max_metric_risk = 0.0
    metric_results = []

    for code in metric_codes:
        metric_rows = metric_points_map.get(code) or []
        if not metric_rows:
            continue
        row = representative_by_code.get(code) or metric_rows[-1]
        if not code:
            continue
        labels = row.labels if isinstance(row.labels, dict) else {}
        weibull_cfg = _infer_weibull_cfg(code, labels)
        is_wear_metric = weibull_cfg is not None
        if code not in relevant_metric_codes and not is_wear_metric:
            continue

        y_hat = _as_float(row.y_hat, None)
        p90 = _as_float(row.p90, y_hat)
        worst_value = _clamp_metric_value(code, p90 if p90 is not None else y_hat)
        history_q95 = _quantile(history_values.get(code, []), 0.95)

        method = "threshold"
        threshold = None
        threshold_source = "none"
        ratio = None
        base_risk = 0.0
        adjusted_risk = 0.0
        trajectory_meta = {
            "mode": "single_point",
            "points": len(metric_rows),
            "risk": 0.0,
        }
        details = {}

        if weibull_cfg is not None:
            eta = float(weibull_cfg["eta"])
            beta = float(weibull_cfg["beta"])
            kind = str(weibull_cfg["kind"])
            first_row = metric_rows[0]
            first_y_hat = _as_float(first_row.y_hat, y_hat)
            t0 = _normalize_wear_t(code, first_y_hat, kind=kind, eta=eta)
            tf = _normalize_wear_t(code, worst_value if worst_value is not None else y_hat, kind=kind, eta=eta)
            if t0 is not None and tf is not None:
                method = "weibull"
                base_risk = _weibull_conditional_failure(t0=t0, tf=tf, eta=eta, beta=beta)
                adjusted_risk = _clamp(base_risk)
                trajectory_meta = {
                    "mode": "weibull",
                    "points": len(metric_rows),
                    "risk": adjusted_risk,
                }
                details = {"eta": eta, "beta": beta, "t0": t0, "tf": tf, "kind": kind}

        if method != "weibull":
            threshold, threshold_source = _threshold_from_history(
                code,
                history_q95,
                base_threshold=BASE_THRESHOLDS.get(code),
                personalized=bool(personalized_thresholds),
                device_type_name=dtype_name,
            )
            point_rows = []
            if threshold is not None and threshold > 0:
                for metric_row in metric_rows:
                    point_y_hat = _as_float(metric_row.y_hat, None)
                    point_p90 = _as_float(metric_row.p90, point_y_hat)
                    point_worst_value = _clamp_metric_value(
                        code,
                        point_p90 if point_p90 is not None else point_y_hat,
                    )
                    point_ratio = None
                    point_risk = 0.0
                    if point_worst_value is not None:
                        point_ratio = float(point_worst_value) / float(threshold)
                        point_risk = _ratio_to_risk(point_ratio)
                    point_rows.append((metric_row, point_worst_value, point_ratio, point_risk))

            if point_rows:
                def _point_rank(item):
                    metric_row, _value, point_ratio, point_risk = item
                    return (
                        float(point_risk),
                        float(point_ratio if point_ratio is not None else -1.0),
                        _point_sort_value(metric_row),
                    )

                best_row, best_value, best_ratio, best_point_risk = max(point_rows, key=_point_rank)
                row = best_row
                y_hat = _as_float(row.y_hat, None)
                p90 = _as_float(row.p90, y_hat)
                worst_value = best_value
                ratio = best_ratio
                base_risk = _clamp(best_point_risk)

                ratios = [entry[2] for entry in point_rows if entry[2] is not None]
                trajectory_stats = _trajectory_signal_from_ratios(ratios)
                trajectory_meta = {
                    "mode": "horizon_trajectory",
                    **trajectory_stats,
                }
                adjusted_risk = _clamp(max(
                    base_risk,
                    0.25 * base_risk + 0.75 * float(trajectory_stats.get("risk", 0.0)),
                ))
            else:
                base_risk = 0.0
                adjusted_risk = 0.0
                trajectory_meta = {
                    "mode": "horizon_trajectory",
                    "points": len(metric_rows),
                    "risk": 0.0,
                }
            details = {
                "ratio": ratio,
                "threshold": threshold,
                "threshold_source": threshold_source,
                "history_q95": history_q95,
                "trajectory": trajectory_meta,
            }

        base_risk = _clamp(base_risk)
        adjusted_risk = _clamp(adjusted_risk if adjusted_risk is not None else base_risk)
        base_weight = float(BASE_METRIC_WEIGHTS.get(code, 1.0))
        weighted_risk_sum += adjusted_risk * base_weight
        weight_sum += base_weight
        max_metric_risk = max(max_metric_risk, adjusted_risk)
        metric_results.append({
            "metric_code": code,
            "method": method,
            "risk": adjusted_risk,
            "base_risk": base_risk,
            "risk_level": _risk_level(adjusted_risk),
            "weight": base_weight,
            "base_weight": base_weight,
            "current_value": None,
            "forecast": {
                "y_hat": y_hat,
                "p90": p90,
                "target_ts": row.target_ts.isoformat() if row.target_ts else None,
                "model_kind": source_model or row.model_kind,
                "run_id": row.run_id,
            },
            "threshold": threshold,
            "threshold_source": threshold_source,
            "ratio": ratio,
            "details": details,
            "trajectory": trajectory_meta,
        })

    weighted_avg = (weighted_risk_sum / weight_sum) if weight_sum > 0 else 0.0
    metric_aggregate_risk = _clamp(0.55 * weighted_avg + 0.45 * max_metric_risk)
    markov_p_s2 = 0.0
    source_kind = str(source_model or "").strip().lower()
    if markov_from_latest_state:
        state_qs = StateEstimate.objects.filter(device=device, horizon=horizon)
        if source_kind in {"sarima", "lstm", "ensemble"}:
            state_qs = state_qs.filter(run__model_kind=source_kind)
        latest_state = state_qs.order_by("-run__created_at", "-created_at", "-id").first()
        if latest_state and latest_state.p_s0 is not None and latest_state.p_s1 is not None and latest_state.p_s2 is not None:
            normalized = normalize_state_probabilities(
                p_s0=latest_state.p_s0,
                p_s1=latest_state.p_s1,
                p_s2=latest_state.p_s2,
            )
            markov_p_s2 = _clamp(_as_float(normalized.get("p_s2"), 0.0) or 0.0)

    return {
        "source_model": source_kind or "unknown",
        "metric_aggregate_risk": metric_aggregate_risk,
        "markov_p_s2": markov_p_s2,
        "metric_results": metric_results,
        "metric_points_total": len(points or []),
        "metric_points_representative": len(representative_points),
        "markov_hint_enabled": bool(markov_from_latest_state),
    }


def _build_risk_history(
    *,
    device: Device,
    horizon: str,
    preferred_model_kind: str,
    history_limit: int,
    overall_weight_markov: float,
) -> list[dict]:
    qs = ForecastRun.objects.filter(device=device, status="success")
    preferred = str(preferred_model_kind or "auto").strip().lower()
    if preferred in {"ensemble", "sarima", "lstm"}:
        qs = qs.filter(model_kind=preferred)
    runs = list(qs.order_by("-created_at", "-id")[:max(3, int(history_limit))])
    if not runs:
        return []

    run_ids = [row.id for row in runs]
    points = list(
        ForecastPoint.objects
        .filter(run_id__in=run_ids, horizon=horizon)
        .order_by("run_id", "metric_code", "-target_ts", "-id")
    )
    points_by_run: dict[int, list[ForecastPoint]] = {}
    for row in points:
        points_by_run.setdefault(row.run_id, []).append(row)

    states = list(
        StateEstimate.objects
        .filter(run_id__in=run_ids, horizon=horizon)
        .order_by("run_id", "-timestamp", "-id")
    )
    state_by_run: dict[int, StateEstimate] = {}
    for row in states:
        if row.run_id not in state_by_run:
            state_by_run[row.run_id] = row

    rows = []
    for run in reversed(runs):
        metric_rows = _select_representative_points(points_by_run.get(run.id) or [])
        metric_risk = _aggregate_metric_risk_for_history(metric_rows)
        state = state_by_run.get(run.id)
        if state is None or state.p_s0 is None or state.p_s1 is None or state.p_s2 is None:
            continue
        normalized = normalize_state_probabilities(
            p_s0=state.p_s0,
            p_s1=state.p_s1,
            p_s2=state.p_s2,
        )
        if normalized["p_s2"] is None:
            continue
        markov_p_s2 = _clamp(normalized["p_s2"])
        overall = _clamp(overall_weight_markov * markov_p_s2 + (1.0 - overall_weight_markov) * metric_risk)
        rows.append({
            "run_id": run.id,
            "run_model_kind": run.model_kind,
            "run_created_at": run.created_at.isoformat() if run.created_at else None,
            "overall_risk": overall,
            "markov_p_s2": markov_p_s2,
            "metric_aggregate_risk": metric_risk,
        })
    return rows


def evaluate_risk_assessment(
    *,
    serial: str | None = None,
    device_id: int | None = None,
    horizons: Iterable[str] | None = None,
    preferred_model_kind: str = "auto",
    personalized_thresholds: bool = True,
    threshold_lookback_days: int = 60,
    markov_lookback_days: int = 120,
    markov_smoothing: float = 1.0,
    type_blend: float = 0.35,
    overall_weight_markov: float = 0.65,
    history_limit: int = 12,
) -> dict:
    devices_qs = Device.objects.all().select_related("device_type")
    if serial:
        devices_qs = devices_qs.filter(serial_number=serial)
    if device_id:
        devices_qs = devices_qs.filter(id=device_id)
    device = devices_qs.first()
    if not device:
        raise RiskAssessmentNotFoundError("Устройство не найдено")

    selected_horizons = _parse_horizons(horizons)
    run = _choose_source_run(device, preferred_model_kind=preferred_model_kind)
    if run is None:
        source_label = _model_kind_label(preferred_model_kind)
        raise RiskAssessmentPrerequisiteError(
            f"Расчет риска остановлен: для устройства «{device.name}» "
            f"не найден успешный прогноз для источника «{source_label}». "
            f"Сначала запустите прогноз и дождитесь его завершения."
        )
    points_by_horizon = _group_forecast_points(run, selected_horizons)

    # Collect current values and history quantiles for metrics that appear in selected forecast horizons.
    all_metric_codes = sorted({
        row.metric_code
        for rows in points_by_horizon.values()
        for row in rows
        if row.metric_code
    })
    now = timezone.now()
    since = now - timedelta(days=max(1, int(threshold_lookback_days)))
    raw_qs = (
        RawMetric.objects
        .filter(device=device, code__in=all_metric_codes, timestamp__gte=since, timestamp__lte=now)
        .order_by("code", "timestamp")
        .values("code", "value", "timestamp")
    )
    history_values: dict[str, list[float]] = {code: [] for code in all_metric_codes}
    for row in raw_qs:
        value = _as_float(row.get("value"), None)
        if value is None:
            continue
        history_values[row["code"]].append(value)

    latest_current = (
        RawMetric.objects
        .filter(device=device, code__in=all_metric_codes, timestamp__lte=now)
        .order_by("code", "-timestamp", "-id")
    )
    current_by_code = {}
    for row in latest_current:
        if row.code not in current_by_code:
            current_by_code[row.code] = row

    dtype_name = device.device_type.name if device.device_type_id else ""
    relevant_metric_codes = _state_relevant_metric_codes()

    overall_weight_markov = _clamp(overall_weight_markov, 0.0, 1.0)
    horizon_payloads = []
    for horizon in selected_horizons:
        rows = list(points_by_horizon.get(horizon) or [])
        if not rows:
            raise RiskAssessmentPrerequisiteError(
                f"Расчет риска остановлен: для устройства «{device.name}» "
                f"нет прогнозных точек на горизонте {horizon} "
                f"для источника «{_model_kind_label(run.model_kind)}». "
                f"Сначала выполните прогноз на этом горизонте."
            )
        original_metric_codes = {str(row.metric_code or "").strip() for row in rows if row.metric_code}
        current_state_components = _collect_current_state_components(device, horizon=horizon, run=run)
        current_active_metric_codes = {
            metric_code
            for metric_code, meta in current_state_components.items()
            if _clamp(_as_float(meta.get("signal"), 0.0) or 0.0) >= CURRENT_STATE_MIN_SIGNAL
        }
        state_metric_history = _collect_state_metric_history(
            device,
            horizon=horizon,
            model_kind=(run.model_kind if run else (preferred_model_kind if preferred_model_kind in {"ensemble", "sarima", "lstm"} else None)),
            limit=max(3, int(history_limit)),
        )
        state_metric_history = {
            metric_code: meta
            for metric_code, meta in state_metric_history.items()
            if metric_code in current_active_metric_codes
        }
        rows = _supplement_rows_from_state_history(
            device=device,
            horizon=horizon,
            rows=rows,
            state_metric_history=state_metric_history,
            preferred_kind=(run.model_kind if run else None),
        )
        metric_results = []
        weighted_risk_sum = 0.0
        weight_sum = 0.0
        max_metric_risk = 0.0

        for row in rows:
            code = row.metric_code
            labels = row.labels if isinstance(row.labels, dict) else {}
            weibull_cfg = _infer_weibull_cfg(code, labels)
            is_wear_metric = weibull_cfg is not None
            if code not in relevant_metric_codes and not is_wear_metric:
                continue
            current_row = current_by_code.get(code)
            current_value = _as_float(getattr(current_row, "value", None), None)
            y_hat = _as_float(row.y_hat, None)
            p90 = _as_float(row.p90, y_hat)
            worst_value = _clamp_metric_value(code, p90 if p90 is not None else y_hat)
            history_q95 = _quantile(history_values.get(code, []), 0.95)

            method = "threshold"
            details = {}
            threshold = None
            threshold_source = "none"
            ratio = None
            risk = 0.0

            if weibull_cfg is not None:
                eta = float(weibull_cfg["eta"])
                beta = float(weibull_cfg["beta"])
                kind = str(weibull_cfg["kind"])
                t0 = _normalize_wear_t(code, current_value if current_value is not None else y_hat, kind=kind, eta=eta)
                tf = _normalize_wear_t(code, worst_value if worst_value is not None else y_hat, kind=kind, eta=eta)
                if t0 is not None and tf is not None:
                    method = "weibull"
                    risk = _weibull_conditional_failure(t0=t0, tf=tf, eta=eta, beta=beta)
                    details = {
                        "eta": eta,
                        "beta": beta,
                        "t0": t0,
                        "tf": tf,
                        "kind": kind,
                    }

            if method != "weibull":
                threshold, threshold_source = _threshold_from_history(
                    code,
                    history_q95,
                    base_threshold=BASE_THRESHOLDS.get(code),
                    personalized=bool(personalized_thresholds),
                    device_type_name=dtype_name,
                )
                if threshold is not None and worst_value is not None and threshold > 0:
                    ratio = float(worst_value) / float(threshold)
                    risk = _ratio_to_risk(ratio)
                else:
                    risk = 0.0
                details = {
                    "ratio": ratio,
                    "threshold": threshold,
                    "threshold_source": threshold_source,
                    "history_q95": history_q95,
                }

            base_risk = _clamp(risk)
            current_state_signal = _clamp(
                _as_float((current_state_components.get(code) or {}).get("signal"), 0.0) or 0.0,
            )
            is_currently_relevant = current_state_signal >= CURRENT_STATE_MIN_SIGNAL
            if not is_wear_metric and not is_currently_relevant and base_risk < CURRENT_STATE_MIN_SIGNAL:
                continue

            history_meta = state_metric_history.get(code) or {}
            state_history_signal = 0.0
            state_history_count = 0
            if is_currently_relevant or base_risk >= CURRENT_STATE_MIN_SIGNAL:
                state_history_signal = _clamp(_as_float(history_meta.get("signal"), 0.0) or 0.0)
                state_history_count = int(history_meta.get("count") or 0)
            adjusted_risk = max(
                base_risk,
                _clamp((1.0 - STATE_HISTORY_BLEND) * base_risk + STATE_HISTORY_BLEND * state_history_signal),
            )

            base_weight = float(BASE_METRIC_WEIGHTS.get(code, 1.0))
            effective_weight = base_weight * (1.0 + STATE_HISTORY_WEIGHT_BOOST * state_history_signal)
            weighted_risk_sum += adjusted_risk * effective_weight
            weight_sum += effective_weight
            max_metric_risk = max(max_metric_risk, adjusted_risk)

            metric_results.append({
                "metric_code": code,
                "method": method,
                "risk": adjusted_risk,
                "base_risk": base_risk,
                "risk_level": _risk_level(adjusted_risk),
                "weight": effective_weight,
                "base_weight": base_weight,
                "current_value": current_value,
                "forecast": {
                    "y_hat": y_hat,
                    "p90": p90,
                    "target_ts": row.target_ts.isoformat() if row.target_ts else None,
                    "model_kind": row.model_kind,
                    "run_id": row.run_id,
                },
                "threshold": threshold,
                "threshold_source": threshold_source,
                "ratio": ratio,
                "current_state_signal": current_state_signal,
                "state_history_signal": state_history_signal,
                "state_history_count": state_history_count,
                "state_history_last_ratio": history_meta.get("last_ratio"),
                "state_history_last_model_kind": history_meta.get("last_model_kind"),
                "supplemented_from_state_history": code not in original_metric_codes,
                "details": details,
                "formula": (
                    "P_fail(h)=1-S(tf)/S(t0), S(t)=exp(-(t/eta)^beta)"
                    if method == "weibull"
                    else "base_risk=clamp((p90/threshold-0.70)/0.30); final_risk=max(base_risk,(1-b)*base_risk+b*state_history_signal)"
                ),
                "formula_inputs": (
                    {
                        "t0": details.get("t0"),
                        "tf": details.get("tf"),
                        "eta": details.get("eta"),
                        "beta": details.get("beta"),
                    }
                    if method == "weibull"
                    else {
                        "p90": p90,
                        "threshold": threshold,
                        "ratio": ratio,
                        "threshold_source": threshold_source,
                        "current_state_signal": current_state_signal,
                        "state_history_signal": state_history_signal,
                        "state_history_count": state_history_count,
                        "history_blend": STATE_HISTORY_BLEND,
                    }
                ),
            })

        weighted_avg = (weighted_risk_sum / weight_sum) if weight_sum > 0 else 0.0
        metric_aggregate_risk = _clamp(0.55 * weighted_avg + 0.45 * max_metric_risk)
        current_state = _extract_current_state_probs(
            device,
            horizon,
            run=run,
        )

        matrix, matrix_meta = _estimate_transition_matrix(
            device,
            horizon=horizon,
            lookback_days=markov_lookback_days,
            smoothing=markov_smoothing,
            type_blend=type_blend,
        )
        markov_step_sec = _infer_markov_step_seconds(
            device,
            horizon=horizon,
            lookback_days=markov_lookback_days,
        )
        horizon_sec = _horizon_seconds(horizon)
        steps = max(1, int(round(horizon_sec / markov_step_sec)))
        projected_matrix = _mat_pow(matrix, steps)
        current_state_vec = [current_state["s0"], current_state["s1"], current_state["s2"]]
        projected_state_raw_vec = _vec_mul(
            current_state_vec,
            projected_matrix,
        )
        markov_raw_projected_p_s2 = projected_state_raw_vec[2]
        markov_confidence = _markov_projection_confidence(
            steps=steps,
            matrix_meta=matrix_meta,
        )
        # Keep long-horizon Markov projection stable when transition history is short:
        # blend the whole projected vector with current state vector, then normalize.
        projected_state_blended_vec = [
            _clamp(markov_confidence * projected_state_raw_vec[idx] + (1.0 - markov_confidence) * current_state_vec[idx])
            for idx in range(3)
        ]
        normalized_projected = normalize_state_probabilities(
            p_s0=projected_state_blended_vec[0],
            p_s1=projected_state_blended_vec[1],
            p_s2=projected_state_blended_vec[2],
        )
        if normalized_projected["p_s0"] is not None:
            projected_state = {
                "s0": normalized_projected["p_s0"],
                "s1": normalized_projected["p_s1"],
                "s2": normalized_projected["p_s2"],
            }
        else:
            projected_state = {
                "s0": current_state["s0"],
                "s1": current_state["s1"],
                "s2": current_state["s2"],
            }
        markov_projected_p_s2 = projected_state["s2"]

        overall_risk = _clamp(
            overall_weight_markov * markov_projected_p_s2
            + (1.0 - overall_weight_markov) * metric_aggregate_risk
        )
        reliability = _clamp(1.0 - overall_risk)

        # Metric contribution in final aggregate.
        denom = sum((item["risk"] * item["weight"]) for item in metric_results)
        for item in metric_results:
            if denom > 0:
                item["contribution"] = (item["risk"] * item["weight"]) / denom
            else:
                item["contribution"] = 0.0
        metric_results.sort(key=lambda x: x["risk"], reverse=True)

        horizon_payloads.append({
            "horizon": horizon,
            "steps": steps,
            "markov_step_sec": markov_step_sec,
            "overall_risk": overall_risk,
            "reliability": reliability,
            "risk_level": _risk_level(overall_risk),
            "metric_aggregate_risk": metric_aggregate_risk,
            "markov_projected_p_s2": markov_projected_p_s2,
            "current_state": current_state,
            "projected_state": projected_state,
            "transition_matrix": matrix,
            "transition_meta": matrix_meta,
            "markov_projection_confidence": markov_confidence,
            "markov_raw_projected_p_s2": markov_raw_projected_p_s2,
            "metrics": metric_results,
            "model_kind_used": run.model_kind if run else "raw_proxy",
            "run_id_used": run.id if run else None,
            "overall_formula": {
                "mode": "weighted_linear_mix",
                "w_markov": overall_weight_markov,
                "w_metric": 1.0 - overall_weight_markov,
            },
        })

    selected_primary_horizon = selected_horizons[0] if selected_horizons else "24h"
    risk_history = _build_risk_history(
        device=device,
        horizon=selected_primary_horizon,
        preferred_model_kind=(run.model_kind if run else preferred_model_kind),
        history_limit=max(3, int(history_limit)),
        overall_weight_markov=overall_weight_markov,
    )

    return {
        "computed_at": timezone.now().isoformat(),
        "device": {
            "id": device.id,
            "name": device.name,
            "serial_number": device.serial_number,
            "device_type": dtype_name,
        },
        "source_run": {
            "id": run.id if run else None,
            "model_kind": run.model_kind if run else None,
            "created_at": run.created_at.isoformat() if run and run.created_at else None,
        },
        "config_used": {
            "preferred_model_kind": preferred_model_kind,
            "personalized_thresholds": bool(personalized_thresholds),
            "threshold_lookback_days": int(threshold_lookback_days),
            "markov_lookback_days": int(markov_lookback_days),
            "markov_smoothing": float(markov_smoothing),
            "type_blend": float(type_blend),
            "overall_weight_markov": float(overall_weight_markov),
            "history_limit": int(max(3, int(history_limit))),
        },
        "horizons": horizon_payloads,
        "risk_history": risk_history,
    }
