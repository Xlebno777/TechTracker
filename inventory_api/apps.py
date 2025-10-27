from django.apps import AppConfig


class InventoryApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory_api'

    def ready(self):
        import inventory_api.signals # Импортируем сигналы при загрузке приложения