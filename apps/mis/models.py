"""
MIS — Management Information System.

Table de mapping client : relie chaque client (identifié par son ID Flexcube)
à sa segmentation analytique (BU, sous-segment, secteur, type client).

Ce mapping permet d'enrichir automatiquement les BalanceSheetLine et
OffBalanceSheetItem avec leur segmentation MIS pour les analyses croisées.
"""
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

SEGMENT_CHOICES = [
    ("retail",     "Retail / Particulier"),
    ("sme",        "PME"),
    ("corporate",  "Corporate"),
    ("public",     "Secteur public / Institutionnel"),
    ("financial",  "Institutions financières"),
    ("other",      "Autre"),
]

SOUS_SEGMENT_CHOICES = [
    # Retail
    ("salarie",        "Salarié"),
    ("professionnel",  "Professionnel / Indépendant"),
    ("etudiant",       "Étudiant"),
    # SME / Corporate
    ("tpe",            "TPE (< 5 salariés)"),
    ("pme",            "PME (5-250 salariés)"),
    ("eti",            "ETI (250-5000 salariés)"),
    ("grande_entreprise", "Grande Entreprise (> 5000 salariés)"),
    # Public
    ("etat",           "État / Administrations centrales"),
    ("collectivite",   "Collectivités territoriales"),
    ("etablissement_public", "Établissements publics"),
    ("ong",            "ONG / Associations"),
    # Institutions financières
    ("banque",         "Banque"),
    ("assurance",      "Assurance"),
    ("microfinance",   "Microfinance"),
    ("fonds",          "Fonds / Asset Manager"),
    ("other",          "Autre"),
]


class ClientMapping(models.Model):
    """
    Mapping client → segmentation MIS.

    Relie client_id (Flexcube CUSTOMER_NO) à la segmentation analytique
    utilisée dans les analyses MIS : BU, segment, sous-segment, secteur.

    Import depuis Excel ou saisie manuelle. Lié automatiquement aux
    BalanceSheetLine via client_id lors des analyses.
    """
    # Identification client
    client_id = models.CharField(
        max_length=32, unique=True, db_index=True,
        help_text="Identifiant client Flexcube (CUSTOMER_NO)."
    )
    client_name = models.CharField(max_length=255, blank=True, default="")

    # Segmentation analytique
    business_unit = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Direction / BU responsable du client (ex: Retail Banking, Corporate, Trésorerie)."
    )
    segment = models.CharField(
        max_length=32, choices=SEGMENT_CHOICES, default="other",
        help_text="Segment client principal."
    )
    sous_segment = models.CharField(
        max_length=32, choices=SOUS_SEGMENT_CHOICES, blank=True, default="",
        help_text="Sous-segment (granularité fine)."
    )
    secteur = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Secteur économique (classification NACE, BEAC ou locale)."
    )
    secteur_code = models.CharField(
        max_length=16, blank=True, default="",
        help_text="Code numérique du secteur (ex: NACE A01, B05...)."
    )

    # Agence et entité
    agence = models.CharField(max_length=16, blank=True, default="")
    entite = models.CharField(max_length=64, blank=True, default="")

    # Métadonnées
    is_active = models.BooleanField(default=True)
    source = models.CharField(
        max_length=32, default="manual",
        help_text="Source : manual, flexcube, import_excel."
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Mapping client MIS"
        verbose_name_plural = "Mappings clients MIS"
        ordering = ["business_unit", "segment", "client_id"]

    def __str__(self):
        return f"{self.client_id} — {self.client_name} ({self.segment}/{self.business_unit})"
