from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

SENS_CHOICES = [("actif", "Actif"), ("passif", "Passif"), ("hors_bilan", "Hors-bilan")]

TYPE_TAUX_CHOICES = [
    ("fixe", "Taux fixe"),
    ("variable", "Taux variable (marché)"),
    ("administre", "Taux administré (BEAC/TIAO)"),
    ("indexe", "Taux indexé (EURIBOR/SOFR)"),
    ("revisable", "Taux révisable"),
]


class BalanceSheetLine(models.Model):
    """Ligne de bilan comptable GL — importée depuis Flexcube ou grand livre.

    Sert de référence officielle pour valider les inputs ALM et calculer
    le bilan LCY/FCY/consolidé, le bilan moyen, et la position FX.
    """
    # Identification
    date_arrete = models.DateField(db_index=True, help_text="Date d'arrêté comptable.")
    compte_gl = models.CharField(max_length=32, db_index=True, help_text="Numéro de compte GL (Flexcube AC_NO).")
    libelle = models.CharField(max_length=255, help_text="Libellé du compte GL.")

    # Produit et client
    product_code = models.CharField(max_length=64, blank=True, default="", help_text="Code produit Flexcube (PRODUCT_CODE).")
    client_id = models.CharField(max_length=32, blank=True, default="", help_text="Identifiant client Flexcube (CUSTOMER_NO).")
    client_name = models.CharField(max_length=255, blank=True, default="")

    # Segmentation MIS
    business_unit = models.CharField(max_length=64, blank=True, default="", help_text="Direction / BU (ex: Retail, Corporate, Trésorerie).")
    segment = models.CharField(max_length=64, blank=True, default="", help_text="Segment client (retail, sme, corporate, public, financial).")
    sous_segment = models.CharField(max_length=64, blank=True, default="")
    secteur = models.CharField(max_length=64, blank=True, default="", help_text="Secteur économique (NACE ou classification locale).")

    # Devise et montants
    devise = models.CharField(max_length=3, default="XAF", help_text="Code ISO 4217 (Flexcube CCY).")
    montant_lcy = models.BigIntegerField(default=0, help_text="Montant en devise locale (XAF).")
    montant_fcy = models.BigIntegerField(default=0, help_text="Montant en devise étrangère (si FCY).")

    # Sens et nature
    sens = models.CharField(max_length=12, choices=SENS_CHOICES, default="actif")

    # Taux
    type_taux = models.CharField(max_length=16, choices=TYPE_TAUX_CHOICES, default="fixe")
    taux_moyen = models.FloatField(default=0.0, help_text="Taux moyen pondéré appliqué à cette ligne (%).")

    # Maturité et buckets
    maturite = models.DateField(null=True, blank=True, help_text="Date de maturité contractuelle.")
    bucket_liquidite = models.CharField(max_length=32, blank=True, default="", help_text="Code bucket de liquidité (calculé automatiquement).")
    bucket_repricing = models.CharField(max_length=32, blank=True, default="", help_text="Code bucket de repricing.")

    # Entité/Agence
    entite = models.CharField(max_length=64, blank=True, default="", help_text="Entité du groupe bancaire.")
    agence = models.CharField(max_length=16, blank=True, default="", help_text="Code agence Flexcube (BRANCH_CODE).")

    # Source
    source = models.CharField(max_length=32, default="flexcube", help_text="Système source (flexcube, manuel, autre).")

    # Audit
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Ligne de bilan GL"
        verbose_name_plural = "Lignes de bilan GL"
        ordering = ["-date_arrete", "sens", "compte_gl"]
        indexes = [
            models.Index(fields=["date_arrete", "sens"]),
            models.Index(fields=["date_arrete", "devise"]),
            models.Index(fields=["date_arrete", "business_unit"]),
            models.Index(fields=["compte_gl"]),
        ]

    def __str__(self):
        return f"{self.date_arrete} | {self.compte_gl} | {self.devise} | {self.montant_lcy:,}"
