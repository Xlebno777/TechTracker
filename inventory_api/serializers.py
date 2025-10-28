from rest_framework import serializers
from .models import Device, DeviceType, Location, UserProfile, ComputerSpecs, PrinterScannerSpecs, NetworkDeviceSpecs, Cartridge, CartridgeLog, Log
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

class DeviceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceType
        fields = '__all__' # Или список конкретных полей

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'

class UserProfileSerializer(serializers.ModelSerializer):
    # Поле для отображения избранных устройств (только для чтения)
    favorite_devices_list = serializers.StringRelatedField(source='favorite_devices', many=True, read_only=True)
    # Поле для установки избранных устройств (требует кастомной логики в to_internal_value или create/update)
    favorite_devices = serializers.PrimaryKeyRelatedField(queryset=Device.objects.all(), many=True, required=False)

    class Meta:
        model = UserProfile
        fields = ['id', 'user', 'favorite_devices', 'favorite_devices_list'] # user - внешний ключ на User
        # exclude = ['user'] # Если user автоматически определяется (например, текущий пользователь), можно исключить из входных данных
        # Но в данном случае оставим, чтобы можно было создать/обновить связь через API (например, админом)

    def update(self, instance, validated_data):
        # Получаем список устройств из validated_data
        favorite_devices_data = validated_data.pop('favorite_devices', None)
        # Вызываем стандартный метод update для остальных полей
        instance = super().update(instance, validated_data)

        # Обновляем ManyToMany связь
        if favorite_devices_data is not None:
            instance.favorite_devices.set(favorite_devices_data)

        return instance
    
# --- Serializers для специфичных данных ---
# ComputerSpecs
class ComputerSpecsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComputerSpecs
        exclude = ['device']
    def to_internal_value(self, data):
        # Убираем 'device' из данных перед стандартной валидацией
        # Это позволяет пройти валидацию, даже если 'device' не передан
        data = data.copy() # Создаем копию, чтобы не изменять оригинальный объект
        data.pop('device', None) # Удаляем 'device', если он есть
        return super().to_internal_value(data)

# PrinterScannerSpecs
class PrinterScannerSpecsSerializer(serializers.ModelSerializer):
    # current_cartridge может быть null, поэтому указываем required=False
    current_cartridge = serializers.PrimaryKeyRelatedField(queryset=Cartridge.objects.all(), required=False, allow_null=True)
    class Meta:
        model = PrinterScannerSpecs
        exclude = ['device']

    def to_internal_value(self, data):
        data = data.copy()
        data.pop('device', None)
        return super().to_internal_value(data)

# NetworkDeviceSpecs
class NetworkDeviceSpecsSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkDeviceSpecs
        exclude = ['device']

    def to_internal_value(self, data):
        data = data.copy()
        data.pop('device', None)
        return super().to_internal_value(data)

# Cartridge
class CartridgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cartridge
        fields = '__all__'
        read_only_fields = ('remaining_pages',) # remaining_pages вычисляется автоматически, не принимаем при создании/обновлении

# CartridgeLog
class CartridgeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartridgeLog
        fields = '__all__'

# Log
class LogSerializer(serializers.ModelSerializer):
    # created_by будет определяться автоматически при создании (см. ViewSet)
    created_by = serializers.StringRelatedField(read_only=True) # Показываем имя пользователя
    # created_by = serializers.PrimaryKeyRelatedField(read_only=True) # Или ID пользователя
    class Meta:
        model = Log
        fields = '__all__'
        # exclude = ['created_by'] # Если будем устанавливать created_by в ViewSet
        # Включаем все, но в ViewSet установим created_by вручную

# --- Основной Device Serializer ---
# Device - основная модель, к которой привязаны специфичные данные.
# Мы хотим включить специфичные данные в JSON ответа для Device.
# Используем `source` для указания связанного поля и `many=True` если связь OneToMany или ManyToMany.
# Для OneToOne связей `many=False` (по умолчанию).
class DeviceSerializer(serializers.ModelSerializer):
    # Включаем связанные данные (только для чтения)
    computer_specs = ComputerSpecsSerializer(required=False, read_only=True)
    printer_scanner_specs = PrinterScannerSpecsSerializer(required=False, read_only=True)
    network_specs = NetworkDeviceSpecsSerializer(required=False, read_only=True)
    # Включаем связанные данные для device_type и location
    device_type = DeviceTypeSerializer(read_only=True)
    location = LocationSerializer(read_only=True)
    # Включаем количество логов
    logs_count = serializers.SerializerMethodField()

    # --- Изменение: Используем PrimaryKeyRelatedField для owner и assigned_to ---
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    # --- /Изменение --

    class Meta:
        model = Device
        fields = '__all__'
        # exclude = ['qr_code_id'] # Если не хотим отдавать qr_code_id клиенту, можно исключить
        # read_only_fields = ('qr_code_id', 'created_at', 'updated_at') # Указываем поля, которые не могут быть изменены через API

    def get_logs_count(self, obj):
        # obj - это экземпляр модели Device
        # Возвращаем количество связанных логов
        return obj.logs.count()

