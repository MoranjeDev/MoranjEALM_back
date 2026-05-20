"""Vues d'import Excel et de génération du template."""
from datetime import datetime
from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from apps.tracking.models import Tracking
from .import_service import import_workbook
from .models import INPUT_LABELS, INPUT_MODELS
from .sample_data import SAMPLE_DATA


# ===========================================================================
# Styles partagés pour le template Excel
# ===========================================================================
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HINT_FONT = Font(name="Calibri", size=9, italic=True, color="595959")
DATA_FONT = Font(name="Calibri", size=11)
TITLE_FONT = Font(name="Calibri", size=18, bold=True, color="1F3864")
H2_FONT = Font(name="Calibri", size=13, bold=True, color="2E74B5")
THIN = Side(border_style="thin", color="BFBFBF")
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)


def _add_readme_sheet(wb, with_sample: bool):
    """Ajoute une feuille README en première position."""
    ws = wb.create_sheet(title="README", index=0)
    ws.column_dimensions["A"].width = 95
    ws.sheet_properties.tabColor = "1F3864"

    rows = [
        ("Template d'import des inputs ALM", TITLE_FONT),
        ("", None),
        (
            f"Type : {'Données de test bancaires réalistes' if with_sample else 'Vide (à remplir par le client)'}",
            H2_FONT,
        ),
        (f"Généré le : {datetime.now().strftime('%d/%m/%Y %H:%M')}", None),
        ("", None),
        ("Mode d'emploi", H2_FONT),
        ("Ce classeur contient une feuille par type d'input ALM. Chaque feuille a :", None),
        ("  • La ligne 1 (en-tête bleue) : noms des colonnes attendus par l'application.", None),
        ("  • La ligne 2 (italique gris) : type de chaque champ (DateTimeField, FloatField, BigIntegerField, etc.).", None),
        ("  • À partir de la ligne 3 : vos données (ou les données de test si vous les avez demandées).", None),
        ("", None),
        ("Règles de saisie", H2_FONT),
        ("  • Dates : format AAAA-MM-JJ ou JJ/MM/AAAA (ex : 2026-05-08).", None),
        ("  • Nombres : pas de séparateurs de milliers, point pour les décimales (ex : 1500000.50).", None),
        ("  • Texte : éviter les retours à la ligne, ils peuvent perturber l'import.", None),
        ("  • Champs obligatoires : tous sauf ceux marqués « optional » dans le type.", None),
        ("  • Devises : codes ISO 4217 (XAF, EUR, USD).", None),
        ("  • Fréquences : MENSUEL, BIMENSUEL, TRIMESTRIEL, SEMESTRIEL, ANNUEL, IN_FINE.", None),
        ("", None),
        ("Importer le fichier", H2_FONT),
        ("  1. Connectez-vous à l'application avec votre compte.", None),
        ("  2. Allez dans « Import Excel ».", None),
        ("  3. Sélectionnez ce fichier et cliquez sur « Importer ».", None),
        ("  4. Cochez « Remplacer les données existantes » uniquement si vous", None),
        ("     voulez écraser les données déjà saisies pour les feuilles importées.", None),
        ("  5. Le rapport d'import affiche, par feuille, le nombre de lignes insérées et les éventuelles erreurs.", None),
        ("", None),
        ("Liste des feuilles", H2_FONT),
    ]
    for kind, _model in INPUT_MODELS.items():
        label, side = INPUT_LABELS.get(kind, (kind, "actif"))
        n_sample = len(SAMPLE_DATA.get(kind, [])) if with_sample else 0
        sample_info = f" — {n_sample} ligne(s) de test" if n_sample else ""
        rows.append((
            f"  • {kind:<20} {label} ({'Actif' if side == 'actif' else 'Passif'}){sample_info}",
            None,
        ))

    rows += [
        ("", None),
        ("Support", H2_FONT),
        ("En cas de difficulté, contactez votre administrateur ou le support de l'éditeur.", None),
    ]

    for i, (text, font) in enumerate(rows, start=1):
        cell = ws.cell(row=i, column=1, value=text)
        if font:
            cell.font = font


