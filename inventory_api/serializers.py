from rest_framework import serializers
from .models import (
    Device, DeviceType, Location, UserProfile, ComputerSpecs,
    PrinterScannerSpecs, NetworkDeviceSpecs, Cartridge, CartridgeLog,
    Log, Metric, PrintJob, MonitoringSetting, RawMetric, TrackedVM, ComputedMetric, AgentStatus, ServiceAgent,
    AgentCommand, DiagnosticReport,
    NetworkPath, NetworkOutage, NetworkAlertRule,
    NetworkMapSnapshot, NetworkMapNode, NetworkMapEdge,
    ForecastRun, ForecastPoint, StateEstimate, StateInferenceProfile, LSTMRemoteQueueJob,
    DecisionAction, DecisionCriterion, DecisionPolicy, DecisionPolicyLoss,
    DecisionPolicyAHPPairwise, DecisionRun, DecisionRunScore, DecisionRunAHP,
    DecisionRunUtility, DecisionFeedback, ApplicationUpdateJob, PageAccessRule,
)
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import Permission, User, Group
from rest_framework.authtoken.models import Token
from .agent_catalog import AGENT_METRIC_TASK_NAMES

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


class PermissionSerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source='content_type.app_label', read_only=True)
    model = serializers.CharField(source='content_type.model', read_only=True)
    label = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'app_label', 'model', 'label']

    def get_label(self, obj):
        return f"{obj.content_type.app_label}.{obj.codename}"


class ManagedGroupSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.select_related('content_type').all(),
        many=True,
        required=False,
    )
    permissions_detail = PermissionSerializer(source='permissions', many=True, read_only=True)
    users_count = serializers.IntegerField(source='user_set.count', read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permissions_detail', 'users_count']


class ManagedUserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        source='groups',
        queryset=Group.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )
    user_permissions = PermissionSerializer(many=True, read_only=True)
    user_permission_ids = serializers.PrimaryKeyRelatedField(
        source='user_permissions',
        queryset=Permission.objects.select_related('content_type').all(),
        many=True,
        required=False,
        write_only=True,
    )
    token_preview = serializers.SerializerMethodField()
    has_token = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email',
            'is_active', 'is_staff', 'is_superuser', 'last_login', 'date_joined',
            'groups', 'group_ids', 'user_permissions', 'user_permission_ids',
            'has_token', 'token_preview', 'password',
        ]
        read_only_fields = ['id', 'last_login', 'date_joined', 'has_token', 'token_preview']

    def _get_token(self, obj):
        if hasattr(obj, '_managed_user_serializer_token'):
            return obj._managed_user_serializer_token
        try:
            token = obj.auth_token
        except (Token.DoesNotExist, AttributeError):
            token = None
        obj._managed_user_serializer_token = token
        return token

    def get_has_token(self, obj):
        return self._get_token(obj) is not None

    def get_token_preview(self, obj):
        token = self._get_token(obj)
        if not token:
            return ''
        key = token.key or ''
        if len(key) <= 12:
            return key
        return f"{key[:6]}...{key[-6:]}"

    def create(self, validated_data):
        groups = validated_data.pop('groups', [])
        user_permissions = validated_data.pop('user_permissions', [])
        password = validated_data.pop('password', '')
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if groups:
            user.groups.set(groups)
        if user_permissions:
            user.user_permissions.set(user_permissions)
        return user

    def update(self, instance, validated_data):
        groups = validated_data.pop('groups', None)
        user_permissions = validated_data.pop('user_permissions', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if groups is not None:
            instance.groups.set(groups)
        if user_permissions is not None:
            instance.user_permissions.set(user_permissions)
        return instance


class PageAccessRuleSerializer(serializers.ModelSerializer):
    allowed_groups = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        many=True,
        required=False,
    )
    allowed_groups_detail = GroupSerializer(source='allowed_groups', many=True, read_only=True)
    allowed_group_names = serializers.SerializerMethodField()

    class Meta:
        model = PageAccessRule
        fields = [
            'id', 'route_name', 'label', 'section', 'icon', 'order', 'is_enabled',
            'allowed_groups', 'allowed_groups_detail', 'allowed_group_names',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'allowed_group_names']

    def get_allowed_group_names(self, obj):
        return [group.name for group in obj.allowed_groups.all()]

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
        cached = getattr(obj, 'logs_count_cached', None)
        if cached is not None:
            return cached
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
    agent_version = serializers.CharField(required=False, allow_blank=True, default='')
    service_name = serializers.CharField(required=False, allow_blank=True, default='TechTrackerAgent')
    service_status = serializers.CharField(required=False, allow_blank=True, default='')
    host_name = serializers.CharField(required=False, allow_blank=True, default='')
    os_name = serializers.CharField(required=False, allow_blank=True, default='')
    ip_address = serializers.CharField(required=False, allow_blank=True, default='')
    metrics_config = serializers.JSONField(required=False)
    supported_metrics = serializers.JSONField(required=False)
    device_info = serializers.JSONField(required=False)


class AgentCommandSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = AgentCommand
        fields = [
            'id', 'agent', 'command', 'status', 'payload', 'result_message',
            'created_by', 'created_by_username', 'acknowledged_at', 'started_at',
            'finished_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ServiceAgentSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    device_ip_address = serializers.CharField(source='device.ip_address', read_only=True)
    device_location = serializers.CharField(source='device.location.name', read_only=True, allow_null=True)
    device_type = serializers.CharField(source='device.device_type.name', read_only=True)
    pending_commands_count = serializers.SerializerMethodField()
    latest_command = serializers.SerializerMethodField()
    health_state = serializers.SerializerMethodField()

    class Meta:
        model = ServiceAgent
        fields = [
            'id', 'device', 'device_name', 'device_serial', 'device_ip_address',
            'device_location', 'device_type', 'name', 'agent_uid', 'installation_type',
            'service_name', 'service_status', 'agent_version', 'host_name', 'os_name',
            'ip_address', 'status', 'health_state', 'last_status_message', 'last_seen_at',
            'metrics_config', 'supported_metrics', 'desired_version', 'last_update_status',
            'last_update_started_at', 'last_update_completed_at', 'last_update_message',
            'pending_commands_count', 'latest_command', 'installed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_pending_commands_count(self, obj):
        return obj.commands.filter(status__in=['pending', 'acknowledged', 'running']).count()

    def get_latest_command(self, obj):
        command = obj.commands.order_by('-created_at').first()
        if not command:
            return None
        return AgentCommandSerializer(command).data

    def get_health_state(self, obj):
        if obj.status == 'error':
            return 'error'
        if not obj.last_seen_at:
            return obj.status or 'unknown'
        if timezone.now() - obj.last_seen_at > timedelta(minutes=10):
            return 'offline'
        return obj.status or 'unknown'


class AgentMetricsConfigSerializer(serializers.Serializer):
    enabled_tasks = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
    )

    def validate_enabled_tasks(self, value):
        known = set(AGENT_METRIC_TASK_NAMES)
        cleaned = []
        unknown = []
        for item in value:
            name = str(item).strip()
            if not name:
                continue
            if name not in known:
                unknown.append(name)
                continue
            if name not in cleaned:
                cleaned.append(name)
        if unknown:
            raise serializers.ValidationError(f"Unknown metric tasks: {', '.join(unknown)}")
        return cleaned


class AgentRestartRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class AgentUpdateRequestSerializer(serializers.Serializer):
    target_version = serializers.CharField(required=False, allow_blank=True, default='')
    installer_url = serializers.URLField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class AgentCommandResultSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    status = serializers.ChoiceField(choices=['running', 'success', 'failed'])
    result_message = serializers.CharField(required=False, allow_blank=True, default='')


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


class StateInferenceProfileSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = StateInferenceProfile
        fields = [
            'id',
            'name',
            'version',
            'is_active',
            'notes',
            'thresholds',
            'forecast_metric_controls',
            'orchestrator_controls',
            'risk_ratio_baseline',
            'risk_ratio_scale',
            'medium_risk_level',
            'critical_risk_level',
            'overall_hint_weight',
            'softmax_temperature',
            'score_weights',
            's0_bias',
            's0_effective_weight',
            's0_avg_weight',
            's0_medium_weight',
            's0_critical_weight',
            's1_bias',
            's1_avg_weight',
            's1_medium_weight',
            's1_markov_weight',
            's2_bias',
            's2_effective_power',
            's2_critical_weight',
            's2_medium_weight',
            's2_markov_weight',
            'confidence_max',
            'confidence_base',
            'confidence_component_weight',
            'confidence_feature_weight',
            'confidence_margin_weight',
            'confidence_component_cap',
            'created_by',
            'created_by_username',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_by', 'created_by_username', 'created_at', 'updated_at']

    def validate_thresholds(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("thresholds must be an object.")
        normalized = {}
        for key, raw in value.items():
            metric_code = str(key or '').strip()
            if not metric_code:
                continue
            try:
                parsed = float(raw)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"Invalid threshold for metric '{metric_code}'.")
            if parsed <= 0:
                raise serializers.ValidationError(f"Threshold for metric '{metric_code}' must be > 0.")
            normalized[metric_code] = parsed
        return normalized

    def validate_score_weights(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("score_weights must be an object.")
        normalized = {}
        for state_key, state_payload in value.items():
            state_name = str(state_key or '').strip()
            if state_name not in {'s0', 's1', 's2'}:
                continue
            if not isinstance(state_payload, dict):
                raise serializers.ValidationError(f"score_weights['{state_name}'] must be an object.")
            normalized[state_name] = {}
            for feature_key, raw in state_payload.items():
                feature_name = str(feature_key or '').strip()
                if not feature_name:
                    continue
                try:
                    normalized[state_name][feature_name] = float(raw)
                except (TypeError, ValueError):
                    raise serializers.ValidationError(
                        f"score_weights['{state_name}']['{feature_name}'] must be numeric."
                    )
        return normalized

    def validate_forecast_metric_controls(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("forecast_metric_controls must be an object.")

        normalized = {}
        for key, raw in value.items():
            metric_code = str(key or '').strip()
            if not metric_code:
                continue
            if not isinstance(raw, dict):
                raise serializers.ValidationError(f"forecast_metric_controls['{metric_code}'] must be an object.")

            alpha_mode = str(raw.get('alpha_mode', 'auto') or 'auto').strip().lower()
            if alpha_mode not in {'auto', 'manual'}:
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['alpha_mode'] must be 'auto' or 'manual'."
                )

            try:
                manual_alpha = float(raw.get('manual_alpha_sarima', 0.5))
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['manual_alpha_sarima'] must be numeric."
                )
            if manual_alpha < 0 or manual_alpha > 1:
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['manual_alpha_sarima'] must be within [0, 1]."
                )

            trend_long_mode = str(raw.get('trend_long_mode', 'mean_regression') or 'mean_regression').strip().lower()
            if trend_long_mode not in {'mean_regression', 'upper_envelope_blend', 'upper_envelope_floor'}:
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['trend_long_mode'] must be one of "
                    "'mean_regression', 'upper_envelope_blend', 'upper_envelope_floor'."
                )

            try:
                trend_transition_steps = int(raw.get('trend_transition_steps', 0))
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['trend_transition_steps'] must be an integer."
                )
            if trend_transition_steps < 0 or trend_transition_steps > 10000:
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['trend_transition_steps'] must be within [0, 10000]."
                )

            try:
                trend_envelope_weight = float(raw.get('trend_envelope_weight', 0.0))
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['trend_envelope_weight'] must be numeric."
                )
            if trend_envelope_weight < 0 or trend_envelope_weight > 1:
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['trend_envelope_weight'] must be within [0, 1]."
                )

            try:
                bias_correction_strength = float(raw.get('bias_correction_strength', 0.0))
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['bias_correction_strength'] must be numeric."
                )
            if bias_correction_strength < 0 or bias_correction_strength > 1:
                raise serializers.ValidationError(
                    f"forecast_metric_controls['{metric_code}']['bias_correction_strength'] must be within [0, 1]."
                )

            normalized[metric_code] = {
                'sarima_enabled': bool(raw.get('sarima_enabled', True)),
                'lstm_enabled': bool(raw.get('lstm_enabled', True)),
                'alpha_mode': alpha_mode,
                'manual_alpha_sarima': manual_alpha,
                'trend_long_mode': trend_long_mode,
                'trend_transition_steps': trend_transition_steps,
                'trend_envelope_weight': trend_envelope_weight,
                'bias_correction_strength': bias_correction_strength,
            }
        return normalized

    def validate_orchestrator_controls(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("orchestrator_controls must be an object.")

        normalized = {}

        if 'alpha_version_aware' in value:
            normalized['alpha_version_aware'] = bool(value.get('alpha_version_aware'))

        if 'normalize_errors_by_scale' in value:
            normalized['normalize_errors_by_scale'] = bool(value.get('normalize_errors_by_scale'))

        if 'compatible_history_runs' in value:
            try:
                compatible_history_runs = int(value.get('compatible_history_runs'))
            except (TypeError, ValueError):
                raise serializers.ValidationError("orchestrator_controls['compatible_history_runs'] must be an integer.")
            if compatible_history_runs < 1 or compatible_history_runs > 50:
                raise serializers.ValidationError("orchestrator_controls['compatible_history_runs'] must be within [1, 50].")
            normalized['compatible_history_runs'] = compatible_history_runs

        if 'history_limit_per_segment' in value:
            try:
                history_limit = int(value.get('history_limit_per_segment'))
            except (TypeError, ValueError):
                raise serializers.ValidationError("orchestrator_controls['history_limit_per_segment'] must be an integer.")
            if history_limit < 1 or history_limit > 200:
                raise serializers.ValidationError("orchestrator_controls['history_limit_per_segment'] must be within [1, 200].")
            normalized['history_limit_per_segment'] = history_limit

        if 'error_scale_lookback_days' in value:
            try:
                lookback_days = int(value.get('error_scale_lookback_days'))
            except (TypeError, ValueError):
                raise serializers.ValidationError("orchestrator_controls['error_scale_lookback_days'] must be an integer.")
            if lookback_days < 1 or lookback_days > 3650:
                raise serializers.ValidationError("orchestrator_controls['error_scale_lookback_days'] must be within [1, 3650].")
            normalized['error_scale_lookback_days'] = lookback_days

        if 'winner_margin' in value:
            try:
                winner_margin = float(value.get('winner_margin'))
            except (TypeError, ValueError):
                raise serializers.ValidationError("orchestrator_controls['winner_margin'] must be numeric.")
            if winner_margin < 1.0 or winner_margin > 10.0:
                raise serializers.ValidationError("orchestrator_controls['winner_margin'] must be within [1.0, 10.0].")
            normalized['winner_margin'] = winner_margin

        if 'winner_weight' in value:
            try:
                winner_weight = float(value.get('winner_weight'))
            except (TypeError, ValueError):
                raise serializers.ValidationError("orchestrator_controls['winner_weight'] must be numeric.")
            if winner_weight < 0.5 or winner_weight > 1.0:
                raise serializers.ValidationError("orchestrator_controls['winner_weight'] must be within [0.5, 1.0].")
            normalized['winner_weight'] = winner_weight

        if 'segment_boundaries_hours' in value:
            raw_boundaries = value.get('segment_boundaries_hours')
            if not isinstance(raw_boundaries, (list, tuple)):
                raise serializers.ValidationError("orchestrator_controls['segment_boundaries_hours'] must be an array.")
            try:
                parsed_boundaries = [int(item) for item in raw_boundaries]
            except (TypeError, ValueError):
                raise serializers.ValidationError("orchestrator_controls['segment_boundaries_hours'] must contain integers.")
            parsed_boundaries = [item for item in parsed_boundaries if item > 0]
            parsed_boundaries = sorted(set(parsed_boundaries))
            if len(parsed_boundaries) < 2:
                raise serializers.ValidationError(
                    "orchestrator_controls['segment_boundaries_hours'] must contain at least two positive boundaries."
                )
            normalized['segment_boundaries_hours'] = parsed_boundaries

        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        probability_like = [
            'risk_ratio_baseline',
            'risk_ratio_scale',
            'medium_risk_level',
            'critical_risk_level',
            'overall_hint_weight',
            'softmax_temperature',
            'confidence_max',
            'confidence_base',
            'confidence_component_weight',
            'confidence_feature_weight',
            'confidence_margin_weight',
        ]
        for field in probability_like:
            if field not in attrs and self.instance is not None:
                continue
            value = attrs.get(field, getattr(self.instance, field, None))
            if value is None:
                continue
            if field == 'risk_ratio_scale':
                if value <= 0:
                    raise serializers.ValidationError({field: "Must be > 0."})
                continue
            if field == 'softmax_temperature':
                if float(value) <= 0:
                    raise serializers.ValidationError({field: "Must be > 0."})
                if float(value) > 5:
                    raise serializers.ValidationError({field: "Expected a value between 0 and 5."})
                continue
            if not (0 <= float(value) <= 1.5):
                raise serializers.ValidationError({field: "Expected a value between 0 and 1.5."})

        positive_fields = [
            's2_effective_power',
            'confidence_component_cap',
        ]
        for field in positive_fields:
            value = attrs.get(field, getattr(self.instance, field, None))
            if value is not None and float(value) <= 0:
                raise serializers.ValidationError({field: "Must be > 0."})
        return attrs


class LSTMRemoteQueueJobSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    run_model_kind = serializers.CharField(source='forecast_run.model_kind', read_only=True)
    run_status = serializers.CharField(source='forecast_run.status', read_only=True)

    class Meta:
        model = LSTMRemoteQueueJob
        fields = [
            'id', 'forecast_run', 'run_model_kind', 'run_status',
            'device', 'device_name', 'device_serial',
            'request_id', 'status', 'remote_job_id',
            'attempts_submit', 'attempts_poll', 'retry_count', 'max_retries',
            'next_retry_at', 'locked_until',
            'last_error', 'request_payload', 'submit_response', 'remote_snapshot',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ApplicationUpdateJobSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = ApplicationUpdateJob
        fields = [
            'id', 'status', 'current_version', 'target_version', 'release_channel',
            'manifest_url', 'git_ref', 'release_notes', 'parameters', 'log', 'error',
            'pid', 'created_by', 'created_by_username', 'started_at', 'finished_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class DecisionActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionAction
        fields = [
            'id', 'code', 'name', 'description', 'is_active', 'constraints_json',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DecisionCriterionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionCriterion
        fields = ['id', 'code', 'name', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class DecisionPolicyLossSerializer(serializers.ModelSerializer):
    action_name = serializers.CharField(source='action.name', read_only=True)
    action_code = serializers.CharField(source='action.code', read_only=True)

    class Meta:
        model = DecisionPolicyLoss
        fields = [
            'id', 'policy', 'action', 'action_name', 'action_code',
            'loss_s0', 'loss_s1', 'loss_s2',
            'fixed_cost', 'downtime_minutes', 'ops_effort',
            'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DecisionPolicyAHPPairwiseSerializer(serializers.ModelSerializer):
    criterion_i_code = serializers.CharField(source='criterion_i.code', read_only=True)
    criterion_j_code = serializers.CharField(source='criterion_j.code', read_only=True)

    class Meta:
        model = DecisionPolicyAHPPairwise
        fields = [
            'id', 'policy',
            'criterion_i', 'criterion_i_code',
            'criterion_j', 'criterion_j_code',
            'value', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DecisionPolicySerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    device_type_name = serializers.CharField(source='device_type.name', read_only=True)
    losses = DecisionPolicyLossSerializer(source='loss_rows', many=True, read_only=True)
    ahp_pairs = DecisionPolicyAHPPairwiseSerializer(source='ahp_pairwise', many=True, read_only=True)

    class Meta:
        model = DecisionPolicy
        fields = [
            'id', 'name', 'version', 'is_active',
            'scope', 'device_type', 'device_type_name', 'device', 'device_name', 'device_serial',
            'horizon', 'previous_version', 'notes', 'created_by', 'created_at', 'updated_at',
            'losses', 'ahp_pairs',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']


class DecisionRunScoreSerializer(serializers.ModelSerializer):
    action_name = serializers.CharField(source='action.name', read_only=True)
    action_code = serializers.CharField(source='action.code', read_only=True)

    class Meta:
        model = DecisionRunScore
        fields = [
            'id', 'run', 'action', 'action_name', 'action_code',
            'expected_loss', 'bayes_utility', 'ahp_utility', 'final_score',
            'rank', 'is_recommended', 'explanation', 'created_at',
        ]
        read_only_fields = fields


class DecisionRunAHPSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionRunAHP
        fields = ['id', 'run', 'weights', 'lambda_max', 'ci', 'cr', 'is_consistent', 'matrix', 'created_at']
        read_only_fields = fields


class DecisionRunUtilitySerializer(serializers.ModelSerializer):
    action_name = serializers.CharField(source='action.name', read_only=True)
    action_code = serializers.CharField(source='action.code', read_only=True)
    criterion_name = serializers.CharField(source='criterion.name', read_only=True)
    criterion_code = serializers.CharField(source='criterion.code', read_only=True)

    class Meta:
        model = DecisionRunUtility
        fields = [
            'id', 'run',
            'action', 'action_name', 'action_code',
            'criterion', 'criterion_name', 'criterion_code',
            'utility', 'evidence', 'created_at',
        ]
        read_only_fields = fields


class DecisionFeedbackSerializer(serializers.ModelSerializer):
    actual_action_name = serializers.CharField(source='actual_action.name', read_only=True)
    actual_action_code = serializers.CharField(source='actual_action.code', read_only=True)

    class Meta:
        model = DecisionFeedback
        fields = [
            'id', 'run', 'actual_action', 'actual_action_name', 'actual_action_code',
            'outcome_state', 'outage_minutes', 'incident_cost', 'notes',
            'created_by', 'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class DecisionRunSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)
    device_serial = serializers.CharField(source='device.serial_number', read_only=True)
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    recommended_action_name = serializers.CharField(source='recommended_action.name', read_only=True)
    recommended_action_code = serializers.CharField(source='recommended_action.code', read_only=True)
    scores = DecisionRunScoreSerializer(many=True, read_only=True)
    ahp = DecisionRunAHPSerializer(read_only=True)
    criterion_utilities = DecisionRunUtilitySerializer(many=True, read_only=True)
    feedback = DecisionFeedbackSerializer(read_only=True)

    class Meta:
        model = DecisionRun
        fields = [
            'id', 'device', 'device_name', 'device_serial',
            'policy', 'policy_name', 'horizon',
            'mode', 'status',
            'risk_snapshot',
            'recommended_action', 'recommended_action_name', 'recommended_action_code',
            'explanation',
            'created_by', 'created_at', 'updated_at',
            'scores', 'ahp', 'criterion_utilities', 'feedback',
        ]
        read_only_fields = fields


class DecisionRecommendationRequestSerializer(serializers.Serializer):
    serial = serializers.CharField(required=False, allow_blank=True)
    device = serializers.IntegerField(required=False)
    horizon = serializers.ChoiceField(choices=['24h', '7d', '30d'], required=False, default='24h')
    policy_id = serializers.IntegerField(required=False)
    mode = serializers.ChoiceField(choices=['bayes', 'advanced'], required=False, default='bayes')
    overall_weight_markov = serializers.FloatField(required=False, default=0.65)
    risk_metric_min_risk = serializers.FloatField(required=False, default=0.08)
    risk_metric_min_contribution = serializers.FloatField(required=False, default=0.03)
    risk_metric_top_k_fallback = serializers.IntegerField(required=False, default=3, min_value=1, max_value=10)
    bayes_weight = serializers.FloatField(required=False, default=0.5)
    ahp_weight = serializers.FloatField(required=False, default=0.5)
    sensitivity_weights = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        if not attrs.get('serial') and not attrs.get('device'):
            raise serializers.ValidationError("Either 'serial' or 'device' must be provided.")
        return attrs


class DecisionAHPPairInputSerializer(serializers.Serializer):
    criterion_i = serializers.IntegerField()
    criterion_j = serializers.IntegerField()
    value = serializers.FloatField()


class DecisionAHPMatrixUpsertSerializer(serializers.Serializer):
    pairs = DecisionAHPPairInputSerializer(many=True)


class DecisionFeedbackCreateSerializer(serializers.Serializer):
    actual_action = serializers.IntegerField(required=False, allow_null=True)
    outcome_state = serializers.ChoiceField(choices=['s0', 's1', 's2', 'unknown'])
    outage_minutes = serializers.FloatField(required=False, default=0.0)
    incident_cost = serializers.FloatField(required=False, default=0.0)
    notes = serializers.CharField(required=False, allow_blank=True, default='')


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
