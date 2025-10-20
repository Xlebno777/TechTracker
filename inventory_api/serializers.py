from rest_framework import serializers
from .models import Device, Log # Импортируй нужные модели

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = '__all__' # Или список конкретных полей

class LogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Log
        fields = '__all__'