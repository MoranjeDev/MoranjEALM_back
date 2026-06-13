from rest_framework import serializers
from .models import ReportAnnotation, ReportRun, ReportTemplate


class ReportTemplateSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    is_editable = serializers.SerializerMethodField()

    def validate_code(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return value
        queryset = ReportTemplate.objects.filter(created_by=user, code=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "Vous avez déjà un template avec ce code."
            )
        return value

    def get_is_editable(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        return obj.created_by_id == user.id

    class Meta:
        model = ReportTemplate
        fields = "__all__"
        read_only_fields = (
            "created_at",
            "updated_at",
            "created_by",
            "created_by_username",
            "is_editable",
        )


class ReportRunSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source="requested_by.username", read_only=True)
    template_label = serializers.CharField(source="template.label", read_only=True)
    submitted_by_name = serializers.CharField(source="submitted_by.username", read_only=True)
    certified_by_name = serializers.CharField(source="certified_by.username", read_only=True)
    rejected_by_name = serializers.CharField(source="rejected_by.username", read_only=True)
    can_submit = serializers.SerializerMethodField()
    can_certify = serializers.SerializerMethodField()

    def get_can_submit(self, obj):
        return obj.can_submit

    def get_can_certify(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not obj.can_certify:
            return False
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        return obj.requested_by_id != user.id

    class Meta:
        model = ReportRun
        fields = "__all__"
        read_only_fields = (
            "requested_by",
            "file_path",
            "status",
            "error",
            "certification_status",
            "certification_comment",
            "submitted_by",
            "submitted_at",
            "certified_by",
            "certified_at",
            "rejected_by",
            "rejected_at",
            "created_at",
        )


class ReportAnnotationSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    scope_key = serializers.CharField(read_only=True)

    class Meta:
        model = ReportAnnotation
        fields = "__all__"
        read_only_fields = (
            "created_by",
            "created_by_name",
            "created_at",
            "scope_key",
        )
