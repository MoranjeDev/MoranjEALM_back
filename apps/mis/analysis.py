"""
Moteur d'analyse MIS — tableau croisé BU / segment / sous-segment / secteur.

Source : BalanceSheetLine enrichi via ClientMapping.
Pour chaque cellule du tableau croisé, calcule :
- Encours actif moyen et passif moyen (LCY)
- WAR (Weighted Asset Rate)
- COF (Cost of Funds)
- NIM = WAR - COF
- Gap de liquidité (si disponible)
- Nombre de lignes
"""
from __future__ import annotations

from django.db.models import Sum

from apps.balance_sheet.models import BalanceSheetLine


def compute_mis_analysis(
    group_by: str = "business_unit",   # "business_unit" | "segment" | "sous_segment" | "secteur" | "devise" | "entite"
    sens_filter: str = "both",         # "actif" | "passif" | "both"
    date_arrete: str | None = None,
    business_unit: str | None = None,
    segment: str | None = None,
    sous_segment: str | None = None,
    devise: str | None = None,
) -> dict:
    """
    Calcule le tableau MIS croisé selon la dimension demandée.

    Retourne :
    {
      "group_by": "business_unit",
      "date_arrete": "2024-12-31",
      "filters": {...},
      "rows": [
        {
          "dimension": "Retail Banking",
          "actif_lcy": 45000000000,
          "passif_lcy": 38000000000,
          "gap_lcy": 7000000000,
          "war": 8.5,
          "cof": 4.1,
          "nim": 4.4,
          "share_actif_pct": 35.2,
          "nb_lignes": 1250,
        },
        ...
      ],
      "totals": { "actif_lcy": ..., "passif_lcy": ..., "gap_lcy": ...,
                  "war": ..., "cof": ..., "nim": ..., "nb_lignes": ... },
      "nb_rows": 5,
    }
    """
    from datetime import date as date_cls

    # Résoudre la date d'arrêté
    if date_arrete:
        arrete = date_cls.fromisoformat(date_arrete)
    else:
        arrete = (
            BalanceSheetLine.objects
            .order_by("-date_arrete")
            .values_list("date_arrete", flat=True)
            .first()
        )
        if arrete is None:
            return {
                "error": (
                    "Aucune donnée de bilan GL. "
                    "Importez d'abord le bilan via /api/balance-sheet/import/."
                ),
                "rows": [],
            }

    # Valider group_by
    valid_groups = ["business_unit", "segment", "sous_segment", "secteur", "devise", "entite"]
    if group_by not in valid_groups:
        group_by = "business_unit"

    # Filtres de base
    qs = BalanceSheetLine.objects.filter(date_arrete=arrete)
    if business_unit:
        qs = qs.filter(business_unit=business_unit)
    if segment:
        qs = qs.filter(segment=segment)
    if sous_segment:
        qs = qs.filter(sous_segment=sous_segment)
    if devise:
        qs = qs.filter(devise=devise)

    # Exclure les lignes sans valeur pour la dimension demandée
    qs = qs.exclude(**{group_by: ""})

    def _war(qs_subset) -> float:
        """Taux moyen pondéré par montant LCY (Weighted Average Rate)."""
        total_m = 0
        total_p = 0.0
        for row in qs_subset.values("montant_lcy", "taux_moyen"):
            m = row["montant_lcy"] or 0
            t = row["taux_moyen"] or 0
            total_m += m
            total_p += m * t
        return round(total_p / total_m, 4) if total_m > 0 else 0.0

    # Agrégation par dimension
    dimensions = (
        qs.values_list(group_by, flat=True)
        .distinct()
        .order_by(group_by)
    )
    rows = []
    for dim_val in dimensions:
        qs_dim = qs.filter(**{group_by: dim_val})
        qs_actif = qs_dim.filter(sens="actif")
        qs_passif = qs_dim.filter(sens="passif")

        actif_lcy = qs_actif.aggregate(t=Sum("montant_lcy"))["t"] or 0
        passif_lcy = qs_passif.aggregate(t=Sum("montant_lcy"))["t"] or 0
        nb_lignes = qs_dim.count()

        war = _war(qs_actif)
        cof = _war(qs_passif)

        rows.append({
            "dimension": dim_val,
            "actif_lcy": actif_lcy,
            "passif_lcy": passif_lcy,
            "gap_lcy": actif_lcy - passif_lcy,
            "war": war,
            "cof": cof,
            "nim": round(war - cof, 4),
            "nb_lignes": nb_lignes,
        })

    # Trier par actif décroissant
    rows.sort(key=lambda x: x["actif_lcy"], reverse=True)

    # Totaux
    total_actif = sum(r["actif_lcy"] for r in rows)
    total_passif = sum(r["passif_lcy"] for r in rows)
    total_nb = sum(r["nb_lignes"] for r in rows)

    # WAR / COF globaux
    war_global = _war(qs.filter(sens="actif"))
    cof_global = _war(qs.filter(sens="passif"))

    # Ajouter parts de marché actif
    for r in rows:
        r["share_actif_pct"] = (
            round(r["actif_lcy"] / total_actif * 100, 2) if total_actif else 0.0
        )

    return {
        "group_by": group_by,
        "date_arrete": str(arrete),
        "filters": {
            "business_unit": business_unit,
            "segment": segment,
            "devise": devise,
        },
        "rows": rows,
        "totals": {
            "actif_lcy": total_actif,
            "passif_lcy": total_passif,
            "gap_lcy": total_actif - total_passif,
            "war": war_global,
            "cof": cof_global,
            "nim": round(war_global - cof_global, 4),
            "nb_lignes": total_nb,
        },
        "nb_rows": len(rows),
    }


def compute_mis_export_excel(
    group_by: str = "business_unit",
    date_arrete: str | None = None,
):
    """Génère un fichier Excel (openpyxl Workbook) avec les données MIS."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    data = compute_mis_analysis(group_by=group_by, date_arrete=date_arrete)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MIS"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)

    headers = [
        "Dimension", "Actif LCY", "Passif LCY", "Gap LCY",
        "WAR (%)", "COF (%)", "NIM (%)", "Part Actif (%)", "Nb lignes",
    ]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for row_idx, row in enumerate(data.get("rows", []), 2):
        ws.cell(row=row_idx, column=1, value=row["dimension"])
        ws.cell(row=row_idx, column=2, value=row["actif_lcy"])
        ws.cell(row=row_idx, column=3, value=row["passif_lcy"])
        ws.cell(row=row_idx, column=4, value=row["gap_lcy"])
        ws.cell(row=row_idx, column=5, value=row["war"])
        ws.cell(row=row_idx, column=6, value=row["cof"])
        ws.cell(row=row_idx, column=7, value=row["nim"])
        ws.cell(row=row_idx, column=8, value=row["share_actif_pct"])
        ws.cell(row=row_idx, column=9, value=row["nb_lignes"])

    # Ligne totaux
    totals = data.get("totals", {})
    last = len(data.get("rows", [])) + 2
    total_cells = [
        "TOTAL",
        totals.get("actif_lcy", 0),
        totals.get("passif_lcy", 0),
        totals.get("gap_lcy", 0),
        totals.get("war", 0),
        totals.get("cof", 0),
        totals.get("nim", 0),
        100.0,
        totals.get("nb_lignes", 0),
    ]
    for col, val in enumerate(total_cells, 1):
        cell = ws.cell(row=last, column=col, value=val)
        cell.font = Font(bold=True)

    ws.column_dimensions["A"].width = 30
    for col in range(2, 10):
        ws.column_dimensions[
            ws.cell(row=1, column=col).column_letter
        ].width = 18

    return wb
