# TechTracker API Specification

## Base
- Base URL: `/api/`
- Auth: Token authentication via header `Authorization: Token <token>`
- Content-Type: `application/json`

## Common error format
```json
{"detail": "message"}
```

## Core resources (CRUD)
### Devices
- `GET /api/devices/`
- `POST /api/devices/`
- `GET /api/devices/{id}/`
- `PATCH /api/devices/{id}/`
- `DELETE /api/devices/{id}/`

### Device types
- `GET /api/devicetypes/`
- `POST /api/devicetypes/`

### Locations
- `GET /api/locations/`
- `POST /api/locations/`

### Users (read-only)
- `GET /api/users/`

### User profiles
- `GET /api/userprofiles/`
- `PATCH /api/userprofiles/{id}/`

### Specs
- `GET /api/computerspecs/`
- `GET /api/printerscannerspecs/`
- `GET /api/networkspecs/`

### Cartridges & logs
- `GET /api/cartridges/`
- `POST /api/cartridges/`
- `GET /api/cartridelogs/`

### Logs
- `GET /api/logs/`

### Print jobs
- `GET /api/printjob/`
- `POST /api/printjob/`

## Monitoring (raw + computed)
### Raw metrics (read)
- `GET /api/metrics-raw/?code=cpu_load_total&since_minutes=60&limit=5000&ordering=-timestamp`

Query params:
- `code` (optional): metric code
- `since_minutes` (optional): limit by time window
- `limit` (optional): server-side slice after filtering
- `ordering` (optional): `-timestamp` or `timestamp`

### Raw metrics ingest
- `POST /api/metrics-raw/ingest/`

Request:
```json
{
  "serial_number": "AUTO-OR-REAL",
  "retention_days": 365,
  "device_info": {
    "name": "Host-01",
    "serial_number": "SERIAL",
    "asset_number": "-",
    "device_type": "ПК",
    "status": "active",
    "owner_username": "techtracker_admin",
    "ip_address": "10.0.0.1",
    "mac_address": "00:11:22:33:44:55",
    "cpu": "Intel...",
    "ram_gb": 64
  },
  "metrics": [
    {"code": "cpu_load_total", "value": 12.3, "unit": "%", "timestamp": "2026-02-03T10:00:00Z", "labels": {}}
  ]
}
```

Response:
```json
{"created": 123}
```

### Computed metrics
- `GET /api/metrics-computed/?ordering=-timestamp`
- `POST /api/metrics-computed/recompute/` (admin only)

Request:
```json
{"serial": "OPTIONAL-SERIAL"}
```

Response:
```json
{"detail": "ok"}
```

## Hyper-V VM sync
- `POST /api/tracked-vms/sync_status/`

Request:
```json
{
  "serial_number": "HOST-SERIAL",
  "vms": [
    {"name": "vm-1", "status": "running", "cpu_usage": 12.3, "memory_usage": 34.5, "uptime_seconds": 12345}
  ]
}
```

Response:
```json
{"created": 1, "updated": 2, "skipped": 0}
```

## Network monitoring (path probe)
### Network paths CRUD
- `GET /api/network-paths/`
- `POST /api/network-paths/`
- `GET /api/network-paths/{id}/`
- `PATCH /api/network-paths/{id}/`
- `DELETE /api/network-paths/{id}/`

`NetworkPath` request body (example):
```json
{
  "src_device": 1,
  "dst_device": 2,
  "enabled": true,
  "interval_sec": 60,
  "timeout_sec": 3,
  "packet_count": 1,
  "fail_threshold": 3,
  "recover_threshold": 2,
  "notes": "Server -> Gateway"
}
```

### Probe run
- `POST /api/network-paths/probe/`

Request (optional):
```json
{"path_id": 10, "path_ids": [10,11], "save_metrics": true, "respect_interval": false}
```

Response:
```json
{
  "checked": 5,
  "skipped": 1,
  "up": 4,
  "down": 1,
  "outages_opened": 1,
  "outages_closed": 0,
  "metrics_created": 14
}
```

### Built-in auto job (backend)
Environment variables:
- `NETWORK_PROBE_AUTOSTART=1` (default)
- `NETWORK_PROBE_AUTO_INTERVAL_SEC=60` (scheduler tick)
- `NETWORK_PROBE_LOCK_KEY=4829137` (PostgreSQL advisory lock key)

