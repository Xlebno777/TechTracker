from django.apps import AppConfig


class InventoryApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory_api'

    def ready(self):
        import inventory_api.signals  # Импортируем сигналы при загрузке приложения
        from inventory_api.network_probe_scheduler import start_network_probe_scheduler
        from inventory_api.network_map_scheduler import start_network_map_scheduler
        start_network_probe_scheduler()
        start_network_map_scheduler()
