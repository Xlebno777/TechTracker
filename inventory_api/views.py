from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly # Пример
from .models import Device, Log
from .serializers import DeviceSerializer, LogSerializer

class DeviceViewSet(viewsets.ModelViewSet):
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    # permission_classes = [IsAuthenticatedOrReadOnly] # Пример добавления прав доступа

class LogViewSet(viewsets.ReadOnlyModelViewSet): # Только чтение для логов
    queryset = Log.objects.all()
    serializer_class = LogSerializer
    # permission_classes = [IsAuthenticatedOrReadOnly]