Behavior:
- Scheduler starts inside Django process automatically.
- Probe respects per-path `interval_sec`.
- Advisory lock prevents duplicate probe runs across multiple backend processes.

### Outages
- `GET /api/network-outages/?is_active=true&ordering=-started_at`
- `GET /api/network-outages/{id}/`

### Bulk update paths
- `POST /api/network-paths/bulk_update/`
```json
{"ids":[1,2,3], "enabled": true, "interval_sec": 60}
```

### Template generator
- `POST /api/network-paths/generate_template/`
```json
{
  "template": "servers_to_gateways",
  "defaults": {"interval_sec":60,"timeout_sec":3,"packet_count":1,"fail_threshold":3,"recover_threshold":2},
  "update_existing": false
}
```
`template` supports: `custom`, `servers_to_gateways`, `servers_to_routers`, `routers_to_gateways`

### Matrix view
- `GET /api/network-paths/matrix/?include_disabled=0`

### Path history
- `GET /api/network-paths/{id}/history/?since_hours=168`

## Agent status (diagnostics)
### Report
- `POST /api/agent-status/report/`

Request:
```json
{
  "serial_number": "HOST-SERIAL",
  "status": "ok",
  "message": "optional text"
}
```

Response:
```json
{"detail": "ok"}
```

### Read
- `GET /api/agent-status/?status=error&ordering=-updated_at`

## AI diagnostics (local template now, LLM later)
- `POST /api/diagnostics/run/` -> runs diagnostics from latest raw+computed metrics and rules
- `GET /api/diagnostics/latest/?serial=HOST-SERIAL` -> latest report for a device
- `GET /api/diagnostics/` -> list reports (admin)

Environment (optional):
- `LLM_PROVIDER=groq` to enable Groq calls
- `GROQ_API_KEY` (required when provider is groq)
- `GROQ_MODEL` (default: `llama-3.1-8b-instant`)
- `GROQ_BASE_URL` (default: `https://api.groq.com/openai/v1`)

Request body (optional):
```json
{"serial": "OPTIONAL-SERIAL", "mode": "llm|rules"}
```

Response (example):
```json
{
  "device": 1,
  "summary": "High CPU + RAM trend suggests possible leak.",
  "severity": "high",
  "issues": [
    {"id": "mem_leak", "severity": "high", "evidence": ["mem_trend_24h", "swap_active_ratio_24h"]}
  ],
  "recommendations": ["Check top processes", "Restart service X"]
}
```

## Forecasts and states (read-only)
### Forecast runs
- `GET /api/forecast-runs/?device=1&model_kind=ensemble&status=success&ordering=-created_at`
- `GET /api/forecast-runs/latest/?serial=HOST-SERIAL&model_kind=ensemble`
- `POST /api/forecast-runs/seed_demo/` (admin) -> generate synthetic forecast data for UI checks
- `POST /api/forecast-runs/run_baseline/` (admin) -> run local STL + SARIMA baseline and save results
- `POST /api/forecast-runs/run_lstm_remote/` (admin) -> submit LSTM jobs to remote service via API (sync or async wait)
- `POST /api/forecast-runs/poll_lstm_remote/` (admin) -> poll pending/running remote LSTM jobs and import completed results
- `POST /api/forecast-runs/run_orchestrated/` (admin) -> run SARIMA now, queue LSTM, then build final ensemble when LSTM completes
- `POST /api/forecast-runs/poll_orchestrated/` (admin) -> poll orchestrated LSTM runs and materialize ensemble results
- `GET /api/forecast-runs/orchestrator_defaults/` (admin) -> read current backend defaults for ensemble calibration (beta + prior weights)
- `GET /api/forecast-runs/workflow_stream/?mode=full&serial=HOST-SERIAL&sarima_run_id=1&lstm_run_id=2` (admin) -> realtime NDJSON stream of step-by-step workflow progress
- `GET /api/forecast-queue-jobs/?status=retry_wait&ordering=next_retry_at` -> DB journal of remote LSTM queue
- `GET /api/forecast-queue-jobs/latest/?serial=HOST-SERIAL` -> latest queue item for host/run

