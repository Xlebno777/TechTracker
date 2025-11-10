# inventory_api/serializers.py

from rest_framework import serializers
from .models import Device, DeviceType, Location, UserProfile, ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs, Cartridge, CartridgeLog, Log
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

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

# --- UserListSerializer: Для использования в списках устройств (owner, assigned_to) ---
# Не включает profile, чтобы избежать цикла
class UserListSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'groups']
        # exclude = ['password', 'profile'] # profile исключаем

# --- UserProfileForDeviceSerializer: Упрощённый профиль для DeviceSerializer (если используется Вариант B) ---
# Не используется в Варианте A, но оставим для ясности
# class UserProfileForDeviceSerializer(serializers.ModelSerializer):
#     favorite_devices = serializers.PrimaryKeyRelatedField(many=True, read_only=True) # Только ID устройств
#     class Meta:
#         model = UserProfile
#         fields = ['id', 'user', 'favorite_devices']

# --- UserWithProfileForDeviceSerializer: Для DeviceSerializer (если используется Вариант B) ---
# Не используется в Варианте A, но оставим для ясности
# class UserWithProfileForDeviceSerializer(serializers.ModelSerializer):
#     groups = GroupSerializer(many=True, read_only=True)
#     profile = UserProfileForDeviceSerializer(read_only=True)
#     class Meta:
#         model = User
#         fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'groups', 'profile']

class LogSerializer(serializers.ModelSerializer):
    # created_by будет определяться автоматически при создании (см. ViewSet)
    created_by = UserListSerializer(read_only=True) # Показываем имя пользователя (или строку)
    # created_by = serializers.StringRelatedField(read_only=True) # Или просто строку
    device = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all()) # Для создания/обновления передаём ID
    # device = DeviceSerializer(read_only=True) # Для чтения возвращаем объект

    class Meta:
        model = Log
        fields = '__all__' # Включаем все поля, включая priority и status
        # exclude = ['created_by'] # Если будем устанавливать created_by в ViewSet
        read_only_fields = ('timestamp', 'created_by') # created_by и timestamp не изменяются клиентом

    def to_representation(self, instance):
        """
        Переопределяем to_representation, чтобы возвращать связанные объекты (device, created_by) как объекты, а не ID.
        """
        representation = super().to_representation(instance)
        # device
        request = self.context.get('request')
        if instance.device and request and request.method in ['GET']:
            representation['device'] = DeviceSerializer(instance.device).data
        # created_by
        if instance.created_by:
             representation['created_by'] = UserListSerializer(instance.created_by).data
        return representation

# --- LimitedDeviceSerializer: Для использования в UserProfileSerializer ---
# Возвращает ограниченную информацию о Device, чтобы избежать цикла через owner/assigned_to
class LimitedDeviceSerializer(serializers.ModelSerializer):
    device_type = serializers.CharField(source='device_type.name', read_only=True)
    location = serializers.CharField(source='location.name', read_only=True)
    # Возвращаем owner и assigned_to как строки, а не объекты User
    owner = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = '__all__' # Включаем все, но owner/assigned_to переопределены

    def get_owner(self, obj):
        if obj.owner:
            return f"{obj.owner.username} ({obj.owner.first_name} {obj.owner.last_name})"
        return None

    def get_assigned_to(self, obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.username} ({obj.assigned_to.first_name} {obj.assigned_to.last_name})"
        return None

# --- UserProfileSerializer: Для использования в UserSerializer (например, /api/users/me/) ---
class UserProfileSerializer(serializers.ModelSerializer):
    # favorite_devices возвращаем как объекты LimitedDeviceSerializer, чтобы избежать цикла
    favorite_devices = LimitedDeviceSerializer(many=True, read_only=True, source='favorite_devices.all')
    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'favorite_devices']

# --- UserSerializer: Для получения информации о пользователе (например, /api/users/me/) ---
class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    profile = UserProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'groups', 'profile']

# --- Основной DeviceSerializer (Вариант A) ---
class DeviceSerializer(serializers.ModelSerializer):
    computer_specs = ComputerSpecsSerializer(required=False, read_only=True)
    printer_scanner_specs = PrinterScannerSpecsSerializer(required=False, read_only=True)
    network_specs = NetworkDeviceSpecsSerializer(required=False, read_only=True)
    # Возвращаем имена связанных справочников как строки
    device_type = serializers.CharField(source='device_type.name', read_only=True)
    location = serializers.CharField(source='location.name', read_only=True)
    logs_count = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    # --- ОБНОВЛЕНО: Используем UserListSerializer (Вариант A) ---
    owner = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    # --- /ОБНОВЛЕНО ---

    class Meta:
        model = Device
        fields = '__all__'

    def get_logs_count(self, obj):
        return obj.logs.count()

    def get_status(self, obj):
        """Преобразует статус на русский язык."""
        status_map = {
            'active': 'В работе',
            'in_repair': 'В ремонте',
            'retired': 'Списано',
            'in_stock': 'На складе',
            'reserved': 'В резерве'
        }
        return status_map.get(obj.status, 'Неизвестно')
    
    # --- НОВЫЕ МЕТОДЫ: Форматирование owner и assigned_to ---
    def get_owner(self, obj):
        if not obj.owner:
            return None
        return f"{obj.owner.username} ({obj.owner.first_name} {obj.owner.last_name})"

    def get_assigned_to(self, obj):
        if not obj.assigned_to:
            return None
        return f"{obj.assigned_to.username} ({obj.assigned_to.first_name} {obj.assigned_to.last_name})"
    # --- /НОВЫЕ МЕТОДЫ ---

# --- Сериализаторы для создания/обновления Device ---
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

        computer_specs_data = data.pop('computer_specs', None)
        printer_scanner_specs_data = data.pop('printer_scanner_specs', None)
        network_specs_data = data.pop('network_specs', None)

        validated_data = super().to_internal_value(data)

        validated_nested_data = {}
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
