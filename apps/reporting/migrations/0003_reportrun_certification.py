from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reporting", "0002_reporttemplate_owner_sharing"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportrun",
            name="certification_status",
            field=models.CharField(
                choices=[
                    ("draft", "Brouillon"),
                    ("submitted", "Soumis"),
                    ("certified", "Validé"),
                    ("rejected", "Rejeté"),
                ],
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="certification_comment",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="certified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="submitted_report_runs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="certified_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="certified_report_runs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="reportrun",
            name="rejected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="rejected_report_runs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
