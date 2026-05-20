"""
Modèles : GroupeUser, Habilitation, User.

Reprend la logique de l'application Symfony existante :
- GroupeUser : groupe métier avec drapeaux is_validator, is_extractor.
- Habilitation : ensemble de droits fonctionnels rattachés à un groupe.
- User : extension de AbstractUser avec gestion d'expiration de mot de passe,
  première connexion, statut, et traçabilité.
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


# ----------------------------------------------------------------------------
# Liste des permissions fonctionnelles disponibles dans l'application.
# Reprise fidèle des habilitations de la version Symfony existante,
# enrichie pour les nouveautés cahier des charges.
# ----------------------------------------------------------------------------
HABILITATION_CHOICES = [
    # Modules métier (existants)
    ("Liquidity Gap", "Liquidity Gap"),
    ("Importation des données", "Importation des données"),
    ("Graphes", "Graphes"),
    ("Rapports", "Rapports"),
    ("Résultats", "Résultats"),
    ("Ratio de liquidité", "Ratio de liquidité"),
    ("Gap de taux", "Gap de taux"),
    ("Charte ALCO", "Charte ALCO"),
    ("Politique ALM", "Politique ALM"),

    # Administration
    ("Gestion des Utilisateurs", "Gestion des Utilisateurs"),
    ("Gestion des Groupes Utilisateurs", "Gestion des Groupes Utilisateurs"),
    ("Gestion des Habilitations", "Gestion des Habilitations"),
    ("Paramètre de mot de passe", "Paramètre de mot de passe"),

    # Nouveautés cahier des charges (phase 4)
    ("NII Sensitivity", "NII Sensitivity"),
    ("EVE Sensitivity", "EVE Sensitivity"),
    ("FTP", "FTP"),
    ("Stress Tests", "Stress Tests"),
    ("Modélisation comportementale", "Modélisation comportementale"),
    ("Multi-devises", "Multi-devises"),
    ("Vue consolidée groupe", "Vue consolidée groupe"),
    ("Concentration", "Concentration"),
    ("Reporting réglementaire", "Reporting réglementaire"),
    ("Tableaux de bord ALCO", "Tableaux de bord ALCO"),
    ("Gouvernance hypothèses", "Gouvernance hypothèses"),
]


class GroupeUser(models.Model):
    """Groupe d'utilisateurs (équivalent de l'entité GroupeUser Symfony)."""

    nom = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    is_validator = models.BooleanField(
        default=False,
        help_text="Le groupe peut valider les actions soumises au workflow maker-checker.",
    )
    is_extractor = models.BooleanField(
        default=False,
        help_text="Le groupe peut extraire les rapports et données.",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Groupe d'utilisateurs"
        verbose_name_plural = "Groupes d'utilisateurs"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom

    @property
    def habilitations_list(self) -> list[str]:
        """Retourne la liste plate des habilitations du groupe."""
        h = getattr(self, "habilitation", None)
        return list(h.permissions) if h else []


class Habilitation(models.Model):
    """Permissions fonctionnelles attachées à un groupe."""

    groupe = models.OneToOneField(
        GroupeUser,
        on_delete=models.CASCADE,
        related_name="habilitation",
    )
    # Stockage en JSON (équivalent de Types::ARRAY de Symfony)
    permissions = models.JSONField(default=list)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Habilitation"
        verbose_name_plural = "Habilitations"

    def __str__(self) -> str:
        return f"Habilitation {self.groupe.nom}"

    def has_permission(self, permission: str) -> bool:
        return permission in (self.permissions or [])


class UserManager(BaseUserManager):
    """Manager pour le modèle User custom."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError("L'identifiant est obligatoire.")
        email = self.normalize_email(email) if email else ""
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", User.STATUS_ACTIVE)
        extra_fields.setdefault("firstconnect", False)
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Utilisateur applicatif.
    Reprend les champs de l'entité User de Symfony :
    first_name, last_name, username, password, email, status, firstconnect,
    groupe, last_login, password_change_date.
    """

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_BLOCKED = "blocked"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Actif"),
        (STATUS_INACTIVE, "Inactif"),
        (STATUS_BLOCKED, "Bloqué"),
    ]

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE
    )
    firstconnect = models.BooleanField(
        default=True,
        help_text="True si l'utilisateur n'a pas encore changé son mot de passe initial.",
    )
    groupe = models.ForeignKey(
        GroupeUser,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
    )
    password_change_date = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    objects = UserManager()

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"
        ordering = ["username"]

    def __str__(self) -> str:
        return self.username

    @property
    def full_name(self) -> str:
        return (f"{self.first_name} {self.last_name}").strip() or self.username

    @property
    def habilitations(self) -> list[str]:
        """Retourne les habilitations héritées du groupe."""
        if self.groupe and hasattr(self.groupe, "habilitation"):
            return list(self.groupe.habilitation.permissions or [])
        return []

    def has_habilitation(self, permission: str) -> bool:
        return self.is_superuser or permission in self.habilitations

    def password_expired(self, delay_days: int) -> bool:
        """Vérifie si le mot de passe a expiré (délai en jours)."""
        if not self.password_change_date or delay_days <= 0:
            return False
        expires_at = self.password_change_date + timezone.timedelta(days=delay_days)
        return timezone.now() >= expires_at

    def set_password(self, raw_password):  # type: ignore[override]
        super().set_password(raw_password)
        self.password_change_date = timezone.now()
