import qrcode
import logging
import io
import ipaddress
import re
import uuid
from django.http import HttpResponse
from django.core.files.base import ContentFile
from PIL import Image

from django.shortcuts import render
from rest_framework import viewsets, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, DjangoModelPermissions, IsAdminUser
from django.contrib.auth.models import User
from django.db import models
from django.db import IntegrityError
from django.db.utils import ProgrammingError
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.core.management import call_command

from .models import (
    Device, DeviceType, Location, UserProfile,
    ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs,
    Cartridge, CartridgeLog, Log, Metric, PrintJob,
    MonitoringSetting, RawMetric, TrackedVM, ComputedMetric, AgentStatus
)
from .serializers import (
    DeviceSerializer, DeviceCreateUpdateSerializer,
    DeviceTypeSerializer, LocationSerializer,
    UserProfileSerializer, ComputerSpecsSerializer,
    PrinterScannerSpecsSerializer, NetworkDeviceSpecsSerializer,
    CartridgeSerializer, CartridgeLogSerializer, LogSerializer, UserSerializer,
    MetricSerializer, PrintJobSerializer, RawMetricSerializer, RawMetricIngestSerializer,
    TrackedVMSerializer, TrackedVMSyncSerializer, ComputedMetricSerializer, AgentStatusSerializer, AgentStatusReportSerializer
)
from .permissions import PrintJobPermission, PrinterAgentPermission, MetricsAgentPermission, VMStatusAgentPermission
from django.utils import timezone
from datetime import timedelta


def _normalize_ip(value):
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _build_printer_serial(base, max_len=100):
    raw = base or str(uuid.uuid4())
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', raw)
    serial = f"PRN-{cleaned}"[:max_len]
    if not Device.objects.filter(serial_number=serial).exists():
        return serial
    # Если конфликт — добавляем суффикс
    for idx in range(1, 1000):
        candidate = f"{serial[:max_len-4]}-{idx}"
        if not Device.objects.filter(serial_number=candidate).exists():
            return candidate
    return f"PRN-{uuid.uuid4().hex[:8]}"


def _get_printer_device_type():
    type_q = (
        Q(name__icontains='принтер') |
        Q(name__icontains='printer') |
        Q(name__icontains='мфу') |
        Q(name__icontains='mfu')
    )
    device_type = DeviceType.objects.filter(type_q).first()
    if device_type:
        return device_type
    device_type, _ = DeviceType.objects.get_or_create(name='Принтер')
    return device_type


def _get_pc_device_type():
    device_type = DeviceType.objects.filter(name__iexact='ПК').first()
    if device_type:
        return device_type
    device_type, _ = DeviceType.objects.get_or_create(name='ПК')
    return device_type


def _coerce_status(value):
    if not value:
        return 'active'
    raw = str(value).strip().lower()
    if raw in ('active', 'in_repair', 'retired', 'in_stock', 'reserved'):
        return raw
    return 'active'


