import time
import requests
import configparser
import logging
import sys
import os
import subprocess
import re
from datetime import datetime, timezone, timedelta

import pythoncom
import wmi
import win32print
import win32com.client

# Пути
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(application_path, 'print_client.ini')
log_path = os.path.join(application_path, 'print_client.log')

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

IP_RE = re.compile(r'(?:\d{1,3}\.){3}\d{1,3}')


def load_config():
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        logging.error("print_client.ini not found!")
        return None
    config.read(config_path)
    return config


def get_serial_number():
    """Автоматически получает серийный номер из Windows"""
    try:
        result = subprocess.check_output("wmic bios get serialnumber", shell=True).decode()
        serial = result.split('\n')[1].strip()
        return serial
    except Exception as e:
        logging.error(f"Failed to auto-detect serial number: {e}")
        return "UNKNOWN"


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


def get_printer_ip_map():
    printers = {}
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
            if name and ip:
                printers[name] = ip
        except Exception as e:
            logging.warning(f"Failed to read printer info: {e}")
            continue

    return printers


def parse_wmi_datetime(value):
    """
    Формат WMI: yyyymmddHHMMSS.mmmmmmsUUU
    Пример: 20260127112535.949000+180
    """
    if not value:
        return None
    try:
        base = value[:14]
        micro = value[15:21]
        sign = value[21]
        offset = value[22:25]
        dt = datetime.strptime(base, "%Y%m%d%H%M%S").replace(microsecond=int(micro))
        tz_minutes = int(offset)
        if sign == '-':
            tz_minutes = -tz_minutes
        tz = timezone(timedelta(minutes=tz_minutes))
        return dt.replace(tzinfo=tz).isoformat()
    except Exception:
        return None


def send_print_job(api_base, token, payload):
    if not api_base.endswith('/'):
        api_base += '/'
    url = f"{api_base}printjob/"
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 201:
            logging.info(f"Sent print job: {payload.get('document_name')} ({payload.get('pages')} p.)")
            return True
        logging.error(f"Failed print job: {response.status_code} {response.text}")
        return False
    except Exception as e:
        logging.error(f"Connection error (print): {e}")
        return False


def monitor_print_jobs(api_base, token, serial, refresh_sec, send_serial):
    printer_ip_map = {}
    last_refresh = 0

    def refresh_map_if_needed():
        nonlocal printer_ip_map, last_refresh
        if time.time() - last_refresh >= refresh_sec:
            printer_ip_map = get_printer_ip_map()
            last_refresh = time.time()

    while True:
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            watcher = c.Win32_PrintJob.watch_for(
                notification_type="Creation",
                delay_secs=1
            )

            logging.info("WMI print monitor started")

            while True:
                job = watcher()
                if not job:
                    continue

                refresh_map_if_needed()

                document = job.Document or "Unknown"
                if 'ipp' in document.lower() or 'http' in document.lower():
                    continue

                printer_name = job.Name.split(',')[0].strip() if job.Name else "Unknown"
                user_name = getattr(job, 'Owner', None) or "Unknown"
                pages = getattr(job, 'TotalPages', None) or 0
                timestamp = parse_wmi_datetime(getattr(job, 'TimeSubmitted', None))

                payload = {
                    'user_name': user_name,
                    'document_name': document,
                    'pages': int(pages) if str(pages).isdigit() else 0,
                    'printer_name': printer_name
                }

                printer_ip = printer_ip_map.get(printer_name)
                if printer_ip:
                    payload['printer_ip'] = printer_ip

                if timestamp:
                    payload['timestamp'] = timestamp

                if send_serial and serial:
                    payload['serial_number'] = serial

                send_print_job(api_base, token, payload)

        except pythoncom.com_error as e:
            logging.error(f"WMI error: {e}")
            time.sleep(5)
        except Exception as e:
            logging.error(f"Monitor error: {e}")
            time.sleep(5)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def main():
    logging.info("Print client started")
    config = load_config()
    if not config:
        return

    try:
        API_BASE = config['DEFAULT']['ApiUrl']
        if not API_BASE.endswith('/'):
            API_BASE += '/'

        TOKEN = config['DEFAULT']['Token']
        SEND_SERIAL = config['DEFAULT'].get('SendSerial', '0').lower() in ('1', 'true', 'yes')
        CONFIG_SERIAL = config['DEFAULT'].get('SerialNumber', '')
        REFRESH_SEC = int(config['DEFAULT'].get('PrinterMapRefreshSec', '300'))

        if SEND_SERIAL:
            if CONFIG_SERIAL.upper() == 'AUTO':
                SERIAL_NUMBER = get_serial_number()
            else:
                SERIAL_NUMBER = CONFIG_SERIAL
        else:
            SERIAL_NUMBER = ''

    except KeyError as e:
        logging.error(f"Missing config key: {e}")
        return

    monitor_print_jobs(API_BASE, TOKEN, SERIAL_NUMBER, REFRESH_SEC, SEND_SERIAL)


if __name__ == "__main__":
    main()
