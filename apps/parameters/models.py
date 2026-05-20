"""
Paramètre ALM unique (singleton) — équivalent de l'entité Parameter Symfony.

Concentre :
- Coefficients comportementaux (beta, stable, var) par catégorie de compte.
- Paramètres de stress modéré et sévère.
- Commentaires ALCO et DG par scénario (base / modéré / sévère).
- Dates de dernière mise à jour des inputs Core / Extra.
- Délai d'expiration de mot de passe.

Le pattern singleton garantit qu'une seule entrée existe en base.
"""

from django.db import models
from simple_history.models import HistoricalRecords


CATEGORIES = ["cheque", "courant", "livret", "beac", "corr"]


class Parameter(models.Model):
    """Paramètre métier global (singleton)."""

    # ---- Mot de passe ----
    passwordDelay = models.IntegerField(default=90)
    delayActivate = models.BooleanField(default=True)

    # ---- Dates de dernière maj ----
    dateMajCore = models.DateTimeField(null=True, blank=True)
    dateMajExtra = models.DateTimeField(null=True, blank=True)
    dateArrete = models.DateTimeField(null=True, blank=True, help_text="Date d'arrêté")

    # ---- Commentaires ALCO ----
    commalcobase = models.TextField(blank=True, default="")
    commalcomodere = models.TextField(blank=True, default="")
    commalcosevere = models.TextField(blank=True, default="")
    # ---- Commentaires DG ----
    commdgbase = models.TextField(blank=True, default="")
    commdgmodere = models.TextField(blank=True, default="")
    commdgsevere = models.TextField(blank=True, default="")

    # ---- Coefficients comportementaux ----
    beta_cheque = models.FloatField(null=True, blank=True)
    beta_courant = models.FloatField(null=True, blank=True)
    beta_livret = models.FloatField(null=True, blank=True)
    beta_beac = models.FloatField(null=True, blank=True)
    beta_corr = models.FloatField(null=True, blank=True)

    stable_courant = models.FloatField(null=True, blank=True)
    stable_cheque = models.FloatField(null=True, blank=True)
    stable_livret = models.FloatField(null=True, blank=True)
    stable_beac = models.FloatField(null=True, blank=True)
    stable_corr = models.FloatField(null=True, blank=True)

    var_courant = models.FloatField(null=True, blank=True)
    var_cheque = models.FloatField(null=True, blank=True)
    var_livret = models.FloatField(null=True, blank=True)
    var_beac = models.FloatField(null=True, blank=True)
    var_corr = models.FloatField(null=True, blank=True)

    # ---- Stress test ----
    credMod = models.IntegerField(default=0)
    credSev = models.IntegerField(default=0)
    banMod = models.IntegerField(default=0)
    banSev = models.IntegerField(default=0)
    retMod = models.IntegerField(default=0)
    retSev = models.IntegerField(default=0)
    guiMod = models.IntegerField(default=0)
    guiSev = models.IntegerField(default=0)

    # ---- Identité client / banque ----
    bankName = models.CharField(max_length=255, blank=True, default="")
    bankLogo = models.FileField(upload_to="bank_logos/", null=True, blank=True)

    # ---- Métadonnées ----
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Paramètre"
        verbose_name_plural = "Paramètres"

    def __str__(self) -> str:
        return f"Paramètre #{self.pk}"

    # ------------------------------------------------------------------
    # Accès singleton
    # ------------------------------------------------------------------
    @classmethod
    def get_solo(cls) -> "Parameter":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
