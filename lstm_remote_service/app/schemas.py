from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SeriesPoint(BaseModel):
    timestamp: datetime
    value: float


class ForecastRequest(BaseModel):
    request_id: str | None = None
    device_serial: str
    freq: str = "1h"
    horizons: list[str] = Field(default_factory=lambda: ["24h", "7d", "30d"])
    metrics: dict[str, list[SeriesPoint]]
    options: dict[str, Any] = Field(default_factory=dict)


class ForecastItem(BaseModel):
    metric_code: str
    horizon: str
    target_ts: datetime | None = None
    forecast_step: int | None = None
    forecast_steps_total: int | None = None
    y_hat: float
    p10: float
    p50: float
    p90: float
    alpha: float = 0.2
    labels: dict[str, Any] = Field(default_factory=dict)


class ForecastResult(BaseModel):
    model_kind: str = "lstm"
    forecasts: list[ForecastItem] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: ForecastResult | None = None
