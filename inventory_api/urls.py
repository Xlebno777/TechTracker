from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'devices', views.DeviceViewSet)
router.register(r'logs', views.LogViewSet) # Добавь другие ViewSets

urlpatterns = [
    path('api/', include(router.urls)),
]
