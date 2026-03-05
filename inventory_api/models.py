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


class NetworkPath(models.Model):
    STATE_CHOICES = [
        ('unknown', 'Unknown'),
        ('up', 'Up'),
        ('down', 'Down'),
    ]

    src_device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='network_paths_src')
    dst_device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='network_paths_dst')
    enabled = models.BooleanField(default=True)
    interval_sec = models.PositiveIntegerField(default=60)
    timeout_sec = models.PositiveIntegerField(default=3)
    packet_count = models.PositiveIntegerField(default=1)
    fail_threshold = models.PositiveIntegerField(default=3)
    recover_threshold = models.PositiveIntegerField(default=2)
    last_state = models.CharField(max_length=20, choices=STATE_CHOICES, default='unknown')
    consecutive_failures = models.PositiveIntegerField(default=0)
    consecutive_successes = models.PositiveIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_latency_ms = models.FloatField(null=True, blank=True)
    last_packet_loss_pct = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Сетевой путь"
        verbose_name_plural = "Сетевые пути"
        ordering = ['src_device__name', 'dst_device__name']
        constraints = [
            models.UniqueConstraint(fields=['src_device', 'dst_device'], name='uniq_network_path_src_dst'),
            models.CheckConstraint(condition=~models.Q(src_device=models.F('dst_device')), name='chk_network_path_src_ne_dst'),
        ]
        indexes = [
            models.Index(fields=['enabled', 'last_state']),
            models.Index(fields=['src_device', 'dst_device']),
        ]

    def __str__(self):
        return f"{self.src_device.name} -> {self.dst_device.name}"


class NetworkOutage(models.Model):
    path = models.ForeignKey(NetworkPath, on_delete=models.CASCADE, related_name='outages')
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_sec = models.BigIntegerField(null=True, blank=True)
    fail_count = models.PositiveIntegerField(default=0)
    recover_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    last_probe_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сетевое пропадание"
        verbose_name_plural = "Сетевые пропадания"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['path', 'is_active', '-started_at']),
            models.Index(fields=['is_active', '-started_at']),
        ]

    def __str__(self):
        return f"{self.path} ({self.started_at} - {self.ended_at or 'active'})"


