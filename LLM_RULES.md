# LLM Diagnostic Rules (v1)

## Input signals
All metrics are considered. Analysis windows: last 1h, 24h, 7d.
- Raw metrics: cpu_load_total, cpu_load_kernel, mem_usage_percent, mem_swap_usage, disk_usage_percent, disk_read_bytes, disk_write_bytes, net_bytes_sent, net_bytes_recv, net_errors_in, net_errors_out, ping_latency_gateway, system_temperature, uptime_seconds
- StorCLI: storcli_drive_temperature, storcli_media_error_count, storcli_other_error_count, storcli_predictive_failure_count, storcli_smart_alert
- VM: vm_status_running, vm_cpu_usage, vm_memory_usage
- Computed: cpu_trend_24h, cpu_peak_24h, cpu_variance_24h, mem_trend_24h, mem_peak_24h, mem_variance_24h, disk_fill_rate_7d, disk_usage_peak_7d, net_traffic_trend_24h, cpu_spike_count_1h, ping_spike_count_1h, ping_jitter_1h, ping_peak_1h, temp_spike_count_24h, temp_variance_24h, cpu_kernel_ratio_1h, swap_active_ratio_24h, mem_leak_prob, net_errors_in_rate_1h, net_errors_out_rate_1h, net_errors_in_burst_count_1h, net_errors_out_burst_count_1h, disk_read_spike_count_24h, disk_write_spike_count_24h, storcli_error_delta_24h, storcli_pred_fail_delta_24h, storcli_overheat_ratio_24h, storcli_smart_alert_active, uptime_reset_count_7d, vm_availability_24h, vm_cpu_peak_24h, vm_mem_peak_24h

## Severity levels
- low / medium / high / critical

## Rules (baseline expert system)
1) CPU saturation (short-term)
- Condition: cpu_spike_count_1h >= 10 OR cpu_peak_24h >= 95
- Severity: medium/high
- Explanation: sustained or repeated CPU saturation
- Recommendation: inspect top CPU processes, stagger heavy jobs, check noisy neighbors

2) CPU load trend (degradation)
- Condition: cpu_trend_24h > 1.0 %/h OR cpu_variance_24h high (e.g. > 200)
- Severity: medium
- Explanation: CPU load increases or is highly unstable
- Recommendation: check recent changes, investigate scheduled tasks and services

3) Kernel CPU dominance
- Condition: cpu_kernel_ratio_1h > 0.6
- Severity: medium
- Explanation: high kernel time can indicate driver/IO issues
- Recommendation: check drivers, storage/IO, antivirus, kernel logs

4) Memory pressure trend
- Condition: mem_trend_24h > 0.5 %/h OR mem_peak_24h >= 95
- Severity: medium/high
- Explanation: memory usage grows or stays near capacity
- Recommendation: identify leaking process, reduce cache, restart service if needed

5) Memory leak probability
- Condition: mem_leak_prob = 1
- Severity: high
- Explanation: memory grows with uptime and swap activity
- Recommendation: review long‑running processes, apply fixes, schedule restarts

6) Swap activity
- Condition: swap_active_ratio_24h > 0.2
- Severity: medium
- Explanation: frequent swap indicates RAM shortage
- Recommendation: increase RAM, tune services, reduce memory footprint

7) Disk fill risk
- Condition: disk_fill_rate_7d > 1 %/day OR disk_usage_peak_7d > 90
- Severity: medium/high
- Explanation: disk likely to fill soon
- Recommendation: cleanup logs, move data, expand volume

8) Disk IO anomalies
- Condition: disk_read_spike_count_24h >= 5 OR disk_write_spike_count_24h >= 5
- Severity: medium
- Explanation: abnormal IO bursts
- Recommendation: check backup jobs, database spikes, malware scans

9) Network instability
- Condition: ping_spike_count_1h >= 5 OR ping_jitter_1h > 20 OR ping_peak_1h > 150
- Severity: medium
- Explanation: unstable latency
- Recommendation: check gateway, link quality, switch errors, congestion

10) Network errors
- Condition: net_errors_in_burst_count_1h > 0 OR net_errors_out_burst_count_1h > 0
- Severity: medium
- Explanation: packet errors detected
- Recommendation: inspect cabling, NIC, switch port, duplex mismatch

11) Temperature risk (system)
- Condition: temp_spike_count_24h > 0 OR temp_variance_24h high
- Severity: high
- Explanation: overheating or unstable temperature
- Recommendation: check cooling, dust, fan profiles, ambient temp

12) StorCLI media errors
- Condition: storcli_error_delta_24h > 0
- Severity: high
- Explanation: RAID media errors increased
- Recommendation: run patrol read, replace failing disk, check logs

13) StorCLI predictive failure
- Condition: storcli_pred_fail_delta_24h > 0 OR storcli_smart_alert_active = 1
- Severity: critical
- Explanation: predictive failure / SMART alert
- Recommendation: replace disk ASAP, verify backups, rebuild RAID

14) StorCLI temperature
- Condition: storcli_overheat_ratio_24h > 0.2
- Severity: high
- Explanation: RAID disk overheating
- Recommendation: check airflow, RAID cooling, disk placement

15) Frequent reboots
- Condition: uptime_reset_count_7d >= 2
- Severity: medium
- Explanation: instability or power issues
- Recommendation: check OS logs, power, updates, driver stability

16) VM availability
- Condition: vm_availability_24h < 0.95
- Severity: medium
- Explanation: VM often down or paused
- Recommendation: verify host resources, storage, VM config, scheduled actions

17) VM resource contention
- Condition: vm_cpu_peak_24h > 90 OR vm_mem_peak_24h > 90
- Severity: medium
- Explanation: VM saturation risk
- Recommendation: resize VM, reduce load, check host contention

## Output schema
- summary (string)
- severity (string)
- issues (array)
  - id, title, severity, evidence[], explanation, recommendation
- confidence (0-1)
