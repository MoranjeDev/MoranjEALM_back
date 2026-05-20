"""
Charge le jeu de données de test directement dans la base.

Pratique pour démarrer rapidement l'application avec des chiffres réalistes
sans passer par l'import Excel.

Usage :
    python manage.py load_sample_data            # ajoute aux données existantes
    python manage.py load_sample_data --reset    # vide d'abord les tables
    python manage.py load_sample_data --kinds credit,bta,ota   # uniquement certaines feuilles
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.inputs.models import INPUT_MODELS
from apps.inputs.sample_data import SAMPLE_DATA, total_records


class Command(BaseCommand):
    help = "Charge le jeu de données de test en base."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Supprime les données existantes des feuilles concernées avant insertion.")
        parser.add_argument("--kinds", default=None,
                            help="Liste de types séparés par virgule (ex: credit,bta,ota). "
                                 "Par défaut, charge tout.")

    @transaction.atomic
    def handle(self, *args, **opts):
        kinds = opts.get("kinds")
        if kinds:
            target = [k.strip() for k in kinds.split(",")]
        else:
            target = list(SAMPLE_DATA.keys())

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Chargement des données de test ({len(target)} type(s), "
            f"{total_records()} lignes au total disponibles)…"
        ))

        for kind in target:
            if kind not in INPUT_MODELS:
                self.stderr.write(self.style.WARNING(f"  Type inconnu, ignoré : {kind}"))
                continue
            model = INPUT_MODELS[kind]
            samples = SAMPLE_DATA.get(kind, [])
            if not samples:
                self.stdout.write(f"  {kind:<22} (aucun échantillon, skip)")
                continue

            if opts["reset"]:
                deleted, _ = model.objects.all().delete()
                if deleted:
                    self.stdout.write(f"  {kind:<22} {deleted} ligne(s) supprimée(s)")

            objs = [model(**s) for s in samples]
            model.objects.bulk_create(objs, batch_size=500)
            self.stdout.write(self.style.SUCCESS(
                f"  {kind:<22} {len(objs)} ligne(s) insérée(s)"
            ))

        self.stdout.write(self.style.SUCCESS("Chargement terminé."))
        self.stdout.write("")
        self.stdout.write("Lancez maintenant le calcul depuis l'interface (« Synthèses » → « Recalculer »)")
        self.stdout.write("ou en ligne de commande :")
        self.stdout.write("  python manage.py shell -c 'from apps.engine.output_generators import regenerate_outputs; print(regenerate_outputs())'")
