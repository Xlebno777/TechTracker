import qrcode
import logging
import io
import ipaddress
import re
import uuid
from collections import defaultdict
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
from django.db import transaction
from django.db.utils import ProgrammingError
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from django.core.management import call_command

from .models import (
    Device, DeviceType, Location, UserProfile,
    ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs,
    Cartridge, CartridgeLog, Log, Metric, PrintJob,
    MonitoringSetting, RawMetric, TrackedVM, ComputedMetric, AgentStatus, DiagnosticReport,
    NetworkPath, NetworkOutage, NetworkAlertRule
)
from .serializers import (
    DeviceSerializer, DeviceCreateUpdateSerializer,
    DeviceTypeSerializer, LocationSerializer,
    UserProfileSerializer, ComputerSpecsSerializer,
    PrinterScannerSpecsSerializer, NetworkDeviceSpecsSerializer,
    CartridgeSerializer, CartridgeLogSerializer, LogSerializer, UserSerializer,
    MetricSerializer, PrintJobSerializer, RawMetricSerializer, RawMetricIngestSerializer,
    TrackedVMSerializer, TrackedVMSyncSerializer, ComputedMetricSerializer, AgentStatusSerializer, AgentStatusReportSerializer,
    DiagnosticReportSerializer, DiagnosticRunSerializer, NetworkPathSerializer, NetworkOutageSerializer,
    NetworkAlertRuleSerializer
)
from .permissions import PrintJobPermission, PrinterAgentPermission, MetricsAgentPermission, VMStatusAgentPermission, AdminGroupPermission
from .diagnostics import generate_diagnostic_report
from .network_probe import run_network_probe
from .network_discovery import scan_network, suggest_local_cidrs
from .network_alerts import (
    ensure_default_network_alert_rules,
    evaluate_network_alert_rules,
    get_network_derived_snapshot,
)
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


def _normalize_mac(value):
    if not value:
        return None
    raw = str(value).strip().upper().replace('-', ':')
    if re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', raw):
        return raw
    return None


def _build_scanned_serial(ip_address=None, mac_address=None, max_len=100):
    base = (ip_address or mac_address or str(uuid.uuid4())).strip()
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', base)
    serial = f"SCAN-{cleaned}"[:max_len]
    if not Device.objects.filter(serial_number=serial).exists():
        return serial
    for idx in range(1, 1000):
        candidate = f"{serial[:max_len-6]}-{idx}"
        if not Device.objects.filter(serial_number=candidate).exists():
            return candidate
    return f"SCAN-{uuid.uuid4().hex[:8]}"


