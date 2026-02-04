import json
import math
import os
from datetime import timedelta

import requests
from django.utils import timezone

from inventory_api.models import RawMetric, ComputedMetric


SEVERITY_ORDER = {
    'low': 1,
    'medium': 2,
    'high': 3,
    'critical': 4,
}


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


def _latest_metrics(device, model, since):
    qs = (
        model.objects
        .filter(device=device, timestamp__gte=since)
        .order_by('-timestamp')
    )
    seen = set()
    out = []
    for row in qs:
        labels = getattr(row, 'labels', None) or {}
        key = (row.code, tuple(sorted(labels.items())))
        if key in seen:
            continue
        seen.add(key)
        value = _to_float(row.value)
        out.append({
            'code': row.code,
            'value': value,
            'unit': getattr(row, 'unit', '') or '',
            'timestamp': row.timestamp.isoformat() if row.timestamp else None,
            'labels': labels,
        })
    return out


def _latest_computed(device, since):
    qs = (
        ComputedMetric.objects
        .filter(device=device, timestamp__gte=since)
        .order_by('-timestamp')
    )
    seen = set()
    out = []
    for row in qs:
        labels = row.labels or {}
        key = (row.code, row.window, tuple(sorted(labels.items())))
        if key in seen:
            continue
        seen.add(key)
        value = _to_float(row.value)
        out.append({
            'code': row.code,
            'value': value,
            'unit': row.unit or '',
            'window': row.window,
            'timestamp': row.timestamp.isoformat() if row.timestamp else None,
            'labels': labels,
        })
    return out


def _group_by_code(metrics):
    grouped = {}
    for item in metrics:
        grouped.setdefault(item['code'], []).append(item)
    return grouped


def _max_value(grouped, code):
    items = grouped.get(code, [])
    vals = [i['value'] for i in items if i['value'] is not None and not math.isnan(i['value'])]
    return max(vals) if vals else None


def _any_value(grouped, code):
    return _max_value(grouped, code)


def _severity_from_issues(issues):
    if not issues:
        return 'low'
    return max((issue['severity'] for issue in issues), key=lambda s: SEVERITY_ORDER.get(s, 0))


def _unique_recommendations(issues):
    recs = []
    seen = set()
    for issue in issues:
        rec = issue.get('recommendation')
        if rec and rec not in seen:
            seen.add(rec)
            recs.append(rec)
    if not recs:
        recs = ["No action required"]
    return recs


