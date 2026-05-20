"""
Gouvernance des hypothèses ALM.

Concepts :
- Assumption : nœud d'hypothèse identifié (ex: "stabilité NMD comptes courants").
  Possède un propriétaire métier et une description.
- AssumptionVersion : valeur historisée d'une hypothèse, avec workflow
  maker/checker/approver (django-fsm).

Ce modèle permet :
- de versionner toute hypothèse de la plateforme,
- de rejouer un calcul historique avec une version donnée,
- d'imposer un workflow d'approbation (maker -> checker -> approved -> active),
- de garder un audit trail complet.

Les autres modules (behavioral, FTP, scenarios, etc.) font référence à des
AssumptionVersion via leur clé primaire et identifiant logique.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django_fsm import FSMField, transition
from simple_history.models import HistoricalRecords


# ----------------------------------------------------------------------------
# Catégories d'hypothèses (typologie standard ALM)
# ----------------------------------------------------------------------------
ASSUMPTION_CATEGORIES = [
    ("nmd_stability", "Stabilité des NMD"),
    ("prepayment", "Remboursement anticipé"),
    ("withdrawal", "Retrait anticipé"),
    ("rollover", "Roll-over"),
    ("embedded_option", "Option embarquée"),
    ("ftp_curve", "Courbe FTP"),
    ("stress_scenario", "Scénario de stress"),
    ("rate_shock", "Choc de taux"),
    ("custom", "Personnalisée"),
]


class Assumption(models.Model):
    """Nœud d'hypothèse — agnostique de sa valeur, qui est portée par les
    AssumptionVersion."""

    code = models.CharField(max_length=64, unique=True,
                            help_text="Identifiant logique (ex: nmd_stable_compte_372).")
    label = models.CharField(max_length=255)
    category = models.CharField(max_length=32, choices=ASSUMPTION_CATEGORIES)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_assumptions",
        help_text="Propriétaire métier de l'hypothèse.",
    )
    methodology = models.TextField(
        blank=True, default="",
        help_text="Description de la méthodologie utilisée pour calibrer la valeur.",
    )
    sources = models.TextField(
        blank=True, default="",
        help_text="Sources de données utilisées (historique, études, etc.).",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "code"]
        verbose_name = "Hypothèse"
        verbose_name_plural = "Hypothèses"

    def __str__(self) -> str:
        return f"{self.code} ({self.label})"

    @property
    def active_version(self) -> "AssumptionVersion | None":
        return self.versions.filter(state=AssumptionVersion.STATE_ACTIVE).first()


# ----------------------------------------------------------------------------
# Workflow maker -> checker -> approved -> active
# ----------------------------------------------------------------------------
class AssumptionVersion(models.Model):
    """Version d'une hypothèse, avec valeur(s) numériques et workflow."""

    STATE_DRAFT = "draft"
    STATE_REVIEW = "review"
    STATE_APPROVED = "approved"
    STATE_ACTIVE = "active"
    STATE_RETIRED = "retired"
    STATE_REJECTED = "rejected"

    STATE_CHOICES = [
        (STATE_DRAFT, "Brouillon (maker)"),
        (STATE_REVIEW, "En revue (checker)"),
        (STATE_APPROVED, "Approuvé"),
        (STATE_ACTIVE, "Actif"),
        (STATE_RETIRED, "Retiré"),
        (STATE_REJECTED, "Rejeté"),
    ]

    assumption = models.ForeignKey(
        Assumption, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    # Valeur principale (la plupart des hypothèses sont scalaires)
    value = models.FloatField(null=True, blank=True)
    # Valeurs structurées (ex: courbes FTP, distributions par bucket)
    payload = models.JSONField(default=dict, blank=True)

    state = FSMField(default=STATE_DRAFT, choices=STATE_CHOICES, protected=True)

    # Champs workflow
    maker = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="made_assumption_versions",
    )
    checker = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="checked_assumption_versions",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_assumption_versions",
    )
    rationale = models.TextField(blank=True, default="",
                                  help_text="Justification du changement.")
    rejection_reason = models.TextField(blank=True, default="")

    effective_from = models.DateTimeField(null=True, blank=True)
    effective_to = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("assumption", "version_number")]
        verbose_name = "Version d'hypothèse"
        verbose_name_plural = "Versions d'hypothèses"
        indexes = [
            models.Index(fields=["assumption", "state"]),
        ]

    def __str__(self) -> str:
        return f"{self.assumption.code} v{self.version_number} [{self.state}]"

    # ------------------------------------------------------------------
    # Transitions FSM
    # ------------------------------------------------------------------
    @transition(field=state, source=STATE_DRAFT, target=STATE_REVIEW)
    def submit(self, user):
        self.submitted_at = timezone.now()
        self.maker = user

    @transition(field=state, source=STATE_REVIEW, target=STATE_APPROVED)
    def approve(self, user):
        self.approver = user
        self.approved_at = timezone.now()

    @transition(field=state, source=[STATE_REVIEW, STATE_DRAFT], target=STATE_REJECTED)
    def reject(self, user, reason: str = ""):
        self.checker = user
        self.rejection_reason = reason

    @transition(field=state, source=STATE_APPROVED, target=STATE_ACTIVE)
    def activate(self, user):
        self.activated_at = timezone.now()
        # Met automatiquement à la retraite la version active précédente
        AssumptionVersion.objects.filter(
            assumption=self.assumption, state=self.STATE_ACTIVE
        ).exclude(pk=self.pk).update(state=self.STATE_RETIRED, retired_at=timezone.now())

    @transition(field=state, source=STATE_ACTIVE, target=STATE_RETIRED)
    def retire(self, user):
        self.retired_at = timezone.now()


# ----------------------------------------------------------------------------
# Bibliothèque de scénarios (référencée par les modules de stress test, EVE, NII)
# ----------------------------------------------------------------------------
class ScenarioLibrary(models.Model):
    """Bibliothèque de scénarios (chocs liquidité, chocs de taux, etc.)."""

    SCOPE_CHOICES = [
        ("liquidity", "Liquidité"),
        ("interest_rate", "Taux d'intérêt"),
        ("combined", "Combiné"),
        ("custom", "Personnalisé"),
    ]

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    scope = models.CharField(max_length=32, choices=SCOPE_CHOICES)
    description = models.TextField(blank=True, default="")
    parameters = models.JSONField(default=dict, blank=True,
                                   help_text="Paramètres du scénario (chocs, déplacements de courbe, etc.)")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="created_scenarios",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_scenarios",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["scope", "code"]
        verbose_name = "Scénario"
        verbose_name_plural = "Bibliothèque de scénarios"

    def __str__(self) -> str:
        return f"{self.code} ({self.scope})"
