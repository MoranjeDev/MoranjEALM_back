from django.contrib import admin
from .models import ReportRun, ReportTemplate


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "scope", "is_active", "updated_at")
    list_filter = ("scope", "is_active")


@admin.register(ReportRun)
class ReportRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "template", "requested_by", "status")
    list_filter = ("status",)
    date_hierarchy = "created_at"
