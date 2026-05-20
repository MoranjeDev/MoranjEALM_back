"""Serializers DRF pour les comptes utilisateurs."""
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import HABILITATION_CHOICES, GroupeUser, Habilitation, User


class HabilitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habilitation
        fields = ["id", "groupe", "permissions", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class GroupeUserSerializer(serializers.ModelSerializer):
    habilitations = serializers.SerializerMethodField()

    class Meta:
        model = GroupeUser
        fields = [
            "id",
            "nom",
            "description",
            "is_validator",
            "is_extractor",
            "habilitations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_habilitations(self, obj: GroupeUser) -> list[str]:
        return obj.habilitations_list


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    habilitations = serializers.ListField(read_only=True)
    groupe_nom = serializers.CharField(source="groupe.nom", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "status",
            "firstconnect",
            "groupe",
            "groupe_nom",
            "habilitations",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "last_login_at",
            "password_change_date",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "last_login",
            "last_login_at",
            "password_change_date",
            "date_joined",
            "is_superuser",
        ]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "status",
            "groupe",
            "password",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.firstconnect = True
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])


class HabilitationChoicesSerializer(serializers.Serializer):
    """Liste plate des habilitations disponibles."""
    value = serializers.CharField()
    label = serializers.CharField()

    @classmethod
    def list(cls):
        return [{"value": v, "label": label} for v, label in HABILITATION_CHOICES]