### Forecast points
- `GET /api/forecast-points/?device=1&metric_code=cpu_load_total&horizon=24h&ordering=-target_ts`
- `GET /api/forecast-points/latest/?serial=HOST-SERIAL&metric_code=cpu_load_total&horizon=24h`

Optional query params:
- `since_hours` (for list, e.g. `since_hours=168`)

### State estimates (S0/S1/S2)
- `GET /api/state-estimates/?device=1&horizon=24h&state=s1&ordering=-timestamp`
- `GET /api/state-estimates/latest/?serial=HOST-SERIAL&horizon=24h`

Common horizons:
- `24h`, `7d`, `30d`

Example `seed_demo` body:
```json
{
  "serial": "OPTIONAL-SERIAL",
  "runs": 2,
  "clear": true,
  "with_raw_history": true,
  "raw_history_days": 30
}
```

Example `run_baseline` body:
```json
{
  "serial": "OPTIONAL-SERIAL",
  "lookback_days": 60,
  "freq": "1h",
  "horizons": "24h,7d,30d",
  "metric_codes": "cpu_load_total,mem_usage_percent,net_bytes_sent,net_bytes_recv,ping_latency_gateway,system_temperature,storcli_drive_temperature,storcli_predictive_failure_count",
  "save_stl_components": true
}
```

Example `run_lstm_remote` body:
```json
{
  "serial": "OPTIONAL-SERIAL",
  "lookback_days": 60,
  "freq": "1h",
  "horizons": "24h,7d,30d",
  "metric_codes": "cpu_load_total,mem_usage_percent,net_bytes_sent,net_bytes_recv,ping_latency_gateway,system_temperature,storcli_drive_temperature,storcli_predictive_failure_count",
  "no_wait": true,
  "poll_interval_sec": 2.0,
  "max_wait_sec": 120.0,
  "max_retries": 5
}
```

Example `poll_lstm_remote` body:
```json
{
  "run_id": 123,
  "serial": "OPTIONAL-SERIAL",
  "limit": 20,
  "poll_interval_sec": 10.0
}
```

Example `run_orchestrated` body:
```json
{
  "serial": "OPTIONAL-SERIAL",
  "sarima_lookback_days": 60,
  "sarima_freq": "1h",
  "save_stl_components": true,
  "lstm_lookback_days": 60,
  "lstm_freq": "1h",
  "horizons": "24h,7d,30d",
  "max_retries": 5,
  "poll_interval_sec": 10.0,
  "max_wait_sec": 120.0,
  "wait_for_lstm": false,
  "ensemble_beta": 0.5,
  "ensemble_sarima_weight": 0.5,
  "ensemble_lstm_weight": 0.5
}
```

Example `poll_orchestrated` body:
```json
{
  "run_id": 123,
  "serial": "OPTIONAL-SERIAL",
  "limit": 20,
  "poll_interval_sec": 10.0
}
```

## Risk assessment (Weibull + threshold + Markov)
- `GET /api/risk-assessment/defaults/` (admin) -> default scientific config (base thresholds, Weibull defaults, metric weights)
- `POST /api/risk-assessment/evaluate/` (admin) -> evaluate device failure risk for selected horizons

Scientific model in backend:
- Wear metrics: Weibull conditional failure probability
- Other metrics: threshold exceedance risk (p90 vs threshold)
- State dynamics: Markov transition matrix over S0/S1/S2 with S2 absorbing
- Overall risk: combined metric risk + Markov projected S2 probability

Example `evaluate` body:
```json
{
  "serial": "HOST-SERIAL",
  "horizons": ["24h", "7d", "30d"],
  "preferred_model_kind": "auto",
  "personalized_thresholds": true,
  "threshold_lookback_days": 60,
  "markov_lookback_days": 120,
  "markov_smoothing": 1.0,
  "type_blend": 0.35,
  "overall_weight_markov": 0.65,
  "history_limit": 12
}
```

