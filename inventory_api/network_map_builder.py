import logging
import time
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from .models import (
    AgentStatus,
    NetworkMapEdge,
    NetworkMapNode,
    NetworkMapSnapshot,
    NetworkOutage,
    NetworkPath,
    RawMetric,
)


logger = logging.getLogger(__name__)


def _to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_hours(value, default=24):
    hours = _to_int(value, default)
    if hours is None:
        return default
    return min(max(hours, 1), 24 * 30)


def _safe_keep_last(value, default=720):
    limit = _to_int(value, default)
    if limit is None:
        return default
    return min(max(limit, 1), 5000)


def _collect_reachability_stats(paths, since):
    if not paths:
        return {}

    path_ids = {path.id for path in paths}
    src_ids = {path.src_device_id for path in paths}

    rows = (
        RawMetric.objects
        .filter(device_id__in=src_ids, code='net_path_reachable', timestamp__gte=since)
        .values('labels', 'value')
    )

    stats = defaultdict(lambda: {'samples': 0, 'up': 0})
    for row in rows:
        labels = row.get('labels') or {}
        path_id = _to_int(labels.get('path_id'))
        if path_id not in path_ids:
            continue
        value = float(row.get('value') or 0.0)
        stats[path_id]['samples'] += 1
        if value >= 0.5:
            stats[path_id]['up'] += 1

    return stats


def _collect_outage_stats(path_ids, since_24h):
    if not path_ids:
        return {}, set()

    outage_rows = (
        NetworkOutage.objects
        .filter(path_id__in=path_ids, started_at__gte=since_24h)
        .values('path_id')
        .annotate(cnt=Count('id'))
    )
    outage_count_24h = {row['path_id']: int(row['cnt']) for row in outage_rows}

    active_outage_path_ids = set(
        NetworkOutage.objects
        .filter(path_id__in=path_ids, is_active=True)
        .values_list('path_id', flat=True)
    )

    return outage_count_24h, active_outage_path_ids


def _calc_confidence_pct(samples, up, state):
    if samples and samples > 0:
        return round((float(up) / float(samples)) * 100.0, 2)
    if state == 'up':
        return 100.0
    if state == 'down':
        return 0.0
    return None


def build_network_map_snapshot(window_hours=24, keep_last=720):
    """
    Build a network map snapshot based on configured network paths and probe history.
    Returns dict with status and snapshot metadata.
    """
    started = time.perf_counter()
    now = timezone.now()

    window_hours = _safe_hours(window_hours, default=24)
    keep_last = _safe_keep_last(keep_last, default=720)

    try:
        since_window = now - timedelta(hours=window_hours)
        since_24h = now - timedelta(hours=24)

        paths = list(
            NetworkPath.objects
            .select_related('src_device__device_type', 'dst_device__device_type')
            .all()
        )
        path_ids = [path.id for path in paths]

        reachability = _collect_reachability_stats(paths, since_window)
        outage_count_24h, active_outage_path_ids = _collect_outage_stats(path_ids, since_24h)

        device_map = {}
        for path in paths:
            device_map[path.src_device_id] = path.src_device
            device_map[path.dst_device_id] = path.dst_device

        device_ids = list(device_map.keys())
        last_seen_rows = (
            AgentStatus.objects
            .filter(device_id__in=device_ids)
            .values('device_id')
            .annotate(last_seen=Max('updated_at'))
        ) if device_ids else []
        last_seen_map = {row['device_id']: row['last_seen'] for row in last_seen_rows}

        with transaction.atomic():
            NetworkMapSnapshot.objects.filter(is_current=True).update(is_current=False)
            snapshot = NetworkMapSnapshot.objects.create(
                generated_at=now,
                source_window_hours=window_hours,
                status='ok',
                is_current=True,
            )

            node_rows = []
            for device_id in sorted(device_map.keys(), key=lambda d_id: (device_map[d_id].name or '').lower()):
                device = device_map[device_id]
                node_rows.append(NetworkMapNode(
                    snapshot=snapshot,
                    device=device,
                    device_name=device.name or f"Device {device.id}",
                    serial_number=device.serial_number or '',
                    ip_address=device.ip_address,
                    device_type_name=device.device_type.name if device.device_type else '',
                    status=device.status or '',
                    last_seen=last_seen_map.get(device.id),
                ))
            if node_rows:
                NetworkMapNode.objects.bulk_create(node_rows, batch_size=500)

            edge_rows = []
            for path in paths:
                stats = reachability.get(path.id, {'samples': 0, 'up': 0})
                confidence_pct = _calc_confidence_pct(
                    samples=stats.get('samples', 0),
                    up=stats.get('up', 0),
                    state=path.last_state,
                )
                edge_rows.append(NetworkMapEdge(
                    snapshot=snapshot,
                    path=path,
                    src_device=path.src_device,
                    dst_device=path.dst_device,
                    src_name=path.src_device.name or f"Device {path.src_device_id}",
                    dst_name=path.dst_device.name or f"Device {path.dst_device_id}",
                    dst_ip=path.dst_device.ip_address,
                    enabled=path.enabled,
                    state=path.last_state or 'unknown',
                    latency_ms=path.last_latency_ms,
                    packet_loss_pct=path.last_packet_loss_pct,
                    confidence_pct=confidence_pct,
                    outage_count_24h=outage_count_24h.get(path.id, 0),
                    has_active_outage=path.id in active_outage_path_ids,
                    last_checked_at=path.last_checked_at,
                ))
            if edge_rows:
                NetworkMapEdge.objects.bulk_create(edge_rows, batch_size=500)

            duration_ms = int((time.perf_counter() - started) * 1000)
            snapshot.node_count = len(node_rows)
            snapshot.edge_count = len(edge_rows)
            snapshot.build_duration_ms = duration_ms
            snapshot.save(update_fields=['node_count', 'edge_count', 'build_duration_ms'])

            old_ids = list(
                NetworkMapSnapshot.objects
                .order_by('-generated_at', '-id')
                .values_list('id', flat=True)[keep_last:]
            )
            if old_ids:
                NetworkMapSnapshot.objects.filter(id__in=old_ids).delete()

        logger.info(
            "Network map snapshot built: id=%s nodes=%s edges=%s duration_ms=%s",
            snapshot.id,
            snapshot.node_count,
            snapshot.edge_count,
            snapshot.build_duration_ms,
        )
        return {
            'status': 'ok',
            'snapshot_id': snapshot.id,
            'generated_at': snapshot.generated_at,
            'node_count': snapshot.node_count,
            'edge_count': snapshot.edge_count,
            'build_duration_ms': snapshot.build_duration_ms,
            'window_hours': window_hours,
            'keep_last': keep_last,
        }

    except Exception as exc:
        logger.exception("Network map build failed: %s", exc)
        try:
            NetworkMapSnapshot.objects.create(
                generated_at=now,
                source_window_hours=window_hours,
                status='error',
                error=str(exc)[:4000],
                is_current=False,
                build_duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception:
            logger.exception("Failed to persist network map error snapshot")

        return {
            'status': 'error',
            'error': str(exc),
            'window_hours': window_hours,
            'keep_last': keep_last,
        }
