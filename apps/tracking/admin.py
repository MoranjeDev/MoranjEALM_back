from django.contrib import admin
from .models import Tracking


@admin.register(Tracking)
class TrackingAdmin(admin.ModelAdmin):
    list_display = ("horodatage", "libelle", "utilisateur", "ip_address")
    list_filter = ("libelle", "horodatage")
    search_fields = ("libelle", "description", "utilisateur__username")
    readonly_fields = tuple(f.name for f in Tracking._meta.fields)
    date_hierarchy = "horodatage"
