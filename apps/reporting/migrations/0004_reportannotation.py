# Generated manually for report section annotations.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reporting", "0003_reportrun_certification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportAnnotation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "section",
                    models.CharField(
                        choices=[
                            ("synthesis", "Synthèse liquidité"),
                            ("lcr", "Liquidity Coverage Ratio"),
                            ("rate_gap", "Gap de taux"),
                            ("nii", "NII Sensitivity"),
                            ("eve", "EVE Sensitivity"),
                            ("concentration", "Concentration"),
                            ("multicurrency", "Multi-devises"),
                            ("custom", "Personnalisé"),
                        ],
                        db_index=True,
                        max_length=64,
                    ),
                ),
                ("scenario", models.CharField(blank=True, db_index=True, default="", max_length=32)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="report_annotations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Annotation de rapport",
                "verbose_name_plural": "Annotations de rapport",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="reportannotation",
            index=models.Index(fields=["section", "scenario", "-created_at"], name="reporting_r_section_b54f1e_idx"),
        ),
    ]