Example response (short):
```json
{
  "computed_at": "2026-03-15T14:00:00Z",
  "device": {"id": 1, "name": "Srv", "serial_number": "HOST-001", "device_type": "Сервер"},
  "source_run": {"id": 123, "model_kind": "ensemble", "created_at": "2026-03-15T13:55:00Z"},
  "horizons": [
    {
      "horizon": "24h",
      "overall_risk": 0.62,
      "metric_aggregate_risk": 0.48,
      "markov_projected_p_s2": 0.39,
      "markov_step_sec": 86400,
      "current_state": {"s0": 0.52, "s1": 0.31, "s2": 0.17},
      "projected_state": {"s0": 0.40, "s1": 0.32, "s2": 0.28},
      "transition_matrix": [[0.92, 0.08, 0.0], [0.0, 0.86, 0.14], [0.0, 0.0, 1.0]],
      "overall_formula": {"mode": "weighted_linear_mix", "w_markov": 0.65, "w_metric": 0.35},
      "metrics": [
        {"metric_code": "cpu_load_total", "method": "threshold", "risk": 0.58},
        {"metric_code": "storcli_drive_wear_percent", "method": "weibull", "risk": 0.22}
      ]
    }
  ],
  "risk_history": [
    {"run_id": 120, "run_created_at": "2026-03-11T12:00:00Z", "overall_risk": 0.51, "markov_p_s2": 0.43}
  ]
}
```

## SPR recommendations (Chapter 5)
### Reference entities
- `GET /api/decision-actions/?is_active=true&ordering=name`
- `POST /api/decision-actions/` (admin)
- `GET /api/decision-criteria/?is_active=true&ordering=name`
- `POST /api/decision-criteria/` (admin)

Notes:
- `DELETE` for action/criterion is history-safe: if entity is already referenced in decision history, backend archives it (`is_active=false`) instead of hard delete.

### Policies
- `GET /api/decision-policies/?horizon=30d&is_active=true&ordering=-updated_at` (admin)
- `POST /api/decision-policies/` (admin)
- `GET /api/decision-policy-losses/?policy=12&ordering=action` (admin)
- `POST /api/decision-policy-losses/` (admin)
- `POST /api/decision-policies/bootstrap_defaults/` (admin) -> create default policy/action/criterion templates for `24h/7d/30d`
- `GET /api/decision-policies/{id}/ahp_matrix/` (admin) -> AHP matrix + weights + CI/CR
- `POST /api/decision-policies/{id}/ahp_matrix/` (admin) -> upsert pairwise matrix values
- `POST /api/decision-policies/{id}/ahp_validate/` (admin) -> recompute and validate CR

Example `ahp_matrix` upsert body:
```json
{
  "pairs": [
    {"criterion_i": 1, "criterion_j": 2, "value": 3.0},
    {"criterion_i": 1, "criterion_j": 3, "value": 5.0}
  ]
}
```

### Decision runs (recommendations)
- `GET /api/decision-runs/?device=1&horizon=30d&ordering=-created_at` (admin)
- `GET /api/decision-runs/latest/?serial=HOST-SERIAL&mode=advanced&horizon=30d` (admin)
- `POST /api/decision-runs/recommend/` (admin) -> Bayes MVP
- `POST /api/decision-runs/recommend_advanced/` (admin) -> Bayes + AHP
- `POST /api/decision-runs/{id}/feedback/` (admin) -> outcome feedback for calibration

Example `recommend` body:
```json
{
  "device": 1,
  "horizon": "30d",
  "policy_id": 12,
  "overall_weight_markov": 0.65,
  "risk_metric_min_risk": 0.08,
  "risk_metric_min_contribution": 0.03,
  "risk_metric_top_k_fallback": 3
}
```

Example `recommend_advanced` body:
```json
{
  "device": 1,
  "horizon": "30d",
  "policy_id": 12,
  "overall_weight_markov": 0.65,
  "risk_metric_min_risk": 0.08,
  "risk_metric_min_contribution": 0.03,
  "risk_metric_top_k_fallback": 3,
  "bayes_weight": 0.5,
  "ahp_weight": 0.5,
  "sensitivity_weights": {
    "reliability": 40,
    "sla": 30,
    "cost": 20,
    "ops_load": 10
  }
}
```

Action-to-metric binding (in `decision-actions.constraints_json`):
- `metric_codes`: list of metric codes relevant for this action (e.g. `["mem_usage_percent","storcli_drive_temperature"]`)
- `metric_groups`: list of groups (`cpu`, `memory`, `disk`, `network`, `temperature`, `degradation`)
- `source_models`: optional forecast source binding (`sarima`, `lstm`, `ensemble`)
- `metric_match_mode`: `any` (default) or `all`

