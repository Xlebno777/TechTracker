from rest_framework import serializers
from .models import (
    Device, DeviceType, Location, UserProfile, ComputerSpecs,
    PrinterScannerSpecs, NetworkDeviceSpecs, Cartridge, CartridgeLog,
    Log, Metric, PrintJob, MonitoringSetting, RawMetric, TrackedVM, ComputedMetric, AgentStatus, DiagnosticReport,
    NetworkPath, NetworkOutage, NetworkAlertRule,
    NetworkMapSnapshot, NetworkMapNode, NetworkMapEdge,
    ForecastRun, ForecastPoint, StateEstimate
)
from django.utils import timezone
from django.contrib.auth.models import User, Group

# --- Serializers для справочников ---
class DeviceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceType
        fields = '__all__'

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'

# --- Serializers для специфичных данных ---
class ComputerSpecsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComputerSpecs
        exclude = ['device']

    def to_internal_value(self, data):
        data = data.copy()
        data.pop('device', None)
        return super().to_internal_value(data)

class PrinterScannerSpecsSerializer(serializers.ModelSerializer):
    current_cartridge = serializers.PrimaryKeyRelatedField(queryset=Cartridge.objects.all(), required=False, allow_null=True)
    class Meta:
        model = PrinterScannerSpecs
        exclude = ['device']

    def to_internal_value(self, data):
        data = data.copy()
        data.pop('device', None)
        return super().to_internal_value(data)

class NetworkDeviceSpecsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkDeviceSpecs
        exclude = ['device']

    def to_internal_value(self, data):
        data = data.copy()
        data.pop('device', None)
        return super().to_internal_value(data)

# --- Serializers для других моделей ---
class CartridgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cartridge
        fields = '__all__'
        read_only_fields = ('remaining_pages',)

class CartridgeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartridgeLog
        fields = '__all__'

# --- Сериализаторы для Group и User ---
class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

# --- UserListSerializer: Легковесный сериализатор пользователя ---
# Используется в списках устройств и логах. НЕ содержит profile во избежание рекурсии.
class UserListSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'groups']

class LogSerializer(serializers.ModelSerializer):
    # Возвращаем объект пользователя для created_by
    created_by = UserListSerializer(read_only=True)
    # При чтении возвращаем объект устройства, при записи принимаем ID
    device = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all())

    class Meta:
        model = Log
        fields = '__all__'
        read_only_fields = ('timestamp', 'created_by')

    def to_representation(self, instance):
        """
        При GET запросах возвращаем вложенный объект устройства для удобства отображения.
        """
        representation = super().to_representation(instance)
        request = self.context.get('request')
        if instance.device and request and request.method in ['GET']:
            # Используем LimitedDeviceSerializer чтобы не тянуть лишние вложенности в логах
            representation['device'] = LimitedDeviceSerializer(instance.device).data
        return representation

# --- LimitedDeviceSerializer ---
# Используется внутри UserProfileSerializer для списка избранного.
# Возвращает объекты owner/location/type, но НЕ использует полные сериализаторы,
# которые могут вызвать тяжелые запросы.
class LimitedDeviceSerializer(serializers.ModelSerializer):
    device_type = DeviceTypeSerializer(read_only=True)
    location = LocationSerializer(read_only=True)
    owner = UserListSerializer(read_only=True)
    assigned_to = UserListSerializer(read_only=True)

    class Meta:
        model = Device
        fields = '__all__'

# --- UserProfileSerializer ---
class UserProfileSerializer(serializers.ModelSerializer):
    # favorite_devices возвращаем как объекты LimitedDeviceSerializer
    favorite_devices = LimitedDeviceSerializer(many=True, read_only=True, source='favorite_devices.all')

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'favorite_devices']

# --- UserSerializer: Полный сериализатор пользователя ---
# Используется для /api/users/me/
class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'groups', 'profile']

