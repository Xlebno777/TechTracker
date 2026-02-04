from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

class DeviceType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тип устройства"
        verbose_name_plural = "Типы устройств"

class Location(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Местоположение"
        verbose_name_plural = "Местоположения"

class Device(models.Model):
    STATUS_CHOICES = [
        ('active', 'В работе'),
        ('in_repair', 'В ремонте'),
        ('retired', 'Списано'),
        ('in_stock', 'На складе'),
        ('reserved', 'В резерве'),
    ]

    name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, unique=True) # Уникальность на уровне БД
    asset_number = models.CharField(max_length=100, blank=True, null=True, unique=True) # Инвентарный номер
    device_type = models.ForeignKey(DeviceType, on_delete=models.CASCADE, related_name='devices')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    mac_address = models.CharField(max_length=17, null=True, blank=True) # Пример формата: 00:11:22:33:44:55
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_devices')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_devices')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    qr_code_id = models.CharField(max_length=200, unique=True, blank=True) # Поле для ID QR-кода

    def __str__(self):
        return f"{self.name} ({self.serial_number})"

    class Meta:
        verbose_name = "Устройство"
        verbose_name_plural = "Устройства"
        # Можно добавить индексы для часто запрашиваемых полей
        indexes = [
            models.Index(fields=['serial_number']),
            models.Index(fields=['status']),
            models.Index(fields=['location']),
        ]

    def clean(self):
        """Валидация на уровне модели."""
        if self.mac_address:
            # Простая проверка формата MAC-адреса (пример)
            import re
            if not re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', self.mac_address):
                 raise ValidationError({'mac_address': 'MAC-адрес имеет неверный формат.'})

    def save(self, *args, **kwargs):
        """Переопределяем save для генерации qr_code_id, если он не задан."""
        if not self.qr_code_id:
            # Генерация уникального ID, например, на основе серийника и времени
            import uuid
            unique_id = str(uuid.uuid4())
            self.qr_code_id = f"{self.serial_number}_{unique_id[:8]}"
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    favorite_devices = models.ManyToManyField(Device, blank=True, related_name='favorited_by_users')

    def __str__(self):
        return f"Профиль {self.user.username}"

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"


# Специфичные модели для разных типов устройств
class ComputerSpecs(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='computer_specs')
    cpu = models.CharField(max_length=200, blank=True)
    ram_gb = models.PositiveIntegerField(null=True, blank=True) # Объем ОЗУ в ГБ
    storage_type = models.CharField(max_length=50, choices=[('SSD', 'SSD'), ('HDD', 'HDD'), ('SSHD', 'SSHD')], blank=True)
    storage_capacity_gb = models.PositiveIntegerField(null=True, blank=True) # Объем накопителя в ГБ
    os = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"Спецификации ПК для {self.device.name}"

    class Meta:
        verbose_name = "Спецификация ПК"
        verbose_name_plural = "Спецификации ПК"


class PrinterScannerSpecs(models.Model):
    PRINTER_TYPE_CHOICES = [
        ('laser', 'Лазерный'),
        ('inkjet', 'Струйный'),
        ('matrix', 'Матричный'),
    ]

    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='printer_scanner_specs')
    printer_type = models.CharField(max_length=20, choices=PRINTER_TYPE_CHOICES, blank=True)
    color_printing = models.BooleanField(default=False)
    max_resolution = models.CharField(max_length=50, blank=True) # Например, "1200x1200 dpi"
    duplex_printing = models.BooleanField(default=False)
    paper_trays = models.TextField(blank=True) # Описание лотков
    current_cartridge = models.ForeignKey('Cartridge', on_delete=models.SET_NULL, null=True, blank=True, related_name='current_in_printers')

    def __str__(self):
        return f"Спецификации МФУ для {self.device.name}"

    class Meta:
        verbose_name = "Спецификация МФУ"
        verbose_name_plural = "Спецификации МФУ"