def _find_existing_scanned_device(serial=None, ip_address=None, mac_address=None):
    if serial:
        found = Device.objects.filter(serial_number=serial).first()
        if found:
            return found
    if ip_address:
        found = Device.objects.filter(ip_address=ip_address).first()
        if found:
            return found
    if mac_address:
        found = Device.objects.filter(mac_address__iexact=mac_address).first()
        if found:
            return found
    return None


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

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission], url_path='network_scan_suggestions')
    def network_scan_suggestions(self, request):
        return Response({"cidrs": suggest_local_cidrs()}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission], url_path='network_scan')
    def network_scan(self, request):
        cidr = (request.data.get('cidr') or '').strip()
        if not cidr:
            suggestions = suggest_local_cidrs()
            if not suggestions:
                return Response(
                    {"detail": "No local network ranges found. Provide CIDR manually."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cidr = suggestions[0]

        timeout_ms = request.data.get('timeout_ms')
        try:
            timeout_ms = int(timeout_ms) if timeout_ms is not None else 600
        except (TypeError, ValueError):
            timeout_ms = 600
        timeout_ms = max(100, min(timeout_ms, 5000))

        try:
            scan_result = scan_network(cidr=cidr, timeout_ms=timeout_ms)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"Network scan failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        items = scan_result.get('results', [])
        ip_values = [item.get('ip_address') for item in items if item.get('ip_address')]
        existing_by_ip = {
            device.ip_address: device
            for device in Device.objects.filter(ip_address__in=ip_values)
        } if ip_values else {}

        for item in items:
            existing = None
            ip_address = item.get('ip_address')
            mac_address = _normalize_mac(item.get('mac_address'))
            if ip_address:
                existing = existing_by_ip.get(ip_address)
            if existing is None and mac_address:
                existing = Device.objects.filter(mac_address__iexact=mac_address).first()
            if existing:
                item['existing_device_id'] = existing.id
                item['existing_device_name'] = existing.name
                item['existing_serial_number'] = existing.serial_number
            else:
                item['existing_device_id'] = None
                item['existing_device_name'] = None
                item['existing_serial_number'] = None

        return Response({
            "cidr": scan_result.get('cidr'),
            "host_count": scan_result.get('host_count'),
            "alive_count": scan_result.get('alive_count'),
            "results": items,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission], url_path='import_scanned')
    def import_scanned(self, request):
        payload = request.data.get('devices', request.data)
        if not isinstance(payload, list):
            return Response({"detail": "Expected list of scanned devices."}, status=status.HTTP_400_BAD_REQUEST)

        device_type = _get_pc_device_type()
        created = 0
        skipped = 0
        errors = []
        created_items = []

        for item in payload:
            if not isinstance(item, dict):
                skipped += 1
                continue

            ip_address = _normalize_ip((item.get('ip_address') or '').strip())
            mac_address = _normalize_mac(item.get('mac_address'))
            if not ip_address:
                skipped += 1
                errors.append({"ip_address": item.get('ip_address'), "detail": "Invalid or empty IP address."})
                continue

            name = (item.get('name') or '').strip() or ip_address
            serial_number = (item.get('serial_number') or '').strip() or None
            if serial_number:
                serial_number = serial_number[:100]

            existing = _find_existing_scanned_device(
                serial=serial_number,
                ip_address=ip_address,
                mac_address=mac_address,
            )
            if existing:
                skipped += 1
                continue

            if not serial_number:
                serial_number = _build_scanned_serial(ip_address=ip_address, mac_address=mac_address)
            elif Device.objects.filter(serial_number=serial_number).exists():
                serial_number = _build_scanned_serial(ip_address=ip_address, mac_address=mac_address)

            try:
                with transaction.atomic():
                    created_device = Device.objects.create(
                        name=name[:200],
                        serial_number=serial_number,
                        device_type=device_type,
                        status='active',
                        ip_address=ip_address,
                        mac_address=mac_address,
                        owner=request.user,
                    )
                    created += 1
                    created_items.append({
                        "id": created_device.id,
                        "name": created_device.name,
                        "ip_address": created_device.ip_address,
                        "serial_number": created_device.serial_number,
                    })
            except Exception as exc:
                skipped += 1
                errors.append({
                    "ip_address": ip_address,
                    "detail": str(exc),
                })

        return Response({
            "created": created,
            "skipped": skipped,
            "errors": errors[:30],
            "created_items": created_items[:100],
        }, status=status.HTTP_200_OK)
    
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


class DiagnosticReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DiagnosticReport.objects.all()
    serializer_class = DiagnosticReportSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'severity']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def run(self, request):
        serializer = DiagnosticRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serial = serializer.validated_data.get('serial') or None
        mode = serializer.validated_data.get('mode')

        devices = Device.objects.all()
        if serial:
            devices = devices.filter(serial_number=serial)
        if not devices.exists():
            return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)

        created = []
        for device in devices:
            report, payload = generate_diagnostic_report(device, mode=mode)
            created.append(DiagnosticReport.objects.create(
                device=device,
                summary=report['summary'],
                severity=report['severity'],
                issues=report['issues'],
                recommendations=report['recommendations'],
                payload=payload,
            ))

        if serial and created:
            return Response(DiagnosticReportSerializer(created[0]).data, status=status.HTTP_200_OK)
        return Response({"created": len(created)}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        serial = request.query_params.get('serial')
        device_id = request.query_params.get('device')

        qs = DiagnosticReport.objects.all()
        if serial:
            device = Device.objects.filter(serial_number=serial).first()
            if not device:
                return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(device=device)
        if device_id:
            qs = qs.filter(device_id=device_id)

        report = qs.order_by('-created_at').first()
        if not report:
            return Response({"detail": "No diagnostic report yet"}, status=status.HTTP_404_NOT_FOUND)
        return Response(DiagnosticReportSerializer(report).data, status=status.HTTP_200_OK)


class NetworkPathViewSet(viewsets.ModelViewSet):
    queryset = NetworkPath.objects.all().select_related('src_device', 'dst_device')
    serializer_class = NetworkPathSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['src_device', 'dst_device', 'enabled', 'last_state']
    search_fields = ['src_device__name', 'src_device__serial_number', 'dst_device__name', 'dst_device__serial_number']
    ordering_fields = ['id', 'enabled', 'last_state', 'last_checked_at', 'updated_at', 'created_at']
    ordering = ['src_device__name', 'dst_device__name']

    @staticmethod
    def _to_bool(value, default=False):
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(value)

    @staticmethod
    def _to_int(value, default=None):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _contains_any(text, keywords):
        raw = (text or '').lower()
        return any(key in raw for key in keywords)

    def _is_server_device(self, device):
        type_name = (device.device_type.name if device.device_type else '') or ''
        name = device.name or ''
        return self._contains_any(type_name, ('сервер', 'server', 'hyper-v', 'хост')) or self._contains_any(name, ('server', 'srv', 'hyper-v', 'host'))

    def _is_router_device(self, device):
        type_name = (device.device_type.name if device.device_type else '') or ''
        name = device.name or ''
        return self._contains_any(type_name, ('маршрутиз', 'router', 'роутер')) or self._contains_any(name, ('router', 'маршрутиз', 'роутер'))

    def _is_gateway_device(self, device):
        type_name = (device.device_type.name if device.device_type else '') or ''
        name = device.name or ''
        return self._contains_any(type_name, ('шлюз', 'gateway', 'gw')) or self._contains_any(name, ('gateway', 'шлюз', 'gw'))

    def _collect_indicators(self, path_ids):
        now = timezone.now()
        since_24h = now - timedelta(hours=24)
        since_7d = now - timedelta(days=7)
        path_ids_set = {int(pid) for pid in path_ids}
        if not path_ids_set:
            return {}
        metrics_map = {
            int(pid): {
                'samples_24h': 0,
                'up_24h': 0,
                'samples_7d': 0,
                'up_7d': 0,
                'outage_count_24h': 0,
                'outage_count_7d': 0,
                'last_outage_duration_sec': None,
            }
            for pid in path_ids_set
        }

        reach_rows = (
            RawMetric.objects
            .filter(code='net_path_reachable', timestamp__gte=since_7d)
            .values('timestamp', 'value', 'labels')
        )
        for row in reach_rows:
            labels = row.get('labels') or {}
            path_id = self._to_int(labels.get('path_id'))
            if path_id not in path_ids_set:
                continue
            value = float(row.get('value') or 0.0)
            ts = row.get('timestamp')
            metrics_map[path_id]['samples_7d'] += 1
            if value >= 0.5:
                metrics_map[path_id]['up_7d'] += 1
            if ts and ts >= since_24h:
                metrics_map[path_id]['samples_24h'] += 1
                if value >= 0.5:
                    metrics_map[path_id]['up_24h'] += 1

        outages = (
            NetworkOutage.objects
            .filter(path_id__in=path_ids_set)
            .values('path_id', 'started_at', 'ended_at', 'duration_sec', 'is_active')
        )
        latest_ended = {}
        for row in outages:
            path_id = row['path_id']
            started_at = row.get('started_at')
            ended_at = row.get('ended_at')
            if started_at and started_at >= since_24h:
                metrics_map[path_id]['outage_count_24h'] += 1
            if started_at and started_at >= since_7d:
                metrics_map[path_id]['outage_count_7d'] += 1
            if ended_at:
                previous = latest_ended.get(path_id)
                if previous is None or ended_at > previous:
                    latest_ended[path_id] = ended_at
                    metrics_map[path_id]['last_outage_duration_sec'] = row.get('duration_sec')

        for path_id, row in metrics_map.items():
            s24 = row['samples_24h']
            s7 = row['samples_7d']
            row['uptime_24h_pct'] = round((row['up_24h'] / s24) * 100.0, 2) if s24 else None
            row['uptime_7d_pct'] = round((row['up_7d'] / s7) * 100.0, 2) if s7 else None
        return metrics_map

    def _attach_indicators(self, payload):
        if isinstance(payload, list):
            ids = [item['id'] for item in payload]
            indicators = self._collect_indicators(ids)
            for item in payload:
                item.update(indicators.get(item['id'], {}))
            return payload
        if isinstance(payload, dict) and payload.get('id'):
            indicators = self._collect_indicators([payload['id']])
            payload.update(indicators.get(payload['id'], {}))
            return payload
        return payload

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = self._attach_indicators(list(serializer.data))
            return self.get_paginated_response(data)
        serializer = self.get_serializer(queryset, many=True)
        data = self._attach_indicators(list(serializer.data))
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = self._attach_indicators(dict(serializer.data))
        return Response(data)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def probe(self, request):
        path_id_raw = request.data.get('path_id')
        path_ids_raw = request.data.get('path_ids')
        save_metrics = request.data.get('save_metrics', True)
        respect_interval = request.data.get('respect_interval', False)
        path_id = None
        path_ids = None

        if path_id_raw not in (None, ''):
            try:
                path_id = int(path_id_raw)
            except (TypeError, ValueError):
                return Response({"detail": "path_id must be integer"}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(path_ids_raw, list):
            path_ids = []
            for raw in path_ids_raw:
                parsed = self._to_int(raw)
                if parsed is None:
                    return Response({"detail": "path_ids must contain integers"}, status=status.HTTP_400_BAD_REQUEST)
                path_ids.append(parsed)

        if isinstance(save_metrics, str):
            save_metrics = save_metrics.strip().lower() not in ('0', 'false', 'no')
        else:
            save_metrics = bool(save_metrics)

        if isinstance(respect_interval, str):
            respect_interval = respect_interval.strip().lower() in ('1', 'true', 'yes')
        else:
            respect_interval = bool(respect_interval)

        stats = run_network_probe(
            path_id=path_id,
            path_ids=path_ids,
            save_metrics=save_metrics,
            respect_interval=respect_interval,
        )
        return Response(stats, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def bulk_update(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "ids must be non-empty list"}, status=status.HTTP_400_BAD_REQUEST)

        allowed_fields = ['enabled', 'interval_sec', 'timeout_sec', 'packet_count', 'fail_threshold', 'recover_threshold']
        update_payload = {field: request.data[field] for field in allowed_fields if field in request.data}
        if not update_payload:
            return Response({"detail": "No update fields provided"}, status=status.HTTP_400_BAD_REQUEST)

        paths = list(NetworkPath.objects.filter(id__in=ids).select_related('src_device', 'dst_device'))
        if not paths:
            return Response({"detail": "No paths found"}, status=status.HTTP_404_NOT_FOUND)

        updated = 0
        errors = []
        with transaction.atomic():
            for path in paths:
                serializer = self.get_serializer(path, data=update_payload, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    updated += 1
                else:
                    errors.append({'id': path.id, 'errors': serializer.errors})

        return Response({'updated': updated, 'errors': errors}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def generate_template(self, request):
        template = (request.data.get('template') or '').strip().lower()
        update_existing = self._to_bool(request.data.get('update_existing'), False)
        defaults = request.data.get('defaults') if isinstance(request.data.get('defaults'), dict) else {}

        src_ids = request.data.get('src_device_ids') or []
        dst_ids = request.data.get('dst_device_ids') or []

        devices = list(Device.objects.select_related('device_type').all())
        devices_by_id = {d.id: d for d in devices}

        if template == 'custom':
            src_devices = [devices_by_id.get(self._to_int(i)) for i in src_ids]
            dst_devices = [devices_by_id.get(self._to_int(i)) for i in dst_ids]
            src_devices = [d for d in src_devices if d]
            dst_devices = [d for d in dst_devices if d]
        elif template == 'servers_to_gateways':
            src_devices = [d for d in devices if self._is_server_device(d)]
            dst_devices = [d for d in devices if self._is_gateway_device(d)]
        elif template == 'servers_to_routers':
            src_devices = [d for d in devices if self._is_server_device(d)]
            dst_devices = [d for d in devices if self._is_router_device(d)]
        elif template == 'routers_to_gateways':
            src_devices = [d for d in devices if self._is_router_device(d)]
            dst_devices = [d for d in devices if self._is_gateway_device(d)]
        else:
            return Response(
                {"detail": "Unsupported template. Use custom|servers_to_gateways|servers_to_routers|routers_to_gateways"},
                status=status.HTTP_400_BAD_REQUEST
            )

        sane_defaults = {
            'enabled': self._to_bool(defaults.get('enabled'), True),
            'interval_sec': self._to_int(defaults.get('interval_sec'), 60),
            'timeout_sec': self._to_int(defaults.get('timeout_sec'), 3),
            'packet_count': self._to_int(defaults.get('packet_count'), 1),
            'fail_threshold': self._to_int(defaults.get('fail_threshold'), 3),
            'recover_threshold': self._to_int(defaults.get('recover_threshold'), 2),
        }

        created = 0
        updated = 0
        skipped = 0
        errors = []
        for src in src_devices:
            for dst in dst_devices:
                if src.id == dst.id:
                    skipped += 1
                    continue
                existing = NetworkPath.objects.filter(src_device=src, dst_device=dst).first()
                if existing:
                    if not update_existing:
                        skipped += 1
                        continue
                    serializer = self.get_serializer(existing, data=sane_defaults, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        updated += 1
                    else:
                        errors.append({'src': src.id, 'dst': dst.id, 'errors': serializer.errors})
                    continue

                serializer = self.get_serializer(data={
                    'src_device': src.id,
                    'dst_device': dst.id,
                    **sane_defaults,
                })
                if serializer.is_valid():
                    serializer.save()
                    created += 1
                else:
                    errors.append({'src': src.id, 'dst': dst.id, 'errors': serializer.errors})

        return Response(
            {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors[:30]},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission])
    def matrix(self, request):
        include_disabled = self._to_bool(request.query_params.get('include_disabled'), False)
        paths_qs = NetworkPath.objects.select_related('src_device', 'dst_device')
        if not include_disabled:
            paths_qs = paths_qs.filter(enabled=True)

        paths = list(paths_qs.order_by('src_device__name', 'dst_device__name'))
        serialized = self.get_serializer(paths, many=True).data
        enriched = self._attach_indicators(list(serialized))

        src_map = {}
        dst_map = {}
        for item in enriched:
            src_map[item['src_device']] = {'id': item['src_device'], 'name': item.get('src_device_name') or str(item['src_device'])}
            dst_map[item['dst_device']] = {'id': item['dst_device'], 'name': item.get('dst_device_name') or str(item['dst_device'])}

        path_by_pair = {(item['src_device'], item['dst_device']): item for item in enriched}
        destinations = [dst_map[key] for key in sorted(dst_map, key=lambda x: dst_map[x]['name'])]

        rows = []
        for src_id in sorted(src_map, key=lambda x: src_map[x]['name']):
            cells = []
            for dst in destinations:
                item = path_by_pair.get((src_id, dst['id']))
                if item:
                    cells.append({
                        'dst_device_id': dst['id'],
                        'path_id': item['id'],
                        'state': item['last_state'],
                        'latency_ms': item['last_latency_ms'],
                        'packet_loss_pct': item['last_packet_loss_pct'],
                        'uptime_24h_pct': item.get('uptime_24h_pct'),
                        'uptime_7d_pct': item.get('uptime_7d_pct'),
                    })
                else:
                    cells.append({
                        'dst_device_id': dst['id'],
                        'path_id': None,
                        'state': 'none',
                        'latency_ms': None,
                        'packet_loss_pct': None,
                        'uptime_24h_pct': None,
                        'uptime_7d_pct': None,
                    })
            rows.append({
                'src_device_id': src_id,
                'src_device_name': src_map[src_id]['name'],
                'cells': cells,
            })

        return Response({
            'sources': [src_map[key] for key in sorted(src_map, key=lambda x: src_map[x]['name'])],
            'destinations': destinations,
            'rows': rows,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission])
    def derived(self, request):
        rows = get_network_derived_snapshot()
        return Response(rows, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], permission_classes=[AdminGroupPermission])
    def history(self, request, pk=None):
        path = self.get_object()
        since_hours = self._to_int(request.query_params.get('since_hours'), 24)
        since_hours = min(max(1, since_hours), 24 * 30)
        since = timezone.now() - timedelta(hours=since_hours)

        rows = (
            RawMetric.objects
            .filter(
                device=path.src_device,
                code__in=['net_path_reachable', 'ping_latency_matrix', 'ping_packet_loss_matrix'],
                timestamp__gte=since,
            )
            .values('code', 'value', 'timestamp', 'labels')
            .order_by('timestamp')
        )
        series = defaultdict(list)
        for row in rows:
            labels = row.get('labels') or {}
            path_id = self._to_int(labels.get('path_id'))
            if path_id != path.id:
                continue
            series[row['code']].append({
                'timestamp': row['timestamp'],
                'value': float(row['value']),
            })

        return Response({
            'path': path.id,
            'src_device': path.src_device.name,
            'dst_device': path.dst_device.name,
            'series': {
                'reachable': series.get('net_path_reachable', []),
                'latency_ms': series.get('ping_latency_matrix', []),
                'packet_loss_pct': series.get('ping_packet_loss_matrix', []),
            },
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def evaluate_alerts(self, request):
        recompute = self._to_bool(request.data.get('recompute'), True)
        ensure_defaults = self._to_bool(request.data.get('ensure_defaults'), False)
        if ensure_defaults:
            ensure_default_network_alert_rules()
        if recompute:
            call_command('compute_derived_metrics')
        payload = evaluate_network_alert_rules()
        return Response(payload, status=status.HTTP_200_OK)


class NetworkOutageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NetworkOutage.objects.all().select_related('path', 'path__src_device', 'path__dst_device')
    serializer_class = NetworkOutageSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['path', 'is_active', 'path__src_device', 'path__dst_device']
    ordering_fields = ['started_at', 'ended_at', 'duration_sec', 'created_at']
    ordering = ['-started_at']

    def get_queryset(self):
        qs = super().get_queryset()
        since_days = self.request.query_params.get('since_days')
        since_hours = self.request.query_params.get('since_hours')
        if since_days:
            try:
                days = int(since_days)
                if days > 0:
                    qs = qs.filter(started_at__gte=timezone.now() - timedelta(days=days))
            except ValueError:
                pass
        elif since_hours:
            try:
                hours = int(since_hours)
                if hours > 0:
                    qs = qs.filter(started_at__gte=timezone.now() - timedelta(hours=hours))
            except ValueError:
                pass
        return qs


class NetworkAlertRuleViewSet(viewsets.ModelViewSet):
    queryset = NetworkAlertRule.objects.all()
    serializer_class = NetworkAlertRuleSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['enabled', 'severity', 'metric_code', 'window']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['order', 'code', 'updated_at']
    ordering = ['order', 'code']

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def seed_defaults(self, request):
        raw = request.data.get('overwrite')
        if raw is None:
            overwrite = True
        elif isinstance(raw, bool):
            overwrite = raw
        else:
            overwrite = str(raw).strip().lower() in ('1', 'true', 'yes', 'y', 'on')
        stats = ensure_default_network_alert_rules(overwrite=overwrite)
        return Response(stats, status=status.HTTP_200_OK)


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
