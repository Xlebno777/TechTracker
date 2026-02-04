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
