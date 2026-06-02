"""
URL configuration for TechTracker_django project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from inventory_api import views as inventory_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('dj_rest_auth.urls')), # <-- dj-rest-auth
    path('api/agents/', inventory_views.ServiceAgentViewSet.as_view({'get': 'list'}), name='root-agents-list'),
    path('api/agents/metric-catalog/', inventory_views.ServiceAgentViewSet.as_view({'get': 'metric_catalog'}), name='root-agents-metric-catalog'),
    path('api/agents/checkin/', inventory_views.ServiceAgentViewSet.as_view({'post': 'checkin'}), name='root-agents-checkin'),
    path('api/agents/commands/<int:command_id>/result/', inventory_views.ServiceAgentViewSet.as_view({'post': 'command_result'}), name='root-agents-command-result'),
    path('api/agents/<int:pk>/commands/', inventory_views.ServiceAgentViewSet.as_view({'get': 'commands'}), name='root-agents-commands'),
    path('api/agents/<int:pk>/restart/', inventory_views.ServiceAgentViewSet.as_view({'post': 'restart'}), name='root-agents-restart'),
    path('api/agents/<int:pk>/update/', inventory_views.ServiceAgentViewSet.as_view({'post': 'queue_update'}), name='root-agents-update'),
    path('api/agents/<int:pk>/set-metrics/', inventory_views.ServiceAgentViewSet.as_view({'post': 'set_metrics'}), name='root-agents-set-metrics'),
    path('api/agent-installer/', inventory_views.agent_installer_release_status, name='root-agent-installer-status'),
    path('api/installers/agent/', inventory_views.agent_installer_release_status, name='root-agent-installer-status-alt'),
    path('api/application-updates/agent-installer/', inventory_views.ApplicationUpdateViewSet.as_view({'get': 'agent_installer'}), name='root-agent-installer'),
    path('api/', include('inventory_api.urls')),     # <-- inventory_api
]