class NetworkAlertRule(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    COMPARISON_CHOICES = [
        ('gt', '>'),
        ('gte', '>='),
        ('lt', '<'),
        ('lte', '<='),
        ('eq', '='),
        ('ne', '!='),
    ]

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    metric_code = models.CharField(max_length=100)
    window = models.CharField(max_length=20, default='24h')
    comparison = models.CharField(max_length=10, choices=COMPARISON_CHOICES, default='gt')
    threshold_value = models.FloatField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Правило сетевой тревоги"
        verbose_name_plural = "Правила сетевых тревог"
        ordering = ['order', 'name']
        indexes = [
            models.Index(fields=['enabled', 'order']),
            models.Index(fields=['metric_code', 'window']),
        ]

    def __str__(self):
        return f"{self.code} ({self.metric_code} {self.comparison} {self.threshold_value})"


class NetworkMapSnapshot(models.Model):
    STATUS_CHOICES = [
        ('ok', 'OK'),
        ('error', 'Error'),
    ]

    generated_at = models.DateTimeField(default=timezone.now)
    source_window_hours = models.PositiveIntegerField(default=24)
    node_count = models.PositiveIntegerField(default=0)
    edge_count = models.PositiveIntegerField(default=0)
    build_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ok')
    error = models.TextField(blank=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Снимок сетевой карты"
        verbose_name_plural = "Снимки сетевой карты"
        ordering = ['-generated_at', '-id']
        indexes = [
            models.Index(fields=['is_current', '-generated_at']),
            models.Index(fields=['status', '-generated_at']),
        ]

    def __str__(self):
        return f"NetworkMapSnapshot #{self.id} ({self.status})"


class NetworkMapNode(models.Model):
    snapshot = models.ForeignKey(NetworkMapSnapshot, on_delete=models.CASCADE, related_name='nodes')
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_map_nodes')
    device_name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_type_name = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Узел сетевой карты"
        verbose_name_plural = "Узлы сетевой карты"
        ordering = ['device_name', 'id']
        indexes = [
            models.Index(fields=['snapshot', 'device_name']),
            models.Index(fields=['snapshot', 'ip_address']),
        ]

    def __str__(self):
        return f"{self.device_name} ({self.ip_address or 'no-ip'})"


class NetworkMapEdge(models.Model):
    STATE_CHOICES = [
        ('unknown', 'Unknown'),
        ('up', 'Up'),
        ('down', 'Down'),
        ('none', 'None'),
    ]

    snapshot = models.ForeignKey(NetworkMapSnapshot, on_delete=models.CASCADE, related_name='edges')
    path = models.ForeignKey(NetworkPath, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_map_edges')
    src_device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_map_edges_src')
    dst_device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True, related_name='network_map_edges_dst')
    src_name = models.CharField(max_length=200)
    dst_name = models.CharField(max_length=200)
    dst_ip = models.GenericIPAddressField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='unknown')
    latency_ms = models.FloatField(null=True, blank=True)
    packet_loss_pct = models.FloatField(null=True, blank=True)
    confidence_pct = models.FloatField(null=True, blank=True)
    outage_count_24h = models.PositiveIntegerField(default=0)
    has_active_outage = models.BooleanField(default=False)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Ребро сетевой карты"
        verbose_name_plural = "Ребра сетевой карты"
        ordering = ['src_name', 'dst_name', 'id']
        indexes = [
            models.Index(fields=['snapshot', 'state']),
            models.Index(fields=['snapshot', 'src_device', 'dst_device']),
        ]

    def __str__(self):
        return f"{self.src_name} -> {self.dst_name} ({self.state})"


class ForecastRun(models.Model):
    MODEL_KIND_CHOICES = [
        ('sarima', 'SARIMA'),
        ('lstm', 'LSTM'),
        ('ensemble', 'Ensemble'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='forecast_runs')
    model_kind = models.CharField(max_length=20, choices=MODEL_KIND_CHOICES, default='ensemble')
    horizon_set = models.CharField(max_length=100, default='24h,7d,30d')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    quality = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Запуск прогноза"
        verbose_name_plural = "Запуски прогноза"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'model_kind', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.device.name} {self.model_kind} ({self.status})"


class ForecastPoint(models.Model):
    HORIZON_CHOICES = [
        ('24h', '24h'),
        ('7d', '7d'),
        ('30d', '30d'),
    ]

    run = models.ForeignKey(ForecastRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='points')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='forecast_points')
    metric_code = models.CharField(max_length=100)
    horizon = models.CharField(max_length=20, choices=HORIZON_CHOICES)
    target_ts = models.DateTimeField()
    model_kind = models.CharField(max_length=20, choices=ForecastRun.MODEL_KIND_CHOICES, default='ensemble')
    y_hat = models.FloatField()
    p10 = models.FloatField(null=True, blank=True)
    p50 = models.FloatField(null=True, blank=True)
    p90 = models.FloatField(null=True, blank=True)
    alpha = models.FloatField(null=True, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Точка прогноза"
        verbose_name_plural = "Точки прогноза"
        ordering = ['-target_ts', '-id']
        indexes = [
            models.Index(fields=['device', 'metric_code', 'horizon', '-target_ts']),
            models.Index(fields=['model_kind', 'horizon', '-target_ts']),
            models.Index(fields=['run', '-target_ts']),
        ]

    def __str__(self):
        return f"{self.device.name} {self.metric_code} {self.horizon} -> {self.y_hat}"


class StateEstimate(models.Model):
    HORIZON_CHOICES = [
        ('24h', '24h'),
        ('7d', '7d'),
        ('30d', '30d'),
    ]
    STATE_CHOICES = [
        ('s0', 'S0'),
        ('s1', 'S1'),
        ('s2', 'S2'),
        ('unknown', 'Unknown'),
    ]

    run = models.ForeignKey(ForecastRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='state_estimates')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='state_estimates')
    horizon = models.CharField(max_length=20, choices=HORIZON_CHOICES)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='unknown')
    p_s0 = models.FloatField(null=True, blank=True)
    p_s1 = models.FloatField(null=True, blank=True)
    p_s2 = models.FloatField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Оценка состояния сервера"
        verbose_name_plural = "Оценки состояния сервера"
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['device', 'horizon', '-timestamp']),
            models.Index(fields=['state', '-timestamp']),
            models.Index(fields=['run', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.device.name} {self.horizon}: {self.state}"
