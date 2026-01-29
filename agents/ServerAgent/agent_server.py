import configparser
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import psutil
import requests
import win32com.client
import win32print

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

IP_RE = re.compile(r'(?:\d{1,3}\.){3}\d{1,3}')


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_serial_number():
    """Автоматически получает серийный номер из Windows."""
    try:
        result = subprocess.check_output("wmic bios get serialnumber", shell=True).decode(errors='ignore')
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


def _detect_smartctl(config_value):
    if config_value:
        return config_value
    try:
        subprocess.check_output(["where", "smartctl"], stderr=subprocess.STDOUT)
        return "smartctl"
    except Exception:
        return None


def _api_url(base, path):
    if not base.endswith('/'):
        base += '/'
    return f"{base}{path}"


def send_metrics_batch(api_base, token, serial, metrics, retention_days=None):
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


def _extract_ip(value):
    if not value:
        return None
    match = IP_RE.search(value)
    return match.group(0) if match else None


def _get_tcpip_ports():
    try:
        locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        service = locator.ConnectServer(".", "root\\cimv2")
        ports = service.ExecQuery("SELECT Name, HostAddress FROM Win32_TCPIPPrinterPort")
        return {p.Name: p.HostAddress for p in ports if p.Name}
    except Exception as e:
        logging.warning(f"Failed to read TCP/IP ports: {e}")
        return {}


def collect_printers():
    printers = []
    ports = _get_tcpip_ports()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS

    try:
        items = win32print.EnumPrinters(flags)
    except Exception as e:
        logging.error(f"EnumPrinters error: {e}")
        return printers

    for item in items:
        try:
            name = item[2]
            handle = win32print.OpenPrinter(name)
            info = win32print.GetPrinter(handle, 2)
            win32print.ClosePrinter(handle)

            port_name = info.get('pPortName', '') if isinstance(info, dict) else ''
            ip = ports.get(port_name) or _extract_ip(port_name) or _extract_ip(name)

            printers.append({
                'name': name,
                'ip_address': ip,
                'port_name': port_name
            })
        except Exception as e:
            logging.warning(f"Failed to read printer info: {e}")
            continue

    return printers


def send_printer_sync(api_base, token, printers):
    if not printers:
        return

    url = _api_url(api_base, 'devices/sync_printers/')
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    payload = {'printers': printers}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            logging.error(f"Failed printer sync: {response.status_code} {response.text}")
        else:
            logging.info(f"Printer sync ok: {response.text}")
    except Exception as e:
        logging.error(f"Connection error (printer sync): {e}")


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
    def __init__(self, ping_target=None, smartctl_path=None):
        self.last_cpu_times = None
        self.last_cpu_time_ts = None
        self.last_interrupts = None
        self.last_interrupts_ts = None
        self.last_disk_io = None
        self.last_disk_io_ts = None
        self.last_net_io = None
        self.last_net_io_ts = None
        self.ping_target = ping_target
        self.smartctl_path = smartctl_path
        self._last_smart = None
        self._last_smart_ts = None
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
            output = subprocess.check_output(
                ["ping", "-n", "1", self.ping_target],
                stderr=subprocess.STDOUT
            ).decode(errors='ignore')
            match = re.search(r'Average = (\d+)ms', output)
            if not match:
                match = re.search(r'Среднее = (\d+)мс', output)
            if match:
                return [_metric('ping_latency_gateway', int(match.group(1)), 'ms')]
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
            return []
        if not temps:
            return []
        return [_metric('system_temperature', max(temps), 'C')]

    def _collect_smart_all(self):
        if not self.smartctl_path:
            return []
        now = time.time()
        if self._last_smart and self._last_smart_ts and (now - self._last_smart_ts) < 30:
            return self._last_smart

        devices = _smartctl_scan(self.smartctl_path)
        metrics = []
        for device in devices:
            attrs = _smartctl_attributes(self.smartctl_path, device)
            if not attrs:
                continue
            if attrs.get('reallocated') is not None:
                metrics.append(_metric(
                    'smart_reallocated_sectors',
                    attrs['reallocated'],
                    'count',
                    {'disk': device}
                ))
            if attrs.get('temperature') is not None:
                metrics.append(_metric(
                    'smart_temperature',
                    attrs['temperature'],
                    'C',
                    {'disk': device}
                ))
        self._last_smart = [m for m in metrics if m]
        self._last_smart_ts = now
        return self._last_smart

    def collect_smart_reallocated(self):
        metrics = self._collect_smart_all()
        return [m for m in metrics if m and m.get('code') == 'smart_reallocated_sectors']

    def collect_smart_temperature(self):
        metrics = self._collect_smart_all()
        return [m for m in metrics if m and m.get('code') == 'smart_temperature']


