"""
Tables de mapping et de transformation entre systèmes sources et nomenclature ALM.

Couvre les exigences exprimées par la Direction de la Trésorerie :
- Mapping des produits (Calypso/Flexcube/GL → ALM).
- Mapping des devises et grilles de change.
- Affectation aux buckets de repricing.
- Tagging comportemental.
- Mapping des entités et des agences.
- Classification des segments clients.
- Classification des collatéraux et sûretés.
- Engagements hors-bilan.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


# ----------------------------------------------------------------------------
# Devises et grilles de change
# ----------------------------------------------------------------------------
class Currency(models.Model):
    """Devise supportée par la plateforme."""

    code = models.CharField(max_length=3, unique=True, help_text="Code ISO 4217 (ex: XAF, EUR, USD).")
    label = models.CharField(max_length=64)
    is_base = models.BooleanField(default=False, help_text="Devise pivot du bilan (ex: XAF).")
    decimals = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["code"]
        verbose_name = "Devise"
        verbose_name_plural = "Devises"

    def __str__(self) -> str:
        return self.code


class FxRate(models.Model):
    """Taux de change spot ou cours fixing (date, devise -> devise pivot)."""

    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name="rates")
    date = models.DateField()
    rate = models.FloatField(help_text="Taux 1 unité de currency = rate × devise pivot.")
    source = models.CharField(max_length=64, blank=True, default="manual")

    class Meta:
        unique_together = [("currency", "date")]
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.currency.code} @ {self.date} = {self.rate}"


# ----------------------------------------------------------------------------
# Entités et agences (groupe bancaire)
# ----------------------------------------------------------------------------
class Entity(models.Model):
    """Entité d'un groupe bancaire (banque, filiale, succursale)."""

    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="children")
    country = models.CharField(max_length=2, blank=True, default="")
    base_currency = models.ForeignKey(Currency, null=True, blank=True,
                                       on_delete=models.SET_NULL)
    consolidation = models.CharField(
        max_length=16,
        choices=[("full", "Intégration globale"),
                 ("proportional", "Intégration proportionnelle"),
                 ("equity", "Mise en équivalence"),
                 ("none", "Hors consolidation")],
        default="full",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["code"]
        verbose_name = "Entité"
        verbose_name_plural = "Entités"

    def __str__(self) -> str:
        return f"{self.code} — {self.label}"


class Branch(models.Model):
    code = models.CharField(max_length=16, unique=True)
    label = models.CharField(max_length=255)
    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="branches")
    region = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Agence"
        verbose_name_plural = "Agences"

    def __str__(self) -> str:
        return self.code


# ----------------------------------------------------------------------------
# Mapping de produits
# ----------------------------------------------------------------------------
class ProductMapping(models.Model):
    """Mapping (système source, code produit source) → (kind ALM, sous-catégorie)."""

    SOURCE_CHOICES = [
        ("calypso", "Calypso"),
        ("flexcube", "Flexcube"),
        ("ledger", "Grand livre"),
        ("manual", "Saisie manuelle"),
        ("other", "Autre"),
    ]

    source_system = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    source_code = models.CharField(max_length=64)
    source_label = models.CharField(max_length=255, blank=True, default="")
    target_kind = models.CharField(
        max_length=64,
        help_text="Type d'input ALM cible (ex: credit, depot_terme, ...)",
    )
    target_subcategory = models.CharField(max_length=64, blank=True, default="")
    repricing_bucket = models.CharField(max_length=16, blank=True, default="")
    behavioral_tag = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        unique_together = [("source_system", "source_code")]
        ordering = ["source_system", "source_code"]
        verbose_name = "Mapping produit"
        verbose_name_plural = "Mappings produits"

    def __str__(self) -> str:
        return f"{self.source_system}:{self.source_code} → {self.target_kind}"


# ----------------------------------------------------------------------------
# Bucket de repricing pour le gap de taux
# ----------------------------------------------------------------------------
class RepricingBucket(models.Model):
    """Bucket de repricing utilisé par les calculs NII/EVE."""

    code = models.CharField(max_length=16, unique=True)
    label = models.CharField(max_length=64)
    days_min = models.IntegerField(help_text="Borne basse (jours)")
    days_max = models.IntegerField(null=True, blank=True,
                                    help_text="Borne haute (jours, null = ∞)")
    midpoint_days = models.IntegerField(help_text="Point milieu utilisé pour la duration")
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "Bucket de repricing"

    def __str__(self) -> str:
        return self.code


# ----------------------------------------------------------------------------
# Segments clients
# ----------------------------------------------------------------------------
class CustomerSegment(models.Model):
    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=255)
    is_retail = models.BooleanField(default=False)
    is_corporate = models.BooleanField(default=False)
    is_financial = models.BooleanField(default=False)
    risk_weight = models.FloatField(default=1.0,
                                     help_text="Pondération risque (0–1) appliquée pour LCR.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Segment client"

    def __str__(self) -> str:
        return f"{self.code} — {self.label}"


# ----------------------------------------------------------------------------
# Collatéraux et sûretés
# ----------------------------------------------------------------------------
class CollateralType(models.Model):
    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=255)
    eligible_basel = models.BooleanField(default=False,
                                          help_text="Éligible au sens Bâle (HQLA, etc.)")
    haircut_pct = models.FloatField(default=0.0,
                                     help_text="Décote (haircut) en %.")
    liquidity_level = models.CharField(
        max_length=16,
        choices=[("level1", "Niveau 1"), ("level2a", "Niveau 2A"),
                 ("level2b", "Niveau 2B"), ("non_hqla", "Non-HQLA")],
        default="non_hqla",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["liquidity_level", "code"]
        verbose_name = "Type de collatéral"

    def __str__(self) -> str:
        return self.code


# ----------------------------------------------------------------------------
# Engagements hors-bilan
# ----------------------------------------------------------------------------
class OffBalanceCommitment(models.Model):
    TYPE_CHOICES = [
        ("credit_line", "Ligne de crédit confirmée"),
        ("undrawn_facility", "Facilité non tirée"),
        ("guarantee", "Garantie / caution"),
        ("loc", "Lettre de crédit"),
        ("derivative", "Engagement dérivé"),
        ("other", "Autre"),
    ]

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    counterparty = models.CharField(max_length=255, blank=True, default="")
    notional = models.BigIntegerField()
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, null=True, blank=True)
    drawdown_pct = models.FloatField(
        default=0.0,
        help_text="Probabilité de tirage retenue pour le LCR / NSFR (%).",
    )
    maturity_date = models.DateField(null=True, blank=True)
    entity = models.ForeignKey(Entity, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["type", "code"]
        verbose_name = "Engagement hors-bilan"

    def __str__(self) -> str:
        return f"{self.type} {self.code}"
