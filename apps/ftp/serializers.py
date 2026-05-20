from rest_framework import serializers
from .models import FtpAllocation, FtpCurve, FtpPoint


class FtpPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = FtpPoint
        fields = "__all__"


class FtpCurveSerializer(serializers.ModelSerializer):
    points = FtpPointSerializer(many=True, read_only=True)

    class Meta:
        model = FtpCurve
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")


class FtpAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FtpAllocation
        fields = "__all__"
