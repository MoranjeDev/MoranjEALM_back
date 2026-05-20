"""
Modèles comportementaux ALM.

Couvre les besoins exprimés par la Direction de la Trésorerie :
- NMD (Non-Maturity Deposits) : stabilité, écoulement, repricing.
- Prepayment : taux de remboursement anticipé des crédits.
- Early withdrawal : taux de retrait anticipé des dépôts à terme.
- Roll-over : taux de renouvellement.
- Embedded options : caps, floors, options de remboursement.

Chaque modèle se rattache à une `Assumption` versionnée (gouvernance).
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.governance.models import AssumptionVersion


# ----------------------------------------------------------------------------
# NMD — Non-Maturity Deposits
# ----------------------------------------------------------------------------
class NmdModel(models.Model):
    """Modèle NMD pour une catégorie de comptes (ex: 372 chèques)."""

    PRODUCT_CHOICES = [
        ("compte_371", "Comptes courants 371"),
        ("compte_372", "Comptes chèques 372"),
        ("compte_373", "Comptes livrets 373"),
        ("compte_vue_cor", "Comptes vue correspondants"),
        ("custom", "Personnalisé"),
    ]

    SEGMENT_CHOICES = [
        ("retail", "Retail / Particulier"),
        ("sme", "PME"),
        ("corporate", "Corporate"),
        ("public", "Secteur public"),
        ("financial", "Institutions financières"),
        ("all", "Tous segments"),
    ]

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    product = models.CharField(max_length=32, choices=PRODUCT_CHOICES)
    segment = models.CharField(max_length=32, choices=SEGMENT_CHOICES, default="all")

    # Trois composantes : core stable, semi-stable, volatile (somme = 100 %)
    core_stable_pct = models.FloatField(help_text="Part stable cœur (%)")
    non_core_stable_pct = models.FloatField(help_text="Part stable non-cœur (%)")
    volatile_pct = models.FloatField(help_text="Part volatile (%)")

    # Écoulement (months) — durée comportementale appliquée à la part stable
    runoff_core_months = models.IntegerField(default=60,
                                             help_text="Durée écoulement cœur (mois)")
    runoff_non_core_months = models.IntegerField(default=24)
    repricing_lag_months = models.IntegerField(default=1,
                                                help_text="Lag de repricing aux taux de marché (mois)")
    pass_through_pct = models.FloatField(default=50.0,
                                          help_text="% de pass-through des taux de marché aux taux clients (β beta)")

    assumption_version = models.ForeignKey(
        AssumptionVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="nmd_models",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Modèle NMD"
        verbose_name_plural = "Modèles NMD"
        ordering = ["product", "segment"]

    def __str__(self) -> str:
        return f"NMD {self.product}/{self.segment}"

    def total_stable_pct(self) -> float:
        return self.core_stable_pct + self.non_core_stable_pct


# ----------------------------------------------------------------------------
# Prepayment — taux de remboursement anticipé
# ----------------------------------------------------------------------------
class PrepaymentModel(models.Model):
    """Taux annuel de remboursement anticipé (CPR — Conditional Prepayment Rate)
    appliqué à un type de crédit."""

    PRODUCT_CHOICES = [
        ("credit_consumer", "Crédit conso"),
        ("credit_mortgage", "Crédit immobilier"),
        ("credit_pro", "Crédit professionnel"),
        ("credit_corporate", "Crédit corporate"),
        ("credit_other", "Autre crédit"),
    ]

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    product = models.CharField(max_length=32, choices=PRODUCT_CHOICES)
    cpr_annual = models.FloatField(help_text="CPR annuel (%)")
    rate_sensitivity = models.FloatField(
        default=0.0,
        help_text="Sensibilité aux taux : variation du CPR par 100 bp de baisse de taux.",
    )
    assumption_version = models.ForeignKey(
        AssumptionVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="prepayment_models",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Modèle de remboursement anticipé"
        ordering = ["product", "code"]

    def __str__(self) -> str:
        return f"Prepayment {self.product} ({self.cpr_annual}%)"


# ----------------------------------------------------------------------------
# Early withdrawal — retrait anticipé sur dépôts à terme
# ----------------------------------------------------------------------------
class EarlyWithdrawalModel(models.Model):
    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    product = models.CharField(max_length=32,
                                choices=[("depot_terme", "Dépôt à terme"),
                                         ("bon", "Bon de caisse")])
    annual_rate_pct = models.FloatField(help_text="Taux annuel de retrait anticipé (%)")
    rate_sensitivity = models.FloatField(default=0.0)
    assumption_version = models.ForeignKey(
        AssumptionVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="withdrawal_models",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Modèle de retrait anticipé"
        ordering = ["product", "code"]

    def __str__(self) -> str:
        return f"Withdrawal {self.product} ({self.annual_rate_pct}%)"


# ----------------------------------------------------------------------------
# Roll-over
# ----------------------------------------------------------------------------
class RolloverModel(models.Model):
    """Hypothèse de renouvellement à maturité."""
    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    product = models.CharField(max_length=64)
    rollover_rate_pct = models.FloatField(help_text="% de renouvellement à maturité")
    new_term_months = models.IntegerField(help_text="Durée du nouveau contrat (mois)")
    assumption_version = models.ForeignKey(
        AssumptionVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="rollover_models",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Modèle de roll-over"
        ordering = ["product"]

    def __str__(self) -> str:
        return f"Rollover {self.product}"


# ----------------------------------------------------------------------------
# Embedded options
# ----------------------------------------------------------------------------
class EmbeddedOption(models.Model):
    OPTION_TYPES = [
        ("cap", "Cap (taux plafond)"),
        ("floor", "Floor (taux plancher)"),
        ("call", "Call (option de remboursement émetteur)"),
        ("put", "Put (option de remboursement détenteur)"),
        ("conversion", "Option de conversion"),
        ("other", "Autre"),
    ]

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    option_type = models.CharField(max_length=16, choices=OPTION_TYPES)
    strike = models.FloatField(null=True, blank=True)
    notional = models.BigIntegerField(null=True, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    assumption_version = models.ForeignKey(
        AssumptionVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="embedded_options",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Option embarquée"
        verbose_name_plural = "Options embarquées"

    def __str__(self) -> str:
        return f"{self.option_type} {self.code}"
