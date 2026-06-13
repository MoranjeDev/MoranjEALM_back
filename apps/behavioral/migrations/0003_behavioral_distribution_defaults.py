# Data migration — paramètres comportementaux par défaut (zone CEMAC/Cameroun)
# Valeurs de départ à valider via le workflow de gouvernance.

from django.db import migrations


DEFAULT_PARAMS = [
    # (code, label, product_type, segment, stable_core, stable_non_core, volatile, runoff_core, runoff_non_core, is_default)
    (
        "compte_courant_retail",
        "Compte courant 371 — Retail",
        "compte_courant", "retail",
        60.0, 10.0, 30.0, 48, 18, False,
    ),
    (
        "compte_courant_corporate",
        "Compte courant 371 — Corporate",
        "compte_courant", "corporate",
        30.0, 10.0, 60.0, 18, 9, False,
    ),
    (
        "compte_courant_public",
        "Compte courant 371 — Secteur public",
        "compte_courant", "public",
        20.0, 5.0, 75.0, 12, 6, False,
    ),
    (
        "compte_cheque_retail",
        "Compte chèque 372 — Retail",
        "compte_cheque", "retail",
        55.0, 15.0, 30.0, 36, 18, False,
    ),
    (
        "compte_cheque_corporate",
        "Compte chèque 372 — Corporate",
        "compte_cheque", "corporate",
        25.0, 15.0, 60.0, 12, 6, False,
    ),
    (
        "compte_livret_retail",
        "Compte livret 373 — Retail",
        "compte_livret", "retail",
        65.0, 15.0, 20.0, 60, 24, False,
    ),
    (
        "compte_courant_all_default",
        "Compte courant 371 — Tous segments (défaut)",
        "compte_courant", "all",
        50.0, 15.0, 35.0, 36, 18, True,
    ),
]


def create_defaults(apps, schema_editor):
    BehavioralDistributionParam = apps.get_model("behavioral", "BehavioralDistributionParam")
    for (
        code, label, product_type, segment,
        stable_core, stable_non_core, volatile,
        runoff_core, runoff_non_core, is_default
    ) in DEFAULT_PARAMS:
        BehavioralDistributionParam.objects.get_or_create(
            code=code,
            defaults=dict(
                label=label,
                product_type=product_type,
                segment=segment,
                stable_core_pct=stable_core,
                stable_non_core_pct=stable_non_core,
                volatile_pct=volatile,
                runoff_core_months=runoff_core,
                runoff_non_core_months=runoff_non_core,
                is_active=False,   # à activer après approbation governance
                is_default=is_default,
            ),
        )


def delete_defaults(apps, schema_editor):
    BehavioralDistributionParam = apps.get_model("behavioral", "BehavioralDistributionParam")
    codes = [row[0] for row in DEFAULT_PARAMS]
    BehavioralDistributionParam.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("behavioral", "0002_add_behavioral_distribution_param"),
    ]

    operations = [
        migrations.RunPython(create_defaults, reverse_code=delete_defaults),
    ]