def _smartctl_scan(smartctl_path):
    try:
        output = subprocess.check_output([smartctl_path, "--scan"], stderr=subprocess.STDOUT)
        lines = output.decode(errors='ignore').splitlines()
    except Exception as e:
        logging.warning(f"smartctl scan failed: {e}")
        return []
    devices = []
    for line in lines:
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if parts:
            devices.append(parts[0])
    return devices


def _smartctl_attributes(smartctl_path, device):
    try:
        output = subprocess.check_output([smartctl_path, "-A", "-j", device], stderr=subprocess.STDOUT)
        data = json.loads(output.decode(errors='ignore'))
        table = data.get('ata_smart_attributes', {}).get('table', [])
        reallocated = None
        temperature = None
        for item in table:
            name = (item.get('name') or '').lower()
            raw = item.get('raw', {}).get('value')
            if name == 'reallocated_sector_ct':
                reallocated = raw
            if name in ('temperature_celsius', 'temperature_internal', 'airflow_temperature_cel'):
                temperature = raw
        return {'reallocated': reallocated, 'temperature': temperature}
    except Exception:
        return _smartctl_attributes_text(smartctl_path, device)


def _smartctl_attributes_text(smartctl_path, device):
    try:
        output = subprocess.check_output([smartctl_path, "-A", device], stderr=subprocess.STDOUT)
        lines = output.decode(errors='ignore').splitlines()
    except Exception as e:
        logging.warning(f"smartctl read failed: {e}")
        return None

    reallocated = None
    temperature = None
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[0].isdigit():
            attr_id = parts[0]
            name = parts[1]
            raw_value = parts[-1]
            if attr_id == '5' or name.lower() == 'reallocated_sector_ct':
                try:
                    reallocated = int(raw_value)
                except ValueError:
                    pass
            if attr_id in ('190', '194') or 'temperature' in name.lower():
                try:
                    temperature = float(raw_value)
                except ValueError:
                    pass
    return {'reallocated': reallocated, 'temperature': temperature}


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
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command],
            stderr=subprocess.STDOUT
        ).decode(errors='ignore')
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
        PRINTER_SYNC_INTERVAL = int(config['DEFAULT'].get('PrinterSyncInterval', '0'))
        VM_SYNC_INTERVAL = int(config['DEFAULT'].get('VmSyncInterval', '60'))
        RETENTION_DAYS = int(config['DEFAULT'].get('RetentionDays', '365'))
        PING_TARGET = config['DEFAULT'].get('PingTarget', '').strip() or None
        SMARTCTL_PATH = _detect_smartctl(config['DEFAULT'].get('SmartctlPath', '').strip())
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

    collector = MetricCollector(ping_target=PING_TARGET, smartctl_path=SMARTCTL_PATH)

    # План сборов
    tasks = [
        ('cpu_total', 60, collector.collect_cpu_total),
        ('cpu_kernel', 300, collector.collect_cpu_kernel),
        ('cpu_interrupts', 300, collector.collect_cpu_interrupts),
        ('mem_usage', 60, collector.collect_mem_usage),
        ('swap_usage', 300, collector.collect_swap_usage),
        ('disk_usage', 600, collector.collect_disk_usage),
        ('disk_io', 60, collector.collect_disk_io),
        ('smart_reallocated', 3600, collector.collect_smart_reallocated),
        ('smart_temp', 600, collector.collect_smart_temperature),
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
    last_printer_sync = 0

    # Первичная синхронизация принтеров
    if PRINTER_SYNC_INTERVAL > 0:
        try:
            printers = collect_printers()
            send_printer_sync(API_BASE, TOKEN, printers)
            last_printer_sync = time.time()
        except Exception as e:
            logging.error(f"Initial printer sync failed: {e}")

    while True:
        now = time.time()
        try:
            # Периодическая синхронизация принтеров
            if PRINTER_SYNC_INTERVAL > 0 and (now - last_printer_sync) >= PRINTER_SYNC_INTERVAL:
                printers = collect_printers()
                send_printer_sync(API_BASE, TOKEN, printers)
                last_printer_sync = now

            # Сбор метрик по расписанию
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
                if send_metrics_batch(API_BASE, TOKEN, SERIAL_NUMBER, metrics_queue, retention):
                    metrics_queue = []
                    last_metrics_flush = now
                    if retention is not None:
                        last_retention_sync = now
                else:
                    if len(metrics_queue) > METRICS_QUEUE_MAX:
                        metrics_queue = metrics_queue[-METRICS_QUEUE_MAX:]
                        logging.warning("Metrics queue trimmed due to size limit.")

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
