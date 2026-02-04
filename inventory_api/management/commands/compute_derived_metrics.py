import math
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory_api.models import Device, RawMetric, ComputedMetric


CPU_SPIKE_THRESHOLD = 90.0
TEMP_SPIKE_C = 80.0
STORCLI_OVERHEAT_C = 55.0
MEM_TREND_THRESHOLD = 0.05  # % per hour
CORR_THRESHOLD = 0.7
MIN_SAMPLES = 5


def _to_float(value):
    try:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ('no', 'false', 'off'):
                return 0.0
            if lowered in ('yes', 'true', 'on'):
                return 1.0
        return float(value)
    except Exception:
        return None


def _linear_slope(points):
    if len(points) < 2:
        return None
    t0 = points[0][0]
    xs = [(p[0] - t0).total_seconds() / 3600.0 for p in points]
    ys = [p[1] for p in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return num / denom


def _variance(values):
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _stddev(values):
    var = _variance(values)
    if var is None:
        return None
    return math.sqrt(var)


def _percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return d0 + d1


def _correlation(xs, ys):
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x == 0 or denom_y == 0:
        return None
    return num / (denom_x * denom_y)


def _group_series(device, code, since):
    qs = (
        RawMetric.objects
        .filter(device=device, code=code, timestamp__gte=since)
        .values('timestamp', 'value', 'labels')
        .order_by('timestamp')
    )
    groups = {}
    for row in qs:
        labels = row.get('labels') or {}
        key = tuple(sorted(labels.items()))
        value = _to_float(row.get('value'))
        if value is None:
            continue
        groups.setdefault(key, {'labels': labels, 'points': []})
        groups[key]['points'].append((row['timestamp'], value))
    return groups


def _add_metric(metrics, device, code, value, unit, window, labels=None, timestamp=None):
    if value is None:
        return
    metrics.append(ComputedMetric(
        device=device,
        code=code,
        value=float(value),
        unit=unit,
        window=window,
        timestamp=timestamp or timezone.now(),
        labels=labels or {},
    ))


class Command(BaseCommand):
    help = "Вычисляет метрики уровня 2 из RawMetric."

    def add_arguments(self, parser):
        parser.add_argument('--serial', type=str, help='Только для устройства с этим серийным номером')

    def handle(self, *args, **options):
        now = timezone.now()
        serial = options.get('serial')
        devices = Device.objects.all()
        if serial:
            devices = devices.filter(serial_number=serial)

        metrics_out = []

        for device in devices:
            # --- CPU / MEM trends ---
            cpu_groups = _group_series(device, 'cpu_load_total', now - timedelta(hours=24))
            if cpu_groups:
                points = next(iter(cpu_groups.values()))['points']
                slope = _linear_slope(points)
                _add_metric(metrics_out, device, 'cpu_trend_24h', slope, '%/h', '24h')
                vals = [v for _, v in points]
                if vals:
                    _add_metric(metrics_out, device, 'cpu_peak_24h', max(vals), '%', '24h')
                    _add_metric(metrics_out, device, 'cpu_variance_24h', _variance(vals), '%^2', '24h')

            mem_groups = _group_series(device, 'mem_usage_percent', now - timedelta(hours=24))
            if mem_groups:
                points = next(iter(mem_groups.values()))['points']
                slope = _linear_slope(points)
                _add_metric(metrics_out, device, 'mem_trend_24h', slope, '%/h', '24h')
                vals = [v for _, v in points]
                if vals:
                    _add_metric(metrics_out, device, 'mem_peak_24h', max(vals), '%', '24h')
                    _add_metric(metrics_out, device, 'mem_variance_24h', _variance(vals), '%^2', '24h')

            # --- Disk fill rate (per disk) ---
            disk_groups = _group_series(device, 'disk_usage_percent', now - timedelta(days=7))
            for group in disk_groups.values():
                pts = group['points']
                if len(pts) < 2:
                    continue
                first_ts, first_val = pts[0]
                last_ts, last_val = pts[-1]
                days = (last_ts - first_ts).total_seconds() / 86400.0
                if days <= 0:
                    continue
                rate = (last_val - first_val) / days
                _add_metric(metrics_out, device, 'disk_fill_rate_7d', rate, '%/day', '7d', group['labels'])
                _add_metric(metrics_out, device, 'disk_usage_peak_7d', max(v for _, v in pts), '%', '7d', group['labels'])

            # --- Net traffic trend ---
            sent_groups = _group_series(device, 'net_bytes_sent', now - timedelta(hours=24))
            recv_groups = _group_series(device, 'net_bytes_recv', now - timedelta(hours=24))
            sent_slope = None
            recv_slope = None
            if sent_groups:
                sent_slope = _linear_slope(next(iter(sent_groups.values()))['points'])
            if recv_groups:
                recv_slope = _linear_slope(next(iter(recv_groups.values()))['points'])
            if sent_slope is not None or recv_slope is not None:
                total_slope = (sent_slope or 0.0) + (recv_slope or 0.0)
                _add_metric(metrics_out, device, 'net_traffic_trend_24h', total_slope, 'KB/s/h', '24h')

            # --- CPU spikes ---
            cpu_1h = _group_series(device, 'cpu_load_total', now - timedelta(hours=1))
            if cpu_1h:
                vals = [v for _, v in next(iter(cpu_1h.values()))['points']]
                spike_count = sum(1 for v in vals if v > CPU_SPIKE_THRESHOLD)
                _add_metric(metrics_out, device, 'cpu_spike_count_1h', spike_count, 'count', '1h')

            # --- Ping spikes & jitter ---
            ping_1h = _group_series(device, 'ping_latency_gateway', now - timedelta(hours=1))
            if ping_1h:
                vals = [v for _, v in next(iter(ping_1h.values()))['points']]
                if len(vals) >= MIN_SAMPLES:
                    p95 = _percentile(vals, 95)
                    if p95 is not None:
                        spike_count = sum(1 for v in vals if v > p95)
                        _add_metric(metrics_out, device, 'ping_spike_count_1h', spike_count, 'count', '1h')
                jitter = _stddev(vals)
                _add_metric(metrics_out, device, 'ping_jitter_1h', jitter, 'ms', '1h')
                _add_metric(metrics_out, device, 'ping_peak_1h', max(vals), 'ms', '1h')

            # --- Temperature ---
            temp_24h = _group_series(device, 'system_temperature', now - timedelta(hours=24))
            if temp_24h:
                vals = [v for _, v in next(iter(temp_24h.values()))['points']]
                spike_count = sum(1 for v in vals if v > TEMP_SPIKE_C)
                _add_metric(metrics_out, device, 'temp_spike_count_24h', spike_count, 'count', '24h')
                var = _variance(vals)
                _add_metric(metrics_out, device, 'temp_variance_24h', var, 'C^2', '24h')

            # --- CPU kernel ratio ---
            kernel_1h = _group_series(device, 'cpu_load_kernel', now - timedelta(hours=1))
            total_1h = _group_series(device, 'cpu_load_total', now - timedelta(hours=1))
            if kernel_1h and total_1h:
                kernel_vals = [v for _, v in next(iter(kernel_1h.values()))['points']]
                total_vals = [v for _, v in next(iter(total_1h.values()))['points']]
                if kernel_vals and total_vals:
                    kernel_avg = sum(kernel_vals) / len(kernel_vals)
                    total_avg = sum(total_vals) / len(total_vals)
                    if total_avg > 0:
                        ratio = kernel_avg / total_avg
                        _add_metric(metrics_out, device, 'cpu_kernel_ratio_1h', ratio, 'ratio', '1h')

            # --- Swap active ratio ---
            swap_24h = _group_series(device, 'mem_swap_usage', now - timedelta(hours=24))
            if swap_24h:
                vals = [v for _, v in next(iter(swap_24h.values()))['points']]
                if vals:
                    ratio = sum(1 for v in vals if v > 0) / len(vals)
                    _add_metric(metrics_out, device, 'swap_active_ratio_24h', ratio, 'ratio', '24h')

            # --- Net error frequency ---
            err_in = _group_series(device, 'net_errors_in', now - timedelta(hours=1))
            err_out = _group_series(device, 'net_errors_out', now - timedelta(hours=1))
            if err_in:
                vals = [v for _, v in next(iter(err_in.values()))['points']]
                if vals:
                    _add_metric(metrics_out, device, 'net_errors_in_rate_1h', sum(vals) / len(vals), 'count', '1h')
                    _add_metric(metrics_out, device, 'net_errors_in_burst_count_1h', sum(1 for v in vals if v > 0), 'count', '1h')
            if err_out:
                vals = [v for _, v in next(iter(err_out.values()))['points']]
                if vals:
                    _add_metric(metrics_out, device, 'net_errors_out_rate_1h', sum(vals) / len(vals), 'count', '1h')
                    _add_metric(metrics_out, device, 'net_errors_out_burst_count_1h', sum(1 for v in vals if v > 0), 'count', '1h')

            # --- Disk IO anomaly (p95 spikes) ---
            read_24h = _group_series(device, 'disk_read_bytes', now - timedelta(hours=24))
            for group in read_24h.values():
                vals = [v for _, v in group['points']]
                if len(vals) >= MIN_SAMPLES:
                    p95 = _percentile(vals, 95)
                    if p95 is not None:
                        spikes = sum(1 for v in vals if v > p95)
                        _add_metric(metrics_out, device, 'disk_read_spike_count_24h', spikes, 'count', '24h', group['labels'])

            write_24h = _group_series(device, 'disk_write_bytes', now - timedelta(hours=24))
            for group in write_24h.values():
                vals = [v for _, v in group['points']]
                if len(vals) >= MIN_SAMPLES:
                    p95 = _percentile(vals, 95)
                    if p95 is not None:
                        spikes = sum(1 for v in vals if v > p95)
                        _add_metric(metrics_out, device, 'disk_write_spike_count_24h', spikes, 'count', '24h', group['labels'])

            # --- Memory leak probability ---
            uptime_24h = _group_series(device, 'uptime_seconds', now - timedelta(hours=24))
            if mem_groups and uptime_24h:
                mem_points = next(iter(mem_groups.values()))['points']
                uptime_points = next(iter(uptime_24h.values()))['points']
                mem_map = {p[0].replace(second=0, microsecond=0): p[1] for p in mem_points}
                up_map = {p[0].replace(second=0, microsecond=0): p[1] for p in uptime_points}
                keys = sorted(set(mem_map.keys()) & set(up_map.keys()))
                mem_vals = [mem_map[k] for k in keys]
                up_vals = [up_map[k] for k in keys]
                slope = _linear_slope(mem_points)
                corr = _correlation(mem_vals, up_vals)
                if slope is not None and corr is not None:
                    leak = 1.0 if slope > MEM_TREND_THRESHOLD and corr > CORR_THRESHOLD else 0.0
                    _add_metric(metrics_out, device, 'mem_leak_prob', leak, 'flag', '24h')

            # --- StorCLI deltas ---
            media_groups = _group_series(device, 'storcli_media_error_count', now - timedelta(hours=24))
            other_groups = _group_series(device, 'storcli_other_error_count', now - timedelta(hours=24))
            pred_groups = _group_series(device, 'storcli_predictive_failure_count', now - timedelta(hours=24))

            def _delta_map(groups):
                result = {}
                for key, group in groups.items():
                    pts = group['points']
                    if len(pts) < 2:
                        continue
                    delta = pts[-1][1] - pts[0][1]
                    if delta < 0:
                        delta = 0
                    result[key] = (delta, group['labels'])
                return result

            media_delta = _delta_map(media_groups)
            other_delta = _delta_map(other_groups)
            pred_delta = _delta_map(pred_groups)

            for key in set(media_delta.keys()) | set(other_delta.keys()):
                delta = 0.0
                labels = {}
                if key in media_delta:
                    delta += media_delta[key][0]
                    labels = media_delta[key][1]
                if key in other_delta:
                    delta += other_delta[key][0]
                    labels = other_delta[key][1]
                _add_metric(metrics_out, device, 'storcli_error_delta_24h', delta, 'count', '24h', labels)

            for key, (delta, labels) in pred_delta.items():
                _add_metric(metrics_out, device, 'storcli_pred_fail_delta_24h', delta, 'count', '24h', labels)

            temp_groups = _group_series(device, 'storcli_drive_temperature', now - timedelta(hours=24))
            for group in temp_groups.values():
                vals = [v for _, v in group['points']]
                if vals:
                    ratio = sum(1 for v in vals if v > STORCLI_OVERHEAT_C) / len(vals)
                    _add_metric(metrics_out, device, 'storcli_overheat_ratio_24h', ratio, 'ratio', '24h', group['labels'])

            alert_groups = _group_series(device, 'storcli_smart_alert', now - timedelta(hours=24))
            for group in alert_groups.values():
                vals = [v for _, v in group['points']]
                if vals:
                    active = max(vals)
                    _add_metric(metrics_out, device, 'storcli_smart_alert_active', active, 'flag', '24h', group['labels'])

            # --- Uptime reset count ---
            uptime_7d = _group_series(device, 'uptime_seconds', now - timedelta(days=7))
            if uptime_7d:
                pts = next(iter(uptime_7d.values()))['points']
                resets = 0
                for idx in range(1, len(pts)):
                    if pts[idx][1] < (pts[idx - 1][1] - 300):
                        resets += 1
                _add_metric(metrics_out, device, 'uptime_reset_count_7d', resets, 'count', '7d')

            # --- VM derived metrics (from RawMetric) ---
            vm_avail = _group_series(device, 'vm_status_running', now - timedelta(hours=24))
            for group in vm_avail.values():
                vals = [v for _, v in group['points']]
                if vals:
                    ratio = sum(1 for v in vals if v >= 0.5) / len(vals)
                    _add_metric(metrics_out, device, 'vm_availability_24h', ratio, 'ratio', '24h', group['labels'])

            vm_cpu = _group_series(device, 'vm_cpu_usage', now - timedelta(hours=24))
            for group in vm_cpu.values():
                vals = [v for _, v in group['points']]
                if vals:
                    _add_metric(metrics_out, device, 'vm_cpu_peak_24h', max(vals), '%', '24h', group['labels'])

            vm_mem = _group_series(device, 'vm_memory_usage', now - timedelta(hours=24))
            for group in vm_mem.values():
                vals = [v for _, v in group['points']]
                if vals:
                    _add_metric(metrics_out, device, 'vm_mem_peak_24h', max(vals), '%', '24h', group['labels'])

        if metrics_out:
            ComputedMetric.objects.bulk_create(metrics_out, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(f"Computed {len(metrics_out)} derived metrics."))
