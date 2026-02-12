import logging
import os
import re
import subprocess

from django.utils import timezone

from .models import NetworkOutage, NetworkPath, RawMetric


logger = logging.getLogger(__name__)


def _extract_packet_loss_pct(output):
    if not output:
        return None
    patterns = [
        r'(\d+(?:[.,]\d+)?)\s*%\s*loss',
        r'(\d+(?:[.,]\d+)?)\s*%\s*lost',
        r'(\d+(?:[.,]\d+)?)\s*%\s*потер',
    ]
    for pattern in patterns:
        match = re.search(pattern, output, flags=re.IGNORECASE)
        if match:
            value = match.group(1).replace(',', '.')
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _extract_latency_ms(output):
    if not output:
        return None

    patterns = [
        r'average\s*=\s*([0-9]+(?:[.,][0-9]+)?)\s*ms',
        r'avg\s*=\s*([0-9]+(?:[.,][0-9]+)?)',
        r'средн[её]е\s*=\s*([0-9]+(?:[.,][0-9]+)?)',
        r'=\s*[0-9]+(?:\.[0-9]+)?/([0-9]+(?:\.[0-9]+)?)/[0-9]+(?:\.[0-9]+)?/[0-9]+(?:\.[0-9]+)?\s*ms',
        r'time[=<]\s*([0-9]+(?:[.,][0-9]+)?)\s*ms',
    ]
    for pattern in patterns:
        match = re.search(pattern, output, flags=re.IGNORECASE)
        if match:
            value = match.group(1).replace(',', '.')
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _run_ping(host, packet_count=1, timeout_sec=3):
    if not host:
        return {
            'reachable': False,
            'latency_ms': None,
            'packet_loss_pct': 100.0,
            'error': 'missing_host',
        }

    if os.name == 'nt':
        cmd = ['ping', '-n', str(max(1, packet_count)), '-w', str(max(1, timeout_sec) * 1000), host]
    else:
        cmd = ['ping', '-c', str(max(1, packet_count)), '-W', str(max(1, timeout_sec)), host]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors='ignore', timeout=max(5, timeout_sec * (packet_count + 1)))
        output = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        loss = _extract_packet_loss_pct(output)
        latency = _extract_latency_ms(output)

        lowered = output.lower()
        ttl_seen = 'ttl=' in lowered or 'ttl ' in lowered

        if loss is None:
            loss = 0.0 if proc.returncode == 0 else 100.0
        reachable = (loss < 100.0) or (proc.returncode == 0) or ttl_seen

        return {
            'reachable': bool(reachable),
            'latency_ms': latency,
            'packet_loss_pct': float(loss),
            'error': '' if reachable else f'ping_failed_rc_{proc.returncode}',
        }
    except subprocess.TimeoutExpired:
        return {
            'reachable': False,
            'latency_ms': None,
            'packet_loss_pct': 100.0,
            'error': 'ping_timeout',
        }
    except FileNotFoundError:
        return {
            'reachable': False,
            'latency_ms': None,
            'packet_loss_pct': 100.0,
            'error': 'ping_not_found',
        }
    except Exception as exc:
        return {
            'reachable': False,
            'latency_ms': None,
            'packet_loss_pct': 100.0,
            'error': str(exc),
        }


def _close_active_outage(path, now):
    outage = (
        NetworkOutage.objects
        .filter(path=path, is_active=True)
        .order_by('-started_at')
        .first()
    )
    if outage is None:
        return False
    outage.ended_at = now
    outage.duration_sec = int((now - outage.started_at).total_seconds())
    outage.is_active = False
    outage.recover_count = (outage.recover_count or 0) + 1
    outage.last_probe_at = now
    outage.save(update_fields=['ended_at', 'duration_sec', 'is_active', 'recover_count', 'last_probe_at'])
    return True


def _open_or_touch_outage(path, now, error_text):
    outage = (
        NetworkOutage.objects
        .filter(path=path, is_active=True)
        .order_by('-started_at')
        .first()
    )
    if outage is None:
        NetworkOutage.objects.create(
            path=path,
            started_at=now,
            fail_count=max(1, path.consecutive_failures),
            recover_count=0,
            is_active=True,
            last_probe_at=now,
            last_error=error_text or '',
        )
        return True

    outage.fail_count = (outage.fail_count or 0) + 1
    outage.last_probe_at = now
    if error_text:
        outage.last_error = error_text
    outage.save(update_fields=['fail_count', 'last_probe_at', 'last_error'])
    return False


