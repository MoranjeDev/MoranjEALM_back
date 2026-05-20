from django.contrib import admin
from .models import LicenseState


@admin.register(LicenseState)
class LicenseStateAdmin(admin.ModelAdmin):
    list_display = ("state", "expires_at", "last_contact_ok_at", "fingerprint")
    readonly_fields = ("fingerprint", "last_token", "last_token_iat",
                       "last_contact_ok_at", "last_contact_error", "updated_at")