def evaluate_rules(raw_latest, computed_latest):
    raw_map = _group_by_code(raw_latest)
    comp_map = _group_by_code(computed_latest)

    issues = []

    def add_issue(issue):
        if issue:
            issues.append(issue)

    def ev(key, value):
        return f"{key}={value}"

    cpu_spikes = _max_value(comp_map, 'cpu_spike_count_1h')
    cpu_peak = _max_value(comp_map, 'cpu_peak_24h')
    cpu_trend = _max_value(comp_map, 'cpu_trend_24h')
    cpu_var = _max_value(comp_map, 'cpu_variance_24h')
    cpu_kernel_ratio = _max_value(comp_map, 'cpu_kernel_ratio_1h')
    mem_trend = _max_value(comp_map, 'mem_trend_24h')
    mem_peak = _max_value(comp_map, 'mem_peak_24h')
    mem_var = _max_value(comp_map, 'mem_variance_24h')
    mem_leak = _max_value(comp_map, 'mem_leak_prob')
    swap_ratio = _max_value(comp_map, 'swap_active_ratio_24h')
    disk_fill = _max_value(comp_map, 'disk_fill_rate_7d')
    disk_peak = _max_value(comp_map, 'disk_usage_peak_7d')
    disk_read_spikes = _max_value(comp_map, 'disk_read_spike_count_24h')
    disk_write_spikes = _max_value(comp_map, 'disk_write_spike_count_24h')
    ping_spikes = _max_value(comp_map, 'ping_spike_count_1h')
    ping_jitter = _max_value(comp_map, 'ping_jitter_1h')
    ping_peak = _max_value(comp_map, 'ping_peak_1h')
    net_err_in = _max_value(comp_map, 'net_errors_in_burst_count_1h')
    net_err_out = _max_value(comp_map, 'net_errors_out_burst_count_1h')
    temp_spikes = _max_value(comp_map, 'temp_spike_count_24h')
    temp_var = _max_value(comp_map, 'temp_variance_24h')
    storcli_err = _max_value(comp_map, 'storcli_error_delta_24h')
    storcli_pred = _max_value(comp_map, 'storcli_pred_fail_delta_24h')
    storcli_overheat = _max_value(comp_map, 'storcli_overheat_ratio_24h')
    storcli_smart = _max_value(comp_map, 'storcli_smart_alert_active')
    uptime_resets = _max_value(comp_map, 'uptime_reset_count_7d')
    vm_avail = _max_value(comp_map, 'vm_availability_24h')
    vm_cpu_peak = _max_value(comp_map, 'vm_cpu_peak_24h')
    vm_mem_peak = _max_value(comp_map, 'vm_mem_peak_24h')

    # 1) CPU saturation
    if (cpu_spikes is not None and cpu_spikes >= 10) or (cpu_peak is not None and cpu_peak >= 95):
        evidence = []
        if cpu_spikes is not None:
            evidence.append(ev('cpu_spike_count_1h', cpu_spikes))
        if cpu_peak is not None:
            evidence.append(ev('cpu_peak_24h', cpu_peak))
        add_issue({
            'id': 'cpu_saturation',
            'title': 'CPU saturation',
            'severity': 'high' if cpu_peak and cpu_peak >= 98 else 'medium',
            'evidence': evidence,
            'explanation': 'CPU load is saturating or spiking frequently.',
            'recommendation': 'Inspect top CPU processes, stagger heavy jobs, check noisy neighbors.'
        })

    # 2) CPU trend/variance
    if (cpu_trend is not None and cpu_trend > 1.0) or (cpu_var is not None and cpu_var > 200):
        evidence = []
        if cpu_trend is not None:
            evidence.append(ev('cpu_trend_24h', cpu_trend))
        if cpu_var is not None:
            evidence.append(ev('cpu_variance_24h', cpu_var))
        add_issue({
            'id': 'cpu_degradation',
            'title': 'CPU load instability',
            'severity': 'medium',
            'evidence': evidence,
            'explanation': 'CPU load is increasing or highly unstable.',
            'recommendation': 'Review recent changes, scheduled tasks, and CPU-intensive services.'
        })

    # 3) Kernel CPU dominance
    if cpu_kernel_ratio is not None and cpu_kernel_ratio > 0.6:
        add_issue({
            'id': 'cpu_kernel_ratio',
            'title': 'High kernel CPU ratio',
            'severity': 'medium',
            'evidence': [ev('cpu_kernel_ratio_1h', cpu_kernel_ratio)],
            'explanation': 'High kernel time may indicate driver or IO issues.',
            'recommendation': 'Check drivers, storage IO, antivirus, and kernel logs.'
        })

    # 4) Memory pressure trend
    if (mem_trend is not None and mem_trend > 0.5) or (mem_peak is not None and mem_peak >= 95):
        evidence = []
        if mem_trend is not None:
            evidence.append(ev('mem_trend_24h', mem_trend))
        if mem_peak is not None:
            evidence.append(ev('mem_peak_24h', mem_peak))
        add_issue({
            'id': 'mem_pressure',
            'title': 'Memory pressure',
            'severity': 'high' if mem_peak and mem_peak >= 98 else 'medium',
            'evidence': evidence,
            'explanation': 'Memory usage is growing or near capacity.',
            'recommendation': 'Identify leaking process, reduce cache, restart service if needed.'
        })

    # 5) Memory leak probability
    if mem_leak is not None and mem_leak >= 0.5:
        add_issue({
            'id': 'mem_leak',
            'title': 'Possible memory leak',
            'severity': 'high',
            'evidence': [ev('mem_leak_prob', mem_leak)],
            'explanation': 'Memory growth correlates with uptime and swap activity.',
            'recommendation': 'Review long-running processes, apply fixes, schedule restarts.'
        })

    # 6) Swap activity
    if swap_ratio is not None and swap_ratio > 0.2:
        add_issue({
            'id': 'swap_active',
            'title': 'Swap activity detected',
            'severity': 'medium',
            'evidence': [ev('swap_active_ratio_24h', swap_ratio)],
            'explanation': 'Swap usage indicates RAM shortage.',
            'recommendation': 'Increase RAM, tune services, reduce memory footprint.'
        })

    # 7) CPU + mem trend (runaway)
    if (cpu_peak is not None and cpu_peak >= 90) and (mem_trend is not None and mem_trend > 0.5):
        add_issue({
            'id': 'cpu_mem_runaway',
            'title': 'CPU + memory runaway',
            'severity': 'high',
            'evidence': [ev('cpu_peak_24h', cpu_peak), ev('mem_trend_24h', mem_trend)],
            'explanation': 'High CPU together with memory growth suggests a runaway process.',
            'recommendation': 'Inspect top processes, isolate service, apply fixes or restart.'
        })

    # 8) Disk fill risk
    if (disk_fill is not None and disk_fill > 1.0) or (disk_peak is not None and disk_peak > 90):
        evidence = []
        if disk_fill is not None:
            evidence.append(ev('disk_fill_rate_7d', disk_fill))
        if disk_peak is not None:
            evidence.append(ev('disk_usage_peak_7d', disk_peak))
        add_issue({
            'id': 'disk_fill',
            'title': 'Disk fill risk',
            'severity': 'high' if disk_peak and disk_peak > 95 else 'medium',
            'evidence': evidence,
            'explanation': 'Disk usage indicates fast growth or near-full volume.',
            'recommendation': 'Cleanup logs, move data, or expand the volume.'
        })

    # 9) Disk IO anomalies
    if (disk_read_spikes is not None and disk_read_spikes >= 5) or (disk_write_spikes is not None and disk_write_spikes >= 5):
        evidence = []
        if disk_read_spikes is not None:
            evidence.append(ev('disk_read_spike_count_24h', disk_read_spikes))
        if disk_write_spikes is not None:
            evidence.append(ev('disk_write_spike_count_24h', disk_write_spikes))
        add_issue({
            'id': 'disk_io_spikes',
            'title': 'Disk IO spikes',
            'severity': 'medium',
            'evidence': evidence,
            'explanation': 'Abnormal disk IO bursts were detected.',
            'recommendation': 'Check backups, database jobs, malware scans, and IO-heavy tasks.'
        })

    # 10) Network instability
    if (ping_spikes is not None and ping_spikes >= 5) or (ping_jitter is not None and ping_jitter > 20) or (ping_peak is not None and ping_peak > 150):
        evidence = []
        if ping_spikes is not None:
            evidence.append(ev('ping_spike_count_1h', ping_spikes))
        if ping_jitter is not None:
            evidence.append(ev('ping_jitter_1h', ping_jitter))
        if ping_peak is not None:
            evidence.append(ev('ping_peak_1h', ping_peak))
        add_issue({
            'id': 'net_instability',
            'title': 'Network instability',
            'severity': 'medium',
            'evidence': evidence,
            'explanation': 'Latency spikes or jitter indicate unstable network.',
            'recommendation': 'Check gateway, link quality, switch port errors, congestion.'
        })

    # 11) Ping spikes + net errors
    if (ping_spikes is not None and ping_spikes >= 5) and ((net_err_in or 0) > 0 or (net_err_out or 0) > 0):
        evidence = [ev('ping_spike_count_1h', ping_spikes)]
        if net_err_in is not None:
            evidence.append(ev('net_errors_in_burst_count_1h', net_err_in))
        if net_err_out is not None:
            evidence.append(ev('net_errors_out_burst_count_1h', net_err_out))
        add_issue({
            'id': 'net_errors_with_ping',
            'title': 'Network errors with latency spikes',
            'severity': 'high',
            'evidence': evidence,
            'explanation': 'Packet errors combined with ping spikes suggest physical or link issues.',
            'recommendation': 'Inspect cabling, NIC, switch port, duplex settings.'
        })

    # 12) Temperature risk
    if (temp_spikes is not None and temp_spikes > 0) or (temp_var is not None and temp_var > 50):
        evidence = []
        if temp_spikes is not None:
            evidence.append(ev('temp_spike_count_24h', temp_spikes))
        if temp_var is not None:
            evidence.append(ev('temp_variance_24h', temp_var))
        add_issue({
            'id': 'temp_risk',
            'title': 'Temperature risk',
            'severity': 'high',
            'evidence': evidence,
            'explanation': 'Overheating spikes or unstable temperature detected.',
            'recommendation': 'Check cooling, fans, airflow, and ambient temperature.'
        })

    # 13) StorCLI media errors
    if storcli_err is not None and storcli_err > 0:
        add_issue({
            'id': 'storcli_media_errors',
            'title': 'RAID media errors increased',
            'severity': 'high',
            'evidence': [ev('storcli_error_delta_24h', storcli_err)],
            'explanation': 'Media error counters increased over 24h.',
            'recommendation': 'Run patrol read and plan disk replacement.'
        })

    # 14) StorCLI predictive failure
    if (storcli_pred is not None and storcli_pred > 0) or (storcli_smart is not None and storcli_smart >= 1):
        evidence = []
        if storcli_pred is not None:
            evidence.append(ev('storcli_pred_fail_delta_24h', storcli_pred))
        if storcli_smart is not None:
            evidence.append(ev('storcli_smart_alert_active', storcli_smart))
        add_issue({
            'id': 'storcli_pred_fail',
            'title': 'Disk failure risk',
            'severity': 'critical',
            'evidence': evidence,
            'explanation': 'Predictive failure or SMART alert detected.',
            'recommendation': 'Replace disk ASAP and verify backups.'
        })

    # 15) StorCLI overheating
    if storcli_overheat is not None and storcli_overheat > 0.2:
        add_issue({
            'id': 'storcli_overheat',
            'title': 'RAID disk overheating',
            'severity': 'high',
            'evidence': [ev('storcli_overheat_ratio_24h', storcli_overheat)],
            'explanation': 'Drive temperature exceeded safe threshold frequently.',
            'recommendation': 'Improve airflow and RAID cooling.'
        })

    # 16) Frequent reboots
    if uptime_resets is not None and uptime_resets >= 2:
        add_issue({
            'id': 'frequent_reboots',
            'title': 'Frequent reboots',
            'severity': 'medium',
            'evidence': [ev('uptime_reset_count_7d', uptime_resets)],
            'explanation': 'Multiple reboots detected in the last 7 days.',
            'recommendation': 'Check OS logs, power stability, and recent patches.'
        })

    # 17) VM availability
    if vm_avail is not None and vm_avail < 0.95:
        add_issue({
            'id': 'vm_availability',
            'title': 'VM availability degraded',
            'severity': 'medium',
            'evidence': [ev('vm_availability_24h', vm_avail)],
            'explanation': 'VMs are often down or paused.',
            'recommendation': 'Check host resources, storage, VM scheduling.'
        })

    # 18) VM resource contention
    if (vm_cpu_peak is not None and vm_cpu_peak > 90) or (vm_mem_peak is not None and vm_mem_peak > 90):
        evidence = []
        if vm_cpu_peak is not None:
            evidence.append(ev('vm_cpu_peak_24h', vm_cpu_peak))
        if vm_mem_peak is not None:
            evidence.append(ev('vm_mem_peak_24h', vm_mem_peak))
        add_issue({
            'id': 'vm_resource_contention',
            'title': 'VM resource saturation',
            'severity': 'medium',
            'evidence': evidence,
            'explanation': 'VM CPU or memory peaks indicate saturation risk.',
            'recommendation': 'Resize VM or reduce workload, check host contention.'
        })

    return issues