def run_network_probe(path_id=None, path_ids=None, save_metrics=True, respect_interval=False):
    qs = NetworkPath.objects.filter(enabled=True).select_related('src_device', 'dst_device')
    if path_ids:
        qs = qs.filter(id__in=path_ids)
    elif path_id is not None:
        qs = qs.filter(id=path_id)

    now = timezone.now()
    raw_rows = []
    stats = {
        'checked': 0,
        'skipped': 0,
        'interval_skipped': 0,
        'up': 0,
        'down': 0,
        'outages_opened': 0,
        'outages_closed': 0,
        'metrics_created': 0,
    }

    for path in qs:
        dst_ip = path.dst_device.ip_address
        if not dst_ip:
            stats['skipped'] += 1
            continue

        if respect_interval and path.last_checked_at:
            elapsed_sec = (now - path.last_checked_at).total_seconds()
            if elapsed_sec < max(1, path.interval_sec):
                stats['interval_skipped'] += 1
                continue

        result = _run_ping(dst_ip, packet_count=path.packet_count, timeout_sec=path.timeout_sec)
        reachable = result['reachable']
        latency_ms = result['latency_ms']
        packet_loss_pct = result['packet_loss_pct']
        error_text = result['error']

        path.last_checked_at = now
        path.last_latency_ms = latency_ms
        path.last_packet_loss_pct = packet_loss_pct

        previous_state = path.last_state
        if reachable:
            path.consecutive_successes += 1
            path.consecutive_failures = 0

            promote_to_up = (
                previous_state == 'unknown' or
                (previous_state == 'down' and path.consecutive_successes >= path.recover_threshold)
            )
            if promote_to_up:
                path.last_state = 'up'
                if previous_state == 'down' and _close_active_outage(path, now):
                    stats['outages_closed'] += 1
        else:
            path.consecutive_failures += 1
            path.consecutive_successes = 0

            demote_to_down = (
                previous_state == 'down' or
                path.consecutive_failures >= path.fail_threshold
            )
            if demote_to_down:
                path.last_state = 'down'
                opened = _open_or_touch_outage(path, now, error_text)
                if opened:
                    stats['outages_opened'] += 1

        path.save(update_fields=[
            'last_checked_at',
            'last_latency_ms',
            'last_packet_loss_pct',
            'consecutive_failures',
            'consecutive_successes',
            'last_state',
            'updated_at',
        ])

        labels = {
            'path_id': path.id,
            'src_device_id': path.src_device_id,
            'src_serial': path.src_device.serial_number,
            'dst_device_id': path.dst_device_id,
            'dst_serial': path.dst_device.serial_number,
            'dst_ip': str(dst_ip),
        }
        raw_rows.append(RawMetric(
            device=path.src_device,
            code='net_path_reachable',
            value=1.0 if reachable else 0.0,
            unit='flag',
            timestamp=now,
            labels=labels,
        ))
        raw_rows.append(RawMetric(
            device=path.src_device,
            code='ping_packet_loss_matrix',
            value=packet_loss_pct if packet_loss_pct is not None else 100.0,
            unit='%',
            timestamp=now,
            labels=labels,
        ))
        if latency_ms is not None:
            raw_rows.append(RawMetric(
                device=path.src_device,
                code='ping_latency_matrix',
                value=float(latency_ms),
                unit='ms',
                timestamp=now,
                labels=labels,
            ))

        stats['checked'] += 1
        if path.last_state == 'up':
            stats['up'] += 1
        elif path.last_state == 'down':
            stats['down'] += 1

    if save_metrics and raw_rows:
        RawMetric.objects.bulk_create(raw_rows, batch_size=500)
        stats['metrics_created'] = len(raw_rows)

    logger.info(
        "Network probe complete: checked=%s skipped=%s interval_skipped=%s up=%s down=%s opened=%s closed=%s metrics=%s",
        stats['checked'],
        stats['skipped'],
        stats['interval_skipped'],
        stats['up'],
        stats['down'],
        stats['outages_opened'],
        stats['outages_closed'],
        stats['metrics_created'],
    )
    return stats
