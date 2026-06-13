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
    code = models.CharField(max_length=64)
    label = models.CharField(max_length=255)
    scope = models.CharField(max_length=32, choices=SCOPE_CHOICES, default="alco")
    description = models.TextField(blank=True, default="")
    sections = models.JSONField(
        default=list, blank=True,
        help_text="Liste des sections du template (synthese, lcr, nii, eve, ftp, "
                  "concentration, multicurrency, charts, commentary).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_templates",
    )
    is_shared = models.BooleanField(
        default=False,
        help_text="Rend le template visible aux autres utilisateurs autorisés.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope", "code"]
        verbose_name = "Template de rapport"
        constraints = [
            models.UniqueConstraint(
                fields=["created_by", "code"],
                name="unique_report_template_code_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} ({self.scope})"


class ReportRun(models.Model):
    """Historique des générations de rapports — audit trail."""
    CERTIFICATION_DRAFT = "draft"
    CERTIFICATION_SUBMITTED = "submitted"
    CERTIFICATION_CERTIFIED = "certified"
    CERTIFICATION_REJECTED = "rejected"
    CERTIFICATION_CHOICES = [
        (CERTIFICATION_DRAFT, "Brouillon"),
        (CERTIFICATION_SUBMITTED, "Soumis"),
        (CERTIFICATION_CERTIFIED, "Validé"),
        (CERTIFICATION_REJECTED, "Rejeté"),
    ]

    template = models.ForeignKey(ReportTemplate, on_delete=models.SET_NULL,
                                  null=True, related_name="runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                      null=True, related_name="report_runs")
    parameters = models.JSONField(default=dict, blank=True)
    file_format = models.CharField(max_length=8, default="pptx")
    file_path = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(max_length=16, default="success")
    error = models.TextField(blank=True, default="")
    certification_status = models.CharField(
        max_length=16,
        choices=CERTIFICATION_CHOICES,
        default=CERTIFICATION_DRAFT,
    )
    certification_comment = models.TextField(blank=True, default="")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_report_runs",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    certified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certified_report_runs",
    )
    certified_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_report_runs",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    @property
    def can_submit(self) -> bool:
        return self.status == "success" and self.certification_status in {
            self.CERTIFICATION_DRAFT,
            self.CERTIFICATION_REJECTED,
        }

    @property
    def can_certify(self) -> bool:
        return self.status == "success" and self.certification_status == self.CERTIFICATION_SUBMITTED

    def submit(self, user, comment: str = ""):
        if not self.can_submit:
            raise ValueError("Ce rapport ne peut pas être soumis.")
        self.certification_status = self.CERTIFICATION_SUBMITTED
        self.certification_comment = comment or self.certification_comment
        self.submitted_by = user
        self.submitted_at = timezone.now()
        self.save(update_fields=[
            "certification_status",
            "certification_comment",
            "submitted_by",
            "submitted_at",
        ])

    def certify(self, user, comment: str = ""):
        if not self.can_certify:
            raise ValueError("Ce rapport ne peut pas être validé.")
        self.certification_status = self.CERTIFICATION_CERTIFIED
        self.certification_comment = comment or self.certification_comment
        self.certified_by = user
        self.certified_at = timezone.now()
        self.save(update_fields=[
            "certification_status",
            "certification_comment",
            "certified_by",
            "certified_at",
        ])

    def reject(self, user, comment: str):
        if not self.can_certify:
            raise ValueError("Seul un rapport soumis peut être rejeté.")
        self.certification_status = self.CERTIFICATION_REJECTED
        self.certification_comment = comment
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.save(update_fields=[
            "certification_status",
            "certification_comment",
            "rejected_by",
            "rejected_at",
        ])


class ReportAnnotation(models.Model):
    """Commentaire versionné rattaché à une section de rapport ALCO."""

    SECTION_CHOICES = [
        ("synthesis", "Synthèse liquidité"),
        ("lcr", "Liquidity Coverage Ratio"),
        ("rate_gap", "Gap de taux"),
        ("nii", "NII Sensitivity"),
        ("eve", "EVE Sensitivity"),
        ("eve_enriched", "EVE enrichi"),
        ("scenario_analysis", "Scenario Analysis"),
        ("concentration", "Concentration"),
        ("concentration_enriched", "Concentration enrichie"),
        ("multicurrency", "Multi-devises"),
        ("balance_sheet", "Bilan complet"),
        ("fx_position", "Position FX"),
        ("custom", "Personnalisé"),
    ]

    section = models.CharField(max_length=64, choices=SECTION_CHOICES, db_index=True)
    scenario = models.CharField(max_length=32, blank=True, default="", db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_annotations",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["section", "scenario", "-created_at"]),
        ]
        verbose_name = "Annotation de rapport"
        verbose_name_plural = "Annotations de rapport"

    @property
    def scope_key(self) -> str:
        return f"{self.section}:{self.scenario or 'global'}"

    def __str__(self) -> str:
        return f"{self.section} / {self.scenario or 'global'} - {self.created_at:%Y-%m-%d %H:%M}"
