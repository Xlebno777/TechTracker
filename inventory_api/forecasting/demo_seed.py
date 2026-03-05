from __future__ import annotations

import math
import random
from datetime import timedelta

from django.utils import timezone

from inventory_api.models import Device, DeviceType, RawMetric, ForecastRun, ForecastPoint, StateEstimate


DEMO_METRICS = {
    "cpu_load_total": (45.0, 10.0),
    "mem_usage_percent": (58.0, 8.0),
    "ping_latency_gateway": (18.0, 6.0),
    "system_temperature": (52.0, 4.0),
    "storcli_predictive_failure_count": (0.2, 0.6),
}


def _horizon_delta(horizon: str) -> timedelta:
    return {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }[horizon]


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


def _estimate_state_from_points(point_map):
    cpu = point_map.get("cpu_load_total", 0.0)
    mem = point_map.get("mem_usage_percent", 0.0)
    ping = point_map.get("ping_latency_gateway", 0.0)
    temp = point_map.get("system_temperature", 0.0)
    pred_fail = point_map.get("storcli_predictive_failure_count", 0.0)

    risk = max(
        min(cpu / 95.0, 1.0) * 0.35,
        min(mem / 95.0, 1.0) * 0.25,
        min(ping / 180.0, 1.0) * 0.2,
        min(temp / 85.0, 1.0) * 0.2,
        1.0 if pred_fail >= 1 else min(pred_fail, 1.0) * 0.8,
    )

    p_s2 = min(max(risk, 0.0), 1.0)
    p_s1 = min((1.0 - p_s2) * 0.55, 1.0)
    p_s0 = max(0.0, 1.0 - p_s2 - p_s1)

    if p_s2 >= max(p_s1, p_s0):
        state = "s2"
    elif p_s1 >= max(p_s0, p_s2):
        state = "s1"
    else:
        state = "s0"

    return state, p_s0, p_s1, p_s2


def _seed_raw_history(device, *, days: int = 30, step_minutes: int = 15):
    now = timezone.now()
    start = now - timedelta(days=max(1, days))
    rng = random.Random(f"demo-raw-{device.id}-{now.date().isoformat()}")

    rows = []
    ts = start
    i = 0
    step = timedelta(minutes=max(1, step_minutes))
    total_steps = int((now - start) / step) + 1

    while ts <= now:
        day_phase = (i % 96) / 96.0 * 2.0 * math.pi
        week_phase = (i % (96 * 7)) / (96.0 * 7.0) * 2.0 * math.pi

        cpu = max(3.0, min(98.0, 42.0 + 18.0 * math.sin(day_phase) + rng.gauss(0, 4.0)))
        mem = max(10.0, min(98.0, 58.0 + 7.0 * math.sin(day_phase + 0.6) + 0.002 * i + rng.gauss(0, 2.0)))
        net_sent = max(10.0, 1100.0 + 450.0 * math.sin(day_phase) + 220.0 * math.sin(week_phase) + rng.gauss(0, 60.0))
        net_recv = max(10.0, 900.0 + 420.0 * math.sin(day_phase + 0.3) + 180.0 * math.sin(week_phase + 0.7) + rng.gauss(0, 70.0))
        ping = max(1.0, 16.0 + 4.0 * math.sin(day_phase * 2.0) + rng.gauss(0, 1.8))
        temp = max(25.0, min(85.0, 49.0 + 4.0 * math.sin(day_phase + 0.2) + rng.gauss(0, 1.2)))
        storcli_temp = max(20.0, min(70.0, 43.0 + 3.0 * math.sin(day_phase) + rng.gauss(0, 0.9)))

        pred_fail = 0.0
        if i > int(total_steps * 0.85) and rng.random() < 0.03:
            pred_fail = 1.0

        labels = {"demo": True, "source": "seed_forecast_demo"}
        rows.extend([
            RawMetric(device=device, code="cpu_load_total", value=cpu, unit="%", timestamp=ts, labels=labels),
            RawMetric(device=device, code="mem_usage_percent", value=mem, unit="%", timestamp=ts, labels=labels),
            RawMetric(device=device, code="net_bytes_sent", value=net_sent, unit="KB/s", timestamp=ts, labels=labels),
            RawMetric(device=device, code="net_bytes_recv", value=net_recv, unit="KB/s", timestamp=ts, labels=labels),
            RawMetric(device=device, code="ping_latency_gateway", value=ping, unit="ms", timestamp=ts, labels=labels),
            RawMetric(device=device, code="system_temperature", value=temp, unit="C", timestamp=ts, labels=labels),
            RawMetric(device=device, code="storcli_drive_temperature", value=storcli_temp, unit="C", timestamp=ts, labels=labels),
            RawMetric(device=device, code="storcli_predictive_failure_count", value=pred_fail, unit="count", timestamp=ts, labels=labels),
        ])

        ts += step
        i += 1

    if rows:
        RawMetric.objects.bulk_create(rows, batch_size=5000)
    return len(rows)


