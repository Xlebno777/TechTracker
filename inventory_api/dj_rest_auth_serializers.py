# inventory_api/dj_rest_auth_serializers.py

from dj_rest_auth.serializers import UserDetailsSerializer as DefaultUserDetailsSerializer
from django.contrib.auth.models import Group
from rest_framework import serializers

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

class UserDetailsSerializer(DefaultUserDetailsSerializer):
    groups = GroupSerializer(many=True, read_only=True)

    class Meta(DefaultUserDetailsSerializer.Meta):
        fields = DefaultUserDetailsSerializer.Meta.fields + ('groups',)