def _build_workbook(with_sample: bool = False) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    _add_readme_sheet(wb, with_sample)

    for kind, model in INPUT_MODELS.items():
        label, side = INPUT_LABELS.get(kind, (kind, "actif"))
        ws = wb.create_sheet(title=kind)
        ws.sheet_properties.tabColor = "2E74B5" if side == "actif" else "C62828"

        # Champs (sans id, created_at, updated_at)
        fields = [
            f for f in model._meta.fields
            if f.name not in ("id", "created_at", "updated_at")
        ]
        headers = [f.name for f in fields]
        types = [f.get_internal_type() for f in fields]

        # Ligne 1 : en-tête stylée
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = BORDER

        # Ligne 2 : type de champ (aide visuelle)
        for col_idx, t in enumerate(types, start=1):
            cell = ws.cell(row=2, column=col_idx, value=t)
            cell.font = HINT_FONT
            cell.alignment = Alignment(horizontal="center")
            cell.border = BORDER

        # Données : sample ou vide
        if with_sample and kind in SAMPLE_DATA:
            for row_idx, sample in enumerate(SAMPLE_DATA[kind], start=3):
                for col_idx, fname in enumerate(headers, start=1):
                    val = sample.get(fname)
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.font = DATA_FONT
                    if isinstance(val, datetime):
                        cell.number_format = "YYYY-MM-DD"

        # Largeur des colonnes
        for col_idx, h in enumerate(headers, start=1):
            ws.column_dimensions[get_column_letter(col_idx)].width = max(len(h) + 2, 14)

        # Geler la première ligne d'aide + en-têtes
        ws.freeze_panes = "A3"

        # Commentaire d'aide sur la première cellule
        ws["A1"].comment = openpyxl.comments.Comment(
            f"{label} ({'Actif' if side == 'actif' else 'Passif'})",
            "ALM",
        )

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ===========================================================================
# Vues
# ===========================================================================
class ExcelImportView(APIView):
    """POST multipart : `file` = classeur Excel ; `replace` = "1" optionnel ; `kinds` = liste optionnelle."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Importation des données"
    parser_classes = [MultiPartParser]

    def post(self, request):
        if "file" not in request.FILES:
            return Response(
                {"detail": "Le fichier Excel est requis (champ « file »)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = request.FILES["file"]
        replace = request.data.get("replace") in ("1", "true", "True")
        kinds_raw = request.data.get("kinds")
        kinds = [k.strip() for k in kinds_raw.split(",")] if kinds_raw else None

        try:
            report = import_workbook(file_obj.file, kinds=kinds, replace=replace)
        except Exception as e:  # noqa: BLE001
            return Response(
                {"detail": f"Échec de la lecture du classeur : {e}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        Tracking.objects.create(
            libelle="Import Excel",
            description=(
                f"Fichier {file_obj.name}, {report.total_inserted} ligne(s) "
                f"insérée(s), {report.total_errors} erreur(s)."
            ),
            utilisateur=request.user,
        )

        return Response({
            "filename": file_obj.name,
            "total_inserted": report.total_inserted,
            "total_errors": report.total_errors,
            "sheets": [
                {
                    "kind": s.kind,
                    "inserted": s.inserted,
                    "skipped": s.skipped,
                    "errors": s.errors,
                }
                for s in report.sheets
            ],
        })


class ExcelTemplateView(APIView):
    """
    GET : génère un classeur Excel modèle.

    Query params :
      - with_sample = "1" : inclut un jeu de données de test (par défaut : vide)
    """
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Importation des données"

    def get(self, request):
        with_sample = request.query_params.get("with_sample") in ("1", "true", "True")
        content = _build_workbook(with_sample=with_sample)
        filename = (
            "template_inputs_alm_donnees_test_realistes.xlsx"
            if with_sample
            else "template_inputs_alm_vide.xlsx"
        )

        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
