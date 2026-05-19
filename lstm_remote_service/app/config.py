from __future__ import annotations

import os
from pathlib import Path


def _as_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _as_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _as_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    api_token: str = os.environ.get("LSTM_API_TOKEN", "")
    max_workers: int = _as_int("LSTM_MAX_WORKERS", 2)

    default_epochs: int = _as_int("LSTM_DEFAULT_EPOCHS", 60)
    default_lookback: int = _as_int("LSTM_DEFAULT_LOOKBACK", 168)
    default_hidden_size: int = _as_int("LSTM_DEFAULT_HIDDEN_SIZE", 96)
    default_lr: float = _as_float("LSTM_DEFAULT_LR", 0.001)
    default_dropout: float = _as_float("LSTM_DEFAULT_DROPOUT", 0.15)
    default_weight_decay: float = _as_float("LSTM_DEFAULT_WEIGHT_DECAY", 1e-5)
    default_batch_size: int = _as_int("LSTM_DEFAULT_BATCH_SIZE", 64)
    default_seasonality_mode: str = str(os.environ.get("LSTM_DEFAULT_SEASONALITY_MODE", "rolling_profile") or "rolling_profile").strip().lower()
    default_seasonality_window_days: int = _as_int("LSTM_DEFAULT_SEASONALITY_WINDOW_DAYS", 14)
    default_loss_kind: str = str(os.environ.get("LSTM_DEFAULT_LOSS_KIND", "quantile") or "quantile").strip().lower()
    default_output_mode: str = str(os.environ.get("LSTM_DEFAULT_OUTPUT_MODE", "direct_multi_horizon") or "direct_multi_horizon").strip().lower()
    default_train_mode: str = str(os.environ.get("LSTM_DEFAULT_TRAIN_MODE", "warm_start") or "warm_start").strip().lower()
    default_target_mode: str = str(os.environ.get("LSTM_DEFAULT_TARGET_MODE", "anchored_delta") or "anchored_delta").strip().lower()
    default_recency_weighted_loss: bool = _as_bool("LSTM_DEFAULT_RECENCY_WEIGHTED_LOSS", True)
    default_recency_weight_min: float = _as_float("LSTM_DEFAULT_RECENCY_WEIGHT_MIN", 0.35)
    default_recency_weight_power: float = _as_float("LSTM_DEFAULT_RECENCY_WEIGHT_POWER", 2.0)
    default_early_stopping_enabled: bool = _as_bool("LSTM_DEFAULT_EARLY_STOPPING", True)
    default_early_stopping_patience: int = _as_int("LSTM_DEFAULT_EARLY_STOPPING_PATIENCE", 10)
    default_early_stopping_min_delta: float = _as_float("LSTM_DEFAULT_EARLY_STOPPING_MIN_DELTA", 0.0005)
    default_scheduler_kind: str = str(os.environ.get("LSTM_DEFAULT_SCHEDULER_KIND", "plateau") or "plateau").strip().lower()
    default_scheduler_patience: int = _as_int("LSTM_DEFAULT_SCHEDULER_PATIENCE", 4)
    default_scheduler_factor: float = _as_float("LSTM_DEFAULT_SCHEDULER_FACTOR", 0.5)
    default_scheduler_min_lr: float = _as_float("LSTM_DEFAULT_SCHEDULER_MIN_LR", 1e-5)
    max_points_per_metric: int = _as_int("LSTM_MAX_POINTS_PER_METRIC", 4000)
    torch_device: str = str(os.environ.get("LSTM_TORCH_DEVICE", "auto") or "auto").strip().lower()
    torch_amp: bool = _as_bool("LSTM_TORCH_AMP", False)
    torch_gpu_index: int = _as_int("LSTM_TORCH_GPU_INDEX", 0)
    checkpoint_dir: str = str(
        Path(os.environ.get("LSTM_CHECKPOINT_DIR", str(Path(__file__).resolve().parents[1] / "artifacts" / "checkpoints")))
    )


settings = Settings()
