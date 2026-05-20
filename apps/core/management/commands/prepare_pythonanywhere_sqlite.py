"""
Prepare a PythonAnywhere SQLite deployment.

This command is intentionally a small orchestrator around existing commands:
- migrate database schema
- bootstrap groups, permissions, parameters and optional admin
- optionally load realistic demo inputs
- recompute Output rows so dashboards and ratios work immediately
- optionally collect static files
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Prepare SQLite data for a PythonAnywhere deployment."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-sample",
            action="store_true",
            help="Load the realistic demo input dataset into SQLite.",
        )
        parser.add_argument(
            "--reset-sample",
            action="store_true",
            help="Delete existing input rows before loading the demo dataset.",
        )
        parser.add_argument(
            "--admin-username",
            default=None,
            help="Create or update a superuser with this username.",
        )
        parser.add_argument(
            "--admin-password",
            default=None,
            help="Password for the superuser.",
        )
        parser.add_argument(
            "--admin-email",
            default="admin@local",
            help="Email for the superuser.",
        )
        parser.add_argument(
            "--skip-static",
            action="store_true",
            help="Do not run collectstatic.",
        )

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING("Preparing PythonAnywhere SQLite deployment"))

        self.stdout.write("1/5 Applying migrations...")
        call_command("migrate", interactive=False)

        self.stdout.write("2/5 Bootstrapping reference data...")
        bootstrap_kwargs = {}
        if opts["admin_username"] and opts["admin_password"]:
            bootstrap_kwargs.update(
                {
                    "admin_username": opts["admin_username"],
                    "admin_password": opts["admin_password"],
                    "admin_email": opts["admin_email"],
                }
            )
        call_command("bootstrap_alm", **bootstrap_kwargs)

        if opts["with_sample"]:
            self.stdout.write("3/5 Loading realistic sample inputs...")
            load_kwargs = {"reset": opts["reset_sample"]}
            call_command("load_sample_data", **load_kwargs)
        else:
            self.stdout.write("3/5 Sample inputs skipped.")

        self.stdout.write("4/5 Recomputing ALM outputs...")
        from apps.engine.output_generators import regenerate_outputs

        summary = regenerate_outputs()
        self.stdout.write(
            self.style.SUCCESS(
                f"  Outputs generated: {summary['total']} rows "
                f"from reference date {summary['reference_date']}"
            )
        )

        if opts["skip_static"]:
            self.stdout.write("5/5 Static collection skipped.")
        else:
            self.stdout.write("5/5 Collecting static files...")
            call_command("collectstatic", interactive=False, verbosity=0)

        self.stdout.write(self.style.SUCCESS("PythonAnywhere SQLite deployment is ready."))
