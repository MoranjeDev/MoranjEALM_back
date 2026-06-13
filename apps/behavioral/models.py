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


# ----------------------------------------------------------------------------
# BehavioralDistributionParam — paramètres comportementaux par segment
# Remplace les scalaires globaux du Parameter singleton
# ----------------------------------------------------------------------------

BEHAVIORAL_PRODUCT_CHOICES = [
    # Comptes non-contractuels (NMD)
    ("compte_courant",    "Comptes courants 371"),
    ("compte_cheque",     "Comptes chèques 372"),
    ("compte_livret",     "Comptes livrets 373"),
    ("cpte_corr",         "Comptes correspondants"),
    ("beac",              "Compte BEAC"),
    # Crédits
    ("credit_conso",      "Crédit consommation"),
    ("credit_immobilier", "Crédit immobilier"),
    ("credit_corporate",  "Crédit corporate"),
    ("credit_autre",      "Autre crédit"),
    # Dépôts à terme
    ("depot_terme",       "Dépôt à terme"),
    ("bon_caisse",        "Bon de caisse"),
    # Autre
    ("autre",             "Autre produit"),
]

BEHAVIORAL_SEGMENT_CHOICES = [
    ("retail",      "Retail / Particulier"),
    ("sme",         "PME"),
    ("corporate",   "Corporate"),
    ("public",      "Secteur public / Institutionnel"),
    ("financial",   "Institutions financières"),
    ("all",         "Tous segments"),
]


class BehavioralDistributionParam(models.Model):
    """Paramètres comportementaux par produit × segment × BU.

    Remplace les coefficients scalaires globaux du Parameter singleton
    (stable_courant, stable_cheque...) par des paramètres granulaires
    permettant de distinguer ex. Retail 70% stable vs Corporate 35% stable.

    Lié au workflow de gouvernance : doit être approuvé (maker-checker)
    avant d'être activé dans le moteur de calcul.
    """
    code = models.CharField(max_length=64, unique=True, help_text="Identifiant unique (ex: compte_courant_retail_BU_RETAIL).")
    label = models.CharField(max_length=255)

    # Axes de segmentation
    product_type = models.CharField(max_length=32, choices=BEHAVIORAL_PRODUCT_CHOICES)
    segment = models.CharField(max_length=32, choices=BEHAVIORAL_SEGMENT_CHOICES, default="all")
    business_unit = models.CharField(max_length=64, blank=True, default="", help_text="BU spécifique (vide = tous les BU).")
    secteur = models.CharField(max_length=64, blank=True, default="", help_text="Secteur économique (vide = tous les secteurs).")
    devise = models.CharField(max_length=3, blank=True, default="", help_text="Devise (vide = toutes les devises).")

    # --- Paramètres NMD (dépôts non-contractuels) ---
    # Décomposition des soldes en 3 composantes (somme = 100%)
    stable_core_pct = models.FloatField(
        default=50.0,
        help_text="Part stable cœur (%) — écoulement long, repricing lent."
    )
    stable_non_core_pct = models.FloatField(
        default=20.0,
        help_text="Part stable non-cœur (%) — écoulement moyen."
    )
    volatile_pct = models.FloatField(
        default=30.0,
        help_text="Part volatile (%) — sort au bucket Call. stable_core + stable_non_core + volatile = 100."
    )

    # Durées d'écoulement comportemental
    runoff_core_months = models.IntegerField(
        default=60,
        help_text="Durée d'écoulement de la part stable cœur (mois)."
    )
    runoff_non_core_months = models.IntegerField(
        default=24,
        help_text="Durée d'écoulement de la part stable non-cœur (mois)."
    )

    # Repricing
    repricing_lag_months = models.IntegerField(
        default=1,
        help_text="Délai de repricing aux taux de marché (mois)."
    )
    pass_through_pct = models.FloatField(
        default=50.0,
        help_text="Pass-through des hausses de taux vers la clientèle (β, %). 0 = aucune transmission, 100 = transmission intégrale."
    )

    # --- Paramètres crédits ---
    cpr_annual_pct = models.FloatField(
        default=0.0,
        help_text="Taux annuel de remboursement anticipé (CPR, %). 0 si non applicable."
    )
    early_withdrawal_pct = models.FloatField(
        default=0.0,
        help_text="Taux annuel de retrait anticipé (pour dépôts à terme). 0 si non applicable."
    )
    rollover_rate_pct = models.FloatField(
        default=0.0,
        help_text="Taux de renouvellement à maturité (%). 0 si non applicable."
    )

    # --- Gouvernance ---
    assumption_version = models.ForeignKey(
        AssumptionVersion,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="behavioral_distribution_params",
        help_text="Version d'hypothèse (workflow maker-checker).",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Actif dans le moteur de calcul. Ne passer à True qu'après approbation."
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Paramètre par défaut utilisé si aucun paramètre plus spécifique n'est trouvé."
    )

    # Audit
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Paramètre comportemental par segment"
        verbose_name_plural = "Paramètres comportementaux par segment"
        ordering = ["product_type", "segment", "business_unit"]
        # Unicité par combinaison d'axes
        unique_together = [["product_type", "segment", "business_unit", "secteur", "devise"]]

    def __str__(self) -> str:
        parts = [self.product_type, self.segment]
        if self.business_unit:
            parts.append(self.business_unit)
        return " / ".join(parts)

    def clean(self):
        from django.core.exceptions import ValidationError
        total = self.stable_core_pct + self.stable_non_core_pct + self.volatile_pct
        if abs(total - 100.0) > 0.01:
            raise ValidationError(
                f"stable_core_pct + stable_non_core_pct + volatile_pct doit être égal à 100% (actuellement {total:.1f}%)"
            )

    @classmethod
    def resolve(cls, product_type: str, segment: str = "", business_unit: str = "", secteur: str = "", devise: str = ""):
        """Résout le paramètre le plus spécifique actif pour une combinaison donnée.

        Ordre de priorité (du plus spécifique au plus général) :
        1. product_type + segment + business_unit + secteur + devise
        2. product_type + segment + business_unit + secteur
        3. product_type + segment + business_unit
        4. product_type + segment
        5. product_type + segment="all"
        6. None (paramètre par défaut introuvable)
        """
        qs = cls.objects.filter(product_type=product_type, is_active=True)
        for seg in [segment, "all"]:
            for bu in [business_unit, ""]:
                for sec in [secteur, ""]:
                    for dev in [devise, ""]:
                        result = qs.filter(segment=seg, business_unit=bu, secteur=sec, devise=dev).first()
                        if result:
                            return result
        return qs.filter(is_default=True).first()
