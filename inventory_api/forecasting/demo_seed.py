from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from django.utils import timezone

from inventory_api.forecasting.state_inference_service import infer_state_distribution
from inventory_api.models import Device, DeviceType, RawMetric, ForecastRun, ForecastPoint, StateEstimate


DEMO_PROFILE_PRESETS = {
    "office_weekday": {
        "label": "Офисный сервер",
        "workday_start": "08:30",
        "workday_end": "17:30",
        "lunch_start": "13:00",
        "lunch_end": "14:00",
        "workdays": [0, 1, 2, 3, 4],
        "backup_start": "21:00",
        "backup_end": "23:00",
        "backup_days": [0, 1, 2, 3, 4],
    },
    "always_on": {
        "label": "Круглосуточный сервис",
        "workday_start": "00:00",
        "workday_end": "23:59",
        "lunch_start": "00:00",
        "lunch_end": "00:00",
        "workdays": [0, 1, 2, 3, 4, 5, 6],
        "backup_start": "02:00",
        "backup_end": "04:00",
        "backup_days": [0, 1, 2, 3, 4, 5, 6],
    },
}

DEMO_METRIC_UNITS = {
    "cpu_load_total": "%",
    "mem_usage_percent": "%",
    "net_bytes_sent": "KB/s",
    "net_bytes_recv": "KB/s",
    "ping_latency_gateway": "ms",
    "system_temperature": "C",
    "storcli_drive_temperature": "C",
    "storcli_predictive_failure_count": "count",
}

DEMO_METRIC_LIMITS = {
    "cpu_load_total": (1.0, 98.0),
    "mem_usage_percent": (8.0, 98.0),
    "net_bytes_sent": (10.0, 10000.0),
    "net_bytes_recv": (10.0, 10000.0),
    "ping_latency_gateway": (1.0, 250.0),
    "system_temperature": (22.0, 85.0),
    "storcli_drive_temperature": (20.0, 72.0),
    "storcli_predictive_failure_count": (0.0, 1.0),
}

DEMO_BASE_SNAPSHOT = {
    "cpu_load_total": 12.0,
    "mem_usage_percent": 46.0,
    "net_bytes_sent": 180.0,
    "net_bytes_recv": 220.0,
    "ping_latency_gateway": 8.0,
    "system_temperature": 32.0,
    "storcli_drive_temperature": 29.0,
    "storcli_predictive_failure_count": 0.0,
}

DEMO_FORECAST_SPREAD = {
    "cpu_load_total": 6.5,
    "mem_usage_percent": 5.0,
    "net_bytes_sent": 260.0,
    "net_bytes_recv": 280.0,
    "ping_latency_gateway": 4.0,
    "system_temperature": 2.2,
    "storcli_drive_temperature": 1.9,
    "storcli_predictive_failure_count": 0.12,
}

DEMO_DEGRADATION_MAX_UPLIFT = {
    "cpu_load_total": 26.0,
    "mem_usage_percent": 24.0,
    "net_bytes_sent": 1500.0,
    "net_bytes_recv": 1350.0,
    "ping_latency_gateway": 26.0,
    "system_temperature": 12.0,
    "storcli_drive_temperature": 10.0,
    "storcli_predictive_failure_count": 1.0,
}

DEMO_SCENARIO_DEFAULTS = {
    "degraded_metric_codes": [],
    "degradation_strength": 0.0,
    "bad_mode_persistence": 0.0,
}
DEMO_SCENARIO_MAX_DEGRADATION_STRENGTH = 3.0
DEMO_SCENARIO_MAX_BAD_MODE_PERSISTENCE = 1.0


def _horizon_delta(horizon: str) -> timedelta:
    return {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }[horizon]


def _clamp(metric_code: str, value: float) -> float:
    low, high = DEMO_METRIC_LIMITS[metric_code]
    return max(low, min(high, float(value)))


