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
