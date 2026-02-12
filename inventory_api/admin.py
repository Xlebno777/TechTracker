from django.contrib import admin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin
from .models import (
    Device, DeviceType, Location, UserProfile, ComputerSpecs, PrinterScannerSpecs,
    NetworkDeviceSpecs, Cartridge, CartridgeLog, Log, Metric,
    MonitoringSetting, RawMetric, TrackedVM, ComputedMetric, AgentStatus, DiagnosticReport,
    NetworkPath, NetworkOutage, NetworkAlertRule
)

@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'serial_number', 'device_type', 'status', 'location', 'owner', 'assigned_to', 'created_at')
    list_filter = ('device_type', 'status', 'location', 'owner', 'assigned_to')
    search_fields = ('name', 'serial_number', 'asset_number')
    readonly_fields = ('qr_code_id', 'created_at', 'updated_at') # qr_code_id генерируется автоматически

    # Добавим нужные Inline Admin'ы в зависимости от типа устройства
    def get_inlines(self, request, obj=None):
        inlines = []
        if obj: # Если редактируем существующий объект
            # Пример: всегда показываем inline, но необязательные
            class ComputerSpecsInlineOptional(admin.StackedInline): # Или TabularInline
                model = ComputerSpecs
                extra = 0 # Не показываем лишние пустые формы
                min_num = 0 # Не требуем обязательного заполнения
                max_num = 1 # Ограничиваем до 1, так как OneToOne

            class PrinterScannerSpecsInlineOptional(admin.StackedInline):
                model = PrinterScannerSpecs
                extra = 0
                min_num = 0
                max_num = 1

            class NetworkDeviceSpecsInlineOptional(admin.StackedInline):
                model = NetworkDeviceSpecs
                extra = 0
                min_num = 0
                max_num = 1

            # Выбираем нужный inline в зависимости от типа устройства или просто добавляем все, но необязательные
            # inlines.append(ComputerSpecsInlineOptional) # Добавляем всегда, но необязательный
            # inlines.append(PrinterScannerSpecsInlineOptional) # Добавляем всегда, но необязательный
            # inlines.append(NetworkDeviceSpecsInlineOptional) # Добавляем всегда, но необязательный
            # Или добавляем только для соответствующего типа (менее гибко при изменении типа)
            device_type_name = obj.device_type.name if obj.device_type else ""
            if "ноутбук" in device_type_name.lower() or "пк" in device_type_name.lower() or "моноблок" in device_type_name.lower():
                inlines.append(ComputerSpecsInlineOptional)
            elif "принтер" in device_type_name.lower() or "сканер" in device_type_name.lower():
                inlines.append(PrinterScannerSpecsInlineOptional)
            elif "коммутатор" in device_type_name.lower() or "маршрутизатор" in device_type_name.lower() or "точка" in device_type_name.lower():
                inlines.append(NetworkDeviceSpecsInlineOptional)
            else:
                # Для остальных можно добавить все, но необязательные, или ни одного
                pass
        else: # Если создаем новый объект
            # Пока не добавляем inline при создании, или добавим все необязательные
            pass
        return inlines


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_favorite_devices')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    def display_favorite_devices(self, obj):
        return ", ".join([dev.name for dev in obj.favorite_devices.all()])
    display_favorite_devices.short_description = "Избранные устройства"


@admin.register(ComputerSpecs)
class ComputerSpecsAdmin(admin.ModelAdmin):
    list_display = ('device', 'cpu', 'ram_gb', 'storage_type', 'storage_capacity_gb', 'os')
    search_fields = ('device__name', 'cpu')

@admin.register(PrinterScannerSpecs)
class PrinterScannerSpecsAdmin(admin.ModelAdmin):
    list_display = ('device', 'printer_type', 'color_printing', 'duplex_printing', 'current_cartridge')
    list_filter = ('printer_type', 'color_printing', 'duplex_printing')
    search_fields = ('device__name', 'printer_type')

@admin.register(NetworkDeviceSpecs)
class NetworkDeviceSpecsAdmin(admin.ModelAdmin):
    list_display = ('device', 'ports_count', 'port_speed', 'wireless_standard')
    search_fields = ('device__name', 'port_speed', 'wireless_standard')

@admin.register(Cartridge)
class CartridgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'initial_pages', 'remaining_pages')
    search_fields = ('name',)

