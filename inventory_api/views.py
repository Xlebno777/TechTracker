from django.shortcuts import render
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    Device, DeviceType, Location, UserProfile,
    ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs,
    Cartridge, CartridgeLog, Log
)
from .serializers import (
    DeviceSerializer, DeviceCreateUpdateSerializer,
    DeviceTypeSerializer, LocationSerializer,
    UserProfileSerializer, ComputerSpecsSerializer,
    PrinterScannerSpecsSerializer, NetworkDeviceSpecsSerializer,
    CartridgeSerializer, CartridgeLogSerializer, LogSerializer, UserSerializer
)

# --- ViewSet для справочников ---
class DeviceTypeViewSet(viewsets.ModelViewSet):
    queryset = DeviceType.objects.all()
    serializer_class = DeviceTypeSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

# --- ViewSet для UserProfile ---
class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]


# --- ViewSet для специфичных данных ---
class ComputerSpecsViewSet(viewsets.ModelViewSet):
    queryset = ComputerSpecs.objects.all()
    serializer_class = ComputerSpecsSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

class PrinterScannerSpecsViewSet(viewsets.ModelViewSet):
    queryset = PrinterScannerSpecs.objects.all()
    serializer_class = PrinterScannerSpecsSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

class NetworkDeviceSpecsViewSet(viewsets.ModelViewSet):
    queryset = NetworkDeviceSpecs.objects.all()
    serializer_class = NetworkDeviceSpecsSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

class CartridgeViewSet(viewsets.ModelViewSet):
    queryset = Cartridge.objects.all()
    serializer_class = CartridgeSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

class CartridgeLogViewSet(viewsets.ModelViewSet):
    queryset = CartridgeLog.objects.all()
    serializer_class = CartridgeLogSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

# --- ViewSet для Log ---
class LogViewSet(viewsets.ModelViewSet):
    queryset = Log.objects.all()
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

# --- ViewSet для Device ---
class DeviceViewSet(viewsets.ModelViewSet):
    """
    Основной API для устройств с поддержкой фильтрации, поиска и сортировки.
    """
    queryset = Device.objects.all().select_related(
        'device_type', 'location', 'owner', 'assigned_to'
    ).prefetch_related('logs')

    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    # --- 🔍 Добавляем фильтрацию и поиск ---
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['device_type', 'location', 'status']  # фильтры по ID
    search_fields = ['name', 'serial_number', 'asset_number', 'ip_address', 'mac_address']  # поиск
    ordering_fields = ['name', 'status', 'created_at', 'location__name']  # сортировка
    ordering = ['name']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DeviceCreateUpdateSerializer
        return DeviceSerializer

    def get_queryset(self):
        """
        Переопределяем queryset для поддержки текстового поиска вручную (через ?search=...).
        """
        queryset = super().get_queryset()
        search_term = self.request.query_params.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(serial_number__icontains=search_term) |
                Q(asset_number__icontains=search_term)
            )
        return queryset

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_devices(self, request):
        """
        Возвращает устройства, связанные с текущим пользователем.
        """
        user = request.user
        owned_or_assigned = self.queryset.filter(Q(owner=user) | Q(assigned_to=user))
        try:
            favorites = user.profile.favorite_devices.all()
        except UserProfile.DoesNotExist:
            favorites = Device.objects.none()

        all_my_devices = (owned_or_assigned | favorites).distinct()
        serializer = self.get_serializer(all_my_devices, many=True)
        return Response(serializer.data)


# --- ViewSet для User ---
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