def _ensure_demo_device(serial: str | None = None):
    serial = (serial or "").strip() or "DEMO-SARIMA-001"
    existing = Device.objects.filter(serial_number=serial).first()
    if existing:
        return existing

    device_type, _ = DeviceType.objects.get_or_create(name="Сервер")
    return Device.objects.create(
        name="Demo Forecast Server",
        serial_number=serial,
        device_type=device_type,
        status="active",
        notes="Auto-created for forecast UI testing",
    )


def _parse_hhmm(value: str | None, default: str) -> int:
    raw = str(value or default).strip() or default
    try:
        hours, minutes = raw.split(":", 1)
        total = int(hours) * 60 + int(minutes)
    except Exception:
        hours, minutes = default.split(":", 1)
        total = int(hours) * 60 + int(minutes)
    return max(0, min(23 * 60 + 59, total))


def _minutes_to_hhmm(total_minutes: int) -> str:
    clamped = max(0, min(23 * 60 + 59, int(total_minutes)))
    return f"{clamped // 60:02d}:{clamped % 60:02d}"


def _normalize_days(value, default_days: list[int]) -> list[int]:
    values = value if isinstance(value, list) else default_days
    out = []
    for item in values:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6 and day not in out:
            out.append(day)
    return sorted(out or list(default_days))


def _normalize_demo_profile(profile_code: str | None = None, overrides: dict | None = None) -> dict:
    code = str(profile_code or "office_weekday").strip().lower()
    if code not in DEMO_PROFILE_PRESETS:
        code = "office_weekday"
    preset = DEMO_PROFILE_PRESETS[code]
    src = overrides if isinstance(overrides, dict) else {}

    workday_start = _parse_hhmm(src.get("workday_start"), preset["workday_start"])
    workday_end = _parse_hhmm(src.get("workday_end"), preset["workday_end"])
    lunch_start = _parse_hhmm(src.get("lunch_start"), preset["lunch_start"])
    lunch_end = _parse_hhmm(src.get("lunch_end"), preset["lunch_end"])
    backup_start = _parse_hhmm(src.get("backup_start"), preset["backup_start"])
    backup_end = _parse_hhmm(src.get("backup_end"), preset["backup_end"])

    return {
        "code": code,
        "label": preset["label"],
        "workday_start": _minutes_to_hhmm(workday_start),
        "workday_end": _minutes_to_hhmm(workday_end),
        "lunch_start": _minutes_to_hhmm(lunch_start),
        "lunch_end": _minutes_to_hhmm(lunch_end),
        "backup_start": _minutes_to_hhmm(backup_start),
        "backup_end": _minutes_to_hhmm(backup_end),
        "workdays": _normalize_days(src.get("workdays"), preset["workdays"]),
        "backup_days": _normalize_days(src.get("backup_days"), preset["backup_days"]),
        "workday_start_min": workday_start,
        "workday_end_min": workday_end,
        "lunch_start_min": lunch_start,
        "lunch_end_min": lunch_end,
        "backup_start_min": backup_start,
        "backup_end_min": backup_end,
    }


def _normalize_metric_codes(value) -> list[str]:
    values = value if isinstance(value, list) else []
    out = []
    for item in values:
        metric_code = str(item or "").strip()
        if metric_code in DEMO_METRIC_UNITS and metric_code not in out:
            out.append(metric_code)
    return out