class NetworkDeviceSpecs(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='network_specs')
    ports_count = models.PositiveIntegerField(null=True, blank=True)
    port_speed = models.CharField(max_length=50, blank=True) # Например, "10/100 Mbps", "10/100/1000 Mbps"
    wireless_standard = models.CharField(max_length=50, blank=True) # Например, "802.11n", "802.11ac"
    wireless_speed = models.CharField(max_length=50, blank=True) # Например, "Up to 300 Mbps"
    management_ip = models.GenericIPAddressField(null=True, blank=True) # IP для управления

    def __str__(self):
        return f"Спецификации сетевого устройства для {self.device.name}"

    class Meta:
        verbose_name = "Спецификация сетевого устройства"
        verbose_name_plural = "Спецификации сетевых устройств"


class Cartridge(models.Model):
    name = models.CharField(max_length=200)
    initial_pages = models.PositiveIntegerField() # Начальное количество страниц
    # Добавим поле для отслеживания оставшихся страниц
    remaining_pages = models.PositiveIntegerField(editable=False) # Вычисляется автоматически

    def save(self, *args, **kwargs):
        # При создании или изменении initial_pages, обновляем remaining_pages
        if not self.pk: # Если это новая запись
            self.remaining_pages = self.initial_pages
        else: # Если обновление существующей
            # Если initial_pages изменилось, пересчитываем remaining_pages
            old_instance = Cartridge.objects.get(pk=self.pk)
            if old_instance.initial_pages != self.initial_pages:
                 # Простое пересчитывание: remaining = initial - pages_used
                 # pages_used нужно где-то хранить или вычислять из CartridgeLog
                 # Пока просто обновим remaining_pages, если initial_pages увеличилось
                 if self.initial_pages > old_instance.initial_pages:
                     self.remaining_pages = self.initial_pages - (old_instance.initial_pages - old_instance.remaining_pages)
                 # Если initial_pages уменьшилось, нужно подумать о логике
                 # Для простоты, пока не будем менять remaining_pages, если initial_pages уменьшается
                 # или добавить проверку, что remaining_pages не может быть больше initial_pages
                 self.remaining_pages = min(self.remaining_pages, self.initial_pages)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.remaining_pages} страниц осталось)"

    class Meta:
        verbose_name = "Картридж"
        verbose_name_plural = "Картриджи"


class CartridgeLog(models.Model):
    cartridge = models.ForeignKey(Cartridge, on_delete=models.CASCADE, related_name='usage_logs')
    printer = models.ForeignKey(PrinterScannerSpecs, on_delete=models.CASCADE, related_name='cartridge_logs')
    installed_at = models.DateTimeField(default=timezone.now)
    removed_at = models.DateTimeField(null=True, blank=True)
    pages_printed_at_removal = models.PositiveIntegerField(null=True, blank=True) # Количество страниц на момент извлечения

    def __str__(self):
        return f"Лог {self.cartridge.name} в {self.printer.device.name} ({self.installed_at} - {self.removed_at or 'установлен'})"

    class Meta:
        verbose_name = "Лог использования картриджа"
        verbose_name_plural = "Логи использования картриджей"


