from django.contrib import admin
from .models import ReportAnnotation, ReportRun, ReportTemplate


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "scope", "is_active", "updated_at")
    list_filter = ("scope", "is_active")


@admin.register(ReportRun)
class ReportRunAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "template",
        "requested_by",
        "file_format",
        "status",
        "certification_status",
        "certified_by",
    )
    list_filter = ("status", "certification_status", "file_format")
    date_hierarchy = "created_at"


@admin.register(ReportAnnotation)
class ReportAnnotationAdmin(admin.ModelAdmin):
    list_display = ("section", "scenario", "title", "created_by", "created_at")
    list_filter = ("section", "scenario", "created_at")
    search_fields = ("title", "body", "created_by__username")
    date_hierarchy = "created_at"
