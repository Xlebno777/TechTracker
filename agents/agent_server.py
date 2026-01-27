import time
import psutil
import requests
import configparser
import logging
import sys
import os
import subprocess
import win32print
import win32com.client
import re

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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_serial_number():
    """Автоматически получает серийный номер из Windows"""
    try:
        result = subprocess.check_output("wmic bios get serialnumber", shell=True).decode()
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

# --- ФУНКЦИИ МЕТРИК ---

def send_metric(api_base, token, serial, metric_type, value):
    if not api_base.endswith('/'):
        api_base += '/'

    url = f"{api_base}metrics/"
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'serial_number': serial, 
        'metric_type': metric_type,
        'value': round(float(value), 2)
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code != 201:
            logging.error(f"Failed metric {metric_type}: {response.status_code} {response.text}")
    except Exception as e:
        logging.error(f"Connection error (metric): {e}")

IP_RE = re.compile(r'(?:\d{1,3}\.){3}\d{1,3}')


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


def get_printer_ip_map():
    ip_map = {}
    for printer in collect_printers():
        if printer.get('name') and printer.get('ip_address'):
            ip_map[printer['name']] = printer['ip_address']
    return ip_map


def send_printer_sync(api_base, token, printers):
    if not printers:
        return

    if not api_base.endswith('/'):
        api_base += '/'

    url = f"{api_base}devices/sync_printers/"
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


# --- MAIN ---

def main():
    logging.info("Agent started")
    config = load_config()
    if not config:
        return

    try:
        # Убедись, что ApiUrl в конфиге заканчивается на /api/
        # Пример: http://192.168.1.10:8000/api/
        API_BASE = config['DEFAULT']['ApiUrl'] 
        if not API_BASE.endswith('/'):
            API_BASE += '/'
            
        TOKEN = config['DEFAULT']['Token']
        CONFIG_SERIAL = config['DEFAULT']['SerialNumber']
        INTERVAL = int(config['DEFAULT']['Interval'])
        PRINTER_SYNC_INTERVAL = int(config['DEFAULT'].get('PrinterSyncInterval', '0'))
        
        if CONFIG_SERIAL.upper() == 'AUTO':
            SERIAL_NUMBER = get_serial_number()
            logging.info(f"Auto-detected Serial: {SERIAL_NUMBER}")
        else:
            SERIAL_NUMBER = CONFIG_SERIAL
            
    except KeyError as e:
        logging.error(f"Missing config key: {e}")
        return

    # Первичная синхронизация списка принтеров
    last_printer_sync = 0
    try:
        printers = collect_printers()
        send_printer_sync(API_BASE, TOKEN, printers)
        last_printer_sync = time.time()
    except Exception as e:
        logging.error(f"Initial printer sync failed: {e}")

    while True:
        try:
            # 0. Периодическая синхронизация принтеров (если включено)
            if PRINTER_SYNC_INTERVAL > 0 and (time.time() - last_printer_sync) >= PRINTER_SYNC_INTERVAL:
                printers = collect_printers()
                send_printer_sync(API_BASE, TOKEN, printers)
                last_printer_sync = time.time()

            # 1. Отправка метрик (CPU, RAM, Disk)
            cpu = psutil.cpu_percent(interval=1)
            send_metric(API_BASE, TOKEN, SERIAL_NUMBER, 'cpu_load', cpu)

            ram = psutil.virtual_memory().percent
            send_metric(API_BASE, TOKEN, SERIAL_NUMBER, 'memory_usage', ram)

            disk = psutil.disk_usage('C:\\').percent
            send_metric(API_BASE, TOKEN, SERIAL_NUMBER, 'disk_usage', disk)

            time.sleep(INTERVAL)

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
def _dump_event_xml(record_id, xml_text):
    try:
        sample_path = os.path.join(application_path, 'print_event_samples.xml')
        with open(sample_path, 'a', encoding='utf-8') as f:
            f.write(f"\n<!-- record_id={record_id} -->\n")
            f.write(xml_text)
            f.write("\n")
    except Exception as e:
        logging.warning(f"Failed to dump event XML: {e}")