# --- Основной DeviceSerializer ---
# Используется для CRUD операций с устройствами
class DeviceSerializer(serializers.ModelSerializer):
    # Вложенные спецификации
    computer_specs = ComputerSpecsSerializer(required=False, read_only=True)
    printer_scanner_specs = PrinterScannerSpecsSerializer(required=False, read_only=True)
    network_specs = NetworkDeviceSpecsSerializer(required=False, read_only=True)
    
    # Вложенные объекты справочников (возвращаем объекты {id, name})
    device_type = DeviceTypeSerializer(read_only=True)
    location = LocationSerializer(read_only=True)
    
    # Вложенные пользователи (возвращаем объекты {id, username...})
    owner = UserListSerializer(read_only=True)
    assigned_to = UserListSerializer(read_only=True)
    
    # Вычисляемое поле
    logs_count = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = '__all__'
        extra_fields = ['logs_count']

    def get_logs_count(self, obj):
        return obj.logs.count()

# --- Сериализаторы для создания/обновления Device ---
# Отдельный сериализатор для записи, чтобы обрабатывать вложенные спецификации
class DeviceCreateUpdateSerializer(serializers.ModelSerializer):
    computer_specs = ComputerSpecsSerializer(required=False)
    printer_scanner_specs = PrinterScannerSpecsSerializer(required=False)
    network_specs = NetworkDeviceSpecsSerializer(required=False)

    class Meta:
        model = Device
        fields = '__all__'
        read_only_fields = ('qr_code_id', 'created_at', 'updated_at')

    def is_spec_empty(self, spec_data):
        if not spec_data:
            return True
        for value in spec_data.values():
            if value not in [None, '', [], {}, False]:
                return False
        return True

    def to_internal_value(self, data):
        data = data.copy()
        
        # Извлекаем данные спецификаций
        computer_specs_data = data.pop('computer_specs', None)
        printer_scanner_specs_data = data.pop('printer_scanner_specs', None)
        network_specs_data = data.pop('network_specs', None)

        validated_data = super().to_internal_value(data)

        validated_nested_data = {}
        
        # Валидация спецификаций
        if computer_specs_data is not None and not self.is_spec_empty(computer_specs_data):
            nested_serializer = self.fields['computer_specs']
            validated_computer_data = nested_serializer.to_internal_value(computer_specs_data)
            validated_computer_data.pop('device', None)
            validated_nested_data['computer_specs'] = validated_computer_data

        if printer_scanner_specs_data is not None and not self.is_spec_empty(printer_scanner_specs_data):
            nested_serializer = self.fields['printer_scanner_specs']
            validated_printer_data = nested_serializer.to_internal_value(printer_scanner_specs_data)
            validated_printer_data.pop('device', None)
            validated_nested_data['printer_scanner_specs'] = validated_printer_data

        if network_specs_data is not None and not self.is_spec_empty(network_specs_data):
            nested_serializer = self.fields['network_specs']
            validated_network_data = nested_serializer.to_internal_value(network_specs_data)
            validated_network_data.pop('device', None)
            validated_nested_data['network_specs'] = validated_network_data

        validated_data.update(validated_nested_data)
        self._validated_nested_data = validated_nested_data

        return validated_data

    def create(self, validated_data):
        computer_specs_data = validated_data.pop('computer_specs', None)
        printer_scanner_specs_data = validated_data.pop('printer_scanner_specs', None)
        network_specs_data = validated_data.pop('network_specs', None)

        device = Device.objects.create(**validated_data)

        if computer_specs_data is not None:
            ComputerSpecs.objects.create(device=device, **computer_specs_data)
        if printer_scanner_specs_data is not None:
            PrinterScannerSpecs.objects.create(device=device, **printer_scanner_specs_data)
        if network_specs_data is not None:
            NetworkDeviceSpecs.objects.create(device=device, **network_specs_data)

        return device

    def update(self, instance, validated_data):
        computer_specs_data = validated_data.pop('computer_specs', None)
        printer_scanner_specs_data = validated_data.pop('printer_scanner_specs', None)
        network_specs_data = validated_data.pop('network_specs', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if computer_specs_data is not None:
            specs, _ = ComputerSpecs.objects.get_or_create(device=instance)
            for key, value in computer_specs_data.items():
                setattr(specs, key, value)
            specs.save()

        if printer_scanner_specs_data is not None:
            specs, _ = PrinterScannerSpecs.objects.get_or_create(device=instance)
            for key, value in printer_scanner_specs_data.items():
                setattr(specs, key, value)
            specs.save()

        if network_specs_data is not None:
            specs, _ = NetworkDeviceSpecs.objects.get_or_create(device=instance)
            for key, value in network_specs_data.items():
                setattr(specs, key, value)
            specs.save()

        return instance
    
class MetricSerializer(serializers.ModelSerializer):
    # Поле для приема серийного номера (только для записи)
    serial_number = serializers.CharField(write_only=True)
    
    # Поле device теперь только для чтения (сервер сам его заполнит)
    device = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Metric
        fields = ['id', 'device', 'serial_number', 'metric_type', 'value', 'timestamp']
        read_only_fields = ('timestamp', 'device')

    def create(self, validated_data):
        # 1. Достаем серийный номер из пришедших данных
        serial = validated_data.pop('serial_number')
        
        try:
            # 2. Ищем устройство в базе по серийнику
            device = Device.objects.get(serial_number=serial)
        except Device.DoesNotExist:
            # Если устройства нет - выбрасываем ошибку (агент увидит 400 Bad Request)
            raise serializers.ValidationError(f"Device with serial number '{serial}' not found.")

        # 3. Создаем метрику, привязанную к найденному устройству
        metric = Metric.objects.create(device=device, **validated_data)
        return metric
    
class PrintJobSerializer(serializers.ModelSerializer):
    # Агент шлет серийный номер ПК, к которому подключен принтер
    serial_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # Альтернатива: агент может прислать IP принтера
    printer_ip = serializers.CharField(write_only=True, required=False, allow_blank=True)
    device = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = PrintJob
        fields = ['id', 'serial_number', 'printer_ip', 'device', 'user_name', 'document_name', 'pages', 'printer_name', 'timestamp']

    def create(self, validated_data):
        serial = (validated_data.pop('serial_number', '') or '').strip()
        printer_ip = (validated_data.pop('printer_ip', '') or '').strip()

        device = None
        if printer_ip:
            device = Device.objects.filter(ip_address=printer_ip).first()

        if device is None and serial:
            device = Device.objects.filter(serial_number=serial).first()

        if device is None:
            # Последняя попытка: матчинг по имени принтера (если совпадает с Device.name)
            printer_name = validated_data.get('printer_name')
            if printer_name:
                device = Device.objects.filter(name=printer_name).first()

        if device is None:
            raise serializers.ValidationError("Printer device not found by IP/serial/name")
        
        # Здесь можно добавить логику уменьшения счетчика картриджа!
        # device.printer_scanner_specs.current_cartridge.remaining_pages -= validated_data['pages']
        # device.printer_scanner_specs.current_cartridge.save()
        
        return PrintJob.objects.create(device=device, **validated_data)


class RawMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawMetric
        fields = ['id', 'device', 'code', 'value', 'unit', 'timestamp', 'labels', 'created_at']
        read_only_fields = ('id', 'created_at')


class ComputedMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComputedMetric
        fields = ['id', 'device', 'code', 'value', 'unit', 'window', 'timestamp', 'labels', 'created_at']
        read_only_fields = ('id', 'created_at')


class AgentStatusSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    class Meta:
        model = AgentStatus
        fields = ['id', 'device', 'device_name', 'device_serial', 'status', 'message', 'updated_at']
        read_only_fields = ('id', 'updated_at')


class AgentStatusReportSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    status = serializers.ChoiceField(choices=['ok', 'error'])
    message = serializers.CharField(required=False, allow_blank=True, default='')


class DiagnosticReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticReport
        fields = '__all__'
        read_only_fields = ('id', 'created_at')


class DiagnosticRunSerializer(serializers.Serializer):
    serial = serializers.CharField(required=False, allow_blank=True)
    mode = serializers.ChoiceField(choices=['llm', 'rules'], required=False)


class ForecastRunSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)

    class Meta:
        model = ForecastRun
        fields = [
            'id', 'device', 'device_name', 'device_serial',
            'model_kind', 'horizon_set', 'status',
            'started_at', 'finished_at',
            'parameters', 'quality', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ForecastPointSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    run_model_kind = serializers.CharField(source='run.model_kind', read_only=True)
    run_status = serializers.CharField(source='run.status', read_only=True)

    class Meta:
        model = ForecastPoint
        fields = [
            'id', 'run', 'run_model_kind', 'run_status',
            'device', 'device_name', 'device_serial',
            'metric_code', 'horizon', 'target_ts', 'model_kind',
            'y_hat', 'p10', 'p50', 'p90', 'alpha',
            'labels', 'created_at',
        ]
        read_only_fields = fields


class StateEstimateSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    run_model_kind = serializers.CharField(source='run.model_kind', read_only=True)
    run_status = serializers.CharField(source='run.status', read_only=True)

    class Meta:
        model = StateEstimate
        fields = [
            'id', 'run', 'run_model_kind', 'run_status',
            'device', 'device_name', 'device_serial',
            'horizon', 'state',
            'p_s0', 'p_s1', 'p_s2', 'confidence',
            'evidence', 'timestamp', 'created_at',
        ]
        read_only_fields = fields


class NetworkPathSerializer(serializers.ModelSerializer):
    src_device_name = serializers.CharField(source='src_device.name', read_only=True)
    dst_device_name = serializers.CharField(source='dst_device.name', read_only=True)
    src_device_serial = serializers.CharField(source='src_device.serial_number', read_only=True)
    dst_device_serial = serializers.CharField(source='dst_device.serial_number', read_only=True)
    dst_ip = serializers.CharField(source='dst_device.ip_address', read_only=True)

    class Meta:
        model = NetworkPath
        fields = [
            'id', 'src_device', 'dst_device',
            'src_device_name', 'dst_device_name', 'src_device_serial', 'dst_device_serial', 'dst_ip',
            'enabled', 'interval_sec', 'timeout_sec', 'packet_count',
            'fail_threshold', 'recover_threshold',
            'last_state', 'consecutive_failures', 'consecutive_successes',
            'last_checked_at', 'last_latency_ms', 'last_packet_loss_pct',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = (
            'last_state', 'consecutive_failures', 'consecutive_successes',
            'last_checked_at', 'last_latency_ms', 'last_packet_loss_pct',
            'created_at', 'updated_at',
        )

    def validate(self, attrs):
        src = attrs.get('src_device') or getattr(self.instance, 'src_device', None)
        dst = attrs.get('dst_device') or getattr(self.instance, 'dst_device', None)

        if src and dst and src.id == dst.id:
            raise serializers.ValidationError("src_device and dst_device must be different.")

        if dst and not dst.ip_address:
            raise serializers.ValidationError("Destination device must have IP address.")

        timeout_sec = attrs.get('timeout_sec', getattr(self.instance, 'timeout_sec', 3))
        interval_sec = attrs.get('interval_sec', getattr(self.instance, 'interval_sec', 60))
        packet_count = attrs.get('packet_count', getattr(self.instance, 'packet_count', 1))
        fail_threshold = attrs.get('fail_threshold', getattr(self.instance, 'fail_threshold', 3))
        recover_threshold = attrs.get('recover_threshold', getattr(self.instance, 'recover_threshold', 2))

        if interval_sec < 5:
            raise serializers.ValidationError("interval_sec must be >= 5.")
        if timeout_sec < 1:
            raise serializers.ValidationError("timeout_sec must be >= 1.")
        if timeout_sec > interval_sec:
            raise serializers.ValidationError("timeout_sec must be <= interval_sec.")
        if packet_count < 1 or packet_count > 10:
            raise serializers.ValidationError("packet_count must be in range 1..10.")
        if fail_threshold < 1 or recover_threshold < 1:
            raise serializers.ValidationError("fail_threshold and recover_threshold must be >= 1.")

        return attrs


class NetworkOutageSerializer(serializers.ModelSerializer):
    path_src = serializers.CharField(source='path.src_device.name', read_only=True)
    path_dst = serializers.CharField(source='path.dst_device.name', read_only=True)
    path_dst_ip = serializers.CharField(source='path.dst_device.ip_address', read_only=True)

    class Meta:
        model = NetworkOutage
        fields = [
            'id', 'path', 'path_src', 'path_dst', 'path_dst_ip',
            'started_at', 'ended_at', 'duration_sec',
            'fail_count', 'recover_count', 'is_active',
            'last_probe_at', 'last_error', 'created_at',
        ]
        read_only_fields = (
            'id', 'path', 'path_src', 'path_dst', 'path_dst_ip',
            'started_at', 'ended_at', 'duration_sec',
            'fail_count', 'recover_count', 'is_active',
            'last_probe_at', 'last_error', 'created_at',
        )


class NetworkAlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkAlertRule
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at')


class NetworkMapNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkMapNode
        fields = [
            'id', 'snapshot', 'device', 'device_name', 'serial_number',
            'ip_address', 'device_type_name', 'status', 'last_seen',
        ]
        read_only_fields = fields


class NetworkMapEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkMapEdge
        fields = [
            'id', 'snapshot', 'path', 'src_device', 'dst_device',
            'src_name', 'dst_name', 'dst_ip', 'enabled', 'state',
            'latency_ms', 'packet_loss_pct', 'confidence_pct',
            'outage_count_24h', 'has_active_outage', 'last_checked_at',
        ]
        read_only_fields = fields


class NetworkMapSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkMapSnapshot
        fields = [
            'id', 'generated_at', 'source_window_hours',
            'node_count', 'edge_count', 'build_duration_ms',
            'status', 'error', 'is_current', 'created_at',
        ]
        read_only_fields = fields


class NetworkMapSnapshotDetailSerializer(NetworkMapSnapshotSerializer):
    nodes = NetworkMapNodeSerializer(many=True, read_only=True)
    edges = NetworkMapEdgeSerializer(many=True, read_only=True)

    class Meta(NetworkMapSnapshotSerializer.Meta):
        fields = NetworkMapSnapshotSerializer.Meta.fields + ['nodes', 'edges']


class RawMetricItemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=100)
    value = serializers.FloatField()
    unit = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    timestamp = serializers.DateTimeField(required=False)
    labels = serializers.JSONField(required=False, default=dict)

    def validate_timestamp(self, value):
        return value or timezone.now()


class RawMetricIngestSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    retention_days = serializers.IntegerField(required=False, min_value=1)
    metrics = RawMetricItemSerializer(many=True)
    device_info = serializers.JSONField(required=False)


class TrackedVMSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackedVM
        fields = [
            'id', 'name', 'host_device', 'status', 'cpu_usage',
            'memory_usage', 'uptime_seconds', 'last_seen', 'is_enabled'
        ]
        read_only_fields = ('last_seen',)


class TrackedVMSyncItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    status = serializers.CharField(required=False, allow_blank=True, default='unknown')
    cpu_usage = serializers.FloatField(required=False, allow_null=True)
    memory_usage = serializers.FloatField(required=False, allow_null=True)
    uptime_seconds = serializers.IntegerField(required=False, allow_null=True)


class TrackedVMSyncSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    vms = TrackedVMSyncItemSerializer(many=True)
