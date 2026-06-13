"""
Service d'import Excel pour les lignes de bilan GL (BalanceSheetLine).

Format attendu : un fichier Excel avec une feuille contenant les colonnes
listées dans EXPECTED_COLUMNS (détection par en-tête, case-insensitive).

L'import est :
- atomique par date d'arrêté,
- option replace=True pour supprimer les lignes du même date_arrete avant import.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import openpyxl
from django.db import transaction
from django.utils import timezone

from .models import BalanceSheetLine, SENS_CHOICES, TYPE_TAUX_CHOICES

VALID_SENS = {c[0] for c in SENS_CHOICES}
VALID_TYPE_TAUX = {c[0] for c in TYPE_TAUX_CHOICES}

EXPECTED_COLUMNS = [
    "date_arrete", "compte_gl", "libelle", "product_code", "client_id", "client_name",
    "business_unit", "segment", "sous_segment", "secteur",
    "devise", "montant_lcy", "montant_fcy", "sens",
    "type_taux", "taux_moyen", "maturite", "bucket_liquidite", "bucket_repricing",
    "entite", "agence", "source",
]


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


def _parse_date(value: Any) -> dt.date | None:
    """Convertit une valeur Excel en date Python."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return dt.datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Date invalide : {value!r}")
    raise ValueError(f"Type de date non reconnu : {type(value)}")


def _parse_value(value: Any, col: str) -> Any:
    """Convertit une valeur Excel selon la colonne cible."""
    if value is None or value == "":
        return None

    if col in ("date_arrete", "maturite"):
        return _parse_date(value)

    if col in ("montant_lcy", "montant_fcy"):
        return int(float(value))

    if col == "taux_moyen":
        return float(value)

    return str(value).strip() if isinstance(value, str) else str(value).strip() if value is not None else None


def _is_template_helper_row(row: tuple[Any, ...], col_map: dict[str, int]) -> bool:
    """Ignore les lignes d'aide/exemple générées par le template Excel."""
    def get(col: str):
        idx = col_map.get(col)
        return row[idx] if idx is not None and idx < len(row) else None

    first = str(get("date_arrete") or "").strip().lower()
    account = str(get("compte_gl") or "").strip()
    label = str(get("libelle") or "").strip().lower()
    return (
        first.startswith("date d'arrêté")
        or first.startswith("date d'arrete")
        or (account == "101001" and label == "caisse xaf")
    )


def import_balance_sheet_excel(file_obj, *, replace: bool = False) -> ImportReport:
    """
    Importe un fichier Excel contenant des lignes de bilan GL.

    :param file_obj: handle binaire (UploadedFile) ou chemin.
    :param replace: si True, supprime les lignes du même date_arrete avant import.
    :returns: ImportReport avec le détail des lignes insérées/erreurs.
    """
    workbook = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    report = ImportReport()

    # Prendre la première feuille disponible (ou "bilan" si elle existe)
    sheet_name = workbook.sheetnames[0] if workbook.sheetnames else None
    if "bilan" in [s.lower() for s in workbook.sheetnames]:
        sheet_name = next(s for s in workbook.sheetnames if s.lower() == "bilan")

    if not sheet_name:
        workbook.close()
        r = SheetReport(kind="bilan")
        r.errors.append("Fichier Excel vide ou sans feuille.")
        report.sheets.append(r)
        return report

    sheet = workbook[sheet_name]
    r = SheetReport(kind=sheet_name)

    rows = sheet.iter_rows(values_only=True)
    try:
        raw_headers = next(rows)
    except StopIteration:
        r.errors.append("Feuille vide.")
        report.sheets.append(r)
        workbook.close()
        return report

    # Mapping index -> nom_colonne (case-insensitive)
    headers_lower = [str(h).strip().lower() if h is not None else "" for h in raw_headers]
    col_map: dict[str, int] = {}
    for idx, h in enumerate(headers_lower):
        if h in EXPECTED_COLUMNS:
            col_map[h] = idx

    if not col_map:
        r.errors.append("Aucune colonne reconnue. Vérifiez les en-têtes.")
        report.sheets.append(r)
        workbook.close()
        return report

    objects: list[BalanceSheetLine] = []
    dates_seen: set[dt.date] = set()

    for row_idx, row in enumerate(rows, start=2):
        if not any(row):
            continue
        if _is_template_helper_row(row, col_map):
            continue

        def get(col):
            idx = col_map.get(col)
            return row[idx] if idx is not None and idx < len(row) else None

        try:
            # Champs obligatoires
            date_arrete = _parse_date(get("date_arrete"))
            if date_arrete is None:
                raise ValueError("date_arrete est obligatoire.")

            compte_gl_raw = get("compte_gl")
            if compte_gl_raw is None or str(compte_gl_raw).strip() == "":
                raise ValueError("compte_gl est obligatoire.")
            compte_gl = str(compte_gl_raw).strip()

            montant_lcy_raw = get("montant_lcy")
            if montant_lcy_raw is None or str(montant_lcy_raw).strip() == "":
                raise ValueError("montant_lcy est obligatoire.")
            montant_lcy = int(float(montant_lcy_raw))

            # Sens
            sens_raw = str(get("sens") or "actif").strip().lower()
            if sens_raw not in VALID_SENS:
                raise ValueError(f"sens invalide : {sens_raw!r}. Attendu : {sorted(VALID_SENS)}.")

            # Type taux
            type_taux_raw = str(get("type_taux") or "fixe").strip().lower()
            if type_taux_raw not in VALID_TYPE_TAUX:
                type_taux_raw = "fixe"

            # Montant FCY
            montant_fcy_raw = get("montant_fcy")
            montant_fcy = int(float(montant_fcy_raw)) if montant_fcy_raw not in (None, "") else 0

            # Taux moyen
            taux_raw = get("taux_moyen")
            taux_moyen = float(taux_raw) if taux_raw not in (None, "") else 0.0

            # Maturité
            maturite = _parse_date(get("maturite"))

            obj = BalanceSheetLine(
                date_arrete=date_arrete,
                compte_gl=compte_gl,
                libelle=str(get("libelle") or "").strip(),
                product_code=str(get("product_code") or "").strip(),
                client_id=str(get("client_id") or "").strip(),
                client_name=str(get("client_name") or "").strip(),
                business_unit=str(get("business_unit") or "").strip(),
                segment=str(get("segment") or "").strip(),
                sous_segment=str(get("sous_segment") or "").strip(),
                secteur=str(get("secteur") or "").strip(),
                devise=str(get("devise") or "XAF").strip()[:3],
                montant_lcy=montant_lcy,
                montant_fcy=montant_fcy,
                sens=sens_raw,
                type_taux=type_taux_raw,
                taux_moyen=taux_moyen,
                maturite=maturite,
                bucket_liquidite=str(get("bucket_liquidite") or "").strip(),
                bucket_repricing=str(get("bucket_repricing") or "").strip(),
                entite=str(get("entite") or "").strip(),
                agence=str(get("agence") or "").strip(),
                source=str(get("source") or "flexcube").strip(),
            )
            objects.append(obj)
            dates_seen.add(date_arrete)

        except Exception as e:  # noqa: BLE001
            r.errors.append(f"Ligne {row_idx} : {e}")
            r.skipped += 1

    with transaction.atomic():
        if replace and dates_seen:
            BalanceSheetLine.objects.filter(date_arrete__in=dates_seen).delete()
        if objects:
            BalanceSheetLine.objects.bulk_create(objects, batch_size=500)
            r.inserted = len(objects)

    workbook.close()
    report.sheets.append(r)
    return report
