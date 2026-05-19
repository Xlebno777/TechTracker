from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from time import monotonic
from typing import Any

import numpy as np
import pandas as pd

from .config import settings
from .schemas import ForecastItem, ForecastRequest, ForecastResult


DEFAULT_LAGS = [1, 24, 168]
DEFAULT_OUTPUT_MODE = "direct_multi_horizon"
DEFAULT_LOSS_KIND = "quantile"
DEFAULT_TRAIN_MODE = "warm_start"
DEFAULT_TARGET_MODE = "anchored_delta"
MODEL_VERSION = "lstm_v2_trend_aware"
PINBALL_TAUS = (0.1, 0.5, 0.9)


def _horizon_to_timedelta(horizon: str) -> pd.Timedelta:
    raw = (horizon or "").strip().lower()
    if raw.endswith("h"):
        return pd.to_timedelta(int(raw[:-1]), unit="h")
    if raw.endswith("d"):
        return pd.to_timedelta(int(raw[:-1]), unit="d")
    raise ValueError(f"Unsupported horizon: {horizon}")


def _horizon_to_steps(horizon: str, freq: str) -> int:
    td = _horizon_to_timedelta(horizon)
    step = pd.to_timedelta(freq)
    if step <= timedelta(0):
        return 1
    return max(1, int(round(td / step)))


def _max_horizon_key(horizons: list[str], freq: str) -> str:
    values = [str(item or "").strip() for item in (horizons or []) if str(item or "").strip()]
    if not values:
        return "24h"
    return max(values, key=lambda item: _horizon_to_steps(item, freq))


def _to_series(points: list[dict[str, Any]], freq: str, max_points: int) -> pd.Series:
    frame = pd.DataFrame(points)
    if frame.empty:
        return pd.Series(dtype=float)

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.dropna(subset=["timestamp", "value"]).sort_values("timestamp")
    if frame.empty:
        return pd.Series(dtype=float)

    series = pd.Series(frame["value"].astype(float).values, index=frame["timestamp"])
    series = series[~series.index.duplicated(keep="last")]
    series = series.resample(freq).mean().interpolate(method="time", limit_direction="both").ffill().bfill()
    if max_points > 0 and len(series) > max_points:
        series = series.iloc[-max_points:]
    return series.astype(float)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _safe_int(value: Any, default: int, *, min_value: int | None = None) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    if min_value is not None:
        out = max(int(min_value), out)
    return out


def _safe_float(value: Any, default: float | None, *, min_value: float | None = None) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        if default is None:
            return None
        out = float(default)
    if min_value is not None:
        out = max(float(min_value), out)
    return out


