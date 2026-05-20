"""Tracking — journal d'audit des actions utilisateur."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Tracking(models.Model):
    """Équivalent de l'entité Tracking de Symfony."""

    libelle = models.CharField(max_length=255)
    description = models.TextField()
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracking_entries",
    )
    horodatage = models.DateTimeField(default=timezone.now, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        verbose_name = "Entrée d'audit"
        verbose_name_plural = "Audit"
        ordering = ["-horodatage"]
        indexes = [
            models.Index(fields=["-horodatage"]),
            models.Index(fields=["libelle"]),
        ]

    def __str__(self) -> str:
        return f"[{self.horodatage:%Y-%m-%d %H:%M}] {self.libelle}"
