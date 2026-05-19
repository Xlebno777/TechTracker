from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
import bisect
import csv
import itertools
import json
import math
import random
from typing import Iterable
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from django.db.models import Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from inventory_api.models import (
    DecisionFeedback,
    DecisionRun,
    DecisionRunScore,
    ForecastPoint,
    RawMetric,
)


DEFAULT_HORIZONS = ["24h", "7d", "30d"]
DEFAULT_MODEL_KINDS = ["sarima", "lstm", "ensemble"]
DEFAULT_BASELINE_ACTION_CODE = "no_action"


@dataclass
class ErrorAggregate:
    n: int = 0
    sum_error: float = 0.0
    sum_abs: float = 0.0
    sum_sq: float = 0.0
    sum_ape: float = 0.0
    ape_n: int = 0
    sum_smape: float = 0.0
    smape_n: int = 0
    sum_scaled_abs: float = 0.0
    scaled_abs_n: int = 0
    sum_scaled_sq: float = 0.0
    scaled_sq_n: int = 0
    sum_pinball_q10: float = 0.0
    pinball_q10_n: int = 0
    sum_pinball_q50: float = 0.0
    pinball_q50_n: int = 0
    sum_pinball_q90: float = 0.0
    pinball_q90_n: int = 0
    interval_n: int = 0
    interval_covered_n: int = 0
    sum_interval_width: float = 0.0
    sum_winkler_80: float = 0.0

    @staticmethod
    def _pinball(actual: float, pred: float, tau: float) -> float:
        diff = float(actual) - float(pred)
        if diff >= 0.0:
            return float(tau) * diff
        return (float(tau) - 1.0) * diff

    def add(
        self,
        *,
        actual: float,
        predicted: float,
        p10: float | None = None,
        p50: float | None = None,
        p90: float | None = None,
        scale_mae: float | None = None,
        scale_mse: float | None = None,
    ) -> dict:
        err = float(predicted) - float(actual)
        abs_err = abs(err)
        sq_err = err * err
        ape = None
        smape = None
        scaled_abs_error = None
        scaled_sq_error = None
        pinball_q10 = None
        pinball_q50 = None
        pinball_q90 = None
        pinball_avg = None
        in_interval80 = None
        winkler80 = None
        if abs(float(actual)) > 1e-12:
            ape = abs_err / abs(float(actual))
            self.sum_ape += ape
            self.ape_n += 1
        denom_smape = abs(float(actual)) + abs(float(predicted))
        if denom_smape > 1e-12:
            smape = (2.0 * abs_err) / denom_smape
        else:
            smape = 0.0
        self.sum_smape += float(smape)
        self.smape_n += 1

        if scale_mae is not None and float(scale_mae) > 1e-12:
            scaled_abs_error = abs_err / float(scale_mae)
            self.sum_scaled_abs += scaled_abs_error
            self.scaled_abs_n += 1
        if scale_mse is not None and float(scale_mse) > 1e-12:
            scaled_sq_error = sq_err / float(scale_mse)
            self.sum_scaled_sq += scaled_sq_error
            self.scaled_sq_n += 1

        if p10 is not None:
            pinball_q10 = self._pinball(actual, p10, 0.1)
            self.sum_pinball_q10 += pinball_q10
            self.pinball_q10_n += 1
        if p50 is not None:
            pinball_q50 = self._pinball(actual, p50, 0.5)
            self.sum_pinball_q50 += pinball_q50
            self.pinball_q50_n += 1
        if p90 is not None:
            pinball_q90 = self._pinball(actual, p90, 0.9)
            self.sum_pinball_q90 += pinball_q90
            self.pinball_q90_n += 1
        pinball_values = [v for v in (pinball_q10, pinball_q50, pinball_q90) if v is not None]
        if pinball_values:
            pinball_avg = sum(pinball_values) / float(len(pinball_values))

        if p10 is not None and p90 is not None:
            lower = min(float(p10), float(p90))
            upper = max(float(p10), float(p90))
            alpha = 0.2
            width = max(0.0, upper - lower)
            covered = lower <= float(actual) <= upper
            in_interval80 = 1 if covered else 0
            self.interval_n += 1
            self.interval_covered_n += in_interval80
            self.sum_interval_width += width

            winkler = width
            if float(actual) < lower:
                winkler += (2.0 / alpha) * (lower - float(actual))
            elif float(actual) > upper:
                winkler += (2.0 / alpha) * (float(actual) - upper)
            winkler80 = winkler
            self.sum_winkler_80 += winkler

        self.n += 1
        self.sum_error += err
        self.sum_abs += abs_err
        self.sum_sq += sq_err
        return {
            "error": err,
            "abs_error": abs_err,
            "sq_error": sq_err,
            "ape": ape,
            "smape": smape,
            "scaled_abs_error": scaled_abs_error,
            "scaled_sq_error": scaled_sq_error,
            "pinball_q10": pinball_q10,
            "pinball_q50": pinball_q50,
            "pinball_q90": pinball_q90,
            "pinball_avg": pinball_avg,
            "in_interval80": in_interval80,
            "winkler80": winkler80,
        }

    def metrics(self) -> dict:
        if self.n <= 0:
            return {
                "n": 0,
                "mean_error": None,
                "mae": None,
                "rmse": None,
                "mape": None,
                "smape": None,
                "mase": None,
                "rmsse": None,
                "pinball_q10": None,
                "pinball_q50": None,
                "pinball_q90": None,
                "pinball_avg": None,
                "picp80": None,
                "ace80": None,
                "miw": None,
                "winkler80": None,
            }
        mae = self.sum_abs / self.n
        rmse = math.sqrt(self.sum_sq / self.n)
        mean_error = self.sum_error / self.n
        mape = (self.sum_ape / self.ape_n) if self.ape_n > 0 else None
        smape = (self.sum_smape / self.smape_n) if self.smape_n > 0 else None
        mase = (self.sum_scaled_abs / self.scaled_abs_n) if self.scaled_abs_n > 0 else None
        rmsse = math.sqrt(self.sum_scaled_sq / self.scaled_sq_n) if self.scaled_sq_n > 0 else None
        pinball_q10 = (self.sum_pinball_q10 / self.pinball_q10_n) if self.pinball_q10_n > 0 else None
        pinball_q50 = (self.sum_pinball_q50 / self.pinball_q50_n) if self.pinball_q50_n > 0 else None
        pinball_q90 = (self.sum_pinball_q90 / self.pinball_q90_n) if self.pinball_q90_n > 0 else None
        pinball_values = [v for v in (pinball_q10, pinball_q50, pinball_q90) if v is not None]
        pinball_avg = (sum(pinball_values) / float(len(pinball_values))) if pinball_values else None
        picp80 = (self.interval_covered_n / float(self.interval_n)) if self.interval_n > 0 else None
        ace80 = abs(picp80 - 0.8) if picp80 is not None else None
        miw = (self.sum_interval_width / float(self.interval_n)) if self.interval_n > 0 else None
        winkler80 = (self.sum_winkler_80 / float(self.interval_n)) if self.interval_n > 0 else None
        return {
            "n": int(self.n),
            "mean_error": float(mean_error),
            "mae": float(mae),
            "rmse": float(rmse),
            "mape": float(mape) if mape is not None else None,
            "smape": float(smape) if smape is not None else None,
            "mase": float(mase) if mase is not None else None,
            "rmsse": float(rmsse) if rmsse is not None else None,
            "pinball_q10": float(pinball_q10) if pinball_q10 is not None else None,
            "pinball_q50": float(pinball_q50) if pinball_q50 is not None else None,
            "pinball_q90": float(pinball_q90) if pinball_q90 is not None else None,
            "pinball_avg": float(pinball_avg) if pinball_avg is not None else None,
            "picp80": float(picp80) if picp80 is not None else None,
            "ace80": float(ace80) if ace80 is not None else None,
            "miw": float(miw) if miw is not None else None,
            "winkler80": float(winkler80) if winkler80 is not None else None,
        }


