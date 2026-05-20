"""Enregistre tous les modèles d'inputs dans l'admin Django."""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import INPUT_MODELS, Output


for kind, model in INPUT_MODELS.items():
    AdminClass = type(
        f"{model.__name__}Admin",
        (SimpleHistoryAdmin,),
        {
            "list_display": [f.name for f in model._meta.fields if f.name != "id"][:8],
            "search_fields": [
                f.name for f in model._meta.fields
                if f.get_internal_type() == "CharField"
            ],
        },
    )
    admin.site.register(model, AdminClass)


@admin.register(Output)
class OutputAdmin(admin.ModelAdmin):
    list_display = ("type_output", "date", "montant")
    list_filter = ("type_output",)
    search_fields = ("type_output",)
    date_hierarchy = "date"
