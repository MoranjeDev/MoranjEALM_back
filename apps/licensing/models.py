"""État local de la licence."""
from django.db import models
from django.utils import timezone


class LicenseState(models.Model):
    """Singleton — état courant de la licence côté client."""

    STATE_OK = "ok"
    STATE_GRACE = "grace"
    STATE_READONLY = "readonly"
    STATE_BLOCKED = "blocked"
    STATE_UNCONFIGURED = "unconfigured"

    state = models.CharField(max_length=16, default=STATE_UNCONFIGURED)
    license_key = models.CharField(max_length=128, blank=True, default="")
    fingerprint = models.CharField(max_length=128, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    enabled_modules = models.JSONField(default=list, blank=True)
    grace_period_days = models.IntegerField(default=30)

    last_token = models.TextField(blank=True, default="")
    last_token_iat = models.DateTimeField(null=True, blank=True)
    last_contact_ok_at = models.DateTimeField(null=True, blank=True)
    last_contact_error = models.TextField(blank=True, default="")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "État de licence"

    @classmethod
    def get_solo(cls) -> "LicenseState":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def days_since_last_contact(self) -> int | None:
        if not self.last_contact_ok_at:
            return None
        return (timezone.now() - self.last_contact_ok_at).days
