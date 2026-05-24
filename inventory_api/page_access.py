from django.contrib.auth.models import Group

from .models import PageAccessRule


DEFAULT_PAGE_ACCESS_RULES = [
    {
        "route_name": "DeviceTable",
        "label": "Устройства",
        "section": "main",
        "icon": "pi pi-table",
        "order": 10,
        "groups": ["Admins", "Users"],
    },
    {
        "route_name": "DeviceCreate",
        "label": "Создание устройства",
        "section": "main",
        "icon": "pi pi-plus",
        "order": 11,
        "groups": ["Admins"],
    },
    {
        "route_name": "DeviceEdit",
        "label": "Редактирование устройства",
        "section": "main",
        "icon": "pi pi-pencil",
        "order": 12,
        "groups": ["Admins", "Users"],
    },
    {
        "route_name": "Printers",
        "label": "Принтеры",
        "section": "main",
        "icon": "pi pi-print",
        "order": 20,
        "groups": ["Admins", "Users"],
    },
    {
        "route_name": "RequestForm",
        "label": "Заявка",
        "section": "main",
        "icon": "pi pi-envelope",
        "order": 30,
        "groups": ["Admins", "Users"],
    },
    {
        "route_name": "AdminRequests",
        "label": "Заявки",
        "section": "admin",
        "icon": "pi pi-list",
        "order": 40,
        "groups": ["Admins"],
    },
    {
        "route_name": "NetworkMonitoring",
        "label": "Сеть",
        "section": "admin",
        "icon": "pi pi-sitemap",
        "order": 50,
        "groups": ["Admins"],
    },
    {
        "route_name": "AgentDiagnostics",
        "label": "Диагностика агента",
        "section": "admin",
        "icon": "pi pi-shield",
        "order": 60,
        "groups": ["Admins"],
    },
    {
        "route_name": "UserManagement",
        "label": "Пользователи",
        "section": "admin",
        "icon": "pi pi-users",
        "order": 70,
        "groups": ["Admins"],
    },
    {
        "route_name": "Settings",
        "label": "Настройки",
        "section": "admin",
        "icon": "pi pi-cog",
        "order": 80,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringPipeline",
        "label": "Полный цикл",
        "section": "monitoring",
        "icon": "pi pi-sitemap",
        "order": 100,
        "groups": ["Admins"],
    },
    {
        "route_name": "Monitoring",
        "label": "Сырые метрики",
        "section": "monitoring",
        "icon": "pi pi-wave-pulse",
        "order": 110,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringAnalysis",
        "label": "Анализ мониторинга",
        "section": "monitoring",
        "icon": "pi pi-chart-bar",
        "order": 120,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringForecast",
        "label": "Прогнозы и состояния",
        "section": "monitoring",
        "icon": "pi pi-chart-scatter",
        "order": 130,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringRisk",
        "label": "Оценка риска",
        "section": "monitoring",
        "icon": "pi pi-exclamation-triangle",
        "order": 140,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringDecision",
        "label": "Рекомендации СППР",
        "section": "monitoring",
        "icon": "pi pi-lightbulb",
        "order": 150,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringDemo",
        "label": "Мониторинг - Демо",
        "section": "monitoring",
        "icon": "pi pi-database",
        "order": 160,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringEvaluation",
        "label": "Оценка прогноза",
        "section": "monitoring",
        "icon": "pi pi-chart-line",
        "order": 170,
        "groups": ["Admins"],
    },
    {
        "route_name": "MonitoringTasks",
        "label": "Центр задач",
        "section": "monitoring",
        "icon": "pi pi-clock",
        "order": 180,
        "groups": ["Admins"],
    },
]


def ensure_default_page_access_rules():
    rows = []
    for config in DEFAULT_PAGE_ACCESS_RULES:
        rule, created = PageAccessRule.objects.get_or_create(
            route_name=config["route_name"],
            defaults={
                "label": config["label"],
                "section": config["section"],
                "icon": config.get("icon", ""),
                "order": config.get("order", 100),
                "is_enabled": True,
            },
        )
        changed = False
        for field in ["label", "section", "icon", "order"]:
            value = config.get(field, getattr(rule, field))
            if getattr(rule, field) != value:
                setattr(rule, field, value)
                changed = True
        if changed:
            rule.save(update_fields=["label", "section", "icon", "order", "updated_at"])
        if created:
            groups = []
            for name in config.get("groups", []):
                group, _ = Group.objects.get_or_create(name=name)
                groups.append(group)
            if groups:
                rule.allowed_groups.set(groups)
        rows.append(rule)
    return rows
