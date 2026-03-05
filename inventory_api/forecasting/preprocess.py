from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass
class PreprocessResult:
    original_count: int
    resampled_count: int
    missing_ratio: float
    freq: str
    seasonal_period: int
    resampled: "pd.Series"
    trend: "pd.Series"
    seasonal: "pd.Series"
    resid: "pd.Series"
    cleaned: "pd.Series"


def _require_deps():
    try:
        import pandas as pd  # type: ignore
        from statsmodels.tsa.seasonal import STL  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Baseline forecast dependencies are missing. Install pandas and statsmodels."
        ) from exc
    return pd, STL


def infer_daily_seasonal_period(freq: str) -> int:
    pd, _ = _require_deps()
    step = pd.to_timedelta(freq)
    if step <= timedelta(0):
        return 24
    period = int(round(timedelta(days=1) / step))
    return max(2, period)


def horizon_to_timedelta(horizon: str):
    pd, _ = _require_deps()
    raw = (horizon or "").strip().lower()
    if raw.endswith("h"):
        return pd.to_timedelta(int(raw[:-1]), unit="h")
    if raw.endswith("d"):
        return pd.to_timedelta(int(raw[:-1]), unit="d")
    raise ValueError(f"Unsupported horizon: {horizon}")


def horizon_to_steps(horizon: str, freq: str) -> int:
    pd, _ = _require_deps()
    td = horizon_to_timedelta(horizon)
    step = pd.to_timedelta(freq)
    if step <= timedelta(0):
        return 1
    steps = int(round(td / step))
    return max(1, steps)


def preprocess_points(
    points,
    *,
    freq: str = "15min",
    clip_quantile: float = 0.01,
    seasonal_period: int | None = None,
    max_points: int = 1200,
) -> PreprocessResult:
    pd, STL = _require_deps()
    if not points:
        raise ValueError("No points to preprocess")

    df = pd.DataFrame(points, columns=["timestamp", "value"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.dropna(subset=["timestamp", "value"]).sort_values("timestamp")
    if df.empty:
        raise ValueError("No valid points after dropping nulls")

    series = pd.Series(df["value"].astype(float).values, index=df["timestamp"])
    series = series[~series.index.duplicated(keep="last")]

    resampled = series.resample(freq).mean()
    missing_ratio = float(resampled.isna().mean()) if len(resampled) else 0.0

    filled = (
        resampled
        .interpolate(method="time", limit=8, limit_direction="both")
        .ffill()
        .bfill()
    )
    if max_points and len(filled) > max_points:
        filled = filled.iloc[-max_points:]

    if clip_quantile > 0:
        low = float(filled.quantile(clip_quantile))
        high = float(filled.quantile(1 - clip_quantile))
        filled = filled.clip(lower=low, upper=high)

    period = seasonal_period or infer_daily_seasonal_period(freq)
    stl = STL(filled, period=period, robust=True).fit()
    cleaned = stl.trend + stl.resid

    return PreprocessResult(
        original_count=len(series),
        resampled_count=len(filled),
        missing_ratio=missing_ratio,
        freq=freq,
        seasonal_period=period,
        resampled=filled,
        trend=stl.trend,
        seasonal=stl.seasonal,
        resid=stl.resid,
        cleaned=cleaned,
    )