@dataclass
class MetricSeries:
    timestamps: list
    values: list[float]
    _resampled_cache: dict[str, pd.Series] | None = None
    _scale_cache: dict[str, tuple[float | None, float | None]] | None = None

    def nearest(self, target_ts, tolerance: timedelta) -> float | None:
        if not self.timestamps:
            return None
        idx = bisect.bisect_left(self.timestamps, target_ts)
        candidates = []
        if idx < len(self.timestamps):
            candidates.append(idx)
        if idx > 0:
            candidates.append(idx - 1)
        if not candidates:
            return None
        best_idx = None
        best_delta = None
        for cand_idx in candidates:
            delta = abs((self.timestamps[cand_idx] - target_ts).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_idx = cand_idx
        if best_idx is None or best_delta is None:
            return None
        if best_delta > max(1.0, float(tolerance.total_seconds())):
            return None
        return float(self.values[best_idx])

    def _get_resampled(self, freq: str) -> pd.Series:
        if self._resampled_cache is None:
            self._resampled_cache = {}
        freq_key = str(freq or "").strip().lower() or "1h"
        if freq_key in self._resampled_cache:
            return self._resampled_cache[freq_key]
        if not self.timestamps:
            series = pd.Series(dtype=float)
            self._resampled_cache[freq_key] = series
            return series
        series = pd.Series(
            [float(v) for v in self.values],
            index=pd.DatetimeIndex(self.timestamps),
            dtype=float,
        )
        series = series[~series.index.duplicated(keep="last")].sort_index()
        try:
            series = series.resample(freq_key).mean().interpolate(method="time", limit_direction="both").ffill().bfill()
        except Exception:
            series = series.sort_index()
        self._resampled_cache[freq_key] = series
        return series

    def seasonal_scales(self, freq: str) -> tuple[float | None, float | None]:
        if self._scale_cache is None:
            self._scale_cache = {}
        freq_key = str(freq or "").strip().lower() or "1h"
        cached = self._scale_cache.get(freq_key)
        if cached is not None:
            return cached
        series = self._get_resampled(freq_key)
        if series.empty:
            out = (None, None)
            self._scale_cache[freq_key] = out
            return out

        lag = _seasonal_lag_from_freq(freq_key)
        if len(series) <= lag:
            lag = 1
        if len(series) <= lag:
            out = (None, None)
            self._scale_cache[freq_key] = out
            return out

        diff = series.astype(float) - series.astype(float).shift(lag)
        diff = diff.dropna()
        if diff.empty:
            out = (None, None)
            self._scale_cache[freq_key] = out
            return out
        scale_mae = float(diff.abs().mean())
        scale_mse = float((diff ** 2).mean())
        if not math.isfinite(scale_mae) or scale_mae <= 1e-12:
            scale_mae = None
        if not math.isfinite(scale_mse) or scale_mse <= 1e-12:
            scale_mse = None
        out = (scale_mae, scale_mse)
        self._scale_cache[freq_key] = out
        return out


def _as_float(value, default=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _parse_csv_values(values: Iterable[str] | None, defaults: list[str]) -> list[str]:
    if not values:
        return list(defaults)
    out = []
    for item in values:
        raw = str(item or "").strip().lower()
        if raw:
            out.append(raw)
    if not out:
        return list(defaults)
    uniq = []
    seen = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def _freq_to_timedelta(freq: str | None) -> timedelta:
    raw = str(freq or "").strip().lower()
    try:
        if raw.endswith("min"):
            return timedelta(minutes=max(1, int(raw[:-3])))
        if raw.endswith("h"):
            return timedelta(hours=max(1, int(raw[:-1])))
        if raw.endswith("d"):
            return timedelta(days=max(1, int(raw[:-1])))
    except ValueError:
        return timedelta(hours=1)
    return timedelta(hours=1)


def _seasonal_lag_from_freq(freq: str | None) -> int:
    raw = str(freq or "").strip().lower()
    try:
        if raw.endswith("min"):
            minutes = max(1, int(raw[:-3]))
            return max(1, int(round((24 * 60) / float(minutes))))
        if raw.endswith("h"):
            hours = max(1, int(raw[:-1]))
            return max(1, int(round(24 / float(hours))))
        if raw.endswith("d"):
            return 7
    except (TypeError, ValueError):
        return 24
    return 24


def _point_freq(point: ForecastPoint) -> str:
    freq = None
    labels = point.labels if isinstance(point.labels, dict) else {}
    if isinstance(labels, dict):
        freq = labels.get("freq")
    if not freq and point.run_id and isinstance(point.run.parameters, dict):
        freq = point.run.parameters.get("freq")
    return str(freq or "1h")


def _point_tolerance(point: ForecastPoint) -> timedelta:
    freq = _point_freq(point)
    base = _freq_to_timedelta(freq)
    fallback = timedelta(hours=2)
    return max(fallback, base * 2)


def _forecast_variant_from_meta(model_kind: str | None, point_labels: dict | None, run_parameters: dict | None) -> tuple[str, str]:
    kind = str(model_kind or "").strip().lower() or "unknown"
    labels = point_labels if isinstance(point_labels, dict) else {}
    params = run_parameters if isinstance(run_parameters, dict) else {}

    if kind == "sarima":
        seasonality_mode = str(
            labels.get("seasonality_mode")
            or params.get("seasonality_mode")
            or ""
        ).strip().lower()
        if seasonality_mode == "sarima_seasonal":
            return ("sarima:sarima_seasonal", "SARIMA • сезонность в модели")
        if seasonality_mode == "stl_reseasonalized":
            return ("sarima:stl_reseasonalized", "SARIMA • STL + возврат сезонности")
        return ("sarima:unknown", "SARIMA • режим не указан")

    if kind == "lstm":
        return ("lstm", "LSTM")
    if kind == "ensemble":
        return ("ensemble", "Оркестр")
    return (kind, kind.upper())


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _to_iso(dt_value):
    if dt_value is None:
        return ""
    try:
        return dt_value.isoformat()
    except Exception:
        return str(dt_value)


def _coerce_datetime(value, *, end_of_day: bool = False):
    if value in (None, ""):
        return None
    dt_value = None
    if isinstance(value, datetime):
        dt_value = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        dt_value = parse_datetime(raw)
        if dt_value is None:
            parsed_date = parse_date(raw)
            if parsed_date is None:
                return None
            dt_value = datetime.combine(parsed_date, time.max if end_of_day else time.min)
    if timezone.is_naive(dt_value):
        dt_value = timezone.make_aware(dt_value, timezone.get_current_timezone())
    return dt_value


def _parse_int_values(values: Iterable[int | str] | None) -> list[int]:
    if not values:
        return []
    if not isinstance(values, (list, tuple, set)):
        values = str(values).split(",")
    out = []
    seen = set()
    for value in values:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            continue
        if parsed <= 0 or parsed in seen:
            continue
        seen.add(parsed)
        out.append(parsed)
    return out


def _normalize_evaluation_windows(
    *,
    days_back: int,
    target_date_from=None,
    target_date_to=None,
    actual_date_from=None,
    actual_date_to=None,
) -> dict:
    now = timezone.now()
    target_to = _coerce_datetime(target_date_to, end_of_day=True) or now
    target_from = _coerce_datetime(target_date_from, end_of_day=False)
    if target_from is None:
        target_from = target_to - timedelta(days=max(1, int(days_back)))
    if target_from > target_to:
        target_from, target_to = target_to, target_from

    actual_from_dt = _coerce_datetime(actual_date_from, end_of_day=False) or (target_from - timedelta(days=2))
    actual_to_dt = _coerce_datetime(actual_date_to, end_of_day=True) or (target_to + timedelta(days=2))
    if actual_from_dt > actual_to_dt:
        actual_from_dt, actual_to_dt = actual_to_dt, actual_from_dt

    return {
        "target_from": target_from,
        "target_to": target_to,
        "actual_from": actual_from_dt,
        "actual_to": actual_to_dt,
    }


def _collect_evaluation_point_rows(
    *,
    serial: str | None,
    target_from,
    target_to,
    actual_from,
    actual_to,
    selected_horizons: list[str],
    selected_models: list[str],
    strict_intersection: bool,
    forecast_run_ids: Iterable[int | str] | None = None,
) -> dict:
    points_qs = (
        ForecastPoint.objects
        .filter(
            target_ts__gte=target_from,
            target_ts__lte=target_to,
            model_kind__in=selected_models,
            horizon__in=selected_horizons,
            run__status="success",
        )
        .select_related("run", "device")
        .order_by("target_ts", "id")
    )
    if serial:
        points_qs = points_qs.filter(device__serial_number=serial)

    parsed_run_ids = _parse_int_values(forecast_run_ids)
    if parsed_run_ids:
        points_qs = points_qs.filter(run_id__in=parsed_run_ids)

    series_cache: dict[tuple[int, str], MetricSeries] = {}
    point_rows: list[dict] = []
    total_points = 0
    points_with_actual = 0
    raw_metric_points_total = 0
    raw_streams_total = 0

    bucket_total: dict[tuple[str, str], int] = {}
    bucket_with_actual: dict[tuple[str, str], int] = {}

    for point in points_qs.iterator(chunk_size=2000):
        total_points += 1
        bucket_key = (str(point.model_kind or "").strip().lower(), str(point.horizon or "").strip().lower())
        bucket_total[bucket_key] = bucket_total.get(bucket_key, 0) + 1

        cache_key = (point.device_id, str(point.metric_code))
        if cache_key not in series_cache:
            raw_rows = list(
                RawMetric.objects
                .filter(
                    device_id=point.device_id,
                    code=point.metric_code,
                    timestamp__gte=actual_from,
                    timestamp__lte=actual_to,
                )
                .order_by("timestamp", "id")
                .values_list("timestamp", "value")
            )
            ts_values = []
            metric_values = []
            for ts, value in raw_rows:
                val = _as_float(value, None)
                if val is None:
                    continue
                ts_values.append(ts)
                metric_values.append(val)
            raw_metric_points_total += len(metric_values)
            raw_streams_total += 1
            series_cache[cache_key] = MetricSeries(timestamps=ts_values, values=metric_values)

        point_freq = _point_freq(point)
        tolerance = _point_tolerance(point)
        actual_value = series_cache[cache_key].nearest(point.target_ts, tolerance=tolerance)
        pred_value = _as_float(point.y_hat, None)
        if pred_value is None:
            continue
        p10_value = _as_float(point.p10, None)
        p50_value = _as_float(point.p50, pred_value)
        p90_value = _as_float(point.p90, None)

        row = {
            "device_id": point.device_id,
            "device_serial": point.device.serial_number,
            "model_kind": point.model_kind,
            "horizon": point.horizon,
            "metric_code": point.metric_code,
            "run_id": point.run_id,
            "target_ts": _to_iso(point.target_ts),
            "predicted": pred_value,
            "actual": actual_value,
            "freq": point_freq,
            "error": "",
            "abs_error": "",
            "sq_error": "",
            "ape": "",
            "smape": "",
            "scaled_abs_error": "",
            "scaled_sq_error": "",
            "pinball_q10": "",
            "pinball_q50": "",
            "pinball_q90": "",
            "pinball_avg": "",
            "in_interval80": "",
            "winkler80": "",
            "p10": p10_value,
            "p50": p50_value,
            "p90": p90_value,
            "interval_width": "",
            "tolerance_sec": int(tolerance.total_seconds()),
        }
        variant_key, variant_label = _forecast_variant_from_meta(
            point.model_kind,
            point.labels if isinstance(point.labels, dict) else {},
            point.run.parameters if point.run_id and isinstance(point.run.parameters, dict) else {},
        )
        row["variant_key"] = variant_key
        row["variant_label"] = variant_label
        if p10_value is not None and p90_value is not None:
            row["interval_width"] = max(0.0, float(row["p90"]) - float(row["p10"]))

        if actual_value is not None:
            points_with_actual += 1
            bucket_with_actual[bucket_key] = bucket_with_actual.get(bucket_key, 0) + 1
            scale_mae, scale_mse = series_cache[cache_key].seasonal_scales(point_freq)
            err_payload = ErrorAggregate().add(
                actual=actual_value,
                predicted=pred_value,
                p10=p10_value,
                p50=p50_value,
                p90=p90_value,
                scale_mae=scale_mae,
                scale_mse=scale_mse,
            )
            row.update({
                "error": err_payload["error"],
                "abs_error": err_payload["abs_error"],
                "sq_error": err_payload["sq_error"],
                "ape": err_payload["ape"],
                "smape": err_payload["smape"],
                "scaled_abs_error": err_payload["scaled_abs_error"],
                "scaled_sq_error": err_payload["scaled_sq_error"],
                "pinball_q10": err_payload["pinball_q10"],
                "pinball_q50": err_payload["pinball_q50"],
                "pinball_q90": err_payload["pinball_q90"],
                "pinball_avg": err_payload["pinball_avg"],
                "in_interval80": err_payload["in_interval80"],
                "winkler80": err_payload["winkler80"],
            })
        point_rows.append(row)

    rows_with_actual_all = _rows_with_actual(point_rows)
    strict_intersection_keys = 0
    if strict_intersection:
        compared_point_rows, strict_intersection_keys = _strict_intersection_rows(rows_with_actual_all, selected_models)
    else:
        compared_point_rows = [
            row for row in rows_with_actual_all
            if str(row.get("model_kind") or "").strip().lower() in selected_models
        ]
        strict_intersection_keys = len({(_evaluation_row_key(row)) for row in compared_point_rows})

    bucket_compared: dict[tuple[str, str], int] = {}
    for row in compared_point_rows:
        bucket_key = (
            str(row.get("model_kind") or "").strip().lower(),
            str(row.get("horizon") or "").strip().lower(),
        )
        bucket_compared[bucket_key] = bucket_compared.get(bucket_key, 0) + 1

    availability_rows = []
    bucket_keys = sorted(set(bucket_total.keys()) | set(bucket_with_actual.keys()) | set(bucket_compared.keys()))
    for model_kind, horizon in bucket_keys:
        forecast_points = int(bucket_total.get((model_kind, horizon), 0))
        with_actual = int(bucket_with_actual.get((model_kind, horizon), 0))
        compared = int(bucket_compared.get((model_kind, horizon), 0))
        availability_rows.append({
            "model_kind": model_kind,
            "horizon": horizon,
            "forecast_points": forecast_points,
            "with_actual": with_actual,
            "compared_points": compared,
            "coverage_raw": (with_actual / forecast_points) if forecast_points > 0 else None,
            "coverage_compared": (compared / forecast_points) if forecast_points > 0 else None,
        })

    return {
        "point_rows": point_rows,
        "rows_with_actual_all": rows_with_actual_all,
        "compared_point_rows": compared_point_rows,
        "total_points": total_points,
        "points_with_actual": points_with_actual,
        "strict_intersection_keys": strict_intersection_keys,
        "raw_metric_points_total": raw_metric_points_total,
        "raw_metric_streams_total": raw_streams_total,
        "availability_rows": availability_rows,
        "forecast_run_ids": parsed_run_ids,
    }


def _fmt_num(value, digits: int = 4) -> str:
    if value is None:
        return "-"
    try:
        out = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(out):
        return "-"
    return f"{out:.{digits}f}"


def _fmt_pct(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        out = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(out):
        return "-"
    return f"{out * 100.0:.{digits}f}%"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _evaluation_row_key(row: dict) -> tuple:
    return (
        int(row.get("device_id") or 0),
        str(row.get("metric_code") or ""),
        str(row.get("horizon") or ""),
        str(row.get("target_ts") or ""),
    )


def _bucket_datetime_for_freq(dt_value: datetime | None, freq: str | None) -> datetime | None:
    if dt_value is None:
        return None
    raw = str(freq or "").strip().lower() or "1h"
    try:
        if raw.endswith("min"):
            step = max(1, int(raw[:-3]))
            minute = (dt_value.minute // step) * step
            return dt_value.replace(minute=minute, second=0, microsecond=0)
        if raw.endswith("h"):
            step = max(1, int(raw[:-1]))
            hour = (dt_value.hour // step) * step
            return dt_value.replace(hour=hour, minute=0, second=0, microsecond=0)
        if raw.endswith("d"):
            step = max(1, int(raw[:-1]))
            start = dt_value.replace(hour=0, minute=0, second=0, microsecond=0)
            if step <= 1:
                return start
            epoch_days = int(start.timestamp() // 86400)
            bucket_days = (epoch_days // step) * step
            return datetime.fromtimestamp(bucket_days * 86400, tz=start.tzinfo)
    except (TypeError, ValueError, OverflowError):
        return dt_value.replace(minute=0, second=0, microsecond=0)
    return dt_value.replace(minute=0, second=0, microsecond=0)


def _evaluation_row_bucket_key(row: dict) -> tuple:
    dt_value = _coerce_datetime(row.get("target_ts"), end_of_day=False)
    freq = str(row.get("freq") or "1h")
    bucket_dt = _bucket_datetime_for_freq(dt_value, freq)
    return (
        int(row.get("device_id") or 0),
        str(row.get("metric_code") or ""),
        str(row.get("horizon") or ""),
        _to_iso(bucket_dt),
    )


def _rows_with_actual(point_rows: list[dict]) -> list[dict]:
    out = []
    for row in point_rows:
        if _as_float(row.get("actual"), None) is None:
            continue
        if _as_float(row.get("predicted"), None) is None:
            continue
        out.append(row)
    return out


def _strict_intersection_rows(point_rows: list[dict], selected_models: list[str]) -> tuple[list[dict], int]:
    model_set = {str(item or "").strip().lower() for item in selected_models if str(item or "").strip()}
    rows = _rows_with_actual(point_rows)
    if len(model_set) <= 1:
        return rows, len({(_evaluation_row_key(row)) for row in rows})

    present_map: dict[tuple, set[str]] = {}
    for row in rows:
        model_kind = str(row.get("model_kind") or "").strip().lower()
        if model_kind not in model_set:
            continue
        key = _evaluation_row_bucket_key(row)
        present_map.setdefault(key, set()).add(model_kind)

    keep_keys = {key for key, present in present_map.items() if model_set.issubset(present)}
    filtered = [
        row for row in rows
        if str(row.get("model_kind") or "").strip().lower() in model_set and _evaluation_row_bucket_key(row) in keep_keys
    ]
    return filtered, len(keep_keys)


def _aggregate_point_rows(point_rows: list[dict]):
    agg_bucket: dict[tuple[str, str, str], ErrorAggregate] = {}
    agg_model_h: dict[tuple[str, str], ErrorAggregate] = {}
    agg_model: dict[tuple[str], ErrorAggregate] = {}
    agg_variant_h: dict[tuple[str, str, str, str], ErrorAggregate] = {}

    for row in point_rows:
        model_kind = str(row.get("model_kind") or "").strip().lower()
        horizon = str(row.get("horizon") or "").strip().lower()
        metric_code = str(row.get("metric_code") or "").strip().lower()
        variant_key = str(row.get("variant_key") or "").strip()
        variant_label = str(row.get("variant_label") or "").strip()
        actual = _as_float(row.get("actual"), None)
        predicted = _as_float(row.get("predicted"), None)
        if actual is None or predicted is None:
            continue

        abs_error = _as_float(row.get("abs_error"), abs(predicted - actual))
        sq_error = _as_float(row.get("sq_error"), (predicted - actual) ** 2)
        ape = _as_float(row.get("ape"), None)
        smape = _as_float(row.get("smape"), None)
        scaled_abs_error = _as_float(row.get("scaled_abs_error"), None)
        scaled_sq_error = _as_float(row.get("scaled_sq_error"), None)
        pinball_q10 = _as_float(row.get("pinball_q10"), None)
        pinball_q50 = _as_float(row.get("pinball_q50"), None)
        pinball_q90 = _as_float(row.get("pinball_q90"), None)
        in_interval80 = _as_float(row.get("in_interval80"), None)
        interval_width = _as_float(row.get("interval_width"), None)
        winkler80 = _as_float(row.get("winkler80"), None)

        for agg in (
            agg_bucket.setdefault((model_kind, horizon, metric_code), ErrorAggregate()),
            agg_model_h.setdefault((model_kind, horizon), ErrorAggregate()),
            agg_model.setdefault((model_kind,), ErrorAggregate()),
            agg_variant_h.setdefault((variant_key, variant_label, model_kind, horizon), ErrorAggregate()),
        ):
            agg.n += 1
            agg.sum_error += float(predicted) - float(actual)
            if abs_error is not None:
                agg.sum_abs += max(0.0, float(abs_error))
            if sq_error is not None:
                agg.sum_sq += max(0.0, float(sq_error))
            if ape is not None:
                agg.sum_ape += float(ape)
                agg.ape_n += 1
            if smape is not None:
                agg.sum_smape += float(smape)
                agg.smape_n += 1
            if scaled_abs_error is not None:
                agg.sum_scaled_abs += float(scaled_abs_error)
                agg.scaled_abs_n += 1
            if scaled_sq_error is not None:
                agg.sum_scaled_sq += float(scaled_sq_error)
                agg.scaled_sq_n += 1
            if pinball_q10 is not None:
                agg.sum_pinball_q10 += float(pinball_q10)
                agg.pinball_q10_n += 1
            if pinball_q50 is not None:
                agg.sum_pinball_q50 += float(pinball_q50)
                agg.pinball_q50_n += 1
            if pinball_q90 is not None:
                agg.sum_pinball_q90 += float(pinball_q90)
                agg.pinball_q90_n += 1
            if in_interval80 is not None:
                agg.interval_n += 1
                agg.interval_covered_n += 1 if float(in_interval80) >= 0.5 else 0
                if interval_width is not None:
                    agg.sum_interval_width += max(0.0, float(interval_width))
                if winkler80 is not None:
                    agg.sum_winkler_80 += max(0.0, float(winkler80))

    bucket_rows = []
    for (model_kind, horizon, metric_code), agg in agg_bucket.items():
        metrics = agg.metrics()
        bucket_rows.append({
            "model_kind": model_kind,
            "horizon": horizon,
            "metric_code": metric_code,
            "samples": metrics["n"],
            "mean_error": metrics["mean_error"],
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "smape": metrics["smape"],
            "mase": metrics["mase"],
            "rmsse": metrics["rmsse"],
            "pinball_q10": metrics["pinball_q10"],
            "pinball_q50": metrics["pinball_q50"],
            "pinball_q90": metrics["pinball_q90"],
            "pinball_avg": metrics["pinball_avg"],
            "picp80": metrics["picp80"],
            "ace80": metrics["ace80"],
            "miw": metrics["miw"],
            "winkler80": metrics["winkler80"],
        })
    bucket_rows.sort(key=lambda x: (x["model_kind"], x["horizon"], x["metric_code"]))

    model_h_rows = []
    for (model_kind, horizon), agg in agg_model_h.items():
        metrics = agg.metrics()
        model_h_rows.append({
            "model_kind": model_kind,
            "horizon": horizon,
            "samples": metrics["n"],
            "mean_error": metrics["mean_error"],
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "smape": metrics["smape"],
            "mase": metrics["mase"],
            "rmsse": metrics["rmsse"],
            "pinball_q10": metrics["pinball_q10"],
            "pinball_q50": metrics["pinball_q50"],
            "pinball_q90": metrics["pinball_q90"],
            "pinball_avg": metrics["pinball_avg"],
            "picp80": metrics["picp80"],
            "ace80": metrics["ace80"],
            "miw": metrics["miw"],
            "winkler80": metrics["winkler80"],
        })
    model_h_rows.sort(key=lambda x: (x["model_kind"], x["horizon"]))

    model_rows = []
    for (model_kind,), agg in agg_model.items():
        metrics = agg.metrics()
        model_rows.append({
            "model_kind": model_kind,
            "samples": metrics["n"],
            "mean_error": metrics["mean_error"],
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "smape": metrics["smape"],
            "mase": metrics["mase"],
            "rmsse": metrics["rmsse"],
            "pinball_q10": metrics["pinball_q10"],
            "pinball_q50": metrics["pinball_q50"],
            "pinball_q90": metrics["pinball_q90"],
            "pinball_avg": metrics["pinball_avg"],
            "picp80": metrics["picp80"],
            "ace80": metrics["ace80"],
            "miw": metrics["miw"],
            "winkler80": metrics["winkler80"],
        })
    model_rows.sort(key=lambda x: x["model_kind"])

    variant_h_rows = []
    for (variant_key, variant_label, model_kind, horizon), agg in agg_variant_h.items():
        metrics = agg.metrics()
        variant_h_rows.append({
            "variant_key": variant_key,
            "variant_label": variant_label,
            "model_kind": model_kind,
            "horizon": horizon,
            "samples": metrics["n"],
            "mean_error": metrics["mean_error"],
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "smape": metrics["smape"],
            "mase": metrics["mase"],
            "rmsse": metrics["rmsse"],
            "pinball_q10": metrics["pinball_q10"],
            "pinball_q50": metrics["pinball_q50"],
            "pinball_q90": metrics["pinball_q90"],
            "pinball_avg": metrics["pinball_avg"],
            "picp80": metrics["picp80"],
            "ace80": metrics["ace80"],
            "miw": metrics["miw"],
            "winkler80": metrics["winkler80"],
        })
    variant_h_rows.sort(key=lambda x: (x["model_kind"], x["variant_label"], x["horizon"]))

    return bucket_rows, model_h_rows, model_rows, variant_h_rows


def _normal_two_sided_pvalue(z: float) -> float:
    value = abs(float(z))
    return float(math.erfc(value / math.sqrt(2.0)))


def _dm_test_rows(point_rows: list[dict], selected_models: list[str]) -> list[dict]:
    model_list = [str(item or "").strip().lower() for item in selected_models if str(item or "").strip()]
    model_list = list(dict.fromkeys(model_list))
    if len(model_list) < 2:
        return []

    by_horizon: dict[str, dict[tuple, dict[str, float]]] = {}
    for row in point_rows:
        model = str(row.get("model_kind") or "").strip().lower()
        if model not in model_list:
            continue
        key = _evaluation_row_key(row)
        horizon = str(row.get("horizon") or "").strip().lower()
        sq_error = _as_float(row.get("sq_error"), None)
        if sq_error is None:
            continue
        by_horizon.setdefault(horizon, {}).setdefault(key, {})[model] = float(sq_error)

    out = []
    for horizon, row_map in by_horizon.items():
        for model_a, model_b in itertools.combinations(model_list, 2):
            d_values = []
            for losses in row_map.values():
                if model_a in losses and model_b in losses:
                    d_values.append(float(losses[model_a]) - float(losses[model_b]))
            n = len(d_values)
            if n < 10:
                out.append({
                    "horizon": horizon,
                    "model_a": model_a,
                    "model_b": model_b,
                    "samples": n,
                    "mean_loss_diff": None,
                    "dm_stat": None,
                    "p_value": None,
                    "significant_005": False,
                    "winner": "",
                })
                continue
            mean_d = sum(d_values) / float(n)
            if n > 1:
                var_d = sum((d - mean_d) ** 2 for d in d_values) / float(n - 1)
            else:
                var_d = 0.0
            dm_stat = None
            p_value = None
            if var_d > 1e-12:
                dm_stat = mean_d / math.sqrt(var_d / float(n))
                p_value = _normal_two_sided_pvalue(dm_stat)
            winner = ""
            if mean_d < 0:
                winner = model_a
            elif mean_d > 0:
                winner = model_b
            out.append({
                "horizon": horizon,
                "model_a": model_a,
                "model_b": model_b,
                "samples": n,
                "mean_loss_diff": mean_d,
                "dm_stat": dm_stat,
                "p_value": p_value,
                "significant_005": bool(p_value is not None and p_value < 0.05),
                "winner": winner,
            })
    out.sort(key=lambda row: (str(row.get("horizon") or ""), str(row.get("model_a") or ""), str(row.get("model_b") or "")))
    return out


def _auto_block_size(n: int) -> int:
    n = max(1, int(n))
    # Heuristic for moving-block bootstrap: cube-root scale with upper bound.
    size = int(round((n ** (1.0 / 3.0)) * 2.0))
    return max(2, min(n, min(96, size)))


def _moving_block_resample(values: list[float], n: int, block_size: int, rng: random.Random) -> list[float]:
    if not values or n <= 0:
        return []
    m = len(values)
    if m == 1:
        return [float(values[0])] * n
    block = max(2, min(int(block_size), m))
    out = []
    # Circular moving-block bootstrap keeps local temporal dependence.
    while len(out) < n:
        start = rng.randrange(m)
        for step in range(block):
            out.append(float(values[(start + step) % m]))
            if len(out) >= n:
                break
    return out[:n]


def _bootstrap_ci_rows(
    point_rows: list[dict],
    *,
    bootstrap_samples: int = 300,
    bootstrap_block_size: int | None = None,
    random_seed: int = 42,
) -> list[dict]:
    rng = random.Random(int(random_seed))
    b = max(50, min(2000, int(bootstrap_samples)))

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in point_rows:
        model = str(row.get("model_kind") or "").strip().lower()
        horizon = str(row.get("horizon") or "").strip().lower()
        if not model or not horizon:
            continue
        grouped.setdefault((model, horizon), []).append(row)

    out = []
    for (model, horizon), rows in grouped.items():
        if len(rows) < 20:
            continue
        sq = [_as_float(r.get("sq_error"), None) for r in rows]
        sq = [v for v in sq if v is not None]
        scaled_abs = [_as_float(r.get("scaled_abs_error"), None) for r in rows]
        scaled_abs = [v for v in scaled_abs if v is not None]
        pinball_avg = [_as_float(r.get("pinball_avg"), None) for r in rows]
        pinball_avg = [v for v in pinball_avg if v is not None]

        def _bootstrap_stat(values: list[float], stat_kind: str):
            n = len(values)
            if n < 10:
                return None, None, None, None
            block_size = _auto_block_size(n)
            if bootstrap_block_size is not None:
                try:
                    parsed_block = int(bootstrap_block_size)
                except (TypeError, ValueError):
                    parsed_block = 0
                if parsed_block > 0:
                    block_size = max(2, min(n, parsed_block))
            stats = []
            for _ in range(b):
                sample = _moving_block_resample(values, n, block_size, rng)
                if stat_kind == "rmse":
                    stats.append(math.sqrt(sum(sample) / float(n)))
                else:
                    stats.append(sum(sample) / float(n))
            if not stats:
                return None, None, None, block_size
            stats.sort()
            low_idx = int(0.025 * (len(stats) - 1))
            high_idx = int(0.975 * (len(stats) - 1))
            if stat_kind == "rmse":
                estimate = math.sqrt(sum(values) / float(n))
            else:
                estimate = sum(values) / float(n)
            return estimate, stats[low_idx], stats[high_idx], block_size

        rmse_est, rmse_low, rmse_high, rmse_block = _bootstrap_stat(sq, "rmse")
        mase_est, mase_low, mase_high, mase_block = _bootstrap_stat(scaled_abs, "mean")
        pin_est, pin_low, pin_high, pin_block = _bootstrap_stat(pinball_avg, "mean")

        for metric_name, estimate, ci_low, ci_high, n_used, block_used in (
            ("rmse", rmse_est, rmse_low, rmse_high, len(sq), rmse_block),
            ("mase", mase_est, mase_low, mase_high, len(scaled_abs), mase_block),
            ("pinball_avg", pin_est, pin_low, pin_high, len(pinball_avg), pin_block),
        ):
            out.append({
                "model_kind": model,
                "horizon": horizon,
                "metric": metric_name,
                "samples": n_used,
                "estimate": estimate,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "bootstrap_samples": b,
                "bootstrap_block_size": block_used,
            })
    out.sort(key=lambda row: (str(row.get("metric") or ""), str(row.get("horizon") or ""), str(row.get("model_kind") or "")))
    return out


def _try_load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_wrapped_text(draw, text, x, y, max_width, font, fill=(31, 41, 55)):
    words = str(text or "").split()
    if not words:
        return y
    line = words[0]
    for word in words[1:]:
        trial = f"{line} {word}"
        box = draw.textbbox((x, y), trial, font=font)
        if (box[2] - box[0]) <= max_width:
            line = trial
        else:
            draw.text((x, y), line, font=font, fill=fill)
            y += int(font.size * 1.5) if hasattr(font, "size") else 18
            line = word
    draw.text((x, y), line, font=font, fill=fill)
    return y + (int(font.size * 1.5) if hasattr(font, "size") else 18)


def _render_summary_page(path: Path, lines: list[str]):
    width, height = 1240, 1754
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    title_font = _try_load_font(36)
    body_font = _try_load_font(22)
    small_font = _try_load_font(18)

    draw.rectangle([(0, 0), (width, 120)], fill=(15, 23, 42))
    draw.text((42, 36), "Dissertation Evaluation Report", font=title_font, fill=(241, 245, 249))

    y = 160
    for line in lines:
        if not line:
            y += 14
            continue
        text = line
        font = body_font if line.startswith("- ") else small_font
        y = _draw_wrapped_text(draw, text, 56, y, width - 112, font)
        if y > (height - 90):
            break

    image.save(path, format="PNG")


def _render_horizontal_bar_chart(
    *,
    path: Path,
    title: str,
    subtitle: str,
    rows: list[dict],
    label_fn,
    value_fn,
    value_format_fn,
    bar_color=(37, 99, 235),
    negative_positive=False,
):
    count = max(1, len(rows))
    width = 1600
    height = max(520, 220 + count * 52)
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    title_font = _try_load_font(34)
    body_font = _try_load_font(20)
    small_font = _try_load_font(16)

    draw.text((48, 28), title, font=title_font, fill=(15, 23, 42))
    draw.text((48, 74), subtitle, font=small_font, fill=(71, 85, 105))

    left = 430
    right = width - 80
    top = 130
    bar_h = 26
    step = 52
    bottom = top + step * count

    values = []
    for row in rows:
        value = value_fn(row)
        values.append(value if value is not None else 0.0)
    max_val = max((abs(v) for v in values), default=1.0)
    if max_val <= 0.0:
        max_val = 1.0

    if negative_positive:
        axis_x = int((left + right) / 2)
        draw.line([(axis_x, top - 10), (axis_x, bottom + 12)], fill=(148, 163, 184), width=2)
    else:
        axis_x = left
        draw.line([(axis_x, top - 10), (axis_x, bottom + 12)], fill=(148, 163, 184), width=2)

    for idx, row in enumerate(rows):
        y = top + idx * step
        label = label_fn(row)
        value = value_fn(row)
        if value is None:
            value = 0.0
        draw.text((52, y), str(label), font=body_font, fill=(31, 41, 55))

        if negative_positive:
            scale_half = (right - left) / 2.0
            bar_w = int((abs(float(value)) / max_val) * max(1.0, scale_half - 6))
            if float(value) >= 0.0:
                x0, x1 = axis_x + 2, axis_x + 2 + bar_w
                color = (16, 185, 129)
            else:
                x0, x1 = axis_x - 2 - bar_w, axis_x - 2
                color = (239, 68, 68)
        else:
            scale_full = (right - left)
            bar_w = int((max(0.0, float(value)) / max_val) * max(1.0, scale_full - 6))
            x0, x1 = axis_x + 2, axis_x + 2 + bar_w
            color = bar_color

        draw.rectangle([(x0, y + 3), (x1, y + bar_h)], fill=color)
        draw.text((x1 + 8, y + 3), value_format_fn(value), font=body_font, fill=(15, 23, 42))

    image.save(path, format="PNG")


def _fit_to_page(image: Image.Image, page_size=(1240, 1754), margin=36):
    page_w, page_h = page_size
    max_w = page_w - margin * 2
    max_h = page_h - margin * 2
    img = image.convert("RGB")
    scale = min(max_w / img.width, max_h / img.height, 1.0)
    new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    img = img.resize(new_size, resample=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (page_w, page_h), color=(255, 255, 255))
    x = (page_w - img.width) // 2
    y = (page_h - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


def _build_pdf_report(pdf_path: Path, page_images: list[Path]) -> bool:
    pages = []
    for image_path in page_images:
        if not image_path.exists():
            continue
        try:
            with Image.open(image_path) as image:
                pages.append(_fit_to_page(image))
        except Exception:
            continue
    if not pages:
        return False
    first, rest = pages[0], pages[1:]
    first.save(pdf_path, format="PDF", resolution=150.0, save_all=True, append_images=rest)
    return True


def run_dissertation_evaluation(
    *,
    serial: str | None = None,
    days_back: int = 120,
    target_date_from=None,
    target_date_to=None,
    actual_date_from=None,
    actual_date_to=None,
    horizons: Iterable[str] | None = None,
    model_kinds: Iterable[str] | None = None,
    forecast_run_ids: Iterable[int | str] | None = None,
    baseline_action_code: str = DEFAULT_BASELINE_ACTION_CODE,
    output_dir: str = "research/evaluation",
    tag: str | None = None,
    strict_intersection: bool = True,
    enable_stat_tests: bool = True,
    bootstrap_samples: int = 300,
    bootstrap_block_size: int | None = None,
) -> dict:
    now = timezone.now()
    selected_horizons = _parse_csv_values(horizons, DEFAULT_HORIZONS)
    selected_models = _parse_csv_values(model_kinds, DEFAULT_MODEL_KINDS)
    baseline_action_code = str(baseline_action_code or DEFAULT_BASELINE_ACTION_CODE).strip().lower()
    bootstrap_iterations = max(50, min(2000, int(bootstrap_samples)))
    bootstrap_block_size_requested = None
    if bootstrap_block_size is not None:
        try:
            parsed_block_size = int(bootstrap_block_size)
        except (TypeError, ValueError):
            parsed_block_size = 0
        if parsed_block_size > 0:
            bootstrap_block_size_requested = max(2, parsed_block_size)

    run_slug = timezone.localtime(now).strftime("%Y%m%d_%H%M%S")
    if tag:
        safe_tag = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(tag).strip())
        if safe_tag:
            run_slug = f"{run_slug}_{safe_tag}"
    base_path = Path(output_dir).resolve()
    run_path = base_path / f"run_{run_slug}"
    run_path.mkdir(parents=True, exist_ok=True)
    windows = _normalize_evaluation_windows(
        days_back=days_back,
        target_date_from=target_date_from,
        target_date_to=target_date_to,
        actual_date_from=actual_date_from,
        actual_date_to=actual_date_to,
    )
    target_from = windows["target_from"]
    target_to = windows["target_to"]
    actual_from_dt = windows["actual_from"]
    actual_to_dt = windows["actual_to"]

    collection = _collect_evaluation_point_rows(
        serial=serial,
        target_from=target_from,
        target_to=target_to,
        actual_from=actual_from_dt,
        actual_to=actual_to_dt,
        selected_horizons=selected_horizons,
        selected_models=selected_models,
        strict_intersection=bool(strict_intersection),
        forecast_run_ids=forecast_run_ids,
    )

    point_rows = collection["point_rows"]
    rows_with_actual_all = collection["rows_with_actual_all"]
    total_points = int(collection["total_points"])
    points_with_actual = int(collection["points_with_actual"])
    raw_metric_points_total = int(collection["raw_metric_points_total"])
    raw_metric_streams_total = int(collection["raw_metric_streams_total"])
    availability_rows = collection["availability_rows"]
    parsed_run_ids = collection["forecast_run_ids"]
    strict_intersection_enabled = bool(strict_intersection)
    compared_point_rows = collection["compared_point_rows"]
    strict_intersection_keys = int(collection["strict_intersection_keys"])

    (
        bucket_rows,
        model_h_rows,
        model_rows,
        variant_h_rows,
    ) = _aggregate_point_rows(compared_point_rows)

    sarima_variant_rows = [row for row in variant_h_rows if row.get("model_kind") == "sarima"]
    dm_test_rows = _dm_test_rows(compared_point_rows, selected_models) if enable_stat_tests else []
    bootstrap_ci_rows = _bootstrap_ci_rows(
        compared_point_rows,
        bootstrap_samples=bootstrap_iterations,
        bootstrap_block_size=bootstrap_block_size_requested,
        random_seed=42,
    ) if enable_stat_tests else []

    prob_model_h_rows = []
    interval_calibration_rows = []
    for row in model_h_rows:
        prob_model_h_rows.append({
            "model_kind": row.get("model_kind"),
            "horizon": row.get("horizon"),
            "samples": row.get("samples"),
            "mean_error": row.get("mean_error"),
            "smape": row.get("smape"),
            "mase": row.get("mase"),
            "rmsse": row.get("rmsse"),
            "pinball_q10": row.get("pinball_q10"),
            "pinball_q50": row.get("pinball_q50"),
            "pinball_q90": row.get("pinball_q90"),
            "pinball_avg": row.get("pinball_avg"),
        })
        interval_calibration_rows.append({
            "model_kind": row.get("model_kind"),
            "horizon": row.get("horizon"),
            "samples": row.get("samples"),
            "picp80": row.get("picp80"),
            "ace80": row.get("ace80"),
            "miw": row.get("miw"),
            "winkler80": row.get("winkler80"),
        })

    decision_qs = (
        DecisionRun.objects
        .filter(
            status="success",
            created_at__gte=target_from,
            created_at__lte=target_to,
            horizon__in=selected_horizons,
        )
        .select_related("device", "policy", "recommended_action")
        .prefetch_related(
            Prefetch("scores", queryset=DecisionRunScore.objects.select_related("action").all()),
        )
        .order_by("created_at", "id")
    )
    if serial:
        decision_qs = decision_qs.filter(device__serial_number=serial)

    decision_rows = []
    delta_values = []
    horizon_delta_map: dict[str, list[float]] = {}
    economic_records = []
    horizon_economic_map: dict[str, list[dict]] = {}
    runs_total = 0
    runs_used = 0
    baseline_missing = 0

    for run in decision_qs.iterator(chunk_size=500):
        runs_total += 1
        scores = list(run.scores.all())
        rec_score = next((row for row in scores if row.is_recommended), None)
        baseline_score = next((row for row in scores if row.action and row.action.code == baseline_action_code), None)

        if rec_score is None:
            continue
        if baseline_score is None:
            baseline_missing += 1
            continue

        runs_used += 1
        expected_with = _as_float(rec_score.expected_loss, 0.0)
        expected_without = _as_float(baseline_score.expected_loss, 0.0)
        delta_r = expected_without - expected_with
        delta_r_pct = (delta_r / expected_without) if expected_without > 1e-12 else None
        economic_record = {
            "expected_loss_with_system": expected_with,
            "expected_loss_without_system": expected_without,
            "delta_r": delta_r,
            "delta_r_pct": delta_r_pct,
        }
        delta_values.append(delta_r)
        horizon_delta_map.setdefault(run.horizon, []).append(delta_r)
        economic_records.append(economic_record)
        horizon_economic_map.setdefault(run.horizon, []).append(economic_record)

        feedback = None
        try:
            feedback = run.feedback
        except DecisionFeedback.DoesNotExist:
            feedback = None

        decision_rows.append({
            "run_id": run.id,
            "created_at": _to_iso(run.created_at),
            "device_serial": run.device.serial_number,
            "horizon": run.horizon,
            "mode": run.mode,
            "recommended_action_code": rec_score.action.code if rec_score.action else "",
            "baseline_action_code": baseline_score.action.code if baseline_score.action else "",
            "expected_loss_with_system": expected_with,
            "expected_loss_without_system": expected_without,
            "delta_r": delta_r,
            "delta_r_pct": delta_r_pct,
            "overall_risk": _as_float((run.risk_snapshot or {}).get("overall_risk"), None),
            "markov_p_s2": _as_float((run.risk_snapshot or {}).get("markov_projected_p_s2"), None),
            "feedback_state": feedback.outcome_state if feedback else "",
            "feedback_incident_cost": _as_float(feedback.incident_cost, None) if feedback else None,
        })

    decision_rows.sort(key=lambda x: (x["created_at"], x["run_id"]))
    latest_decision_row = decision_rows[-1] if decision_rows else None

    def _value_summary(values: list[float]) -> dict:
        xs = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
        if not xs:
            return {"mean": None, "median": None, "min": None, "max": None}
        n = len(xs)
        median = xs[n // 2] if (n % 2 == 1) else (xs[n // 2 - 1] + xs[n // 2]) / 2.0
        return {"mean": sum(xs) / n, "median": median, "min": xs[0], "max": xs[-1]}

    def _delta_summary(values: list[float], records: list[dict] | None = None) -> dict:
        if not values:
            return {
                "samples": 0,
                "delta_r_mean": None,
                "delta_r_median": None,
                "delta_r_min": None,
                "delta_r_max": None,
                "share_positive": None,
                "expected_loss_with_system_mean": None,
                "expected_loss_with_system_median": None,
                "expected_loss_without_system_mean": None,
                "expected_loss_without_system_median": None,
                "delta_r_pct_mean": None,
                "delta_r_pct_median": None,
            }
        xs = sorted(float(v) for v in values)
        n = len(xs)
        median = xs[n // 2] if (n % 2 == 1) else (xs[n // 2 - 1] + xs[n // 2]) / 2.0
        records = records or []
        with_stats = _value_summary([_as_float(row.get("expected_loss_with_system"), None) for row in records])
        without_stats = _value_summary([_as_float(row.get("expected_loss_without_system"), None) for row in records])
        pct_stats = _value_summary([
            float(row.get("delta_r_pct"))
            for row in records
            if row.get("delta_r_pct") is not None and math.isfinite(float(row.get("delta_r_pct")))
        ])
        return {
            "samples": n,
            "delta_r_mean": sum(xs) / n,
            "delta_r_median": median,
            "delta_r_min": xs[0],
            "delta_r_max": xs[-1],
            "share_positive": sum(1 for v in xs if v > 0.0) / n,
            "expected_loss_with_system_mean": with_stats["mean"],
            "expected_loss_with_system_median": with_stats["median"],
            "expected_loss_without_system_mean": without_stats["mean"],
            "expected_loss_without_system_median": without_stats["median"],
            "delta_r_pct_mean": pct_stats["mean"],
            "delta_r_pct_median": pct_stats["median"],
        }

    delta_summary_all = _delta_summary(delta_values, economic_records)
    delta_h_rows = []
    for horizon in sorted(horizon_delta_map.keys()):
        row = {"horizon": horizon}
        row.update(_delta_summary(horizon_delta_map[horizon], horizon_economic_map.get(horizon) or []))
        delta_h_rows.append(row)

    forecast_point_csv = run_path / "forecast_point_errors.csv"
    forecast_bucket_csv = run_path / "forecast_metrics_by_bucket.csv"
    forecast_model_h_csv = run_path / "forecast_metrics_by_model_horizon.csv"
    forecast_model_csv = run_path / "forecast_metrics_by_model.csv"
    forecast_variant_h_csv = run_path / "forecast_metrics_by_variant_horizon.csv"
    forecast_prob_h_csv = run_path / "forecast_prob_metrics_by_model_horizon.csv"
    forecast_interval_calibration_csv = run_path / "forecast_interval_calibration_by_model_horizon.csv"
    forecast_dm_tests_csv = run_path / "forecast_dm_tests.csv"
    forecast_bootstrap_ci_csv = run_path / "forecast_bootstrap_ci.csv"
    decision_run_csv = run_path / "decision_delta_r_runs.csv"
    decision_h_csv = run_path / "decision_delta_r_by_horizon.csv"
    decision_summary_csv = run_path / "decision_delta_r_summary.csv"
    report_md = run_path / "dissertation_evaluation_report.md"
    manifest_json = run_path / "manifest.json"

    _write_csv(
        forecast_point_csv,
        [
            "device_id", "device_serial", "model_kind", "variant_key", "variant_label", "horizon", "metric_code", "run_id",
            "target_ts", "predicted", "actual", "freq",
            "error", "abs_error", "sq_error", "ape", "smape",
            "scaled_abs_error", "scaled_sq_error",
            "pinball_q10", "pinball_q50", "pinball_q90", "pinball_avg",
            "in_interval80", "winkler80",
            "p10", "p50", "p90", "interval_width", "tolerance_sec",
        ],
        point_rows,
    )
    _write_csv(
        forecast_bucket_csv,
        [
            "model_kind", "horizon", "metric_code", "samples",
            "mean_error", "mae", "rmse", "mape", "smape", "mase", "rmsse",
            "pinball_q10", "pinball_q50", "pinball_q90", "pinball_avg",
            "picp80", "ace80", "miw", "winkler80",
        ],
        bucket_rows,
    )
    _write_csv(
        forecast_model_h_csv,
        [
            "model_kind", "horizon", "samples",
            "mean_error", "mae", "rmse", "mape", "smape", "mase", "rmsse",
            "pinball_q10", "pinball_q50", "pinball_q90", "pinball_avg",
            "picp80", "ace80", "miw", "winkler80",
        ],
        model_h_rows,
    )
    _write_csv(
        forecast_model_csv,
        [
            "model_kind", "samples",
            "mean_error", "mae", "rmse", "mape", "smape", "mase", "rmsse",
            "pinball_q10", "pinball_q50", "pinball_q90", "pinball_avg",
            "picp80", "ace80", "miw", "winkler80",
        ],
        model_rows,
    )
    _write_csv(
        forecast_variant_h_csv,
        [
            "variant_key", "variant_label", "model_kind", "horizon", "samples",
            "mean_error", "mae", "rmse", "mape", "smape", "mase", "rmsse",
            "pinball_q10", "pinball_q50", "pinball_q90", "pinball_avg",
            "picp80", "ace80", "miw", "winkler80",
        ],
        variant_h_rows,
    )
    _write_csv(
        forecast_prob_h_csv,
        [
            "model_kind", "horizon", "samples",
            "mean_error", "smape", "mase", "rmsse",
            "pinball_q10", "pinball_q50", "pinball_q90", "pinball_avg",
        ],
        prob_model_h_rows,
    )
    _write_csv(
        forecast_interval_calibration_csv,
        [
            "model_kind", "horizon", "samples",
            "picp80", "ace80", "miw", "winkler80",
        ],
        interval_calibration_rows,
    )
    _write_csv(
        forecast_dm_tests_csv,
        [
            "horizon", "model_a", "model_b", "samples",
            "mean_loss_diff", "dm_stat", "p_value", "significant_005", "winner",
        ],
        dm_test_rows,
    )
    _write_csv(
        forecast_bootstrap_ci_csv,
        [
            "model_kind", "horizon", "metric", "samples",
            "estimate", "ci95_low", "ci95_high", "bootstrap_samples", "bootstrap_block_size",
        ],
        bootstrap_ci_rows,
    )
    _write_csv(
        decision_run_csv,
        [
            "run_id", "created_at", "device_serial", "horizon", "mode",
            "recommended_action_code", "baseline_action_code",
            "expected_loss_with_system", "expected_loss_without_system", "delta_r",
            "delta_r_pct",
            "overall_risk", "markov_p_s2", "feedback_state", "feedback_incident_cost",
        ],
        decision_rows,
    )
    _write_csv(
        decision_h_csv,
        [
            "horizon", "samples",
            "expected_loss_with_system_mean", "expected_loss_with_system_median",
            "expected_loss_without_system_mean", "expected_loss_without_system_median",
            "delta_r_mean", "delta_r_median", "delta_r_min", "delta_r_max",
            "delta_r_pct_mean", "delta_r_pct_median", "share_positive",
        ],
        delta_h_rows,
    )
    _write_csv(
        decision_summary_csv,
        [
            "samples",
            "expected_loss_with_system_mean", "expected_loss_with_system_median",
            "expected_loss_without_system_mean", "expected_loss_without_system_median",
            "delta_r_mean", "delta_r_median", "delta_r_min", "delta_r_max",
            "delta_r_pct_mean", "delta_r_pct_median", "share_positive",
        ],
        [delta_summary_all],
    )

    top_model_h = sorted(model_h_rows, key=lambda x: (x["rmse"] if x["rmse"] is not None else 10**9))[:12]
    model_h_table = _markdown_table(
        ["Модель", "Горизонт", "N", "MAE", "RMSE", "MAPE"],
        [
            [
                str(row["model_kind"]),
                str(row["horizon"]),
                str(row["samples"]),
                _fmt_num(row["mae"], 4),
                _fmt_num(row["rmse"], 4),
                _fmt_pct(row["mape"], 2),
            ]
            for row in top_model_h
        ],
    )

    prob_h_table = _markdown_table(
        ["Модель", "Горизонт", "N", "sMAPE", "MASE", "RMSSE", "Pinball(avg)"],
        [
            [
                str(row.get("model_kind")),
                str(row.get("horizon")),
                str(row.get("samples")),
                _fmt_pct(row.get("smape"), 2),
                _fmt_num(row.get("mase"), 4),
                _fmt_num(row.get("rmsse"), 4),
                _fmt_num(row.get("pinball_avg"), 4),
            ]
            for row in prob_model_h_rows
        ],
    )

    interval_calibration_table = _markdown_table(
        ["Модель", "Горизонт", "N", "PICP80", "ACE80", "MIW", "Winkler80"],
        [
            [
                str(row.get("model_kind")),
                str(row.get("horizon")),
                str(row.get("samples")),
                _fmt_pct(row.get("picp80"), 2),
                _fmt_pct(row.get("ace80"), 2),
                _fmt_num(row.get("miw"), 4),
                _fmt_num(row.get("winkler80"), 4),
            ]
            for row in interval_calibration_rows
        ],
    )

    dm_table = _markdown_table(
        ["Горизонт", "Модель A", "Модель B", "N", "DM-stat", "p-value", "Значимо (0.05)", "Победитель"],
        [
            [
                str(row.get("horizon")),
                str(row.get("model_a")),
                str(row.get("model_b")),
                str(row.get("samples")),
                _fmt_num(row.get("dm_stat"), 4),
                _fmt_num(row.get("p_value"), 4),
                "Да" if bool(row.get("significant_005")) else "Нет",
                str(row.get("winner") or "-"),
            ]
            for row in dm_test_rows
        ],
    )

    bootstrap_table = _markdown_table(
        ["Модель", "Горизонт", "Метрика", "N", "Оценка", "CI95 low", "CI95 high", "B", "L"],
        [
            [
                str(row.get("model_kind")),
                str(row.get("horizon")),
                str(row.get("metric")),
                str(row.get("samples")),
                _fmt_num(row.get("estimate"), 4),
                _fmt_num(row.get("ci95_low"), 4),
                _fmt_num(row.get("ci95_high"), 4),
                str(row.get("bootstrap_samples") or "-"),
                str(row.get("bootstrap_block_size") or "-"),
            ]
            for row in bootstrap_ci_rows
        ],
    )

    delta_h_table = _markdown_table(
        ["Горизонт", "N", "Потери baseline", "Потери СППР", "ΔR медиана", "Снижение потерь", "Доля ΔR>0"],
        [
            [
                str(row["horizon"]),
                str(row["samples"]),
                _fmt_num(row.get("expected_loss_without_system_median"), 2),
                _fmt_num(row.get("expected_loss_with_system_median"), 2),
                _fmt_num(row["delta_r_median"], 2),
                _fmt_pct(row.get("delta_r_pct_median"), 2),
                _fmt_pct(row["share_positive"], 2),
            ]
            for row in delta_h_rows
        ],
    )

    sarima_mode_table = _markdown_table(
        ["Режим SARIMA", "Горизонт", "N", "MAE", "RMSE", "MAPE"],
        [
            [
                str(row["variant_label"]),
                str(row["horizon"]),
                str(row["samples"]),
                _fmt_num(row["mae"], 4),
                _fmt_num(row["rmse"], 4),
                _fmt_pct(row["mape"], 2),
            ]
            for row in sarima_variant_rows
        ],
    )

    points_with_actual_raw = int(points_with_actual)
    points_compared = int(len(compared_point_rows))
    coverage_raw = (points_with_actual_raw / total_points) if total_points > 0 else 0.0
    coverage_compared = (points_compared / total_points) if total_points > 0 else 0.0
    coverage = coverage_compared if strict_intersection_enabled else coverage_raw
    best_rmse = min(
        (row for row in model_h_rows if row.get("rmse") is not None),
        key=lambda row: float(row.get("rmse")),
        default=None,
    )
    best_mae = min(
        (row for row in model_h_rows if row.get("mae") is not None),
        key=lambda row: float(row.get("mae")),
        default=None,
    )
    best_delta = max(
        (row for row in delta_h_rows if row.get("delta_r_mean") is not None),
        key=lambda row: float(row.get("delta_r_mean")),
        default=None,
    )
    best_sarima_variant = min(
        (
            row for row in sarima_variant_rows
            if row.get("rmse") is not None and str(row.get("variant_key") or "") != "sarima:unknown"
        ),
        key=lambda row: float(row.get("rmse")),
        default=None,
    )
    best_pinball = min(
        (row for row in prob_model_h_rows if row.get("pinball_avg") is not None),
        key=lambda row: float(row.get("pinball_avg")),
        default=None,
    )
    best_interval_calibration = min(
        (row for row in interval_calibration_rows if row.get("ace80") is not None),
        key=lambda row: float(row.get("ace80")),
        default=None,
    )
    significant_dm_rows = [
        row for row in dm_test_rows
        if row.get("p_value") is not None and float(row.get("p_value")) < 0.05
    ]
    bootstrap_block_sizes_used = sorted({
        int(row.get("bootstrap_block_size"))
        for row in bootstrap_ci_rows
        if row.get("bootstrap_block_size") is not None
    })
    best_dm_row = min(
        (row for row in dm_test_rows if row.get("p_value") is not None),
        key=lambda row: float(row.get("p_value")),
        default=None,
    )
    insights = {
        "coverage_note": (
            f"Покрытие фактом: {coverage * 100.0:.1f}% "
            f"({points_compared}/{total_points} точек для сравнения; "
            f"сырое покрытие {coverage_raw * 100.0:.1f}% = {points_with_actual_raw}/{total_points})."
        ),
        "best_rmse": (
            {
                "model_kind": best_rmse.get("model_kind"),
                "horizon": best_rmse.get("horizon"),
                "rmse": best_rmse.get("rmse"),
                "samples": best_rmse.get("samples"),
            } if best_rmse else None
        ),
        "best_mae": (
            {
                "model_kind": best_mae.get("model_kind"),
                "horizon": best_mae.get("horizon"),
                "mae": best_mae.get("mae"),
                "samples": best_mae.get("samples"),
            } if best_mae else None
        ),
        "best_delta_horizon": (
            {
                "horizon": best_delta.get("horizon"),
                "delta_r_mean": best_delta.get("delta_r_mean"),
                "share_positive": best_delta.get("share_positive"),
                "samples": best_delta.get("samples"),
            } if best_delta else None
        ),
        "best_sarima_variant": (
            {
                "variant_key": best_sarima_variant.get("variant_key"),
                "variant_label": best_sarima_variant.get("variant_label"),
                "horizon": best_sarima_variant.get("horizon"),
                "rmse": best_sarima_variant.get("rmse"),
                "mae": best_sarima_variant.get("mae"),
                "mape": best_sarima_variant.get("mape"),
                "samples": best_sarima_variant.get("samples"),
            } if best_sarima_variant else None
        ),
        "best_pinball": (
            {
                "model_kind": best_pinball.get("model_kind"),
                "horizon": best_pinball.get("horizon"),
                "pinball_avg": best_pinball.get("pinball_avg"),
                "samples": best_pinball.get("samples"),
            } if best_pinball else None
        ),
        "best_interval_calibration": (
            {
                "model_kind": best_interval_calibration.get("model_kind"),
                "horizon": best_interval_calibration.get("horizon"),
                "picp80": best_interval_calibration.get("picp80"),
                "ace80": best_interval_calibration.get("ace80"),
                "miw": best_interval_calibration.get("miw"),
                "winkler80": best_interval_calibration.get("winkler80"),
                "samples": best_interval_calibration.get("samples"),
            } if best_interval_calibration else None
        ),
        "dm_tests": {
            "total_pairs": len(dm_test_rows),
            "significant_pairs_005": len(significant_dm_rows),
            "best_p_value_row": best_dm_row,
        },
    }

    report_lines = [
        "# Диссертационный отчет верификации модели",
        "",
        f"- Время расчета: `{_to_iso(now)}`",
        f"- Прогнозный интервал: `{_to_iso(target_from)}` → `{_to_iso(target_to)}`",
        f"- Интервал факта: `{_to_iso(actual_from_dt)}` → `{_to_iso(actual_to_dt)}`",
        f"- Фильтр устройства: `{serial or 'all'}`",
        f"- Forecast run IDs: `{', '.join(str(item) for item in parsed_run_ids) if parsed_run_ids else 'all'}`",
        f"- Горизонты: `{', '.join(selected_horizons)}`",
        f"- Модели: `{', '.join(selected_models)}`",
        f"- Базовое реактивное действие для ΔR: `{baseline_action_code}`",
        f"- Bootstrap итераций: `{bootstrap_iterations}`",
        f"- Bootstrap размер блока L: `{bootstrap_block_size_requested if bootstrap_block_size_requested is not None else 'auto'}`",
        "",
        "## 1. Технические критерии (глава 7.1)",
        "",
        f"- Всего прогнозных точек: `{total_points}`",
        f"- Точек с найденным фактом (сырое покрытие): `{points_with_actual_raw}` ({coverage_raw * 100.0:.1f}%)",
        f"- Точек в финальном сравнении моделей: `{points_compared}` ({coverage_compared * 100.0:.1f}%)",
        f"- Strict intersection: `{strict_intersection_enabled}` (ключей: `{strict_intersection_keys}`)",
        f"- Артефакт: `{forecast_model_h_csv}`",
        "",
        model_h_table or "_Недостаточно данных для RMSE/MAE._",
        "",
        "### 1.1. Вероятностные метрики и устойчивость",
        "",
        f"- Артефакт: `{forecast_prob_h_csv}`",
        "",
        prob_h_table or "_Недостаточно данных для вероятностных метрик._",
        "",
        "### 1.2. Калибровка интервалов (80%)",
        "",
        f"- Артефакт: `{forecast_interval_calibration_csv}`",
        "",
        interval_calibration_table or "_Недостаточно данных для калибровки интервалов._",
        "",
        "### 1.3. Статистическая значимость (DM-test)",
        "",
        f"- Артефакт: `{forecast_dm_tests_csv}`",
        "",
        dm_table or "_Недостаточно данных для DM-test._",
        "",
        "### 1.4. Доверительные интервалы метрик (moving block bootstrap CI95)",
        "",
        f"- Артефакт: `{forecast_bootstrap_ci_csv}`",
        "",
        bootstrap_table or "_Недостаточно данных для block bootstrap CI._",
        "",
        "### 1.5. Сравнение режимов SARIMA",
        "",
        f"- Артефакт: `{forecast_variant_h_csv}`",
        "",
        sarima_mode_table or "_Недостаточно данных для сравнения режимов SARIMA._",
        "",
        "## 2. Экономический критерий (глава 7.2)",
        "",
        f"- Запусков СППР в периоде: `{runs_total}`",
        f"- Запусков, где есть сравнение с baseline `{baseline_action_code}`: `{runs_used}`",
        f"- Запусков без baseline-строки: `{baseline_missing}`",
        f"- Средние потери baseline: `{_fmt_num(delta_summary_all.get('expected_loss_without_system_mean'), 2)}`",
        f"- Средние потери СППР: `{_fmt_num(delta_summary_all.get('expected_loss_with_system_mean'), 2)}`",
        f"- Среднее ΔR: `{_fmt_num(delta_summary_all.get('delta_r_mean'), 2)}`",
        f"- Медиана ΔR: `{_fmt_num(delta_summary_all.get('delta_r_median'), 2)}`",
        f"- Медианное снижение потерь: `{_fmt_pct(delta_summary_all.get('delta_r_pct_median'), 2)}`",
        f"- Доля положительного эффекта (ΔR > 0): `{_fmt_pct(delta_summary_all.get('share_positive'), 2)}`",
        f"- Артефакт: `{decision_h_csv}`",
        "",
        delta_h_table or "_Недостаточно данных по decision-runs для расчета ΔR._",
        "",
        "## 3. Формулы и интерпретация",
        "",
        "- RMSE = sqrt(mean((y_hat - y_actual)^2))",
        "- MAE = mean(abs(y_hat - y_actual))",
        "- sMAPE = mean(2*abs(y_hat-y)/(abs(y)+abs(y_hat)+eps))",
        "- MASE = MAE / MAE(seasonal naive), RMSSE = RMSE / RMSE(seasonal naive)",
        "- Pinball(q) для q={0.1,0.5,0.9}: качество квантильного прогноза",
        "- PICP80 = доля фактов внутри [p10, p90], ACE80 = |PICP80 - 0.80|",
        "- MIW = средняя ширина интервала, Winkler80 = штраф узкого/некалиброванного интервала",
        "- Block bootstrap CI95: ресемплинг contiguous-блоков длины L для учета временной зависимости ошибок",
        "- ΔR = R(без системы) - R(с системой), где baseline = реактивное действие",
        "",
        "## 4. Что делать дальше",
        "",
        "1. Повысить покрытие фактом (сейчас coverage зависит от совпадения target_ts и raw history).",
        "2. Добавить отдельный backtest pipeline по фиксированным срезам времени.",
        "3. Зафиксировать контрольные экспериментальные наборы для сравнения версий модели.",
        "",
    ]
    report_md.write_text("\n".join(report_lines), encoding="utf-8")

    # Auto-generated chart artifacts and PDF report.
    chart_summary_png = run_path / "evaluation_summary_page.png"
    chart_rmse_png = run_path / "chart_rmse_by_model_horizon.png"
    chart_mae_png = run_path / "chart_mae_by_model_horizon.png"
    chart_sarima_modes_png = run_path / "chart_sarima_modes_rmse_by_horizon.png"
    chart_delta_png = run_path / "chart_delta_r_by_horizon.png"
    report_pdf = run_path / "dissertation_evaluation_report.pdf"
    chart_warnings = []

    summary_lines_pdf = [
        f"- Generated at: {_to_iso(now)}",
        f"- Device filter: {serial or 'all'}",
        f"- Target range: {_to_iso(target_from)} .. {_to_iso(target_to)}",
        f"- Actual range: {_to_iso(actual_from_dt)} .. {_to_iso(actual_to_dt)}",
        f"- Forecast run IDs: {', '.join(str(item) for item in parsed_run_ids) if parsed_run_ids else 'all'}",
        f"- Horizons: {', '.join(selected_horizons)}",
        f"- Models: {', '.join(selected_models)}",
        f"- Baseline action: {baseline_action_code}",
        f"- Bootstrap samples: {bootstrap_iterations}",
        f"- Bootstrap block size L: {bootstrap_block_size_requested if bootstrap_block_size_requested is not None else 'auto'}",
        "",
        f"- Forecast points: {total_points}",
        f"- Points with actual (raw): {points_with_actual_raw} ({coverage_raw * 100.0:.1f}%)",
        f"- Points compared (strict): {points_compared} ({coverage_compared * 100.0:.1f}%)",
        f"- Strict intersection enabled: {strict_intersection_enabled}",
        f"- Decision runs used: {runs_used}/{runs_total}",
        f"- Baseline expected loss mean: {_fmt_num(delta_summary_all.get('expected_loss_without_system_mean'), 2)}",
        f"- DSS expected loss mean: {_fmt_num(delta_summary_all.get('expected_loss_with_system_mean'), 2)}",
        f"- Delta R mean: {_fmt_num(delta_summary_all.get('delta_r_mean'), 2)}",
        f"- Delta R median: {_fmt_num(delta_summary_all.get('delta_r_median'), 2)}",
        f"- Delta R median pct: {_fmt_pct(delta_summary_all.get('delta_r_pct_median'), 2)}",
        f"- Share Delta R > 0: {_fmt_pct(delta_summary_all.get('share_positive'), 2)}",
        f"- Best pinball (model/h): {best_pinball.get('model_kind') if best_pinball else '-'} / {best_pinball.get('horizon') if best_pinball else '-'}",
        f"- Best calibration ACE80: {_fmt_pct(best_interval_calibration.get('ace80'), 2) if best_interval_calibration else '-'}",
        f"- DM significant pairs (p<0.05): {len(significant_dm_rows)} / {len(dm_test_rows)}",
    ]

    try:
        _render_summary_page(chart_summary_png, summary_lines_pdf)
    except Exception as exc:
        chart_warnings.append(f"summary page render failed: {exc}")

    try:
        rows = [row for row in model_h_rows if row.get("rmse") is not None]
        rows = sorted(rows, key=lambda row: float(row.get("rmse")))[:18]
        _render_horizontal_bar_chart(
            path=chart_rmse_png,
            title="RMSE by model/horizon",
            subtitle="Lower is better",
            rows=rows,
            label_fn=lambda row: f"{row.get('model_kind', '-')}/{row.get('horizon', '-')}",
            value_fn=lambda row: _as_float(row.get("rmse"), 0.0),
            value_format_fn=lambda value: _fmt_num(value, 4),
            bar_color=(37, 99, 235),
            negative_positive=False,
        )
    except Exception as exc:
        chart_warnings.append(f"rmse chart render failed: {exc}")

    try:
        rows = [row for row in model_h_rows if row.get("mae") is not None]
        rows = sorted(rows, key=lambda row: float(row.get("mae")))[:18]
        _render_horizontal_bar_chart(
            path=chart_mae_png,
            title="MAE by model/horizon",
            subtitle="Lower is better",
            rows=rows,
            label_fn=lambda row: f"{row.get('model_kind', '-')}/{row.get('horizon', '-')}",
            value_fn=lambda row: _as_float(row.get("mae"), 0.0),
            value_format_fn=lambda value: _fmt_num(value, 4),
            bar_color=(124, 58, 237),
            negative_positive=False,
        )
    except Exception as exc:
        chart_warnings.append(f"mae chart render failed: {exc}")

    try:
        rows = [row for row in sarima_variant_rows if row.get("rmse") is not None]
        rows = sorted(rows, key=lambda row: (str(row.get("horizon", "")), float(row.get("rmse"))))
        _render_horizontal_bar_chart(
            path=chart_sarima_modes_png,
            title="SARIMA modes by horizon",
            subtitle="RMSE comparison for seasonal handling modes",
            rows=rows,
            label_fn=lambda row: f"{row.get('horizon', '-')} • {row.get('variant_label', '-')}",
            value_fn=lambda row: _as_float(row.get("rmse"), 0.0),
            value_format_fn=lambda value: _fmt_num(value, 4),
            bar_color=(14, 165, 233),
            negative_positive=False,
        )
    except Exception as exc:
        chart_warnings.append(f"sarima mode chart render failed: {exc}")

    try:
        rows = [row for row in delta_h_rows if row.get("delta_r_mean") is not None]
        _render_horizontal_bar_chart(
            path=chart_delta_png,
            title="Delta R mean by horizon",
            subtitle="Positive means decision support reduced expected loss",
            rows=rows,
            label_fn=lambda row: f"horizon={row.get('horizon', '-')}",
            value_fn=lambda row: _as_float(row.get("delta_r_mean"), 0.0),
            value_format_fn=lambda value: _fmt_num(value, 2),
            bar_color=(16, 185, 129),
            negative_positive=True,
        )
    except Exception as exc:
        chart_warnings.append(f"delta chart render failed: {exc}")

    pdf_generated = False
    try:
        pdf_generated = _build_pdf_report(
            report_pdf,
            [chart_summary_png, chart_rmse_png, chart_mae_png, chart_sarima_modes_png, chart_delta_png],
        )
        if not pdf_generated:
            chart_warnings.append("pdf report build skipped: no chart pages")
    except Exception as exc:
        chart_warnings.append(f"pdf report build failed: {exc}")

    manifest = {
        "generated_at": _to_iso(now),
        "config": {
            "serial": serial,
            "days_back": max(1, int(days_back)),
            "target_date_from": _to_iso(target_from),
            "target_date_to": _to_iso(target_to),
            "actual_date_from": _to_iso(actual_from_dt),
            "actual_date_to": _to_iso(actual_to_dt),
            "horizons": selected_horizons,
            "model_kinds": selected_models,
            "forecast_run_ids": parsed_run_ids,
            "baseline_action_code": baseline_action_code,
            "strict_intersection": strict_intersection_enabled,
            "enable_stat_tests": bool(enable_stat_tests),
            "bootstrap_samples": bootstrap_iterations,
            "bootstrap_block_size": bootstrap_block_size_requested,
        },
        "summary": {
            "forecast_points_total": total_points,
            "forecast_points_with_actual": points_compared,
            "forecast_points_with_actual_raw": points_with_actual_raw,
            "forecast_points_compared": points_compared,
            "raw_metric_points_total": raw_metric_points_total,
            "raw_metric_streams_total": raw_metric_streams_total,
            "forecast_coverage_raw": coverage_raw,
            "forecast_coverage_compared": coverage_compared,
            "forecast_coverage": coverage,
            "strict_intersection_enabled": strict_intersection_enabled,
            "strict_intersection_keys": strict_intersection_keys,
            "availability_rows": availability_rows,
            "decision_runs_total": runs_total,
            "decision_runs_used": runs_used,
            "decision_runs_without_baseline": baseline_missing,
            "delta_r": delta_summary_all,
            "dm_tests": {
                "total_pairs": len(dm_test_rows),
                "significant_pairs_005": len(significant_dm_rows),
            },
            "bootstrap_ci": {
                "rows": len(bootstrap_ci_rows),
                "bootstrap_samples": bootstrap_iterations if bool(enable_stat_tests) else 0,
                "bootstrap_block_size_requested": bootstrap_block_size_requested,
                "bootstrap_block_sizes_used": bootstrap_block_sizes_used if bool(enable_stat_tests) else [],
            },
            "latest_decision_run": latest_decision_row,
            "insights": insights,
        },
        "chart_data": {
            "forecast_metrics_by_model_horizon": model_h_rows,
            "forecast_metrics_by_variant_horizon": variant_h_rows,
            "forecast_metrics_by_sarima_variant_horizon": sarima_variant_rows,
            "forecast_prob_metrics_by_model_horizon": prob_model_h_rows,
            "forecast_interval_calibration_by_model_horizon": interval_calibration_rows,
            "stat_tests_dm": dm_test_rows,
            "bootstrap_ci": bootstrap_ci_rows,
            "decision_delta_r_by_horizon": delta_h_rows,
        },
        "artifacts": {
            "forecast_point_errors_csv": str(forecast_point_csv),
            "forecast_metrics_by_bucket_csv": str(forecast_bucket_csv),
            "forecast_metrics_by_model_horizon_csv": str(forecast_model_h_csv),
            "forecast_metrics_by_model_csv": str(forecast_model_csv),
            "forecast_metrics_by_variant_horizon_csv": str(forecast_variant_h_csv),
            "forecast_prob_metrics_by_model_horizon_csv": str(forecast_prob_h_csv),
            "forecast_interval_calibration_by_model_horizon_csv": str(forecast_interval_calibration_csv),
            "forecast_dm_tests_csv": str(forecast_dm_tests_csv),
            "forecast_bootstrap_ci_csv": str(forecast_bootstrap_ci_csv),
            "decision_delta_r_runs_csv": str(decision_run_csv),
            "decision_delta_r_by_horizon_csv": str(decision_h_csv),
            "decision_delta_r_summary_csv": str(decision_summary_csv),
            "report_md": str(report_md),
            "chart_summary_png": str(chart_summary_png),
            "chart_rmse_by_model_horizon_png": str(chart_rmse_png),
            "chart_mae_by_model_horizon_png": str(chart_mae_png),
            "chart_sarima_modes_rmse_by_horizon_png": str(chart_sarima_modes_png),
            "chart_delta_r_by_horizon_png": str(chart_delta_png),
        },
        "warnings": chart_warnings,
    }
    if pdf_generated:
        manifest["artifacts"]["report_pdf"] = str(report_pdf)
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "output_dir": str(run_path),
        "manifest": str(manifest_json),
        "summary": manifest["summary"],
        "artifacts": manifest["artifacts"],
        "warnings": manifest.get("warnings") or [],
    }


def preview_dissertation_evaluation(
    *,
    serial: str | None = None,
    days_back: int = 120,
    target_date_from=None,
    target_date_to=None,
    actual_date_from=None,
    actual_date_to=None,
    horizons: Iterable[str] | None = None,
    model_kinds: Iterable[str] | None = None,
    forecast_run_ids: Iterable[int | str] | None = None,
    strict_intersection: bool = True,
) -> dict:
    selected_horizons = _parse_csv_values(horizons, DEFAULT_HORIZONS)
    selected_models = _parse_csv_values(model_kinds, DEFAULT_MODEL_KINDS)
    windows = _normalize_evaluation_windows(
        days_back=days_back,
        target_date_from=target_date_from,
        target_date_to=target_date_to,
        actual_date_from=actual_date_from,
        actual_date_to=actual_date_to,
    )
    collection = _collect_evaluation_point_rows(
        serial=serial,
        target_from=windows["target_from"],
        target_to=windows["target_to"],
        actual_from=windows["actual_from"],
        actual_to=windows["actual_to"],
        selected_horizons=selected_horizons,
        selected_models=selected_models,
        strict_intersection=bool(strict_intersection),
        forecast_run_ids=forecast_run_ids,
    )

    total_points = int(collection["total_points"])
    with_actual_raw = int(collection["points_with_actual"])
    compared_points = int(len(collection["compared_point_rows"]))
    coverage_raw = (with_actual_raw / total_points) if total_points > 0 else 0.0
    coverage_compared = (compared_points / total_points) if total_points > 0 else 0.0

    warnings = []
    if total_points <= 0:
        warnings.append("Прогнозные точки в выбранном окне не найдены.")
    elif with_actual_raw <= 0:
        warnings.append("Фактические точки для выбранных прогнозов не найдены в интервале факта.")
    elif compared_points <= 0:
        warnings.append("Факт найден, но после режима strict intersection не осталось общих точек для сравнения.")

    readiness = "insufficient"
    if compared_points > 0:
        if coverage_compared >= 0.7:
            readiness = "good"
        elif coverage_compared >= 0.35:
            readiness = "partial"
        else:
            readiness = "weak"

    return {
        "config": {
            "serial": serial,
            "days_back": max(1, int(days_back)),
            "target_date_from": _to_iso(windows["target_from"]),
            "target_date_to": _to_iso(windows["target_to"]),
            "actual_date_from": _to_iso(windows["actual_from"]),
            "actual_date_to": _to_iso(windows["actual_to"]),
            "horizons": selected_horizons,
            "model_kinds": selected_models,
            "forecast_run_ids": collection["forecast_run_ids"],
            "strict_intersection": bool(strict_intersection),
        },
        "summary": {
            "forecast_points_total": total_points,
            "forecast_points_with_actual_raw": with_actual_raw,
            "forecast_points_compared": compared_points,
            "forecast_coverage_raw": coverage_raw,
            "forecast_coverage_compared": coverage_compared,
            "strict_intersection_keys": int(collection["strict_intersection_keys"]),
            "raw_metric_points_total": int(collection["raw_metric_points_total"]),
            "raw_metric_streams_total": int(collection["raw_metric_streams_total"]),
            "readiness": readiness,
        },
        "availability_rows": collection["availability_rows"],
        "warnings": warnings,
    }
