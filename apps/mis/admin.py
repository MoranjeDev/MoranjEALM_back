from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import ClientMapping


@admin.register(ClientMapping)
class ClientMappingAdmin(SimpleHistoryAdmin):
    list_display = [
        "client_id", "client_name", "business_unit", "segment",
        "sous_segment", "secteur", "agence", "entite", "is_active", "source",
    ]
    list_filter = ["segment", "business_unit", "is_active", "source"]
    search_fields = ["client_id", "client_name", "secteur", "agence"]
    ordering = ["business_unit", "segment", "client_id"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        ("Identification", {
            "fields": ["client_id", "client_name"],
        }),
        ("Segmentation analytique", {
            "fields": ["business_unit", "segment", "sous_segment", "secteur", "secteur_code"],
        }),
        ("Localisation", {
            "fields": ["agence", "entite"],
        }),
        ("Métadonnées", {
            "fields": ["is_active", "source", "created_at", "updated_at"],
        }),
    ]
