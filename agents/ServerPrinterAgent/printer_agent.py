import configparser
import logging
import os
import sys
import time
import re

import requests
import win32print
import win32com.client

# Paths
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(application_path, 'printer_agent.ini')
log_path = os.path.join(application_path, 'printer_agent.log')

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

IP_RE = re.compile(r'(?:\d{1,3}\.){3}\d{1,3}')
DEFAULT_EXCLUDE = [
    'adobe pdf',
    'microsoft print to pdf',
    'microsoft xps document writer',
]


def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        logging.error("printer_agent.ini not found!")
        return None
    config.read(config_path)
    return config


def _api_url(base, path):
    if not base.endswith('/'):
        base += '/'
    return f"{base}{path}"


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


def collect_printers(excluded):
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
            if name and any(ex in name.lower() for ex in excluded):
                continue

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


def _parse_excluded(raw):
    if not raw:
        return list(DEFAULT_EXCLUDE)
    parts = [p.strip().lower() for p in raw.split(',') if p.strip()]
    return parts or list(DEFAULT_EXCLUDE)


def main():
    logging.info("ServerPrinterAgent started")
    config = load_config()
    if not config:
        return

    try:
        API_BASE = config['DEFAULT']['ApiUrl']
        TOKEN = config['DEFAULT']['Token']
        INTERVAL = int(config['DEFAULT'].get('SyncInterval', '300'))
        EXCLUDE_RAW = config['DEFAULT'].get('ExcludePrinters', '')
        excluded = _parse_excluded(EXCLUDE_RAW)
    except KeyError as e:
        logging.error(f"Missing config key: {e}")
        return

    while True:
        try:
            printers = collect_printers(excluded)
            send_printer_sync(API_BASE, TOKEN, printers)
        except Exception as e:
            logging.error(f"Printer sync loop error: {e}")

        time.sleep(INTERVAL)


if __name__ == '__main__':
    main()