def seed_demo_forecasts(
    *,
    serial: str | None = None,
    runs: int = 1,
    clear_existing: bool = False,
    allow_create_demo_device: bool = True,
    with_raw_history: bool = True,
    raw_history_days: int = 30,
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

    now = timezone.now()
    created_runs = 0
    created_points = 0
    created_states = 0
    created_raw = 0
    horizons = ["24h", "7d", "30d"]

    for device in devices:
        if with_raw_history:
            created_raw += _seed_raw_history(device, days=raw_history_days)

        rng = random.Random(f"demo-{device.id}-{now.date().isoformat()}")
        for _ in range(max(1, runs)):
            run = ForecastRun.objects.create(
                device=device,
                model_kind="ensemble",
                horizon_set="24h,7d,30d",
                status="success",
                started_at=now - timedelta(seconds=2),
                finished_at=now,
                parameters={"mode": "demo_seed", "source": "seed_demo_forecasts"},
                quality={"demo": True},
                notes="[demo] Synthetic forecast data for UI validation",
            )
            created_runs += 1

            points_batch = []
            states_batch = []
            for horizon in horizons:
                point_map = {}
                horizon_mul = {"24h": 1.0, "7d": 1.35, "30d": 1.75}[horizon]
                for metric_code, (base, spread) in DEMO_METRICS.items():
                    noise = rng.gauss(0.0, spread * horizon_mul)
                    value = max(0.0, base + noise)
                    if metric_code == "storcli_predictive_failure_count":
                        value = float(max(0, int(round(value))))
                    interval = max(0.5, spread * horizon_mul)
                    p10 = max(0.0, value - interval)
                    p50 = value
                    p90 = value + interval
                    point_map[metric_code] = value

                    points_batch.append(
                        ForecastPoint(
                            run=run,
                            device=device,
                            metric_code=metric_code,
                            horizon=horizon,
                            target_ts=now + _horizon_delta(horizon),
                            model_kind="ensemble",
                            y_hat=value,
                            p10=p10,
                            p50=p50,
                            p90=p90,
                            alpha=round(rng.uniform(0.2, 0.8), 3),
                            labels={"demo": True, "seed": "forecast_ui"},
                        )
                    )

                state, p_s0, p_s1, p_s2 = _estimate_state_from_points(point_map)
                states_batch.append(
                    StateEstimate(
                        run=run,
                        device=device,
                        horizon=horizon,
                        state=state,
                        p_s0=round(p_s0, 4),
                        p_s1=round(p_s1, 4),
                        p_s2=round(p_s2, 4),
                        confidence=round(rng.uniform(0.65, 0.95), 3),
                        evidence={
                            "demo": True,
                            "top_metrics": {
                                "cpu_load_total": point_map.get("cpu_load_total"),
                                "mem_usage_percent": point_map.get("mem_usage_percent"),
                                "ping_latency_gateway": point_map.get("ping_latency_gateway"),
                                "storcli_predictive_failure_count": point_map.get("storcli_predictive_failure_count"),
                            },
                        },
                        timestamp=now,
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
    }
