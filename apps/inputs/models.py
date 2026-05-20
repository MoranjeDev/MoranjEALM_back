"""
Modèles Inputs ALM — reprise fidèle des 23 entités Symfony.

Chaque modèle hérite de TimestampedModel pour la traçabilité (created_at,
updated_at, historisation django-simple-history).

Catégories :
- Inputs « Core » : alimentés depuis le core banking (mise à jour suivie via
  Parameter.dateMajCore — voir indicateur de fraîcheur sur le dashboard).
- Inputs « Extra » : alimentés depuis d'autres systèmes (suivi via
  Parameter.dateMajExtra).
"""

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


# ----------------------------------------------------------------------------
# Catégorie de fraîcheur (utile pour le dashboard, équivalent des badges
# vert/orange/rouge de la version Symfony).
# ----------------------------------------------------------------------------
CATEGORY_CORE = "core"
CATEGORY_EXTRA = "extra"


class TimestampedModel(models.Model):
    """Ajoute created_at et updated_at à tous les modèles d'inputs."""
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


# ============================================================================
# ============================================================================
#                              ACTIFS
# ============================================================================
# ============================================================================

class InputCredit(TimestampedModel):
    """Crédits à la clientèle (entité InputCredit Symfony)."""
    code_agence = models.CharField(max_length=5)
    num_dossier = models.CharField(max_length=6)
    raci = models.CharField(max_length=6)
    avenant = models.BigIntegerField()
    date_mep = models.DateTimeField()
    date_prem_echeance = models.DateTimeField()
    date_deu_echeance = models.DateTimeField()
    nbre_echeance = models.IntegerField()
    taux_interet = models.FloatField()
    capital_restant = models.BigIntegerField()
    montant_debloque = models.BigIntegerField()
    frequence = models.CharField(max_length=255)

    history = HistoricalRecords()

    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Crédit"
        verbose_name_plural = "Crédits"
        ordering = ["-date_mep"]

    def __str__(self) -> str:
        return f"{self.num_dossier} ({self.code_agence})"


class InputTerme(TimestampedModel):
    """Prêts à terme (entité InputTerme)."""
    ref_cat = models.CharField(max_length=6)
    racine = models.CharField(max_length=6)
    compte_client = models.CharField(max_length=11)
    compte_cat = models.CharField(max_length=11)
    date_mep = models.DateTimeField()
    maturite = models.DateTimeField()
    montant = models.BigIntegerField()
    periodicite = models.CharField(max_length=255)
    taux_int = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Prêt à terme"
        verbose_name_plural = "Prêts à terme"


class InputDecouvert(TimestampedModel):
    """Découverts (entité InputDecouvert)."""
    agence = models.CharField(max_length=5)
    naut = models.CharField(max_length=6)
    code_client = models.CharField(max_length=11)
    montant = models.BigIntegerField()
    data_mise_place = models.DateTimeField()
    taux_auto = models.FloatField()
    plafond = models.BigIntegerField()
    taux_dela_plafond = models.FloatField()
    duree = models.IntegerField()
    date_fin = models.DateTimeField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Découvert"
        verbose_name_plural = "Découverts"


class InputBta(TimestampedModel):
    """BTA — Bons du Trésor Assimilables (entité InputBta)."""
    nom_client = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True, default="")
    date_valeur = models.DateTimeField()
    solde = models.BigIntegerField()
    maturite = models.DateTimeField()
    per_paiement = models.CharField(max_length=255)
    taux_int = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "BTA"
        verbose_name_plural = "BTA"


class InputOta(TimestampedModel):
    """OTA — Obligations du Trésor Assimilables (entité InputOta)."""
    code_emission = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True, default="")
    date_valeur = models.DateTimeField()
    solde = models.BigIntegerField()
    maturite = models.DateTimeField()
    taux_int = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "OTA"
        verbose_name_plural = "OTA"


class InputEmpruntObl(TimestampedModel):
    """Emprunts obligataires détenus (entité InputEmpruntObl)."""
    devise = models.CharField(max_length=255)
    nom_client = models.CharField(max_length=255)
    code_emission = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    date_valeur = models.DateTimeField()
    solde = models.BigIntegerField()
    maturite = models.DateTimeField()
    taux_int = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Emprunt obligataire"
        verbose_name_plural = "Emprunts obligataires"


