AGENT_METRIC_TASKS = [
    {
        "name": "cpu_total",
        "codes": ["cpu_load_total"],
        "title": "Загрузка CPU",
        "description": "Общая загрузка процессора по данным Windows.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "cpu_kernel",
        "codes": ["cpu_load_kernel"],
        "title": "Нагрузка ядра CPU",
        "description": "Доля времени процессора, занятая системным ядром.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "cpu_interrupts",
        "codes": ["cpu_interrupts"],
        "title": "Прерывания CPU",
        "description": "Частота аппаратных прерываний процессора.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "mem_usage",
        "codes": ["mem_usage_percent"],
        "title": "Использование памяти",
        "description": "Процент занятой оперативной памяти.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "swap_usage",
        "codes": ["mem_swap_usage"],
        "title": "Файл подкачки",
        "description": "Использование swap/pagefile.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "disk_usage",
        "codes": ["disk_usage_percent"],
        "title": "Заполнение дисков",
        "description": "Процент занятого места по локальным томам.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "disk_io",
        "codes": ["disk_read_bytes", "disk_write_bytes"],
        "title": "Дисковый ввод-вывод",
        "description": "Скорость чтения и записи по дисковой подсистеме.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "storcli_errors",
        "codes": [
            "storcli_media_error_count",
            "storcli_other_error_count",
            "storcli_predictive_failure_count",
            "storcli_smart_alert",
        ],
        "title": "Ошибки RAID-дисков StorCLI",
        "description": "Ошибки носителя, predictive failure и SMART-алерты с контроллеров Broadcom/LSI.",
        "setup": "Нужно установить Broadcom/LSI StorCLI и добавить storcli64.exe в PATH или указать путь в конфиге агента.",
    },
    {
        "name": "storcli_temp",
        "codes": ["storcli_drive_temperature"],
        "title": "Температура RAID-дисков StorCLI",
        "description": "Температура физических дисков за Broadcom/LSI RAID-контроллером.",
        "setup": "Нужно установить Broadcom/LSI StorCLI и добавить storcli64.exe в PATH или указать путь в конфиге агента.",
    },
    {
        "name": "net",
        "codes": ["net_bytes_sent", "net_bytes_recv", "net_errors_in", "net_errors_out"],
        "title": "Сеть",
        "description": "Скорость приема/передачи и счетчики сетевых ошибок.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "ping",
        "codes": ["ping_latency_gateway"],
        "title": "Ping-задержка",
        "description": "ICMP-задержка до заданной цели.",
        "setup": "Нужно указать ping target и разрешить ICMP до этой цели.",
    },
    {
        "name": "uptime",
        "codes": ["uptime_seconds"],
        "title": "Uptime",
        "description": "Время работы ОС с последней загрузки.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "process_count",
        "codes": ["process_count"],
        "title": "Количество процессов",
        "description": "Текущее число процессов в ОС.",
        "setup": "Ничего настраивать не нужно.",
    },
    {
        "name": "system_temperature",
        "codes": ["system_temperature"],
        "title": "Температура системы",
        "description": "Температура по доступным ACPI/WMI-сенсорам.",
        "setup": "Нужны доступные ACPI thermal WMI-данные или WMI-сенсоры OpenHardwareMonitor/LibreHardwareMonitor.",
    },
]

AGENT_METRIC_TASK_NAMES = tuple(item["name"] for item in AGENT_METRIC_TASKS)


def default_agent_metrics_config():
    return {"enabled_tasks": list(AGENT_METRIC_TASK_NAMES)}
