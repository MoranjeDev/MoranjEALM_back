from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Assumption, AssumptionVersion, ScenarioLibrary


@admin.register(Assumption)
class AssumptionAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "category", "owner", "updated_at")
    list_filter = ("category",)
    search_fields = ("code", "label", "description")


@admin.register(AssumptionVersion)
class AssumptionVersionAdmin(SimpleHistoryAdmin):
    list_display = ("assumption", "version_number", "state", "value", "maker", "approver", "activated_at")
    list_filter = ("state", "assumption__category")
    search_fields = ("assumption__code",)


@admin.register(ScenarioLibrary)
class ScenarioLibraryAdmin(SimpleHistoryAdmin):
    list_display = ("code", "label", "scope", "is_active", "created_by", "created_at")
    list_filter = ("scope", "is_active")
    search_fields = ("code", "label")
