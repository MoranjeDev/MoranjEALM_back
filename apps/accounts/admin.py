"""Configuration de l'admin Django pour les comptes."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from simple_history.admin import SimpleHistoryAdmin

from .models import GroupeUser, Habilitation, User


@admin.register(GroupeUser)
class GroupeUserAdmin(SimpleHistoryAdmin):
    list_display = ("nom", "is_validator", "is_extractor", "created_at")
    search_fields = ("nom",)


@admin.register(Habilitation)
class HabilitationAdmin(SimpleHistoryAdmin):
    list_display = ("groupe", "permissions_count", "updated_at")

    def permissions_count(self, obj):
        return len(obj.permissions or [])


@admin.register(User)
class UserAdmin(DjangoUserAdmin, SimpleHistoryAdmin):
    list_display = ("username", "email", "full_name", "groupe", "status", "is_active")
    list_filter = ("status", "is_active", "is_superuser", "groupe")
    search_fields = ("username", "first_name", "last_name", "email")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("ALM", {"fields": ("status", "firstconnect", "groupe", "password_change_date", "last_login_at")}),
    )
    readonly_fields = ("last_login_at", "password_change_date")
