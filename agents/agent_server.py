import time
import psutil
import requests
import configparser
import logging
import sys
import os
import subprocess
import win32evtlog # Требует pip install pywin32

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
    payload = {
        'serial_number': serial,
        'user_name': user,
        'document_name': doc,
        'pages': pages,
        'printer_name': printer
    }

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

def check_print_logs(api_base, token, serial):
    """Читает журнал Windows и отправляет новые задания"""
    server = 'localhost'
    log_type = 'Microsoft-Windows-PrintService/Operational'
    
    last_record_id = get_last_processed_record_id()
    new_last_record_id = last_record_id
    
    try:
        hand = win32evtlog.OpenEventLog(server, log_type)
        # Читаем журнал в обратном порядке (от новых к старым), чтобы быстрее найти свежие
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        
        # Собираем новые события в список, чтобы отправить их в хронологическом порядке
        new_jobs = []

        while events:
            for event in events:
                # Если дошли до уже обработанной записи - останавливаемся
                if event.RecordNumber <= last_record_id:
                    break
                
                # Event ID 307 = Document Printed
                if event.EventID == 307:
                    try:
                        # Структура StringInserts для ID 307:
                        # [0]Id, [1]DocName, [2]User, [3]PC, [4]Printer, [5]Port, [6]Size, [7]Pages
                        data = event.StringInserts
                        if data and len(data) >= 8:
                            job = {
                                'doc': data[1],
                                'user': data[2],
                                'printer': data[4],
                                'pages': int(data[7]),
                                'record_id': event.RecordNumber
                            }
                            new_jobs.append(job)
                    except Exception as parse_err:
                        logging.error(f"Error parsing event {event.RecordNumber}: {parse_err}")

            if events and events[-1].RecordNumber <= last_record_id:
                break # Прерываем внешний цикл while
            
            events = win32evtlog.ReadEventLog(hand, flags, 0)

        win32evtlog.CloseEventLog(hand)

        # Отправляем события (разворачиваем, чтобы старые ушли первыми)
        if new_jobs:
            for job in reversed(new_jobs):
                success = send_print_job(
                    api_base, token, serial, 
                    job['user'], job['doc'], job['pages'], job['printer']
                )
                # Если отправилось успешно - обновляем "курсор"
                if success:
                    new_last_record_id = job['record_id']
            
            # Сохраняем последний успешный ID
            if new_last_record_id > last_record_id:
                save_last_processed_record_id(new_last_record_id)

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
        
        if CONFIG_SERIAL.upper() == 'AUTO':
            SERIAL_NUMBER = get_serial_number()
            logging.info(f"Auto-detected Serial: {SERIAL_NUMBER}")
        else:
            SERIAL_NUMBER = CONFIG_SERIAL
            
    except KeyError as e:
        logging.error(f"Missing config key: {e}")
        return

    while True:
        try:
            # 1. Отправка метрик (CPU, RAM, Disk)
            cpu = psutil.cpu_percent(interval=1)
            send_metric(API_BASE, TOKEN, SERIAL_NUMBER, 'cpu_load', cpu)

            ram = psutil.virtual_memory().percent
            send_metric(API_BASE, TOKEN, SERIAL_NUMBER, 'memory_usage', ram)

            disk = psutil.disk_usage('C:\\').percent
            send_metric(API_BASE, TOKEN, SERIAL_NUMBER, 'disk_usage', disk)

            # 2. Проверка печати
            check_print_logs(API_BASE, TOKEN, SERIAL_NUMBER)

            time.sleep(INTERVAL)

        except Exception as e:
            logging.error(f"Main loop error: {e}")
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main()