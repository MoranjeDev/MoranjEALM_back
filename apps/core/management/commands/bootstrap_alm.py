"""
Initialise les données de référence pour un démarrage local.

Crée :
- Le groupe « Administrateurs » avec TOUTES les habilitations.
- Le groupe « Trésorerie » avec les habilitations métier (sans gestion).
- Le groupe « Risques » avec habilitations risk + gouvernance.
- Le groupe « Lecture seule » avec habilitations de consultation.
- Le Parameter singleton avec valeurs ALM par défaut.
- Optionnellement, un super-utilisateur.

Usage :
    python manage.py bootstrap_alm
    python manage.py bootstrap_alm --admin-username admin --admin-password admin
    python manage.py bootstrap_alm --reset    # recrée les groupes
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import HABILITATION_CHOICES, GroupeUser, Habilitation, User
from apps.parameters.models import Parameter


GROUP_DEFINITIONS = {
    "Administrateurs": {
        "habilitations": [code for code, _ in HABILITATION_CHOICES],
        "is_validator": True,
        "is_extractor": True,
    },
    "Trésorerie": {
        "habilitations": [
            "Liquidity Gap", "Importation des données", "Graphes", "Rapports",
            "Résultats", "Ratio de liquidité", "Gap de taux",
            "NII Sensitivity", "EVE Sensitivity", "FTP",
            "Stress Tests", "Multi-devises", "Tableaux de bord ALCO",
            "Charte ALCO", "Politique ALM",
        ],
        "is_validator": False,
        "is_extractor": True,
    },
    "Risques": {
        "habilitations": [
            "Liquidity Gap", "Graphes", "Rapports", "Résultats",
            "Ratio de liquidité", "Gap de taux",
            "NII Sensitivity", "EVE Sensitivity",
            "Stress Tests", "Modélisation comportementale",
            "Concentration", "Multi-devises", "Vue consolidée groupe",
            "Reporting réglementaire",
            "Gouvernance hypothèses",
            "Charte ALCO", "Politique ALM",
        ],
        "is_validator": True,
        "is_extractor": True,
    },
    "Lecture seule": {
        "habilitations": [
            "Liquidity Gap", "Graphes", "Rapports", "Résultats",
            "Ratio de liquidité", "Gap de taux",
            "Charte ALCO", "Politique ALM",
        ],
        "is_validator": False,
        "is_extractor": False,
    },
}


class Command(BaseCommand):
    help = "Initialise les données de référence (groupes, habilitations, paramètre)."

    def add_arguments(self, parser):
        parser.add_argument("--admin-username", default=None,
                            help="Si fourni, crée un super-utilisateur avec ce nom.")
        parser.add_argument("--admin-password", default=None,
                            help="Mot de passe du super-utilisateur (si --admin-username fourni).")
        parser.add_argument("--admin-email", default="admin@local",
                            help="Email du super-utilisateur.")
        parser.add_argument("--reset", action="store_true",
                            help="Supprime les groupes existants avant de les recréer.")
        parser.add_argument("--with-sample", action="store_true",
                            help="Charge aussi le jeu de données de test (load_sample_data).")

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING("Bootstrap MoranjEALM"))

        if opts["reset"]:
            self.stdout.write("Suppression des groupes existants…")
            GroupeUser.objects.filter(nom__in=GROUP_DEFINITIONS.keys()).delete()

        # ---- Groupes ----
        for name, cfg in GROUP_DEFINITIONS.items():
            group, created = GroupeUser.objects.get_or_create(
                nom=name,
                defaults={
                    "is_validator": cfg["is_validator"],
                    "is_extractor": cfg["is_extractor"],
                    "description": f"Groupe {name} créé par bootstrap_alm.",
                },
            )
            Habilitation.objects.update_or_create(
                groupe=group,
                defaults={"permissions": cfg["habilitations"]},
            )
            verb = "Créé" if created else "Mis à jour"
            self.stdout.write(f"  {verb} : {name} ({len(cfg['habilitations'])} permissions)")

        # ---- Parameter singleton ----
        param = Parameter.get_solo()
        if not param.dateMajCore:
            now = timezone.now()
            param.dateMajCore = now
            param.dateMajExtra = now
            param.dateArrete = now
            # Valeurs comportementales par défaut (à calibrer en phase 6)
            param.beta_cheque = 0.5
            param.beta_courant = 0.6
            param.beta_livret = 0.4
            param.beta_beac = 0.0
            param.beta_corr = 0.7
            param.stable_cheque = 0.85
            param.stable_courant = 0.80
            param.stable_livret = 0.90
            param.stable_beac = 1.0
            param.stable_corr = 0.50
            param.var_cheque = 0.05
            param.var_courant = 0.05
            param.var_livret = 0.03
            param.var_beac = 0.01
            param.var_corr = 0.10
            # Chocs de stress par défaut (à calibrer)
            param.credMod = 5
            param.credSev = 15
            param.banMod = 5
            param.banSev = 15
            param.retMod = 10
            param.retSev = 25
            param.guiMod = 5
            param.guiSev = 15
            param.passwordDelay = 90
            param.delayActivate = True
            param.save()
            self.stdout.write("  Paramètre singleton initialisé avec valeurs par défaut.")
        else:
            self.stdout.write("  Paramètre singleton déjà initialisé (skip).")

        # ---- Super-utilisateur (optionnel) ----
        if opts["admin_username"] and opts["admin_password"]:
            admin_group = GroupeUser.objects.get(nom="Administrateurs")
            user, created = User.objects.get_or_create(
                username=opts["admin_username"],
                defaults={
                    "email": opts["admin_email"],
                    "first_name": "Admin",
                    "last_name": "MoranjEALM",
                    "is_staff": True,
                    "is_superuser": True,
                    "status": User.STATUS_ACTIVE,
                    "firstconnect": False,
                    "groupe": admin_group,
                },
            )
            user.set_password(opts["admin_password"])
            user.firstconnect = False
            user.is_staff = True
            user.is_superuser = True
            user.status = User.STATUS_ACTIVE
            user.groupe = admin_group
            user.save()
            verb = "Créé" if created else "Mis à jour"
            self.stdout.write(self.style.SUCCESS(
                f"  {verb} super-utilisateur : {user.username}"
            ))

        # ---- Données de test (optionnel) ----
        if opts["with_sample"]:
            from django.core.management import call_command
            self.stdout.write("")
            call_command("load_sample_data", reset=True)

        self.stdout.write(self.style.SUCCESS("Bootstrap terminé."))
