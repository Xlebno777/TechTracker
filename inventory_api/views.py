import qrcode
import logging
import io
import ipaddress
import re
import uuid
import json
import csv
import shutil
import os
import secrets
import time as pytime
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlsplit
from django.http import HttpResponse, StreamingHttpResponse, FileResponse
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
from django.conf import settings

from .models import (
    Device, DeviceType, Location, UserProfile,
    ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs,
    Cartridge, CartridgeLog, Log, Metric, PrintJob,
    MonitoringSetting, RawMetric, TrackedVM, ComputedMetric, AgentStatus, DiagnosticReport,
    NetworkPath, NetworkOutage, NetworkAlertRule,
    NetworkMapSnapshot, ForecastRun, ForecastPoint, StateEstimate, StateInferenceProfile, LSTMRemoteQueueJob,
    DecisionAction, DecisionCriterion, DecisionPolicy, DecisionPolicyLoss, DecisionRun,
    ApplicationUpdateJob,
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
    NetworkAlertRuleSerializer, NetworkMapSnapshotSerializer, NetworkMapSnapshotDetailSerializer,
    ForecastRunSerializer, ForecastPointSerializer, StateEstimateSerializer, StateInferenceProfileSerializer, LSTMRemoteQueueJobSerializer,
    DecisionActionSerializer, DecisionCriterionSerializer, DecisionPolicySerializer, DecisionRunSerializer,
    DecisionPolicyLossSerializer,
    DecisionRecommendationRequestSerializer, DecisionAHPMatrixUpsertSerializer, DecisionFeedbackCreateSerializer,
    ApplicationUpdateJobSerializer,
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
from .network_map_builder import build_network_map_snapshot
from .forecasting.demo_seed import seed_demo_forecasts
from .release_management import check_for_update, get_current_release_info, launch_update_worker
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from datetime import timedelta, datetime


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


def _parse_query_datetime(value, *, end_of_day=False):
    if value in (None, ""):
        return None
    dt_value = None
    if isinstance(value, datetime):
        dt_value = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        dt_value = parse_datetime(raw)
        if dt_value is None:
            parsed_date = parse_date(raw)
            if parsed_date is None:
                return None
            dt_value = datetime.combine(parsed_date, datetime.max.time() if end_of_day else datetime.min.time())
    if timezone.is_naive(dt_value):
        dt_value = timezone.make_aware(dt_value, timezone.get_current_timezone())
    return dt_value


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
        mac_values = [
            normalized for normalized in (
                _normalize_mac(item.get('mac_address')) for item in items if item.get('mac_address')
            ) if normalized
        ]
        existing_by_ip = {
            device.ip_address: device
            for device in Device.objects.filter(ip_address__in=ip_values)
        } if ip_values else {}
        existing_by_mac = {
            str(device.mac_address).upper().replace('-', ':'): device
            for device in Device.objects.filter(mac_address__in=mac_values)
            if device.mac_address
        } if mac_values else {}

        ip_updated_count = 0

        for item in items:
            existing = None
            matched_by = None
            ip_address = item.get('ip_address')
            mac_address = _normalize_mac(item.get('mac_address'))
            existing_ip = existing_by_ip.get(ip_address) if ip_address else None
            existing_mac = existing_by_mac.get(mac_address) if mac_address else None

            if existing_mac is not None:
                existing = existing_mac
                matched_by = 'mac'
            elif existing_ip is not None:
                existing = existing_ip
                matched_by = 'ip'

            if existing:
                # Если IP изменился, но MAC совпал — обновляем IP найденного устройства.
                if matched_by == 'mac' and ip_address and existing.ip_address != ip_address:
                    conflict = Device.objects.filter(ip_address=ip_address).exclude(id=existing.id).first()
                    if conflict is None:
                        old_ip = existing.ip_address
                        existing.ip_address = ip_address
                        existing.save(update_fields=['ip_address', 'updated_at'])
                        ip_updated_count += 1
                        item['ip_updated'] = True
                        item['old_ip_address'] = old_ip
                        if old_ip and old_ip in existing_by_ip and existing_by_ip[old_ip].id == existing.id:
                            del existing_by_ip[old_ip]
                        existing_by_ip[ip_address] = existing
                    else:
                        item['ip_updated'] = False
                        item['ip_update_conflict_device_id'] = conflict.id
                else:
                    item['ip_updated'] = False
                item['existing_device_id'] = existing.id
                item['existing_device_name'] = existing.name
                item['existing_serial_number'] = existing.serial_number
                item['matched_by'] = matched_by
            else:
                item['existing_device_id'] = None
                item['existing_device_name'] = None
                item['existing_serial_number'] = None
                item['matched_by'] = None
                item['ip_updated'] = False

        return Response({
            "cidr": scan_result.get('cidr'),
            "host_count": scan_result.get('host_count'),
            "alive_count": scan_result.get('alive_count'),
            "ip_updated_count": ip_updated_count,
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
        date_from = _parse_query_datetime(self.request.query_params.get('date_from'))
        date_to = _parse_query_datetime(self.request.query_params.get('date_to'), end_of_day=True)
        if since_minutes:
            try:
                minutes = int(since_minutes)
                if minutes > 0:
                    qs = qs.filter(timestamp__gte=timezone.now() - timedelta(minutes=minutes))
            except ValueError:
                pass
        if date_from is not None:
            qs = qs.filter(timestamp__gte=date_from)
        if date_to is not None:
            qs = qs.filter(timestamp__lte=date_to)
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


class ForecastRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ForecastRun.objects.all().select_related('device')
    serializer_class = ForecastRunSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'model_kind', 'status']
    ordering_fields = ['created_at', 'started_at', 'finished_at', 'updated_at']
    ordering = ['-created_at']

    def _find_run(self, run_id: int | None, serial: str | None, model_kind: str):
        qs = ForecastRun.objects.filter(model_kind=model_kind).select_related("device")
        if run_id:
            return qs.filter(id=run_id).first()
        if serial:
            return qs.filter(device__serial_number=serial).order_by("-created_at").first()
        return None

    def _find_queue_job(self, lstm_run_id: int | None, serial: str | None):
        qs = LSTMRemoteQueueJob.objects.all().select_related("device", "forecast_run")
        if lstm_run_id:
            return qs.filter(forecast_run_id=lstm_run_id).order_by("-created_at").first()
        if serial:
            return qs.filter(device__serial_number=serial).order_by("-created_at").first()
        return None

    def _normalize_lstm_status(self, lstm_run: ForecastRun | None, queue_job: LSTMRemoteQueueJob | None):
        queue_status = str(getattr(queue_job, "status", "") or "").lower()
        if queue_status == "success":
            return "completed"
        if queue_status == "failed":
            return "failed"
        if queue_status in ("queued", "retry_wait"):
            return "queued"
        if queue_status in ("submitting", "submitted", "polling"):
            return "running"

        run_status = str(getattr(lstm_run, "status", "") or "").lower()
        if run_status == "success":
            return "completed"
        if run_status == "failed":
            return "failed"
        if run_status in ("pending",):
            return "queued"
        if run_status in ("running",):
            return "running"
        return "none"

    def _run_brief(self, run: ForecastRun | None):
        if not run:
            return None
        return {
            "id": run.id,
            "model_kind": run.model_kind,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "horizon_set": run.horizon_set,
            "quality": run.quality if isinstance(run.quality, dict) else {},
            "parameters": run.parameters if isinstance(run.parameters, dict) else {},
        }

    def _queue_brief(self, queue_job: LSTMRemoteQueueJob | None):
        if not queue_job:
            return None
        return {
            "id": queue_job.id,
            "status": queue_job.status,
            "remote_job_id": queue_job.remote_job_id,
            "retry_count": queue_job.retry_count,
            "attempts_submit": queue_job.attempts_submit,
            "attempts_poll": queue_job.attempts_poll,
            "last_error": queue_job.last_error,
            "updated_at": queue_job.updated_at.isoformat() if queue_job.updated_at else None,
        }

    def _build_stream_snapshot(
        self,
        *,
        mode: str,
        sarima_run: ForecastRun | None,
        lstm_run: ForecastRun | None,
        ensemble_run: ForecastRun | None,
        queue_job: LSTMRemoteQueueJob | None,
        started_at: float,
        poll_error: str | None = None,
    ):
        now_iso = timezone.now().isoformat()
        elapsed_sec = max(0.0, pytime.monotonic() - started_at)
        lstm_status = self._normalize_lstm_status(lstm_run, queue_job)

        if mode == "full":
            steps = [
                {"key": "sarima", "title": "SARIMA baseline", "description": "Локальная предобработка и SARIMA."},
                {"key": "lstm", "title": "Удаленный LSTM", "description": "Очередь, удаленный расчет и импорт результата."},
                {"key": "ensemble", "title": "Интеграция итогового прогноза", "description": "Сборка оркестра SARIMA+LSTM."},
            ]

            if sarima_run is None:
                current_key = "sarima"
                status = "queued"
            elif sarima_run.status in ("pending", "running"):
                current_key = "sarima"
                status = "running"
            elif sarima_run.status == "failed":
                current_key = "sarima"
                status = "failed"
            elif lstm_status in ("none", "queued", "running"):
                current_key = "lstm"
                status = "running"
            elif lstm_status == "failed":
                current_key = "lstm"
                status = "failed"
            elif ensemble_run is None:
                current_key = "ensemble"
                status = "running"
            elif ensemble_run.status in ("pending", "running"):
                current_key = "ensemble"
                status = "running"
            elif ensemble_run.status == "failed":
                current_key = "ensemble"
                status = "failed"
            else:
                current_key = "ensemble"
                status = "completed"

            if status == "completed":
                final_run = ensemble_run or lstm_run or sarima_run
            elif status == "failed":
                final_run = ensemble_run if current_key == "ensemble" else (lstm_run if current_key == "lstm" else sarima_run)
            else:
                final_run = None

        elif mode == "lstm":
            steps = [
                {"key": "lstm", "title": "Удаленный LSTM", "description": "Очередь, удаленный расчет и импорт результата."},
            ]
            current_key = "lstm"
            if lstm_status in ("queued", "running"):
                status = "running"
            elif lstm_status == "failed":
                status = "failed"
            elif lstm_status == "completed":
                status = "completed"
            else:
                status = "queued"
            final_run = lstm_run if status in ("completed", "failed") else None

        else:
            steps = [
                {"key": "sarima", "title": "SARIMA baseline", "description": "Локальная предобработка и SARIMA."},
            ]
            current_key = "sarima"
            if sarima_run is None:
                status = "queued"
            elif sarima_run.status in ("pending", "running"):
                status = "running"
            elif sarima_run.status == "failed":
                status = "failed"
            else:
                status = "completed"
            final_run = sarima_run if status in ("completed", "failed") else None

        current_index = 1
        for idx, item in enumerate(steps, start=1):
            if item["key"] == current_key:
                current_index = idx
                break

        final_quality = {}
        if final_run and isinstance(final_run.quality, dict):
            final_quality = final_run.quality
        sarima_quality = sarima_run.quality if sarima_run and isinstance(sarima_run.quality, dict) else {}
        lstm_quality = lstm_run.quality if lstm_run and isinstance(lstm_run.quality, dict) else {}
        summary = {
            "duration_sec": elapsed_sec,
            "metrics_processed": (
                final_quality.get("metrics_processed")
                or sarima_quality.get("metrics_processed")
                or lstm_quality.get("metrics_processed")
                or (lstm_quality.get("remote_quality") or {}).get("metrics_processed")
            ),
            "history_points_total": (
                final_quality.get("history_points_total")
                or sarima_quality.get("history_points_total")
                or lstm_quality.get("history_points_total")
                or (lstm_quality.get("remote_quality") or {}).get("history_points_total")
            ),
            "points_created": (
                final_quality.get("points_created")
                or sarima_quality.get("points_created")
                or lstm_quality.get("points_created")
            ),
            "states_created": (
                final_quality.get("states_created")
                or sarima_quality.get("states_created")
                or lstm_quality.get("states_created")
            ),
            "horizon_set": getattr(final_run, "horizon_set", None),
        }

        return {
            "mode": mode,
            "status": status,
            "timestamp": now_iso,
            "current_step": {
                "key": current_key,
                "index": current_index,
                "total": len(steps),
            },
            "steps": steps,
            "runs": {
                "sarima": self._run_brief(sarima_run),
                "lstm": self._run_brief(lstm_run),
                "ensemble": self._run_brief(ensemble_run),
            },
            "queue_job": self._queue_brief(queue_job),
            "summary": summary,
            "poll_error": poll_error,
        }

    def _stream_message(self, payload: dict):
        return f"{json.dumps(payload, ensure_ascii=False)}\n"

    @action(detail=False, methods=['get'])
    def latest(self, request):
        serial = request.query_params.get('serial')
        device_id = request.query_params.get('device')
        model_kind = request.query_params.get('model_kind')

        qs = self.filter_queryset(self.get_queryset())
        if serial:
            device = Device.objects.filter(serial_number=serial).first()
            if not device:
                return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(device=device)
        if device_id:
            qs = qs.filter(device_id=device_id)
        if model_kind:
            qs = qs.filter(model_kind=model_kind)

        row = qs.order_by('-created_at').first()
        if not row:
            return Response({"detail": "Forecast run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission], url_path='workflow_stream')
    def workflow_stream(self, request):
        mode = str(request.query_params.get("mode") or "full").strip().lower()
        if mode not in ("full", "lstm", "sarima"):
            mode = "full"

        serial = str(request.query_params.get("serial") or "").strip() or None
        try:
            sarima_run_id = int(request.query_params.get("sarima_run_id")) if request.query_params.get("sarima_run_id") else None
        except (TypeError, ValueError):
            sarima_run_id = None
        try:
            lstm_run_id = int(request.query_params.get("lstm_run_id")) if request.query_params.get("lstm_run_id") else None
        except (TypeError, ValueError):
            lstm_run_id = None
        try:
            ensemble_run_id = int(request.query_params.get("ensemble_run_id")) if request.query_params.get("ensemble_run_id") else None
        except (TypeError, ValueError):
            ensemble_run_id = None

        try:
            poll_interval_sec = max(1.0, float(request.query_params.get("poll_interval_sec", 2.0)))
        except (TypeError, ValueError):
            poll_interval_sec = 2.0
        try:
            max_wait_sec = max(5.0, float(request.query_params.get("max_wait_sec", 600.0)))
        except (TypeError, ValueError):
            max_wait_sec = 600.0

        if not serial and not any([sarima_run_id, lstm_run_id, ensemble_run_id]):
            return Response(
                {"detail": "serial or run_id parameters are required for workflow_stream"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        def event_generator():
            started = pytime.monotonic()
            while True:
                poll_error = None
                try:
                    if mode == "full":
                        from .forecasting.orchestration_service import poll_orchestrated_forecasts
                        poll_orchestrated_forecasts(
                            run_id=lstm_run_id,
                            serial=serial,
                            limit=20,
                            poll_interval_sec=poll_interval_sec,
                        )
                    elif mode == "lstm":
                        from .forecasting.lstm_remote_service import poll_lstm_remote_runs
                        poll_lstm_remote_runs(
                            run_id=lstm_run_id,
                            serial=serial,
                            limit=20,
                            poll_interval_sec=poll_interval_sec,
                        )
                except Exception as exc:
                    poll_error = str(exc)

                sarima_run = self._find_run(sarima_run_id, serial, "sarima")
                lstm_run = self._find_run(lstm_run_id, serial, "lstm")

                ensemble_from_lstm = None
                if lstm_run and isinstance(lstm_run.parameters, dict):
                    ensemble_from_lstm = lstm_run.parameters.get("ensemble_run_id")
                resolved_ensemble_id = ensemble_run_id or ensemble_from_lstm
                ensemble_run = self._find_run(
                    int(resolved_ensemble_id) if resolved_ensemble_id else None,
                    serial,
                    "ensemble",
                )
                queue_job = self._find_queue_job(lstm_run.id if lstm_run else lstm_run_id, serial)

                snapshot = self._build_stream_snapshot(
                    mode=mode,
                    sarima_run=sarima_run,
                    lstm_run=lstm_run,
                    ensemble_run=ensemble_run,
                    queue_job=queue_job,
                    started_at=started,
                    poll_error=poll_error,
                )

                if poll_error:
                    snapshot["event"] = "poll_error"
                else:
                    snapshot["event"] = "progress"

                yield self._stream_message(snapshot)

                if snapshot["status"] in ("completed", "failed"):
                    done_payload = dict(snapshot)
                    done_payload["event"] = "done"
                    yield self._stream_message(done_payload)
                    break

                if (pytime.monotonic() - started) >= max_wait_sec:
                    timeout_payload = dict(snapshot)
                    timeout_payload["event"] = "timeout"
                    timeout_payload["status"] = "timeout"
                    timeout_payload["summary"] = {
                        **(timeout_payload.get("summary") or {}),
                        "duration_sec": pytime.monotonic() - started,
                    }
                    yield self._stream_message(timeout_payload)
                    break

                pytime.sleep(poll_interval_sec)

        response = StreamingHttpResponse(event_generator(), content_type="application/x-ndjson; charset=utf-8")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def seed_demo(self, request):
        serial = request.data.get('serial')
        runs_raw = request.data.get('runs', 1)
        clear_raw = request.data.get('clear', False)
        with_raw_raw = request.data.get('with_raw_history', True)
        raw_history_days_raw = request.data.get('raw_history_days', 30)
        history_start_date_raw = request.data.get('history_start_date')
        history_end_date_raw = request.data.get('history_end_date')
        profile_code = str(request.data.get('profile_code') or 'office_weekday').strip().lower() or 'office_weekday'
        schedule_config = {
            'workday_start': request.data.get('workday_start'),
            'workday_end': request.data.get('workday_end'),
            'lunch_start': request.data.get('lunch_start'),
            'lunch_end': request.data.get('lunch_end'),
            'backup_start': request.data.get('backup_start'),
            'backup_end': request.data.get('backup_end'),
            'workdays': request.data.get('workdays'),
            'backup_days': request.data.get('backup_days'),
        }
        scenario_config = {
            'degraded_metric_codes': request.data.get('degraded_metric_codes'),
            'degradation_strength': request.data.get('degradation_strength'),
            'bad_mode_persistence': request.data.get('bad_mode_persistence'),
        }

        try:
            runs = int(runs_raw)
        except (TypeError, ValueError):
            runs = 1
        runs = max(1, min(runs, 50))

        if isinstance(clear_raw, str):
            clear_existing = clear_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            clear_existing = bool(clear_raw)

        if isinstance(with_raw_raw, str):
            with_raw_history = with_raw_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            with_raw_history = bool(with_raw_raw)
        try:
            raw_history_days = max(1, int(raw_history_days_raw))
        except (TypeError, ValueError):
            raw_history_days = 30

        history_start_at = None
        history_end_at = None
        start_date = parse_date(str(history_start_date_raw)) if history_start_date_raw else None
        end_date = parse_date(str(history_end_date_raw)) if history_end_date_raw else None
        tz = timezone.get_current_timezone()
        if start_date:
            history_start_at = timezone.make_aware(datetime.combine(start_date, datetime.min.time()), tz)
        if end_date:
            history_end_at = timezone.make_aware(datetime.combine(end_date, datetime.min.time().replace(hour=23, minute=45)), tz)

        payload = seed_demo_forecasts(
            serial=serial,
            runs=runs,
            clear_existing=clear_existing,
            with_raw_history=with_raw_history,
            raw_history_days=raw_history_days,
            history_start_at=history_start_at,
            history_end_at=history_end_at,
            profile_code=profile_code,
            schedule_config=schedule_config,
            scenario_config=scenario_config,
        )
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def run_baseline(self, request):
        serial = request.data.get('serial')
        lookback_raw = request.data.get('lookback_days', 60)
        freq = request.data.get('freq', '1h')
        horizons_raw = request.data.get('horizons', '24h,7d,30d')
        metric_codes_raw = request.data.get('metric_codes', '')
        save_stl_raw = request.data.get('save_stl_components', True)
        seasonality_mode = request.data.get('seasonality_mode')

        try:
            lookback_days = max(1, int(lookback_raw))
        except (TypeError, ValueError):
            lookback_days = 60

        if isinstance(horizons_raw, list):
            horizons = [str(h).strip() for h in horizons_raw if str(h).strip()]
        else:
            horizons = [h.strip() for h in str(horizons_raw or '').split(',') if h.strip()]

        if isinstance(metric_codes_raw, list):
            metric_codes = [str(m).strip() for m in metric_codes_raw if str(m).strip()]
        else:
            metric_codes = [m.strip() for m in str(metric_codes_raw or '').split(',') if m.strip()]

        if isinstance(save_stl_raw, str):
            save_stl_components = save_stl_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            save_stl_components = bool(save_stl_raw)

        try:
            from .forecasting.baseline_service import run_baseline_forecasts
            payload = run_baseline_forecasts(
                serial=serial,
                lookback_days=lookback_days,
                freq=str(freq or '1h'),
                horizons=horizons or None,
                metric_codes=metric_codes or None,
                save_stl_components=save_stl_components,
                seasonality_mode=seasonality_mode,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"detail": f"baseline failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def run_lstm_remote(self, request):
        serial = request.data.get('serial')
        lookback_raw = request.data.get('lookback_days', 60)
        freq = request.data.get('freq', '1h')
        horizons_raw = request.data.get('horizons', '24h,7d,30d')
        metric_codes_raw = request.data.get('metric_codes', '')
        model_options_raw = request.data.get('lstm_options')
        no_wait_raw = request.data.get('no_wait', False)
        poll_interval_raw = request.data.get('poll_interval_sec', 2.0)
        max_wait_raw = request.data.get('max_wait_sec', 120.0)
        max_retries_raw = request.data.get('max_retries', 5)

        try:
            lookback_days = max(1, int(lookback_raw))
        except (TypeError, ValueError):
            lookback_days = 60

        if isinstance(horizons_raw, list):
            horizons = [str(h).strip() for h in horizons_raw if str(h).strip()]
        else:
            horizons = [h.strip() for h in str(horizons_raw or '').split(',') if h.strip()]

        if isinstance(metric_codes_raw, list):
            metric_codes = [str(m).strip() for m in metric_codes_raw if str(m).strip()]
        else:
            metric_codes = [m.strip() for m in str(metric_codes_raw or '').split(',') if m.strip()]

        if isinstance(no_wait_raw, str):
            no_wait = no_wait_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            no_wait = bool(no_wait_raw)

        try:
            poll_interval_sec = max(0.5, float(poll_interval_raw))
        except (TypeError, ValueError):
            poll_interval_sec = 2.0
        try:
            max_wait_sec = max(1.0, float(max_wait_raw))
        except (TypeError, ValueError):
            max_wait_sec = 120.0
        try:
            max_retries = max(0, int(max_retries_raw))
        except (TypeError, ValueError):
            max_retries = 5

        model_options = model_options_raw if isinstance(model_options_raw, dict) else None

        try:
            from .forecasting.lstm_remote_service import run_lstm_remote_forecasts
            payload = run_lstm_remote_forecasts(
                serial=serial,
                lookback_days=lookback_days,
                freq=str(freq or '1h'),
                horizons=horizons or None,
                metric_codes=metric_codes or None,
                wait_for_result=not no_wait,
                poll_interval_sec=poll_interval_sec,
                max_wait_sec=max_wait_sec,
                max_retries=max_retries,
                model_options=model_options,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"detail": f"lstm remote failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def poll_lstm_remote(self, request):
        run_id_raw = request.data.get('run_id')
        serial = request.data.get('serial')
        limit_raw = request.data.get('limit', 20)
        poll_interval_raw = request.data.get('poll_interval_sec', 10.0)

        run_id = None
        if run_id_raw not in (None, ''):
            try:
                run_id = int(run_id_raw)
            except (TypeError, ValueError):
                return Response({"detail": "Invalid run_id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = 20
        try:
            poll_interval_sec = max(1.0, float(poll_interval_raw))
        except (TypeError, ValueError):
            poll_interval_sec = 10.0

        try:
            from .forecasting.lstm_remote_service import poll_lstm_remote_runs
            payload = poll_lstm_remote_runs(
                run_id=run_id,
                serial=serial,
                limit=limit,
                poll_interval_sec=poll_interval_sec,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"detail": f"lstm remote poll failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission])
    def orchestrator_defaults(self, request):
        try:
            from .forecasting.orchestration_service import _default_ensemble_beta, _default_ensemble_weights
            from .forecasting.state_inference_service import get_active_state_inference_profile_config, get_orchestrator_controls_config
            profile_config = get_active_state_inference_profile_config()
            return Response({
                "ensemble_beta": _default_ensemble_beta(),
                "ensemble_weights": _default_ensemble_weights(),
                "orchestrator_controls": get_orchestrator_controls_config(config=profile_config),
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"detail": f"orchestrator defaults failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def run_orchestrated(self, request):
        serial = request.data.get('serial')
        sarima_lookback_raw = request.data.get('sarima_lookback_days', request.data.get('lookback_days', 60))
        lstm_lookback_raw = request.data.get('lstm_lookback_days', request.data.get('lookback_days', 60))
        sarima_freq = request.data.get('sarima_freq', request.data.get('freq', '1h'))
        lstm_freq = request.data.get('lstm_freq', request.data.get('freq', '1h'))
        sarima_seasonality_mode = request.data.get('sarima_seasonality_mode', request.data.get('seasonality_mode'))
        horizons_raw = request.data.get('horizons', '24h,7d,30d')
        metric_codes_raw = request.data.get('metric_codes', '')
        save_stl_raw = request.data.get('save_stl_components', True)
        wait_raw = request.data.get('wait_for_lstm', False)
        poll_interval_raw = request.data.get('poll_interval_sec', 2.0)
        max_wait_raw = request.data.get('max_wait_sec', 120.0)
        max_retries_raw = request.data.get('max_retries', 5)
        ensemble_beta_raw = request.data.get('ensemble_beta')
        ensemble_sarima_weight_raw = request.data.get('ensemble_sarima_weight')
        ensemble_lstm_weight_raw = request.data.get('ensemble_lstm_weight')
        lstm_options_raw = request.data.get('lstm_options')

        try:
            sarima_lookback_days = max(1, int(sarima_lookback_raw))
        except (TypeError, ValueError):
            sarima_lookback_days = 60
        try:
            lstm_lookback_days = max(1, int(lstm_lookback_raw))
        except (TypeError, ValueError):
            lstm_lookback_days = 60

        if isinstance(horizons_raw, list):
            horizons = [str(h).strip() for h in horizons_raw if str(h).strip()]
        else:
            horizons = [h.strip() for h in str(horizons_raw or '').split(',') if h.strip()]

        if isinstance(metric_codes_raw, list):
            metric_codes = [str(m).strip() for m in metric_codes_raw if str(m).strip()]
        else:
            metric_codes = [m.strip() for m in str(metric_codes_raw or '').split(',') if m.strip()]

        if isinstance(save_stl_raw, str):
            save_stl_components = save_stl_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            save_stl_components = bool(save_stl_raw)

        if isinstance(wait_raw, str):
            wait_for_lstm = wait_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            wait_for_lstm = bool(wait_raw)

        try:
            poll_interval_sec = max(0.5, float(poll_interval_raw))
        except (TypeError, ValueError):
            poll_interval_sec = 2.0
        try:
            max_wait_sec = max(1.0, float(max_wait_raw))
        except (TypeError, ValueError):
            max_wait_sec = 120.0
        try:
            max_retries = max(0, int(max_retries_raw))
        except (TypeError, ValueError):
            max_retries = 5
        try:
            ensemble_beta = max(0.0, float(ensemble_beta_raw)) if ensemble_beta_raw not in (None, '') else None
        except (TypeError, ValueError):
            ensemble_beta = None
        try:
            ensemble_sarima_weight = max(0.0, float(ensemble_sarima_weight_raw)) if ensemble_sarima_weight_raw not in (None, '') else None
        except (TypeError, ValueError):
            ensemble_sarima_weight = None
        try:
            ensemble_lstm_weight = max(0.0, float(ensemble_lstm_weight_raw)) if ensemble_lstm_weight_raw not in (None, '') else None
        except (TypeError, ValueError):
            ensemble_lstm_weight = None

        lstm_model_options = lstm_options_raw if isinstance(lstm_options_raw, dict) else None

        ensemble_weights = None
        if ensemble_sarima_weight is not None or ensemble_lstm_weight is not None:
            ensemble_weights = {
                "sarima": ensemble_sarima_weight if ensemble_sarima_weight is not None else 0.5,
                "lstm": ensemble_lstm_weight if ensemble_lstm_weight is not None else 0.5,
            }

        try:
            from .forecasting.orchestration_service import run_orchestrated_forecasts
            payload = run_orchestrated_forecasts(
                serial=serial,
                sarima_lookback_days=sarima_lookback_days,
                lstm_lookback_days=lstm_lookback_days,
                sarima_freq=str(sarima_freq or '1h'),
                lstm_freq=str(lstm_freq or '1h'),
                horizons=horizons or None,
                metric_codes=metric_codes or None,
                save_stl_components=save_stl_components,
                sarima_seasonality_mode=sarima_seasonality_mode,
                wait_for_lstm=wait_for_lstm,
                poll_interval_sec=poll_interval_sec,
                max_wait_sec=max_wait_sec,
                max_retries=max_retries,
                ensemble_weights=ensemble_weights,
                ensemble_beta=ensemble_beta,
                lstm_model_options=lstm_model_options,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"detail": f"orchestrated forecast failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def poll_orchestrated(self, request):
        run_id_raw = request.data.get('run_id')
        serial = request.data.get('serial')
        limit_raw = request.data.get('limit', 20)
        poll_interval_raw = request.data.get('poll_interval_sec', 10.0)

        run_id = None
        if run_id_raw not in (None, ''):
            try:
                run_id = int(run_id_raw)
            except (TypeError, ValueError):
                return Response({"detail": "Invalid run_id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            limit = max(1, int(limit_raw))
        except (TypeError, ValueError):
            limit = 20
        try:
            poll_interval_sec = max(1.0, float(poll_interval_raw))
        except (TypeError, ValueError):
            poll_interval_sec = 10.0

        try:
            from .forecasting.orchestration_service import poll_orchestrated_forecasts
            payload = poll_orchestrated_forecasts(
                run_id=run_id,
                serial=serial,
                limit=limit,
                poll_interval_sec=poll_interval_sec,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response({"detail": f"orchestrated poll failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LSTMRemoteQueueJobViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LSTMRemoteQueueJob.objects.all().select_related('forecast_run', 'device')
    serializer_class = LSTMRemoteQueueJobSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['forecast_run', 'device', 'status']
    ordering_fields = ['created_at', 'updated_at', 'next_retry_at', 'retry_count', 'attempts_submit', 'attempts_poll']
    ordering = ['next_retry_at', '-id']

    @action(detail=False, methods=['get'])
    def latest(self, request):
        serial = request.query_params.get('serial')
        run_id = request.query_params.get('run_id')

        qs = self.filter_queryset(self.get_queryset())
        if serial:
            qs = qs.filter(device__serial_number=serial)
        if run_id:
            qs = qs.filter(forecast_run_id=run_id)

        row = qs.order_by('-created_at').first()
        if not row:
            return Response({"detail": "Queue job not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)


class ForecastPointViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ForecastPoint.objects.all().select_related('device', 'run')
    serializer_class = ForecastPointSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'metric_code', 'horizon', 'model_kind', 'run']
    ordering_fields = ['target_ts', 'created_at', 'y_hat']
    ordering = ['-target_ts', '-id']

    def get_queryset(self):
        qs = super().get_queryset()
        since_hours = self.request.query_params.get('since_hours')
        date_from = _parse_query_datetime(self.request.query_params.get('date_from'))
        date_to = _parse_query_datetime(self.request.query_params.get('date_to'), end_of_day=True)
        if since_hours:
            try:
                hours = int(since_hours)
                if hours > 0:
                    qs = qs.filter(target_ts__gte=timezone.now() - timedelta(hours=hours))
            except ValueError:
                pass
        if date_from is not None:
            qs = qs.filter(target_ts__gte=date_from)
        if date_to is not None:
            qs = qs.filter(target_ts__lte=date_to)
        return qs

    @action(detail=False, methods=['get'])
    def latest(self, request):
        serial = request.query_params.get('serial')
        device_id = request.query_params.get('device')
        metric_code = request.query_params.get('metric_code')
        horizon = request.query_params.get('horizon')

        qs = self.filter_queryset(self.get_queryset())
        if serial:
            device = Device.objects.filter(serial_number=serial).first()
            if not device:
                return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(device=device)
        if device_id:
            qs = qs.filter(device_id=device_id)
        if metric_code:
            qs = qs.filter(metric_code=metric_code)
        if horizon:
            qs = qs.filter(horizon=horizon)

        row = qs.order_by('-target_ts', '-id').first()
        if not row:
            return Response({"detail": "Forecast point not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)


class StateEstimateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StateEstimate.objects.all().select_related('device', 'run')
    serializer_class = StateEstimateSerializer
    permission_classes = [IsAuthenticated, DjangoModelPermissions]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'horizon', 'state', 'run']
    ordering_fields = ['timestamp', 'created_at', 'confidence']
    ordering = ['-timestamp', '-id']

    def get_queryset(self):
        qs = super().get_queryset()
        since_hours = self.request.query_params.get('since_hours')
        date_from = _parse_query_datetime(self.request.query_params.get('date_from'))
        date_to = _parse_query_datetime(self.request.query_params.get('date_to'), end_of_day=True)
        model_kind = self.request.query_params.get('model_kind')
        if since_hours:
            try:
                hours = int(since_hours)
                if hours > 0:
                    qs = qs.filter(timestamp__gte=timezone.now() - timedelta(hours=hours))
            except ValueError:
                pass
        if date_from is not None:
            qs = qs.filter(timestamp__gte=date_from)
        if date_to is not None:
            qs = qs.filter(timestamp__lte=date_to)
        if model_kind:
            qs = qs.filter(run__model_kind=model_kind)
        return qs

    @action(detail=False, methods=['get'])
    def latest(self, request):
        serial = request.query_params.get('serial')
        device_id = request.query_params.get('device')
        horizon = request.query_params.get('horizon')

        qs = self.filter_queryset(self.get_queryset())
        if serial:
            device = Device.objects.filter(serial_number=serial).first()
            if not device:
                return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(device=device)
        if device_id:
            qs = qs.filter(device_id=device_id)
        if horizon:
            qs = qs.filter(horizon=horizon)

        row = qs.order_by('-run__created_at', '-created_at', '-id').first()
        if not row:
            return Response({"detail": "State estimate not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)


class StateInferenceProfileViewSet(viewsets.ModelViewSet):
    queryset = StateInferenceProfile.objects.all().select_related('created_by')
    serializer_class = StateInferenceProfileSerializer
    permission_classes = [AdminGroupPermission]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_active', 'version']
    ordering_fields = ['is_active', 'updated_at', 'created_at', 'version', 'name']
    ordering = ['-is_active', '-updated_at', '-id']

    def perform_create(self, serializer):
        instance = serializer.save(
            created_by=self.request.user if getattr(self.request.user, 'is_authenticated', False) else None,
        )
        if instance.is_active:
            StateInferenceProfile.objects.exclude(id=instance.id).filter(is_active=True).update(is_active=False)

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.is_active:
            StateInferenceProfile.objects.exclude(id=instance.id).filter(is_active=True).update(is_active=False)

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission], url_path='active')
    def active(self, request):
        from .forecasting.state_inference_service import build_default_state_inference_profile_payload

        row = (
            self.get_queryset()
            .filter(is_active=True)
            .order_by('-updated_at', '-id')
            .first()
        )
        if row is not None:
            return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)

        payload = build_default_state_inference_profile_payload()
        payload.update({
            "id": None,
            "created_by": None,
            "created_by_username": None,
            "created_at": None,
            "updated_at": None,
            "is_fallback_default": True,
        })
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission], url_path='defaults')
    def defaults(self, request):
        from .forecasting.state_inference_service import build_default_state_inference_profile_payload

        return Response(build_default_state_inference_profile_payload(), status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission], url_path='bootstrap_defaults')
    def bootstrap_defaults(self, request):
        from .forecasting.state_inference_service import ensure_default_state_inference_profile

        profile = ensure_default_state_inference_profile(
            created_by=request.user if getattr(request.user, 'is_authenticated', False) else None,
        )
        return Response(self.get_serializer(profile).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[AdminGroupPermission], url_path='activate')
    def activate(self, request, pk=None):
        profile = self.get_object()
        with transaction.atomic():
            StateInferenceProfile.objects.exclude(id=profile.id).filter(is_active=True).update(is_active=False)
            if not profile.is_active:
                profile.is_active = True
                profile.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(profile).data, status=status.HTTP_200_OK)


class DissertationEvaluationViewSet(viewsets.ViewSet):
    permission_classes = [AdminGroupPermission]

    @staticmethod
    def _base_dir() -> Path:
        base = Path(getattr(settings, "BASE_DIR", Path.cwd())) / "research" / "evaluation"
        base.mkdir(parents=True, exist_ok=True)
        return base.resolve()

    @staticmethod
    def _to_int(value, default, min_value=None, max_value=None):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        if min_value is not None:
            parsed = max(min_value, parsed)
        if max_value is not None:
            parsed = min(max_value, parsed)
        return parsed

    @staticmethod
    def _parse_csv(raw, fallback):
        if raw is None:
            return list(fallback)
        if isinstance(raw, list):
            out = [str(v).strip() for v in raw if str(v).strip()]
            return out or list(fallback)
        out = [chunk.strip() for chunk in str(raw).split(",") if chunk.strip()]
        return out or list(fallback)

    @staticmethod
    def _to_bool(value, default=False):
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off"):
            return False
        return bool(default)

    def _run_dir(self, run_id: str) -> Path:
        if not re.match(r"^run_[A-Za-z0-9_-]+$", str(run_id or "")):
            raise RuntimeError("Invalid run_id format")
        base = self._base_dir()
        run_dir = (base / run_id).resolve()
        if not str(run_dir).startswith(str(base)):
            raise RuntimeError("Invalid run path")
        if not run_dir.exists() or not run_dir.is_dir():
            raise RuntimeError("Run directory not found")
        return run_dir

    @staticmethod
    def _read_json(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_manifest(self, run_dir: Path):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("manifest.json not found")
        return self._read_json(manifest_path)

    @staticmethod
    def _to_float(value):
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        if out != out:
            return None
        return out

    def _read_csv_rows(self, path: Path, limit: int = 5000):
        if not path.exists() or not path.is_file():
            return []
        rows = []
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader):
                    if idx >= limit:
                        break
                    rows.append(dict(row))
        except Exception:
            return []
        return rows

    def _build_chart_data_from_artifacts(self, manifest: dict, run_dir: Path):
        existing = manifest.get("chart_data")
        chart_data = dict(existing) if isinstance(existing, dict) else {}

        artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else {}
        if not isinstance(artifacts, dict):
            artifacts = {}

        def _artifact_path(key: str, fallback: str):
            raw = artifacts.get(key)
            if raw:
                path = Path(str(raw)).resolve()
                if str(path).startswith(str(run_dir)) and path.exists():
                    return path
            fallback_path = (run_dir / fallback).resolve()
            if str(fallback_path).startswith(str(run_dir)) and fallback_path.exists():
                return fallback_path
            return None

        model_h_path = _artifact_path("forecast_metrics_by_model_horizon_csv", "forecast_metrics_by_model_horizon.csv")
        bucket_path = _artifact_path("forecast_metrics_by_bucket_csv", "forecast_metrics_by_bucket.csv")
        variant_h_path = _artifact_path("forecast_metrics_by_variant_horizon_csv", "forecast_metrics_by_variant_horizon.csv")
        prob_h_path = _artifact_path(
            "forecast_prob_metrics_by_model_horizon_csv",
            "forecast_prob_metrics_by_model_horizon.csv",
        )
        interval_h_path = _artifact_path(
            "forecast_interval_calibration_by_model_horizon_csv",
            "forecast_interval_calibration_by_model_horizon.csv",
        )
        dm_tests_path = _artifact_path("forecast_dm_tests_csv", "forecast_dm_tests.csv")
        bootstrap_ci_path = _artifact_path("forecast_bootstrap_ci_csv", "forecast_bootstrap_ci.csv")
        delta_h_path = _artifact_path("decision_delta_r_by_horizon_csv", "decision_delta_r_by_horizon.csv")

        model_rows = self._read_csv_rows(model_h_path) if model_h_path else []
        bucket_rows = self._read_csv_rows(bucket_path) if bucket_path else []
        variant_rows = self._read_csv_rows(variant_h_path) if variant_h_path else []
        prob_rows = self._read_csv_rows(prob_h_path) if prob_h_path else []
        interval_rows = self._read_csv_rows(interval_h_path) if interval_h_path else []
        dm_rows = self._read_csv_rows(dm_tests_path) if dm_tests_path else []
        bootstrap_rows = self._read_csv_rows(bootstrap_ci_path) if bootstrap_ci_path else []
        delta_rows = self._read_csv_rows(delta_h_path) if delta_h_path else []

        normalized_model_rows = []
        for row in model_rows:
            normalized_model_rows.append({
                "model_kind": row.get("model_kind"),
                "horizon": row.get("horizon"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "mean_error": self._to_float(row.get("mean_error")),
                "mae": self._to_float(row.get("mae")),
                "rmse": self._to_float(row.get("rmse")),
                "mape": self._to_float(row.get("mape")),
                "smape": self._to_float(row.get("smape")),
                "mase": self._to_float(row.get("mase")),
                "rmsse": self._to_float(row.get("rmsse")),
                "pinball_q10": self._to_float(row.get("pinball_q10")),
                "pinball_q50": self._to_float(row.get("pinball_q50")),
                "pinball_q90": self._to_float(row.get("pinball_q90")),
                "pinball_avg": self._to_float(row.get("pinball_avg")),
                "picp80": self._to_float(row.get("picp80")),
                "ace80": self._to_float(row.get("ace80")),
                "miw": self._to_float(row.get("miw")),
                "winkler80": self._to_float(row.get("winkler80")),
            })

        normalized_variant_rows = []
        for row in variant_rows:
            normalized_variant_rows.append({
                "variant_key": row.get("variant_key"),
                "variant_label": row.get("variant_label"),
                "model_kind": row.get("model_kind"),
                "horizon": row.get("horizon"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "mean_error": self._to_float(row.get("mean_error")),
                "mae": self._to_float(row.get("mae")),
                "rmse": self._to_float(row.get("rmse")),
                "mape": self._to_float(row.get("mape")),
                "smape": self._to_float(row.get("smape")),
                "mase": self._to_float(row.get("mase")),
                "rmsse": self._to_float(row.get("rmsse")),
                "pinball_q10": self._to_float(row.get("pinball_q10")),
                "pinball_q50": self._to_float(row.get("pinball_q50")),
                "pinball_q90": self._to_float(row.get("pinball_q90")),
                "pinball_avg": self._to_float(row.get("pinball_avg")),
                "picp80": self._to_float(row.get("picp80")),
                "ace80": self._to_float(row.get("ace80")),
                "miw": self._to_float(row.get("miw")),
                "winkler80": self._to_float(row.get("winkler80")),
            })

        normalized_bucket_rows = []
        for row in bucket_rows:
            normalized_bucket_rows.append({
                "model_kind": row.get("model_kind"),
                "horizon": row.get("horizon"),
                "metric_code": row.get("metric_code"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "mean_error": self._to_float(row.get("mean_error")),
                "mae": self._to_float(row.get("mae")),
                "rmse": self._to_float(row.get("rmse")),
                "mape": self._to_float(row.get("mape")),
                "smape": self._to_float(row.get("smape")),
                "mase": self._to_float(row.get("mase")),
                "rmsse": self._to_float(row.get("rmsse")),
                "pinball_q10": self._to_float(row.get("pinball_q10")),
                "pinball_q50": self._to_float(row.get("pinball_q50")),
                "pinball_q90": self._to_float(row.get("pinball_q90")),
                "pinball_avg": self._to_float(row.get("pinball_avg")),
                "picp80": self._to_float(row.get("picp80")),
                "ace80": self._to_float(row.get("ace80")),
                "miw": self._to_float(row.get("miw")),
                "winkler80": self._to_float(row.get("winkler80")),
            })

        normalized_prob_rows = []
        for row in prob_rows:
            normalized_prob_rows.append({
                "model_kind": row.get("model_kind"),
                "horizon": row.get("horizon"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "mean_error": self._to_float(row.get("mean_error")),
                "smape": self._to_float(row.get("smape")),
                "mase": self._to_float(row.get("mase")),
                "rmsse": self._to_float(row.get("rmsse")),
                "pinball_q10": self._to_float(row.get("pinball_q10")),
                "pinball_q50": self._to_float(row.get("pinball_q50")),
                "pinball_q90": self._to_float(row.get("pinball_q90")),
                "pinball_avg": self._to_float(row.get("pinball_avg")),
            })

        normalized_interval_rows = []
        for row in interval_rows:
            normalized_interval_rows.append({
                "model_kind": row.get("model_kind"),
                "horizon": row.get("horizon"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "picp80": self._to_float(row.get("picp80")),
                "ace80": self._to_float(row.get("ace80")),
                "miw": self._to_float(row.get("miw")),
                "winkler80": self._to_float(row.get("winkler80")),
            })

        normalized_delta_rows = []
        for row in delta_rows:
            normalized_delta_rows.append({
                "horizon": row.get("horizon"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "expected_loss_with_system_mean": self._to_float(row.get("expected_loss_with_system_mean")),
                "expected_loss_with_system_median": self._to_float(row.get("expected_loss_with_system_median")),
                "expected_loss_without_system_mean": self._to_float(row.get("expected_loss_without_system_mean")),
                "expected_loss_without_system_median": self._to_float(row.get("expected_loss_without_system_median")),
                "delta_r_mean": self._to_float(row.get("delta_r_mean")),
                "delta_r_median": self._to_float(row.get("delta_r_median")),
                "delta_r_min": self._to_float(row.get("delta_r_min")),
                "delta_r_max": self._to_float(row.get("delta_r_max")),
                "delta_r_pct_mean": self._to_float(row.get("delta_r_pct_mean")),
                "delta_r_pct_median": self._to_float(row.get("delta_r_pct_median")),
                "share_positive": self._to_float(row.get("share_positive")),
            })

        normalized_dm_rows = []
        for row in dm_rows:
            normalized_dm_rows.append({
                "horizon": row.get("horizon"),
                "model_a": row.get("model_a"),
                "model_b": row.get("model_b"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "mean_loss_diff": self._to_float(row.get("mean_loss_diff")),
                "dm_stat": self._to_float(row.get("dm_stat")),
                "p_value": self._to_float(row.get("p_value")),
                "significant_005": str(row.get("significant_005") or "").strip().lower() in ("1", "true", "yes"),
                "winner": row.get("winner"),
            })

        normalized_bootstrap_rows = []
        for row in bootstrap_rows:
            normalized_bootstrap_rows.append({
                "model_kind": row.get("model_kind"),
                "horizon": row.get("horizon"),
                "metric": row.get("metric"),
                "samples": self._to_int(row.get("samples"), default=0, min_value=0),
                "estimate": self._to_float(row.get("estimate")),
                "ci95_low": self._to_float(row.get("ci95_low")),
                "ci95_high": self._to_float(row.get("ci95_high")),
                "bootstrap_samples": self._to_int(row.get("bootstrap_samples"), default=0, min_value=0),
                "bootstrap_block_size": self._to_int(row.get("bootstrap_block_size"), default=0, min_value=0),
            })

        if normalized_model_rows and not chart_data.get("forecast_metrics_by_model_horizon"):
            chart_data["forecast_metrics_by_model_horizon"] = normalized_model_rows
        if normalized_bucket_rows and not chart_data.get("forecast_metrics_by_bucket"):
            chart_data["forecast_metrics_by_bucket"] = normalized_bucket_rows
        if normalized_variant_rows and not chart_data.get("forecast_metrics_by_variant_horizon"):
            chart_data["forecast_metrics_by_variant_horizon"] = normalized_variant_rows
        if normalized_variant_rows and not chart_data.get("forecast_metrics_by_sarima_variant_horizon"):
            chart_data["forecast_metrics_by_sarima_variant_horizon"] = [
                row for row in normalized_variant_rows if str(row.get("model_kind") or "").lower() == "sarima"
            ]
        if normalized_prob_rows and not chart_data.get("forecast_prob_metrics_by_model_horizon"):
            chart_data["forecast_prob_metrics_by_model_horizon"] = normalized_prob_rows
        elif normalized_model_rows and not chart_data.get("forecast_prob_metrics_by_model_horizon"):
            chart_data["forecast_prob_metrics_by_model_horizon"] = [
                {
                    "model_kind": row.get("model_kind"),
                    "horizon": row.get("horizon"),
                    "samples": row.get("samples"),
                    "mean_error": row.get("mean_error"),
                    "smape": row.get("smape"),
                    "mase": row.get("mase"),
                    "rmsse": row.get("rmsse"),
                    "pinball_q10": row.get("pinball_q10"),
                    "pinball_q50": row.get("pinball_q50"),
                    "pinball_q90": row.get("pinball_q90"),
                    "pinball_avg": row.get("pinball_avg"),
                }
                for row in normalized_model_rows
            ]
        if normalized_interval_rows and not chart_data.get("forecast_interval_calibration_by_model_horizon"):
            chart_data["forecast_interval_calibration_by_model_horizon"] = normalized_interval_rows
        elif normalized_model_rows and not chart_data.get("forecast_interval_calibration_by_model_horizon"):
            chart_data["forecast_interval_calibration_by_model_horizon"] = [
                {
                    "model_kind": row.get("model_kind"),
                    "horizon": row.get("horizon"),
                    "samples": row.get("samples"),
                    "picp80": row.get("picp80"),
                    "ace80": row.get("ace80"),
                    "miw": row.get("miw"),
                    "winkler80": row.get("winkler80"),
                }
                for row in normalized_model_rows
            ]
        if normalized_delta_rows and not chart_data.get("decision_delta_r_by_horizon"):
            chart_data["decision_delta_r_by_horizon"] = normalized_delta_rows
        if normalized_dm_rows and not chart_data.get("stat_tests_dm"):
            chart_data["stat_tests_dm"] = normalized_dm_rows
        if normalized_bootstrap_rows and not chart_data.get("bootstrap_ci"):
            chart_data["bootstrap_ci"] = normalized_bootstrap_rows
        return chart_data

    def _build_insights_from_chart_data(self, manifest: dict, chart_data: dict):
        summary = manifest.get("summary") if isinstance(manifest, dict) else {}
        if not isinstance(summary, dict):
            summary = {}
        existing = summary.get("insights")
        existing = dict(existing) if isinstance(existing, dict) else {}

        model_rows = chart_data.get("forecast_metrics_by_model_horizon") if isinstance(chart_data, dict) else []
        delta_rows = chart_data.get("decision_delta_r_by_horizon") if isinstance(chart_data, dict) else []
        if not isinstance(model_rows, list):
            model_rows = []
        if not isinstance(delta_rows, list):
            delta_rows = []

        best_rmse = min(
            (row for row in model_rows if self._to_float(row.get("rmse")) is not None),
            key=lambda row: float(row.get("rmse")),
            default=None,
        )
        best_delta = max(
            (row for row in delta_rows if self._to_float(row.get("delta_r_mean")) is not None),
            key=lambda row: float(row.get("delta_r_mean")),
            default=None,
        )
        variant_rows = chart_data.get("forecast_metrics_by_sarima_variant_horizon") if isinstance(chart_data, dict) else []
        if not isinstance(variant_rows, list) or not variant_rows:
            raw_variant_rows = chart_data.get("forecast_metrics_by_variant_horizon") if isinstance(chart_data, dict) else []
            variant_rows = [
                row for row in (raw_variant_rows if isinstance(raw_variant_rows, list) else [])
                if str(row.get("model_kind") or "").lower() == "sarima"
            ]
        prob_rows = chart_data.get("forecast_prob_metrics_by_model_horizon") if isinstance(chart_data, dict) else []
        if not isinstance(prob_rows, list) or not prob_rows:
            prob_rows = model_rows
        interval_rows = chart_data.get("forecast_interval_calibration_by_model_horizon") if isinstance(chart_data, dict) else []
        if not isinstance(interval_rows, list) or not interval_rows:
            interval_rows = model_rows
        dm_rows = chart_data.get("stat_tests_dm") if isinstance(chart_data, dict) else []
        if not isinstance(dm_rows, list):
            dm_rows = []
        best_sarima_variant = min(
            (
                row for row in variant_rows
                if self._to_float(row.get("rmse")) is not None and str(row.get("variant_key") or "") != "sarima:unknown"
            ),
            key=lambda row: float(row.get("rmse")),
            default=None,
        )
        best_pinball = min(
            (row for row in prob_rows if self._to_float(row.get("pinball_avg")) is not None),
            key=lambda row: float(row.get("pinball_avg")),
            default=None,
        )
        best_interval_calibration = min(
            (row for row in interval_rows if self._to_float(row.get("ace80")) is not None),
            key=lambda row: float(row.get("ace80")),
            default=None,
        )
        significant_dm = [
            row for row in dm_rows
            if bool(row.get("significant_005")) or (
                self._to_float(row.get("p_value")) is not None and float(row.get("p_value")) < 0.05
            )
        ]
        best_dm = min(
            (row for row in dm_rows if self._to_float(row.get("p_value")) is not None),
            key=lambda row: float(row.get("p_value")),
            default=None,
        )
        coverage = self._to_float(summary.get("forecast_coverage"))
        points_with_actual = self._to_int(summary.get("forecast_points_with_actual"), default=0, min_value=0)
        points_with_actual_raw = self._to_int(summary.get("forecast_points_with_actual_raw"), default=points_with_actual, min_value=0)
        points_compared = self._to_int(summary.get("forecast_points_compared"), default=points_with_actual, min_value=0)
        points_total = self._to_int(summary.get("forecast_points_total"), default=0, min_value=0)
        strict_enabled = bool(summary.get("strict_intersection_enabled"))

        computed = {
            "coverage_note": (
                f"Покрытие фактом: {(coverage * 100.0):.1f}% "
                f"({points_compared}/{points_total} точек для сравнения; raw {points_with_actual_raw}/{points_total}; "
                f"strict={strict_enabled})."
                if coverage is not None else "Покрытие фактом недоступно."
            ),
            "best_rmse": best_rmse,
            "best_delta_horizon": best_delta,
            "best_sarima_variant": best_sarima_variant,
            "best_pinball": best_pinball,
            "best_interval_calibration": best_interval_calibration,
            "dm_tests": {
                "total_pairs": len(dm_rows),
                "significant_pairs_005": len(significant_dm),
                "best_p_value_row": best_dm,
            },
        }
        for key, value in computed.items():
            if key not in existing or existing.get(key) in (None, "", [], {}):
                existing[key] = value
        return existing

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="run")
    def run(self, request):
        serial = (request.data.get("serial") or "").strip() or None
        days_back = self._to_int(request.data.get("days_back"), default=120, min_value=1, max_value=2000)
        target_date_from = request.data.get("target_date_from")
        target_date_to = request.data.get("target_date_to")
        actual_date_from = request.data.get("actual_date_from")
        actual_date_to = request.data.get("actual_date_to")
        horizons = self._parse_csv(request.data.get("horizons"), fallback=["24h", "7d", "30d"])
        model_kinds = self._parse_csv(request.data.get("model_kinds"), fallback=["sarima", "lstm", "ensemble"])
        forecast_run_ids = self._parse_csv(request.data.get("forecast_run_ids"), fallback=[])
        baseline_action_code = (request.data.get("baseline_action_code") or "no_action").strip() or "no_action"
        tag = (request.data.get("tag") or "").strip() or None
        strict_intersection = self._to_bool(request.data.get("strict_intersection", True), default=True)
        enable_stat_tests = self._to_bool(request.data.get("enable_stat_tests", True), default=True)
        bootstrap_samples = self._to_int(request.data.get("bootstrap_samples"), default=300, min_value=50, max_value=2000)
        bootstrap_block_size = self._to_int(request.data.get("bootstrap_block_size"), default=0, min_value=0, max_value=5000)

        try:
            from .forecasting.evaluation_service import run_dissertation_evaluation
            payload = run_dissertation_evaluation(
                serial=serial,
                days_back=days_back,
                target_date_from=target_date_from,
                target_date_to=target_date_to,
                actual_date_from=actual_date_from,
                actual_date_to=actual_date_to,
                horizons=horizons,
                model_kinds=model_kinds,
                forecast_run_ids=forecast_run_ids,
                baseline_action_code=baseline_action_code,
                output_dir=str(self._base_dir()),
                tag=tag,
                strict_intersection=strict_intersection,
                enable_stat_tests=enable_stat_tests,
                bootstrap_samples=bootstrap_samples,
                bootstrap_block_size=(bootstrap_block_size if bootstrap_block_size > 0 else None),
            )
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"detail": f"evaluation failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="preview")
    def preview(self, request):
        serial = (request.data.get("serial") or "").strip() or None
        days_back = self._to_int(request.data.get("days_back"), default=120, min_value=1, max_value=2000)
        target_date_from = request.data.get("target_date_from")
        target_date_to = request.data.get("target_date_to")
        actual_date_from = request.data.get("actual_date_from")
        actual_date_to = request.data.get("actual_date_to")
        horizons = self._parse_csv(request.data.get("horizons"), fallback=["24h", "7d", "30d"])
        model_kinds = self._parse_csv(request.data.get("model_kinds"), fallback=["sarima", "lstm", "ensemble"])
        forecast_run_ids = self._parse_csv(request.data.get("forecast_run_ids"), fallback=[])
        strict_intersection = self._to_bool(request.data.get("strict_intersection", True), default=True)

        try:
            from .forecasting.evaluation_service import preview_dissertation_evaluation
            payload = preview_dissertation_evaluation(
                serial=serial,
                days_back=days_back,
                target_date_from=target_date_from,
                target_date_to=target_date_to,
                actual_date_from=actual_date_from,
                actual_date_to=actual_date_to,
                horizons=horizons,
                model_kinds=model_kinds,
                forecast_run_ids=forecast_run_ids,
                strict_intersection=strict_intersection,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"detail": f"evaluation preview failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="history")
    def history(self, request):
        limit = self._to_int(request.query_params.get("limit"), default=20, min_value=1, max_value=200)
        serial_filter = str(request.query_params.get("serial") or "").strip()
        base = self._base_dir()
        rows = []
        for child in base.iterdir():
            if not child.is_dir() or not child.name.startswith("run_"):
                continue
            manifest_path = child / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = self._read_json(manifest_path)
            except Exception:
                continue
            config = manifest.get("config") or {}
            if serial_filter and str(config.get("serial") or "").strip() != serial_filter:
                continue
            rows.append({
                "run_id": child.name,
                "generated_at": manifest.get("generated_at"),
                "output_dir": str(child),
                "config": config,
                "summary": manifest.get("summary") or {},
                "artifacts": manifest.get("artifacts") or {},
                "mtime": child.stat().st_mtime,
            })
        rows.sort(key=lambda row: row.get("generated_at") or row.get("mtime") or 0, reverse=True)
        for row in rows:
            row.pop("mtime", None)
        return Response(rows[:limit], status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="latest")
    def latest(self, request):
        history_response = self.history(request)
        rows = history_response.data if isinstance(history_response.data, list) else []
        if not rows:
            return Response({"detail": "No evaluation runs found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(rows[0], status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="detail")
    def run_detail(self, request):
        run_id = (request.query_params.get("run_id") or "").strip()
        if not run_id:
            return Response({"detail": "run_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            run_dir = self._run_dir(run_id)
            manifest = self._load_manifest(run_dir)
            report_path = run_dir / "dissertation_evaluation_report.md"
            report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
            chart_data = self._build_chart_data_from_artifacts(manifest, run_dir)
            insights = self._build_insights_from_chart_data(manifest, chart_data)
            return Response({
                "run_id": run_id,
                "output_dir": str(run_dir),
                "manifest": manifest,
                "report_text": report_text,
                "chart_data": chart_data,
                "insights": insights,
            }, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response({"detail": f"detail read failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="download")
    def download(self, request):
        run_id = (request.query_params.get("run_id") or "").strip()
        artifact = (request.query_params.get("artifact") or "").strip()
        if not run_id or not artifact:
            return Response({"detail": "run_id and artifact are required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            run_dir = self._run_dir(run_id)
            manifest = self._load_manifest(run_dir)
            artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else {}
            if artifact in (artifacts or {}):
                target = Path(artifacts[artifact]).resolve()
            else:
                target = (run_dir / artifact).resolve()
            if not str(target).startswith(str(run_dir)):
                return Response({"detail": "Invalid artifact path"}, status=status.HTTP_400_BAD_REQUEST)
            if not target.exists() or not target.is_file():
                return Response({"detail": "Artifact file not found"}, status=status.HTTP_404_NOT_FOUND)
            response = FileResponse(target.open("rb"), as_attachment=True, filename=target.name)
            return response
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            return Response({"detail": f"download failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MonitoringSystemViewSet(viewsets.ViewSet):
    permission_classes = [AdminGroupPermission]

    @staticmethod
    def _evaluation_base_dir() -> Path:
        base = Path(getattr(settings, "BASE_DIR", Path.cwd())) / "research" / "evaluation"
        base.mkdir(parents=True, exist_ok=True)
        return base.resolve()

    def _summary_payload(self):
        base = self._evaluation_base_dir()
        evaluation_dirs = [child for child in base.iterdir() if child.is_dir() and child.name.startswith("run_")]
        evaluation_files = 0
        for child in evaluation_dirs:
            try:
                evaluation_files += sum(1 for _ in child.rglob("*") if _.is_file())
            except Exception:
                continue
        return {
            "raw_metrics": RawMetric.objects.count(),
            "computed_metrics": ComputedMetric.objects.count(),
            "agent_status_rows": AgentStatus.objects.count(),
            "forecast_runs": ForecastRun.objects.count(),
            "forecast_points": ForecastPoint.objects.count(),
            "state_estimates": StateEstimate.objects.count(),
            "lstm_queue_jobs": LSTMRemoteQueueJob.objects.count(),
            "decision_runs": DecisionRun.objects.count(),
            "evaluation_runs": len(evaluation_dirs),
            "evaluation_files": evaluation_files,
        }

    @staticmethod
    def _env_local_path() -> Path:
        return (Path(getattr(settings, "BASE_DIR", Path.cwd())) / ".env.local").resolve()

    @staticmethod
    def _parse_env_line(raw_line: str):
        line = str(raw_line or "").strip()
        if not line or line.startswith("#"):
            return None, None
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            return None, None
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            return None, None
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return key, value

    @classmethod
    def _read_env_local_map(cls) -> dict[str, str]:
        path = cls._env_local_path()
        out: dict[str, str] = {}
        if not path.exists():
            return out
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                key, value = cls._parse_env_line(raw)
                if key:
                    out[key] = value
        except Exception:
            return {}
        return out

    @staticmethod
    def _render_env_value(value: str) -> str:
        text = str(value if value is not None else "")
        if not text:
            return ""
        if any(ch in text for ch in (" ", "#", "\t")):
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            return f"\"{escaped}\""
        return text

    @classmethod
    def _upsert_env_local_values(cls, values: dict[str, str]) -> Path:
        path = cls._env_local_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        existing_lines: list[str] = []
        if path.exists():
            try:
                existing_lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                existing_lines = []

        key_to_line_idx: dict[str, int] = {}
        for idx, raw in enumerate(existing_lines):
            key, _ = cls._parse_env_line(raw)
            if key and key not in key_to_line_idx:
                key_to_line_idx[key] = idx

        normalized_values = {str(k): str(v if v is not None else "") for k, v in (values or {}).items()}
        for key, value in normalized_values.items():
            line = f"{key}={cls._render_env_value(value)}"
            if key in key_to_line_idx:
                existing_lines[key_to_line_idx[key]] = line
            else:
                existing_lines.append(line)
            os.environ[key] = value

        content = "\n".join(existing_lines).rstrip("\n")
        path.write_text(content + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _as_bool(value, default=False):
        if value is None:
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _token_preview(token: str) -> str:
        text = str(token or "")
        if not text:
            return ""
        if len(text) <= 10:
            return "*" * len(text)
        return f"{text[:6]}...{text[-4:]}"

    @staticmethod
    def _split_lstm_base_url(base_url: str):
        raw = str(base_url or "").strip()
        if not raw:
            raw = "http://127.0.0.1:8099"
        if "://" not in raw:
            raw = f"http://{raw}"
        try:
            parsed = urlsplit(raw)
        except Exception:
            parsed = urlsplit("http://127.0.0.1:8099")
        scheme = (parsed.scheme or "http").strip().lower()
        if scheme not in {"http", "https"}:
            scheme = "http"
        host = (parsed.hostname or "").strip()
        if not host:
            host = "127.0.0.1"
        default_port = 443 if scheme == "https" else 80
        port = parsed.port or default_port
        return {
            "scheme": scheme,
            "host": host,
            "port": int(port),
        }

    @staticmethod
    def _build_lstm_base_url(*, scheme: str, host: str, port: int):
        scheme_value = str(scheme or "http").strip().lower()
        if scheme_value not in {"http", "https"}:
            scheme_value = "http"
        host_value = str(host or "").strip()
        if not host_value:
            raise ValueError("lstm_host is required")
        if ":" in host_value and not host_value.startswith("[") and not host_value.endswith("]"):
            host_value = f"[{host_value}]"
        port_value = int(port)
        if port_value < 1 or port_value > 65535:
            raise ValueError("lstm_port must be in range 1..65535")
        return f"{scheme_value}://{host_value}:{port_value}"

    @classmethod
    def _lstm_config_payload(cls, *, include_token: bool = False):
        env_local = cls._read_env_local_map()
        base_url_raw = str(
            env_local.get("LSTM_REMOTE_API_BASE_URL")
            or os.environ.get("LSTM_REMOTE_API_BASE_URL")
            or "http://127.0.0.1:8099"
        ).strip()
        parsed = cls._split_lstm_base_url(base_url_raw)
        scheme = str(
            env_local.get("LSTM_REMOTE_API_SCHEME")
            or os.environ.get("LSTM_REMOTE_API_SCHEME")
            or parsed["scheme"]
        ).strip().lower()
        if scheme not in {"http", "https"}:
            scheme = parsed["scheme"]
        host = str(
            env_local.get("LSTM_REMOTE_API_HOST")
            or os.environ.get("LSTM_REMOTE_API_HOST")
            or parsed["host"]
        ).strip() or parsed["host"]
        port_raw = env_local.get("LSTM_REMOTE_API_PORT", os.environ.get("LSTM_REMOTE_API_PORT", str(parsed["port"])))
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = int(parsed["port"])
        if port < 1 or port > 65535:
            port = int(parsed["port"])
        try:
            base_url = cls._build_lstm_base_url(scheme=scheme, host=host, port=port)
        except Exception:
            scheme = parsed["scheme"]
            host = parsed["host"]
            port = parsed["port"]
            base_url = cls._build_lstm_base_url(scheme=scheme, host=host, port=port)

        api_token = str(
            env_local.get("LSTM_REMOTE_API_TOKEN")
            or os.environ.get("LSTM_REMOTE_API_TOKEN")
            or ""
        ).strip()

        timeout_raw = env_local.get("LSTM_REMOTE_TIMEOUT_SEC", os.environ.get("LSTM_REMOTE_TIMEOUT_SEC", "20"))
        verify_raw = env_local.get("LSTM_REMOTE_VERIFY_SSL", os.environ.get("LSTM_REMOTE_VERIFY_SSL", "0"))

        try:
            timeout_sec = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_sec = 20.0
        timeout_sec = max(1.0, min(timeout_sec, 180.0))
        verify_ssl = cls._as_bool(verify_raw, default=False)

        payload = {
            "base_url": base_url,
            "scheme": scheme,
            "lstm_host": host,
            "lstm_port": port,
            "timeout_sec": timeout_sec,
            "verify_ssl": verify_ssl,
            "has_token": bool(api_token),
            "token_preview": cls._token_preview(api_token),
            "env_file": str(cls._env_local_path()),
            "env_file_exists": cls._env_local_path().exists(),
        }
        if include_token:
            payload["api_token"] = api_token
        return payload

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="summary")
    def summary(self, request):
        return Response(self._summary_payload(), status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="lstm-config")
    def lstm_config(self, request):
        return Response(self._lstm_config_payload(include_token=True), status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="save-lstm-config")
    def save_lstm_config(self, request):
        current = self._lstm_config_payload(include_token=True)
        incoming_base_url = str(request.data.get("base_url", "")).strip()
        scheme = str(request.data.get("scheme", current.get("scheme") or "http")).strip().lower()
        if scheme not in {"http", "https"}:
            return Response({"detail": "scheme must be http or https"}, status=status.HTTP_400_BAD_REQUEST)
        lstm_host = str(request.data.get("lstm_host", current.get("lstm_host") or "")).strip()
        lstm_port_raw = request.data.get("lstm_port", current.get("lstm_port", 8099))
        if incoming_base_url:
            parsed = self._split_lstm_base_url(incoming_base_url)
            if not lstm_host:
                lstm_host = parsed["host"]
            if "lstm_port" not in request.data:
                lstm_port_raw = parsed["port"]
            if "scheme" not in request.data:
                scheme = parsed["scheme"]

        if not lstm_host:
            return Response({"detail": "lstm_host is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lstm_port = int(lstm_port_raw)
        except (TypeError, ValueError):
            return Response({"detail": "lstm_port must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if lstm_port < 1 or lstm_port > 65535:
            return Response({"detail": "lstm_port must be in range 1..65535"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            base_url = self._build_lstm_base_url(scheme=scheme, host=lstm_host, port=lstm_port)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        timeout_raw = request.data.get("timeout_sec", current.get("timeout_sec", 20))
        verify_ssl = self._as_bool(request.data.get("verify_ssl", current.get("verify_ssl", False)), default=False)

        token_provided = "api_token" in request.data
        if token_provided:
            api_token = str(request.data.get("api_token") or "").strip()
        else:
            api_token = str(current.get("api_token") or "").strip()

        if not base_url:
            return Response({"detail": "base_url is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            timeout_sec = float(timeout_raw)
        except (TypeError, ValueError):
            return Response({"detail": "timeout_sec must be a number"}, status=status.HTTP_400_BAD_REQUEST)
        timeout_sec = max(1.0, min(timeout_sec, 180.0))

        try:
            self._upsert_env_local_values({
                "LSTM_REMOTE_API_BASE_URL": base_url,
                "LSTM_REMOTE_API_SCHEME": scheme,
                "LSTM_REMOTE_API_HOST": lstm_host,
                "LSTM_REMOTE_API_PORT": str(lstm_port),
                "LSTM_REMOTE_API_TOKEN": api_token,
                "LSTM_REMOTE_TIMEOUT_SEC": str(timeout_sec),
                "LSTM_REMOTE_VERIFY_SSL": "1" if verify_ssl else "0",
            })
        except Exception as exc:
            return Response({"detail": f"Не удалось сохранить .env.local: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "detail": "Настройки LSTM сохранены в .env.local",
            "config": self._lstm_config_payload(include_token=True),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="generate-lstm-token")
    def generate_lstm_token(self, request):
        bytes_raw = request.data.get("bytes", 32)
        save_immediately = self._as_bool(request.data.get("save", True), default=True)
        try:
            token_bytes = int(bytes_raw)
        except (TypeError, ValueError):
            token_bytes = 32
        token_bytes = max(16, min(token_bytes, 64))
        token = secrets.token_hex(token_bytes)

        if save_immediately:
            try:
                self._upsert_env_local_values({
                    "LSTM_REMOTE_API_TOKEN": token,
                })
            except Exception as exc:
                return Response({"detail": f"Не удалось сохранить токен в .env.local: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            os.environ["LSTM_REMOTE_API_TOKEN"] = token

        return Response({
            "detail": "Новый токен сгенерирован.",
            "generated_token": token,
            "saved_to_env_local": bool(save_immediately),
            "config": self._lstm_config_payload(include_token=True),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="clear-history")
    def clear_history(self, request):
        before = self._summary_payload()
        base = self._evaluation_base_dir()
        cleared_dirs = 0

        with transaction.atomic():
            DecisionRun.objects.all().delete()
            StateEstimate.objects.all().delete()
            ForecastPoint.objects.all().delete()
            LSTMRemoteQueueJob.objects.all().delete()
            ForecastRun.objects.all().delete()
            RawMetric.objects.all().delete()
            ComputedMetric.objects.all().delete()
            AgentStatus.objects.all().delete()

        for child in list(base.iterdir()):
            if not child.is_dir() or not child.name.startswith("run_"):
                continue
            try:
                shutil.rmtree(child)
                cleared_dirs += 1
            except Exception:
                continue

        after = self._summary_payload()
        return Response({
            "detail": "История мониторинга очищена.",
            "before": before,
            "after": after,
            "cleared_evaluation_runs": cleared_dirs,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="pipeline-report")
    def pipeline_report(self, request):
        serial = str(request.query_params.get("serial") or "").strip()
        horizon = str(request.query_params.get("horizon") or "30d").strip() or "30d"
        decision_mode = str(request.query_params.get("decision_mode") or "bayes").strip() or "bayes"
        raw_horizons = request.query_params.getlist("forecast_horizons")
        if not raw_horizons:
            raw_horizons = [request.query_params.get("forecast_horizons") or ""]
        forecast_horizons = []
        for chunk in raw_horizons:
            for item in str(chunk or "").split(","):
                cleaned = item.strip()
                if cleaned:
                    forecast_horizons.append(cleaned)

        if not serial:
            return Response({"detail": "serial is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from .forecasting.pipeline_report_service import build_pipeline_summary_report

            payload = build_pipeline_summary_report(
                serial=serial,
                horizon=horizon,
                decision_mode=decision_mode,
                forecast_horizons=forecast_horizons,
            )
            pdf_path = Path(payload["pdf_path"]).resolve()
            return FileResponse(pdf_path.open("rb"), as_attachment=True, filename=payload.get("file_name") or pdf_path.name)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"pipeline report failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplicationUpdateViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AdminGroupPermission]
    serializer_class = ApplicationUpdateJobSerializer
    queryset = ApplicationUpdateJob.objects.all().order_by('-created_at')

    @staticmethod
    def _last_job_payload():
        job = ApplicationUpdateJob.objects.order_by('-created_at').first()
        if not job:
            return None
        return ApplicationUpdateJobSerializer(job).data

    @action(detail=False, methods=["get"], permission_classes=[AdminGroupPermission], url_path="status")
    def status_info(self, request):
        payload = get_current_release_info()
        payload["last_job"] = self._last_job_payload()
        payload["can_start_update"] = bool(payload.get("update_enabled")) and bool(payload.get("update_script_exists"))
        if not payload.get("update_enabled"):
            payload["blocked_reason"] = "APP_UPDATE_ENABLED=0. Включите обновления на сервере явно."
        elif not payload.get("update_script_exists"):
            payload["blocked_reason"] = "Скрипт обновления не найден."
        else:
            payload["blocked_reason"] = ""
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="check")
    def check(self, request):
        manifest_url = str(request.data.get("manifest_url") or "").strip() or None
        try:
            payload = check_for_update(manifest_url=manifest_url)
        except Exception as exc:
            return Response({"detail": f"Не удалось проверить обновления: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        payload["last_job"] = self._last_job_payload()
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], permission_classes=[AdminGroupPermission], url_path="start-update")
    def start_update(self, request):
        current = get_current_release_info()
        if not current.get("update_enabled"):
            return Response(
                {"detail": "Обновление из интерфейса выключено. Установите APP_UPDATE_ENABLED=1 на сервере."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not current.get("update_script_exists"):
            return Response(
                {"detail": f"Скрипт обновления не найден: {current.get('update_script')}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            check_payload = check_for_update()
        except Exception as exc:
            return Response({"detail": f"Не удалось получить manifest обновления: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        force = MonitoringSystemViewSet._as_bool(request.data.get("force", False), default=False)
        if not check_payload.get("update_available") and not force:
            return Response({"detail": "Новая версия не найдена. Для принудительного запуска передайте force=true."}, status=status.HTTP_400_BAD_REQUEST)

        manifest = check_payload.get("manifest") or {}
        job = ApplicationUpdateJob.objects.create(
            status="queued",
            current_version=current.get("current_version") or "",
            target_version=manifest.get("version") or "",
            release_channel=manifest.get("channel") or current.get("release_channel") or "single",
            manifest_url=current.get("manifest_url") or "",
            git_ref=manifest.get("git_ref") or "",
            release_notes=manifest.get("notes") or [],
            parameters={
                "manifest": manifest,
                "force": force,
                "git_commit_before": current.get("git_commit"),
                "git_branch_before": current.get("git_branch"),
            },
            created_by=request.user if request.user.is_authenticated else None,
        )
        try:
            launch_update_worker(job)
        except Exception as exc:
            job.status = "failed"
            job.error = f"Не удалось запустить процесс обновления: {exc}"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error", "finished_at", "updated_at"])
            return Response(ApplicationUpdateJobSerializer(job).data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(ApplicationUpdateJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class RiskAssessmentViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _to_bool(value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

    @staticmethod
    def _parse_horizons(raw):
        if raw is None:
            return None
        if isinstance(raw, list):
            out = [str(item).strip() for item in raw if str(item).strip()]
            return out or None
        text = str(raw).strip()
        if not text:
            return None
        return [item.strip() for item in text.split(',') if item.strip()] or None

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission])
    def defaults(self, request):
        from .forecasting.risk_assessment_service import (
            DEFAULT_HORIZONS,
            BASE_THRESHOLDS,
            WEAR_WEIBULL_DEFAULTS,
            BASE_METRIC_WEIGHTS,
        )
        return Response({
            "default_horizons": list(DEFAULT_HORIZONS),
            "base_thresholds": dict(BASE_THRESHOLDS),
            "wear_weibull_defaults": dict(WEAR_WEIBULL_DEFAULTS),
            "base_metric_weights": dict(BASE_METRIC_WEIGHTS),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def evaluate(self, request):
        serial = request.data.get('serial')
        device_id_raw = request.data.get('device')
        horizons = self._parse_horizons(request.data.get('horizons'))
        preferred_model_kind = str(request.data.get('preferred_model_kind', 'auto') or 'auto')
        personalized_thresholds = self._to_bool(request.data.get('personalized_thresholds', True), default=True)

        threshold_lookback_raw = request.data.get('threshold_lookback_days', 60)
        markov_lookback_raw = request.data.get('markov_lookback_days', 120)
        markov_smoothing_raw = request.data.get('markov_smoothing', 1.0)
        type_blend_raw = request.data.get('type_blend', 0.35)
        overall_weight_markov_raw = request.data.get('overall_weight_markov', 0.65)
        history_limit_raw = request.data.get('history_limit', 12)

        device_id = None
        if device_id_raw not in (None, ''):
            try:
                device_id = int(device_id_raw)
            except (TypeError, ValueError):
                return Response({"detail": "Invalid device id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            threshold_lookback_days = max(1, int(threshold_lookback_raw))
        except (TypeError, ValueError):
            threshold_lookback_days = 60
        try:
            markov_lookback_days = max(1, int(markov_lookback_raw))
        except (TypeError, ValueError):
            markov_lookback_days = 120
        try:
            markov_smoothing = max(0.001, float(markov_smoothing_raw))
        except (TypeError, ValueError):
            markov_smoothing = 1.0
        try:
            type_blend = max(0.0, float(type_blend_raw))
        except (TypeError, ValueError):
            type_blend = 0.35
        try:
            overall_weight_markov = min(1.0, max(0.0, float(overall_weight_markov_raw)))
        except (TypeError, ValueError):
            overall_weight_markov = 0.65
        try:
            history_limit = max(3, min(64, int(history_limit_raw)))
        except (TypeError, ValueError):
            history_limit = 12

        try:
            from .forecasting.risk_assessment_service import (
                RiskAssessmentError,
                evaluate_risk_assessment,
            )
            payload = evaluate_risk_assessment(
                serial=serial,
                device_id=device_id,
                horizons=horizons,
                preferred_model_kind=preferred_model_kind,
                personalized_thresholds=personalized_thresholds,
                threshold_lookback_days=threshold_lookback_days,
                markov_lookback_days=markov_lookback_days,
                markov_smoothing=markov_smoothing,
                type_blend=type_blend,
                overall_weight_markov=overall_weight_markov,
                history_limit=history_limit,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except RiskAssessmentError as exc:
            return Response({"detail": str(exc)}, status=getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST))
        except Exception as exc:
            return Response({"detail": f"risk assessment failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DecisionActionViewSet(viewsets.ModelViewSet):
    queryset = DecisionAction.objects.all()
    serializer_class = DecisionActionSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'code']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['id', 'code', 'name', 'updated_at']
    ordering = ['name']

    def destroy(self, request, *args, **kwargs):
        instance: DecisionAction = self.get_object()
        has_links = (
            instance.policy_losses.exists()
            or instance.run_scores.exists()
            or instance.recommended_runs.exists()
            or instance.feedback_items.exists()
        )
        if has_links:
            if instance.is_active:
                instance.is_active = False
                instance.save(update_fields=['is_active', 'updated_at'])
            return Response(
                {"detail": "Action is referenced in history and was archived (is_active=false) instead of hard delete."},
                status=status.HTTP_200_OK,
            )
        return super().destroy(request, *args, **kwargs)


class DecisionCriterionViewSet(viewsets.ModelViewSet):
    queryset = DecisionCriterion.objects.all()
    serializer_class = DecisionCriterionSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'code']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['id', 'code', 'name', 'updated_at']
    ordering = ['name']

    def destroy(self, request, *args, **kwargs):
        instance: DecisionCriterion = self.get_object()
        has_links = (
            instance.ahp_as_i.exists()
            or instance.ahp_as_j.exists()
            or instance.run_utilities.exists()
        )
        if has_links:
            if instance.is_active:
                instance.is_active = False
                instance.save(update_fields=['is_active', 'updated_at'])
            return Response(
                {"detail": "Criterion is referenced in history and was archived (is_active=false) instead of hard delete."},
                status=status.HTTP_200_OK,
            )
        return super().destroy(request, *args, **kwargs)


class DecisionPolicyViewSet(viewsets.ModelViewSet):
    queryset = DecisionPolicy.objects.all().select_related('device', 'device_type', 'previous_version', 'created_by')
    serializer_class = DecisionPolicySerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'scope', 'horizon', 'device_type', 'device']
    search_fields = ['name', 'notes']
    ordering_fields = ['id', 'name', 'version', 'horizon', 'updated_at', 'created_at']
    ordering = ['-updated_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request and self.request.user.is_authenticated else None)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission], url_path='bootstrap_defaults')
    def bootstrap_defaults(self, request):
        from .forecasting.decision_support_service import bootstrap_decision_defaults
        rows = bootstrap_decision_defaults(created_by=request.user if request.user.is_authenticated else None)
        return Response({
            "created_or_updated": len(rows),
            "policy_ids": [row.id for row in rows],
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get', 'put', 'patch', 'post'], permission_classes=[AdminGroupPermission], url_path='ahp_matrix')
    def ahp_matrix(self, request, pk=None):
        policy = self.get_object()
        from .forecasting.decision_support_service import get_policy_ahp_matrix, upsert_policy_ahp_pairs

        if request.method.lower() in ('put', 'patch', 'post'):
            payload_serializer = DecisionAHPMatrixUpsertSerializer(data=request.data)
            payload_serializer.is_valid(raise_exception=True)
            pairs = payload_serializer.validated_data.get('pairs', [])
            try:
                upsert_policy_ahp_pairs(policy, pairs)
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(get_policy_ahp_matrix(policy), status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[AdminGroupPermission], url_path='ahp_validate')
    def ahp_validate(self, request, pk=None):
        policy = self.get_object()
        from .forecasting.decision_support_service import validate_policy_ahp
        return Response(validate_policy_ahp(policy), status=status.HTTP_200_OK)


class DecisionPolicyLossViewSet(viewsets.ModelViewSet):
    queryset = DecisionPolicyLoss.objects.all().select_related('policy', 'action')
    serializer_class = DecisionPolicyLossSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['policy', 'action']
    ordering_fields = ['id', 'policy', 'action', 'updated_at']
    ordering = ['policy_id', 'action_id']


class DecisionRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        DecisionRun.objects.all()
        .select_related('device', 'policy', 'recommended_action', 'created_by')
        .prefetch_related('scores', 'criterion_utilities', 'feedback')
    )
    serializer_class = DecisionRunSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['device', 'policy', 'horizon', 'mode', 'status']
    ordering_fields = ['id', 'created_at', 'updated_at', 'horizon']
    ordering = ['-created_at']

    @action(detail=False, methods=['get'])
    def latest(self, request):
        serial = request.query_params.get('serial')
        device_id = request.query_params.get('device')
        mode = request.query_params.get('mode')
        horizon = request.query_params.get('horizon')

        qs = self.filter_queryset(self.get_queryset())
        if serial:
            device = Device.objects.filter(serial_number=serial).first()
            if not device:
                return Response({"detail": "Device not found"}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(device=device)
        if device_id:
            qs = qs.filter(device_id=device_id)
        if mode:
            qs = qs.filter(mode=mode)
        if horizon:
            qs = qs.filter(horizon=horizon)

        row = qs.order_by('-created_at').first()
        if not row:
            return Response({"detail": "Decision run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)

    def _run_recommendation(self, request, forced_mode: str | None = None):
        req = DecisionRecommendationRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = req.validated_data

        mode = forced_mode or data.get('mode') or 'bayes'
        if mode not in ('bayes', 'advanced'):
            mode = 'bayes'

        try:
            from .forecasting.decision_support_service import run_decision_recommendation
            run = run_decision_recommendation(
                serial=data.get('serial') or None,
                device_id=data.get('device'),
                horizon=data.get('horizon', '24h'),
                policy_id=data.get('policy_id'),
                mode=mode,
                user=request.user if request.user.is_authenticated else None,
                bayes_weight=data.get('bayes_weight', 0.5),
                ahp_weight=data.get('ahp_weight', 0.5),
                sensitivity_weights=data.get('sensitivity_weights') or {},
                overall_weight_markov=data.get('overall_weight_markov', 0.65),
                risk_metric_min_risk=data.get('risk_metric_min_risk', 0.08),
                risk_metric_min_contribution=data.get('risk_metric_min_contribution', 0.03),
                risk_metric_top_k_fallback=data.get('risk_metric_top_k_fallback', 3),
            )
            return Response(self.get_serializer(run).data, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"recommendation failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission], url_path='recommend')
    def recommend(self, request):
        return self._run_recommendation(request, forced_mode='bayes')

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission], url_path='recommend_advanced')
    def recommend_advanced(self, request):
        return self._run_recommendation(request, forced_mode='advanced')

    @action(detail=True, methods=['post'], permission_classes=[AdminGroupPermission], url_path='feedback')
    def feedback(self, request, pk=None):
        run = self.get_object()
        payload = DecisionFeedbackCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        try:
            from .forecasting.decision_support_service import create_decision_feedback
            create_decision_feedback(
                run=run,
                actual_action_id=data.get('actual_action'),
                outcome_state=data.get('outcome_state'),
                outage_minutes=data.get('outage_minutes', 0.0),
                incident_cost=data.get('incident_cost', 0.0),
                notes=data.get('notes') or '',
                user=request.user if request.user.is_authenticated else None,
            )
            run.refresh_from_db()
            return Response(self.get_serializer(run).data, status=status.HTTP_200_OK)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": f"feedback save failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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


class NetworkMapViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NetworkMapSnapshot.objects.all()
    serializer_class = NetworkMapSnapshotSerializer
    permission_classes = [AdminGroupPermission]

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'is_current']
    ordering_fields = ['id', 'generated_at', 'node_count', 'edge_count', 'build_duration_ms']
    ordering = ['-generated_at', '-id']

    @staticmethod
    def _to_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ('retrieve', 'current'):
            qs = qs.prefetch_related('nodes', 'edges')
        return qs

    def get_serializer_class(self):
        if self.action in ('retrieve', 'current'):
            return NetworkMapSnapshotDetailSerializer
        return NetworkMapSnapshotSerializer

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission])
    def current(self, request):
        snapshot = (
            self.get_queryset()
            .filter(is_current=True)
            .order_by('-generated_at', '-id')
            .first()
        )
        if snapshot is None:
            snapshot = self.get_queryset().order_by('-generated_at', '-id').first()
        if snapshot is None:
            return Response({"detail": "Network map snapshot not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(snapshot)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[AdminGroupPermission])
    def history(self, request):
        limit = self._to_int(request.query_params.get('limit'), 20)
        limit = max(1, min(limit, 200))
        qs = self.filter_queryset(super().get_queryset()).order_by('-generated_at', '-id')[:limit]
        serializer = NetworkMapSnapshotSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[AdminGroupPermission])
    def rebuild(self, request):
        window_hours = self._to_int(request.data.get('window_hours'), 24)
        keep_last = self._to_int(request.data.get('keep_last'), 720)
        include_data_raw = request.data.get('include_data', True)
        if isinstance(include_data_raw, str):
            include_data = include_data_raw.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            include_data = bool(include_data_raw)

        payload = build_network_map_snapshot(window_hours=window_hours, keep_last=keep_last)
        if payload.get('status') != 'ok':
            return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if include_data:
            snapshot = self.get_queryset().filter(id=payload.get('snapshot_id')).first()
            if snapshot is not None:
                serializer = self.get_serializer(snapshot)
                return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(payload, status=status.HTTP_200_OK)


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
