"""
Service d'import Excel multi-feuilles pour les inputs ALM.

Le classeur Excel attendu contient une feuille par type d'input. Le nom
de chaque feuille correspond à la clé du modèle (ex: "credit", "bta",
"depot_terme"). La première ligne contient les en-têtes correspondant
aux noms de champs Django.

Exemple :
    Feuille "credit" avec colonnes :
        code_agence | num_dossier | raci | avenant | date_mep |
        date_prem_echeance | date_deu_echeance | nbre_echeance |
        taux_interet | capital_restant | montant_debloque | frequence

L'import est :
- atomique par feuille (toutes les lignes ou aucune),
- non destructif (ne supprime pas les données existantes par défaut),
- option `replace=True` pour remplacer le contenu d'une feuille.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import openpyxl
from django.db import transaction
from django.utils import timezone

from .models import INPUT_MODELS


@dataclass
class SheetReport:
    kind: str
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    sheets: list[SheetReport] = field(default_factory=list)

    @property
    def total_inserted(self) -> int:
        return sum(s.inserted for s in self.sheets)

    @property
    def total_errors(self) -> int:
        return sum(len(s.errors) for s in self.sheets)


def _parse_value(value: Any, field_obj) -> Any:
    """Convertit une valeur Excel vers le type Django attendu."""
    if value is None or value == "":
        return None

    internal = field_obj.get_internal_type()

    if internal in ("DateTimeField", "DateField"):
        if isinstance(value, dt.datetime):
            return timezone.make_aware(value) if timezone.is_naive(value) else value
        if isinstance(value, dt.date):
            return timezone.make_aware(dt.datetime.combine(value, dt.time.min))
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M"):
                try:
                    parsed = dt.datetime.strptime(value.strip(), fmt)
                    return timezone.make_aware(parsed)
                except ValueError:
                    continue
            raise ValueError(f"Date invalide : {value!r}")

    if internal in ("BigIntegerField", "IntegerField", "PositiveIntegerField"):
        return int(float(value))

    if internal in ("FloatField", "DecimalField"):
        return float(value)

    if internal == "BooleanField":
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "oui", "vrai")
        return bool(value)

    return str(value).strip() if isinstance(value, str) else value


# ----------------------------------------------------------------------------
# Détection de la ligne d'aide (template généré)
# ----------------------------------------------------------------------------
_FIELD_TYPE_NAMES = {
    "AutoField", "BigAutoField", "BigIntegerField", "BooleanField", "CharField",
    "DateField", "DateTimeField", "DecimalField", "DurationField", "EmailField",
    "FileField", "FloatField", "ForeignKey", "GenericIPAddressField",
    "IntegerField", "JSONField", "ManyToManyField", "OneToOneField",
    "PositiveBigIntegerField", "PositiveIntegerField", "PositiveSmallIntegerField",
    "SlugField", "SmallIntegerField", "TextField", "TimeField", "URLField",
    "UUIDField",
}


def _is_type_hint_row(row) -> bool:
    """Détecte la ligne 2 du template généré : elle contient les types Django
    (CharField, DateTimeField, BigIntegerField, ...) en aide visuelle.
    On la saute lors de l'import."""
    non_empty = [str(v).strip() for v in row if v is not None and str(v).strip()]
    if not non_empty:
        return False
    matches = sum(1 for v in non_empty if v in _FIELD_TYPE_NAMES)
    # Si au moins 60% des cellules non vides sont des noms de FieldType, c'est l'aide.
    return matches >= max(1, int(len(non_empty) * 0.6))


def _import_sheet(workbook, kind: str, *, replace: bool) -> SheetReport:
    report = SheetReport(kind=kind)
    if kind not in workbook.sheetnames:
        return report  # silencieux : la feuille n'existe pas, c'est OK

    model = INPUT_MODELS[kind]
    sheet = workbook[kind]

    # Première ligne = en-têtes
    rows = sheet.iter_rows(values_only=True)
    try:
        headers = [str(h).strip() if h is not None else "" for h in next(rows)]
    except StopIteration:
        return report

    field_map = {f.name: f for f in model._meta.fields if f.name != "id"}

    valid_columns: list[tuple[int, str]] = []
    for idx, header in enumerate(headers):
        if header in field_map:
            valid_columns.append((idx, header))

    if not valid_columns:
        report.errors.append(f"Aucune colonne reconnue pour la feuille {kind}.")
        return report

    objects: list = []
    for row_idx, row in enumerate(rows, start=2):
        if not any(row):
            continue
        # Sauter la ligne d'aide « ligne 2 » du template généré
        if row_idx == 2 and _is_type_hint_row(row):
            continue
        try:
            obj_kwargs = {}
            for col_idx, field_name in valid_columns:
                value = row[col_idx] if col_idx < len(row) else None
                obj_kwargs[field_name] = _parse_value(value, field_map[field_name])

            # Validation rapide des champs obligatoires non nullables
            for fname, fobj in field_map.items():
                if (
                    not fobj.null
                    and not fobj.blank
                    and not fobj.has_default()
                    and obj_kwargs.get(fname) is None
                    and fname in [c[1] for c in valid_columns]
                ):
                    raise ValueError(f"Valeur manquante pour la colonne « {fname} ».")

            objects.append(model(**obj_kwargs))
        except Exception as e:  # noqa: BLE001
            report.errors.append(f"Ligne {row_idx} : {e}")
            report.skipped += 1

    with transaction.atomic():
        if replace:
            model.objects.all().delete()
        if objects:
            model.objects.bulk_create(objects, batch_size=500)
            report.inserted = len(objects)

    return report


def import_workbook(file_obj, *, kinds: list[str] | None = None, replace: bool = False) -> ImportReport:
    """
    Importe un classeur Excel.

    :param file_obj: handle binaire (UploadedFile.file) ou chemin.
    :param kinds: liste des feuilles à importer (None = toutes celles connues).
    :param replace: si True, vide la table avant l'import.
    """
    workbook = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    report = ImportReport()
    targets = kinds or list(INPUT_MODELS.keys())

    for kind in targets:
        sheet_report = _import_sheet(workbook, kind, replace=replace)
        if sheet_report.kind:
            report.sheets.append(sheet_report)

    workbook.close()
    return report