class InputTabAmort(TimestampedModel):
    """Tableau d'amortissement des crédits (entité InputTabAmort)."""
    code_agence = models.CharField(max_length=5)
    num_dossier = models.CharField(max_length=6)
    avenant = models.BigIntegerField()
    devise = models.CharField(max_length=255)
    num_echeance = models.BigIntegerField()
    date_echeance = models.DateTimeField()
    amort_calcul = models.BigIntegerField()
    montant_echeance = models.BigIntegerField()
    statut_echeance = models.CharField(max_length=255)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Tableau amortissement crédit"
        verbose_name_plural = "Tableaux amortissement crédits"


class InputPretCor(TimestampedModel):
    """Prêts aux correspondants (entité InputPretCor)."""
    code_agence = models.CharField(max_length=5)
    num_dossier = models.CharField(max_length=6)
    racine = models.CharField(max_length=6)
    avenant = models.BigIntegerField()
    date_mep = models.DateTimeField()
    date_prem_echeance = models.DateTimeField()
    date_dern_echeance = models.DateTimeField()
    nbre_echeance = models.IntegerField()
    montant = models.BigIntegerField()
    taux_interet = models.FloatField()
    capital_restant = models.BigIntegerField()
    periodicite = models.CharField(max_length=255)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Prêt correspondant"
        verbose_name_plural = "Prêts correspondants"


class InputPretInterBanc(TimestampedModel):
    """Prêts interbancaires à blanc (entité InputPretInterBanc)."""
    racine = models.CharField(max_length=6)
    devise = models.CharField(max_length=255)
    contrepartie = models.CharField(max_length=255)
    solde = models.BigIntegerField()
    date_mep = models.DateTimeField()
    maturite = models.DateTimeField()
    per_paiement = models.CharField(max_length=255)
    taux_int = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Prêt interbancaire à blanc"
        verbose_name_plural = "Prêts interbancaires à blanc"


class InputBeac(TimestampedModel):
    """Compte courant à la BEAC (entité InputBeac)."""
    date = models.DateTimeField()
    cumul = models.BigIntegerField()
    tableauLog = models.FloatField(null=True, blank=True)
    tableauVarLog = models.FloatField(null=True, blank=True)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Compte BEAC"
        verbose_name_plural = "Comptes BEAC"
        ordering = ["-date"]


class InputPretTitre(TimestampedModel):
    """Prêts de titres (entité InputPretTitre)."""
    contrepartie = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    montant = models.BigIntegerField()
    date_mise = models.DateTimeField()
    date_echeance = models.DateTimeField()
    duree = models.IntegerField()
    taux_integer = models.FloatField()
    interet = models.BigIntegerField()
    tva = models.BigIntegerField()
    montant_rembourser = models.BigIntegerField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Prêt titre"
        verbose_name_plural = "Prêts titres"


class InputBillet(TimestampedModel):
    """Billets et pièces (entité InputBillet)."""
    date = models.DateTimeField()
    solde = models.BigIntegerField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Billets et pièces"
        verbose_name_plural = "Billets et pièces"
        ordering = ["-date"]


# ============================================================================
# ============================================================================
#                              PASSIFS
# ============================================================================
# ============================================================================

class InputCpteCorr(TimestampedModel):
    """Comptes de correspondants bancaires (entité InputCpteCorr)."""
    date = models.DateTimeField()
    cumul = models.BigIntegerField()
    tableauLog = models.FloatField(null=True, blank=True)
    tableauVarLog = models.FloatField(null=True, blank=True)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Compte correspondant"
        verbose_name_plural = "Comptes correspondants"
        ordering = ["-date"]


class InputDepotTerme(TimestampedModel):
    """Dépôts à terme (entité InputDepotTerme)."""
    reference = models.CharField(max_length=6)
    racine = models.CharField(max_length=6)
    compte_client = models.CharField(max_length=11)
    date_mep = models.DateTimeField()
    maturite = models.DateTimeField()
    montant = models.BigIntegerField()
    taux_interet = models.FloatField()
    periodicite = models.CharField(max_length=255)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Dépôt à terme"
        verbose_name_plural = "Dépôts à terme"


