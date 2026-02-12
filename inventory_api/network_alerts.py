from collections import defaultdict

from django.utils import timezone

from .models import ComputedMetric, NetworkAlertRule, NetworkPath


SEVERITY_ORDER = {
    'critical': 4,
    'high': 3,
    'medium': 2,
    'low': 1,
}

DERIVED_NETWORK_CODES = [
    'net_path_uptime_24h',
    'net_path_uptime_7d',
    'net_path_outage_count_24h',
    'net_path_outage_count_7d',
    'net_path_latency_p95_24h',
    'net_path_latency_jitter_1h',
    'net_path_packet_loss_avg_24h',
    'net_path_down_flag_current',
]

DEFAULT_NETWORK_ALERT_RULES = [
    {
        'code': 'path_down_now',
        'name': 'Путь недоступен сейчас',
        'description': 'Путь в состоянии DOWN по последнему probe.',
        'metric_code': 'net_path_down_flag_current',
        'window': 'current',
        'comparison': 'eq',
        'threshold_value': 1.0,
        'severity': 'critical',
        'order': 10,
    },
    {
        'code': 'uptime_low_24h',
        'name': 'Низкий uptime за 24ч',
        'description': 'Uptime пути за 24 часа меньше порога.',
        'metric_code': 'net_path_uptime_24h',
        'window': '24h',
        'comparison': 'lt',
        'threshold_value': 99.0,
        'severity': 'high',
        'order': 20,
    },
    {
        'code': 'outage_burst_24h',
        'name': 'Много пропаданий за 24ч',
        'description': 'Количество outage за 24 часа превысило порог.',
        'metric_code': 'net_path_outage_count_24h',
        'window': '24h',
        'comparison': 'gte',
        'threshold_value': 3.0,
        'severity': 'high',
        'order': 30,
    },
    {
        'code': 'latency_p95_high_24h',
        'name': 'Высокая p95 задержка',
        'description': '95-й перцентиль задержки за 24 часа выше порога.',
        'metric_code': 'net_path_latency_p95_24h',
        'window': '24h',
        'comparison': 'gt',
        'threshold_value': 80.0,
        'severity': 'medium',
        'order': 40,
    },
    {
        'code': 'loss_avg_high_24h',
        'name': 'Высокие потери пакетов',
        'description': 'Средние потери пакетов за 24 часа выше порога.',
        'metric_code': 'net_path_packet_loss_avg_24h',
        'window': '24h',
        'comparison': 'gt',
        'threshold_value': 5.0,
        'severity': 'high',
        'order': 50,
    },
]


def ensure_default_network_alert_rules():
    created = 0
    updated = 0
    for item in DEFAULT_NETWORK_ALERT_RULES:
        obj, was_created = NetworkAlertRule.objects.update_or_create(
            code=item['code'],
            defaults=item,
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {'created': created, 'updated': updated}


def _coerce_path_id(labels):
    if not isinstance(labels, dict):
        return None
    raw = labels.get('path_id')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _latest_metrics_by_path():
    qs = (
        ComputedMetric.objects
        .filter(code__in=DERIVED_NETWORK_CODES)
        .values('code', 'value', 'window', 'timestamp', 'labels')
        .order_by('-timestamp')
    )
    latest = {}
    for row in qs:
        path_id = _coerce_path_id(row.get('labels') or {})
        if not path_id:
            continue
        key = (path_id, row['code'])
        if key in latest:
            continue
        latest[key] = row
    return latest


def get_network_derived_snapshot():
    latest = _latest_metrics_by_path()
    paths = list(NetworkPath.objects.select_related('src_device', 'dst_device').order_by('src_device__name', 'dst_device__name'))
    path_map = {path.id: path for path in paths}
    path_ids = [path.id for path in paths]
    by_path = defaultdict(dict)
    for (path_id, code), row in latest.items():
        by_path[path_id][code] = float(row['value'])
        by_path[path_id][f'{code}__ts'] = row['timestamp']

    rows = []
    for path_id in path_ids:
        path = path_map.get(path_id)
        if path is None:
            continue
        values = by_path.get(path_id, {})
        metric_timestamps = [
            values.get('net_path_uptime_24h__ts'),
            values.get('net_path_uptime_7d__ts'),
            values.get('net_path_latency_p95_24h__ts'),
            values.get('net_path_packet_loss_avg_24h__ts'),
        ]
        metric_timestamps = [ts for ts in metric_timestamps if ts is not None]
        rows.append({
            'path_id': path_id,
            'src_device_name': path.src_device.name,
            'dst_device_name': path.dst_device.name,
            'dst_ip': path.dst_device.ip_address,
            'state': path.last_state,
            'net_path_uptime_24h': values.get('net_path_uptime_24h'),
            'net_path_uptime_7d': values.get('net_path_uptime_7d'),
            'net_path_outage_count_24h': values.get('net_path_outage_count_24h'),
            'net_path_outage_count_7d': values.get('net_path_outage_count_7d'),
            'net_path_latency_p95_24h': values.get('net_path_latency_p95_24h'),
            'net_path_latency_jitter_1h': values.get('net_path_latency_jitter_1h'),
            'net_path_packet_loss_avg_24h': values.get('net_path_packet_loss_avg_24h'),
            'net_path_down_flag_current': values.get('net_path_down_flag_current'),
            'updated_at': max(metric_timestamps) if metric_timestamps else None,
        })
    return rows


def _compare(value, comparison, threshold):
    if value is None:
        return False
    if comparison == 'gt':
        return value > threshold
    if comparison == 'gte':
        return value >= threshold
    if comparison == 'lt':
        return value < threshold
    if comparison == 'lte':
        return value <= threshold
    if comparison == 'eq':
        return value == threshold
    if comparison == 'ne':
        return value != threshold
    return False


def evaluate_network_alert_rules():
    rows = get_network_derived_snapshot()
    rows_by_path = {row['path_id']: row for row in rows}
    rules = list(NetworkAlertRule.objects.filter(enabled=True).order_by('order', 'id'))
    alerts = []

    for rule in rules:
        for row in rows:
            value = row.get(rule.metric_code)
            if _compare(value, rule.comparison, rule.threshold_value):
                alerts.append({
                    'rule_code': rule.code,
                    'rule_name': rule.name,
                    'severity': rule.severity,
                    'path_id': row['path_id'],
                    'src_device_name': row['src_device_name'],
                    'dst_device_name': row['dst_device_name'],
                    'dst_ip': row['dst_ip'],
                    'metric_code': rule.metric_code,
                    'metric_value': value,
                    'comparison': rule.comparison,
                    'threshold_value': rule.threshold_value,
                    'window': rule.window,
                    'message': f"{rule.metric_code} {rule.comparison} {rule.threshold_value} (actual={value})",
                    'updated_at': row.get('updated_at'),
                })

    alerts.sort(
        key=lambda item: (
            -SEVERITY_ORDER.get(item['severity'], 0),
            item['rule_name'],
            item['src_device_name'],
            item['dst_device_name'],
        )
    )

    summary = {
        'critical': sum(1 for item in alerts if item['severity'] == 'critical'),
        'high': sum(1 for item in alerts if item['severity'] == 'high'),
        'medium': sum(1 for item in alerts if item['severity'] == 'medium'),
        'low': sum(1 for item in alerts if item['severity'] == 'low'),
        'total': len(alerts),
        'generated_at': timezone.now(),
    }
    return {
        'summary': summary,
        'alerts': alerts,
        'rows': list(rows_by_path.values()),
    }