class Log(models.Model):
    LOG_TYPE_CHOICES = [
        ('error', 'Ошибка'),
        ('info', 'Информация'),
        ('warning', 'Предупреждение'),
        ('request', 'Заявка'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
        ('critical', 'Критический'),
    ]

    STATUS_CHOICES = [
        ('open', 'Открыта'),
        ('in_progress', 'В работе'),
        ('closed', 'Завершена'),
        ('cancelled', 'Отменена'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='logs')
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES)
    message = models.TextField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    timestamp = models.DateTimeField(auto_now_add=True)
    # Добавим поле для связи с пользователем, создавшим запись (например, заявку)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_logs')

    def __str__(self):
        return f"[{self.timestamp}] {self.log_type.upper()} - {self.device.name}: {self.message[:50]}..."

    class Meta:
        verbose_name = "Лог"
        verbose_name_plural = "Логи"
        ordering = ['-timestamp'] # Сортировка по убыванию времени

class Metric(models.Model):
    METRIC_TYPES = [
        ('cpu_load', 'Загрузка ЦП (%)'),
        ('memory_usage', 'Использование ОЗУ (%)'),
        ('disk_usage', 'Использование диска (%)'),
        ('pages_printed', 'Отпечатано страниц'),
        ('temperature', 'Температура (°C)'),
        ('uptime', 'Время работы (сек)'),
        ('ping_latency', 'Задержка сети (мс)'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='metrics')
    metric_type = models.CharField(max_length=50, choices=METRIC_TYPES)
    value = models.FloatField() # Используем Float, чтобы хранить и проценты (45.5), и целые числа
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Метрика"
        verbose_name_plural = "Метрики"
        ordering = ['-timestamp']
        # Индексы критически важны для быстрого построения графиков
        indexes = [
            models.Index(fields=['device', 'metric_type', '-timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.device.name} - {self.metric_type}: {self.value} ({self.timestamp})"
    
    
class PrintJob(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='print_jobs')
    user_name = models.CharField(max_length=150) # Имя пользователя в Windows
    document_name = models.CharField(max_length=255)
    pages = models.PositiveIntegerField()
    printer_name = models.CharField(max_length=255)
    timestamp = models.DateTimeField(default=timezone.now)
    # file = models.FileField(upload_to='print_archives/', null=True, blank=True) # На будущее

    def __str__(self):
        return f"{self.document_name} ({self.pages} p.) by {self.user_name}"


class MonitoringSetting(models.Model):
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='monitoring_settings')
    retention_days = models.PositiveIntegerField(default=365)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки мониторинга"
        verbose_name_plural = "Настройки мониторинга"

    def __str__(self):
        return f"{self.device.name}: retention {self.retention_days} days"


class RawMetric(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='metrics_raw')
    code = models.CharField(max_length=100)
    value = models.FloatField()
    unit = models.CharField(max_length=20, blank=True)
    timestamp = models.DateTimeField()
    labels = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сырая метрика"
        verbose_name_plural = "Сырые метрики"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', 'code', '-timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.device.name} - {self.code}: {self.value} ({self.timestamp})"


class TrackedVM(models.Model):
    STATUS_CHOICES = [
        ('running', 'Включена'),
        ('off', 'Выключена'),
        ('paused', 'Пауза'),
        ('saved', 'Сохранена'),
        ('unknown', 'Неизвестно'),
    ]

    name = models.CharField(max_length=200, unique=True)
    host_device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='tracked_vms')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unknown')
    cpu_usage = models.FloatField(null=True, blank=True)
    memory_usage = models.FloatField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Отслеживаемая ВМ"
        verbose_name_plural = "Отслеживаемые ВМ"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.status})"

  

# Вычисленные (уровень 2) метрики
class ComputedMetric(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='metrics_computed')
    code = models.CharField(max_length=100)
    value = models.FloatField()
    unit = models.CharField(max_length=20, blank=True)
    window = models.CharField(max_length=20)
    timestamp = models.DateTimeField()
    labels = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Вычисленная метрика"
        verbose_name_plural = "Вычисленные метрики"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', 'code', '-timestamp']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.device.name} - {self.code}: {self.value} ({self.timestamp})"


class AgentStatus(models.Model):
    STATUS_CHOICES = [
        ('ok', 'OK'),
        ('error', 'Error'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='agent_statuses')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ok')
    message = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Статус агента"
        verbose_name_plural = "Статусы агентов"
        ordering = ['-updated_at']


class DiagnosticReport(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='diagnostic_reports')
    summary = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='low')
    issues = models.JSONField(default=list, blank=True)
    recommendations = models.JSONField(default=list, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Диагностический отчет"
        verbose_name_plural = "Диагностические отчеты"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'severity', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
        ]

    def __str__(self):
        return f"{self.device.name} - {self.severity}"

# ... другие модели (например, Request для заявок)