class InputBonCaisse(TimestampedModel):
    """Bons de caisse (entité InputBonCaisse)."""
    reference = models.CharField(max_length=6)
    racine = models.CharField(max_length=6)
    compte_client = models.CharField(max_length=11)
    date_mep = models.DateTimeField()
    maturite = models.DateTimeField()
    montant = models.BigIntegerField()
    taux = models.FloatField()
    periodicite = models.CharField(max_length=255)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Bon de caisse"
        verbose_name_plural = "Bons de caisse"


class InputPensionLivree(TimestampedModel):
    """Pensions livrées / repos (entité InputPensionLivree)."""
    type = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    montant = models.BigIntegerField()
    date_mise_place = models.DateTimeField()
    duree = models.IntegerField()
    echeance = models.DateTimeField()
    jour_echeance = models.IntegerField()
    taux_interet = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Pension livrée"
        verbose_name_plural = "Pensions livrées"


class InputEmpruntInter(TimestampedModel):
    """Emprunts interbancaires à blanc (entité InputEmpruntInter)."""
    type = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    montant = models.BigIntegerField()
    date_mise_place = models.DateTimeField()
    duree = models.IntegerField()
    echance = models.DateTimeField()  # NB: nom volontairement conservé (typo Symfony)
    jour_echeance = models.IntegerField()
    taux_interet = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Emprunt interbancaire à blanc"
        verbose_name_plural = "Emprunts interbancaires à blanc"


class InputEmpruntInterBanc(TimestampedModel):
    """Emprunts interbancaires (avec garanties) — entité InputEmpruntInterBanc."""
    date_dern_paiement = models.DateTimeField()
    date_pro_echeance = models.DateTimeField()
    encours = models.CharField(max_length=255)
    principal = models.BigIntegerField()
    interet = models.BigIntegerField()
    frequence_paiement = models.CharField(max_length=255)
    taux = models.FloatField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Emprunt interbancaire"
        verbose_name_plural = "Emprunts interbancaires"


class InputCompteCourant(TimestampedModel):
    """Comptes courants — comptabilité 371 (entité InputCompteCourant)."""
    date = models.DateTimeField()
    cumul = models.BigIntegerField()
    tableauLog = models.FloatField(null=True, blank=True)
    tableauVarLog = models.FloatField(null=True, blank=True)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Compte courant 371"
        verbose_name_plural = "Comptes courants 371"
        ordering = ["-date"]


class InputCompteCheque(TimestampedModel):
    """Comptes chèques — comptabilité 372 (entité InputCompteCheque)."""
    date = models.DateTimeField()
    # NB : Symfony utilisait int (32 bits, max ~2,1 Md). Élargi à BigIntegerField
    # pour supporter des cumuls en dizaines de milliards FCFA (cas réel banque).
    cumul = models.BigIntegerField()
    tableauLog = models.FloatField(null=True, blank=True)
    tableauVarLog = models.FloatField(null=True, blank=True)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Compte chèque 372"
        verbose_name_plural = "Comptes chèques 372"
        ordering = ["-date"]


class InputCompteLivret(TimestampedModel):
    """Comptes livrets — comptabilité 373 (entité InputCompteLivret)."""
    date = models.DateTimeField()
    # NB : Symfony typait BIGINT en DB mais string côté PHP (limite int 32 bits).
    # Côté Django on utilise directement BigIntegerField, plus naturel.
    cumul = models.BigIntegerField()
    tableauLog = models.FloatField(null=True, blank=True)
    tableauVarLog = models.FloatField(null=True, blank=True)

    history = HistoricalRecords()
    CATEGORY = CATEGORY_CORE

    class Meta:
        verbose_name = "Compte livret 373"
        verbose_name_plural = "Comptes livrets 373"
        ordering = ["-date"]


class InputAvanceBeac(TimestampedModel):
    """Avances reçues de la BEAC (entité InputAvanceBeac)."""
    montant = models.IntegerField()
    date_valeur = models.DateTimeField()
    echeance = models.DateTimeField()
    taux = models.FloatField()
    interets = models.BigIntegerField()
    montant_total_rembourse = models.BigIntegerField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Avance BEAC"
        verbose_name_plural = "Avances BEAC"


