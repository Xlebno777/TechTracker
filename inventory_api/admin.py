from django.contrib import admin
from .models import Device, DeviceType, Location, UserProfile, ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs, Cartridge, CartridgeLog, Log

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
    list_display = ('device', 'log_type', 'severity', 'timestamp', 'created_by')
    list_filter = ('log_type', 'severity', 'timestamp', 'device__device_type')
    search_fields = ('device__name', 'message')
    readonly_fields = ('timestamp',) # timestamp заполняется автоматически