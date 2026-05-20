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
        parser.add_argument("--compute", action="store_true",
                            help="Recalcule les Outputs après le chargement des données.")

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

        # ---- Hypothèses standards gouvernées ----
        from apps.governance.services import ensure_standard_assumptions

        ensure_standard_assumptions()
        self.stdout.write("  Hypothèses standards initialisées / vérifiées.")

        # ---- Référentiels de base ----
        from apps.mapping.models import (
            CollateralType,
            Currency,
            CustomerSegment,
            Entity,
            FxRate,
            RepricingBucket,
        )
        from apps.reporting.models import ReportTemplate
        from apps.reporting.pptx_export import DEFAULT_SECTIONS

        xaf, _ = Currency.objects.update_or_create(
            code="XAF",
            defaults={"label": "Franc CFA BEAC", "is_base": True, "decimals": 0, "is_active": True},
        )
        for code, label, rate, decimals in [
            ("EUR", "Euro", 655.957, 2),
            ("USD", "Dollar américain", 610.0, 2),
        ]:
            currency, _ = Currency.objects.update_or_create(
                code=code,
                defaults={"label": label, "is_base": False, "decimals": decimals, "is_active": True},
            )
            FxRate.objects.get_or_create(
                currency=currency,
                date=(param.dateArrete or timezone.now()).date(),
                defaults={"rate": rate, "source": "bootstrap"},
            )
        FxRate.objects.get_or_create(
            currency=xaf,
            date=(param.dateArrete or timezone.now()).date(),
            defaults={"rate": 1.0, "source": "bootstrap"},
        )
        Entity.objects.update_or_create(
            code="BANK",
            defaults={
                "label": param.bankName or "Banque cliente",
                "country": "CM",
                "base_currency": xaf,
                "consolidation": "full",
                "is_active": True,
            },
        )
        for code, label, days_min, days_max, midpoint, order in [
            ("TODAY", "Aujourd'hui", 0, 1, 1, 1),
            ("D7", "+ 7 jours", 2, 7, 4, 2),
            ("D15", "+ 15 jours", 8, 15, 11, 3),
            ("M1", "+ 1 mois", 16, 30, 23, 4),
            ("M2", "+ 2 mois", 31, 60, 45, 5),
            ("M3", "+ 3 mois", 61, 90, 75, 6),
            ("M6", "+ 6 mois", 91, 180, 135, 7),
            ("Y1", "+ 1 an", 181, 365, 273, 8),
            ("Y3", "+ 3 ans", 366, 1095, 730, 9),
            ("Y5", "+ 5 ans", 1096, 1825, 1460, 10),
            ("GT5", "Au-delà", 1826, None, 2555, 11),
        ]:
            RepricingBucket.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "days_min": days_min,
                    "days_max": days_max,
                    "midpoint_days": midpoint,
                    "order": order,
                },
            )
        for code, label, flags, risk_weight in [
            ("RETAIL", "Particuliers", {"is_retail": True}, 0.10),
            ("CORPORATE", "Entreprises", {"is_corporate": True}, 0.40),
            ("FINANCIAL", "Institutions financières", {"is_financial": True}, 1.00),
            ("PUBLIC", "Secteur public", {}, 0.20),
        ]:
            CustomerSegment.objects.update_or_create(
                code=code,
                defaults={"label": label, "risk_weight": risk_weight, "is_active": True, **flags},
            )
        for code, label, liquidity_level, haircut in [
            ("CASH", "Caisse et banque centrale", "level1", 0.0),
            ("SOVEREIGN", "Titres souverains éligibles", "level1", 0.0),
            ("OPCVM", "Parts OPCVM/SICAV éligibles", "level2a", 15.0),
            ("OTHER", "Autres sûretés", "non_hqla", 100.0),
        ]:
            CollateralType.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "eligible_basel": liquidity_level != "non_hqla",
                    "haircut_pct": haircut,
                    "liquidity_level": liquidity_level,
                    "is_active": True,
                },
            )
        ReportTemplate.objects.update_or_create(
            code="ALCO_STANDARD",
            defaults={
                "label": "Rapport ALCO standard",
                "scope": "alco",
                "description": "Template standard généré au bootstrap.",
                "sections": DEFAULT_SECTIONS,
                "is_active": True,
            },
        )
        self.stdout.write("  Référentiels standards initialisés / vérifiés.")

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

        if opts["compute"]:
            from apps.engine.output_generators import regenerate_outputs
            self.stdout.write("")
            self.stdout.write("Recalcul des outputs ALM…")
            summary = regenerate_outputs()
            self.stdout.write(self.style.SUCCESS(
                f"  {summary['total']} ligne(s) Output générée(s)."
            ))

        self.stdout.write(self.style.SUCCESS("Bootstrap terminé."))