def _parse_hhmm_minutes(value: Any, default_minutes: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        return int(default_minutes)
    if raw.isdigit():
        minute = int(raw)
        return max(0, min(1439, minute))
    if ":" in raw:
        left, right = raw.split(":", 1)
        try:
            hh = int(left)
            mm = int(right)
        except (TypeError, ValueError):
            return int(default_minutes)
        hh = max(0, min(23, hh))
        mm = max(0, min(59, mm))
        return (hh * 60) + mm
    return int(default_minutes)


def _parse_weekdays(value: Any, default: list[int]) -> list[int]:
    if value is None:
        return list(default)
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            try:
                idx = int(item)
            except (TypeError, ValueError):
                continue
            if 0 <= idx <= 6 and idx not in out:
                out.append(idx)
        return out or list(default)
    text = str(value or "").strip()
    if not text:
        return list(default)
    out = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            idx = int(chunk)
        except (TypeError, ValueError):
            continue
        if 0 <= idx <= 6 and idx not in out:
            out.append(idx)
    return out or list(default)


def _parse_lags(value: Any, freq: str) -> list[int]:
    step = pd.to_timedelta(freq)
    step_hours = max(1.0 / 60.0, float(step.total_seconds()) / 3600.0)
    default = [1, max(1, int(round(24.0 / step_hours))), max(1, int(round(168.0 / step_hours)))]
    if value is None:
        return default
    items = value if isinstance(value, (list, tuple, set)) else str(value).split(",")
    out = []
    for item in items:
        try:
            lag = int(item)
        except (TypeError, ValueError):
            continue
        if lag > 0 and lag not in out:
            out.append(lag)
    return out or default


def _minute_in_window(minute_of_day: int, start_minute: int, end_minute: int) -> bool:
    start = int(start_minute) % 1440
    end = int(end_minute) % 1440
    minute = int(minute_of_day) % 1440
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


@dataclass
class CalendarFeatureConfig:
    workday_start_minute: int = 8 * 60 + 30
    workday_end_minute: int = 17 * 60 + 30
    lunch_start_minute: int = 13 * 60
    lunch_end_minute: int = 14 * 60
    workday_weekdays: list[int] | None = None
    backup_start_minute: int = 21 * 60
    backup_end_minute: int = 23 * 60
    backup_weekdays: list[int] | None = None

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "CalendarFeatureConfig":
        opts = dict(options or {})
        workday_weekdays = _parse_weekdays(opts.get("workday_weekdays"), [0, 1, 2, 3, 4])
        backup_weekdays = _parse_weekdays(opts.get("backup_weekdays"), [0, 1, 2, 3, 4])
        return cls(
            workday_start_minute=_parse_hhmm_minutes(opts.get("workday_start"), 8 * 60 + 30),
            workday_end_minute=_parse_hhmm_minutes(opts.get("workday_end"), 17 * 60 + 30),
            lunch_start_minute=_parse_hhmm_minutes(opts.get("lunch_start"), 13 * 60),
            lunch_end_minute=_parse_hhmm_minutes(opts.get("lunch_end"), 14 * 60),
            workday_weekdays=workday_weekdays,
            backup_start_minute=_parse_hhmm_minutes(opts.get("backup_start"), 21 * 60),
            backup_end_minute=_parse_hhmm_minutes(opts.get("backup_end"), 23 * 60),
            backup_weekdays=backup_weekdays,
        )

    def to_labels(self) -> dict[str, Any]:
        return {
            "workday_start": f"{self.workday_start_minute // 60:02d}:{self.workday_start_minute % 60:02d}",
            "workday_end": f"{self.workday_end_minute // 60:02d}:{self.workday_end_minute % 60:02d}",
            "lunch_start": f"{self.lunch_start_minute // 60:02d}:{self.lunch_start_minute % 60:02d}",
            "lunch_end": f"{self.lunch_end_minute // 60:02d}:{self.lunch_end_minute % 60:02d}",
            "workday_weekdays": list(self.workday_weekdays or [0, 1, 2, 3, 4]),
            "backup_start": f"{self.backup_start_minute // 60:02d}:{self.backup_start_minute % 60:02d}",
            "backup_end": f"{self.backup_end_minute // 60:02d}:{self.backup_end_minute % 60:02d}",
            "backup_weekdays": list(self.backup_weekdays or [0, 1, 2, 3, 4]),
        }


def _build_calendar_features(index: pd.DatetimeIndex, cfg: CalendarFeatureConfig, *, enabled: bool) -> np.ndarray:
    if len(index) == 0:
        return np.zeros((0, 0), dtype=np.float32)
    if not enabled:
        return np.zeros((len(index), 0), dtype=np.float32)

    minutes = (index.hour.to_numpy() * 60) + index.minute.to_numpy()
    dow = index.dayofweek.to_numpy()
    hour_frac = minutes.astype(np.float64) / 1440.0
    week_frac = ((dow.astype(np.float64) * 1440.0) + minutes.astype(np.float64)) / (7.0 * 1440.0)

    sin_hour = np.sin(2.0 * np.pi * hour_frac)
    cos_hour = np.cos(2.0 * np.pi * hour_frac)
    sin_week = np.sin(2.0 * np.pi * week_frac)
    cos_week = np.cos(2.0 * np.pi * week_frac)

    workday_set = set(cfg.workday_weekdays or [0, 1, 2, 3, 4])
    backup_set = set(cfg.backup_weekdays or [0, 1, 2, 3, 4])

    is_workday = np.asarray([1.0 if int(day) in workday_set else 0.0 for day in dow], dtype=np.float64)
    is_lunch = np.asarray(
        [
            1.0
            if _minute_in_window(int(m), cfg.lunch_start_minute, cfg.lunch_end_minute) and int(day) in workday_set
            else 0.0
            for m, day in zip(minutes, dow)
        ],
        dtype=np.float64,
    )
    is_work_hours = np.asarray(
        [
            1.0
            if (
                int(day) in workday_set
                and _minute_in_window(int(m), cfg.workday_start_minute, cfg.workday_end_minute)
                and not _minute_in_window(int(m), cfg.lunch_start_minute, cfg.lunch_end_minute)
            )
            else 0.0
            for m, day in zip(minutes, dow)
        ],
        dtype=np.float64,
    )
    is_backup_window = np.asarray(
        [
            1.0
            if (int(day) in backup_set and _minute_in_window(int(m), cfg.backup_start_minute, cfg.backup_end_minute))
            else 0.0
            for m, day in zip(minutes, dow)
        ],
        dtype=np.float64,
    )

    features = np.column_stack(
        [
            sin_hour,
            cos_hour,
            sin_week,
            cos_week,
            is_workday,
            is_work_hours,
            is_lunch,
            is_backup_window,
        ]
    )
    return features.astype(np.float32)


def _build_future_index(last_timestamp: pd.Timestamp, *, steps: int, freq_step: pd.Timedelta) -> pd.DatetimeIndex:
    if steps <= 0:
        return pd.DatetimeIndex([])
    values = [last_timestamp + (freq_step * (idx + 1)) for idx in range(int(steps))]
    return pd.DatetimeIndex(values)


def _steps_per_day(freq: str) -> int:
    try:
        step = pd.to_timedelta(freq)
    except Exception:
        step = pd.to_timedelta("1h")
    step_minutes = max(1.0, float(step.total_seconds()) / 60.0)
    return max(1, int(round((24.0 * 60.0) / step_minutes)))


def _trend_window_steps(freq: str) -> int:
    steps_day = _steps_per_day(freq)
    # Trend must be slower than the dominant daily/weekly rhythm, otherwise
    # the model mistakes a routine cycle dip for a structural decline.
    return max(24, int(steps_day * 7))


def _short_trend_window_steps(freq: str) -> int:
    steps_day = _steps_per_day(freq)
    return max(12, int(steps_day * 2))


def _long_slope_window_steps(freq: str) -> int:
    steps_day = _steps_per_day(freq)
    return max(48, int(steps_day * 14))


def _trend_transition_steps(freq: str) -> int:
    steps_day = _steps_per_day(freq)
    return max(24, int(steps_day * 3))


def _extrapolate_future_trend(
    *,
    anchor_trend_value: float,
    short_slope_value: float,
    long_slope_value: float,
    total_steps: int,
    transition_steps: int | None = None,
    enforce_long_floor: bool = False,
) -> np.ndarray:
    if total_steps <= 0:
        return np.zeros(0, dtype=np.float64)
    step_idx = np.arange(1, int(total_steps) + 1, dtype=np.float64)
    transition = max(1.0, float(transition_steps or 72))
    short_slope = float(short_slope_value)
    long_slope = float(long_slope_value)
    short_offset = (short_slope - long_slope) * transition * (1.0 - np.exp(-step_idx / transition))
    projected = float(anchor_trend_value) + (long_slope * step_idx) + short_offset
    if enforce_long_floor:
        long_floor = float(anchor_trend_value) + (long_slope * step_idx)
        projected = np.maximum(projected, long_floor)
    return projected.astype(np.float64)


def _estimate_output_limit_norm(values: np.ndarray) -> float:
    if values.size == 0:
        return 4.0
    abs_values = np.abs(np.asarray(values, dtype=np.float64).reshape(-1))
    quantile = float(np.quantile(abs_values, 0.995)) if len(abs_values) else 0.0
    return float(max(3.0, min(12.0, quantile * 1.25)))


def _parse_metric_overrides(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, raw in value.items():
        metric_code = str(key or "").strip().lower()
        if not metric_code or not isinstance(raw, dict):
            continue
        normalized[metric_code] = dict(raw)
    return normalized


def _metric_override(metric_overrides: dict[str, dict[str, Any]] | None, metric_code: str, key: str, default: Any = None) -> Any:
    if not isinstance(metric_overrides, dict):
        return default
    metric_key = str(metric_code or "").strip().lower()
    raw = metric_overrides.get(metric_key)
    if not isinstance(raw, dict):
        return default
    return raw.get(key, default)


def _metric_trend_mode(metric_code: str, metric_overrides: dict[str, dict[str, Any]] | None = None) -> str:
    override = str(_metric_override(metric_overrides, metric_code, "trend_long_mode", "") or "").strip().lower()
    if override in {"mean_regression", "upper_envelope_blend", "upper_envelope_floor"}:
        return override
    raw = str(metric_code or "").strip().lower()
    if raw in {"cpu_load_total", "mem_usage_percent"}:
        return "upper_envelope_floor"
    if "temperature" in raw:
        return "upper_envelope_floor"
    return "mean_regression"


def _metric_envelope_quantile(metric_code: str) -> float:
    raw = str(metric_code or "").strip().lower()
    if raw == "cpu_load_total":
        return 0.92
    if raw == "mem_usage_percent":
        return 0.90
    if "temperature" in raw:
        return 0.88
    return 0.85


def _metric_envelope_weight(metric_code: str, metric_overrides: dict[str, dict[str, Any]] | None = None) -> float:
    override = _safe_float(_metric_override(metric_overrides, metric_code, "trend_envelope_weight", None), None)
    if override is not None:
        return float(max(0.0, min(1.0, override)))
    raw = str(metric_code or "").strip().lower()
    if raw == "cpu_load_total":
        return 0.55
    if raw == "mem_usage_percent":
        return 0.50
    if "temperature" in raw:
        return 0.45
    return 0.0


def _metric_enforce_long_floor(metric_code: str) -> bool:
    return _is_upward_risk_metric(metric_code)


def _is_upward_risk_metric(metric_code: str) -> bool:
    raw = str(metric_code or "").strip().lower()
    return (
        raw in {"cpu_load_total", "mem_usage_percent", "storcli_predictive_failure_count", "storcli_drive_wear_percent"}
        or "temperature" in raw
        or "latency" in raw
    )


def _metric_bias_correction_strength(metric_code: str, metric_overrides: dict[str, dict[str, Any]] | None = None) -> float:
    override = _safe_float(_metric_override(metric_overrides, metric_code, "bias_correction_strength", None), None)
    if override is not None:
        return float(max(0.0, min(1.0, override)))
    raw = str(metric_code or "").strip().lower()
    if raw == "cpu_load_total":
        return 0.55
    if raw == "mem_usage_percent":
        return 0.50
    if "temperature" in raw:
        return 0.45
    if _is_upward_risk_metric(raw):
        return 0.40
    return 0.25


def _metric_trend_transition_steps(freq: str, metric_code: str, metric_overrides: dict[str, dict[str, Any]] | None = None) -> int:
    override = _safe_int(_metric_override(metric_overrides, metric_code, "trend_transition_steps", None), 0, min_value=0)
    if override > 0:
        return int(override)
    return _trend_transition_steps(freq)


def _metric_bias_quantile(metric_code: str) -> float:
    return 0.65 if _is_upward_risk_metric(metric_code) else 0.5


@dataclass
class SeasonalProfile:
    step_minutes: int
    slots_per_day: int
    weekly_means: dict[tuple[int, int], float]
    daily_means: dict[int, float]
    fallback_mean: float
    enabled: bool = True
    requested_mode: str = "rolling_profile"
    effective_mode: str = "rolling_profile"
    window_days: int = 14
    zero_centered: bool = True
    trend_window_steps: int = 24

    @classmethod
    def from_series(
        cls,
        series: pd.Series,
        freq: str,
        *,
        enabled: bool,
        mode: str = "rolling_profile",
        window_days: int = 14,
    ) -> "SeasonalProfile":
        requested_mode = str(mode or "rolling_profile").strip().lower() or "rolling_profile"
        effective_mode = requested_mode
        trend_window_steps = _trend_window_steps(freq)
        if not enabled or series.empty:
            return cls(
                step_minutes=60,
                slots_per_day=24,
                weekly_means={},
                daily_means={},
                fallback_mean=float(series.mean()) if len(series) else 0.0,
                enabled=False,
                requested_mode=requested_mode,
                effective_mode="disabled",
                window_days=int(window_days),
                zero_centered=True,
                trend_window_steps=int(trend_window_steps),
            )

        try:
            step = pd.to_timedelta(freq)
        except Exception:
            step = pd.to_timedelta("1h")
        step_minutes = max(1, int(round(step.total_seconds() / 60.0)))
        slots_per_day = max(1, int(round((24.0 * 60.0) / float(step_minutes))))

        source_series = series
        if requested_mode in ("rolling_profile", "stl_like_local"):
            tail_start = series.index.max() - pd.to_timedelta(max(1, int(window_days)), unit="d")
            tail_series = series.loc[series.index >= tail_start]
            if len(tail_series) >= max(24, min(len(series), slots_per_day * 3)):
                source_series = tail_series
            else:
                effective_mode = "global_profile_fallback"
        elif requested_mode == "global_profile":
            source_series = series
        else:
            effective_mode = "rolling_profile"
            tail_start = series.index.max() - pd.to_timedelta(max(1, int(window_days)), unit="d")
            source_series = series.loc[series.index >= tail_start]
            if source_series.empty:
                source_series = series
                effective_mode = "global_profile_fallback"

        idx = source_series.index
        source_values = source_series.astype(float).to_numpy()
        source_trend = _rolling_mean(source_values, trend_window_steps)
        source_anomaly = source_values - source_trend
        minutes = (idx.hour.to_numpy() * 60) + idx.minute.to_numpy()
        dow = idx.dayofweek.to_numpy()
        slot = ((minutes // step_minutes) % slots_per_day).astype(int)
        frame = pd.DataFrame({
            "value": source_anomaly.astype(float),
            "dow": dow.astype(int),
            "slot": slot.astype(int),
        })
        overall_mean = float(frame["value"].mean()) if len(frame) else 0.0
        weekly = frame.groupby(["dow", "slot"])["value"].mean()
        daily = frame.groupby(["slot"])["value"].mean()
        weekly_map = {(int(k1), int(k2)): float(v - overall_mean) for (k1, k2), v in weekly.items()}
        daily_map = {int(k): float(v - overall_mean) for k, v in daily.items()}
        fallback = 0.0

        return cls(
            step_minutes=step_minutes,
            slots_per_day=slots_per_day,
            weekly_means=weekly_map,
            daily_means=daily_map,
            fallback_mean=fallback,
            enabled=True,
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            window_days=max(1, int(window_days)),
            zero_centered=True,
            trend_window_steps=int(trend_window_steps),
        )

    def _slot(self, ts: pd.Timestamp) -> tuple[int, int]:
        minute = int(ts.hour) * 60 + int(ts.minute)
        slot = int((minute // max(1, self.step_minutes)) % max(1, self.slots_per_day))
        return int(ts.dayofweek), slot

    def value_for_timestamp(self, ts: pd.Timestamp) -> float:
        if not self.enabled:
            return 0.0
        dow, slot = self._slot(ts)
        if (dow, slot) in self.weekly_means:
            return float(self.weekly_means[(dow, slot)])
        if slot in self.daily_means:
            return float(self.daily_means[slot])
        return float(self.fallback_mean)

    def values_for_index(self, index: pd.DatetimeIndex) -> np.ndarray:
        if len(index) == 0:
            return np.zeros(0, dtype=np.float64)
        if not self.enabled:
            return np.zeros(len(index), dtype=np.float64)
        out = np.empty(len(index), dtype=np.float64)
        for idx, ts in enumerate(index):
            out[idx] = self.value_for_timestamp(ts)
        return out


def _safe_std(values: np.ndarray) -> float:
    sigma = float(np.std(values)) if len(values) else 0.0
    return sigma if sigma >= 1e-6 else 1.0


def _zscore(values: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    return ((values - mu) / max(1e-6, sigma)).astype(np.float32)


def _shift_fill(values: np.ndarray, lag: int) -> np.ndarray:
    lag = max(1, int(lag))
    series = pd.Series(values)
    shifted = series.shift(lag)
    shifted = shifted.bfill().ffill()
    return shifted.to_numpy(dtype=np.float64)


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    return pd.Series(values).rolling(window=window, min_periods=1).mean().to_numpy(dtype=np.float64)


def _rolling_quantile(values: np.ndarray, window: int, quantile: float) -> np.ndarray:
    window = max(1, int(window))
    q = float(max(0.5, min(0.99, quantile)))
    return pd.Series(values).rolling(window=window, min_periods=1).quantile(q).to_numpy(dtype=np.float64)


def _smooth_vector(values: np.ndarray, window: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return arr
    smoothed = pd.Series(arr).rolling(window=max(1, int(window)), min_periods=1, center=True).mean()
    smoothed = smoothed.bfill().ffill()
    return smoothed.to_numpy(dtype=np.float64)


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    window = max(2, int(window))
    out = pd.Series(values).rolling(window=window, min_periods=2).std()
    out = out.bfill().ffill().fillna(0.0)
    return out.to_numpy(dtype=np.float64)


def _slope_feature(values: np.ndarray, window: int) -> np.ndarray:
    window = max(2, int(window))
    series = pd.Series(values)
    slope = (series - series.shift(window)) / float(window)
    slope = slope.bfill().ffill().fillna(0.0)
    return slope.to_numpy(dtype=np.float64)


def _rolling_regression_slope(values: np.ndarray, window: int) -> np.ndarray:
    window = max(2, int(window))
    arr = np.asarray(values, dtype=np.float64)
    n = int(arr.size)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)
    for end in range(n):
        start = max(0, end - window + 1)
        y = arr[start : end + 1]
        m = int(y.size)
        if m < 2:
            out[end] = 0.0
            continue
        x = np.arange(m, dtype=np.float64)
        x_mean = float(x.mean())
        y_mean = float(y.mean())
        denom = float(np.sum((x - x_mean) ** 2))
        if denom <= 1e-12:
            out[end] = 0.0
            continue
        numer = float(np.sum((x - x_mean) * (y - y_mean)))
        out[end] = numer / denom
    if n >= 2:
        out[0] = out[1]
    return out.astype(np.float64)


@dataclass
class PreparedSeries:
    target_values: np.ndarray
    target_norm: np.ndarray
    seasonal_values: np.ndarray
    seasonal_norm: np.ndarray
    trend_values: np.ndarray
    trend_norm: np.ndarray
    trend_slope_short_values: np.ndarray
    trend_slope_short_norm: np.ndarray
    trend_slope_values: np.ndarray
    trend_slope_norm: np.ndarray
    calendar_features: np.ndarray
    history_features: np.ndarray
    raw_norm: np.ndarray
    roll_mean_24: np.ndarray
    slope_24: np.ndarray
    target_mu: float
    target_sigma: float
    seasonal_profile: SeasonalProfile
    raw_mu: float
    raw_sigma: float
    lags: list[int]
    trend_long_mode: str
    trend_envelope_quantile: float | None
    trend_envelope_weight: float
    trend_short_window_steps: int
    trend_long_slope_window_steps: int
    trend_window_steps: int
    trend_transition_steps: int
    bias_correction_strength: float


def _prepare_series_features(
    *,
    metric_code: str,
    series: pd.Series,
    freq: str,
    calendar_cfg: CalendarFeatureConfig,
    use_calendar_features: bool,
    use_seasonal_residual: bool,
    seasonality_mode: str,
    seasonality_window_days: int,
    lags: list[int],
    metric_overrides: dict[str, dict[str, Any]] | None = None,
) -> PreparedSeries:
    raw_values = series.to_numpy(dtype=np.float64)
    raw_mu = float(raw_values.mean()) if len(raw_values) else 0.0
    raw_sigma = _safe_std(raw_values)
    trend_short_window_steps = _short_trend_window_steps(freq)
    trend_long_slope_window_steps = _long_slope_window_steps(freq)
    trend_window_steps = _trend_window_steps(freq)
    trend_transition_steps = _metric_trend_transition_steps(freq, metric_code, metric_overrides)
    trend_long_mode = _metric_trend_mode(metric_code, metric_overrides)
    trend_envelope_quantile = _metric_envelope_quantile(metric_code) if trend_long_mode in {"upper_envelope_blend", "upper_envelope_floor"} else None
    trend_envelope_weight = _metric_envelope_weight(metric_code, metric_overrides) if trend_long_mode in {"upper_envelope_blend", "upper_envelope_floor"} else 0.0
    bias_correction_strength = _metric_bias_correction_strength(metric_code, metric_overrides)
    short_trend_values = _rolling_mean(raw_values, trend_short_window_steps)
    trend_values = _rolling_mean(raw_values, trend_window_steps)
    trend_slope_short_values = _slope_feature(short_trend_values, max(2, _steps_per_day(freq)))
    mean_regression_slope = _rolling_regression_slope(trend_values, trend_long_slope_window_steps)
    if trend_long_mode in {"upper_envelope_blend", "upper_envelope_floor"}:
        envelope_basis_values = _rolling_quantile(raw_values, trend_window_steps, trend_envelope_quantile or 0.85)
        envelope_regression_slope = _rolling_regression_slope(envelope_basis_values, trend_long_slope_window_steps)
        blend_weight = float(max(0.0, min(1.0, trend_envelope_weight)))
        blended_slope = ((1.0 - blend_weight) * mean_regression_slope) + (blend_weight * envelope_regression_slope)
        if trend_long_mode == "upper_envelope_floor":
            # Conservative floor: do not let long trend fall below the
            # sustained multi-day drift, but do not promote short-term spikes
            # into the 30-day slope.
            trend_slope_values = np.maximum(mean_regression_slope, blended_slope)
        else:
            trend_slope_values = blended_slope
    else:
        trend_slope_values = mean_regression_slope

    seasonal_profile = SeasonalProfile.from_series(
        series=series,
        freq=freq,
        enabled=use_seasonal_residual,
        mode=seasonality_mode,
        window_days=seasonality_window_days,
    )
    seasonal_values = seasonal_profile.values_for_index(series.index)
    target_values = raw_values - trend_values - seasonal_values if use_seasonal_residual else raw_values - trend_values
    target_mu = float(target_values.mean()) if len(target_values) else 0.0
    target_sigma = _safe_std(target_values)
    target_norm = _zscore(target_values, target_mu, target_sigma)
    raw_norm = _zscore(raw_values, raw_mu, raw_sigma)
    trend_norm = _zscore(trend_values, raw_mu, raw_sigma)
    trend_slope_short_norm = _zscore(trend_slope_short_values, 0.0, raw_sigma)
    trend_slope_norm = _zscore(trend_slope_values, 0.0, raw_sigma)
    seasonal_scale = _safe_std(seasonal_values)
    seasonal_norm = _zscore(seasonal_values, 0.0, seasonal_scale)

    calendar = _build_calendar_features(series.index, calendar_cfg, enabled=use_calendar_features)
    diff1 = np.diff(target_norm, prepend=target_norm[0]).astype(np.float64)
    roll_mean_24 = _rolling_mean(target_norm, 24)
    roll_std_24 = _rolling_std(target_norm, 24)
    roll_mean_168 = _rolling_mean(target_norm, 168)
    slope_24 = _slope_feature(target_norm, 24)
    slope_48 = _slope_feature(target_norm, 48)

    lag_arrays = [_shift_fill(target_norm, lag) for lag in lags]
    history_parts = [
        target_norm.astype(np.float64),
        raw_norm.astype(np.float64),
        trend_norm.astype(np.float64),
        seasonal_norm.astype(np.float64),
        diff1,
        roll_mean_24,
        roll_std_24,
        roll_mean_168,
        slope_24,
        slope_48,
        trend_slope_short_norm.astype(np.float64),
        trend_slope_norm.astype(np.float64),
        *lag_arrays,
    ]
    if calendar.size:
        history_parts.append(calendar.astype(np.float64).T)
    history_features = np.vstack(history_parts).T.astype(np.float32)

    return PreparedSeries(
        target_values=target_values.astype(np.float64),
        target_norm=target_norm.astype(np.float32),
        seasonal_values=seasonal_values.astype(np.float64),
        seasonal_norm=seasonal_norm.astype(np.float32),
        trend_values=trend_values.astype(np.float64),
        trend_norm=trend_norm.astype(np.float32),
        trend_slope_short_values=trend_slope_short_values.astype(np.float64),
        trend_slope_short_norm=trend_slope_short_norm.astype(np.float32),
        trend_slope_values=trend_slope_values.astype(np.float64),
        trend_slope_norm=trend_slope_norm.astype(np.float32),
        calendar_features=calendar.astype(np.float32),
        history_features=history_features,
        raw_norm=raw_norm.astype(np.float32),
        roll_mean_24=roll_mean_24.astype(np.float32),
        slope_24=slope_24.astype(np.float32),
        target_mu=target_mu,
        target_sigma=target_sigma,
        seasonal_profile=seasonal_profile,
        raw_mu=raw_mu,
        raw_sigma=raw_sigma,
        lags=list(lags),
        trend_long_mode=str(trend_long_mode),
        trend_envelope_quantile=float(trend_envelope_quantile) if trend_envelope_quantile is not None else None,
        trend_envelope_weight=float(trend_envelope_weight),
        trend_short_window_steps=int(trend_short_window_steps),
        trend_long_slope_window_steps=int(trend_long_slope_window_steps),
        trend_window_steps=int(trend_window_steps),
        trend_transition_steps=int(trend_transition_steps),
        bias_correction_strength=float(bias_correction_strength),
    )


def _compose_decoder_features(
    *,
    seasonal_norm: np.ndarray,
    future_trend_norm: np.ndarray,
    calendar_features: np.ndarray,
    anchor_target_norm: float,
    anchor_raw_norm: float,
    anchor_trend_norm: float,
    recent_mean_24: float,
    recent_slope_24: float,
) -> np.ndarray:
    total_steps = int(len(seasonal_norm))
    if total_steps <= 0:
        return np.zeros((0, 0), dtype=np.float32)
    step_ratio = (np.arange(total_steps, dtype=np.float64) + 1.0) / max(1.0, float(total_steps))
    parts = [
        seasonal_norm.astype(np.float64),
        future_trend_norm.astype(np.float64),
        step_ratio,
        np.sin(2.0 * np.pi * step_ratio),
        np.cos(2.0 * np.pi * step_ratio),
        np.full(total_steps, float(anchor_target_norm), dtype=np.float64),
        np.full(total_steps, float(anchor_raw_norm), dtype=np.float64),
        np.full(total_steps, float(anchor_trend_norm), dtype=np.float64),
        np.full(total_steps, float(recent_mean_24), dtype=np.float64),
        np.full(total_steps, float(recent_slope_24), dtype=np.float64),
    ]
    if getattr(calendar_features, "size", 0):
        parts.append(np.asarray(calendar_features, dtype=np.float64).T)
    return np.vstack(parts).T.astype(np.float32)


def _build_future_decoder_features(
    *,
    future_index: pd.DatetimeIndex,
    total_steps: int,
    calendar_cfg: CalendarFeatureConfig,
    use_calendar_features: bool,
    seasonal_profile: SeasonalProfile,
    raw_mu: float,
    raw_sigma: float,
    future_trend_values: np.ndarray,
    anchor_target_norm: float,
    anchor_raw_norm: float,
    anchor_trend_norm: float,
    recent_mean_24: float,
    recent_slope_24: float,
) -> np.ndarray:
    if total_steps <= 0:
        return np.zeros((0, 0), dtype=np.float32)
    calendar_future = _build_calendar_features(future_index, calendar_cfg, enabled=use_calendar_features)
    seasonal_future = seasonal_profile.values_for_index(future_index)
    seasonal_scale = _safe_std(seasonal_future)
    seasonal_norm = _zscore(seasonal_future.astype(np.float64), 0.0, seasonal_scale)
    future_trend_norm = _zscore(np.asarray(future_trend_values, dtype=np.float64), raw_mu, raw_sigma)
    return _compose_decoder_features(
        seasonal_norm=seasonal_norm,
        future_trend_norm=future_trend_norm,
        calendar_features=calendar_future,
        anchor_target_norm=anchor_target_norm,
        anchor_raw_norm=anchor_raw_norm,
        anchor_trend_norm=anchor_trend_norm,
        recent_mean_24=recent_mean_24,
        recent_slope_24=recent_slope_24,
    )


def _build_training_samples(
    *,
    prepared: PreparedSeries,
    lookback: int,
    steps: int,
    target_mode: str,
    recency_weighted_loss: bool,
    recency_weight_min: float,
    recency_weight_power: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    total_len = len(prepared.target_norm)
    if total_len < lookback + steps + 8:
        raise ValueError("not enough points for direct multi-step LSTM")

    x_hist = []
    x_future = []
    y = []
    sample_weights = []
    max_end = total_len - steps
    denom = max(1, max_end - lookback)
    weight_floor = max(0.05, min(1.0, float(recency_weight_min)))
    weight_power = max(1.0, float(recency_weight_power))
    for end in range(lookback, max_end + 1):
        start = end - lookback
        x_hist.append(prepared.history_features[start:end])
        anchor_target_norm = float(prepared.target_norm[end - 1])
        future_trend_values = _extrapolate_future_trend(
            anchor_trend_value=float(prepared.trend_values[end - 1]),
            short_slope_value=float(prepared.trend_slope_short_values[end - 1]),
            long_slope_value=float(prepared.trend_slope_values[end - 1]),
            total_steps=steps,
            transition_steps=int(prepared.trend_transition_steps),
        )
        x_future.append(
            _compose_decoder_features(
                seasonal_norm=prepared.seasonal_norm[end:end + steps],
                future_trend_norm=_zscore(future_trend_values, prepared.raw_mu, prepared.raw_sigma),
                calendar_features=prepared.calendar_features[end:end + steps],
                anchor_target_norm=anchor_target_norm,
                anchor_raw_norm=float(prepared.raw_norm[end - 1]),
                anchor_trend_norm=float(prepared.trend_norm[end - 1]),
                recent_mean_24=float(prepared.roll_mean_24[end - 1]),
                recent_slope_24=float(prepared.slope_24[end - 1]),
            )
        )
        future_target = prepared.target_norm[end:end + steps]
        if target_mode == "anchored_delta":
            y.append((future_target - anchor_target_norm).astype(np.float32))
        else:
            y.append(future_target.astype(np.float32))
        if recency_weighted_loss:
            ratio = float(end - lookback) / float(denom)
            weight = weight_floor + (1.0 - weight_floor) * (ratio ** weight_power)
        else:
            weight = 1.0
        sample_weights.append(float(weight))

    x_hist_arr = np.asarray(x_hist, dtype=np.float32)
    x_future_arr = np.asarray(x_future, dtype=np.float32)
    y_arr = np.asarray(y, dtype=np.float32)
    sample_weight_arr = np.asarray(sample_weights, dtype=np.float32)
    if len(x_hist_arr) < 8:
        raise ValueError("not enough train samples for direct multi-step LSTM")
    if len(sample_weight_arr):
        sample_weight_arr = sample_weight_arr / max(1e-6, float(sample_weight_arr.mean()))
    return x_hist_arr, x_future_arr, y_arr, sample_weight_arr


class LSTMForecaster:
    def __init__(
        self,
        *,
        epochs: int,
        lookback: int,
        hidden_size: int,
        learning_rate: float,
        device_preference: str = "auto",
        amp: bool = False,
        gpu_index: int = 0,
        dropout: float = 0.15,
        weight_decay: float = 1e-5,
        batch_size: int = 64,
        output_mode: str = DEFAULT_OUTPUT_MODE,
        loss_kind: str = DEFAULT_LOSS_KIND,
        train_mode: str = DEFAULT_TRAIN_MODE,
        target_mode: str = DEFAULT_TARGET_MODE,
        recency_weighted_loss: bool = True,
        recency_weight_min: float = 0.35,
        recency_weight_power: float = 2.0,
        early_stopping_enabled: bool = True,
        early_stopping_patience: int = 10,
        early_stopping_min_delta: float = 0.0005,
        lr_scheduler_kind: str = "plateau",
        lr_scheduler_patience: int = 4,
        lr_scheduler_factor: float = 0.5,
        lr_scheduler_min_lr: float = 1e-5,
        checkpoint_dir: str | None = None,
    ):
        self.epochs = max(4, int(epochs))
        self.lookback = max(24, int(lookback))
        self.hidden_size = max(16, int(hidden_size))
        self.learning_rate = float(learning_rate)
        self.dropout = float(max(0.0, min(0.5, dropout)))
        self.weight_decay = float(max(0.0, weight_decay))
        self.batch_size = max(4, int(batch_size))
        self.output_mode = str(output_mode or DEFAULT_OUTPUT_MODE).strip().lower() or DEFAULT_OUTPUT_MODE
        self.loss_kind = str(loss_kind or DEFAULT_LOSS_KIND).strip().lower() or DEFAULT_LOSS_KIND
        self.train_mode = str(train_mode or DEFAULT_TRAIN_MODE).strip().lower() or DEFAULT_TRAIN_MODE
        self.target_mode = str(target_mode or DEFAULT_TARGET_MODE).strip().lower() or DEFAULT_TARGET_MODE
        if self.target_mode not in ("anchored_delta", "absolute_level"):
            self.target_mode = DEFAULT_TARGET_MODE
        self.recency_weighted_loss = bool(recency_weighted_loss)
        self.recency_weight_min = float(max(0.05, min(1.0, recency_weight_min)))
        self.recency_weight_power = float(max(1.0, recency_weight_power))
        self.early_stopping_enabled = bool(early_stopping_enabled)
        self.early_stopping_patience = max(1, int(early_stopping_patience))
        self.early_stopping_min_delta = float(max(0.0, early_stopping_min_delta))
        scheduler_kind_normalized = str(lr_scheduler_kind or "plateau").strip().lower()
        if scheduler_kind_normalized not in {"plateau", "cosine", "none"}:
            scheduler_kind_normalized = "plateau"
        self.lr_scheduler_kind = scheduler_kind_normalized
        self.lr_scheduler_patience = max(1, int(lr_scheduler_patience))
        self.lr_scheduler_factor = float(max(0.1, min(0.95, lr_scheduler_factor)))
        self.lr_scheduler_min_lr = float(max(1e-7, lr_scheduler_min_lr))
        self.checkpoint_dir = Path(checkpoint_dir or settings.checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._output_limit_norm = 4.0

        pref = str(device_preference or "auto").strip().lower()
        if pref not in ("auto", "cpu", "cuda", "gpu", "rocm"):
            pref = "auto"
        self.device_preference = pref
        self.amp = bool(amp)
        self.gpu_index = max(0, int(gpu_index))

        self._runtime_device = None
        self._runtime_device_label = ""
        self._runtime_cuda_available = False
        self._runtime_amp_enabled = False

    @staticmethod
    def _lazy_torch():
        try:
            import torch
            import torch.nn as nn
            import torch.nn.functional as F
            from torch.utils.data import DataLoader, TensorDataset
        except Exception as exc:
            raise RuntimeError("Torch is required for remote LSTM forecasting") from exc
        return torch, nn, F, DataLoader, TensorDataset

    def _resolve_runtime(self):
        torch, nn, F, DataLoader, TensorDataset = self._lazy_torch()
        if self._runtime_device is not None:
            return torch, nn, F, DataLoader, TensorDataset, self._runtime_device, self._runtime_amp_enabled, self._runtime_cuda_available

        cuda_available = bool(torch.cuda.is_available())
        if self.device_preference in ("cuda", "gpu", "rocm"):
            device = torch.device(f"cuda:{self.gpu_index}") if cuda_available else torch.device("cpu")
        elif self.device_preference == "cpu":
            device = torch.device("cpu")
        else:
            device = torch.device(f"cuda:{self.gpu_index}") if cuda_available else torch.device("cpu")

        if device.type == "cuda":
            try:
                torch.cuda.set_device(device)
            except Exception:
                pass

        amp_enabled = bool(self.amp and device.type == "cuda")
        self._runtime_device = device
        self._runtime_device_label = str(device)
        self._runtime_cuda_available = cuda_available
        self._runtime_amp_enabled = amp_enabled
        return torch, nn, F, DataLoader, TensorDataset, device, amp_enabled, cuda_available

    def _autocast_ctx(self, torch, amp_enabled: bool):
        if amp_enabled and hasattr(torch, "autocast"):
            try:
                return torch.autocast(device_type="cuda", dtype=torch.float16)
            except TypeError:
                return torch.autocast("cuda", dtype=torch.float16)
        return nullcontext()

    def runtime_info(self) -> dict[str, Any]:
        torch, _, _, _, _, device, amp_enabled, cuda_available = self._resolve_runtime()
        device_name = ""
        if device.type == "cuda":
            try:
                index = int(device.index) if device.index is not None else 0
                device_name = str(torch.cuda.get_device_name(index))
            except Exception:
                device_name = ""
        return {
            "requested_device": self.device_preference,
            "device": str(device),
            "cuda_available": bool(cuda_available),
            "amp_enabled": bool(amp_enabled),
            "gpu_index": int(self.gpu_index),
            "device_name": device_name,
        }

    def _checkpoint_path(self, *, device_serial: str, metric_code: str, freq: str, steps: int, horizon_key: str) -> Path:
        def _slug(value: str) -> str:
            safe = []
            for char in str(value or ""):
                safe.append(char if char.isalnum() or char in ("-", "_") else "_")
            return "".join(safe).strip("_") or "na"
        filename = (
            f"{_slug(device_serial)}__{_slug(metric_code)}__{_slug(freq)}__"
            f"{_slug(horizon_key)}__h{int(steps)}__{_slug(self.output_mode)}.pt"
        )
        return self.checkpoint_dir / filename

    def _build_model(self, *, history_input_size: int, future_input_size: int, steps: int, quantile_mode: bool):
        torch, nn, F, _, _, device, _, _ = self._resolve_runtime()

        class _DirectNet(nn.Module):
            def __init__(
                self,
                hidden_size: int,
                hist_in: int,
                fut_in: int,
                dropout: float,
                quantile_mode: bool,
                output_limit_norm: float,
            ):
                super().__init__()
                self.quantile_mode = quantile_mode
                self.register_buffer("output_limit_norm", torch.tensor(float(output_limit_norm), dtype=torch.float32))
                self.encoder = nn.LSTM(input_size=hist_in, hidden_size=hidden_size, num_layers=1, batch_first=True)
                self.context = nn.Sequential(
                    nn.LayerNorm(hidden_size),
                    nn.Linear(hidden_size, hidden_size),
                    nn.SiLU(),
                    nn.Dropout(dropout),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(hidden_size + fut_in, hidden_size),
                    nn.SiLU(),
                    nn.Dropout(dropout),
                    nn.Linear(hidden_size, 3 if quantile_mode else 1),
                )

            def forward(self, history_x, future_x):
                encoded, _ = self.encoder(history_x)
                context = self.context(encoded[:, -1, :])
                repeated = context[:, None, :].expand(-1, future_x.shape[1], -1)
                raw = self.decoder(torch.cat([repeated, future_x], dim=-1))
                output_limit = self.output_limit_norm.to(dtype=raw.dtype, device=raw.device)
                if self.quantile_mode:
                    center = torch.tanh(raw[..., 0]) * output_limit
                    low_gap = torch.sigmoid(raw[..., 1]) * output_limit
                    high_gap = torch.sigmoid(raw[..., 2]) * output_limit
                    q10 = torch.clamp(center - low_gap, min=-output_limit, max=output_limit)
                    q50 = torch.clamp(center, min=-output_limit, max=output_limit)
                    q90 = torch.clamp(center + high_gap, min=-output_limit, max=output_limit)
                    q10 = torch.minimum(q10, q50)
                    q90 = torch.maximum(q90, q50)
                    return torch.stack([q10, q50, q90], dim=-1)
                return torch.tanh(raw[..., 0]) * output_limit

        model = _DirectNet(
            self.hidden_size,
            history_input_size,
            future_input_size,
            self.dropout,
            quantile_mode,
            self._output_limit_norm,
        ).to(device)
        return model

    def _pinball_loss_per_sample(self, torch, pred, target):
        loss = 0.0
        for idx, tau in enumerate(PINBALL_TAUS):
            err = target - pred[..., idx]
            loss = loss + torch.maximum(tau * err, (tau - 1.0) * err).mean(dim=-1)
        return loss / float(len(PINBALL_TAUS))

    def _try_load_checkpoint(self, *, model, device_serial: str, metric_code: str, freq: str, steps: int, horizon_key: str, meta: dict[str, Any]):
        if self.train_mode != "warm_start":
            return False, None
        torch, _, _, _, _, device, _, _ = self._resolve_runtime()
        path = self._checkpoint_path(
            device_serial=device_serial,
            metric_code=metric_code,
            freq=freq,
            steps=steps,
            horizon_key=horizon_key,
        )
        if not path.exists():
            return False, str(path)
        try:
            payload = torch.load(path, map_location=device)
            saved_meta = payload.get("meta") if isinstance(payload, dict) else None
            state_dict = payload.get("state_dict") if isinstance(payload, dict) else None
            if not isinstance(saved_meta, dict) or state_dict is None:
                return False, str(path)
            required = {
                "history_input_size": meta.get("history_input_size"),
                "future_input_size": meta.get("future_input_size"),
                "steps": meta.get("steps"),
                "output_mode": meta.get("output_mode"),
                "loss_kind": meta.get("loss_kind"),
            }
            for key, expected in required.items():
                if saved_meta.get(key) != expected:
                    return False, str(path)
            model.load_state_dict(state_dict)
            return True, str(path)
        except Exception:
            return False, str(path)

    def _save_checkpoint(self, *, model, device_serial: str, metric_code: str, freq: str, steps: int, horizon_key: str, meta: dict[str, Any]):
        if self.train_mode != "warm_start":
            return None
        torch, _, _, _, _, _, _, _ = self._resolve_runtime()
        path = self._checkpoint_path(
            device_serial=device_serial,
            metric_code=metric_code,
            freq=freq,
            steps=steps,
            horizon_key=horizon_key,
        )
        try:
            torch.save({"meta": meta, "state_dict": model.state_dict()}, path)
            return str(path)
        except Exception:
            return str(path)

    def forecast(
        self,
        prepared: PreparedSeries,
        *,
        device_serial: str,
        metric_code: str,
        freq: str,
        steps: int,
        horizon_key: str,
        future_features: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        torch, nn, F, DataLoader, TensorDataset, device, amp_enabled, _ = self._resolve_runtime()
        x_hist_arr, x_future_arr, y_arr, sample_weight_arr = _build_training_samples(
            prepared=prepared,
            lookback=self.lookback,
            steps=steps,
            target_mode=self.target_mode,
            recency_weighted_loss=self.recency_weighted_loss,
            recency_weight_min=self.recency_weight_min,
            recency_weight_power=self.recency_weight_power,
        )
        quantile_mode = self.loss_kind == "quantile"
        self._output_limit_norm = _estimate_output_limit_norm(y_arr)
        history_input_size = int(x_hist_arr.shape[2])
        future_input_size = int(x_future_arr.shape[2])
        total_samples = int(len(x_hist_arr))
        validation_count = 0
        if total_samples >= 64:
            validation_count = min(max(16, int(round(total_samples * 0.15))), max(0, total_samples // 4))
            if total_samples - validation_count < 32:
                validation_count = max(0, total_samples - 32)
        train_count = total_samples - validation_count
        if train_count <= 0:
            train_count = total_samples
            validation_count = 0

        train_x_hist_arr = x_hist_arr[:train_count]
        train_x_future_arr = x_future_arr[:train_count]
        train_y_arr = y_arr[:train_count]
        train_sample_weight_arr = sample_weight_arr[:train_count]
        val_x_hist_arr = x_hist_arr[train_count:] if validation_count > 0 else np.zeros((0,), dtype=np.float32)
        val_x_future_arr = x_future_arr[train_count:] if validation_count > 0 else np.zeros((0,), dtype=np.float32)
        val_y_arr = y_arr[train_count:] if validation_count > 0 else np.zeros((0,), dtype=np.float32)

        model = self._build_model(
            history_input_size=history_input_size,
            future_input_size=future_input_size,
            steps=steps,
            quantile_mode=quantile_mode,
        )
        optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay)
        scheduler = None
        if self.lr_scheduler_kind == "plateau":
            scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
                optimizer,
                mode="min",
                factor=self.lr_scheduler_factor,
                patience=self.lr_scheduler_patience,
                min_lr=self.lr_scheduler_min_lr,
            )
        elif self.lr_scheduler_kind == "cosine":
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer,
                T_max=max(1, self.epochs),
                eta_min=self.lr_scheduler_min_lr,
            )

        model_meta = {
            "history_input_size": history_input_size,
            "future_input_size": future_input_size,
            "steps": int(steps),
            "horizon_key": str(horizon_key),
            "output_mode": self.output_mode,
            "loss_kind": self.loss_kind,
            "target_mode": self.target_mode,
            "output_limit_norm": float(self._output_limit_norm),
        }
        warm_start_loaded, checkpoint_path = self._try_load_checkpoint(
            model=model,
            device_serial=device_serial,
            metric_code=metric_code,
            freq=freq,
            steps=steps,
            horizon_key=horizon_key,
            meta=model_meta,
        )

        x_hist_tensor = torch.tensor(train_x_hist_arr, dtype=torch.float32)
        x_future_tensor = torch.tensor(train_x_future_arr, dtype=torch.float32)
        y_tensor = torch.tensor(train_y_arr, dtype=torch.float32)
        weight_tensor = torch.tensor(train_sample_weight_arr, dtype=torch.float32)
        dataset = TensorDataset(x_hist_tensor, x_future_tensor, y_tensor, weight_tensor)
        batch_size = min(max(4, self.batch_size), len(dataset))
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        train_start = monotonic()
        final_train_loss = None
        final_val_loss = None
        best_val_loss = None
        best_epoch = 0
        epochs_trained = 0
        early_stopped = False
        best_state = None
        patience_counter = 0
        model.train()
        huber = nn.SmoothL1Loss(beta=0.5, reduction="none")
        for epoch_idx in range(self.epochs):
            epoch_loss = 0.0
            epoch_n = 0
            for hist_batch, future_batch, target_batch, sample_weight_batch in loader:
                hist_batch = hist_batch.to(device)
                future_batch = future_batch.to(device)
                target_batch = target_batch.to(device)
                sample_weight_batch = sample_weight_batch.to(device)
                optimizer.zero_grad()
                with self._autocast_ctx(torch, amp_enabled):
                    pred = model(hist_batch, future_batch)
                    if quantile_mode:
                        sample_loss = self._pinball_loss_per_sample(torch, pred, target_batch)
                    else:
                        sample_loss = huber(pred, target_batch).mean(dim=-1)
                    loss = (sample_loss * sample_weight_batch).sum() / sample_weight_batch.sum().clamp_min(1e-6)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                epoch_loss += float(loss.detach().cpu().item()) * int(hist_batch.shape[0])
                epoch_n += int(hist_batch.shape[0])
            if epoch_n > 0:
                final_train_loss = epoch_loss / float(epoch_n)
            epochs_trained = epoch_idx + 1

            val_loss_value = None
            if validation_count > 0:
                model.eval()
                with torch.no_grad():
                    val_hist_tensor = torch.tensor(val_x_hist_arr, dtype=torch.float32, device=device)
                    val_future_tensor = torch.tensor(val_x_future_arr, dtype=torch.float32, device=device)
                    val_target_tensor = torch.tensor(val_y_arr, dtype=torch.float32, device=device)
                    with self._autocast_ctx(torch, amp_enabled):
                        val_pred_tensor = model(val_hist_tensor, val_future_tensor)
                        if quantile_mode:
                            val_loss_tensor = self._pinball_loss_per_sample(torch, val_pred_tensor, val_target_tensor)
                        else:
                            val_loss_tensor = huber(val_pred_tensor, val_target_tensor).mean(dim=-1)
                    val_loss_value = float(val_loss_tensor.mean().detach().cpu().item())
                    final_val_loss = val_loss_value
                model.train()

                if self.lr_scheduler_kind == "plateau" and scheduler is not None:
                    scheduler.step(val_loss_value)
                elif self.lr_scheduler_kind == "cosine" and scheduler is not None:
                    scheduler.step()

                if best_val_loss is None or val_loss_value < (best_val_loss - self.early_stopping_min_delta):
                    best_val_loss = val_loss_value
                    best_epoch = epoch_idx + 1
                    best_state = {
                        key: value.detach().cpu().clone()
                        for key, value in model.state_dict().items()
                    }
                    patience_counter = 0
                else:
                    patience_counter = epoch_idx + 1 - best_epoch
                    if self.early_stopping_enabled and patience_counter >= self.early_stopping_patience:
                        early_stopped = True
                        break
            elif self.lr_scheduler_kind == "cosine" and scheduler is not None:
                scheduler.step()

        if best_state is not None:
            model.load_state_dict(best_state)

        inference_hist = torch.tensor(prepared.history_features[-self.lookback:][None, :, :], dtype=torch.float32, device=device)
        inference_future = torch.tensor(np.asarray(future_features, dtype=np.float32)[None, :, :], dtype=torch.float32, device=device)

        model.eval()
        with torch.no_grad():
            with self._autocast_ctx(torch, amp_enabled):
                pred = model(inference_hist, inference_future)
            pred_np = pred.detach().cpu().numpy()[0]

        bias_curve = np.zeros(int(steps), dtype=np.float64)
        bias_summary = {
            "enabled": False,
            "validation_samples": int(validation_count),
            "strength": 0.0,
            "quantile": None,
            "upward_only": False,
            "curve_mean": 0.0,
            "curve_last": 0.0,
        }
        if validation_count > 0:
            val_hist_tensor = torch.tensor(val_x_hist_arr, dtype=torch.float32, device=device)
            val_future_tensor = torch.tensor(val_x_future_arr, dtype=torch.float32, device=device)
            with torch.no_grad():
                with self._autocast_ctx(torch, amp_enabled):
                    val_pred = model(val_hist_tensor, val_future_tensor)
                val_pred_np = val_pred.detach().cpu().numpy()
            if quantile_mode:
                val_center = val_pred_np[..., 1]
            else:
                val_center = val_pred_np.reshape(val_y_arr.shape)
            residual_matrix = val_y_arr.astype(np.float64) - np.asarray(val_center, dtype=np.float64)
            bias_quantile = float(_metric_bias_quantile(metric_code))
            if abs(bias_quantile - 0.5) < 1e-9:
                step_bias = np.median(residual_matrix, axis=0)
                overall_bias = float(np.median(residual_matrix))
            else:
                step_bias = np.quantile(residual_matrix, bias_quantile, axis=0)
                overall_bias = float(np.quantile(residual_matrix, bias_quantile))
            step_bias = _smooth_vector(np.asarray(step_bias, dtype=np.float64), window=min(24, max(3, steps // 24 or 3)))
            upward_only = _is_upward_risk_metric(metric_code)
            if upward_only:
                step_bias = np.maximum(step_bias, 0.0)
                overall_bias = max(0.0, overall_bias)
            strength = float(prepared.bias_correction_strength)
            bias_curve = strength * ((0.65 * step_bias) + (0.35 * overall_bias))
            bias_summary = {
                "enabled": True,
                "validation_samples": int(validation_count),
                "strength": float(strength),
                "quantile": float(bias_quantile),
                "upward_only": bool(upward_only),
                "curve_mean": float(np.mean(bias_curve)) if bias_curve.size else 0.0,
                "curve_last": float(bias_curve[-1]) if bias_curve.size else 0.0,
            }

        checkpoint_saved_to = self._save_checkpoint(
            model=model,
            device_serial=device_serial,
            metric_code=metric_code,
            freq=freq,
            steps=steps,
            horizon_key=horizon_key,
            meta=model_meta,
        )

        anchor_target_norm = float(prepared.target_norm[-1])
        if quantile_mode:
            q10 = pred_np[:, 0].astype(np.float64)
            q50 = pred_np[:, 1].astype(np.float64)
            q90 = pred_np[:, 2].astype(np.float64)
            if self.target_mode == "anchored_delta":
                q10 = q10 + anchor_target_norm
                q50 = q50 + anchor_target_norm
                q90 = q90 + anchor_target_norm
            if bias_curve.size:
                q10 = q10 + bias_curve
                q50 = q50 + bias_curve
                q90 = q90 + bias_curve
            interval_mode = "quantile_direct"
        else:
            center = pred_np.astype(np.float64).reshape(-1)
            if self.target_mode == "anchored_delta":
                center = center + anchor_target_norm
            with torch.no_grad():
                fitted = model(x_hist_tensor.to(device), x_future_tensor.to(device)).detach().cpu().numpy()
            resid = y_arr - np.asarray(fitted).reshape(y_arr.shape)
            resid_std = max(0.08, float(np.std(resid)))
            horizon_scale = np.sqrt(1.0 + (np.arange(steps, dtype=np.float64) / 24.0))
            width = 1.2815515655446004 * resid_std * horizon_scale
            if bias_curve.size:
                center = center + bias_curve
            q10 = center - width
            q50 = center
            q90 = center + width
            interval_mode = "residual_std_fallback"

        mean = (q50 * prepared.target_sigma) + prepared.target_mu
        lower = (q10 * prepared.target_sigma) + prepared.target_mu
        upper = (q90 * prepared.target_sigma) + prepared.target_mu
        train_runtime_sec = float(monotonic() - train_start)

        quality = {
            "model_version": MODEL_VERSION,
            "output_mode": self.output_mode,
            "loss_kind": self.loss_kind,
            "target_mode": self.target_mode,
            "interval_mode": interval_mode,
            "epochs": int(self.epochs),
            "lookback": int(self.lookback),
            "hidden_size": int(self.hidden_size),
            "dropout": float(self.dropout),
            "weight_decay": float(self.weight_decay),
            "batch_size": int(self.batch_size),
            "train_mode": self.train_mode,
            "recency_weighted_loss": bool(self.recency_weighted_loss),
            "recency_weight_min": float(self.recency_weight_min),
            "recency_weight_power": float(self.recency_weight_power),
            "warm_start_loaded": bool(warm_start_loaded),
            "checkpoint_path": checkpoint_path or checkpoint_saved_to,
            "final_train_loss": float(final_train_loss) if final_train_loss is not None else None,
            "final_val_loss": float(final_val_loss) if final_val_loss is not None else None,
            "best_val_loss": float(best_val_loss) if best_val_loss is not None else None,
            "best_epoch": int(best_epoch) if best_epoch else None,
            "epochs_trained": int(epochs_trained),
            "early_stopped": bool(early_stopped),
            "train_samples": int(len(dataset)),
            "validation_samples": int(validation_count),
            "steps_total": int(steps),
            "runtime_sec": train_runtime_sec,
            "history_input_size": history_input_size,
            "future_input_size": future_input_size,
            "output_limit_norm": float(self._output_limit_norm),
            "bias_correction": bias_summary,
            "lr_scheduler_kind": self.lr_scheduler_kind,
            "lr_scheduler_patience": int(self.lr_scheduler_patience),
            "lr_scheduler_factor": float(self.lr_scheduler_factor),
            "lr_scheduler_min_lr": float(self.lr_scheduler_min_lr),
            "early_stopping_enabled": bool(self.early_stopping_enabled),
            "early_stopping_patience": int(self.early_stopping_patience),
            "early_stopping_min_delta": float(self.early_stopping_min_delta),
            "last_learning_rate": float(optimizer.param_groups[0].get("lr", self.learning_rate)),
        }
        return mean, lower, upper, quality


@dataclass
class MetricForecastPack:
    metric_code: str
    mean: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    last_timestamp: pd.Timestamp
    diagnostics: dict[str, Any]


def run_lstm_job(payload: ForecastRequest) -> ForecastResult:
    options = payload.options or {}
    epochs = _safe_int(options.get("epochs", settings.default_epochs), settings.default_epochs, min_value=4)
    lookback = _safe_int(options.get("lookback", settings.default_lookback), settings.default_lookback, min_value=24)
    hidden_size = _safe_int(options.get("hidden_size", settings.default_hidden_size), settings.default_hidden_size, min_value=16)
    learning_rate = _safe_float(options.get("learning_rate", settings.default_lr), settings.default_lr, min_value=1e-5)
    alpha = _safe_float(options.get("alpha", 0.2), 0.2, min_value=0.0)
    device_preference = str(options.get("device", settings.torch_device) or settings.torch_device).strip().lower()
    amp = _as_bool(options.get("amp", settings.torch_amp), default=settings.torch_amp)
    gpu_index = _safe_int(options.get("gpu_index", settings.torch_gpu_index), settings.torch_gpu_index, min_value=0)
    dropout = _safe_float(options.get("dropout", settings.default_dropout), settings.default_dropout, min_value=0.0)
    weight_decay = _safe_float(options.get("weight_decay", settings.default_weight_decay), settings.default_weight_decay, min_value=0.0)
    batch_size = _safe_int(options.get("batch_size", settings.default_batch_size), settings.default_batch_size, min_value=4)
    use_calendar_features = _as_bool(options.get("use_calendar_features", options.get("calendar_features", True)), default=True)
    use_seasonal_residual = _as_bool(options.get("use_seasonal_residual", options.get("seasonal_residual", True)), default=True)
    seasonality_mode = str(options.get("seasonality_mode", settings.default_seasonality_mode) or settings.default_seasonality_mode).strip().lower() or "rolling_profile"
    seasonality_window_days = _safe_int(options.get("seasonality_window_days", settings.default_seasonality_window_days), settings.default_seasonality_window_days, min_value=1)
    lags = _parse_lags(options.get("lags"), payload.freq)
    loss_kind = str(options.get("loss_kind", settings.default_loss_kind) or settings.default_loss_kind).strip().lower() or DEFAULT_LOSS_KIND
    if loss_kind not in ("quantile", "huber", "mse"):
        loss_kind = DEFAULT_LOSS_KIND
    output_mode = str(options.get("output_mode", settings.default_output_mode) or settings.default_output_mode).strip().lower() or DEFAULT_OUTPUT_MODE
    if output_mode not in ("direct_multi_horizon",):
        output_mode = DEFAULT_OUTPUT_MODE
    forecast_stride = _safe_int(options.get("forecast_stride", 1), 1, min_value=1)
    if forecast_stride != 1:
        forecast_stride = 1
    train_mode = str(options.get("train_mode", settings.default_train_mode) or settings.default_train_mode).strip().lower() or DEFAULT_TRAIN_MODE
    if train_mode not in ("fit_on_request", "warm_start"):
        train_mode = DEFAULT_TRAIN_MODE
    target_mode = str(options.get("target_mode", getattr(settings, "default_target_mode", DEFAULT_TARGET_MODE)) or getattr(settings, "default_target_mode", DEFAULT_TARGET_MODE)).strip().lower() or DEFAULT_TARGET_MODE
    if target_mode not in ("anchored_delta", "absolute_level"):
        target_mode = DEFAULT_TARGET_MODE
    recency_weighted_loss = _as_bool(options.get("recency_weighted_loss", getattr(settings, "default_recency_weighted_loss", True)), default=getattr(settings, "default_recency_weighted_loss", True))
    recency_weight_min = _safe_float(options.get("recency_weight_min", getattr(settings, "default_recency_weight_min", 0.35)), getattr(settings, "default_recency_weight_min", 0.35), min_value=0.05)
    recency_weight_power = _safe_float(options.get("recency_weight_power", getattr(settings, "default_recency_weight_power", 2.0)), getattr(settings, "default_recency_weight_power", 2.0), min_value=1.0)
    early_stopping_enabled = _as_bool(
        options.get("early_stopping_enabled", getattr(settings, "default_early_stopping_enabled", True)),
        default=getattr(settings, "default_early_stopping_enabled", True),
    )
    early_stopping_patience = _safe_int(
        options.get("early_stopping_patience", getattr(settings, "default_early_stopping_patience", 10)),
        getattr(settings, "default_early_stopping_patience", 10),
        min_value=1,
    )
    early_stopping_min_delta = _safe_float(
        options.get("early_stopping_min_delta", getattr(settings, "default_early_stopping_min_delta", 0.0005)),
        getattr(settings, "default_early_stopping_min_delta", 0.0005),
        min_value=0.0,
    )
    lr_scheduler_kind = str(
        options.get("lr_scheduler_kind", getattr(settings, "default_scheduler_kind", "plateau"))
        or getattr(settings, "default_scheduler_kind", "plateau")
    ).strip().lower()
    if lr_scheduler_kind not in ("plateau", "cosine", "none"):
        lr_scheduler_kind = "plateau"
    lr_scheduler_patience = _safe_int(
        options.get("lr_scheduler_patience", getattr(settings, "default_scheduler_patience", 4)),
        getattr(settings, "default_scheduler_patience", 4),
        min_value=1,
    )
    lr_scheduler_factor = _safe_float(
        options.get("lr_scheduler_factor", getattr(settings, "default_scheduler_factor", 0.5)),
        getattr(settings, "default_scheduler_factor", 0.5),
        min_value=0.1,
    )
    lr_scheduler_min_lr = _safe_float(
        options.get("lr_scheduler_min_lr", getattr(settings, "default_scheduler_min_lr", 1e-5)),
        getattr(settings, "default_scheduler_min_lr", 1e-5),
        min_value=1e-7,
    )
    metric_overrides = _parse_metric_overrides(options.get("metric_overrides"))
    horizon_key = str(options.get("horizon_key") or "").strip() or _max_horizon_key(payload.horizons, payload.freq)
    calendar_cfg = CalendarFeatureConfig.from_options(options)

    forecaster = LSTMForecaster(
        epochs=epochs,
        lookback=lookback,
        hidden_size=hidden_size,
        learning_rate=learning_rate,
        device_preference=device_preference,
        amp=amp,
        gpu_index=gpu_index,
        dropout=dropout,
        weight_decay=weight_decay,
        batch_size=batch_size,
        output_mode=output_mode,
        loss_kind=loss_kind,
        train_mode=train_mode,
        target_mode=target_mode,
        recency_weighted_loss=recency_weighted_loss,
        recency_weight_min=recency_weight_min,
        recency_weight_power=recency_weight_power,
        early_stopping_enabled=early_stopping_enabled,
        early_stopping_patience=early_stopping_patience,
        early_stopping_min_delta=early_stopping_min_delta,
        lr_scheduler_kind=lr_scheduler_kind,
        lr_scheduler_patience=lr_scheduler_patience,
        lr_scheduler_factor=lr_scheduler_factor,
        lr_scheduler_min_lr=lr_scheduler_min_lr,
        checkpoint_dir=settings.checkpoint_dir,
    )
    runtime_info = forecaster.runtime_info()

    metrics_processed = 0
    metrics_skipped = 0
    errors: list[str] = []
    metric_diagnostics: dict[str, Any] = {}

    packs: list[MetricForecastPack] = []
    max_steps = max(_horizon_to_steps(h, payload.freq) for h in payload.horizons)
    try:
        freq_step = pd.to_timedelta(payload.freq)
    except Exception:
        freq_step = pd.to_timedelta("1h")

    for metric_code, points in (payload.metrics or {}).items():
        metric_started = monotonic()
        try:
            rows = [{"timestamp": item.timestamp, "value": item.value} for item in (points or [])]
            series = _to_series(rows, payload.freq, settings.max_points_per_metric)
            if len(series) < (lookback + max_steps + 8):
                metrics_skipped += 1
                metric_diagnostics[metric_code] = {
                    "status": "skipped",
                    "reason": "not_enough_points",
                    "points": int(len(series)),
                    "min_required": int(lookback + max_steps + 8),
                }
                continue

            prepared = _prepare_series_features(
                metric_code=metric_code,
                series=series,
                freq=payload.freq,
                calendar_cfg=calendar_cfg,
                use_calendar_features=use_calendar_features,
                use_seasonal_residual=use_seasonal_residual,
                seasonality_mode=seasonality_mode,
                seasonality_window_days=seasonality_window_days,
                lags=lags,
                metric_overrides=metric_overrides,
            )
            future_index = _build_future_index(series.index[-1], steps=max_steps, freq_step=freq_step)
            future_trend_values = _extrapolate_future_trend(
                anchor_trend_value=float(prepared.trend_values[-1]),
                short_slope_value=float(prepared.trend_slope_short_values[-1]),
                long_slope_value=float(prepared.trend_slope_values[-1]),
                total_steps=max_steps,
                transition_steps=int(prepared.trend_transition_steps),
                enforce_long_floor=_metric_enforce_long_floor(metric_code),
            )
            future_features = _build_future_decoder_features(
                future_index=future_index,
                total_steps=max_steps,
                calendar_cfg=calendar_cfg,
                use_calendar_features=use_calendar_features,
                seasonal_profile=prepared.seasonal_profile,
                raw_mu=prepared.raw_mu,
                raw_sigma=prepared.raw_sigma,
                future_trend_values=future_trend_values,
                anchor_target_norm=float(prepared.target_norm[-1]),
                anchor_raw_norm=float(prepared.raw_norm[-1]),
                anchor_trend_norm=float(prepared.trend_norm[-1]),
                recent_mean_24=float(prepared.roll_mean_24[-1]),
                recent_slope_24=float(prepared.slope_24[-1]),
            )
            residual_mean, residual_lower, residual_upper, fit_quality = forecaster.forecast(
                prepared,
                device_serial=payload.device_serial,
                metric_code=metric_code,
                freq=payload.freq,
                steps=max_steps,
                horizon_key=horizon_key,
                future_features=future_features,
            )
            seasonal_future = prepared.seasonal_profile.values_for_index(future_index) if use_seasonal_residual else np.zeros(max_steps, dtype=np.float64)
            mean = future_trend_values + seasonal_future + residual_mean
            lower = future_trend_values + seasonal_future + residual_lower
            upper = future_trend_values + seasonal_future + residual_upper

            diagnostics = {
                **fit_quality,
                "status": "ok",
                "points_used": int(len(series)),
                "decomposition_mode": "trend_plus_zero_centered_seasonality_plus_nn_residual",
                "seasonality_mode_requested": prepared.seasonal_profile.requested_mode,
                "seasonality_mode_effective": prepared.seasonal_profile.effective_mode,
                "seasonality_window_days": int(prepared.seasonal_profile.window_days),
                "seasonality_zero_centered": bool(prepared.seasonal_profile.zero_centered),
                "trend_long_mode": str(prepared.trend_long_mode),
                "trend_envelope_quantile": prepared.trend_envelope_quantile,
                "trend_envelope_weight": float(prepared.trend_envelope_weight),
                "trend_short_window_steps": int(prepared.trend_short_window_steps),
                "trend_long_slope_window_steps": int(prepared.trend_long_slope_window_steps),
                "trend_window_steps": int(prepared.trend_window_steps),
                "trend_transition_steps": int(prepared.trend_transition_steps),
                "trend_damping_steps": int(prepared.trend_transition_steps),
                "trend_projection_mode": "hybrid_short_to_regression_long_with_floor" if _metric_enforce_long_floor(metric_code) else "hybrid_short_to_regression_long",
                "trend_short_slope_anchor": float(prepared.trend_slope_short_values[-1]),
                "trend_long_slope_anchor": float(prepared.trend_slope_values[-1]),
                "trend_long_floor_enforced": bool(_metric_enforce_long_floor(metric_code)),
                "rolling_seasonality": bool(use_seasonal_residual and prepared.seasonal_profile.effective_mode in ("rolling_profile", "stl_like_local")),
                "quantile_mode": bool(loss_kind == "quantile"),
                "calendar_features": bool(use_calendar_features),
                "forecast_stride": int(forecast_stride),
                "lags": list(lags),
                "target_mode": target_mode,
                "recency_weighted_loss": bool(recency_weighted_loss),
                "recency_weight_min": float(recency_weight_min),
                "recency_weight_power": float(recency_weight_power),
                "early_stopping_enabled": bool(early_stopping_enabled),
                "early_stopping_patience": int(early_stopping_patience),
                "early_stopping_min_delta": float(early_stopping_min_delta),
                "lr_scheduler_kind": lr_scheduler_kind,
                "lr_scheduler_patience": int(lr_scheduler_patience),
                "lr_scheduler_factor": float(lr_scheduler_factor),
                "lr_scheduler_min_lr": float(lr_scheduler_min_lr),
                "horizon_key": horizon_key,
                "metric_runtime_sec": float(monotonic() - metric_started),
            }
            metric_diagnostics[metric_code] = diagnostics

            packs.append(
                MetricForecastPack(
                    metric_code=metric_code,
                    mean=mean,
                    lower=lower,
                    upper=upper,
                    last_timestamp=series.index[-1],
                    diagnostics=diagnostics,
                )
            )
            metrics_processed += 1
        except Exception as exc:
            metric_diagnostics[metric_code] = {
                "status": "failed",
                "error": str(exc),
                "metric_runtime_sec": float(monotonic() - metric_started),
            }
            errors.append(f"{metric_code}: {exc}")
            metrics_skipped += 1

    forecasts: list[ForecastItem] = []
    for pack in packs:
        for horizon in payload.horizons:
            steps_total = _horizon_to_steps(horizon, payload.freq)
            for step_idx in range(steps_total):
                idx = step_idx
                if idx >= len(pack.mean):
                    break
                y_hat = float(pack.mean[idx])
                p10 = float(pack.lower[idx])
                p90 = float(pack.upper[idx])
                target_ts = pack.last_timestamp + (freq_step * (step_idx + 1))
                forecasts.append(
                    ForecastItem(
                        metric_code=pack.metric_code,
                        horizon=horizon,
                        target_ts=target_ts.to_pydatetime(),
                        forecast_step=int(step_idx + 1),
                        forecast_steps_total=int(steps_total),
                        y_hat=y_hat,
                        p10=min(p10, p90),
                        p50=y_hat,
                        p90=max(p10, p90),
                        alpha=alpha,
                        labels={
                            "source": "lstm_remote",
                            "model_version": MODEL_VERSION,
                            "decomposition_mode": "trend_plus_zero_centered_seasonality_plus_nn_residual",
                            "freq": payload.freq,
                            "epochs": epochs,
                            "lookback": lookback,
                            "hidden_size": hidden_size,
                            "learning_rate": learning_rate,
                            "dropout": dropout,
                            "weight_decay": weight_decay,
                            "batch_size": batch_size,
                            "lags": list(lags),
                            "use_calendar_features": bool(use_calendar_features),
                            "use_seasonal_residual": bool(use_seasonal_residual),
                            "seasonality_mode": seasonality_mode,
                            "seasonality_window_days": int(seasonality_window_days),
                            "seasonality_zero_centered": bool(pack.diagnostics.get("seasonality_zero_centered")),
                            "trend_long_mode": str(pack.diagnostics.get("trend_long_mode") or _metric_trend_mode(pack.metric_code)),
                            "trend_envelope_quantile": pack.diagnostics.get("trend_envelope_quantile"),
                            "trend_envelope_weight": pack.diagnostics.get("trend_envelope_weight"),
                            "trend_short_window_steps": int(pack.diagnostics.get("trend_short_window_steps") or _short_trend_window_steps(payload.freq)),
                            "trend_long_slope_window_steps": int(pack.diagnostics.get("trend_long_slope_window_steps") or _long_slope_window_steps(payload.freq)),
                            "trend_window_steps": int(pack.diagnostics.get("trend_window_steps") or _trend_window_steps(payload.freq)),
                            "trend_transition_steps": int(pack.diagnostics.get("trend_transition_steps") or _trend_transition_steps(payload.freq)),
                            "trend_damping_steps": int(pack.diagnostics.get("trend_damping_steps") or _trend_transition_steps(payload.freq)),
                            "trend_projection_mode": str(pack.diagnostics.get("trend_projection_mode") or "hybrid_short_to_regression_long"),
                            "trend_short_slope_anchor": pack.diagnostics.get("trend_short_slope_anchor"),
                            "trend_long_slope_anchor": pack.diagnostics.get("trend_long_slope_anchor"),
                            "trend_long_floor_enforced": bool(pack.diagnostics.get("trend_long_floor_enforced")),
                            "bias_correction_enabled": bool((pack.diagnostics.get("bias_correction") or {}).get("enabled")),
                            "bias_correction_strength": (pack.diagnostics.get("bias_correction") or {}).get("strength"),
                            "bias_correction_quantile": (pack.diagnostics.get("bias_correction") or {}).get("quantile"),
                            "bias_correction_curve_mean": (pack.diagnostics.get("bias_correction") or {}).get("curve_mean"),
                            "bias_correction_curve_last": (pack.diagnostics.get("bias_correction") or {}).get("curve_last"),
                            "output_mode": output_mode,
                            "loss_kind": loss_kind,
                            "target_mode": target_mode,
                            "interval_mode": pack.diagnostics.get("interval_mode"),
                            "output_limit_norm": pack.diagnostics.get("output_limit_norm"),
                            "train_mode": train_mode,
                            "horizon_key": horizon_key,
                            "recency_weighted_loss": bool(recency_weighted_loss),
                            "recency_weight_min": float(recency_weight_min),
                            "recency_weight_power": float(recency_weight_power),
                            "early_stopping_enabled": bool(early_stopping_enabled),
                            "early_stopping_patience": int(early_stopping_patience),
                            "early_stopping_min_delta": float(early_stopping_min_delta),
                            "lr_scheduler_kind": lr_scheduler_kind,
                            "lr_scheduler_patience": int(lr_scheduler_patience),
                            "lr_scheduler_factor": float(lr_scheduler_factor),
                            "lr_scheduler_min_lr": float(lr_scheduler_min_lr),
                            "rolling_seasonality": bool(pack.diagnostics.get("rolling_seasonality")),
                            "quantile_mode": bool(pack.diagnostics.get("quantile_mode")),
                            "warm_start_loaded": bool(pack.diagnostics.get("warm_start_loaded")),
                            "calendar_profile": calendar_cfg.to_labels(),
                            "torch_device": runtime_info.get("device"),
                            "torch_amp": runtime_info.get("amp_enabled"),
                        },
                    )
                )

    quality = {
        "metrics_processed": metrics_processed,
        "metrics_skipped": metrics_skipped,
        "forecast_points_emitted": len(forecasts),
        "errors": errors,
        "model_version": MODEL_VERSION,
        "decomposition_mode": "trend_plus_zero_centered_seasonality_plus_nn_residual",
        "output_mode": output_mode,
        "loss_kind": loss_kind,
        "target_mode": target_mode,
        "interval_mode": "quantile_direct" if loss_kind == "quantile" else "residual_std_fallback",
        "seasonality_mode": seasonality_mode,
        "seasonality_window_days": int(seasonality_window_days),
        "seasonality_zero_centered": True,
        "trend_short_window_steps": int(_short_trend_window_steps(payload.freq)),
        "trend_long_slope_window_steps": int(_long_slope_window_steps(payload.freq)),
        "trend_window_steps": int(_trend_window_steps(payload.freq)),
        "trend_transition_steps": int(_trend_transition_steps(payload.freq)),
        "trend_damping_steps": int(_trend_transition_steps(payload.freq)),
        "trend_projection_mode": "hybrid_short_to_regression_long",
        "lookback": int(lookback),
        "epochs": int(epochs),
        "hidden_size": int(hidden_size),
        "learning_rate": float(learning_rate),
        "dropout": float(dropout),
        "weight_decay": float(weight_decay),
        "batch_size": int(batch_size),
        "train_mode": train_mode,
        "horizon_key": horizon_key,
        "recency_weighted_loss": bool(recency_weighted_loss),
        "recency_weight_min": float(recency_weight_min),
        "recency_weight_power": float(recency_weight_power),
        "early_stopping_enabled": bool(early_stopping_enabled),
        "early_stopping_patience": int(early_stopping_patience),
        "early_stopping_min_delta": float(early_stopping_min_delta),
        "lr_scheduler_kind": lr_scheduler_kind,
        "lr_scheduler_patience": int(lr_scheduler_patience),
        "lr_scheduler_factor": float(lr_scheduler_factor),
        "lr_scheduler_min_lr": float(lr_scheduler_min_lr),
        "forecast_stride": int(forecast_stride),
        "lags": list(lags),
        "metric_overrides": metric_overrides,
        "modeling": {
            "use_calendar_features": bool(use_calendar_features),
            "use_seasonal_residual": bool(use_seasonal_residual),
            "calendar_profile": calendar_cfg.to_labels(),
        },
        "metrics": metric_diagnostics,
        "runtime": runtime_info,
    }
    return ForecastResult(forecasts=forecasts, quality=quality)
