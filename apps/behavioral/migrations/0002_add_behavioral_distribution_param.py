# Generated manually on 2026-06-03

import django.db.models.deletion
import django.utils.timezone
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("behavioral", "0001_initial"),
        ("governance", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BehavioralDistributionParam",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(help_text="Identifiant unique (ex: compte_courant_retail_BU_RETAIL).", max_length=64, unique=True)),
                ("label", models.CharField(max_length=255)),
                ("product_type", models.CharField(
                    choices=[
                        ("compte_courant", "Comptes courants 371"),
                        ("compte_cheque", "Comptes chèques 372"),
                        ("compte_livret", "Comptes livrets 373"),
                        ("cpte_corr", "Comptes correspondants"),
                        ("beac", "Compte BEAC"),
                        ("credit_conso", "Crédit consommation"),
                        ("credit_immobilier", "Crédit immobilier"),
                        ("credit_corporate", "Crédit corporate"),
                        ("credit_autre", "Autre crédit"),
                        ("depot_terme", "Dépôt à terme"),
                        ("bon_caisse", "Bon de caisse"),
                        ("autre", "Autre produit"),
                    ],
                    max_length=32,
                )),
                ("segment", models.CharField(
                    choices=[
                        ("retail", "Retail / Particulier"),
                        ("sme", "PME"),
                        ("corporate", "Corporate"),
                        ("public", "Secteur public / Institutionnel"),
                        ("financial", "Institutions financières"),
                        ("all", "Tous segments"),
                    ],
                    default="all",
                    max_length=32,
                )),
                ("business_unit", models.CharField(blank=True, default="", help_text="BU spécifique (vide = tous les BU).", max_length=64)),
                ("secteur", models.CharField(blank=True, default="", help_text="Secteur économique (vide = tous les secteurs).", max_length=64)),
                ("devise", models.CharField(blank=True, default="", help_text="Devise (vide = toutes les devises).", max_length=3)),
                ("stable_core_pct", models.FloatField(default=50.0, help_text="Part stable cœur (%) — écoulement long, repricing lent.")),
                ("stable_non_core_pct", models.FloatField(default=20.0, help_text="Part stable non-cœur (%) — écoulement moyen.")),
                ("volatile_pct", models.FloatField(default=30.0, help_text="Part volatile (%) — sort au bucket Call. stable_core + stable_non_core + volatile = 100.")),
                ("runoff_core_months", models.IntegerField(default=60, help_text="Durée d'écoulement de la part stable cœur (mois).")),
                ("runoff_non_core_months", models.IntegerField(default=24, help_text="Durée d'écoulement de la part stable non-cœur (mois).")),
                ("repricing_lag_months", models.IntegerField(default=1, help_text="Délai de repricing aux taux de marché (mois).")),
                ("pass_through_pct", models.FloatField(default=50.0, help_text="Pass-through des hausses de taux vers la clientèle (β, %). 0 = aucune transmission, 100 = transmission intégrale.")),
                ("cpr_annual_pct", models.FloatField(default=0.0, help_text="Taux annuel de remboursement anticipé (CPR, %). 0 si non applicable.")),
                ("early_withdrawal_pct", models.FloatField(default=0.0, help_text="Taux annuel de retrait anticipé (pour dépôts à terme). 0 si non applicable.")),
                ("rollover_rate_pct", models.FloatField(default=0.0, help_text="Taux de renouvellement à maturité (%). 0 si non applicable.")),
                ("assumption_version", models.ForeignKey(
                    blank=True,
                    help_text="Version d'hypothèse (workflow maker-checker).",
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="behavioral_distribution_params",
                    to="governance.assumptionversion",
                )),
                ("is_active", models.BooleanField(default=False, help_text="Actif dans le moteur de calcul. Ne passer à True qu'après approbation.")),
                ("is_default", models.BooleanField(default=False, help_text="Paramètre par défaut utilisé si aucun paramètre plus spécifique n'est trouvé.")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Paramètre comportemental par segment",
                "verbose_name_plural": "Paramètres comportementaux par segment",
                "ordering": ["product_type", "segment", "business_unit"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalBehavioralDistributionParam",
            fields=[
                ("id", models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name="ID")),
                ("code", models.CharField(db_index=True, help_text="Identifiant unique (ex: compte_courant_retail_BU_RETAIL).", max_length=64)),
                ("label", models.CharField(max_length=255)),
                ("product_type", models.CharField(
                    choices=[
                        ("compte_courant", "Comptes courants 371"),
                        ("compte_cheque", "Comptes chèques 372"),
                        ("compte_livret", "Comptes livrets 373"),
                        ("cpte_corr", "Comptes correspondants"),
                        ("beac", "Compte BEAC"),
                        ("credit_conso", "Crédit consommation"),
                        ("credit_immobilier", "Crédit immobilier"),
                        ("credit_corporate", "Crédit corporate"),
                        ("credit_autre", "Autre crédit"),
                        ("depot_terme", "Dépôt à terme"),
                        ("bon_caisse", "Bon de caisse"),
                        ("autre", "Autre produit"),
                    ],
                    max_length=32,
                )),
                ("segment", models.CharField(
                    choices=[
                        ("retail", "Retail / Particulier"),
                        ("sme", "PME"),
                        ("corporate", "Corporate"),
                        ("public", "Secteur public / Institutionnel"),
                        ("financial", "Institutions financières"),
                        ("all", "Tous segments"),
                    ],
                    default="all",
                    max_length=32,
                )),
                ("business_unit", models.CharField(blank=True, default="", max_length=64)),
                ("secteur", models.CharField(blank=True, default="", max_length=64)),
                ("devise", models.CharField(blank=True, default="", max_length=3)),
                ("stable_core_pct", models.FloatField(default=50.0)),
                ("stable_non_core_pct", models.FloatField(default=20.0)),
                ("volatile_pct", models.FloatField(default=30.0)),
                ("runoff_core_months", models.IntegerField(default=60)),
                ("runoff_non_core_months", models.IntegerField(default=24)),
                ("repricing_lag_months", models.IntegerField(default=1)),
                ("pass_through_pct", models.FloatField(default=50.0)),
                ("cpr_annual_pct", models.FloatField(default=0.0)),
                ("early_withdrawal_pct", models.FloatField(default=0.0)),
                ("rollover_rate_pct", models.FloatField(default=0.0)),
                ("is_active", models.BooleanField(default=False)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                ("history_type", models.CharField(choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")], max_length=1)),
                ("assumption_version", models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="+",
                    to="governance.assumptionversion",
                )),
                ("history_user", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("history_relation", models.ForeignKey(
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name="history",
                    to="behavioral.behavioraldistributionparam",
                )),
            ],
            options={
                "verbose_name": "historical Paramètre comportemental par segment",
                "verbose_name_plural": "historical Paramètres comportementaux par segment",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.AlterUniqueTogether(
            name="behavioraldistributionparam",
            unique_together={("product_type", "segment", "business_unit", "secteur", "devise")},
        ),
    ]
