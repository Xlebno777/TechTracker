import time
import psutil
import requests
import configparser
import logging
import sys
import os
import subprocess
import win32evtlog # Требует pip install pywin32
import win32print
import win32com.client
import re
import xml.etree.ElementTree as ET

# Настройка путей
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(application_path, 'config.ini')
log_path = os.path.join(application_path, 'agent.log')
last_print_record_path = os.path.join(application_path, 'last_print.dat')

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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

# --- ФУНКЦИИ ПЕЧАТИ ---

def get_last_processed_record_id():
    """Читает ID последней обработанной записи печати из файла"""
    if not os.path.exists(last_print_record_path):
        return 0
    try:
        with open(last_print_record_path, 'r') as f:
            return int(f.read().strip())
    except:
        return 0

def save_last_processed_record_id(record_id):
    """Сохраняет ID последней записи"""
    try:
        with open(last_print_record_path, 'w') as f:
            f.write(str(record_id))
    except Exception as e:
        logging.error(f"Failed to save last print record: {e}")

def send_print_job(api_base, token, serial, user, doc, pages, printer):
    if not api_base.endswith('/'):
        api_base += '/'

    url = f"{api_base}printjob/" # Предполагается, что ты создал этот эндпоинт
    headers = {
        'Authorization': f'Token {token}',
        'Content-Type': 'application/json'
    }
    printer_name = printer.get('name') if isinstance(printer, dict) else printer
    payload = {
        'serial_number': serial,
        'user_name': user,
        'document_name': doc,
        'pages': pages,
        'printer_name': printer_name
    }
    if isinstance(printer, dict) and printer.get('ip_address'):
        payload['printer_ip'] = printer.get('ip_address')

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 201:
            logging.info(f"Sent print job: {doc} ({pages} p.)")
            return True
        else:
            logging.error(f"Failed print job: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logging.error(f"Connection error (print): {e}")
        return False

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


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _parse_event_xml(xml_text, debug=False):
    """
    Парсит XML события (EvtRenderEventXml) и возвращает dict:
    {event_id, record_id, data_map, data_list}
    """
    try:
        root = ET.fromstring(xml_text)
    except Exception as e:
        if debug:
            logging.warning(f"Failed to parse event XML: {e}")
        return None

    # Namespaces are usually present; ignore them via tag ending
    def _find_first(tag_endswith):
        for elem in root.iter():
            if elem.tag.endswith(tag_endswith):
                return elem
        return None

    event_id = None
    record_id = None

    event_id_elem = _find_first('EventID')
    if event_id_elem is not None and event_id_elem.text:
        event_id = _safe_int(event_id_elem.text, None)

    record_id_elem = _find_first('EventRecordID')
    if record_id_elem is not None and record_id_elem.text:
        record_id = _safe_int(record_id_elem.text, None)

    data_map = {}
    data_list = []
    for data_elem in root.iter():
        if not data_elem.tag.endswith('Data'):
            continue
        name = data_elem.attrib.get('Name')
        value = data_elem.text or ''
        data_list.append(value)
        if name:
            data_map[name] = value

    return {
        'event_id': event_id,
        'record_id': record_id,
        'data_map': data_map,
        'data_list': data_list,
    }


def _extract_print_from_xml(xml_text, debug=False):
    """
    Парсит событие печати из XML (EvtQuery).
    Пытается по именованным полям, иначе по позициям.
    """
    parsed = _parse_event_xml(xml_text, debug=debug)
    if not parsed:
        return None

    event_id = parsed['event_id']
    record_id = parsed['record_id']
    data_map = parsed['data_map']
    data_list = parsed['data_list']

    # Именованные поля (если есть)
    doc = data_map.get('DocumentName') or data_map.get('Param2')
    user = data_map.get('UserName') or data_map.get('Param3')
    printer = data_map.get('PrinterName') or data_map.get('Param5')
    pages = data_map.get('Pages') or data_map.get('Param8')

    # Фоллбек по позициям
    if not doc and len(data_list) > 1:
        doc = data_list[1]
    if not user and len(data_list) > 2:
        user = data_list[2]
    if not printer and len(data_list) > 4:
        printer = data_list[4]
    if not pages and len(data_list) > 7:
        pages = data_list[7]

    if not doc or not user or not printer:
        if debug:
            logging.warning(f"XML print event missing fields: record={record_id} data={data_map or data_list}")
        return None

    return {
        'event_id': event_id,
        'record_id': record_id,
        'doc': doc,
        'user': user,
        'printer': printer,
        'pages': _safe_int(pages, 0),
    }


def _read_print_events_new_api(log_type, last_record_id, debug=False):
    """Читает события через EvtQuery (новый API) с несколькими попытками."""
    attempts = [
        # (flags, query)
        (win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection, "*[System[(EventID=307 or EventID=10010)]]"),
        (win32evtlog.EvtQueryChannelPath, "*[System[(EventID=307 or EventID=10010)]]"),
        (win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection, "*"),
        (win32evtlog.EvtQueryChannelPath, "*"),
    ]

    for flags, query in attempts:
        try:
            handle = win32evtlog.EvtQuery(log_type, flags, query)
            events = []
            while True:
                try:
                    batch = win32evtlog.EvtNext(handle, 16, 0)
                except Exception as e:
                    # 259 = no more items
                    winerr = getattr(e, 'winerror', None)
                    if winerr == 259:
                        break
                    if debug:
                        logging.warning(f"EvtNext failed (flags={flags}, query={query}): {e}")
                    raise

                if not batch:
                    break

                for evt_handle in batch:
                    try:
                        xml_text = win32evtlog.EvtRender(evt_handle, win32evtlog.EvtRenderEventXml)
                    finally:
                        try:
                            win32evtlog.EvtClose(evt_handle)
                        except Exception:
                            pass

                    parsed = _extract_print_from_xml(xml_text, debug=debug)
                    if not parsed:
                        continue

                    record_id = parsed.get('record_id')
                    if record_id is None:
                        continue
                    if record_id <= last_record_id:
                        return events

                    # Если запрос не фильтрует по 307, фильтруем здесь
                    if query == "*" and parsed.get('event_id') not in (307, 10010):
                        continue
                    events.append(parsed)
            return events
        except Exception as e:
            if debug:
                logging.warning(f"EvtQuery attempt failed (flags={flags}, query={query}): {e}")
            continue

    if debug:
        logging.warning("EvtQuery not available or failed after all attempts")
    return None


def check_print_logs(api_base, token, serial, debug=False):
    """Читает журнал Windows и отправляет новые задания"""
    log_type = 'Microsoft-Windows-PrintService/Operational'

    printer_ip_map = get_printer_ip_map()
    
    last_record_id = get_last_processed_record_id()
    new_last_record_id = last_record_id
    
    try:
        # Новый API (EvtQuery + EvtRender XML)
        events = _read_print_events_new_api(log_type, last_record_id, debug=debug)
        using_new_api = events is not None

        if not using_new_api:
            logging.warning("EvtQuery not available or failed after all attempts")
            return
        if debug:
            newest = events[0].get('record_id') if events else None
            logging.info(f"Print log read (EvtQuery). last_record_id={last_record_id}, newest_record={newest}")
        
        # Собираем новые события в список, чтобы отправить их в хронологическом порядке
        new_jobs = []

        while events:
            for event in events:
                record_number = event.get('record_id')
                event_id = event.get('event_id')
                if record_number is not None and record_number <= last_record_id:
                    break
                if debug:
                    logging.info(
                        f"Event record={record_number} event_id={event_id} "
                        f"doc={event.get('doc')} user={event.get('user')} printer={event.get('printer')}"
                    )
                if event_id in (307, 10010):
                    event['printer_ip'] = printer_ip_map.get(event['printer'])
                    new_jobs.append(event)

            last_rec = events[-1].get('record_id') if events else None
            if events and last_rec is not None and last_rec <= last_record_id:
                break # Прерываем внешний цикл while
            
            if using_new_api:
                # EvtQuery уже вернул пачку; повторно не читаем, чтобы не дублировать
                break

        # Отправляем события (разворачиваем, чтобы старые ушли первыми)
        if new_jobs:
            if debug:
                logging.info(f"New print jobs found: {len(new_jobs)}")
            for job in reversed(new_jobs):
                payload_printer = {
                    'name': job['printer'],
                    'ip_address': job.get('printer_ip')
                }
                success = send_print_job(
                    api_base, token, serial,
                    job['user'], job['doc'], job['pages'], payload_printer
                )
                # Если отправилось успешно - обновляем "курсор"
                if success:
                    new_last_record_id = job['record_id']
            
            # Сохраняем последний успешный ID
            if new_last_record_id > last_record_id:
                save_last_processed_record_id(new_last_record_id)
        elif debug:
            logging.info("No new print jobs found.")

    except Exception as e:
        # Часто бывает, что журнал отключен
        if "The system cannot find the file specified" in str(e):
            logging.warning("PrintService log not found. Enable it in Event Viewer!")
        else:
            logging.error(f"Log check error: {e}")

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
        PRINT_DEBUG = config['DEFAULT'].get('PrintDebug', '0').lower() in ('1', 'true', 'yes')
        
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

            # 2. Проверка печати
            check_print_logs(API_BASE, TOKEN, SERIAL_NUMBER, debug=PRINT_DEBUG)

            time.sleep(INTERVAL)

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
