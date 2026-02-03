import configparser
import json
import logging
import os
import re
import subprocess
import sys
import socket
import time
from datetime import datetime, timezone

import psutil
import requests
import win32com.client

# Настройка путей
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(application_path, 'config.ini')
log_path = os.path.join(application_path, 'agent.log')
logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _run_cmd(cmd):
    kwargs = {
        'stderr': subprocess.STDOUT
    }
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs['startupinfo'] = startupinfo
    return subprocess.check_output(cmd, **kwargs)


def _run_cmd_optional(cmd):
    kwargs = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.STDOUT,
        'check': False,
        'text': False,
    }
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs['startupinfo'] = startupinfo
    return subprocess.run(cmd, **kwargs)


def _decode_cmd_output(raw):
    if os.name == 'nt':
        for enc in ('cp866', 'utf-8', 'cp1251'):
            try:
                return raw.decode(enc)
            except Exception:
                continue
        return raw.decode(errors='ignore')
    return raw.decode(errors='ignore')


def get_serial_number():
    """Автоматически получает серийный номер из Windows."""
    try:
        result = _run_cmd(["wmic", "bios", "get", "serialnumber"]).decode(errors='ignore')
        serial = result.split('\n')[1].strip()
        return serial
    except Exception as e:
        logging.error(f"Failed to auto-detect serial number: {e}")
        return "UNKNOWN"


def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        logging.error("Config file not found!")
        return None
    config.read(config_path)
    return config


def _resolve_storcli_path(config_value):
    if config_value:
        if os.path.isdir(config_value):
            candidate = os.path.join(config_value, "storcli64.exe")
            if os.path.exists(candidate):
                return candidate
        if os.path.exists(config_value):
            return config_value
    try:
        output = _decode_cmd_output(_run_cmd(["where", "storcli64"]))
        first = output.splitlines()[0].strip()
        return first or None
    except Exception:
        return None


def _safe_int(value, default=None):
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _parse_temp_c(value):
    if not value:
        return None
    match = re.search(r'([-+]?\d+)\s*C', str(value))
    if match:
        return _safe_int(match.group(1))
    return None


def _storcli_run_json(storcli_path, args):
    if not storcli_path:
        return None
    output = _decode_cmd_output(_run_cmd([storcli_path] + args))
    idx = output.find('{')
    if idx == -1:
        logging.warning("StorCLI output does not contain JSON.")
        return None
    try:
        return json.loads(output[idx:])
    except Exception as e:
        logging.warning(f"Failed to parse StorCLI JSON: {e}")
        return None


def _log_storcli_info(storcli_path):
    if not storcli_path:
        logging.info("StorCLI not found; RAID metrics disabled.")
        return

    logging.info(f"StorCLI detected: {storcli_path}")
    try:
        result = _run_cmd_optional([storcli_path, "/v"])
        version_text = _decode_cmd_output(result.stdout or b'')
        first_line = version_text.splitlines()[0] if version_text else ""
        if result.returncode == 0 and first_line:
            logging.info(f"StorCLI version: {first_line}")
        else:
            logging.warning(
                f"StorCLI version read failed (rc={result.returncode}). "
                f"Maybe requires admin or /v unsupported."
            )
    except Exception as e:
        logging.warning(f"StorCLI version read failed: {e}")

    data = _storcli_run_json(storcli_path, ["/cALL", "show", "J"])
    if not data:
        return
    controllers = data.get("Controllers", [])
    logging.info(f"StorCLI controllers: {len(controllers)}")


def _check_ping_target(target):
    if not target:
        logging.info("PingTarget не задан - метрика выключена.")
        return
    try:
        latency = _ping_latency_ms(target)
        if latency is not None:
            logging.info(f"PingTarget ok: {target} latency={latency}ms")
        else:
            logging.warning(f"PingTarget unreachable: {target}")
    except Exception as e:
        logging.warning(f"PingTarget check failed ({target}): {e}")


def _ping_latency_ms(target):
    try:
        output = _decode_cmd_output(_run_cmd(["ping", "-n", "1", "-w", "1000", target]))
        match = re.search(r'Average = (\d+)ms', output)
        if not match:
            match = re.search(r'Average = (<1)ms', output)
        if not match:
            match = re.search(r'Среднее = (\d+)мс', output)
        if not match:
            match = re.search(r'Среднее = (<1)мс', output)
        if not match:
            match = re.search(r'time[=<] ?(\d+|<1)ms', output, re.IGNORECASE)
        if not match:
            match = re.search(r'время[=<] ?(\d+|<1)мс', output, re.IGNORECASE)
        if match:
            value = match.group(1)
            if value == '<1':
                return 0
            return int(value)
        if 'TTL=' in output.upper():
            return 0
    except Exception:
        return None
    return None


