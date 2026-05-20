from rest_framework import serializers
from .models import ReportRun, ReportTemplate


class ReportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportTemplate
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")


class ReportRunSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source="requested_by.username", read_only=True)
    template_label = serializers.CharField(source="template.label", read_only=True)

    class Meta:
        model = ReportRun
        fields = "__all__"
        read_only_fields = (
            "requested_by", "file_path", "status", "error", "created_at",
        )
