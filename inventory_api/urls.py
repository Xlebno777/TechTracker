from django.urls import path, include
from django.contrib import admin
from rest_framework.routers import DefaultRouter
from . import views

# Создаем роутер
router = DefaultRouter()

# Регистрируем ViewSet'ы. Django DRF автоматически создаст URL-ы.
# Например, для DeviceViewSet будут созданы:
# GET /api/devices/ - list
# POST /api/devices/ - create
# GET /api/devices/{id}/ - retrieve
# PUT /api/devices/{id}/ - update
# PATCH /api/devices/{id}/ - partial_update
# DELETE /api/devices/{id}/ - destroy
# Также будет доступен кастомный эндпоинт GET /api/devices/my_devices/
router.register(r'devices', views.DeviceViewSet)
router.register(r'devicetypes', views.DeviceTypeViewSet)
router.register(r'locations', views.LocationViewSet)
router.register(r'userprofiles', views.UserProfileViewSet)
router.register(r'computerspecs', views.ComputerSpecsViewSet)
router.register(r'printerscannerspecs', views.PrinterScannerSpecsViewSet)
router.register(r'networkspecs', views.NetworkDeviceSpecsViewSet)
router.register(r'cartridges', views.CartridgeViewSet)
router.register(r'cartridelogs', views.CartridgeLogViewSet)
router.register(r'logs', views.LogViewSet)
router.register(r'users', views.UserViewSet) # Только эндпоинты чтения
router.register(r'metrics', views.MetricViewSet)
router.register(r'metrics-raw', views.RawMetricViewSet, basename='metrics-raw')
router.register(r'metrics-computed', views.ComputedMetricViewSet, basename='metrics-computed')
router.register(r'agent-status', views.AgentStatusViewSet, basename='agent-status')
router.register(r'diagnostics', views.DiagnosticReportViewSet, basename='diagnostics')
router.register(r'network-paths', views.NetworkPathViewSet, basename='network-paths')
router.register(r'network-outages', views.NetworkOutageViewSet, basename='network-outages')
router.register(r'network-alert-rules', views.NetworkAlertRuleViewSet, basename='network-alert-rules')
router.register(r'network-map', views.NetworkMapViewSet, basename='network-map')
router.register(r'printjob', views.PrintJobViewSet)
router.register(r'tracked-vms', views.TrackedVMViewSet)

# Подключаем маршруты роутера к этому файлу
urlpatterns = [
    path('', include(router.urls)),
    # Можно добавить дополнительные URL-ы, не связанные с ViewSet'ами, здесь
]