def _api_url(base, path):
    if not base.endswith('/'):
        base += '/'
    return f"{base}{path}"


def send_metrics_batch(api_base, token, serial, metrics, retention_days=None, device_info=None):
    if not metrics:
        return True
    url = _api_url(api_base, 'metrics-raw/ingest/')
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'serial_number': serial,
        'metrics': metrics,
    }
    if device_info:
        payload['device_info'] = device_info
    if retention_days:
        payload['retention_days'] = retention_days
    try:
        logging.debug(f"Sending metrics batch: count={len(metrics)} retention={retention_days}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 201:
            logging.error(f"Failed metrics ingest: {response.status_code} {response.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"Connection error (metrics ingest): {e}")
        return False


def send_agent_status(api_base, token, serial, status_value, message=""):
    url = _api_url(api_base, 'agent-status/report/')
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'serial_number': serial,
        'status': status_value,
        'message': message or ''
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def send_vm_status(api_base, token, serial, vms):
    if vms is None:
        return False
    url = _api_url(api_base, 'tracked-vms/sync_status/')
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'serial_number': serial,
        'vms': vms,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.error(f"Failed VM sync: {response.status_code} {response.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"Connection error (vm sync): {e}")
        return False


def _get_cpu_name():
    try:
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = locator.ConnectServer(".", "root\\cimv2")
        cpus = service.ExecQuery("SELECT Name FROM Win32_Processor")
        for cpu in cpus:
            name = getattr(cpu, 'Name', None)
            if name:
                return name.strip()
    except Exception:
        return None
    return None


def _get_primary_ip_mac():
    ip_address = None
    mac_address = None
    try:
        import socket
        for iface, addrs in psutil.net_if_addrs().items():
            stats = psutil.net_if_stats().get(iface)
            if stats and not stats.isup:
                continue
            ipv4 = None
            mac = None
            for addr in addrs:
                if getattr(addr, 'family', None) == socket.AF_INET:
                    if addr.address and not addr.address.startswith('127.'):
                        ipv4 = addr.address
                if getattr(psutil, 'AF_LINK', None) and addr.family == psutil.AF_LINK:
                    mac = addr.address
            if ipv4:
                ip_address = ipv4
                mac_address = mac
                break
    except Exception:
        pass
    return ip_address, mac_address


_DEVICE_INFO_CACHE = None


def get_device_info():
    global _DEVICE_INFO_CACHE
    if _DEVICE_INFO_CACHE:
        return _DEVICE_INFO_CACHE

    name = os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME') or socket.gethostname()
    serial = get_serial_number()
    ip_address, mac_address = _get_primary_ip_mac()
    cpu_name = _get_cpu_name()
    ram_gb = int(round(psutil.virtual_memory().total / (1024 ** 3)))

    _DEVICE_INFO_CACHE = {
        'name': name or serial,
        'serial_number': serial,
        'asset_number': '-',
        'device_type': 'ПК',
        'status': 'active',
        'owner_username': 'techtracker_admin',
        'ip_address': ip_address,
        'mac_address': mac_address,
        'cpu': cpu_name,
        'ram_gb': ram_gb,
    }
    return _DEVICE_INFO_CACHE


def _metric(code, value, unit, labels=None, timestamp=None):
    if value is None:
        return None
    return {
        'code': code,
        'value': float(value),
        'unit': unit,
        'labels': labels or {},
        'timestamp': timestamp or _now_iso(),
    }


class MetricCollector:
    def __init__(self, ping_target=None, storcli_path=None):
        self.last_cpu_times = None
        self.last_cpu_time_ts = None
        self.last_interrupts = None
        self.last_interrupts_ts = None
        self.last_disk_io = None
        self.last_disk_io_ts = None
        self.last_net_io = None
        self.last_net_io_ts = None
        self.last_ping_latency = None
        self.last_ping_ts = None
        self.ping_target = ping_target
        self.storcli_path = storcli_path
        self._last_storcli = None
        self._last_storcli_ts = None
        psutil.cpu_percent(interval=None)

    def collect_cpu_total(self):
        return [_metric('cpu_load_total', psutil.cpu_percent(interval=None), '%')]

    def collect_cpu_kernel(self):
        now = time.time()
        times = psutil.cpu_times()
        if self.last_cpu_times is None:
            self.last_cpu_times = times
            self.last_cpu_time_ts = now
            return []
        prev_total = sum(self.last_cpu_times)
        curr_total = sum(times)
        delta_total = curr_total - prev_total
        if delta_total <= 0:
            return []
        delta_sys = getattr(times, 'system', 0.0) - getattr(self.last_cpu_times, 'system', 0.0)
        kernel_percent = max(0.0, min(100.0, (delta_sys / delta_total) * 100.0))
        self.last_cpu_times = times
        self.last_cpu_time_ts = now
        return [_metric('cpu_load_kernel', kernel_percent, '%')]

    def collect_cpu_interrupts(self):
        now = time.time()
        stats = psutil.cpu_stats()
        if self.last_interrupts is None:
            self.last_interrupts = stats.interrupts
            self.last_interrupts_ts = now
            return []
        delta = stats.interrupts - self.last_interrupts
        dt = now - (self.last_interrupts_ts or now)
        if dt <= 0:
            return []
        rate = delta / dt
        self.last_interrupts = stats.interrupts
        self.last_interrupts_ts = now
        return [_metric('cpu_interrupts', rate, 'count/sec')]

    def collect_mem_usage(self):
        return [_metric('mem_usage_percent', psutil.virtual_memory().percent, '%')]

    def collect_swap_usage(self):
        return [_metric('mem_swap_usage', psutil.swap_memory().percent, '%')]

    def collect_disk_usage(self):
        metrics = []
        for part in psutil.disk_partitions(all=False):
            if 'cdrom' in part.opts.lower():
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            label = part.device or part.mountpoint
            metrics.append(_metric('disk_usage_percent', usage.percent, '%', {'disk': label}))
        return [m for m in metrics if m]

    def collect_disk_io(self):
        now = time.time()
        io = psutil.disk_io_counters()
        if self.last_disk_io is None:
            self.last_disk_io = io
            self.last_disk_io_ts = now
            return []
        dt = now - (self.last_disk_io_ts or now)
        if dt <= 0:
            return []
        read_rate = (io.read_bytes - self.last_disk_io.read_bytes) / dt / (1024 * 1024)
        write_rate = (io.write_bytes - self.last_disk_io.write_bytes) / dt / (1024 * 1024)
        self.last_disk_io = io
        self.last_disk_io_ts = now
        return [
            _metric('disk_read_bytes', read_rate, 'MB/s'),
            _metric('disk_write_bytes', write_rate, 'MB/s'),
        ]

    def collect_network(self):
        now = time.time()
        net = psutil.net_io_counters()
        if self.last_net_io is None:
            self.last_net_io = net
            self.last_net_io_ts = now
            return []
        dt = now - (self.last_net_io_ts or now)
        if dt <= 0:
            return []
        sent_rate = (net.bytes_sent - self.last_net_io.bytes_sent) / dt / 1024
        recv_rate = (net.bytes_recv - self.last_net_io.bytes_recv) / dt / 1024
        err_in = net.errin - self.last_net_io.errin
        err_out = net.errout - self.last_net_io.errout
        self.last_net_io = net
        self.last_net_io_ts = now
        return [
            _metric('net_bytes_sent', sent_rate, 'KB/s'),
            _metric('net_bytes_recv', recv_rate, 'KB/s'),
            _metric('net_errors_in', err_in, 'count'),
            _metric('net_errors_out', err_out, 'count'),
        ]

    def collect_ping(self):
        if not self.ping_target:
            return []
        try:
            now = time.time()
            if self.last_ping_ts and (now - self.last_ping_ts) < 30 and self.last_ping_latency is not None:
                return [_metric('ping_latency_gateway', self.last_ping_latency, 'ms')]
            latency = _ping_latency_ms(self.ping_target)
            if latency is not None:
                self.last_ping_latency = latency
                self.last_ping_ts = now
                return [_metric('ping_latency_gateway', latency, 'ms')]
        except Exception as e:
            logging.warning(f"Ping failed: {e}")
        return []

    def collect_uptime(self):
        uptime = time.time() - psutil.boot_time()
        return [_metric('uptime_seconds', uptime, 'sec')]

    def collect_process_count(self):
        return [_metric('process_count', len(psutil.pids()), 'count')]

    def collect_system_temperature(self):
        temps = []
        try:
            locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            service = locator.ConnectServer(".", "root\\wmi")
            items = service.ExecQuery("SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature")
            for item in items:
                value = getattr(item, 'CurrentTemperature', None)
                if value is None:
                    continue
                temps.append((value / 10.0) - 273.15)
        except Exception:
            temps = []
        if temps:
            return [_metric('system_temperature', max(temps), 'C')]

        temps = _read_hw_monitor_temps("root\\OpenHardwareMonitor")
        if not temps:
            temps = _read_hw_monitor_temps("root\\LibreHardwareMonitor")
        if temps:
            return [_metric('system_temperature', max(temps), 'C')]
        return []

    def _collect_storcli_all(self):
        if not self.storcli_path:
            return []
        now = time.time()
        if self._last_storcli and self._last_storcli_ts and (now - self._last_storcli_ts) < 30:
            return self._last_storcli
        metrics = _storcli_collect_physical(self.storcli_path)
        self._last_storcli = [m for m in metrics if m]
        self._last_storcli_ts = now
        return self._last_storcli

    def collect_storcli_temperature(self):
        metrics = self._collect_storcli_all()
        return [m for m in metrics if m and m.get('code') == 'storcli_drive_temperature']

    def collect_storcli_errors(self):
        metrics = self._collect_storcli_all()
        return [
            m for m in metrics
            if m and m.get('code') in (
                'storcli_media_error_count',
                'storcli_other_error_count',
                'storcli_predictive_failure_count',
                'storcli_smart_alert',
            )
        ]


def _storcli_collect_physical(storcli_path):
    data = _storcli_run_json(storcli_path, ["/cALL", "/eALL", "/sALL", "show", "all", "J"])
    if not data:
        return []

    controllers = data.get("Controllers", [])
    metrics = []

    for ctrl in controllers:
        status = ctrl.get("Command Status", {})
        controller_id = status.get("Controller")
        response = ctrl.get("Response Data", {})

        for key, value in response.items():
            if not key.startswith("Drive /c") or key.endswith(" - Detailed Information"):
                continue
            drive_key = key
            summary = {}
            if isinstance(value, list) and value:
                summary = value[0]
            elif isinstance(value, dict):
                summary = value

            detail = response.get(f"{drive_key} - Detailed Information", {})
            state = detail.get(f"{drive_key} State", {})
            attrs = detail.get(f"{drive_key} Device attributes", {})

            labels = {"drive": drive_key.replace("Drive ", "")}
            eid = summary.get("EID:Slt")
            did = summary.get("DID")
            model = summary.get("Model") or attrs.get("Model Number")
            serial = attrs.get("SN")

            if controller_id is not None:
                labels["controller"] = str(controller_id)
            if eid:
                labels["eid_slt"] = str(eid)
            if did is not None:
                labels["did"] = str(did)
            if model:
                labels["model"] = str(model).strip()
            if serial:
                labels["serial"] = str(serial).strip()

            temp_c = _parse_temp_c(state.get("Drive Temperature"))
            media_err = _safe_int(state.get("Media Error Count"))
            other_err = _safe_int(state.get("Other Error Count"))
            pred_fail = _safe_int(state.get("Predictive Failure Count"))
            smart_alert = state.get("S.M.A.R.T alert flagged by drive")

            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(
                    "StorCLI drive %s temp=%s media_err=%s other_err=%s pred_fail=%s smart_alert=%s",
                    labels.get("drive"), temp_c, media_err, other_err, pred_fail, smart_alert
                )

            if temp_c is not None:
                metrics.append(_metric("storcli_drive_temperature", temp_c, "C", labels))
            if media_err is not None:
                metrics.append(_metric("storcli_media_error_count", media_err, "count", labels))
            if other_err is not None:
                metrics.append(_metric("storcli_other_error_count", other_err, "count", labels))
            if pred_fail is not None:
                metrics.append(_metric("storcli_predictive_failure_count", pred_fail, "count", labels))
            if smart_alert is not None:
                smart_alert_val = 0 if str(smart_alert).strip().lower() in ('no', 'false', '0') else 1
                metrics.append(_metric("storcli_smart_alert", smart_alert_val, "flag", labels))

    return metrics


def _read_hw_monitor_temps(namespace):
    temps = []
    try:
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = locator.ConnectServer(".", namespace)
        items = service.ExecQuery("SELECT Name, Value, SensorType FROM Sensor")
        for item in items:
            sensor_type = str(getattr(item, 'SensorType', '')).lower()
            if sensor_type != 'temperature':
                continue
            value = getattr(item, 'Value', None)
            if value is None:
                continue
            temps.append(float(value))
    except Exception:
        return []
    return temps


def _parse_timespan(value):
    if not value:
        return 0
    text = str(value)
    # Formats: "DD.HH:MM:SS" or "HH:MM:SS"
    try:
        if '.' in text:
            days_part, time_part = text.split('.', 1)
            days = int(days_part)
        else:
            days = 0
            time_part = text
        parts = time_part.split(':')
        if len(parts) != 3:
            return 0
        hours, minutes, seconds = [int(p) for p in parts]
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0


def collect_hyperv_vm_status():
    command = (
        "Get-VM | Select-Object Name, State, CPUUsage, MemoryAssigned, MemoryDemand, Uptime | "
        "ConvertTo-Json -Compress"
    )
    try:
        output = _run_cmd(["powershell", "-NoProfile", "-Command", command]).decode(errors='ignore')
        if not output.strip():
            return []
        data = json.loads(output)
    except Exception as e:
        logging.warning(f"Failed to collect Hyper-V status: {e}")
        return []

    if isinstance(data, dict):
        items = [data]
    else:
        items = data

    vms = []
    for item in items:
        name = item.get('Name')
        if not name:
            continue
        status = item.get('State', '') or 'unknown'
        cpu_usage = item.get('CPUUsage', None)
        mem_assigned = item.get('MemoryAssigned', 0) or 0
        mem_demand = item.get('MemoryDemand', 0) or 0
        mem_usage = None
        if mem_assigned > 0:
            mem_usage = (mem_demand / mem_assigned) * 100.0
        uptime = _parse_timespan(item.get('Uptime'))
        vms.append({
            'name': name,
            'status': status,
            'cpu_usage': cpu_usage,
            'memory_usage': mem_usage,
            'uptime_seconds': uptime,
        })
    return vms


def main():
    logging.info("Agent started")
    config = load_config()
    if not config:
        return

    try:
        API_BASE = config['DEFAULT']['ApiUrl']
        TOKEN = config['DEFAULT']['Token']
        CONFIG_SERIAL = config['DEFAULT']['SerialNumber']
        LOOP_INTERVAL = int(config['DEFAULT'].get('LoopInterval', '5'))
        METRICS_BATCH_INTERVAL = int(config['DEFAULT'].get('MetricsBatchInterval', '60'))
        VM_SYNC_INTERVAL = int(config['DEFAULT'].get('VmSyncInterval', '60'))
        RETENTION_DAYS = int(config['DEFAULT'].get('RetentionDays', '365'))
        PING_TARGET = config['DEFAULT'].get('PingTarget', '').strip() or None
        STORCLI_PATH = _resolve_storcli_path(config['DEFAULT'].get('StorcliPath', '').strip())
        METRICS_QUEUE_MAX = int(config['DEFAULT'].get('MetricsQueueMax', '5000'))
        METRICS_DEBUG = config['DEFAULT'].get('MetricsDebug', '0').strip().lower() in ('1', 'true', 'yes', 'on')

        if CONFIG_SERIAL.upper() == 'AUTO':
            SERIAL_NUMBER = get_serial_number()
            logging.info(f"Auto-detected Serial: {SERIAL_NUMBER}")
        else:
            SERIAL_NUMBER = CONFIG_SERIAL
    except KeyError as e:
        logging.error(f"Missing config key: {e}")
        return

    if METRICS_DEBUG:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Metrics debug logging enabled.")

    _log_storcli_info(STORCLI_PATH)

    _check_ping_target(PING_TARGET)

    send_agent_status(API_BASE, TOKEN, SERIAL_NUMBER, 'ok', 'agent started')

    collector = MetricCollector(ping_target=PING_TARGET, storcli_path=STORCLI_PATH)
    if STORCLI_PATH and METRICS_DEBUG:
        try:
            preview = collector._collect_storcli_all()
            if not preview:
                logging.warning("StorCLI preview returned no metrics.")
            else:
                logging.debug(f"StorCLI preview metrics: {len(preview)}")
        except Exception as e:
            logging.warning(f"StorCLI preview failed: {e}")

    # План сборов
    tasks = [
        ('cpu_total', 60, collector.collect_cpu_total),
        ('cpu_kernel', 300, collector.collect_cpu_kernel),
        ('cpu_interrupts', 300, collector.collect_cpu_interrupts),
        ('mem_usage', 60, collector.collect_mem_usage),
        ('swap_usage', 300, collector.collect_swap_usage),
        ('disk_usage', 600, collector.collect_disk_usage),
        ('disk_io', 60, collector.collect_disk_io),
        ('storcli_errors', 3600, collector.collect_storcli_errors),
        ('storcli_temp', 600, collector.collect_storcli_temperature),
        ('net', 60, collector.collect_network),
        ('ping', 60, collector.collect_ping),
        ('uptime', 600, collector.collect_uptime),
        ('process_count', 300, collector.collect_process_count),
        ('system_temperature', 300, collector.collect_system_temperature),
    ]

    last_run = {name: 0 for name, _, _ in tasks}
    metrics_queue = []
    last_metrics_flush = 0
    last_retention_sync = 0
    last_vm_sync = 0
    last_ping_check = 0
    metrics_paused = False
    next_probe_at = 0
    ERROR_PAUSE_SECONDS = int(config['DEFAULT'].get('ErrorPauseSeconds', '300'))

    while True:
        now = time.time()
        try:
            if (now - last_ping_check) >= 60:
                _check_ping_target(PING_TARGET)
                last_ping_check = now

            # Сбор метрик по расписанию (может быть приостановлен при ошибке отправки)
            if metrics_paused:
                if next_probe_at and now >= next_probe_at:
                    probe_metric = _metric('uptime_seconds', time.time() - psutil.boot_time(), 'sec')
                    device_info = get_device_info()
                    if send_metrics_batch(API_BASE, TOKEN, SERIAL_NUMBER, [probe_metric], None, device_info=device_info):
                        metrics_paused = False
                        next_probe_at = 0
                        send_agent_status(API_BASE, TOKEN, SERIAL_NUMBER, 'ok', 'metrics resumed')
                        last_metrics_flush = now
                        logging.info("Metrics resumed after successful probe send.")
                    else:
                        send_agent_status(API_BASE, TOKEN, SERIAL_NUMBER, 'error', 'metrics ingest failed')
                        next_probe_at = now + ERROR_PAUSE_SECONDS
                # Пока пауза активна, не собираем метрики
            else:
                for name, interval, func in tasks:
                    if (now - last_run[name]) >= interval:
                        try:
                            metrics = func() or []
                            valid = [m for m in metrics if m]
                            if METRICS_DEBUG and valid:
                                codes = [m.get('code') for m in valid]
                                logging.debug(f"Collected {len(valid)} metrics from {name}: {codes}")
                            metrics_queue.extend(valid)
                        except Exception as e:
                            logging.warning(f"Metric task '{name}' failed: {e}")
                        last_run[name] = now

            # Отправка метрик пачкой
            if metrics_queue and (now - last_metrics_flush) >= METRICS_BATCH_INTERVAL:
                retention = None
                if (now - last_retention_sync) >= 86400:
                    retention = RETENTION_DAYS
                device_info = get_device_info()
                if send_metrics_batch(API_BASE, TOKEN, SERIAL_NUMBER, metrics_queue, retention, device_info=device_info):
                    metrics_queue = []
                    last_metrics_flush = now
                    if retention is not None:
                        last_retention_sync = now
                    send_agent_status(API_BASE, TOKEN, SERIAL_NUMBER, 'ok', '')
                else:
                    send_agent_status(API_BASE, TOKEN, SERIAL_NUMBER, 'error', 'metrics ingest failed')
                    metrics_queue = []
                    metrics_paused = True
                    next_probe_at = now + ERROR_PAUSE_SECONDS
                    logging.warning(f"Metrics paused after send error. Retry in {ERROR_PAUSE_SECONDS}s.")

            # Отправка статуса ВМ
            if VM_SYNC_INTERVAL > 0 and (now - last_vm_sync) >= VM_SYNC_INTERVAL:
                vms = collect_hyperv_vm_status()
                if vms:
                    send_vm_status(API_BASE, TOKEN, SERIAL_NUMBER, vms)
                last_vm_sync = now

        except Exception as e:
            logging.error(f"Main loop error: {e}")

        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()
