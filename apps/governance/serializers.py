from rest_framework import serializers

from .impact import assumption_impact_preview
from .models import Assumption, AssumptionVersion, ScenarioLibrary


class AssumptionVersionSerializer(serializers.ModelSerializer):
    maker_name = serializers.CharField(source="maker.username", read_only=True)
    checker_name = serializers.CharField(source="checker.username", read_only=True)
    approver_name = serializers.CharField(source="approver.username", read_only=True)
    state_label = serializers.CharField(source="get_state_display", read_only=True)
    impact_preview = serializers.SerializerMethodField()

    def get_impact_preview(self, obj):
        return assumption_impact_preview(obj)

    class Meta:
        model = AssumptionVersion
        fields = [
            "id", "assumption", "version_number", "value", "payload",
            "state", "state_label", "rationale", "rejection_reason",
            "maker", "maker_name", "checker", "checker_name",
            "approver", "approver_name",
            "impact_preview",
            "effective_from", "effective_to",
            "created_at", "submitted_at", "approved_at", "activated_at", "retired_at",
        ]
        read_only_fields = (
            "version_number", "state", "maker", "checker", "approver",
            "submitted_at", "approved_at", "activated_at", "retired_at",
            "rejection_reason", "created_at",
        )


class AssumptionSerializer(serializers.ModelSerializer):
    versions = AssumptionVersionSerializer(many=True, read_only=True)
    active_version = AssumptionVersionSerializer(read_only=True)
    owner_name = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Assumption
        fields = [
            "id", "code", "label", "category", "description",
            "owner", "owner_name", "methodology", "sources",
            "impacted_modules", "calculation_notes", "requires_approval",
            "active_version", "versions",
            "created_at", "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")


class ScenarioLibrarySerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.username", read_only=True)

    class Meta:
        model = ScenarioLibrary
        fields = [
            "id", "code", "label", "scope", "description", "parameters",
            "is_active",
            "created_by", "created_by_name",
            "approved_by", "approved_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ("created_by", "created_at", "updated_at")
