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
router.register(r'managed-users', views.ManagedUserViewSet, basename='managed-users')
router.register(r'managed-groups', views.ManagedGroupViewSet, basename='managed-groups')
router.register(r'auth-permissions', views.PermissionViewSet, basename='auth-permissions')
router.register(r'page-access', views.PageAccessRuleViewSet, basename='page-access')
router.register(r'metrics', views.MetricViewSet)
router.register(r'metrics-raw', views.RawMetricViewSet, basename='metrics-raw')
router.register(r'metrics-computed', views.ComputedMetricViewSet, basename='metrics-computed')
router.register(r'agent-status', views.AgentStatusViewSet, basename='agent-status')
router.register(r'agents', views.ServiceAgentViewSet, basename='agents')
router.register(r'diagnostics', views.DiagnosticReportViewSet, basename='diagnostics')
router.register(r'forecast-runs', views.ForecastRunViewSet, basename='forecast-runs')
router.register(r'forecast-queue-jobs', views.LSTMRemoteQueueJobViewSet, basename='forecast-queue-jobs')
router.register(r'forecast-points', views.ForecastPointViewSet, basename='forecast-points')
router.register(r'state-estimates', views.StateEstimateViewSet, basename='state-estimates')
router.register(r'state-inference-profiles', views.StateInferenceProfileViewSet, basename='state-inference-profiles')
router.register(r'risk-assessment', views.RiskAssessmentViewSet, basename='risk-assessment')
router.register(r'dissertation-evaluation', views.DissertationEvaluationViewSet, basename='dissertation-evaluation')
router.register(r'monitoring-system', views.MonitoringSystemViewSet, basename='monitoring-system')
router.register(r'system-health', views.SystemHealthViewSet, basename='system-health')
router.register(r'application-updates', views.ApplicationUpdateViewSet, basename='application-updates')
router.register(r'decision-actions', views.DecisionActionViewSet, basename='decision-actions')
router.register(r'decision-criteria', views.DecisionCriterionViewSet, basename='decision-criteria')
router.register(r'decision-policies', views.DecisionPolicyViewSet, basename='decision-policies')
router.register(r'decision-policy-losses', views.DecisionPolicyLossViewSet, basename='decision-policy-losses')
router.register(r'decision-runs', views.DecisionRunViewSet, basename='decision-runs')
router.register(r'network-paths', views.NetworkPathViewSet, basename='network-paths')
router.register(r'network-outages', views.NetworkOutageViewSet, basename='network-outages')
router.register(r'network-alert-rules', views.NetworkAlertRuleViewSet, basename='network-alert-rules')
router.register(r'network-map', views.NetworkMapViewSet, basename='network-map')
router.register(r'printjob', views.PrintJobViewSet)
router.register(r'tracked-vms', views.TrackedVMViewSet)

# Подключаем маршруты роутера к этому файлу
urlpatterns = [
    path('health/', views.health_check, name='api-health'),
    path('agents/', views.ServiceAgentViewSet.as_view({'get': 'list'}), name='agents-list-direct'),
    path('agents/metric-catalog/', views.ServiceAgentViewSet.as_view({'get': 'metric_catalog'}), name='agents-metric-catalog-direct'),
    path('agents/checkin/', views.ServiceAgentViewSet.as_view({'post': 'checkin'}), name='agents-checkin-direct'),
    path('agents/commands/<int:command_id>/result/', views.ServiceAgentViewSet.as_view({'post': 'command_result'}), name='agents-command-result-direct'),
    path('agents/<int:pk>/commands/', views.ServiceAgentViewSet.as_view({'get': 'commands'}), name='agents-commands-direct'),
    path('agents/<int:pk>/restart/', views.ServiceAgentViewSet.as_view({'post': 'restart'}), name='agents-restart-direct'),
    path('agents/<int:pk>/update/', views.ServiceAgentViewSet.as_view({'post': 'queue_update'}), name='agents-update-direct'),
    path('agents/<int:pk>/set-metrics/', views.ServiceAgentViewSet.as_view({'post': 'set_metrics'}), name='agents-set-metrics-direct'),
    path('application-updates/agent-installer/', views.ApplicationUpdateViewSet.as_view({'get': 'agent_installer'}), name='agent-installer-direct'),
    path('', include(router.urls)),
    # Можно добавить дополнительные URL-ы, не связанные с ViewSet'ами, здесь
]