class InputEmpruntTitre(TimestampedModel):
    """Emprunts de titres (entité InputEmpruntTitre)."""
    contrepartie = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    montant = models.BigIntegerField()
    date_valeur = models.DateTimeField()
    echeance = models.DateTimeField()
    duree = models.IntegerField()
    taux = models.FloatField()
    interet = models.BigIntegerField()
    tva = models.BigIntegerField()
    montant_total_rembourse = models.BigIntegerField()

    history = HistoricalRecords()
    CATEGORY = CATEGORY_EXTRA

    class Meta:
        verbose_name = "Emprunt titre"
        verbose_name_plural = "Emprunts titres"


# ============================================================================
# OUTPUT (entité Output Symfony)
# ============================================================================

class Output(TimestampedModel):
    """Résultats agrégés produits par les moteurs de calcul (à venir phase 3)."""
    type_output = models.CharField(max_length=255, db_index=True)
    date = models.DateTimeField(default=timezone.now)
    montant = models.BigIntegerField()

    class Meta:
        verbose_name = "Output"
        verbose_name_plural = "Outputs"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["type_output", "-date"]),
        ]

    def __str__(self) -> str:
        return f"{self.type_output} = {self.montant}"


# ----------------------------------------------------------------------------
# Registre des modèles d'inputs : facilite l'introspection
# (utilisé pour générer dynamiquement les ViewSets et le menu).
# ----------------------------------------------------------------------------
INPUT_MODELS = {
    # Actifs
    "credit": InputCredit,
    "terme": InputTerme,
    "decouvert": InputDecouvert,
    "bta": InputBta,
    "ota": InputOta,
    "emprunt_obl": InputEmpruntObl,
    "tab_amort": InputTabAmort,
    "pret_cor": InputPretCor,
    "pret_inter_banc": InputPretInterBanc,
    "beac": InputBeac,
    "pret_titre": InputPretTitre,
    "billet": InputBillet,
    # Passifs
    "cpte_corr": InputCpteCorr,
    "depot_terme": InputDepotTerme,
    "bon_caisse": InputBonCaisse,
    "pension_livree": InputPensionLivree,
    "emprunt_inter": InputEmpruntInter,
    "emprunt_inter_banc": InputEmpruntInterBanc,
    "compte_courant": InputCompteCourant,
    "compte_cheque": InputCompteCheque,
    "compte_livret": InputCompteLivret,
    "avance_beac": InputAvanceBeac,
    "emprunt_titre": InputEmpruntTitre,
}

INPUT_LABELS = {
    "credit": ("Crédits", "actif"),
    "terme": ("Prêts à terme", "actif"),
    "decouvert": ("Découverts", "actif"),
    "bta": ("BTA", "actif"),
    "ota": ("OTA", "actif"),
    "emprunt_obl": ("Emprunts Obligataires", "actif"),
    "tab_amort": ("Tableau am. Crédits", "actif"),
    "pret_cor": ("Prêts correspondants", "actif"),
    "pret_inter_banc": ("Prêts interbanc. à blanc", "actif"),
    "beac": ("Compte BEAC", "actif"),
    "pret_titre": ("Prêts titre", "actif"),
    "billet": ("Billets et pièces", "actif"),
    "cpte_corr": ("Comptes correspondants", "passif"),
    "depot_terme": ("Dépôts à terme", "passif"),
    "bon_caisse": ("Bons de caisse", "passif"),
    "pension_livree": ("Pensions livrées", "passif"),
    "emprunt_inter": ("Emprunts interbanc. à blanc", "passif"),
    "emprunt_inter_banc": ("Emprunts interbancaires", "passif"),
    "compte_courant": ("Comptes 371", "passif"),
    "compte_cheque": ("Comptes 372", "passif"),
    "compte_livret": ("Comptes 373", "passif"),
    "avance_beac": ("Avances BEAC", "passif"),
    "emprunt_titre": ("Emprunts titres", "passif"),
}