def _create_device_from_info(info):
    if not info:
        return None

    name = (info.get('name') or '').strip()
    serial = (info.get('serial_number') or '').strip()
    if not serial:
        return None

    if Device.objects.filter(serial_number=serial).exists():
        return Device.objects.filter(serial_number=serial).first()

    asset_number = (info.get('asset_number') or '').strip() or None
    if asset_number == '-' and Device.objects.filter(asset_number=asset_number).exists():
        asset_number = None

    device_type = _get_pc_device_type()
    status = _coerce_status(info.get('status'))
    ip_address = _normalize_ip(info.get('ip_address') or '')
    mac_address = (info.get('mac_address') or '').strip() or None

    owner_username = (info.get('owner_username') or '').strip()
    owner = None
    if owner_username:
        owner = User.objects.filter(username=owner_username).first()
    if owner is None:
        owner = User.objects.filter(is_superuser=True).first()

    try:
        device = Device.objects.create(
            name=name or serial,
            serial_number=serial,
            asset_number=asset_number,
            device_type=device_type,
            status=status,
            ip_address=ip_address,
            mac_address=mac_address,
            owner=owner,
        )
    except IntegrityError:
        device = Device.objects.filter(serial_number=serial).first()

    if device:
        cpu = (info.get('cpu') or '').strip()
        ram_gb = info.get('ram_gb')
        if cpu or ram_gb:
            specs, _ = ComputerSpecs.objects.get_or_create(device=device)
            if cpu:
                specs.cpu = cpu
            if ram_gb:
                try:
                    specs.ram_gb = int(ram_gb)
                except Exception:
                    pass
            specs.save()

    return device

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
    queryset = Log.objects.all().select_related('device', 'created_by') # <-- Оптимизируем запросы
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions] # <-- Оставим стандартные разрешения

    def perform_create(self, serializer):
        """
        Переопределяем perform_create, чтобы автоматически установить created_by на текущего пользователя.
        """
        serializer.save(created_by=self.request.user)

    # Добавим фильтрацию, чтобы админ мог видеть все, а обычный пользователь - только свои
    def get_queryset(self):
        user = self.request.user
        # Проверяем, является ли пользователь администратором
        if user.is_staff:
            # Админ видит все логи
            return Log.objects.all().select_related('device', 'created_by')
        else:
            # Обычный пользователь видит только свои логи (например, заявки)
            # Или только определённые типы логов, например, только 'request'
            # В данном случае, если это ViewSet для заявок, можно ограничить по created_by
            # Или создать отдельный ViewSet для заявок.
            # Пока оставим так, чтобы обычный пользователь мог видеть только свои 'request'
            return Log.objects.filter(created_by=user, log_type='request').select_related('device', 'created_by')

    # Добавим разрешение на обновление статуса только админу
    def get_permissions(self):
        permission_classes = [IsAuthenticated]
        # Для обновления (PUT, PATCH) проверяем, является ли пользователь админом
        if self.action in ['update', 'partial_update']:
            permission_classes.append(DjangoModelPermissions) # Или кастомное разрешение
            # Лучше использовать кастомную проверку в методе update
        else:
            permission_classes.append(DjangoModelPermissions)
        return [permission() for permission in permission_classes]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        # Только админ может обновлять статус
        if not user.is_staff:
            # Проверим, пытается ли пользователь изменить статус
            if 'status' in request.data:
                return Response(
                    {"detail": "Только администратор может изменять статус заявки."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # Также можно запретить изменение других полей, кроме message (если разрешено)
            # или просто разрешить только владельцу изменять свои заявки (кроме статуса)
            if instance.created_by != user:
                 return Response(
                    {"detail": "Вы можете изменять только свои заявки."},
                    status=status.HTTP_403_FORBIDDEN
                )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        # Аналогично для PATCH
        instance = self.get_object()
        user = request.user
        if not user.is_staff:
            if 'status' in request.data:
                return Response(
                    {"detail": "Только администратор может изменять статус заявки."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if instance.created_by != user:
                 return Response(
                    {"detail": "Вы можете изменять только свои заявки."},
                    status=status.HTTP_403_FORBIDDEN
                )
        return super().partial_update(request, *args, **kwargs)

# --- ViewSet для Device ---
class DeviceViewSet(viewsets.ModelViewSet):
    """
    Основной API для устройств с поддержкой фильтрации, поиска и сортировки.
    """
    queryset = Device.objects.all().select_related('device_type', 'location', 'owner', 'assigned_to') \
                                    .prefetch_related('logs')
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

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated], url_path='favorite_printers')
    def favorite_printers(self, request):
        """
        Возвращает избранные принтеры текущего пользователя.
        Принтер определяется по printer_scanner_specs или имени типа устройства.
        """
        user = request.user
        try:
            favorites = user.profile.favorite_devices.all()
        except UserProfile.DoesNotExist:
            favorites = Device.objects.none()

        printer_q = (
            Q(printer_scanner_specs__isnull=False) |
            Q(device_type__name__icontains='принтер') |
            Q(device_type__name__icontains='printer') |
            Q(device_type__name__icontains='мфу') |
            Q(device_type__name__icontains='mfu')
        )
        favorites = favorites.filter(printer_q).distinct()
        serializer = self.get_serializer(favorites, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[PrinterAgentPermission], url_path='sync_printers')
    def sync_printers(self, request):
        """
        Принимает список принтеров (name/ip_address) и синхронизирует с БД.
        """
        payload = request.data.get('printers', request.data)
        if not isinstance(payload, list):
            return Response({"detail": "Expected list of printers."}, status=status.HTTP_400_BAD_REQUEST)

        device_type = _get_printer_device_type()
        created = 0
        updated = 0
        skipped = 0

        for item in payload:
            if not isinstance(item, dict):
                skipped += 1
                continue

            name = (item.get('name') or item.get('printer_name') or item.get('display_name') or '').strip()
            lower_name = name.lower()
            ip_raw = (item.get('ip_address') or item.get('ip') or '').strip()
            ip = _normalize_ip(ip_raw)

            if name and any(key in lower_name for key in EXCLUDED_PRINTER_KEYWORDS):
                skipped += 1
                continue

            if not name and not ip:
                skipped += 1
                continue

            device = None
            if ip:
                device = Device.objects.filter(ip_address=ip).first()
            if device is None and name:
                device = Device.objects.filter(name=name).first()

            if device:
                changed = False
                if name and device.name != name:
                    device.name = name
                    changed = True
                if ip and device.ip_address != ip:
                    device.ip_address = ip
                    changed = True
                if device.device_type_id != device_type.id:
                    device.device_type = device_type
                    changed = True
                if changed:
                    device.save()
                    updated += 1
                else:
                    skipped += 1
            else:
                serial = _build_printer_serial(ip or name)
                device = Device.objects.create(
                    name=name or f"Printer {ip or serial}",
                    serial_number=serial,
                    device_type=device_type,
                    ip_address=ip,
                )
                created += 1

            PrinterScannerSpecs.objects.get_or_create(device=device)

        return Response(
            {"created": created, "updated": updated, "skipped": skipped},
            status=status.HTTP_200_OK
        )
    
    # --- НОВЫЙ МЕТОД ДЛЯ QR-КОДА ---
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def qr(self, request, pk=None):
        """
        Возвращает QR-код для конкретного устройства в формате PNG.
        URL: /api/devices/{id}/qr/
        """
        device = self.get_object() # Получает устройство по pk, проверяет разрешения

        # Создаём QR-код с qr_code_id
        qr = qrcode.QRCode(
            version=1, # Размер QR-кода (1 - минимальный)
            error_correction=qrcode.constants.ERROR_CORRECT_L, # Уровень коррекции ошибок
            box_size=10, # Размер "пикселя" QR-кода
            border=4, # Размер рамки
        )
        qr.add_data(device.qr_code_id) # Добавляем qr_code_id в QR
        qr.make(fit=True) # Создаём QR-код

        # Создаём изображение
        img = qr.make_image(fill_color="black", back_color="white")

        # Сохраняем изображение в BytesIO (в памяти)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0) # Перемещаем указатель в начало буфера

        # Возвращаем HTTP-ответ с изображением
        response = HttpResponse(buffer.getvalue(), content_type="image/png")
        response['Content-Disposition'] = f'inline; filename="qr_{device.qr_code_id}.png"' # Необязательно
        return response
    # --- /НОВЫЙ МЕТОД ДЛЯ QR-КОДА ---

    # --- НОВЫЙ МЕТОД: Переключение избранного ---
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def toggle_favorite(self, request, pk=None):
        """
        POST /api/devices/{id}/toggle_favorite/
        Добавляет/удаляет устройство с pk в избранное текущего пользователя.
        """
        device = self.get_object() # Получает устройство по pk
        user = request.user

        try:
            user_profile = user.profile
        except UserProfile.DoesNotExist:
            # Создаем профиль, если его нет (альтернатива сигналу)
            user_profile = UserProfile.objects.create(user=user)

        # Проверяем, есть ли устройство в избранном
        if user_profile.favorite_devices.filter(pk=device.pk).exists():
            # Удаляем из избранного
            user_profile.favorite_devices.remove(device)
            message = "Устройство удалено из избранного."
            is_favorite = False
        else:
            # Добавляем в избранное
            user_profile.favorite_devices.add(device)
            message = "Устройство добавлено в избранное."
            is_favorite = True

        # Возвращаем статус и сообщение
        return Response(
            {"message": message, "is_favorite": is_favorite, "device_id": device.id},
            status=status.HTTP_200_OK
        )
    # --- /НОВЫЙ МЕТОД ---

# --- ViewSet для User ---
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
class MetricViewSet(viewsets.ModelViewSet):
    queryset = Metric.objects.all()
    serializer_class = MetricSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    
    # Подключаем фильтрацию
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    
    # Поля, по которым можно фильтровать (точное совпадение)
    filterset_fields = ['device', 'metric_type']
    
    # Поля для сортировки
    ordering_fields = ['timestamp', 'value']
    ordering = ['-timestamp']

    # Оптимизация: если фронт запрашивает график, ему нужно много точек.
    # Можно настроить пагинацию отдельно, если глобальная слишком мала,
    # но пока оставим стандартную.


class RawMetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RawMetric.objects.all()
    serializer_class = RawMetricSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'code']
    ordering_fields = ['timestamp', 'value']
    ordering = ['-timestamp']

    def get_queryset(self):
        qs = super().get_queryset()
        since_minutes = self.request.query_params.get('since_minutes')
        if since_minutes:
            try:
                minutes = int(since_minutes)
                if minutes > 0:
                    qs = qs.filter(timestamp__gte=timezone.now() - timedelta(minutes=minutes))
            except ValueError:
                pass
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        limit = request.query_params.get('limit')
        if limit:
            try:
                limit_val = int(limit)
                if limit_val > 0:
                    queryset = queryset[:limit_val]
            except ValueError:
                pass

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[MetricsAgentPermission])
    def ingest(self, request):
        serializer = RawMetricIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serial = serializer.validated_data['serial_number']
        retention_days = serializer.validated_data.get('retention_days')
        metrics = serializer.validated_data['metrics']
        device_info = serializer.validated_data.get('device_info')

        device = Device.objects.filter(serial_number=serial).first()
        if not device and isinstance(device_info, dict):
            device = _create_device_from_info(device_info)
        if not device:
            return Response(
                {"detail": f"Device with serial number '{serial}' not found."},
                status=status.HTTP_400_BAD_REQUEST
            )

        setting, _ = MonitoringSetting.objects.get_or_create(device=device)
        if retention_days and setting.retention_days != retention_days:
            setting.retention_days = retention_days
            setting.save(update_fields=['retention_days', 'updated_at'])

        now = timezone.now()
        objects = []
        for item in metrics:
            ts = item.get('timestamp') or now
            objects.append(RawMetric(
                device=device,
                code=item['code'],
                value=item['value'],
                unit=item.get('unit', ''),
                timestamp=ts,
                labels=item.get('labels', {})
            ))

        if objects:
            RawMetric.objects.bulk_create(objects, batch_size=1000)

        return Response({"created": len(objects)}, status=status.HTTP_201_CREATED)


class ComputedMetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ComputedMetric.objects.all()
    serializer_class = ComputedMetricSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'code', 'window']
    ordering_fields = ['timestamp', 'value']
    ordering = ['-timestamp']

    @action(detail=False, methods=['post'], permission_classes=[IsAdminUser])
    def recompute(self, request):
        serial = request.data.get('serial')
        try:
            if serial:
                call_command('compute_derived_metrics', serial=serial)
            else:
                call_command('compute_derived_metrics')
            return Response({"detail": "ok"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": f"compute failed: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AgentStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AgentStatus.objects.all()
    serializer_class = AgentStatusSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'status']
    ordering_fields = ['updated_at']
    ordering = ['-updated_at']

    @action(detail=False, methods=['post'], permission_classes=[MetricsAgentPermission])
    def report(self, request):
        serializer = AgentStatusReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serial = serializer.validated_data['serial_number']
        status_value = serializer.validated_data['status']
        message = serializer.validated_data.get('message', '')

        device = Device.objects.filter(serial_number=serial).first()
        if not device:
            return Response({"detail": "Device not found"}, status=status.HTTP_400_BAD_REQUEST)

        AgentStatus.objects.update_or_create(
            device=device,
            defaults={
                'status': status_value,
                'message': message or ''
            }
        )
        return Response({"detail": "ok"}, status=status.HTTP_200_OK)


def _normalize_vm_status(value):
    if value is None:
        return 'unknown'
    if isinstance(value, (int, float)):
        code = int(value)
        if code == 2:
            return 'running'
        if code == 3:
            return 'off'
        if code == 6:
            return 'saved'
        if code == 9:
            return 'paused'
        return 'unknown'
    raw = str(value).strip().lower()
    if raw.isdigit():
        code = int(raw)
        if code == 2:
            return 'running'
        if code == 3:
            return 'off'
        if code == 6:
            return 'saved'
        if code == 9:
            return 'paused'
    if raw in ('running', 'on', 'started', 'работает', 'включена', 'включен', 'запущена', 'запущен'):
        return 'running'
    if raw in ('off', 'stopped', 'poweroff', 'poweredoff', 'выключена', 'выключен', 'остановлена', 'остановлен'):
        return 'off'
    if 'pause' in raw:
        return 'paused'
    if 'пауза' in raw:
        return 'paused'
    if 'saved' in raw:
        return 'saved'
    if 'сохран' in raw:
        return 'saved'
    return 'unknown'


class TrackedVMViewSet(viewsets.ModelViewSet):
    queryset = TrackedVM.objects.all()
    serializer_class = TrackedVMSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['status', 'is_enabled', 'host_device']
    search_fields = ['name']
    ordering_fields = ['name', 'status', 'cpu_usage', 'memory_usage', 'uptime_seconds', 'last_seen']
    ordering = ['name']

    @action(detail=False, methods=['post'], permission_classes=[VMStatusAgentPermission])
    def sync_status(self, request):
        serializer = TrackedVMSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serial = serializer.validated_data['serial_number']
        vms = serializer.validated_data['vms']
        host_device = Device.objects.filter(serial_number=serial).first()
        now = timezone.now()

        created = 0
        updated = 0
        skipped = 0
        vm_metrics = []

        try:
            for vm_data in vms:
                name = vm_data.get('name')
                if not name:
                    skipped += 1
                    continue
                raw_status = vm_data.get('status')
                normalized_status = _normalize_vm_status(raw_status)
                vm = TrackedVM.objects.filter(name=name).first()
                is_new = False
                cpu_usage = vm_data.get('cpu_usage')
                mem_usage = vm_data.get('memory_usage')
                uptime_sec = vm_data.get('uptime_seconds')
                try:
                    cpu_usage = float(cpu_usage) if cpu_usage is not None else None
                except (TypeError, ValueError):
                    cpu_usage = None
                try:
                    mem_usage = float(mem_usage) if mem_usage is not None else None
                except (TypeError, ValueError):
                    mem_usage = None
                try:
                    uptime_sec = int(float(uptime_sec)) if uptime_sec is not None else None
                except (TypeError, ValueError):
                    uptime_sec = None

                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(
                        "VM sync: name=%s status_raw=%s status_norm=%s cpu=%s mem=%s uptime=%s",
                        name, raw_status, normalized_status, cpu_usage, mem_usage, uptime_sec
                    )
                if not vm:
                    vm = TrackedVM.objects.create(
                        name=name,
                        status=normalized_status,
                        cpu_usage=cpu_usage,
                        memory_usage=mem_usage,
                        uptime_seconds=uptime_sec,
                        last_seen=now,
                        host_device=host_device,
                        is_enabled=True,
                    )
                    created += 1
                    is_new = True
                if not vm.is_enabled:
                    skipped += 1
                    continue

                vm.status = normalized_status
                vm.cpu_usage = cpu_usage
                vm.memory_usage = mem_usage
                vm.uptime_seconds = uptime_sec
                vm.last_seen = now
                if host_device:
                    vm.host_device = host_device
                vm.save()
                if not is_new:
                    updated += 1

                if host_device:
                    labels = {'vm': name}
                    if vm.id:
                        labels['vm_id'] = vm.id
                    if cpu_usage is not None:
                        vm_metrics.append(RawMetric(
                            device=host_device,
                            code='vm_cpu_usage',
                            value=cpu_usage,
                            unit='%',
                            timestamp=now,
                            labels=labels,
                        ))
                    if mem_usage is not None:
                        vm_metrics.append(RawMetric(
                            device=host_device,
                            code='vm_memory_usage',
                            value=mem_usage,
                            unit='%',
                            timestamp=now,
                            labels=labels,
                        ))
                    if uptime_sec is not None:
                        vm_metrics.append(RawMetric(
                            device=host_device,
                            code='vm_uptime_seconds',
                            value=uptime_sec,
                            unit='sec',
                            timestamp=now,
                            labels=labels,
                        ))
                    vm_metrics.append(RawMetric(
                        device=host_device,
                        code='vm_status_running',
                        value=1.0 if normalized_status == 'running' else 0.0,
                        unit='flag',
                        timestamp=now,
                        labels=labels,
                    ))
        except ProgrammingError:
            return Response(
                {"detail": "TrackedVM table is missing. Run migrations (python manage.py migrate)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if vm_metrics:
            RawMetric.objects.bulk_create(vm_metrics, batch_size=1000)

        return Response({"created": created, "updated": updated, "skipped": skipped}, status=status.HTTP_200_OK)

class PrintJobViewSet(viewsets.ModelViewSet):
    queryset = PrintJob.objects.all()
    serializer_class = PrintJobSerializer
    permission_classes = [PrintJobPermission]
    
    # Подключаем фильтрацию
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    
    # Поля, по которым можно фильтровать (точное совпадение)
    filterset_fields = ['device', 'device__serial_number', 'user_name', 'document_name', 'printer_name']
    
    # Поля для сортировки
    ordering_fields = ['id', 'device__serial_number', 'device', 'user_name', 'document_name', 'pages', 'printer_name', 'timestamp']
    ordering = ['-id']
EXCLUDED_PRINTER_KEYWORDS = [
    'adobe pdf',
    'microsoft print to pdf',
    'microsoft xps document writer',
]
