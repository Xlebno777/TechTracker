# TechTracker Database Schema (summary)

## DeviceType
- id (PK)
- name (unique)

## Location
- id (PK)
- name (unique)

## Device
- id (PK)
- name
- serial_number (unique)
- asset_number (unique, nullable)
- device_type_id (FK -> DeviceType)
- status (active/in_repair/retired/in_stock/reserved)
- location_id (FK -> Location, nullable)
- ip_address (nullable)
- mac_address (nullable)
- owner_id (FK -> auth.User, nullable)
- assigned_to_id (FK -> auth.User, nullable)
- notes
- qr_code_id (unique)
- created_at, updated_at

## UserProfile
- id (PK)
- user_id (FK -> auth.User)
- favorite_devices (M2M -> Device)

## ComputerSpecs
- id (PK)
- device_id (FK -> Device, unique)
- cpu
- ram_gb
- storage_type (SSD/HDD/SSHD)
- storage_capacity_gb
- os

## PrinterScannerSpecs
- id (PK)
- device_id (FK -> Device, unique)
- printer_type (laser/inkjet/matrix)
- color_printing (bool)
- max_resolution
- duplex_printing (bool)
- paper_trays
- current_cartridge_id (FK -> Cartridge, nullable)

## NetworkDeviceSpecs
- id (PK)
- device_id (FK -> Device, unique)
- ports_count
- port_speed
- wireless_standard
- wireless_speed
- management_ip

## Cartridge
- id (PK)
- name
- initial_pages
- remaining_pages

## CartridgeLog
- id (PK)
- cartridge_id (FK -> Cartridge)
- printer_id (FK -> PrinterScannerSpecs)
- installed_at
- removed_at
- pages_printed_at_removal

## Log
- id (PK)
- log_type (error/info)
- message
- timestamp
- device_id (FK -> Device, nullable)

## Metric (legacy)
- id (PK)
- device_id (FK -> Device)
- metric_type
- value
- timestamp

## PrintJob
- id (PK)
- device_id (FK -> Device)
- user_name
- document_name
- pages
- printer_name
- timestamp

## MonitoringSetting
- id (PK)
- device_id (FK -> Device, unique)
- retention_days
- updated_at

## RawMetric
- id (PK)
- device_id (FK -> Device)
- code
- value
- unit
- timestamp
- labels (JSON)
- created_at

## TrackedVM
- id (PK)
- name (unique)
- host_device_id (FK -> Device, nullable)
- status (running/off/paused/saved/unknown)
- cpu_usage
- memory_usage
- uptime_seconds
- last_seen
- is_enabled

## ComputedMetric
- id (PK)
- device_id (FK -> Device)
- code
- value
- unit
- window (e.g., 1h/24h/7d)
- timestamp
- labels (JSON)
- created_at

## AgentStatus
- id (PK)
- device_id (FK -> Device)
- status (ok/error)
- message
- updated_at

## DiagnosticReport
- id (PK)
- device_id (FK -> Device)
- summary
- severity (low/medium/high/critical)
- issues (JSON)
- recommendations (JSON)
- payload (JSON)
- created_at

## ForecastRun
- id (PK)
- device_id (FK -> Device)
- model_kind (sarima/lstm/ensemble)
- horizon_set (e.g., `24h,7d,30d`)
- status (pending/running/success/failed)
- started_at
- finished_at
- parameters (JSON)
- quality (JSON)
- notes
- created_at, updated_at

## ForecastPoint
- id (PK)
- run_id (FK -> ForecastRun, nullable)
- device_id (FK -> Device)
- metric_code
- horizon (`24h`/`7d`/`30d`)
- target_ts
- model_kind (sarima/lstm/ensemble)
- y_hat
- p10, p50, p90 (nullable)
- alpha (nullable)
- labels (JSON)
- created_at

## StateEstimate
- id (PK)
- run_id (FK -> ForecastRun, nullable)
- device_id (FK -> Device)
- horizon (`24h`/`7d`/`30d`)
- state (`s0`/`s1`/`s2`/`unknown`)
- p_s0, p_s1, p_s2 (nullable)
- confidence (nullable)
- evidence (JSON)
- timestamp
- created_at

## NetworkPath
- id (PK)
- src_device_id (FK -> Device)
- dst_device_id (FK -> Device)
- enabled
- interval_sec
- timeout_sec
- packet_count
- fail_threshold
- recover_threshold
- last_state (unknown/up/down)
- consecutive_failures
- consecutive_successes
- last_checked_at
- last_latency_ms
- last_packet_loss_pct
- notes
- created_at, updated_at

## NetworkOutage
- id (PK)
- path_id (FK -> NetworkPath)
- started_at
- ended_at
- duration_sec
- fail_count
- recover_count
- is_active
- last_probe_at
- last_error
- created_at

## Indexes (key)
- Device: serial_number, status, location
- RawMetric: (device, code, -timestamp), timestamp
- ComputedMetric: (device, code, -timestamp), timestamp
- AgentStatus: (device, status, -updated_at), status