# --- Сериализаторы для создания/обновления Device ---
# При создании/обновлении Device, возможно, нужно одновременно создать/обновить связанные специфичные данные.
# Для этого переопределяем методы `create` и `update`.

class DeviceCreateUpdateSerializer(serializers.ModelSerializer):
    # Специфичные данные передаются как вложенные объекты
    computer_specs = ComputerSpecsSerializer(required=False)
    printer_scanner_specs = PrinterScannerSpecsSerializer(required=False)
    network_specs = NetworkDeviceSpecsSerializer(required=False)

    class Meta:
        model = Device
        fields = '__all__'
        read_only_fields = ('qr_code_id', 'created_at', 'updated_at') # Эти поля не изменяются клиентом

    def is_spec_empty(self, spec_data):
        """
        Проверяет, является ли вложенный объект спецификации пустым.
        """
        if not spec_data:
            return True
        # Проверяем, есть ли хотя бы одно непустое значение
        for value in spec_data.values():
            if value not in [None, '', [], {}, False]:
                return False
        return True

    def to_internal_value(self, data):
        """
        Переопределяем to_internal_value, чтобы изолировать валидацию вложенных объектов.
        """
        data = data.copy()

        # Извлекаем вложенные данные и сохраняем их отдельно
        computer_specs_data = data.pop('computer_specs', None)
        printer_scanner_specs_data = data.pop('printer_scanner_specs', None)
        network_specs_data = data.pop('network_specs', None)

        # Валидируем ТОЛЬКО основной Device (без вложенных данных)
        validated_data = super().to_internal_value(data)

        # Валидируем вложенные объекты ОТДЕЛЬНО, убирая 'device' поле
        validated_nested_data = {}
        if computer_specs_data is not None and not self.is_spec_empty(computer_specs_data):
            nested_serializer = self.fields['computer_specs']
            validated_computer_data = nested_serializer.to_internal_value(computer_specs_data)
            validated_computer_data.pop('device', None) # Убедимся, что 'device' удален из валидированных данных
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

        # Объединяем валидированные данные
        validated_data.update(validated_nested_data)

        # Сохраняем валидированные вложенные данные как атрибут экземпляра
        self._validated_nested_data = validated_nested_data

        return validated_data


    def create(self, validated_data):
        # Извлекаем валидированные вложенные данные ИЗ атрибута экземпляра
        computer_specs_data = validated_data.pop('computer_specs', None) # Удаляем из validated_data перед созданием Device
        printer_scanner_specs_data = validated_data.pop('printer_scanner_specs', None)
        network_specs_data = validated_data.pop('network_specs', None)

        # Создаём основной объект Device с очищенными validated_data
        device = Device.objects.create(**validated_data)

        # Создаём связанные специфичные данные, добавив 'device' ID
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

        # --- обновляем сам Device
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # --- Компьютерные спецификации
        if computer_specs_data is not None:
            specs, _ = ComputerSpecs.objects.get_or_create(device=instance)
            for key, value in computer_specs_data.items():
                setattr(specs, key, value)
            specs.save()

        # --- Принтерные спецификации
        if printer_scanner_specs_data is not None:
            specs, _ = PrinterScannerSpecs.objects.get_or_create(device=instance)
            for key, value in printer_scanner_specs_data.items():
                setattr(specs, key, value)
            specs.save()

        # --- Сетевые спецификации
        if network_specs_data is not None:
            specs, _ = NetworkDeviceSpecs.objects.get_or_create(device=instance)
            for key, value in network_specs_data.items():
                setattr(specs, key, value)
            specs.save()

        return instance

# Опционально: создай сериализатор для Group, если хочешь возвращать ID и имя
class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

# --- User Serializer (для получения информации о пользователе) ---
# Часто нужно получать данные пользователя, например, для владельца устройства.
class UserSerializer(serializers.ModelSerializer):
    groups = GroupSerializer(many=True, read_only=True) # Возвращает полную информацию о группах

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'is_staff', 'groups'] # Выбираем нужные поля
        # exclude = ['password'] # Пароль исключаем всегда при сериализации