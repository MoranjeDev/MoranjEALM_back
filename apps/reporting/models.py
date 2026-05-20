"""Modèles de reporting : templates et historique de génération."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportTemplate(models.Model):
    """Template de tableau de bord ALCO."""
    SCOPE_CHOICES = [
        ("alco", "ALCO mensuel"),
        ("dg", "Direction Générale"),
        ("regulatory", "Réglementaire"),
        ("custom", "Personnalisé"),
    ]
    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    scope = models.CharField(max_length=32, choices=SCOPE_CHOICES, default="alco")
    description = models.TextField(blank=True, default="")
    sections = models.JSONField(
        default=list, blank=True,
        help_text="Liste des sections du template (synthese, lcr, nii, eve, ftp, "
                  "concentration, multicurrency, charts, commentary).",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope", "code"]
        verbose_name = "Template de rapport"

    def __str__(self) -> str:
        return f"{self.code} ({self.scope})"


class ReportRun(models.Model):
    """Historique des générations de rapports — audit trail."""
    template = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL,
                                  null=True, related_name="runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                      null=True, related_name="report_runs")
    parameters = models.JSONField(default=dict, blank=True)
    file_format = models.CharField(max_length=8, default="pptx")
    file_path = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=16, default="success")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