Behavior:
- Recommendation run auto-selects active risk metrics from forecast-risk output.
- Only actions matching active metrics/groups/source stay enabled in ranking.
- Actions without metric binding (`metric_codes`/`metric_groups`) are excluded when active risk metrics are present.
- If actions are bound but none match current active risk context, API returns 400 with configuration hint.

Example `feedback` body:
```json
{
  "actual_action": 3,
  "outcome_state": "s1",
  "outage_minutes": 15,
  "incident_cost": 12000,
  "notes": "Проверка цикла обратной связи"
}
```

Backend env for remote LSTM integration:
- `LSTM_REMOTE_API_BASE_URL` (default `http://127.0.0.1:8099`)
- `LSTM_REMOTE_API_TOKEN` (optional, sent as `X-API-Key`)
- `LSTM_REMOTE_TIMEOUT_SEC` (default `20`)
- `LSTM_REMOTE_VERIFY_SSL` (`1/true/yes/on` to enable TLS cert verification)

Backend env for ensemble defaults:
- `FORECAST_ENSEMBLE_BETA` (default `0.5`)
- `FORECAST_ENSEMBLE_DEFAULT_SARIMA_WEIGHT` (default `0.5`)
- `FORECAST_ENSEMBLE_DEFAULT_LSTM_WEIGHT` (default `0.5`)

## Dissertation evaluation (Chapter 7 verification)
- `POST /api/dissertation-evaluation/run/` (admin) -> run full evaluation and write artifacts to `research/evaluation/run_*`
- `GET /api/dissertation-evaluation/history/?limit=30` (admin) -> list latest evaluation runs
- `GET /api/dissertation-evaluation/latest/` (admin) -> latest run summary
- `GET /api/dissertation-evaluation/detail/?run_id=run_...` (admin) -> manifest + markdown report text
- `GET /api/dissertation-evaluation/download/?run_id=run_...&artifact=<artifact_key>` (admin) -> download CSV/MD/PDF/PNG artifact

Example `run` body:
```json
{
  "serial": "HOST-001",
  "days_back": 120,
  "horizons": ["24h", "7d", "30d"],
  "model_kinds": ["sarima", "lstm", "ensemble"],
  "baseline_action_code": "no_action",
  "tag": "chapter7",
  "strict_intersection": true,
  "enable_stat_tests": true,
  "bootstrap_samples": 300,
  "bootstrap_block_size": 0
}
```

`bootstrap_block_size`:
- `0` or omitted -> auto-heuristic block length (moving block bootstrap)
- `>0` -> fixed block length `L`

Artifact keys:
- `forecast_point_errors_csv`
- `forecast_metrics_by_bucket_csv`
- `forecast_metrics_by_model_horizon_csv`
- `forecast_metrics_by_model_csv`
- `forecast_metrics_by_variant_horizon_csv`
- `forecast_prob_metrics_by_model_horizon_csv`
- `forecast_interval_calibration_by_model_horizon_csv`
- `forecast_dm_tests_csv`
- `forecast_bootstrap_ci_csv`
- `decision_delta_r_runs_csv`
- `decision_delta_r_by_horizon_csv`
- `decision_delta_r_summary_csv`
- `report_md`
- `chart_summary_png`
- `chart_rmse_by_model_horizon_png`
- `chart_mae_by_model_horizon_png`
- `chart_sarima_modes_rmse_by_horizon_png`
- `chart_delta_r_by_horizon_png`
- `report_pdf`

`detail` response additionally includes:
- `chart_data.forecast_metrics_by_model_horizon` (rows for RMSE/MAE/MAPE charts)
- `chart_data.forecast_prob_metrics_by_model_horizon` (Pinball/sMAPE/MASE/RMSSE)
- `chart_data.forecast_interval_calibration_by_model_horizon` (PICP80/ACE80/MIW/Winkler80)
- `chart_data.stat_tests_dm` (DM-test rows)
- `chart_data.bootstrap_ci` (bootstrap CI95 rows)
- `chart_data.decision_delta_r_by_horizon` (rows for ΔR charts)
- `insights` (auto-generated key findings for UI cards)