def _normalize_demo_scenario(scenario_config: dict | None = None) -> dict:
    src = scenario_config if isinstance(scenario_config, dict) else {}

    def _float_field(key: str, default: float, max_value: float = 1.0) -> float:
        try:
            value = float(src.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(0.0, min(float(max_value), value))

    return {
        "degraded_metric_codes": _normalize_metric_codes(src.get("degraded_metric_codes")),
        "degradation_strength": _float_field(
            "degradation_strength",
            DEMO_SCENARIO_DEFAULTS["degradation_strength"],
            max_value=DEMO_SCENARIO_MAX_DEGRADATION_STRENGTH,
        ),
        "bad_mode_persistence": _float_field(
            "bad_mode_persistence",
            DEMO_SCENARIO_DEFAULTS["bad_mode_persistence"],
            max_value=DEMO_SCENARIO_MAX_BAD_MODE_PERSISTENCE,
        ),
    }


def _resolve_history_window(
    *,
    history_start_at=None,
    history_end_at=None,
    raw_history_days: int = 30,
    step_minutes: int = 15,
):
    now = timezone.now()
    end_at = history_end_at if history_end_at is not None else now
    if timezone.is_naive(end_at):
        end_at = timezone.make_aware(end_at, timezone.get_current_timezone())
    start_at = history_start_at if history_start_at is not None else (end_at - timedelta(days=max(1, raw_history_days)))
    if timezone.is_naive(start_at):
        start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
    if start_at >= end_at:
        start_at = end_at - timedelta(days=1)
    aligned_end = end_at.replace(second=0, microsecond=0)
    minute = aligned_end.minute - (aligned_end.minute % max(1, step_minutes))
    aligned_end = aligned_end.replace(minute=minute)
    if start_at >= aligned_end:
        start_at = aligned_end - timedelta(days=1)
    return start_at, aligned_end


def _window_factor(minute_of_day: int, start_min: int, end_min: int, edge_min: int = 30) -> float:
    if end_min <= start_min:
        return 0.0
    minute = float(minute_of_day)
    if start_min <= minute <= end_min:
        return 1.0
    if minute < start_min:
        distance = start_min - minute
    else:
        distance = minute - end_min
    if distance >= edge_min:
        return 0.0
    return max(0.0, 1.0 - distance / max(1.0, float(edge_min)))


def _activity_context(ts, profile: dict) -> dict:
    minute = ts.hour * 60 + ts.minute
    weekday = ts.weekday()
    is_workday = weekday in profile["workdays"]
    is_backup_day = weekday in profile["backup_days"]

    work_window = _window_factor(minute, profile["workday_start_min"], profile["workday_end_min"], edge_min=50) if is_workday else 0.0
    lunch_window = _window_factor(minute, profile["lunch_start_min"], profile["lunch_end_min"], edge_min=15) if is_workday else 0.0
    backup_window = _window_factor(minute, profile["backup_start_min"], profile["backup_end_min"], edge_min=20) if is_backup_day else 0.0

    work_pressure = work_window * (1.0 - 0.58 * lunch_window)
    idle_floor = 0.18 if is_workday else 0.10
    monday_boost = 0.10 if weekday == 0 and minute < 11 * 60 and is_workday else 0.0
    friday_relief = 0.12 if weekday == 4 and minute > 16 * 60 and is_workday else 0.0
    day_phase = math.sin(((minute / 1440.0) * 2.0 * math.pi) - math.pi / 2.0)
    week_phase = math.sin((((weekday + minute / 1440.0) / 7.0) * 2.0 * math.pi))

    return {
        "minute_of_day": minute,
        "weekday": weekday,
        "is_workday": is_workday,
        "work_pressure": max(0.0, work_pressure),
        "backup_pressure": max(0.0, backup_window),
        "idle_floor": idle_floor,
        "monday_boost": monday_boost,
        "friday_relief": friday_relief,
        "day_phase": day_phase,
        "week_phase": week_phase,
    }


def _progress_ratio(ts, start_at, end_at) -> float:
    total = max(1.0, (end_at - start_at).total_seconds())
    elapsed = max(0.0, (ts - start_at).total_seconds())
    return min(1.35, elapsed / total)


def _apply_demo_degradation(metric_code: str, value: float, *, ctx: dict, progress: float, scenario: dict | None = None) -> float:
    scenario = scenario or DEMO_SCENARIO_DEFAULTS
    if metric_code not in set(scenario.get("degraded_metric_codes") or []):
        return _clamp(metric_code, value)

    strength = max(
        0.0,
        min(DEMO_SCENARIO_MAX_DEGRADATION_STRENGTH, float(scenario.get("degradation_strength", 0.0) or 0.0)),
    )
    persistence = max(0.0, min(1.0, float(scenario.get("bad_mode_persistence", 0.0) or 0.0)))
    progress_curve = max(0.0, min(1.0, float(progress))) ** 1.35
    pressure = max(0.0, 0.55 * float(ctx.get("work_pressure", 0.0)) + 0.45 * float(ctx.get("backup_pressure", 0.0)))
    base_uplift = DEMO_DEGRADATION_MAX_UPLIFT.get(metric_code, 0.0)

    if metric_code == "storcli_predictive_failure_count":
        uplift = base_uplift * max(progress_curve * strength, progress_curve * 0.65 * persistence)
    else:
        uplift = base_uplift * ((0.85 * strength * progress_curve) + (0.15 * persistence * (0.35 + pressure)))
    return _clamp(metric_code, value + uplift)


def _target_vector(ts, profile: dict, start_at, end_at, scenario: dict | None = None) -> dict:
    ctx = _activity_context(ts, profile)
    progress = _progress_ratio(ts, start_at, end_at)

    cpu = 8.0 + 36.0 * ctx["work_pressure"] + 11.0 * ctx["backup_pressure"] + 2.5 * max(0.0, ctx["week_phase"])
    cpu += 9.0 * ctx["monday_boost"] - 8.0 * ctx["friday_relief"] + 2.5 * max(0.0, ctx["day_phase"])

    mem = 38.0 + 16.0 * ctx["work_pressure"] + 9.0 * ctx["backup_pressure"] + 7.0 * progress + 1.8 * max(0.0, ctx["week_phase"])
    net_sent = 120.0 + 920.0 * ctx["work_pressure"] + 1750.0 * ctx["backup_pressure"] + 140.0 * max(0.0, ctx["week_phase"])
    net_recv = 160.0 + 1080.0 * ctx["work_pressure"] + 1220.0 * ctx["backup_pressure"] + 170.0 * max(0.0, ctx["week_phase"])
    ping = 6.5 + 7.0 * ctx["work_pressure"] + 12.0 * ctx["backup_pressure"] + 0.028 * cpu
    temp = 28.0 + 0.27 * cpu + 0.05 * mem + 2.4 * ctx["backup_pressure"] + 0.9 * max(0.0, ctx["day_phase"])
    storcli_temp = 27.0 + 0.17 * cpu + 4.6 * ctx["backup_pressure"] + 0.035 * (net_sent / 100.0)

    return {
        "cpu_load_total": _apply_demo_degradation("cpu_load_total", cpu, ctx=ctx, progress=progress, scenario=scenario),
        "mem_usage_percent": _apply_demo_degradation("mem_usage_percent", mem, ctx=ctx, progress=progress, scenario=scenario),
        "net_bytes_sent": _apply_demo_degradation("net_bytes_sent", net_sent, ctx=ctx, progress=progress, scenario=scenario),
        "net_bytes_recv": _apply_demo_degradation("net_bytes_recv", net_recv, ctx=ctx, progress=progress, scenario=scenario),
        "ping_latency_gateway": _apply_demo_degradation("ping_latency_gateway", ping, ctx=ctx, progress=progress, scenario=scenario),
        "system_temperature": _apply_demo_degradation("system_temperature", temp, ctx=ctx, progress=progress, scenario=scenario),
        "storcli_drive_temperature": _apply_demo_degradation("storcli_drive_temperature", storcli_temp, ctx=ctx, progress=progress, scenario=scenario),
    }


def _smooth_metric(metric_code: str, previous: float, target: float, rng: random.Random, *, scenario: dict | None = None) -> float:
    config = {
        "cpu_load_total": (0.26, 3.2),
        "mem_usage_percent": (0.12, 0.8),
        "net_bytes_sent": (0.34, 65.0),
        "net_bytes_recv": (0.34, 72.0),
        "ping_latency_gateway": (0.24, 0.9),
        "system_temperature": (0.18, 0.45),
        "storcli_drive_temperature": (0.16, 0.35),
    }
    alpha, sigma = config[metric_code]
    scenario = scenario or DEMO_SCENARIO_DEFAULTS
    selected = metric_code in set(scenario.get("degraded_metric_codes") or [])
    persistence = max(0.0, min(1.0, float(scenario.get("bad_mode_persistence", 0.0) or 0.0))) if selected else 0.0
    is_recovery = target < previous
    effective_alpha = alpha * (1.0 + 0.20 * persistence) if not is_recovery else max(0.03, alpha * (1.0 - 0.75 * persistence))
    noise = rng.gauss(0.0, sigma * (0.85 if selected else 1.0))
    next_value = previous + effective_alpha * (target - previous) + noise
    return _clamp(metric_code, next_value)


def _seed_raw_history(
    device,
    *,
    start_at,
    end_at,
    profile: dict,
    scenario: dict | None = None,
    step_minutes: int = 15,
):
    rng = random.Random(f"demo-raw-{device.id}-{start_at.isoformat()}-{end_at.isoformat()}-{profile['code']}")
    rows = []
    ts = start_at
    step = timedelta(minutes=max(1, step_minutes))

    previous = dict(DEMO_BASE_SNAPSHOT)
    scenario = scenario or DEMO_SCENARIO_DEFAULTS
    previous.update(_target_vector(ts, profile, start_at, end_at, scenario))
    predictive_fail_count = 0.0

    while ts <= end_at:
        target_vector = _target_vector(ts, profile, start_at, end_at, scenario)
        values = {}
        for metric_code in DEMO_BASE_SNAPSHOT.keys():
            if metric_code == "storcli_predictive_failure_count":
                continue
            values[metric_code] = _smooth_metric(
                metric_code,
                previous[metric_code],
                target_vector[metric_code],
                rng,
                scenario=scenario,
            )

        progress = _progress_ratio(ts, start_at, end_at)
        ctx = _activity_context(ts, profile)
        natural_predictive = max(0.0, (values["storcli_drive_temperature"] - 43.0) / 18.0) * max(0.0, min(1.0, progress))
        predictive_target = _apply_demo_degradation(
            "storcli_predictive_failure_count",
            natural_predictive,
            ctx=ctx,
            progress=progress,
            scenario=scenario,
        )
        predictive_fail_count = max(
            predictive_fail_count,
            _clamp(
                "storcli_predictive_failure_count",
                predictive_fail_count + 0.18 * (predictive_target - predictive_fail_count),
            ),
        )
        values["storcli_predictive_failure_count"] = predictive_fail_count

        labels = {
            "demo": True,
            "source": "seed_forecast_demo",
            "profile_code": profile["code"],
        }
        rows.extend([
            RawMetric(device=device, code="cpu_load_total", value=values["cpu_load_total"], unit=DEMO_METRIC_UNITS["cpu_load_total"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="mem_usage_percent", value=values["mem_usage_percent"], unit=DEMO_METRIC_UNITS["mem_usage_percent"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="net_bytes_sent", value=values["net_bytes_sent"], unit=DEMO_METRIC_UNITS["net_bytes_sent"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="net_bytes_recv", value=values["net_bytes_recv"], unit=DEMO_METRIC_UNITS["net_bytes_recv"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="ping_latency_gateway", value=values["ping_latency_gateway"], unit=DEMO_METRIC_UNITS["ping_latency_gateway"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="system_temperature", value=values["system_temperature"], unit=DEMO_METRIC_UNITS["system_temperature"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="storcli_drive_temperature", value=values["storcli_drive_temperature"], unit=DEMO_METRIC_UNITS["storcli_drive_temperature"], timestamp=ts, labels=labels),
            RawMetric(device=device, code="storcli_predictive_failure_count", value=values["storcli_predictive_failure_count"], unit=DEMO_METRIC_UNITS["storcli_predictive_failure_count"], timestamp=ts, labels=labels),
        ])

        previous.update(values)
        ts += step

    if rows:
        RawMetric.objects.bulk_create(rows, batch_size=5000)
    return {
        "created_count": len(rows),
        "latest_snapshot": dict(previous),
    }


def _build_forecast_points(anchor_ts, profile: dict, start_at, end_at, latest_snapshot: dict, rng: random.Random, scenario: dict | None = None):
    horizons = ["24h", "7d", "30d"]
    horizon_weights = {"24h": 0.45, "7d": 0.72, "30d": 0.86}
    horizon_interval = {"24h": 1.0, "7d": 1.45, "30d": 2.05}

    out = {}
    for horizon in horizons:
        target_ts = anchor_ts + _horizon_delta(horizon)
        future_target = _target_vector(target_ts, profile, start_at, end_at + _horizon_delta(horizon), scenario)
        current_weight = 1.0 - horizon_weights[horizon]
        point_map = {}
        for metric_code in DEMO_BASE_SNAPSHOT.keys():
            current_value = float(latest_snapshot.get(metric_code, DEMO_BASE_SNAPSHOT[metric_code]))
            if metric_code == "storcli_predictive_failure_count":
                ctx = _activity_context(target_ts, profile)
                future_value = max(
                    current_value,
                    _apply_demo_degradation(
                        metric_code,
                        future_target.get(metric_code, 0.0),
                        ctx=ctx,
                        progress=_progress_ratio(target_ts, start_at, end_at + _horizon_delta(horizon)),
                        scenario=scenario,
                    ),
                )
                value = _clamp(metric_code, future_value)
            else:
                future_value = future_target.get(metric_code, current_value)
                mean = current_weight * current_value + horizon_weights[horizon] * future_value
                mean += rng.gauss(0.0, DEMO_FORECAST_SPREAD[metric_code] * 0.18 * horizon_interval[horizon])
                value = _clamp(metric_code, mean)

            interval = DEMO_FORECAST_SPREAD[metric_code] * horizon_interval[horizon]
            p10 = _clamp(metric_code, value - interval)
            p50 = value
            p90 = _clamp(metric_code, value + interval)

            point_map[metric_code] = {
                "y_hat": value,
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "target_ts": target_ts,
            }
        out[horizon] = point_map
    return out


def seed_demo_forecasts(
    *,
    serial: str | None = None,
    runs: int = 1,
    clear_existing: bool = False,
    allow_create_demo_device: bool = True,
    with_raw_history: bool = True,
    raw_history_days: int = 30,
    history_start_at=None,
    history_end_at=None,
    profile_code: str | None = None,
    schedule_config: dict | None = None,
    scenario_config: dict | None = None,
):
    devices = Device.objects.all()
    if serial:
        devices = devices.filter(serial_number=serial)
    devices = list(devices)
    if not devices:
        if allow_create_demo_device:
            devices = [_ensure_demo_device(serial)]
        else:
            return {"created_runs": 0, "created_points": 0, "created_states": 0, "detail": "No devices found"}

    if clear_existing:
        deleted_points = ForecastPoint.objects.filter(labels__demo=True).delete()[0]
        deleted_states = StateEstimate.objects.filter(evidence__demo=True).delete()[0]
        deleted_runs = ForecastRun.objects.filter(notes__icontains="[demo]").delete()[0]
        deleted_raw = RawMetric.objects.filter(labels__demo=True).delete()[0]
    else:
        deleted_points = deleted_states = deleted_runs = deleted_raw = 0

    start_at, end_at = _resolve_history_window(
        history_start_at=history_start_at,
        history_end_at=history_end_at,
        raw_history_days=raw_history_days,
    )
    profile = _normalize_demo_profile(profile_code, schedule_config)
    scenario = _normalize_demo_scenario(scenario_config)
    anchor_ts = end_at

    created_runs = 0
    created_points = 0
    created_states = 0
    created_raw = 0

    for device in devices:
        latest_snapshot = dict(DEMO_BASE_SNAPSHOT)
        if with_raw_history:
            raw_payload = _seed_raw_history(
                device,
                start_at=start_at,
                end_at=end_at,
                profile=profile,
                scenario=scenario,
            )
            created_raw += int(raw_payload["created_count"])
            latest_snapshot.update(raw_payload["latest_snapshot"])

        rng = random.Random(f"demo-forecast-{device.id}-{anchor_ts.isoformat()}-{profile['code']}")
        for _ in range(max(1, runs)):
            run = ForecastRun.objects.create(
                device=device,
                model_kind="ensemble",
                horizon_set="24h,7d,30d",
                status="success",
                started_at=anchor_ts - timedelta(seconds=2),
                finished_at=anchor_ts,
                parameters={
                    "mode": "demo_seed",
                    "source": "seed_demo_forecasts",
                    "history_start_at": start_at.isoformat(),
                    "history_end_at": end_at.isoformat(),
                    "profile_code": profile["code"],
                    "profile_label": profile["label"],
                    "scenario": scenario,
                    "schedule": {
                        "workday_start": profile["workday_start"],
                        "workday_end": profile["workday_end"],
                        "lunch_start": profile["lunch_start"],
                        "lunch_end": profile["lunch_end"],
                        "workdays": profile["workdays"],
                        "backup_start": profile["backup_start"],
                        "backup_end": profile["backup_end"],
                        "backup_days": profile["backup_days"],
                    },
                },
                quality={"demo": True, "profile_code": profile["code"], "scenario": scenario},
                notes="[demo] Synthetic forecast data for UI validation",
            )
            created_runs += 1

            point_payload = _build_forecast_points(anchor_ts, profile, start_at, end_at, latest_snapshot, rng, scenario)
            points_batch = []
            states_batch = []
            for horizon, point_map in point_payload.items():
                state_point_map = {}
                for metric_code, metric_payload in point_map.items():
                    state_point_map[metric_code] = metric_payload["y_hat"]
                    points_batch.append(
                        ForecastPoint(
                            run=run,
                            device=device,
                            metric_code=metric_code,
                            horizon=horizon,
                            target_ts=metric_payload["target_ts"],
                            model_kind="ensemble",
                            y_hat=metric_payload["y_hat"],
                            p10=metric_payload["p10"],
                            p50=metric_payload["p50"],
                            p90=metric_payload["p90"],
                            alpha=round(rng.uniform(0.25, 0.75), 3),
                            labels={
                                "demo": True,
                                "seed": "forecast_ui",
                                "profile_code": profile["code"],
                                "profile_label": profile["label"],
                                "scenario": scenario,
                            },
                        )
                    )

                state_result = infer_state_distribution(
                    points_by_metric=state_point_map,
                    risk_features={"source_model": "demo_seed"},
                )
                states_batch.append(
                    StateEstimate(
                        run=run,
                        device=device,
                        horizon=horizon,
                        state=state_result["state"],
                        p_s0=round(float(state_result["p_s0"] or 0.0), 4),
                        p_s1=round(float(state_result["p_s1"] or 0.0), 4),
                        p_s2=round(float(state_result["p_s2"] or 0.0), 4),
                        confidence=round(float(state_result["confidence"] or 0.0), 3),
                        evidence={
                            "demo": True,
                            "profile_code": profile["code"],
                            "scenario": scenario,
                            **(state_result["evidence"] or {}),
                        },
                        timestamp=anchor_ts,
                    )
                )

            if points_batch:
                ForecastPoint.objects.bulk_create(points_batch, batch_size=500)
                created_points += len(points_batch)
            if states_batch:
                StateEstimate.objects.bulk_create(states_batch, batch_size=100)
                created_states += len(states_batch)

    return {
        "created_runs": created_runs,
        "created_points": created_points,
        "created_states": created_states,
        "created_raw_metrics": created_raw,
        "deleted_runs": deleted_runs,
        "deleted_points": deleted_points,
        "deleted_states": deleted_states,
        "deleted_raw_metrics": deleted_raw,
        "history_start_at": start_at.isoformat(),
        "history_end_at": end_at.isoformat(),
        "profile_code": profile["code"],
        "profile_label": profile["label"],
        "scenario": scenario,
        "schedule": {
            "workday_start": profile["workday_start"],
            "workday_end": profile["workday_end"],
            "lunch_start": profile["lunch_start"],
            "lunch_end": profile["lunch_end"],
            "workdays": profile["workdays"],
            "backup_start": profile["backup_start"],
            "backup_end": profile["backup_end"],
            "backup_days": profile["backup_days"],
        },
    }