@admin.register(CartridgeLog)
class CartridgeLogAdmin(admin.ModelAdmin):
    list_display = ('cartridge', 'printer', 'installed_at', 'removed_at', 'pages_printed_at_removal')
    list_filter = ('installed_at', 'removed_at')
    search_fields = ('cartridge__name', 'printer__device__name')

@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ('device', 'log_type', 'priority', 'timestamp', 'created_by')
    list_filter = ('log_type', 'priority', 'timestamp', 'device__device_type')
    search_fields = ('device__name', 'message')
    readonly_fields = ('timestamp',) # timestamp заполняется автоматически

# Создаем ресурс для настройки того, КАК экспортировать данные
class MetricResource(resources.ModelResource):
    # Чтобы вместо ID устройства выводилось его имя, используем widget
    device = fields.Field(
        column_name='Устройство',
        attribute='device',
        widget=ForeignKeyWidget(Device, field='name')
    )
    
    # Переименуем остальные колонки для красоты
    metric_type = fields.Field(attribute='get_metric_type_display', column_name='Тип метрики')
    value = fields.Field(attribute='value', column_name='Значение')
    timestamp = fields.Field(attribute='timestamp', column_name='Время')

    class Meta:
        model = Metric
        fields = ('device', 'metric_type', 'value', 'timestamp') # Порядок колонок
        export_order = ('timestamp', 'device', 'metric_type', 'value')

@admin.register(Metric)
class MetricAdmin(ImportExportModelAdmin):
    resource_class = MetricResource
    list_display = ('device', 'metric_type', 'value', 'timestamp')
    list_filter = ('metric_type', 'timestamp', 'device')
    # Для больших таблиц полезно убрать ссылку на полное редактирование, если записей миллионы
    # Но для начала подойдет стандартный вид.


@admin.register(MonitoringSetting)
class MonitoringSettingAdmin(admin.ModelAdmin):
    list_display = ('device', 'retention_days', 'updated_at')
    search_fields = ('device__name', 'device__serial_number')


@admin.register(TrackedVM)
class TrackedVMAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'cpu_usage', 'memory_usage', 'uptime_seconds', 'last_seen', 'host_device', 'is_enabled')
    list_filter = ('status', 'is_enabled', 'host_device')
    search_fields = ('name',)


@admin.register(RawMetric)
class RawMetricAdmin(admin.ModelAdmin):
    list_display = ('device', 'code', 'value', 'unit', 'timestamp')
    list_filter = ('code', 'device')
    search_fields = ('device__name', 'code')
    readonly_fields = ('created_at',)


@admin.register(ComputedMetric)
class ComputedMetricAdmin(admin.ModelAdmin):
    list_display = ('device', 'code', 'value', 'unit', 'window', 'timestamp')
    list_filter = ('code', 'window', 'device')
    search_fields = ('device__name', 'code')
    readonly_fields = ('created_at',)


@admin.register(AgentStatus)
class AgentStatusAdmin(admin.ModelAdmin):
    list_display = ('device', 'status', 'updated_at')
    list_filter = ('status', 'device')
    search_fields = ('device__name', 'device__serial_number', 'message')


@admin.register(DiagnosticReport)
class DiagnosticReportAdmin(admin.ModelAdmin):
    list_display = ('device', 'severity', 'created_at')
    list_filter = ('severity', 'device')
    search_fields = ('device__name', 'summary')


@admin.register(NetworkPath)
class NetworkPathAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'src_device', 'dst_device', 'enabled', 'last_state',
        'last_latency_ms', 'last_packet_loss_pct', 'last_checked_at'
    )
    list_filter = ('enabled', 'last_state')
    search_fields = (
        'src_device__name', 'src_device__serial_number',
        'dst_device__name', 'dst_device__serial_number'
    )


@admin.register(NetworkOutage)
class NetworkOutageAdmin(admin.ModelAdmin):
    list_display = ('id', 'path', 'is_active', 'started_at', 'ended_at', 'duration_sec', 'fail_count')
    list_filter = ('is_active',)
    search_fields = ('path__src_device__name', 'path__dst_device__name')


@admin.register(NetworkAlertRule)
class NetworkAlertRuleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'metric_code', 'comparison', 'threshold_value', 'severity', 'enabled', 'order')
    list_filter = ('enabled', 'severity', 'window')
    search_fields = ('code', 'name', 'metric_code')
