from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

TYPE_CHOICES = [
    ("ligne_credit",      "Ligne de crédit confirmée"),
    ("garantie",          "Garantie émise"),
    ("lettre_credit",     "Lettre de crédit (LC)"),
    ("engagement_fin",    "Engagement de financement"),
    ("swap",              "Swap de taux / change"),
    ("lfp",               "Ligne de financement potentielle (LFP)"),
    ("autre",             "Autre engagement"),
]


class OffBalanceSheetItem(models.Model):
    """Engagement hors-bilan — engagements, garanties, dérivés, LFPs.

    Utilisé pour calculer la position FX nette, le liquidity gap complet,
    l'EVE avec hors-bilan, et la concentration réelle (incluant les engagements).
    """
    date_arrete = models.DateField(db_index=True)
    type_engagement = models.CharField(max_length=32, choices=TYPE_CHOICES)
    reference = models.CharField(max_length=64, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")

    # Contrepartie
    client_id = models.CharField(max_length=32, blank=True, default="")
    client_name = models.CharField(max_length=255, blank=True, default="")
    segment = models.CharField(max_length=64, blank=True, default="")
    secteur = models.CharField(max_length=64, blank=True, default="")
    business_unit = models.CharField(max_length=64, blank=True, default="")
    entite = models.CharField(max_length=64, blank=True, default="")

    # Devise et montants
    devise = models.CharField(max_length=3, default="XAF")
    notionnel = models.BigIntegerField(default=0, help_text="Montant notionnel total de l'engagement.")
    montant_utilise = models.BigIntegerField(default=0, help_text="Montant déjà utilisé/tiré.")
    prob_tirage_pct = models.FloatField(default=100.0, help_text="Probabilité de tirage en % (utilisée pour pondérer dans le gap liquidité et LCR).")

    # Taux (pour les dérivés)
    taux = models.FloatField(default=0.0, help_text="Taux d'intérêt ou de swap (%).")
    type_taux = models.CharField(max_length=16, choices=[
        ("fixe", "Fixe"),
        ("variable", "Variable"),
        ("administre", "Administré"),
        ("indexe", "Indexé"),
        ("revisable", "Révisable"),
    ], default="fixe")

    # Maturité
    date_mise_place = models.DateField(null=True, blank=True)
    maturite = models.DateField(null=True, blank=True)
    bucket_liquidite = models.CharField(max_length=32, blank=True, default="")

    # Source
    source = models.CharField(max_length=32, default="flexcube")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Engagement hors-bilan"
        verbose_name_plural = "Engagements hors-bilan"
        ordering = ["-date_arrete", "type_engagement"]
        indexes = [
            models.Index(fields=["date_arrete", "type_engagement"]),
            models.Index(fields=["date_arrete", "devise"]),
        ]

    def __str__(self):
        return f"{self.date_arrete} | {self.type_engagement} | {self.devise} | {self.notionnel:,}"