def build_diagnostic_report(device):
    now = timezone.now()
    since = now - timedelta(days=7)

    raw_latest = _latest_metrics(device, RawMetric, since)
    computed_latest = _latest_computed(device, since)
    issues = evaluate_rules(raw_latest, computed_latest)
    severity = _severity_from_issues(issues)

    if issues:
        titles = [i['title'] for i in issues[:2]]
        summary = f"{len(issues)} issue(s) detected: " + ", ".join(titles)
    else:
        summary = "No critical issues detected in the selected windows."

    report = {
        'summary': summary,
        'severity': severity,
        'issues': issues,
        'recommendations': _unique_recommendations(issues),
        'confidence': 0.4 if issues else 0.7,
    }

    payload = {
        'generated_at': now.isoformat(),
        'windows': ['1h', '24h', '7d'],
        'raw_latest': raw_latest,
        'computed_latest': computed_latest,
        'active_rules': [i['id'] for i in issues],
        'rule_issues': issues,
    }

    return report, payload


def _load_prompt_template(payload):
    template = None
    try:
        from django.conf import settings
        path = os.path.join(settings.BASE_DIR, 'LLM_PROMPT_TEMPLATE.md')
        with open(path, 'r', encoding='utf-8') as handle:
            template = handle.read()
    except Exception:
        template = None

    if template and 'SYSTEM:' in template and 'USER:' in template:
        system_part = template.split('SYSTEM:', 1)[1].split('USER:', 1)[0].strip()
        user_part = template.split('USER:', 1)[1].strip()
    else:
        system_part = (
            "You are a diagnostic assistant for system administrators. "
            "Use only the provided data. If data is missing, say so. "
            "Provide a concise summary, then issues with evidence and recommendations. "
            "Do not invent metrics or devices."
        )
        user_part = (
            "You are given JSON with raw metrics, computed metrics, agent status, and active rules. "
            "Use all metrics. Analyze 3 windows: last 1h, 24h, 7d. "
            "Produce a diagnostic report.\n\n"
            "INPUT JSON:\n```{{DIAGNOSTIC_PAYLOAD_JSON}}```\n\n"
            "REQUIRED OUTPUT (JSON):\n"
            "{\n"
            '  "summary": "...",\n'
            '  "severity": "low|medium|high|critical",\n'
            '  "issues": [\n'
            '    {\n'
            '      "id": "mem_leak",\n'
            '      "title": "Possible memory leak",\n'
            '      "severity": "high",\n'
            '      "evidence": ["mem_trend_24h=0.8", "swap_active_ratio_24h=0.2"],\n'
            '      "explanation": "...",\n'
            '      "recommendation": "..." \n'
            '    }\n'
            "  ],\n"
            '  "recommendations": ["...", "..."],\n'
            '  "confidence": 0.0\n'
            "}\n\n"
            "NOTES:\n"
            "- Use evidence from input only.\n"
            "- If no issues, return empty issues array and recommend \"No action required\".\n"
            "- Keep summary under 2 sentences."
        )

    payload_json = json.dumps(payload, ensure_ascii=False)
    user_part = user_part.replace('{{DIAGNOSTIC_PAYLOAD_JSON}}', payload_json)
    return system_part, user_part


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    if not text:
        return None
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start:end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def _run_groq_llm(payload):
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return None, 'GROQ_API_KEY is not set'

    base_url = os.environ.get('GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
    model = os.environ.get('GROQ_MODEL', 'llama-3.1-8b-instant')
    timeout = int(os.environ.get('GROQ_TIMEOUT_SEC', '45'))

    system_part, user_part = _load_prompt_template(payload)
    req = {
        'model': model,
        'temperature': 0.2,
        'max_tokens': 800,
        'messages': [
            {'role': 'system', 'content': system_part},
            {'role': 'user', 'content': user_part},
        ],
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                'Authorization': f"Bearer {api_key}",
                'Content-Type': 'application/json',
            },
            json=req,
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return None, f"Groq error {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        content = data['choices'][0]['message']['content']
        parsed = _extract_json(content)
        if not parsed:
            return None, "Groq response not JSON"
        return parsed, None
    except Exception as exc:
        return None, str(exc)


def generate_diagnostic_report(device, mode=None):
    local_report, payload = build_diagnostic_report(device)

    provider = os.environ.get('LLM_PROVIDER', 'local').lower()
    if mode == 'rules':
        payload['llm_used'] = False
        payload['llm_provider'] = provider
        payload['llm_mode'] = 'rules'
        return local_report, payload
    if provider != 'groq':
        payload['llm_used'] = False
        payload['llm_provider'] = provider
        payload['llm_mode'] = 'rules'
        return local_report, payload

    llm_report, err = _run_groq_llm(payload)
    if not llm_report:
        payload['llm_used'] = False
        payload['llm_provider'] = 'groq'
        payload['llm_mode'] = 'rules'
        payload['llm_error'] = err
        return local_report, payload

    report = {
        'summary': llm_report.get('summary') or local_report['summary'],
        'severity': llm_report.get('severity') or local_report['severity'],
        'issues': llm_report.get('issues') or local_report['issues'],
        'recommendations': llm_report.get('recommendations') or local_report['recommendations'],
        'confidence': llm_report.get('confidence', local_report.get('confidence', 0.0)),
    }
    payload['llm_used'] = True
    payload['llm_provider'] = 'groq'
    payload['llm_mode'] = 'llm'
    payload['llm_model'] = os.environ.get('GROQ_MODEL', 'llama-3.1-8b-instant')
    return report, payload
