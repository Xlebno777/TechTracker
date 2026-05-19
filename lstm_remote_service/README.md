# LSTM Remote Service

Minimal remote forecasting service for TechTracker.

This service is intended to run on a separate PC (reachable via VPN) and expose
an API for asynchronous LSTM forecast jobs.

## Features
- `POST /v1/jobs` - submit forecast job
- `GET /v1/jobs/{job_id}` - get job status/result
- `GET /health` - health check
- In-memory async job execution (thread pool)
- Direct multi-horizon LSTM forecast per metric
- Rolling seasonality + calendar-aware decoder features
- Quantile output `p10/p50/p90` for probabilistic forecast

Detailed deployment guide (RU, Manjaro/Arch + AMD ROCm): `SETUP_RU.md`

## Quick start
```bash
cd lstm_remote_service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8099
```

For Manjaro/Arch with system `python-pytorch-rocm`, use:
- `requirements.arch.txt`
- `python -m venv .venv --system-site-packages`

## Environment variables
- `LSTM_API_TOKEN` - optional API token. If set, backend must send `X-API-Key`.
- `LSTM_MAX_WORKERS` - worker threads (default: `2`)
- `LSTM_DEFAULT_EPOCHS` - train epochs per metric (default: `60`)
- `LSTM_DEFAULT_LOOKBACK` - sequence length in steps (default: `168`)
- `LSTM_DEFAULT_HIDDEN_SIZE` - hidden size (default: `96`)
- `LSTM_DEFAULT_LR` - learning rate (default: `0.001`)
- `LSTM_DEFAULT_DROPOUT` - dropout for encoder/head (default: `0.15`)
- `LSTM_DEFAULT_WEIGHT_DECAY` - AdamW weight decay (default: `1e-5`)
- `LSTM_DEFAULT_BATCH_SIZE` - batch size (default: `64`)
- `LSTM_DEFAULT_SEASONALITY_MODE` - `rolling_profile` / `global_profile` / `stl_like_local`
- `LSTM_DEFAULT_SEASONALITY_WINDOW_DAYS` - rolling seasonality window (default: `14`)
- `LSTM_DEFAULT_LOSS_KIND` - `quantile` / `huber` / `mse` (default: `quantile`)
- `LSTM_DEFAULT_OUTPUT_MODE` - `direct_multi_horizon` (default)
- `LSTM_DEFAULT_TRAIN_MODE` - `fit_on_request` / `warm_start`
- `LSTM_DEFAULT_TARGET_MODE` - `anchored_delta` / `absolute_level` (default: `anchored_delta`)
- `LSTM_DEFAULT_RECENCY_WEIGHTED_LOSS` - give higher weight to recent windows (`1` by default)
- `LSTM_DEFAULT_RECENCY_WEIGHT_MIN` - minimum weight for oldest windows (default: `0.35`)
- `LSTM_DEFAULT_RECENCY_WEIGHT_POWER` - how aggressively weight grows toward recent windows (default: `2.0`)
- `LSTM_MAX_POINTS_PER_METRIC` - max points used per metric (default: `4000`)
- `LSTM_TORCH_DEVICE` - `auto`/`cpu`/`cuda` (default: `auto`)
- `LSTM_TORCH_AMP` - mixed precision on GPU (`0/1`, default: `0`)
- `LSTM_TORCH_GPU_INDEX` - GPU index for multi-GPU hosts (default: `0`)
- `LSTM_CHECKPOINT_DIR` - checkpoint directory for warm start

Note: for AMD ROCm builds, PyTorch still uses `cuda` runtime API name.

## Example submit payload
```json
{
  "device_serial": "HOST-001",
  "freq": "1h",
  "horizons": ["24h", "7d", "30d"],
  "metrics": {
    "cpu_load_total": [
      {"timestamp": "2026-03-10T00:00:00Z", "value": 42.1},
      {"timestamp": "2026-03-10T01:00:00Z", "value": 43.0}
    ]
  },
  "options": {
    "epochs": 24,
    "lookback": 168,
    "hidden_size": 96,
    "dropout": 0.15,
    "weight_decay": 0.00001,
    "batch_size": 64,
    "alpha": 0.2,
    "device": "auto",
    "amp": false,
    "gpu_index": 0,
    "use_calendar_features": true,
    "use_seasonal_residual": true,
    "seasonality_mode": "rolling_profile",
    "seasonality_window_days": 14,
    "lags": [1, 24, 168],
    "loss_kind": "quantile",
    "output_mode": "direct_multi_horizon",
    "train_mode": "fit_on_request",
    "target_mode": "anchored_delta",
    "recency_weighted_loss": true,
    "recency_weight_min": 0.35,
    "recency_weight_power": 2.0,
    "workday_start": "08:30",
    "workday_end": "17:30",
    "lunch_start": "13:00",
    "lunch_end": "14:00",
    "workday_weekdays": [0, 1, 2, 3, 4],
    "backup_start": "21:00",
    "backup_end": "23:00",
    "backup_weekdays": [0, 1, 2, 3, 4]
  }
}
```

## Modeling details
- Encoder LSTM + direct multi-horizon decoder head, not recursive one-step rollout.
- `use_calendar_features=true`: adds calendar context (`hour/day-of-week`, work/lunch/backup flags).
- `use_seasonal_residual=true`: forecasts deseasonalized signal and adds seasonal profile back to restore level.
- `seasonality_mode=rolling_profile`: computes seasonality only on recent history to avoid pulling the forecast back to an outdated average level.
- `loss_kind=quantile`: trains `q10/q50/q90` directly via pinball loss.
- `target_mode=anchored_delta`: the network predicts future deviation relative to the latest deseasonalized state, which reduces the typical drift back to the global mean level.
- `recency_weighted_loss=true`: newer training windows have higher weight than older windows, so the model follows the most recent trend regime instead of averaging all history equally.
- This mode is intended to preserve local trend better on `7d` and `30d` horizons than the old recursive residual LSTM.

## Status response (completed)
```json
{
  "job_id": "...",
  "status": "completed",
  "result": {
    "model_kind": "lstm",
    "forecasts": [
      {
        "metric_code": "cpu_load_total",
        "horizon": "24h",
        "y_hat": 44.2,
        "p10": 40.3,
        "p50": 44.2,
        "p90": 48.0,
        "alpha": 0.2,
        "labels": {"source": "lstm_remote"}
      }
    ],
    "quality": {
      "metrics_processed": 1,
      "metrics_skipped": 0,
      "errors": []
    }
  }
}
```

## Notes
- This service keeps jobs in RAM (prototype stage).
- For production, add persistent queue/storage, auth rotation, TLS, and observability.
